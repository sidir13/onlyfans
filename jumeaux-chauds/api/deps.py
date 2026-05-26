"""Dépendances FastAPI partagées (injection via module-level state).

Le pattern retenu est un état module-level initialisé dans le lifespan,
pluôt que `app.state`, pour simplifier l'accès depuis les tests unitaires.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from simulation.cluster import ClusterSimulator
    from api.ws import ConnectionManager

# Initialisé par le lifespan dans main.py
_simulator: "ClusterSimulator | None" = None
_ws_manager: "ConnectionManager | None" = None
_config: dict | None = None


def get_cluster() -> "ClusterSimulator":
    """Retourne l'instance unique du simulateur.

    Raises
    ------
    RuntimeError
        Si appelé avant que le lifespan ait initialisé le simulateur.
    """
    if _simulator is None:
        raise RuntimeError("ClusterSimulator non initialisé — lifespan non démarré.")
    return _simulator


def get_ws_manager() -> "ConnectionManager":
    """Retourne le ConnectionManager WebSocket."""
    if _ws_manager is None:
        raise RuntimeError("ConnectionManager non initialisé — lifespan non démarré.")
    return _ws_manager


def get_config() -> dict:
    """Retourne la config OmegaConf courante (convertie en dict natif)."""
    if _config is None:
        raise RuntimeError("Config non initialisée — lifespan non démarré.")
    from omegaconf import OmegaConf
    return OmegaConf.to_container(_config, resolve=True)  # type: ignore[return-value]
