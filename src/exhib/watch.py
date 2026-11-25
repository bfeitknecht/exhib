"""The processor loop: watch the inbox and publish uploads.

``exhib watch`` runs it forever. ``exhib rebuild`` and ``exhib variants``
are the one-shot jobs (``just rebuild``, ``just variants``).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


from .bundle import build_and_publish, fail_package, publish_bundle
from .metadata import keep
from .paths import APP, CONTENT, INCOMING, ORIGINALS, POLL_SECONDS, PUBLIC
from .rules import SECTIONS, media_type
from .variants import digest, is_candidate, make_all


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


def rebuild() -> None:
    build_and_publish()


def variants() -> None:
    made = make_all(CONTENT)
    print(f"{made} copies made", flush=True)
    build_and_publish()


def original_of(master: Path) -> Path | None:
    """The uploaded source of a master, from /data/originals, if it is there."""
    section, slug = master.parent.parent.name, master.parent.name
    kind = {v: k for k, v in SECTIONS.items()}.get(section)
    folder = ORIGINALS / kind / slug if kind else None
    if folder is None or not folder.is_dir():
        return None
    stem = master.stem.removesuffix("-poster")
    for path in sorted(folder.iterdir()):
        if path.stem == stem and media_type(path):
            return path
    return None


def metadata() -> None:
    """Bring every published image to the kept metadata (exhib.metadata).

    The colour profile comes from the uploaded original when it is still
    there; every other tag from the master itself. The pixels do not
    change, so the small copies are renamed to the new hash, not encoded
    again. Safe to re-run.
    """
    masters = sorted(p for p in CONTENT.rglob("*.webp") if is_candidate(p))
    for index, master in enumerate(masters, 1):
        keep(master, master)
        original = original_of(master)
        if original is not None and media_type(original) == "image":
            subprocess.run(
                ["exiftool", "-q", "-m", "-overwrite_original"]
                + ["-tagsFromFile", str(original), "-ICC_Profile", str(master)],
                check=False,
            )
        # Same pixels, new bytes: the copies stay valid under the new hash.
        new = digest(master)
        own = re.compile(re.escape(master.stem) + r"\.([0-9a-f]{8})\.(w\d+)\.webp")
        for copy in master.parent.iterdir():
            match = own.fullmatch(copy.name)
            if match and match[1] != new:
                copy.rename(copy.with_name(f"{master.stem}.{new}.{match[2]}.webp"))
        print(f"[{index}/{len(masters)}] {master.relative_to(CONTENT)}", flush=True)
    build_and_publish()
