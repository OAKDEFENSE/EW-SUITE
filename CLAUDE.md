# EW Suite – guidance for Claude Code

## What this is
Electronic warfare operator console: `backend/` (Python 3.11, FastAPI, numpy) runs an ESM
pipeline (simulated receiver → detector → tracker/geolocation/classifier → alerts → REST+WS);
`frontend/` (Vite, React 19, TypeScript, Leaflet) is the console. See README.md for layout.

## Commands
- Backend: `cd backend && uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check .`
- Backend dev server: `uv run python -m ew_core` (port 8000, `/docs` for OpenAPI)
- Frontend: `cd frontend && npm install && npm run typecheck && npm test && npm run build`
- Frontend dev server: `npm run dev` (port 5173, proxies `/api` and `/ws` to 8000)

## Conventions
- `backend/ew_core/models.py` and `frontend/src/lib/types.ts` mirror each other. Change both.
- Keep the pipeline hardware-agnostic: anything that talks to a receiver lives behind the
  `acquire(receiver, time) -> (SpectrumFrame, list[PulseDescriptor])` contract in
  `simulation.py`. Detector, tracker, classifier and API must not know about the simulation.
- Propagation lives in `propagation.py` on top of a `Terrain` from `terrain.py`; both are
  vectorised over numpy arrays so coverage grids are computed in one call. Emitter `alt_m`
  in scenarios is height above ground; ownship altitude is MSL.
- Blue-force link budgets live in `links.py`; interference comes only from geolocated
  tracks with an EIRP estimate (never from simulation truth), so the console reflects what
  the ESM picture actually knows.
- Signal library entries are notional and unclassified. Do not add real system parameters.
- Pure logic (geo, detector, tracker, classifier, store reducer, formatters) gets unit tests.
  UI components are exercised via typecheck and build only.
- Ruff (line length 100) for Python; TypeScript strict mode for the frontend.
- Frequencies are stored in Hz as floats, times as epoch seconds, bearings as true degrees
  0–360, positions as WGS-84 lat/lon.
