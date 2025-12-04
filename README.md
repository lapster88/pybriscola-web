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
