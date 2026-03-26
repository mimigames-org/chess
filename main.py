"""Chess game microservice — implements the MimiGames game backend contract."""

import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from games.chess import logic
from shared.redis_client import get_redis

app = FastAPI(title="mimigames-chess", version="0.1.0")

MIMI_SECRET = os.getenv("MIMI_SECRET", "dev-mimi-secret")


def _auth(x_mimi_secret: str = Header(...)) -> None:
    if x_mimi_secret != MIMI_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


# --- Pydantic schemas ---


class StartRequest(BaseModel):
    room_id: str
    players: list[dict]
    config: dict = {}


class ActionRequest(BaseModel):
    room_id: str
    player_id: str
    action: str
    payload: dict = {}


class TickRequest(BaseModel):
    room_id: str


# --- Endpoints ---


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/start")
async def start(body: StartRequest, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret)
    r = get_redis()
    try:
        result = await logic.start_game(r, body.room_id, body.players)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.post("/action")
async def action(body: ActionRequest, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret)
    r = get_redis()
    result = await logic.handle_action(r, body.room_id, body.player_id, body.action, body.payload)
    if result is None:
        raise HTTPException(status_code=400, detail="Invalid action")
    return result


@app.post("/tick", status_code=204)
async def tick(body: TickRequest, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret)
    return None


@app.get("/state/{room_id}")
async def state(room_id: str, player_id: str = "", x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret)
    r = get_redis()
    result = await logic.get_state(r, room_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return result
