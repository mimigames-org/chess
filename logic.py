"""Chess game logic — pure functions, no external dependencies."""

from typing import Any

import chess


def _piece_code(piece: chess.Piece) -> str:
    color = "w" if piece.color == chess.WHITE else "b"
    return color + piece.symbol().upper()


def _full_board(board: chess.Board) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        result[chess.square_name(sq)] = _piece_code(piece) if piece else None
    return result


def _board_delta(old: chess.Board, new: chess.Board) -> dict[str, str | None]:
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


def _public_snapshot(board: chess.Board, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "board": _full_board(board),
        "fen": board.fen(),
        "turn": _turn(board),
        "status": _status(board),
        "white_player": state["white"],
        "black_player": state["black"],
        "white_name": state.get("white_name", "Белые"),
        "black_name": state.get("black_name", "Чёрные"),
    }


def start_game(players: list[dict[str, Any]]) -> dict[str, Any]:
    """Initialise a new chess game. Returns {state, public_delta, private_deltas, events}."""
    if len(players) < 2:
        raise ValueError("Chess requires at least 2 players")

    white_id = players[0]["id"]
    black_id = players[1]["id"]

    board = chess.Board()
    state = {
        "fen": board.fen(),
        "white": white_id,
        "black": black_id,
        "white_name": players[0].get("name", "Белые"),
        "black_name": players[1].get("name", "Чёрные"),
    }

    return {
        "state": state,
        "public_delta": _public_snapshot(board, state),
        "private_deltas": {},
        "events": [],
    }


def handle_action(
    state: dict[str, Any],
    player_id: str,
    action: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Process a move action. Returns None to signal a 400 response."""
    if action != "move":
        return None

    board = chess.Board(state["fen"])

    from_sq = payload.get("from", "")
    to_sq = payload.get("to", "")
    if not from_sq or not to_sq:
        return None

    if board.turn == chess.WHITE and player_id != state["white"]:
        return None
    if board.turn == chess.BLACK and player_id != state["black"]:
        return None

    try:
        from_int = chess.parse_square(from_sq)
        to_int = chess.parse_square(to_sq)
        promotion = None
        if board.piece_type_at(from_int) == chess.PAWN and chess.square_rank(to_int) in (0, 7):
            promo_map = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP, "n": chess.KNIGHT}
            promotion = promo_map.get(str(payload.get("promotion", "q")).lower(), chess.QUEEN)
        move = chess.Move(from_int, to_int, promotion=promotion)
    except (ValueError, chess.InvalidMoveError):
        return None

    if move not in board.legal_moves:
        return None

    old_board = board.copy()
    board.push(move)

    new_status = _status(board)
    new_state = {**state, "fen": board.fen()}

    response: dict[str, Any] = {
        "state": new_state,
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
        if new_status == "checkmate":
            winner = "white" if board.turn == chess.BLACK else "black"
        else:
            winner = "draw"
        response["events"].append({"type": "game_over", "payload": {"winner": winner, "reason": new_status}})

    return response


def get_view(state: dict[str, Any], player_id: str) -> dict[str, Any]:
    """Return player-specific snapshot from full state."""
    board = chess.Board(state["fen"])
    return {
        "public_state": _public_snapshot(board, state),
        "private_state": {},
    }
