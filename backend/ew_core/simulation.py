"""Simulated RF environment.

The simulation plays the role of an ESM receiver front end. Each tick it produces:

* a wideband power spectrum (``SpectrumFrame``) covering the receiver's tuned band, and
* a list of ``PulseDescriptor`` records: per-signal DF bearing and pulse measurements, the
  way a real ESM receiver emits pulse descriptor words (PDWs) alongside raw spectrum.

Replace :class:`RfEnvironment` with a hardware adapter that returns the same two things
and the rest of the pipeline (detector, tracker, classifier, API) is unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import geo
from .models import Ownship, Position, PulseParams, ReceiverConfig, ScenarioInfo, SpectrumFrame

MHZ = 1e6
GHZ = 1e9
KT = 0.514444  # knots -> m/s


@dataclass
class SimEmitter:
    id: str
    name: str
    lat: float
    lon: float
    freq_hz: float
    bandwidth_hz: float
    eirp_dbm: float
    pulsed: bool = False
    pri_us: float = 0.0
    pw_us: float = 0.0
    scan_period_s: float = 0.0  # 0 = no scan (steady illumination)
    beamwidth_deg: float = 2.0
    sidelobe_db: float = -25.0
    duty_cycle: float = 1.0  # fraction of burst_period_s spent transmitting
    burst_period_s: float = 10.0
    speed_mps: float = 0.0
    heading_deg: float = 0.0
    alt_m: float = 10.0

    def step(self, dt: float) -> None:
        if self.speed_mps > 0:
            self.lat, self.lon = geo.destination(
                self.lat, self.lon, self.heading_deg, self.speed_mps * dt
            )

    def transmitting(self, t: float) -> bool:
        if self.duty_cycle >= 1.0:
            return True
        return (t % self.burst_period_s) < self.duty_cycle * self.burst_period_s

    def antenna_gain_db(self, t: float, bearing_to_rx_deg: float) -> float:
        """Relative gain toward the receiver for a rotating antenna."""
        if self.scan_period_s <= 0:
            return 0.0
        pointing = (t / self.scan_period_s) * 360.0 % 360.0
        off = geo.angular_diff_deg(pointing, bearing_to_rx_deg)
        half = self.beamwidth_deg / 2
        if off <= half:
            return 0.0
        if off <= 3 * half:
            # Taper from main lobe into first sidelobe.
            return self.sidelobe_db * (off - half) / (2 * half)
        return self.sidelobe_db


@dataclass
class Route:
    waypoints: list[tuple[float, float]]
    speed_mps: float
    alt_m: float
    _leg: int = 0
    _progress_m: float = 0.0

    def position_heading(self) -> tuple[float, float, float]:
        a = self.waypoints[self._leg]
        b = self.waypoints[(self._leg + 1) % len(self.waypoints)]
        brg = geo.bearing_deg(a[0], a[1], b[0], b[1])
        lat, lon = geo.destination(a[0], a[1], brg, self._progress_m)
        return lat, lon, brg

    def step(self, dt: float) -> None:
        self._progress_m += self.speed_mps * dt
        while True:
            a = self.waypoints[self._leg]
            b = self.waypoints[(self._leg + 1) % len(self.waypoints)]
            leg_len = geo.distance_m(a[0], a[1], b[0], b[1])
            if self._progress_m < leg_len:
                return
            self._progress_m -= leg_len
            self._leg = (self._leg + 1) % len(self.waypoints)


@dataclass
class Scenario:
    name: str
    title: str
    description: str
    route: Route
    emitters: list[SimEmitter] = field(default_factory=list)
    noise_floor_dbm: float = -100.0

    def info(self) -> ScenarioInfo:
        return ScenarioInfo(name=self.name, title=self.title, description=self.description)


@dataclass
class PulseDescriptor:
    """Per-signal measurement a DF/PDW channel would report alongside the spectrum."""

    freq_hz: float
    bearing_deg: float
    power_dbm: float
    pulse: PulseParams | None


def free_space_path_loss_db(distance_m: float, freq_hz: float) -> float:
    d_km = max(distance_m / 1000.0, 0.01)
    f_mhz = freq_hz / 1e6
    return 20 * math.log10(d_km) + 20 * math.log10(f_mhz) + 32.44


def build_scenarios() -> dict[str, Scenario]:
    """Scenario catalogue. Geometry is set in the North Sea off north-east England."""
    littoral = Scenario(
        name="littoral_patrol",
        title="Littoral patrol",
        description=(
            "Maritime patrol aircraft flying a racetrack off the coast. Mixed coastal, "
            "shipborne and small-UAS emitters including a fire control radar lock."
        ),
        route=Route(
            waypoints=[(55.40, -0.50), (55.90, -0.20), (56.00, -1.00), (55.50, -1.30)],
            speed_mps=240 * KT,
            alt_m=3000,
        ),
        emitters=[
            SimEmitter(
                id="SIM-ASR",
                name="Coastal air surveillance radar",
                lat=55.35,
                lon=-1.55,
                freq_hz=2.905 * GHZ,
                bandwidth_hz=2 * MHZ,
                eirp_dbm=95,
                pulsed=True,
                pri_us=1000,
                pw_us=10,
                scan_period_s=10,
                beamwidth_deg=2,
                sidelobe_db=-25,
            ),
            SimEmitter(
                id="SIM-NAV",
                name="Merchant vessel navigation radar",
                lat=55.75,
                lon=-0.40,
                freq_hz=9.41 * GHZ,
                bandwidth_hz=12 * MHZ,
                eirp_dbm=78,
                pulsed=True,
                pri_us=600,
                pw_us=0.3,
                scan_period_s=2.5,
                beamwidth_deg=1.5,
                sidelobe_db=-22,
                speed_mps=7,
                heading_deg=200,
            ),
            SimEmitter(
                id="SIM-FCR",
                name="Patrol craft fire control radar",
                lat=55.95,
                lon=-0.10,
                freq_hz=9.02 * GHZ,
                bandwidth_hz=5 * MHZ,
                eirp_dbm=86,
                pulsed=True,
                pri_us=250,
                pw_us=0.5,
                scan_period_s=0,
                speed_mps=12,
                heading_deg=250,
            ),
            SimEmitter(
                id="SIM-DL",
                name="Patrol craft data link terminal",
                lat=55.95,
                lon=-0.10,
                freq_hz=1.10 * GHZ,
                bandwidth_hz=3 * MHZ,
                eirp_dbm=70,
                pulsed=True,
                pri_us=13,
                pw_us=6.4,
                speed_mps=12,
                heading_deg=250,
            ),
            SimEmitter(
                id="SIM-VHF",
                name="VHF tactical voice net",
                lat=55.30,
                lon=-1.60,
                freq_hz=46.5 * MHZ,
                bandwidth_hz=25e3,
                eirp_dbm=42,
                duty_cycle=0.4,
                burst_period_s=12,
            ),
            SimEmitter(
                id="SIM-MAR",
                name="Merchant vessel marine VHF",
                lat=55.75,
                lon=-0.40,
                freq_hz=156.8 * MHZ,
                bandwidth_hz=25e3,
                eirp_dbm=44,
                duty_cycle=0.15,
                burst_period_s=30,
                speed_mps=7,
                heading_deg=200,
            ),
            SimEmitter(
                id="SIM-UAS-C2",
                name="Small UAS command link",
                lat=55.80,
                lon=-0.90,
                freq_hz=2.44 * GHZ,
                bandwidth_hz=20 * MHZ,
                eirp_dbm=38,
                speed_mps=20,
                heading_deg=90,
                alt_m=120,
            ),
            SimEmitter(
                id="SIM-UAS-VID",
                name="Small UAS video downlink",
                lat=55.80,
                lon=-0.90,
                freq_hz=5.80 * GHZ,
                bandwidth_hz=20 * MHZ,
                eirp_dbm=36,
                speed_mps=20,
                heading_deg=90,
                alt_m=120,
            ),
        ],
    )

    quiet = Scenario(
        name="quiet_range",
        title="Quiet range",
        description="Training scenario: two benign emitters and a slow ship transit.",
        route=Route(
            waypoints=[(55.60, -0.60), (55.80, -0.60), (55.80, -1.00), (55.60, -1.00)],
            speed_mps=180 * KT,
            alt_m=2500,
        ),
        emitters=[
            SimEmitter(
                id="SIM-ASR",
                name="Coastal air surveillance radar",
                lat=55.35,
                lon=-1.55,
                freq_hz=2.95 * GHZ,
                bandwidth_hz=2 * MHZ,
                eirp_dbm=95,
                pulsed=True,
                pri_us=1100,
                pw_us=8,
                scan_period_s=12,
            ),
            SimEmitter(
                id="SIM-NAV",
                name="Fishing vessel navigation radar",
                lat=55.70,
                lon=-0.80,
                freq_hz=9.44 * GHZ,
                bandwidth_hz=10 * MHZ,
                eirp_dbm=72,
                pulsed=True,
                pri_us=800,
                pw_us=0.25,
                scan_period_s=3,
                speed_mps=4,
                heading_deg=20,
            ),
        ],
    )
    return {littoral.name: littoral, quiet.name: quiet}


class RfEnvironment:
    """Propagates the scenario and synthesises receiver output each tick."""

    def __init__(self, scenario: Scenario, seed: int | None = None) -> None:
        self.scenario = scenario
        self.rng = np.random.default_rng(seed)
        self.t = 0.0
        self.bearing_sigma_deg = 2.0

    # ------------------------------------------------------------------ state
    def step(self, dt: float) -> None:
        self.t += dt
        self.scenario.route.step(dt)
        for e in self.scenario.emitters:
            e.step(dt)

    def ownship(self) -> Ownship:
        lat, lon, hdg = self.scenario.route.position_heading()
        return Ownship(
            position=Position(lat=lat, lon=lon, alt_m=self.scenario.route.alt_m),
            heading_deg=hdg,
            speed_mps=self.scenario.route.speed_mps,
        )

    # --------------------------------------------------------------- receiver
    def acquire(
        self, rx: ReceiverConfig, wall_time: float
    ) -> tuple[SpectrumFrame, list[PulseDescriptor]]:
        own = self.ownship()
        n = rx.n_bins
        bin_w = rx.bin_width_hz
        freqs = rx.start_hz + (np.arange(n) + 0.5) * bin_w

        noise_db = self.rng.normal(self.scenario.noise_floor_dbm, 1.5, n)
        power_lin = 10 ** (noise_db / 10)
        descriptors: list[PulseDescriptor] = []

        for e in self.scenario.emitters:
            if not e.transmitting(self.t):
                continue
            dist = geo.distance_m(own.position.lat, own.position.lon, e.lat, e.lon)
            dist = math.hypot(dist, own.position.alt_m - e.alt_m)
            brg_to_rx = geo.bearing_deg(e.lat, e.lon, own.position.lat, own.position.lon)
            rx_dbm = (
                e.eirp_dbm
                - free_space_path_loss_db(dist, e.freq_hz)
                + e.antenna_gain_db(self.t, brg_to_rx)
                + self.rng.normal(0, 0.8)
            )

            if rx.start_hz <= e.freq_hz <= rx.stop_hz:
                sigma_hz = max(e.bandwidth_hz / 2.355, bin_w * 0.6)
                lo = int(max(0, (e.freq_hz - 3 * sigma_hz - rx.start_hz) // bin_w))
                hi = int(min(n, (e.freq_hz + 3 * sigma_hz - rx.start_hz) // bin_w + 2))
                if hi > lo:
                    seg = freqs[lo:hi]
                    lobe = np.exp(-0.5 * ((seg - e.freq_hz) / sigma_hz) ** 2)
                    power_lin[lo:hi] += 10 ** (rx_dbm / 10) * lobe

            # The DF / PDW channel only reports signals it can actually see.
            if rx_dbm > self.scenario.noise_floor_dbm + 6:
                true_brg = geo.bearing_deg(own.position.lat, own.position.lon, e.lat, e.lon)
                pulse = None
                if e.pulsed:
                    pulse = PulseParams(
                        pri_us=e.pri_us * (1 + self.rng.normal(0, 0.01)),
                        pw_us=e.pw_us * (1 + self.rng.normal(0, 0.03)),
                    )
                descriptors.append(
                    PulseDescriptor(
                        freq_hz=e.freq_hz,
                        bearing_deg=geo.wrap_deg(
                            true_brg + self.rng.normal(0, self.bearing_sigma_deg)
                        ),
                        power_dbm=rx_dbm,
                        pulse=pulse,
                    )
                )

        power_db = 10 * np.log10(power_lin)
        frame = SpectrumFrame(
            time=wall_time,
            start_hz=rx.start_hz,
            stop_hz=rx.stop_hz,
            power_dbm=[round(float(v), 1) for v in power_db],
            noise_floor_dbm=float(np.median(power_db)),
        )
        return frame, descriptors
