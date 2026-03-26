"""Chess game logic. Stateless functions operating on Redis state."""

import json
from typing import Any

import chess


def _key(room_id: str) -> str:
    return f"chess:{room_id}"


def _piece_code(piece: chess.Piece) -> str:
    """Convert piece to 'wP', 'bK' etc."""
    color = "w" if piece.color == chess.WHITE else "b"
    return color + piece.symbol().upper()


def _full_board(board: chess.Board) -> dict[str, str | None]:
    """Return all 64 squares with piece codes or null."""
    result: dict[str, str | None] = {}
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        result[chess.square_name(sq)] = _piece_code(piece) if piece else None
    return result


def _board_delta(old: chess.Board, new: chess.Board) -> dict[str, str | None]:
    """Return only squares that changed between two board states."""
    delta: dict[str, str | None] = {}
    for sq in chess.SQUARES:
        old_piece = old.piece_at(sq)
        new_piece = new.piece_at(sq)
        if old_piece != new_piece:
            delta[chess.square_name(sq)] = _piece_code(new_piece) if new_piece else None
    return delta


def _status(board: chess.Board) -> str:
    if board.is_checkmate():
        return "checkmate"
    if board.is_stalemate():
        return "stalemate"
    if board.is_check():
        return "check"
    return "active"


def _turn(board: chess.Board) -> str:
    return "white" if board.turn == chess.WHITE else "black"


async def start_game(r: Any, room_id: str, players: list[dict[str, Any]]) -> dict[str, Any]:
    """Initialise a new chess game. First player is white."""
    if len(players) < 2:
        raise ValueError("Chess requires at least 2 players")

    white_id = players[0]["id"]
    black_id = players[1]["id"]

    board = chess.Board()
    state = {"fen": board.fen(), "white": white_id, "black": black_id}
    await r.set(_key(room_id), json.dumps(state))

    return {
        "public_delta": {
            "board": _full_board(board),
            "fen": board.fen(),
            "turn": "white",
            "status": "active",
            "white_player": white_id,
            "black_player": black_id,
        },
        "private_deltas": {},
        "events": [],
    }


async def handle_action(
    r: Any,
    room_id: str,
    player_id: str,
    action: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Process a move action. Returns None to signal a 400 response."""
    if action != "move":
        return None

    raw = await r.get(_key(room_id))
    if not raw:
        return None

    state = json.loads(raw)
    board = chess.Board(state["fen"])

    from_sq = payload.get("from", "")
    to_sq = payload.get("to", "")
    if not from_sq or not to_sq:
        return None

    # Validate it's this player's turn
    if board.turn == chess.WHITE and player_id != state["white"]:
        return None
    if board.turn == chess.BLACK and player_id != state["black"]:
        return None

    # Parse move (auto-promote to queen)
    try:
        from_int = chess.parse_square(from_sq)
        to_int = chess.parse_square(to_sq)
        promotion = None
        if board.piece_type_at(from_int) == chess.PAWN and chess.square_rank(to_int) in (0, 7):
            promotion = chess.QUEEN
        move = chess.Move(from_int, to_int, promotion=promotion)
    except (ValueError, chess.InvalidMoveError):
        return None

    if move not in board.legal_moves:
        return None

    old_board = board.copy()
    board.push(move)

    new_status = _status(board)
    state["fen"] = board.fen()
    await r.set(_key(room_id), json.dumps(state))

    response: dict[str, Any] = {
        "public_delta": {
            "board": _board_delta(old_board, board),
            "fen": board.fen(),
            "turn": _turn(board),
            "status": new_status,
            "last_move": {"from": from_sq, "to": to_sq},
        },
        "private_deltas": {},
        "events": [],
    }

    if new_status in ("checkmate", "stalemate"):
        winner: str
        if new_status == "checkmate":
            # The side whose turn it is now lost (they're in checkmate)
            winner = "white" if board.turn == chess.BLACK else "black"
        else:
            winner = "draw"
        response["events"].append(
            {
                "type": "game_over",
                "payload": {"winner": winner, "reason": new_status},
            }
        )

    return response


async def get_state(r: Any, room_id: str) -> dict[str, Any] | None:
    """Return full public state for reconnect / spectators."""
    raw = await r.get(_key(room_id))
    if not raw:
        return None

    state = json.loads(raw)
    board = chess.Board(state["fen"])

    return {
        "board": _full_board(board),
        "fen": board.fen(),
        "turn": _turn(board),
        "status": _status(board),
        "white_player": state["white"],
        "black_player": state["black"],
    }


async def cleanup(r: Any, room_id: str) -> None:
    await r.delete(_key(room_id))
