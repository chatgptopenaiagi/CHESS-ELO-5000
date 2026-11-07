"""Versioned authenticated Flask API and same-origin static chess client."""
from pathlib import Path
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from urllib.parse import urlparse
from flask import Flask, g, jsonify, request, send_from_directory, session, Response
from werkzeug.exceptions import HTTPException
from .core import ChessService
from .errors import ChessError
from .rules import valid_board, facts


def create_app(runtime_dir=None, engine_path=None, testing=False):
    workspace = Path(os.environ.get("CHESS_WORKSPACE") or Path(__file__).resolve().parents[2]).resolve()
    runtime = Path(runtime_dir or os.environ.get("CHESS_RUNTIME_DIR") or workspace / "runtime").resolve()
    private = runtime / "private"
    private.mkdir(parents=True, exist_ok=True)
    cfg_path = private / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig")) if cfg_path.is_file() else {}
    secret_path = private / "session.key"
    if not secret_path.is_file():
        with secret_path.open("xb") as stream:
            stream.write(secrets.token_bytes(48))
    app = Flask(__name__, static_folder=None)
    app.config.update(TESTING=testing, SECRET_KEY=secret_path.read_bytes(), MAX_CONTENT_LENGTH=2_000_000,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_NAME="chesselo5000_session",
                      OWNER_PASSWORD=os.environ.get("CHESS_OWNER_PASSWORD") or cfg.get("owner_password") or ("test-owner" if testing else None),
                      BRIDGE_SECRET=os.environ.get("CHESS_BRIDGE_SECRET") or cfg.get("bridge_secret"),
                      PERMANENT_SESSION_LIFETIME=43200)
    service = ChessService(runtime, engine_path or cfg.get("engine_path"), workspace)
    app.extensions["chess_service"] = service
    login_attempts = {}

    @app.before_request
    def authenticate():
        if not request.path.startswith("/api/v1/"):
            return
        if request.path in ("/api/v1/system/status", "/api/v1/engines") and request.method == "GET":
            return
        if request.path == "/api/v1/session" and request.method == "POST":
            return
        user = request.headers.get("X-Chess-User")
        if user is not None:
            stamp, nonce, signature = (request.headers.get(k, "") for k in ("X-Chess-Time", "X-Chess-Nonce", "X-Chess-Signature"))
            bridge = app.config["BRIDGE_SECRET"]
            try:
                timely = abs(time.time() - int(stamp)) <= 60
            except ValueError:
                timely = False
            if not bridge or not timely or not 16 <= len(nonce) <= 128 or not 1 <= len(user) <= 128:
                raise ChessError("bridge_authentication_failed", "Invalid or expired Joomla bridge request", 401)
            body_hash = hashlib.sha256(request.get_data(cache=True)).hexdigest()
            packet = "\n".join((stamp, nonce, user, request.method, request.path, body_hash))
            expected = hmac.new(bridge.encode(), packet.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise ChessError("bridge_authentication_failed", "Joomla bridge signature failed", 401)
            with service.storage.transaction() as db:
                db.execute("DELETE FROM bridge_nonces WHERE expires<?", (time.time(),))
                try:
                    db.execute("INSERT INTO bridge_nonces(nonce,expires) VALUES(?,?)", (nonce, time.time() + 120))
                except sqlite3.IntegrityError as exc:
                    raise ChessError("bridge_replay", "Bridge nonce was already used", 409) from exc
            g.owner = "joomla:" + user
            g.auth_mode = "bridge"
            return
        if not session.get("owner"):
            raise ChessError("authentication_required", "Sign in to access saved chess data", 401)
        g.owner = session["owner"]
        g.auth_mode = "session"
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            csrf = request.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(session.get("csrf_token", ""), csrf) or not csrf:
                raise ChessError("csrf_failed", "A valid session CSRF token is required", 403)
            origin = request.headers.get("Origin")
            if origin and urlparse(origin).netloc != request.host:
                raise ChessError("origin_failed", "Cross-origin persistent actions are refused", 403)

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(ChessError)
    def chess_error(exc):
        return jsonify(error=exc.code, message=exc.message), exc.status

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(error=exc.name.lower().replace(" ", "_"), message=exc.description), exc.code

    def body():
        value = request.get_json()
        if not isinstance(value, dict):
            raise ChessError("invalid_input", "JSON body must be an object")
        return value

    @app.route("/api/v1/session", methods=["POST", "GET", "DELETE"])
    def owner_session():
        if request.method == "POST":
            now = time.time()
            ip = request.remote_addr or "local"
            attempts = [t for t in login_attempts.get(ip, []) if now - t < 60]
            if len(attempts) >= 15:
                raise ChessError("rate_limited", "Too many sign-in attempts; wait one minute", 429)
            attempts.append(now)
            login_attempts[ip] = attempts
            supplied = body().get("password", "")
            password = app.config["OWNER_PASSWORD"]
            if not password:
                raise ChessError("owner_unconfigured", "Configure the independent local owner password before sign-in", 503)
            if not isinstance(supplied, str) or not hmac.compare_digest(password, supplied):
                raise ChessError("authentication_failed", "Owner password is incorrect", 401)
            session.clear()
            session.permanent = True
            session.update(owner="local-owner", csrf_token=secrets.token_urlsafe(32))
            return jsonify(user="local-owner", csrf_token=session["csrf_token"])
        if request.method == "DELETE":
            session.clear()
            return jsonify(status="signed_out")
        return jsonify(user=g.owner, csrf_token=session.get("csrf_token") if g.auth_mode == "session" else None)

    @app.get("/api/v1/system/status")
    def status():
        return jsonify(product="CHESS ELO 5000", version="0.1.0-development", status="ready", schema_version=1,
                       rules="python-chess", engine_available=service.engine.identity()["available"],
                       authentication="configured" if app.config["OWNER_PASSWORD"] else "unconfigured",
                       tablebases="UNCONFIGURED", optional_ai="UNCONFIGURED", elo_claim="BRAND IDENTITY, NOT AN ESTABLISHED PERFORMANCE RATING")

    @app.get("/api/v1/engines")
    def engines():
        return jsonify(engines=[service.engine.identity()], tablebases={"status": "UNCONFIGURED"}, optional_ai={"status": "UNCONFIGURED"})

    @app.post("/api/v1/engines/probe")
    def probe_engine():
        return jsonify(service.engine.analyze(valid_board(), nodes=1000, movetime_ms=100, multipv=1))

    @app.route("/api/v1/games", methods=["GET", "POST"])
    def games():
        return jsonify(games=service.list_games(g.owner)) if request.method == "GET" else (jsonify(service.create_game(g.owner, body())), 201)

    @app.get("/api/v1/games/<game_id>")
    def game(game_id):
        return jsonify(service.get_game(g.owner, game_id))

    @app.get("/api/v1/games/<game_id>/legal-moves")
    def legal_moves(game_id):
        state = service.get_game(g.owner, game_id)
        return jsonify(fen=state["fen"], version=state["version"], legal_moves=state["legal_moves"])

    @app.post("/api/v1/games/<game_id>/moves")
    def move(game_id):
        return jsonify(service.move(g.owner, game_id, body()))

    @app.post("/api/v1/games/<game_id>/engine")
    def engine_move(game_id):
        return jsonify(service.engine_move(g.owner, game_id, body()))

    @app.post("/api/v1/games/<game_id>/<action>")
    def game_action(game_id, action):
        if action not in ("resign", "draw", "undo", "tick"):
            raise ChessError("not_found", "Unknown game action", 404)
        return jsonify(service.action(g.owner, game_id, action, body()))

    @app.get("/api/v1/games/<game_id>/pgn")
    def pgn(game_id):
        return Response(service.export_pgn(g.owner, game_id), mimetype="application/x-chess-pgn", headers={"Content-Disposition": f'attachment; filename="chess-{game_id}.pgn"'})

    @app.post("/api/v1/studies/import")
    def import_study():
        return jsonify(service.import_pgn(g.owner, body().get("pgn"))), 201

    @app.route("/api/v1/games/<game_id>/variations", methods=["POST", "GET"])
    def variations(game_id):
        if request.method == "POST":
            return jsonify(service.variation(g.owner, game_id, body())), 201
        return jsonify(variations=service.list_variations(g.owner, game_id))

    @app.get("/api/v1/positions")
    def position():
        return jsonify(facts(valid_board(request.args.get("fen"))))

    @app.post("/api/v1/analysis")
    def analysis():
        return jsonify(service.request_analysis(g.owner, body())), 202

    @app.get("/api/v1/analysis/<job_id>")
    def analysis_job(job_id):
        return jsonify(service.get_analysis(g.owner, job_id))

    @app.post("/api/v1/analysis/<job_id>/cancel")
    def cancel_job(job_id):
        return jsonify(service.cancel_analysis(g.owner, job_id))

    @app.get("/api/v1/analysis")
    def analysis_history():
        return jsonify(jobs=service.list_analysis(g.owner))

    try:
        from .research.blueprint import register_research
    except ModuleNotFoundError as exc:
        if exc.name not in ("chess_elo_5000.research", "chess_elo_5000.research.blueprint"):
            raise
    else:
        register_research(app, service)

    web = workspace / "client/web"

    @app.get("/")
    def home():
        return send_from_directory(web, "index.html")

    @app.get("/<path:filename>")
    def static_file(filename):
        return send_from_directory(web, filename)

    return app
