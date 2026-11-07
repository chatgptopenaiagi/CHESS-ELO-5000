"""Independent regression review of chess research boundaries and evidence claims."""
import copy
import json
import math
import chess
import pytest
from chess_elo_5000 import create_app
from chess_elo_5000.research import content, ranking
from chess_elo_5000.research.laboratory import dataset, score_order
from chess_elo_5000.research.search import search


@pytest.mark.parametrize("fen", [
    "7k/8/8/8/8/8/8/7K w - - 0 1",
    "7k/8/8/8/8/8/R7/7K w - - 150 76",
    "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1",
    "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1",
])
def test_transparent_search_does_not_move_after_automatic_termination(fen):
    board = chess.Board(fen)
    assert board.is_valid() and board.outcome(claim_draw=False)
    result = search(board, 100)
    assert result["move"] is None and result["terminal"] is True


def test_transparent_search_budget_and_input_preservation():
    board = content.board_after("e4 e5 Nf3 Nc6 Bb5 a6")
    before, stack = board.fen(), list(board.move_stack)
    result = search(board, 120)
    assert result["nodes"] <= 120 and result["budget"] == 120
    assert board.fen() == before and board.move_stack == stack
    replay = board.copy(stack=True)
    for uci in result["pv"]:
        move = chess.Move.from_uci(uci)
        assert move in replay.legal_moves
        replay.push(move)


@pytest.mark.parametrize("budget", [0, -1, True, 1_000_001, float("nan")])
def test_transparent_search_invalid_budget(budget):
    with pytest.raises(ValueError):
        search(chess.Board(), budget)


def test_mate_scores_are_ordered_outside_centipawns_for_both_colors():
    order = [{"type": "mate", "value": 1}, {"type": "mate", "value": 3},
             {"type": "cp", "value": 999999}, {"type": "cp", "value": -999999},
             {"type": "mate", "value": -3}, {"type": "mate", "value": -1}]
    assert sorted(order, key=lambda x: score_order(x, chess.WHITE), reverse=True) == order
    black_order = [{**item, "value": -item["value"]} for item in order]
    assert sorted(black_order, key=lambda x: score_order(x, chess.BLACK), reverse=True) == black_order


def test_frozen_model_rejects_validation_heldout_and_nonfinite_training():
    features = ranking.features(chess.Board(), chess.Move.from_uci("e2e4"))
    row = {"features": features, "label": 0.7, "split": "TRAIN", "group": "one"}
    model = ranking.fit([row])
    assert math.isfinite(ranking.predict(features, model))
    for split in ("VALIDATION", "HELD_OUT"):
        with pytest.raises(ValueError):
            ranking.fit([{**row, "split": split}])
    corrupted = copy.deepcopy(model)
    corrupted["coefficients"][0] += 1
    with pytest.raises(ValueError):
        ranking.predict(features, corrupted)
    bad = {**features, "intercept": float("nan")}
    with pytest.raises(ValueError):
        ranking.fit([{**row, "features": bad}])
    with pytest.raises(ValueError):
        ranking.predict(bad, model)


@pytest.mark.parametrize("seed", [0, 1, 7331])
def test_dataset_group_and_mirrored_transposition_splits(seed):
    records = dataset(seed)
    group_splits, positions = {}, {}
    for row in records:
        assert row["group"] not in group_splits or group_splits[row["group"]] == row["split"]
        group_splits[row["group"]] = row["split"]
        board = chess.Board(row["fen"])
        identity = min(ranking.position_id(board), ranking.position_id(board.mirror()))
        assert identity not in positions or positions[identity] == row["split"]
        positions[identity] = row["split"]
    assert {r["split"] for r in records} == {"TRAIN", "VALIDATION", "HELD_OUT"}


@pytest.mark.parametrize("policy", ["uniform", "heuristic", "learned"])
def test_every_legal_candidate_gets_positive_equal_total_budget(policy):
    board = chess.Board()
    rows = ranking.rank(board)
    for row in rows:
        row["learned_score"] = row["heuristic_score"] / 100
    allocation = ranking.allocate(rows, 1001, policy)
    assert set(allocation) == {m.uci() for m in board.legal_moves}
    assert sum(allocation.values()) == 1001 and min(allocation.values()) >= 1


def test_playable_content_is_legal_and_mate_solutions_match_stated_objective():
    for row in content.lessons() + content.studies():
        board = chess.Board(row["fen"])
        assert board.is_valid()
        for uci in row.get("solution", row.get("moves", [])):
            move = chess.Move.from_uci(uci)
            assert move in board.legal_moves
            board.push(move)
    for row in content.puzzles():
        board = chess.Board(row["fen"])
        accepted = {m.uci() for m in board.legal_moves if content.puzzle_objective(board, m, row)}
        assert accepted == set(row["solutions"])
        assert row["unique_under_objective"] == (len(accepted) == 1)


def test_missing_optional_engine_does_not_block_ordinary_chess(tmp_path, monkeypatch):
    import chess_elo_5000.core as core
    monkeypatch.setattr(core, "discover_engine", lambda workspace: None)
    app = create_app(tmp_path, testing=True)
    try:
        app.config["OWNER_PASSWORD"] = "test-owner"
        client = app.test_client()
        assert client.get("/api/v1/system/status").json["engine_available"] is False
        session = client.post("/api/v1/session", json={"password": "test-owner"}).json
        response = client.post("/api/v1/games", json={"mode": "human", "time_seconds": 0}, headers={"X-CSRF-Token": session["csrf_token"]})
        assert response.status_code == 201 and len(response.json["legal_moves"]) == 20
    finally:
        if "research_lab" in app.extensions:
            app.extensions["research_lab"].shutdown()
        app.extensions["chess_service"].close()


def test_deterministic_coach_refuses_illegal_concrete_line(tmp_path):
    app = create_app(tmp_path, testing=True)
    app.config["OWNER_PASSWORD"] = "test-owner"
    try:
        client = app.test_client()
        session = client.post("/api/v1/session", json={"password": "test-owner"}).json
        response = client.post("/api/v1/coach", json={"fen": chess.STARTING_FEN, "moves": ["e2e5"]}, headers={"X-CSRF-Token": session["csrf_token"]})
        assert response.status_code == 400
        assert "ILLEGAL" in response.json["message"]
    finally:
        app.extensions["research_lab"].shutdown()
        app.extensions["chess_service"].close()


def test_coach_uses_only_owned_matching_completed_engine_evidence(tmp_path):
    app = create_app(tmp_path, testing=True)
    app.config["OWNER_PASSWORD"] = "test-owner"
    service = app.extensions["chess_service"]
    # Boundary fixture exercises provenance selection; actual Stockfish execution
    # has its independent test_core_engines.py acceptance.
    job = {"id": "coach-boundary-fixture", "status": "completed", "fen": chess.STARTING_FEN,
           "result": {"engine": {"name": "Boundary fixture"}, "lines": [{"pv": ["e2e4", "e7e5"], "score": {"type": "cp", "value": 17, "perspective": "white"}}]}}
    with service.storage.transaction() as db:
        db.execute("INSERT INTO analysis_jobs(id,owner,cache_key,state) VALUES(?,?,?,?)", (job["id"], "local-owner", "coach", json.dumps(job)))
    try:
        client = app.test_client()
        session = client.post("/api/v1/session", json={"password": "test-owner"}).json
        headers = {"X-CSRF-Token": session["csrf_token"]}
        good = client.post("/api/v1/coach", json={"fen": chess.STARTING_FEN, "analysis_id": job["id"]}, headers=headers)
        assert good.status_code == 200
        assert any(f["kind"] == "ENGINE_EVALUATION" for f in good.json["facts"])
        other = chess.Board()
        other.push_uci("e2e4")
        wrong_position = client.post("/api/v1/coach", json={"fen": other.fen(), "analysis_id": job["id"]}, headers=headers)
        assert wrong_position.status_code == 400
        with service.storage.transaction() as db:
            db.execute("UPDATE analysis_jobs SET owner='other-owner' WHERE id=?", (job["id"],))
        wrong_owner = client.post("/api/v1/coach", json={"fen": chess.STARTING_FEN, "analysis_id": job["id"]}, headers=headers)
        assert wrong_owner.status_code == 404
    finally:
        app.extensions["research_lab"].shutdown()
        service.close()
