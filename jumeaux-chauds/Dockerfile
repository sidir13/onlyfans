# ── Simulateur + API FastAPI ──────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="Tristan Vanrullen"
LABEL description="Jumeaux Chauds — simulateur thermique IoT + API FastAPI"

WORKDIR /app

# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source
COPY config/       config/
COPY simulation/   simulation/
COPY mqtt/         mqtt/
COPY api/          api/
COPY scripts/      scripts/
COPY __init__.py   .

# Variables d'environnement par défaut
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SCENARIO=nominal \
    CLUSTER_ID=cluster_alpha \
    MQTT_ENABLED=1 \
    MQTT_BROKER_HOST=mosquitto \
    MQTT_BROKER_PORT=1883 \
    API_HOST=0.0.0.0 \
    API_PORT=8000

EXPOSE 8000

# Healthcheck sur l'endpoint racine de l'API
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
