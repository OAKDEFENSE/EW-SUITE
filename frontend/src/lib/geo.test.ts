import { describe, expect, it } from "vitest";
import { bearingDeg, destination, distanceM } from "./geo";

describe("geo", () => {
  it("destination round-trips through distance and bearing", () => {
    const [lat, lon] = destination(55.5, -1.0, 45, 20_000);
    expect(distanceM(55.5, -1.0, lat, lon)).toBeCloseTo(20_000, -1);
    expect(bearingDeg(55.5, -1.0, lat, lon)).toBeCloseTo(45, 0);
  });
  it("bearing due north is 0 and due east is 90", () => {
    expect(bearingDeg(55, -1, 56, -1)).toBeCloseTo(0, 5);
    expect(bearingDeg(0, 0, 0, 1)).toBeCloseTo(90, 5);
  });
});
