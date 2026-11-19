"""Web uploader for the gallery: drag and drop from any device, no terminal.

It does what `just upload` does. Files stream into a hidden staging folder in
/data/incoming. On finish it writes manifest.toml (and body.md for a writing)
and renames the folder to /data/incoming/<slug> in one step. The processor
takes it from there. The published site stays static: this server only ever
writes into the inbox.

Access: Traefik sends /upload here only after authentik forward auth (app
bound to one user). This server checks the X-authentik-username header again
(UPLOAD_USER) and the Origin of every write. A network policy lets only
Traefik reach the port.

Stdlib only. Routes, all under /upload:
  GET  /upload/                      the page
  GET  /upload/api/queue             slugs waiting in the inbox
  POST /upload/api/start             JSON manifest fields -> {"id": ...}
  PUT  /upload/api/<id>/files/<name> raw file body (streamed)
  POST /upload/api/<id>/finish       write manifest, publish to the inbox
  POST /upload/api/<id>/abort        drop the staging folder
"""

import json
import os
import re
import secrets
import shutil
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from processor.paths import INCOMING

PORT = int(os.environ.get("UPLOAD_PORT", "8081"))
USER = os.environ.get("UPLOAD_USER", "bf")
ORIGIN = os.environ.get("UPLOAD_ORIGIN", "https://gallery.0xbf.ch")
MAX_FILE = int(os.environ.get("UPLOAD_MAX_FILE_BYTES", str(8 * 1024**3)))
CHUNK = 1024 * 1024
STAGING_PREFIX = ".upload-web-"

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
KINDS = {"collection", "piece", "writing"}
MEDIA = {
    "jpg",
    "jpeg",
    "png",
    "webp",
    "avif",
    "tif",
    "tiff",
    "heic",
    "heif",
    "mov",
    "mp4",
    "m4v",
    "3gp",
    "mkv",
    "webm",
}
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,200}$")
PAGE = Path(__file__).with_name("index.html")

# Upload id -> {"dir": Path, "slug": str, "fields": dict}. One replica, so
# memory is enough; a restart drops unfinished uploads (staging is cleaned).
SESSIONS: dict[str, dict] = {}
LOCK = threading.Lock()


def toml_str(value: str) -> str:
    # A JSON string is a valid TOML basic string.
    return json.dumps(value, ensure_ascii=False)


def toml_date(value: str) -> str:
    # The page sends datetime-local ("2026-11-19T18:30") in the browser's
    # time zone with the offset ("+01:00"); store it in UTC like the editor.
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def manifest(fields: dict) -> str:
    lines = [
        f"kind = {toml_str(fields['kind'])}",
        f"title = {toml_str(fields['title'])}",
        f"date = {toml_date(fields['date'])}",
    ]
    if fields.get("description"):
        lines.append(f"description = {toml_str(fields['description'])}")
    tags = [t for t in fields.get("tags", []) if t]
    if tags:
        lines.append("tags = [" + ", ".join(toml_str(t) for t in tags) + "]")
    if fields["kind"] != "writing" and fields.get("sort") in {"date", "position"}:
        lines.append(f"sort = {toml_str(fields['sort'])}")
    return "\n".join(lines) + "\n"


def validate(fields: dict) -> str | None:
    if not SLUG.match(fields.get("slug", "")):
        return "slug: lowercase letters, numbers and hyphens"
    if fields.get("kind") not in KINDS:
        return "kind: collection, piece or writing"
    if not str(fields.get("title", "")).strip():
        return "title is required"
    try:
        toml_date(fields.get("date", ""))
    except TypeError, ValueError:
        return "date is not valid"
    tags = fields.get("tags", [])
    if not isinstance(tags, list) or not all(
        isinstance(t, str) and SLUG.match(t) for t in tags if t
    ):
        return "tags: slug-like names"
    if fields["kind"] == "writing" and not str(fields.get("body", "")).strip():
        return "a writing needs a body"
    return None


def clean_staging() -> None:
    INCOMING.mkdir(parents=True, exist_ok=True)
    for path in INCOMING.glob(STAGING_PREFIX + "*"):
        shutil.rmtree(path, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "exhib-upload"

    def log_message(self, fmt, *args):
        sys.stderr.write("upload: " + (fmt % args) + "\n")

    def reply(
        self, code: int, body: dict | bytes, ctype: str = "application/json"
    ) -> None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(data)

    def allowed(self, write: bool) -> bool:
        if self.headers.get("X-authentik-username") != USER:
            self.reply(403, {"error": "forbidden"})
            return False
        if write and self.headers.get("Origin") != ORIGIN:
            self.reply(403, {"error": "bad origin"})
            return False
        return True

    def read_json(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1024 * 1024:
            return None
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def session(self, sid: str) -> dict | None:
        with LOCK:
            return SESSIONS.get(sid)

    def do_GET(self):
        if not self.allowed(write=False):
            return
        path = self.path.split("?", 1)[0]
        if path in ("/upload", "/upload/"):
            self.reply(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif path == "/upload/api/queue":
            queued = sorted(
                p.name
                for p in INCOMING.iterdir()
                if p.is_dir() and not p.name.startswith(".")
            )
            self.reply(200, {"queued": queued, "user": USER})
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self):
        if not self.allowed(write=True):
            return
        parts = self.path.split("?", 1)[0].strip("/").split("/")
        if parts == ["upload", "api", "start"]:
            return self.start()
        if len(parts) == 4 and parts[:2] == ["upload", "api"] and parts[3] == "finish":
            return self.publish(parts[2])
        if len(parts) == 4 and parts[:2] == ["upload", "api"] and parts[3] == "abort":
            return self.abort(parts[2])
        self.reply(404, {"error": "not found"})

    def do_PUT(self):
        if not self.allowed(write=True):
            return
        parts = self.path.split("?", 1)[0].strip("/").split("/")
        if len(parts) != 5 or parts[:2] != ["upload", "api"] or parts[3] != "files":
            return self.reply(404, {"error": "not found"})
        sess = self.session(parts[2])
        if sess is None:
            return self.reply(404, {"error": "unknown upload"})
        name = unquote(parts[4])
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if not SAFE_NAME.match(name) or ext not in MEDIA:
            return self.reply(400, {"error": f"not a supported media file: {name}"})
        length = int(self.headers.get("Content-Length") or -1)
        if length < 0 or length > MAX_FILE:
            return self.reply(413, {"error": "file too large or no length"})
        target = sess["dir"] / name
        if target.exists():
            return self.reply(409, {"error": f"{name} already uploaded"})
        partial = sess["dir"] / f".{name}.part"
        with partial.open("wb") as out:
            remaining = length
            while remaining > 0:
                chunk = self.rfile.read(min(CHUNK, remaining))
                if not chunk:
                    break
                out.write(chunk)
                remaining -= len(chunk)
        if remaining:
            partial.unlink(missing_ok=True)
            return self.reply(400, {"error": "upload interrupted"})
        partial.rename(target)
        self.reply(201, {"ok": True, "file": name})

    def start(self):
        fields = self.read_json()
        if fields is None:
            return self.reply(400, {"error": "bad request"})
        error = validate(fields)
        if error:
            return self.reply(400, {"error": error})
        slug = fields["slug"]
        if (INCOMING / slug).exists():
            return self.reply(409, {"error": f"'{slug}' is already queued"})
        sid = secrets.token_urlsafe(16)
        staging = INCOMING / f"{STAGING_PREFIX}{slug}-{sid}"
        staging.mkdir(parents=True)
        with LOCK:
            SESSIONS[sid] = {"dir": staging, "slug": slug, "fields": fields}
        self.reply(201, {"id": sid})

    def publish(self, sid: str):
        sess = self.session(sid)
        if sess is None:
            return self.reply(404, {"error": "unknown upload"})
        fields = sess["fields"]
        media = [p for p in sess["dir"].iterdir() if not p.name.startswith(".")]
        if fields["kind"] != "writing" and not media:
            return self.reply(400, {"error": "no files uploaded"})
        (sess["dir"] / "manifest.toml").write_text(manifest(fields))
        if fields["kind"] == "writing":
            (sess["dir"] / "body.md").write_text(fields["body"].rstrip() + "\n")
        dest = INCOMING / sess["slug"]
        if dest.exists():
            return self.reply(409, {"error": f"'{sess['slug']}' is already queued"})
        sess["dir"].rename(dest)
        with LOCK:
            SESSIONS.pop(sid, None)
        self.reply(200, {"ok": True, "queued": sess["slug"], "files": len(media)})

    def abort(self, sid: str):
        with LOCK:
            sess = SESSIONS.pop(sid, None)
        if sess is not None:
            shutil.rmtree(sess["dir"], ignore_errors=True)
        self.reply(200, {"ok": True})


def main() -> int:
    clean_staging()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    print(f"upload: listening on :{PORT} for {USER}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
