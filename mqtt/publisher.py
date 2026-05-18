"""Publisher MQTT pour Jumeaux Chauds.

Publie les données de simulation sur un broker Mosquitto via aiomqtt v2.4.
Utilise le pattern de reconnexion automatique ``async for client in aiomqtt.Client(...)``
recommandé par aiomqtt pour les connexions longue durée.

Convention des topics (§ 6 des spécifications) :
    dt/{cluster}/{machine}/telemetry          QoS 0  (chaque cycle events_per_sec)
    dt/{cluster}/{machine}/temp/{sensor_id}   QoS 0
    dt/{cluster}/{machine}/power              QoS 0
    dt/{cluster}/{machine}/fan/{idx}          QoS 0  (sur changement seulement)
    dt/{cluster}/{machine}/status             QoS 1  (sur changement d'état)
    dt/{cluster}/{machine}/fault              QoS 1  (injection / recovery)
    dt/{cluster}/summary                      QoS 1  (toutes les 5 s)
    dt/{cluster}/metrics/energy               QoS 1  (toutes les 60 s)
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiomqtt

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class MqttPublisher:
    """Context manager asyncio pour la publication MQTT.

    Usage :
        async with MqttPublisher(mqtt_cfg) as pub:
            await pub.publish_telemetry(machine_snapshot)

    Parameters
    ----------
    mqtt_cfg :
        Bloc ``cluster.mqtt`` extrait de la config OmegaConf/dict.
    """

    def __init__(self, mqtt_cfg: Any) -> None:
        self._host: str = str(mqtt_cfg.get("broker_host", "mosquitto"))
        self._port: int = int(mqtt_cfg.get("broker_port", 1883))
        self._client_id: str = (
            f"{mqtt_cfg.get('client_id_prefix', 'twin')}-publisher"
        )
        self._topic_root: str = str(mqtt_cfg.get("topic_root", "dt"))
        self._qos_telemetry: int = int(mqtt_cfg.get("qos_telemetry", 0))
        self._qos_events: int = int(mqtt_cfg.get("qos_events", 1))

        # Client courant (assigné dans __aenter__ via la boucle de reconnexion)
        self._client: aiomqtt.Client | None = None
        self._connected = asyncio.Event()
        self._stop = asyncio.Event()
        self._reconnect_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "MqttPublisher":
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())
        # Attendre la première connexion (max 10 s)
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning(
                "MQTT broker %s:%s non disponible au démarrage — "
                "la publication sera ignorée jusqu'à la reconnexion.",
                self._host,
                self._port,
            )
        return self

    async def __aexit__(self, *_: Any) -> None:
        self._stop.set()
        if self._reconnect_task:
            self._reconnect_task.cancel()
            await asyncio.gather(self._reconnect_task, return_exceptions=True)

    async def _reconnect_loop(self) -> None:
        """Boucle de reconnexion automatique aiomqtt v2.x."""
        while not self._stop.is_set():
            try:
                async with aiomqtt.Client(
                    hostname=self._host,
                    port=self._port,
                    identifier=self._client_id,
                ) as client:
                    self._client = client
                    self._connected.set()
                    logger.info(
                        "MQTT connecté à %s:%s (id=%s)",
                        self._host,
                        self._port,
                        self._client_id,
                    )
                    # Attendre le signal d'arrêt
                    await self._stop.wait()
            except aiomqtt.MqttError as exc:
                self._connected.clear()
                self._client = None
                logger.warning("MQTT déconnecté (%s) — reconnexion dans 2 s", exc)
                await asyncio.sleep(2.0)

    # ------------------------------------------------------------------
    # Helpers internes
    # ------------------------------------------------------------------

    async def _publish(self, topic: str, payload: dict | str, qos: int = 0) -> None:
        """Publie un message JSON ; ignore silencieusement si non connecté."""
        if self._client is None:
            return
        try:
            if isinstance(payload, dict):
                data = json.dumps(payload, separators=(",", ":"))
            else:
                data = payload
            await self._client.publish(topic, data, qos=qos)
        except aiomqtt.MqttError as exc:
            logger.debug("Échec publication sur %s : %s", topic, exc)

    def _t(self, cluster_id: str, machine_id: str, *parts: str) -> str:
        """Construit un topic dt/{cluster}/{machine}/{parts...}."""
        return "/".join([self._topic_root, cluster_id, machine_id, *parts])

    def _tc(self, cluster_id: str, *parts: str) -> str:
        """Construit un topic dt/{cluster}/{parts...}."""
        return "/".join([self._topic_root, cluster_id, *parts])

    # ------------------------------------------------------------------
    # API publique — topics machine
    # ------------------------------------------------------------------

    async def publish_telemetry(self, snapshot: dict) -> None:
        """Publie le snapshot complet d'une machine (QoS 0).

        ``snapshot`` est le dict retourné par ``MachineSimulator.snapshot()``.
        """
        cluster_id = snapshot["cluster_id"]
        machine_id = snapshot["machine_id"]
        payload = {
            "schema_version": "1.0",
            "ts": _now_iso(),
            **snapshot,
        }
        await self._publish(
            self._t(cluster_id, machine_id, "telemetry"),
            payload,
            qos=self._qos_telemetry,
        )

        # Topics dérivés scalaires (QoS 0)
        for sensor_id, sensor_data in snapshot.get("temperatures", {}).items():
            await self._publish(
                self._t(cluster_id, machine_id, "temp", sensor_id),
                {"ts": payload["ts"], "value_c": sensor_data["value_c"]},
                qos=self._qos_telemetry,
            )

        await self._publish(
            self._t(cluster_id, machine_id, "power"),
            {
                "ts": payload["ts"],
                "power_w": snapshot.get("power_w"),
                "energy_kwh_cumulated": snapshot.get("energy_kwh_cumulated"),
            },
            qos=self._qos_telemetry,
        )

    async def publish_fan_state(
        self, cluster_id: str, machine_id: str, fans: list[dict]
    ) -> None:
        """Publie l'état de chaque ventilateur (QoS 0, sur changement)."""
        ts = _now_iso()
        for fan in fans:
            idx = fan.get("idx", 0)
            await self._publish(
                self._t(cluster_id, machine_id, "fan", str(idx)),
                {"ts": ts, **fan},
                qos=self._qos_telemetry,
            )

    async def publish_status(
        self, cluster_id: str, machine_id: str, status: str
    ) -> None:
        """Publie un changement d'état de machine (QoS 1)."""
        await self._publish(
            self._t(cluster_id, machine_id, "status"),
            {"ts": _now_iso(), "status": status},
            qos=self._qos_events,
        )

    async def publish_fault(
        self,
        cluster_id: str,
        machine_id: str,
        fault_data: dict,
        event: str = "injected",
    ) -> None:
        """Publie un événement de panne ou de recovery (QoS 1).

        Parameters
        ----------
        event : ``"injected"`` | ``"recovered"``
        """
        payload = {
            "ts": _now_iso(),
            "event": event,
            **fault_data,
        }
        await self._publish(
            self._t(cluster_id, machine_id, "fault"),
            payload,
            qos=self._qos_events,
        )

    # ------------------------------------------------------------------
    # API publique — topics cluster
    # ------------------------------------------------------------------

    async def publish_summary(self, cluster_snapshot: dict) -> None:
        """Publie un résumé KPI du cluster (QoS 1, toutes les 5 s)."""
        cluster_id = cluster_snapshot["cluster_id"]
        machines = cluster_snapshot.get("machines", {})
        machines_on = sum(
            1 for m in machines.values() if m.get("status") == "on"
        )
        t_max = max(
            (
                max(
                    (s["value_c"] for s in m.get("temperatures", {}).values()),
                    default=0.0,
                )
                for m in machines.values()
            ),
            default=0.0,
        )
        power_total = sum(m.get("power_w", 0.0) for m in machines.values())
        payload = {
            "ts": _now_iso(),
            "cluster_id": cluster_id,
            "machines_total": len(machines),
            "machines_on": machines_on,
            "t_max_c": round(t_max, 2),
            "power_total_w": round(power_total, 2),
        }
        await self._publish(
            self._tc(cluster_id, "summary"),
            payload,
            qos=self._qos_events,
        )

    async def publish_energy(
        self, cluster_id: str, energy_metrics: dict
    ) -> None:
        """Publie les métriques énergétiques du cluster (QoS 1, toutes les 60 s)."""
        payload = {
            "ts": _now_iso(),
            "cluster_id": cluster_id,
            **energy_metrics,
        }
        await self._publish(
            self._tc(cluster_id, "metrics", "energy"),
            payload,
            qos=self._qos_events,
        )
