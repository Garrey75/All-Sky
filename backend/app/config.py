from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("ALLSKY_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = Path(os.environ.get("ALLSKY_DATA", ROOT / "data"))
IMAGE_DIR = DATA_DIR / "images"
STACK_DIR = DATA_DIR / "stacks"
HOST = os.environ.get("ALLSKY_HOST", "0.0.0.0")
PORT = int(os.environ.get("ALLSKY_PORT", "8080"))
INDI_HOST = os.environ.get("ALLSKY_INDI_HOST", "")
INDI_PORT = int(os.environ.get("ALLSKY_INDI_PORT", "7624"))
DEFAULT_LAT = float(os.environ.get("ALLSKY_LAT", "31.2304"))
DEFAULT_LON = float(os.environ.get("ALLSKY_LON", "121.4737"))
DEFAULT_ELEV = float(os.environ.get("ALLSKY_ELEV", "12"))

IMAGE_DIR.mkdir(parents=True, exist_ok=True)
STACK_DIR.mkdir(parents=True, exist_ok=True)
