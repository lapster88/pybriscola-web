import json
from unittest.mock import MagicMock

import jwt
import pytest
from channels.testing import WebsocketCommunicator
from django.conf import settings

from pybriscola.asgi import application
from briscola import consumers


class DummyRedis:
    def __init__(self):
        self.published = []
        self.pubsub_obj = DummyPubSub(self)

    def publish(self, channel, data):
        self.published.append((channel, data))

    def pubsub(self):
        return self.pubsub_obj


class DummyPubSub:
    def __init__(self, parent):
        self.parent = parent
        self.subscribed = set()
        self.listeners = []

    def subscribe(self, channel):
        self.subscribed.add(channel)

    def listen(self):
        while self.listeners:
            yield self.listeners.pop(0)

    def push(self, data):
        self.listeners.append({"type": "message", "data": data})


@pytest.mark.asyncio
async def test_observer_cannot_send_actions(monkeypatch):
    dummy = DummyRedis()
    monkeypatch.setattr(consumers.redis, "Redis", MagicMock(from_url=lambda *args, **kwargs: dummy))
    monkeypatch.setattr(consumers.jwt, "decode", lambda token, key, algorithms: {"game_id": "TEST01", "role": "observer"})

    token = jwt.encode({"game_id": "TEST01", "role": "observer"}, settings.SECRET_KEY, algorithm="HS256")
    communicator = WebsocketCommunicator(application, "/ws/client/")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to({"message_type": "join", "token": token, "game_id": "TEST01", "action_id": "a1"})
    await communicator.receive_json_from(timeout=1)  # ack

    await communicator.send_json_to({"message_type": "play", "game_id": "TEST01", "action_id": "a2", "card": {}})
    resp = await communicator.receive_json_from(timeout=1)
    assert resp["message_type"] == "action.result"
    assert resp["status"] == "error"
    assert resp["code"] == "forbidden"
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_duplicate_connection_forces_previous_disconnect(monkeypatch):
    dummy = DummyRedis()
    monkeypatch.setattr(consumers.redis, "Redis", MagicMock(from_url=lambda *args, **kwargs: dummy))

    claims = {"game_id": "TEST01", "role": "player", "player_id": 0}
    monkeypatch.setattr(consumers.jwt, "decode", lambda token, key, algorithms: claims)
    token = jwt.encode(claims, settings.SECRET_KEY, algorithm="HS256")

    comm1 = WebsocketCommunicator(application, "/ws/client/")
    comm2 = WebsocketCommunicator(application, "/ws/client/")
    await comm1.connect()
    await comm1.send_json_to({"message_type": "join", "token": token, "game_id": "TEST01", "action_id": "a1"})
    await comm1.receive_json_from(timeout=1)

    await comm2.connect()
    await comm2.send_json_to({"message_type": "join", "token": token, "game_id": "TEST01", "action_id": "a2"})
    await comm2.receive_json_from(timeout=1)

    # First connection should receive a duplicate notice
    msg = await comm1.receive_json_from(timeout=1)
    assert msg["code"] == "duplicate_connection_handled"

    await comm1.disconnect()
    await comm2.disconnect()
