"""ConnectionManager WebSocket et endpoint /ws/cluster.

Le manager maintient la liste des connexions actives et diffuse
le snapshot cluster à chaque appel à `broadcast()`.

La méthode `broadcast()` est appelée par `ClusterSimulator.run()`
(ws_manager injecté depuis le lifespan) à la fréquence `events_per_sec`.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Gère les connexions WebSocket actives."""

    def __init__(self) -> None:
        self._active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._active.append(websocket)
        logger.debug("WS connecté — %d connexion(s) active(s)", len(self._active))

    def disconnect(self, websocket: WebSocket) -> None:
        self._active.remove(websocket)
        logger.debug("WS déconnecté — %d connexion(s) active(s)", len(self._active))

    async def broadcast(self, data: dict) -> None:
        """Envoie le snapshot JSON à toutes les connexions actives.

        Les connexions mortes sont retirées silencieusement.
        """
        if not self._active:
            return
        payload = json.dumps(data, default=str)
        dead: list[WebSocket] = []
        for ws in list(self._active):
            try:
                await ws.send_text(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            if ws in self._active:
                self._active.remove(ws)

    @property
    def connection_count(self) -> int:
        return len(self._active)


# ---------------------------------------------------------------------------
# Endpoint WebSocket
# ---------------------------------------------------------------------------

@router.websocket("/ws/cluster")
async def ws_cluster(websocket: WebSocket) -> None:  # pragma: no cover
    """Flux temps réel du snapshot cluster (push par le simulateur).

    Le client se connecte et reçoit passivement les snapshots JSON
    envoyés par `ConnectionManager.broadcast()` à chaque tick.

    Exemple wscat ::

        wscat -c ws://localhost:8000/ws/cluster
    """
    from api import deps
    manager: ConnectionManager = deps.get_ws_manager()
    await manager.connect(websocket)
    try:
        while True:
            # Maintenir la connexion ouverte ; le push vient de broadcast().
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
