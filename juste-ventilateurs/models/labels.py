"""Phase 4 — Génération des labels de prédiction de pannes.

Deux labels binaires sont construits à partir de la colonne ``status``
et de la température de chaque machine :

failure_60s
    1 si la machine passe à l'état ``degraded`` ou ``off`` dans les 60
    secondes suivantes, 0 sinon. Cible principale pour la détection
    précoce de pannes.

hot_30s
    1 si la température dépasse ``t_hot_c`` dans les 30 secondes
    suivantes, 0 sinon. Signal d'alerte thermique plus immédiat.

Usage CLI ::

    python -m juste_ventilateurs.models.labels \\
           data/features/ep01.parquet --output data/labeled/ep01.parquet

Usage Python ::

    from juste_ventilateurs.models.labels import build_labels
    df_labeled = build_labels(df_features)
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ── Constantes ────────────────────────────────────────────────────────────────
FAILURE_HORIZON_S: int = 60   # horizon de prédiction de panne (secondes)
HOT_HORIZON_S: int = 30       # horizon de prédiction de surchauffe (secondes)
T_HOT_C: float = 75.0         # seuil thermique "zone chaude" (°C)
FAILURE_STATES: frozenset[str] = frozenset({"degraded", "off"})


# ── Labellisation ─────────────────────────────────────────────────────────────

def build_labels(
    df: pd.DataFrame,
    failure_horizon_s: int = FAILURE_HORIZON_S,
    hot_horizon_s: int = HOT_HORIZON_S,
    t_hot_c: float = T_HOT_C,
) -> pd.DataFrame:
    """Ajoute les colonnes ``failure_60s`` et ``hot_30s`` au DataFrame.

    Les labels sont construits de manière prospective (look-ahead) :
    pour chaque tick t, on regarde si un événement critique survient
    dans la fenêtre ]t, t + horizon].

    Parameters
    ----------
    df :
        DataFrame de features (colonnes requises : ``ts``, ``machine_id``,
        ``status``, ``temperature_c``).
    failure_horizon_s :
        Durée de la fenêtre look-ahead pour ``failure_60s`` (en secondes).
    hot_horizon_s :
        Durée de la fenêtre look-ahead pour ``hot_30s`` (en secondes).
    t_hot_c :
        Seuil thermique (°C) pour ``hot_30s``.

    Returns
    -------
    pd.DataFrame
        DataFrame enrichi, trié par (machine_id, ts).
        Les ticks trop proches de la fin de la série (moins d'un horizon
        complet devant eux) sont conservés mais leurs labels peuvent être
        sous-estimés — à filtrer en entraînement selon le besoin.
    """
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values(["machine_id", "ts"]).reset_index(drop=True)

    failure_delta = pd.Timedelta(seconds=failure_horizon_s)
    hot_delta = pd.Timedelta(seconds=hot_horizon_s)

    parts: list[pd.DataFrame] = []

    for machine_id, grp in df.groupby("machine_id", sort=False):
        grp = grp.sort_values("ts").reset_index(drop=True)

        ts_arr = grp["ts"].values
        status_arr = grp["status"].values
        temp_arr = grp["temperature_c"].ffill().fillna(0.0).values

        failure_label = pd.array([0] * len(grp), dtype="Int8")
        hot_label = pd.array([0] * len(grp), dtype="Int8")

        n = len(grp)
        j_fail = 0
        j_hot = 0

        for i in range(n):
            t0 = ts_arr[i]

            # ── failure_60s ────────────────────────────────────────────────
            # avance j_fail jusqu'au premier tick hors de la fenêtre
            while j_fail < n and ts_arr[j_fail] <= t0:
                j_fail += 1
            # cherche un état de panne dans ]t0, t0 + horizon]
            k = j_fail
            while k < n and ts_arr[k] <= t0 + failure_delta:
                if status_arr[k] in FAILURE_STATES:
                    failure_label[i] = 1
                    break
                k += 1

            # ── hot_30s ────────────────────────────────────────────────────
            while j_hot < n and ts_arr[j_hot] <= t0:
                j_hot += 1
            k = j_hot
            while k < n and ts_arr[k] <= t0 + hot_delta:
                if temp_arr[k] > t_hot_c:
                    hot_label[i] = 1
                    break
                k += 1

        grp["failure_60s"] = failure_label
        grp["hot_30s"] = hot_label
        parts.append(grp)

    result = pd.concat(parts, ignore_index=True)
    result = result.sort_values(["machine_id", "ts"]).reset_index(drop=True)

    n_fail = int(result["failure_60s"].sum())
    n_hot = int(result["hot_30s"].sum())
    logger.info(
        "Labels générés — failure_60s: %d positifs / %d ticks (%.1f %%)",
        n_fail, len(result), 100 * n_fail / max(len(result), 1),
    )
    logger.info(
        "Labels générés — hot_30s:     %d positifs / %d ticks (%.1f %%)",
        n_hot, len(result), 100 * n_hot / max(len(result), 1),
    )
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Génère les labels failure_60s et hot_30s."
    )
    parser.add_argument("input", help="Parquet de features (Phase 3)")
    parser.add_argument(
        "--output",
        default=None,
        help="Parquet de sortie (défaut: data/labeled/<nom_fichier>)",
    )
    parser.add_argument(
        "--failure-horizon",
        type=int,
        default=FAILURE_HORIZON_S,
        help=f"Horizon panne en secondes (défaut: {FAILURE_HORIZON_S})",
    )
    parser.add_argument(
        "--hot-horizon",
        type=int,
        default=HOT_HORIZON_S,
        help=f"Horizon chaud en secondes (défaut: {HOT_HORIZON_S})",
    )
    parser.add_argument(
        "--t-hot",
        type=float,
        default=T_HOT_C,
        help=f"Seuil zone chaude en °C (défaut: {T_HOT_C})",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = (
        Path(args.output)
        if args.output
        else Path("data/labeled") / input_path.name
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Chargement de %s …", input_path)
    df = pd.read_parquet(input_path)

    df_labeled = build_labels(
        df,
        failure_horizon_s=args.failure_horizon,
        hot_horizon_s=args.hot_horizon,
        t_hot_c=args.t_hot,
    )

    df_labeled.to_parquet(output_path, index=False)
    logger.info("Sauvegardé → %s", output_path)


if __name__ == "__main__":
    main()
