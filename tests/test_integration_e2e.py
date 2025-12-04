import os

import pytest
from channels.testing import WebsocketCommunicator
from django.test import Client

from pybriscola.asgi import application


pytestmark = pytest.mark.asyncio


@pytest.mark.skipif(
    os.getenv("INTEGRATION_E2E") != "1",
    reason="Set INTEGRATION_E2E=1 to run end-to-end integration test",
)
async def test_join_round_trip_with_game_server():
    # Create a game via HTTP endpoint
    client = Client()
    resp = client.post("/briscola/create/")
    assert resp.status_code == 200
    data = resp.json()
    game_id = data["game_id"]
    token = data["players"][0]["token"]

    communicator = WebsocketCommunicator(application, "/ws/client/")
    connected, _ = await communicator.connect()
    assert connected

    join_msg = {
        "message_type": "join",
        "token": token,
        "game_id": game_id,
        "action_id": "join-1",
    }
    await communicator.send_json_to(join_msg)

    received = []
    for _ in range(5):
        msg = await communicator.receive_json_from(timeout=5)
        received.append(msg)
        # break early if we already have both action.result and sync
        has_action_result = any(
            m.get("message_type") == "action.result"
            or m.get("payload", {}).get("message_type") == "action.result"
            for m in received
        )
        has_sync = any(
            m.get("message_type") == "sync"
            or m.get("payload", {}).get("message_type") == "sync"
            for m in received
        )
        if has_action_result and has_sync:
            break

    assert any(
        m.get("message_type") == "action.result"
        or m.get("payload", {}).get("message_type") == "action.result"
        for m in received
    ), f"Did not receive action.result in messages: {received}"

    assert any(
        m.get("message_type") == "sync"
        or m.get("payload", {}).get("message_type") == "sync"
        for m in received
    ), f"Did not receive sync snapshot in messages: {received}"

    await communicator.disconnect()
