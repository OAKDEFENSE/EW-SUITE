"""HTTP + WebSocket API for the EW console."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import __version__
from .engine import Engine
from .models import (
    Alert,
    EmitterTrack,
    EngineState,
    ReceiverConfig,
    ScenarioInfo,
    SignalLibraryEntry,
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
    app.state.engine = Engine(scenario, seed=int(seed_env) if seed_env else None)
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
