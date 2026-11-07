"""Exercise an extracted development package through its real owned backend.

Run only after extraction and offline dependency provisioning. Credentials remain
in process memory; receipts contain source/engine identities and test outcomes.
This checks process/API/storage behavior. Browser and Joomla administrator
acceptance have separate receipts and are not inferred from this script.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unused_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class PackageAcceptance:
    def __init__(self, workspace, output):
        self.workspace = workspace.resolve()
        self.output = output.resolve()
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.runtime = self.workspace / "runtime" / ("acceptance-" + uuid.uuid4().hex[:12])
        self.runtime.mkdir(parents=True, exist_ok=False)
        self.python = self.workspace / ".venv/Scripts/python.exe"
        if not self.python.is_file():
            alternative = self.workspace / ".venv/bin/python"
            self.python = alternative if alternative.is_file() else Path(sys.executable)
        self.engine = self.workspace / "stockfish/stockfish/stockfish-windows-x86-64-universal.exe"
        self.port = unused_port()
        self.base = "http://127.0.0.1:" + str(self.port)
        self.password = secrets.token_urlsafe(36)
        self.bridge_secret = secrets.token_hex(32)
        self.env = dict(os.environ)
        self.env.update(PYTHONPATH=str(self.workspace / "src"), CHESS_WORKSPACE=str(self.workspace),
                        CHESS_RUNTIME_DIR=str(self.runtime), CHESS_ENGINE_PATH=str(self.engine),
                        CHESS_OWNER_PASSWORD=self.password, CHESS_BRIDGE_SECRET=self.bridge_secret,
                        PYTHONUNBUFFERED="1", PYTHONNOUSERSITE="1")
        self.process = None
        self.log_handle = None
        self.opener = None
        self.csrf = None
        self.receipt = {"schema_version": "chesselo5000.extracted-package-acceptance/1", "status": "RUNNING",
                        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "workspace": str(self.workspace), "runtime": str(self.runtime), "python": str(self.python),
                        "python_from_extracted_venv": self.python.is_relative_to(self.workspace / ".venv"),
                        "backend_url": self.base, "checks": [], "owned_process_ids": [],
                        "scope": "Extracted package real backend process, authenticated APIs, UCI engine, restart and databases. Browser/Joomla acceptance is separate."}

    def check(self, name, condition, detail=None):
        self.receipt["checks"].append({"name": name, "status": "PASS" if condition else "FAIL", **({"detail": detail} if detail is not None else {})})
        if not condition:
            raise AssertionError(name)

    def python_call(self, code, payload=None):
        result = subprocess.run([str(self.python), "-c", code], cwd=self.workspace, env=self.env,
                                input=json.dumps(payload) if payload is not None else None,
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            # No credentials are passed to this helper or included in its errors.
            raise RuntimeError("Extracted Python verification failed: " + result.stderr[-1500:])
        return json.loads(result.stdout)

    def start(self):
        self.log_handle = (self.runtime / "backend.log").open("a", encoding="utf-8")
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.process = subprocess.Popen([str(self.python), "-m", "chess_elo_5000", "--host", "127.0.0.1", "--port", str(self.port),
                                         "--runtime", str(self.runtime), "--engine", str(self.engine)],
                                        cwd=self.workspace, env=self.env, stdin=subprocess.DEVNULL,
                                        stdout=self.log_handle, stderr=subprocess.STDOUT, creationflags=flags)
        self.receipt["owned_process_ids"].append(self.process.pid)
        end = time.monotonic() + 30
        while time.monotonic() < end:
            if self.process.poll() is not None:
                raise RuntimeError("Owned extracted backend exited before becoming ready")
            try:
                with urllib.request.urlopen(self.base + "/api/v1/system/status", timeout=1) as response:
                    status = json.load(response)
                if status.get("status") == "ready":
                    self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                    self.csrf = None
                    return status
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(0.1)
        raise TimeoutError("Extracted backend did not become ready within 30 seconds")

    def stop(self):
        process = self.process
        if process is not None and process.poll() is None:
            if os.name == "nt":
                # Popen is the authority for this exact PID. Windows venv redirectors
                # can own a child interpreter, so terminate only this owned tree.
                killer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/taskkill.exe"
                result = subprocess.run([str(killer), "/PID", str(process.pid), "/T", "/F"],
                                        capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode and process.poll() is None:
                    process.kill()
            else:
                process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process is not None:
            end = time.monotonic() + 5
            listening = True
            while time.monotonic() < end:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(0.2)
                    listening = sock.connect_ex(("127.0.0.1", self.port)) == 0
                if not listening:
                    break
                time.sleep(0.1)
            if listening:
                raise RuntimeError("Owned backend tree still listens after termination; restart acceptance refused")
        self.process = None
        if self.log_handle:
            self.log_handle.close()
            self.log_handle = None

    def request(self, method, path, payload=None, *, raw=False, expected=200):
        data = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=20) as response:
                status, content = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, content = exc.code, exc.read()
        if status != expected:
            try:
                diagnostic = json.loads(content)
                message = str(diagnostic.get("error", "HTTP failure")) + ": " + str(diagnostic.get("message", ""))
            except ValueError:
                message = "Unexpected non-JSON HTTP response"
            raise RuntimeError(f"{method} {path}: HTTP {status}, expected {expected}; {message}")
        return content.decode("utf-8") if raw else json.loads(content)

    def login(self):
        result = self.request("POST", "/api/v1/session", {"password": self.password})
        self.csrf = result["csrf_token"]
        self.check("authenticated_owner_session", result.get("user") == "local-owner" and bool(self.csrf))

    def move(self, game, uci):
        self.check("submitted_move_is_server_legal_" + str(len(game["moves"]) + 1), uci in game["legal_moves"])
        return self.request("POST", "/api/v1/games/" + game["id"] + "/moves",
                            {"uci": uci, "expected_version": game["version"], "request_id": uuid.uuid4().hex})

    def await_analysis(self, job):
        end = time.monotonic() + 20
        while time.monotonic() < end:
            current = self.request("GET", "/api/v1/analysis/" + job["id"])
            if current["status"] not in ("queued", "running"):
                self.check("bounded_analysis_completed", current["status"] == "completed", {"status": current["status"], "error": current.get("error")})
                return current
            time.sleep(0.05)
        raise TimeoutError("Analysis job exceeded the package acceptance deadline")

    def database_count(self, table):
        if table not in ("engine_runs", "analysis_jobs"):
            raise ValueError("Unknown internal count table")
        with closing(sqlite3.connect((self.runtime / "chess.sqlite3").as_uri() + "?mode=ro", uri=True)) as db:
            return db.execute("SELECT count(*) FROM " + table).fetchone()[0]

    def run(self):
        self.check("extracted_source_present", (self.workspace / "src/chess_elo_5000/api.py").is_file())
        self.check("extracted_stockfish_present", self.engine.is_file())
        self.receipt["engine_sha256"] = sha256(self.engine)
        build_info = self.workspace / "build-info.json"
        self.check("archive_source_identity_present", build_info.is_file())
        build = json.loads(build_info.read_text(encoding="utf-8-sig"))
        self.receipt["source_identity"] = build
        probe = self.python_call("import os,sys,json,importlib.metadata as m,chess,flask,chess_elo_5000; print(json.dumps({'cwd':os.getcwd(),'python':sys.executable,'modules':{'product':chess_elo_5000.__file__,'chess':chess.__file__,'flask':flask.__file__},'versions':{'chess':m.version('chess'),'flask':m.version('flask')},'foreign_imports':[k for k in sys.modules if k.startswith('dragonhydra')]}))")
        self.receipt["runtime_bindings"] = probe
        self.check("product_imported_from_extracted_source", Path(probe["modules"]["product"]).resolve().is_relative_to(self.workspace / "src"))
        self.check("execution_cwd_is_extracted_workspace", Path(probe["cwd"]).resolve() == self.workspace)
        self.check("no_dragonhydra_module_or_runtime_dependency", not probe["foreign_imports"] and all("dragonhydra" not in value.lower() for value in probe["modules"].values()))
        status = self.start()
        self.check("independent_backend_started", status.get("product") == "CHESS ELO 5000")
        page = self.request("GET", "/", raw=True)
        self.check("extracted_web_client_served", "CHESS" in page.upper() and "<html" in page.lower())
        self.request("GET", "/api/v1/games", expected=401)
        self.check("anonymous_saved_game_access_denied", True)
        self.login()

        game = self.request("POST", "/api/v1/games", {"mode": "human", "time_seconds": 0}, expected=201)
        self.check("standard_board_has_twenty_legal_moves", len(game["legal_moves"]) == 20)
        for uci in ("f2f3", "e7e5", "g2g4", "d8h4"):
            game = self.move(game, uci)
        mate_fen = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"
        self.check("complete_fools_mate_terminal_game", game["status"] == "finished" and game["result"] == "0-1" and game["reason"] == "checkmate" and game["fen"] == mate_fen)
        pgn = self.request("GET", "/api/v1/games/" + game["id"] + "/pgn", raw=True)
        study = self.request("POST", "/api/v1/studies/import", {"pgn": pgn}, expected=201)
        self.check("pgn_export_import_separate_study_exact_final_fen", study["id"] != game["id"] and study["fen"] == game["fen"] and study["result"] == game["result"] and len(study["moves"]) == 4)
        variation = self.request("POST", "/api/v1/games/" + game["id"] + "/variations", {"ply": 1, "moves": ["e7e6", "e2e4"], "name": "Extracted package hypothetical continuation"}, expected=201)
        unchanged = self.request("GET", "/api/v1/games/" + game["id"])
        self.check("variation_ancestry_preserves_historical_parent", variation["parent_id"] == game["id"] and variation["parent_ply"] == 1 and unchanged["fen"] == game["fen"] and unchanged["moves"] == game["moves"])

        engine_game = self.request("POST", "/api/v1/games", {"mode": "engine", "human_color": "white", "time_seconds": 0, "skill_level": 20}, expected=201)
        engine_game = self.move(engine_game, "e2e4")
        legal_replies = set(engine_game["legal_moves"])
        engine_started = time.monotonic()
        engine_game = self.request("POST", "/api/v1/games/" + engine_game["id"] + "/engine", {"expected_version": engine_game["version"], "request_id": uuid.uuid4().hex, "movetime_ms": 150})
        elapsed = time.monotonic() - engine_started
        self.check("real_human_engine_reply_is_legal_and_bounded", len(engine_game["moves"]) == 2 and engine_game["moves"][-1]["uci"] in legal_replies and bool(engine_game.get("last_engine_run")) and elapsed < 12,
                   {"human_move": "e2e4", "engine_reply": engine_game["moves"][-1]["uci"], "elapsed_seconds": round(elapsed, 4)})
        analysis_payload = {"fen": engine_game["fen"], "depth": 12, "movetime_ms": 500, "multipv": 3}
        job = self.request("POST", "/api/v1/analysis", analysis_payload, expected=202)
        completed = self.await_analysis(job)
        result = completed["result"]
        self.check("actual_stockfish_identity_and_three_pv_lines", result["engine"]["name"] == "Stockfish 19" and result["engine"]["sha256"].lower() == self.receipt["engine_sha256"].lower() and len(result["lines"]) == 3 and result["nodes"] > 0)
        pv_probe = self.python_call("import sys,json,chess; d=json.load(sys.stdin); n=0;\nfor line in d['lines']:\n b=chess.Board(d['fen'])\n for uci in line['pv']:\n  move=chess.Move.from_uci(uci)\n  assert move in b.legal_moves\n  b.push(move); n+=1\n assert line['score']['type'] in ('cp','mate') and line['score']['perspective']=='white'\nprint(json.dumps({'verified_lines':len(d['lines']),'verified_moves':n}))", {"fen": engine_game["fen"], "lines": result["lines"]})
        self.check("independently_replayed_all_analysis_principal_variations", pv_probe["verified_lines"] == 3 and pv_probe["verified_moves"] >= 3, pv_probe)
        self.receipt["analysis_evidence"] = {"job_id": job["id"], "engine_name": result["engine"]["name"], "nodes": result["nodes"], "elapsed_seconds": result["elapsed_seconds"],
                                             "lines": [{"score": line["score"], "pv": line["pv"], "depth": line["depth"], "nodes": line["nodes"]} for line in result["lines"]]}
        cached = self.request("POST", "/api/v1/analysis", analysis_payload, expected=202)
        self.check("duplicate_analysis_reuses_completed_identity", cached["id"] == completed["id"] and cached.get("duplicate") is True)

        before_reads = self.database_count("engine_runs")
        status = self.request("GET", "/api/v1/system/status")
        tools = self.request("GET", "/api/v1/system/tools")
        self.request("GET", "/api/v1/engines")
        self.check("read_only_status_does_not_run_engine", self.database_count("engine_runs") == before_reads)
        self.check("optional_ai_and_tablebase_absence_are_honest", status["optional_ai"] == "UNCONFIGURED" and status["tablebases"] == "UNCONFIGURED" and tools["optional_ai"]["status"] == "UNCONFIGURED")
        lessons = self.request("GET", "/api/v1/lessons")["lessons"]
        puzzles = self.request("GET", "/api/v1/puzzles")["puzzles"]
        studies = self.request("GET", "/api/v1/learning/studies")["studies"]
        self.check("playable_learning_content_available", len(lessons) >= 4 and bool(puzzles) and bool(studies), {"lessons": len(lessons), "puzzles": len(puzzles), "studies": len(studies)})

        snapshots = {item["id"]: {key: item[key] for key in ("fen", "moves", "version", "status", "result", "turn", "white_ms", "black_ms")} for item in (game, study, engine_game)}
        self.stop()
        self.check("owned_backend_stopped_for_real_restart", self.process is None)
        self.start()
        self.login()
        for game_id, expected in snapshots.items():
            restored = self.request("GET", "/api/v1/games/" + game_id)
            self.check("restart_exact_saved_game_" + game_id[:8], all(restored[key] == value for key, value in expected.items()))
        restored_job = self.request("GET", "/api/v1/analysis/" + completed["id"])
        self.check("completed_analysis_persisted_after_restart", restored_job["status"] == "completed" and restored_job["result"] == completed["result"])
        cached_after_restart = self.request("POST", "/api/v1/analysis", analysis_payload, expected=202)
        self.check("cache_identity_survives_restart", cached_after_restart["id"] == completed["id"] and cached_after_restart.get("duplicate") is True)
        branches = self.request("GET", "/api/v1/games/" + game["id"] + "/variations")["variations"]
        self.check("variation_persisted_after_restart", any(v["id"] == variation["id"] and v["parent_id"] == game["id"] for v in branches))
        continued = self.request("GET", "/api/v1/games/" + engine_game["id"])
        continued = self.move(continued, continued["legal_moves"][0])
        self.check("continue_real_game_after_restart", len(continued["moves"]) == 3)
        finished = self.request("POST", "/api/v1/games/" + continued["id"] + "/resign", {"expected_version": continued["version"], "request_id": uuid.uuid4().hex})
        self.check("explicit_resignation_finishes_resumed_game", finished["status"] == "finished" and finished["reason"] == "resignation" and finished["result"] == "0-1")
        final_pgn = self.request("GET", "/api/v1/games/" + finished["id"] + "/pgn", raw=True)
        final_study = self.request("POST", "/api/v1/studies/import", {"pgn": final_pgn}, expected=201)
        self.check("resumed_game_pgn_roundtrip", final_study["fen"] == finished["fen"] and final_study["result"] == finished["result"])
        self.receipt["game_ids"] = {"checkmate": game["id"], "imported_checkmate_study": study["id"], "engine_game": engine_game["id"], "variation": variation["id"]}
        for name in ("chess.sqlite3", "research.sqlite3"):
            path = self.runtime / name
            self.check("independent_database_exists_" + name, path.is_file())
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
                foreign = db.execute("PRAGMA foreign_key_check").fetchall()
            self.check("database_integrity_" + name, integrity == "ok" and not foreign)
        self.receipt["status"] = "PASS"

    def finish(self):
        try:
            self.stop()
        except Exception as exc:
            self.receipt["status"] = "FAIL"
            self.receipt["checks"].append({"name": "owned_process_cleanup", "status": "FAIL", "detail": str(exc)})
        self.receipt["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.receipt["passed"] = sum(row["status"] == "PASS" for row in self.receipt["checks"])
        self.receipt["failed"] = sum(row["status"] == "FAIL" for row in self.receipt["checks"])
        self.output.write_text(json.dumps(self.receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    acceptance = PackageAcceptance(args.workspace, args.output)
    try:
        acceptance.run()
    except Exception as exc:
        acceptance.receipt["status"] = "FAIL"
        acceptance.receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
        if not acceptance.receipt["checks"] or acceptance.receipt["checks"][-1]["status"] != "FAIL":
            acceptance.receipt["checks"].append({"name": "unhandled_acceptance_failure", "status": "FAIL", "detail": str(exc)})
    finally:
        acceptance.finish()
    print(json.dumps({"status": acceptance.receipt["status"], "passed": acceptance.receipt["passed"], "failed": acceptance.receipt["failed"], "receipt": str(acceptance.output)}))
    return 0 if acceptance.receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
