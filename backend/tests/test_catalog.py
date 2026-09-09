from app.astro.catalog import get_object, search_objects


def test_messier_lookup():
    m42 = get_object("M42")
    assert m42 is not None
    assert m42.ra_hours > 5
    assert "猎户" in m42.name_zh
    hits = search_objects("猎户")
    assert any(o.id == "M42" for o in hits)
