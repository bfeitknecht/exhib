"""Validate uploads, write Hugo page bundles and rebuild the public site."""

from __future__ import annotations

import json
import re
import shutil
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from .media import IMAGE_EXTS, VIDEO_EXTS, convert_image, convert_video, probe_video, run
from .paths import APP, CONTENT, DATA, ORIGINALS, PUBLIC


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
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def humanize_stem(stem: str) -> str:
    # "01-evening-walk.jpg" -> "Evening walk"
    text = re.sub(r"^\d+[-_ ]*", "", stem)
    text = re.sub(r"[-_]+", " ", text).strip()
    return (text[:1].upper() + text[1:]) if text else stem


def collect_media(package: Path) -> list[dict]:
    # No [[media]] tables in the manifest: every supported file in the
    # folder becomes an item, in natural filename order, titled after the
    # filename. Weights follow the order (set later from the index).
    entries = []
    for path in sorted(package.iterdir(), key=lambda p: natural_key(p.name)):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() in IMAGE_EXTS | VIDEO_EXTS:
            entries.append({"file": path.name, "title": humanize_stem(path.stem)})
    if not entries:
        raise ValueError("no supported media files in the folder")
    return entries


def build_front_matter(
    manifest: dict, media_rows: list[dict], thumbnail: str | None
) -> str:
    kind = manifest["kind"]
    lines = ["+++", f"title = {toml_string(manifest['title'])}"]
    date = manifest["date"]
    if not isinstance(date, datetime):
        raise ValueError("date must be a TOML datetime, e.g. 2026-11-07T12:00:00Z")
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    lines.append(f"date = {date.isoformat()}")
    if manifest.get("description"):
        lines.append(f"description = {toml_string(manifest['description'])}")
    if kind == "collection" and thumbnail:
        lines.append(f"thumbnail = {toml_string(thumbnail)}")
    for row in media_rows:
        lines += [
            "",
            "[[resources]]",
            f"src = {toml_string(row['file'])}",
            f"title = {toml_string(row['title'])}",
            "[resources.params]",
            f"weight = {int(row['weight'])}",
            f"kind = {toml_string(row['kind'])}",
        ]
        if row.get("format"):
            lines.append(f"format = {toml_string(row['format'])}")
        if row.get("resolution"):
            lines.append(f"resolution = {toml_string(row['resolution'])}")
        if row.get("framerate"):
            lines.append(f"framerate = {toml_string(row['framerate'])}")
        if row.get("duration"):
            lines.append(f"duration = {toml_string(row['duration'])}")
        if row.get("poster"):
            lines.append(f"poster = {toml_string(row['poster'])}")
        if row.get("role"):
            lines.append(f"role = {toml_string(row['role'])}")
    lines.append("+++")
    return "\n".join(lines) + "\n"


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
        ]
    )
    if PUBLIC.exists():
        PUBLIC.rename(backup)
    try:
        staging.rename(PUBLIC)
    except Exception:
        if backup.exists() and not PUBLIC.exists():
            backup.rename(PUBLIC)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def publish_bundle(package: Path) -> None:
    slug = package.name
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError(f"upload folder name must be a lowercase slug: {slug}")
    manifest_path = package / "manifest.toml"
    if not manifest_path.is_file():
        raise ValueError("manifest.toml is missing")
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    kind = manifest.get("kind")
    if kind not in {"piece", "collection"}:
        raise ValueError("kind must be 'piece' or 'collection'")
    if not manifest.get("title") or not isinstance(manifest.get("date"), datetime):
        raise ValueError("manifest.toml must include title and a TOML datetime date")
    media = manifest.get("media")
    if media is None:
        media = collect_media(package)
    elif not isinstance(media, list) or not media:
        raise ValueError("manifest.toml: [[media]] must be a non-empty list")

    original_dir = ORIGINALS / kind / slug
    if original_dir.exists():
        raise ValueError(f"an item with this slug already exists: {slug}")

    original_dir.parent.mkdir(parents=True, exist_ok=True)
    original_pending = original_dir.parent / ("." + slug + ".pending")
    if original_pending.exists():
        raise ValueError(
            f"a previous processing attempt left a pending original for {slug}"
        )
    bundle_dir = CONTENT / ("pieces" if kind == "piece" else "collections") / slug
    if bundle_dir.exists():
        # The previous attempt stopped before cleanup. The bundle holds
        # generated output, so discard it before re-processing.
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=False)
    converted = bundle_dir / ".converted"
    converted.mkdir()
    rows: list[dict] = []
    source_to_output: dict[str, str] = {}
    video_rows: list[dict] = []
    try:
        for index, entry in enumerate(media, 1):
            source = safe_relative(package, str(entry["file"]))
            if not source.is_file():
                raise ValueError(f"media file does not exist: {entry['file']}")
            ext = source.suffix.lower()
            title = str(entry.get("title") or source.stem)
            weight = int(entry.get("weight", index))
            if ext in IMAGE_EXTS:
                filename = convert_image(source, converted).name
                row = {
                    "file": filename,
                    "title": title,
                    "weight": weight,
                    "kind": "image",
                }
                rows.append(row)
                source_to_output[Path(str(entry["file"])).name] = filename
            elif ext in VIDEO_EXTS:
                output, poster = convert_video(source, converted)
                filename = output.name
                poster_name = poster.name
                row = {
                    "file": filename,
                    "title": title,
                    "weight": weight,
                    "kind": "video",
                    "poster": poster_name,
                    "format": "WebM · VP9",
                    **probe_video(source),
                }
                video_rows.append(row)
                rows.append(row)
                rows.append(
                    {
                        "file": poster_name,
                        "title": title,
                        "weight": weight,
                        "kind": "image",
                        "role": "poster",
                    }
                )
                source_to_output[Path(str(entry["file"])).name] = poster_name
            else:
                raise ValueError(f"unsupported media type: {source.suffix}")
        for file in converted.iterdir():
            shutil.move(str(file), bundle_dir / file.name)
        converted.rmdir()
        thumbnail_source = manifest.get("thumbnail")
        thumbnail = (
            source_to_output.get(Path(str(thumbnail_source)).name)
            if thumbnail_source
            else None
        )
        if thumbnail_source and not thumbnail:
            raise ValueError("thumbnail must refer to a listed media file")
        if (
            kind == "piece"
            and not any(
                row["kind"] == "image" and row.get("role") != "poster" for row in rows
            )
            and not video_rows
        ):
            raise ValueError("piece must contain at least one supported image or video")
        page_file = bundle_dir / ("index.md" if kind == "piece" else "_index.md")
        page_file.write_text(
            build_front_matter(manifest, rows, thumbnail), encoding="utf-8"
        )
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
