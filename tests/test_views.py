import json

import jwt
import pytest
from django.conf import settings
from django.test import Client


def _auth_header(token):
    return {'HTTP_AUTHORIZATION': f'Bearer {token}'}


@pytest.mark.django_db
def test_create_mints_host_token_only():
    client = Client()
    resp = client.post("/briscola/create/")
    assert resp.status_code == 200
    data = resp.json()
    assert "game_id" in data
    assert "host_token" in data
    claims = jwt.decode(data["host_token"], settings.SECRET_KEY, algorithms=["HS256"])
    assert claims["game_id"] == data["game_id"]
    assert claims["role"] == "host"


@pytest.mark.django_db
def test_issue_token_requires_host_and_mints_player():
    client = Client()
    create_resp = client.post("/briscola/create/")
    game_id = create_resp.json()["game_id"]
    host_token = create_resp.json()["host_token"]

    resp = client.post(
        f"/briscola/token/{game_id}/",
        data=json.dumps({"role": "player", "player_id": 0, "ttl_minutes": 30}),
        content_type="application/json",
        **_auth_header(host_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    claims = jwt.decode(data["token"], settings.SECRET_KEY, algorithms=["HS256"])
    assert claims["role"] == "player"
    assert claims["game_id"] == game_id
    assert claims["player_id"] == 0


@pytest.mark.django_db
def test_issue_token_rejects_without_host():
    client = Client()
    create_resp = client.post("/briscola/create/")
    assert create_resp.status_code == 200
    resp = client.post(
        "/briscola/token/TEST01/",
        data=json.dumps({"role": "observer"}),
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_health_endpoint_checks_redis():
    client = Client()
    resp = client.get("/briscola/health/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "redis" in data


@pytest.mark.django_db
def test_game_status():
    client = Client()
    resp = client.get("/briscola/game/TEST01/status/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["game_id"] == "TEST01"
    assert "redis" in data
    assert "observers_open" in data


@pytest.mark.django_db
def test_join_observer_mints_token_without_host():
    client = Client()
    resp = client.post(
        "/briscola/join/observer/TEST01/",
        data=json.dumps({"display_name": "Ann", "ttl_minutes": 15}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    claims = jwt.decode(data["token"], settings.SECRET_KEY, algorithms=["HS256"])
    assert claims["role"] == "observer"
    assert claims["game_id"] == "TEST01"
    assert claims["display_name"] == "Ann"
