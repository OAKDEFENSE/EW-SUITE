"""Ties the receiver front end, detector, tracker and alerting together."""

from __future__ import annotations

import math
import time
from collections import deque

import numpy as np

from .detector import detect, fuse_descriptors
from .library import DEFAULT_LIBRARY
from .models import (
    Alert,
    AlertKind,
    CoverageGrid,
    CoverageRequest,
    EmitterTrack,
    EngineState,
    GridBounds,
    Position,
    ReceiverConfig,
    ScenarioInfo,
    SignalLibraryEntry,
    SpectrumFrame,
    TerrainGrid,
    TerrainInfo,
    ThreatLevel,
)
from .propagation import PropagationModel
from .simulation import RfEnvironment, build_scenarios
from .terrain import Terrain, load_terrain
from .tracker import ASSUMED_EMITTER_AGL_M, Tracker, TrackEvent, TrackEventKind


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
        terrain: Terrain | str | None = None,
    ) -> None:
        self.library = library or DEFAULT_LIBRARY
        self.receiver = ReceiverConfig()
        self.scenarios = build_scenarios()
        self.terrain: Terrain = (
            terrain if not isinstance(terrain, str | None) else load_terrain(terrain)
        )
        self.propagation = PropagationModel(self.terrain)
        self.tracker = Tracker(self.library, propagation=self.propagation)
        self.alerts: deque[Alert] = deque(maxlen=200)
        self._alert_seq = 0
        self._seed = seed
        self.time = start_time if start_time is not None else time.time()
        self.scenario_name = scenario
        self.env = RfEnvironment(self.scenarios[scenario], seed=seed, terrain=self.terrain)
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
        self.env = RfEnvironment(self.scenarios[name], seed=self._seed, terrain=self.terrain)
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

    # ------------------------------------------------------- terrain / coverage
    def terrain_info(self) -> TerrainInfo:
        return TerrainInfo(model=self.terrain.name, description=self.terrain.description)

    def terrain_grid(self, bounds: GridBounds, n: int = 120) -> TerrainGrid:
        if bounds.north <= bounds.south or bounds.east <= bounds.west:
            raise ValueError("bounds must have north > south and east > west")
        aspect = (
            (bounds.east - bounds.west)
            * math.cos(math.radians((bounds.north + bounds.south) / 2))
            / (bounds.north - bounds.south)
        )
        n_lat = n
        n_lon = int(np.clip(round(n * aspect), 10, 2 * n))
        lats = np.linspace(bounds.north, bounds.south, n_lat)  # north -> south
        lons = np.linspace(bounds.west, bounds.east, n_lon)
        grid_lat, grid_lon = np.meshgrid(lats, lons, indexing="ij")
        elev = self.terrain.elevation(grid_lat, grid_lon)
        return TerrainGrid(
            bounds=bounds,
            n_lat=n_lat,
            n_lon=n_lon,
            elevation_m=np.round(elev, 0).tolist(),
        )

    def coverage(self, req: CoverageRequest) -> CoverageGrid:
        dlat = req.radius_km / 111.2
        dlon = req.radius_km / (111.2 * math.cos(math.radians(req.lat)))
        bounds = GridBounds(
            south=req.lat - dlat, west=req.lon - dlon, north=req.lat + dlat, east=req.lon + dlon
        )
        lats = np.linspace(bounds.north, bounds.south, req.n)
        lons = np.linspace(bounds.west, bounds.east, req.n)
        grid_lat, grid_lon = np.meshgrid(lats, lons, indexing="ij")
        flat_lat, flat_lon = grid_lat.ravel(), grid_lon.ravel()
        if req.rx_alt_ref == "agl":
            rx_alt = self.terrain.elevation(flat_lat, flat_lon) + req.rx_alt_m
        else:
            rx_alt = np.full(flat_lat.shape, req.rx_alt_m)
        power = self.propagation.received_power_grid(
            req.lat,
            req.lon,
            self.propagation.msl(req.lat, req.lon, req.alt_agl_m),
            req.eirp_dbm,
            req.freq_hz,
            flat_lat,
            flat_lon,
            rx_alt,
        ).reshape(req.n, req.n)
        return CoverageGrid(
            bounds=bounds,
            n=req.n,
            power_dbm=np.round(power, 1).tolist(),
            threshold_dbm=req.threshold_dbm,
            covered_fraction=float((power >= req.threshold_dbm).mean()),
            tx=Position(lat=req.lat, lon=req.lon, alt_m=req.alt_agl_m),
            eirp_dbm=req.eirp_dbm,
            freq_hz=req.freq_hz,
            rx_alt_m=req.rx_alt_m,
            rx_alt_ref=req.rx_alt_ref,
        )

    def track_coverage(
        self,
        track_id: str,
        *,
        rx_alt_m: float | None = None,
        rx_alt_ref: str = "agl",
        radius_km: float = 60.0,
        n: int = 80,
    ) -> CoverageGrid | None:
        """Coverage of a geolocated track using its estimated EIRP. ``None`` without a fix."""
        t = self.tracker.get(track_id)
        if t is None:
            raise KeyError(track_id)
        if t.geo is None or t.est_eirp_dbm is None:
            return None
        if rx_alt_m is None:
            rx_alt_m, rx_alt_ref = self.env.ownship().position.alt_m, "msl"
        threshold = self.spectrum.noise_floor_dbm + self.receiver.detection_threshold_db
        req = CoverageRequest(
            lat=t.geo.position.lat,
            lon=t.geo.position.lon,
            alt_agl_m=ASSUMED_EMITTER_AGL_M,
            eirp_dbm=t.est_eirp_dbm,
            freq_hz=t.freq_hz,
            rx_alt_m=rx_alt_m,
            rx_alt_ref=rx_alt_ref,  # type: ignore[arg-type]
            radius_km=radius_km,
            n=n,
            threshold_dbm=threshold,
        )
        return self.coverage(req)

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
