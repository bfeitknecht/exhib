"""The gallery editor on the web: the `just manifest` editor, run in the cluster.

Same page and manifest code as the local tool (tools/manifest). Here it works
on the PVC instead of a folder on the Mac:

- Every item is a slug. A published item lives in /data/originals/<kind>/<slug>
  (the upload as it was published). Opening it makes a draft in
  /data/drafts/<slug>: manifest and body copied, media files as hard links
  (no extra disk, the original is never written).
- `new` makes an empty draft. Files upload into the draft; `delete file`
  removes a file from the draft only.
- save writes manifest.toml into the draft (as the local tool does).
- publish moves the draft into /data/incoming with a `.replace` marker. The
  processor builds the new version, swaps it in, and moves files that the
  new version dropped to /data/trash. A failed publish comes back as the
  draft, with the error.
- discard deletes the draft. The published item stays.

Access: Traefik sends /upload here only after authentik forward auth (app
bound to one user). This server checks X-authentik-username again
(UPLOAD_USER) and the Origin of every write. A network policy lets only
Traefik reach the port. Stdlib only, plus ffmpeg/exiftool from the image.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import tomllib
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools/manifest/src"))

from exhib_manifest import manifest  # noqa: E402
from exhib_manifest.server import PAGE, Handler  # noqa: E402

from processor.media import decode_upright  # noqa: E402
from processor.paths import DATA, INCOMING, ORIGINALS  # noqa: E402

PORT = int(os.environ.get("UPLOAD_PORT", "8081"))
USER = os.environ.get("UPLOAD_USER", "bf")
ORIGIN = os.environ.get("UPLOAD_ORIGIN", "https://gallery.0xbf.ch")
MAX_FILE = int(os.environ.get("UPLOAD_MAX_FILE_BYTES", str(8 * 1024**3)))
PREFIX = "/upload"
DRAFTS = DATA / "drafts"
PREVIEWS = DATA / ".previews"
CHUNK = 1024 * 1024
KINDS = manifest.KINDS
# Previews run ffmpeg. A grid asks for 30 at once; two at a time keeps the Pi usable.
PREVIEW_SLOTS = threading.BoundedSemaphore(2)
LOCK = threading.Lock()


def published_kind(slug: str) -> str | None:
    for kind in KINDS:
        if (ORIGINALS / kind / slug).is_dir():
            return kind
    return None


def draft_kind(folder: Path) -> str | None:
    try:
        return tomllib.loads((folder / "manifest.toml").read_text())["kind"]
    except OSError, ValueError, KeyError:
        return None


def check_slug(slug: str) -> str:
    if not manifest.SLUG.fullmatch(slug or ""):
        raise ValueError("slug: lowercase letters, digits and hyphens")
    return slug


def visible_dirs(root: Path) -> list[Path]:
    return (
        [p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]
        if root.is_dir()
        else []
    )


def list_items() -> list[dict]:
    names: set[str] = {p.name for p in visible_dirs(DRAFTS)}
    for kind in KINDS:
        names |= {p.name for p in visible_dirs(ORIGINALS / kind)}
    queued = {p.name for p in visible_dirs(INCOMING)}
    names |= queued
    items = []
    for name in sorted(names, key=manifest.natural_key, reverse=True):
        draft = DRAFTS / name
        kind = published_kind(name)
        if name in queued:
            status = "publishing…"
        elif draft.is_dir():
            status = (
                "draft · last publish failed"
                if (draft / ".error").is_file()
                else "draft"
            )
        else:
            status = "published"
        items.append(
            {
                "name": name,
                "slug_ok": bool(manifest.SLUG.fullmatch(name)),
                "has_manifest": (draft / "manifest.toml").is_file() or kind is not None,
                "draft": draft.is_dir(),
                "kind": (draft_kind(draft) if draft.is_dir() else None) or kind,
                "status": status,
            }
        )
    return items


def ensure_draft(slug: str) -> Path:
    """The draft folder of slug; made from the published original if needed."""
    draft = DRAFTS / check_slug(slug)
    with LOCK:
        if draft.is_dir():
            return draft
        if (INCOMING / slug).exists():
            raise ValueError(f"{slug} is being published; wait a minute")
        kind = published_kind(slug)
        if kind is None:
            raise FileNotFoundError(f"no item {slug}")
        DRAFTS.mkdir(parents=True, exist_ok=True)
        tmp = DRAFTS / f".new-{slug}"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        for path in (ORIGINALS / kind / slug).iterdir():
            if not path.is_file() or path.name.startswith("."):
                continue
            if manifest.media_type(path):
                os.link(
                    path, tmp / path.name
                )  # never written: the editor only adds or unlinks
            else:
                shutil.copy2(path, tmp / path.name)
        tmp.rename(draft)
        return draft


class WebEditor(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("0.0.0.0", PORT), WebHandler)
        self.root = DRAFTS
        self.previews = PREVIEWS


class WebHandler(Handler):
    server: WebEditor

    def log_message(self, format: str, *args) -> None:
        sys.stderr.write("upload: " + (format % args) + "\n")

    def send(
        self, status: int, body: bytes, content_type: str, cache: str = "no-store"
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(body)

    def error(self, status: int, message: str) -> None:
        self.send_json(status, {"error": message})

    def allowed(self, write: bool) -> bool:
        if self.headers.get("X-authentik-username") != USER:
            self.error(HTTPStatus.FORBIDDEN, "forbidden")
            return False
        if write and self.headers.get("Origin") != ORIGIN:
            self.error(HTTPStatus.FORBIDDEN, "bad origin")
            return False
        return True

    def route(self) -> str | None:
        path = unquote(urlparse(self.path).path)
        if path == PREFIX:
            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", PREFIX + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        if not path.startswith(PREFIX + "/"):
            self.not_found()
            return None
        return path.removeprefix(PREFIX)

    def query(self, key: str) -> str:
        return parse_qs(urlparse(self.path).query).get(key, [""])[0]

    def folder(self) -> Path:
        return manifest.child(DRAFTS, self.query("f"))

    # ── GET ──────────────────────────────────────────────────────────
    def do_GET(self) -> None:
        if not self.allowed(write=False) or (path := self.route()) is None:
            return
        try:
            if path == "/":
                self.send(HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/folders":
                self.send_json(
                    HTTPStatus.OK,
                    {"root": "gallery", "web": True, "folders": list_items()},
                )
            elif path == "/api/state":
                folder = self.folder()
                state = manifest.load_state(folder)
                error = folder / ".error"
                state["folder"] = folder.name
                state["web"] = {
                    "published": published_kind(folder.name),
                    "error": error.read_text().strip() if error.is_file() else "",
                }
                self.send_json(HTTPStatus.OK, state)
            elif path.startswith("/media/"):
                self.send_media(*path.removeprefix("/media/").split("/", 1))
            else:
                self.not_found()
        except ValueError, TypeError, FileNotFoundError:
            self.not_found()

    def send_media(self, slug: str, name: str = "") -> None:
        folder = manifest.child(DRAFTS, slug)
        source = {p.name: p for p in manifest.media_files(folder)}.get(name)
        if source is None:
            self.not_found()
            return
        if manifest.media_type(source) == "image":
            preview = self.preview(slug, source)
            if preview is None:
                self.not_found()
                return
            self.send(
                HTTPStatus.OK,
                preview.read_bytes(),
                "image/jpeg",
                cache="private, max-age=600",
            )
        else:
            self.stream(source)

    def preview(self, slug: str, source: Path) -> Path | None:
        """An upright JPEG, at most 1600 px: what the processor decodes, smaller.

        The editor crops and rotates on this picture, so it must be upright
        like the processor's input (decode_upright). Cached by file identity.
        """
        stat = source.stat()
        target = PREVIEWS / slug / f"{source.name}.{stat.st_ino}-{stat.st_mtime_ns}.jpg"
        if target.is_file():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        with PREVIEW_SLOTS:
            if target.is_file():
                return target
            upright = target.with_name(f".{target.name}.png")
            try:
                decode_upright(source, upright)
                subprocess.run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(upright),
                        "-vf",
                        "scale='min(1600,iw)':'min(1600,ih)':force_original_aspect_ratio=decrease",
                        "-q:v",
                        "4",
                        "-frames:v",
                        "1",
                        str(target),
                    ],
                    check=True,
                )
            except subprocess.CalledProcessError, OSError:
                return None
            finally:
                upright.unlink(missing_ok=True)
        for old in target.parent.glob(source.name + ".*.jpg"):
            if old != target:
                old.unlink(missing_ok=True)
        return target

    def stream(self, source: Path) -> None:
        """Videos as files, with byte ranges (Safari plays video only with ranges)."""
        size = source.stat().st_size
        start, end = 0, size - 1
        ranged = self.headers.get("Range", "")
        if ranged.startswith("bytes="):
            first, _, last = ranged.removeprefix("bytes=").split(",")[0].partition("-")
            try:
                if first:
                    start, end = int(first), int(last) if last else size - 1
                else:
                    start, end = max(0, size - int(last)), size - 1
            except ValueError:
                start, end = 0, size - 1
            end = min(end, size - 1)
            if start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        self.send_response(HTTPStatus.PARTIAL_CONTENT if ranged else HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            "video/quicktime"
            if source.suffix.lower() == ".mov"
            else "video/mp4"
            if source.suffix.lower() in {".mp4", ".m4v"}
            else "application/octet-stream",
        )
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if ranged:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "private, max-age=600")
        self.end_headers()
        with source.open("rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(CHUNK, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except BrokenPipeError, ConnectionResetError:
                    return
                left -= len(chunk)

    # ── POST ─────────────────────────────────────────────────────────
    def do_POST(self) -> None:
        if not self.allowed(write=True) or (path := self.route()) is None:
            return
        actions = {
            "/api/save": self.save,
            "/api/open": self.open_draft,
            "/api/new": self.new,
            "/api/publish": self.publish,
            "/api/discard": self.discard,
            "/api/delete": self.delete,
        }
        action = actions.get(path)
        if action is None:
            self.not_found()
            return
        try:
            action()
        except FileNotFoundError as exc:
            self.error(HTTPStatus.NOT_FOUND, str(exc))
        except (ValueError, KeyError, TypeError) as exc:
            self.error(HTTPStatus.BAD_REQUEST, str(exc))

    def save(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        if length > 4 * 1024 * 1024:
            raise ValueError("request too large")
        folder = self.folder()
        text = manifest.save(folder, json.loads(self.rfile.read(length)))
        self.send_json(HTTPStatus.OK, {"manifest": text})

    def open_draft(self) -> None:
        ensure_draft(self.query("f"))
        self.send_json(HTTPStatus.OK, {"ok": True})

    def new(self) -> None:
        slug = check_slug(self.query("f"))
        with LOCK:
            if (
                (DRAFTS / slug).exists()
                or (INCOMING / slug).exists()
                or published_kind(slug)
            ):
                raise ValueError(f"{slug} exists already: open it instead")
            (DRAFTS / slug).mkdir(parents=True)
        self.send_json(HTTPStatus.CREATED, {"ok": True})

    def publish(self) -> None:
        folder = self.folder()
        slug = folder.name
        data = tomllib.loads((folder / "manifest.toml").read_text())  # save first
        if data.get("kind") not in KINDS:
            raise ValueError("manifest.toml has no valid kind")
        if data["kind"] != "writing" and not manifest.media_files(folder):
            raise ValueError("no media files")
        with LOCK:
            if (INCOMING / slug).exists():
                raise ValueError(f"{slug} is being published already")
            (folder / ".error").unlink(missing_ok=True)
            old = published_kind(slug)
            marker = folder / ".replace"
            if old:
                marker.write_text(old + "\n")
            else:
                marker.unlink(missing_ok=True)
            INCOMING.mkdir(parents=True, exist_ok=True)
            folder.rename(INCOMING / slug)
        shutil.rmtree(PREVIEWS / slug, ignore_errors=True)
        self.send_json(HTTPStatus.OK, {"ok": True, "queued": slug})

    def discard(self) -> None:
        folder = self.folder()
        with LOCK:
            shutil.rmtree(folder)
        shutil.rmtree(PREVIEWS / folder.name, ignore_errors=True)
        self.send_json(HTTPStatus.OK, {"ok": True})

    def delete(self) -> None:
        folder = self.folder()
        name = self.query("name")
        source = {p.name: p for p in manifest.media_files(folder)}.get(name)
        if source is None:
            raise FileNotFoundError(f"no file {name}")
        source.unlink()
        self.send_json(HTTPStatus.OK, {"ok": True})

    # ── PUT: one file into a draft, streamed ─────────────────────────
    def do_PUT(self) -> None:
        if not self.allowed(write=True) or (path := self.route()) is None:
            return
        if path != "/api/file":
            self.not_found()
            return
        try:
            folder = self.folder()
        except ValueError:
            self.error(HTTPStatus.NOT_FOUND, "unknown draft")
            return
        name = self.query("name")
        if (
            not manifest.media_type(Path(name))
            or "/" in name
            or "\\" in name
            or name.startswith(".")
            or len(name) > 200
        ):
            self.error(HTTPStatus.BAD_REQUEST, f"not a supported media file: {name}")
            return
        length = int(self.headers.get("Content-Length") or -1)
        if length < 0 or length > MAX_FILE:
            self.error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "file too large or no length"
            )
            return
        target = folder / name
        if target.exists():
            self.error(HTTPStatus.CONFLICT, f"{name} is already in this item")
            return
        partial = folder / f".{name}.part"
        with partial.open("wb") as out:
            left = length
            while left > 0:
                chunk = self.rfile.read(min(CHUNK, left))
                if not chunk:
                    break
                out.write(chunk)
                left -= len(chunk)
        if left:
            partial.unlink(missing_ok=True)
            self.error(HTTPStatus.BAD_REQUEST, "upload interrupted")
            return
        partial.rename(target)
        self.send_json(HTTPStatus.CREATED, {"ok": True, "file": name})


def main() -> int:
    DRAFTS.mkdir(parents=True, exist_ok=True)
    for stale in DRAFTS.glob(".new-*"):
        shutil.rmtree(stale, ignore_errors=True)
    for part in DRAFTS.glob("*/.*.part"):
        part.unlink(missing_ok=True)
    # Drafts of the old web uploader (.upload-web-*) are dropped.
    for stale in INCOMING.glob(".upload-web-*"):
        shutil.rmtree(stale, ignore_errors=True)
    server = WebEditor()
    print(f"upload: gallery editor on :{PORT} for {USER}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
