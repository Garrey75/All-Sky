from __future__ import annotations

from ..config import INDI_HOST, INDI_PORT
from .indi import IndiClient
from .simulator import Simulator

sim = Simulator()
indi: IndiClient | None = None


def boot() -> None:
    global indi
    if INDI_HOST:
        client = IndiClient(INDI_HOST, INDI_PORT)
        if client.ping():
            indi = client
            sim.log(f"已连接 INDI {INDI_HOST}:{INDI_PORT}", "info")
        else:
            sim.log(f"INDI {INDI_HOST}:{INDI_PORT} 不可达，使用模拟器", "warn")
