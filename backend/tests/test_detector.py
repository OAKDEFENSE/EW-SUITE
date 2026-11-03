import numpy as np

from ew_core.detector import detect, fuse_descriptors
from ew_core.models import Detection, PulseParams, SpectrumFrame
from ew_core.simulation import PulseDescriptor


def _frame(n=1024, start=1e9, stop=2e9, floor=-100.0, seed=1):
    rng = np.random.default_rng(seed)
    p = rng.normal(floor, 1.5, n)
    frame = SpectrumFrame(time=0, start_hz=start, stop_hz=stop, power_dbm=[], noise_floor_dbm=floor)
    return p, frame


def test_detect_finds_single_peak():
    p, fr = _frame()
    p[500:503] = [-70, -60, -72]
    fr.power_dbm = p.tolist()
    dets = detect(fr, 10)
    assert len(dets) == 1
    d = dets[0]
    bin_w = fr.bin_width_hz
    expected = fr.start_hz + 501.5 * bin_w
    assert abs(d.freq_hz - expected) < bin_w
    assert d.power_dbm == -60
    # Only the -60 bin is within 6 dB of the peak.
    assert d.bandwidth_hz == bin_w


def test_detect_bandwidth_uses_minus_6db_width():
    p, fr = _frame()
    p[300:306] = [-80, -63, -60, -61, -64, -80]
    fr.power_dbm = p.tolist()
    (d,) = detect(fr, 10)
    assert d.bandwidth_hz == 4 * fr.bin_width_hz


def test_detect_separates_two_peaks():
    p, fr = _frame()
    p[100] = -55
    p[900] = -65
    fr.power_dbm = p.tolist()
    dets = detect(fr, 10)
    assert [round(d.power_dbm) for d in dets] == [-55, -65]


def test_detect_empty_when_quiet():
    p, fr = _frame()
    fr.power_dbm = p.tolist()
    assert detect(fr, 12) == []


def test_fuse_descriptors_attaches_bearing_and_pulse():
    dets = [
        Detection(freq_hz=3.0e9, bandwidth_hz=2e6, power_dbm=-60),
        Detection(freq_hz=9.0e9, bandwidth_hz=5e6, power_dbm=-70),
    ]
    pdws = [
        PulseDescriptor(
            freq_hz=9.001e9,
            bearing_deg=120,
            power_dbm=-70,
            pulse=PulseParams(pri_us=250, pw_us=0.5),
        ),
        PulseDescriptor(freq_hz=7.0e9, bearing_deg=10, power_dbm=-80, pulse=None),
    ]
    fused = fuse_descriptors(dets, pdws, bin_width_hz=8e6)
    assert fused[0].bearing_deg is None
    assert fused[1].bearing_deg == 120
    assert fused[1].pulse is not None and fused[1].pulse.pri_us == 250
