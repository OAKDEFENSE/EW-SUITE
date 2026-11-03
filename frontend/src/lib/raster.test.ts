import { describe, expect, it } from "vitest";
import { COVERAGE_SPAN_DB, coverageColor, gridToRgba, terrainColor } from "./raster";

describe("coverageColor", () => {
  it("is transparent below the threshold and opaque above", () => {
    expect(coverageColor(-95, -90)[3]).toBe(0);
    expect(coverageColor(-90, -90)[3]).toBeGreaterThan(0);
    expect(coverageColor(Number.NaN, -90)[3]).toBe(0);
  });
  it("warms as power rises and clamps at the top of the span", () => {
    const weak = coverageColor(-89, -90);
    const strong = coverageColor(-90 + COVERAGE_SPAN_DB, -90);
    const beyond = coverageColor(0, -90);
    expect(weak[2]).toBeGreaterThan(weak[0]); // blue-ish
    expect(strong[0]).toBeGreaterThan(strong[2]); // red-ish
    expect(beyond).toEqual(strong);
  });
});

describe("terrainColor", () => {
  it("leaves sea transparent and tints land", () => {
    expect(terrainColor(0)[3]).toBe(0);
    expect(terrainColor(-5)[3]).toBe(0);
    expect(terrainColor(50)[3]).toBeGreaterThan(0);
    expect(terrainColor(2000)).toEqual(terrainColor(900));
  });
});

describe("gridToRgba", () => {
  it("lays out rows top-down and four bytes per cell", () => {
    const rgba = gridToRgba(
      [
        [1, 2],
        [3, 4],
      ],
      (v) => [v, 0, 0, 255],
    );
    expect(rgba.length).toBe(16);
    expect(Array.from(rgba.slice(0, 4))).toEqual([1, 0, 0, 255]);
    expect(Array.from(rgba.slice(12, 16))).toEqual([4, 0, 0, 255]);
  });
  it("handles an empty grid", () => {
    expect(gridToRgba([], () => [0, 0, 0, 0]).length).toBe(0);
  });
});
