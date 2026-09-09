from __future__ import annotations

import numpy as np


def half_flux_radius(image: np.ndarray, x: float, y: float, box: int = 21) -> float:
    """Compute HFR (half-flux radius) around a star centroid in pixels."""
    h, w = image.shape
    x0 = int(round(x))
    y0 = int(round(y))
    r = box // 2
    x1, x2 = max(0, x0 - r), min(w, x0 + r + 1)
    y1, y2 = max(0, y0 - r), min(h, y0 + r + 1)
    cut = image[y1:y2, x1:x2].astype(np.float64)
    if cut.size < 9:
        return 9.0
    bg = np.percentile(cut, 15)
    star = np.clip(cut - bg, 0, None)
    total = float(star.sum())
    if total <= 1e-6:
        return 9.0
    yy, xx = np.indices(cut.shape)
    cx = float((star * xx).sum() / total)
    cy = float((star * yy).sum() / total)
    rr = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    order = np.argsort(rr.ravel())
    cum = np.cumsum(star.ravel()[order])
    half = total * 0.5
    idx = int(np.searchsorted(cum, half))
    radii = rr.ravel()[order]
    if idx >= len(radii):
        return float(radii[-1])
    return float(radii[idx])


def detect_stars(image: np.ndarray, max_stars: int = 40, threshold_sigma: float = 4.0) -> list[dict]:
    data = image.astype(np.float64)
    med = float(np.median(data))
    mad = float(np.median(np.abs(data - med))) + 1e-6
    thresh = med + threshold_sigma * 1.4826 * mad
    h, w = data.shape
    ys, xs = np.where(data > thresh)
    if len(xs) == 0:
        return []
    # greedy local maxima
    stars: list[dict] = []
    used = np.zeros(len(xs), dtype=bool)
    brightness = data[ys, xs]
    order = np.argsort(brightness)[::-1]
    min_dist2 = 8 * 8
    for idx in order:
        if used[idx]:
            continue
        x, y = int(xs[idx]), int(ys[idx])
        if x < 4 or y < 4 or x >= w - 4 or y >= h - 4:
            continue
        # refine centroid
        cut = data[y - 4 : y + 5, x - 4 : x + 5]
        bg = np.percentile(cut, 20)
        star = np.clip(cut - bg, 0, None)
        s = star.sum()
        if s <= 0:
            continue
        yy, xx = np.indices(cut.shape)
        cx = x - 4 + float((star * xx).sum() / s)
        cy = y - 4 + float((star * yy).sum() / s)
        too_close = False
        for st in stars:
            if (st["x"] - cx) ** 2 + (st["y"] - cy) ** 2 < min_dist2:
                too_close = True
                break
        if too_close:
            continue
        hfr = half_flux_radius(data, cx, cy)
        stars.append(
            {
                "x": round(cx, 2),
                "y": round(cy, 2),
                "peak": round(float(data[y, x] - med), 1),
                "hfr": round(hfr, 2),
                "flux": round(float(s), 1),
            }
        )
        if len(stars) >= max_stars:
            break
    return stars


def median_hfr(image: np.ndarray) -> float:
    stars = detect_stars(image, max_stars=25)
    if not stars:
        return 9.0
    vals = sorted(s["hfr"] for s in stars)[: max(1, len(stars) // 2 + 1)]
    return float(np.median(vals))
