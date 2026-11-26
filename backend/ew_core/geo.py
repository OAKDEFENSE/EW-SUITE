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


def _bearing_cost(
    x: float, y: float, px: np.ndarray, py: np.ndarray, brg_rad: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Angular residuals (rad) and ranges from each observer to candidate (x, y)."""
    dx = x - px
    dy = y - py
    pred = np.arctan2(dx, dy)
    res = (pred - brg_rad + np.pi) % (2 * np.pi) - np.pi
    return res, np.hypot(dx, dy)


def triangulate(
    observations: Sequence[tuple[float, float, float]],
    min_spread_deg: float = 3.0,
    max_range_m: float = 400_000.0,
) -> tuple[float, float, float] | None:
    """Bearings-only position estimate from a set of observer positions and bearings.

    ``observations`` are ``(observer_lat, observer_lon, bearing_deg)`` tuples. The estimate
    minimises the sum of squared *angular* residuals (maximum likelihood for Gaussian
    bearing noise). A pseudolinear "closest point to all lines" solution is deliberately
    not used: with noisy bearings and a short baseline it is strongly biased toward the
    observers. The solver initialises with a range search along the mean bearing and
    refines with damped Gauss-Newton.

    Returns ``(lat, lon, error_radius_m)`` or ``None`` when the geometry is too weak
    (fewer than two bearings, insufficient angular spread, a solution behind the observers
    or beyond ``max_range_m``, or an unusable uncertainty).
    """
    if len(observations) < 2:
        return None

    bearings = [b for _, _, b in observations]
    # Observability: the bearing must actually drift across the window. A linear fit of the
    # (time-ordered) bearings is robust to per-sample noise, unlike a raw min/max spread,
    # and is what catches a platform flying straight at the emitter.
    unwrapped = np.degrees(np.unwrap(np.radians(np.array(bearings, dtype=float))))
    if len(unwrapped) > 2:
        slope = np.polyfit(np.arange(len(unwrapped)), unwrapped, 1)[0]
        spread = abs(float(slope) * (len(unwrapped) - 1))
    else:
        spread = angular_diff_deg(bearings[0], bearings[-1])
    if spread < min_spread_deg:
        return None

    ref_lat = sum(o[0] for o in observations) / len(observations)
    ref_lon = sum(o[1] for o in observations) / len(observations)
    xy = np.array([to_local_xy(lat, lon, ref_lat, ref_lon) for lat, lon, _ in observations])
    px, py = xy[:, 0], xy[:, 1]
    brg = np.radians(np.array(bearings, dtype=float))
    n = brg.size

    # Initial guess: best range along the mean bearing from the observer centroid.
    mean_dir = np.array([np.sin(brg).mean(), np.cos(brg).mean()])
    norm = float(np.hypot(*mean_dir))
    if norm < 1e-9:
        return None
    mean_dir /= norm
    best_cost, x, y = math.inf, 0.0, 0.0
    for r in np.geomspace(200.0, max_range_m, 60):
        cx, cy = float(mean_dir[0] * r), float(mean_dir[1] * r)
        res, _ = _bearing_cost(cx, cy, px, py, brg)
        cost = float(res @ res)
        if cost < best_cost:
            best_cost, x, y = cost, cx, cy

    # Damped Gauss-Newton on the angular residuals.
    lam = 1e-3
    for _ in range(40):
        res, rng = _bearing_cost(x, y, px, py, brg)
        rng2 = np.maximum(rng * rng, 1.0)
        jac = np.column_stack(((y - py) / rng2, -(x - px) / rng2))  # d(bearing)/d(x, y)
        jtj = jac.T @ jac
        g = jac.T @ res
        try:
            step = np.linalg.solve(jtj + lam * np.diag(np.diag(jtj)) + 1e-18 * np.eye(2), -g)
        except np.linalg.LinAlgError:
            return None
        nx, ny = x + float(step[0]), y + float(step[1])
        new_res, _ = _bearing_cost(nx, ny, px, py, brg)
        if float(new_res @ new_res) < float(res @ res):
            x, y = nx, ny
            lam = max(lam / 3.0, 1e-9)
            if float(np.hypot(*step)) < 0.5:
                break
        else:
            lam *= 10.0
            if lam > 1e6:
                break

    res, rng = _bearing_cost(x, y, px, py, brg)
    if float(np.hypot(x, y)) > max_range_m:
        return None
    # Reject solutions behind the majority of observers (reciprocal-bearing ambiguity).
    ahead = int((np.abs(res) < np.pi / 2).sum())
    if ahead < 0.6 * n:
        return None

    # Uncertainty from the Jacobian at the solution, with the bearing noise estimated from
    # the residuals (floored so a perfectly consistent set still gets a finite radius).
    rms = float(np.sqrt((res @ res) / n))
    sigma = max(rms, math.radians(0.5))
    rng2 = np.maximum(rng * rng, 1.0)
    jac = np.column_stack(((y - py) / rng2, -(x - px) / rng2))
    try:
        cov = sigma * sigma * np.linalg.inv(jac.T @ jac)
    except np.linalg.LinAlgError:
        return None
    error_radius = float(2.0 * math.sqrt(max(np.trace(cov), 0.0)))
    if not math.isfinite(error_radius) or error_radius > 100_000.0:
        return None
    error_radius = max(100.0, error_radius)

    lat, lon = from_local_xy(x, y, ref_lat, ref_lon)
    return lat, lon, error_radius
