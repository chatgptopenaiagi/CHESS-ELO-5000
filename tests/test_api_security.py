import hashlib
import hmac
import json
import time
import uuid
import pytest
from chess_elo_5000 import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path, testing=True)
    app.config.update(OWNER_PASSWORD="test-owner", BRIDGE_SECRET="b"*40)
    yield app
    app.extensions["chess_service"].close()


def login(client):
    response = client.post("/api/v1/session", json={"password": "test-owner"})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json["csrf_token"]}


def signed(app, path, payload=None, user="37", method="GET", nonce=None, stamp=None):
    body = json.dumps(payload, separators=(",", ":")) if payload is not None else ""
    stamp, nonce = str(stamp or int(time.time())), nonce or uuid.uuid4().hex
    packet = "\n".join((stamp, nonce, user, method, path, hashlib.sha256(body.encode()).hexdigest()))
    signature = hmac.new(app.config["BRIDGE_SECRET"].encode(), packet.encode(), hashlib.sha256).hexdigest()
    return body, {"X-Chess-User": user, "X-Chess-Time": stamp, "X-Chess-Nonce": nonce, "X-Chess-Signature": signature, "Content-Type": "application/json"}


def test_anonymous_and_csrf_denied(app):
    client = app.test_client()
    assert client.get("/api/v1/games").status_code == 401
    assert client.post("/api/v1/session", json={"password": "wrong"}).status_code == 401
    headers = login(client)
    assert client.post("/api/v1/games", json={}).status_code == 403
    bad_origin = {**headers, "Origin": "https://evil.example"}
    assert client.post("/api/v1/games", json={}, headers=bad_origin).status_code == 403
    response = client.post("/api/v1/games", json={"mode": "human"}, headers=headers)
    assert response.status_code == 201
    assert "HttpOnly" in client.get("/api/v1/session").headers.get("Set-Cookie", "")


def test_bridge_signature_nonce_owner_and_body_integrity(app):
    client = app.test_client()
    body, headers = signed(app, "/api/v1/games", {"mode": "human", "time_seconds": 0}, method="POST")
    result = client.post("/api/v1/games", data=body, headers=headers)
    assert result.status_code == 201
    assert client.post("/api/v1/games", data=body, headers=headers).status_code == 409
    other_body, other_headers = signed(app, "/api/v1/games/"+result.json["id"], user="38")
    assert client.get("/api/v1/games/"+result.json["id"], headers=other_headers).status_code == 404
    body, headers = signed(app, "/api/v1/games", {"mode": "human"}, method="POST")
    assert client.post("/api/v1/games", data=body+" ", headers=headers).status_code == 401
    body, headers = signed(app, "/api/v1/games", stamp=int(time.time())-300)
    assert client.get("/api/v1/games", headers=headers).status_code == 401


def test_status_reads_never_launch_engines_or_change_database(app, monkeypatch):
    client = app.test_client()
    service = app.extensions["chess_service"]
    def prohibited(*args, **kwargs):
        raise AssertionError("Status must not analyze")
    monkeypatch.setattr(service.engine, "analyze", prohibited)
    before = service.storage.read("SELECT count(*) AS n FROM engine_runs")[0]["n"]
    assert client.get("/api/v1/system/status").status_code == 200
    assert client.get("/api/v1/engines").status_code == 200
    assert service.storage.read("SELECT count(*) AS n FROM engine_runs")[0]["n"] == before


def test_api_gameplay_export_import_actions(app):
    client = app.test_client()
    headers = login(client)
    game = client.post("/api/v1/games", json={"mode": "human", "time_seconds": 0}, headers=headers).json
    for i, uci in enumerate(("f2f3", "e7e5", "g2g4", "d8h4")):
        response = client.post(f'/api/v1/games/{game["id"]}/moves', json={"uci": uci, "expected_version": i, "request_id": str(i)}, headers=headers)
        assert response.status_code == 200
        game = response.json
    assert game["reason"] == "checkmate" and game["result"] == "0-1"
    pgn = client.get(f'/api/v1/games/{game["id"]}/pgn').get_data(as_text=True)
    imported = client.post("/api/v1/studies/import", json={"pgn": pgn}, headers=headers)
    assert imported.status_code == 201 and imported.json["fen"] == game["fen"]
    assert client.post("/api/v1/games", json=[1], headers=headers).status_code == 400
    assert client.post("/api/v1/analysis", json={"fen": "invalid"}, headers=headers).status_code == 400


def test_bridge_auth_failure_does_not_leak_secrets(app):
    client = app.test_client()
    response = client.get("/api/v1/games", headers={"X-Chess-User": "37"})
    assert response.status_code == 401 and "b"*40 not in response.get_data(as_text=True)
