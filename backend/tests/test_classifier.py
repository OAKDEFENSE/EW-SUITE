from ew_core.classifier import classify
from ew_core.library import DEFAULT_LIBRARY
from ew_core.models import Detection, EmitterClass, PulseParams, ThreatLevel


def _det(freq, pri=None, pw=None):
    pulse = PulseParams(pri_us=pri, pw_us=pw) if pri is not None else None
    return Detection(freq_hz=freq, bandwidth_hz=1e6, power_dbm=-60, pulse=pulse)


def test_s_band_surveillance_radar():
    c = classify(_det(2.9e9, 1000, 10), DEFAULT_LIBRARY)
    assert c.library_id == "SR-S"
    assert c.emitter_class == EmitterClass.SURVEILLANCE_RADAR
    assert c.confidence >= 0.9


def test_x_band_fire_control_is_high_threat():
    c = classify(_det(9.0e9, 250, 0.5), DEFAULT_LIBRARY)
    assert c.library_id == "FC-X"
    assert c.threat == ThreatLevel.HIGH


def test_x_band_nav_radar_distinguished_by_frequency():
    c = classify(_det(9.41e9, 600, 0.3), DEFAULT_LIBRARY)
    assert c.library_id == "NAV-X"
    assert c.threat == ThreatLevel.NONE


def test_cw_uas_link():
    c = classify(_det(2.44e9), DEFAULT_LIBRARY)
    assert c.library_id == "UAS-C2-24"


def test_unknown_outside_library_bands():
    c = classify(_det(7.0e9), DEFAULT_LIBRARY)
    assert c.library_id is None
    assert c.emitter_class == EmitterClass.UNKNOWN


def test_pulse_mismatch_lowers_confidence_but_keeps_band():
    good = classify(_det(2.9e9, 1000, 10), DEFAULT_LIBRARY)
    bad_pri = classify(_det(2.9e9, 50, 10), DEFAULT_LIBRARY)
    assert bad_pri.library_id == "SR-S"
    assert bad_pri.confidence < good.confidence
