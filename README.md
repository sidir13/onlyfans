# 🌡️ Jumeaux Chauds

> **Simulateur de jumeaux numériques IoT pour la maintenance prédictive de clusters de machines**

**Auteur :** Tristan Vanrullen  
**Organisation :** La Plateforme — École Numérique, Marseille  
**Dépôt :** [https://github.com/TristanV/jumeaux-chauds](https://github.com/TristanV/jumeaux-chauds)  
**Licence :** MIT  
**Version :** 1.0.0

---

## Présentation

**Jumeaux Chauds** est un simulateur Python de jumeaux numériques pour un cluster de machines IoT dotées de capteurs physiques. Le projet produit des flux de données réalistes en MQTT, expose une API de commande FastAPI, et fournit un dashboard de visualisation temps réel sous Streamlit.

Il est conçu comme support pédagogique pour des étudiants en data engineering, IoT et intelligence artificielle, avec un noyau fonctionnel stable et de nombreuses pistes d'extension documentées.

---

## Statut du projet

- ✅ **Phase 1 — Fondations** : structure du projet, configuration YAML hiérarchique, modèle physique thermique, socle de tests unitaires (config + physique).
- ✅ **Phase 2 — Simulation** : `MachineSimulator`, `ScenarioEngine`, `FaultScheduler` et `ClusterSimulator` implémentés et testés.
- ⏳ **Phases 3 à 6** : couche MQTT, API FastAPI, dashboard Streamlit et stack Docker complète encore à implémenter.

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

## Table des matières

1. [Prérequis](#prérequis)
2. [Installation](#installation)
   - [Mode Docker (recommandé)](#mode-docker-recommandé)
   - [Mode développement local](#mode-développement-local)
3. [Configuration](#configuration)
   - [Variables d'environnement](#variables-denvironnement)
   - [Fichiers YAML](#fichiers-yaml)
   - [Personnaliser le cluster](#personnaliser-le-cluster)
   - [Créer un scénario personnalisé](#créer-un-scénario-personnalisé)
4. [Exécution](#exécution)
   - [Lancer en mode nominal](#lancer-en-mode-nominal)
   - [Lancer en mode stress](#lancer-en-mode-stress)
   - [Lancer avec stockage TimescaleDB + Grafana](#lancer-avec-stockage-timescaledb--grafana)
   - [Exécution locale sans Docker](#exécution-locale-sans-docker)
5. [Utilisation de l'API](#utilisation-de-lapi)
6. [Observer les flux MQTT](#observer-les-flux-mqtt)
7. [Lancer les tests](#lancer-les-tests)
8. [Architecture rapide](#architecture-rapide)
9. [Structure du projet](#structure-du-projet)
10. [Topics MQTT](#topics-mqtt)
11. [Documentation](#documentation)
12. [Contribuer](#contribuer)

---

## Prérequis

### Mode Docker (recommandé)

| Outil | Version minimale | Vérification |
|---|---|---|
| Docker Engine | 24.0+ | `docker --version` |
| Docker Compose | v2.20+ (plugin intégré) | `docker compose version` |
| Git | 2.x | `git --version` |

### Mode développement local

| Outil | Version minimale | Vérification |
|---|---|---|
| Python | 3.11+ | `python --version` |
| pip | 23+ | `pip --version` |
| Git | 2.x | `git --version` |

> Un broker MQTT est également nécessaire en local. Mosquitto peut être lancé séparément via `docker compose up mosquitto`.

---

## Installation

### Mode Docker (recommandé)

Aucune installation Python n'est nécessaire. Tout est conteneurisé.

```bash
# 1. Cloner le dépôt
git clone https://github.com/TristanV/jumeaux-chauds.git
cd jumeaux-chauds

# 2. Construire les images
docker compose build

# Vérifier que les images sont créées
docker images | grep jumeaux
```

### Mode développement local

Installation recommandée dans un environnement virtuel.

```bash
# 1. Cloner le dépôt
git clone https://github.com/TristanV/jumeaux-chauds.git
cd jumeaux-chauds

# 2. Créer et activer un environnement virtuel
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# ou : .venv\Scripts\activate    # Windows

# 3. Installer les dépendances du simulateur + API
pip install -r requirements.txt

# 4. (Optionnel) Installer les dépendances du dashboard
pip install -r requirements.dashboard.txt

# 5. (Optionnel) Installer les dépendances du consumer TimescaleDB
pip install -r requirements.consumer.txt

# 6. (Optionnel) Installer les dépendances de test
pip install -r requirements.test.txt
```

> **Note :** Les quatre fichiers `requirements*.txt` sont indépendants. En développement, il est conseillé d'installer `requirements.txt` + `requirements.dashboard.txt` + `requirements.test.txt` ensemble.

---

## Configuration

La configuration est entièrement pilotée par des **fichiers YAML** et des **variables d'environnement**. Il n'y a pas de fichier `.env` à créer pour démarrer — toutes les valeurs ont des défauts raisonnables.

### Variables d'environnement

Ces variables peuvent être définies dans le shell ou passées à `docker compose` :

| Variable | Défaut | Description |
|---|---|---|
| `CLUSTER_ID` | `cluster_alpha` | Identifiant du cluster (utilisé dans les topics MQTT) |
| `SCENARIO` | `nominal` | Scénario actif au démarrage : `nominal` ou `stress` |
| `MQTT_BROKER_HOST` | `mosquitto` (Docker) / `localhost` (local) | Hostname du broker Mosquitto |
| `MQTT_BROKER_PORT` | `1883` | Port TCP du broker |
| `TICK_RATE_HZ` | `10` | Fréquence de simulation (ticks/seconde) |
| `API_URL` | `http://iot-twin:8000` | URL de l'API (utilisée par le dashboard) |
| `WS_URL` | `ws://iot-twin:8000/ws/cluster` | URL WebSocket (utilisée par le dashboard) |

**Exemples :**

```bash
# Surcharger le scénario et le cluster au démarrage Docker
CLUSTER_ID=datacenter_ouest SCENARIO=stress docker compose up

# En développement local
export MQTT_BROKER_HOST=localhost
export SCENARIO=nominal
```

### Fichiers YAML

La configuration se décompose en deux couches qui se **mergent** automatiquement :

```
config/
├── base.yaml               ← Paramètres du cluster, des rôles (master/worker),
│                             des capteurs, des fans, du bruit
└── scenarios/
    ├── nominal.yaml        ← Profil de charge sinusoïdal, pas de pannes
    └── stress.yaml         ← Montée en charge + pannes Weibull
```

Le fichier `base.yaml` définit les **valeurs de référence**. Le fichier de scénario actif **surcharge** uniquement les clés qu'il mentionne, sans effacer le reste.

### Personnaliser le cluster

Ouvrir `config/base.yaml` pour modifier :

```yaml
cluster:
  id: "cluster_alpha"             # ← Changer l'identifiant
  electricity_price_eur_kwh: 0.20 # ← Tarif électrique local

  role_profiles:
    master:
      thermal:
        t_shutdown_c: 90.0        # ← Seuil de coupure thermique
        t_restart_c: 55.0         # ← Seuil de redémarrage
      fans:
        max_rpm: 5000             # ← Vitesse max des fans

  machines:
    - id: "srv-master-01"         # ← Ajouter / renommer des machines
      role: "master"
    - id: "srv-worker-01"
      role: "worker"
      thermal:                    # ← Surcharge individuelle (optionnelle)
        t_shutdown_c: 85.0
```

> **Règle d'héritage :** les paramètres d'une machine individuelle surchargent ceux de son `role_profile`, qui lui-même surcharge les défauts du cluster.

### Créer un scénario personnalisé

Dupliquer `config/scenarios/nominal.yaml` et modifier les paramètres :

```bash
cp config/scenarios/nominal.yaml config/scenarios/heatwave.yaml
```

```yaml
# config/scenarios/heatwave.yaml
simulation:
  mode: "heatwave"
  load_profile:
    type: "sine_wave"
    base_load: 0.60       # ← Charge de base plus élevée
    amplitude: 0.25
    period_s: 180.0
  noise:
    enabled: true
    spike_probability: 0.005
    spike_magnitude_c: 4.0
  fault_injection:
    enabled: true
    faults:
      - type: "fan_failure"
        distribution: "weibull"
        shape: 1.5
        scale_s: 3600     # ← MTBF réduit à 1h
        magnitude: 1.0
    recovery_delay_s: 180.0
```

Démarrer avec ce scénario :

```bash
SCENARIO=heatwave docker compose up
# ou en local :
export SCENARIO=heatwave && uvicorn api.main:app
```

---

## Exécution

### Lancer en mode nominal

Le mode nominal simule une charge sinusoïdale sans pannes. C'est le point d'entrée recommandé.

```bash
# Démarrer tous les services (simulateur + broker + dashboard)
docker compose up

# En arrière-plan
docker compose up -d

# Vérifier que tous les services sont up
docker compose ps
```

Services disponibles après démarrage :

| Service | URL | Description |
|---|---|---|
| Dashboard Streamlit | http://localhost:8501 | Visualisation temps réel |
| API FastAPI (docs) | http://localhost:8000/docs | Documentation OpenAPI interactive |
| API FastAPI (JSON) | http://localhost:8000/cluster/status | État du cluster en JSON |
| Broker MQTT (TCP) | `localhost:1883` | Connexion clients MQTT externes |
| Broker MQTT (WS) | `localhost:9001` | Connexion WebSocket MQTT |

### Lancer en mode stress

Le mode stress active la montée en charge progressive et l'injection automatique de pannes (fan failures, dérives capteurs, power surges).

```bash
# Via variable d'environnement au démarrage
SCENARIO=stress docker compose up

# Ou basculer à chaud sans redémarrer (API)
curl -X PUT http://localhost:8000/simulation/scenario \
     -H 'Content-Type: application/json' \
     -d '{"scenario": "stress"}'
```

> En mode stress, les températures montent progressivement sur ~10 minutes. Les machines commencent à s'éteindre automatiquement par protection thermique si les fans ne sont pas activés.

### Lancer avec stockage TimescaleDB + Grafana

Le profil `storage` ajoute une base de données de séries temporelles et un tableau de bord Grafana.

```bash
# Démarrer avec la stack de stockage
docker compose --profile storage up

# Services supplémentaires
# Grafana     : http://localhost:3000  (admin / admin)
# TimescaleDB : localhost:5432         (tsuser / tspassword / tsdb)
```

Le consumer MQTT s'abonne automatiquement à `dt/#` et insère les données dans TimescaleDB. Pour visualiser dans Grafana :

1. Ouvrir http://localhost:3000, se connecter avec `admin` / `admin`
2. La datasource PostgreSQL (TimescaleDB) est pré-provisionnée
3. Créer un panel avec la requête :
   ```sql
   SELECT time, value
   FROM sensor_data
   WHERE machine_id = 'srv-worker-01' AND sensor_type = 'temp_cpu'
   ORDER BY time DESC
   LIMIT 500
   ```

### Exécution locale sans Docker

Nécessite Python 3.11+ installé et un broker Mosquitto accessible.

```bash
# Terminal 1 : démarrer uniquement le broker Mosquitto
docker compose up mosquitto

# Terminal 2 : démarrer le simulateur + API
export MQTT_BROKER_HOST=localhost
export SCENARIO=nominal
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 3 : démarrer le dashboard
export API_URL=http://localhost:8000
export WS_URL=ws://localhost:8000/ws/cluster
streamlit run dashboard/app.py
```

> Le flag `--reload` d'uvicorn recharge automatiquement le code à chaque modification — utile pendant le développement.

### Arrêt propre

```bash
# Arrêter et supprimer les conteneurs
docker compose down

# Arrêter et supprimer également les volumes (réinitialise TimescaleDB)
docker compose down -v
```

---

## Utilisation de l'API

La documentation interactive OpenAPI est accessible sur **http://localhost:8000/docs**.

### Exemples curl

```bash
# État complet du cluster
curl http://localhost:8000/cluster/status | python -m json.tool

# Métriques énergétiques
curl http://localhost:8000/cluster/metrics/energy

# Éteindre une machine
curl -X POST http://localhost:8000/machines/srv-worker-01/power \
     -H 'Content-Type: application/json' \
     -d '{"action": "off"}'

# Allumer une machine
curl -X POST http://localhost:8000/machines/srv-worker-01/power \
     -H 'Content-Type: application/json' \
     -d '{"action": "on"}'

# Régler la vitesse d'un fan (manuellement)
curl -X PUT http://localhost:8000/machines/srv-worker-01/fan_speed \
     -H 'Content-Type: application/json' \
     -d '{"rpm": 3500, "fan_idx": 0}'

# Passer un fan en mode automatique
curl -X PUT http://localhost:8000/machines/srv-worker-01/fan_mode \
     -H 'Content-Type: application/json' \
     -d '{"mode": "auto"}'

# Injecter une panne fan sur une machine
curl -X POST http://localhost:8000/simulation/fault \
     -H 'Content-Type: application/json' \
     -d '{"machine_id": "srv-master-01", "fault_type": "fan_failure", "duration_s": 60, "magnitude": 1.0}'

# Annuler la panne
curl -X DELETE http://localhost:8000/simulation/fault/srv-master-01

# Changer de scénario à chaud
curl -X PUT http://localhost:8000/simulation/scenario \
     -H 'Content-Type: application/json' \
     -d '{"scenario": "stress"}'
```

### WebSocket temps réel

Se connecter au flux WebSocket (push 1 Hz) :

```bash
# Avec wscat (npm install -g wscat)
wscat -c ws://localhost:8000/ws/cluster

# Avec websocat
websocat ws://localhost:8000/ws/cluster
```

Chaque message reçu est un snapshot JSON complet du cluster avec l'état de toutes les machines.

---

## Observer les flux MQTT

### Avec MQTT Explorer (interface graphique)

1. Télécharger [MQTT Explorer](https://mqtt-explorer.com/)
2. Se connecter à `localhost:1883` (sans authentification)
3. Les topics `dt/cluster_alpha/#` apparaissent automatiquement

### Avec mosquitto_sub (ligne de commande)

```bash
# Souscrire à tous les topics du cluster
mosquitto_sub -h localhost -p 1883 -t 'dt/#' -v

# Souscrire uniquement aux télémétries d'une machine
mosquitto_sub -h localhost -p 1883 -t 'dt/cluster_alpha/srv-worker-01/telemetry' -v

# Souscrire aux événements de panne uniquement
mosquitto_sub -h localhost -p 1883 -t 'dt/+/+/fault' -v

# Souscrire aux résumés du cluster (toutes les 5s)
mosquitto_sub -h localhost -p 1883 -t 'dt/cluster_alpha/summary' -v
```

### Avec un script Python aiomqtt

```python
import asyncio
import aiomqtt

async def main():
    async with aiomqtt.Client("localhost") as client:
        await client.subscribe("dt/#")
        async for message in client.messages:
            print(f"{message.topic}: {message.payload.decode()}")

asyncio.run(main())
```

---

## Lancer les tests

```bash
# Installer les dépendances de test
pip install -r requirements.test.txt

# Lancer tous les tests
pytest

# Tests unitaires uniquement (physique, config, machine)
pytest tests/test_physics.py tests/test_config.py tests/test_machine.py -v

# Tests d'intégration API
pytest tests/test_api.py -v

# Avec rapport de couverture
pytest --cov=simulation --cov=config --cov-report=html
# Ouvrir htmlcov/index.html dans le navigateur

# Lancer un test spécifique
pytest tests/test_physics.py::test_temperature_increases_under_load -v
```

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

Le simulateur, l'API et le publisher MQTT tournent dans **un seul processus Python** grâce à `asyncio`. FastAPI gère le cycle de vie via `lifespan`, qui démarre la tâche de simulation en arrière-plan dans la même boucle d'événements.

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
│   ├── deps.py                    # Dépendances FastAPI
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

## Documentation

- [`documents/specifications.md`](./documents/specifications.md) — Spécifications techniques détaillées (architecture, modèle physique, YAML, API, tests, extensions pédagogiques)
- [`documents/roadmap.md`](./documents/roadmap.md) — Plan de développement décomposé en 8 phases et 20 étapes

---

## Contribuer

Ce projet est un support pédagogique. Les étudiants sont invités à :

1. **Explorer le noyau** : comprendre le modèle physique, tester l'API depuis `/docs`, observer les topics MQTT avec MQTT Explorer
2. **Étendre** : choisir une piste d'extension dans `documents/roadmap.md` (niveau ⭐ à ⭐⭐⭐)
3. **Proposer une PR** : toute amélioration documentée est bienvenue

---

*Tristan Vanrullen — La Plateforme, Marseille — 2026*
