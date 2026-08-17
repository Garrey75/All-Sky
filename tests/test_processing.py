from datetime import datetime, timezone

from PIL import Image

from allsky.camera import SkySimulator
from allsky.config import StationConfig
from allsky.processing import make_keogram, make_startrails


def test_simulator_returns_square_rgb():
    config = StationConfig(image_size=120)
    image = SkySimulator().capture(config, datetime(2024, 12, 21, 7, 0, tzinfo=timezone.utc))
    assert image.size == (120, 120)
    assert image.mode == "RGB"


def test_keogram_stacks_center_slices():
    frames = [
        Image.new("RGB", (20, 10), (i * 10, 0, 0))
        for i in range(5)
    ]
    keogram = make_keogram(frames, slice_width=2)
    assert keogram.size == (10, 10)


def test_startrails_keeps_brightest_pixels():
    dark = Image.new("RGB", (8, 8), (0, 0, 0))
    bright = Image.new("RGB", (8, 8), (0, 0, 0))
    bright.putpixel((3, 3), (255, 255, 255))
    stacked = make_startrails([dark, bright])
    assert stacked.getpixel((3, 3)) == (255, 255, 255)
    assert stacked.getpixel((0, 0)) == (0, 0, 0)
