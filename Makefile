.PHONY: install install-all dev test test-cov docker-up docker-down lint format

install:
	pip install -r requirements.txt

install-all:
	pip install -r requirements.txt -r requirements.dashboard.txt -r requirements.test.txt

dev:
	MQTT_BROKER_HOST=localhost uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=simulation --cov=config --cov-report=html --cov-report=term-missing

docker-up:
	docker compose up

docker-down:
	docker compose down

docker-storage:
	docker compose --profile storage up

lint:
	ruff check .

format:
	ruff format .
