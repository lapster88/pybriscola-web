COMPOSE ?= docker compose
COMPOSE_FILE ?= docker-compose.yml

.PHONY: up up-foreground down build logs ps test-web test-game test-all

# Default to detached so the command returns once services are healthy
up:
	$(COMPOSE) -f $(COMPOSE_FILE) up -d

up-foreground:
	$(COMPOSE) -f $(COMPOSE_FILE) up

down:
	$(COMPOSE) -f $(COMPOSE_FILE) down

build:
	$(COMPOSE) -f $(COMPOSE_FILE) build

logs:
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f

ps:
	$(COMPOSE) -f $(COMPOSE_FILE) ps

test-web:
	$(COMPOSE) -f $(COMPOSE_FILE) run --rm web python -m pytest

test-game:
	$(COMPOSE) -f $(COMPOSE_FILE) run --rm game python -m pytest

test-all: test-web test-game

# Bring up redis+game, run the web integration test (INTEGRATION_E2E=1), then tear down.
test-integration:
	$(COMPOSE) -f $(COMPOSE_FILE) up -d redis game
	$(COMPOSE) -f $(COMPOSE_FILE) run --rm -e INTEGRATION_E2E=1 web python -m pytest tests/test_integration_e2e.py
	$(COMPOSE) -f $(COMPOSE_FILE) down

cli:
	$(COMPOSE) -f $(COMPOSE_FILE) up -d redis web game
	$(COMPOSE) -f $(COMPOSE_FILE) run --rm web python scripts/briscola_repl.py --http-base http://web:8000 --ws-url ws://web:8000/ws/client/
