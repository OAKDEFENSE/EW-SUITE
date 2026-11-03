import L from "leaflet";
import { useEffect, useRef } from "react";
import { destination } from "../lib/geo";
import { formatBearing, formatDistance, formatFreq } from "../lib/format";
import type { EmitterTrack, Ownship } from "../lib/types";
import { THREAT_COLOR } from "./SpectrumPanel";

interface Props {
  ownship: Ownship | null;
  tracks: EmitterTrack[];
  selectedTrackId: string | null;
  onSelect: (id: string | null) => void;
}

const BEARING_LINE_M = 150_000;
const TRAIL_LEN = 600;

interface TrackLayers {
  line: L.Polyline;
  fix: L.CircleMarker;
  ellipse: L.Circle;
}

const TILE_URL = import.meta.env.VITE_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTR = import.meta.env.VITE_TILE_ATTRIBUTION ?? "&copy; OpenStreetMap contributors";

export function TacticalMap({ ownship, tracks, selectedTrackId, onSelect }: Props) {
  const divRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const ownRef = useRef<L.Marker | null>(null);
  const trailRef = useRef<L.Polyline | null>(null);
  const trailPts = useRef<L.LatLngExpression[]>([]);
  const layersRef = useRef<Map<string, TrackLayers>>(new Map());
  const centred = useRef(false);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!divRef.current || mapRef.current) return;
    const map = L.map(divRef.current, {
      center: [55.7, -0.8],
      zoom: 8,
      zoomControl: true,
      attributionControl: true,
    });
    L.tileLayer(TILE_URL, { attribution: TILE_ATTR, maxZoom: 18, className: "tiles" }).addTo(map);
    L.control.scale({ imperial: false }).addTo(map);
    map.on("click", () => onSelectRef.current(null));
    trailRef.current = L.polyline([], { color: "#9ad7ff", weight: 1.5, opacity: 0.6 }).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Ownship
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ownship) return;
    const pos: L.LatLngExpression = [ownship.position.lat, ownship.position.lon];
    const icon = L.divIcon({
      className: "ownship-icon",
      html: `<div class="ownship" style="transform: rotate(${ownship.heading_deg}deg)">▲</div>`,
      iconSize: [24, 24],
      iconAnchor: [12, 12],
    });
    if (!ownRef.current) {
      ownRef.current = L.marker(pos, { icon, zIndexOffset: 1000, interactive: false }).addTo(map);
    } else {
      ownRef.current.setLatLng(pos);
      ownRef.current.setIcon(icon);
    }
    trailPts.current.push(pos);
    if (trailPts.current.length > TRAIL_LEN) trailPts.current.shift();
    trailRef.current?.setLatLngs(trailPts.current);
    if (!centred.current) {
      map.setView(pos, 8);
      centred.current = true;
    }
  }, [ownship]);

  // Tracks
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ownship) return;
    const live = new Set<string>();
    for (const t of tracks) {
      live.add(t.id);
      const color = THREAT_COLOR[t.classification.threat];
      const sel = t.id === selectedTrackId;
      const lost = t.status === "lost";
      let layers = layersRef.current.get(t.id);
      if (!layers) {
        const line = L.polyline([], { color, weight: 1.5, opacity: 0.8, dashArray: "6 6" });
        const fix = L.circleMarker([0, 0], { radius: 6, color, fillColor: color, fillOpacity: 0.9, weight: 1.5 });
        const ellipse = L.circle([0, 0], { radius: 1000, color, weight: 1, fillOpacity: 0.08, interactive: false });
        for (const l of [line, fix]) {
          l.on("click", (e) => {
            L.DomEvent.stopPropagation(e);
            onSelectRef.current(t.id);
          });
        }
        layers = { line, fix, ellipse };
        layersRef.current.set(t.id, layers);
      }
      const tip = `<b>${t.id}</b> ${t.classification.name}<br/>${formatFreq(t.freq_hz)} · brg ${formatBearing(t.bearing_deg)}` +
        (t.geo ? `<br/>fix ±${formatDistance(t.geo.error_radius_m)}` : "");

      if (t.bearing_deg !== null && !lost) {
        const far = destination(ownship.position.lat, ownship.position.lon, t.bearing_deg, BEARING_LINE_M);
        layers.line.setLatLngs([[ownship.position.lat, ownship.position.lon], far]);
        layers.line.setStyle({ color, weight: sel ? 3 : 1.5, opacity: sel ? 1 : 0.7 });
        layers.line.bindTooltip(tip, { sticky: true });
        if (!map.hasLayer(layers.line)) layers.line.addTo(map);
      } else if (map.hasLayer(layers.line)) {
        map.removeLayer(layers.line);
      }

      if (t.geo) {
        const p: L.LatLngExpression = [t.geo.position.lat, t.geo.position.lon];
        layers.fix.setLatLng(p);
        layers.fix.setStyle({ color: sel ? "#ffffff" : color, fillColor: color, radius: sel ? 8 : 6, opacity: lost ? 0.4 : 1, fillOpacity: lost ? 0.3 : 0.9 });
        layers.fix.bindTooltip(tip, { direction: "top" });
        layers.ellipse.setLatLng(p);
        layers.ellipse.setRadius(t.geo.error_radius_m);
        layers.ellipse.setStyle({ color, opacity: lost ? 0.2 : 0.6 });
        if (!map.hasLayer(layers.ellipse)) layers.ellipse.addTo(map);
        if (!map.hasLayer(layers.fix)) layers.fix.addTo(map);
      } else {
        if (map.hasLayer(layers.fix)) map.removeLayer(layers.fix);
        if (map.hasLayer(layers.ellipse)) map.removeLayer(layers.ellipse);
      }
    }
    for (const [id, layers] of layersRef.current) {
      if (live.has(id)) continue;
      map.removeLayer(layers.line);
      map.removeLayer(layers.fix);
      map.removeLayer(layers.ellipse);
      layersRef.current.delete(id);
    }
  }, [tracks, ownship, selectedTrackId]);

  return (
    <div className="tactical-map">
      <div className="panel-head">
        <h2>Tactical picture</h2>
        <span className="legend">
          <i style={{ background: THREAT_COLOR.high }} /> high <i style={{ background: THREAT_COLOR.medium }} /> medium{" "}
          <i style={{ background: THREAT_COLOR.low }} /> low <i style={{ background: THREAT_COLOR.none }} /> benign
        </span>
      </div>
      <div ref={divRef} className="map" />
    </div>
  );
}
