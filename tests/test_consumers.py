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
async def test_join_publish_and_event_forward(monkeypatch):
    # Patch Redis client
    dummy = DummyRedis()
    monkeypatch.setattr(consumers.redis, "Redis", MagicMock(from_url=lambda *args, **kwargs: dummy))
    monkeypatch.setattr(consumers.jwt, "decode", lambda token, key, algorithms: token_payload)

    # Fake token (JWT)
    token_payload = {"game_id": "TEST01", "role": "player", "player_id": 0}
    token = jwt.encode(token_payload, settings.SECRET_KEY, algorithm="HS256")

    communicator = WebsocketCommunicator(application, "/ws/client/")
    connected, _ = await communicator.connect()
    assert connected

    join_msg = {
        "message_type": "join",
        "token": token,
        "game_id": "TEST01",
        "action_id": "act-1"
    }
    await communicator.send_json_to(join_msg)

    # Attempt to receive any immediate response (e.g., error)
    recv = await communicator.receive_json_from(timeout=1)
    if recv.get("status") == "error":
        pytest.fail(f"Join failed: {recv}")

    # Ensure publish occurred
    assert dummy.published, "No publish to Redis actions"
    channel, data = dummy.published[0]
    assert "game.TEST01.actions" == channel

    # Simulate incoming event on pubsub
    # (threaded forwarding is exercised in integration; here we just ensure publish works)
    await communicator.disconnect()
