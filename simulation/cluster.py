"""Orchestrateur de cluster de machines.

Ce module fournit `ClusterSimulator`, responsable de :
- instancier les `MachineSimulator` à partir de la config mergée,
- orchestrer la boucle de simulation (ticks),
- calculer les métriques agrégées (énergie, coût, PUE effectif),
- exposer un snapshot consolidé pour MQTT / WebSocket / API.

La connexion à MQTT et au WebSocket manager sera câblée en Phase 3–4.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from config.loader import get_machine_config
from .machine import MachineSimulator, SensorConfig, ThermalConfig
from .physics import compute_cost
from .scenarios import FaultConfig, FaultScheduler, LoadProfileConfig, ScenarioEngine


@dataclass
class ClusterMetrics:
    """Métriques agrégées du cluster."""

    energy_kwh_total: float
    cost_eur_total: float
    pue_effective: float


class ClusterSimulator:
    """Orchestrateur de N machines simulées."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._cfg = config
        self.cluster_id: str = config["cluster"]["id"]
        self._tick_rate_hz: float = float(config["simulation"]["tick_rate_hz"])

        # PUE et coût
        self._pue: float = float(config["cluster"].get("pue", 1.4))
        self._price_eur_kwh: float = float(
            config["cluster"].get("electricity_price_eur_kwh", 0.2)
        )

        # Construction des machines
        self.machines: dict[str, MachineSimulator] = {}
        self._build_machines()

        # Scénario de charge (global pour le cluster)
        lp_cfg = LoadProfileConfig(
            type=config["simulation"]["load_profile"]["type"],
            params={
                k: v
                for k, v in config["simulation"]["load_profile"].items()
                if k != "type"
            },
        )
        self._scenario_engine = ScenarioEngine(profile_cfg=lp_cfg)

        # Scheduler de pannes
        fault_cfgs: list[FaultConfig] = []
        fault_section = config["simulation"].get("fault_injection", {})
        for raw in fault_section.get("faults", []):
            fault_cfgs.append(
                FaultConfig(
                    type=raw["type"],
                    distribution=raw["distribution"],
                    shape=raw.get("shape"),
                    scale_s=raw.get("scale_s"),
                    probability_per_tick=raw.get("probability_per_tick"),
                    magnitude=raw.get("magnitude", 1.0),
                )
            )

        self._fault_scheduler = FaultScheduler(
            fault_configs=fault_cfgs,
            recovery_delay_s=float(fault_section.get("recovery_delay_s", 60.0)),
        )

        # Temps et métriques agrégées
        self._running = False
        self._t_elapsed_s: float = 0.0
        self.energy_kwh_total: float = 0.0
        self.cost_eur_total: float = 0.0
        self.pue_effective: float = self._pue

    # ------------------------------------------------------------------
    # Construction des machines
    # ------------------------------------------------------------------
    def _build_machines(self) -> None:
        """Instancie les MachineSimulator à partir des role_profiles.

        Utilise get_machine_config() pour merger le profil de rôle avec
        les surcharges individuelles de chaque machine, conformément à la
        structure de base.yaml (cluster.role_profiles.{role}.thermal / .fans).
        """
        cluster_cfg = self._cfg["cluster"]
        tick_rate_hz = float(self._cfg["simulation"]["tick_rate_hz"])

        for m_entry in cluster_cfg["machines"]:
            machine_id = m_entry["id"]
            role = m_entry.get("role", "worker")

            # Merge role_profile + surcharges individuelles
            m_cfg = get_machine_config(self._cfg, machine_id)

            th = m_cfg["thermal"]
            fans = m_cfg["fans"]
            power = m_cfg["power"]

            thermal_cfg = ThermalConfig(
                idle_w=float(power["idle_watts"]),
                max_w=float(power["max_watts"]),
                alpha=float(th.get("alpha_load_exponent", 1.5)),
                heat_ratio=float(power.get("heat_ratio", 0.9)),
                tau_max_s=float(th["tau_max_s"]),
                k_cool=float(th["k_cool_rpm_factor"]),
                c_th_j_per_c=float(th["thermal_capacity_j_per_c"]),
                ambient_temp_c=float(th["ambient_temp_c"]),
                t_shutdown_c=float(th["t_shutdown_c"]),
                t_restart_c=float(th["t_restart_c"]),
                recovery_delay_s=float(th.get("recovery_delay_s", 60.0)),
                fan_gain_rpm_per_c=float(fans["auto_policy"]["gain_rpm_per_c"]),
                fan_max_rpm=int(fans["max_rpm"]),
                fan_power_w=float(fans["power_per_fan_w"]),
                tick_rate_hz=tick_rate_hz,
            )

            sensor_configs: list[SensorConfig] = []
            for s_cfg in m_cfg.get("temperature_sensors", []):
                sensor_configs.append(
                    SensorConfig(
                        sensor_id=s_cfg["id"],
                        bias_c=float(s_cfg.get("bias_c", 0.0)),
                        noise_std_c=float(s_cfg.get("noise_std_c", 0.0)),
                        drift_rate_c_per_s=float(s_cfg.get("drift_rate_c_per_s", 0.0)),
                    )
                )

            fan_count = int(fans.get("count", 2))

            machine = MachineSimulator(
                machine_id=machine_id,
                role=role,
                thermal=thermal_cfg,
                sensor_configs=sensor_configs,
                fan_count=fan_count,
            )
            self.machines[machine_id] = machine

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------
    async def run(self) -> None:  # pragma: no cover - testé via intégration
        """Boucle de simulation principale.

        Cette méthode est pensée pour être lancée dans un task asyncio
        par FastAPI (lifespan). La publication MQTT et le broadcast WS
        seront branchés en Phase 3–4.
        """

        self._running = True
        dt = 1.0 / self._tick_rate_hz

        while self._running:
            await asyncio.sleep(dt)
            self._t_elapsed_s += dt

            # Charge globale fournie par le scénario
            load_factor = self._scenario_engine.get_load_factor(self._t_elapsed_s)

            # Tick de chaque machine
            for machine in self.machines.values():
                machine.tick(load_factor=load_factor, dt=dt)

            # Planification de pannes
            self._fault_scheduler.tick(self.machines, dt=dt)

            # Mise à jour des métriques agrégées
            self._update_metrics()

    def stop(self) -> None:
        """Demande l'arrêt de la boucle de simulation."""

        self._running = False

    # ------------------------------------------------------------------
    # Métriques & snapshot
    # ------------------------------------------------------------------
    def _update_metrics(self) -> None:
        self.energy_kwh_total = sum(
            m.energy_kwh_cumulated for m in self.machines.values()
        )
        self.cost_eur_total = compute_cost(
            energy_kwh=self.energy_kwh_total,
            pue=self._pue,
            price_eur_kwh=self._price_eur_kwh,
        )
        self.pue_effective = self._pue

    def get_snapshot(self) -> dict:
        """Retourne un snapshot consolidé du cluster."""

        return {
            "cluster_id": self.cluster_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "energy_kwh_total": self.energy_kwh_total,
                "cost_eur_total": self.cost_eur_total,
                "pue_effective": self.pue_effective,
            },
            "machines": {mid: m.snapshot() for mid, m in self.machines.items()},
        }
