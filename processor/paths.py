"""Filesystem locations and tuning, derived from the environment."""

import os
from pathlib import Path

DATA = Path(os.environ.get("EXHIB_DATA", "/data"))
APP = Path(os.environ.get("EXHIB_APP", "/app"))
INCOMING = DATA / "incoming"
CONTENT = DATA / "content"
ORIGINALS = DATA / "originals"
PUBLIC = DATA / "public"
POLL_SECONDS = int(os.environ.get("EXHIB_POLL_SECONDS", "3"))
