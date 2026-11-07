from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
import pytest
import chess
from chess_elo_5000.core import ChessService
from chess_elo_5000.errors import ChessError
from chess_elo_5000.rules import valid_board, legal_move, facts


@pytest.fixture
def service(tmp_path):
    value = ChessService(tmp_path)
    yield value
    value.close()


def new(service, fen=None, mode="human", **kwargs):
    return service.create_game("tester", {"mode": mode, "time_seconds": 0, **({"fen": fen} if fen else {}), **kwargs})


def play(service, game, uci, request_id=None):
    return service.move("tester", game["id"], {"uci": uci, "expected_version": game["version"], "request_id": request_id or str(game["version"])})


@pytest.mark.parametrize("fen", ["invalid", "8/8/8/8/8/8/8/8 w - - 0 1", "8/8/8/8/8/8/4k3/4K3 w - - 0 1"])
def test_invalid_fen(fen):
    with pytest.raises(ChessError, match="FEN|Illegal"):
        valid_board(fen)


def test_legal_moves_and_illegal_wrong_side(service):
    game = new(service)
    assert len(game["legal_moves"]) == 20
    for uci in ("e2e5", "e7e5", "e2e4q", "a9a8", "0000"):
        with pytest.raises(ChessError):
            play(service, game, uci)
    assert service.get_game("tester", game["id"])["version"] == 0


def test_castling_legal_and_through_check(service):
    game = new(service, "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    game = play(service, game, "e1g1")
    assert game["piece_map"]["f1"] == "R" and game["piece_map"]["g1"] == "K"
    board = valid_board("4k3/8/8/8/8/5r2/8/4K2R w K - 0 1")
    with pytest.raises(ChessError):
        legal_move(board, "e1g1")


def test_en_passant_and_pinned_en_passant(service):
    game = new(service)
    for uci in ("e2e4", "a7a6", "e4e5", "d7d5", "e5d6"):
        game = play(service, game, uci)
    assert "d5" not in game["piece_map"] and game["piece_map"]["d6"] == "P"
    assert game["captures"]["white"] == ["p"]
    board = valid_board("k3r3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    with pytest.raises(ChessError):
        legal_move(board, "e5d6")


@pytest.mark.parametrize("promotion,piece", [("q", "Q"), ("r", "R"), ("b", "B"), ("n", "N")])
def test_promotion(service, promotion, piece):
    game = new(service, "7k/P7/8/8/8/8/8/7K w - - 0 1")
    with pytest.raises(ChessError) as error:
        play(service, game, "a7a8")
    assert error.value.code == "promotion_required"
    game = play(service, game, "a7a8"+promotion)
    assert game["piece_map"]["a8"] == piece


@pytest.mark.parametrize("fen,result,reason", [
    ("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1", "1-0", "checkmate"),
    ("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", "1/2-1/2", "stalemate"),
    ("7k/8/8/8/8/8/8/7K w - - 0 1", "1/2-1/2", "insufficient_material"),
    ("7k/8/8/8/8/8/R7/7K w - - 150 76", "1/2-1/2", "seventyfive_moves")])
def test_automatic_terminal_positions(service, fen, result, reason):
    game = new(service, fen)
    assert (game["status"], game["result"], game["reason"]) == ("finished", result, reason)
    assert not game["legal_moves"]
    with pytest.raises(ChessError):
        play(service, game, "a2a3")


def test_fifty_move_claim_is_not_automatic(service):
    game = new(service, "7k/8/8/8/8/8/R7/7K w - - 100 51")
    assert game["status"] == "active" and "fifty_moves" in game["claimable_draws"]
    game = service.action("tester", game["id"], "draw", {"kind": "claim", "expected_version": 0, "request_id": "claim"})
    assert game["reason"] == "claimed_draw" and game["result"] == "1/2-1/2"


def test_threefold_claim_and_fivefold_automatic(service):
    sequence = ("g1f3", "g8f6", "f3g1", "f6g8")
    game = new(service)
    for uci in sequence * 2:
        game = play(service, game, uci)
    assert game["status"] == "active" and "threefold_repetition" in game["claimable_draws"]
    claimed = service.action("tester", game["id"], "draw", {"kind": "claim", "expected_version": game["version"], "request_id": "claim"})
    assert claimed["result"] == "1/2-1/2"
    other = new(service)
    for uci in sequence * 4:
        other = play(service, other, uci)
    assert other["reason"] == "fivefold_repetition"


def test_draw_not_claimable(service):
    game = new(service)
    with pytest.raises(ChessError) as error:
        service.action("tester", game["id"], "draw", {"kind": "claim", "expected_version": 0, "request_id": "x"})
    assert error.value.code == "draw_not_claimable"


def test_resignation_and_draw_agreement(service):
    game = new(service)
    game = service.action("tester", game["id"], "resign", {"expected_version": 0, "request_id": "resign"})
    assert game["result"] == "0-1" and game["reason"] == "resignation"
    game = new(service)
    game = service.action("tester", game["id"], "draw", {"kind": "offer", "expected_version": 0, "request_id": "offer"})
    with pytest.raises(ChessError):
        service.action("tester", game["id"], "draw", {"kind": "accept", "expected_version": 1, "request_id": "self_accept"})
    game = play(service, game, "e2e4")
    game = service.action("tester", game["id"], "draw", {"kind": "accept", "expected_version": 2, "request_id": "accept"})
    assert game["result"] == "1/2-1/2" and game["reason"] == "draw_agreement"


def test_duplicate_and_conflicting_move(service):
    game = new(service)
    result = play(service, game, "e2e4", "same")
    duplicate = play(service, game, "e2e4", "same")
    assert duplicate["duplicate"] and duplicate["fen"] == result["fen"]
    with pytest.raises(ChessError) as error:
        play(service, game, "d2d4", "same")
    assert error.value.code == "idempotency_conflict"
    with pytest.raises(ChessError) as error:
        play(service, game, "d2d4", "different")
    assert error.value.code == "stale_version"


def test_concurrent_move_submissions(service):
    game = new(service)
    def attempt(uci):
        try:
            return play(service, game, uci, uci)["version"]
        except ChessError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("e2e4", "d2d4")))
    assert sorted(map(str, results)) == ["1", "stale_version"]
    assert len(service.get_game("tester", game["id"])["moves"]) == 1


def test_restart_exact_replay_and_terminal(tmp_path):
    service = ChessService(tmp_path)
    game = new(service)
    for uci in ("f2f3", "e7e5", "g2g4", "d8h4"):
        game = play(service, game, uci)
    assert game["reason"] == "checkmate"
    service.close()
    restarted = ChessService(tmp_path)
    restored = restarted.get_game("tester", game["id"])
    assert restored["fen"] == game["fen"] and restored["moves"] == game["moves"]
    assert restored["result"] == "0-1" and restored["status"] == "finished"
    restarted.close()


def test_integrity_replay_rejects_corrupt_saved_fen(service):
    game = new(service)
    with service.storage.transaction() as db:
        row = db.execute("SELECT state FROM games WHERE id=?", (game["id"],)).fetchone()
        state = json.loads(row["state"])
        state["fen"] = "broken"
        db.execute("UPDATE games SET state=? WHERE id=?", (json.dumps(state), game["id"]))
    with pytest.raises(ChessError) as error:
        service.get_game("tester", game["id"])
    assert error.value.code == "integrity_error"


def test_transaction_failure_rolls_back(service, monkeypatch):
    game = new(service)
    def failing(*args, **kwargs):
        raise OSError("simulated storage interruption")
    monkeypatch.setattr(service, "_save", failing)
    with pytest.raises(OSError):
        play(service, game, "e2e4")
    assert service.get_game("tester", game["id"])["version"] == 0


def test_clock_expiry_and_persistence_without_status_mutation(service):
    game = new(service, time_seconds=1)
    with service.storage.transaction() as db:
        row = db.execute("SELECT state FROM games WHERE id=?", (game["id"],)).fetchone()
        state = json.loads(row["state"])
        state["clock_anchor"] -= 2
        db.execute("UPDATE games SET state=? WHERE id=?", (json.dumps(state), game["id"]))
    displayed = service.get_game("tester", game["id"])
    assert displayed["reason"] == "time_forfeit" and displayed["result"] == "0-1"
    persisted = service.action("tester", game["id"], "tick", {"expected_version": 0, "request_id": "tick"})
    assert persisted["status"] == "finished" and not persisted["moves"]


def test_pgn_round_trip_and_original_variation_preservation(service):
    game = new(service)
    for uci in ("e2e4", "e7e5", "g1f3"):
        game = play(service, game, uci)
    exported = service.export_pgn("tester", game["id"])
    imported = service.import_pgn("tester", exported)
    assert imported["fen"] == game["fen"] and imported["mode"] == "study"
    variation = service.variation("tester", game["id"], {"ply": 1, "moves": ["c7c5", "g1f3"], "name": "Sicilian alternative"})
    assert variation["parent_id"] == game["id"] and variation["parent_ply"] == 1
    assert service.get_game("tester", game["id"])["fen"] == game["fen"]
    assert len(service.list_variations("tester", game["id"])) == 1
    with pytest.raises(ChessError):
        service.variation("tester", game["id"], {"ply": 1, "moves": ["e2e4"]})


@pytest.mark.parametrize("pgn", ["garbage", '[Event "Bad"]\n\n1. e5 *', '[Event "Bad"]\n\n1. e4 e5 2. Ke3 *', '[Event "Bad"]\n[Result "1-0"]\n\n1. f3 e5 2. g4 Qh4# 1-0'])
def test_malformed_pgn(service, pgn):
    with pytest.raises(ChessError) as error:
        service.import_pgn("tester", pgn)
    assert error.value.code == "invalid_pgn"


def test_study_undo_isolated_from_historical_game(service):
    historical = play(service, new(service), "e2e4")
    with pytest.raises(ChessError):
        service.action("tester", historical["id"], "undo", {"expected_version": 1, "request_id": "undo"})
    study = play(service, new(service, mode="study"), "e2e4")
    study = service.action("tester", study["id"], "undo", {"expected_version": 1, "request_id": "undo"})
    assert study["fen"] == chess.STARTING_FEN and not study["moves"]
    assert service.get_game("tester", historical["id"])["moves"]


def test_owner_isolation(service):
    game = new(service)
    with pytest.raises(ChessError) as error:
        service.get_game("another", game["id"])
    assert error.value.status == 404


def test_position_facts_distinguish_heuristics():
    result = facts(chess.Board())
    assert result["material_balance"] == 0 and len(result["legal_moves"]) == 20
    assert result["fact_label"] == "RULES-VERIFIED FACT"


def test_draw_offer_declined_by_opponent_move(service):
    game = new(service)
    game = service.action("tester", game["id"], "draw", {"kind": "offer", "expected_version": 0, "request_id": "offer"})
    game = play(service, game, "e2e4")
    assert game["draw_offer"] == "white"
    game = play(service, game, "e7e5")
    assert game["draw_offer"] is None


@pytest.mark.parametrize("pgn", ['[Event "Bad"]\n\n1. e4 nonsense *', '[Event "Bad"]\n\n1. e4 (1. d4 *', '[Event "Bad"]\n\n1. e4 {unclosed *'])
def test_pgn_never_silently_truncates(service, pgn):
    with pytest.raises(ChessError) as error:
        service.import_pgn("tester", pgn)
    assert error.value.code == "invalid_pgn"


def test_pgn_comments_and_variations_preserved(service):
    pgn = '[Event "Study"]\n[Result "*"]\n\n1. e4 {King pawn} e5 (1... c5 {Sicilian}) 2. Nf3 *'
    game = service.import_pgn("tester", pgn)
    exported = service.export_pgn("tester", game["id"])
    assert "King pawn" in exported and "Sicilian" in exported and "c5" in exported


def test_clock_forfeit_draw_if_opponent_has_no_mating_material(service):
    game = new(service, "7k/8/8/8/8/8/R7/7K w - - 0 1", time_seconds=1)
    with service.storage.transaction() as db:
        row = db.execute("SELECT state FROM games WHERE id=?", (game["id"],)).fetchone()
        state = json.loads(row["state"])
        state["clock_anchor"] -= 2
        db.execute("UPDATE games SET state=? WHERE id=?", (json.dumps(state), game["id"]))
    finished = service.action("tester", game["id"], "tick", {"expected_version": 0, "request_id": "flag"})
    assert finished["result"] == "1/2-1/2" and finished["reason"] == "time_forfeit_insufficient_mating_material"
