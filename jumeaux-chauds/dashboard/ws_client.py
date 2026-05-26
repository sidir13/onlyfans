"""Client WebSocket asyncio pour recevoir le snapshot ClusterSimulator en temps réel.

Utilisation (Streamlit) :
    from dashboard.ws_client import ClusterWSClient
    client = ClusterWSClient(url="ws://localhost:8000/ws/cluster")
    snapshot = client.latest   # dict ou None si pas encore reçu
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

logger = logging.getLogger(__name__)


class ClusterWSClient:
    """Maintient une connexion WebSocket persistante dans un thread dédié.

    Le snapshot le plus récent est accessible via ``self.latest``.
    La reconnexion est automatique avec backoff exponentiel (1 s → 16 s max).
    """

    def __init__(self, url: str = "ws://localhost:8000/ws/cluster") -> None:
        self.url = url
        self.latest: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ws-client")
        self._thread.start()

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def get_snapshot(self) -> dict[str, Any] | None:
        """Retourne le dernier snapshot reçu (thread-safe)."""
        with self._lock:
            return self.latest

    def stop(self) -> None:
        """Arrête proprement le thread de réception."""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Boucle interne
    # ------------------------------------------------------------------

    def _run(self) -> None:
        asyncio.run(self._listen_loop())

    async def _listen_loop(self) -> None:
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                async with websockets.connect(self.url, ping_interval=20) as ws:
                    backoff = 1.0  # reset on successful connect
                    logger.info("WebSocket connecté : %s", self.url)
                    async for raw in ws:
                        if self._stop_event.is_set():
                            break
                        try:
                            data = json.loads(raw)
                            with self._lock:
                                self.latest = data
                        except json.JSONDecodeError as exc:
                            logger.warning("JSON invalide : %s", exc)
            except (ConnectionClosedOK, ConnectionClosedError):
                logger.info("WebSocket fermé, reconnexion dans %.0f s…", backoff)
            except OSError as exc:
                logger.warning("WebSocket indisponible (%s), retry dans %.0f s…", exc, backoff)
            if not self._stop_event.is_set():
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 16.0)
