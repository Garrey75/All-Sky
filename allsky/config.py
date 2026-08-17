"""Station configuration loaded from config.json or defaults."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class StationConfig(BaseModel):
    station_name: str = "Garrey All-Sky"
    operator: str = "Garrey"
    latitude: float = 40.0
    longitude: float = -105.0
    elevation_m: float = 1650.0
    capture_interval_seconds: int = Field(default=20, ge=1)
    image_size: int = Field(default=720, ge=64, le=2048)
    data_dir: str = "data"
    demo_mode: bool = True
    demo_frames: int = Field(default=36, ge=3, le=288)
    night_threshold_deg: float = -6.0
    host: str = "0.0.0.0"
    port: int = 8080

    @property
    def root(self) -> Path:
        return Path(self.data_dir)

    @property
    def captures_dir(self) -> Path:
        return self.root / "captures"

    @property
    def products_dir(self) -> Path:
        return self.root / "products"

    @property
    def latest_image(self) -> Path:
        return self.root / "latest.jpg"

    @property
    def latest_meta(self) -> Path:
        return self.root / "latest.json"


def config_path() -> Path:
    return Path("config.json")


def load_config(path: Path | None = None) -> StationConfig:
    target = path or config_path()
    if target.exists():
        return StationConfig.model_validate(json.loads(target.read_text()))
    return StationConfig()


def save_config(config: StationConfig, path: Path | None = None) -> None:
    target = path or config_path()
    target.write_text(config.model_dump_json(indent=2) + "\n")
