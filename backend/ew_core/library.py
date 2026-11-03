"""Notional signal library used for emitter classification.

Every entry here is generic, textbook-level and unclassified. Parameter ranges describe
broad equipment categories, not specific systems.
"""

from __future__ import annotations

from .models import EmitterClass, SignalLibraryEntry, ThreatLevel

MHZ = 1e6
GHZ = 1e9

DEFAULT_LIBRARY: list[SignalLibraryEntry] = [
    SignalLibraryEntry(
        id="VHF-TAC",
        name="VHF tactical voice net",
        emitter_class=EmitterClass.VOICE_COMMS,
        threat=ThreatLevel.LOW,
        freq_min_hz=30 * MHZ,
        freq_max_hz=88 * MHZ,
        pulsed=False,
        notes="Narrowband FM push-to-talk; intermittent carrier.",
    ),
    SignalLibraryEntry(
        id="VHF-MAR",
        name="Marine VHF voice",
        emitter_class=EmitterClass.VOICE_COMMS,
        threat=ThreatLevel.NONE,
        freq_min_hz=156 * MHZ,
        freq_max_hz=162.05 * MHZ,
        pulsed=False,
        notes="International maritime mobile band.",
    ),
    SignalLibraryEntry(
        id="DL-L",
        name="L-band tactical data link",
        emitter_class=EmitterClass.DATA_LINK,
        threat=ThreatLevel.MEDIUM,
        freq_min_hz=960 * MHZ,
        freq_max_hz=1215 * MHZ,
        pulsed=True,
        pri_min_us=5,
        pri_max_us=40,
        pw_min_us=2,
        pw_max_us=10,
        notes="TDMA pulsed terminal; frequency-hopping variants show as wide band.",
    ),
    SignalLibraryEntry(
        id="SR-L",
        name="L-band long-range surveillance radar",
        emitter_class=EmitterClass.SURVEILLANCE_RADAR,
        threat=ThreatLevel.LOW,
        freq_min_hz=1.215 * GHZ,
        freq_max_hz=1.4 * GHZ,
        pulsed=True,
        pri_min_us=2000,
        pri_max_us=4500,
        pw_min_us=20,
        pw_max_us=300,
        notes="Long PRI, long pulse; slow mechanical scan.",
    ),
    SignalLibraryEntry(
        id="UAS-C2-24",
        name="2.4 GHz UAS command link",
        emitter_class=EmitterClass.UAS_CONTROL,
        threat=ThreatLevel.MEDIUM,
        freq_min_hz=2.4 * GHZ,
        freq_max_hz=2.4835 * GHZ,
        pulsed=False,
        notes="ISM-band spread spectrum control uplink.",
    ),
    SignalLibraryEntry(
        id="SR-S",
        name="S-band air surveillance radar",
        emitter_class=EmitterClass.SURVEILLANCE_RADAR,
        threat=ThreatLevel.LOW,
        freq_min_hz=2.7 * GHZ,
        freq_max_hz=3.1 * GHZ,
        pulsed=True,
        pri_min_us=700,
        pri_max_us=1300,
        pw_min_us=0.8,
        pw_max_us=25,
        notes="Airport / coastal air surveillance class.",
    ),
    SignalLibraryEntry(
        id="UAS-VID-58",
        name="5.8 GHz UAS video downlink",
        emitter_class=EmitterClass.UAS_VIDEO,
        threat=ThreatLevel.MEDIUM,
        freq_min_hz=5.725 * GHZ,
        freq_max_hz=5.875 * GHZ,
        pulsed=False,
        notes="Analogue or digital FPV video, 10-40 MHz wide.",
    ),
    SignalLibraryEntry(
        id="FC-X",
        name="X-band fire control / tracking radar",
        emitter_class=EmitterClass.FIRE_CONTROL_RADAR,
        threat=ThreatLevel.HIGH,
        freq_min_hz=8.5 * GHZ,
        freq_max_hz=9.25 * GHZ,
        pulsed=True,
        pri_min_us=40,
        pri_max_us=450,
        pw_min_us=0.1,
        pw_max_us=3,
        notes="High PRF, short pulse. Steady illumination indicates a track lock.",
    ),
    SignalLibraryEntry(
        id="NAV-X",
        name="X-band marine navigation radar",
        emitter_class=EmitterClass.NAVIGATION_RADAR,
        threat=ThreatLevel.NONE,
        freq_min_hz=9.3 * GHZ,
        freq_max_hz=9.5 * GHZ,
        pulsed=True,
        pri_min_us=250,
        pri_max_us=1600,
        pw_min_us=0.04,
        pw_max_us=1.5,
        notes="Commercial magnetron navigation radar, 20-48 rpm scan.",
    ),
    SignalLibraryEntry(
        id="FC-KU",
        name="Ku-band fire control radar",
        emitter_class=EmitterClass.FIRE_CONTROL_RADAR,
        threat=ThreatLevel.HIGH,
        freq_min_hz=15.0 * GHZ,
        freq_max_hz=17.5 * GHZ,
        pulsed=True,
        pri_min_us=20,
        pri_max_us=300,
        pw_min_us=0.05,
        pw_max_us=2,
        notes="Short-range precision tracker.",
    ),
]


def get_entry(library: list[SignalLibraryEntry], entry_id: str) -> SignalLibraryEntry | None:
    return next((e for e in library if e.id == entry_id), None)
