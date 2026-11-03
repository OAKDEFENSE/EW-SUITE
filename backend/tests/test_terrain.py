import numpy as np
import pytest

from ew_core.terrain import FlatTerrain, HgtTerrain, SyntheticCoastTerrain, load_terrain


def test_flat_is_zero_and_broadcasts():
    t = FlatTerrain()
    assert t.elevation(55.0, -1.0) == 0.0
    assert t.elevation(np.array([55.0, 56.0]), np.array([-1.0, -2.0])).shape == (2,)


def test_synthetic_sea_east_land_west():
    t = SyntheticCoastTerrain()
    assert float(t.elevation(55.6, -0.5)) == 0.0  # open sea
    coast_plain = float(t.elevation(55.35, -1.60))
    hills = float(t.elevation(55.48, -2.15))
    assert 10 < coast_plain < 200
    assert hills > 600
    assert hills > coast_plain


def test_synthetic_is_vectorised_and_deterministic():
    t = SyntheticCoastTerrain()
    lats = np.linspace(55.0, 56.0, 50)
    lons = np.linspace(-2.5, 0.0, 60)
    g_lat, g_lon = np.meshgrid(lats, lons, indexing="ij")
    a = t.elevation(g_lat, g_lon)
    b = t.elevation(g_lat, g_lon)
    assert a.shape == (50, 60)
    assert np.array_equal(a, b)
    assert (a >= 0).all()


def test_hgt_reader_bilinear_and_missing_tiles(tmp_path):
    # 11x11 tile for N55W002: elevation = 100 * row index (row 0 = north edge = lat 56).
    n = 11
    tile = (np.arange(n)[:, None] * 100 + np.zeros((n, n))).astype(">i2")
    tile[5, 5] = -32768  # a void should read as 0, not -32768
    (tmp_path / "N55W002.hgt").write_bytes(tile.tobytes())
    t = HgtTerrain(tmp_path)
    assert t.elevation(56.0, -2.0) == pytest.approx(0.0)  # north edge, row 0
    assert t.elevation(55.0, -2.0) == pytest.approx(1000.0)  # south edge, row 10
    assert t.elevation(55.55, -1.7) == pytest.approx(450.0)  # 4.5 rows down -> interpolated
    assert t.elevation(55.5, -1.5) == pytest.approx(0.0)  # void cell
    assert t.elevation(55.5, -3.5) == 0.0  # missing tile -> sea
    assert HgtTerrain.tile_name(-33, 151) == "S33E151.hgt"


def test_load_terrain_specs(tmp_path):
    assert load_terrain(None).name == "synthetic"
    assert load_terrain("flat").name == "flat"
    assert load_terrain(f"hgt:{tmp_path}").name == "hgt"
    with pytest.raises(ValueError):
        load_terrain("moon")
    with pytest.raises(FileNotFoundError):
        load_terrain("hgt:/definitely/not/here")
