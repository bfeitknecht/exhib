"""Small lossy copies of each image, made once when the image is processed.

The lossless master stays the fullscreen original. Grids, cards and stages
link the copies, so browsers load kilobytes, and Hugo never resizes a
9 MB source at build time.

A copy is named ``<stem>.<hash>.w<width>.webp``. ``<hash>`` is the first 8
hex digits of the master's SHA-256. The name changes when the master does,
so a copy can be cached forever (``immutable``). The smallest copy
(``BLUR_WIDTH``) is a blurred preview that the page inlines.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

WIDTHS = (480, 960, 1920, 2880)
BLUR_WIDTH = 24
QUALITY = 80
BLUR_QUALITY = 30

# The same pattern is in layouts/partials/media/sorted-media.html and img.html.
VARIANT = re.compile(r"\.[0-9a-f]{8}\.w\d+\.webp$")


def is_variant(path: Path) -> bool:
    return VARIANT.search(path.name) is not None


def is_candidate(path: Path) -> bool:
    """A lossless still master. Animated previews and copies are not."""
    return (
        path.suffix.lower() == ".webp"
        and not is_variant(path)
        and not path.stem.endswith("-preview")
    )


def digest(master: Path) -> str:
    sha = hashlib.sha256()
    with master.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()[:8]


def pixel_width(master: Path) -> int:
    result = subprocess.run(
        ["exiftool", "-s3", "-RIFF:ImageWidth", str(master)],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(result.stdout.split()[0])


def encode(master: Path, output: Path, width: int, quality: int) -> None:
    # Write beside the target, then rename: an interrupted run leaves no
    # half-written copy that a later run would trust.
    partial = output.with_name("." + output.name + ".part")
    subprocess.run(
        [
            "cwebp",
            "-quiet",
            "-q",
            str(quality),
            "-m",
            "4",
            "-resize",
            str(width),
            "0",
            str(master),
            "-o",
            str(partial),
        ],
        check=True,
    )
    partial.rename(output)


def make_variants(master: Path) -> list[Path]:
    """Create the missing copies of one master. Drop copies of an older master."""
    key = digest(master)
    own = re.compile(re.escape(master.stem) + r"\.([0-9a-f]{8})\.w\d+\.webp")
    for old in master.parent.iterdir():
        match = own.fullmatch(old.name)
        if match and match.group(1) != key:
            old.unlink()
    width = pixel_width(master)
    made = []
    for target, quality in [(w, QUALITY) for w in WIDTHS] + [
        (BLUR_WIDTH, BLUR_QUALITY)
    ]:
        # Never upscale. An image barely wider than a step still gets that step.
        if target >= width:
            continue
        output = master.with_name(f"{master.stem}.{key}.w{target}.webp")
        if output.is_file() and output.stat().st_size > 0:
            continue
        encode(master, output, target, quality)
        made.append(output)
    return made


def make_all(root: Path) -> int:
    """Create the copies for every master under ``root``. Returns the count made."""
    total = 0
    masters = sorted(p for p in root.rglob("*.webp") if is_candidate(p))
    for index, master in enumerate(masters, 1):
        made = make_variants(master)
        total += len(made)
        print(
            f"[{index}/{len(masters)}] {master.relative_to(root)}: {len(made)} new",
            flush=True,
        )
    return total
