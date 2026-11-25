"""Convert uploaded images and videos into web-ready assets."""

from __future__ import annotations

import json
import math
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def run(args: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.run(args, check=True, env=env)


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
    keep_creation_date(source, output)


def keep_creation_date(source: Path, output: Path) -> None:
    # PNG has no EXIF date of its own: the creation date lives in a text
    # chunk (CreationTime), tIME (ModifyDate) or XMP (CreateDate). WebP reads
    # capture dates from EXIF, so copy the best source date there. -wm cg only
    # creates tags and never overwrites a real EXIF date. Later arguments win:
    # creation beats modification. A source with no date gets none. Never
    # invent one from file times, which only record the upload.
    subprocess.run(
        [
            "exiftool",
            "-q",
            "-m",
            "-wm",
            "cg",
            "-overwrite_original",
            "-TagsFromFile",
            str(source),
            "-EXIF:DateTimeOriginal<PNG:ModifyDate",
            "-EXIF:DateTimeOriginal<PNG:CreationTime",
            "-EXIF:DateTimeOriginal<XMP-xmp:CreateDate",
            str(output),
        ],
        check=False,
    )


# EXIF Orientation code -> ffmpeg filters that make the pixels upright.
ORIENTATION = {
    1: [],
    2: ["hflip"],
    3: ["hflip", "vflip"],
    4: ["vflip"],
    5: ["transpose=0"],
    6: ["transpose=1"],
    7: ["transpose=3"],
    8: ["transpose=2"],
}
QUARTER_TURNS = {0: [], 1: ["transpose=1"], 2: ["hflip", "vflip"], 3: ["transpose=2"]}


def parse_edit(entry: dict) -> tuple[float, list[float] | None]:
    """Read and check ``rotate`` and ``crop`` of a [[media]] entry.

    rotate: degrees clockwise, any number. crop: [x, y, w, h] as fractions
    (0 to 1) of the upright image after rotation, so of the bounding box
    of the rotated picture. No-op values come back as (0.0, None).
    """
    rotate = entry.get("rotate", 0)
    if isinstance(rotate, bool) or not isinstance(rotate, int | float):
        raise ValueError("rotate must be a number of degrees")
    if not math.isfinite(rotate):
        raise ValueError("rotate must be finite")
    rotate = float(rotate) % 360
    if rotate < 1e-6 or rotate > 360 - 1e-6:
        rotate = 0.0
    crop = entry.get("crop")
    if crop is not None:
        ok = (
            isinstance(crop, list)
            and len(crop) == 4
            and all(
                isinstance(v, int | float) and not isinstance(v, bool) for v in crop
            )
        )
        if not ok:
            raise ValueError("crop must be [x, y, width, height]")
        x, y, w, h = (float(v) for v in crop)
        eps = 1e-6
        if not (
            0 <= x <= 1
            and 0 <= y <= 1
            and w > 0
            and h > 0
            and x + w <= 1 + eps
            and y + h <= 1 + eps
        ):
            raise ValueError("crop must lie inside the image (fractions 0 to 1)")
        if x < eps and y < eps and w > 1 - eps and h > 1 - eps:
            crop = None
        else:
            crop = [x, y, min(w, 1 - x), min(h, 1 - y)]
    return rotate, crop


def edit_filters(
    width: int, height: int, rotate: float, crop: list[float] | None
) -> list[str]:
    """ffmpeg filters that rotate an upright width x height image, then crop it.

    Whole quarter turns are exact transposes. The remainder (-45 to 45
    degrees) turns the picture about its centre on a canvas that holds the
    whole rotated picture, with transparent corners. The crop is a fraction
    of that canvas. The editor draws the same frame.
    """
    quarters = round(rotate / 90)
    fine = rotate - quarters * 90
    filters = list(QUARTER_TURNS[quarters % 4])
    if quarters % 2:
        width, height = height, width
    if abs(fine) > 1e-6:
        angle = math.radians(fine)
        cos, sin = abs(math.cos(angle)), abs(math.sin(angle))
        out_w = max(1, round(width * cos + height * sin))
        out_h = max(1, round(width * sin + height * cos))
        filters += [
            "format=rgba",
            f"rotate={angle:.9f}:ow={out_w}:oh={out_h}:c=black@0:bilinear=1",
        ]
        width, height = out_w, out_h
    if crop:
        x = min(round(crop[0] * width), width - 1)
        y = min(round(crop[1] * height), height - 1)
        w = max(1, min(round(crop[2] * width), width - x))
        h = max(1, min(round(crop[3] * height), height - y))
        filters.append(f"crop={w}:{h}:{x}:{y}")
    return filters


def image_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    width, height = out.strip().split(",")[:2]
    return int(width), int(height)


def decode_upright(source: Path, decoded: Path) -> None:
    """Decode to a PNG whose pixels are upright (EXIF orientation applied)."""
    if source.suffix.lower() in {".heic", ".heif"}:
        # heif-convert applies the rotation to the pixels.
        run(["heif-convert", str(source), str(decoded)])
        return
    code = subprocess.run(
        ["exiftool", "-s3", "-n", "-Orientation", str(source)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    filters = ORIENTATION.get(int(code) if code.isdigit() else 1, [])
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-noautorotate"]
    command += ["-i", str(source), "-frames:v", "1"]
    if filters:
        command += ["-vf", ",".join(filters)]
    run([*command, str(decoded)])


def edit_image(source: Path, decoded: Path, rotate: float, crop) -> None:
    """Write ``decoded``: the upright source, rotated and cropped."""
    upright = decoded.with_name(source.stem + ".upright.png")
    decode_upright(source, upright)
    try:
        width, height = image_size(upright)
        filters = edit_filters(width, height, rotate, crop)
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        command += ["-i", str(upright), "-frames:v", "1"]
        if filters:
            command += ["-vf", ",".join(filters)]
        run([*command, str(decoded)])
    finally:
        upright.unlink(missing_ok=True)


def convert_image(
    source: Path,
    destination: Path,
    rotate: float = 0.0,
    crop: list[float] | None = None,
) -> Path:
    # Encode lossless WebP. Copy the full source metadata back, so Hugo can read it.
    # rotate and crop (see parse_edit) are the owner's edits; Apple Photos
    # edits are lost when an original is exported, so they are redone here.
    ext = source.suffix.lower()
    decoded = destination / (source.stem + ".decoded.png")
    output = destination / (source.stem + ".webp")
    cwebp_inputs = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
    rotated = False
    edited = bool(rotate) or crop is not None
    if edited:
        edit_image(source, decoded, rotate, crop)
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
        rotated = True
    elif ext in cwebp_inputs:
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
            # heif-convert applies the rotation to the pixels.
            run(["heif-convert", str(source), str(decoded)])
            rotated = True
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
    if rotated:
        # The pixels are already upright (HEIC decode, or an edit). The copied Orientation tag would
        # turn them again in a viewer that honours it, and the copied EXIF
        # size would describe the unrotated frame.
        run(
            [
                "exiftool",
                "-q",
                "-m",
                "-overwrite_original",
                "-Orientation#=1",
                "-ExifIFD:ExifImageWidth<RIFF:ImageWidth",
                "-ExifIFD:ExifImageHeight<RIFF:ImageHeight",
                str(output),
            ]
        )
    return output


def video_pixel_format(source: Path) -> str:
    """Keep 10-bit sources 10-bit (iPhone HLG HDR), others 8-bit."""
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=pix_fmt",
            "-of",
            "csv=p=0",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return "yuv420p10le" if "10le" in out else "yuv420p"


def convert_video(source: Path, destination: Path) -> tuple[Path, Path]:
    output = destination / (source.stem + ".webm")
    poster_png = destination / (source.stem + "-poster.png")
    poster = destination / (source.stem + "-poster.webp")
    # Quality-targeted VP9, not lossless: camera footage defeats lossless
    # compression (a 10 MB clip became 550 MB). CRF 32 keeps phone clips
    # around their original size at a look nobody can tell apart. The scale
    # caps the long side at 1920 px (no upscaling) for future 4K uploads.
    # row-mt and cpu-used 4 trade a little efficiency for much faster runs.
    # 10-bit HLG sources stay 10-bit, so HDR clips keep their look.
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
            # Only the first audio track. Phone clips carry extra audio-typed
            # streams with no decoder (Apple metadata); 0:a? maps those too
            # and the conversion fails. The first track is the real sound.
            "-map",
            "0:a:0?",
            "-map_metadata",
            "0",
            "-vf",
            "scale='min(1920,iw)':'min(1920,ih)':"
            "force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-c:v",
            "libvpx-vp9",
            "-crf",
            "32",
            "-b:v",
            "0",
            "-deadline",
            "good",
            "-cpu-used",
            "4",
            "-row-mt",
            "1",
            "-pix_fmt",
            video_pixel_format(source),
            "-c:a",
            "libopus",
            "-b:a",
            "128k",
            "-f",
            "webm",
            str(output),
        ]
    )
    # Poster: the frame at 1 s. A clip of 1 s or less has no frame there;
    # ffmpeg then writes nothing but still exits 0. Fall back to frame 0.
    grab = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    try:
        run([*grab, "-ss", "1", "-i", str(source), "-frames:v", "1", str(poster_png)])
    except subprocess.CalledProcessError:
        pass
    if not poster_png.is_file() or poster_png.stat().st_size == 0:
        run([*grab, "-i", str(source), "-frames:v", "1", str(poster_png)])
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
    except ValueError, ZeroDivisionError:
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
    except TypeError, ValueError:
        pass
    tags = (data.get("format") or {}).get("tags") or {}
    # Phones write the local capture time with its offset in the Apple tag;
    # creation_time is UTC. Either gives the capture moment.
    for key in ("com.apple.quicktime.creationdate", "creation_time"):
        captured = _parse_capture_date(tags.get(key))
        if captured:
            info["date"] = captured
            break
    return info


def _parse_capture_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if moment.year <= 1970:  # Encoders write 1970/1904 for "unknown".
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.isoformat(timespec="seconds")


def _probe_from_ffmpeg_stderr(text: str) -> dict:
    info: dict[str, str] = {}
    duration = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if duration:
        hours, minutes, seconds = duration.groups()
        total = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if total > 0:
            info["duration"] = format_duration(total)
    video_line = next((line for line in text.splitlines() if "Video:" in line), "")
    size = re.search(r"(\d{2,5})x(\d{2,5})", video_line)
    if size:
        info["resolution"] = f"{size.group(1)}×{size.group(2)}"
    fps = re.search(r"(\d+(?:\.\d+)?)\s*fps", video_line)
    if fps:
        info["framerate"] = format_fps(float(fps.group(1)))
    return info


def probe_video(source: Path) -> dict:
    """Return resolution/framerate/duration/date for a video, or {} on failure.

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
                "-show_entries",
                "format_tags=creation_time,com.apple.quicktime.creationdate",
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
