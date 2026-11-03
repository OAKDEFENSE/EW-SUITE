"""Shared data models for the EW core service and its API."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ThreatLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


THREAT_RANK: dict[ThreatLevel, int] = {
    ThreatLevel.NONE: 0,
    ThreatLevel.LOW: 1,
    ThreatLevel.MEDIUM: 2,
    ThreatLevel.HIGH: 3,
    ThreatLevel.CRITICAL: 4,
}


class EmitterClass(StrEnum):
    SURVEILLANCE_RADAR = "surveillance_radar"
    NAVIGATION_RADAR = "navigation_radar"
    FIRE_CONTROL_RADAR = "fire_control_radar"
    VOICE_COMMS = "voice_comms"
    DATA_LINK = "data_link"
    UAS_CONTROL = "uas_control"
    UAS_VIDEO = "uas_video"
    UNKNOWN = "unknown"


class PulseParams(BaseModel):
    """Pulse descriptor measurements for a pulsed emitter."""

    pri_us: float = Field(description="Pulse repetition interval, microseconds")
    pw_us: float = Field(description="Pulse width, microseconds")


class SignalLibraryEntry(BaseModel):
    id: str
    name: str
    emitter_class: EmitterClass
    threat: ThreatLevel
    freq_min_hz: float
    freq_max_hz: float
    pulsed: bool
    pri_min_us: float | None = None
    pri_max_us: float | None = None
    pw_min_us: float | None = None
    pw_max_us: float | None = None
    notes: str = ""


class Position(BaseModel):
    lat: float
    lon: float
    alt_m: float = 0.0


class Ownship(BaseModel):
    position: Position
    heading_deg: float
    speed_mps: float


class Detection(BaseModel):
    """A signal detected in one spectrum frame, optionally enriched with DF and PDW data."""

    freq_hz: float
    bandwidth_hz: float
    power_dbm: float
    bearing_deg: float | None = None
    pulse: PulseParams | None = None


class GeoFix(BaseModel):
    position: Position
    error_radius_m: float
    n_bearings: int


class Classification(BaseModel):
    library_id: str | None
    name: str
    emitter_class: EmitterClass
    threat: ThreatLevel
    confidence: float = Field(ge=0.0, le=1.0)


UNKNOWN_CLASSIFICATION = Classification(
    library_id=None,
    name="Unknown emitter",
    emitter_class=EmitterClass.UNKNOWN,
    threat=ThreatLevel.LOW,
    confidence=0.0,
)


class TrackStatus(StrEnum):
    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    LOST = "lost"


class EmitterTrack(BaseModel):
    id: str
    status: TrackStatus
    freq_hz: float
    bandwidth_hz: float
    power_dbm: float
    bearing_deg: float | None
    pulse: PulseParams | None
    classification: Classification
    hits: int
    first_seen: float
    last_seen: float
    geo: GeoFix | None = None
    peak_power_dbm: float | None = Field(
        default=None, description="Highest received power over the recent window"
    )
    est_eirp_dbm: float | None = Field(
        default=None, description="EIRP estimated from peak power and path loss to the fix"
    )
    los: bool | None = Field(
        default=None, description="Whether the geolocated fix is line-of-sight from ownship"
    )


class AlertKind(StrEnum):
    NEW_TRACK = "new_track"
    THREAT = "threat"
    TRACK_LOST = "track_lost"
    GEO_FIX = "geo_fix"
    SYSTEM = "system"


class Alert(BaseModel):
    id: int
    time: float
    severity: ThreatLevel
    kind: AlertKind
    track_id: str | None
    message: str


class SpectrumFrame(BaseModel):
    time: float
    start_hz: float
    stop_hz: float
    power_dbm: list[float]
    noise_floor_dbm: float

    @property
    def n_bins(self) -> int:
        return len(self.power_dbm)

    @property
    def bin_width_hz(self) -> float:
        return (self.stop_hz - self.start_hz) / max(self.n_bins, 1)


class ReceiverConfig(BaseModel):
    start_hz: float = Field(default=30e6, gt=0)
    stop_hz: float = Field(default=18e9, gt=0)
    n_bins: int = Field(default=2048, ge=64, le=16384)
    detection_threshold_db: float = Field(default=10.0, ge=3.0, le=40.0)

    @property
    def bin_width_hz(self) -> float:
        return (self.stop_hz - self.start_hz) / self.n_bins


class ScenarioInfo(BaseModel):
    name: str
    title: str
    description: str


class EngineState(BaseModel):
    time: float
    scenario: str
    receiver: ReceiverConfig
    ownship: Ownship
    spectrum: SpectrumFrame
    tracks: list[EmitterTrack]
    alerts: list[Alert]


class TerrainInfo(BaseModel):
    model: str
    description: str


class GridBounds(BaseModel):
    south: float
    west: float
    north: float
    east: float


class TerrainGrid(BaseModel):
    """Elevation raster. Rows run north to south, columns west to east."""

    bounds: GridBounds
    n_lat: int
    n_lon: int
    elevation_m: list[list[float]]


class CoverageRequest(BaseModel):
    lat: float
    lon: float
    alt_agl_m: float = Field(default=10.0, ge=0.0, description="Transmit antenna height AGL")
    eirp_dbm: float
    freq_hz: float = Field(gt=0)
    rx_alt_m: float = Field(default=50.0, ge=0.0)
    rx_alt_ref: Literal["agl", "msl"] = "agl"
    radius_km: float = Field(default=60.0, gt=1.0, le=300.0)
    n: int = Field(default=80, ge=10, le=120)
    threshold_dbm: float = Field(default=-90.0, description="Receiver sensitivity for shading")


class CoverageGrid(BaseModel):
    """Received-power raster. Rows run north to south, columns west to east."""

    bounds: GridBounds
    n: int
    power_dbm: list[list[float]]
    threshold_dbm: float
    covered_fraction: float
    tx: Position
    eirp_dbm: float
    freq_hz: float
    rx_alt_m: float
    rx_alt_ref: Literal["agl", "msl"]
