"""Phase 2 — Export TimescaleDB → Parquet train/val/test.

Interroge TimescaleDB et produit des splits temporels reproductibles
pour l'entraînement des modèles ML.

Usage ::

    python -m juste_ventilateurs.ingest.export_dataset \\
           --split 0.70 0.15 0.15 --output data/splits

Variables d'environnement :
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB,
    POSTGRES_USER, POSTGRES_PASSWORD
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import pandas as pd
import psycopg2

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ── Connexion ─────────────────────────────────────────────────────────────────

def _get_conn():
    host = os.environ.get("POSTGRES_HOST", "localhost")
    # Sur Windows, 'localhost' peut résoudre en IPv6 (::1) alors que Docker
    # n'expose le port qu'en IPv4 — on force 127.0.0.1 dans ce cas.
    if host == "localhost":
        host = "127.0.0.1"
    return psycopg2.connect(
        host=host,
        port=int(os.environ.get("POSTGRES_PORT", 5433)),
        dbname=os.environ.get("POSTGRES_DB", "jumeaux"),
        user=os.environ.get("POSTGRES_USER", "jumeaux"),
        password=os.environ.get("POSTGRES_PASSWORD", "jumeaux"),
    )


# ── Requêtes ──────────────────────────────────────────────────────────────────

def load_telemetry(conn) -> pd.DataFrame:
    df = pd.read_sql(
        """
        SELECT
            ts, cluster_id, machine_id, status,
            temperature_c, power_w, energy_kwh,
            load_factor, fan_rpm_avg
        FROM telemetry
        ORDER BY ts ASC
        """,
        conn,
    )
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def load_events(conn) -> pd.DataFrame:
    df = pd.read_sql(
        """
        SELECT ts, cluster_id, machine_id, event_type, payload
        FROM events
        ORDER BY ts ASC
        """,
        conn,
    )
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


# ── Split ─────────────────────────────────────────────────────────────────────

def temporal_split(
    df: pd.DataFrame,
    ratios: tuple[float, float, float],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Découpe temporellement en train / val / test selon les ratios."""
    n = len(df)
    i1 = int(n * ratios[0])
    i2 = i1 + int(n * ratios[1])
    return (
        df.iloc[:i1].copy(),
        df.iloc[i1:i2].copy(),
        df.iloc[i2:].copy(),
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exporte TimescaleDB → Parquet train/val/test."
    )
    parser.add_argument(
        "--split",
        nargs=3,
        type=float,
        default=[0.70, 0.15, 0.15],
        metavar=("TRAIN", "VAL", "TEST"),
        help="Ratios de découpe temporelle (doivent sommer à 1.0)",
    )
    parser.add_argument(
        "--output",
        default="data/splits",
        help="Dossier de sortie Parquet",
    )
    args = parser.parse_args()

    ratios: tuple[float, float, float] = tuple(args.split)  # type: ignore[assignment]
    if abs(sum(ratios) - 1.0) > 1e-4:
        raise ValueError(f"Les ratios doivent sommer à 1.0 (reçu : {sum(ratios):.4f})")

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    logger.info("Connexion à TimescaleDB…")
    conn = _get_conn()
    try:
        tel = load_telemetry(conn)
        evt = load_events(conn)
        logger.info(
            "Télémétrie : %d lignes  |  Événements : %d lignes",
            len(tel),
            len(evt),
        )

        # ── Split télémétrie ──────────────────────────────────────────────
        train, val, test = temporal_split(tel, ratios)
        for name, df in [("train", train), ("val", val), ("test", test)]:
            path = out / f"telemetry_{name}.parquet"
            df.to_parquet(path, index=False)
            logger.info(
                "%-5s → %s  (%d lignes | %s → %s)",
                name,
                path,
                len(df),
                df["ts"].min().isoformat()[:19],
                df["ts"].max().isoformat()[:19],
            )

        # ── Événements (référence complète pour l'évaluation) ─────────────
        evt_path = out / "events_all.parquet"
        evt.to_parquet(evt_path, index=False)
        logger.info("Événements → %s", evt_path)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
