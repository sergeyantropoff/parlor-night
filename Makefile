PYTHON ?= python3.12
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

.PHONY: install up down logs migrate create-admin test lint format backup \
	registry-login image namespace ensure-secret registry-secret deploy undeploy status kube-admin \
	compose compose-down compose-logs compose-admin

REGISTRY ?= hub.antropoff.ru
IMAGE_NAME ?= parlor-night/parlor-night
TAG ?= $(shell date -u +%Y%m%d%H%M%S)
IMAGE := $(REGISTRY)/$(IMAGE_NAME)
PLATFORMS ?= linux/amd64,linux/arm64
RELEASE ?= parlor-night
KUBE_NAMESPACE ?= parlor-night
HELM ?= helm
KUBECTL ?= kubectl
CHART := deploy/helm/parlor-night
COMPOSE_FILE := docker-compose.standalone.yml
COMPOSE_ENV := deploy/standalone.env
COMPOSE := docker compose --env-file $(COMPOSE_ENV) -f $(COMPOSE_FILE)
POSTGRES_USER ?= boardmentor
POSTGRES_DB ?= boardmentor

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"

up:
	test -f .env || cp .env.example .env
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

migrate:
	docker compose exec web python -m scripts.migrate

create-admin:
	docker compose exec -e ADMIN_USERNAME -e ADMIN_PASSWORD web python -m scripts.create_admin

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check app scripts tests

format:
	$(PY) -m ruff format app scripts tests
	$(PY) -m ruff check --fix app scripts tests

backup:
	mkdir -p backups
	docker compose exec -T db sh -c 'pg_dump -U "$$POSTGRES_USER" "$$POSTGRES_DB"' > backups/boardmentor-$$(date +%Y%m%d-%H%M%S).sql

registry-login:
	@if [ -n "$$HUB_USERNAME" ] && [ -n "$$HUB_PASSWORD" ]; then \
		printf '%s' "$$HUB_PASSWORD" | docker login $(REGISTRY) --username "$$HUB_USERNAME" --password-stdin; \
	fi

image: registry-login
	docker buildx build --platform $(PLATFORMS) --push \
		-t $(IMAGE):$(TAG) -t $(IMAGE):latest .

namespace:
	@$(KUBECTL) get namespace $(KUBE_NAMESPACE) >/dev/null 2>&1 || $(KUBECTL) create namespace $(KUBE_NAMESPACE)

ensure-secret: namespace
	@set -e; \
	if $(KUBECTL) -n $(KUBE_NAMESPACE) get secret $(RELEASE)-env >/dev/null 2>&1; then \
		echo "Секрет $(RELEASE)-env уже есть"; \
	else \
		url=$$(DB_HOST='$(RELEASE)-db' POSTGRES_USER='$(POSTGRES_USER)' POSTGRES_DB='$(POSTGRES_DB)' python3 deploy/scripts/database_url.py); \
		$(KUBECTL) -n $(KUBE_NAMESPACE) create secret generic $(RELEASE)-env \
			--from-literal=SECRET_KEY="$$SECRET_KEY" \
			--from-literal=POSTGRES_USER='$(POSTGRES_USER)' \
			--from-literal=POSTGRES_PASSWORD="$$POSTGRES_PASSWORD" \
			--from-literal=POSTGRES_DB='$(POSTGRES_DB)' \
			--from-literal=DATABASE_URL="$$url"; \
	fi

registry-secret: namespace
	@if [ -n "$$HUB_USERNAME" ] && [ -n "$$HUB_PASSWORD" ]; then \
		$(KUBECTL) -n $(KUBE_NAMESPACE) create secret docker-registry hub-antropoff \
			--docker-server=$(REGISTRY) \
			--docker-username="$$HUB_USERNAME" \
			--docker-password="$$HUB_PASSWORD" \
			--dry-run=client -o yaml | $(KUBECTL) apply -f -; \
	fi

deploy: image ensure-secret registry-secret
	@pull=""; \
	if $(KUBECTL) -n $(KUBE_NAMESPACE) get secret hub-antropoff >/dev/null 2>&1; then \
		pull="--set imagePullSecrets[0].name=hub-antropoff"; \
	fi; \
	$(HELM) upgrade --install $(RELEASE) $(CHART) \
		--namespace $(KUBE_NAMESPACE) --create-namespace \
		--set fullnameOverride=$(RELEASE) \
		--set image.repository=$(IMAGE) \
		--set image.tag=$(TAG) \
		$$pull \
		--wait --timeout 10m

undeploy:
	$(HELM) uninstall $(RELEASE) --namespace $(KUBE_NAMESPACE)

status:
	$(KUBECTL) -n $(KUBE_NAMESPACE) get pods,svc,ingress

kube-admin:
	$(KUBECTL) -n $(KUBE_NAMESPACE) exec deploy/$(RELEASE) -- \
		env ADMIN_USERNAME="$$ADMIN_USERNAME" ADMIN_PASSWORD="$$ADMIN_PASSWORD" \
		python -m scripts.create_admin

$(COMPOSE_ENV):
	cp deploy/standalone.env.example $(COMPOSE_ENV)

compose: image $(COMPOSE_ENV)
	PARLOR_IMAGE=$(IMAGE):$(TAG) $(COMPOSE) up -d

compose-down: $(COMPOSE_ENV)
	$(COMPOSE) down

compose-logs: $(COMPOSE_ENV)
	$(COMPOSE) logs -f --tail=200

compose-admin: $(COMPOSE_ENV)
	$(COMPOSE) exec \
		-e ADMIN_USERNAME -e ADMIN_PASSWORD \
		web python -m scripts.create_admin
