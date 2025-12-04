# PyBriscola Architecture (Draft)

## Mermaid Diagram
```mermaid
flowchart LR
    subgraph Frontend["Frontend (React)"]
        C["WS client<br/>/ws/client<br/>actions with action_id"]
    end

    subgraph Web["Django/Channels"]
        BCC["BriscolaClientConsumer<br/>verify JWT<br/>publish actions to Redis<br/>events -> client<br/>action.result on errors"]
        OT["Observer token endpoint<br/>POST /api/games/{id}/observer-token<br/>JWT role=observer"]
    end

    subgraph Redis["Redis"]
        RA["game.<id>.actions<br/>(pubsub)"]
        RE["game.<id>.events<br/>(pubsub)"]
        RS["game:<id>:state<br/>(snapshot, TTL)<br/>used to reload on restart"]
        RH["game:<id>:heartbeat<br/>(~5s set, ~20s TTL)<br/>monitored by service"]
    end

    subgraph Game["Game Service / Servers"]
        GS["Game service<br/>create/start games<br/>monitor heartbeats"]
        GE["Per-game engine<br/>consume actions<br/>publish events/results<br/>validate/execute<br/>persist state<br/>heartbeat"]
    end

    C -->|WS join/sync/actions| BCC
    C -.->|observer token| OT
    BCC -->|publish| RA
    RE -->|events/snapshots/action.result| BCC
    GS --> GE
    GS -.->|monitor| RH
    GE -->|consume| RA
    GE -->|publish events/results| RE
    GE --> RS
    GE --> RH
    GE -.->|restart loads| RS

    subgraph Meta["Meta"]
        Proto["Protocol: PROTOCOL_VERSION=1.0.0<br/>envelope: action_id, ts (ms), version, origin, claims"]
        Persist["Persistence: full snapshot per action<br/>TTL configurable (GAME_STATE_TTL_SECONDS)"]
        Errors["Errors: unauthorized, join_failed, duplicate_connection_handled,<br/>invalid_turn, invalid_card, invalid_bid, invalid_action,<br/>forbidden, desync, game_unavailable, routing_failed"]
        Tokens["Tokens: player (game_id, player_id, role), observer (game_id, role=observer)"]
        Roles["Roles:<br/>BriscolaService: start/restart per-game servers, monitor heartbeats, replay first action<br/>GameServer: consume actions, emit action.result + events, persist state, heartbeat"]
    end

    BCC -.-> Proto
    GE -.-> Persist
    BCC -.-> Errors
    OT -.-> Tokens
    GS -.-> Roles
    GE -.-> Roles
```

## Component Responsibilities (as shown in the diagram)
- **Frontend (React)**: Maintains a WebSocket to `/ws/client/`, sends actions with `action_id`, receives `action.result`, events, and snapshots; uses observer/player tokens to join.
- **Web (Django/Channels)**: Verifies JWTs (player/observer), publishes client actions to Redis `game.<id>.actions`, subscribes to `game.<id>.events`, forwards events/action.results to clients, and issues observer tokens via HTTP endpoint.
- **Redis**: Transports actions/events via pubsub (`game.<id>.actions` / `game.<id>.events`) and stores state snapshots (`game:<id>:state`, TTL) and heartbeats (`game:<id>:heartbeat`, ~5s set, ~20s TTL, monitored).
- **Game Service**: Creates/starts per-game servers, monitors heartbeat keys, restarts servers if heartbeats expire, and replays the first action if needed when a server starts.
- **Per-game GameServer**: Subscribes to `game.<id>.actions`, validates/executes actions (bid, call-rank/suit, play, reorder, sync), emits `action.result` + events to `game.<id>.events`, persists snapshots to Redis, writes heartbeats, and reloads state from snapshots on restart.
- **Meta**: Protocol (PROTOCOL_VERSION, envelope fields), persistence (snapshot TTL), error codes (e.g., unauthorized, invalid_action, desync), token roles (player/observer), roles (service vs per-game server).
