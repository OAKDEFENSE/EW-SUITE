from ew_core.engine import Engine
from ew_core.models import AlertKind, EmitterClass, ReceiverConfig, ThreatLevel, TrackStatus


def _run(engine: Engine, seconds: float, dt: float = 0.2):
    alerts = []
    for _ in range(int(seconds / dt)):
        alerts += engine.tick(dt)
    return alerts


def test_littoral_patrol_builds_picture():
    eng = Engine("littoral_patrol", seed=7, start_time=0.0)
    alerts = _run(eng, 30)
    confirmed = [t for t in eng.tracks if t.status == TrackStatus.CONFIRMED]
    assert len(confirmed) >= 3
    classes = {t.classification.emitter_class for t in confirmed}
    assert EmitterClass.FIRE_CONTROL_RADAR in classes
    assert EmitterClass.SURVEILLANCE_RADAR in classes
    assert any(a.kind == AlertKind.THREAT and a.severity == ThreatLevel.HIGH for a in alerts)
    state = eng.state()
    assert len(state.spectrum.power_dbm) == state.receiver.n_bins
    assert state.ownship.position.lat > 55


def test_geolocation_emerges_over_time():
    eng = Engine("littoral_patrol", seed=3, start_time=0.0)
    _run(eng, 90)
    fixes = [t for t in eng.tracks if t.geo is not None]
    assert fixes, "expected at least one geolocated emitter after 90 s of ownship motion"


def test_retune_narrows_band_and_resets_frame_size():
    eng = Engine("quiet_range", seed=1, start_time=0.0)
    eng.set_receiver(ReceiverConfig(start_hz=8e9, stop_hz=10e9, n_bins=1024))
    _run(eng, 5)
    s = eng.state()
    assert s.spectrum.start_hz == 8e9 and len(s.spectrum.power_dbm) == 1024
    assert all(8e9 <= t.freq_hz <= 10e9 for t in eng.tracks)


def test_load_scenario_resets_tracks():
    eng = Engine("littoral_patrol", seed=1, start_time=0.0)
    _run(eng, 5)
    assert eng.tracks
    eng.load_scenario("quiet_range")
    assert eng.tracks == []
    assert eng.scenario_name == "quiet_range"
