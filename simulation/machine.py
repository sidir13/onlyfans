"""Simulateur de machine individuelle.

Cette classe encapsule l'état d'une machine, sa dynamique thermique
et la gestion des ventilateurs / pannes.

Elle ne connaît pas MQTT ni FastAPI : uniquement de la logique métier.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .physics import (
    compute_energy_kwh,
    compute_fan_auto_speed,
    compute_heat_input,
    compute_load_power,
    compute_thermal_step,
)


MachineStatus = Literal["on", "off", "degraded"]
FanMode = Literal["auto", "manual"]


@dataclass
class FanState:
    """État d'un ventilateur individuel."""

    rpm: int = 0
    mode: FanMode = "auto"


@dataclass
class ActiveFault:
    """Représente une panne injectée sur une machine."""

    fault_type: str
    remaining_s: float
    magnitude: float


@dataclass
class ThermalConfig:
    """Paramètres thermiques d'une machine.

    Ces champs sont extraits depuis la configuration YAML mergée.
    """

    idle_w: float
    max_w: float
    alpha: float
    heat_ratio: float
    tau_max_s: float
    k_cool: float
    c_th_j_per_c: float
    ambient_temp_c: float
    t_shutdown_c: float
    t_restart_c: float
    recovery_delay_s: float
    fan_gain_rpm_per_c: float
    fan_max_rpm: int
    fan_power_w: float
    tick_rate_hz: float


@dataclass
class SensorConfig:
    """Paramètres d'une sonde de température."""

    sensor_id: str
    bias_c: float = 0.0
    noise_std_c: float = 0.0
    drift_rate_c_per_s: float = 0.0


@dataclass
class SensorState:
    """État interne associé à une sonde (pour la dérive)."""

    config: SensorConfig
    drift_c: float = 0.0


class MachineSimulator:
    """Simulation d'une machine unique.

    La simulation est pilotée par :
    - un `ThermalConfig` (paramètres physiques)
    - une liste de `SensorConfig` pour les sondes
    - un nombre de ventilateurs.

    La méthode principale est : `tick(load_factor, dt)`.
    """

    def __init__(
        self,
        machine_id: str,
        role: str,
        thermal: ThermalConfig,
        sensor_configs: list[SensorConfig],
        fan_count: int,
    ) -> None:
        self.id = machine_id
        self.role = role
        self.thermal = thermal

        self.status: MachineStatus = "off"
        self.temperature_c: float = thermal.ambient_temp_c
        self.energy_kwh_cumulated: float = 0.0
        self._time_since_overheat_s: float = 0.0

        self.fans: list[FanState] = [FanState() for _ in range(fan_count)]
        self._sensors: list[SensorState] = [
            SensorState(config=sc) for sc in sensor_configs
        ]

        self.faults: list[ActiveFault] = []

    # ---------------------------------------------------------------------
    # API de commande
    # ---------------------------------------------------------------------
    def power_on(self) -> bool:
        """Tente d'allumer la machine.

        Retourne False si la température est encore trop élevée pour un
        redémarrage (hystérésis thermique).
        """

        if self.temperature_c > self.thermal.t_restart_c:
            return False
        self.status = "on"
        self._time_since_overheat_s = 0.0
        return True

    def power_off(self) -> None:
        """Éteint la machine (arrêt logique)."""

        self.status = "off"

    def set_fan_speed(self, fan_idx: int, rpm: int) -> None:
        """Fixe manuellement la vitesse d'un ventilateur.

        Place automatiquement le fan en mode "manual".
        """

        if not 0 <= fan_idx < len(self.fans):
            return
        rpm_clamped = max(0, min(self.thermal.fan_max_rpm, int(rpm)))
        fan = self.fans[fan_idx]
        fan.mode = "manual"
        fan.rpm = rpm_clamped

    def set_fan_mode(self, fan_idx: int, mode: FanMode) -> None:
        """Change le mode d'un ventilateur (auto / manual).

        En mode auto, la consigne rpm sera recalculée à chaque tick.
        """

        if not 0 <= fan_idx < len(self.fans):
            return
        self.fans[fan_idx].mode = mode

    def inject_fault(self, fault_type: str, duration_s: float, magnitude: float) -> None:
        """Ajoute une panne active.

        L'interprétation précise de `fault_type` et `magnitude` est laissée
        au `tick()`, qui applique les effets (ex: fan_failure, power_surge...).
        """

        self.faults.append(
            ActiveFault(
                fault_type=fault_type,
                remaining_s=max(0.0, duration_s),
                magnitude=magnitude,
            )
        )

    def cancel_fault(self) -> None:
        """Annule toutes les pannes actives."""

        self.faults.clear()

    # ---------------------------------------------------------------------
    # Boucle de simulation
    # ---------------------------------------------------------------------
    def tick(self, load_factor: float, dt: float) -> None:
        """Effectue un pas de simulation.

        - Met à jour la température interne selon le modèle thermique.
        - Applique les pannes actives.
        - Met à jour l'énergie cumulée.
        - Gère les transitions d'état (on/off/degraded).
        """

        # Mise à jour des durées restantes des pannes
        for fault in list(self.faults):
            fault.remaining_s -= dt
            if fault.remaining_s <= 0:
                self.faults.remove(fault)

        # Si la machine est éteinte, on ne simule que le refroidissement passif.
        if self.status == "off":
            self._integrate_thermal(load_factor=0.0, dt=dt)
            return

        # Machine en fonctionnement (on ou degraded)
        self._integrate_thermal(load_factor=load_factor, dt=dt)

        # Gestion de la surchauffe
        if self.temperature_c >= self.thermal.t_shutdown_c:
            # Protection thermique : passage en OFF
            self.status = "off"
            self._time_since_overheat_s = 0.0
            return

        # Gestion de l'état degraded en fonction de l'historique de surchauffe
        if self.temperature_c >= self.thermal.t_shutdown_c:
            self.status = "degraded"
            self._time_since_overheat_s = 0.0
        elif self.status == "degraded":
            self._time_since_overheat_s += dt
            if self._time_since_overheat_s >= self.thermal.recovery_delay_s:
                self.status = "on"
                self._time_since_overheat_s = 0.0

    # ------------------------------------------------------------------
    # Détails internes
    # ------------------------------------------------------------------
    def _integrate_thermal(self, load_factor: float, dt: float) -> None:
        """Met à jour température et énergie en tenant compte des fans/pannes."""

        # Vitesse des fans (auto vs manual)
        fan_rpms: list[int] = []
        for fan in self.fans:
            if fan.mode == "auto":
                fan.rpm = compute_fan_auto_speed(
                    t_current=self.temperature_c,
                    t_amb=self.thermal.ambient_temp_c,
                    gain_rpm_per_c=self.thermal.fan_gain_rpm_per_c,
                    f_max=self.thermal.fan_max_rpm,
                )
            fan_rpms.append(fan.rpm)

        fan_rpm_mean = float(sum(fan_rpms) / len(fan_rpms)) if fan_rpms else 0.0

        # Puissance électrique de base en fonction de la charge
        power_w = compute_load_power(
            load_factor=load_factor,
            idle_w=self.thermal.idle_w,
            max_w=self.thermal.max_w,
            alpha=self.thermal.alpha,
        )

        # Application de pannes de type power_surge (surconsommation)
        for fault in self.faults:
            if fault.fault_type == "power_surge":
                power_w *= 1.0 + fault.magnitude

        # Chaleur injectée
        q_in = compute_heat_input(power_w=power_w, heat_ratio=self.thermal.heat_ratio)

        # Constante de temps en fonction des fans
        tau = compute_thermal_step.__defaults__  # type: ignore[assignment]
        # On délègue le calcul de tau à compute_tau via physics, mais pour
        # éviter un import circulaire, celui-ci est appliqué au niveau cluster.
        # Ici on considère tau constant = tau_max_s.
        tau = self.thermal.tau_max_s  # type: ignore[assignment]

        # Intégration de la température
        self.temperature_c = compute_thermal_step(
            t_current=self.temperature_c,
            q_in=q_in,
            tau=tau,
            c_th=self.thermal.c_th_j_per_c,
            t_amb=self.thermal.ambient_temp_c,
            dt=dt,
        )

        # Mise à jour de l'énergie consommée
        delta_kwh = compute_energy_kwh(
            power_w=power_w,
            fan_count=len(self.fans),
            fan_power_w=self.thermal.fan_power_w,
            tick_rate_hz=self.thermal.tick_rate_hz,
        )
        self.energy_kwh_cumulated += delta_kwh

    # ------------------------------------------------------------------
    # Observation pour MQTT / API
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """Retourne un snapshot JSON-serialisable de la machine.

        Le format est volontairement générique, le mapping exact vers les
        topics MQTT est effectué par la couche publisher.
        """

        sensors_payload: list[dict] = []
        for sensor in self._sensors:
            sensors_payload.append(
                {
                    "sensor_id": sensor.config.sensor_id,
                    # La dérive et le bruit seront appliqués plus tard
                    # (Phase 3 lors de la génération des messages capteurs).
                    "temp_c": self.temperature_c + sensor.config.bias_c,
                }
            )

        fans_payload = [
            {"idx": idx, "rpm": fan.rpm, "mode": fan.mode}
            for idx, fan in enumerate(self.fans)
        ]

        faults_payload = [
            {
                "type": fault.fault_type,
                "remaining_s": max(0.0, fault.remaining_s),
                "magnitude": fault.magnitude,
            }
            for fault in self.faults
        ]

        return {
            "id": self.id,
            "role": self.role,
            "status": self.status,
            "temperature_c": self.temperature_c,
            "energy_kwh_cumulated": self.energy_kwh_cumulated,
            "fans": fans_payload,
            "sensors": sensors_payload,
            "faults": faults_payload,
        }
