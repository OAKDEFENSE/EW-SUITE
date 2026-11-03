import { describe, expect, it } from "vitest";
import { formatAge, formatBearing, formatFreq, formatLatLon, formatUtc } from "./format";

describe("format", () => {
  it("formats frequencies by magnitude", () => {
    expect(formatFreq(9.02e9)).toBe("9.020 GHz");
    expect(formatFreq(156.8e6)).toBe("156.80 MHz");
    expect(formatFreq(25e3)).toBe("25.0 kHz");
  });
  it("pads bearings to three digits and wraps", () => {
    expect(formatBearing(5)).toBe("005°");
    expect(formatBearing(-10)).toBe("350°");
    expect(formatBearing(null)).toBe("—");
  });
  it("formats UTC time", () => {
    expect(formatUtc(0)).toBe("00:00:00Z");
    expect(formatUtc(3661)).toBe("01:01:01Z");
  });
  it("formats ages", () => {
    expect(formatAge(42)).toBe("42s");
    expect(formatAge(125)).toBe("2m05s");
  });
  it("formats lat/lon with hemispheres", () => {
    expect(formatLatLon(55.5, -1.25)).toBe("55.5000°N 1.2500°W");
  });
});
