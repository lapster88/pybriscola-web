# pybriscola-web

## Dev quickstart (Docker)
- Bring up the stack (web, game, redis): `make up` (foreground) or `make up-detach`.
- Rebuild images: `make build`.
- Tail logs: `make logs`.
- Stop everything: `make down`.
- Inspect status: `make ps`.

Prereqs: Docker (with `docker compose` plugin) and make. The stack uses `REDIS_URL=redis://redis:6379/0` and `PROTOCOL_VERSION=1.0.0` by default.
