from __future__ import annotations

import pytest
from datetime import datetime, timezone

from app.astro.coords import altaz, angular_sep_deg, format_dec, format_ra, gmst_deg, julian_date
from app.astro.hfr import half_flux_radius, median_hfr
from app.astro.polar import polar_error_from_solves
from app.astro.platesolve import solve_from_pointing
import numpy as np


def test_julian_date_known_epoch():
    dt = datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert abs(julian_date(dt) - 2451545.0) < 1e-4


def test_format_coords():
    assert format_ra(5.5881).startswith("05h")
    assert format_dec(-5.3911).startswith("-05")


def test_angular_sep_identical():
    assert angular_sep_deg(5.0, 20.0, 5.0, 20.0) < 1e-6


def test_altaz_zenith_ish():
    dt = datetime(2024, 9, 9, 12, 0, tzinfo=timezone.utc)
    gmst = gmst_deg(dt)
    # object on local meridian at observer longitude 0, lat 0
    ra_h = (gmst / 15.0) % 24
    alt, az = altaz(ra_h, 0.0, 0.0, 0.0, dt)
    assert alt > 80


def test_hfr_gaussian():
    img = np.zeros((80, 80))
    y, x = np.ogrid[:80, :80]
    img += 200 * np.exp(-((x - 40) ** 2 + (y - 40) ** 2) / (2 * 2.2**2))
    hfr = half_flux_radius(img, 40, 40)
    assert 1.5 < hfr < 4.5
    assert median_hfr(img) < 5


def test_polar_error_scales_with_dec_drift():
    err = polar_error_from_solves(1.0, 45.0, 5.0, 45.1, expected_dra_deg=60.0)
    assert err["ddec_deg"] == pytest.approx(0.1, rel=1e-9, abs=1e-9)
    assert err["total_arcsec"] > 0


def test_platesolve_success_and_fail():
    ok = solve_from_pointing(5.588, -5.39, 800, 600, 3.76, 580, star_count=20)
    assert ok.success
    bad = solve_from_pointing(5.588, -5.39, 800, 600, 3.76, 580, star_count=2)
    assert not bad.success
