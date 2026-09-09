from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .astro.fitsio import write_fits16
from .config import IMAGE_DIR
from .devices import sim


@dataclass
class SequenceItem:
    kind: str = "LIGHT"
    filter: str = "L"
    exposure: float = 30.0
    gain: int = 100
    binning: int = 1
    count: int = 5


@dataclass
class SequenceJob:
    id: str
    target: str
    ra_hours: float | None = None
    dec_deg: float | None = None
    items: list[SequenceItem] = field(default_factory=list)
    dither: bool = True
    meridian_flip: bool = True
    park_when_done: bool = False
    delay: float = 0.0


class Sequencer:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.paused = False
        self.abort = False
        self.job: SequenceJob | None = None
        self.progress: dict = {}
        self.captured: list[dict] = []
        self.thread: threading.Thread | None = None

    def snapshot(self) -> dict:
        return {
            "running": self.running,
            "paused": self.paused,
            "progress": self.progress,
            "captured": self.captured[-80:],
            "job": None
            if not self.job
            else {
                "id": self.job.id,
                "target": self.job.target,
                "items": [item.__dict__ for item in self.job.items],
                "dither": self.job.dither,
                "meridian_flip": self.job.meridian_flip,
                "park_when_done": self.job.park_when_done,
            },
        }

    def start(self, payload: dict) -> dict:
        if self.running:
            raise RuntimeError("序列已在运行")
        items = [
            SequenceItem(
                kind=i.get("kind", "LIGHT"),
                filter=i.get("filter", "L"),
                exposure=float(i.get("exposure", 30)),
                gain=int(i.get("gain", 100)),
                binning=int(i.get("binning", 1)),
                count=int(i.get("count", 1)),
            )
            for i in payload.get("items", [])
        ]
        if not items:
            items = [SequenceItem()]
        job = SequenceJob(
            id=uuid.uuid4().hex[:8],
            target=payload.get("target") or "Preview",
            ra_hours=payload.get("ra_hours"),
            dec_deg=payload.get("dec_deg"),
            items=items,
            dither=bool(payload.get("dither", True)),
            meridian_flip=bool(payload.get("meridian_flip", True)),
            park_when_done=bool(payload.get("park_when_done", False)),
            delay=float(payload.get("delay", 0)),
        )
        self.job = job
        self.abort = False
        self.paused = False
        self.running = True
        self.progress = {"item": 0, "frame": 0, "total": sum(i.count for i in items), "done": 0}
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        sim.log(f"开始自动拍摄 {job.target}，共 {self.progress['total']} 帧")
        return self.snapshot()

    def stop(self) -> dict:
        self.abort = True
        self.running = False
        sim.log("自动拍摄已停止")
        return self.snapshot()

    def pause(self, paused: bool) -> dict:
        self.paused = paused
        return self.snapshot()

    def _run(self) -> None:
        assert self.job is not None
        job = self.job
        try:
            if job.ra_hours is not None and job.dec_deg is not None:
                sim.goto(job.ra_hours, job.dec_deg, job.target)
            if job.delay:
                time.sleep(min(job.delay, 5))
            frame_index = 0
            for item_i, item in enumerate(job.items):
                if item.filter in sim.wheel.filters:
                    sim.set_filter(sim.wheel.filters.index(item.filter))
                sim.camera.gain = item.gain
                sim.camera.binning = item.binning
                for n in range(item.count):
                    while self.paused and not self.abort:
                        time.sleep(0.2)
                    if self.abort:
                        return
                    result = sim.capture(exposure=item.exposure)
                    frame_index += 1
                    name = f"{job.target}_{item.kind}_{item.filter}_{frame_index:04d}"
                    path = IMAGE_DIR / f"{name}.fits"
                    if sim.last_image is not None:
                        write_fits16(
                            path,
                            sim.last_image,
                            {
                                "OBJECT": job.target,
                                "IMAGETYP": item.kind,
                                "FILTER": item.filter,
                                "EXPTIME": str(item.exposure),
                                "GAIN": str(item.gain),
                                "DATE-OBS": datetime.now(timezone.utc).isoformat(),
                                "INSTRUME": sim.camera.name,
                                "FOCALLEN": str(sim.main_focal),
                            },
                        )
                    rec = {
                        "id": uuid.uuid4().hex[:10],
                        "name": name,
                        "path": str(path),
                        "kind": item.kind,
                        "filter": item.filter,
                        "exposure": item.exposure,
                        "hfr": result["hfr"],
                        "stars": result["star_count"],
                        "time": datetime.now().strftime("%H:%M:%S"),
                    }
                    self.captured.append(rec)
                    self.progress = {
                        "item": item_i,
                        "frame": n + 1,
                        "total": self.progress["total"],
                        "done": frame_index,
                    }
                    if job.dither and n + 1 < item.count:
                        sim.slew_fixed("e", 0.15)
            if job.park_when_done:
                sim.park()
            sim.log(f"自动拍摄完成 {job.target}")
        except Exception as exc:  # noqa: BLE001
            sim.log(f"自动拍摄失败：{exc}", "error")
        finally:
            self.running = False


sequencer = Sequencer()


def list_images() -> list[dict]:
    files = []
    if IMAGE_DIR.exists():
        for p in sorted(IMAGE_DIR.glob("*.fits"), key=lambda x: x.stat().st_mtime, reverse=True):
            files.append(
                {
                    "id": p.stem,
                    "name": p.name,
                    "path": str(p),
                    "size_mb": round(p.stat().st_size / 1e6, 2),
                    "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                }
            )
    files.extend(sequencer.captured)
    # unique by name
    seen = set()
    out = []
    for f in files:
        key = f.get("name") or f.get("id")
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out[:200]
