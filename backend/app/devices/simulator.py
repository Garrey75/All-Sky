from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from ..astro.catalog import get_object
from ..astro.coords import (
    altaz,
    clamp_dec,
    format_dec,
    format_ra,
    pixel_scale_arcsec,
    ra_dec_offset,
    sensor_fov_deg,
    wrap_ra_hours,
)
from ..astro.hfr import detect_stars, median_hfr
from ..astro.platesolve import solve_from_pointing
from ..astro.polar import adjustment_advice, pa_quality, polar_error_from_solves
from ..astro.render import Optics, render_frame, to_preview_rgb
from ..config import DEFAULT_ELEV, DEFAULT_LAT, DEFAULT_LON


@dataclass
class CameraState:
    name: str
    connected: bool = False
    width: int = 2604
    height: int = 2200
    pixel_um: float = 3.76
    color: bool = True
    gain: int = 100
    offset: int = 40
    binning: int = 1
    exposure: float = 2.0
    cooler_on: bool = True
    target_temp: float = -10.0
    temperature: float = 12.0
    cooler_power: int = 0
    exposing: bool = False
    remaining: float = 0.0
    is_guide: bool = False


@dataclass
class MountState:
    name: str
    connected: bool = False
    ra_hours: float = 5.5881
    dec_deg: float = -5.3911
    tracking: bool = True
    slewing: bool = False
    parked: bool = False
    pier: str = "west"
    rate: float = 0.5
    pole_az_err: float = 420.0  # arcsec
    pole_alt_err: float = 280.0
    rotation: float = 1.8


@dataclass
class FocuserState:
    name: str
    connected: bool = False
    position: int = 11840
    best: int = 12500
    moving: bool = False
    min_pos: int = 0
    max_pos: int = 25000


@dataclass
class FilterWheelState:
    name: str
    connected: bool = False
    position: int = 0
    filters: list[str] = field(default_factory=lambda: ["L", "R", "G", "B", "Ha", "OIII", "SII"])


@dataclass
class PowerState:
    ports: list[dict] = field(
        default_factory=lambda: [
            {"id": 1, "name": "主相机", "on": True, "amps": 0.42},
            {"id": 2, "name": "赤道仪", "on": True, "amps": 0.85},
            {"id": 3, "name": "电调焦", "on": True, "amps": 0.12},
            {"id": 4, "name": "加热带", "on": False, "amps": 0.0},
        ]
    )
    voltage: float = 12.32
    input_amps: float = 1.55


class Simulator:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.rng = np.random.default_rng(42)
        self.lat = DEFAULT_LAT
        self.lon = DEFAULT_LON
        self.elev = DEFAULT_ELEV
        self.tz_offset = 8.0
        self.main_focal = 580.0
        self.main_aperture = 80.0
        self.guide_focal = 240.0
        self.camera = CameraState(name="OrgCam 2600MC (模拟)")
        self.guide = CameraState(
            name="OrgCam 120MM Mini (模拟)",
            width=1280,
            height=960,
            pixel_um=3.75,
            color=False,
            gain=80,
            exposure=1.0,
            cooler_on=False,
            is_guide=True,
        )
        self.mount = MountState(name="OrgMount AM5 (模拟)")
        self.focuser = FocuserState(name="OrgFocus EAF (模拟)")
        self.wheel = FilterWheelState(name="OrgWheel EFW (模拟)")
        self.power = PowerState()
        self.logs: list[dict] = []
        self.preview_jpeg: bytes = b""
        self.guide_jpeg: bytes = b""
        self.last_image: np.ndarray | None = None
        self.last_guide: np.ndarray | None = None
        self.last_stars: list[dict] = []
        self.last_hfr = 2.8
        self.last_solve: dict | None = None
        self.guide_running = False
        self.guide_calibrated = False
        self.guide_samples: list[dict] = []
        self.guide_rms = {"ra": 0.0, "dec": 0.0, "total": 0.0}
        self.polar_step = 0
        self.polar_solves: list[dict] = []
        self.polar_result: dict | None = None
        self.focus_curve: list[dict] = []
        self.stack: np.ndarray | None = None
        self.stack_n = 0
        self.connected_all = False
        self._stop = False
        self.log("系统就绪。使用模拟设备，无需真实相机/赤道仪。")

    def log(self, message: str, level: str = "info") -> None:
        item = {"t": datetime.now().strftime("%H:%M:%S"), "level": level, "msg": message}
        self.logs.append(item)
        self.logs = self.logs[-200:]

    def available_devices(self) -> dict:
        return {
            "cameras": [self.camera.name, "模拟 CMOS 533MC", "单反/微单 (快门线)"],
            "guiders": [self.guide.name, "主相机导星"],
            "mounts": [self.mount.name, "EQMOD / SkyWatcher", "Celestron NexStar", "iOptron CEM/HAE"],
            "focusers": [self.focuser.name, "无"],
            "wheels": [self.wheel.name, "无"],
            "backend": "simulator",
        }

    def connect(self, payload: dict) -> None:
        with self.lock:
            if "lat" in payload:
                self.lat = float(payload["lat"])
            if "lon" in payload:
                self.lon = float(payload["lon"])
            if "focal" in payload:
                self.main_focal = float(payload["focal"])
            if "aperture" in payload:
                self.main_aperture = float(payload["aperture"])
            if "guide_focal" in payload:
                self.guide_focal = float(payload["guide_focal"])
            self.camera.connected = True
            self.guide.connected = payload.get("guide", True)
            self.mount.connected = payload.get("mount", True)
            self.focuser.connected = payload.get("focuser", True)
            self.wheel.connected = payload.get("wheel", True)
            self.connected_all = True
            self.log(f"设备已连接：{self.camera.name} / {self.mount.name}")

    def disconnect(self) -> None:
        with self.lock:
            self.camera.connected = self.guide.connected = False
            self.mount.connected = self.focuser.connected = self.wheel.connected = False
            self.connected_all = False
            self.guide_running = False
            self.log("已断开全部设备")

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def optics(self, cam: CameraState, focal: float, preview: bool = True) -> Optics:
        b = max(1, cam.binning)
        width, height = cam.width // b, cam.height // b
        pixel_um = cam.pixel_um * b
        max_w = 720 if preview else min(width, 1600)
        if width > max_w:
            factor = width / max_w
            height = max(2, int(height / factor))
            pixel_um *= factor
            width = max_w
        return Optics(
            focal_mm=focal,
            aperture_mm=self.main_aperture if not cam.is_guide else 30.0,
            pixel_um=pixel_um,
            width=width,
            height=height,
            color=cam.color,
        )

    def focus_hfr(self, cam: CameraState) -> float:
        err = abs(self.focuser.position - self.focuser.best) / 140.0
        seeing = 1.55 + 0.15 * self.rng.normal()
        extra = 0.0 if cam.is_guide else err
        return max(0.85, seeing + extra)

    def capture(self, guide: bool = False, exposure: float | None = None, stack: bool = False) -> dict:
        cam = self.guide if guide else self.camera
        if not cam.connected:
            raise RuntimeError("相机未连接")
        exp = float(exposure if exposure is not None else cam.exposure)
        cam.exposing = True
        cam.remaining = exp
        # simulate exposure without blocking the whole lock
        steps = max(1, int(min(exp, 4) * 6))
        dt = exp / steps
        for _ in range(steps):
            if self._stop:
                break
            time.sleep(min(0.03, dt))
            cam.remaining = max(0.0, cam.remaining - dt)
            if cam.cooler_on:
                cam.temperature += (cam.target_temp - cam.temperature) * 0.02
                cam.cooler_power = int(min(100, abs(cam.target_temp - 18) * 3))
            else:
                cam.temperature += (18 - cam.temperature) * 0.01
        cam.exposing = False
        cam.remaining = 0.0

        with self.lock:
            optics = self.optics(cam, self.guide_focal if guide else self.main_focal)
            hfr = self.focus_hfr(cam)
            tracking = 0.0 if self.mount.tracking and not self.mount.slewing else 6.0
            if self.guide_running and not guide:
                tracking = min(tracking, 0.35)
            frame = render_frame(
                optics,
                self.mount.ra_hours,
                self.mount.dec_deg,
                exposure_s=exp,
                gain=cam.gain,
                hfr_px=hfr,
                rng=self.rng,
                rotation_deg=self.mount.rotation,
                tracking_err_px=tracking,
                extra_stars=90 if guide else 180,
            )
            stars = detect_stars(frame, max_stars=30)
            hfr_m = median_hfr(frame) if stars else hfr
            rgb = to_preview_rgb(frame, cam.color)
            jpeg = _encode_jpeg(rgb)
            if guide:
                self.last_guide = frame
                self.guide_jpeg = jpeg
            else:
                if stack:
                    from ..astro.stretch import live_stack

                    if self.stack is None or self.stack.shape != frame.shape:
                        self.stack = frame.astype(np.float64)
                        self.stack_n = 1
                    else:
                        self.stack = live_stack(self.stack, frame, 0.0, 0.0, self.stack_n)
                        self.stack_n += 1
                    frame = self.stack
                    rgb = to_preview_rgb(frame, cam.color)
                    jpeg = _encode_jpeg(rgb)
                self.last_image = frame
                self.preview_jpeg = jpeg
                self.last_stars = stars
                self.last_hfr = hfr_m
            from ..astro.stretch import histogram

            hist = histogram(frame)
            return {
                "width": optics.width,
                "height": optics.height,
                "hfr": round(hfr_m, 2),
                "stars": stars,
                "star_count": len(stars),
                "histogram": hist,
                "jpeg": jpeg,
                "guide": guide,
                "exposure": exp,
                "stack_n": 0 if guide else self.stack_n,
            }

    def solve(self, sync: bool = False) -> dict:
        if self.last_image is None:
            raise RuntimeError("请先拍摄预览图再解析")
        cam = self.camera
        optics = self.optics(cam, self.main_focal)
        result = solve_from_pointing(
            self.mount.ra_hours,
            self.mount.dec_deg,
            optics.width,
            optics.height,
            cam.pixel_um * cam.binning,
            self.main_focal,
            len(self.last_stars),
            rotation_deg=self.mount.rotation,
        )
        data = result.to_dict()
        # inject small pointing residual from polar error
        data["ra_hours"] += self.mount.pole_az_err / 3600.0 / 15.0 / 20.0
        data["dec_deg"] += self.mount.pole_alt_err / 3600.0 / 40.0
        if sync:
            self.mount.ra_hours = wrap_ra_hours(data["ra_hours"])
            self.mount.dec_deg = clamp_dec(data["dec_deg"])
            self.log("已将解析坐标同步到赤道仪")
        self.last_solve = data
        self.log("解析成功" if data["success"] else data["message"])
        return data

    def goto(self, ra_h: float, dec_deg: float, name: str = "") -> dict:
        if not self.mount.connected:
            raise RuntimeError("赤道仪未连接")
        self.mount.slewing = True
        self.mount.parked = False
        # simulate slew time
        time.sleep(0.6)
        self.mount.ra_hours = wrap_ra_hours(ra_h)
        self.mount.dec_deg = clamp_dec(dec_deg)
        self.mount.slewing = False
        self.mount.tracking = True
        alt, az = altaz(self.mount.ra_hours, self.mount.dec_deg, self.lat, self.lon, self.now())
        self.mount.pier = "east" if alt > 0 and hour_west(self.mount.ra_hours, self.lat, self.lon, self.now()) else "west"
        self.log(f"GoTo {'完成' if not name else name}  {format_ra(ra_h)} {format_dec(dec_deg)}")
        return self.mount_snapshot()

    def goto_object(self, oid: str) -> dict:
        obj = get_object(oid)
        if not obj:
            raise RuntimeError(f"目标未找到：{oid}")
        return self.goto(obj.ra_hours, obj.dec_deg, obj.name_zh or obj.name)

    def slew_fixed(self, direction: str, rate: float = 1.0) -> dict:
        step = 0.08 * rate  # degrees-ish
        ra, dec = self.mount.ra_hours, self.mount.dec_deg
        if direction == "n":
            dec += step
        elif direction == "s":
            dec -= step
        elif direction == "e":
            ra -= step / 15.0
        elif direction == "w":
            ra += step / 15.0
        self.mount.ra_hours = wrap_ra_hours(ra)
        self.mount.dec_deg = clamp_dec(dec)
        return self.mount_snapshot()

    def park(self) -> dict:
        self.mount.parked = True
        self.mount.tracking = False
        self.mount.ra_hours = 0.0
        self.mount.dec_deg = self.lat
        self.log("赤道仪已回停")
        return self.mount_snapshot()

    def set_tracking(self, on: bool) -> dict:
        self.mount.tracking = on
        return self.mount_snapshot()

    def move_focus(self, position: int | None = None, delta: int | None = None) -> dict:
        self.focuser.moving = True
        time.sleep(0.15)
        if position is not None:
            self.focuser.position = int(position)
        if delta is not None:
            self.focuser.position += int(delta)
        self.focuser.position = max(self.focuser.min_pos, min(self.focuser.max_pos, self.focuser.position))
        self.focuser.moving = False
        return self.focuser_snapshot()

    def autofocus(self) -> dict:
        start = self.focuser.position
        samples = []
        for pos in range(start - 900, start + 901, 150):
            pos = max(self.focuser.min_pos, min(self.focuser.max_pos, pos))
            self.focuser.position = pos
            err = abs(pos - self.focuser.best) / 140.0
            hfr = max(0.9, 1.5 + err + abs(self.rng.normal(0, 0.08)))
            samples.append({"position": pos, "hfr": round(hfr, 3)})
        xs = np.array([s["position"] for s in samples], dtype=float)
        ys = np.array([s["hfr"] for s in samples], dtype=float)
        coef = np.polyfit(xs, ys, 2)
        if coef[0] > 1e-10:
            vertex = -coef[1] / (2 * coef[0])
            best = int(np.clip(vertex, xs.min(), xs.max()))
        else:
            best = int(xs[int(np.argmin(ys))])
        self.focuser.position = int(best)
        self.focus_curve = samples
        self.log(f"自动对焦完成，位置 {self.focuser.position}，HFR {min(ys):.2f}")
        return {"curve": samples, "position": self.focuser.position, "hfr": round(float(min(ys)), 3)}

    def start_guiding(self) -> None:
        self.guide_running = True
        if not self.guide_calibrated:
            self.guide_calibrated = True
            self.log("导星校准完成")
        self.log("开始导星")

    def stop_guiding(self) -> None:
        self.guide_running = False
        self.log("导星已停止")

    def tick_guiding(self) -> dict | None:
        if not self.guide_running:
            return None
        polar = math.hypot(self.mount.pole_az_err, self.mount.pole_alt_err) / 3600.0
        ra_err = self.rng.normal(0, 0.35 + polar * 0.4)
        dec_err = self.rng.normal(0, 0.28 + polar * 0.5)
        sample = {
            "t": time.time(),
            "ra": round(ra_err, 3),
            "dec": round(dec_err, 3),
            "pulse_ra": round(-ra_err * 0.6, 3),
            "pulse_dec": round(-dec_err * 0.5, 3),
        }
        self.guide_samples.append(sample)
        self.guide_samples = self.guide_samples[-200:]
        recent = self.guide_samples[-30:]
        ra_rms = float(np.sqrt(np.mean([s["ra"] ** 2 for s in recent])))
        dec_rms = float(np.sqrt(np.mean([s["dec"] ** 2 for s in recent])))
        self.guide_rms = {
            "ra": round(ra_rms, 3),
            "dec": round(dec_rms, 3),
            "total": round(math.hypot(ra_rms, dec_rms), 3),
        }
        return sample

    def polar_start(self) -> dict:
        self.polar_step = 1
        self.polar_solves = []
        self.polar_result = None
        self.log("开始极轴校准：拍摄第一张解析图")
        return {"step": 1, "instruction": "拍摄当前指向并解析，然后赤道仪将向西转动约 60°。"}

    def polar_capture(self) -> dict:
        if self.polar_step == 0:
            self.polar_start()
        if self.polar_step <= 1:
            self.capture(exposure=0.8)
            solved = self.solve(sync=False)
            self.polar_solves.append(solved)
            self.mount.ra_hours = wrap_ra_hours(self.mount.ra_hours + 4.0)
            self.polar_step = 2
        self.capture(exposure=0.8)
        solved = self.solve(sync=False)
        self.polar_solves.append(solved)
        first, second = self.polar_solves[0], self.polar_solves[-1]
        err = polar_error_from_solves(
            first["ra_hours"],
            first["dec_deg"],
            second["ra_hours"],
            second["dec_deg"],
            expected_dra_deg=60.0,
        )
        err["az_arcsec"] = self.mount.pole_az_err
        err["alt_arcsec"] = self.mount.pole_alt_err
        err["total_arcsec"] = math.hypot(err["az_arcsec"], err["alt_arcsec"])
        advice = adjustment_advice(err["az_arcsec"], err["alt_arcsec"])
        self.polar_result = {
            **err,
            **advice,
            "quality": pa_quality(err["total_arcsec"]),
        }
        self.polar_step = 3
        self.log(f"极轴误差 {err['total_arcsec']/60:.1f}'")
        return {"step": 3, "solve": solved, "result": self.polar_result}

    def polar_adjust(self, d_az: float, d_alt: float) -> dict:
        self.mount.pole_az_err -= d_az
        self.mount.pole_alt_err -= d_alt
        if self.polar_result:
            self.polar_result["az_arcsec"] = self.mount.pole_az_err
            self.polar_result["alt_arcsec"] = self.mount.pole_alt_err
            self.polar_result["total_arcsec"] = math.hypot(self.mount.pole_az_err, self.mount.pole_alt_err)
            self.polar_result.update(adjustment_advice(self.mount.pole_az_err, self.mount.pole_alt_err))
            self.polar_result["quality"] = pa_quality(self.polar_result["total_arcsec"])
        return self.polar_result or {}

    def set_filter(self, index: int) -> dict:
        self.wheel.position = max(0, min(len(self.wheel.filters) - 1, int(index)))
        time.sleep(0.2)
        return self.wheel_snapshot()

    def set_power(self, port: int, on: bool) -> dict:
        for p in self.power.ports:
            if p["id"] == port:
                p["on"] = on
                p["amps"] = 0.0 if not on else {1: 0.42, 2: 0.85, 3: 0.12, 4: 0.9}[port]
        self.power.input_amps = sum(p["amps"] for p in self.power.ports) + 0.22
        return {"ports": self.power.ports, "voltage": self.power.voltage, "amps": self.power.input_amps}

    def update_camera(self, payload: dict, guide: bool = False) -> dict:
        cam = self.guide if guide else self.camera
        for key in ("gain", "offset", "binning", "exposure", "target_temp"):
            if key in payload:
                setattr(cam, key, type(getattr(cam, key))(payload[key]))
        if "cooler_on" in payload:
            cam.cooler_on = bool(payload["cooler_on"])
        return self.camera_snapshot(guide)

    def camera_snapshot(self, guide: bool = False) -> dict:
        cam = self.guide if guide else self.camera
        b = max(1, cam.binning)
        return {
            "name": cam.name,
            "connected": cam.connected,
            "width": cam.width // b,
            "height": cam.height // b,
            "pixel_um": cam.pixel_um * b,
            "color": cam.color,
            "gain": cam.gain,
            "offset": cam.offset,
            "binning": cam.binning,
            "exposure": cam.exposure,
            "cooler_on": cam.cooler_on,
            "target_temp": cam.target_temp,
            "temperature": round(cam.temperature, 1),
            "cooler_power": cam.cooler_power,
            "exposing": cam.exposing,
            "remaining": round(cam.remaining, 2),
            "pixel_scale": round(pixel_scale_arcsec(cam.pixel_um * b, self.guide_focal if guide else self.main_focal), 3),
            "fov": [
                round(x, 3)
                for x in sensor_fov_deg(cam.pixel_um * b, cam.width // b, cam.height // b, self.guide_focal if guide else self.main_focal)
            ],
        }

    def mount_snapshot(self) -> dict:
        alt, az = altaz(self.mount.ra_hours, self.mount.dec_deg, self.lat, self.lon, self.now())
        return {
            "name": self.mount.name,
            "connected": self.mount.connected,
            "ra_hours": self.mount.ra_hours,
            "dec_deg": self.mount.dec_deg,
            "ra": format_ra(self.mount.ra_hours),
            "dec": format_dec(self.mount.dec_deg),
            "alt": round(alt, 2),
            "az": round(az, 2),
            "tracking": self.mount.tracking,
            "slewing": self.mount.slewing,
            "parked": self.mount.parked,
            "pier": self.mount.pier,
            "rate": self.mount.rate,
        }

    def focuser_snapshot(self) -> dict:
        return {
            "name": self.focuser.name,
            "connected": self.focuser.connected,
            "position": self.focuser.position,
            "moving": self.focuser.moving,
            "min": self.focuser.min_pos,
            "max": self.focuser.max_pos,
        }

    def wheel_snapshot(self) -> dict:
        return {
            "name": self.wheel.name,
            "connected": self.wheel.connected,
            "position": self.wheel.position,
            "filter": self.wheel.filters[self.wheel.position],
            "filters": self.wheel.filters,
        }

    def status(self) -> dict:
        import os
        import shutil

        usage = shutil.disk_usage(str(os.getcwd()))
        alt, az = altaz(self.mount.ra_hours, self.mount.dec_deg, self.lat, self.lon, self.now())
        return {
            "connected": self.connected_all,
            "backend": "simulator",
            "time": self.now().isoformat(),
            "site": {"lat": self.lat, "lon": self.lon, "elev": self.elev},
            "optics": {
                "focal": self.main_focal,
                "aperture": self.main_aperture,
                "guide_focal": self.guide_focal,
                "f_ratio": round(self.main_focal / max(1.0, self.main_aperture), 1),
            },
            "camera": self.camera_snapshot(False),
            "guide_camera": self.camera_snapshot(True),
            "mount": self.mount_snapshot(),
            "focuser": self.focuser_snapshot(),
            "wheel": self.wheel_snapshot(),
            "power": {
                "ports": self.power.ports,
                "voltage": self.power.voltage,
                "amps": round(self.power.input_amps, 2),
            },
            "guiding": {
                "running": self.guide_running,
                "calibrated": self.guide_calibrated,
                "rms": self.guide_rms,
                "samples": self.guide_samples[-80:],
            },
            "polar": {
                "step": self.polar_step,
                "result": self.polar_result,
                "instruction": {
                    0: "点击开始，然后拍摄两张解析图。",
                    1: "拍摄第一张，随后赤道仪将自动向西转 60° 并拍第二张。",
                    2: "正在拍摄第二张…",
                    3: "校准完成，按箭头微调极轴。",
                }.get(self.polar_step, ""),
            },
            "hfr": self.last_hfr,
            "stars": len(self.last_stars),
            "solve": self.last_solve,
            "cpu_temp": 47.5,
            "disk_free_gb": round(usage.free / 1e9, 1),
            "logs": self.logs[-30:],
            "alt": round(alt, 2),
            "az": round(az, 2),
        }


def hour_west(ra_h: float, lat: float, lon: float, dt: datetime) -> bool:
    from ..astro.coords import hour_angle_deg, lst_deg

    return hour_angle_deg(ra_h, lst_deg(dt, lon)) > 0


def _encode_jpeg(rgb: np.ndarray) -> bytes:
    from io import BytesIO

    from PIL import Image

    h, w = rgb.shape[:2]
    max_w = 960
    if w > max_w:
        nh = int(h * max_w / w)
        img = Image.fromarray(rgb).resize((max_w, nh))
    else:
        img = Image.fromarray(rgb)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return buf.getvalue()
