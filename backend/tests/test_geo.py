import math

from ew_core import geo


def test_destination_bearing_roundtrip():
    lat, lon = 55.5, -1.0
    dlat, dlon = geo.destination(lat, lon, 45.0, 20_000)
    assert math.isclose(geo.distance_m(lat, lon, dlat, dlon), 20_000, rel_tol=1e-3)
    assert math.isclose(geo.bearing_deg(lat, lon, dlat, dlon), 45.0, abs_tol=0.2)


def test_angular_diff_wraps():
    assert geo.angular_diff_deg(350, 10) == 20
    assert geo.angular_diff_deg(10, 350) == 20
    assert geo.angular_diff_deg(180, 0) == 180


def test_triangulate_recovers_target():
    target = (55.80, -0.70)
    observers = [(55.50, -1.20), (55.55, -1.00), (55.60, -0.80), (55.65, -0.60)]
    obs = [(la, lo, geo.bearing_deg(la, lo, *target)) for la, lo in observers]
    result = geo.triangulate(obs)
    assert result is not None
    lat, lon, err = result
    assert geo.distance_m(lat, lon, *target) < 300
    assert err >= 100


def test_triangulate_rejects_parallel_bearings():
    obs = [(55.5, -1.0, 90.0), (55.5, -1.1, 90.5), (55.5, -1.2, 90.2)]
    assert geo.triangulate(obs) is None


def test_triangulate_rejects_fix_behind_observers():
    target = (55.80, -0.70)
    observers = [(55.50, -1.20), (55.55, -1.00), (55.60, -0.80)]
    # Reciprocal bearings point away from the target.
    obs = [(la, lo, (geo.bearing_deg(la, lo, *target) + 180) % 360) for la, lo in observers]
    assert geo.triangulate(obs) is None
