from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_connect_and_status():
    r = client.post("/api/connect", json={"lat": 31.2, "lon": 121.4, "focal": 580})
    assert r.status_code == 200
    body = r.json()
    assert body["connected"] is True
    assert body["camera"]["connected"] is True


def test_catalog_search():
    r = client.get("/api/catalog", params={"q": "M42"})
    assert r.status_code == 200
    ids = [o["id"] for o in r.json()["objects"]]
    assert "M42" in ids


def test_preview_and_solve():
    client.post("/api/connect", json={})
    r = client.post("/api/preview", json={"exposure": 0.4})
    assert r.status_code == 200
    body = r.json()
    assert body["star_count"] >= 1
    assert body["image"].startswith("data:image/jpeg")
    s = client.post("/api/solve", json={"sync": True})
    assert s.status_code == 200
    assert s.json()["success"] is True


def test_goto_and_autorun():
    client.post("/api/connect", json={})
    g = client.post("/api/goto", json={"id": "M31"})
    assert g.status_code == 200
    r = client.post(
        "/api/autorun/start",
        json={
            "target": "M31",
            "items": [{"kind": "LIGHT", "filter": "L", "exposure": 0.2, "count": 1, "gain": 80, "binning": 2}],
        },
    )
    assert r.status_code == 200
    assert r.json()["running"] is True
    import time

    images = []
    for _ in range(40):
        time.sleep(0.15)
        st = client.get("/api/status").json()
        if not st["sequencer"]["running"]:
            images = client.get("/api/images").json()["images"]
            break
    assert images, "autorun should write at least one FITS frame"


def test_polar_workflow():
    client.post("/api/connect", json={})
    s = client.post("/api/polar/start")
    assert s.json()["step"] == 1
    c1 = client.post("/api/polar/capture")
    assert c1.json()["step"] == 3
    assert "result" in c1.json()
    adj = client.post("/api/polar/adjust", json={"az": 60, "alt": 40})
    assert adj.status_code == 200


def test_guide_and_focus():
    client.post("/api/connect", json={})
    client.post("/api/guide/start")
    st = client.get("/api/status").json()
    assert st["guiding"]["running"] is True
    af = client.post("/api/autofocus")
    assert "curve" in af.json()
    assert 9000 < af.json()["position"] < 18000
    client.post("/api/guide/stop")
