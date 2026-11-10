#!/usr/bin/env python3
"""Consumes manifest.toml upload folders, creates Hugo bundles, then rebuilds public/."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(os.environ.get("EXHIB_DATA", "/data"))
APP = Path(os.environ.get("EXHIB_APP", "/app"))
INCOMING = DATA / "incoming"
CONTENT = DATA / "content"
ORIGINALS = DATA / "originals"
PUBLIC = DATA / "public"
POLL_SECONDS = int(os.environ.get("EXHIB_POLL_SECONDS", "3"))
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


def run(args: list[str]) -> None:
    subprocess.run(args, check=True)


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


def copy_metadata(source: Path, output: Path) -> None:
    # Preserve embedded EXIF/IPTC/XMP when a still image is converted.
    run(
        [
            "exiftool",
            "-overwrite_original",
            "-TagsFromFile",
            str(source),
            "-all:all",
            str(output),
        ]
    )


def convert_image(source: Path, destination: Path) -> Path:
    # Encode lossless WebP; copy full source metadata back so Hugo can extract it.
    ext = source.suffix.lower()
    decoded = destination / (source.stem + ".decoded.png")
    output = destination / (source.stem + ".webp")
    cwebp_inputs = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
    if ext in cwebp_inputs:
        run(
            [
                "cwebp",
                "-quiet",
                "-lossless",
                "-exact",
                "-m",
                "6",
                str(source),
                "-o",
                str(output),
            ]
        )
    else:
        if ext in {".heic", ".heif"}:
            run(["heif-convert", str(source), str(decoded)])
        else:
            run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-noautorotate",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    str(decoded),
                ]
            )
        run(
            [
                "cwebp",
                "-quiet",
                "-lossless",
                "-exact",
                "-m",
                "6",
                str(decoded),
                "-o",
                str(output),
            ]
        )
        decoded.unlink(missing_ok=True)
    copy_metadata(source, output)
    return output


def convert_video(source: Path, destination: Path) -> tuple[Path, Path]:
    output = destination / (source.stem + ".webm")
    poster_png = destination / (source.stem + "-poster.png")
    poster = destination / (source.stem + "-poster.webp")
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-map_metadata",
            "0",
            "-c:v",
            "libvpx-vp9",
            "-lossless",
            "1",
            "-b:v",
            "0",
            "-deadline",
            "good",
            "-cpu-used",
            "2",
            "-c:a",
            "libopus",
            "-b:a",
            "128k",
            "-f",
            "webm",
            str(output),
        ]
    )
    try:
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                "1",
                "-i",
                str(source),
                "-frames:v",
                "1",
                str(poster_png),
            ]
        )
    except subprocess.CalledProcessError:
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-frames:v",
                "1",
                str(poster_png),
            ]
        )
    run(
        [
            "cwebp",
            "-quiet",
            "-lossless",
            "-exact",
            "-m",
            "6",
            str(poster_png),
            "-o",
            str(poster),
        ]
    )
    poster_png.unlink(missing_ok=True)
    copy_metadata(source, poster)
    return output, poster


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
    if not isinstance(media, list) or not media:
        raise ValueError("manifest.toml needs at least one [[media]] entry")

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
        # A previous attempt died before cleaning up; the bundle is generated
        # output, so it is safe to discard before re-processing.
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


def main() -> None:
    for path in (INCOMING, CONTENT, ORIGINALS, PUBLIC):
        path.mkdir(parents=True, exist_ok=True)
    # Seed the persistent content tree with the repository's demo and preserved assets once.
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
                # Avoid retrying a malformed package in a tight loop.
                failed = INCOMING / (".failed-" + package.name)
                try:
                    package.rename(failed)
                except OSError:
                    pass
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
