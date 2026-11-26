import math

import numpy as np
import pytest

from ew_core import geo
from ew_core.propagation import PropagationModel, fspl_db, knife_edge_loss_db
from ew_core.terrain import FlatTerrain, SyntheticCoastTerrain


class Ridge:
    """A single 300 m ridge running north-south at lon = -1.0, 2 km wide."""

    name = "ridge"
    description = "test"

    def elevation(self, lat, lon):
        lon = np.asarray(lon, dtype=float)
        return np.where(np.abs(lon + 1.0) < 0.015, 300.0, 0.0) * np.ones_like(
            np.asarray(lat, dtype=float)
        )


def test_fspl_matches_textbook():
    # 10 km at 1 GHz: 20log10(10) + 20log10(1000) + 32.44 = 112.44 dB
    assert float(fspl_db(10_000, 1e9)) == pytest.approx(112.44, abs=0.02)


def test_knife_edge_loss_shape():
    assert float(knife_edge_loss_db(-2.0)) == 0.0
    assert float(knife_edge_loss_db(0.0)) == pytest.approx(6.0, abs=0.1)  # grazing ~6 dB
    assert float(knife_edge_loss_db(3.0)) > 20.0
    assert knife_edge_loss_db(np.array([-1.0, 0.0, 1.0, 2.0])).tolist() == sorted(
        knife_edge_loss_db(np.array([-1.0, 0.0, 1.0, 2.0])).tolist()
    )


def test_flat_terrain_los_equals_fspl():
    pm = PropagationModel(FlatTerrain())
    tx = (55.5, -1.0)
    rx = geo.destination(55.5, -1.0, 90.0, 30_000)
    pl = pm.path_loss(*tx, 20.0, *rx, 3000.0, 3e9)
    slant = math.hypot(30_000, 2980)
    assert pl.los
    assert pl.diffraction_db == 0.0
    assert pl.total_db == pytest.approx(float(fspl_db(slant, 3e9)), abs=0.05)


def test_ridge_between_low_antennas_adds_loss_and_breaks_los():
    pm = PropagationModel(Ridge())
    tx = (55.5, -1.2)
    rx = (55.5, -0.8)
    low = pm.path_loss(*tx, 10.0, *rx, 10.0, 400e6)
    high = pm.path_loss(*tx, 10.0, *rx, 3000.0, 400e6)
    assert not low.los
    assert low.diffraction_db > 15.0
    assert high.los
    assert high.diffraction_db == 0.0


def test_grid_matches_scalar_path_loss():
    pm = PropagationModel(SyntheticCoastTerrain())
    tx = (55.35, -1.55)
    tx_alt = pm.msl(*tx, 10.0)
    lats = np.array([55.35, 55.60, 55.30])
    lons = np.array([-0.50, -1.00, -2.30])
    power = pm.received_power_grid(*tx, tx_alt, 90.0, 2.9e9, lats, lons, 500.0)
    # The batch shares one profile sample count across all paths, so agreement is to a few
    # hundredths of a dB rather than exact.
    for i in range(3):
        pl = pm.path_loss(*tx, tx_alt, float(lats[i]), float(lons[i]), 500.0, 2.9e9)
        assert power[i] == pytest.approx(90.0 - pl.total_db, abs=0.2)


def test_inland_receiver_is_shadowed_by_hills():
    pm = PropagationModel(SyntheticCoastTerrain())
    coast_radar = (55.35, -1.55)
    tx_alt = pm.msl(*coast_radar, 10.0)
    # Low receiver west of the Cheviot-like hill vs. the same range out to sea.
    behind_hill = pm.path_loss(
        *coast_radar, tx_alt, 55.50, -2.60, pm.msl(55.50, -2.60, 50.0), 2.9e9
    )
    at_sea = pm.path_loss(*coast_radar, tx_alt, 55.35, -0.50, 50.0, 2.9e9)
    assert not behind_hill.los
    assert behind_hill.diffraction_db > at_sea.diffraction_db + 10.0
