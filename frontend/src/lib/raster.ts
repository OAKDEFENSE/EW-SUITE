export type Rgba = [number, number, number, number];

function lerp(a: number, b: number, f: number): number {
  return a + (b - a) * f;
}

function ramp(stops: [number, Rgba][], t: number): Rgba {
  const x = Math.min(1, Math.max(0, t));
  for (let i = 1; i < stops.length; i++) {
    const [t0, c0] = stops[i - 1];
    const [t1, c1] = stops[i];
    if (x <= t1) {
      const f = t1 === t0 ? 0 : (x - t0) / (t1 - t0);
      return [
        Math.round(lerp(c0[0], c1[0], f)),
        Math.round(lerp(c0[1], c1[1], f)),
        Math.round(lerp(c0[2], c1[2], f)),
        Math.round(lerp(c0[3], c1[3], f)),
      ];
    }
  }
  return stops[stops.length - 1][1];
}

/** Span of received power above the detection threshold that the coverage ramp covers. */
export const COVERAGE_SPAN_DB = 50;

/**
 * Received power to colour. Cells below the threshold are transparent; above it the ramp
 * runs weak (blue) through cyan and yellow to strong (red) over COVERAGE_SPAN_DB.
 */
export function coverageColor(powerDbm: number, thresholdDbm: number): Rgba {
  if (!Number.isFinite(powerDbm) || powerDbm < thresholdDbm) return [0, 0, 0, 0];
  const t = (powerDbm - thresholdDbm) / COVERAGE_SPAN_DB;
  return ramp(
    [
      [0, [40, 90, 220, 120]],
      [0.33, [40, 200, 220, 150]],
      [0.66, [245, 220, 70, 170]],
      [1, [255, 60, 40, 190]],
    ],
    t,
  );
}

/** Hypsometric tint for land; sea (<= 0 m) is transparent. */
export function terrainColor(elevationM: number): Rgba {
  if (!Number.isFinite(elevationM) || elevationM <= 0) return [0, 0, 0, 0];
  const t = elevationM / 900;
  return ramp(
    [
      [0, [60, 110, 70, 140]],
      [0.25, [120, 150, 80, 150]],
      [0.5, [160, 130, 80, 160]],
      [0.8, [130, 110, 100, 170]],
      [1, [235, 235, 235, 180]],
    ],
    t,
  );
}

/** Flatten a row-major grid (rows north to south) into RGBA bytes for an image. */
export function gridToRgba(grid: number[][], color: (v: number) => Rgba): Uint8ClampedArray {
  const rows = grid.length;
  const cols = rows ? grid[0].length : 0;
  const out = new Uint8ClampedArray(rows * cols * 4);
  let k = 0;
  for (let r = 0; r < rows; r++) {
    const row = grid[r];
    for (let c = 0; c < cols; c++) {
      const [cr, cg, cb, ca] = color(row[c]);
      out[k++] = cr;
      out[k++] = cg;
      out[k++] = cb;
      out[k++] = ca;
    }
  }
  return out;
}

/** Render a grid to a PNG data URL via a canvas. Browser only. */
export function gridToDataUrl(grid: number[][], color: (v: number) => Rgba): string {
  const rows = grid.length;
  const cols = rows ? grid[0].length : 0;
  const canvas = document.createElement("canvas");
  canvas.width = cols;
  canvas.height = rows;
  const ctx = canvas.getContext("2d");
  if (!ctx || !rows) return "";
  const img = ctx.createImageData(cols, rows);
  img.data.set(gridToRgba(grid, color));
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL("image/png");
}
