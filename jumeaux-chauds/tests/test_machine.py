"""Tests de la MachineSimulator.

Ces tests couvrent les principaux comportements de la machine :
- dynamique thermique basique,
- transitions d'état on/off/degraded,
- commandes de fans,
- injection de pannes.
"""
from __future__ import annotations

from typing import Literal

import numpy as np

from simulation.machine import (
    MachineSimulator,
    SensorConfig,
    ThermalConfig,
)


def _make_default_thermal() -> ThermalConfig:
    return ThermalConfig(
        idle_w=100.0,
        max_w=400.0,
        alpha=1.5,
        heat_ratio=0.9,
        tau_max_s=300.0,
        k_cool=0.5,
        c_th_j_per_c=5_000.0,
        ambient_temp_c=25.0,
        t_shutdown_c=80.0,
        t_restart_c=50.0,
        recovery_delay_s=30.0,
        fan_gain_rpm_per_c=200.0,
        fan_max_rpm=5_000,
        fan_power_w=5.0,
        tick_rate_hz=10.0,
    )


def test_power_on_fails_when_too_hot() -> None:
    thermal = _make_default_thermal()
    machine = MachineSimulator(
        machine_id="srv-01",
        role="worker",
        thermal=thermal,
        sensor_configs=[],
        fan_count=2,
    )
    machine.temperature_c = 60.0  # > t_restart_c
    assert machine.power_on() is False


def test_power_on_succeeds_when_cool_enough() -> None:
    thermal = _make_default_thermal()
    machine = MachineSimulator(
        machine_id="srv-01",
        role="worker",
        thermal=thermal,
        sensor_configs=[],
        fan_count=2,
    )
    machine.temperature_c = 40.0
    assert machine.power_on() is True
    assert machine.status == "on"


def test_overheat_switches_machine_off() -> None:
    thermal = _make_default_thermal()
    machine = MachineSimulator(
        machine_id="srv-01",
        role="worker",
        thermal=thermal,
        sensor_configs=[],
        fan_count=2,
    )
    assert machine.power_on() is True
    # Force une température au-dessus du seuil de shutdown
    machine.temperature_c = thermal.t_shutdown_c + 1.0
    machine.tick(load_factor=1.0, dt=0.1)
    assert machine.status == "off"


def test_set_fan_speed_manual_mode() -> None:
    thermal = _make_default_thermal()
    machine = MachineSimulator(
        machine_id="srv-01",
        role="worker",
        thermal=thermal,
        sensor_configs=[],
        fan_count=1,
    )
    machine.set_fan_speed(0, 8_000)  # au-dessus de max → clamp
    assert machine.fans[0].rpm == thermal.fan_max_rpm
    assert machine.fans[0].mode == "manual"


def test_snapshot_contains_expected_keys() -> None:
    thermal = _make_default_thermal()
    sensor_cfg = [SensorConfig(sensor_id="temp_cpu", bias_c=1.0)]
    machine = MachineSimulator(
        machine_id="srv-01",
        role="worker",
        thermal=thermal,
        sensor_configs=sensor_cfg,
        fan_count=1,
    )

    snap = machine.snapshot()
    assert snap["id"] == "srv-01"
    assert snap["role"] == "worker"
    assert "status" in snap
    assert "temperature_c" in snap
    assert "energy_kwh_cumulated" in snap
    assert isinstance(snap["fans"], list)
    assert isinstance(snap["sensors"], list)


def test_energy_increases_with_ticks() -> None:
    thermal = _make_default_thermal()
    machine = MachineSimulator(
        machine_id="srv-01",
        role="worker",
        thermal=thermal,
        sensor_configs=[],
        fan_count=2,
    )
    assert machine.power_on() is True
    e0 = machine.energy_kwh_cumulated
    for _ in range(20):
        machine.tick(load_factor=0.8, dt=0.1)
    assert machine.energy_kwh_cumulated > e0


def test_fault_injection_adds_fault() -> None:
    thermal = _make_default_thermal()
    machine = MachineSimulator(
        machine_id="srv-01",
        role="worker",
        thermal=thermal,
        sensor_configs=[],
        fan_count=2,
    )

    assert machine.faults == []
    machine.inject_fault("power_surge", duration_s=10.0, magnitude=0.5)
    assert len(machine.faults) == 1
    assert machine.faults[0].fault_type == "power_surge"


def test_faults_expire_over_time() -> None:
    thermal = _make_default_thermal()
    machine = MachineSimulator(
        machine_id="srv-01",
        role="worker",
        thermal=thermal,
        sensor_configs=[],
        fan_count=2,
    )
    machine.inject_fault("power_surge", duration_s=0.2, magnitude=0.5)
    # On laisse le temps s'écouler suffisamment
    for _ in range(10):
        machine.tick(load_factor=0.5, dt=0.05)
    assert machine.faults == []
