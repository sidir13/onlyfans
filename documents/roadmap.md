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
- [ ] Phase 4 — API FastAPI
- [ ] Phase 5 — Dashboard Streamlit
- [ ] Phase 6 — Déploiement Docker
- [ ] Phase 7 — Tests (intégration et compléments)
- [ ] Phase 8 — Extensions pédagogiques

---

## Phase 1 — Fondations

### Étape 1.1 — Bootstrap du projet ✅

**Objectif :** Mettre en place la structure de fichiers, les dépendances et l'environnement de développement.

**Tâches :**
- [x] Créer la structure de dossiers conforme à `documents/specifications.md § 10`
- [x] Créer `requirements.txt`, `requirements.dashboard.txt`, `requirements.consumer.txt`, `requirements.test.txt` avec les versions figées
- [x] Créer un `Makefile` avec les commandes : `install`, `install-all`, `dev`, `test`, `test-cov`, `docker-up`, `docker-down`, `docker-storage`, `lint`, `format`
- [x] Configurer `pyproject.toml` (ruff, mypy, pytest)
- [x] Vérifier que tous les packages s'importent sans erreur (squelettes de modules vides)

**Livrables :** Structure de dossiers, requirements installables, CI locale fonctionnelle.

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

**Tests écrits :** `tests/test_config.py` — 14 tests
- [x] Merge 3 niveaux (base + scénario + override)
- [x] Surcharge individuelle d'une machine (srv-master-02)
- [x] `parse_duration` : cas nominaux + cas erreur

**Critère d'acceptation :** Tous les tests `test_config.py` passent. ✅

---

### Étape 1.3 — Modèle physique (fonctions pures) ✅

**Objectif :** Implémenter l'intégralité du modèle thermique sous forme de fonctions pures et testables.

**Tâches :**
- [x] Implémenter `simulation/physics.py` avec les fonctions :
  - `compute_load_power(load_factor, idle_w, max_w, alpha) -> float`
  - `compute_heat_input(power_w, heat_ratio) -> float`
  - `compute_tau(tau_max, fan_rpm_mean, k_cool) -> float`
  - `compute_thermal_step(T_current, Q_in, tau, C_th, T_amb, dt) -> float`
  - `compute_fan_auto_speed(T_current, T_amb, gain, f_max) -> int`
  - `compute_energy_kwh(power_w, fan_count, fan_power_w, tick_rate_hz) -> float`
  - `compute_cost(energy_kwh, pue, price_eur_kwh) -> float`
- [x] Implémenter `simulation/noise.py` :
  - `gaussian_noise(value, std) -> float`
  - `add_spike(value, probability, magnitude) -> float`
  - `accumulate_drift(current_drift, rate_per_s, dt) -> float`
  - `weibull_event(shape, scale_s, elapsed_s, dt) -> bool`
  - `exponential_event(scale_s, dt) -> bool`
  - `uniform_event(probability_per_tick) -> float` *(ajout : nécessaire pour power_surge)*

**Tests écrits :** `tests/test_physics.py` — 35 tests
- [x] La température augmente sous charge (load=0.8, fans off)
- [x] La température se stabilise avec des fans à fond
- [x] La température converge vers T_amb sans charge
- [x] L'énergie cumulée croît strictement à chaque tick
- [x] Le bruit gaussien ne produit pas de valeurs aberrantes (±5σ)

**Critère d'acceptation :** Tous les tests `test_physics.py` passent. Les fonctions sont purement déterministes (numpy seed fixé dans les tests). ✅

---

## Phase 2 — Simulation ✅

### Étape 2.1 — MachineSimulator ✅

**Objectif :** Implémenter la machine individuelle avec son état et sa logique de tick.

**Tâches :**
- [x] Implémenter `simulation/machine.py` avec `MachineSimulator`, `FanState`, `ActiveFault`, `ThermalConfig`, `SensorConfig`
- [x] Implémenter la logique d'état (ON/OFF/DEGRADED) basée sur la température et l'hystérésis
- [x] Implémenter le calcul d'énergie cumulée et la gestion des ventilateurs (auto / manual)
- [x] Implémenter `snapshot()` retournant un payload JSON-serialisable

**Tests écrits :** `tests/test_machine.py`
- [x] `power_on()` échoue si T > t_restart_c
- [x] `power_on()` réussit si T <= t_restart_c
- [x] Surchauffe force le passage en `off`
- [x] `set_fan_speed()` clamp la vitesse et force le mode `manual`
- [x] L'énergie cumulée augmente avec les ticks
- [x] `inject_fault()` ajoute bien une panne et elle expire dans le temps

**Critère d'acceptation :** Tous les tests `test_machine.py` passent. ✅

---

### Étape 2.2 — Profils de charge et bruit ✅

**Objectif :** Implémenter le moteur de scénarios (profils de charge).

**Tâches :**
- [x] Implémenter `ScenarioEngine` dans `simulation/scenarios.py` avec les profils :
  - `sine_wave`
  - `ramp_with_spikes`
  - `constant`
  - `step`
- [x] Utiliser `numpy` pour les profils sinusoïdaux et les spikes (processus de Poisson)

**Critère d'acceptation :** Les profils peuvent être sélectionnés via la config et renvoient des valeurs dans [0, 1]. ✅

---

### Étape 2.3 — Injection de pannes (FaultScheduler) ✅

**Objectif :** Implémenter le planificateur de pannes avec distributions statistiques.

**Tâches :**
- [x] Implémenter `FaultConfig` et `FaultScheduler` dans `simulation/scenarios.py`
- [x] Supporter les distributions : `weibull`, `exponential`, `uniform`
- [x] Appeler `machine.inject_fault()` lorsque l'événement est tiré

**Critère d'acceptation :** Le scheduler peut injecter des pannes selon les distributions configurées. ✅

---

### Étape 2.4 — ClusterSimulator ✅

**Objectif :** Orchestrer N machines en parallèle avec asyncio.

**Tâches :**
- [x] Implémenter `ClusterSimulator` dans `simulation/cluster.py`
- [x] Construire les `MachineSimulator` à partir de la config mergée
- [x] Implémenter `run()` avec une boucle à `tick_rate_hz`
- [x] Intégrer `ScenarioEngine` et `FaultScheduler`
- [x] Implémenter `get_snapshot()` retournant un snapshot complet du cluster

**Critère d'acceptation :** La boucle `run()` peut être lancée dans une tâche asyncio et `get_snapshot()` retourne un payload cohérent. ✅

---

## Phase 3 — MQTT ✅

### Étape 3.1 — Publisher aiomqtt ✅

**Objectif :** Implémenter la couche de publication MQTT avec la convention de topics `dt/`.

**Tâches :**
- [x] Implémenter `mqtt/publisher.py` avec `MqttPublisher` comme context manager asyncio
- [x] Pattern de reconnexion automatique (`_reconnect_loop` avec `async with aiomqtt.Client(...)`)
- [x] Méthodes : `publish_telemetry`, `publish_fan_state`, `publish_status`, `publish_fault`, `publish_summary`, `publish_energy`
- [x] Sérialisation JSON avec `datetime.now(timezone.utc)` pour `ts`
- [x] Publication silencieuse si broker indisponible (pas de crash simulateur)

**Critère d'acceptation :** Un message visible dans MQTT Explorer sur `dt/cluster_alpha/srv-worker-01/telemetry`. ✅

---

### Étape 3.2 — Intégration simulation → MQTT ✅

**Objectif :** Connecter `ClusterSimulator` et `MqttPublisher` dans la boucle principale.

**Tâches :**
- [x] `ClusterSimulator.run()` accepte `publisher: MqttPublisher | None` et `ws_manager: Any | None`
- [x] Appeler `publish_telemetry()` + topics scalaires à chaque cycle `events_per_sec`
- [x] Publier `publish_status()` uniquement lors d'un changement d'état (mémorisation `_prev_status`)
- [x] Publier `publish_fan_state()` uniquement lors d'un changement (mémorisation `_prev_fans`)
- [x] Publier `publish_fault()` à la première détection d'une panne (set `_published_faults`)
- [x] Publier `publish_summary()` toutes les 5 s (timer interne par compteur de ticks)
- [x] Publier `publish_energy()` toutes les 60 s (timer interne)
- [x] Flag `--no-mqtt` court-circuite l'instanciation du publisher

**Correctifs associés :**
- [x] `fix(scenarios)` : alignement des paramètres `_ramp_with_spikes()` sur les clés de `stress.yaml`
- [x] `fix(deps)` : `websockets` monté à `15.0.1` dans `requirements.dashboard.txt` (compatibilité `amqtt`)

**Critère d'acceptation :** `docker compose up mosquitto` + `python scripts/run_simulator.py --scenario nominal` → flux visible sur `mosquitto_sub -h localhost -t 'dt/#' -v`. ✅

---

## Phase 4 — API FastAPI

### Étape 4.1 — Lifespan et structure API

**Objectif :** Mettre en place le squelette FastAPI avec le pattern lifespan.

**Tâches :**
- [ ] Implémenter `api/main.py` avec `@asynccontextmanager lifespan` (code de référence dans `specifications.md § 7.1`)
- [ ] Configurer CORS (origines autorisées : `http://localhost:8501` pour Streamlit)
- [ ] Implémenter `api/deps.py` avec `get_cluster()` et `get_ws_manager()`
- [ ] Créer `api/models.py` avec tous les schémas Pydantic v2
- [ ] `GET /` retournant nom, version, cluster_id, scénario actif

**Critère d'acceptation :** `uvicorn api.main:app --reload` démarre, `/docs` accessible.

---

### Étape 4.2 — Endpoints de commande

**Objectif :** Implémenter tous les endpoints REST de commande.

**Tâches :**
- [ ] `api/routes/machines.py` : POST power, PUT fan_speed, PUT fan_mode, GET machine
- [ ] `api/routes/cluster.py` : GET status, GET energy, POST power cluster, PUT fan_speed cluster
- [ ] Retourner `404` si `machine_id` inconnu
- [ ] Retourner `409` si `power_on()` impossible (T > t_restart_c)

**Tests :** `tests/test_api.py` (httpx AsyncClient)

**Critère d'acceptation :** Tous les tests API endpoints passent.

---

### Étape 4.3 — WebSocket /ws/cluster

**Objectif :** Implémenter le push temps réel du snapshot cluster.

**Tâches :**
- [ ] `api/ws.py` : `ConnectionManager` + endpoint `/ws/cluster` (code de référence dans `specifications.md § 7.2`)
- [ ] `ClusterSimulator.run()` appelle `ws_manager.broadcast(snapshot)` à 1 Hz (déjà prévu dans la signature)
- [ ] Vérifier avec `wscat -c ws://localhost:8000/ws/cluster`
- [ ] Vérifier le nettoyage automatique des connexions mortes

**Critère d'acceptation :** `wscat` reçoit un JSON toutes les ~1s.

---

### Étape 4.4 — Endpoints simulation

**Objectif :** Permettre le contrôle du simulateur depuis l'API.

**Tâches :**
- [ ] `POST /simulation/fault` : appelle `machine.inject_fault()`
- [ ] `DELETE /simulation/fault/{machine_id}` : appelle `machine.cancel_fault()`
- [ ] `PUT /simulation/scenario` : recharge la config et reconstruit le `ScenarioEngine` à chaud

**Critère d'acceptation :** `PUT /simulation/scenario {scenario: stress}` change le profil de charge en moins de 2s.

---

## Phase 5 — Dashboard Streamlit

### Étape 5.1 — Client WebSocket Streamlit

**Tâches :**
- [ ] Implémenter `dashboard/ws_client.py` (code de référence dans `specifications.md § 8.1`)
- [ ] Implémenter `dashboard/api_client.py` avec `httpx.AsyncClient`
- [ ] `@st.cache_resource` pour instancier `ClusterWSClient` une seule fois
- [ ] Reconnexion automatique si l'API redémarre

**Critère d'acceptation :** `streamlit run dashboard/app.py` démarre sans erreur, snapshot non-vide en moins de 3s.

---

### Étape 5.2 — Vue Cluster (onglet 1)

**Tâches :**
- [ ] 4 métriques : machines ON, T_max, W_total, coût €/h
- [ ] Heatmap plotly : une cellule par machine, couleur = `temp_cpu`
- [ ] `st.fragment(run_every=1)` pour mise à jour automatique

**Critère d'acceptation :** Heatmap se met à jour toutes les secondes.

---

### Étape 5.3 — Vue Machine + commandes (onglet 2)

**Tâches :**
- [ ] Sélecteur machine, métriques toutes sondes, état fans
- [ ] Buffer circulaire (100 points) pour `st.line_chart` de `temp_cpu`
- [ ] Boutons : Power ON/OFF, Set Fan Speed, Fan Mode Auto/Manual
- [ ] Afficher en rouge si `fault_active: true` ou `status: degraded`

**Critère d'acceptation :** `Power OFF` passe la machine en état `off` en moins de 2s.

---

### Étape 5.4 — Vues Simulation et Énergie (onglets 3 et 4)

**Tâches :**
- [ ] Onglet 3 : sélecteur scénario, formulaire injection panne, journal 20 événements
- [ ] Onglet 4 : kWh cumulés, €/h, PUE, bar chart par machine, projection mensuelle

**Critère d'acceptation :** Injection de panne depuis le dashboard visible dans le journal en moins de 2s.

---

## Phase 6 — Déploiement Docker

### Étape 6.1 — Dockerfiles

**Tâches :**
- [ ] `Dockerfile` (simulateur + API)
- [ ] `Dockerfile.dashboard`
- [ ] `Dockerfile.consumer`
- [ ] `mosquitto/config/mosquitto.conf` ✅ *(déjà créé en étape 1.1)*

**Critère d'acceptation :** `docker build -t jumeaux-chauds .` sans erreur.

---

### Étape 6.2 — Docker Compose noyau

**Tâches :**
- [ ] Créer `docker-compose.yml`
- [ ] Vérifier le démarrage ordonné (mosquitto → iot-twin → dashboard)
- [ ] Variables d'environnement `SCENARIO`, `CLUSTER_ID` prises en compte

**Critère d'acceptation :** `docker compose up` → dashboard sur `http://localhost:8501` avec données temps réel.

---

### Étape 6.3 — Profil storage (TimescaleDB + Grafana)

**Tâches :**
- [ ] Implémenter `consumer/mqtt_to_timescale.py`
- [ ] `consumer/schema.sql` avec `sensor_data` + `create_hypertable`
- [ ] Services `timescaledb`, `mqtt-consumer`, `grafana` avec `profiles: ["storage"]`
- [ ] `grafana/provisioning/datasources/timescaledb.yaml`
- [ ] Dashboard Grafana basique (courbe `temp_cpu` par machine)

**Critère d'acceptation :** `docker compose --profile storage up` → Grafana sur `http://localhost:3000` avec données visibles.

---

## Phase 7 — Tests

### Étape 7.1 — Tests unitaires

**Tâches :**
- [x] `tests/conftest.py` : fixtures partagées (`numpy.random.seed(42)`) ✅
- [x] Compléter `tests/test_physics.py` (35 cas) ✅
- [x] Compléter `tests/test_config.py` (14 cas) ✅
- [x] Compléter `tests/test_machine.py` (≥ 8 cas)
- [ ] `pytest --cov=simulation --cov=config --cov-report=html`

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

Ces extensions sont laissées à l'initiative des étudiants. Elles sont documentées dans `documents/specifications.md § 14`.

### Extensions ⭐
- [ ] **Scénario heatwave** : `config/scenarios/heatwave.yaml` avec `ambient_temp_c: 32.0`
- [ ] **Observer MQTT** : abonner MQTT Explorer ou Node-RED, documenter les topics

### Extensions ⭐⭐
- [ ] **Régulateur PID** : remplacer le régulateur proportionnel (P, I, D configurables en YAML)
- [ ] **Candlestick OHLC** : buffer 60s sur `temp_cpu`, graphe Plotly candlestick
- [ ] **Coût électrique** : projection mensuelle avec différents tarifs et PUE, export CSV
- [ ] **Stack Grafana** : activer profil `storage`, dashboard Grafana complet

### Extensions ⭐⭐⭐
- [ ] **Détection d'anomalie ML** : IsolationForest / PyOD sur séries MQTT, alertes dashboard
- [ ] **Classification drift / surchauffe** : écart `temp_cpu - temp_inlet` comme feature
- [ ] **Estimation Weibull (MLE)** : estimer β et η par maximum de vraisemblance
- [ ] **Agent RL** : formaliser le contrôle des fans comme MDP, DQN (Stable-Baselines3)
- [ ] **Command consumer MQTT** : subscriber `cmd/#`, appeler les méthodes du simulateur sans REST
- [ ] **Outil MCP** : exposer les endpoints comme outils MCP pour un agent LLM de monitoring

---

## Checklist de démarrage pour un développeur

1. **Lire** `documents/specifications.md` en entier (~30 min)
2. **Cloner** le dépôt et créer une branche `feature/phase-4-api`
3. **S'appuyer sur ClusterSimulator** pour brancher l'API FastAPI (Phase 4) — le publisher MQTT est déjà intégré
4. **Valider** chaque étape avec ses tests avant de passer à la suivante
5. **Utiliser** `docker compose up mosquitto` pour avoir le broker disponible

---

*Tristan Vanrullen — La Plateforme, Marseille — 2026*
