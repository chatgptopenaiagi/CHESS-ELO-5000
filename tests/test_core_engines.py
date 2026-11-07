import json
from pathlib import Path
import sys
import threading
import time
import chess
import pytest
from chess_elo_5000.core import ChessService
from chess_elo_5000.engines import EngineAdapter, score_json
from chess_elo_5000.errors import ChessError

ROOT = Path(__file__).resolve().parents[1]
STOCKFISH = ROOT / "stockfish/stockfish/stockfish-windows-x86-64-universal.exe"
FAULT = ROOT / "tests/fixtures/fault_uci.py"


@pytest.fixture
def service(tmp_path):
    service = ChessService(tmp_path, STOCKFISH)
    yield service
    service.close()


def wait_job(service, job):
    end = time.monotonic() + 15
    while time.monotonic() < end:
        result = service.get_analysis("test", job["id"])
        if result["status"] not in ("queued", "running"):
            return result
        time.sleep(0.03)
    raise AssertionError("Analysis did not finish within bounded test deadline")


def test_real_stockfish_uci_and_multipv():
    adapter = EngineAdapter(STOCKFISH)
    result = adapter.analyze(chess.Board(), depth=12, movetime_ms=500, multipv=3)
    assert result["engine"]["name"] == "Stockfish 19"
    assert result["configuration"] == {"Threads": 6, "Hash": 512, "Skill Level": 20, "UCI_LimitStrength": False}
    assert len(result["lines"]) == 3 and result["nodes"] > 0
    assert chess.Move.from_uci(result["bestmove"]) in chess.Board().legal_moves
    assert result["elapsed_seconds"] < 8
    for line in result["lines"]:
        board = chess.Board()
        for uci in line["pv"]:
            move = chess.Move.from_uci(uci)
            assert move in board.legal_moves
            board.push(move)


def test_real_stockfish_mate_score_distinct():
    board = chess.Board("7k/8/5KQ1/8/8/8/8/8 w - - 0 1")
    result = EngineAdapter(STOCKFISH).analyze(board, nodes=2000, movetime_ms=300, multipv=1)
    assert result["lines"][0]["score"]["type"] == "mate"
    assert result["lines"][0]["score"]["value"] == 1
    board.push_uci(result["bestmove"])
    assert board.is_checkmate()


def test_score_perspective():
    from chess.engine import PovScore, Cp, Mate
    assert score_json(PovScore(Cp(25), chess.BLACK), chess.BLACK)["value"] == -25
    assert score_json(PovScore(Mate(2), chess.BLACK), chess.BLACK)["value"] == -2
    assert score_json(PovScore(Mate(2), chess.BLACK), chess.BLACK)["type"] == "mate"


@pytest.mark.parametrize("mode,code", [("crash", "engine_failed"), ("invalid", "malformed_engine_response"), ("missing_score", "malformed_engine_response"), ("timeout", "engine_timeout")])
def test_real_owned_uci_fault_process(mode, code):
    adapter = EngineAdapter(FAULT, command=[sys.executable, "-u", str(FAULT), mode])
    start = time.monotonic()
    with pytest.raises(ChessError) as error:
        adapter.analyze(chess.Board(), movetime_ms=10, multipv=1)
    assert error.value.code == code
    assert time.monotonic() - start < 9


def test_engine_failure_preserves_game(service):
    game = service.create_game("test", {"mode": "engine", "human_color": "black", "time_seconds": 0})
    service.engine = EngineAdapter(FAULT, command=[sys.executable, "-u", str(FAULT), "crash"])
    with pytest.raises(ChessError):
        service.engine_move("test", game["id"], {"expected_version": 0, "request_id": "reply", "movetime_ms": 10})
    saved = service.get_game("test", game["id"])
    assert saved["fen"] == game["fen"] and saved["version"] == 0 and not saved["moves"]


def test_real_human_black_engine_white_and_duplicate(service):
    game = service.create_game("test", {"mode": "engine", "human_color": "black", "time_seconds": 0, "skill_level": 5})
    payload = {"expected_version": 0, "request_id": "reply", "movetime_ms": 50}
    result = service.engine_move("test", game["id"], payload)
    assert len(result["moves"]) == 1 and result["turn"] == "black"
    duplicate = service.engine_move("test", game["id"], payload)
    assert duplicate["duplicate"] and duplicate["fen"] == result["fen"]
    with pytest.raises(ChessError) as error:
        service.engine_move("test", game["id"], {**payload, "movetime_ms": 60})
    assert error.value.code == "idempotency_conflict"


def test_stale_engine_response_rejected(service, monkeypatch):
    game = service.create_game("test", {"mode": "engine", "human_color": "black", "time_seconds": 0})
    def changed_during_search(board, **kwargs):
        service.action("test", game["id"], "resign", {"expected_version": 0, "request_id": "resign"})
        return {"bestmove": "e2e4", "lines": [], "engine": {"name": "fault fixture"}}
    monkeypatch.setattr(service.engine, "analyze", changed_during_search)
    with pytest.raises(ChessError) as error:
        service.engine_move("test", game["id"], {"expected_version": 0, "request_id": "reply", "movetime_ms": 50})
    assert error.value.code == "stale_version"
    assert not service.get_game("test", game["id"])["moves"]


def test_duplicate_job_cache_and_budget_identity(service):
    payload = {"fen": chess.STARTING_FEN, "depth": 8, "movetime_ms": 100, "multipv": 2}
    job = service.request_analysis("test", payload)
    duplicate = service.request_analysis("test", payload)
    assert duplicate["id"] == job["id"] and duplicate["duplicate"]
    completed = wait_job(service, job)
    assert completed["status"] == "completed"
    same = service.request_analysis("test", payload)
    assert same["duplicate"] and same["id"] == job["id"]
    different = service.request_analysis("test", {**payload, "depth": 9})
    assert different["cache_key"] != job["cache_key"] and different["id"] != job["id"]
    assert wait_job(service, different)["status"] == "completed"


def test_cache_engine_identity_mismatch(service, monkeypatch):
    payload = {"fen": chess.STARTING_FEN, "nodes": 100, "movetime_ms": 50, "multipv": 1}
    first = service.request_analysis("test", payload)
    assert wait_job(service, first)["status"] == "completed"
    original = service.engine.refresh_identity
    monkeypatch.setattr(service.engine, "refresh_identity", lambda: {**original(), "sha256": "different-engine-version"})
    other = service.request_analysis("test", payload)
    assert other["cache_key"] != first["cache_key"]
    assert wait_job(service, other)["status"] == "completed"


def test_restart_interrupted_job_recoverable(tmp_path):
    service = ChessService(tmp_path, STOCKFISH)
    job = {"id": "interrupted", "status": "running", "fen": chess.STARTING_FEN, "settings": {}, "cache_key": "fixture"}
    with service.storage.transaction() as db:
        db.execute("INSERT INTO analysis_jobs(id,owner,cache_key,state) VALUES(?,?,?,?)", (job["id"], "test", "fixture", json.dumps(job)))
    service.close()
    restarted = ChessService(tmp_path, STOCKFISH)
    assert restarted.get_analysis("test", "interrupted")["status"] == "interrupted"
    next_job = restarted.request_analysis("test", {"fen": chess.STARTING_FEN, "nodes": 100, "movetime_ms": 50, "multipv": 1})
    assert wait_job(restarted, next_job)["status"] == "completed"
    restarted.close()


@pytest.mark.parametrize("payload", [{"depth": 0}, {"depth": 41}, {"nodes": 5000001}, {"movetime_ms": 10001}, {"multipv": 9}])
def test_search_budget_exceeded_rejected(service, payload):
    with pytest.raises(ChessError):
        service.request_analysis("test", {"fen": chess.STARTING_FEN, **payload})


def test_missing_optional_tools_and_engine(tmp_path):
    adapter = EngineAdapter(tmp_path/"missing.exe")
    assert not adapter.identity()["available"]
    with pytest.raises(ChessError) as error:
        adapter.analyze(chess.Board(), movetime_ms=10)
    assert error.value.code == "engine_unavailable"
