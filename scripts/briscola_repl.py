"""
Interactive REPL for debugging and testing Briscola game interactions.

Usage:
    python scripts/briscola_repl.py [--server URL]

Commands:
    connect <game_id> <player_id>  - Connect to a game as a player
    bootstrap [n]                  - Bootstrap a new game with n players (default: 2)
    bid <amount>                   - Place a bid
    play <suit> <rank>             - Play a card
    sync                           - Request game state sync
    status                         - Show connection status
    quit                           - Exit the REPL
"""

import argparse
import asyncio
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple

PROTOCOL_VERSION = "1.0.0"


def describe_message(message: Dict[str, Any]) -> str:
    """Return a human-readable single-line description of a game message."""
    if not isinstance(message, dict):
        return json.dumps(message, separators=(",", ":"), sort_keys=True)

    message_type = message.get("message_type", "")
    game_id = message.get("game_id", "")
    player_id = message.get("player_id")

    if message_type == "action.result":
        status = message.get("status", "unknown")
        action_id = message.get("action_id", "")
        if status == "ok":
            return f"Action {action_id}: OK"
        code = message.get("code", "")
        reason = message.get("reason", "")
        return f"Action {action_id}: {status} - {code}: {reason}"

    if message_type == "hand.update":
        hand = message.get("hand", [])
        return f"Hand update for player {player_id}: {len(hand)} cards"

    if message_type == "trick.played":
        card = message.get("card", {})
        suit = card.get("suit", "?")
        rank = card.get("rank", "?")
        return f"Player {player_id} played {rank} of {suit}"

    if message_type == "trick.won":
        winner = message.get("winner_id")
        points = message.get("points", 0)
        return f"Player {winner} won trick for {points} points"

    if message_type == "phase.change":
        phase = message.get("phase", "unknown")
        return f"Phase changed to: {phase}"

    if message_type == "sync":
        phase = message.get("phase", "unknown")
        return f"Sync: game {game_id} in phase {phase}"

    if message_type in ("player.join", "player.leave", "player.reconnect"):
        verb = message_type.split(".")[1]
        past_map = {"join": "joined", "leave": "left", "reconnect": "reconnected"}
        past = past_map.get(verb, verb + "ed")
        suffix = f" ({message.get('name')})" if message.get("name") else ""
        return f"Player {player_id}{suffix} {past}."

    if message_type == "score.update":
        scores = message.get("scores", [])
        return f"Score update: {scores}"

    # Fallback: compact single-line JSON
    return json.dumps(message, separators=(",", ":"), sort_keys=True)


def build_action_payload(
    message_type: str,
    game_id: str,
    player_id: Optional[int] = None,
    role: str = "player",
    **extra: Any
) -> Dict[str, Any]:
    """Build an action payload with envelope fields."""
    action_id = f"{message_type}-{uuid.uuid4()}"
    ts = int(time.time() * 1000)
    payload: Dict[str, Any] = {
        "message_type": message_type,
        "game_id": game_id,
        "action_id": action_id,
        "ts": ts,
        "version": PROTOCOL_VERSION,
        "origin": "repl",
    }
    if player_id is not None:
        payload["player_id"] = player_id
    payload["role"] = role
    payload.update(extra)
    return payload


class BriscolaREPL:
    """Interactive REPL for Briscola game interactions."""

    def __init__(self, server_url: str = "http://localhost:8000"):
        self.server_url = server_url.rstrip("/")
        self.game_id: Optional[str] = None
        self.player_id: Optional[int] = None
        self.role: str = "player"
        self.token: Optional[str] = None
        self.listeners: Dict[int, asyncio.Task] = {}
        self._running = True

    def _post_json(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST JSON to the server and return the response."""
        url = f"{self.server_url}{endpoint}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _parse_optional_int(self, args: str, default: Optional[int] = None) -> Optional[int]:
        """Parse an optional integer from args string."""
        args = args.strip()
        if not args:
            return default
        try:
            return int(args)
        except ValueError:
            return default

    def _require_player_and_value(self, args: str) -> Tuple[int, int]:
        """Parse required player_id and value from args."""
        parts = args.strip().split()
        if len(parts) < 2:
            raise ValueError("Expected: <player_id> <value>")
        return int(parts[0]), int(parts[1])

    async def bootstrap(self, num_players: Optional[int] = None) -> None:
        """Bootstrap a new game with the specified number of players."""
        n = num_players if num_players is not None else 2
        print(f"Bootstrapping game with {n} players...")
        # This would typically call a game creation endpoint
        game_id = f"GAME{uuid.uuid4().hex[:4].upper()}"
        self.game_id = game_id
        self.player_id = 0
        print(f"Created game: {game_id}")
        print(f"You are player {self.player_id}")

    async def connect(self, game_id: str, player_id: int) -> None:
        """Connect to an existing game."""
        self.game_id = game_id
        self.player_id = player_id
        print(f"Connected to game {game_id} as player {player_id}")

    async def bid(self, amount: int) -> None:
        """Place a bid."""
        if not self.game_id or self.player_id is None:
            print("Error: Not connected to a game")
            return
        payload = build_action_payload(
            "bid",
            self.game_id,
            self.player_id,
            self.role,
            bid=amount,
        )
        print(f"Bid payload: {describe_message(payload)}")

    async def play_card(self, suit: str, rank: int) -> None:
        """Play a card."""
        if not self.game_id or self.player_id is None:
            print("Error: Not connected to a game")
            return
        payload = build_action_payload(
            "play",
            self.game_id,
            self.player_id,
            self.role,
            card={"suit": suit, "rank": rank},
        )
        print(f"Play payload: {describe_message(payload)}")

    async def sync_state(self) -> None:
        """Request a game state sync."""
        if not self.game_id:
            print("Error: Not connected to a game")
            return
        payload = build_action_payload(
            "sync",
            self.game_id,
            self.player_id,
            self.role,
        )
        print(f"Sync payload: {describe_message(payload)}")

    async def status(self) -> None:
        """Show current connection status."""
        print(f"Server: {self.server_url}")
        print(f"Game ID: {self.game_id or 'Not connected'}")
        print(f"Player ID: {self.player_id if self.player_id is not None else 'N/A'}")
        print(f"Role: {self.role}")

    async def _listen_to_player(self, player_id: int) -> None:
        """Listen for events for a specific player."""
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def _handle_command(self, line: str) -> None:
        """Handle a single command line."""
        if not line:
            return

        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "quit" or cmd == "exit":
            self._running = False
            print("Goodbye!")
            return

        if cmd == "connect":
            parts = args.split()
            if len(parts) < 2:
                print("Usage: connect <game_id> <player_id>")
                return
            await self.connect(parts[0], int(parts[1]))
            return

        if cmd == "bootstrap":
            n = self._parse_optional_int(args, 0)
            await self.bootstrap(n if n is not None else None)
            return

        if cmd == "bid":
            amount = self._parse_optional_int(args)
            if amount is None:
                print("Usage: bid <amount>")
                return
            await self.bid(amount)
            return

        if cmd == "play":
            parts = args.split()
            if len(parts) < 2:
                print("Usage: play <suit> <rank>")
                return
            try:
                await self.play_card(parts[0], int(parts[1]))
            except ValueError:
                print("Error: rank must be a number")
            return

        if cmd == "sync":
            await self.sync_state()
            return

        if cmd == "status":
            await self.status()
            return

        if cmd == "help":
            print(__doc__)
            return

        print(f"Unknown command: {cmd}. Type 'help' for available commands.")

    async def repl(self) -> None:
        """Run the interactive REPL loop."""
        print("Briscola REPL - type 'help' for commands, 'quit' to exit")
        print()

        while self._running:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("briscola> ")
                )
            except EOFError:
                break
            except KeyboardInterrupt:
                print()
                break

            try:
                await self._handle_command(line.strip())
            except Exception as exc:
                print("Error:", exc)

    async def close(self) -> None:
        """Clean up resources."""
        self._running = False
        for listener in self.listeners.values():
            listener.cancel()
        for listener in self.listeners.values():
            try:
                await listener
            except asyncio.CancelledError:
                pass
        self.listeners.clear()


async def main(server_url: str) -> None:
    """Main entry point."""
    repl = BriscolaREPL(server_url)
    try:
        await repl.repl()
    finally:
        await repl.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Briscola game REPL")
    parser.add_argument(
        "--server",
        default="http://localhost:8000",
        help="Server URL (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.server))
