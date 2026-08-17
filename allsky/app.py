"""FastAPI station server: live image, archive, and night products."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from allsky.astronomy import is_night, moon_illumination, solar_position
from allsky.camera import DirectoryCamera, SkySimulator
from allsky.config import StationConfig, load_config
from allsky.storage import build_products, ensure_dirs, list_days, list_frames, product_path, save_capture

WEB_DIR = Path(__file__).resolve().parent / "web"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def camera_for(config: StationConfig):
    if config.demo_mode:
        return SkySimulator()
    inbox = config.root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    return DirectoryCamera(inbox)


def capture_once(config: StationConfig, when: datetime | None = None) -> dict:
    when = when or _now()
    image = camera_for(config).capture(config, when)
    sun_alt, sun_az = solar_position(config.latitude, config.longitude, when)
    path = save_capture(
        config,
        image,
        when,
        extra={"sun_alt": round(sun_alt, 2), "sun_az": round(sun_az, 2)},
    )
    return {"path": str(path), "captured_at": when.isoformat(), "sun_alt": sun_alt}


def seed_demo_night(config: StationConfig, frames: int | None = None) -> str:
    """Generate a 24-hour sequence so the dashboard is not empty on first run."""
    ensure_dirs(config)
    frames = frames or config.demo_frames
    day_date = (_now() - timedelta(days=1)).date()
    start = datetime(day_date.year, day_date.month, day_date.day, 0, 0, tzinfo=timezone.utc)
    day = start.strftime("%Y-%m-%d")
    span = timedelta(hours=23, minutes=50)
    for i in range(frames):
        when = start + span * (i / max(frames - 1, 1))
        capture_once(config, when)
    build_products(config, day)
    return day


async def capture_loop(config: StationConfig) -> None:
    while True:
        try:
            capture_once(config)
        except Exception:
            pass
        await asyncio.sleep(config.capture_interval_seconds)


def create_app(config: StationConfig | None = None) -> FastAPI:
    config = config or load_config()
    ensure_dirs(config)
    (config.root / "inbox").mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.config = config
        if config.demo_mode and not list_days(config) and os.environ.get("ALLSKY_NO_SEED") != "1":
            seed_demo_night(config)
        task = None
        if os.environ.get("ALLSKY_NO_CAPTURE") != "1":
            task = asyncio.create_task(capture_loop(config))
        yield
        if task:
            task.cancel()

    app = FastAPI(title=config.station_name, lifespan=lifespan)
    app.state.config = config
    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    def index():
        index_path = WEB_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(404, "web UI missing")
        return FileResponse(index_path)

    @app.get("/api/status")
    def status():
        cfg: StationConfig = app.state.config
        when = _now()
        sun_alt, sun_az = solar_position(cfg.latitude, cfg.longitude, when)
        moon_frac, moon_name = moon_illumination(when)
        days = list_days(cfg)
        latest_meta = {}
        if cfg.latest_meta.exists():
            latest_meta = json.loads(cfg.latest_meta.read_text())
        return {
            "station": cfg.station_name,
            "operator": cfg.operator,
            "latitude": cfg.latitude,
            "longitude": cfg.longitude,
            "elevation_m": cfg.elevation_m,
            "demo_mode": cfg.demo_mode,
            "utc": when.isoformat(),
            "sun_alt": round(sun_alt, 2),
            "sun_az": round(sun_az, 2),
            "is_night": is_night(cfg.latitude, cfg.longitude, when, cfg.night_threshold_deg),
            "moon_illumination": round(moon_frac, 3),
            "moon_phase": moon_name,
            "days": days,
            "latest": latest_meta,
            "capture_interval_seconds": cfg.capture_interval_seconds,
        }

    @app.get("/api/latest")
    def latest():
        cfg: StationConfig = app.state.config
        if not cfg.latest_image.exists():
            capture_once(cfg)
        return FileResponse(cfg.latest_image, media_type="image/jpeg")

    @app.get("/api/archive")
    def archive(day: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$")):
        cfg: StationConfig = app.state.config
        frames = list_frames(cfg, day)
        return {
            "day": day,
            "frames": [f"/api/frame/{day}/{path.name}" for path in frames],
            "count": len(frames),
        }

    @app.get("/api/frame/{day}/{name}")
    def frame(day: str, name: str):
        cfg: StationConfig = app.state.config
        path = cfg.captures_dir / day / name
        if not path.exists() or path.suffix.lower() != ".jpg":
            raise HTTPException(404, "frame not found")
        return FileResponse(path, media_type="image/jpeg")

    @app.post("/api/capture")
    def manual_capture():
        cfg: StationConfig = app.state.config
        return capture_once(cfg)

    @app.post("/api/products")
    def products(day: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$")):
        cfg: StationConfig = app.state.config
        try:
            result = build_products(cfg, day)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return result

    @app.get("/api/keogram")
    def keogram(day: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$")):
        cfg: StationConfig = app.state.config
        path = product_path(cfg, day, "keogram")
        if not path.exists():
            try:
                build_products(cfg, day)
            except FileNotFoundError as exc:
                raise HTTPException(404, str(exc)) from exc
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/startrails")
    def startrails(day: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$")):
        cfg: StationConfig = app.state.config
        path = product_path(cfg, day, "startrails")
        if not path.exists():
            try:
                build_products(cfg, day)
            except FileNotFoundError as exc:
                raise HTTPException(404, str(exc)) from exc
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/healthz")
    def healthz():
        return JSONResponse({"ok": True})

    return app


app = create_app()
