"""Energy detection on spectrum frames, plus fusion with DF / PDW measurements."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .models import Detection, SpectrumFrame
from .simulation import PulseDescriptor


def detect(frame: SpectrumFrame, threshold_db: float = 10.0) -> list[Detection]:
    """Find contiguous runs of bins above the noise floor plus ``threshold_db``."""
    p = np.asarray(frame.power_dbm, dtype=float)
    if p.size == 0:
        return []
    floor = float(np.median(p))
    thr = floor + threshold_db
    above = p > thr
    if not above.any():
        return []

    bin_w = frame.bin_width_hz
    # Edges of True runs.
    padded = np.concatenate(([False], above, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    starts, stops = edges[0::2], edges[1::2]

    detections: list[Detection] = []
    for s, e in zip(starts, stops, strict=True):
        seg = p[s:e]
        lin = 10 ** (seg / 10)
        idx = np.arange(s, e)
        centroid = float((idx * lin).sum() / lin.sum())
        freq = frame.start_hz + (centroid + 0.5) * bin_w
        peak = float(seg.max())
        # Occupied bandwidth as the -6 dB width, which is far less sensitive to signal
        # strength than the above-threshold width; resolution is still one bin.
        width_bins = int((seg >= peak - 6.0).sum())
        detections.append(
            Detection(
                freq_hz=freq,
                bandwidth_hz=float(max(width_bins, 1) * bin_w),
                power_dbm=peak,
            )
        )
    return detections


def fuse_descriptors(
    detections: list[Detection],
    descriptors: Sequence[PulseDescriptor],
    bin_width_hz: float,
) -> list[Detection]:
    """Attach bearing and pulse data from the PDW channel to spectral detections.

    A descriptor is matched to the detection whose centre frequency is closest, provided
    it falls within the detection's bandwidth or 1.5 bins, whichever is larger.
    """
    if not detections or not descriptors:
        return detections
    used: set[int] = set()
    for d in descriptors:
        best_i, best_df = -1, float("inf")
        for i, det in enumerate(detections):
            if i in used:
                continue
            df = abs(det.freq_hz - d.freq_hz)
            tol = max(det.bandwidth_hz, 1.5 * bin_width_hz)
            if df <= tol and df < best_df:
                best_i, best_df = i, df
        if best_i >= 0:
            det = detections[best_i]
            detections[best_i] = det.model_copy(
                update={"bearing_deg": d.bearing_deg, "pulse": d.pulse}
            )
            used.add(best_i)
    return detections
