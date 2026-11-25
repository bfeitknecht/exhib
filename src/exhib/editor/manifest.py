"""Read a slug folder and write its manifest.toml.

The extension sets, the slug rule, natural_key and humanize_stem come from
exhib.rules, the same code the processor uses. edit_of mirrors
exhib.media.parse_edit. The tool writes the smallest manifest that gives
the result: [[media]] tables (file, title, position) only when the
selection, the order or a caption differs from the processor defaults.

The editor works on one root folder (uploads/) and its direct child
folders, one per slug. No other path is reachable.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from ..rules import KINDS, SLUG, humanize_stem, media_type, natural_key, toml_string

__all__ = ["KINDS", "SLUG", "media_type", "natural_key"]

BODY_FILE = "body.md"
# Default crop of the cover: centered. Not written to the manifest.
CENTER = [50, 50]


def media_files(folder: Path) -> list[Path]:
    return sorted(
        (
            p
            for p in folder.iterdir()
            if p.is_file() and not p.name.startswith(".") and media_type(p)
        ),
        key=lambda p: natural_key(p.name),
    )


def capture_date(path: Path) -> str | None:
    """Capture time as local ISO text, or None. Same sources as the site.

    The site orders by the EXIF capture date of a photo and the creation
    tag of a video. A file with neither is undated and follows the dated
    ones. File times only record the export, so they are never used.
    macOS only (sips, mdls); elsewhere every file is undated.
    """
    try:
        if media_type(path) == "image" and shutil.which("sips"):
            out = subprocess.run(
                ["sips", "-g", "creation", str(path)],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            value = out.rsplit("creation:", 1)[-1].strip()
            return (
                datetime.strptime(value, "%Y:%m:%d %H:%M:%S").isoformat()
                if "creation:" in out and value != "<nil>"
                else None
            )
        if media_type(path) == "video" and shutil.which("mdls"):
            out = subprocess.run(
                ["mdls", "-raw", "-name", "kMDItemContentCreationDate", str(path)],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            moment = datetime.strptime(out, "%Y-%m-%d %H:%M:%S %z")
            return moment.astimezone().replace(tzinfo=None).isoformat()
    except ValueError:
        pass
    return None


def capture_dates(files: list[Path]) -> dict[str, str | None]:
    """Capture dates of all files, by name. sips/mdls on macOS, else exiftool.

    exiftool (the web editor in the cluster) reads every file in one call:
    EXIF DateTimeOriginal for photos, the QuickTime creation date (converted
    from UTC to local time) for videos. No file times, as above.
    """
    if shutil.which("sips") or not shutil.which("exiftool") or not files:
        return {p.name: capture_date(p) for p in files}
    out = subprocess.run(
        [
            "exiftool",
            "-j",
            "-q",
            "-m",
            "-api",
            "QuickTimeUTC",
            "-d",
            "%Y-%m-%dT%H:%M:%S",
            "-DateTimeOriginal",
            "-CreationDate",
            "-CreateDate",
            *(str(p) for p in files),
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    dates: dict[str, str | None] = {p.name: None for p in files}
    try:
        rows = json.loads(out or "[]")
    except ValueError:
        rows = []
    for row in rows:
        name = Path(str(row.get("SourceFile", ""))).name
        for key in ("DateTimeOriginal", "CreationDate", "CreateDate"):
            value = str(row.get(key) or "")
            if re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value[:19]
            ) and not value.startswith("0000"):
                dates[name] = value[:19]
                break
    return dates


def body_file(folder: Path) -> Path:
    bodies = sorted(p for p in folder.glob("*.md") if not p.name.startswith("."))
    return bodies[0] if len(bodies) == 1 else folder / BODY_FILE


def child(root: Path, name: str) -> Path:
    """Return root/name if it is a direct, visible child folder of root."""
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError(f"not a folder name: {name!r}")
    if name.startswith("."):
        raise ValueError(f"hidden folder: {name}")
    folder = root / name
    if folder.resolve().parent != root.resolve() or not folder.is_dir():
        raise ValueError(f"no folder {name} in {root}")
    return folder


def list_folders(root: Path) -> list[dict]:
    return [
        {
            "name": p.name,
            "slug_ok": bool(SLUG.fullmatch(p.name)),
            "has_manifest": (p / "manifest.toml").is_file(),
        }
        for p in sorted(root.iterdir(), key=lambda p: natural_key(p.name))
        if p.is_dir() and not p.name.startswith(".")
    ]


def edit_of(entry: dict) -> tuple[float, list[float] | None]:
    """Read rotate and crop of a [[media]] entry. Same rules as the processor
    (exhib.media.parse_edit). Raises ValueError on a bad value."""
    rotate = entry.get("rotate", 0) or 0
    if isinstance(rotate, bool) or not isinstance(rotate, int | float):
        raise ValueError("rotate must be a number of degrees")
    if not math.isfinite(rotate):
        raise ValueError("rotate must be finite")
    rotate = round(float(rotate) % 360, 1)
    if rotate >= 360:
        rotate = 0.0
    crop = entry.get("crop")
    if crop is not None:
        if not (
            isinstance(crop, list)
            and len(crop) == 4
            and all(
                isinstance(v, int | float) and not isinstance(v, bool) for v in crop
            )
        ):
            raise ValueError("crop must be [x, y, width, height]")
        x, y, w, h = (round(float(v), 4) for v in crop)
        if not (0 <= x <= 1 and 0 <= y <= 1 and w > 0 and h > 0):
            raise ValueError("crop must lie inside the image")
        # Same tolerance as the processor (parse_edit): a crop that reaches
        # past the edge is invalid, not silently clamped.
        if x + w > 1.0001 or y + h > 1.0001:
            raise ValueError("crop must lie inside the image")
        w, h = min(w, round(1 - x, 4)), min(h, round(1 - y, 4))
        crop = None if x == 0 and y == 0 and w >= 1 and h >= 1 else [x, y, w, h]
    return rotate, crop


def focus_of(value: object) -> list[int] | None:
    """[x, y] in percent (0-100), or None if value is not such a pair."""
    if (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(v, int | float) and 0 <= v <= 100 for v in value)
    ):
        return [round(v) for v in value]
    return None


def iso(value: datetime) -> str:
    # Keep the offset the date was written with (local time). A date with
    # no offset is UTC, as in the processor.
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat(timespec="seconds")


def load_state(folder: Path) -> dict:
    """Return the editor state: manifest values plus every media file."""
    path = folder / "manifest.toml"
    manifest = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    files = media_files(folder)
    names = [p.name for p in files]
    listed = manifest.get("media")
    titles: dict[str, str] = {}
    captions: dict[str, str] = {}
    edits: dict[str, tuple[float, list[float] | None]] = {}
    if isinstance(listed, list):
        # Same rule as the processor: explicit position, else list index.
        # Manifests from before the rename may say order or weight.
        ranked = sorted(
            (
                int(e.get("position", e.get("order", e.get("weight", i)))),
                i,
                str(e["file"]),
            )
            for i, e in enumerate(listed, 1)
            if str(e.get("file")) in names
        )
        order = [name for _, _, name in ranked]
        titles = {str(e["file"]): str(e["title"]) for e in listed if e.get("title")}
        captions = {
            str(e["file"]): str(e["caption"]) for e in listed if e.get("caption")
        }
        for e in listed:
            try:
                edits[str(e["file"])] = edit_of(e)
            except KeyError, ValueError:
                pass
        included = set(order)
        order += [n for n in names if n not in included]
    else:
        order = names
        included = set(names)
    by_name = {p.name: p for p in files}
    dates = capture_dates(files)
    body = body_file(folder)
    kind = manifest.get("kind")
    if kind not in KINDS:
        kind = (
            "writing"
            if not files and body.is_file()
            else ("piece" if len(files) == 1 else "collection")
        )
    date = manifest.get("date")
    return {
        "folder": str(folder),
        "slug": folder.name,
        "slug_ok": bool(SLUG.fullmatch(folder.name)),
        "has_manifest": path.is_file(),
        "kind": kind,
        "title": manifest.get("title") or humanize_stem(folder.name),
        "date": iso(date) if isinstance(date, datetime) else None,
        "description": manifest.get("description", ""),
        "tags": list(manifest.get("tags") or []),
        "sort": "date" if manifest.get("sort") == "date" else "position",
        "thumbnail": manifest.get("thumbnail") or "",
        "thumbnail_focus": focus_of(manifest.get("thumbnail_focus")) or CENTER,
        "items": [
            {
                "name": name,
                "type": media_type(by_name[name]),
                "default_title": humanize_stem(by_name[name].stem),
                "title": titles.get(name, ""),
                "caption": captions.get(name, ""),
                "included": name in included,
                "rotate": edits.get(name, (0.0, None))[0],
                "crop": edits.get(name, (0.0, None))[1],
                "captured": dates.get(name),
            }
            for name in order
        ],
        "body_file": body.name,
        "body": body.read_text(encoding="utf-8") if body.is_file() else "",
    }


def parse_date(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except TypeError, ValueError:
        raise ValueError(f"date is not a valid ISO datetime: {value!r}") from None
    return iso(parsed)


def render(folder: Path, data: dict) -> tuple[str, str | None]:
    """Validate editor data. Return (manifest text, body text or None)."""
    kind = data.get("kind")
    if kind not in KINDS:
        raise ValueError("kind must be collection, piece or writing")
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    lines = [
        f"kind = {toml_string(kind)}",
        f"title = {toml_string(title)}",
        f"date = {parse_date(data.get('date'))}",
    ]
    description = str(data.get("description") or "").strip()
    if description:
        lines.append(f"description = {toml_string(description)}")
    tags = [str(t).strip() for t in data.get("tags") or [] if str(t).strip()]
    if tags:
        lines.append("tags = [" + ", ".join(toml_string(t) for t in tags) + "]")

    if kind == "writing":
        body = str(data.get("body") or "")
        if not body.strip():
            raise ValueError("a writing needs a body")
        if body.lstrip().startswith(("+++", "---")):
            raise ValueError("the body must not have front matter")
        if media_files(folder):
            raise ValueError("a writing takes no media; move the media files out")
        return "\n".join(lines) + "\n", body.rstrip("\n") + "\n"

    if data.get("sort") == "date":
        lines.append('sort = "date"')
    names = [p.name for p in media_files(folder)]
    items = [i for i in data.get("items") or [] if i.get("name") in names]
    chosen = [i for i in items if i.get("included")]
    if not chosen:
        raise ValueError("select at least one media file")
    thumbnail = str(data.get("thumbnail") or "")
    if kind == "collection" and thumbnail:
        if thumbnail not in {i["name"] for i in chosen}:
            raise ValueError("the thumbnail must be an included file")
        lines.append(f"thumbnail = {toml_string(thumbnail)}")
        focus = focus_of(data.get("thumbnail_focus"))
        if focus and focus != CENTER:
            lines.append(f"thumbnail_focus = [{focus[0]}, {focus[1]}]")

    def text(item: dict, key: str) -> str:
        return str(item.get(key) or "").strip()

    for item in chosen:
        if media_type(folder / item["name"]) == "video" and (
            item.get("rotate") or item.get("crop")
        ):
            raise ValueError(f"rotate and crop apply to images only: {item['name']}")
        edit_of(item)  # Reject a bad value now, not at upload.

    def edit(item: dict) -> tuple[float, list[float] | None]:
        return edit_of(item)

    custom = any(
        text(i, "title") or text(i, "caption") or edit(i) != (0.0, None) for i in chosen
    )
    defaults = [i["name"] for i in chosen] == names and not custom
    if not defaults:
        for index, item in enumerate(chosen, 1):
            lines += ["", "[[media]]", f"file = {toml_string(item['name'])}"]
            # Empty title: the processor uses the file name.
            for key in ("title", "caption"):
                if text(item, key):
                    lines.append(f"{key} = {toml_string(text(item, key))}")
            rotate, crop = edit(item)
            if rotate:
                # Whole degrees read better as integers.
                shown = int(rotate) if rotate == int(rotate) else rotate
                lines.append(f"rotate = {shown}")
            if crop:
                lines.append("crop = [" + ", ".join(str(v) for v in crop) + "]")
            lines.append(f"position = {index}")
    return "\n".join(lines) + "\n", None


def save(folder: Path, data: dict) -> str:
    manifest, body = render(folder, data)
    tomllib.loads(manifest)  # Never write a file the processor cannot read.
    (folder / "manifest.toml").write_text(manifest, encoding="utf-8")
    if body is not None:
        body_file(folder).write_text(body, encoding="utf-8")
    return manifest
