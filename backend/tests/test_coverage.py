import pytest

from ew_core import geo
from ew_core.engine import Engine
from ew_core.models import CoverageRequest, GridBounds
from ew_core.simulation import build_scenarios


def _run(engine, seconds, dt=0.2):
    for _ in range(int(seconds / dt)):
        engine.tick(dt)


def test_terrain_grid_orientation_and_shape():
    eng = Engine("quiet_range", seed=1, start_time=0.0, terrain="synthetic")
    g = eng.terrain_grid(GridBounds(south=55.0, west=-2.5, north=56.0, east=0.0), n=40)
    assert g.n_lat == 40 and 10 <= g.n_lon <= 80
    assert len(g.elevation_m) == g.n_lat and len(g.elevation_m[0]) == g.n_lon
    # East column is sea, west column is land.
    assert all(row[-1] == 0 for row in g.elevation_m)
    assert sum(row[0] for row in g.elevation_m) > 0
    with pytest.raises(ValueError):
        eng.terrain_grid(GridBounds(south=56.0, west=-2.5, north=55.0, east=0.0))


def test_coverage_grid_shrinks_at_low_altitude_behind_terrain():
    eng = Engine("quiet_range", seed=1, start_time=0.0, terrain="synthetic")
    base = dict(lat=55.35, lon=-1.55, alt_agl_m=10, eirp_dbm=95, freq_hz=2.9e9, radius_km=60, n=40)
    # A -70 dBm sensitivity: at 60 km the radar arrives at about -42 dBm in free space, so
    # only terrain shadowing (tens of dB) can push a cell below the threshold.
    low = eng.coverage(CoverageRequest(**base, rx_alt_m=50, rx_alt_ref="agl", threshold_dbm=-70))
    high = eng.coverage(CoverageRequest(**base, rx_alt_m=3000, rx_alt_ref="msl", threshold_dbm=-70))
    assert low.n == 40 and len(low.power_dbm) == 40 and len(low.power_dbm[0]) == 40
    assert high.covered_fraction > low.covered_fraction
    assert low.covered_fraction < 0.98
    assert high.covered_fraction > 0.95
    assert low.bounds.north > low.bounds.south and low.bounds.east > low.bounds.west


def test_track_eirp_estimate_and_coverage():
    eng = Engine("littoral_patrol", seed=3, start_time=0.0, terrain="synthetic")
    _run(eng, 90)
    sim = {e.freq_hz: e for e in build_scenarios()["littoral_patrol"].emitters}
    own = eng.env.ownship()

    fixed = [t for t in eng.tracks if t.geo is not None]
    assert fixed, "expected geolocated tracks"
    # Every published fix must be honest: the miss lies within the quoted radius (2-sigma)
    # and the radius is small relative to range.
    for t in fixed:
        e = sim[min(sim, key=lambda f: abs(f - t.freq_hz))]
        miss = geo.distance_m(t.geo.position.lat, t.geo.position.lon, e.lat, e.lon)
        rng = geo.distance_m(own.position.lat, own.position.lon, e.lat, e.lon)
        assert miss <= max(2.0 * t.geo.error_radius_m, 2_000), f"{t.id}: miss {miss:.0f} m"
        assert t.geo.error_radius_m <= 0.5 * rng
        assert t.est_eirp_dbm is not None and t.peak_power_dbm is not None

    # The coastal S-band radar sits abeam of the first leg (good geometry): tight fix and
    # an EIRP estimate from its main-lobe peaks.
    asr = next(t for t in fixed if abs(t.freq_hz - 2.905e9) < 20e6)
    true_asr = sim[2.905e9]
    assert (
        geo.distance_m(asr.geo.position.lat, asr.geo.position.lon, true_asr.lat, true_asr.lon)
        < 8_000
    )
    assert asr.est_eirp_dbm == pytest.approx(true_asr.eirp_dbm, abs=4.0)
    assert asr.los is True
    assert asr.peak_power_dbm >= asr.power_dbm - 1.0

    # The fire control radar lies almost dead ahead on this leg, so range is unobservable
    # from bearings alone: the tracker must withhold the fix rather than publish a bad one.
    fcr = next(t for t in eng.tracks if abs(t.freq_hz - 9.02e9) < 20e6)
    assert fcr.geo is None

    grid = eng.track_coverage(asr.id, n=30)
    assert grid is not None
    assert grid.eirp_dbm == asr.est_eirp_dbm
    assert grid.rx_alt_ref == "msl"  # defaults to ownship altitude
    assert grid.covered_fraction > 0.5
    assert eng.track_coverage(fcr.id, n=20) is None

    with pytest.raises(KeyError):
        eng.track_coverage("E-999")


def test_flat_terrain_engine_has_no_shadowing():
    eng = Engine("quiet_range", seed=1, start_time=0.0, terrain="flat")
    grid = eng.coverage(
        CoverageRequest(
            lat=55.6, lon=-0.8, eirp_dbm=80, freq_hz=1e9, rx_alt_m=100, radius_km=30, n=20
        )
    )
    assert grid.covered_fraction == 1.0
