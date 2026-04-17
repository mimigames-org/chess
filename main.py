"""Chess game microservice — implements the MimiGames game backend contract."""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import logic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s:%(lineno)d] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

MIMI_SECRET = os.getenv("MIMI_SECRET", "dev-mimi-secret")
CORE_URL = os.getenv("CORE_URL", "").rstrip("/")
SELF_BACKEND_URL = os.getenv("SELF_BACKEND_URL", "").rstrip("/")
SELF_FRONTEND_URL = os.getenv("SELF_FRONTEND_URL", "")
SELF_NAME = os.getenv("SELF_NAME", "Шахматы")
PORT = int(os.getenv("PORT", "8081"))


async def _register_self() -> None:
    if not CORE_URL or not SELF_BACKEND_URL or not SELF_FRONTEND_URL:
        return
    payload = {
        "name": SELF_NAME,
        "backend_url": SELF_BACKEND_URL,
        "frontend_url": SELF_FRONTEND_URL,
        "api_key": MIMI_SECRET,
    }
    while True:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(f"{CORE_URL}/games", json=payload)
                resp.raise_for_status()
            logger.info("registered game=%s core_url=%s", SELF_NAME, CORE_URL)
            return
        except Exception as e:
            logger.warning("registration_failed reason=%s retrying_in=5s", e)
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup game=%s port=%d", SELF_NAME, PORT)
    asyncio.create_task(_register_self())
    yield
    logger.info("shutdown game=%s", SELF_NAME)


app = FastAPI(title="mimigames-chess", version="0.1.0", lifespan=lifespan)

app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")


@app.middleware("http")
async def log_requests(request: Request, call_next):  # type: ignore[return]
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = (time.perf_counter() - start) * 1000
    # Skip noisy endpoints
    if request.url.path not in ("/health", "/tick"):
        logger.info(
            "request method=%s path=%s status=%d latency_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            latency_ms,
        )
    return response


def _auth(x_mimi_secret: str, remote_addr: str = "") -> None:
    if x_mimi_secret != MIMI_SECRET:
        logger.warning("auth_failed reason=invalid_secret remote_addr=%s", remote_addr)
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
async def start(body: StartRequest, request: Request, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret, request.client.host if request.client else "")
    try:
        result = logic.start_game(body.players)
        logger.info("game_started room_id=%s players=%d", body.room_id, len(body.players))
        return result
    except ValueError as e:
        logger.warning("game_error room_id=%s reason=%s", body.room_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/action")
async def action(body: ActionRequest, request: Request, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret, request.client.host if request.client else "")
    move_from = body.payload.get("from", "")
    move_to = body.payload.get("to", "")
    if move_from and move_to:
        logger.info(
            "player_action room_id=%s player_id=%s action=%s from=%s to=%s",
            body.room_id,
            body.player_id,
            body.action,
            move_from,
            move_to,
        )
    else:
        logger.info(
            "player_action room_id=%s player_id=%s action=%s",
            body.room_id,
            body.player_id,
            body.action,
        )
    result = logic.handle_action(body.state, body.player_id, body.action, body.payload)
    if result is None:
        logger.warning(
            "game_error room_id=%s reason=invalid_action player_id=%s action=%s",
            body.room_id,
            body.player_id,
            body.action,
        )
        raise HTTPException(status_code=400, detail="Invalid action")
    # Log game_over events emitted by logic
    for event in result.get("events", []):
        if event.get("type") == "game_over":
            ep = event.get("payload", {})
            logger.info(
                "game_over room_id=%s result=%s winner=%s",
                body.room_id,
                ep.get("reason", ""),
                ep.get("winner", ""),
            )
    return result


@app.post("/tick", status_code=204)
async def tick(body: TickRequest, request: Request, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret, request.client.host if request.client else "")
    return None


@app.post("/view")
async def view(body: ViewRequest, request: Request, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret, request.client.host if request.client else "")
    return logic.get_view(body.state, body.player_id)
