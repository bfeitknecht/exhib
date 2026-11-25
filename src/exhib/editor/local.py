"""``exhib edit [folder] [--port N] [--no-browser]`` (``just manifest``).

folder is the uploads root, or one slug folder in it. The editor can
switch between all slug folders of the root.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

from .manifest import media_files
from .server import Editor


def is_slug_folder(folder: Path) -> bool:
    return (
        (folder / "manifest.toml").is_file()
        or bool(media_files(folder))
        or any(folder.glob("*.md"))
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="exhib edit", description="Edit exhib upload manifests."
    )
    parser.add_argument("folder", type=Path, nargs="?", default=Path("uploads"))
    parser.add_argument("--port", type=int, default=0, help="default: any free port")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    folder = args.folder.expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"Not a folder: {folder}")
    root, start = (
        (folder.parent, folder.name) if is_slug_folder(folder) else (folder, "")
    )

    server = Editor(root, args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    if start:
        url += f"?f={quote(start)}"
    print(f"Editing {root}\nOpen {url}\nPress Ctrl-C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
