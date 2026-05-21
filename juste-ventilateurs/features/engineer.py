"""Phase 3 — Feature engineering.

Construit les features ML à partir d'un Parquet de télémétrie brute.
Fonctionne avec les deux sources : ``mqtt_recorder`` et ``export_dataset``.

Usage CLI ::

    python -m juste_ventilateurs.features.engineer \\
           data/raw/telemetry_ep01.parquet --output data/features/ep01.parquet

Usage Python ::

    from juste_ventilateurs.features.engineer import build_features
    df_feat = build_features(df_raw)

Features produites
------------------
Dérivées de température :
    dT_5s, dT_15s, dT_30s          — taux de montée en °C/s sur 5/15/30 s

Marge au shutdown :
    margin_to_shutdown_c            — T_SHUTDOWN - temp (plus c'est petit, plus c'est chaud)

Rolling charge (si load_factor disponible) :
    load_mean_15s, load_mean_30s

Rolling ventilateurs :
    rpm_mean_15s, rpm_var_15s
    rpm_mean_30s

Temps en zone chaude (cumulatif par machine) :
    time_in_hot_zone_s              — secondes passées au-dessus de T_HOT_C

Événements degraded récents :
    recent_degraded_30s             — nb ticks en état degraded sur les 30 s
    recent_degraded_60s

Changements de consigne ventilateur :
    fan_changes_30s                 — nb de sauts RPM > seuil sur les 30 s
    fan_changes_60s

Features énergie :
    cost_eur                        — énergie cumulée × PUE × prix
    power_w_mean_15s                — rolling mean de la puissance (si disponible)
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

# ── Constantes (calibrées sur config jumeaux-chauds) ─────────────────────────
T_SHUTDOWN_C: float = 90.0       # seuil d'arrêt thermique master (°C)
T_HOT_C: float = 75.0            # zone chaude (~83 % du shutdown)
PUE: float = 1.40                # Power Usage Effectiveness du datacenter
PRICE_EUR_KWH: float = 0.20      # prix électricité (€/kWh)
TELEMETRY_HZ: float = 1.0        # fréquence de publication du simulateur
RPM_CHANGE_THRESHOLD: float = 100.0  # variation RPM considérée comme un changement de consigne


# ── Feature engineering ───────────────────────────────────────────────────────

def build_features(
    df: pd.DataFrame,
    t_shutdown_c: float = T_SHUTDOWN_C,
    t_hot_c: float = T_HOT_C,
    pue: float = PUE,
    price_eur_kwh: float = PRICE_EUR_KWH,
    dt_s: float = 1.0 / TELEMETRY_HZ,
) -> pd.DataFrame:
    """Construit les features ML par machine à partir du DataFrame brut.

    Parameters
    ----------
    df :
        DataFrame de télémétrie (colonnes minimales requises :
        ``ts``, ``machine_id``, ``temperature_c``, ``status``, ``fan_rpm_avg``).
    t_shutdown_c :
        Température de shutdown (°C) utilisée pour le calcul de marge.
    t_hot_c :
        Seuil de zone chaude (°C) pour le compteur ``time_in_hot_zone_s``.
    pue :
        Power Usage Effectiveness pour le calcul du coût estimé.
    price_eur_kwh :
        Prix de l'électricité en €/kWh.
    dt_s :
        Intervalle de temps entre deux ticks en secondes (1.0 à 1 Hz).

    Returns
    -------
    pd.DataFrame
        DataFrame enrichi des features, trié par (machine_id, ts).
        Les NaN en début de fenêtre rolling sont normaux et attendus.
    """
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values(["machine_id", "ts"]).reset_index(drop=True)

    parts: list[pd.DataFrame] = []

    for _, grp in df.groupby("machine_id", sort=False):
        grp = grp.sort_values("ts").reset_index(drop=True)

        temp = grp["temperature_c"].ffill().fillna(0.0)

        # ── Dérivées de température ───────────────────────────────────────
        for lag, label in [(5, "5s"), (15, "15s"), (30, "30s")]:
            grp[f"dT_{label}"] = (temp - temp.shift(lag)) / (lag * dt_s)

        # ── Marge au shutdown ─────────────────────────────────────────────
        grp["margin_to_shutdown_c"] = t_shutdown_c - temp

        # ── Rolling charge (optionnel) ────────────────────────────────────
        if "load_factor" in grp.columns:
            load = grp["load_factor"].fillna(0.0)
            grp["load_mean_15s"] = load.rolling(15, min_periods=1).mean()
            grp["load_mean_30s"] = load.rolling(30, min_periods=1).mean()

        # ── Rolling ventilateurs ──────────────────────────────────────────
        rpm = grp["fan_rpm_avg"].fillna(0.0)
        grp["rpm_mean_15s"] = rpm.rolling(15, min_periods=1).mean()
        grp["rpm_var_15s"] = rpm.rolling(15, min_periods=1).var().fillna(0.0)
        grp["rpm_mean_30s"] = rpm.rolling(30, min_periods=1).mean()

        # ── Temps cumulatif en zone chaude ────────────────────────────────
        in_hot = (temp > t_hot_c).astype(float)
        grp["time_in_hot_zone_s"] = in_hot.cumsum() * dt_s

        # ── Événements degraded récents ───────────────────────────────────
        is_degraded = (grp["status"] == "degraded").astype(float)
        grp["recent_degraded_30s"] = is_degraded.rolling(30, min_periods=1).sum()
        grp["recent_degraded_60s"] = is_degraded.rolling(60, min_periods=1).sum()

        # ── Changements de consigne ventilateur ───────────────────────────
        rpm_jump = (rpm.diff().abs() > RPM_CHANGE_THRESHOLD).astype(float)
        grp["fan_changes_30s"] = rpm_jump.rolling(30, min_periods=1).sum()
        grp["fan_changes_60s"] = rpm_jump.rolling(60, min_periods=1).sum()

        # ── Features énergie ─────────────────────────────────────────────
        # energy_kwh_cumulated : cumulée par la machine depuis son démarrage
        # energy_kwh           : alias TimescaleDB pour la même colonne
        energy_col = next(
            (c for c in ("energy_kwh_cumulated", "energy_kwh") if c in grp.columns),
            None,
        )
        if energy_col:
            grp["cost_eur"] = grp[energy_col].fillna(0.0) * pue * price_eur_kwh

        if "power_w" in grp.columns:
            grp["power_w_mean_15s"] = (
                grp["power_w"].fillna(0.0).rolling(15, min_periods=1).mean()
            )

        parts.append(grp)

    result = pd.concat(parts, ignore_index=True)
    result = result.sort_values(["machine_id", "ts"]).reset_index(drop=True)
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Construit les features ML à partir d'un Parquet de télémétrie."
    )
    parser.add_argument("input", help="Parquet de télémétrie brute")
    parser.add_argument(
        "--output",
        default=None,
        help="Parquet de sortie (défaut: data/features/<nom_fichier>)",
    )
    parser.add_argument(
        "--t-shutdown",
        type=float,
        default=T_SHUTDOWN_C,
        help=f"Température de shutdown en °C (défaut: {T_SHUTDOWN_C})",
    )
    parser.add_argument(
        "--t-hot",
        type=float,
        default=T_HOT_C,
        help=f"Seuil de zone chaude en °C (défaut: {T_HOT_C})",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = (
        Path(args.output)
        if args.output
        else Path("data/features") / input_path.name
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Chargement : %s", input_path)
    df = pd.read_parquet(input_path)
    logger.info("  %d lignes, %d colonnes, %d machines",
                len(df), df.shape[1], df["machine_id"].nunique())

    df_feat = build_features(
        df,
        t_shutdown_c=args.t_shutdown,
        t_hot_c=args.t_hot,
    )

    df_feat.to_parquet(output_path, index=False)
    new_cols = [c for c in df_feat.columns if c not in df.columns]
    logger.info(
        "Features → %s  (%d nouvelles colonnes : %s)",
        output_path,
        len(new_cols),
        ", ".join(new_cols),
    )


if __name__ == "__main__":
    main()
