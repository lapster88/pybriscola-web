# Actions, Events, and Envelopes (Redis Bridge)

This documents the message types exchanged between web (Django/Channels) and per-game servers over Redis pub/sub channels. The game service only creates/starts games and monitors heartbeats; per-game servers consume actions and publish events/results.
- Actions: publish to `game.<game_id>.actions`
- Events (including `action.result`): publish to `game.<game_id>.events` (from per-game servers)

## Envelope
Every published message (action or event) is wrapped in a JSON envelope:
- `message_type`: action/event type (see below)
- `game_id`: string (6-char id)
- `action_id`: string (UUID or client-generated) — required on actions/results
- `player_id`: int or null (null for observers)
- `role`: `"player"` or `"observer"`
- `ts`: epoch milliseconds
- `version`: protocol semver (default `1.0.0`)
- `origin`: `"web"` or `"game"`
- `payload`: action/event-specific body (may duplicate some top-level fields for clarity)

## Actions (web → game)
Publish to: `game.<game_id>.actions`  
Payloads shown without the envelope keys above.

- `join`  
  - `{ "message_type":"join", "game_id":"...", "player_id":<int|null>, "role":"player|observer" }`
- `sync`  
  - `{ "message_type":"sync", "game_id":"..." }`
- `bid`  
  - `{ "message_type":"bid", "game_id":"...", "player_id":<int>, "bid":<int|-1> }` (`-1` = pass)
- `call-partner-rank`  
  - `{ "message_type":"call-partner-rank", "game_id":"...", "player_id":<int>, "partner_rank":<1-10> }`
- `call-partner-suit`  
  - `{ "message_type":"call-partner-suit", "game_id":"...", "player_id":<int>, "partner_suit":"coins|cups|swords|clubs" }`
- `play`  
  - `{ "message_type":"play", "game_id":"...", "player_id":<int>, "card":{ "suit":"...", "rank":<1-10>, "card_id"?:<0-39> } }`
- `reorder`  
  - `{ "message_type":"reorder", "game_id":"...", "player_id":<int>, "hand":[ {suit,rank} | card_id ... ] }` (persist order; echo via `hand.update`)

## Action Results (game → web → client)
Publish to: `game.<game_id>.events`  
- `action.result`  
  - Success: `{ "message_type":"action.result", "action_id":"...", "status":"ok", "game_id":"...", "effects":{...} }`
  - Error: `{ "message_type":"action.result", "action_id":"...", "status":"error", "game_id":"...", "code":"<error_code>", "reason":"...", "recovery":"sync|retry|noop" }`
  - Error codes: `unauthorized`, `join_failed`, `duplicate_connection_handled`, `invalid_turn`, `invalid_card`, `invalid_bid`, `invalid_action`, `forbidden`, `desync`, `game_unavailable`, `routing_failed`.
  - Semantics: use `invalid_*` for rule/phase violations (retry/noop), `desync` when client/server state mismatch (sync), `game_unavailable`/`routing_failed` for delivery issues.

## Events (game → web → client)
Publish to: `game.<game_id>.events`

- `hand.update`  
  - `{ "message_type":"hand.update", "game_id":"...", "player_id":<int>, "hand":[cards] }` (to owner only)
- `trick.played`  
  - `{ "message_type":"trick.played", "game_id":"...", "player_id":<int>, "card":{...}, "trick":[{player_id,card}], "current_player_id":<int> }`
- `trick.won`  
  - `{ "message_type":"trick.won", "game_id":"...", "winner_id":<int>, "points":<int>, "trick_cards":[{card,player_id}], "scores":[{player_id,points}], "current_player_id":<int> }`
- `score.update`  
  - `{ "message_type":"score.update", "game_id":"...", "scores":[{player_id,points}], "delta"?:{player_id,points} }`
- `phase.change`  
  - `{ "message_type":"phase.change", "game_id":"...", "phase":"...", "trump_suit"?:..., "caller_id"?:..., "partner_id"?:..., "partner_rank"?:..., "bid"?:... }`
- `player.join` / `player.leave` / `player.reconnect`  
  - `{ "message_type":"player.join", "game_id":"...", "player_id":<int>, "name": "..." }` (and similar)
- `sync`  
  - Full snapshot per spec (phase, players, scores, bids, trick, hand for owner, etc.)
- `error`  
  - `{ "message_type":"error", "code":"...", "reason":"..." }` (non-action errors; prefer action.result when tied to an action)

## State & Heartbeat Keys (Redis)
- Snapshots: `game:<game_id>:state` (full state per action; TTL `GAME_STATE_TTL_SECONDS`; used by per-game server on restart)
- Heartbeat: `game:<game_id>:heartbeat` (set ~5s, TTL ~20s; watched by game service supervisor to restart servers)

## Tokens
- Player token: JWT signed with `SECRET_KEY`, claims `{game_id, player_id, role:"player", exp}`.
- Observer token: JWT with `{game_id, role:"observer", display_name?, exp}`; actions forbidden.

## Roles
- BriscolaService: watches `game.*.actions`, (re)starts per-game GameServer threads, monitors heartbeat keys, reloads state from snapshot on restart, and replays the initial action if needed on first sight of a game_id.
- GameServer (per game): subscribes to `game.<id>.actions`, validates/executes actions, emits `action.result` + events to `game.<id>.events`, persists snapshots to `game:<id>:state`, writes `game:<id>:heartbeat`, and reloads snapshots on restart. Service restarts if thread dies or heartbeat expires.
