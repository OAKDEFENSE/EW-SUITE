"""HTTP + WebSocket API for the EW console."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import __version__
from .engine import Engine
from .models import (
    Alert,
    BlueNetwork,
    CoverageGrid,
    CoverageRequest,
    EmitterTrack,
    EngineState,
    GridBounds,
    LinkStatus,
    ReceiverConfig,
    RelayGrid,
    ScenarioInfo,
    SignalLibraryEntry,
    TerrainGrid,
    TerrainInfo,
)

log = logging.getLogger("ew_core.api")

TICK_HZ = float(os.environ.get("EW_TICK_HZ", "5"))


class Health(BaseModel):
    status: str
    version: str
    scenario: str
    tick_hz: float


class ReceiverUpdate(BaseModel):
    start_hz: float | None = None
    stop_hz: float | None = None
    n_bins: int | None = None
    detection_threshold_db: float | None = None


class Broadcaster:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def send(self, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001 - any failure means the socket is gone
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


async def _run_loop(app: FastAPI) -> None:
    engine: Engine = app.state.engine
    bc: Broadcaster = app.state.broadcaster
    dt = 1.0 / TICK_HZ
    try:
        while True:
            started = asyncio.get_running_loop().time()
            new_alerts = engine.tick(dt)
            if bc.clients:
                payload = {
                    "type": "state",
                    "data": engine.state().model_dump(mode="json"),
                    "new_alerts": [a.model_dump(mode="json") for a in new_alerts],
                }
                await bc.send(payload)
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(0.0, dt - elapsed))
    except asyncio.CancelledError:
        pass


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    scenario = os.environ.get("EW_SCENARIO", "littoral_patrol")
    seed_env = os.environ.get("EW_SEED")
    app.state.engine = Engine(
        scenario,
        seed=int(seed_env) if seed_env else None,
        terrain=os.environ.get("EW_TERRAIN", "synthetic"),
    )
    app.state.broadcaster = Broadcaster()
    task = asyncio.create_task(_run_loop(app))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    app = FastAPI(title="EW Suite core", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("EW_CORS_ORIGINS", "*").split(","),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def engine() -> Engine:
        return app.state.engine

    @app.get("/api/health", response_model=Health)
    def health() -> Health:
        return Health(
            status="ok", version=__version__, scenario=engine().scenario_name, tick_hz=TICK_HZ
        )

    @app.get("/api/state", response_model=EngineState)
    def state() -> EngineState:
        return engine().state()

    @app.get("/api/tracks", response_model=list[EmitterTrack])
    def tracks() -> list[EmitterTrack]:
        return engine().tracks

    @app.get("/api/tracks/{track_id}", response_model=EmitterTrack)
    def track(track_id: str) -> EmitterTrack:
        t = engine().tracker.get(track_id)
        if t is None:
            raise HTTPException(status_code=404, detail="track not found")
        return t

    @app.get("/api/alerts", response_model=list[Alert])
    def alerts() -> list[Alert]:
        return list(engine().alerts)

    @app.get("/api/library", response_model=list[SignalLibraryEntry])
    def library() -> list[SignalLibraryEntry]:
        return engine().library

    @app.get("/api/scenarios", response_model=list[ScenarioInfo])
    def scenarios() -> list[ScenarioInfo]:
        return engine().list_scenarios()

    @app.post("/api/scenarios/{name}/load", response_model=EngineState)
    def load_scenario(name: str) -> EngineState:
        try:
            engine().load_scenario(name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown scenario") from exc
        return engine().state()

    @app.get("/api/receiver", response_model=ReceiverConfig)
    def receiver() -> ReceiverConfig:
        return engine().receiver

    @app.put("/api/receiver", response_model=ReceiverConfig)
    def set_receiver(update: ReceiverUpdate) -> ReceiverConfig:
        current = engine().receiver
        merged = current.model_copy(update=update.model_dump(exclude_none=True))
        try:
            return engine().set_receiver(ReceiverConfig.model_validate(merged.model_dump()))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/terrain", response_model=TerrainInfo)
    def terrain() -> TerrainInfo:
        return engine().terrain_info()

    @app.get("/api/terrain/elevation")
    def terrain_elevation(lat: float, lon: float) -> dict[str, float]:
        return {"lat": lat, "lon": lon, "elevation_m": engine().propagation.ground_m(lat, lon)}

    @app.get("/api/terrain/grid", response_model=TerrainGrid)
    def terrain_grid(
        south: float,
        west: float,
        north: float,
        east: float,
        n: int = Query(default=120, ge=10, le=300),
    ) -> TerrainGrid:
        try:
            return engine().terrain_grid(
                GridBounds(south=south, west=west, north=north, east=east), n
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/coverage", response_model=CoverageGrid)
    def coverage(req: CoverageRequest) -> CoverageGrid:
        return engine().coverage(req)

    @app.get("/api/tracks/{track_id}/coverage", response_model=CoverageGrid)
    def track_coverage(
        track_id: str,
        rx_alt_m: float | None = Query(default=None, ge=0),
        rx_alt_ref: str = Query(default="agl", pattern="^(agl|msl)$"),
        radius_km: float = Query(default=60.0, gt=1.0, le=300.0),
        n: int = Query(default=80, ge=10, le=120),
    ) -> CoverageGrid:
        try:
            grid = engine().track_coverage(
                track_id, rx_alt_m=rx_alt_m, rx_alt_ref=rx_alt_ref, radius_km=radius_km, n=n
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="track not found") from exc
        if grid is None:
            raise HTTPException(status_code=409, detail="track has no geolocation fix yet")
        return grid

    @app.get("/api/blue", response_model=BlueNetwork)
    def blue() -> BlueNetwork:
        return engine().blue

    @app.put("/api/blue", response_model=BlueNetwork)
    def set_blue(network: BlueNetwork) -> BlueNetwork:
        return engine().set_blue(network)

    @app.get("/api/links", response_model=list[LinkStatus])
    def links() -> list[LinkStatus]:
        return engine().links

    @app.get("/api/links/{link_id}/relay-grid", response_model=RelayGrid)
    def relay_grid(
        link_id: str,
        relay_alt_m: float = Query(default=300.0, ge=0),
        relay_alt_ref: str = Query(default="agl", pattern="^(agl|msl)$"),
        radius_km: float | None = Query(default=None, gt=1.0, le=300.0),
        n: int = Query(default=60, ge=10, le=100),
    ) -> RelayGrid:
        try:
            return engine().relay_grid(
                link_id,
                relay_alt_m=relay_alt_m,
                relay_alt_ref=relay_alt_ref,
                radius_km=radius_km,
                n=n,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="link not found") from exc

    @app.websocket("/ws/stream")
    async def stream(ws: WebSocket) -> None:
        await ws.accept()
        bc: Broadcaster = app.state.broadcaster
        bc.clients.add(ws)
        try:
            await ws.send_json({"type": "hello", "version": __version__, "tick_hz": TICK_HZ})
            await ws.send_json(
                {
                    "type": "state",
                    "data": engine().state().model_dump(mode="json"),
                    "new_alerts": [],
                }
            )
            while True:
                # Clients may send pings or retune requests.
                msg = await ws.receive_json()
                if msg.get("type") == "retune":
                    update = ReceiverUpdate.model_validate(msg.get("data", {}))
                    set_receiver(update)
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001
            log.warning("websocket closed: %s", exc)
        finally:
            bc.clients.discard(ws)

    return app


app = create_app()
