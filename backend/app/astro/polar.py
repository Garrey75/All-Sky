from __future__ import annotations

import math

from .coords import DEG2RAD


def polar_error_from_solves(
    ra1_h: float,
    dec1: float,
    ra2_h: float,
    dec2: float,
    expected_dra_deg: float,
) -> dict:
    """Estimate polar alignment error from two plate-solves separated by an RA rotation.

    The mount rotates around its RA axis. If the polar axis is offset from the true
    celestial pole, the solved declination and the apparent RA travel both deviate.
    Returns azimuth and altitude errors in arcseconds, plus total error.
    """
    dra = ((ra2_h - ra1_h) * 15.0 + 180.0) % 360.0 - 180.0
    ddec = dec2 - dec1
    # Residual rotation not explained by commanded RA move.
    ra_residual_deg = dra - expected_dra_deg
    # Small-angle geometry: polar error ≈ residual / sin(rotation)
    denom = math.sin(abs(expected_dra_deg) * DEG2RAD) or 1e-3
    # Azimuth error mainly shows up as Dec drift; altitude error as RA residual.
    az_err_deg = ddec / denom
    alt_err_deg = ra_residual_deg / denom
    az_arcsec = az_err_deg * 3600.0
    alt_arcsec = alt_err_deg * 3600.0
    total = math.hypot(az_arcsec, alt_arcsec)
    return {
        "az_arcsec": az_arcsec,
        "alt_arcsec": alt_arcsec,
        "total_arcsec": total,
        "dra_deg": dra,
        "ddec_deg": ddec,
    }


def adjustment_advice(az_arcsec: float, alt_arcsec: float, hemisphere: str = "N") -> dict:
    az_dir = "西" if az_arcsec > 0 else "东"
    if hemisphere.upper().startswith("S"):
        alt_dir = "降低" if alt_arcsec > 0 else "抬高"
    else:
        alt_dir = "降低" if alt_arcsec > 0 else "抬高"
    return {
        "az": az_dir,
        "alt": alt_dir,
        "az_arcsec": az_arcsec,
        "alt_arcsec": alt_arcsec,
        "message": f"方位向{az_dir}调整 {abs(az_arcsec)/60:.1f}'，高度{alt_dir} {abs(alt_arcsec)/60:.1f}'",
    }


def apply_mount_adjustment(
    pole_az_err: float,
    pole_alt_err: float,
    d_az_arcsec: float,
    d_alt_arcsec: float,
) -> tuple[float, float]:
    return pole_az_err - d_az_arcsec, pole_alt_err - d_alt_arcsec


def pa_quality(total_arcsec: float) -> str:
    a = abs(total_arcsec)
    if a < 30:
        return "excellent"
    if a < 90:
        return "good"
    if a < 180:
        return "usable"
    return "poor"
