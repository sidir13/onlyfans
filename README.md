# 🌡️ Jumeaux Chauds

> **Simulateur de jumeaux numériques IoT pour la maintenance prédictive de clusters de machines**

**Auteur :** Tristan Vanrullen  
**Organisation :** La Plateforme — École Numérique, Marseille  
**Dépôt :** [https://github.com/TristanV/jumeaux-chauds](https://github.com/TristanV/jumeaux-chauds)  
**Licence :** MIT  
**Version :** 1.0.0 (spécifications)

---

## Présentation

**Jumeaux Chauds** est un simulateur Python de jumeaux numériques pour un cluster de machines IoT dotées de capteurs physiques. Le projet produit des flux de données réalistes en MQTT, expose une API de commande FastAPI, et fournit un dashboard de visualisation temps réel sous Streamlit.

Il est conçu comme support pédagogique pour des étudiants en data engineering, IoT et intelligence artificielle, avec un noyau fonctionnel stable et de nombreuses pistes d'extension documentées.

---

## Fonctionnalités principales

- **Simulation physique** : modèle thermique du 1er ordre (température, puissance, vitesse des ventilateurs) avec états persistants (`ON` / `OFF` / `DEGRADED`)
- **Streaming MQTT** : publication continue des données capteurs sur un broker Mosquitto via `aiomqtt` (MQTTv5 pur asyncio)
- **API de commande** : FastAPI avec WebSocket — allumage/extinction des machines, réglage des ventilateurs, injection de pannes à chaud
- **Configuration hiérarchique** : fichiers YAML avec héritage sur 3 niveaux (cluster → rôle → machine individuelle) via OmegaConf
- **Scénarios de simulation** : mode nominal (charge sinusoïdale) et mode stress (montée en charge + pannes Weibull)
- **Dashboard Streamlit** : visualisation temps réel via WebSocket push
- **Stack de stockage optionnelle** : consumer MQTT → TimescaleDB + Grafana, activable via profil Docker Compose

---

## Architecture rapide

```
Mosquitto broker ←── aiomqtt publisher ←── ClusterSimulator
                                                  │
                                           FastAPI lifespan
                                                  │
                         ┌────────────────────────┤
                         │                        │
                    REST + WS              YAML config
                    endpoints             (OmegaConf merge)
                         │
                   Streamlit dashboard
```

---

## Démarrage rapide

### Prérequis

- Docker 24+ et Docker Compose v2
- Python 3.11+ (développement local)

### Lancement avec Docker Compose

```bash
# Cloner le dépôt
git clone https://github.com/TristanV/jumeaux-chauds.git
cd jumeaux-chauds

# Mode minimal : simulateur + broker MQTT + dashboard
docker compose up

# Accéder au dashboard
open http://localhost:8501

# Accéder à la documentation API (OpenAPI)
open http://localhost:8000/docs
```

### Lancement avec stockage TimescaleDB + Grafana

```bash
docker compose --profile storage up

# Grafana disponible sur
open http://localhost:3000   # admin / admin
```

### Changer de scénario

```bash
# Démarrer en mode stress
SCENARIO=stress docker compose up

# Ou via l'API à chaud
curl -X PUT http://localhost:8000/simulation/scenario \
     -H 'Content-Type: application/json' \
     -d '{"scenario": "stress"}'
```

---

## Structure du projet

```
jumeaux-chauds/
│
├── config/
│   ├── base.yaml                  # Configuration cluster + profils par rôle
│   └── scenarios/
│       ├── nominal.yaml           # Scénario nominal (charge sinusoïdale)
│       └── stress.yaml            # Scénario stress (montée en charge + pannes)
│
├── simulation/
│   ├── cluster.py                 # Orchestrateur N machines
│   ├── machine.py                 # État, tick, injection de pannes
│   ├── physics.py                 # Modèle thermique, PUE, énergie
│   ├── noise.py                   # Bruit gaussien, drift, spikes
│   ├── scenarios.py               # Profils de charge + scheduler de pannes
│   └── duration.py                # Parsing "1h30m" → secondes
│
├── mqtt/
│   └── publisher.py               # aiomqtt client, construction des topics
│
├── api/
│   ├── main.py                    # FastAPI + lifespan asyncio
│   ├── deps.py                    # Dépendances FastAPI (get_cluster, get_ws_manager)
│   ├── ws.py                      # ConnectionManager + /ws/cluster
│   ├── models.py                  # Schemas Pydantic v2
│   └── routes/
│       ├── machines.py            # Commandes par machine
│       ├── cluster.py             # Commandes cluster + métriques
│       └── simulation.py          # Injection pannes + changement scénario
│
├── consumer/                      # Optionnel (profil storage)
│   ├── mqtt_to_timescale.py
│   └── schema.sql
│
├── dashboard/
│   ├── app.py                     # Application Streamlit principale
│   ├── ws_client.py               # Client WebSocket push
│   ├── api_client.py              # Client REST httpx
│   └── components/
│       ├── cluster_view.py
│       ├── machine_view.py
│       ├── simulation_panel.py
│       └── energy_panel.py
│
├── tests/
│   ├── conftest.py
│   ├── test_physics.py
│   ├── test_config.py
│   ├── test_machine.py
│   └── test_api.py
│
├── mosquitto/config/mosquitto.conf
├── grafana/provisioning/
│
├── Dockerfile
├── Dockerfile.dashboard
├── Dockerfile.consumer
├── docker-compose.yml
├── requirements.txt
├── requirements.consumer.txt
├── requirements.dashboard.txt
└── requirements.test.txt
```

---

## Topics MQTT

Le simulateur publie sur la convention `dt/` (data telemetry) / `cmd/` (commands) :

| Topic | QoS | Description |
|---|---|---|
| `dt/{cluster}/{machine}/telemetry` | 0 | Snapshot complet JSON |
| `dt/{cluster}/{machine}/temp/{sensor_id}` | 0 | Valeur scalaire °C |
| `dt/{cluster}/{machine}/power` | 0 | Puissance W + énergie kWh |
| `dt/{cluster}/{machine}/fan/{idx}` | 0 | RPM + mode + status |
| `dt/{cluster}/{machine}/status` | 1 | on / off / degraded |
| `dt/{cluster}/{machine}/fault` | 1 | Événement de panne |
| `dt/{cluster}/summary` | 1 | KPIs cluster (5s) |
| `dt/{cluster}/metrics/energy` | 1 | kWh, coût €, PUE (60s) |

---

## API de commande

Documentation interactive : `http://localhost:8000/docs`

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/cluster/status` | État complet du cluster |
| `GET` | `/cluster/metrics/energy` | kWh, coût €, PUE |
| `POST` | `/machines/{id}/power` | Allumer / éteindre |
| `PUT` | `/machines/{id}/fan_speed` | Régler vitesse fan |
| `PUT` | `/machines/{id}/fan_mode` | Mode auto / manual |
| `POST` | `/simulation/fault` | Injecter une panne |
| `PUT` | `/simulation/scenario` | Changer le scénario |
| `WS` | `/ws/cluster` | Push temps réel 1 Hz |

---

## Dépendances

```
# Simulateur + API
aiomqtt==2.4.0
fastapi==0.115.0
uvicorn[standard]==0.30.0
omegaconf==2.3.0
pydantic==2.7.0
numpy==1.26.0
pyyaml==6.0.1

# Dashboard
streamlit==1.37.0
websockets==12.0
httpx==0.27.0
plotly==5.22.0

# Consumer (optionnel)
aiomqtt==2.4.0
asyncpg==0.29.0

# Tests
pytest==8.2.0
pytest-asyncio==0.23.0
httpx==0.27.0
amqtt==0.11.0
```

---

## Documentation

Les spécifications complètes et la roadmap de développement se trouvent dans le dossier [`documents/`](./documents/) :

- [`documents/specifications.md`](./documents/specifications.md) — Spécifications techniques détaillées (architecture, modèle physique, YAML, API, tests)
- [`documents/roadmap.md`](./documents/roadmap.md) — Plan de développement décomposé en étapes

---

## Contribuer

Ce projet est un support pédagogique. Les étudiants sont invités à :

1. **Explorer le noyau** : comprendre le modèle physique, tester l'API depuis `/docs`, observer les topics MQTT avec MQTT Explorer
2. **Étendre** : choisir une piste d'extension dans `documents/roadmap.md` (niveau ⭐ à ⭐⭐⭐)
3. **Proposer une PR** : toute amélioration documentée est bienvenue

---

*Tristan Vanrullen — La Plateforme, Marseille — 2026*
