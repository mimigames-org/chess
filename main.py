"""Chess game microservice — implements the MimiGames game backend contract."""

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from mimigames_sdk.protocol import ActionRequest, HealthResponse, StartRequest, TickRequest, ViewRequest
from pydantic import BaseModel, ConfigDict, Field

import logic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s:%(lineno)d] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

MIMI_SECRET = os.environ["MIMI_SECRET"]
CORE_URL = os.environ["CORE_URL"].rstrip("/")
SELF_BACKEND_URL = os.environ["SELF_BACKEND_URL"].rstrip("/")
SELF_FRONTEND_URL = os.environ["SELF_FRONTEND_URL"]
SELF_NAME = os.environ["SELF_NAME"]
PORT = int(os.environ["PORT"])


class ChessMovePayload(BaseModel):
    """Required fields for a chess move action."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    promotion: str | None = None  # optional; "q" is the chess default when pawn promotes


async def _register_self(client: httpx.AsyncClient) -> None:
    payload = {
        "name": SELF_NAME,
        "backend_url": SELF_BACKEND_URL,
        "frontend_url": SELF_FRONTEND_URL,
        "api_key": MIMI_SECRET,
    }
    while True:
        try:
            resp = await client.post(f"{CORE_URL}/games", json=payload, timeout=5.0)
            resp.raise_for_status()
            logger.info("registered game=%s core_url=%s", SELF_NAME, CORE_URL)
            return
        except (TimeoutError, httpx.HTTPError) as e:
            # Retry only on transient network/timeout errors; other exceptions
            # (e.g. programming bugs, auth misconfig) must propagate.
            logger.warning("registration_failed reason=%s retrying_in=5s", e)
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup game=%s port=%d", SELF_NAME, PORT)
    http_client = httpx.AsyncClient()
    register_task = asyncio.create_task(_register_self(http_client))
    yield
    if not register_task.done():
        register_task.cancel()
        try:
            await register_task
        except asyncio.CancelledError:
            pass
    await http_client.aclose()
    logger.info("shutdown game=%s", SELF_NAME)


app = FastAPI(title="mimigames-chess", version="0.1.0", lifespan=lifespan)

app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")


@app.middleware("http")
async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
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


# --- Exception handlers ---


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "code": "http_error"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": str(exc), "code": "validation_error"},
    )


# --- Endpoints ---


@app.get("/health")
async def health() -> HealthResponse:
    return HealthResponse()


@app.post("/start")
async def start(body: StartRequest, request: Request, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret, request.client.host if request.client else "")
    try:
        result = logic.start_game([p.model_dump() for p in body.players])
        logger.info("game_started room_id=%s players=%d", body.room_id, len(body.players))
        return result
    except ValueError as e:
        logger.warning("game_error room_id=%s reason=%s", body.room_id, e)
        return JSONResponse(status_code=400, content={"error": str(e), "code": "invalid_request"})


@app.post("/action")
async def action(body: ActionRequest, request: Request, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret, request.client.host if request.client else "")
    if body.state is None:
        return JSONResponse(status_code=400, content={"error": "state is required", "code": "invalid_request"})
    if body.action == logic.Action.MOVE:
        try:
            move = ChessMovePayload.model_validate(body.payload)
        except Exception as exc:
            return JSONResponse(
                status_code=422,
                content={"error": f"invalid move payload: {exc}", "code": "validation_error"},
            )
        logger.info(
            "player_action room_id=%s player_id=%s action=%s from=%s to=%s",
            body.room_id,
            body.player_id,
            body.action,
            move.from_,
            move.to,
        )
    else:
        logger.info(
            "player_action room_id=%s player_id=%s action=%s",
            body.room_id,
            body.player_id,
            body.action,
        )
    result = logic.handle_action(body.state, body.player_id, body.action, body.payload, body.room_id)
    if result is None:
        logger.warning(
            "game_error room_id=%s reason=invalid_action player_id=%s action=%s",
            body.room_id,
            body.player_id,
            body.action,
        )
        return JSONResponse(status_code=400, content={"error": "Invalid action", "code": "invalid_action"})
    return result


@app.post("/tick", status_code=204)
async def tick(body: TickRequest, request: Request, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret, request.client.host if request.client else "")
    return None


@app.get("/healthz/live")
async def healthz_live() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@app.get("/healthz/ready")
async def healthz_ready() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@app.post("/view")
async def view(body: ViewRequest, request: Request, x_mimi_secret: str = Header(...)):
    _auth(x_mimi_secret, request.client.host if request.client else "")
    if body.state is None:
        return JSONResponse(status_code=400, content={"error": "state is required", "code": "invalid_request"})
    return logic.get_view(body.state, body.player_id)
