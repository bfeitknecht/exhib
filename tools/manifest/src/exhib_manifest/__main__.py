"""CLI: ``exhib-manifest <folder> [--port N] [--no-browser]``."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from .manifest import SLUG
from .server import Editor


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="exhib-manifest", description="Edit an exhib upload manifest."
    )
    parser.add_argument("folder", type=Path, help="slug folder with the media files")
    parser.add_argument("--port", type=int, default=0, help="default: any free port")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    folder = args.folder.expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"Not a folder: {folder}")
    if not SLUG.fullmatch(folder.name):
        print(
            f"Warning: '{folder.name}' is not a lowercase slug. Rename the folder"
            " before upload.",
            file=sys.stderr,
        )

    server = Editor(folder, args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Editing {folder}\nOpen {url}\nPress Ctrl-C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print(f"\nUpload with: just upload {args.folder}")


if __name__ == "__main__":
    main()
