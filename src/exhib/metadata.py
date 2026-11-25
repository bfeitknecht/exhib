"""The metadata a published image keeps, and its place name.

A phone photo carries hundreds of tags: Apple's MakerNote (binary plists),
HDR gain-map XMP, software versions, the same date three times. The site
shows what a photographer cares about, so the master keeps only that:

- camera and lens: make, model, lens, focal length (and the 35 mm value);
- exposure: aperture, shutter time, ISO, exposure compensation, flash;
- time: capture date and its UTC offset;
- place: GPS latitude, longitude, altitude, plus the nearest town and
  country (``exhib.places``, offline) as XMP City and Country;
- orientation, the colour profile (iPhone photos are Display P3), and
  artist and copyright if the source has them.

Everything else is dropped. The small lossy copies carry no metadata.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .places import nearest

# Copied as `-EXIF:<tag><<tag>`: the source tag can sit in any group (EXIF in
# a JPEG or HEIC, Keys or UserData in a phone video), the copy lands in EXIF.
EXIF_TAGS = (
    "Make",
    "Model",
    "LensMake",
    "LensModel",
    "FocalLength",
    "FocalLengthIn35mmFormat",
    "FNumber",
    "ExposureTime",
    "ISO",
    "ExposureCompensation",
    "Flash",
    "DateTimeOriginal",
    "CreateDate",
    "OffsetTimeOriginal",
    "OffsetTime",
    "Artist",
    "Copyright",
)
# Composite GPS values are signed decimals for every source format; the
# reference tags (N/S, E/W, above/below sea level) follow from the sign.
GPS = (
    "-EXIF:GPSLatitude<Composite:GPSLatitude",
    "-EXIF:GPSLatitudeRef<Composite:GPSLatitude",
    "-EXIF:GPSLongitude<Composite:GPSLongitude",
    "-EXIF:GPSLongitudeRef<Composite:GPSLongitude",
    "-EXIF:GPSAltitude<Composite:GPSAltitude",
    "-EXIF:GPSAltitudeRef<Composite:GPSAltitude",
)


def keep(source: Path, output: Path, orientation_from: Path | None = None) -> None:
    """Replace all metadata of ``output`` with the kept tags of ``source``.

    ``orientation_from``: the file whose Orientation is right for the
    pixels of ``output`` (the output itself when it was made long ago from
    a rotated decode); default ``source``.
    """
    command = ["exiftool", "-q", "-m", "-overwrite_original", "-all="]
    command += ["-tagsFromFile", str(source), "-ICC_Profile"]
    command += [f"-EXIF:{tag}<{tag}" for tag in EXIF_TAGS]
    command += GPS
    if orientation_from is None:
        command.append("-EXIF:Orientation<Orientation")
    else:
        command += ["-tagsFromFile", str(orientation_from)]
        command.append("-EXIF:Orientation<Orientation")
    subprocess.run([*command, str(output)], check=True)
    add_place(output)


def add_place(output: Path) -> None:
    """Write the nearest town and country of the GPS position, if any."""
    out = subprocess.run(
        ["exiftool", "-j", "-n", "-Composite:GPSLatitude", "-Composite:GPSLongitude"]
        + [str(output)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    try:
        row = json.loads(out)[0]
        lat, lon = float(row["GPSLatitude"]), float(row["GPSLongitude"])
    except ValueError, KeyError, IndexError, TypeError:
        return
    place = nearest(lat, lon)
    if place is None:
        return
    city, country = place
    subprocess.run(
        ["exiftool", "-q", "-m", "-overwrite_original"]
        + [f"-XMP-photoshop:City={city}", f"-XMP-photoshop:Country={country}"]
        + [str(output)],
        check=True,
    )
