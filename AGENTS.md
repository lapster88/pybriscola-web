# AGENTS.md

Notes for automation/agent work in this repo:

- Run and add tests as you implement features. Use pytest/Django Channels test client where possible; mock Redis for bridge tests.
- Default commands: `make up` (detached compose), `make up-foreground`, `make down`, `make logs`, `make build`.
- Redis defaults: `REDIS_URL=redis://redis:6379/0`, protocol version `1.0.0`.
- Message contracts and flows are documented in `docs/actions_events.md` and `docs/architecture.md`; keep changes in sync.
- Persistence TTL configurable via `GAME_STATE_TTL_SECONDS` (e.g., 1h dev/12h prod).
