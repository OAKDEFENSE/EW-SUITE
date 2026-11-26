from ew_core import geo
from ew_core.library import DEFAULT_LIBRARY
from ew_core.models import Detection, Ownship, Position, PulseParams, TrackStatus
from ew_core.tracker import Tracker, TrackEventKind

BIN_W = 8.77e6


def _own(lat=55.5, lon=-1.0, hdg=90.0):
    return Ownship(position=Position(lat=lat, lon=lon, alt_m=3000), heading_deg=hdg, speed_mps=120)


def _fcr(bearing=None):
    return Detection(
        freq_hz=9.02e9,
        bandwidth_hz=5e6,
        power_dbm=-60,
        bearing_deg=bearing,
        pulse=PulseParams(pri_us=250, pw_us=0.5),
    )


def test_track_confirms_then_threat_then_lost():
    tr = Tracker(DEFAULT_LIBRARY, confirm_hits=3, lost_after_s=2.0, drop_after_s=10.0)
    kinds = []
    for i in range(4):
        kinds += [e.kind for e in tr.update([_fcr(45)], _own(), i * 0.2, BIN_W)]
    assert TrackEventKind.CONFIRMED in kinds
    assert TrackEventKind.THREAT in kinds
    tracks = tr.tracks
    assert len(tracks) == 1
    assert tracks[0].status == TrackStatus.CONFIRMED
    assert tracks[0].classification.library_id == "FC-X"

    kinds = [e.kind for e in tr.update([], _own(), 5.0, BIN_W)]
    assert kinds == [TrackEventKind.LOST]
    assert tr.tracks[0].status == TrackStatus.LOST

    kinds = [e.kind for e in tr.update([], _own(), 20.0, BIN_W)]
    assert kinds == [TrackEventKind.DROPPED]
    assert tr.tracks == []


def test_nearby_frequencies_stay_separate_tracks():
    tr = Tracker(DEFAULT_LIBRARY)
    dets = [
        Detection(freq_hz=9.02e9, bandwidth_hz=5e6, power_dbm=-60, bearing_deg=40),
        Detection(freq_hz=9.41e9, bandwidth_hz=12e6, power_dbm=-65, bearing_deg=200),
    ]
    for i in range(3):
        tr.update(dets, _own(), i * 0.2, BIN_W)
    assert len(tr.tracks) == 2


def test_geolocation_from_ownship_motion():
    target = (55.80, -0.70)
    tr = Tracker(DEFAULT_LIBRARY, min_geo_bearings=6, min_geo_baseline_m=2000)
    lat, lon = 55.50, -1.20
    got_fix = False
    for i in range(40):
        lat, lon = geo.destination(lat, lon, 70.0, 600)  # 600 m per tick
        brg = geo.bearing_deg(lat, lon, *target)
        events = tr.update([_fcr(brg)], _own(lat, lon, 70.0), i * 0.2, BIN_W)
        got_fix |= any(e.kind == TrackEventKind.GEO_FIX for e in events)
    assert got_fix
    track = tr.tracks[0]
    assert track.geo is not None
    assert geo.distance_m(track.geo.position.lat, track.geo.position.lon, *target) < 1500
