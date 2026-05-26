"""Router /machines — commandes sur une machine individuelle.

Endpoints (Phase 4.2) :
  GET  /machines/{machine_id}                  → snapshot machine
  POST /machines/{machine_id}/power             → power on/off
  PUT  /machines/{machine_id}/fan_speed         → vitesse manuelle d'un fan
  PUT  /machines/{machine_id}/fan_mode          → mode auto/manual d'un fan
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api import deps
from api.models import (
    CommandResponse,
    FanModeCommand,
    FanSpeedCommand,
    MachineSnapshot,
    PowerCommand,
)

router = APIRouter()


def _get_machine(machine_id: str):
    """Helper : retourne la machine ou lève 404."""
    simulator = deps.get_cluster()
    machine = simulator.machines.get(machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail=f"Machine '{machine_id}' inconnue.")
    return machine


@router.get("/{machine_id}", response_model=MachineSnapshot)
async def get_machine(machine_id: str) -> dict:
    """Retourne le snapshot courant d'une machine."""
    return _get_machine(machine_id).snapshot()


@router.post("/{machine_id}/power", response_model=CommandResponse)
async def power_machine(machine_id: str, cmd: PowerCommand) -> CommandResponse:
    """Allume ou éteint une machine.

    - **action=on** : échoue avec 409 si T > t_restart_c.
    - **action=off** : toujours accepté.
    """
    machine = _get_machine(machine_id)
    if cmd.action == "on":
        success = machine.power_on()
        if not success:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Impossible d'allumer '{machine_id}' : température trop élevée "
                    f"({machine.temperature_c:.1f}°C > {machine.thermal.t_restart_c}°C)."
                ),
            )
        return CommandResponse(ok=True, message=f"Machine '{machine_id}' allumée.")
    else:
        machine.power_off()
        return CommandResponse(ok=True, message=f"Machine '{machine_id}' éteinte.")


@router.put("/{machine_id}/fan_speed", response_model=CommandResponse)
async def set_fan_speed(machine_id: str, cmd: FanSpeedCommand) -> CommandResponse:
    """Fixe manuellement la vitesse d'un ventilateur."""
    machine = _get_machine(machine_id)
    machine.set_fan_speed(fan_idx=cmd.fan_idx, rpm=cmd.rpm)
    return CommandResponse(
        ok=True,
        message=f"Fan {cmd.fan_idx} de '{machine_id}' réglé à {cmd.rpm} RPM (mode manual).",
    )


@router.put("/{machine_id}/fan_mode", response_model=CommandResponse)
async def set_fan_mode(machine_id: str, cmd: FanModeCommand) -> CommandResponse:
    """Change le mode d'un ventilateur (auto / manual)."""
    machine = _get_machine(machine_id)
    machine.set_fan_mode(fan_idx=cmd.fan_idx, mode=cmd.mode)
    return CommandResponse(
        ok=True,
        message=f"Fan {cmd.fan_idx} de '{machine_id}' passé en mode '{cmd.mode}'.",
    )
