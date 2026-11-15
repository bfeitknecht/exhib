"""Localhost HTTP server for the manifest editor. Standard library only."""

from __future__ import annotations

import json
import mimetypes
import shutil
import subprocess
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import manifest

PAGE = Path(__file__).with_name("index.html")
# Browsers cannot show these. On macOS, sips makes a JPEG preview.
NEEDS_PREVIEW = {".heic", ".heif", ".tif", ".tiff"}


class Editor(ThreadingHTTPServer):
    def __init__(self, folder: Path, port: int) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.folder = folder
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

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path == "/":
            self.send(HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/state":
            self.send_json(HTTPStatus.OK, manifest.load_state(self.server.folder))
        elif path.startswith("/media/"):
            self.send_media(path.removeprefix("/media/"))
        else:
            self.send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/save":
            self.send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length))
            text = manifest.save(self.server.folder, data)
        except (ValueError, KeyError, TypeError) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        print(f"Saved {self.server.folder / 'manifest.toml'}", flush=True)
        self.send_json(HTTPStatus.OK, {"manifest": text})

    def send_media(self, name: str) -> None:
        # Serve only files the editor lists. No other path is reachable.
        files = {p.name: p for p in manifest.media_files(self.server.folder)}
        source = files.get(name)
        if source is None:
            self.send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
            return
        if source.suffix.lower() in NEEDS_PREVIEW:
            source = self.preview(source) or source
        content_type = mimetypes.guess_type(source.name)[0]
        self.send(
            HTTPStatus.OK,
            source.read_bytes(),
            content_type or "application/octet-stream",
            cache="private, max-age=600",
        )

    def preview(self, source: Path) -> Path | None:
        target = self.server.previews / (source.name + ".jpg")
        if target.is_file():
            return target
        if not shutil.which("sips"):
            return None
        result = subprocess.run(
            [
                "sips",
                "-s",
                "format",
                "jpeg",
                "-Z",
                "1600",
                str(source),
                "--out",
                str(target),
            ],
            check=False,
            capture_output=True,
        )
        return target if result.returncode == 0 and target.is_file() else None
