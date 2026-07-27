"""The main game: simulation loop + WebSocket state stream + spectator page.

Run with:
    python -m game_app.server
or via start.sh, which brings up the lobby alongside it.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from arena import config as cfg
from arena.match import Match

log = logging.getLogger("arena.game")
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="AI Fight Arena — Game")
match = Match()

_clients: set[WebSocket] = set()
_loop_task: asyncio.Task | None = None


# ------------------------------------------------------------------ lifecycle
def _notify_lobby_match_ended(winner: dict | None) -> None:
    """Tell the lobby to release every reserved character."""
    async def send():
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                await client.post(
                    f"{cfg.LOBBY_URL}/internal/match-ended",
                    json={"winner": winner},
                    headers={"X-Arena-Token": cfg.INTERNAL_TOKEN},
                )
        except Exception as e:                       # noqa: BLE001 - lobby may be down
            log.warning("could not notify lobby: %s", e)

    with contextlib.suppress(RuntimeError):
        asyncio.get_running_loop().create_task(send())


match.set_match_end_hook(_notify_lobby_match_ended)


async def _game_loop() -> None:
    """Fixed-timestep simulation. Broadcasts state at 30 Hz."""
    frame = 1.0 / cfg.TICK_RATE
    loop = asyncio.get_running_loop()
    next_frame = loop.time()
    broadcast_every = max(1, cfg.TICK_RATE // 30)

    while True:
        try:
            match.step()
        except Exception:                            # noqa: BLE001 - never stop the arena
            log.exception("simulation error on tick %s", match.tick)

        if match.tick % broadcast_every == 0 and _clients:
            await _broadcast(match.state_dict())

        next_frame += frame
        delay = next_frame - loop.time()
        if delay < -0.25:                            # fell far behind, resync
            next_frame = loop.time()
            delay = 0
        await asyncio.sleep(max(0.0, delay))


async def _broadcast(payload: dict) -> None:
    message = json.dumps(payload, separators=(",", ":"))
    dead = []
    for ws in list(_clients):
        try:
            await ws.send_text(message)
        except Exception:                            # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    global _loop_task
    _loop_task = asyncio.create_task(_game_loop())
    log.info("arena running — stage %s", match.stage.name)
    yield
    _loop_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _loop_task


app.router.lifespan_context = lifespan


# ----------------------------------------------------------------- endpoints
@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/static")
async def static_data() -> dict:
    return match.static_dict()


@app.get("/api/state")
async def state() -> dict:
    return match.state_dict()


@app.post("/api/next-game")
async def next_game() -> dict:
    """Wired to the Next Game button on the main screen."""
    match.next_game()
    return {"ok": True, "state": match.state, "match": match.match_number}


@app.post("/internal/roster-changed")
async def roster_changed(x_arena_token: str = Header(default="")) -> dict:
    """Lobby nudge so a newly written script appears without waiting for the poll."""
    if x_arena_token != cfg.INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="bad token")
    match.refresh_roster()
    return {"ok": True, "fighters": len(match.fighters)}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _clients.add(ws)
    try:
        await ws.send_text(json.dumps({"init": match.static_dict()}))
        await ws.send_text(json.dumps(match.state_dict(), separators=(",", ":")))
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("cmd") == "next":
                match.next_game()
    except WebSocketDisconnect:
        pass
    except Exception:                                # noqa: BLE001
        log.debug("websocket dropped", exc_info=True)
    finally:
        _clients.discard(ws)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=cfg.GAME_PORT, log_level="warning")
