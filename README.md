# EW Suite

Electronic warfare operator console. A wideband ESM picture built from a spectrum
receiver and a DF / pulse-descriptor channel: emitter detection, tracking,
bearing-only geolocation from ownship motion, signal-library classification and
threat alerting, presented on a spectrum display, track table and tactical map.

The first release runs against a built-in RF environment simulation so the whole
pipeline can be developed and demonstrated without hardware. The simulation sits
behind the same interface a receiver adapter will use (see
`backend/ew_core/simulation.py`), so swapping in real SDR / ESM hardware does not
touch the detector, tracker, classifier, API or console.

```
┌──────────────────────┐      ┌─────────────────────────────────────────┐
│  frontend/           │ WS   │  backend/ (FastAPI, Python 3.11)        │
│  React + TypeScript  │◄─────┤  RfEnvironment ─► detect ─► fuse PDWs   │
│  spectrum · tracks   │ REST │      ─► Tracker (assoc, geo, classify)  │
│  map · alerts        │─────►│      ─► alerts ─► /api, /ws/stream      │
└──────────────────────┘      └─────────────────────────────────────────┘
```

## Quick start

Backend (Python 3.11+, [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv sync
uv run python -m ew_core        # API on http://localhost:8000, docs at /docs
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev                     # console on http://localhost:5173 (proxies to :8000)
```

Or both with Docker:

```bash
docker compose up --build       # console on http://localhost:8080
```

## What you get

- **Spectrum panel**: live trace with detection threshold, scrolling waterfall,
  band presets (VHF/UHF, L/S, C, X, Ku, full 30 MHz–18 GHz) and manual retune.
  Track markers sit on their frequency; click one to select it.
- **Emitter track table**: ID, status (tentative / confirmed / lost), frequency,
  bandwidth, power, bearing, PRI, PW, identification, threat, confidence, fix quality.
  Sorted threat-first.
- **Tactical map**: ownship with trail, DF bearing lines coloured by threat,
  geolocation fixes with error circles.
- **Track detail**: smoothed parameters, PRF, library match notes, geolocation,
  range to fix.
- **Alerts**: new emitter, threat, geolocation fix, track lost, system. High threats
  also raise a banner.
- **Scenarios**: `littoral_patrol` (default, includes a fire control lock) and
  `quiet_range` (training). Switch from the status bar.

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/ew_core/models.py` | Pydantic models shared by the pipeline and API |
| `backend/ew_core/simulation.py` | Scenarios, emitters, ownship route, spectrum + PDW synthesis |
| `backend/ew_core/detector.py` | Energy detection and PDW fusion |
| `backend/ew_core/tracker.py` | Association, smoothing, aging, geolocation, reclassification |
| `backend/ew_core/classifier.py` / `library.py` | Signal-library matching (notional, unclassified entries) |
| `backend/ew_core/geo.py` | Geodesy and least-squares bearing triangulation |
| `backend/ew_core/engine.py` | Tick loop orchestration and alerting |
| `backend/ew_core/api.py` | REST + WebSocket service |
| `frontend/src/components/` | Console panels |
| `frontend/src/state/store.ts` | Console state reducer and track ordering |
| `frontend/src/lib/` | Types mirrored from the backend, formatting, geodesy, stream client |

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness, version, scenario, tick rate |
| GET | `/api/state` | Full engine state (receiver, ownship, spectrum, tracks, alerts) |
| GET | `/api/tracks`, `/api/tracks/{id}` | Emitter tracks |
| GET | `/api/alerts` | Last 200 alerts |
| GET | `/api/library` | Signal library |
| GET | `/api/scenarios`, POST `/api/scenarios/{name}/load` | Scenario catalogue and switch |
| GET / PUT | `/api/receiver` | Tuned band, bin count, detection threshold |
| WS | `/ws/stream` | `state` message every tick (5 Hz default) with `new_alerts` |

## Development

```bash
cd backend  && uv run ruff check . && uv run pytest
cd frontend && npm run typecheck && npm test && npm run build
```

CI runs the same on every push and pull request (`.github/workflows/ci.yml`).

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `EW_SCENARIO` | `littoral_patrol` | Scenario loaded at start |
| `EW_TICK_HZ` | `5` | Engine / stream rate |
| `EW_SEED` | unset | Fix the simulation RNG seed |
| `EW_PORT` | `8000` | Backend port |
| `EW_CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `VITE_TILE_URL` | OpenStreetMap | Map tile template; point at a local server for offline use |

## Roadmap

- Hardware receiver adapter (SoapySDR / vendor ESM API) implementing the
  `acquire()` contract.
- Multi-platform bearing fusion and TDOA geolocation.
- Persisted mission log and replay.
- Operator-editable signal library with import / export.
- Authentication and role separation for the console.
