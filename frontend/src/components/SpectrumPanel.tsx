import { useCallback, useEffect, useRef, useState } from "react";
import { formatFreq } from "../lib/format";
import type { EmitterTrack, ReceiverConfig, SpectrumFrame, ThreatLevel } from "../lib/types";

interface Props {
  spectrum: SpectrumFrame | null;
  receiver: ReceiverConfig | null;
  tracks: EmitterTrack[];
  selectedTrackId: string | null;
  onSelect: (id: string | null) => void;
  onRetune: (update: Partial<ReceiverConfig>) => void;
}

const DB_MIN = -112;
const DB_MAX = -30;
const TRACE_H = 150;
const WATERFALL_H = 220;

export const THREAT_COLOR: Record<ThreatLevel, string> = {
  none: "#6b7f8e",
  low: "#4fb286",
  medium: "#e0b84d",
  high: "#f06449",
  critical: "#ff2d55",
};

const PRESETS: { label: string; start: number; stop: number }[] = [
  { label: "Full", start: 30e6, stop: 18e9 },
  { label: "VHF/UHF", start: 30e6, stop: 1e9 },
  { label: "L/S", start: 1e9, stop: 4e9 },
  { label: "C", start: 4e9, stop: 8e9 },
  { label: "X", start: 8e9, stop: 12e9 },
  { label: "Ku", start: 12e9, stop: 18e9 },
];

function colorFor(db: number): [number, number, number] {
  const t = Math.min(1, Math.max(0, (db - DB_MIN) / (DB_MAX - DB_MIN)));
  // black -> deep blue -> cyan -> yellow -> red
  const stops: [number, [number, number, number]][] = [
    [0, [6, 10, 20]],
    [0.25, [20, 60, 140]],
    [0.5, [30, 190, 200]],
    [0.75, [245, 220, 70]],
    [1, [255, 60, 40]],
  ];
  for (let i = 1; i < stops.length; i++) {
    const [t0, c0] = stops[i - 1];
    const [t1, c1] = stops[i];
    if (t <= t1) {
      const f = (t - t0) / (t1 - t0);
      return [
        Math.round(c0[0] + (c1[0] - c0[0]) * f),
        Math.round(c0[1] + (c1[1] - c0[1]) * f),
        Math.round(c0[2] + (c1[2] - c0[2]) * f),
      ];
    }
  }
  return stops[stops.length - 1][1];
}

function niceTicks(start: number, stop: number, target = 8): number[] {
  const span = stop - start;
  const raw = span / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= target) ?? mag * 10;
  const ticks: number[] = [];
  for (let f = Math.ceil(start / step) * step; f <= stop; f += step) ticks.push(f);
  return ticks;
}

export function SpectrumPanel({ spectrum, receiver, tracks, selectedTrackId, onSelect, onRetune }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const traceRef = useRef<HTMLCanvasElement>(null);
  const wfRef = useRef<HTMLCanvasElement>(null);
  const wfBuffer = useRef<HTMLCanvasElement | null>(null);
  const wfBins = useRef(0);
  const [width, setWidth] = useState(800);
  const [startMhz, setStartMhz] = useState("");
  const [stopMhz, setStopMhz] = useState("");
  const [threshold, setThreshold] = useState("");

  useEffect(() => {
    if (!receiver) return;
    setStartMhz((receiver.start_hz / 1e6).toFixed(0));
    setStopMhz((receiver.stop_hz / 1e6).toFixed(0));
    setThreshold(receiver.detection_threshold_db.toFixed(0));
  }, [receiver?.start_hz, receiver?.stop_hz, receiver?.detection_threshold_db]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(200, Math.floor(entry.contentRect.width))));
    ro.observe(el);
    setWidth(Math.max(200, Math.floor(el.clientWidth)));
    return () => ro.disconnect();
  }, []);

  // Trace + markers
  useEffect(() => {
    const canvas = traceRef.current;
    if (!canvas || !spectrum) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = TRACE_H * dpr;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    const W = width;
    const H = TRACE_H;
    ctx.fillStyle = "#0b1017";
    ctx.fillRect(0, 0, W, H);

    const yFor = (db: number) => H - ((db - DB_MIN) / (DB_MAX - DB_MIN)) * (H - 18) - 2;
    ctx.strokeStyle = "#1c2733";
    ctx.fillStyle = "#5c6b7a";
    ctx.font = "10px ui-monospace, monospace";
    ctx.lineWidth = 1;
    for (let db = -100; db <= -40; db += 20) {
      const y = Math.round(yFor(db)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
      ctx.stroke();
      ctx.fillText(`${db}`, 4, y - 2);
    }

    const n = spectrum.power_dbm.length;
    if (n > 0) {
      // Threshold line
      if (receiver) {
        const y = Math.round(yFor(spectrum.noise_floor_dbm + receiver.detection_threshold_db)) + 0.5;
        ctx.strokeStyle = "rgba(240,100,73,0.45)";
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(W, y);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      ctx.beginPath();
      ctx.moveTo(0, H);
      for (let i = 0; i < n; i++) {
        const x = (i / (n - 1)) * W;
        ctx.lineTo(x, yFor(spectrum.power_dbm[i]));
      }
      ctx.lineTo(W, H);
      ctx.closePath();
      const grad = ctx.createLinearGradient(0, 0, 0, H);
      grad.addColorStop(0, "rgba(60,200,230,0.55)");
      grad.addColorStop(1, "rgba(60,200,230,0.05)");
      ctx.fillStyle = grad;
      ctx.fill();
      ctx.strokeStyle = "#5ad1e6";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const x = (i / (n - 1)) * W;
        const y = yFor(spectrum.power_dbm[i]);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    // Frequency ticks
    const span = spectrum.stop_hz - spectrum.start_hz;
    ctx.fillStyle = "#8a9aab";
    ctx.strokeStyle = "#2a3744";
    for (const f of niceTicks(spectrum.start_hz, spectrum.stop_hz)) {
      const x = Math.round(((f - spectrum.start_hz) / span) * W) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, H - 14);
      ctx.lineTo(x, H);
      ctx.stroke();
      const label = formatFreq(f, f >= 1e9 ? 1 : 0);
      ctx.fillText(label, Math.min(W - 44, x + 3), H - 4);
    }

    // Track markers
    for (const t of tracks) {
      if (t.freq_hz < spectrum.start_hz || t.freq_hz > spectrum.stop_hz) continue;
      const x = ((t.freq_hz - spectrum.start_hz) / span) * W;
      const color = THREAT_COLOR[t.classification.threat];
      const sel = t.id === selectedTrackId;
      ctx.globalAlpha = t.status === "lost" ? 0.35 : 1;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(x, 10);
      ctx.lineTo(x - 5, 2);
      ctx.lineTo(x + 5, 2);
      ctx.closePath();
      ctx.fill();
      if (sel) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x + 0.5, 10);
        ctx.lineTo(x + 0.5, H - 16);
        ctx.stroke();
      }
      ctx.fillStyle = sel ? "#ffffff" : color;
      ctx.fillText(t.id, x + 6, 10);
      ctx.globalAlpha = 1;
    }
  }, [spectrum, tracks, selectedTrackId, width, receiver]);

  // Waterfall
  useEffect(() => {
    const canvas = wfRef.current;
    if (!canvas || !spectrum) return;
    const n = spectrum.power_dbm.length;
    if (n === 0) return;
    if (!wfBuffer.current || wfBins.current !== n) {
      const buf = document.createElement("canvas");
      buf.width = n;
      buf.height = WATERFALL_H;
      wfBuffer.current = buf;
      wfBins.current = n;
    }
    const buf = wfBuffer.current;
    const bctx = buf.getContext("2d");
    if (!bctx) return;
    bctx.drawImage(buf, 0, 0, n, WATERFALL_H - 1, 0, 1, n, WATERFALL_H - 1);
    const row = bctx.createImageData(n, 1);
    for (let i = 0; i < n; i++) {
      const [r, g, b] = colorFor(spectrum.power_dbm[i]);
      row.data[i * 4] = r;
      row.data[i * 4 + 1] = g;
      row.data[i * 4 + 2] = b;
      row.data[i * 4 + 3] = 255;
    }
    bctx.putImageData(row, 0, 0);

    canvas.width = width;
    canvas.height = WATERFALL_H;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(buf, 0, 0, n, WATERFALL_H, 0, 0, width, WATERFALL_H);
  }, [spectrum, width]);

  // Reset the waterfall when the band changes.
  useEffect(() => {
    wfBuffer.current = null;
  }, [spectrum?.start_hz, spectrum?.stop_hz]);

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!spectrum) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const span = spectrum.stop_hz - spectrum.start_hz;
      let best: EmitterTrack | null = null;
      let bestDx = 10;
      for (const t of tracks) {
        const tx = ((t.freq_hz - spectrum.start_hz) / span) * rect.width;
        const dx = Math.abs(tx - x);
        if (dx < bestDx) {
          best = t;
          bestDx = dx;
        }
      }
      onSelect(best ? best.id : null);
    },
    [spectrum, tracks, onSelect],
  );

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const start = Number(startMhz) * 1e6;
    const stop = Number(stopMhz) * 1e6;
    const thr = Number(threshold);
    if (!Number.isFinite(start) || !Number.isFinite(stop) || stop <= start) return;
    onRetune({ start_hz: start, stop_hz: stop, detection_threshold_db: thr });
  };

  return (
    <div className="spectrum" ref={wrapRef}>
      <div className="panel-head">
        <h2>Spectrum</h2>
        <form className="retune" onSubmit={submit}>
          {PRESETS.map((p) => (
            <button
              type="button"
              key={p.label}
              className={receiver && receiver.start_hz === p.start && receiver.stop_hz === p.stop ? "active" : ""}
              onClick={() => onRetune({ start_hz: p.start, stop_hz: p.stop })}
            >
              {p.label}
            </button>
          ))}
          <label>
            <input value={startMhz} onChange={(e) => setStartMhz(e.target.value)} size={6} inputMode="decimal" /> –
            <input value={stopMhz} onChange={(e) => setStopMhz(e.target.value)} size={6} inputMode="decimal" /> MHz
          </label>
          <label>
            thr <input value={threshold} onChange={(e) => setThreshold(e.target.value)} size={2} inputMode="decimal" /> dB
          </label>
          <button type="submit">Tune</button>
        </form>
      </div>
      <canvas
        ref={traceRef}
        className="trace"
        style={{ width, height: TRACE_H }}
        onClick={handleClick}
        role="img"
        aria-label="Spectrum trace"
      />
      <canvas
        ref={wfRef}
        className="waterfall"
        style={{ width, height: WATERFALL_H }}
        onClick={handleClick}
        role="img"
        aria-label="Spectrum waterfall"
      />
    </div>
  );
}
