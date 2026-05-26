"""Profils de charge et planification des pannes.

Ce module fournit :
- `ScenarioEngine` : génère un facteur de charge en fonction du temps.
- `FaultScheduler` : déclenche des pannes sur les machines selon des distributions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .machine import MachineSimulator
from .noise import exponential_event, uniform_event, weibull_event


@dataclass
class LoadProfileConfig:
    """Configuration d'un profil de charge."""

    type: str
    params: dict[str, Any]


class ScenarioEngine:
    """Moteur de scénarios de charge.

    Les paramètres proviennent du YAML (`config/scenarios/*.yaml`).
    """

    def __init__(self, profile_cfg: LoadProfileConfig) -> None:
        self.profile_cfg = profile_cfg

    def get_load_factor(self, t_elapsed_s: float) -> float:
        """Retourne un facteur de charge dans [0, 1] pour un temps donné."""

        t = max(0.0, float(t_elapsed_s))
        ptype = self.profile_cfg.type
        params = self.profile_cfg.params

        if ptype == "sine_wave":
            return self._sine_wave(t, **params)
        if ptype == "ramp_with_spikes":
            return self._ramp_with_spikes(t, **params)
        if ptype == "constant":
            return float(params.get("value", 0.0))
        if ptype == "step":
            return self._step(t, **params)

        # Profil inconnu → charge nulle (comportement sûr)
        return 0.0

    # ------------------------------------------------------------------
    # Profils concrets
    # ------------------------------------------------------------------
    @staticmethod
    def _sine_wave(
        t: float,
        base_load: float,
        amplitude: float,
        period_s: float,
    ) -> float:
        if period_s <= 0:
            return max(0.0, min(1.0, base_load))
        omega = 2.0 * np.pi / period_s
        value = base_load + amplitude * np.sin(omega * t)
        return float(max(0.0, min(1.0, value)))

    @staticmethod
    def _ramp_with_spikes(
        t: float,
        ramp_start: float = 0.20,
        ramp_end: float = 0.95,
        ramp_duration_s: float = 600.0,
        spike_probability: float = 0.02,
        spike_duration_s: float = 30.0,
        spike_magnitude: float = 0.30,
        # alias legacy (anciens noms internes — ignorés silencieusement)
        ramp_start_s: float | None = None,
        ramp_end_s: float | None = None,
        spike_rate_hz: float | None = None,
        base_load: float | None = None,
        max_load: float | None = None,
    ) -> float:
        """Profil de charge : rampe linéaire de `ramp_start` à `ramp_end`
        sur `ramp_duration_s` secondes, avec des spikes stochastiques.

        Noms des paramètres alignés sur ``config/scenarios/stress.yaml``.
        """
        # Rampe linéaire
        if ramp_duration_s <= 0:
            load = ramp_end
        elif t >= ramp_duration_s:
            load = ramp_end
        else:
            alpha = t / ramp_duration_s
            load = ramp_start + alpha * (ramp_end - ramp_start)

        # Spikes de Poisson discrets (à chaque appel ≈ events_per_sec)
        if spike_probability > 0 and np.random.random() < spike_probability:
            load += spike_magnitude

        return float(max(0.0, min(1.0, load)))

    @staticmethod
    def _step(
        t: float,
        t_switch_s: float,
        low_load: float = 0.1,
        high_load: float = 0.9,
    ) -> float:
        if t < t_switch_s:
            return float(max(0.0, min(1.0, low_load)))
        return float(max(0.0, min(1.0, high_load)))


@dataclass
class FaultConfig:
    """Configuration d'un type de panne."""

    type: str
    distribution: str
    shape: float | None = None
    scale_s: float | None = None
    probability_per_tick: float | None = None
    magnitude: float = 1.0


class FaultScheduler:
    """Planificateur de pannes pour un cluster de machines.

    Il est paramétré par une liste de `FaultConfig` issue du YAML.
    """

    def __init__(
        self,
        fault_configs: list[FaultConfig],
        recovery_delay_s: float,
    ) -> None:
        self._fault_configs = fault_configs
        self._recovery_delay_s = recovery_delay_s
        # Temps écoulé pour les distributions dépendant de t (Weibull)
        self._elapsed_by_machine: dict[str, float] = {}

    def tick(self, machines: dict[str, MachineSimulator], dt: float) -> None:
        """Evalue les déclenchements potentiels de pannes.

        Pour chaque machine et chaque configuration de panne, tire
        un événement et, le cas échéant, appelle `inject_fault()`.
        """

        if dt <= 0:
            return

        for machine_id, machine in machines.items():
            elapsed = self._elapsed_by_machine.get(machine_id, 0.0)
            elapsed += dt
            self._elapsed_by_machine[machine_id] = elapsed

            for cfg in self._fault_configs:
                if cfg.distribution == "weibull":
                    if cfg.shape is None or cfg.scale_s is None:
                        continue
                    fired = weibull_event(
                        shape=cfg.shape,
                        scale_s=cfg.scale_s,
                        elapsed_s=elapsed,
                        dt=dt,
                    )
                elif cfg.distribution == "exponential":
                    if cfg.scale_s is None:
                        continue
                    fired = exponential_event(scale_s=cfg.scale_s, dt=dt)
                elif cfg.distribution == "uniform":
                    if cfg.probability_per_tick is None:
                        continue
                    fired = uniform_event(cfg.probability_per_tick)
                else:
                    fired = False

                if fired:
                    machine.inject_fault(
                        fault_type=cfg.type,
                        duration_s=self._recovery_delay_s,
                        magnitude=cfg.magnitude,
                    )
