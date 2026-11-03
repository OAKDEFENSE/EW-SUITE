"""Ties the receiver front end, detector, tracker and alerting together."""

from __future__ import annotations

import time
from collections import deque

from .detector import detect, fuse_descriptors
from .library import DEFAULT_LIBRARY
from .models import (
    Alert,
    AlertKind,
    EmitterTrack,
    EngineState,
    ReceiverConfig,
    ScenarioInfo,
    SignalLibraryEntry,
    SpectrumFrame,
    ThreatLevel,
)
from .simulation import RfEnvironment, build_scenarios
from .tracker import Tracker, TrackEvent, TrackEventKind


def _fmt_freq(hz: float) -> str:
    if hz >= 1e9:
        return f"{hz / 1e9:.3f} GHz"
    if hz >= 1e6:
        return f"{hz / 1e6:.2f} MHz"
    return f"{hz / 1e3:.0f} kHz"


class Engine:
    def __init__(
        self,
        scenario: str = "littoral_patrol",
        *,
        library: list[SignalLibraryEntry] | None = None,
        seed: int | None = None,
        start_time: float | None = None,
    ) -> None:
        self.library = library or DEFAULT_LIBRARY
        self.receiver = ReceiverConfig()
        self.scenarios = build_scenarios()
        self.tracker = Tracker(self.library)
        self.alerts: deque[Alert] = deque(maxlen=200)
        self._alert_seq = 0
        self._seed = seed
        self.time = start_time if start_time is not None else time.time()
        self.scenario_name = scenario
        self.env = RfEnvironment(self.scenarios[scenario], seed=seed)
        self.spectrum: SpectrumFrame = SpectrumFrame(
            time=self.time,
            start_hz=self.receiver.start_hz,
            stop_hz=self.receiver.stop_hz,
            power_dbm=[],
            noise_floor_dbm=-100.0,
        )
        self._push_alert(
            ThreatLevel.NONE,
            AlertKind.SYSTEM,
            None,
            f"Scenario loaded: {self.env.scenario.title}",
        )

    # ------------------------------------------------------------ control
    def list_scenarios(self) -> list[ScenarioInfo]:
        return [s.info() for s in self.scenarios.values()]

    def load_scenario(self, name: str) -> None:
        if name not in self.scenarios:
            raise KeyError(name)
        # Rebuild so a reloaded scenario starts from its initial geometry.
        self.scenarios = build_scenarios()
        self.scenario_name = name
        self.env = RfEnvironment(self.scenarios[name], seed=self._seed)
        self.tracker.reset()
        self._push_alert(
            ThreatLevel.NONE,
            AlertKind.SYSTEM,
            None,
            f"Scenario loaded: {self.env.scenario.title}",
        )

    def set_receiver(self, cfg: ReceiverConfig) -> ReceiverConfig:
        if cfg.stop_hz <= cfg.start_hz:
            raise ValueError("stop_hz must be greater than start_hz")
        self.receiver = cfg
        self._push_alert(
            ThreatLevel.NONE,
            AlertKind.SYSTEM,
            None,
            f"Receiver tuned {_fmt_freq(cfg.start_hz)} - {_fmt_freq(cfg.stop_hz)}",
        )
        return self.receiver

    # --------------------------------------------------------------- tick
    def tick(self, dt: float) -> list[Alert]:
        self.time += dt
        self.env.step(dt)
        frame, descriptors = self.env.acquire(self.receiver, self.time)
        self.spectrum = frame
        dets = detect(frame, self.receiver.detection_threshold_db)
        dets = fuse_descriptors(dets, descriptors, frame.bin_width_hz)
        events = self.tracker.update(dets, self.env.ownship(), self.time, frame.bin_width_hz)
        return [a for a in (self._alert_for(ev) for ev in events) if a is not None]

    # -------------------------------------------------------------- state
    @property
    def tracks(self) -> list[EmitterTrack]:
        return self.tracker.tracks

    def state(self) -> EngineState:
        return EngineState(
            time=self.time,
            scenario=self.scenario_name,
            receiver=self.receiver,
            ownship=self.env.ownship(),
            spectrum=self.spectrum,
            tracks=self.tracker.tracks,
            alerts=list(self.alerts),
        )

    # ------------------------------------------------------------- alerts
    def _push_alert(
        self, severity: ThreatLevel, kind: AlertKind, track_id: str | None, message: str
    ) -> Alert:
        self._alert_seq += 1
        alert = Alert(
            id=self._alert_seq,
            time=self.time,
            severity=severity,
            kind=kind,
            track_id=track_id,
            message=message,
        )
        self.alerts.append(alert)
        return alert

    def _alert_for(self, ev: TrackEvent) -> Alert | None:
        t = ev.track
        label = f"{t.id} {t.classification.name} @ {_fmt_freq(t.freq_hz)}"
        brg = f", brg {t.bearing_deg:03.0f}" if t.bearing_deg is not None else ""
        if ev.kind == TrackEventKind.CONFIRMED:
            return self._push_alert(
                t.classification.threat, AlertKind.NEW_TRACK, t.id, f"New emitter {label}{brg}"
            )
        if ev.kind == TrackEventKind.THREAT:
            return self._push_alert(
                t.classification.threat,
                AlertKind.THREAT,
                t.id,
                f"THREAT {t.classification.threat.upper()}: {label}{brg}",
            )
        if ev.kind == TrackEventKind.LOST:
            return self._push_alert(ThreatLevel.NONE, AlertKind.TRACK_LOST, t.id, f"Lost {label}")
        if ev.kind == TrackEventKind.GEO_FIX and t.geo is not None:
            return self._push_alert(
                t.classification.threat,
                AlertKind.GEO_FIX,
                t.id,
                f"Geolocated {label}: {t.geo.position.lat:.3f}, {t.geo.position.lon:.3f} "
                f"(±{t.geo.error_radius_m / 1000:.1f} km)",
            )
        return None
