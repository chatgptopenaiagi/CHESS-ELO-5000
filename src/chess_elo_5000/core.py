"""Transactional chess application. Historical game moves are separate from studies."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import hashlib
import io
import json
import math
import re
import threading
import time
import uuid
import chess
import chess.pgn
from .errors import ChessError
from .rules import valid_board, legal_move, position_id, facts
from .storage import Storage
from .engines import EngineAdapter, discover_engine


def integer(value, name, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        raise ChessError("invalid_input", f"{name} must be an integer from {lo} to {hi}")
    return value


class ChessService:
    def __init__(self, runtime_dir, engine_path=None, workspace=None):
        self.runtime_dir = Path(runtime_dir).resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.storage = Storage(self.runtime_dir / "chess.sqlite3")
        self.engine = EngineAdapter(engine_path or discover_engine(workspace or Path.cwd()))
        self.engine_path = self.engine.path
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chess-analysis")
        self.cancellations = {}
        self._job_lock = threading.RLock()
        # Explicit recovery at service initialization, never on a status read.
        with self.storage.transaction() as db:
            for row in db.execute("SELECT id,state FROM analysis_jobs"):
                job = json.loads(row["state"])
                if job["status"] in ("queued", "running"):
                    job.update(status="interrupted", error="Application restarted during analysis", updated_at=time.time())
                    db.execute("UPDATE analysis_jobs SET state=? WHERE id=?", (self.storage.encode(job), row["id"]))

    def close(self):
        for token in list(self.cancellations.values()):
            token.set()
        self.executor.shutdown(wait=True, cancel_futures=True)

    def _load(self, db, game_id, owner):
        row = db.execute("SELECT owner,state FROM games WHERE id=?", (game_id,)).fetchone()
        if not row or row["owner"] != owner:
            raise ChessError("not_found", "Game not found", 404)
        state = json.loads(row["state"])
        board = valid_board(state["starting_fen"])
        for item in state["moves"]:
            move = legal_move(board, item["uci"])
            board.push(move)
            if board.fen() != item["fen"]:
                raise ChessError("integrity_error", "Stored move replay differs from saved FEN", 500)
        if board.fen() != state["fen"]:
            raise ChessError("integrity_error", "Stored game replay differs from saved position", 500)
        return state, board

    @staticmethod
    def _clock(state, board, now):
        if state["status"] != "active" or state["mode"] == "study" or state["time_seconds"] == 0:
            return False
        key = "white_ms" if board.turn else "black_ms"
        elapsed = max(0, int((now - state["clock_anchor"]) * 1000))
        state[key] = max(0, state[key] - elapsed)
        state["clock_anchor"] = now
        if state[key] == 0:
            state["status"] = "finished"
            no_mating_material = board.has_insufficient_material(not board.turn)
            state["result"] = "1/2-1/2" if no_mating_material else "0-1" if board.turn else "1-0"
            state["reason"] = "time_forfeit_insufficient_mating_material" if no_mating_material else "time_forfeit"
            return True
        return False

    @staticmethod
    def _outcome(state, board):
        outcome = board.outcome(claim_draw=False)
        if outcome:
            state.update(status="finished", result=outcome.result(), reason=outcome.termination.name.lower())

    def _serialize(self, state, board, project_clock=True):
        state = json.loads(self.storage.encode(state))
        if project_clock:
            self._clock(state, board, time.time())
        state["turn"] = "white" if board.turn else "black"
        state["legal_moves"] = [m.uci() for m in board.legal_moves] if state["status"] == "active" else []
        state["piece_map"] = {chess.square_name(s): p.symbol() for s, p in board.piece_map().items()}
        state["check"] = board.is_check()
        state["terminal"] = state["status"] == "finished"
        state["position_id"] = position_id(board)
        state["last_move"] = state["moves"][-1]["uci"] if state["moves"] else None
        state["claimable_draws"] = []
        if state["status"] == "active":
            if board.can_claim_threefold_repetition():
                state["claimable_draws"].append("threefold_repetition")
            if board.can_claim_fifty_moves():
                state["claimable_draws"].append("fifty_moves")
        state.pop("owner", None)
        return state

    def _save(self, db, state, kind, payload):
        encoded = self.storage.encode(state)
        db.execute("UPDATE games SET state=? WHERE id=?", (encoded, state["id"]))
        db.execute("INSERT INTO positions(id,fen) VALUES(?,?) ON CONFLICT(id) DO NOTHING", (hashlib.sha256(state["fen"].encode()).hexdigest(), state["fen"]))
        db.execute("INSERT INTO game_events(game_id,kind,payload,created) VALUES(?,?,?,?)", (state["id"], kind, self.storage.encode({"schema_version": 1, **payload}), time.time()))

    def create_game(self, owner, payload):
        mode = payload.get("mode", "engine")
        human_color = payload.get("human_color", "white")
        if mode not in ("human", "engine", "study") or human_color not in ("white", "black"):
            raise ChessError("invalid_input", "Choose mode human/engine/study and color white/black")
        clock = integer(payload.get("time_seconds", 300), "time_seconds", 0, 86400)
        increment = integer(payload.get("increment_seconds", 0), "increment_seconds", 0, 600)
        skill = integer(payload.get("skill_level", 20), "skill_level", 0, 20)
        if payload.get("engine_id") and payload["engine_id"] != self.engine.identity()["id"]:
            raise ChessError("engine_unavailable", "Requested engine identity is not configured")
        board = valid_board(payload.get("fen"))
        now = time.time()
        state = {"id": uuid.uuid4().hex, "owner": owner, "mode": mode, "human_color": human_color, "skill_level": skill,
                 "starting_fen": board.fen(), "fen": board.fen(), "moves": [], "status": "active", "result": "*", "reason": None,
                 "version": 0, "white_ms": clock * 1000, "black_ms": clock * 1000, "time_seconds": clock,
                 "increment_seconds": increment, "clock_anchor": now, "created_at": now, "updated_at": now,
                 "white": str(payload.get("white", "Player" if human_color == "white" or mode != "engine" else "Stockfish"))[:100],
                 "black": str(payload.get("black", "Stockfish" if human_color == "white" and mode == "engine" else "Player"))[:100],
                 "captures": {"white": [], "black": []}, "draw_offer": None, "annotations": []}
        self._outcome(state, board)
        with self.storage.transaction() as db:
            db.execute("INSERT INTO games(id,owner,state) VALUES(?,?,?)", (state["id"], owner, self.storage.encode(state)))
            self._save(db, state, "GAME_CREATED", {"fen": board.fen()})
        return self._serialize(state, board)

    def get_game(self, owner, game_id):
        with closing(self.storage.connect()) as db:
            state, board = self._load(db, game_id, owner)
        return self._serialize(state, board)

    def list_games(self, owner):
        rows = self.storage.read("SELECT id FROM games WHERE owner=? ORDER BY rowid DESC LIMIT 200", (owner,))
        return [self.get_game(owner, r["id"]) for r in rows]

    def _mutate(self, owner, game_id, payload, kind, operation, fingerprint_payload=None):
        expected = integer(payload.get("expected_version"), "expected_version", 0, 100000)
        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ChessError("request_id_required", "Supply a unique request_id of 1..128 characters")
        fingerprint = hashlib.sha256(self.storage.encode({"kind": kind, **(fingerprint_payload if fingerprint_payload is not None else payload)}).encode()).hexdigest()
        with self.storage.transaction() as db:
            state, board = self._load(db, game_id, owner)
            prior = db.execute("SELECT payload_hash,response FROM game_operations WHERE game_id=? AND request_id=?", (game_id, request_id)).fetchone()
            if prior:
                if prior["payload_hash"] != fingerprint:
                    raise ChessError("idempotency_conflict", "request_id was already used for different input", 409)
                response = json.loads(prior["response"])
                response["duplicate"] = True
                return response
            if state["version"] != expected:
                raise ChessError("stale_version", "Game changed; reload the current version", 409)
            if state["status"] != "active" and kind != "STUDY_UNDO":
                raise ChessError("game_finished", "This game has finished", 409)
            flagged = self._clock(state, board, time.time())
            if not flagged:
                operation(db, state, board)
            state["version"] += 1
            state["fen"] = board.fen()
            state["updated_at"] = time.time()
            self._outcome(state, board)
            self._save(db, state, "GAME_FINISHED" if flagged else kind, {"version": state["version"], "fen": state["fen"], "result": state["result"]})
            response = self._serialize(state, board, project_clock=False)
            db.execute("INSERT INTO game_operations(game_id,request_id,payload_hash,response) VALUES(?,?,?,?)", (game_id, request_id, fingerprint, self.storage.encode(response)))
            return response

    def move(self, owner, game_id, payload, *, engine=False):
        def accepted(db, state, board):
            human_turn = board.turn == (state["human_color"] == "white")
            if state["mode"] == "engine" and human_turn == engine:
                raise ChessError("wrong_side", "This side is controlled by the engine" if not engine else "It is the human player's turn", 409)
            move = legal_move(board, payload.get("uci"))
            san = board.san(move)
            moving_color = "white" if board.turn else "black"
            if state["draw_offer"] and state["draw_offer"] != moving_color:
                state["draw_offer"] = None
            captured = board.piece_at(move.to_square)
            if board.is_en_passant(move):
                captured = chess.Piece(chess.PAWN, not board.turn)
            if captured:
                state["captures"]["white" if board.turn else "black"].append(captured.symbol())
            clock_key = "white_ms" if board.turn else "black_ms"
            if state["time_seconds"]:
                state[clock_key] += state["increment_seconds"] * 1000
            board.push(move)
            item = {"ply": len(state["moves"]) + 1, "uci": move.uci(), "san": san, "fen": board.fen(),
                    "white_ms": state["white_ms"], "black_ms": state["black_ms"]}
            state["moves"].append(item)
            # Historical rows are immutable. Undo operates only on a separate study state.
            db.execute("INSERT INTO moves(game_id,ply,uci,san,fen) VALUES(?,?,?,?,?)", (game_id, item["ply"], item["uci"], item["san"], item["fen"]))
            state["clock_anchor"] = time.time()
            if engine:
                state["last_engine_run"] = payload.get("engine_run")
        return self._mutate(owner, game_id, payload, "ENGINE_MOVE_ACCEPTED" if engine else "MOVE_ACCEPTED", accepted, payload.get("_engine_request") if engine else None)

    def engine_move(self, owner, game_id, payload):
        # Check duplicate before performing expensive work.
        integer(payload.get("expected_version"), "expected_version", 0, 100000)
        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ChessError("request_id_required", "Supply a unique request_id of 1..128 characters")
        prior = self.storage.read("SELECT payload_hash,response FROM game_operations WHERE game_id=? AND request_id=?", (game_id, request_id))
        if prior:
            existing = self.get_game(owner, game_id)
            if existing["mode"] != "engine":
                raise ChessError("invalid_mode", "Engine replies require engine game mode")
            fingerprint = hashlib.sha256(self.storage.encode({"kind": "ENGINE_MOVE_ACCEPTED", **payload}).encode()).hexdigest()
            if prior[0]["payload_hash"] != fingerprint:
                raise ChessError("idempotency_conflict", "request_id was already used for different engine input", 409)
            return {**json.loads(prior[0]["response"]), "duplicate": True}
        with closing(self.storage.connect()) as db:
            state, board = self._load(db, game_id, owner)
        if state["mode"] != "engine" or board.turn == (state["human_color"] == "white"):
            raise ChessError("wrong_side", "It is not the configured engine's turn", 409)
        if state["version"] != payload.get("expected_version"):
            raise ChessError("stale_version", "Game changed before engine search", 409)
        request = {"movetime_ms": integer(payload.get("movetime_ms", 500), "movetime_ms", 10, 10000), "multipv": 1, "skill": state["skill_level"]}
        result = self.engine.analyze(board, **request)
        run_id = self._record_run(owner, result, board.fen())
        clean = {**payload, "uci": result["bestmove"], "engine_run": run_id, "_engine_request": payload}
        return self.move(owner, game_id, clean, engine=True)

    def action(self, owner, game_id, action, payload):
        def apply(db, state, board):
            if action == "resign":
                color = state["human_color"] if state["mode"] == "engine" else ("white" if board.turn else "black")
                state.update(status="finished", result="0-1" if color == "white" else "1-0", reason="resignation")
            elif action == "draw":
                kind = payload.get("kind", "claim")
                if kind == "claim":
                    claim_board = board.copy(stack=True)
                    if payload.get("uci"):
                        claim_board.push(legal_move(claim_board, payload["uci"]))
                    if not (claim_board.is_repetition(3) or claim_board.is_fifty_moves()):
                        raise ChessError("draw_not_claimable", "No threefold or fifty-move draw is currently claimable")
                    state.update(status="finished", result="1/2-1/2", reason="claimed_draw")
                elif kind == "offer":
                    if state["mode"] == "engine":
                        raise ChessError("unsupported_draw_offer", "This UCI opponent does not negotiate draws; valid draw claims remain supported")
                    state["draw_offer"] = "white" if board.turn else "black"
                elif kind == "accept" and state["draw_offer"] and state["mode"] != "engine" and state["draw_offer"] != ("white" if board.turn else "black"):
                    state.update(status="finished", result="1/2-1/2", reason="draw_agreement")
                else:
                    raise ChessError("draw_not_offered", "A local two-player draw offer is required")
            elif action == "undo":
                if state["mode"] != "study":
                    raise ChessError("study_only", "Undo is allowed only in a study; archive history is preserved", 409)
                if not state["moves"]:
                    raise ChessError("no_move", "Study is at its starting position")
                state["moves"].pop()
                board.pop()
                state.update(status="active", result="*", reason=None)
                replay = valid_board(state["starting_fen"])
                state["captures"] = {"white": [], "black": []}
                for item in state["moves"]:
                    move = legal_move(replay, item["uci"])
                    captured = replay.piece_at(move.to_square)
                    if replay.is_en_passant(move):
                        captured = chess.Piece(chess.PAWN, not replay.turn)
                    if captured:
                        state["captures"]["white" if replay.turn else "black"].append(captured.symbol())
                    replay.push(move)
                # These rows describe an editable study, never historical games.
                db.execute("DELETE FROM moves WHERE game_id=? AND ply>?", (game_id, len(state["moves"])))
            elif action == "tick":
                pass
            else:
                raise ChessError("unknown_action", "Unsupported game action")
        return self._mutate(owner, game_id, payload, "STUDY_UNDO" if action == "undo" else action.upper(), apply)

    def export_pgn(self, owner, game_id):
        state = self.get_game(owner, game_id)
        if state.get("imported_pgn"):
            original = chess.pgn.read_game(io.StringIO(state["imported_pgn"]))
            if [m.uci() for m in original.mainline_moves()] == [m["uci"] for m in state["moves"]]:
                original.headers["Result"] = state["result"]
                return original.accept(chess.pgn.StringExporter(headers=True, variations=True, comments=True)) + "\n"
        game = chess.pgn.Game()
        game.setup(valid_board(state["starting_fen"]))
        game.headers.update(Event="CHESS ELO 5000 local game", Site="Local", Date=time.strftime("%Y.%m.%d", time.gmtime(state["created_at"])),
                            White=state["white"], Black=state["black"], Result=state["result"], TimeControl=f'{state["time_seconds"]}+{state["increment_seconds"]}')
        node = game
        for item in state["moves"]:
            node = node.add_variation(chess.Move.from_uci(item["uci"]))
        return game.accept(chess.pgn.StringExporter(headers=True, variations=True, comments=True)) + "\n"

    def import_pgn(self, owner, pgn):
        if not isinstance(pgn, str) or not pgn.strip() or len(pgn) > 2_000_000:
            raise ChessError("invalid_pgn", "Supply a nonempty PGN under 2 MB")
        stream = io.StringIO(pgn)
        try:
            # python-chess deliberately tolerates unrecognized PGN text. This application
            # rejects residual tokens instead of silently importing a truncated record.
            text = re.sub(r'^\s*\[[A-Za-z][A-Za-z0-9_]*\s+"(?:[^"\\]|\\.)*"\]\s*$', '', pgn, flags=re.M)
            text = re.sub(r'^%[^\n]*', '', text, flags=re.M)
            text = re.sub(r';[^\n]*', '', text)
            text = re.sub(r'\{[^{}]*\}', ' ', text, flags=re.S)
            nesting = 0
            for character in text:
                nesting += 1 if character == '(' else -1 if character == ')' else 0
                if nesting < 0:
                    raise ValueError("Unbalanced PGN variation")
            if nesting:
                raise ValueError("Unbalanced PGN variation")
            text = re.sub(r'\d+\.(?:\.\.)?|\$\d+|1/2-1/2|1-0|0-1|\*|O-O(?:-O)?[+#]?|0-0(?:-0)?[+#]?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?|e\.p\.|[()!?]', ' ', text)
            if text.strip():
                raise ValueError("Unrecognized or malformed PGN text")
            parsed = chess.pgn.read_game(stream)
            if not parsed or parsed.errors:
                raise ValueError("PGN parser reported illegal moves")
            if chess.pgn.read_game(stream) is not None:
                raise ValueError("Import exactly one game at a time")
            board = valid_board(parsed.board().fen())
            moves = []
            for move in parsed.mainline_moves():
                if move not in board.legal_moves:
                    raise ValueError("Illegal move in PGN")
                san = board.san(move)
                board.push(move)
                moves.append({"ply": len(moves)+1, "uci": move.uci(), "san": san, "fen": board.fen()})
            if not moves and not any(k in pgn for k in ("[Event", "[FEN")):
                raise ValueError("No game headers or legal moves")
            actual = board.outcome(claim_draw=False)
            claimed = parsed.headers.get("Result", "*")
            if claimed not in ("*", "1-0", "0-1", "1/2-1/2") or (actual and claimed not in ("*", actual.result())):
                raise ValueError("PGN result contradicts the terminal position")
        except (ValueError, TypeError, ChessError) as exc:
            raise ChessError("invalid_pgn", str(exc)) from exc
        created = self.create_game(owner, {"mode": "study", "time_seconds": 0, "fen": parsed.board().fen(), "white": parsed.headers.get("White", "White"), "black": parsed.headers.get("Black", "Black")})
        with self.storage.transaction() as db:
            state, unused = self._load(db, created["id"], owner)
            state.update(moves=moves, fen=board.fen(), imported_headers=dict(parsed.headers), result=actual.result() if actual else claimed,
                         status="finished" if actual or claimed != "*" else "active", reason=actual.termination.name.lower() if actual else "imported_result" if claimed != "*" else None,
                         imported_pgn=parsed.accept(chess.pgn.StringExporter(headers=True, variations=True, comments=True)))
            for item in moves:
                db.execute("INSERT INTO moves(game_id,ply,uci,san,fen) VALUES(?,?,?,?,?)", (state["id"], item["ply"], item["uci"], item["san"], item["fen"]))
            self._save(db, state, "PGN_IMPORTED", {"moves": len(moves), "result": state["result"]})
        return self.get_game(owner, created["id"])

    def variation(self, owner, game_id, payload):
        with self.storage.transaction() as db:
            parent, board = self._load(db, game_id, owner)
            ply = integer(payload.get("ply", len(parent["moves"])), "ply", 0, len(parent["moves"]))
            board = valid_board(parent["starting_fen"])
            for item in parent["moves"][:ply]:
                board.push(legal_move(board, item["uci"]))
            starting = board.fen()
            moves = payload.get("moves", [])
            if not isinstance(moves, list) or len(moves) > 200:
                raise ChessError("invalid_variation", "Variation moves must be a list of at most 200 UCI moves")
            verified = []
            for uci in moves:
                move = legal_move(board, uci)
                san = board.san(move)
                board.push(move)
                verified.append({"uci": uci, "san": san, "fen": board.fen()})
            state = {"id": uuid.uuid4().hex, "parent_id": game_id, "parent_ply": ply, "starting_fen": starting,
                     "fen": board.fen(), "moves": verified, "name": str(payload.get("name", "Study variation"))[:100],
                     "created_at": time.time(), "kind": "HYPOTHETICAL VARIATION", "position_id": position_id(board),
                     "engine_identity": payload.get("engine_identity"), "evaluation": payload.get("evaluation"), "search_budget": payload.get("search_budget")}
            db.execute("INSERT INTO variations(id,owner,parent_id,state) VALUES(?,?,?,?)", (state["id"], owner, game_id, self.storage.encode(state)))
            return state

    def list_variations(self, owner, game_id):
        self.get_game(owner, game_id)
        return [json.loads(r["state"]) for r in self.storage.read("SELECT state FROM variations WHERE owner=? AND parent_id=? ORDER BY rowid", (owner, game_id))]

    def _record_run(self, owner, result, fen):
        run_id = uuid.uuid4().hex
        with self.storage.transaction() as db:
            db.execute("INSERT INTO engine_runs(id,owner,state) VALUES(?,?,?)", (run_id, owner, self.storage.encode({"id": run_id, "fen": fen, "created_at": time.time(), **result})))
        return run_id

    def request_analysis(self, owner, payload):
        board = valid_board(payload.get("fen"))
        settings = {"depth": payload.get("depth"), "nodes": payload.get("nodes"), "movetime_ms": payload.get("movetime_ms", 1500), "multipv": payload.get("multipv", 3)}
        # Validate all budget constraints before a job is accepted.
        if settings["depth"] is not None:
            integer(settings["depth"], "depth", 1, 40)
        if settings["nodes"] is not None:
            integer(settings["nodes"], "nodes", 1, 5_000_000)
        integer(settings["movetime_ms"], "movetime_ms", 10, 10000)
        integer(settings["multipv"], "multipv", 1, 8)
        identity = self.engine.refresh_identity()
        key_data = {"fen": board.fen(en_passant="fen"), "engine_sha256": identity["sha256"], "threads": self.engine.threads, "hash_mb": self.engine.hash_mb, **settings}
        cache_key = hashlib.sha256(self.storage.encode(key_data).encode()).hexdigest()
        with self._job_lock, self.storage.transaction() as db:
            for row in db.execute("SELECT state FROM analysis_jobs WHERE owner=? AND cache_key=? ORDER BY rowid DESC", (owner, cache_key)):
                prior = json.loads(row["state"])
                if prior["status"] in ("queued", "running", "completed"):
                    return {**prior, "duplicate": True}
            cache = db.execute("SELECT result FROM engine_evaluations WHERE cache_key=?", (cache_key,)).fetchone()
            job = {"id": uuid.uuid4().hex, "status": "completed" if cache else "queued", "fen": board.fen(), "settings": settings,
                   "cache_key": cache_key, "cache_hit": bool(cache), "created_at": time.time(), "updated_at": time.time()}
            if cache:
                job["result"] = json.loads(cache["result"])
            db.execute("INSERT INTO analysis_jobs(id,owner,cache_key,state) VALUES(?,?,?,?)", (job["id"], owner, cache_key, self.storage.encode(job)))
        if not cache:
            token = threading.Event()
            self.cancellations[job["id"]] = token
            self.executor.submit(self._analyze_job, owner, job["id"], token)
        return job

    def get_analysis(self, owner, job_id):
        rows = self.storage.read("SELECT state FROM analysis_jobs WHERE id=? AND owner=?", (job_id, owner))
        if not rows:
            raise ChessError("not_found", "Analysis job not found", 404)
        return json.loads(rows[0]["state"])

    def list_analysis(self, owner):
        return [json.loads(row["state"]) for row in self.storage.read("SELECT state FROM analysis_jobs WHERE owner=? ORDER BY rowid DESC LIMIT 100", (owner,))]

    def cancel_analysis(self, owner, job_id):
        job = self.get_analysis(owner, job_id)
        if job["status"] in ("queued", "running"):
            self.cancellations.get(job_id, threading.Event()).set()
            self._update_job(owner, job_id, status="cancelled", error="Cancelled by owner")
        return self.get_analysis(owner, job_id)

    def _update_job(self, owner, job_id, **updates):
        with self.storage.transaction() as db:
            row = db.execute("SELECT state FROM analysis_jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            job = json.loads(row["state"])
            if job["status"] == "cancelled" and updates.get("status") != "cancelled":
                return
            job.update(updates, updated_at=time.time())
            db.execute("UPDATE analysis_jobs SET state=? WHERE id=?", (self.storage.encode(job), job_id))

    def _analyze_job(self, owner, job_id, cancel):
        try:
            if cancel.is_set():
                return
            self._update_job(owner, job_id, status="running")
            job = self.get_analysis(owner, job_id)
            result = self.engine.analyze(valid_board(job["fen"]), cancel=cancel, **job["settings"])
            if cancel.is_set():
                return
            result["run_id"] = self._record_run(owner, result, job["fen"])
            with self.storage.transaction() as db:
                db.execute("INSERT OR IGNORE INTO engine_evaluations(cache_key,result) VALUES(?,?)", (job["cache_key"], self.storage.encode(result)))
            self._update_job(owner, job_id, status="completed", result=result)
        except Exception as exc:
            self._update_job(owner, job_id, status="cancelled" if cancel.is_set() else "failed", error=str(exc), error_code=getattr(exc, "code", "analysis_failed"))
        finally:
            self.cancellations.pop(job_id, None)
