"""Supported python-chess UCI adapter. Every operation owns and bounds its process."""
import hashlib
import os
from pathlib import Path
import threading
import time
import chess
import chess.engine
from .errors import ChessError


def discover_engine(workspace):
    candidates = [os.environ.get("CHESS_ENGINE_PATH", ""),
                  str(Path(workspace) / "stockfish/stockfish/stockfish-windows-x86-64-universal.exe")]
    local = os.environ.get("APPDATA")
    if local:
        catalog = Path(local) / "org.encroissant.app/engines/engines.json"
        if catalog.is_file():
            try:
                import json
                candidates += [r["path"] for r in json.loads(catalog.read_text(encoding="utf-8-sig")) if r.get("type") == "local" and r.get("path")]
            except (ValueError, OSError, KeyError):
                pass
    return next((Path(p) for p in candidates if p and Path(p).is_file()), None)


def score_json(score, turn):
    view = score.white()
    return {"type": "mate" if view.is_mate() else "cp", "value": view.mate() if view.is_mate() else view.score(),
            "perspective": "white", "reported_perspective": "side_to_move", "reported_value": score.pov(turn).mate() if score.pov(turn).is_mate() else score.pov(turn).score()}


class EngineAdapter:
    def __init__(self, path, threads=6, hash_mb=512, command=None):
        self.path = Path(path) if path else None
        self.command = command or (str(self.path) if self.path else None)
        self.threads, self.hash_mb = threads, hash_mb
        self._identity = None
        self._sha = hashlib.sha256(self.path.read_bytes()).hexdigest() if self.path and self.path.is_file() else None

    def identity(self):
        return {"id": self._sha or "unconfigured", "path": str(self.path) if self.path else None,
                "sha256": self._sha, "available": bool(self.path and self.path.is_file()),
                "status": "VERIFIED" if self._identity else "DISCOVERED" if self.path else "UNCONFIGURED", **(self._identity or {})}

    def refresh_identity(self):
        """Explicit analysis request checks the executable binding before cache selection."""
        current = hashlib.sha256(self.path.read_bytes()).hexdigest() if self.path and self.path.is_file() else None
        if current != self._sha:
            self._sha, self._identity = current, None
        return self.identity()

    def analyze(self, board, *, depth=None, nodes=None, movetime_ms=1000, multipv=3, root_moves=None, cancel=None, skill=20):
        if not self.path or not self.path.is_file():
            raise ChessError("engine_unavailable", "No configured local UCI executable is available", 503)
        if not board.is_valid():
            raise ChessError("invalid_fen", "Engine refuses invalid positions")
        if not list(board.legal_moves):
            return {"engine": self.identity(), "lines": [], "terminal": True, "elapsed_seconds": 0, "nodes": 0}
        if depth is not None and (type(depth) is not int or not 1 <= depth <= 40):
            raise ChessError("invalid_budget", "Depth must be 1..40")
        if nodes is not None and (type(nodes) is not int or not 1 <= nodes <= 5_000_000):
            raise ChessError("invalid_budget", "Node budget must be 1..5000000")
        if type(movetime_ms) is not int or not 10 <= movetime_ms <= 10000:
            raise ChessError("invalid_budget", "Move time must be 10..10000 ms")
        if type(multipv) is not int or not 1 <= multipv <= 8:
            raise ChessError("invalid_budget", "MultiPV must be 1..8")
        if type(skill) is not int or not 0 <= skill <= 20:
            raise ChessError("invalid_skill", "Skill must be 0..20")
        started = time.perf_counter()
        engine = None
        timer = None
        timed_out = threading.Event()
        malformed = threading.Event()
        # UciProtocol's permissive parser logs some illegal PV/bestmove errors without
        # completing an analysis future. Guard the raw chess-bearing fields so an
        # invalid line cannot hang until the deadline or be silently displayed.
        class ValidatingUciProtocol(chess.engine.UciProtocol):
            def line_received(protocol, line):
                tokens = None
                if line.startswith("bestmove "):
                    tokens = line.split()[1:2]
                elif line.startswith("info ") and not line.startswith("info string ") and " pv " in line:
                    tokens = line.split(" pv ", 1)[1].split()
                if tokens:
                    replay = board.copy(stack=True)
                    try:
                        for token in tokens:
                            candidate = chess.Move.from_uci(token)
                            if candidate not in replay.legal_moves:
                                raise ValueError("illegal engine move")
                            replay.push(candidate)
                    except ValueError:
                        malformed.set()
                        if engine:
                            engine.close()
                        return
                super().line_received(line)
        try:
            engine = chess.engine.SimpleEngine.popen(ValidatingUciProtocol, self.command, timeout=3)
            options = {n: {"type": o.type, "default": o.default, "min": o.min, "max": o.max, "var": o.var} for n, o in engine.options.items()}
            self._identity = {"name": engine.id.get("name", self.path.stem), "author": engine.id.get("author"), "uci_options": options,
                              "operations": ["uci", "isready", "ucinewgame", "position", "go", "stop", "quit"]}
            configuration = {"Threads": self.threads, "Hash": self.hash_mb, "Skill Level": skill, "UCI_LimitStrength": False}
            supported = {k: v for k, v in configuration.items() if k in engine.options}
            engine.configure(supported)
            engine.ping()
            def deadline():
                timed_out.set()
                engine.close()
            timer = threading.Timer(movetime_ms / 1000 + 4, deadline)
            timer.daemon = True
            timer.start()
            limit = chess.engine.Limit(time=movetime_ms / 1000, depth=depth, nodes=nodes)
            lines = []
            with engine.analysis(board, limit, multipv=min(multipv, board.legal_moves.count()), root_moves=root_moves, game=object()) as analysis:
                while True:
                    if cancel and cancel.is_set():
                        analysis.stop()
                        raise ChessError("cancelled", "Engine analysis was cancelled", 409)
                    info = analysis.next()
                    if info is None:
                        break
                infos = analysis.multipv
                reported_best = analysis.wait()
            for info in infos:
                replay = board.copy(stack=True)
                pv, san = [], []
                for move in info.get("pv", []):
                    if move not in replay.legal_moves:
                        raise ChessError("invalid_pv", "Engine returned an illegal principal variation", 502)
                    pv.append(move.uci())
                    san.append(replay.san(move))
                    replay.push(move)
                if not pv or "score" not in info:
                    raise ChessError("malformed_engine_response", "Engine did not return a scored legal principal variation", 502)
                lines.append({"score": score_json(info["score"], board.turn), "pv": pv, "san": san, "depth": info.get("depth"),
                              "seldepth": info.get("seldepth"), "nodes": info.get("nodes", 0), "nps": info.get("nps"), "time": info.get("time")})
            if not lines:
                raise ChessError("malformed_engine_response", "Engine returned no legal line", 502)
            if reported_best.move not in board.legal_moves:
                raise ChessError("invalid_bestmove", "Engine did not return a legal bestmove", 502)
            return {"engine": self.identity(), "configuration": supported, "lines": lines, "bestmove": reported_best.move.uci(),
                    "requested": {"depth": depth, "nodes": nodes, "movetime_ms": movetime_ms, "multipv": multipv},
                    "elapsed_seconds": time.perf_counter() - started, "nodes": max(l["nodes"] for l in lines), "score_kind": "ENGINE EVALUATION"}
        except ChessError:
            raise
        except (TimeoutError, chess.engine.EngineTerminatedError, chess.engine.EngineError, OSError) as exc:
            code = "malformed_engine_response" if malformed.is_set() else "engine_timeout" if timed_out.is_set() or isinstance(exc, TimeoutError) else "engine_failed"
            raise ChessError(code, "Local engine returned illegal output" if malformed.is_set() else "Local engine failed or exceeded its bounded deadline", 502) from exc
        finally:
            if timer:
                timer.cancel()
            if engine:
                try:
                    engine.quit()
                except Exception:
                    engine.close()
