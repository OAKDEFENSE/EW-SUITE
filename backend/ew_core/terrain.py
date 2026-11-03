"""Terrain elevation models.

All models expose ``elevation(lat, lon)`` returning metres above mean sea level, vectorised
over numpy arrays. Three implementations are provided:

* :class:`FlatTerrain` - sea level everywhere.
* :class:`SyntheticCoastTerrain` - a deterministic coastline with hills, matching the
  North Sea geometry of the built-in scenarios, so terrain shadowing can be demonstrated
  without downloading elevation data.
* :class:`HgtTerrain` - reads SRTM / ASTER ``.hgt`` tiles (big-endian int16 squares named
  like ``N55W002.hgt``) from a directory, with bilinear interpolation and lazy caching.

Select one with ``load_terrain("flat" | "synthetic" | "hgt:/path/to/tiles")``.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import ArrayLike, NDArray

HGT_VOID = -32768


class Terrain(Protocol):
    name: str
    description: str

    def elevation(self, lat: ArrayLike, lon: ArrayLike) -> NDArray[np.float64]: ...


class FlatTerrain:
    name = "flat"
    description = "Sea level everywhere (free-space propagation)."

    def elevation(self, lat: ArrayLike, lon: ArrayLike) -> NDArray[np.float64]:
        lat_a = np.asarray(lat, dtype=float)
        return np.zeros(np.broadcast(lat_a, np.asarray(lon, dtype=float)).shape)


class SyntheticCoastTerrain:
    """Procedural coast running roughly north-north-west with a coastal plain and hills.

    Land lies west of the coastline ``lon_c(lat) = -1.5 - 0.6 * (lat - 55.3)``. Elevation rises
    inland and is topped with a few Gaussian hills. Everything is smooth and deterministic.
    """

    name = "synthetic"
    description = "Synthetic North Sea coastline with inland hills (demonstration terrain)."

    # (lat, lon, height_m, sigma_km)
    HILLS = (
        (55.48, -2.15, 760.0, 9.0),
        (55.28, -1.95, 400.0, 5.0),
        (55.72, -2.25, 520.0, 7.0),
        (55.05, -1.85, 260.0, 6.0),
    )

    def coast_lon(self, lat: NDArray[np.float64]) -> NDArray[np.float64]:
        return -1.5 - 0.6 * (lat - 55.3)

    def elevation(self, lat: ArrayLike, lon: ArrayLike) -> NDArray[np.float64]:
        lat_a, lon_a = np.broadcast_arrays(
            np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
        )
        km_per_deg_lon = 111.2 * np.cos(np.radians(lat_a))
        inland_km = (self.coast_lon(lat_a) - lon_a) * km_per_deg_lon  # +ve on land
        land = 0.5 * (1.0 + np.tanh(inland_km / 0.6))
        plain = 12.0 + 9.0 * np.clip(inland_km, 0.0, 45.0)
        # Gentle rolling texture so profiles are not perfectly planar.
        texture = 18.0 * (np.sin(lat_a * 180.0) * np.cos(lon_a * 120.0) + 1.0)
        elev = plain + texture
        for h_lat, h_lon, h_m, sigma_km in self.HILLS:
            dx = (lon_a - h_lon) * km_per_deg_lon
            dy = (lat_a - h_lat) * 111.2
            elev = elev + h_m * np.exp(-0.5 * (dx * dx + dy * dy) / (sigma_km * sigma_km))
        return np.where(land > 0.02, land * elev, 0.0)


class HgtTerrain:
    """Elevation from a directory of ``.hgt`` tiles. Missing tiles read as sea level."""

    name = "hgt"

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        if not self.directory.is_dir():
            raise FileNotFoundError(f"terrain directory not found: {self.directory}")
        self.description = f"SRTM/ASTER .hgt tiles from {self.directory}"
        self._tiles: dict[tuple[int, int], NDArray[np.float64] | None] = {}

    @staticmethod
    def tile_name(lat0: int, lon0: int) -> str:
        ns = "N" if lat0 >= 0 else "S"
        ew = "E" if lon0 >= 0 else "W"
        return f"{ns}{abs(lat0):02d}{ew}{abs(lon0):03d}.hgt"

    def _tile(self, lat0: int, lon0: int) -> NDArray[np.float64] | None:
        key = (lat0, lon0)
        if key not in self._tiles:
            path = self.directory / self.tile_name(lat0, lon0)
            if path.is_file():
                raw = np.fromfile(path, dtype=">i2")
                n = int(round(math.sqrt(raw.size)))
                if n * n != raw.size:
                    raise ValueError(f"{path} is not a square .hgt tile ({raw.size} samples)")
                data = raw.reshape(n, n).astype(float)
                data[data == HGT_VOID] = 0.0
                self._tiles[key] = data
            else:
                self._tiles[key] = None
        return self._tiles[key]

    def elevation(self, lat: ArrayLike, lon: ArrayLike) -> NDArray[np.float64]:
        lat_a, lon_a = np.broadcast_arrays(
            np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
        )
        out = np.zeros(lat_a.shape)
        lat0 = np.floor(lat_a).astype(int)
        lon0 = np.floor(lon_a).astype(int)
        for key in set(zip(lat0.ravel().tolist(), lon0.ravel().tolist(), strict=True)):
            tile = self._tile(*key)
            if tile is None:
                continue
            n = tile.shape[0]
            mask = (lat0 == key[0]) & (lon0 == key[1])
            # Row 0 is the northern edge of the tile.
            r = (key[0] + 1 - lat_a[mask]) * (n - 1)
            c = (lon_a[mask] - key[1]) * (n - 1)
            r0 = np.clip(np.floor(r).astype(int), 0, n - 2)
            c0 = np.clip(np.floor(c).astype(int), 0, n - 2)
            fr = np.clip(r - r0, 0.0, 1.0)
            fc = np.clip(c - c0, 0.0, 1.0)
            top = tile[r0, c0] * (1 - fc) + tile[r0, c0 + 1] * fc
            bot = tile[r0 + 1, c0] * (1 - fc) + tile[r0 + 1, c0 + 1] * fc
            out[mask] = top * (1 - fr) + bot * fr
        return out


def load_terrain(spec: str | None) -> Terrain:
    spec = (spec or "synthetic").strip()
    if spec == "flat":
        return FlatTerrain()
    if spec == "synthetic":
        return SyntheticCoastTerrain()
    if spec.startswith("hgt:"):
        return HgtTerrain(spec[4:])
    raise ValueError(f"unknown terrain spec {spec!r}; use flat, synthetic or hgt:<dir>")
