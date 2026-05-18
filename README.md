# 🌡️ Jumeaux Chauds — Digital Twin de Cluster IoT

> Simulateur de jumeaux numériques thermiques pour un cluster de serveurs, avec publication MQTT temps réel, API FastAPI et dashboard Streamlit.

**Auteur :** Tristan Vanrullen — La Plateforme, Marseille — 2026

---

## Avancement

| Phase | Statut |
|---|---|
| 1 — Fondations (config, modèle physique) | ✅ Complète |
| 2 — Simulation (MachineSimulator, ClusterSimulator) | ✅ Complète |
| 3 — MQTT (publisher aiomqtt, intégration cluster) | ✅ Complète |
| 4 — API FastAPI (lifespan, endpoints, WebSocket) | 🔜 À venir |
| 5 — Dashboard Streamlit | 🔜 À venir |
| 6 — Déploiement Docker | 🔜 À venir |
| 7 — Tests d'intégration | 🔜 À venir |
| 8 — Extensions pédagogiques | 🔜 Facultatif |

---

## Fonctionnement rapide

### Prérequis

```bash
conda create -n jumeaux-chauds python=3.12
conda activate jumeaux-chauds
pip install -r requirements.txt
```

### Lancer la simulation (standalone, sans MQTT)

```bash
python scripts/run_simulator.py --scenario nominal
python scripts/run_simulator.py --scenario stress --duration 2m
```

### Lancer avec le broker MQTT

```bash
docker compose up mosquitto -d
mosquitto_sub -h localhost -t 'dt/#' -v &
python scripts/run_simulator.py --scenario nominal
```

---

## Architecture

```
simulation/      Modèle physique thermique, MachineSimulator, ClusterSimulator
mqtt/            MqttPublisher aiomqtt (Phase 3 ✅)
api/             FastAPI lifespan + endpoints REST + WebSocket (Phase 4)
dashboard/       Streamlit temps réel (Phase 5)
consumer/        MQTT → TimescaleDB (Phase 6, profil storage)
config/          YAML hiérarchique OmegaConf (base + scénarios)
tests/           pytest + pytest-asyncio
```

Voir [`documents/specifications.md`](documents/specifications.md) pour le détail technique complet  
et [`documents/roadmap.md`](documents/roadmap.md) pour le suivi d'avancement.

---

## Topics MQTT publiés (Phase 3)

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

```
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
├── api/                      ← Phase 4 (à venir)
├── dashboard/                ← Phase 5 (à venir)
├── consumer/                 ← Phase 6 (à venir)
├── tests/
├── scripts/
│   └── run_simulator.py
├── mosquitto/config/
├── documents/
│   ├── specifications.md
│   └── roadmap.md
├── requirements.txt
├── requirements.dashboard.txt
├── requirements.consumer.txt
└── requirements.test.txt
```
