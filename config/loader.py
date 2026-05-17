"""Chargeur de configuration hiérarchique via OmegaConf.

Niveaux de merge (du plus général au plus spécifique) :
    1. config/base.yaml          — valeurs de référence cluster + rôles
    2. config/scenarios/<x>.yaml — profil de simulation actif
    3. overrides dict            — surcharges programmatiques ou ENV
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from omegaconf import DictConfig, OmegaConf

_CONFIG_DIR = Path(__file__).parent


def load_config(
    scenario: str | None = None,
    overrides: dict[str, Any] | None = None,
    config_dir: Path | None = None,
) -> DictConfig:
    """Charge et fusionne la configuration en 3 niveaux.

    Args:
        scenario: Nom du scénario (ex: "nominal", "stress").
                  Si None, utilise la variable d'environnement SCENARIO,
                  ou "nominal" par défaut.
        overrides: Dictionnaire de surcharges appliquées en dernier.
        config_dir: Répertoire de configuration (défaut : config/).

    Returns:
        DictConfig fusionné.
    """
    base_dir = config_dir or _CONFIG_DIR
    if scenario is None:
        scenario = os.environ.get("SCENARIO", "nominal")

    base_path = base_dir / "base.yaml"
    scenario_path = base_dir / "scenarios" / f"{scenario}.yaml"

    if not base_path.exists():
        raise FileNotFoundError(f"Fichier de configuration introuvable : {base_path}")
    if not scenario_path.exists():
        raise FileNotFoundError(f"Scénario introuvable : {scenario_path}")

    base_cfg = OmegaConf.load(base_path)
    scenario_cfg = OmegaConf.load(scenario_path)
    merged = OmegaConf.merge(base_cfg, scenario_cfg)

    if overrides:
        override_cfg = OmegaConf.create(overrides)
        merged = OmegaConf.merge(merged, override_cfg)

    # Surcharge depuis les variables d'environnement
    cluster_id = os.environ.get("CLUSTER_ID")
    if cluster_id:
        merged.cluster.id = cluster_id

    mqtt_host = os.environ.get("MQTT_BROKER_HOST")
    if mqtt_host:
        merged.cluster.mqtt.broker_host = mqtt_host

    tick_rate = os.environ.get("TICK_RATE_HZ")
    if tick_rate:
        merged.simulation.tick_rate_hz = float(tick_rate)

    return merged


def get_machine_config(cfg: DictConfig, machine_id: str) -> DictConfig:
    """Retourne la configuration fusionnée d'une machine spécifique.

    Fusionne : role_profile + surcharges individuelles de la machine.

    Args:
        cfg: Configuration globale chargée via load_config().
        machine_id: Identifiant de la machine.

    Returns:
        DictConfig de la machine avec héritage du rôle.

    Raises:
        KeyError: Si la machine n'existe pas dans la configuration.
    """
    machines = cfg.cluster.machines
    machine_entry = None
    for m in machines:
        if m.id == machine_id:
            machine_entry = m
            break

    if machine_entry is None:
        raise KeyError(f"Machine '{machine_id}' introuvable dans la configuration")

    role = machine_entry.role
    if role not in cfg.cluster.role_profiles:
        raise KeyError(f"Rôle '{role}' non défini dans role_profiles")

    role_cfg = OmegaConf.structured(cfg.cluster.role_profiles[role])
    machine_overrides = OmegaConf.masked_copy(
        machine_entry,
        [k for k in machine_entry if k not in ("id", "role")],
    )
    return OmegaConf.merge(role_cfg, machine_overrides)
