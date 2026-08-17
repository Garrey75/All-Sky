import os

import pytest
from fastapi.testclient import TestClient

from allsky.app import create_app, seed_demo_night
from allsky.config import StationConfig


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLSKY_NO_CAPTURE", "1")
    monkeypatch.setenv("ALLSKY_NO_SEED", "1")
    config = StationConfig(
        data_dir=str(tmp_path),
        image_size=96,
        demo_mode=True,
        demo_frames=6,
        capture_interval_seconds=60,
    )
    with TestClient(create_app(config)) as api:
        yield api, config


def test_healthz(client):
    api, _ = client
    response = api.get("/healthz")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_status_and_manual_capture(client):
    api, config = client
    status = api.get("/api/status")
    assert status.status_code == 200
    body = status.json()
    assert body["operator"] == "Garrey"
    assert "Garrey" in body["station"]

    captured = api.post("/api/capture")
    assert captured.status_code == 200
    latest = api.get("/api/latest")
    assert latest.status_code == 200
    assert latest.headers["content-type"].startswith("image/jpeg")
    assert config.latest_image.exists()


def test_seeded_archive_and_products(client):
    api, config = client
    day = seed_demo_night(config, frames=6)
    archive = api.get(f"/api/archive?day={day}")
    assert archive.status_code == 200
    assert archive.json()["count"] == 6
    keogram = api.get(f"/api/keogram?day={day}")
    trails = api.get(f"/api/startrails?day={day}")
    assert keogram.status_code == 200
    assert trails.status_code == 200
    home = api.get("/")
    assert home.status_code == 200
    assert b"Garrey All-Sky" in home.content
