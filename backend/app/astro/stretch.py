from __future__ import annotations

import numpy as np


def asinh_stretch(image: np.ndarray, black: float | None = None, stretch: float = 0.25) -> np.ndarray:
    img = image.astype(np.float64)
    if black is None:
        black = float(np.percentile(img, 25))
    mid = float(np.percentile(img, 99.5) - black)
    if mid <= 1e-6:
        mid = 1.0
    norm = np.clip((img - black) / mid, 0, None)
    out = np.arcsinh(norm / max(1e-4, stretch)) / np.arcsinh(1.0 / max(1e-4, stretch))
    return np.clip(out, 0, 1)


def histogram(image: np.ndarray, bins: int = 256) -> dict:
    img = image.astype(np.float64)
    hist, edges = np.histogram(img, bins=bins, range=(float(img.min()), float(img.max()) + 1e-6))
    return {
        "bins": hist.astype(int).tolist(),
        "min": float(img.min()),
        "max": float(img.max()),
        "mean": float(img.mean()),
        "std": float(img.std()),
        "p01": float(np.percentile(img, 1)),
        "p50": float(np.percentile(img, 50)),
        "p99": float(np.percentile(img, 99.5)),
    }


def live_stack(stack: np.ndarray, frame: np.ndarray, dx: float, dy: float, n: int) -> np.ndarray:
    shifted = _shift(frame, dx, dy)
    if n <= 0:
        return shifted
    return (stack * n + shifted) / (n + 1)


def _shift(frame: np.ndarray, dx: float, dy: float) -> np.ndarray:
    iy, ix = int(round(dy)), int(round(dx))
    out = np.zeros_like(frame)
    h, w = frame.shape
    y1s, y1d = max(0, -iy), max(0, iy)
    x1s, x1d = max(0, -ix), max(0, ix)
    y2s, x2s = h - max(0, iy), w - max(0, ix)
    y2d, x2d = h - max(0, -iy), w - max(0, -ix)
    out[y1d:y2d, x1d:x2d] = frame[y1s:y2s, x1s:x2s]
    return out
