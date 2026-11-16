"""Read a slug folder and write its manifest.toml.

The rules mirror the processor (processor/bundle.py, processor/media.py).
Keep the extension sets, the slug rule, natural_key and humanize_stem in
step with it. The tool writes the smallest manifest that gives the
result: [[media]] tables (file, title, position) only when the selection,
the order or a caption differs from the processor defaults.

The editor works on one root folder (uploads/) and its direct child
folders, one per slug. No other path is reachable.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tomllib
from datetime import UTC, datetime
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
KINDS = ("collection", "piece", "writing")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
BODY_FILE = "body.md"
# Default crop of the cover: centered. Not written to the manifest.
CENTER = [50, 50]


def natural_key(name: str) -> list:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", name)
    ]


def humanize_stem(stem: str) -> str:
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
        included = set(order)
        order += [n for n in names if n not in included]
    else:
        order = names
        included = set(names)
    by_name = {p.name: p for p in files}
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
                "captured": capture_date(by_name[name]),
            }
            for name in order
        ],
        "body_file": body.name,
        "body": body.read_text(encoding="utf-8") if body.is_file() else "",
    }


def toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


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

    custom = any(text(i, "title") or text(i, "caption") for i in chosen)
    defaults = [i["name"] for i in chosen] == names and not custom
    if not defaults:
        for index, item in enumerate(chosen, 1):
            lines += ["", "[[media]]", f"file = {toml_string(item['name'])}"]
            # Empty title: the processor uses the file name.
            for key in ("title", "caption"):
                if text(item, key):
                    lines.append(f"{key} = {toml_string(text(item, key))}")
            lines.append(f"position = {index}")
    return "\n".join(lines) + "\n", None


def save(folder: Path, data: dict) -> str:
    manifest, body = render(folder, data)
    tomllib.loads(manifest)  # Never write a file the processor cannot read.
    (folder / "manifest.toml").write_text(manifest, encoding="utf-8")
    if body is not None:
        body_file(folder).write_text(body, encoding="utf-8")
    return manifest
