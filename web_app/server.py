"""The public lobby website.

Players open this on their phone or laptop, pick one of the twelve characters,
describe how it should fight, and the description is turned into a sandboxed
script dropped into /player - which the running game picks up on its own.

Run with:
    python -m web_app.server
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx
from fastapi import Body, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from arena import config as cfg
from arena.characters import get as get_character
from arena.sandbox import validate_source

from .llm import Interpreter, sanitise_brief
from .lobby import Lobby

log = logging.getLogger("arena.web")
STATIC = Path(__file__).parent / "static"
COOKIE = "arena_sid"

app = FastAPI(title="AI Fight Arena — Lobby")
lobby = Lobby()
interpreter = Interpreter()


def _player(request: Request):
    return lobby.get(request.cookies.get(COOKIE))


def _require(request: Request):
    player = _player(request)
    if player is None:
        raise HTTPException(status_code=401, detail="Join the lobby first.")
    return player


async def _nudge_game() -> None:
    """Ask the game to rescan /player immediately rather than wait for its poll."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(f"{cfg.GAME_URL}/internal/roster-changed",
                              headers={"X-Arena-Token": cfg.INTERNAL_TOKEN})
    except Exception as e:                           # noqa: BLE001 - game may not be up
        log.debug("game nudge failed: %s", e)


# ------------------------------------------------------------------- pages
@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
async def state(request: Request) -> dict:
    data = lobby.roster_state(_player(request))
    data["llm"] = {"available": interpreter.available, "reason": interpreter.reason}
    return data


@app.post("/api/join")
async def join(response: Response, payload: dict = Body(default={})) -> dict:
    name = str(payload.get("name", ""))[:40]
    player = lobby.join(name)
    response.set_cookie(COOKIE, player.sid, httponly=True, samesite="lax", max_age=86400)
    return {"ok": True, "name": player.name}


@app.post("/api/select")
async def select(request: Request, payload: dict = Body(default={})) -> JSONResponse:
    player = _require(request)
    ok, message = lobby.claim(player, str(payload.get("character", "")))
    return JSONResponse({"ok": ok, "message": message}, status_code=200 if ok else 409)


@app.post("/api/behaviour")
async def behaviour(request: Request, payload: dict = Body(default={})) -> JSONResponse:
    """Turn the player's description into a fighter script."""
    player = _require(request)
    if not player.character_id:
        return JSONResponse({"ok": False, "message": "Pick a character first."}, status_code=409)

    preset = get_character(player.character_id)
    brief = sanitise_brief(str(payload.get("brief", "")))
    if len(brief) < 8:
        return JSONResponse(
            {"ok": False, "message": "Describe how your fighter should act (a sentence or two)."},
            status_code=400,
        )

    # The model call is blocking; keep the event loop free.
    source, note = await asyncio.to_thread(
        interpreter.generate, player.name, preset, brief)

    problems = validate_source(source)
    if problems:
        # Should not happen - generate() already validates - but never write a
        # file the arena would reject.
        log.error("refusing to write invalid script for %s: %s", player.name, problems)
        return JSONResponse(
            {"ok": False, "message": "Could not build a valid fighter from that. Try rewording it."},
            status_code=500,
        )

    filename = lobby.write_script(player, source, brief, note)
    await _nudge_game()
    return JSONResponse({
        "ok": True,
        "message": f"{player.name} is in the arena as {preset.name}.",
        "file": filename,
        "note": note,
        "source": source,
    })


@app.post("/api/leave")
async def leave(request: Request) -> dict:
    """Give up a character before the match starts."""
    lobby.release(_require(request))
    await _nudge_game()
    return {"ok": True}


@app.post("/internal/match-ended")
async def match_ended(payload: dict = Body(default={}),
                      x_arena_token: str = Header(default="")) -> dict:
    """Called by the game process the moment a winner is declared."""
    if x_arena_token != cfg.INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="bad token")
    removed = lobby.reset_for_next_match(payload.get("winner"))
    return {"ok": True, "released": removed}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not interpreter.available:
        log.warning("LLM interpreter disabled (%s) — fighters will use the fallback script",
                    interpreter.reason)
    uvicorn.run(app, host="0.0.0.0", port=cfg.LOBBY_PORT, log_level="warning")
