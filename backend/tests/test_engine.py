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


def test_links_react_to_jammer_in_littoral_scenario():
    eng = Engine("littoral_patrol", seed=3, start_time=0.0)
    alerts = _run(eng, 40)
    by_id = {ls.link_id: ls for ls in eng.links}
    assert by_id["C2-UP"].state == "ok" and by_id["ADL"].state == "ok"
    assert by_id["VID-DN"].state == "marginal"  # 5.8 GHz video at loiter range is tight
    assert all(not ls.interferers for ls in eng.links)
    assert not any(a.kind == AlertKind.LINK and "FAILED" in a.message for a in alerts)

    # Jammer comes up at 45 s: first it is an unlocated in-band threat...
    _run(eng, 20)
    jam = next(t for t in eng.tracks if abs(t.freq_hz - 1.355e9) < 30e6)
    assert jam.classification.emitter_class == EmitterClass.JAMMER
    assert jam.classification.threat == ThreatLevel.HIGH
    by_id = {ls.link_id: ls for ls in eng.links}
    if jam.geo is None:
        assert jam.id in by_id["C2-UP"].unlocated_interferers
        assert by_id["ADL"].unlocated_interferers == []  # out of band

    # ...then, once geolocated, it takes the 1.35 GHz links down and leaves the 1.05 GHz
    # aircraft data link alone.
    alerts = _run(eng, 60)
    jam = eng.tracker.get(jam.id)
    assert jam is not None and jam.geo is not None and jam.est_eirp_dbm is not None
    by_id = {ls.link_id: ls for ls in eng.links}
    for lid in ("C2-UP", "TLM-DN", "RLY-UP", "RLY-DN"):
        assert by_id[lid].state == "failed", lid
        assert [i.track_id for i in by_id[lid].interferers] == [jam.id]
        assert by_id[lid].jam_dbm is not None and by_id[lid].jam_dbm > by_id[lid].noise_dbm
    assert by_id["ADL"].state == "ok" and by_id["ADL"].interferers == []
    failed_alerts = [a for a in alerts if a.kind == AlertKind.LINK and "FAILED" in a.message]
    assert any("C2 uplink" in a.message and jam.id in a.message for a in failed_alerts)
    assert all(a.severity == ThreatLevel.HIGH for a in failed_alerts)

    grid = eng.relay_grid("C2-UP", n=20)
    assert grid.direct_margin_db < 0
    assert grid.best is not None
