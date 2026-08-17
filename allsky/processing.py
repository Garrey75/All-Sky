"""Keogram and star-trail products from a night's frames."""

from __future__ import annotations

from collections.abc import Iterable

from PIL import Image, ImageChops


def make_keogram(frames: Iterable[Image.Image], slice_width: int = 2) -> Image.Image:
    """Stack a vertical center slice from each frame into a time-vs-altitude image."""
    columns: list[Image.Image] = []
    height = 0
    for frame in frames:
        rgb = frame.convert("RGB")
        height = rgb.size[1]
        cx = rgb.size[0] // 2
        left = max(0, cx - slice_width // 2)
        columns.append(rgb.crop((left, 0, left + slice_width, height)))
    if not columns:
        raise ValueError("need at least one frame to build a keogram")
    width = sum(col.size[0] for col in columns)
    keogram = Image.new("RGB", (width, height), (0, 0, 0))
    x = 0
    for col in columns:
        keogram.paste(col, (x, 0))
        x += col.size[0]
    return keogram


def make_startrails(frames: Iterable[Image.Image]) -> Image.Image:
    """Brightest-pixel composite, the usual all-sky star-trail stack."""
    stacked: Image.Image | None = None
    for frame in frames:
        rgb = frame.convert("RGB")
        stacked = rgb if stacked is None else ImageChops.lighter(stacked, rgb)
    if stacked is None:
        raise ValueError("need at least one frame to build star trails")
    return stacked
