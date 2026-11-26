"""Blue-force link budgets with interference from the ESM picture.

For each own link the budget is: received signal from the transmitter (terrain-aware path
loss), thermal noise in the link bandwidth, and in-band interference from every geolocated
emitter track whose occupied band overlaps the link, using the track's estimated EIRP and
the modelled path loss from its fix to the link receiver. The result is a signal-to-
interference-plus-noise margin against the link's required SNR.

The same machinery evaluates candidate relay positions over a grid.
"""

from __future__ import annotations

import math

import numpy as np

from . import geo
from .models import (
    BlueLink,
    BlueNetwork,
    BlueNode,
    BlueNodeKind,
    EmitterTrack,
    GridBounds,
    LinkInterferer,
    LinkState,
    LinkStatus,
    Ownship,
    Position,
    RelayGrid,
    TrackStatus,
)
from .propagation import PropagationModel

THERMAL_NOISE_DBM_HZ = -174.0
MARGIN_OK_DB = 6.0
# Antenna height assumed for a geolocated interferer, matching the tracker's EIRP estimate.
INTERFERER_AGL_M = 10.0


def noise_dbm(bandwidth_hz: float, noise_figure_db: float) -> float:
    return THERMAL_NOISE_DBM_HZ + 10.0 * math.log10(max(bandwidth_hz, 1.0)) + noise_figure_db


def overlap_fraction(
    link_freq_hz: float, link_bw_hz: float, em_freq_hz: float, em_bw_hz: float
) -> float:
    """Fraction of an emitter's power (spread evenly over its band) that lands in the link."""
    lo = max(link_freq_hz - link_bw_hz / 2, em_freq_hz - em_bw_hz / 2)
    hi = min(link_freq_hz + link_bw_hz / 2, em_freq_hz + em_bw_hz / 2)
    if hi <= lo:
        return 0.0
    return (hi - lo) / max(em_bw_hz, 1.0)


def _db_sum(*values_dbm: float) -> float:
    return 10.0 * math.log10(sum(10 ** (v / 10.0) for v in values_dbm))


def link_state(margin_db: float) -> LinkState:
    if margin_db >= MARGIN_OK_DB:
        return LinkState.OK
    if margin_db >= 0.0:
        return LinkState.MARGINAL
    return LinkState.FAILED


class LinkBudget:
    def __init__(self, propagation: PropagationModel) -> None:
        self.propagation = propagation

    # ------------------------------------------------------------ positions
    def resolve(self, node: BlueNode, ownship: Ownship) -> tuple[Position, float]:
        """Return the node's position and its antenna height above mean sea level."""
        if node.kind == BlueNodeKind.OWNSHIP or node.position is None:
            pos = ownship.position
            return pos, pos.alt_m
        pos = node.position
        if node.alt_ref == "agl":
            return pos, self.propagation.msl(pos.lat, pos.lon, pos.alt_m)
        return pos, pos.alt_m

    # ---------------------------------------------------------- interference
    def _in_band_tracks(self, link: BlueLink, tracks: list[EmitterTrack]) -> list[EmitterTrack]:
        return [
            t
            for t in tracks
            if t.status != TrackStatus.LOST
            and overlap_fraction(link.freq_hz, link.bandwidth_hz, t.freq_hz, t.bandwidth_hz) > 0
        ]

    def _interference_at(
        self,
        link: BlueLink,
        rx_gain_dbi: float,
        rx_pos: Position,
        rx_alt_msl: float,
        tracks: list[EmitterTrack],
    ) -> tuple[list[LinkInterferer], list[str]]:
        located: list[LinkInterferer] = []
        unlocated: list[str] = []
        for t in self._in_band_tracks(link, tracks):
            if t.geo is None or t.est_eirp_dbm is None:
                unlocated.append(t.id)
                continue
            fix = t.geo.position
            loss = self.propagation.path_loss(
                fix.lat,
                fix.lon,
                self.propagation.msl(fix.lat, fix.lon, INTERFERER_AGL_M),
                rx_pos.lat,
                rx_pos.lon,
                rx_alt_msl,
                t.freq_hz,
            )
            frac = overlap_fraction(link.freq_hz, link.bandwidth_hz, t.freq_hz, t.bandwidth_hz)
            jam = t.est_eirp_dbm - loss.total_db + rx_gain_dbi + 10.0 * math.log10(frac)
            located.append(
                LinkInterferer(
                    track_id=t.id,
                    name=t.classification.name,
                    freq_hz=t.freq_hz,
                    jam_dbm=round(jam, 1),
                    los=loss.los,
                )
            )
        return located, unlocated

    # -------------------------------------------------------------- budgets
    def evaluate_link(
        self, network: BlueNetwork, link: BlueLink, ownship: Ownship, tracks: list[EmitterTrack]
    ) -> LinkStatus:
        tx_node = network.node(link.tx)
        rx_node = network.node(link.rx)
        if tx_node is None or rx_node is None:
            raise KeyError(f"link {link.id} references an unknown node")
        tx_pos, tx_alt = self.resolve(tx_node, ownship)
        rx_pos, rx_alt = self.resolve(rx_node, ownship)
        loss = self.propagation.path_loss(
            tx_pos.lat, tx_pos.lon, tx_alt, rx_pos.lat, rx_pos.lon, rx_alt, link.freq_hz
        )
        signal = link.tx_power_dbm + link.tx_gain_dbi - loss.total_db + rx_node.antenna_gain_dbi
        noise = noise_dbm(link.bandwidth_hz, rx_node.noise_figure_db)
        interferers, unlocated = self._interference_at(
            link, rx_node.antenna_gain_dbi, rx_pos, rx_alt, tracks
        )
        jam = _db_sum(*(i.jam_dbm for i in interferers)) if interferers else None
        snr = signal - noise
        sinr = signal - (_db_sum(noise, jam) if jam is not None else noise)
        margin = sinr - link.required_snr_db
        return LinkStatus(
            link_id=link.id,
            name=link.name,
            tx=link.tx,
            rx=link.rx,
            tx_position=tx_pos,
            rx_position=rx_pos,
            distance_m=round(loss.distance_m, 0),
            los=loss.los,
            signal_dbm=round(signal, 1),
            noise_dbm=round(noise, 1),
            jam_dbm=None if jam is None else round(jam, 1),
            snr_db=round(snr, 1),
            sinr_db=round(sinr, 1),
            margin_db=round(margin, 1),
            state=link_state(margin),
            interferers=interferers,
            unlocated_interferers=unlocated,
        )

    def evaluate(
        self, network: BlueNetwork, ownship: Ownship, tracks: list[EmitterTrack]
    ) -> list[LinkStatus]:
        return [self.evaluate_link(network, link, ownship, tracks) for link in network.links]

    # ----------------------------------------------------------- relay sites
    def relay_grid(
        self,
        network: BlueNetwork,
        link: BlueLink,
        ownship: Ownship,
        tracks: list[EmitterTrack],
        *,
        relay_alt_m: float = 300.0,
        relay_alt_ref: str = "agl",
        relay_gain_dbi: float = 2.0,
        relay_noise_figure_db: float = 5.0,
        radius_km: float | None = None,
        n: int = 60,
    ) -> RelayGrid:
        """Minimum of the two hop margins (tx -> relay, relay -> rx) over candidate relay cells.

        The relay re-transmits with the link's power and gain. Interference at the relay is
        position-dependent and evaluated per cell; interference at the final receiver is the
        same as for the direct link.
        """
        direct = self.evaluate_link(network, link, ownship, tracks)
        tx_pos, tx_alt = self.resolve(network.node(link.tx), ownship)  # type: ignore[arg-type]
        rx_pos, rx_alt = self.resolve(network.node(link.rx), ownship)  # type: ignore[arg-type]
        rx_node = network.node(link.rx)
        assert rx_node is not None

        mid_lat = (tx_pos.lat + rx_pos.lat) / 2
        mid_lon = (tx_pos.lon + rx_pos.lon) / 2
        if radius_km is None:
            radius_km = max(20.0, 0.75 * direct.distance_m / 1000.0)
        dlat = radius_km / 111.2
        dlon = radius_km / (111.2 * math.cos(math.radians(mid_lat)))
        bounds = GridBounds(
            south=mid_lat - dlat, west=mid_lon - dlon, north=mid_lat + dlat, east=mid_lon + dlon
        )
        lats = np.linspace(bounds.north, bounds.south, n)
        lons = np.linspace(bounds.west, bounds.east, n)
        g_lat, g_lon = np.meshgrid(lats, lons, indexing="ij")
        f_lat, f_lon = g_lat.ravel(), g_lon.ravel()
        if relay_alt_ref == "agl":
            relay_alt = self.propagation.terrain.elevation(f_lat, f_lon) + relay_alt_m
        else:
            relay_alt = np.full(f_lat.shape, relay_alt_m)

        eirp = link.tx_power_dbm + link.tx_gain_dbi
        # Hop 1: transmitter -> relay candidates.
        s1 = (
            self.propagation.received_power_grid(
                tx_pos.lat, tx_pos.lon, tx_alt, eirp, link.freq_hz, f_lat, f_lon, relay_alt
            )
            + relay_gain_dbi
        )
        n1 = noise_dbm(link.bandwidth_hz, relay_noise_figure_db)
        j1_lin = np.zeros(f_lat.shape)
        for t in self._in_band_tracks(link, tracks):
            if t.geo is None or t.est_eirp_dbm is None:
                continue
            fix = t.geo.position
            frac = overlap_fraction(link.freq_hz, link.bandwidth_hz, t.freq_hz, t.bandwidth_hz)
            jam = (
                self.propagation.received_power_grid(
                    fix.lat,
                    fix.lon,
                    self.propagation.msl(fix.lat, fix.lon, INTERFERER_AGL_M),
                    t.est_eirp_dbm,
                    t.freq_hz,
                    f_lat,
                    f_lon,
                    relay_alt,
                )
                + relay_gain_dbi
                + 10.0 * math.log10(frac)
            )
            j1_lin += 10 ** (jam / 10.0)
        sinr1 = s1 - 10.0 * np.log10(10 ** (n1 / 10.0) + j1_lin)
        margin1 = sinr1 - link.required_snr_db

        # Hop 2: relay candidates -> receiver (reciprocal path loss).
        s2 = (
            self.propagation.received_power_grid(
                rx_pos.lat, rx_pos.lon, rx_alt, eirp, link.freq_hz, f_lat, f_lon, relay_alt
            )
            + rx_node.antenna_gain_dbi
        )
        n2_total = (
            _db_sum(direct.noise_dbm, direct.jam_dbm)
            if direct.jam_dbm is not None
            else direct.noise_dbm
        )
        margin2 = s2 - n2_total - link.required_snr_db

        margin = np.minimum(margin1, margin2).reshape(n, n)
        best_idx = int(np.argmax(margin))
        best_r, best_c = divmod(best_idx, n)
        best_margin = float(margin[best_r, best_c])
        return RelayGrid(
            link_id=link.id,
            bounds=bounds,
            n=n,
            margin_db=np.round(margin, 1).tolist(),
            relay_alt_m=relay_alt_m,
            relay_alt_ref=relay_alt_ref,  # type: ignore[arg-type]
            best=Position(lat=float(lats[best_r]), lon=float(lons[best_c]), alt_m=relay_alt_m)
            if math.isfinite(best_margin)
            else None,
            best_margin_db=round(best_margin, 1) if math.isfinite(best_margin) else None,
            direct_margin_db=direct.margin_db,
        )


def blue_positions(network: BlueNetwork, ownship: Ownship) -> dict[str, Position]:
    """Convenience for callers that only need where each node is right now."""
    out: dict[str, Position] = {}
    for node in network.nodes:
        out[node.id] = (
            ownship.position
            if node.kind == BlueNodeKind.OWNSHIP or node.position is None
            else node.position
        )
    return out


def bearing_between(a: Position, b: Position) -> float:
    return geo.bearing_deg(a.lat, a.lon, b.lat, b.lon)
