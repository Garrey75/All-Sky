"""Solar position, sidereal time, and sky-coordinate helpers."""

from __future__ import annotations

import math
from datetime import datetime, timezone

# Days since J2000.0 (TT ≈ UTC for this purpose).
_J2000 = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
_SYNODIC_DAYS = 29.530588853
_NEW_MOON_J2000 = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


def ensure_utc(when: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def julian_date(when: datetime) -> float:
    when = ensure_utc(when)
    delta = when - _J2000
    return 2451545.0 + delta.total_seconds() / 86400.0


def _fractional_year(when: datetime) -> float:
    when = ensure_utc(when)
    day_of_year = when.timetuple().tm_yday
    hour = when.hour + when.minute / 60.0 + when.second / 3600.0
    return (2.0 * math.pi / 365.0) * (day_of_year - 1 + (hour - 12.0) / 24.0)


def solar_position(latitude_deg: float, longitude_deg: float, when: datetime) -> tuple[float, float]:
    """Return (altitude_deg, azimuth_deg) of the Sun. Azimuth is degrees from north, east-positive."""
    when = ensure_utc(when)
    gamma = _fractional_year(when)
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    hour = when.hour + when.minute / 60.0 + when.second / 3600.0
    time_offset = eqtime + 4.0 * longitude_deg
    true_solar_minutes = hour * 60.0 + time_offset
    hour_angle = math.radians(true_solar_minutes / 4.0 - 180.0)
    lat = math.radians(latitude_deg)
    cos_zenith = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(hour_angle)
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    zenith = math.acos(cos_zenith)
    altitude = 90.0 - math.degrees(zenith)
    if abs(math.sin(zenith)) < 1e-9:
        azimuth = 180.0 if altitude >= 0 else 0.0
        return altitude, azimuth
    cos_az = (math.sin(decl) - math.sin(lat) * math.cos(zenith)) / (math.cos(lat) * math.sin(zenith))
    cos_az = max(-1.0, min(1.0, cos_az))
    azimuth = math.degrees(math.acos(cos_az))
    if hour_angle > 0:
        azimuth = 360.0 - azimuth
    return altitude, azimuth


def solar_altitude(latitude_deg: float, longitude_deg: float, when: datetime) -> float:
    altitude, _ = solar_position(latitude_deg, longitude_deg, when)
    return altitude


def is_night(latitude_deg: float, longitude_deg: float, when: datetime, threshold_deg: float = -6.0) -> bool:
    """True during nautical night when the Sun is below `threshold_deg`."""
    return solar_altitude(latitude_deg, longitude_deg, when) < threshold_deg


def greenwich_mean_sidereal_time_deg(when: datetime) -> float:
    jd = julian_date(when)
    t = (jd - 2451545.0) / 36525.0
    gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * t * t - (t ** 3) / 38710000.0
    return gmst % 360.0


def equatorial_to_horizontal(
    ra_deg: float,
    dec_deg: float,
    latitude_deg: float,
    longitude_deg: float,
    when: datetime,
) -> tuple[float, float]:
    """Convert right ascension/declination to (altitude_deg, azimuth_deg)."""
    lst = (greenwich_mean_sidereal_time_deg(when) + longitude_deg) % 360.0
    hour_angle = math.radians((lst - ra_deg + 360.0) % 360.0)
    dec = math.radians(dec_deg)
    lat = math.radians(latitude_deg)
    sin_alt = math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(hour_angle)
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.asin(sin_alt)
    cos_az = (math.sin(dec) - math.sin(alt) * math.sin(lat)) / (math.cos(alt) * math.cos(lat) + 1e-12)
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.acos(cos_az)
    if math.sin(hour_angle) > 0:
        az = 2 * math.pi - az
    return math.degrees(alt), math.degrees(az)


def moon_illumination(when: datetime) -> tuple[float, str]:
    """Return (illuminated fraction 0–1, phase name) from a mean synodic month."""
    when = ensure_utc(when)
    age = (when - _NEW_MOON_J2000).total_seconds() / 86400.0 % _SYNODIC_DAYS
    phase_angle = 2 * math.pi * (age / _SYNODIC_DAYS)
    fraction = 0.5 * (1.0 - math.cos(phase_angle))
    if age < 1.84566:
        name = "New"
    elif age < 5.53699:
        name = "Waxing crescent"
    elif age < 9.22831:
        name = "First quarter"
    elif age < 12.91963:
        name = "Waxing gibbous"
    elif age < 16.61096:
        name = "Full"
    elif age < 20.30228:
        name = "Waning gibbous"
    elif age < 23.99361:
        name = "Last quarter"
    elif age < 27.68493:
        name = "Waning crescent"
    else:
        name = "New"
    return fraction, name
