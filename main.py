"""Chess game microservice — implements the MimiGames game backend contract."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import logic

logger = logging.getLogger(__name__)

MIMI_SECRET = os.getenv("MIMI_SECRET", "dev-mimi-secret")
CORE_URL = os.getenv("CORE_URL", "").rstrip("/")
SELF_BACKEND_URL = os.getenv("SELF_BACKEND_URL", "").rstrip("/")
SELF_FRONTEND_URL = os.getenv("SELF_FRONTEND_URL", "")
SELF_NAME = os.getenv("SELF_NAME", "Шахматы")


async def _register_self() -> None:
    if not CORE_URL or not SELF_BACKEND_URL or not SELF_FRONTEND_URL:
        return
    payload = {
        "name": SELF_NAME,
        "backend_url": SELF_BACKEND_URL,
        "frontend_url": SELF_FRONTEND_URL,
        "api_key": MIMI_SECRET,
    }
    for attempt in range(1, 6):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(f"{CORE_URL}/games", json=payload)
                resp.raise_for_status()
            logger.info("Registered with core at %s", CORE_URL)
            return
        except Exception as e:
            logger.warning("Registration attempt %d failed: %s", attempt, e)
            await asyncio.sleep(attempt * 2)
    logger.error("Failed to register with core after 5 attempts")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_register_self())
    yield


app = FastAPI(title="mimigames-chess", version="0.1.0", lifespan=lifespan)

app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")


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
    state: dict


class TickRequest(BaseModel):
    room_id: str


class ViewRequest(BaseModel):
    room_id: str
    player_id: str
    state: dict


# --- Endpoints ---


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/start")
async def start(body: StartRequest, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret)
    try:
        return logic.start_game(body.players)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/action")
async def action(body: ActionRequest, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret)
    result = logic.handle_action(body.state, body.player_id, body.action, body.payload)
    if result is None:
        raise HTTPException(status_code=400, detail="Invalid action")
    return result


@app.post("/tick", status_code=204)
async def tick(body: TickRequest, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret)
    return None


@app.post("/view")
async def view(body: ViewRequest, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret)
    return logic.get_view(body.state, body.player_id)
