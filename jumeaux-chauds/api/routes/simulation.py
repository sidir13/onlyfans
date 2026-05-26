"""Router /simulation — contrôle du simulateur depuis l'API.

Endpoints (Phase 4.4) :
  POST   /simulation/fault                → injecte une panne sur une machine
  DELETE /simulation/fault/{machine_id}   → annule toutes les pannes d'une machine
  PUT    /simulation/scenario             → change le scénario de charge à chaud
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api import deps
from api.models import CommandResponse, FaultInjectCommand, ScenarioChangeCommand

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/fault", response_model=CommandResponse)
async def inject_fault(cmd: FaultInjectCommand) -> CommandResponse:
    """Injecte une panne sur une machine."""
    simulator = deps.get_cluster()
    machine = simulator.machines.get(cmd.machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail=f"Machine '{cmd.machine_id}' inconnue.")
    machine.inject_fault(
        fault_type=cmd.fault_type,
        duration_s=cmd.duration_s,
        magnitude=cmd.magnitude,
    )
    return CommandResponse(
        ok=True,
        message=(
            f"Panne '{cmd.fault_type}' injectée sur '{cmd.machine_id}' "
            f"(durée={cmd.duration_s}s, magnitude={cmd.magnitude})."
        ),
    )


@router.delete("/fault/{machine_id}", response_model=CommandResponse)
async def cancel_fault(machine_id: str) -> CommandResponse:
    """Annule toutes les pannes actives d'une machine."""
    simulator = deps.get_cluster()
    machine = simulator.machines.get(machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail=f"Machine '{machine_id}' inconnue.")
    machine.cancel_fault()
    return CommandResponse(ok=True, message=f"Pannes annulées sur '{machine_id}'.")


@router.put("/scenario", response_model=CommandResponse)
async def change_scenario(cmd: ScenarioChangeCommand) -> CommandResponse:
    """Change le scénario de charge à chaud.

    Recharge la config depuis le YAML correspondant et reconstruit
    le ScenarioEngine du simulateur sans redémarrer la boucle.
    """
    from config.loader import load_config
    from simulation.scenarios import LoadProfileConfig, ScenarioEngine

    try:
        new_cfg = load_config(scenario=cmd.scenario)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Scénario '{cmd.scenario}' invalide ou introuvable : {exc}",
        ) from exc

    simulator = deps.get_cluster()
    lp = new_cfg["simulation"]["load_profile"]
    lp_cfg = LoadProfileConfig(
        type=lp["type"],
        params={k: v for k, v in lp.items() if k != "type"},
    )
    simulator._scenario_engine = ScenarioEngine(profile_cfg=lp_cfg)
    logger.info("Scénario changé → '%s'", cmd.scenario)

    return CommandResponse(
        ok=True,
        message=f"Scénario changé vers '{cmd.scenario}' (profil: {lp['type']}).",
    )
