"""Emitter track management, classification refresh and bearing-only geolocation."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

from . import geo
from .classifier import classify, is_threat
from .models import (
    THREAT_RANK,
    Classification,
    Detection,
    EmitterTrack,
    GeoFix,
    Ownship,
    Position,
    PulseParams,
    SignalLibraryEntry,
    TrackStatus,
)


class TrackEventKind(StrEnum):
    CONFIRMED = "confirmed"
    THREAT = "threat"
    LOST = "lost"
    DROPPED = "dropped"
    GEO_FIX = "geo_fix"


@dataclass
class TrackEvent:
    kind: TrackEventKind
    track: EmitterTrack


@dataclass
class _Track:
    id: str
    freq_hz: float
    bandwidth_hz: float
    power_dbm: float
    bearing_deg: float | None
    pulse: PulseParams | None
    classification: Classification
    first_seen: float
    last_seen: float
    hits: int = 1
    status: TrackStatus = TrackStatus.TENTATIVE
    geo: GeoFix | None = None
    threat_alerted: bool = False
    geo_alerted: bool = False
    bearing_obs: deque[tuple[float, float, float]] = field(
        default_factory=lambda: deque(maxlen=240)
    )

    def to_model(self) -> EmitterTrack:
        return EmitterTrack(
            id=self.id,
            status=self.status,
            freq_hz=self.freq_hz,
            bandwidth_hz=self.bandwidth_hz,
            power_dbm=self.power_dbm,
            bearing_deg=self.bearing_deg,
            pulse=self.pulse,
            classification=self.classification,
            hits=self.hits,
            first_seen=self.first_seen,
            last_seen=self.last_seen,
            geo=self.geo,
        )


def _circular_ema(prev: float, new: float, alpha: float) -> float:
    d = (new - prev + 180.0) % 360.0 - 180.0
    return geo.wrap_deg(prev + alpha * d)


class Tracker:
    def __init__(
        self,
        library: list[SignalLibraryEntry],
        *,
        confirm_hits: int = 3,
        lost_after_s: float = 5.0,
        drop_after_s: float = 60.0,
        freq_tol_frac: float = 0.003,
        bearing_tol_deg: float = 20.0,
        min_geo_bearings: int = 6,
        min_geo_baseline_m: float = 2500.0,
    ) -> None:
        self.library = library
        self.confirm_hits = confirm_hits
        self.lost_after_s = lost_after_s
        self.drop_after_s = drop_after_s
        self.freq_tol_frac = freq_tol_frac
        self.bearing_tol_deg = bearing_tol_deg
        self.min_geo_bearings = min_geo_bearings
        self.min_geo_baseline_m = min_geo_baseline_m
        self._tracks: dict[str, _Track] = {}
        self._seq = 0

    # ------------------------------------------------------------- queries
    @property
    def tracks(self) -> list[EmitterTrack]:
        return [t.to_model() for t in self._tracks.values()]

    def get(self, track_id: str) -> EmitterTrack | None:
        t = self._tracks.get(track_id)
        return t.to_model() if t else None

    def reset(self) -> None:
        self._tracks.clear()
        self._seq = 0

    # -------------------------------------------------------------- update
    def update(
        self,
        detections: list[Detection],
        ownship: Ownship,
        now: float,
        bin_width_hz: float,
    ) -> list[TrackEvent]:
        events: list[TrackEvent] = []
        unmatched = list(range(len(detections)))

        # Greedy association: closest frequency first.
        pairs: list[tuple[float, str, int]] = []
        for tid, tr in self._tracks.items():
            for i, det in enumerate(detections):
                df = abs(det.freq_hz - tr.freq_hz)
                tol = max(self.freq_tol_frac * tr.freq_hz, 2.0 * bin_width_hz, tr.bandwidth_hz)
                if df > tol:
                    continue
                if (
                    det.bearing_deg is not None
                    and tr.bearing_deg is not None
                    and geo.angular_diff_deg(det.bearing_deg, tr.bearing_deg) > self.bearing_tol_deg
                ):
                    continue
                pairs.append((df / tol, tid, i))
        pairs.sort()
        assigned_tracks: set[str] = set()
        for _, tid, i in pairs:
            if tid in assigned_tracks or i not in unmatched:
                continue
            assigned_tracks.add(tid)
            unmatched.remove(i)
            events.extend(self._update_track(self._tracks[tid], detections[i], ownship, now))

        for i in unmatched:
            self._new_track(detections[i], ownship, now)

        # Age out.
        for tid in list(self._tracks):
            tr = self._tracks[tid]
            if tid in assigned_tracks:
                continue
            age = now - tr.last_seen
            if tr.status != TrackStatus.LOST and age > self.lost_after_s:
                tr.status = TrackStatus.LOST
                if tr.hits >= self.confirm_hits:
                    events.append(TrackEvent(TrackEventKind.LOST, tr.to_model()))
            if age > self.drop_after_s:
                events.append(TrackEvent(TrackEventKind.DROPPED, tr.to_model()))
                del self._tracks[tid]
        return events

    # ------------------------------------------------------------ internals
    def _new_track(self, det: Detection, ownship: Ownship, now: float) -> None:
        self._seq += 1
        tr = _Track(
            id=f"E-{self._seq:03d}",
            freq_hz=det.freq_hz,
            bandwidth_hz=det.bandwidth_hz,
            power_dbm=det.power_dbm,
            bearing_deg=det.bearing_deg,
            pulse=det.pulse,
            classification=classify(det, self.library),
            first_seen=now,
            last_seen=now,
        )
        self._record_bearing(tr, det, ownship, now)
        self._tracks[tr.id] = tr

    def _update_track(
        self, tr: _Track, det: Detection, ownship: Ownship, now: float
    ) -> list[TrackEvent]:
        events: list[TrackEvent] = []
        tr.freq_hz += 0.3 * (det.freq_hz - tr.freq_hz)
        tr.bandwidth_hz += 0.3 * (det.bandwidth_hz - tr.bandwidth_hz)
        tr.power_dbm += 0.5 * (det.power_dbm - tr.power_dbm)
        if det.bearing_deg is not None:
            tr.bearing_deg = (
                det.bearing_deg
                if tr.bearing_deg is None
                else _circular_ema(tr.bearing_deg, det.bearing_deg, 0.35)
            )
        if det.pulse is not None:
            if tr.pulse is None:
                tr.pulse = det.pulse
            else:
                tr.pulse = PulseParams(
                    pri_us=tr.pulse.pri_us + 0.3 * (det.pulse.pri_us - tr.pulse.pri_us),
                    pw_us=tr.pulse.pw_us + 0.3 * (det.pulse.pw_us - tr.pulse.pw_us),
                )
        tr.hits += 1
        tr.last_seen = now
        if tr.status == TrackStatus.LOST:
            confirmed = tr.hits >= self.confirm_hits
            tr.status = TrackStatus.CONFIRMED if confirmed else TrackStatus.TENTATIVE

        # Re-classify with the smoothed parameters.
        smoothed = Detection(
            freq_hz=tr.freq_hz,
            bandwidth_hz=tr.bandwidth_hz,
            power_dbm=tr.power_dbm,
            bearing_deg=tr.bearing_deg,
            pulse=tr.pulse,
        )
        new_cls = classify(smoothed, self.library)
        if new_cls.confidence >= tr.classification.confidence or (
            THREAT_RANK[new_cls.threat] > THREAT_RANK[tr.classification.threat]
        ):
            tr.classification = new_cls

        if tr.status == TrackStatus.TENTATIVE and tr.hits >= self.confirm_hits:
            tr.status = TrackStatus.CONFIRMED
            events.append(TrackEvent(TrackEventKind.CONFIRMED, tr.to_model()))

        if (
            tr.status == TrackStatus.CONFIRMED
            and not tr.threat_alerted
            and is_threat(tr.classification)
        ):
            tr.threat_alerted = True
            events.append(TrackEvent(TrackEventKind.THREAT, tr.to_model()))

        self._record_bearing(tr, det, ownship, now)
        if self._try_geolocate(tr) and not tr.geo_alerted:
            tr.geo_alerted = True
            events.append(TrackEvent(TrackEventKind.GEO_FIX, tr.to_model()))
        return events

    def _record_bearing(self, tr: _Track, det: Detection, ownship: Ownship, now: float) -> None:
        if det.bearing_deg is None:
            return
        tr.bearing_obs.append((ownship.position.lat, ownship.position.lon, det.bearing_deg))

    def _try_geolocate(self, tr: _Track) -> bool:
        obs = list(tr.bearing_obs)
        if len(obs) < self.min_geo_bearings:
            return False
        baseline = geo.distance_m(obs[0][0], obs[0][1], obs[-1][0], obs[-1][1])
        if baseline < self.min_geo_baseline_m:
            return False
        # Thin to at most 48 observations to keep the solve cheap.
        step = max(1, math.ceil(len(obs) / 48))
        result = geo.triangulate(obs[::step])
        if result is None:
            return False
        lat, lon, err = result
        if err > 50_000:
            return False
        tr.geo = GeoFix(
            position=Position(lat=lat, lon=lon, alt_m=0.0),
            error_radius_m=round(err, 0),
            n_bearings=len(obs),
        )
        return True
