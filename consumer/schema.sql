-- ── Schéma TimescaleDB — Jumeaux Chauds ──────────────────────────────
-- Exécuté automatiquement au premier démarrage du conteneur timescaledb
-- via le montage dans /docker-entrypoint-initdb.d/

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ── Table de télémétrie principale ────────────────────────────────────
CREATE TABLE IF NOT EXISTS telemetry (
    ts              TIMESTAMPTZ     NOT NULL,
    cluster_id      TEXT            NOT NULL,
    machine_id      TEXT            NOT NULL,
    status          TEXT,
    temperature_c   DOUBLE PRECISION,
    power_w         DOUBLE PRECISION,
    energy_kwh      DOUBLE PRECISION,
    load_factor     DOUBLE PRECISION,
    fan_rpm_avg     DOUBLE PRECISION
);

SELECT create_hypertable(
    'telemetry',
    'ts',
    if_not_exists => TRUE
);

-- Index composite pour les requêtes par machine dans une fenêtre de temps
CREATE INDEX IF NOT EXISTS idx_telemetry_machine_ts
    ON telemetry (machine_id, ts DESC);

-- ── Table des événements (pannes, changements de statut) ───────────────
CREATE TABLE IF NOT EXISTS events (
    ts              TIMESTAMPTZ     NOT NULL,
    cluster_id      TEXT            NOT NULL,
    machine_id      TEXT            NOT NULL,
    event_type      TEXT            NOT NULL,   -- 'fault' | 'status_change'
    payload         JSONB
);

SELECT create_hypertable(
    'events',
    'ts',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_events_machine_ts
    ON events (machine_id, ts DESC);

-- ── Vue agrégée : température max par minute et par machine ───────────
CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_1min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', ts)    AS bucket,
    cluster_id,
    machine_id,
    AVG(temperature_c)             AS temp_avg_c,
    MAX(temperature_c)             AS temp_max_c,
    AVG(power_w)                   AS power_avg_w,
    MAX(power_w)                   AS power_max_w,
    AVG(load_factor)               AS load_avg,
    LAST(status, ts)               AS status_last
FROM telemetry
GROUP BY bucket, cluster_id, machine_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'telemetry_1min',
    start_offset => INTERVAL '10 minutes',
    end_offset   => INTERVAL '30 seconds',
    schedule_interval => INTERVAL '30 seconds',
    if_not_exists => TRUE
);

-- Rétention : supprimer les données brutes après 7 jours
SELECT add_retention_policy(
    'telemetry',
    INTERVAL '7 days',
    if_not_exists => TRUE
);
