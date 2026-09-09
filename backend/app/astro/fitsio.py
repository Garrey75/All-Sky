from __future__ import annotations

from pathlib import Path

import numpy as np


def write_fits16(path: Path, image: np.ndarray, header: dict[str, str]) -> None:
    data = np.clip(image, 0, 65535).astype(np.uint16)
    if not data.flags["C_CONTIGUOUS"]:
        data = np.ascontiguousarray(data)
    naxis2, naxis1 = data.shape
    cards = [
        "SIMPLE  =                    T / file does conform to FITS standard",
        "BITPIX  =                   16 / number of bits per data pixel",
        "NAXIS   =                    2 / number of data axes",
        f"NAXIS1  = {naxis1:20d} / length of data axis 1",
        f"NAXIS2  = {naxis2:20d} / length of data axis 2",
        "BZERO   =                32768 / offset data range to that of unsigned short",
        "BSCALE  =                    1 / default scaling factor",
        "EXTEND  =                    T / FITS dataset may contain extensions",
    ]
    for key, value in header.items():
        k = key.strip().upper()[:8].ljust(8)
        val = "".join(ch if ord(ch) < 128 else "?" for ch in str(value))
        if len(val) > 60:
            val = val[:60]
        if val[:1] in "TF" and len(val) == 1:
            line = f"{k}= {val:>20} /"
        else:
            try:
                float(val)
                line = f"{k}= {val:>20} /"
            except ValueError:
                line = f"{k}= '{val}'"
        cards.append(line[:80])
    cards.append("END")
    text = "".join(c.ljust(80) for c in cards)
    pad = (2880 - (len(text) % 2880)) % 2880
    blob = text.encode("ascii") + b" " * pad
    # FITS unsigned 16 via BZERO: store as signed with offset
    raw = (data.astype(np.int32) - 32768).astype(">i2").tobytes()
    extra = (2880 - (len(raw) % 2880)) % 2880
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob + raw + b"\x00" * extra)
