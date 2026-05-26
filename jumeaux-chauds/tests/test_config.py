"""Tests du système de configuration YAML hiérarchique."""
from __future__ import annotations

from pathlib import Path

import pytest

from config.loader import get_machine_config, load_config
from simulation.duration import parse_duration

_CONFIG_DIR = Path(__file__).parent.parent / "config"


class TestLoadConfig:
    def test_nominal_loads_without_error(self):
        cfg = load_config(scenario="nominal", config_dir=_CONFIG_DIR)
        assert cfg is not None
        assert cfg.cluster.id == "cluster_alpha"

    def test_stress_loads_without_error(self):
        cfg = load_config(scenario="stress", config_dir=_CONFIG_DIR)
        assert cfg.simulation.mode == "stress"

    def test_merge_scenario_overrides_base(self):
        """Le scénario stress doit activer la fault_injection."""
        nominal = load_config(scenario="nominal", config_dir=_CONFIG_DIR)
        stress = load_config(scenario="stress", config_dir=_CONFIG_DIR)
        assert nominal.simulation.fault_injection.enabled is False
        assert stress.simulation.fault_injection.enabled is True

    def test_merge_preserves_base_keys(self):
        """Les clés non mentionnées dans le scénario restent du base."""
        cfg = load_config(scenario="stress", config_dir=_CONFIG_DIR)
        assert cfg.cluster.electricity_price_eur_kwh == pytest.approx(0.20)
        assert cfg.cluster.pue == pytest.approx(1.40)

    def test_programmatic_overrides(self):
        """Les overrides programmatiques prennent le dessus."""
        cfg = load_config(
            scenario="nominal",
            config_dir=_CONFIG_DIR,
            overrides={"cluster": {"id": "test_cluster"}},
        )
        assert cfg.cluster.id == "test_cluster"

    def test_unknown_scenario_raises(self):
        with pytest.raises(FileNotFoundError, match="Scénario introuvable"):
            load_config(scenario="inexistant", config_dir=_CONFIG_DIR)

    def test_cluster_has_five_machines(self):
        cfg = load_config(scenario="nominal", config_dir=_CONFIG_DIR)
        assert len(cfg.cluster.machines) == 5


class TestGetMachineConfig:
    def test_master_role_profile_applied(self):
        cfg = load_config(scenario="nominal", config_dir=_CONFIG_DIR)
        m_cfg = get_machine_config(cfg, "srv-master-01")
        assert m_cfg.thermal.t_shutdown_c == pytest.approx(90.0)
        assert m_cfg.power.idle_watts == pytest.approx(200.0)

    def test_individual_override_on_srv_master_02(self):
        """srv-master-02 a t_shutdown_c=92.0 en surcharge individuelle."""
        cfg = load_config(scenario="nominal", config_dir=_CONFIG_DIR)
        m_cfg = get_machine_config(cfg, "srv-master-02")
        assert m_cfg.thermal.t_shutdown_c == pytest.approx(92.0)

    def test_worker_role_profile_applied(self):
        cfg = load_config(scenario="nominal", config_dir=_CONFIG_DIR)
        m_cfg = get_machine_config(cfg, "srv-worker-01")
        assert m_cfg.thermal.t_shutdown_c == pytest.approx(88.0)
        assert m_cfg.power.idle_watts == pytest.approx(100.0)

    def test_unknown_machine_raises(self):
        cfg = load_config(scenario="nominal", config_dir=_CONFIG_DIR)
        with pytest.raises(KeyError, match="introuvable"):
            get_machine_config(cfg, "srv-inexistant")

    def test_master_has_three_temp_sensors(self):
        cfg = load_config(scenario="nominal", config_dir=_CONFIG_DIR)
        m_cfg = get_machine_config(cfg, "srv-master-01")
        assert len(m_cfg.temperature_sensors) == 3

    def test_worker_has_two_temp_sensors(self):
        cfg = load_config(scenario="nominal", config_dir=_CONFIG_DIR)
        m_cfg = get_machine_config(cfg, "srv-worker-01")
        assert len(m_cfg.temperature_sensors) == 2


class TestParseDuration:
    def test_zero_returns_zero(self):
        assert parse_duration("0") == 0.0

    def test_empty_string_returns_zero(self):
        assert parse_duration("") == 0.0

    def test_seconds_only(self):
        assert parse_duration("30s") == 30.0

    def test_minutes_only(self):
        assert parse_duration("5m") == 300.0

    def test_hours_only(self):
        assert parse_duration("1h") == 3600.0

    def test_hours_and_minutes(self):
        assert parse_duration("1h30m") == 5400.0

    def test_full_format(self):
        assert parse_duration("2h15m30s") == pytest.approx(2 * 3600 + 15 * 60 + 30)

    def test_numeric_string(self):
        assert parse_duration("120") == 120.0

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Format de durée non reconnu"):
            parse_duration("abc")

    def test_whitespace_stripped(self):
        assert parse_duration("  5m  ") == 300.0
