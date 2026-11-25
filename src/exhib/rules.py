"""Rules that the processor and the editor share. Change them here only."""

from __future__ import annotations

import json
import re
from pathlib import Path

IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".avif",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".3gp", ".mkv", ".webm"}
# Upload kind -> Hugo section directory.
SECTIONS = {"piece": "pieces", "collection": "collections", "writing": "writings"}
KINDS = ("collection", "piece", "writing")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def natural_key(name: str) -> list:
    """Numeric-aware sort key, so "2-a.jpg" comes before "10-b.jpg"."""
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", name)
    ]


def humanize_stem(stem: str) -> str:
    """The default title of a file: "01-evening-walk" -> "Evening walk"."""
    text = re.sub(r"^\d+[-_ ]*", "", stem)
    text = re.sub(r"[-_]+", " ", text).strip()
    return (text[:1].upper() + text[1:]) if text else stem


def media_type(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)
