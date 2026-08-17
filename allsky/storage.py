"""On-disk capture archive and derived products."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from allsky.config import StationConfig
from allsky.processing import make_keogram, make_startrails


def ensure_dirs(config: StationConfig) -> None:
    config.captures_dir.mkdir(parents=True, exist_ok=True)
    config.products_dir.mkdir(parents=True, exist_ok=True)
    config.root.mkdir(parents=True, exist_ok=True)


def _day_dir(config: StationConfig, when: datetime) -> Path:
    day = ensure_utc(when).strftime("%Y-%m-%d")
    path = config.captures_dir / day
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_utc(when: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def save_capture(config: StationConfig, image: Image.Image, when: datetime, extra: dict | None = None) -> Path:
    ensure_dirs(config)
    when = ensure_utc(when)
    path = _day_dir(config, when) / f"{when.strftime('%H%M%S')}.jpg"
    image.save(path, "JPEG", quality=90)
    image.save(config.latest_image, "JPEG", quality=90)
    meta = {
        "captured_at": when.isoformat(),
        "path": str(path),
        "station": config.station_name,
        **(extra or {}),
    }
    config.latest_meta.write_text(json.dumps(meta, indent=2) + "\n")
    return path


def list_days(config: StationConfig) -> list[str]:
    if not config.captures_dir.exists():
        return []
    return sorted(p.name for p in config.captures_dir.iterdir() if p.is_dir())


def list_frames(config: StationConfig, day: str) -> list[Path]:
    folder = config.captures_dir / day
    if not folder.exists():
        return []
    return sorted(folder.glob("*.jpg"))


def load_frames(config: StationConfig, day: str) -> list[Image.Image]:
    return [Image.open(path).convert("RGB") for path in list_frames(config, day)]


def product_path(config: StationConfig, day: str, kind: str) -> Path:
    folder = config.products_dir / day
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{kind}.jpg"


def build_products(config: StationConfig, day: str) -> dict[str, str]:
    frames = load_frames(config, day)
    if not frames:
        raise FileNotFoundError(f"no frames for {day}")
    keogram = make_keogram(frames)
    trails = make_startrails(frames)
    kpath = product_path(config, day, "keogram")
    tpath = product_path(config, day, "startrails")
    keogram.save(kpath, "JPEG", quality=92)
    trails.save(tpath, "JPEG", quality=92)
    return {"keogram": str(kpath), "startrails": str(tpath), "frames": str(len(frames))}
