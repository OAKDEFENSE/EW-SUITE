import L from "leaflet";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { destination } from "../lib/geo";
import { formatBearing, formatDistance, formatFreq } from "../lib/format";
import { coverageColor, gridToDataUrl, terrainColor } from "../lib/raster";
import type { CoverageGrid, EmitterTrack, GridBounds, Ownship, TerrainGrid } from "../lib/types";
import { THREAT_COLOR } from "./SpectrumPanel";

export type RxAltitudeOption = "ownship" | "agl50" | "agl500";

export const RX_ALTITUDE_LABEL: Record<RxAltitudeOption, string> = {
  ownship: "at ownship altitude",
  agl50: "50 m AGL",
  agl500: "500 m AGL",
};

interface Props {
  ownship: Ownship | null;
  tracks: EmitterTrack[];
  selectedTrackId: string | null;
  onSelect: (id: string | null) => void;
  coverage: CoverageGrid | null;
  coverageEnabled: boolean;
  coverageAvailable: boolean;
  coverageBusy: boolean;
  onToggleCoverage: () => void;
  rxAltitude: RxAltitudeOption;
  onRxAltitude: (o: RxAltitudeOption) => void;
}

function toLeafletBounds(b: GridBounds): L.LatLngBoundsExpression {
  return [
    [b.south, b.west],
    [b.north, b.east],
  ];
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

export function TacticalMap({
  ownship,
  tracks,
  selectedTrackId,
  onSelect,
  coverage,
  coverageEnabled,
  coverageAvailable,
  coverageBusy,
  onToggleCoverage,
  rxAltitude,
  onRxAltitude,
}: Props) {
  const divRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const terrainLayer = useRef<L.ImageOverlay | null>(null);
  const coverageLayer = useRef<L.ImageOverlay | null>(null);
  const [showTerrain, setShowTerrain] = useState(false);
  const [terrainGrid, setTerrainGrid] = useState<TerrainGrid | null>(null);
  const [terrainError, setTerrainError] = useState<string | null>(null);
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

  // Terrain raster: fetched for the visible bounds, refreshed when the view settles.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !showTerrain) {
      if (terrainLayer.current && map) map.removeLayer(terrainLayer.current);
      terrainLayer.current = null;
      setTerrainGrid(null);
      return;
    }
    let cancelled = false;
    let timer: number | null = null;
    const fetchGrid = () => {
      const b = map.getBounds().pad(0.2);
      api
        .terrainGrid(
          { south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast() },
          140,
        )
        .then((g) => {
          if (!cancelled) {
            setTerrainGrid(g);
            setTerrainError(null);
          }
        })
        .catch((e) => !cancelled && setTerrainError(String(e)));
    };
    const onMove = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = window.setTimeout(fetchGrid, 400);
    };
    fetchGrid();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [showTerrain]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (terrainLayer.current) {
      map.removeLayer(terrainLayer.current);
      terrainLayer.current = null;
    }
    if (!terrainGrid) return;
    const url = gridToDataUrl(terrainGrid.elevation_m, terrainColor);
    if (!url) return;
    terrainLayer.current = L.imageOverlay(url, toLeafletBounds(terrainGrid.bounds), {
      opacity: 1,
      interactive: false,
      className: "terrain-overlay",
    }).addTo(map);
    terrainLayer.current.bringToBack();
  }, [terrainGrid]);

  // Coverage raster for the selected emitter.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (coverageLayer.current) {
      map.removeLayer(coverageLayer.current);
      coverageLayer.current = null;
    }
    if (!coverage || !coverageEnabled) return;
    const url = gridToDataUrl(coverage.power_dbm, (v) => coverageColor(v, coverage.threshold_dbm));
    if (!url) return;
    coverageLayer.current = L.imageOverlay(url, toLeafletBounds(coverage.bounds), {
      opacity: 0.85,
      interactive: false,
      className: "coverage-overlay",
    }).addTo(map);
  }, [coverage, coverageEnabled]);

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
        <div className="map-controls">
          <button
            type="button"
            className={showTerrain ? "active" : ""}
            onClick={() => setShowTerrain((v) => !v)}
            title="Shade terrain elevation"
          >
            Terrain
          </button>
          <button
            type="button"
            className={coverageEnabled ? "active" : ""}
            disabled={!coverageAvailable && !coverageEnabled}
            onClick={onToggleCoverage}
            title={
              coverageAvailable
                ? "Where the selected emitter is detectable"
                : "Select a geolocated track to show its coverage"
            }
          >
            {coverageBusy ? "Coverage…" : "Coverage"}
          </button>
          <select
            value={rxAltitude}
            onChange={(e) => onRxAltitude(e.target.value as RxAltitudeOption)}
            disabled={!coverageEnabled}
            title="Receiver altitude for the coverage map"
          >
            {(Object.keys(RX_ALTITUDE_LABEL) as RxAltitudeOption[]).map((k) => (
              <option key={k} value={k}>
                {RX_ALTITUDE_LABEL[k]}
              </option>
            ))}
          </select>
        </div>
        <span className="legend">
          <i style={{ background: THREAT_COLOR.high }} /> high <i style={{ background: THREAT_COLOR.medium }} /> medium{" "}
          <i style={{ background: THREAT_COLOR.low }} /> low <i style={{ background: THREAT_COLOR.none }} /> benign
        </span>
      </div>
      <div className="map-wrap">
        <div ref={divRef} className="map" />
        {coverageEnabled && coverage && (
          <div className="coverage-legend">
            <div className="coverage-ramp" />
            <div className="coverage-ticks">
              <span>{coverage.threshold_dbm.toFixed(0)} dBm</span>
              <span>+25</span>
              <span>+50</span>
            </div>
            <div className="dim small">
              {formatFreq(coverage.freq_hz)} · EIRP {coverage.eirp_dbm.toFixed(0)} dBm · rx{" "}
              {coverage.rx_alt_ref === "msl" ? `${coverage.rx_alt_m.toFixed(0)} m MSL` : `${coverage.rx_alt_m.toFixed(0)} m AGL`}
              {" · "}
              {(coverage.covered_fraction * 100).toFixed(0)}% of area
            </div>
          </div>
        )}
        {terrainError && <div className="map-error">{terrainError}</div>}
      </div>
    </div>
  );
}
