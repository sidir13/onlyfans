# 🌡️ Jumeaux Chauds — Digital Twin de Cluster IoT

> Simulateur de jumeaux numériques thermiques pour un cluster de serveurs, avec publication MQTT temps réel, API FastAPI, dashboard Streamlit et stack de stockage TimescaleDB + Grafana.

**Auteur :** Tristan Vanrullen — La Plateforme, Marseille — 2026

---

## Avancement

| Phase | Statut |
|---|---|
| 1 — Fondations (config, modèle physique) | ✅ Complète |
| 2 — Simulation (MachineSimulator, ClusterSimulator) | ✅ Complète |
| 3 — MQTT (publisher aiomqtt, intégration cluster) | ✅ Complète |
| 4 — API FastAPI (lifespan, endpoints REST, WebSocket) | ✅ Complète |
| 5 — Dashboard Streamlit (temps réel, commandes, énergie) | ✅ Complète |
| 6 — Déploiement Docker (Compose noyau + profil storage) | ✅ Complète |
| 7 — Tests d'intégration | 🔄 Prochaine priorité |
| 8 — Extensions pédagogiques | 🔜 Facultatif |

---

## Démarrage rapide

### Prérequis

```bash
conda create -n jumeaux-chauds python=3.12
conda activate jumeaux-chauds
pip install -r requirements.txt
```

### Développement local (sans Docker)

```bash
# Broker MQTT seul
docker compose up mosquitto -d

# Simulation CLI
python scripts/run_simulator.py --scenario nominal
python scripts/run_simulator.py --scenario stress --duration 2m

# API FastAPI
export MQTT_ENABLED=0   # Linux/macOS
set MQTT_ENABLED=0      # Windows
uvicorn api.main:app --reload --port 8000

# Dashboard Streamlit
streamlit run dashboard/app.py
```

Docs API : **http://localhost:8000/docs**  
Dashboard : **http://localhost:8501**  
WebSocket : `wscat -c ws://localhost:8000/ws/cluster`

---

## Docker Compose — Stack complète (Phase 6)

### Noyau (simulateur + broker + dashboard)

```bash
docker compose up -d
```

Services démarrés :
- `mosquitto` — broker MQTT sur le port 1883
- `iot-twin` — simulateur + API FastAPI sur le port 8000
- `dashboard` — Streamlit sur le port 8501

### Profil storage (TimescaleDB + consumer + Grafana)

```bash
docker compose --profile storage up -d
```

Services supplémentaires :
- `timescaledb` — PostgreSQL + extension TimescaleDB sur le port 5432
- `mqtt-consumer` — abonné MQTT → écrit dans TimescaleDB
- `grafana` — dashboards sur le port 3000 (admin / admin)

### Variables d'environnement utiles

| Variable | Défaut | Rôle |
|---|---|---|
| `SCENARIO` | `nominal` | Scénario de charge |
| `CLUSTER_ID` | `cluster_alpha` | Identifiant du cluster |
| `MQTT_ENABLED` | `1` | Désactiver MQTT (`0`) |
| `POSTGRES_PASSWORD` | `jumeaux` | Mot de passe TimescaleDB / Grafana datasource |

### Arrêt et nettoyage

```bash
docker compose down
docker compose --profile storage down -v
```

---

## Accès aux services

### Depuis la machine hôte / un client externe

| Service | URL / hôte | Port | Détails |
|---|---|---:|---|
| API FastAPI | `http://localhost:8000` | 8000 | Endpoint racine `/` |
| Documentation OpenAPI | `http://localhost:8000/docs` | 8000 | Swagger UI |
| WebSocket cluster | `ws://localhost:8000/ws/cluster` | 8000 | Flux temps réel du snapshot |
| Dashboard Streamlit | `http://localhost:8501` | 8501 | Interface utilisateur |
| Broker MQTT Mosquitto | `localhost` | 1883 | Accès MQTT TCP |
| MQTT over WebSocket | `ws://localhost:9001` | 9001 | Pour clients MQTT WebSocket |
| TimescaleDB | `localhost` | 5432 | Base PostgreSQL/TimescaleDB |
| Grafana | `http://localhost:3000` | 3000 | Login par défaut : `admin / admin` |

### Depuis un autre conteneur Docker du même réseau Compose

| Service | Adresse interne | Port |
|---|---|---:|
| API FastAPI | `http://iot-twin:8000` | 8000 |
| Dashboard Streamlit | `http://dashboard:8501` | 8501 |
| Mosquitto MQTT | `mosquitto` | 1883 |
| Mosquitto WebSocket | `mosquitto` | 9001 |
| TimescaleDB | `timescaledb` | 5432 |
| Grafana | `http://grafana:3000` | 3000 |

### Exemples d'accès

```bash
# Vérifier l'API
curl http://localhost:8000/

# Consulter la doc interactive
# http://localhost:8000/docs

# Tester le WebSocket temps réel
wscat -c ws://localhost:8000/ws/cluster

# S'abonner aux topics MQTT
mosquitto_sub -h localhost -t 'dt/#' -v

# Se connecter à TimescaleDB
psql -h localhost -p 5432 -U jumeaux -d jumeaux

# Ouvrir Grafana
# http://localhost:3000
# login: admin / admin
```

---

## Architecture

```
simulation/      Modèle physique thermique, MachineSimulator, ClusterSimulator
mqtt/            MqttPublisher aiomqtt (Phase 3 ✅)
api/             FastAPI lifespan + endpoints REST + WebSocket (Phase 4 ✅)
dashboard/       Streamlit temps réel (Phase 5 ✅)
consumer/        MQTT → TimescaleDB (Phase 6 ✅)
config/          YAML hiérarchique OmegaConf (base + scénarios)
tests/           pytest + pytest-asyncio
grafana/         Provisioning datasource + dashboard (Phase 6 ✅)
mosquitto/       Configuration broker MQTT
```

Voir [`documents/specifications.md`](documents/specifications.md) pour le détail technique complet  
et [`documents/roadmap.md`](documents/roadmap.md) pour le suivi d'avancement.

---

## API FastAPI (Phase 4 ✅)

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Info API + état simulateur |
| `GET` | `/cluster/status` | Snapshot complet du cluster |
| `GET` | `/cluster/energy` | Métriques énergétiques |
| `POST` | `/cluster/power` | Allumer/éteindre tout le cluster |
| `PUT` | `/cluster/fan_speed` | Vitesse homogène tous les fans |
| `GET` | `/machines/{id}` | Snapshot d'une machine |
| `POST` | `/machines/{id}/power` | Power ON/OFF (409 si T trop haute) |
| `PUT` | `/machines/{id}/fan_speed` | Vitesse manuelle d'un fan |
| `PUT` | `/machines/{id}/fan_mode` | Mode auto/manual d'un fan |
| `POST` | `/simulation/fault` | Injecter une panne |
| `DELETE` | `/simulation/fault/{id}` | Annuler les pannes d'une machine |
| `PUT` | `/simulation/scenario` | Changer de scénario à chaud |
| `WS` | `/ws/cluster` | Flux temps réel du snapshot |

---

## Topics MQTT publiés (Phase 3 ✅)

| Topic | QoS | Fréquence |
|---|---|---|
| `dt/{cluster}/{machine}/telemetry` | 0 | `events_per_sec` |
| `dt/{cluster}/{machine}/temp/{sensor}` | 0 | `events_per_sec` |
| `dt/{cluster}/{machine}/power` | 0 | `events_per_sec` |
| `dt/{cluster}/{machine}/fan/{idx}` | 0 | Sur changement |
| `dt/{cluster}/{machine}/status` | 1 | Sur changement |
| `dt/{cluster}/{machine}/fault` | 1 | Sur événement |
| `dt/{cluster}/summary` | 1 | Toutes les 5 s |
| `dt/{cluster}/metrics/energy` | 1 | Toutes les 60 s |

---

## Structure du projet

```text
jumeaux-chauds/
├── config/
│   ├── base.yaml
│   ├── loader.py
│   └── scenarios/
│       ├── nominal.yaml
│       └── stress.yaml
├── simulation/
│   ├── cluster.py
│   ├── machine.py
│   ├── physics.py
│   ├── noise.py
│   ├── scenarios.py
│   └── duration.py
├── mqtt/
│   └── publisher.py          ← Phase 3 ✅
├── api/                      ← Phase 4 ✅
│   ├── main.py
│   ├── deps.py
│   ├── models.py
│   ├── ws.py
│   └── routes/
│       ├── machines.py
│       ├── cluster.py
│       └── simulation.py
├── dashboard/                ← Phase 5 ✅
│   ├── app.py
│   ├── ws_client.py
│   └── api_client.py
├── consumer/                 ← Phase 6 ✅
│   ├── mqtt_to_timescale.py
│   └── schema.sql
├── grafana/                  ← Phase 6 ✅
│   └── provisioning/
│       ├── datasources/
│       │   └── timescale.yaml
│       └── dashboards/
│           ├── dashboard.yaml
│           └── jumeaux-chauds.json
├── mosquitto/config/
│   └── mosquitto.conf
├── tests/
├── scripts/
│   └── run_simulator.py
├── Dockerfile
├── Dockerfile.dashboard
├── Dockerfile.consumer
├── docker-compose.yml
├── documents/
│   ├── specifications.md
│   └── roadmap.md
├── requirements.txt
├── requirements.dashboard.txt
├── requirements.consumer.txt
├── requirements.test.txt
└── Makefile
```

---

## Prochaine étape de développement

La prochaine priorité du projet est la **Phase 7 — Tests d'intégration et couverture**.

Objectifs :
- sécuriser les endpoints FastAPI ;
- valider le flux WebSocket temps réel ;
- tester la publication MQTT de bout en bout ;
- vérifier l'ingestion MQTT → TimescaleDB ;
- mesurer et améliorer la couverture de code.

Cette étape permettra de stabiliser le socle existant avant d'ajouter de nouvelles extensions pédagogiques ou des fonctionnalités avancées d'observabilité.

---

*Tristan Vanrullen — La Plateforme, Marseille — 2026*
