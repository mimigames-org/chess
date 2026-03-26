"""Tests for the chess game microservice."""

import pytest
from httpx import ASGITransport, AsyncClient

MIMI_SECRET = "dev-mimi-secret"
H = {"X-Mimi-Secret": MIMI_SECRET}

PLAYERS = [{"id": "white-player", "name": "Alice"}, {"id": "black-player", "name": "Bob"}]


@pytest.fixture
async def chess_client(redis):
    from main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def started_game(chess_client):
    """Start a game and return (client, room_id)."""
    room_id = "chess-room-1"
    resp = await chess_client.post(
        "/start",
        json={"room_id": room_id, "players": PLAYERS, "config": {}},
        headers=H,
    )
    assert resp.status_code == 200
    return chess_client, room_id


# ── Basic endpoints ──────────────────────────────────────────────────────────


async def test_health(chess_client):
    resp = await chess_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_start_returns_full_board(chess_client):
    resp = await chess_client.post(
        "/start",
        json={"room_id": "start-test", "players": PLAYERS, "config": {}},
        headers=H,
    )
    assert resp.status_code == 200
    data = resp.json()
    board = data["public_delta"]["board"]
    assert board["e1"] == "wK"
    assert board["e8"] == "bK"
    assert board["a1"] == "wR"
    assert data["public_delta"]["turn"] == "white"
    assert data["public_delta"]["status"] == "active"


async def test_get_state(chess_client):
    room_id = "state-test"
    await chess_client.post(
        "/start",
        json={"room_id": room_id, "players": PLAYERS, "config": {}},
        headers=H,
    )
    resp = await chess_client.get(f"/state/{room_id}?player_id=white-player", headers=H)
    assert resp.status_code == 200
    data = resp.json()
    assert "board" in data
    assert "fen" in data
    assert data["turn"] == "white"


async def test_tick_returns_204(chess_client):
    resp = await chess_client.post("/tick", json={"room_id": "any"}, headers=H)
    assert resp.status_code == 204


# ── Valid moves ──────────────────────────────────────────────────────────────


async def test_valid_move_updates_board(started_game):
    client, room_id = started_game
    resp = await client.post(
        "/action",
        json={
            "room_id": room_id,
            "player_id": "white-player",
            "action": "move",
            "payload": {"from": "e2", "to": "e4"},
        },
        headers=H,
    )
    assert resp.status_code == 200
    data = resp.json()
    delta = data["public_delta"]
    assert delta["last_move"] == {"from": "e2", "to": "e4"}
    assert delta["turn"] == "black"
    assert delta["board"]["e2"] is None
    assert delta["board"]["e4"] == "wP"


async def test_valid_move_sequence(started_game):
    client, room_id = started_game
    r = await client.post("/action", json={
        "room_id": room_id, "player_id": "white-player",
        "action": "move", "payload": {"from": "e2", "to": "e4"},
    }, headers=H)
    assert r.status_code == 200
    r = await client.post("/action", json={
        "room_id": room_id, "player_id": "black-player",
        "action": "move", "payload": {"from": "e7", "to": "e5"},
    }, headers=H)
    assert r.status_code == 200
    assert r.json()["public_delta"]["turn"] == "white"


# ── Invalid actions ──────────────────────────────────────────────────────────


async def test_wrong_turn_returns_400(started_game):
    """Black player trying to move on white's turn."""
    client, room_id = started_game
    resp = await client.post(
        "/action",
        json={
            "room_id": room_id,
            "player_id": "black-player",
            "action": "move",
            "payload": {"from": "e7", "to": "e5"},
        },
        headers=H,
    )
    assert resp.status_code == 400


async def test_illegal_move_returns_400(started_game):
    """Pawn can't jump 3 squares."""
    client, room_id = started_game
    resp = await client.post(
        "/action",
        json={
            "room_id": room_id,
            "player_id": "white-player",
            "action": "move",
            "payload": {"from": "e2", "to": "e5"},
        },
        headers=H,
    )
    assert resp.status_code == 400


async def test_unknown_action_returns_400(started_game):
    client, room_id = started_game
    resp = await client.post(
        "/action",
        json={
            "room_id": room_id,
            "player_id": "white-player",
            "action": "surrender",
            "payload": {},
        },
        headers=H,
    )
    assert resp.status_code == 400


async def test_missing_secret_returns_422(chess_client):
    resp = await chess_client.post(
        "/start",
        json={"room_id": "r1", "players": PLAYERS, "config": {}},
    )
    assert resp.status_code == 422  # missing required header → FastAPI 422


# ── Checkmate ────────────────────────────────────────────────────────────────


async def test_fools_mate_produces_game_over(chess_client):
    """Fool's mate: fastest checkmate in chess (2 moves each)."""
    room_id = "fools-mate"
    await chess_client.post(
        "/start",
        json={"room_id": room_id, "players": PLAYERS, "config": {}},
        headers=H,
    )

    moves = [
        ("white-player", "f2", "f3"),
        ("black-player", "e7", "e5"),
        ("white-player", "g2", "g4"),
    ]
    for pid, frm, to in moves:
        r = await chess_client.post("/action", json={
            "room_id": room_id, "player_id": pid,
            "action": "move", "payload": {"from": frm, "to": to},
        }, headers=H)
        assert r.status_code == 200, r.text

    resp = await chess_client.post("/action", json={
        "room_id": room_id, "player_id": "black-player",
        "action": "move", "payload": {"from": "d8", "to": "h4"},
    }, headers=H)

    assert resp.status_code == 200
    data = resp.json()
    assert data["public_delta"]["status"] == "checkmate"
    events = data["events"]
    assert any(e["type"] == "game_over" for e in events)
    game_over = next(e for e in events if e["type"] == "game_over")
    assert game_over["payload"]["winner"] == "black"
