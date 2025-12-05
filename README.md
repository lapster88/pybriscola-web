# pybriscola-web

## Dev quickstart (Docker)
- Bring up the stack (web, game, redis): `make up` (foreground) or `make up-detach`.
- Rebuild images: `make build`.
- Tail logs: `make logs`.
- Stop everything: `make down`.
- Inspect status: `make ps`.
- Run unit tests: `make test-web` (frontend/web) and `make test-game` (game engine).
- Run end-to-end Redis bridge smoke test: `make test-integration` (brings up redis+game, runs web integration test, then tears down).

### Minting dev tokens
- Use `python scripts/mint_token.py --game-id TEST01 --player-id 0 --role player` to mint a player token (uses `SECRET_KEY` env, default `devsecret`).
- Observers: `python scripts/mint_token.py --game-id TEST01 --role observer`.

Prereqs: Docker (with `docker compose` plugin) and make. The stack uses `REDIS_URL=redis://redis:6379/0` and `PROTOCOL_VERSION=1.0.0` by default.

### CLI test harness
- `python scripts/briscola_repl.py` will create a new game, mint five player tokens, join them over websockets, and drop you into a REPL.
- Commands (type `help` inside the REPL for the full list):
  - `bootstrap [n]`: create a game and join `n` players (default 5)
  - `play <pid> <suit> <rank>`: play a card as a specific player (e.g., `play 2 coins 7`)
  - `bid <pid> <amt>` / `call-rank <pid> <r>` / `call-suit <pid> <suit>` / `sync <pid>`: send the corresponding action for a given player
  - `reorder <pid> <card...>`: persist a hand order using tokens like `coins-7` or `cups:10`
- Use `--no-bootstrap` to start the REPL without creating or joining a game, or `--players`/`--http-base`/`--ws-url` to customize defaults.
