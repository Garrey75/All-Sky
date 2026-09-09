from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .astro.catalog import CATALOG, get_object, search_objects, tonight_best
from .astro.coords import altaz, format_dec, format_ra
from .config import ROOT
from .devices import boot, sim
from .sequencer import list_images, sequencer

app = FastAPI(title="All-Sky OrgPi", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

clients: set[WebSocket] = set()


@app.on_event("startup")
async def _startup() -> None:
    boot()
    asyncio.create_task(_guide_loop())
    asyncio.create_task(_broadcast_loop())


async def _guide_loop() -> None:
    while True:
        await asyncio.sleep(1.0)
        sample = sim.tick_guiding()
        if sample:
            await broadcast({"type": "guide", "sample": sample, "rms": sim.guide_rms})


async def _broadcast_loop() -> None:
    while True:
        await asyncio.sleep(1.5)
        await broadcast({"type": "status", "status": sim.status() | {"sequencer": sequencer.snapshot()}})


async def broadcast(payload: dict[str, Any]) -> None:
    dead = []
    for ws in list(clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    clients.add(ws)
    await ws.send_json({"type": "status", "status": sim.status() | {"sequencer": sequencer.snapshot()}})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.discard(ws)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": __version__, "name": "All-Sky OrgPi"}


@app.get("/api/status")
def status() -> dict:
    return sim.status() | {"sequencer": sequencer.snapshot()}


@app.get("/api/devices")
def devices() -> dict:
    return sim.available_devices()


@app.post("/api/connect")
def connect(payload: dict = Body(default_factory=dict)) -> dict:
    sim.connect(payload)
    return sim.status()


@app.post("/api/disconnect")
def disconnect() -> dict:
    sim.disconnect()
    return sim.status()


@app.post("/api/camera")
def camera_settings(payload: dict) -> dict:
    return sim.update_camera(payload, guide=bool(payload.get("guide")))


@app.post("/api/preview")
async def preview(payload: dict = Body(default_factory=dict)) -> dict:
    guide = bool(payload.get("guide"))
    exposure = payload.get("exposure")
    try:
        result = await asyncio.to_thread(sim.capture, guide, exposure, bool(payload.get("stack")))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    jpeg = base64.b64encode(result["jpeg"]).decode("ascii")
    await broadcast({"type": "preview", "guide": guide, "hfr": result["hfr"], "stars": result["star_count"]})
    return {
        "hfr": result["hfr"],
        "stars": result["stars"],
        "star_count": result["star_count"],
        "histogram": result["histogram"],
        "exposure": result["exposure"],
        "width": result["width"],
        "height": result["height"],
        "stack_n": result.get("stack_n", 0),
        "image": f"data:image/jpeg;base64,{jpeg}",
    }


@app.post("/api/stack/reset")
def stack_reset() -> dict:
    sim.stack = None
    sim.stack_n = 0
    return {"stack_n": 0}


@app.get("/api/preview.jpg")
def preview_jpg(guide: int = 0) -> Response:
    data = sim.guide_jpeg if guide else sim.preview_jpeg
    if not data:
        raise HTTPException(404, "还没有预览图")
    return Response(data, media_type="image/jpeg")


@app.post("/api/solve")
def solve(payload: dict) -> dict:
    try:
        return sim.solve(sync=bool(payload.get("sync")))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/goto")
async def goto(payload: dict) -> dict:
    try:
        if payload.get("id"):
            result = await asyncio.to_thread(sim.goto_object, payload["id"])
        else:
            result = await asyncio.to_thread(sim.goto, float(payload["ra_hours"]), float(payload["dec_deg"]), payload.get("name", ""))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    return result


@app.post("/api/slew")
def slew(payload: dict) -> dict:
    return sim.slew_fixed(payload.get("direction", "n"), float(payload.get("rate", 1)))


@app.post("/api/park")
def park() -> dict:
    return sim.park()


@app.post("/api/tracking")
def tracking(payload: dict) -> dict:
    return sim.set_tracking(bool(payload.get("on", True)))


@app.post("/api/focus")
async def focus(payload: dict) -> dict:
    return await asyncio.to_thread(sim.move_focus, payload.get("position"), payload.get("delta"))


@app.post("/api/autofocus")
async def autofocus() -> dict:
    return await asyncio.to_thread(sim.autofocus)


@app.post("/api/filter")
def filter_set(payload: dict) -> dict:
    return sim.set_filter(int(payload["index"]))


@app.post("/api/power")
def power(payload: dict) -> dict:
    return sim.set_power(int(payload["port"]), bool(payload["on"]))


@app.post("/api/guide/start")
def guide_start() -> dict:
    sim.start_guiding()
    return sim.status()["guiding"]


@app.post("/api/guide/stop")
def guide_stop() -> dict:
    sim.stop_guiding()
    return sim.status()["guiding"]


@app.post("/api/polar/start")
def polar_start() -> dict:
    return sim.polar_start()


@app.post("/api/polar/capture")
async def polar_capture() -> dict:
    return await asyncio.to_thread(sim.polar_capture)


@app.post("/api/polar/adjust")
def polar_adjust(payload: dict) -> dict:
    return sim.polar_adjust(float(payload.get("az", 0)), float(payload.get("alt", 0)))


@app.post("/api/autorun/start")
def autorun_start(payload: dict) -> dict:
    try:
        return sequencer.start(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/autorun/stop")
def autorun_stop() -> dict:
    return sequencer.stop()


@app.post("/api/autorun/pause")
def autorun_pause(payload: dict) -> dict:
    return sequencer.pause(bool(payload.get("paused", True)))


@app.get("/api/images")
def images() -> dict:
    return {"images": list_images()}


@app.get("/api/catalog")
def catalog(q: str = "", lat: float | None = None, lon: float | None = None) -> dict:
    site_lat = sim.lat if lat is None else lat
    site_lon = sim.lon if lon is None else lon
    dt = datetime.now(timezone.utc)
    objs = search_objects(q) if q else [o for o in CATALOG if o.kind != "Star"][:40]
    out = []
    for o in objs:
        alt, az = altaz(o.ra_hours, o.dec_deg, site_lat, site_lon, dt)
        out.append(
            {
                "id": o.id,
                "name": o.name,
                "name_zh": o.name_zh,
                "ra_hours": o.ra_hours,
                "dec_deg": o.dec_deg,
                "ra": format_ra(o.ra_hours),
                "dec": format_dec(o.dec_deg),
                "mag": o.mag,
                "size_arcmin": o.size_arcmin,
                "kind": o.kind,
                "alt": round(alt, 1),
                "az": round(az, 1),
            }
        )
    return {
        "objects": out,
        "tonight": tonight_best(site_lat, site_lon, dt),
        "target": None if not q else (None if not get_object(q) else True),
    }


@app.get("/api/atlas")
def atlas() -> dict:
    dt = datetime.now(timezone.utc)
    stars = []
    dsos = []
    for o in CATALOG:
        alt, az = altaz(o.ra_hours, o.dec_deg, sim.lat, sim.lon, dt)
        rec = {
            "id": o.id,
            "name": o.name_zh or o.name,
            "ra_hours": o.ra_hours,
            "dec_deg": o.dec_deg,
            "mag": o.mag,
            "alt": alt,
            "az": az,
            "kind": o.kind,
            "size_arcmin": o.size_arcmin,
        }
        if o.kind == "Star":
            stars.append(rec)
        else:
            dsos.append(rec)
    return {
        "lat": sim.lat,
        "lon": sim.lon,
        "mount": sim.mount_snapshot(),
        "stars": stars,
        "dsos": dsos,
    }


frontend_dist = ROOT / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="ui")
