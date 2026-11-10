"""Entrypoint. Watch the incoming queue and publish uploads as they arrive."""

from __future__ import annotations

import shutil
import sys
import time

from .bundle import build_and_publish, publish_bundle
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
                # Do not retry a malformed package in a tight loop.
                failed = INCOMING / (".failed-" + package.name)
                try:
                    package.rename(failed)
                except OSError:
                    pass
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
