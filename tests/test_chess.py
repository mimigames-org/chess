"""Tests for the chess game microservice."""

from httpx import AsyncClient

MIMI_SECRET = "dev-mimi-secret"
H = {"X-Mimi-Secret": MIMI_SECRET}

PLAYERS = [{"id": "white-player", "name": "Alice"}, {"id": "black-player", "name": "Bob"}]


async def _start(client: AsyncClient, room_id: str) -> dict:
    resp = await client.post("/start", json={"room_id": room_id, "players": PLAYERS, "config": {}}, headers=H)
    assert resp.status_code == 200
    return resp.json()


async def _action(client: AsyncClient, room_id: str, state: dict, player_id: str, frm: str, to: str):
    resp = await client.post(
        "/action",
        json={
            "room_id": room_id, "player_id": player_id,
            "action": "move", "payload": {"from": frm, "to": to}, "state": state,
        },
        headers=H,
    )
    return resp


# ── Basic endpoints ──────────────────────────────────────────────────────────


async def test_health(chess_client):
    resp = await chess_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_start_returns_full_board(chess_client):
    data = await _start(chess_client, "start-test")
    board = data["public_delta"]["board"]
    assert board["e1"] == "wK"
    assert board["e8"] == "bK"
    assert board["a1"] == "wR"
    assert data["public_delta"]["turn"] == "white"
    assert data["public_delta"]["status"] == "active"
    assert "state" in data


async def test_view_returns_snapshot(chess_client):
    started = await _start(chess_client, "view-test")
    resp = await chess_client.post(
        "/view",
        json={"room_id": "view-test", "player_id": "white-player", "state": started["state"]},
        headers=H,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "public_state" in data
    assert data["public_state"]["turn"] == "white"


async def test_tick_returns_204(chess_client):
    started = await _start(chess_client, "tick-test")
    resp = await chess_client.post("/tick", json={"room_id": "tick-test", "state": started["state"]}, headers=H)
    assert resp.status_code == 204


# ── Valid moves ──────────────────────────────────────────────────────────────


async def test_valid_move_updates_board(chess_client):
    started = await _start(chess_client, "move-test")
    resp = await _action(chess_client, "move-test", started["state"], "white-player", "e2", "e4")
    assert resp.status_code == 200
    data = resp.json()
    delta = data["public_delta"]
    assert delta["last_move"] == {"from": "e2", "to": "e4"}
    assert delta["turn"] == "black"
    assert delta["board"]["e2"] is None
    assert delta["board"]["e4"] == "wP"
    assert "state" in data


async def test_valid_move_sequence(chess_client):
    started = await _start(chess_client, "seq-test")
    state = started["state"]

    r = await _action(chess_client, "seq-test", state, "white-player", "e2", "e4")
    assert r.status_code == 200
    state = r.json()["state"]

    r = await _action(chess_client, "seq-test", state, "black-player", "e7", "e5")
    assert r.status_code == 200
    assert r.json()["public_delta"]["turn"] == "white"


# ── Invalid actions ──────────────────────────────────────────────────────────


async def test_wrong_turn_returns_400(chess_client):
    started = await _start(chess_client, "wrong-turn")
    resp = await _action(chess_client, "wrong-turn", started["state"], "black-player", "e7", "e5")
    assert resp.status_code == 400


async def test_illegal_move_returns_400(chess_client):
    started = await _start(chess_client, "illegal-move")
    resp = await _action(chess_client, "illegal-move", started["state"], "white-player", "e2", "e5")
    assert resp.status_code == 400


async def test_unknown_action_returns_400(chess_client):
    started = await _start(chess_client, "unknown-action")
    resp = await chess_client.post(
        "/action",
        json={
            "room_id": "unknown-action", "player_id": "white-player",
            "action": "surrender", "payload": {}, "state": started["state"],
        },
        headers=H,
    )
    assert resp.status_code == 400


async def test_missing_secret_returns_422(chess_client):
    resp = await chess_client.post("/start", json={"room_id": "r1", "players": PLAYERS, "config": {}})
    assert resp.status_code == 422


# ── Checkmate ────────────────────────────────────────────────────────────────


async def test_fools_mate_produces_game_over(chess_client):
    """Fool's mate: fastest checkmate in chess (2 moves each)."""
    started = await _start(chess_client, "fools-mate")
    state = started["state"]

    moves = [
        ("white-player", "f2", "f3"),
        ("black-player", "e7", "e5"),
        ("white-player", "g2", "g4"),
        ("black-player", "d8", "h4"),
    ]
    resp = None
    for pid, frm, to in moves:
        resp = await _action(chess_client, "fools-mate", state, pid, frm, to)
        assert resp.status_code == 200, resp.text
        state = resp.json()["state"]

    assert resp is not None
    data = resp.json()
    assert data["public_delta"]["status"] == "checkmate"
    events = data["events"]
    assert any(e["type"] == "game_over" for e in events)
    game_over = next(e for e in events if e["type"] == "game_over")
    assert game_over["payload"]["winner"] == "black"
