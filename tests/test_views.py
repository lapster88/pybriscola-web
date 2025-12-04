import jwt
import pytest
from django.conf import settings
from django.test import Client


@pytest.mark.django_db
def test_create_mints_tokens_and_game_id():
    client = Client()
    resp = client.post("/briscola/create/")
    assert resp.status_code == 200
    data = resp.json()
    assert "game_id" in data
    assert len(data["players"]) == 5
    # validate one token decodes
    first = data["players"][0]
    claims = jwt.decode(first["token"], settings.SECRET_KEY, algorithms=["HS256"])
    assert claims["game_id"] == data["game_id"]
    assert claims["player_id"] == 0
    assert claims["role"] == "player"
    # observer token decodes
    obs = jwt.decode(data["observer_token"], settings.SECRET_KEY, algorithms=["HS256"])
    assert obs["role"] == "observer"
    assert obs["game_id"] == data["game_id"]


@pytest.mark.django_db
def test_observer_token_endpoint():
    client = Client()
    resp = client.get("/briscola/observer-token/TEST01/?ttl=30&display_name=Ann")
    assert resp.status_code == 200
    data = resp.json()
    claims = jwt.decode(data["token"], settings.SECRET_KEY, algorithms=["HS256"])
    assert claims["role"] == "observer"
    assert claims["game_id"] == "TEST01"
    assert claims["display_name"] == "Ann"
