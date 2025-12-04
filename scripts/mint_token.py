"""
Utility to mint JWTs for players or observers during development/testing.

Examples:
  python scripts/mint_token.py --game-id TEST01 --player-id 0 --role player
  python scripts/mint_token.py --game-id TEST01 --role observer --ttl-minutes 120
"""

import argparse
import os
import time

import jwt


def main():
    parser = argparse.ArgumentParser(description="Mint a JWT for pybriscola dev/testing.")
    parser.add_argument("--game-id", required=True, help="6-char game id")
    parser.add_argument("--player-id", type=int, help="Player seat id (omit for observers)")
    parser.add_argument(
        "--role",
        choices=["player", "observer"],
        default="player",
        help="Role for the token",
    )
    parser.add_argument(
        "--ttl-minutes",
        type=int,
        default=60,
        help="Token lifetime in minutes (default 60)",
    )
    args = parser.parse_args()

    secret = os.environ.get("SECRET_KEY", "devsecret")
    exp = int(time.time()) + args.ttl_minutes * 60
    claims = {"game_id": args.game_id, "role": args.role, "exp": exp}
    if args.player_id is not None:
        claims["player_id"] = args.player_id

    token = jwt.encode(claims, secret, algorithm="HS256")
    print(token)


if __name__ == "__main__":
    main()
