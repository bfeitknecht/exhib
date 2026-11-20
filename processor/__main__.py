"""Entrypoint.

``python -m processor``         watch the incoming queue and publish uploads.
``python -m processor rebuild`` rebuild the public site once and exit.
``python -m processor variants`` create missing small copies of every image, rebuild, exit.
"""

from __future__ import annotations

import shutil
import sys
import time

from .bundle import build_and_publish, fail_package, publish_bundle
from .variants import make_all
from .paths import APP, CONTENT, INCOMING, ORIGINALS, POLL_SECONDS, PUBLIC


def main() -> None:
    for path in (INCOMING, CONTENT, ORIGINALS, PUBLIC):
        path.mkdir(parents=True, exist_ok=True)
    # On first boot, seed the persistent content tree from the repository.
    if not any(CONTENT.iterdir()):
        seed = APP / "content"
        if seed.is_dir():
            shutil.copytree(seed, CONTENT, dirs_exist_ok=True)
    build_and_publish()
    while True:
        packages = sorted(
            p for p in INCOMING.iterdir() if p.is_dir() and not p.name.startswith(".")
        )
        for package in packages:
            try:
                publish_bundle(package)
            except Exception as exc:
                print(
                    f"Upload {package.name} failed: {exc}", file=sys.stderr, flush=True
                )
                # Do not retry a malformed package in a tight loop. It goes
                # back to the drafts with the error (the web editor shows it).
                try:
                    fail_package(package, exc)
                except OSError:
                    pass
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    if sys.argv[1:] == ["rebuild"]:
        build_and_publish()
    elif sys.argv[1:] == ["variants"]:
        made = make_all(CONTENT)
        print(f"{made} copies made", flush=True)
        build_and_publish()
    elif sys.argv[1:]:
        sys.exit("usage: python -m processor [rebuild|variants]")
    else:
        main()
