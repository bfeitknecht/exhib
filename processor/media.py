"""Convert uploaded images and videos into web-ready assets."""

from __future__ import annotations

import json
import re
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
    # Encode lossless WebP. Copy the full source metadata back, so Hugo can read it.
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


def _parse_rate(rate: str | None) -> float | None:
    if not rate:
        return None
    try:
        num, den = rate.split("/", 1)
        num_f, den_f = float(num), float(den)
        return num_f / den_f if den_f else None
    except (ValueError, ZeroDivisionError):
        return None


def format_fps(fps: float) -> str:
    whole = round(fps)
    if abs(fps - whole) < 0.01:
        return f"{whole} fps"
    return f"{fps:.3f}".rstrip("0").rstrip(".") + " fps"


def format_duration(seconds: float) -> str:
    whole = round(seconds)
    if abs(seconds - whole) < 0.05:
        return f"{whole} s"
    return f"{seconds:.1f} s"


def _probe_from_ffprobe_json(data: dict) -> dict:
    streams = data.get("streams") or []
    stream = streams[0] if streams else {}
    info: dict[str, str] = {}
    width, height = stream.get("width"), stream.get("height")
    if width and height:
        info["resolution"] = f"{width}×{height}"
    fps = _parse_rate(stream.get("avg_frame_rate")) or _parse_rate(
        stream.get("r_frame_rate")
    )
    if fps:
        info["framerate"] = format_fps(fps)
    try:
        duration = float((data.get("format") or {}).get("duration", "nan"))
        if duration == duration and duration > 0:  # NaN check
            info["duration"] = format_duration(duration)
    except (TypeError, ValueError):
        pass
    return info


def _probe_from_ffmpeg_stderr(text: str) -> dict:
    info: dict[str, str] = {}
    duration = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text
    )
    if duration:
        hours, minutes, seconds = duration.groups()
        total = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if total > 0:
            info["duration"] = format_duration(total)
    video_line = next(
        (line for line in text.splitlines() if "Video:" in line), ""
    )
    size = re.search(r"(\d{2,5})x(\d{2,5})", video_line)
    if size:
        info["resolution"] = f"{size.group(1)}×{size.group(2)}"
    fps = re.search(r"(\d+(?:\.\d+)?)\s*fps", video_line)
    if fps:
        info["framerate"] = format_fps(float(fps.group(1)))
    return info


def probe_video(source: Path) -> dict:
    """Return resolution/framerate/duration for a video, or {} on failure.

    Values describe the source; the conversion neither resizes nor
    changes the frame rate, so they match the WebM output. Prefers
    ffprobe (JSON); falls back to parsing ffmpeg's input banner.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,avg_frame_rate,r_frame_rate",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return _probe_from_ffprobe_json(json.loads(result.stdout))
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(source)],
            capture_output=True,
            text=True,
        )
        return _probe_from_ffmpeg_stderr(result.stderr)
    except Exception:
        return {}
