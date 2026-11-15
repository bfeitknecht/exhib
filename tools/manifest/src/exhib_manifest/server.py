"""Localhost HTTP server for the manifest editor. Standard library only.

The server owns one root folder (uploads/). Requests name a slug folder
with ?f=<name>; only direct, visible child folders of the root resolve.
"""

from __future__ import annotations

import json
import mimetypes
import shutil
import subprocess
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import manifest

PAGE = Path(__file__).with_name("index.html")
# Browsers cannot show these. On macOS, sips makes a JPEG preview.
NEEDS_PREVIEW = {".heic", ".heif", ".tif", ".tiff"}


class Editor(ThreadingHTTPServer):
    def __init__(self, root: Path, port: int) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.root = root
        self.previews = Path(tempfile.mkdtemp(prefix="exhib-manifest-"))

    def server_close(self) -> None:
        super().server_close()
        shutil.rmtree(self.previews, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    server: Editor

    def log_message(self, format: str, *args) -> None:
        pass

    def send(
        self, status: int, body: bytes, content_type: str, cache: str = "no-store"
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, value: object) -> None:
        self.send(status, json.dumps(value).encode(), "application/json")

    def not_found(self) -> None:
        self.send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")

    def folder(self) -> Path:
        name = parse_qs(urlparse(self.path).query).get("f", [""])[0]
        return manifest.child(self.server.root, name)

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/":
                page = PAGE.read_bytes()
                self.send(HTTPStatus.OK, page, "text/html; charset=utf-8")
            elif path == "/api/folders":
                root = self.server.root
                folders = manifest.list_folders(root)
                self.send_json(HTTPStatus.OK, {"root": root.name, "folders": folders})
            elif path == "/api/state":
                self.send_json(HTTPStatus.OK, manifest.load_state(self.folder()))
            elif path.startswith("/media/"):
                self.send_media(*path.removeprefix("/media/").split("/", 1))
            else:
                self.not_found()
        except ValueError, TypeError:
            self.not_found()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/save":
            self.not_found()
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            folder = self.folder()
            data = json.loads(self.rfile.read(length))
            text = manifest.save(folder, data)
        except (ValueError, KeyError, TypeError) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        print(f"Saved {folder / 'manifest.toml'}", flush=True)
        self.send_json(HTTPStatus.OK, {"manifest": text})

    def send_media(self, slug: str, name: str = "") -> None:
        # Serve only files the editor lists. No other path is reachable.
        folder = manifest.child(self.server.root, slug)
        source = {p.name: p for p in manifest.media_files(folder)}.get(name)
        if source is None:
            self.not_found()
            return
        if source.suffix.lower() in NEEDS_PREVIEW:
            source = self.preview(slug, source) or source
        content_type = mimetypes.guess_type(source.name)[0]
        self.send(
            HTTPStatus.OK,
            source.read_bytes(),
            content_type or "application/octet-stream",
            cache="private, max-age=600",
        )

    def preview(self, slug: str, source: Path) -> Path | None:
        target = self.server.previews / slug / (source.name + ".jpg")
        if target.is_file():
            return target
        if not shutil.which("sips"):
            return None
        target.parent.mkdir(exist_ok=True)
        result = subprocess.run(
            ["sips", "-s", "format", "jpeg", "-Z", "1600", str(source)]
            + ["--out", str(target)],
            check=False,
            capture_output=True,
        )
        return target if result.returncode == 0 and target.is_file() else None
