"""Phase 2 — Enregistreur MQTT → Parquet.

S'abonne à ``dt/#`` et persiste la télémétrie et les événements dans des
fichiers Parquet partitionnés par épisode.

Usage ::

    python -m juste_ventilateurs.ingest.mqtt_recorder \\
           --duration 300 --output data/raw --seed 42

Variables d'environnement :
    MQTT_BROKER_HOST  (défaut: localhost)
    MQTT_BROKER_PORT  (défaut: 1883)

Structure du payload télémétrie attendu (topic ``dt/<cluster>/<machine>/telemetry``) :
    ts, status, energy_kwh_cumulated, sensors (list), fans (list), faults (list)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiomqtt
import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

_TOPIC_RE = re.compile(
    r"^dt/(?P<cluster>[^/]+)/(?P<machine>[^/]+)/(?P<kind>.+)$"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Collecteur ────────────────────────────────────────────────────────────────

class MqttRecorder:
    """Accumule les messages MQTT en mémoire puis les sauvegarde en Parquet."""

    def __init__(self, output_dir: Path, episode_id: str, seed: int) -> None:
        self._output_dir = output_dir
        self._episode_id = episode_id
        self._seed = seed
        self._tel_rows: list[dict] = []
        self._evt_rows: list[dict] = []

    # ── Parsing ──────────────────────────────────────────────────────────── #

    def _parse_telemetry(
        self, cluster_id: str, machine_id: str, data: dict
    ) -> dict:
        sensors = {
            s["sensor_id"]: s.get("temp_c")
            for s in data.get("sensors", [])
        }
        fans = data.get("fans", [])
        fan_rpms = [f.get("rpm", 0) for f in fans]
        return {
            "episode_id": self._episode_id,
            "seed": self._seed,
            "ts": data.get("ts", _now_iso()),
            "cluster_id": cluster_id,
            "machine_id": machine_id,
            "status": data.get("status"),
            # Températures par capteur
            "temperature_c": sensors.get("temp_cpu"),
            "temp_inlet_c": sensors.get("temp_inlet"),
            "temp_chassis_c": sensors.get("temp_chassis"),
            # Énergie (cumulée par la machine depuis le démarrage)
            "energy_kwh_cumulated": data.get("energy_kwh_cumulated"),
            # Ventilateurs
            "fan_rpm_avg": (
                sum(fan_rpms) / len(fan_rpms) if fan_rpms else None
            ),
            "fan_rpm_0": fan_rpms[0] if len(fan_rpms) > 0 else None,
            "fan_rpm_1": fan_rpms[1] if len(fan_rpms) > 1 else None,
            "fan_mode_0": fans[0].get("mode") if fans else None,
            # Pannes actives
            "faults_count": len(data.get("faults", [])),
        }

    def handle_message(self, topic: str, payload: bytes) -> None:
        m = _TOPIC_RE.match(topic)
        if not m:
            return

        cluster_id = m.group("cluster")
        machine_id = m.group("machine")
        kind = m.group("kind")

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return

        if kind == "telemetry":
            self._tel_rows.append(
                self._parse_telemetry(cluster_id, machine_id, data)
            )
        elif kind in ("fault", "status"):
            self._evt_rows.append(
                {
                    "episode_id": self._episode_id,
                    "seed": self._seed,
                    "ts": data.get("ts", _now_iso()),
                    "cluster_id": cluster_id,
                    "machine_id": machine_id,
                    "event_type": kind,
                    "payload": json.dumps(data),
                }
            )

    # ── Sauvegarde ───────────────────────────────────────────────────────── #

    def save(self) -> tuple[Path | None, Path | None]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        tel_path = evt_path = None

        if self._tel_rows:
            df = pd.DataFrame(self._tel_rows)
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            df = df.sort_values(["machine_id", "ts"]).reset_index(drop=True)
            tel_path = (
                self._output_dir / f"telemetry_{self._episode_id}.parquet"
            )
            df.to_parquet(tel_path, index=False)
            logger.info(
                "Télémétrie → %s  (%d lignes, %d machines)",
                tel_path,
                len(df),
                df["machine_id"].nunique(),
            )

        if self._evt_rows:
            df_e = pd.DataFrame(self._evt_rows)
            df_e["ts"] = pd.to_datetime(df_e["ts"], utc=True)
            df_e = df_e.sort_values("ts").reset_index(drop=True)
            evt_path = (
                self._output_dir / f"events_{self._episode_id}.parquet"
            )
            df_e.to_parquet(evt_path, index=False)
            logger.info("Événements → %s  (%d lignes)", evt_path, len(df_e))

        return tel_path, evt_path


# ── Boucle asyncio ────────────────────────────────────────────────────────────

async def record(
    duration_s: float,
    output_dir: Path,
    episode_id: str,
    seed: int,
    mqtt_host: str,
    mqtt_port: int,
) -> None:
    recorder = MqttRecorder(output_dir, episode_id, seed)
    logger.info(
        "Début de l'enregistrement — épisode=%s  durée=%.0fs  broker=%s:%s",
        episode_id,
        duration_s,
        mqtt_host,
        mqtt_port,
    )

    async with aiomqtt.Client(hostname=mqtt_host, port=mqtt_port) as client:
        await client.subscribe("dt/#")
        logger.info("Abonné à dt/#")

        async def _collect() -> None:
            async for message in client.messages:
                recorder.handle_message(str(message.topic), bytes(message.payload))

        try:
            await asyncio.wait_for(_collect(), timeout=duration_s)
        except asyncio.TimeoutError:
            pass  # Fin normale — durée écoulée

    recorder.save()
    logger.info("Enregistrement terminé.")


# ── Entrée CLI ────────────────────────────────────────────────────────────────

def main() -> None:
    # paho-mqtt utilise add_reader/add_writer — incompatible avec ProactorEventLoop
    # (défaut Windows Python 3.8+). On force SelectorEventLoop.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    parser = argparse.ArgumentParser(
        description="Enregistre la télémétrie MQTT en Parquet."
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=300.0,
        help="Durée d'enregistrement en secondes (défaut: 300)",
    )
    parser.add_argument(
        "--output",
        default="data/raw",
        help="Dossier de sortie Parquet",
    )
    parser.add_argument(
        "--episode",
        default=None,
        help="ID épisode (UUID court généré automatiquement si absent)",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    asyncio.run(
        record(
            duration_s=args.duration,
            output_dir=Path(args.output),
            episode_id=args.episode or str(uuid.uuid4())[:8],
            seed=args.seed,
            mqtt_host=os.environ.get("MQTT_BROKER_HOST", "localhost"),
            mqtt_port=int(os.environ.get("MQTT_BROKER_PORT", 1883)),
        )
    )


if __name__ == "__main__":
    main()
