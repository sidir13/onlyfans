"""Schémas Pydantic v2 pour les requêtes et réponses de l'API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Modèles de réponse — snapshot
# ---------------------------------------------------------------------------

class FanResponse(BaseModel):
    idx: int
    rpm: int
    mode: Literal["auto", "manual"]


class SensorResponse(BaseModel):
    sensor_id: str
    temp_c: float


class FaultResponse(BaseModel):
    type: str
    remaining_s: float
    magnitude: float


class MachineSnapshot(BaseModel):
    id: str
    role: str
    status: Literal["on", "off", "degraded"]
    temperature_c: float
    energy_kwh_cumulated: float
    fans: list[FanResponse]
    sensors: list[SensorResponse]
    faults: list[FaultResponse]


class ClusterMetricsResponse(BaseModel):
    energy_kwh_total: float
    cost_eur_total: float
    pue_effective: float


class ClusterSnapshot(BaseModel):
    cluster_id: str
    ts: str
    metrics: ClusterMetricsResponse
    machines: dict[str, MachineSnapshot]


# ---------------------------------------------------------------------------
# Modèles de commande — machines
# ---------------------------------------------------------------------------

class PowerCommand(BaseModel):
    action: Literal["on", "off"] = Field(
        ..., description="'on' pour allumer, 'off' pour éteindre."
    )


class FanSpeedCommand(BaseModel):
    fan_idx: int = Field(..., ge=0, description="Index du ventilateur (0-based).")
    rpm: int = Field(..., ge=0, description="Vitesse cible en RPM.")


class FanModeCommand(BaseModel):
    fan_idx: int = Field(..., ge=0, description="Index du ventilateur (0-based).")
    mode: Literal["auto", "manual"]


# ---------------------------------------------------------------------------
# Modèles de commande — cluster
# ---------------------------------------------------------------------------

class ClusterPowerCommand(BaseModel):
    action: Literal["on", "off"]


class ClusterFanSpeedCommand(BaseModel):
    rpm: int = Field(..., ge=0, description="Vitesse appliquée à tous les fans de toutes les machines.")


# ---------------------------------------------------------------------------
# Modèles de commande — simulation
# ---------------------------------------------------------------------------

class FaultInjectCommand(BaseModel):
    machine_id: str
    fault_type: str = Field(..., description="Ex: 'fan_failure', 'power_surge'.")
    duration_s: float = Field(default=30.0, gt=0)
    magnitude: float = Field(default=1.0, ge=0)


class ScenarioChangeCommand(BaseModel):
    scenario: str = Field(
        ..., description="Nom du scénario YAML à charger (ex: 'nominal', 'stress')."
    )


# ---------------------------------------------------------------------------
# Réponses génériques
# ---------------------------------------------------------------------------

class CommandResponse(BaseModel):
    ok: bool
    message: str
