"""Fixtures partagées pour tous les tests."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from omegaconf import DictConfig

from config.loader import load_config

# Répertoire de configuration pour les tests
_CONFIG_DIR = Path(__file__).parent.parent / "config"


@pytest.fixture(autouse=True)
def fix_random_seed():
    """Fixe le seed numpy pour la reproductibilité de tous les tests."""
    np.random.seed(42)
    yield
    # Pas de teardown nécessaire


@pytest.fixture
def nominal_config() -> DictConfig:
    """Configuration nominale complète."""
    return load_config(scenario="nominal", config_dir=_CONFIG_DIR)


@pytest.fixture
def stress_config() -> DictConfig:
    """Configuration stress complète."""
    return load_config(scenario="stress", config_dir=_CONFIG_DIR)


@pytest.fixture
def master_thermal_params() -> dict:
    """Paramètres thermiques du rôle master pour les tests physiques."""
    return {
        "idle_w": 200.0,
        "max_w": 1700.0,
        "heat_ratio": 0.70,
        "ambient_temp_c": 22.0,
        "thermal_capacity_j_per_c": 800.0,
        "tau_max_s": 90.0,
        "k_cool_rpm_factor": 3.5,
        "alpha_load_exponent": 1.5,
        "t_shutdown_c": 90.0,
        "t_restart_c": 55.0,
        "max_rpm": 5000,
        "gain_rpm_per_c": 50.0,
        "fan_count": 2,
        "fan_power_w": 15.0,
    }
