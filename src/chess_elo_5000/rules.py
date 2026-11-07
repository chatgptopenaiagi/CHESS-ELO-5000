"""Authoritative standard-chess facts; draw claims are distinct from termination."""
import hashlib
import chess
from .errors import ChessError


def valid_board(fen=None):
    try:
        board = chess.Board(fen or chess.STARTING_FEN)
    except (ValueError, TypeError) as exc:
        raise ChessError("invalid_fen", "FEN could not be parsed") from exc
    if not board.is_valid():
        raise ChessError("invalid_fen", f"Illegal standard-chess position (status {int(board.status())})")
    return board


def position_id(board):
    # Full legal EP rights matter; halfmove counters affect draw eligibility and cache identity.
    return hashlib.sha256(board.fen(en_passant="fen").encode()).hexdigest()


def opening_position_id(board):
    # Position lookup deliberately excludes counters, but includes only legal EP rights.
    return hashlib.sha256(" ".join(board.fen().split()[:4]).encode()).hexdigest()


def legal_move(board, uci):
    if not isinstance(uci, str):
        raise ChessError("invalid_move", "Supply a UCI move such as e2e4 or a7a8q")
    try:
        move = chess.Move.from_uci(uci)
    except ValueError as exc:
        raise ChessError("invalid_move", "Invalid UCI notation") from exc
    if move not in board.legal_moves:
        if len(uci) == 4:
            candidates = [m for m in board.legal_moves if m.uci().startswith(uci)]
            if any(m.promotion for m in candidates):
                raise ChessError("promotion_required", "Select queen, rook, bishop or knight for promotion")
        raise ChessError("illegal_move", "Move is not legal in the current position")
    return move


def facts(board):
    values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    material = sum(values.get(p.piece_type, 0) * (1 if p.color else -1) for p in board.piece_map().values())
    pawns = {}
    for color, label in [(chess.WHITE, "white"), (chess.BLACK, "black")]:
        files = [len(board.pieces(chess.PAWN, color) & chess.BB_FILES[f]) for f in range(8)]
        pawns[label] = {"doubled_files": [chess.FILE_NAMES[i] for i, n in enumerate(files) if n > 1],
                        "isolated_files": [chess.FILE_NAMES[i] for i, n in enumerate(files) if n and not (files[i-1] if i else 0) and not (files[i+1] if i<7 else 0)]}
    return {"fen": board.fen(), "position_id": position_id(board), "opening_position_id": opening_position_id(board),
            "side_to_move": "white" if board.turn else "black", "legal_moves": [m.uci() for m in board.legal_moves],
            "check": board.is_check(), "checkmate": board.is_checkmate(), "stalemate": board.is_stalemate(),
            "insufficient_material": board.is_insufficient_material(), "material_balance": material,
            "piece_activity": {"legal_move_count": board.legal_moves.count()}, "pawn_structure": pawns,
            "king_safety": {"in_check": board.is_check(), "checkers": [chess.square_name(s) for s in board.checkers()]},
            "tactical_threats": {"checks": [m.uci() for m in board.legal_moves if board.gives_check(m)], "captures": [m.uci() for m in board.legal_moves if board.is_capture(m)]},
            "fact_label": "RULES-VERIFIED FACT", "heuristic_label": "Material/activity/pawn descriptions are HEURISTIC INTERPRETATION, not an engine evaluation"}
