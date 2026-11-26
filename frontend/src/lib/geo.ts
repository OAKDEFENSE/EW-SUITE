export const EARTH_RADIUS_M = 6_371_000;

const toRad = (d: number) => (d * Math.PI) / 180;
const toDeg = (r: number) => (r * 180) / Math.PI;

export function destination(
  lat: number,
  lon: number,
  bearingDeg: number,
  distanceM: number,
): [number, number] {
  const p1 = toRad(lat);
  const l1 = toRad(lon);
  const b = toRad(bearingDeg);
  const ad = distanceM / EARTH_RADIUS_M;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(ad) + Math.cos(p1) * Math.sin(ad) * Math.cos(b));
  const l2 =
    l1 +
    Math.atan2(
      Math.sin(b) * Math.sin(ad) * Math.cos(p1),
      Math.cos(ad) - Math.sin(p1) * Math.sin(p2),
    );
  return [toDeg(p2), ((toDeg(l2) + 540) % 360) - 180];
}

export function distanceM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const p1 = toRad(lat1);
  const p2 = toRad(lat2);
  const dp = p2 - p1;
  const dl = toRad(lon2 - lon1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a));
}

export function bearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const p1 = toRad(lat1);
  const p2 = toRad(lat2);
  const dl = toRad(lon2 - lon1);
  const x = Math.sin(dl) * Math.cos(p2);
  const y = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return (toDeg(Math.atan2(x, y)) + 360) % 360;
}
