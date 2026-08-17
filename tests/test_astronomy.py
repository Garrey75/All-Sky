from datetime import datetime, timezone

from allsky.astronomy import is_night, moon_illumination, solar_altitude, solar_position


def test_solar_noon_near_greenwich_is_high_in_june():
    when = datetime(2024, 6, 21, 12, 0, tzinfo=timezone.utc)
    altitude = solar_altitude(51.5, 0.0, when)
    assert altitude > 50


def test_solar_midnight_is_below_horizon_in_june_uk():
    when = datetime(2024, 6, 21, 0, 0, tzinfo=timezone.utc)
    assert solar_altitude(51.5, 0.0, when) < 0


def test_colorado_night_flag():
    night = datetime(2024, 1, 15, 7, 0, tzinfo=timezone.utc)  # midnight MST
    day = datetime(2024, 1, 15, 19, 0, tzinfo=timezone.utc)  # noon MST
    assert is_night(40.0, -105.0, night)
    assert not is_night(40.0, -105.0, day)


def test_azimuth_increases_through_the_morning():
    morning = solar_position(40.0, -105.0, datetime(2024, 6, 21, 14, 0, tzinfo=timezone.utc))
    afternoon = solar_position(40.0, -105.0, datetime(2024, 6, 21, 20, 0, tzinfo=timezone.utc))
    assert morning[0] > 20
    assert afternoon[0] > 20
    assert morning[1] < 180 < afternoon[1]


def test_moon_illumination_is_a_fraction():
    fraction, name = moon_illumination(datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc))
    assert 0 <= fraction <= 0.05
    assert name == "New"
