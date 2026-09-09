from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .catalog import CATALOG
from .coords import gnomonic_xy, sensor_fov_deg


@dataclass
class Optics:
    focal_mm: float
    aperture_mm: float
    pixel_um: float
    width: int
    height: int
    color: bool = True


def _gaussian_stamp(sigma: float, radius: int | None = None) -> np.ndarray:
    sigma = max(0.45, sigma)
    r = int(radius or max(3, math.ceil(sigma * 3.5)))
    y, x = np.mgrid[-r : r + 1, -r : r + 1]
    g = np.exp(-(x * x + y * y) / (2.0 * sigma * sigma))
    return g


def render_frame(
    optics: Optics,
    ra_h: float,
    dec_deg: float,
    exposure_s: float,
    gain: float,
    hfr_px: float,
    rng: np.random.Generator,
    rotation_deg: float = 0.0,
    sky_adu: float = 180.0,
    extra_stars: int = 220,
    tracking_err_px: float = 0.0,
) -> np.ndarray:
    w, h = optics.width, optics.height
    fov_x, fov_y = sensor_fov_deg(optics.pixel_um, w, optics.height, optics.focal_mm)
    img = np.zeros((h, w), dtype=np.float32)
    # sky gradient
    yy, xx = np.indices((h, w))
    vign = 1.0 - 0.22 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    img += sky_adu * np.clip(vign, 0.35, 1.0) * max(0.2, min(8.0, exposure_s))

    rot = math.radians(rotation_deg)
    cr, sr = math.cos(rot), math.sin(rot)
    scale_x = w / math.radians(max(fov_x, 1e-3))
    scale_y = h / math.radians(max(fov_y, 1e-3))
    sigma = max(0.55, hfr_px / 1.177)  # HFR ≈ 1.177 σ for Gaussian
    stamp = _gaussian_stamp(sigma)
    sh, sw = stamp.shape
    r = sh // 2

    def paint(px: float, py: float, flux: float) -> None:
        px += tracking_err_px
        ix, iy = int(px) - r, int(py) - r
        if ix + sw < 0 or iy + sh < 0 or ix >= w or iy >= h:
            return
        x0, y0 = max(0, ix), max(0, iy)
        x1, y1 = min(w, ix + sw), min(h, iy + sh)
        sx0, sy0 = x0 - ix, y0 - iy
        img[y0:y1, x0:x1] += stamp[sy0 : sy0 + (y1 - y0), sx0 : sx0 + (x1 - x0)] * flux

    # catalog sources
    for obj in CATALOG:
        x, y, c = gnomonic_xy(obj.ra_hours, obj.dec_deg, ra_h, dec_deg)
        if c < 0.2:
            continue
        xr = x * cr - y * sr
        yr = x * sr + y * cr
        px = w / 2 + xr * scale_x
        py = h / 2 - yr * scale_y
        if px < -20 or py < -20 or px > w + 20 or py > h + 20:
            continue
        mag = obj.mag
        flux = exposure_s * (10 ** (-0.4 * (mag - 6.0))) * (80.0 + gain)
        if obj.kind == "Star":
            paint(px, py, flux * 18)
            if mag < 1.5:
                _spikes(img, px, py, flux * 0.4)
        else:
            _extended(img, px, py, obj.size_arcmin, fov_x, w, flux, obj.kind)

    # random field stars — keep a few bright enough for plate solving
    for i in range(extra_stars):
        mag = float(rng.uniform(5.2, 12.5) if i > 24 else rng.uniform(4.8, 8.8))
        dx = rng.uniform(-fov_x * 0.48, fov_x * 0.48)
        dy = rng.uniform(-fov_y * 0.48, fov_y * 0.48)
        px = w / 2 + (dx / fov_x) * w
        py = h / 2 + (dy / fov_y) * h
        flux = exposure_s * (10 ** (-0.4 * (mag - 4.5))) * (140.0 + gain)
        paint(px, py, flux)

    # read noise + poisson
    img = np.clip(img, 0, None)
    shot = rng.normal(0, np.sqrt(np.clip(img, 1, None)) * 0.25, size=img.shape)
    read = rng.normal(0, 4.5 + 18 / max(1.0, gain / 30), size=img.shape)
    img = img + shot + read + 32
    return np.clip(img, 0, 65535)


def _extended(img: np.ndarray, px: float, py: float, size_arcmin: float, fov_x: float, width: int, flux: float, kind: str) -> None:
    pix_per_arcmin = width / (fov_x * 60.0)
    rad = max(2.0, min(width * 0.45, size_arcmin * pix_per_arcmin * 0.35))
    r = int(min(80, max(6, rad * 2.2)))
    h, w = img.shape
    ix, iy = int(px), int(py)
    if ix < -r or iy < -r or ix >= w + r or iy >= h + r:
        return
    y0, x0 = np.ogrid[-r : r + 1, -r : r + 1]
    if kind == "Gal":
        ellipse = (x0 / (rad * 0.9 + 1e-3)) ** 2 + (y0 / (rad * 0.45 + 1e-3)) ** 2
        core = np.exp(-ellipse)
    elif kind in {"Neb", "SNR"}:
        ellipse = (x0 * x0 + y0 * y0) / (rad * rad + 1e-3)
        core = np.exp(-ellipse * 0.7) * (0.55 + 0.45 * np.sin(x0 * 0.4) ** 2)
    elif kind in {"GC", "OC"}:
        rr = np.sqrt(x0 * x0 + y0 * y0)
        core = np.exp(-(rr / (rad * 0.55 + 1e-3)) ** 1.4)
    else:
        core = np.exp(-(x0 * x0 + y0 * y0) / (2 * (rad * 0.4) ** 2))
    y1, x1 = iy - r, ix - r
    ya, xa = max(0, y1), max(0, x1)
    yb, xb = min(h, iy + r + 1), min(w, ix + r + 1)
    sy, sx = ya - y1, xa - x1
    img[ya:yb, xa:xb] += core[sy : sy + (yb - ya), sx : sx + (xb - xa)] * flux * 0.08


def _spikes(img: np.ndarray, px: float, py: float, flux: float) -> None:
    h, w = img.shape
    for ang in (0, 90):
        for t in range(-18, 19):
            x = int(px + t * math.cos(math.radians(ang)))
            y = int(py + t * math.sin(math.radians(ang)))
            if 0 <= x < w and 0 <= y < h:
                img[y, x] += flux * (1.0 - abs(t) / 18.0)


def to_preview_rgb(mono: np.ndarray, color: bool, stretch: float = 0.22) -> np.ndarray:
    from .stretch import asinh_stretch

    base = asinh_stretch(mono, stretch=stretch)
    if not color:
        u8 = (base * 255).astype(np.uint8)
        return np.stack([u8, u8, u8], axis=-1)
    # fake OSC: warm nebula / cool sky
    r = np.clip(base * 1.05 + 0.04, 0, 1)
    g = np.clip(base * 0.98, 0, 1)
    b = np.clip(base * 1.12 + 0.03, 0, 1)
    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255).astype(np.uint8)
