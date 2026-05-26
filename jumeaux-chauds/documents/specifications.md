# Jumeaux Chauds — Spécifications Techniques v1.0

> **Auteur :** Tristan Vanrullen  
> **Date :** Mai 2026  
> **Version :** 1.0.0

---

## Table des matières

1. [Périmètre et noyau fonctionnel](#1-périmètre-et-noyau-fonctionnel)
2. [Décisions techniques](#2-décisions-techniques)
3. [Architecture globale](#3-architecture-globale)
4. [Configuration YAML hiérarchique](#4-configuration-yaml-hiérarchique)
5. [Modèle physique](#5-modèle-physique)
6. [Topics MQTT](#6-topics-mqtt)
7. [API FastAPI](#7-api-fastapi)
8. [Dashboard Streamlit](#8-dashboard-streamlit)
9. [Consumer MQTT → TimescaleDB (optionnel)](#9-consumer-mqtt--timescaledb-optionnel)
10. [Structure du projet](#10-structure-du-projet)
11. [Requirements](#11-requirements)
12. [Docker Compose](#12-docker-compose)
13. [Tests](#13-tests)
14. [Extensions pédagogiques](#14-extensions-pédagogiques)

---

## 1. Périmètre et noyau fonctionnel

### 1.1 Ce que fait le projet (noyau non négociable)

**Jumeaux Chauds** remplit trois fonctions fondamentales :

1. **Simuler** : chaque machine a un état interne cohérent (température, puissance, vitesse des fans) régi par un modèle physique thermique en temps réel.
2. **Diffuser** : les données capteurs sont publiées en continu sur un broker MQTT Mosquitto via `aiomqtt`. N'importe quel consumer MQTT peut s'abonner sans modification du simulateur.
3. **Recevoir des commandes** : une API FastAPI permet de commander les machines (allumage, vitesse des fans, mode automatique/manuel) et d'injecter des scénarios de pannes à chaud.

Tout le reste — dashboard, persistance TimescaleDB, Grafana — est optionnel et activable via des profils Docker Compose.

### 1.2 Ce que le projet ne fait pas (délibérément)

- Pas d'authentification MQTT (mode `allow_anonymous true` pour le dev)
- Pas de persistance des états entre redémarrages (état in-memory)
- Pas de multiples clusters en parallèle dans un seul processus (utiliser `docker compose scale`)
- Pas de scalabilité horizontale (un processus asyncio suffit pour ~100 machines)

---

## 2. Décisions techniques

| Composant | Choix | Justification |
|---|---|---|
| Client MQTT | **`aiomqtt` v2.4.x** | État de l'art asyncio 2025 — MQTTv5, reconnexion intégrée, sans callbacks, sans héritage paho |
| API | **FastAPI** + lifespan asyncio | Même event loop que le simulateur, WebSocket natif, OpenAPI auto-générée |
| Configuration | **OmegaConf** merge 3 niveaux | Deep merge YAML hiérarchique : cluster → rôle → machine individuelle |
| Dashboard | **Streamlit** + WebSocket push | Push 1 Hz via `/ws/cluster`, pas de polling |
| Tests | **pytest-asyncio** + broker embarqué `amqtt` | Tests unitaires du publisher sans broker externe |
| Déploiement | **Docker Compose** avec profils | `default` = simulateur seul ; `--profile storage` = +TimescaleDB+Grafana |
| Modèle physique | **Équation thermique du 1er ordre** | Standard industriel lumped-parameter, entièrement paramétrable en YAML |
| Convention topics MQTT | **`dt/` / `cmd/`** | Séparation données / commandes, recommandation AWS IoT Core |

---

## 3. Architecture globale

```
┌──────────────────────────────────────────────────────────────────┐
│  Docker Network : iot_net                                        │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  iot-twin (processus Python unique — asyncio event loop)  │   │
│  │                                                           │   │
│  │  FastAPI lifespan                                         │   │
│  │  ┌──────────────────────────────────────────────────────┐ │   │
│  │  │  asyncio.create_task(cluster.run())                  │ │   │
│  │  │    ├── MachineSimulator.tick() × N  (modèle physique)│ │   │
│  │  │    └── aiomqtt Publisher ──────────────────────────► │ │   │
│  │  └──────────────────────┬───────────────────────────────┘ │   │
│  │                         │                                  │   │
│  │  FastAPI routes (async) │                                  │   │
│  │  ├── POST /machines/{id}/power                             │   │
│  │  ├── PUT  /machines/{id}/fan_speed                         │   │
│  │  ├── POST /simulation/fault                                │   │
│  │  ├── PUT  /simulation/scenario                             │   │
│  │  └── WS   /ws/cluster  ◄── push 1Hz (dashboard)           │   │
│  └───────────────────────────────────────────────────────────┘   │
│                         │ MQTT publish                           │
│  ┌──────────────────────▼──────────────────────────────────┐     │
│  │  Mosquitto broker (eclipse-mosquitto:2)                  │     │
│  │  Port 1883 (TCP) — Port 9001 (WebSocket MQTT)            │     │
│  └──────────────────────────────────────────────────────────┘     │
│            │ subscribe dt/#                                       │
│            ├──────────────────────────────────────────────────┐   │
│            │ [profil default]         [profil storage]         │   │
│  ┌─────────▼─────────┐    ┌───────────▼──────────────────────┐   │
│  │  Dashboard        │    │  mqtt-consumer                   │   │
│  │  Streamlit :8501  │    │  aiomqtt → asyncpg               │   │
│  │  WS + REST        │    │  → TimescaleDB :5432             │   │
│  └───────────────────┘    │  → Grafana :3000                 │   │
│                            └──────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 3.1 Séparation des responsabilités

| Couche | Module | Responsabilité |
|---|---|---|
| Physique | `simulation/physics.py` | Équation thermique, calcul puissance, PUE, énergie |
| Bruit | `simulation/noise.py` | Gaussien, drift, spikes, Weibull |
| Machine | `simulation/machine.py` | État, tick, inject_fault, snapshot |
| Cluster | `simulation/cluster.py` | Orchestration N machines, asyncio.gather |
| MQTT | `mqtt/publisher.py` | Topics, sérialisation JSON, publish |
| Config | `config/loader.py` | OmegaConf merge 3 niveaux |
| API | `api/main.py` + `api/routes/` | FastAPI, lifespan, WebSocket, endpoints |
| Dashboard | `dashboard/` | Streamlit, WebSocket client, REST client |
| Consumer | `consumer/` (optionnel) | MQTT → TimescaleDB |

---

## 4. Configuration YAML hiérarchique

Le système de configuration repose sur **trois niveaux de merge** via `OmegaConf.merge()`. Un niveau plus profond surcharge le niveau parent sans effacer les clés non mentionnées.

```
Niveau 1 : config/base.yaml          (valeurs de référence cluster + machines)
           ↓ OmegaConf.merge()
Niveau 2 : config/scenarios/nominal.yaml  (profil de simulation)
           ↓ OmegaConf.merge()
Niveau 3 : overrides via ENV vars ou CLI  (ex: CLUSTER_ID, SCENARIO, TICK_RATE)
```

### 4.1 `config/base.yaml` (spécification normative)

```yaml
# ─── Identité du cluster ──────────────────────────────────────────────────────
cluster:
  id: "cluster_alpha"
  location: "Marseille"
  pue: 1.40                          # Power Usage Effectiveness global
  env_factor: 1.05                   # multiplicateur overhead refroidissement
  electricity_price_eur_kwh: 0.20    # coût €/kWh

  # ─── Broker MQTT ────────────────────────────────────────────────────────────
  mqtt:
    broker_host: "mosquitto"
    broker_port: 1883
    protocol_version: 5              # MQTTv5 via aiomqtt
    client_id_prefix: "twin"
    topic_root: "dt"                 # data telemetry (convention AWS IoT)
    cmd_root: "cmd"                  # commands
    publish_interval_s: 1.0
    qos_telemetry: 0
    qos_events: 1                    # QoS 1 pour pannes et changements d'état

  # ─── Profils par rôle ───────────────────────────────────────────────────────
  role_profiles:
    master:
      power:
        idle_watts: 200.0
        max_watts: 1700.0
        heat_ratio: 0.70
      thermal:
        ambient_temp_c: 22.0
        thermal_capacity_j_per_c: 800.0
        tau_max_s: 90.0              # constante de temps thermique max (fans off)
        k_cool_rpm_factor: 3.5       # contribution refroidissement par rpm×1000
        alpha_load_exponent: 1.5     # non-linéarité charge → puissance
        t_shutdown_c: 90.0
        t_restart_c: 55.0
      temperature_sensors:
        - id: "temp_cpu"
          bias_c: 0.0
        - id: "temp_inlet"
          bias_c: -8.0
        - id: "temp_chassis"
          bias_c: -4.0
      fans:
        count: 2
        max_rpm: 5000
        initial_rpm: 0
        power_per_fan_w: 15.0
        control_mode: "auto"         # "auto" | "manual"
        auto_policy:
          type: "proportional"
          gain_rpm_per_c: 50.0
      noise:
        temperature_std_c: 0.3
        power_std_w: 2.0
        fan_speed_std_rpm: 10.0

    worker:
      power:
        idle_watts: 100.0
        max_watts: 1450.0
        heat_ratio: 0.70
      thermal:
        ambient_temp_c: 22.0
        thermal_capacity_j_per_c: 600.0
        tau_max_s: 100.0
        k_cool_rpm_factor: 3.0
        alpha_load_exponent: 1.5
        t_shutdown_c: 88.0
        t_restart_c: 50.0
      temperature_sensors:
        - id: "temp_cpu"
          bias_c: 0.0
        - id: "temp_inlet"
          bias_c: -6.0
      fans:
        count: 2
        max_rpm: 5000
        initial_rpm: 0
        power_per_fan_w: 12.0
        control_mode: "auto"
        auto_policy:
          type: "proportional"
          gain_rpm_per_c: 45.0
      noise:
        temperature_std_c: 0.3
        power_std_w: 1.5
        fan_speed_std_rpm: 8.0

  # ─── Machines du cluster ────────────────────────────────────────────────────
  machines:
    - id: "srv-master-01"
      role: "master"
    - id: "srv-master-02"
      role: "master"
      thermal:                       # surcharge individuelle
        t_shutdown_c: 92.0
    - id: "srv-worker-01"
      role: "worker"
    - id: "srv-worker-02"
      role: "worker"
    - id: "srv-worker-03"
      role: "worker"
```

### 4.2 `config/scenarios/nominal.yaml`

```yaml
simulation:
  mode: "nominal"
  tick_rate_hz: 10.0
  events_per_sec: 1.0
  duration: "0"                      # "0" = infini ; "1h30m" = durée finie

  load_profile:
    type: "sine_wave"
    base_load: 0.35
    amplitude: 0.20
    period_s: 300.0

  noise:
    enabled: true
    spike_probability: 0.002
    spike_magnitude_c: 2.0
    drift:
      enabled: false

  fault_injection:
    enabled: false
```

### 4.3 `config/scenarios/stress.yaml`

```yaml
simulation:
  mode: "stress"
  tick_rate_hz: 10.0
  events_per_sec: 2.0
  duration: "0"

  load_profile:
    type: "ramp_with_spikes"
    ramp_start: 0.20
    ramp_end: 0.95
    ramp_duration_s: 600.0
    spike_probability: 0.02
    spike_duration_s: 30.0
    spike_magnitude: 0.30

  noise:
    enabled: true
    spike_probability: 0.005
    spike_magnitude_c: 5.0
    drift:
      enabled: true
      rate_c_per_s: 0.01

  fault_injection:
    enabled: true
    faults:
      - type: "fan_failure"
        distribution: "weibull"
        shape: 1.5
        scale_s: 7200
        magnitude: 1.0
      - type: "sensor_drift"
        distribution: "exponential"
        scale_s: 3600
        magnitude: 0.5
      - type: "power_surge"
        distribution: "uniform"
        probability_per_tick: 0.0002
        magnitude: 1.30
    recovery_delay_s: 120.0
```

---

## 5. Modèle physique

### 5.1 Modèle thermique du premier ordre

À chaque tick `Δt = 1 / tick_rate_hz`, pour chaque machine allumée :

**Puissance électrique consommée :**

```
P_elec(t) = P_idle + (P_max - P_idle) × L(t)^alpha
```

avec `L(t) ∈ [0,1]` le facteur de charge fourni par le profil de simulation.

**Production de chaleur :**

```
Q_in(t) = P_elec(t) × heat_ratio
```

**Constante de refroidissement dynamique :**

```
tau(t) = tau_max / (1 + k_cool × mean_fan_rpm(t) / 1000)
```

**Équation thermique différentielle (Euler explicite) :**

```
T(t + Δt) = T(t) + Δt × [ Q_in(t) / C_th  -  (T(t) - T_amb) / tau(t) ]
```

**Valeur observée pour chaque capteur s :**

```
T_obs_s(t) = T(t) + bias_s + delta_s(t) + N(0, sigma_temp²)
```

avec `delta_s(t)` la dérive cumulative (active si le capteur est en mode drift).

### 5.2 Régulateur automatique des fans (mode AUTO)

```
f_auto(t) = clip( k_fan × max(0, T(t) - T_amb),  0,  f_max )
```

En mode `manual`, la valeur de `f_rpm` est fixée par la dernière commande API.

### 5.3 Logique d'état des machines

```
OFF → ON       : commande API power_on, si T ≤ t_restart_c
ON  → OFF      : T ≥ t_shutdown_c  (protection thermique automatique)
ON  → DEGRADED : panne active (fan_failure, sensor_drift, power_surge)
DEGRADED → ON : recovery après recovery_delay_s si T ≤ t_restart_c
```

### 5.4 Métriques énergétiques du cluster

**Énergie IT cumulée (kWh) :**

```
E_IT(t) += (1 / tick_rate) × Σ_k_ON( P_elec_k(t) + n_fans × P_fan ) / 3_600_000
```

**Coût total avec PUE (€) :**

```
C_total = E_IT × PUE × prix_kWh
```

---

## 6. Topics MQTT

Convention `dt/` (data telemetry) / `cmd/` (commands), hiérarchie general-to-specific.

### 6.1 Topics de données (simulateur → broker)

| Topic | QoS | Fréquence | Contenu |
|---|---|---|---|
| `dt/{cluster}/{machine}/telemetry` | 0 | `events_per_sec` | Snapshot complet machine |
| `dt/{cluster}/{machine}/temp/{sensor_id}` | 0 | `events_per_sec` | Valeur scalaire °C |
| `dt/{cluster}/{machine}/power` | 0 | `events_per_sec` | Puissance W + énergie kWh |
| `dt/{cluster}/{machine}/fan/{idx}` | 0 | On change | RPM + mode + status |
| `dt/{cluster}/{machine}/status` | 1 | On change | `on/off/degraded` |
| `dt/{cluster}/{machine}/fault` | 1 | On event | Type + magnitude + ts_start |
| `dt/{cluster}/summary` | 1 | 5s | KPIs cluster |
| `dt/{cluster}/metrics/energy` | 1 | 60s | kWh, coût €, PUE effectif |

### 6.2 Topics de commande (cmd/)

| Topic | Payload |
|---|---|
| `cmd/{cluster}/{machine}/power` | `{"action": "on" \| "off"}` |
| `cmd/{cluster}/{machine}/fan/{idx}/speed` | `{"rpm": 3200}` |
| `cmd/{cluster}/{machine}/fan/{idx}/mode` | `{"mode": "auto" \| "manual"}` |
| `cmd/{cluster}/fault_inject` | `{"type": ..., "machine_id": ...}` |

### 6.3 Payload `telemetry` (format normalisé v1.0)

```json
{
  "schema_version": "1.0",
  "ts": "2026-05-17T12:00:00.123Z",
  "cluster_id": "cluster_alpha",
  "machine_id": "srv-worker-01",
  "role": "worker",
  "simulation_mode": "stress",
  "status": "on",
  "load_factor": 0.67,
  "temperatures": {
    "temp_cpu":   { "value_c": 72.4, "drift_active": false, "fault": false },
    "temp_inlet": { "value_c": 64.2, "drift_active": false, "fault": false }
  },
  "fans": [
    { "idx": 0, "rpm": 3200, "mode": "auto", "fault": false },
    { "idx": 1, "rpm": 3200, "mode": "auto", "fault": false }
  ],
  "power_w": 980.5,
  "energy_kwh_cumulated": 1.241,
  "fault_active": false
}
```

---

## 7. API FastAPI

### 7.1 Pattern lifespan (code de référence)

```python
# api/main.py
from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from simulation.cluster import ClusterSimulator
from mqtt.publisher import MqttPublisher
from config.loader import load_config

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    publisher = MqttPublisher(cfg.cluster.mqtt)
    cluster = ClusterSimulator(cfg)
    app.state.cluster = cluster
    app.state.ws_manager = ConnectionManager()

    async with publisher:                        # aiomqtt async context manager
        task = asyncio.create_task(
            cluster.run(publisher, app.state.ws_manager)
        )
        yield
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

app = FastAPI(title="Jumeaux Chauds API", version="1.0.0", lifespan=lifespan)
```

### 7.2 ConnectionManager WebSocket

```python
# api/ws.py
class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)   # nettoyage connexions mortes

@router.websocket("/ws/cluster")
async def ws_cluster(websocket: WebSocket,
                     manager: ConnectionManager = Depends(get_ws_manager)):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive + détection déconnexion
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

### 7.3 Endpoints REST

| Méthode | Path | Body / Params | Description |
|---|---|---|---|
| `GET` | `/` | — | Infos API + version config |
| `GET` | `/cluster/status` | — | Snapshot complet JSON |
| `GET` | `/cluster/metrics/energy` | — | kWh, coût €, PUE, timestamp |
| `GET` | `/machines/{id}` | — | État d'une machine |
| `POST` | `/machines/{id}/power` | `{"action": "on"\|"off"}` | Allumer / éteindre |
| `PUT` | `/machines/{id}/fan_speed` | `{"rpm": int, "fan_idx": int}` | Régler vitesse fan |
| `PUT` | `/machines/{id}/fan_mode` | `{"mode": "auto"\|"manual"}` | Changer mode fan |
| `POST` | `/cluster/power` | `{"action": "on"\|"off"}` | Tout le cluster |
| `PUT` | `/cluster/fan_speed` | `{"rpm": int}` | Fans de tout le cluster |
| `POST` | `/simulation/fault` | `FaultCmd` | Injecter une panne |
| `DELETE` | `/simulation/fault/{machine_id}` | — | Annuler une panne |
| `PUT` | `/simulation/scenario` | `{"scenario": "nominal"\|"stress"}` | Changer scénario |
| `WS` | `/ws/cluster` | — | Push JSON 1 Hz |

### 7.4 Schéma Pydantic FaultCmd

```python
class FaultInjectionCommand(BaseModel):
    machine_id: str
    fault_type: Literal["fan_failure", "sensor_drift", "power_surge", "network_loss"]
    duration_s: float | None = None   # None = permanent jusqu'à DELETE
    magnitude: float = 1.0            # amplitude de l'effet
```

---

## 8. Dashboard Streamlit

### 8.1 Client WebSocket

```python
# dashboard/ws_client.py
import asyncio, json, threading, websockets

class ClusterWSClient:
    def __init__(self, ws_url: str):
        self._url = ws_url
        self._snapshot: dict = {}
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        asyncio.run(self._listen())

    async def _listen(self):
        async for ws in websockets.connect(self._url, ping_interval=20):
            try:
                async for msg in ws:
                    with self._lock:
                        self._snapshot = json.loads(msg)
            except websockets.ConnectionClosed:
                await asyncio.sleep(2)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._snapshot)
```

### 8.2 Structure des onglets

```
app.py
├── Onglet 1 : Vue Cluster
│   ├── KPIs : machines ON, T_max, W_total, PUE, coût €
│   └── Heatmap des températures (plotly)
│
├── Onglet 2 : Vue Machine
│   ├── Sélecteur machine
│   ├── Métriques : T_cpu, T_inlet, fans, puissance, état
│   ├── Courbes temps réel (st.line_chart avec buffer circulaire)
│   └── Panneau de commandes (power on/off, fan speed, fan mode)
│
├── Onglet 3 : Simulation
│   ├── Sélecteur de scénario (nominal / stress)
│   ├── Injection de panne : type, machine, durée, magnitude
│   └── Journal des événements récents
│
└── Onglet 4 : Énergie
    ├── kWh cumulés, coût €/h, PUE effectif
    └── Graphique consommation par machine
```

---

## 9. Consumer MQTT → TimescaleDB (optionnel)

```python
# consumer/mqtt_to_timescale.py
import asyncio, json
import aiomqtt
import asyncpg

async def consume(broker_host: str, db_url: str):
    pool = await asyncpg.create_pool(db_url)
    async with aiomqtt.Client(broker_host) as client:
        await client.subscribe("dt/#")
        async for message in client.messages:
            payload = json.loads(message.payload)
            topic = str(message.topic)
            if "/telemetry" in topic:
                temps = payload.get("temperatures", {})
                for sensor_id, sensor_data in temps.items():
                    await pool.execute(
                        "INSERT INTO sensor_data(time, cluster_id, machine_id, "
                        "sensor_type, value) VALUES(NOW(), $1, $2, $3, $4)",
                        payload["cluster_id"], payload["machine_id"],
                        sensor_id, sensor_data.get("value_c")
                    )
```

```sql
-- consumer/schema.sql
CREATE TABLE IF NOT EXISTS sensor_data (
    time        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cluster_id  TEXT        NOT NULL,
    machine_id  TEXT        NOT NULL,
    sensor_type TEXT        NOT NULL,
    value       DOUBLE PRECISION
);
SELECT create_hypertable('sensor_data', 'time', if_not_exists => TRUE);
```

---

## 10. Structure du projet

```
jumeaux-chauds/
│
├── config/
│   ├── base.yaml
│   └── scenarios/
│       ├── nominal.yaml
│       └── stress.yaml
│
├── simulation/
│   ├── __init__.py
│   ├── cluster.py
│   ├── machine.py
│   ├── physics.py
│   ├── noise.py
│   ├── scenarios.py
│   └── duration.py
│
├── mqtt/
│   └── publisher.py
│
├── api/
│   ├── main.py
│   ├── deps.py
│   ├── ws.py
│   ├── models.py
│   └── routes/
│       ├── machines.py
│       ├── cluster.py
│       └── simulation.py
│
├── consumer/
│   ├── mqtt_to_timescale.py
│   └── schema.sql
│
├── dashboard/
│   ├── app.py
│   ├── ws_client.py
│   ├── api_client.py
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

## 11. Requirements (versions figées)

```
# requirements.txt — simulateur + API
aiomqtt==2.4.0
fastapi==0.115.0
uvicorn[standard]==0.30.0
omegaconf==2.3.0
pydantic==2.7.0
numpy==1.26.0
pyyaml==6.0.1

# requirements.consumer.txt
aiomqtt==2.4.0
asyncpg==0.29.0

# requirements.dashboard.txt
streamlit==1.37.0
websockets==12.0
httpx==0.27.0
plotly==5.22.0

# requirements.test.txt
pytest==8.2.0
pytest-asyncio==0.23.0
httpx==0.27.0
amqtt==0.11.0
```

---

## 12. Docker Compose

```yaml
version: "3.9"
services:

  mosquitto:
    image: eclipse-mosquitto:2
    container_name: mosquitto
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./mosquitto/config/mosquitto.conf:/mosquitto/config/mosquitto.conf
    networks: [iot_net]
    restart: unless-stopped

  iot-twin:
    build: .
    container_name: iot-twin
    ports:
      - "8000:8000"
    environment:
      CLUSTER_ID: "${CLUSTER_ID:-cluster_alpha}"
      SCENARIO: "${SCENARIO:-nominal}"
      MQTT_BROKER_HOST: "mosquitto"
      TICK_RATE_HZ: "${TICK_RATE_HZ:-10}"
    volumes:
      - ./config:/app/config:ro
    depends_on: [mosquitto]
    networks: [iot_net]
    restart: unless-stopped

  dashboard:
    build:
      context: .
      dockerfile: Dockerfile.dashboard
    container_name: dashboard
    ports:
      - "8501:8501"
    environment:
      API_URL: "http://iot-twin:8000"
      WS_URL: "ws://iot-twin:8000/ws/cluster"
    depends_on: [iot-twin]
    networks: [iot_net]

  # ── Storage stack (optionnel : --profile storage) ────────────────────────────
  timescaledb:
    image: timescale/timescaledb:latest-pg16
    profiles: ["storage"]
    container_name: timescaledb
    environment:
      POSTGRES_USER: tsuser
      POSTGRES_PASSWORD: tspassword
      POSTGRES_DB: tsdb
    ports: ["5432:5432"]
    volumes: [timescale_data:/var/lib/postgresql/data]
    networks: [iot_net]

  mqtt-consumer:
    build:
      context: .
      dockerfile: Dockerfile.consumer
    profiles: ["storage"]
    container_name: mqtt-consumer
    environment:
      MQTT_BROKER_HOST: "mosquitto"
      DATABASE_URL: "postgresql://tsuser:tspassword@timescaledb:5432/tsdb"
    depends_on: [mosquitto, timescaledb]
    networks: [iot_net]

  grafana:
    image: grafana/grafana:latest
    profiles: ["storage"]
    container_name: grafana
    ports: ["3000:3000"]
    environment:
      GF_SECURITY_ADMIN_PASSWORD: "admin"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
    depends_on: [timescaledb]
    networks: [iot_net]

volumes:
  timescale_data:
  grafana_data:

networks:
  iot_net:
    driver: bridge
```

---

## 13. Tests

### 13.1 Stratégie de test

| Couche | Type | Outil | Description |
|---|---|---|---|
| Physique | Unitaire | pytest | Équation thermique, stabilisation, shutdown |
| Config | Unitaire | pytest | Merge OmegaConf 3 niveaux, surcharges |
| Machine | Unitaire | pytest | États, transitions, inject_fault |
| Publisher | Intégration | pytest-asyncio + amqtt | Publish sans broker externe |
| API | Intégration | httpx TestClient | Endpoints REST, WebSocket |

### 13.2 Exemple de test physique

```python
# tests/test_physics.py
from simulation.physics import compute_thermal_step

def test_temperature_increases_under_load():
    T = 22.0  # ambient
    for _ in range(100):
        T = compute_thermal_step(
            T_current=T, load_factor=0.8, fan_rpm_mean=0,
            dt=0.1, params=DEFAULT_MASTER_THERMAL
        )
    assert T > 40.0, "La température doit augmenter sous charge"

def test_temperature_stabilizes_with_fans():
    T = 80.0
    for _ in range(500):
        T = compute_thermal_step(
            T_current=T, load_factor=0.5, fan_rpm_mean=4000,
            dt=0.1, params=DEFAULT_MASTER_THERMAL
        )
    assert T < 70.0, "Les fans doivent refroidir la machine"
```

---

## 14. Extensions pédagogiques

### 14.1 Tableau des extensions par niveau

| Niveau | Domaine | Extension | Effort estimé |
|---|---|---|---|
| ⭐ | Config | Créer un scénario `heatwave.yaml` : T_amb +10°C, panne progressive | 2h |
| ⭐ | MQTT | Abonner MQTT Explorer / Node-RED au broker | 1h |
| ⭐ | API | Tester tous les endpoints depuis `/docs` (OpenAPI auto-générée) | 1h |
| ⭐⭐ | Dashboard | Ajouter un graphe candlestick OHLC sur `temp_cpu` (fenêtres 60s) | 4h |
| ⭐⭐ | Physique | Remplacer le régulateur proportionnel par un **PID** configurable | 6h |
| ⭐⭐ | Storage | Activer le profil `storage`, configurer un dashboard Grafana | 3h |
| ⭐⭐ | Coût | Calculer la facture d'électricité mensuelle avec PUE réaliste | 3h |
| ⭐⭐ | Config | Implémenter un 3ème niveau YAML par machine (surcharge totale) | 4h |
| ⭐⭐⭐ | ML | Entraîner un modèle de **détection d'anomalie** (IsolationForest / PyOD) | 12h |
| ⭐⭐⭐ | ML | Classifier `capteur_en_drift` vs `vraie_surchauffe` | 8h |
| ⭐⭐⭐ | Stats | Estimer les paramètres Weibull (MLE) sur l'historique de pannes simulées | 6h |
| ⭐⭐⭐ | RL | Entraîner un agent **Reinforcement Learning** pour optimiser les fans | 20h+ |
| ⭐⭐⭐ | Archi | Ajouter un **command consumer MQTT** répondant aux topics `cmd/` | 6h |
| ⭐⭐⭐ | MCP | Exposer l'API comme **outil MCP** pour un agent LLM de monitoring | 8h |

---

*Tristan Vanrullen — La Plateforme, Marseille — 2026*
