"""Optional INDI backend.

When ALLSKY_INDI_HOST is set, the controller will try to talk to an INDI server
(default port 7624) for mount + CCD. The protocol client is intentionally small:
it is enough to slew/sync an equatorial mount and trigger CCD exposures. If the
server is unreachable, the simulator remains in charge.
"""

from __future__ import annotations

import socket
import threading


class IndiClient:
    def __init__(self, host: str, port: int = 7624, timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.lock = threading.Lock()

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        self.sock = sock
        self.send('<getProperties version="1.7"/>')

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def send(self, xml: str) -> None:
        if not self.sock:
            raise RuntimeError("INDI 未连接")
        with self.lock:
            self.sock.sendall(xml.encode("utf-8"))

    def new_number(self, device: str, name: str, values: dict[str, float]) -> None:
        inner = "".join(f'<oneNumber name="{k}">{v}</oneNumber>' for k, v in values.items())
        self.send(f'<newNumberVector device="{device}" name="{name}">{inner}</newNumberVector>')

    def new_switch(self, device: str, name: str, on: str) -> None:
        self.send(
            f'<newSwitchVector device="{device}" name="{name}">'
            f'<oneSwitch name="{on}">On</oneSwitch></newSwitchVector>'
        )

    def try_slew(self, device: str, ra_h: float, dec: float) -> None:
        self.new_number(device, "EQUATORIAL_EOD_COORD", {"RA": ra_h, "DEC": dec})

    def try_expose(self, device: str, seconds: float) -> None:
        self.new_number(device, "CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": seconds})

    def ping(self) -> bool:
        try:
            if not self.sock:
                self.connect()
            return True
        except OSError:
            return False
