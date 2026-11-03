"""Match detections against the signal library."""

from __future__ import annotations

from .models import (
    UNKNOWN_CLASSIFICATION,
    Classification,
    Detection,
    EmitterClass,
    SignalLibraryEntry,
    ThreatLevel,
)


def _in_range(value: float, lo: float | None, hi: float | None, slack: float) -> bool:
    if lo is None or hi is None:
        return True
    width = hi - lo
    return (lo - slack * width) <= value <= (hi + slack * width)


def score_entry(det: Detection, entry: SignalLibraryEntry) -> float:
    """Return a 0..1 match score for one library entry."""
    if not (entry.freq_min_hz <= det.freq_hz <= entry.freq_max_hz):
        return 0.0

    score = 0.45
    if entry.pulsed and det.pulse is not None:
        if _in_range(det.pulse.pri_us, entry.pri_min_us, entry.pri_max_us, 0.1):
            score += 0.3
        else:
            score -= 0.2
        if _in_range(det.pulse.pw_us, entry.pw_min_us, entry.pw_max_us, 0.1):
            score += 0.25
        else:
            score -= 0.15
    elif not entry.pulsed and det.pulse is None:
        score += 0.35
    else:
        # Modulation type disagrees with the library: strong penalty but not zero,
        # because PDW extraction can miss pulses on weak or scanning emitters.
        score *= 0.4
    return max(0.0, min(1.0, score))


def classify(det: Detection, library: list[SignalLibraryEntry]) -> Classification:
    best: SignalLibraryEntry | None = None
    best_score = 0.0
    for entry in library:
        s = score_entry(det, entry)
        if s > best_score:
            best, best_score = entry, s

    if best is None or best_score < 0.3:
        return UNKNOWN_CLASSIFICATION.model_copy()

    return Classification(
        library_id=best.id,
        name=best.name,
        emitter_class=best.emitter_class,
        threat=best.threat,
        confidence=round(best_score, 2),
    )


def is_threat(c: Classification) -> bool:
    return c.threat in (ThreatLevel.HIGH, ThreatLevel.CRITICAL) and (
        c.emitter_class != EmitterClass.UNKNOWN
    )
