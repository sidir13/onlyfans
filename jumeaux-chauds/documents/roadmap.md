# Jumeaux Chauds — Roadmap de développement

> **Auteur :** Tristan Vanrullen  
> **Date :** Mai 2026  
> **Version :** 1.0.0

Ce document décompose les spécifications techniques en étapes de développement concrètes et ordonnées. Chaque étape est une unité de travail livrable, testable et mergeable de façon indépendante.

---

## Vue d'ensemble

```
Phase 1 : Fondations
  ├── Étape 1.1 : Bootstrap du projet
  ├── Étape 1.2 : Système de configuration YAML
  └── Étape 1.3 : Modèle physique (fonctions pures)

Phase 2 : Simulation
  ├── Étape 2.1 : MachineSimulator
  ├── Étape 2.2 : Profils de charge et bruit
  ├── Étape 2.3 : Injection de pannes
  └── Étape 2.4 : ClusterSimulator

Phase 3 : MQTT
  ├── Étape 3.1 : Publisher aiomqtt
  └── Étape 3.2 : Intégration simulation → MQTT

Phase 4 : API FastAPI
  ├── Étape 4.1 : Lifespan et structure API
  ├── Étape 4.2 : Endpoints de commande
  ├── Étape 4.3 : WebSocket /ws/cluster
  └── Étape 4.4 : Endpoints simulation

Phase 5 : Dashboard Streamlit
  ├── Étape 5.1 : Client WebSocket
  ├── Étape 5.2 : Vue Cluster
  ├── Étape 5.3 : Vue Machine + commandes
  └── Étape 5.4 : Vue Énergie

Phase 6 : Déploiement Docker
  ├── Étape 6.1 : Dockerfiles
  ├── Étape 6.2 : Docker Compose noyau
  └── Étape 6.3 : Profil storage (TimescaleDB + Grafana)

Phase 7 : Tests
  ├── Étape 7.1 : Tests unitaires
  └── Étape 7.2 : Tests d'intégration

Phase 8 : Extensions (facultatif)
```

### Statut global

- [x] Phase 1 — Fondations
- [x] Phase 2 — Simulation
- [x] Phase 3 — MQTT
- [x] Phase 4 — API FastAPI
- [x] Phase 5 — Dashboard Streamlit
- [x] Phase 6 — Déploiement Docker
- [ ] Phase 7 — Tests (intégration et compléments)
- [ ] Phase 8 — Extensions pédagogiques

---

## Phase 1 — Fondations ✅

### Étape 1.1 — Bootstrap du projet ✅

**Objectif :** Mettre en place la structure de fichiers, les dépendances et l'environnement de développement.

**Tâches :**
- [x] Créer la structure de dossiers conforme à `documents/specifications.md § 10`
- [x] Créer `requirements.txt`, `requirements.dashboard.txt`, `requirements.consumer.txt`, `requirements.test.txt` avec les versions figées
- [x] Créer un `Makefile` avec les commandes : `install`, `install-all`, `dev`, `test`, `test-cov`, `docker-up`, `docker-down`, `docker-storage`, `lint`, `format`
- [x] Configurer `pyproject.toml` (ruff, mypy, pytest)
- [x] Vérifier que tous les packages s'importent sans erreur (squelettes de modules vides)

**Critère d'acceptation :** `pip install -r requirements.txt` s'exécute sans erreur. ✅

---

### Étape 1.2 — Système de configuration YAML (OmegaConf) ✅

**Objectif :** Implémenter le chargeur de config avec merge 3 niveaux.

**Tâches :**
- [x] Créer `config/base.yaml` (cluster, role_profiles master/worker, 5 machines)
- [x] Créer `config/scenarios/nominal.yaml` (sine_wave, pas de pannes)
- [x] Créer `config/scenarios/stress.yaml` (ramp_with_spikes, pannes Weibull/exp/uniforme)
- [x] Implémenter `config/loader.py` : `load_config()` (merge 3 niveaux + ENV) et `get_machine_config()` (héritage rôle → machine)
- [x] Vérifier que la surcharge individuelle de machine (ex: `t_shutdown_c: 92.0` sur `srv-master-02`) fonctionne
- [x] Implémenter `simulation/duration.py` : `parse_duration("1h30m") -> 5400.0`

**Critère d'acceptation :** Tous les tests `test_config.py` passent. ✅

---

### Étape 1.3 — Modèle physique (fonctions pures) ✅

**Objectif :** Implémenter l'intégralité du modèle thermique sous forme de fonctions pures et testables.

**Tâches :**
- [x] Implémenter `simulation/physics.py`
- [x] Implémenter `simulation/noise.py`

**Tests écrits :** `tests/test_physics.py` — 35 tests

**Critère d'acceptation :** Tous les tests `test_physics.py` passent. ✅

---

## Phase 2 — Simulation ✅

### Étape 2.1 — MachineSimulator ✅

**Tâches :**
- [x] Implémenter `simulation/machine.py` avec `MachineSimulator`, `FanState`, `ActiveFault`, `ThermalConfig`, `SensorConfig`
- [x] Logique d'état (ON/OFF/DEGRADED), calcul énergie, gestion fans, `snapshot()`

**Critère d'acceptation :** Tous les tests `test_machine.py` passent. ✅

---

### Étape 2.2 — Profils de charge et bruit ✅

**Tâches :**
- [x] `ScenarioEngine` dans `simulation/scenarios.py` : `sine_wave`, `ramp_with_spikes`, `constant`, `step`

**Critère d'acceptation :** Profils sélectionnables via config, valeurs dans [0, 1]. ✅

---

### Étape 2.3 — Injection de pannes (FaultScheduler) ✅

**Tâches :**
- [x] `FaultConfig` et `FaultScheduler` dans `simulation/scenarios.py`
- [x] Distributions : `weibull`, `exponential`, `uniform`

**Critère d'acceptation :** Pannes injectées selon les distributions configurées. ✅

---

### Étape 2.4 — ClusterSimulator ✅

**Tâches :**
- [x] `ClusterSimulator` dans `simulation/cluster.py`
- [x] Boucle `run()` avec `tick_rate_hz`, intégration `ScenarioEngine` + `FaultScheduler`
- [x] `get_snapshot()` — payload JSON complet

**Critère d'acceptation :** Boucle asyncio fonctionnelle, snapshot cohérent. ✅

---

## Phase 3 — MQTT ✅

### Étape 3.1 — Publisher aiomqtt ✅

**Tâches :**
- [x] `mqtt/publisher.py` : `MqttPublisher` context manager asyncio
- [x] Reconnexion automatique (`_reconnect_loop`)
- [x] Méthodes : `publish_telemetry`, `publish_fan_state`, `publish_status`, `publish_fault`, `publish_summary`, `publish_energy`
- [x] Publication silencieuse si broker indisponible

**Critère d'acceptation :** Messages visibles dans MQTT Explorer. ✅

---

### Étape 3.2 — Intégration simulation → MQTT ✅

**Tâches :**
- [x] `ClusterSimulator.run()` accepte `publisher` et `ws_manager` optionnels
- [x] Publication différentielle (statut, fans) sur changement uniquement
- [x] Timers summary (5 s) et energy (60 s)
- [x] Flag `--no-mqtt`

**Critère d'acceptation :** Flux visible sur `mosquitto_sub -h localhost -t 'dt/#' -v`. ✅

---

## Phase 4 — API FastAPI ✅

### Étape 4.1 — Lifespan et structure API ✅

**Tâches :**
- [x] `api/main.py` : `@asynccontextmanager lifespan` — charge config, instancie simulator + publisher + ws_manager, lance la boucle en background task
- [x] CORS configuré (origines : `http://localhost:8501` pour Streamlit)
- [x] `api/deps.py` : `get_cluster()`, `get_ws_manager()`, `get_config()`
- [x] `api/models.py` : tous les schémas Pydantic v2
- [x] `GET /` retournant nom, version, cluster_id, scénario actif, running

**Critère d'acceptation :** `uvicorn api.main:app --reload` démarre, `/docs` accessible. ✅

---

### Étape 4.2 — Endpoints de commande ✅

**Tâches :**
- [x] `api/routes/machines.py` : `GET /{id}`, `POST /{id}/power`, `PUT /{id}/fan_speed`, `PUT /{id}/fan_mode`
- [x] `api/routes/cluster.py` : `GET /status`, `GET /energy`, `POST /power`, `PUT /fan_speed`
- [x] `404` si `machine_id` inconnu
- [x] `409` si `power_on()` impossible (T > t_restart_c)

**Critère d'acceptation :** Endpoints fonctionnels, codes HTTP corrects. ✅

---

### Étape 4.3 — WebSocket /ws/cluster ✅

**Tâches :**
- [x] `api/ws.py` : `ConnectionManager` + endpoint `/ws/cluster`
- [x] `ClusterSimulator.run()` appelle `ws_manager.broadcast(snapshot)` à `events_per_sec` Hz
- [x] Nettoyage automatique des connexions mortes

**Critère d'acceptation :** `wscat -c ws://localhost:8000/ws/cluster` reçoit un JSON à chaque tick. ✅

---

### Étape 4.4 — Endpoints simulation ✅

**Tâches :**
- [x] `api/routes/simulation.py` : `POST /simulation/fault`, `DELETE /simulation/fault/{id}`, `PUT /simulation/scenario`
- [x] Hot-reload du `ScenarioEngine` sans redémarrage

**Critère d'acceptation :** `PUT /simulation/scenario {scenario: stress}` change le profil en < 2s. ✅

---

## Phase 5 — Dashboard Streamlit ✅

### Étape 5.1 — Client WebSocket Streamlit ✅

**Tâches :**
- [x] Implémenter `dashboard/ws_client.py`
- [x] Implémenter `dashboard/api_client.py` avec `httpx.AsyncClient`
- [x] `@st.cache_resource` pour instancier `ClusterWSClient` une seule fois
- [x] Reconnexion automatique si l'API redémarre

**Critère d'acceptation :** `streamlit run dashboard/app.py` démarre sans erreur, snapshot non-vide en moins de 3s. ✅

---

### Étape 5.2 — Vue Cluster (onglet 1) ✅

**Tâches :**
- [x] 4 métriques : machines ON, T_max, W_total, coût €/h
- [x] Heatmap Plotly : une cellule par machine, couleur = `temp_cpu`
- [x] Auto-refresh toutes les 2 s via `st.rerun()` (compatible Streamlit < 1.37)

**Critère d'acceptation :** Heatmap se met à jour automatiquement. ✅

---

### Étape 5.3 — Vue Machine + commandes (onglet 2) ✅

**Tâches :**
- [x] Sélecteur machine, métriques toutes sondes, état fans
- [x] Buffer circulaire (100 points) pour `st.line_chart` de `temperature_c`
- [x] Boutons : Power ON/OFF, Set Fan Speed, Fan Mode Auto/Manual
- [x] Afficher en rouge si `status: degraded` ou `faults` non vide

**Critère d'acceptation :** `Power OFF` passe la machine en état `off` en moins de 2s. ✅

---

### Étape 5.4 — Vues Simulation et Énergie (onglets 3 et 4) ✅

**Tâches :**
- [x] Onglet 3 : sélecteur scénario, formulaire injection panne, journal 20 événements
- [x] Onglet 4 : kWh cumulés, €/h, PUE, bar chart par machine, projection mensuelle

**Critère d'acceptation :** Injection de panne depuis le dashboard visible dans le journal en moins de 2s. ✅

---

## Phase 6 — Déploiement Docker ✅

### Étape 6.1 — Dockerfiles ✅

**Tâches :**
- [x] `Dockerfile` (simulateur + API)
- [x] `Dockerfile.dashboard`
- [x] `Dockerfile.consumer`
- [x] `mosquitto/config/mosquitto.conf`

**Critère d'acceptation :** `docker build -t jumeaux-chauds .` sans erreur. ✅

---

### Étape 6.2 — Docker Compose noyau ✅

**Tâches :**
- [x] Créer `docker-compose.yml`
- [x] Démarrage ordonné : mosquitto → iot-twin → dashboard
- [x] Variables `SCENARIO`, `CLUSTER_ID`, `MQTT_ENABLED`

**Critère d'acceptation :** `docker compose up` → dashboard sur `http://localhost:8501`. ✅

---

### Étape 6.3 — Profil storage (TimescaleDB + Grafana) ✅

**Tâches :**
- [x] `consumer/mqtt_to_timescale.py`
- [x] `consumer/schema.sql` avec `create_hypertable`
- [x] Services `timescaledb`, `mqtt-consumer`, `grafana` avec `profiles: ["storage"]`
- [x] Dashboard Grafana basique

**Critère d'acceptation :** `docker compose --profile storage up` → Grafana sur `http://localhost:3000`. ✅

---

## Phase 7 — Tests

### Étape 7.1 — Tests unitaires

**Tâches :**
- [x] `tests/conftest.py` : fixtures partagées ✅
- [x] `tests/test_physics.py` (35 cas) ✅
- [x] `tests/test_config.py` (14 cas) ✅
- [x] `tests/test_machine.py` (≥ 8 cas) ✅
- [ ] `pytest --cov=simulation --cov=config --cov=api --cov-report=html`

**Critère d'acceptation :** 100% pass, couverture ≥ 80%.

---

### Étape 7.2 — Tests d'intégration

**Tâches :**
- [ ] Fixture `mqtt_broker` lançant `amqtt` sur un port aléatoire
- [ ] `tests/test_api.py` avec `httpx.AsyncClient(app=app, base_url="http://test")`
- [ ] Test flux complet : `ClusterSimulator.run()` 5s → messages publiés sur broker `amqtt`

**Critère d'acceptation :** `pytest tests/test_api.py` → 100% pass.

---

## Phase 8 — Extensions pédagogiques (facultatif)

### Extensions ⭐
- [ ] **Scénario heatwave** : `config/scenarios/heatwave.yaml` avec `ambient_temp_c: 32.0`
- [ ] **Observer MQTT** : abonner MQTT Explorer ou Node-RED

### Extensions ⭐⭐
- [ ] **Régulateur PID** : P, I, D configurables en YAML
- [ ] **Candlestick OHLC** : buffer 60s sur `temperature_c`, graphe Plotly
- [ ] **Coût électrique** : projection mensuelle, export CSV
- [ ] **Stack Grafana** : profil `storage` complet

### Extensions ⭐⭐⭐
- [ ] **Détection d'anomalie ML** : IsolationForest / PyOD sur séries MQTT
- [ ] **Classification drift / surchauffe**
- [ ] **Estimation Weibull (MLE)**
- [ ] **Agent RL** : DQN (Stable-Baselines3)
- [ ] **Command consumer MQTT** : subscriber `cmd/#`
- [ ] **Outil MCP** : endpoints comme outils MCP pour agent LLM

---

## Checklist de démarrage pour un développeur

1. **Lire** `documents/specifications.md` en entier (~30 min)
2. **Cloner** le dépôt et créer une branche `feature/phase-7-tests`
3. **Lancer** `MQTT_ENABLED=0 uvicorn api.main:app --reload` pour avoir l'API disponible
4. **Valider** chaque étape avec ses tests avant de passer à la suivante
5. **Utiliser** `docker compose up mosquitto` pour le broker MQTT

---

*Tristan Vanrullen — La Plateforme, Marseille — 2026*
