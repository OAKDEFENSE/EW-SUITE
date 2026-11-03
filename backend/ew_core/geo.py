"""Geodesy helpers and bearing-only geolocation.

Positions are WGS-84 latitude/longitude in degrees. A spherical Earth model is used,
which is accurate to well under 1% over the tactical ranges (< 300 km) this service
works with.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

EARTH_RADIUS_M = 6_371_000.0


def wrap_deg(angle: float) -> float:
    """Wrap an angle to [0, 360)."""
    return angle % 360.0


def angular_diff_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings, in degrees [0, 180]."""
    d = (a - b + 180.0) % 360.0 - 180.0
    return abs(d)


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial true bearing from point 1 to point 2, degrees [0, 360)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return wrap_deg(math.degrees(math.atan2(x, y)))


def destination(lat: float, lon: float, brg_deg: float, dist_m: float) -> tuple[float, float]:
    """Point reached travelling ``dist_m`` along ``brg_deg`` from (lat, lon)."""
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    b = math.radians(brg_deg)
    ad = dist_m / EARTH_RADIUS_M
    p2 = math.asin(math.sin(p1) * math.cos(ad) + math.cos(p1) * math.sin(ad) * math.cos(b))
    l2 = l1 + math.atan2(
        math.sin(b) * math.sin(ad) * math.cos(p1),
        math.cos(ad) - math.sin(p1) * math.sin(p2),
    )
    return math.degrees(p2), (math.degrees(l2) + 540.0) % 360.0 - 180.0


def to_local_xy(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """Equirectangular projection to a local east/north frame in metres."""
    x = math.radians(lon - ref_lon) * math.cos(math.radians(ref_lat)) * EARTH_RADIUS_M
    y = math.radians(lat - ref_lat) * EARTH_RADIUS_M
    return x, y


def from_local_xy(x: float, y: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    lat = ref_lat + math.degrees(y / EARTH_RADIUS_M)
    lon = ref_lon + math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(ref_lat))))
    return lat, lon


def triangulate(
    observations: Sequence[tuple[float, float, float]],
    min_spread_deg: float = 3.0,
) -> tuple[float, float, float] | None:
    """Least-squares intersection of bearing lines.

    ``observations`` are ``(observer_lat, observer_lon, bearing_deg)`` tuples. The
    estimate minimises the sum of squared perpendicular distances from the fix to each
    bearing line. Returns ``(lat, lon, error_radius_m)`` or ``None`` when the geometry
    is too weak (fewer than two lines, insufficient angular spread, or the fix lies
    behind the observers).
    """
    if len(observations) < 2:
        return None

    bearings = [b for _, _, b in observations]
    spread = max(angular_diff_deg(b, bearings[0]) for b in bearings)
    if spread < min_spread_deg:
        return None

    ref_lat = sum(o[0] for o in observations) / len(observations)
    ref_lon = sum(o[1] for o in observations) / len(observations)

    a_mat = np.zeros((2, 2))
    b_vec = np.zeros(2)
    points: list[np.ndarray] = []
    dirs: list[np.ndarray] = []
    for lat, lon, brg in observations:
        p = np.array(to_local_xy(lat, lon, ref_lat, ref_lon))
        d = np.array([math.sin(math.radians(brg)), math.cos(math.radians(brg))])
        proj = np.eye(2) - np.outer(d, d)
        a_mat += proj
        b_vec += proj @ p
        points.append(p)
        dirs.append(d)

    if abs(np.linalg.det(a_mat)) < 1e-9:
        return None
    fix = np.linalg.solve(a_mat, b_vec)

    # Reject solutions behind the majority of observers (reciprocal-bearing ambiguity).
    ahead = sum(1 for p, d in zip(points, dirs, strict=True) if float((fix - p) @ d) > 0)
    if ahead < 0.6 * len(points):
        return None

    residuals = []
    for p, d in zip(points, dirs, strict=True):
        v = fix - p
        residuals.append(abs(float(d[0] * v[1] - d[1] * v[0])))
    rms = math.sqrt(sum(r * r for r in residuals) / len(residuals))
    # Scale the residual by sample count: a confident fix tightens as bearings accumulate.
    error_radius = max(100.0, 2.0 * rms / math.sqrt(max(len(points) / 4.0, 1.0)))

    lat, lon = from_local_xy(float(fix[0]), float(fix[1]), ref_lat, ref_lon)
    return lat, lon, error_radius
