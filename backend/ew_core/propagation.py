"""Terrain-aware RF path loss.

Model: free-space loss plus single knife-edge diffraction over the dominant obstacle on a
sampled terrain profile, with 4/3-Earth curvature. It is deliberately simple (no
multi-edge Deygout, no clutter, no ducting) but captures the first-order effect that
matters for an ESM picture: whether a low emitter is shadowed by terrain, and how much.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from . import geo
from .terrain import Terrain

C_MPS = 299_792_458.0
K_FACTOR = 4.0 / 3.0
EFFECTIVE_RADIUS_M = K_FACTOR * geo.EARTH_RADIUS_M


def fspl_db(distance_m: NDArray[np.float64] | float, freq_hz: float) -> NDArray[np.float64]:
    d = np.maximum(np.asarray(distance_m, dtype=float), 1.0)
    return 20.0 * np.log10(d) + 20.0 * np.log10(freq_hz) - 147.55


def knife_edge_loss_db(v: NDArray[np.float64] | float) -> NDArray[np.float64]:
    """ITU-R P.526 single knife-edge approximation; zero below v = -0.78."""
    v = np.asarray(v, dtype=float)
    # Clamp before evaluating so -inf (no profile samples) cannot produce inf - inf.
    v_safe = np.maximum(v, -0.78)
    loss = 6.9 + 20.0 * np.log10(np.sqrt((v_safe - 0.1) ** 2 + 1.0) + v_safe - 0.1)
    return np.where(v > -0.78, loss, 0.0)


@dataclass(frozen=True)
class PathLoss:
    total_db: float
    fspl_db: float
    diffraction_db: float
    los: bool
    distance_m: float


class PropagationModel:
    def __init__(
        self,
        terrain: Terrain,
        *,
        sample_spacing_m: float = 200.0,
        min_samples: int = 16,
        max_samples: int = 400,
    ) -> None:
        self.terrain = terrain
        self.sample_spacing_m = sample_spacing_m
        self.min_samples = min_samples
        self.max_samples = max_samples

    # ----------------------------------------------------------------- helpers
    def ground_m(self, lat: float, lon: float) -> float:
        return float(self.terrain.elevation(lat, lon))

    def msl(self, lat: float, lon: float, agl_m: float) -> float:
        return self.ground_m(lat, lon) + agl_m

    def _n_samples(self, max_distance_m: float) -> int:
        return int(
            np.clip(max_distance_m / self.sample_spacing_m, self.min_samples, self.max_samples)
        )

    # ------------------------------------------------------------------- core
    def excess_loss(
        self,
        tx_lat: float,
        tx_lon: float,
        tx_alt_msl: float,
        rx_lat: NDArray[np.float64],
        rx_lon: NDArray[np.float64],
        rx_alt_msl: NDArray[np.float64] | float,
        freq_hz: float,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.bool_]]:
        """Return (distance_m, diffraction_db, los) for one transmitter and many receivers."""
        rx_lat = np.asarray(rx_lat, dtype=float).ravel()
        rx_lon = np.asarray(rx_lon, dtype=float).ravel()
        rx_alt = np.broadcast_to(np.asarray(rx_alt_msl, dtype=float), rx_lat.shape).astype(float)
        m = rx_lat.size

        dist = np.array(
            [
                geo.distance_m(tx_lat, tx_lon, float(la), float(lo))
                for la, lo in zip(rx_lat, rx_lon, strict=True)
            ]
        )
        n = self._n_samples(float(dist.max(initial=0.0)))
        # Interior sample fractions; endpoints are the antennas themselves.
        t = (np.arange(1, n) / n).reshape(1, n - 1)
        lats = tx_lat + (rx_lat.reshape(m, 1) - tx_lat) * t
        lons = tx_lon + (rx_lon.reshape(m, 1) - tx_lon) * t
        ground = self.terrain.elevation(lats, lons)

        d = dist.reshape(m, 1)
        d1 = d * t
        d2 = d - d1
        bulge = d1 * d2 / (2.0 * EFFECTIVE_RADIUS_M)
        ray = tx_alt_msl + (rx_alt.reshape(m, 1) - tx_alt_msl) * t
        obstruction = ground + bulge - ray  # +ve where terrain pokes above the direct ray

        lam = C_MPS / freq_hz
        with np.errstate(divide="ignore", invalid="ignore"):
            v = obstruction * np.sqrt(2.0 * d / (lam * d1 * d2))
        v = np.where(np.isfinite(v), v, -np.inf)
        v_max = v.max(axis=1)
        diffraction = knife_edge_loss_db(v_max)
        los = obstruction.max(axis=1) < 0.0
        return dist, diffraction, los

    def path_loss(
        self,
        tx_lat: float,
        tx_lon: float,
        tx_alt_msl: float,
        rx_lat: float,
        rx_lon: float,
        rx_alt_msl: float,
        freq_hz: float,
    ) -> PathLoss:
        dist, diff, los = self.excess_loss(
            tx_lat, tx_lon, tx_alt_msl, np.array([rx_lat]), np.array([rx_lon]), rx_alt_msl, freq_hz
        )
        # Include the height difference in the free-space distance (slant range).
        slant = float(np.hypot(dist[0], rx_alt_msl - tx_alt_msl))
        f = float(fspl_db(slant, freq_hz))
        return PathLoss(
            total_db=f + float(diff[0]),
            fspl_db=f,
            diffraction_db=float(diff[0]),
            los=bool(los[0]),
            distance_m=float(dist[0]),
        )

    def received_power_grid(
        self,
        tx_lat: float,
        tx_lon: float,
        tx_alt_msl: float,
        eirp_dbm: float,
        freq_hz: float,
        lats: NDArray[np.float64],
        lons: NDArray[np.float64],
        rx_alt_msl: NDArray[np.float64] | float,
    ) -> NDArray[np.float64]:
        """Received power (dBm) at every (lat, lon) in the flattened receiver arrays."""
        dist, diff, _ = self.excess_loss(
            tx_lat, tx_lon, tx_alt_msl, lats, lons, rx_alt_msl, freq_hz
        )
        rx_alt = np.broadcast_to(np.asarray(rx_alt_msl, dtype=float), dist.shape)
        slant = np.hypot(dist, rx_alt - tx_alt_msl)
        return eirp_dbm - fspl_db(slant, freq_hz) - diff
