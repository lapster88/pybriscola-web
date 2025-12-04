# Implementation Plan (pybriscola-web)

## Message Contracts & Auth
- Adopt spec messages with `action_id` and standardized events.
- Implement token issuance (player/observer) on create/join; verify on connect/join; enforce seat takeover (new connection wins).
- Add join/sync handlers to `BriscolaClientConsumer`: verify token, add to game group, send role-appropriate snapshot.
- Game IDs: 6-character identifiers used for create/share/join; no discovery/list endpoint for now.
- Observer tokens: issued via create/join-as-observer flow; same signing as player tokens but payload `role:"observer"` (no `player_id`, optional display handle). Observers use the same join endpoint/flow and only receive observer snapshots; any actions are rejected as `forbidden`.
  - Endpoint: e.g., `POST /api/games/{id}/observer-token` (or `join?role=observer`) returning a signed token with `game_id`, `role:"observer"`, optional `display_name`, and short expiry. Shareable observer link can call this to fetch a token client-side.

## Routing & Actions
- Replace the second WebSocket hop with Redis channel-layer bridging:
  - Publish player actions to a per-game channel (e.g., `game.<game_id>.actions`), include `action_id`, `ts`, `version`, `origin:"web"`, and signed claims.
  - Subscribe to per-game events channel (e.g., `game.<game_id>.events`) and broadcast to clients + reply with `action.result` to the originator.
  - Game service only creates/starts per-game servers and monitors heartbeats; per-game servers consume actions and publish events.
- Handle actions: `bid`, `call-partner-rank`, `call-partner-suit`, `play`, `reorder`, `sync`.
- Send `action.result` (status ok/error with codes) and broadcast authoritative events (`trick.played`, `trick.won`, `phase.change`, `hand.update`, `score.update`, `player.join/leave/reconnect`).
- Observer flow: accept observer tokens; never send hands.
- Reorder: accept and persist order server-side; emit `hand.update` with new order to the owner.

## Snapshots & Errors
- Generate phase-specific snapshots (player vs observer) for join/sync and trick-won/end transitions.
- Standardize error codes: `unauthorized`, `join_failed`, `duplicate_connection_handled`, `invalid_turn`, `invalid_card`, `invalid_bid`, `invalid_action`, `forbidden`, `desync`, `game_unavailable`, `routing_failed`.
- Support recovery from game-server crashes: detect lost game server, restart/reconnect, request/load persisted state, and push a fresh `sync` snapshot to clients.
- Persistence choice: use Option 1 (full snapshot per action) in Redis with AOF; games stored at `game:<id>:state`, optional short action log for debugging. Cleanup via TTL/delete when a game ends, configurable per env (`GAME_STATE_TTL_SECONDS`, e.g., 1h dev, 12h prod).
- Deliver failures: emit `action.result` errors for application and delivery/routing failures you detect (e.g., game unavailable, routing_failed); transport/socket errors fall back to connection close.
- Error semantics: use `invalid_*` for rule/phase violations (recovery: retry/noop) and `desync` when client state mismatches server (recovery: sync).

## Auth Propagation
- Client → Web: verify client JWT/token (auth, expiry, seat/role).
- Web → Game: send minimal claims (`game_id`, `player_id`, `role`) with an internal HMAC/signature so the game trusts the envelope without re-verifying client JWTs.
- Include `action_id`, `ts` (epoch ms), `version` (protocol semver), and `origin` in all envelopes; keep `action.result` on the events channel and route back via `action_id`.

## Health & Restart
- Game workers emit heartbeats via a TTL key (`game:<id>:heartbeat`) every ~5s with TTL ~20s.
- Game service (not web) monitors heartbeats and restarts dead workers; on restart it should reload state and resume publishing events.
- Web reacts to `game_unavailable`/`routing_failed` by surfacing errors and, once the game service recovers and publishes events again, triggers a fresh `sync` to clients. Treat event subscription failure as an immediate signal to show “reconnecting”.

## Testing
- WebSocket integration tests: create → join → bid/call → play → trick resolution → reconnect; token validation; takeover behavior.
