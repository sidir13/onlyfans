"""Router /cluster — état global et commandes cluster.

Endpoints (Phase 4.2) :
  GET  /cluster/status          → snapshot complet du cluster
  GET  /cluster/energy          → métriques énergétiques
  POST /cluster/power           → allumer/éteindre toutes les machines
  PUT  /cluster/fan_speed       → vitesse homogène sur tous les fans
"""
from __future__ import annotations

from fastapi import APIRouter

from api import deps
from api.models import (
    ClusterFanSpeedCommand,
    ClusterMetricsResponse,
    ClusterPowerCommand,
    ClusterSnapshot,
    CommandResponse,
)

router = APIRouter()


@router.get("/status", response_model=ClusterSnapshot)
async def cluster_status() -> dict:
    """Retourne le snapshot complet du cluster."""
    return deps.get_cluster().get_snapshot()


@router.get("/energy", response_model=ClusterMetricsResponse)
async def cluster_energy() -> dict:
    """Retourne les métriques énergétiques agrégées."""
    simulator = deps.get_cluster()
    return {
        "energy_kwh_total": simulator.energy_kwh_total,
        "cost_eur_total": simulator.cost_eur_total,
        "pue_effective": simulator.pue_effective,
    }


@router.post("/power", response_model=CommandResponse)
async def cluster_power(cmd: ClusterPowerCommand) -> CommandResponse:
    """Allume ou éteint toutes les machines du cluster."""
    simulator = deps.get_cluster()
    results = []
    for machine in simulator.machines.values():
        if cmd.action == "on":
            ok = machine.power_on()
            results.append(f"{machine.id}={'ok' if ok else 'skip (T trop haute)'}") 
        else:
            machine.power_off()
            results.append(f"{machine.id}=off")
    return CommandResponse(ok=True, message=", ".join(results))


@router.put("/fan_speed", response_model=CommandResponse)
async def cluster_fan_speed(cmd: ClusterFanSpeedCommand) -> CommandResponse:
    """Applique la même vitesse à tous les fans de toutes les machines."""
    simulator = deps.get_cluster()
    for machine in simulator.machines.values():
        for idx in range(len(machine.fans)):
            machine.set_fan_speed(fan_idx=idx, rpm=cmd.rpm)
    return CommandResponse(
        ok=True,
        message=f"Tous les fans du cluster réglés à {cmd.rpm} RPM.",
    )
