COMPOSE ?= docker compose
COMPOSE_FILE ?= docker-compose.yml

.PHONY: up up-foreground down build logs ps

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
