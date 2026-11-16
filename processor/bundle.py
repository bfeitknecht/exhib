"""Validate uploads, write Hugo page bundles and rebuild the public site."""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from .media import (
    IMAGE_EXTS,
    VIDEO_EXTS,
    convert_image,
    convert_video,
    probe_video,
    run,
)
from .variants import make_variants
from .paths import APP, CONTENT, DATA, ORIGINALS, PUBLIC, RESOURCES

# Upload kind -> Hugo section directory.
SECTIONS = {"piece": "pieces", "collection": "collections", "writing": "writings"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def safe_relative(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"media path must stay inside its upload folder: {value}")
    resolved = (root / path).resolve()
    if root.resolve() not in resolved.parents:
        raise ValueError(f"media path escapes upload folder: {value}")
    return resolved


def natural_key(name: str) -> list:
    # Numeric-aware sort so "2-a.jpg" comes before "10-b.jpg".
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", name)
    ]


def humanize_stem(stem: str) -> str:
    # "01-evening-walk.jpg" -> "Evening walk"
    text = re.sub(r"^\d+[-_ ]*", "", stem)
    text = re.sub(r"[-_]+", " ", text).strip()
    return (text[:1].upper() + text[1:]) if text else stem


def visible_files(package: Path) -> list[Path]:
    return sorted(
        (p for p in package.iterdir() if p.is_file() and not p.name.startswith(".")),
        key=lambda p: natural_key(p.name),
    )


def is_media(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS | VIDEO_EXTS


def collect_media(package: Path) -> list[dict]:
    # No [[media]] tables in the manifest: every supported file in the
    # folder becomes an item, in natural filename order, titled after the
    # filename. The position follows the index (set later).
    entries = [
        {"file": p.name, "title": humanize_stem(p.stem)}
        for p in visible_files(package)
        if is_media(p)
    ]
    if not entries:
        raise ValueError("no supported media files in the folder")
    return entries


def read_manifest(package: Path) -> dict:
    slug = package.name
    if not SLUG.fullmatch(slug):
        raise ValueError(f"upload folder name must be a lowercase slug: {slug}")
    manifest_path = package / "manifest.toml"
    if not manifest_path.is_file():
        raise ValueError("manifest.toml is missing")
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("kind") not in SECTIONS:
        raise ValueError("kind must be 'piece', 'collection' or 'writing'")
    if not manifest.get("title"):
        raise ValueError("manifest.toml must include a title")
    if not isinstance(manifest.get("date"), datetime):
        raise ValueError("date must be a TOML datetime, e.g. 2026-11-07T12:00:00Z")
    return manifest


def build_front_matter(
    manifest: dict, media_rows: list[dict], thumbnail: str | None
) -> str:
    lines = ["+++", f"title = {toml_string(manifest['title'])}"]
    date = manifest["date"]
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    lines.append(f"date = {date.isoformat()}")
    if manifest.get("description"):
        lines.append(f"description = {toml_string(manifest['description'])}")
    tags = manifest.get("tags")
    if tags:
        if not isinstance(tags, list) or not all(
            isinstance(t, str) and t.strip() for t in tags
        ):
            raise ValueError("tags must be a list of non-empty strings")
        lines.append("tags = [" + ", ".join(toml_string(t.strip()) for t in tags) + "]")
    sort = manifest.get("sort", "position")
    if sort not in {"position", "date"}:
        raise ValueError("sort must be 'position' or 'date'")
    if sort == "date" and manifest["kind"] != "writing":
        # Media order on the page: capture date, then position. Default is
        # position only.
        lines.append('sort = "date"')
    if manifest["kind"] == "collection" and thumbnail:
        lines.append(f"thumbnail = {toml_string(thumbnail)}")
        focus = manifest.get("thumbnail_focus")
        if focus is not None:
            # Crop of the cover on the homepage card: [x, y] in percent,
            # used as CSS object-position. Default is the center.
            if not (
                isinstance(focus, list)
                and len(focus) == 2
                and all(isinstance(v, int | float) and 0 <= v <= 100 for v in focus)
            ):
                raise ValueError("thumbnail_focus must be [x, y] in percent (0-100)")
            lines.append(f"thumbnail_focus = [{round(focus[0])}, {round(focus[1])}]")
    for row in media_rows:
        lines += [
            "",
            "[[resources]]",
            f"src = {toml_string(row['file'])}",
            f"title = {toml_string(row['title'])}",
            "[resources.params]",
            f"position = {int(row['position'])}",
            f"kind = {toml_string(row['kind'])}",
        ]
        for key in (
            "format",
            "resolution",
            "framerate",
            "duration",
            "caption",
            "date",
            "poster",
            "role",
        ):
            if row.get(key):
                lines.append(f"{key} = {toml_string(row[key])}")
    lines.append("+++")
    return "\n".join(lines) + "\n"


# Hugo resizes images in parallel. Large posters (35 Mpx RGBA) then pass the
# 2 GiB pod limit and the kernel kills Hugo. Fewer threads and a Go soft
# memory limit keep the build inside the limit. Override from the pod env.
HUGO_ENV = {
    "HUGO_RESOURCEDIR": str(RESOURCES),
    "GOMAXPROCS": os.environ.get("EXHIB_HUGO_THREADS", "2"),
    "GOMEMLIMIT": os.environ.get("EXHIB_HUGO_MEMLIMIT", "1GiB"),
}


# Text files SWS serves from a ".gz" sibling (compression-static), so no
# request pays for compression. Binary formats are already compressed.
PRECOMPRESS = {".html", ".xml", ".svg", ".js", ".css", ".txt"}


def precompress(root: Path) -> None:
    for path in root.rglob("*"):
        if path.suffix not in PRECOMPRESS or not path.is_file():
            continue
        data = path.read_bytes()
        if len(data) < 512:
            continue
        # mtime=0 keeps the output reproducible. SWS reads Last-Modified from
        # the original file, not from the .gz.
        packed = gzip.compress(data, compresslevel=9, mtime=0)
        if len(packed) < len(data):
            path.with_name(path.name + ".gz").write_bytes(packed)


def build_and_publish() -> None:
    staging = DATA / ".public-next"
    backup = DATA / ".public-previous"
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    staging.mkdir(parents=True)
    run(
        [
            "hugo",
            "--source",
            str(APP),
            "--contentDir",
            str(CONTENT),
            "--destination",
            str(staging),
            "--minify",
            # Drop resized images that no page uses any more.
            "--gc",
        ],
        env=os.environ | HUGO_ENV,
    )
    precompress(staging)
    if PUBLIC.exists():
        PUBLIC.rename(backup)
    try:
        staging.rename(PUBLIC)
    except Exception:
        if backup.exists() and not PUBLIC.exists():
            backup.rename(PUBLIC)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def write_writing(package: Path, manifest: dict, bundle_dir: Path) -> None:
    # A writing upload is manifest.toml plus exactly one markdown body.
    files = [p for p in visible_files(package) if p.name != "manifest.toml"]
    bodies = [p for p in files if p.suffix.lower() == ".md"]
    if len(bodies) != 1:
        raise ValueError("a writing needs exactly one .md file for the body")
    extra = [p.name for p in files if p != bodies[0]]
    if extra:
        raise ValueError(f"a writing takes no other files: {', '.join(extra)}")
    body = bodies[0].read_text(encoding="utf-8")
    if body.lstrip().startswith(("+++", "---")):
        raise ValueError("the body must not have front matter; put it in manifest.toml")
    page = build_front_matter(manifest, [], None) + "\n" + body.lstrip("\n")
    (bundle_dir / "index.md").write_text(page, encoding="utf-8")


def write_media_bundle(package: Path, manifest: dict, bundle_dir: Path) -> None:
    kind = manifest["kind"]
    media = manifest.get("media")
    if media is None:
        media = collect_media(package)
    elif not isinstance(media, list) or not media:
        raise ValueError("manifest.toml: [[media]] must be a non-empty list")
    for old in ("order", "weight"):
        if any(old in entry for entry in media):
            raise ValueError(f"[[media]] {old} is renamed to position")

    converted = bundle_dir / ".converted"
    converted.mkdir()
    rows: list[dict] = []
    source_to_output: dict[str, str] = {}
    for index, entry in enumerate(media, 1):
        source = safe_relative(package, str(entry["file"]))
        if not source.is_file():
            raise ValueError(f"media file does not exist: {entry['file']}")
        ext = source.suffix.lower()
        # Title: short name, defaults to the file name. Caption: optional
        # markdown text shown under the title in the detail panel.
        title = str(entry.get("title") or humanize_stem(source.stem))
        caption = str(entry.get("caption") or "").strip()
        position = int(entry.get("position", index))
        if ext in IMAGE_EXTS:
            filename = convert_image(source, converted).name
            rows.append(
                {
                    "file": filename,
                    "title": title,
                    "caption": caption,
                    "position": position,
                    "kind": "image",
                }
            )
            source_to_output[source.name] = filename
        elif ext in VIDEO_EXTS:
            output, poster = convert_video(source, converted)
            rows.append(
                {
                    "file": output.name,
                    "title": title,
                    "caption": caption,
                    "position": position,
                    "kind": "video",
                    "poster": poster.name,
                    "format": "WebM · VP9",
                    **probe_video(source),
                }
            )
            rows.append(
                {
                    "file": poster.name,
                    "title": title,
                    "position": position,
                    "kind": "image",
                    "role": "poster",
                }
            )
            source_to_output[source.name] = poster.name
        else:
            raise ValueError(f"unsupported media type: {source.suffix}")
    for file in converted.iterdir():
        shutil.move(str(file), bundle_dir / file.name)
    converted.rmdir()
    # Small lossy copies for grids, cards and stages. One image at a time keeps memory low.
    for row in rows:
        if row["kind"] == "image":
            make_variants(bundle_dir / row["file"])

    thumbnail_source = manifest.get("thumbnail")
    thumbnail = None
    if thumbnail_source:
        thumbnail = source_to_output.get(Path(str(thumbnail_source)).name)
        if not thumbnail:
            raise ValueError("thumbnail must refer to a listed media file")
    page_file = bundle_dir / ("index.md" if kind == "piece" else "_index.md")
    page_file.write_text(
        build_front_matter(manifest, rows, thumbnail), encoding="utf-8"
    )


def publish_bundle(package: Path) -> None:
    manifest = read_manifest(package)
    kind = manifest["kind"]
    slug = package.name

    original_dir = ORIGINALS / kind / slug
    if original_dir.exists():
        raise ValueError(f"an item with this slug already exists: {slug}")
    original_dir.parent.mkdir(parents=True, exist_ok=True)
    original_pending = original_dir.parent / ("." + slug + ".pending")
    if original_pending.exists():
        raise ValueError(
            f"a previous processing attempt left a pending original for {slug}"
        )
    bundle_dir = CONTENT / SECTIONS[kind] / slug
    if bundle_dir.exists():
        # No upload original owns this bundle: it is left over from a
        # stopped attempt, seeded from the repo or added by hand. The
        # upload replaces it.
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)
    try:
        if kind == "writing":
            write_writing(package, manifest, bundle_dir)
        else:
            write_media_bundle(package, manifest, bundle_dir)
        shutil.copytree(package, original_pending)
        build_and_publish()
        original_pending.rename(original_dir)
        shutil.rmtree(package)
        print(f"Published {kind} {slug}", flush=True)
    except Exception:
        shutil.rmtree(bundle_dir, ignore_errors=True)
        shutil.rmtree(original_pending, ignore_errors=True)
        # Leave the incoming folder available for inspection/retry.
        raise
