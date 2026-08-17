"""Camera sources: a physically based sky simulator and a drop-folder camera."""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from allsky.astronomy import equatorial_to_horizontal, moon_illumination, solar_position
from allsky.config import StationConfig


def _font(size: int) -> ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _mix(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(_lerp(c1[0], c2[0], t)),
        int(_lerp(c1[1], c2[1], t)),
        int(_lerp(c1[2], c2[2], t)),
    )


def _fisheye_xy(alt: float, az: float, cx: float, cy: float, radius: float) -> tuple[float, float] | None:
    if alt < -2:
        return None
    zenith = max(0.0, 90.0 - alt)
    r = (zenith / 90.0) * radius
    theta = math.radians(az)
    x = cx + r * math.sin(theta)
    y = cy - r * math.cos(theta)
    return x, y


def _star_catalog(seed: int, count: int) -> list[tuple[float, float, float]]:
    rng = random.Random(seed)
    stars = []
    for _ in range(count):
        ra = rng.uniform(0, 360)
        dec = math.degrees(math.asin(rng.uniform(-1, 1)))
        mag = min(6.5, max(0.2, rng.gauss(3.8, 1.4)))
        stars.append((ra, dec, mag))
    return stars


_STARS = _star_catalog(seed=75, count=420)


def _sky_colors(sun_alt: float) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    if sun_alt < -12:
        return (4, 8, 22), (10, 16, 38)
    if sun_alt < -6:
        t = (sun_alt + 12) / 6
        return _mix((4, 8, 22), (28, 22, 58), t), _mix((10, 16, 38), (92, 48, 78), t)
    if sun_alt < 0:
        t = (sun_alt + 6) / 6
        return _mix((28, 22, 58), (210, 92, 54), t), _mix((92, 48, 78), (255, 176, 88), t)
    if sun_alt < 8:
        t = sun_alt / 8
        return _mix((210, 92, 54), (92, 148, 210), t), _mix((255, 176, 88), (186, 214, 242), t)
    return (78, 142, 208), (168, 206, 238)


class SkySimulator:
    """Zenith-centered 180° fisheye of a time-dependent sky."""

    def capture(self, config: StationConfig, when: datetime | None = None) -> Image.Image:
        when = when or datetime.now(timezone.utc)
        size = config.image_size
        cx = cy = size / 2
        radius = size / 2 - 6
        sun_alt, sun_az = solar_position(config.latitude, config.longitude, when)
        zenith, horizon = _sky_colors(sun_alt)

        img = Image.new("RGB", (size, size), (6, 7, 10))
        draw = ImageDraw.Draw(img)
        for i in range(int(radius), 0, -3):
            t = i / radius
            draw.ellipse((cx - i, cy - i, cx + i, cy + i), fill=_mix(zenith, horizon, t * t))

        night = max(0.0, min(1.0, (-sun_alt - 2.0) / 10.0))
        if night > 0.15:
            self._draw_milky_way(draw, config, when, cx, cy, radius, night)
            self._draw_stars(draw, config, when, cx, cy, radius, night)

        sun_xy = _fisheye_xy(sun_alt, sun_az, cx, cy, radius)
        if sun_xy and sun_alt > -9:
            self._disc(draw, sun_xy, max(10, 18 + sun_alt * 0.4), (255, 230, 160))

        if night > 0.2:
            moon_frac, _ = moon_illumination(when)
            moon_ra = (sun_az + 180.0) % 360.0
            moon_dec = 18.0 * math.sin(math.radians(when.timetuple().tm_yday))
            malt, maz = equatorial_to_horizontal(moon_ra, moon_dec, config.latitude, config.longitude, when)
            mxy = _fisheye_xy(malt, maz, cx, cy, radius)
            if mxy and moon_frac > 0.05:
                r = 4 + 5 * moon_frac
                self._disc(draw, mxy, r + 6, (90, 100, 140))
                draw.ellipse(
                    (mxy[0] - r, mxy[1] - r, mxy[0] + r, mxy[1] + r),
                    fill=(230, 232, 245),
                )

        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=(120, 150, 180), width=2)
        self._compass(draw, cx, cy, radius)
        self._overlay(draw, config, when, sun_alt, size)
        return img.filter(ImageFilter.SMOOTH)

    def _draw_stars(
        self,
        draw: ImageDraw.ImageDraw,
        config: StationConfig,
        when: datetime,
        cx: float,
        cy: float,
        radius: float,
        night: float,
    ) -> None:
        for ra, dec, mag in _STARS:
            alt, az = equatorial_to_horizontal(ra, dec, config.latitude, config.longitude, when)
            xy = _fisheye_xy(alt, az, cx, cy, radius)
            if xy is None:
                continue
            brightness = night * max(0.0, (6.8 - mag) / 6.8)
            if brightness < 0.12:
                continue
            v = int(255 * brightness)
            r = 1.2 if mag < 1.8 else 0.7
            x, y = xy
            draw.ellipse((x - r, y - r, x + r, y + r), fill=(v, v, min(255, v + 14)))

    def _draw_milky_way(
        self,
        draw: ImageDraw.ImageDraw,
        config: StationConfig,
        when: datetime,
        cx: float,
        cy: float,
        radius: float,
        night: float,
    ) -> None:
        alpha = int(40 * night)
        color = (90 + alpha, 96 + alpha, 140 + alpha)
        for i in range(0, 360, 3):
            ra = (i + 40) % 360
            dec = 22 * math.sin(math.radians(i))
            alt, az = equatorial_to_horizontal(ra, dec, config.latitude, config.longitude, when)
            xy = _fisheye_xy(alt, az, cx, cy, radius)
            if xy is None:
                continue
            x, y = xy
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color)

    def _disc(self, draw: ImageDraw.ImageDraw, center: tuple[float, float], radius: float, color: tuple[int, int, int]) -> None:
        x, y = center
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    def _compass(self, draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float) -> None:
        font = _font(16)
        for text, az in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
            theta = math.radians(az)
            x = cx + (radius - 22) * math.sin(theta)
            y = cy - (radius - 22) * math.cos(theta)
            draw.text((x, y), text, fill=(210, 220, 230), font=font, anchor="mm")

    def _overlay(
        self,
        draw: ImageDraw.ImageDraw,
        config: StationConfig,
        when: datetime,
        sun_alt: float,
        size: int,
    ) -> None:
        font = _font(15)
        small = _font(12)
        stamp = when.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        draw.text((14, 10), config.station_name.upper(), fill=(236, 240, 248), font=font)
        draw.text((14, 30), stamp, fill=(168, 180, 198), font=small)
        draw.text((14, size - 28), f"Sun {sun_alt:+.1f}°", fill=(168, 180, 198), font=small)
        draw.text(
            (size - 14, size - 28),
            f"{config.latitude:.2f}°, {config.longitude:.2f}°",
            fill=(168, 180, 198),
            font=small,
            anchor="rs",
        )


class DirectoryCamera:
    """Reads the newest image from a watched directory (drop-folder / real capture)."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def capture(self, config: StationConfig, when: datetime | None = None) -> Image.Image:
        files = sorted(self.folder.glob("*.jpg")) + sorted(self.folder.glob("*.png"))
        if not files:
            return SkySimulator().capture(config, when)
        return Image.open(files[-1]).convert("RGB").resize((config.image_size, config.image_size))
