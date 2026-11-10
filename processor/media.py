"""Convert uploaded images and videos into web-ready assets."""

from __future__ import annotations

import subprocess
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


def run(args: list[str]) -> None:
    subprocess.run(args, check=True)


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
