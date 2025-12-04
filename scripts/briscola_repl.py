"""
A REPL-friendly CLI client for creating and exercising Briscola games.

It can bootstrap a full 5-player table and lets you send actions for any
player from a single terminal session. Commands are intentionally verbose to
mirror the websocket API exposed by the Django Channels consumer.
"""
import argparse
import asyncio
import json
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

try:  # Optional dependency for test environments without internet access
    import websockets
except ImportError:  # pragma: no cover - exercised in runtime, not tests
    websockets = None

if TYPE_CHECKING:  # pragma: no cover
    from websockets import WebSocketClientProtocol

VALID_SUITS = {"coins", "cups", "swords", "clubs"}


def parse_rank(raw: str) -> int:
    """Convert a rank string to an int and validate the range."""
    try:
        rank = int(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Rank must be an integer: {raw}") from exc
    if not 1 <= rank <= 10:
        raise ValueError(f"Rank must be between 1 and 10: {rank}")
    return rank


def parse_card_token(token: str) -> Dict[str, int]:
    """Parse a card token such as ``coins-7`` or ``cups:10`` into a dict."""
    cleaned = token.strip().lower()
    delimiter = ":" if ":" in cleaned else "-"
    if delimiter not in cleaned:
        raise ValueError(
            f"Card tokens must look like suit-rank (e.g. coins-7); got '{token}'"
        )
    suit, raw_rank = cleaned.split(delimiter, 1)
    if suit not in VALID_SUITS:
        raise ValueError(f"Suit must be one of {', '.join(sorted(VALID_SUITS))}")
    return {"suit": suit, "rank": parse_rank(raw_rank)}


def build_action_payload(
    message_type: str,
    game_id: str,
    player_id: Optional[int] = None,
    action_id: Optional[str] = None,
    **payload,
) -> Dict[str, object]:
    """Construct the JSON payload sent over the websocket for an action."""
    data: Dict[str, object] = {
        "message_type": message_type,
        "game_id": game_id,
        "action_id": action_id or f"{message_type}-{uuid.uuid4()}",
    }
    if player_id is not None:
        data["player_id"] = player_id
    data.update(payload)
    return data


@dataclass
class PlayerSession:
    player_id: int
    token: str
    websocket: Optional["WebSocketClientProtocol"] = None
    listener: Optional[asyncio.Task] = None


class BriscolaRepl:
    """Interactive REPL that manages multiple player sessions."""

    def __init__(self, http_base: str, ws_url: str, default_players: int = 5):
        self.http_base = http_base.rstrip("/")
        self.ws_url = ws_url
        self.default_players = default_players
        self.game_id: Optional[str] = None
        self.host_token: Optional[str] = None
        self.players: Dict[int, PlayerSession] = {}
        self._should_exit = False

    async def bootstrap(self, num_players: Optional[int] = None) -> None:
        """Create a game and join ``num_players`` sequentially."""
        num_players = num_players or self.default_players
        await self.create_game()
        for pid in range(num_players):
            await self.join_player(pid)
        print(
            f"Bootstrapped game {self.game_id} with players 0-{num_players - 1}."
        )

    async def create_game(self) -> None:
        """Call the HTTP endpoint to create a game and store the host token."""
        url = f"{self.http_base}/briscola/create/"
        body = await self._post_json(url)
        self.game_id = body["game_id"]
        self.host_token = body["host_token"]
        print(f"Created game {self.game_id}. Host token stored for minting players.")

    async def join_player(self, player_id: int) -> None:
        """Mint a token for ``player_id`` and open a websocket connection."""
        if self.game_id is None or self.host_token is None:
            raise RuntimeError("Create a game before joining players.")
        if websockets is None:
            raise RuntimeError(
                "The 'websockets' package is required to open connections. Install it via pip."
            )

        token_resp = await self._post_json(
            f"{self.http_base}/briscola/token/{self.game_id}/",
            body={"role": "player", "player_id": player_id},
            headers={"Authorization": f"Bearer {self.host_token}"},
        )
        token = token_resp["token"]

        connection = await websockets.connect(self.ws_url)
        join_payload = build_action_payload(
            "join", self.game_id, player_id=player_id, token=token
        )
        await connection.send(json.dumps(join_payload))

        session = PlayerSession(player_id=player_id, token=token, websocket=connection)
        session.listener = asyncio.create_task(self._listen_to_player(session))
        self.players[player_id] = session
        print(f"Player {player_id} joined game {self.game_id}.")

    async def _listen_to_player(self, session: PlayerSession) -> None:
        prefix = f"[player {session.player_id}]"
        try:
            async for raw in session.websocket:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    print(prefix, raw)
                    continue
                print(prefix, describe_message(message))
        except websockets.ConnectionClosed as exc:  # pragma: no cover - runtime
            print(prefix, f"connection closed ({exc.code})")

    async def repl(self) -> None:
        """Run the interactive REPL loop."""
        self._print_help()
        while not self._should_exit:
            line = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("briscola> ")
            )
            if line is None:
                continue
            await self._handle_command(line.strip())
        await self.close()

    async def _handle_command(self, line: str) -> None:
        if not line:
            return
        parts = line.split()
        command = parts[0].lower()
        args = parts[1:]

        if command in {"quit", "exit"}:
            self._should_exit = True
            return
        if command in {"help", "?"}:
            self._print_help()
            return
        if command == "create":
            await self.create_game()
            return
        if command == "bootstrap":
            await self.bootstrap(self._parse_optional_int(args, 0) or None)
            return
        if command == "join":
            for raw in args:
                await self.join_player(int(raw))
            return
        if command == "players":
            self._print_players()
            return
        if command == "sync":
            await self._send_simple_action(args, "sync")
            return
        if command == "bid":
            await self._send_numeric_action(args, "bid")
            return
        if command == "call-rank":
            await self._send_numeric_action(args, "call-partner-rank")
            return
        if command == "call-suit":
            await self._send_call_suit(args)
            return
        if command == "play":
            await self._send_play(args)
            return
        if command == "reorder":
            await self._send_reorder(args)
            return

        print(f"Unknown command '{command}'. Type 'help' for options.")

    async def _send_simple_action(self, args: List[str], message_type: str) -> None:
        player_id = self._require_player_arg(args)
        await self._send_action(player_id, message_type)

    async def _send_numeric_action(self, args: List[str], message_type: str) -> None:
        player_id, value = self._require_player_and_value(args)
        await self._send_action(player_id, message_type, **{self._value_key(message_type): value})

    async def _send_call_suit(self, args: List[str]) -> None:
        player_id = self._require_player_arg(args)
        if len(args) < 2:
            raise ValueError("call-suit requires <player_id> <suit>")
        suit = args[1].lower()
        if suit not in VALID_SUITS:
            raise ValueError(f"Suit must be one of {', '.join(sorted(VALID_SUITS))}")
        await self._send_action(player_id, "call-partner-suit", partner_suit=suit)

    async def _send_play(self, args: List[str]) -> None:
        player_id = self._require_player_arg(args)
        if len(args) < 3:
            raise ValueError("play requires <player_id> <suit> <rank>")
        card = self._parse_card_args(args[1], args[2])
        await self._send_action(player_id, "play", card=card)

    async def _send_reorder(self, args: List[str]) -> None:
        player_id = self._require_player_arg(args)
        if len(args) < 2:
            raise ValueError("reorder requires <player_id> <card1> <card2> ...")
        cards = [parse_card_token(token) for token in args[1:]]
        await self._send_action(player_id, "reorder", hand=cards)

    async def _send_action(self, player_id: int, message_type: str, **payload) -> None:
        if self.game_id is None:
            raise RuntimeError("No game created yet. Use create or bootstrap first.")
        session = self.players.get(player_id)
        if not session or not session.websocket:
            raise RuntimeError(f"Player {player_id} is not connected.")
        message = build_action_payload(
            message_type, self.game_id, player_id=player_id, **payload
        )
        await session.websocket.send(json.dumps(message))
        print(f"Sent {message_type} for player {player_id} ({payload or 'no payload'}).")

    def _value_key(self, message_type: str) -> str:
        if message_type == "bid":
            return "bid"
        if message_type == "call-partner-rank":
            return "partner_rank"
        return "value"

    async def _post_json(
        self, url: str, body: Optional[Dict[str, object]] = None, headers=None
    ) -> Dict[str, object]:
        payload = json.dumps(body or {}).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req) as resp:  # nosec - dev helper
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:  # pragma: no cover - runtime
            detail = exc.read().decode()
            raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {detail}") from exc

    def _print_help(self) -> None:
        print(
            """
Available commands:
  bootstrap [n]      Create a game and auto-join n players (default: 5)
  create             Create a new game (clears existing state)
  join <p0> [p1...]  Join specific player ids using the stored host token
  players            Show joined players
  sync <pid>         Request a sync snapshot for a player
  bid <pid> <amt>    Submit a bid (use -1 to pass)
  call-rank <pid> r  Call partner rank (1-10)
  call-suit <pid> s  Call partner suit (coins|cups|swords|clubs)
  play <pid> s r     Play a card (e.g., play 2 coins 7)
  reorder <pid> ...  Persist hand order (cards like coins-7 cups-3 ...)
  help               Show this message
  quit/exit          Close all websockets and exit
"""
        )

    def _print_players(self) -> None:
        if not self.players:
            print("No players joined yet.")
            return
        for pid, session in sorted(self.players.items()):
            status = "connected" if session.websocket and not session.websocket.closed else "closed"
            print(f"Player {pid}: {status}")

    def _parse_optional_int(self, args: List[str], index: int) -> Optional[int]:
        try:
            return int(args[index])
        except (IndexError, ValueError):
            return None

    def _require_player_arg(self, args: List[str]) -> int:
        if not args:
            raise ValueError("Command requires a <player_id> argument")
        return int(args[0])

    def _require_player_and_value(self, args: List[str]) -> (int, int):
        if len(args) < 2:
            raise ValueError("Command requires <player_id> <value>")
        player_id = int(args[0])
        value = int(args[1])
        return player_id, value

    def _parse_card_args(self, suit: str, rank: str) -> Dict[str, int]:
        return parse_card_token(f"{suit}-{rank}")

    async def close(self) -> None:
        for session in self.players.values():
            if session.listener:
                session.listener.cancel()
            if session.websocket:
                await session.websocket.close()
        self.players.clear()
        print("Closed all player sessions.")


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Briscola websocket test REPL")
    parser.add_argument(
        "--http-base",
        default="http://localhost:8000",
        help="Base URL for the Django web service",
    )
    parser.add_argument(
        "--ws-url",
        default="ws://localhost:8000/ws/client/",
        help="Websocket URL exposed by Django Channels",
    )
    parser.add_argument(
        "--players",
        type=int,
        default=5,
        help="Number of players to bootstrap when using the bootstrap command",
    )
    parser.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Start the REPL without creating a game or joining players",
    )
    args = parser.parse_args(argv)

    repl = BriscolaRepl(args.http_base, args.ws_url, default_players=args.players)

    async def _run() -> None:
        if not args.no_bootstrap:
            await repl.bootstrap()
        await repl.repl()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:  # pragma: no cover - user flow
        print("\nReceived Ctrl+C, closing...")
        try:
            asyncio.run(repl.close())
        except Exception:  # pragma: no cover - cleanup best effort
            pass
        sys.exit(0)


if __name__ == "__main__":
    main()


def describe_message(message: Dict[str, object]) -> str:
    """Render a websocket message in a human-readable, single-line format."""

    def _payload(msg: Dict[str, object]) -> Dict[str, object]:
        nested = msg.get("payload")
        if isinstance(nested, dict) and nested.get("message_type"):
            # Merge common envelope fields when available
            merged = {**nested}
            for key in ("game_id", "action_id", "player_id"):
                merged.setdefault(key, msg.get(key))
            return merged
        return msg

    body = _payload(message)
    message_type = body.get("message_type")

    def _card(card: Optional[Dict[str, object]]) -> str:
        if not isinstance(card, dict):
            return "(unknown card)"
        suit = card.get("suit")
        rank = card.get("rank")
        label = f"{suit} {rank}" if suit and rank else json.dumps(card, sort_keys=True)
        if "card_id" in card:
            label += f" (#{card['card_id']})"
        return label

    def _hand(cards: Optional[List[object]]) -> str:
        if not isinstance(cards, list):
            return "(unknown hand)"
        return ", ".join(_card(c) for c in cards) or "(empty hand)"

    def _scores(scores: Optional[List[Dict[str, object]]]) -> str:
        if not isinstance(scores, list):
            return "(unknown scores)"
        return ", ".join(
            f"p{entry.get('player_id')}: {entry.get('points')}" for entry in scores
        )

    def _trick(trick_cards: Optional[List[Dict[str, object]]]) -> str:
        if not isinstance(trick_cards, list):
            return "(unknown trick)"
        return ", ".join(
            f"p{entry.get('player_id')} {_card(entry.get('card'))}" for entry in trick_cards
        )

    if message_type == "action.result":
        status = body.get("status")
        action_id = body.get("action_id")
        if status == "ok":
            effects = body.get("effects") or {}
            effect_keys = ", ".join(sorted(effects))
            suffix = f" Effects: {effect_keys}." if effect_keys else ""
            return f"Action {action_id} succeeded.{suffix}".strip()
        code = body.get("code", "unknown error")
        reason = body.get("reason")
        recovery = body.get("recovery")
        detail = code
        if reason:
            detail += f" ({reason})"
        if recovery:
            detail += f" – recovery: {recovery}"
        return f"Action {action_id} failed: {detail}."

    if message_type == "hand.update":
        return f"Hand updated: {_hand(body.get('hand'))}."

    if message_type == "trick.played":
        current = body.get("current_player_id")
        played_by = body.get("player_id")
        card = _card(body.get("card"))
        trick = _trick(body.get("trick"))
        parts = [f"Player {played_by} played {card}"]
        if trick:
            parts.append(f"trick: {trick}")
        if current is not None:
            parts.append(f"next: player {current}")
        return "; ".join(parts) + "."

    if message_type == "trick.won":
        winner = body.get("winner_id")
        points = body.get("points")
        trick = _trick(body.get("trick_cards"))
        scores = _scores(body.get("scores"))
        return f"Trick won by player {winner} for {points} points (trick: {trick}; scores: {scores})."

    if message_type == "score.update":
        delta = body.get("delta")
        delta_text = (
            f" (delta p{delta.get('player_id')}: {delta.get('points')})" if isinstance(delta, dict) else ""
        )
        return f"Scores updated: {_scores(body.get('scores'))}{delta_text}."

    if message_type == "phase.change":
        phase = body.get("phase")
        trump = body.get("trump_suit")
        caller = body.get("caller_id")
        partner = body.get("partner_id")
        bid = body.get("bid")
        extras = []
        if trump:
            extras.append(f"trump: {trump}")
        if caller is not None:
            extras.append(f"caller: {caller}")
        if partner is not None:
            extras.append(f"partner: {partner}")
        if bid is not None:
            extras.append(f"bid: {bid}")
        suffix = f" ({'; '.join(extras)})" if extras else ""
        return f"Phase changed to {phase}{suffix}."

    if message_type in {"player.join", "player.leave", "player.reconnect"}:
        player_id = body.get("player_id")
        name = body.get("name")
        suffix = f" as {name}" if name else ""
        verb = message_type.split(".")[1]
        return f"Player {player_id}{suffix} {verb}ed."

    if message_type == "sync":
        phase = body.get("phase") or body.get("state", {}).get("phase")
        current = body.get("current_player_id") or body.get("state", {}).get("current_player_id")
        parts = ["Sync snapshot"]
        if phase:
            parts.append(f"phase: {phase}")
        if current is not None:
            parts.append(f"current player: {current}")
        return "; ".join(parts) + "."

    if message_type == "error":
        code = body.get("code", "error")
        reason = body.get("reason")
        return f"Error {code}: {reason or 'no reason provided'}."

    return json.dumps(message, indent=2)
