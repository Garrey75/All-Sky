from __future__ import annotations

from pathlib import Path

import numpy as np

from app.astro.fitsio import write_fits16


def test_fits_header_strips_non_ascii(tmp_path: Path):
    path = tmp_path / "cn.fits"
    img = np.zeros((8, 8), dtype=np.uint16)
    write_fits16(path, img, {"OBJECT": "猎户", "INSTRUME": "OrgCam 模拟"})
    raw = path.read_bytes()
    assert raw.startswith(b"SIMPLE")
    assert b"INSTRUME" in raw
    assert b"?" in raw or b"OrgCam" in raw
