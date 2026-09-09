from __future__ import annotations

from dataclasses import dataclass

from .catalog import CATALOG, nearby
from .coords import angular_sep_deg, format_dec, format_ra, pixel_scale_arcsec, sensor_fov_deg


@dataclass
class SolveResult:
    success: bool
    ra_hours: float
    dec_deg: float
    rotation_deg: float
    pixel_scale: float
    fov_x_deg: float
    fov_y_deg: float
    stars: int
    error_arcsec: float
    message: str
    objects: list[dict]

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "ra_hours": self.ra_hours,
            "dec_deg": self.dec_deg,
            "ra": format_ra(self.ra_hours),
            "dec": format_dec(self.dec_deg),
            "rotation_deg": round(self.rotation_deg, 2),
            "pixel_scale": round(self.pixel_scale, 3),
            "fov_x_deg": round(self.fov_x_deg, 3),
            "fov_y_deg": round(self.fov_y_deg, 3),
            "stars": self.stars,
            "error_arcsec": round(self.error_arcsec, 1),
            "message": self.message,
            "objects": self.objects,
        }


def solve_from_pointing(
    ra_h: float,
    dec_deg: float,
    width: int,
    height: int,
    pixel_um: float,
    focal_mm: float,
    star_count: int,
    rotation_deg: float = 0.0,
    noise_arcsec: float = 2.5,
) -> SolveResult:
    fov_x, fov_y = sensor_fov_deg(pixel_um, width, height, focal_mm)
    scale = pixel_scale_arcsec(pixel_um, focal_mm)
    fov = max(fov_x, fov_y)
    if star_count < 4:
        return SolveResult(
            False,
            ra_h,
            dec_deg,
            rotation_deg,
            scale,
            fov_x,
            fov_y,
            star_count,
            0,
            "星点不足，无法解析。增加曝光或检查对焦。",
            [],
        )
    if fov < 0.25 or fov > 40:
        return SolveResult(
            False,
            ra_h,
            dec_deg,
            rotation_deg,
            scale,
            fov_x,
            fov_y,
            star_count,
            0,
            f"视场 {fov:.2f}° 超出解析范围 (0.25°–40°)。请核对焦距。",
            [],
        )
    objs = [
        {
            "id": o.id,
            "name": o.name,
            "name_zh": o.name_zh,
            "sep_deg": round(angular_sep_deg(ra_h, dec_deg, o.ra_hours, o.dec_deg), 3),
        }
        for o in nearby(ra_h, dec_deg, fov)
        if o.kind != "Star"
    ]
    objs.sort(key=lambda o: o["sep_deg"])
    return SolveResult(
        True,
        ra_h,
        dec_deg,
        rotation_deg,
        scale,
        fov_x,
        fov_y,
        star_count,
        noise_arcsec,
        "解析成功",
        objs[:8],
    )


def match_target(ra_h: float, dec_deg: float) -> dict | None:
    best = None
    best_sep = 9e9
    for obj in CATALOG:
        if obj.kind == "Star":
            continue
        sep = angular_sep_deg(ra_h, dec_deg, obj.ra_hours, obj.dec_deg)
        if sep < best_sep:
            best_sep = sep
            best = obj
    if best is None:
        return None
    return {
        "id": best.id,
        "name": best.name,
        "name_zh": best.name_zh,
        "sep_deg": round(best_sep, 3),
        "in_frame": best_sep < 1.0,
    }
