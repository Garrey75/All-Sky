from __future__ import annotations

import math
from datetime import datetime, timezone

DEG2RAD = math.pi / 180.0
RAD2DEG = 180.0 / math.pi
SEC_PER_DAY = 86400.0


def julian_date(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    y, m, d = dt.year, dt.month, dt.day
    frac = (
        dt.hour / 24.0
        + dt.minute / 1440.0
        + dt.second / 86400.0
        + dt.microsecond / 86400.0 / 1e6
    )
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5
    return jd + frac


def gmst_deg(dt: datetime) -> float:
    jd = julian_date(dt)
    t = (jd - 2451545.0) / 36525.0
    gmst = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * t * t
        - t * t * t / 38710000.0
    )
    return gmst % 360.0


def lst_deg(dt: datetime, lon_deg: float) -> float:
    return (gmst_deg(dt) + lon_deg) % 360.0


def hour_angle_deg(ra_hours: float, lst_deg_value: float) -> float:
    return (lst_deg_value - ra_hours * 15.0 + 180.0) % 360.0 - 180.0


def altaz(ra_hours: float, dec_deg: float, lat_deg: float, lon_deg: float, dt: datetime) -> tuple[float, float]:
    ha = hour_angle_deg(ra_hours, lst_deg(dt, lon_deg)) * DEG2RAD
    dec = dec_deg * DEG2RAD
    lat = lat_deg * DEG2RAD
    sin_alt = math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(ha)
    alt = math.asin(max(-1.0, min(1.0, sin_alt)))
    cos_az = (math.sin(dec) - math.sin(alt) * math.sin(lat)) / (math.cos(alt) * math.cos(lat) + 1e-12)
    sin_az = -math.cos(dec) * math.sin(ha) / (math.cos(alt) + 1e-12)
    az = math.atan2(sin_az, cos_az)
    return alt * RAD2DEG, (az * RAD2DEG) % 360.0


def angular_sep_deg(ra1_h: float, dec1: float, ra2_h: float, dec2: float) -> float:
    a1 = ra1_h * 15.0 * DEG2RAD
    a2 = ra2_h * 15.0 * DEG2RAD
    d1 = dec1 * DEG2RAD
    d2 = dec2 * DEG2RAD
    cos_c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(a1 - a2)
    return math.acos(max(-1.0, min(1.0, cos_c))) * RAD2DEG


def gnomonic_xy(
    ra_h: float,
    dec_deg: float,
    ra0_h: float,
    dec0_deg: float,
) -> tuple[float, float, float]:
    """Return tangent-plane coordinates in radians and cosine of angular distance."""
    ra = ra_h * 15.0 * DEG2RAD
    dec = dec_deg * DEG2RAD
    ra0 = ra0_h * 15.0 * DEG2RAD
    dec0 = dec0_deg * DEG2RAD
    cos_c = math.sin(dec0) * math.sin(dec) + math.cos(dec0) * math.cos(dec) * math.cos(ra - ra0)
    if cos_c <= 0.05:
        return 0.0, 0.0, cos_c
    x = math.cos(dec) * math.sin(ra - ra0) / cos_c
    y = (
        math.cos(dec0) * math.sin(dec) - math.sin(dec0) * math.cos(dec) * math.cos(ra - ra0)
    ) / cos_c
    return x, y, cos_c


def airmass(alt_deg: float) -> float:
    z = max(0.0, 90.0 - alt_deg)
    if z >= 87.0:
        return 20.0
    return 1.0 / max(0.05, math.cos(z * DEG2RAD) + 0.025 * math.exp(-11.0 * math.cos(z * DEG2RAD)))


def wrap_ra_hours(ra: float) -> float:
    return ra % 24.0


def clamp_dec(dec: float) -> float:
    return max(-90.0, min(90.0, dec))


def format_ra(ra_hours: float) -> str:
    ra = wrap_ra_hours(ra_hours)
    h = int(ra)
    m = int((ra - h) * 60)
    s = (ra - h - m / 60.0) * 3600.0
    return f"{h:02d}h{m:02d}m{s:05.2f}s"


def format_dec(dec_deg: float) -> str:
    sign = "+" if dec_deg >= 0 else "-"
    d = abs(dec_deg)
    deg = int(d)
    m = int((d - deg) * 60)
    s = (d - deg - m / 60.0) * 3600.0
    return f"{sign}{deg:02d}°{m:02d}'{s:04.1f}\""


def format_angle(arcsec: float) -> str:
    sign = "-" if arcsec < 0 else ""
    a = abs(arcsec)
    d = int(a // 3600)
    m = int((a % 3600) // 60)
    s = a % 60
    if d:
        return f"{sign}{d}°{m:02d}'{s:04.1f}\""
    return f"{sign}{m}'{s:04.1f}\""


def sensor_fov_deg(pixel_um: float, width_px: int, height_px: int, focal_mm: float) -> tuple[float, float]:
    if focal_mm <= 0:
        return 1.0, 1.0
    w_mm = pixel_um * width_px / 1000.0
    h_mm = pixel_um * height_px / 1000.0
    return (
        2.0 * math.atan(w_mm / (2.0 * focal_mm)) * RAD2DEG,
        2.0 * math.atan(h_mm / (2.0 * focal_mm)) * RAD2DEG,
    )


def pixel_scale_arcsec(pixel_um: float, focal_mm: float) -> float:
    if focal_mm <= 0:
        return 1.0
    return pixel_um / focal_mm * 206.265


def ra_dec_offset(ra_h: float, dec_deg: float, dra_arcsec: float, ddec_arcsec: float) -> tuple[float, float]:
    cosd = max(0.05, math.cos(dec_deg * DEG2RAD))
    return wrap_ra_hours(ra_h + dra_arcsec / 3600.0 / 15.0 / cosd), clamp_dec(dec_deg + ddec_arcsec / 3600.0)
