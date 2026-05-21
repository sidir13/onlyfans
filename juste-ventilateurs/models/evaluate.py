"""Phase 4 — Évaluation des modèles de détection de pannes.

Métriques calculées
-------------------
Métriques de classification standard :
    precision, recall, f1, roc_auc, pr_auc (average precision)

Métriques métier :
    mean_lead_time_s    — temps moyen d'anticipation (en secondes) entre
                          la première alarme levée et l'événement réel.
                          Mesure l'utilité opérationnelle du modèle.
    false_negative_rate — proportion de pannes non détectées.
    false_alarm_rate    — proportion d'alarmes incorrectes.

Validation par épisodes :
    La fonction ``evaluate_by_episode`` calcule toutes les métriques
    séparément pour chaque épisode/split afin de détecter la variance
    inter-épisodes et les faux-négatifs systématiques.

Usage Python ::

    from juste_ventilateurs.models.evaluate import evaluate_model
    report = evaluate_model(pipeline, df_test, target="failure_60s")
    print(report)

Usage CLI ::

    python -m juste_ventilateurs.models.evaluate \\
           models/failure_lgbm.joblib \\
           data/labeled/test.parquet \\
           --target failure_60s \\
           --plot
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    PrecisionRecallDisplay,
    RocCurveDisplay,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ── Métriques de base ─────────────────────────────────────────────────────────

def compute_metrics(
    y_true: pd.Series | np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray | None = None,
) -> dict[str, float]:
    """Calcule l'ensemble des métriques sur un split.

    Parameters
    ----------
    y_true :
        Vraies étiquettes binaires (0/1).
    y_pred :
        Prédictions binaires (0/1).
    y_score :
        Scores de probabilité de la classe positive (optionnel mais
        recommandé pour roc_auc et pr_auc).

    Returns
    -------
    dict
        Clés : precision, recall, f1, roc_auc, pr_auc,
               false_negative_rate, false_alarm_rate.
    """
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    fnr = fn / max(fn + tp, 1)   # false negative rate
    fpr = fp / max(fp + tn, 1)   # false alarm rate

    metrics: dict[str, float] = {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall":    float(recall_score(y_true, y_pred, zero_division=0)),
        "f1":        float(f1_score(y_true, y_pred, zero_division=0)),
        "false_negative_rate": float(fnr),
        "false_alarm_rate":    float(fpr),
        "n_total":  int(len(y_true)),
        "n_pos":    int(y_true.sum()),
        "n_pred_pos": int(y_pred.sum()),
    }

    if y_score is not None:
        y_score = np.asarray(y_score, dtype=float)
        if len(np.unique(y_true)) > 1:
            metrics["roc_auc"] = float(roc_auc_score(y_true, y_score))
            metrics["pr_auc"]  = float(average_precision_score(y_true, y_score))
        else:
            metrics["roc_auc"] = float("nan")
            metrics["pr_auc"]  = float("nan")

    return metrics


# ── Temps moyen d'anticipation ────────────────────────────────────────────────

def mean_lead_time(
    df: pd.DataFrame,
    y_pred: np.ndarray,
    target: str = "failure_60s",
    machine_col: str = "machine_id",
    ts_col: str = "ts",
) -> float:
    """Calcule le temps moyen d'anticipation en secondes.

    Pour chaque panne réelle (transition vers label=1), on cherche la
    **première** alarme levée avant cet événement dans la même machine.
    Le lead time est la différence de timestamps entre l'alarme et la panne.

    Parameters
    ----------
    df :
        DataFrame avec colonnes ts, machine_id, et la colonne target.
    y_pred :
        Prédictions binaires alignées sur les lignes de df.
    target :
        Nom du label (``failure_60s`` ou ``hot_30s``).

    Returns
    -------
    float
        Temps moyen d'anticipation en secondes. ``nan`` si aucun TP détecté.
    """
    df = df.copy()
    df["__pred__"] = y_pred
    df[ts_col] = pd.to_datetime(df[ts_col], utc=True)

    lead_times: list[float] = []

    for _, grp in df.groupby(machine_col, sort=False):
        grp = grp.sort_values(ts_col).reset_index(drop=True)
        label_arr = grp[target].to_numpy(dtype=int)
        pred_arr = grp["__pred__"].to_numpy(dtype=int)
        ts_arr = grp[ts_col].to_numpy()

        # Repère les débuts d'événement réel (front montant du label)
        failure_onsets = np.where((label_arr[1:] == 1) & (label_arr[:-1] == 0))[0] + 1
        # Ajoute le premier tick positif si le label commence à 1
        if label_arr[0] == 1:
            failure_onsets = np.concatenate([[0], failure_onsets])

        for onset_idx in failure_onsets:
            onset_ts = ts_arr[onset_idx]
            # Cherche la première alarme levée avant cet onset
            alarm_candidates = np.where(pred_arr[:onset_idx] == 1)[0]
            if len(alarm_candidates) > 0:
                first_alarm_idx = alarm_candidates[0]
                delta = (onset_ts - ts_arr[first_alarm_idx]) / np.timedelta64(1, "s")
                lead_times.append(float(delta))

    return float(np.mean(lead_times)) if lead_times else float("nan")


# ── Analyse des faux négatifs ─────────────────────────────────────────────────

def analyze_false_negatives(
    df: pd.DataFrame,
    y_pred: np.ndarray,
    target: str = "failure_60s",
    machine_col: str = "machine_id",
) -> pd.DataFrame:
    """Retourne les ticks positifs manqués (faux négatifs) avec contexte.

    Utile pour comprendre les conditions thermiques/mécaniques qui ont
    trompé le modèle.
    """
    df = df.copy()
    df["__pred__"] = y_pred
    fn_mask = (df[target].astype(int) == 1) & (df["__pred__"] == 0)
    fn_df = df[fn_mask].copy()

    feature_context = [
        c for c in [
            "temperature_c", "dT_15s", "dT_30s",
            "margin_to_shutdown_c", "time_in_hot_zone_s",
            "recent_degraded_60s", "rpm_mean_30s",
        ]
        if c in df.columns
    ]
    cols = [machine_col, "ts", target] + feature_context + ["__pred__"]
    return fn_df[[c for c in cols if c in fn_df.columns]].reset_index(drop=True)


# ── Évaluation complète d'un modèle ──────────────────────────────────────────

def evaluate_model(
    pipeline: Any,
    df: pd.DataFrame,
    target: str = "failure_60s",
    feature_cols: list[str] | None = None,
) -> dict:
    """Évalue un pipeline sur un DataFrame et retourne un rapport complet.

    Parameters
    ----------
    pipeline :
        Pipeline scikit-learn avec méthodes ``predict`` / ``predict_proba``
        ou l'une des baselines de ``models.baseline``.
    df :
        DataFrame de test (features + labels).
    target :
        Colonne label.
    feature_cols :
        Colonnes features à sélectionner. Si ``None``, toutes les colonnes
        numériques sauf le label sont utilisées.

    Returns
    -------
    dict
        Rapport complet : metrics, mean_lead_time_s, n_false_negatives.
    """
    if feature_cols is not None:
        available = [c for c in feature_cols if c in df.columns]
        X = df[available]
    else:
        # Colonnes numériques hors labels et identifiants
        exclude = {target, "failure_60s", "hot_30s", "ts", "machine_id",
                   "cluster_id", "status", "episode_id"}
        X = df.select_dtypes(include="number").drop(
            columns=[c for c in exclude if c in df.columns], errors="ignore"
        )

    y_true = df[target].astype(int)
    y_pred = pipeline.predict(X)

    y_score = None
    if hasattr(pipeline, "predict_proba"):
        y_score = pipeline.predict_proba(X)[:, 1]

    metrics = compute_metrics(y_true, y_pred, y_score)
    mlt = mean_lead_time(df, y_pred, target=target)
    fn_df = analyze_false_negatives(df, y_pred, target=target)

    report = {
        **metrics,
        "mean_lead_time_s": mlt,
        "n_false_negatives": int(len(fn_df)),
    }

    logger.info(
        "Évaluation %s — Precision: %.3f | Recall: %.3f | F1: %.3f | "
        "PR-AUC: %.3f | Lead time: %.1f s | FN: %d",
        target,
        metrics.get("precision", float("nan")),
        metrics.get("recall", float("nan")),
        metrics.get("f1", float("nan")),
        metrics.get("pr_auc", float("nan")),
        mlt if not np.isnan(mlt) else -1,
        len(fn_df),
    )
    return report


# ── Validation par épisodes ───────────────────────────────────────────────────

def evaluate_by_episode(
    pipeline: Any,
    df: pd.DataFrame,
    target: str = "failure_60s",
    episode_col: str = "episode_id",
    feature_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Évalue le modèle séparément sur chaque épisode.

    Parameters
    ----------
    episode_col :
        Colonne identifiant l'épisode. Si absente, toutes les lignes
        sont traitées comme un seul épisode (``'all'``).

    Returns
    -------
    pd.DataFrame
        Une ligne par épisode avec toutes les métriques.
    """
    if episode_col not in df.columns:
        df = df.copy()
        df[episode_col] = "all"

    rows = []
    for ep, grp in df.groupby(episode_col, sort=True):
        if grp[target].sum() == 0:
            logger.warning("Épisode %s — aucun positif, skip.", ep)
            continue
        rep = evaluate_model(pipeline, grp, target=target, feature_cols=feature_cols)
        rep["episode"] = ep
        rows.append(rep)

    return pd.DataFrame(rows).set_index("episode")


# ── Courbes + CLI ─────────────────────────────────────────────────────────────

def _plot_curves(
    y_true: np.ndarray,
    y_score: np.ndarray,
    y_pred: np.ndarray,
    output_dir: Path,
    target: str,
) -> None:
    """Trace et sauvegarde les courbes PR, ROC et la matrice de confusion."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    PrecisionRecallDisplay.from_predictions(y_true, y_score, ax=axes[0])
    axes[0].set_title(f"Courbe Précision-Rappel — {target}")

    RocCurveDisplay.from_predictions(y_true, y_score, ax=axes[1])
    axes[1].set_title(f"Courbe ROC — {target}")

    ConfusionMatrixDisplay(
        confusion_matrix(y_true, y_pred, labels=[0, 1]),
        display_labels=["Normal", "Alarme"],
    ).plot(ax=axes[2])
    axes[2].set_title(f"Matrice de confusion — {target}")

    plt.tight_layout()
    out_file = output_dir / f"{target}_curves.png"
    fig.savefig(out_file, dpi=150)
    plt.close(fig)
    logger.info("Courbes sauvegardées → %s", out_file)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Évalue un modèle sauvegardé sur un Parquet de test."
    )
    parser.add_argument("model", help="Fichier joblib du pipeline entraîné")
    parser.add_argument("test", help="Parquet de test (labelisé, Phase 4)")
    parser.add_argument(
        "--target",
        default="failure_60s",
        choices=["failure_60s", "hot_30s"],
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Génère et sauvegarde les courbes PR/ROC/confusion",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Dossier de sortie pour les courbes et le rapport JSON",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Chargement du modèle: %s", args.model)
    pipeline = joblib.load(args.model)

    logger.info("Chargement du test: %s", args.test)
    df_test = pd.read_parquet(args.test)

    report = evaluate_model(pipeline, df_test, target=args.target)

    report_path = output_dir / f"{args.target}_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    logger.info("Rapport → %s", report_path)

    if args.plot:
        meta_path = Path(args.model).with_suffix(".meta.json")
        feature_cols = None
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
                feature_cols = meta.get("feature_cols")

        exclude = {args.target, "failure_60s", "hot_30s", "ts", "machine_id",
                   "cluster_id", "status", "episode_id"}
        if feature_cols:
            X = df_test[[c for c in feature_cols if c in df_test.columns]]
        else:
            X = df_test.select_dtypes(include="number").drop(
                columns=[c for c in exclude if c in df_test.columns], errors="ignore"
            )

        y_true = df_test[args.target].astype(int).to_numpy()
        y_pred = pipeline.predict(X)
        y_score = pipeline.predict_proba(X)[:, 1]
        _plot_curves(y_true, y_score, y_pred, output_dir, args.target)


if __name__ == "__main__":
    main()
