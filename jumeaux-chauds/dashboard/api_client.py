"""Client HTTP synchrone vers l'API FastAPI (Phase 4).

Utilise httpx en mode synchrone pour être compatible avec Streamlit
(pas de boucle asyncio dans le thread principal Streamlit).

Utilisation :
    from dashboard.api_client import ApiClient
    client = ApiClient(base_url="http://localhost:8000")
    client.power_machine("srv-worker-01", "off")
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5.0  # secondes


class ApiClient:
    """Wrapper httpx synchrone vers l'API FastAPI."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Cluster
    # ------------------------------------------------------------------

    def get_cluster_status(self) -> dict[str, Any]:
        return self._get("/cluster/status")

    def get_cluster_energy(self) -> dict[str, Any]:
        return self._get("/cluster/energy")

    def cluster_power(self, action: str) -> dict[str, Any]:
        """action : 'on' | 'off'"""
        return self._post("/cluster/power", {"action": action})

    def cluster_fan_speed(self, rpm: int) -> dict[str, Any]:
        return self._put("/cluster/fan_speed", {"rpm": rpm})

    # ------------------------------------------------------------------
    # Machine
    # ------------------------------------------------------------------

    def get_machine(self, machine_id: str) -> dict[str, Any]:
        return self._get(f"/machines/{machine_id}")

    def power_machine(self, machine_id: str, action: str) -> dict[str, Any]:
        """action : 'on' | 'off'"""
        return self._post(f"/machines/{machine_id}/power", {"action": action})

    def set_fan_speed(
        self, machine_id: str, fan_idx: int, rpm: int
    ) -> dict[str, Any]:
        return self._put(
            f"/machines/{machine_id}/fan_speed",
            {"fan_idx": fan_idx, "rpm": rpm},
        )

    def set_fan_mode(
        self, machine_id: str, fan_idx: int, mode: str
    ) -> dict[str, Any]:
        """mode : 'auto' | 'manual'"""
        return self._put(
            f"/machines/{machine_id}/fan_mode",
            {"fan_idx": fan_idx, "mode": mode},
        )

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def inject_fault(
        self,
        machine_id: str,
        fault_type: str,
        duration_s: float = 30.0,
        magnitude: float = 1.0,
    ) -> dict[str, Any]:
        return self._post(
            "/simulation/fault",
            {
                "machine_id": machine_id,
                "fault_type": fault_type,
                "duration_s": duration_s,
                "magnitude": magnitude,
            },
        )

    def clear_faults(self, machine_id: str) -> dict[str, Any]:
        return self._delete(f"/simulation/fault/{machine_id}")

    def change_scenario(self, scenario: str) -> dict[str, Any]:
        return self._put("/simulation/scenario", {"scenario": scenario})

    # ------------------------------------------------------------------
    # Helpers privés
    # ------------------------------------------------------------------

    def _get(self, path: str) -> dict[str, Any]:
        try:
            r = self._client.get(path)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.error("GET %s → %s", path, exc)
            return {"error": str(exc)}

    def _post(self, path: str, body: dict) -> dict[str, Any]:
        try:
            r = self._client.post(path, json=body)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.error("POST %s → %s", path, exc)
            return {"error": str(exc), "status_code": getattr(exc.response, "status_code", None)}

    def _put(self, path: str, body: dict) -> dict[str, Any]:
        try:
            r = self._client.put(path, json=body)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.error("PUT %s → %s", path, exc)
            return {"error": str(exc)}

    def _delete(self, path: str) -> dict[str, Any]:
        try:
            r = self._client.delete(path)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.error("DELETE %s → %s", path, exc)
            return {"error": str(exc)}
