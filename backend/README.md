# ew-core

Backend service for the EW Suite. Simulates an ESM receiver (wideband spectrum plus
DF / pulse-descriptor channel), detects and tracks emitters, geolocates them from
ownship motion, classifies them against a notional signal library and streams the
result over a WebSocket.

```bash
uv sync
uv run python -m ew_core          # http://localhost:8000/docs
uv run pytest
uv run ruff check .
```

Environment variables: `EW_SCENARIO` (default `littoral_patrol`), `EW_TICK_HZ` (5),
`EW_SEED`, `EW_PORT` (8000), `EW_CORS_ORIGINS`, `EW_TERRAIN` (`synthetic`, `flat` or
`hgt:/path/to/tiles`).
