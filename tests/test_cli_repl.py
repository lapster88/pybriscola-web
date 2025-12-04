"""
Tests for scripts/briscola_repl.py

These tests do NOT require Django setup and test the REPL utility functions directly.
"""

import re

import pytest

from scripts.briscola_repl import (
    build_action_payload,
    describe_message,
)


class TestDescribeMessage:
    """Tests for describe_message function."""

    def test_action_result_ok(self):
        msg = {
            "message_type": "action.result",
            "action_id": "test-123",
            "status": "ok",
        }
        result = describe_message(msg)
        assert "OK" in result
        assert "test-123" in result

    def test_action_result_error(self):
        msg = {
            "message_type": "action.result",
            "action_id": "test-456",
            "status": "error",
            "code": "invalid_bid",
            "reason": "Bid too low",
        }
        result = describe_message(msg)
        assert "error" in result
        assert "invalid_bid" in result
        assert "Bid too low" in result

    def test_hand_update(self):
        msg = {
            "message_type": "hand.update",
            "player_id": 1,
            "hand": [{"suit": "coins", "rank": 3}, {"suit": "cups", "rank": 7}],
        }
        result = describe_message(msg)
        assert "player 1" in result
        assert "2 cards" in result

    def test_trick_played(self):
        msg = {
            "message_type": "trick.played",
            "player_id": 2,
            "card": {"suit": "swords", "rank": 10},
        }
        result = describe_message(msg)
        assert "Player 2" in result
        assert "10" in result
        assert "swords" in result

    def test_trick_won(self):
        msg = {
            "message_type": "trick.won",
            "winner_id": 0,
            "points": 21,
        }
        result = describe_message(msg)
        assert "Player 0" in result
        assert "21 points" in result

    def test_phase_change(self):
        msg = {
            "message_type": "phase.change",
            "phase": "bidding",
        }
        result = describe_message(msg)
        assert "bidding" in result

    def test_player_join(self):
        msg = {
            "message_type": "player.join",
            "player_id": 3,
            "name": "Alice",
        }
        result = describe_message(msg)
        assert "Player 3" in result
        assert "Alice" in result
        assert "joined" in result

    def test_player_leave(self):
        msg = {
            "message_type": "player.leave",
            "player_id": 1,
        }
        result = describe_message(msg)
        assert "Player 1" in result
        assert "left" in result
        # Ensure we don't have "leaveed"
        assert "leaveed" not in result

    def test_player_reconnect(self):
        msg = {
            "message_type": "player.reconnect",
            "player_id": 2,
        }
        result = describe_message(msg)
        assert "Player 2" in result
        assert "reconnected" in result

    def test_sync(self):
        msg = {
            "message_type": "sync",
            "game_id": "TEST01",
            "phase": "playing",
        }
        result = describe_message(msg)
        assert "TEST01" in result
        assert "playing" in result

    def test_score_update(self):
        msg = {
            "message_type": "score.update",
            "scores": [{"player_id": 0, "points": 40}],
        }
        result = describe_message(msg)
        assert "Score update" in result

    def test_fallback_unknown_message(self):
        msg = {
            "message_type": "unknown.type",
            "custom_field": "custom_value",
        }
        result = describe_message(msg)
        # Should be compact single-line JSON
        assert "\n" not in result
        assert "unknown.type" in result
        assert "custom_value" in result

    def test_fallback_non_dict(self):
        result = describe_message("just a string")
        # Should return compact JSON representation
        assert result == '"just a string"'

    def test_fallback_compact_json(self):
        msg = {
            "message_type": "exotic.event",
            "z_field": "z",
            "a_field": "a",
        }
        result = describe_message(msg)
        # Should be compact (no spaces after colons/commas) and sorted
        assert " " not in result
        # Check it's valid JSON
        import json
        parsed = json.loads(result)
        assert parsed["a_field"] == "a"


class TestBuildActionPayload:
    """Tests for build_action_payload function."""

    def test_basic_payload(self):
        payload = build_action_payload("bid", "GAME01", 1, "player", bid=60)
        assert payload["message_type"] == "bid"
        assert payload["game_id"] == "GAME01"
        assert payload["player_id"] == 1
        assert payload["role"] == "player"
        assert payload["bid"] == 60
        assert "action_id" in payload
        assert "ts" in payload
        assert payload["version"] == "1.0.0"
        assert payload["origin"] == "repl"

    def test_build_action_payload_sets_defaults(self):
        payload = build_action_payload("bid", "GAME01")
        assert "action_id" in payload
        # Use anchored regex to verify the whole action_id format
        assert re.match(r"^bid-[0-9a-f-]{36}$", payload["action_id"])
        assert payload["role"] == "player"
        assert "player_id" not in payload  # None should not be included

    def test_observer_role(self):
        payload = build_action_payload("sync", "GAME02", role="observer")
        assert payload["role"] == "observer"
        assert "player_id" not in payload

    def test_player_id_zero(self):
        # Ensure player_id=0 is included (not treated as falsy)
        payload = build_action_payload("bid", "GAME03", player_id=0)
        assert payload["player_id"] == 0

    def test_extra_fields(self):
        payload = build_action_payload(
            "play",
            "GAME04",
            2,
            card={"suit": "coins", "rank": 1},
        )
        assert payload["card"] == {"suit": "coins", "rank": 1}

    def test_timestamp_is_recent(self):
        import time
        before = int(time.time() * 1000)
        payload = build_action_payload("sync", "GAME05")
        after = int(time.time() * 1000)
        assert before <= payload["ts"] <= after
