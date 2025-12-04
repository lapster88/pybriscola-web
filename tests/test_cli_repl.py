import os
import re

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pybriscola.settings")
import django

django.setup()

from scripts.briscola_repl import (
    build_action_payload,
    describe_message,
    parse_card_token,
    parse_rank,
)


@pytest.mark.parametrize(
    "token,expected",
    [
        ("coins-7", {"suit": "coins", "rank": 7}),
        ("CUPS:10", {"suit": "cups", "rank": 10}),
    ],
)
def test_parse_card_token_accepts_suit_and_rank(token, expected):
    assert parse_card_token(token) == expected


def test_parse_card_token_rejects_invalid_suit():
    with pytest.raises(ValueError):
        parse_card_token("stars-2")


def test_parse_rank_limits_range():
    with pytest.raises(ValueError):
        parse_rank("11")


def test_build_action_payload_sets_defaults():
    payload = build_action_payload("bid", "GAME01", player_id=2, bid=90)
    assert payload["message_type"] == "bid"
    assert payload["game_id"] == "GAME01"
    assert payload["player_id"] == 2
    assert payload["bid"] == 90
    assert re.match(r"bid-[0-9a-f-]{36}$", payload["action_id"])


def test_build_action_payload_respects_custom_action_id():
    payload = build_action_payload(
        "play", "GAME01", player_id=1, card={"suit": "coins", "rank": 3}, action_id="custom"
    )
    assert payload["action_id"] == "custom"


def test_describe_message_formats_action_result_success():
    summary = describe_message(
        {
            "message_type": "action.result",
            "action_id": "bid-123",
            "status": "ok",
            "effects": {"phase.change": {}, "score.update": {}},
        }
    )
    assert summary == "Action bid-123 succeeded. Effects: phase.change, score.update."


def test_describe_message_formats_trick_won_event():
    summary = describe_message(
        {
            "message_type": "trick.won",
            "winner_id": 3,
            "points": 11,
            "trick_cards": [
                {"player_id": 1, "card": {"suit": "coins", "rank": 1}},
                {"player_id": 3, "card": {"suit": "cups", "rank": 3}},
            ],
            "scores": [
                {"player_id": 1, "points": 0},
                {"player_id": 3, "points": 11},
            ],
        }
    )
    assert "Trick won by player 3 for 11 points" in summary
    assert "p1 coins 1" in summary
    assert "p3 cups 3" in summary
    assert "scores: p1: 0, p3: 11" in summary
