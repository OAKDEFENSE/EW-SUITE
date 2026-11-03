import math

import pytest

from ew_core import geo
from ew_core.links import (
    MARGIN_OK_DB,
    LinkBudget,
    link_state,
    noise_dbm,
    overlap_fraction,
)
from ew_core.models import (
    BlueLink,
    BlueNetwork,
    BlueNode,
    BlueNodeKind,
    Classification,
    EmitterClass,
    EmitterTrack,
    GeoFix,
    LinkState,
    Ownship,
    Position,
    ThreatLevel,
    TrackStatus,
)
from ew_core.propagation import PropagationModel, fspl_db
from ew_core.terrain import FlatTerrain


def _own(lat=55.5, lon=-1.0, alt=3000.0):
    return Ownship(position=Position(lat=lat, lon=lon, alt_m=alt), heading_deg=0, speed_mps=100)


def _network():
    return BlueNetwork(
        nodes=[
            BlueNode(id="OWN", name="own", kind=BlueNodeKind.OWNSHIP, antenna_gain_dbi=3.0),
            BlueNode(
                id="GCS",
                name="gcs",
                kind=BlueNodeKind.GROUND,
                position=Position(lat=55.5, lon=-1.0, alt_m=10.0),
                antenna_gain_dbi=6.0,
                noise_figure_db=4.0,
            ),
            BlueNode(
                id="UAS",
                name="uas",
                kind=BlueNodeKind.UAS,
                position=Position(lat=55.5, lon=-0.6, alt_m=500.0),
                alt_ref="msl",
                antenna_gain_dbi=2.0,
                noise_figure_db=5.0,
            ),
        ],
        links=[
            BlueLink(
                id="C2",
                name="c2",
                tx="GCS",
                rx="UAS",
                freq_hz=1.35e9,
                bandwidth_hz=5e6,
                tx_power_dbm=40.0,
                tx_gain_dbi=6.0,
                required_snr_db=10.0,
            ),
            BlueLink(
                id="ADL",
                name="adl",
                tx="OWN",
                rx="GCS",
                freq_hz=1.05e9,
                bandwidth_hz=3e6,
                tx_power_dbm=47.0,
                tx_gain_dbi=3.0,
            ),
        ],
    )


def _jammer(lat, lon, eirp, freq=1.355e9, bw=40e6, fixed=True, status=TrackStatus.CONFIRMED):
    return EmitterTrack(
        id="E-009",
        status=status,
        freq_hz=freq,
        bandwidth_hz=bw,
        power_dbm=-60,
        bearing_deg=270,
        pulse=None,
        classification=Classification(
            library_id="JAM-WB",
            name="Wideband noise jammer",
            emitter_class=EmitterClass.JAMMER,
            threat=ThreatLevel.HIGH,
            confidence=0.9,
        ),
        hits=50,
        first_seen=0,
        last_seen=10,
        geo=GeoFix(position=Position(lat=lat, lon=lon, alt_m=0), error_radius_m=500, n_bearings=50)
        if fixed
        else None,
        est_eirp_dbm=eirp if fixed else None,
    )


def test_noise_and_overlap_and_state():
    assert noise_dbm(1e6, 0.0) == pytest.approx(-114.0)
    assert noise_dbm(5e6, 4.0) == pytest.approx(-103.0, abs=0.05)
    assert overlap_fraction(1.35e9, 5e6, 1.355e9, 40e6) == pytest.approx(5e6 / 40e6)
    assert overlap_fraction(1.35e9, 5e6, 1.40e9, 40e6) == 0.0
    assert overlap_fraction(1.35e9, 5e6, 1.349e9, 2e6) == pytest.approx(1.0)
    assert link_state(MARGIN_OK_DB) == LinkState.OK
    assert link_state(3.0) == LinkState.MARGINAL
    assert link_state(-0.1) == LinkState.FAILED


def test_budget_matches_free_space_hand_calculation():
    lb = LinkBudget(PropagationModel(FlatTerrain()))
    net = _network()
    status = lb.evaluate(net, _own(), [])
    c2 = next(s for s in status if s.link_id == "C2")
    slant = math.hypot(c2.distance_m, 500.0 - 10.0)
    expected_signal = 40 + 6 - float(fspl_db(slant, 1.35e9)) + 2
    assert c2.signal_dbm == pytest.approx(expected_signal, abs=0.1)
    assert c2.noise_dbm == pytest.approx(noise_dbm(5e6, 5.0), abs=0.05)
    assert c2.jam_dbm is None
    assert c2.sinr_db == c2.snr_db
    assert c2.margin_db == pytest.approx(c2.snr_db - 10.0, abs=0.1)
    assert c2.state == LinkState.OK
    assert c2.los
    adl = next(s for s in status if s.link_id == "ADL")
    assert adl.tx_position.alt_m == 3000.0  # ownship resolved dynamically


def test_in_band_fixed_jammer_degrades_link_and_unfixed_is_flagged():
    lb = LinkBudget(PropagationModel(FlatTerrain()))
    net = _network()
    clean = lb.evaluate_link(net, net.links[0], _own(), [])
    jammed = lb.evaluate_link(net, net.links[0], _own(), [_jammer(55.5, -0.65, 66.0)])
    assert jammed.jam_dbm is not None and jammed.jam_dbm > jammed.noise_dbm
    assert jammed.margin_db < clean.margin_db - 20
    assert jammed.state == LinkState.FAILED
    assert [i.track_id for i in jammed.interferers] == ["E-009"]
    # Interference scales with bandwidth overlap: 5 of 40 MHz lands in the link.
    assert jammed.interferers[0].jam_dbm == pytest.approx(
        66
        - float(fspl_db(math.hypot(jammed.distance_m * 0 + 3140, 490), 1.355e9))
        + 2
        + 10 * math.log10(5 / 40),
        abs=1.5,
    )

    unfixed = lb.evaluate_link(net, net.links[0], _own(), [_jammer(55.5, -0.65, 66.0, fixed=False)])
    assert unfixed.jam_dbm is None
    assert unfixed.unlocated_interferers == ["E-009"]
    assert unfixed.state == clean.state

    out_of_band = lb.evaluate_link(
        net, net.links[0], _own(), [_jammer(55.5, -0.65, 66.0, freq=2.4e9)]
    )
    assert out_of_band.interferers == [] and out_of_band.unlocated_interferers == []

    lost = lb.evaluate_link(
        net, net.links[0], _own(), [_jammer(55.5, -0.65, 66.0, status=TrackStatus.LOST)]
    )
    assert lost.interferers == []


def test_relay_grid_prefers_sites_between_the_ends_and_away_from_jammer():
    lb = LinkBudget(PropagationModel(FlatTerrain()))
    net = _network()
    link = net.links[0]
    grid = lb.relay_grid(net, link, _own(), [], relay_alt_m=300, n=21, radius_km=30)
    assert grid.n == 21 and len(grid.margin_db) == 21
    assert grid.best is not None and grid.best_margin_db is not None
    # Best relay site lies roughly between the two ends.
    assert 55.3 < grid.best.lat < 55.7 and -1.05 < grid.best.lon < -0.55
    # Flat terrain, modest range: a relay cannot beat the direct link by much but is close.
    assert grid.best_margin_db > grid.direct_margin_db - 6

    jammed = lb.relay_grid(
        net, link, _own(), [_jammer(55.5, -0.65, 70.0)], relay_alt_m=300, n=21, radius_km=30
    )
    # Interference at the receiver is the same for every candidate, so the way to recover
    # margin is a short final hop: the best site moves toward the (jammed) UAS end.
    assert jammed.best is not None and grid.best is not None
    uas = (55.5, -0.6)
    d_clean = geo.distance_m(grid.best.lat, grid.best.lon, *uas)
    d_jammed = geo.distance_m(jammed.best.lat, jammed.best.lon, *uas)
    assert d_jammed < d_clean
    assert jammed.best_margin_db is not None and jammed.best_margin_db < grid.best_margin_db


def test_network_validation():
    with pytest.raises(ValueError):
        BlueNetwork(
            nodes=[BlueNode(id="A", name="a", kind=BlueNodeKind.GROUND)],  # missing position
        )
    with pytest.raises(ValueError):
        BlueNetwork(
            nodes=[
                BlueNode(id="A", name="a", kind=BlueNodeKind.OWNSHIP),
            ],
            links=[
                BlueLink(
                    id="L", name="l", tx="A", rx="B", freq_hz=1e9, bandwidth_hz=1e6, tx_power_dbm=30
                )
            ],
        )
