"""Phase 4 — Entraînement du modèle supervisé de détection de pannes.

Supporte Random Forest (scikit-learn) et LightGBM.  Le choix du backend
se fait via l'argument ``--model`` ou le paramètre ``model_type``.

Pipeline d'entraînement
-----------------------
1. Chargement des Parquets labelisés (Phase 4 – labels.py)
2. Sélection des features, imputation des NaN, scaling optionnel
3. Entraînement (RF ou LightGBM) sur le split train
4. Sauvegarde du modèle (joblib) + des métadonnées d'entraînement

Usage CLI ::

    python -m juste_ventilateurs.models.train \\
           data/labeled/train.parquet \\
           --val data/labeled/val.parquet \\
           --target failure_60s \\
           --model lgbm \\
           --output models/failure_lgbm.joblib

Usage Python ::

    from juste_ventilateurs.models.train import train_model
    clf, meta = train_model(df_train, df_val, target="failure_60s")
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
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_class_weight

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ── Features utilisées par le modèle ─────────────────────────────────────────
# (toutes produites par features/engineer.py + models/labels.py)
DEFAULT_FEATURES: list[str] = [
    "temperature_c",
    "dT_5s",
    "dT_15s",
    "dT_30s",
    "margin_to_shutdown_c",
    "load_mean_15s",
    "load_mean_30s",
    "rpm_mean_15s",
    "rpm_var_15s",
    "rpm_mean_30s",
    "time_in_hot_zone_s",
    "recent_degraded_30s",
    "recent_degraded_60s",
    "fan_changes_30s",
    "fan_changes_60s",
    "power_w_mean_15s",
]

# ── Hyperparamètres par défaut ────────────────────────────────────────────────
RF_PARAMS: dict[str, Any] = {
    "n_estimators": 300,
    "max_depth": 12,
    "min_samples_leaf": 10,
    "n_jobs": -1,
    "random_state": 42,
}

LGBM_PARAMS: dict[str, Any] = {
    "n_estimators": 500,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "max_depth": -1,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _select_features(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Sélectionne les colonnes de features disponibles."""
    available = [c for c in feature_cols if c in df.columns]
    missing = set(feature_cols) - set(available)
    if missing:
        logger.warning("Features absentes (ignorées) : %s", sorted(missing))
    return df[available]


def _class_weights(y: pd.Series) -> dict[int, float]:
    """Calcule les poids de classes pour compenser le déséquilibre."""
    classes = np.unique(y)
    weights = compute_class_weight("balanced", classes=classes, y=y)
    return dict(zip(classes.tolist(), weights.tolist()))


# ── Entraînement ─────────────────────────────────────────────────────────────

def train_model(
    df_train: pd.DataFrame,
    df_val: pd.DataFrame | None = None,
    target: str = "failure_60s",
    model_type: str = "lgbm",
    feature_cols: list[str] | None = None,
    model_params: dict[str, Any] | None = None,
) -> tuple[Pipeline, dict]:
    """Entraîne un classifieur et retourne le pipeline + les métadonnées.

    Parameters
    ----------
    df_train :
        DataFrame d'entraînement avec features ET labels (Phase 4).
    df_val :
        DataFrame de validation facultatif (utilisé pour early stopping
        LightGBM et logs de performance).
    target :
        Nom de la colonne label (``'failure_60s'`` ou ``'hot_30s'``).
    model_type :
        ``'rf'`` (Random Forest) ou ``'lgbm'`` (LightGBM).
    feature_cols :
        Liste de colonnes à utiliser comme features. Par défaut
        ``DEFAULT_FEATURES``.
    model_params :
        Hyperparamètres à surcharger pour le modèle choisi.

    Returns
    -------
    pipeline :
        sklearn ``Pipeline`` (imputer → classifier).
    meta :
        Dict de métadonnées : feature_cols, target, model_type, class_weights,
        n_train, n_val, val_metrics (si df_val fourni).
    """
    if feature_cols is None:
        feature_cols = DEFAULT_FEATURES

    X_train = _select_features(df_train, feature_cols)
    y_train = df_train[target].astype(int)
    used_features = list(X_train.columns)

    cw = _class_weights(y_train)
    logger.info(
        "Entraînement %s sur %d ticks — positifs: %.1f %% — class weights: %s",
        target, len(y_train), 100 * y_train.mean(), cw,
    )

    # ── Construction du pipeline ──────────────────────────────────────────
    imputer = SimpleImputer(strategy="median")

    if model_type == "lgbm":
        try:
            import lightgbm as lgb
        except ImportError as exc:
            raise ImportError(
                "LightGBM non installé. Lancez `pip install lightgbm` "
                "ou utilisez --model rf."
            ) from exc
        params = {**LGBM_PARAMS, **(model_params or {})}
        params["class_weight"] = cw
        classifier = lgb.LGBMClassifier(**params)
    else:
        params = {**RF_PARAMS, **(model_params or {})}
        params["class_weight"] = cw
        classifier = RandomForestClassifier(**params)

    pipeline = Pipeline([
        ("imputer", imputer),
        ("classifier", classifier),
    ])

    # ── Fit ───────────────────────────────────────────────────────────────
    if model_type == "lgbm" and df_val is not None:
        X_val_fit = _select_features(df_val, used_features)
        y_val_fit = df_val[target].astype(int)
        pipeline.fit(
            X_train, y_train,
            classifier__eval_set=[(pipeline.named_steps["imputer"].fit_transform(X_val_fit), y_val_fit)],
            classifier__callbacks=[
                __import__("lightgbm").early_stopping(50, verbose=False),
                __import__("lightgbm").log_evaluation(100),
            ],
        )
    else:
        pipeline.fit(X_train, y_train)

    # ── Métadonnées ───────────────────────────────────────────────────────
    meta: dict = {
        "target": target,
        "model_type": model_type,
        "feature_cols": used_features,
        "n_train": int(len(y_train)),
        "pos_rate_train": float(y_train.mean()),
        "class_weights": {str(k): v for k, v in cw.items()},
    }

    if df_val is not None:
        from juste_ventilateurs.models.evaluate import compute_metrics
        X_val = _select_features(df_val, used_features)
        y_val = df_val[target].astype(int)
        y_pred = pipeline.predict(X_val)
        y_score = pipeline.predict_proba(X_val)[:, 1]
        val_metrics = compute_metrics(y_val, y_pred, y_score)
        meta["val_metrics"] = val_metrics
        meta["n_val"] = int(len(y_val))
        logger.info("Val — %s", val_metrics)

    return pipeline, meta


# ── Feature importance ────────────────────────────────────────────────────────

def feature_importance(pipeline: Pipeline, feature_cols: list[str]) -> pd.DataFrame:
    """Retourne un DataFrame trié des importances de features."""
    clf = pipeline.named_steps["classifier"]
    if hasattr(clf, "feature_importances_"):
        imp = clf.feature_importances_
    else:
        raise ValueError("Le classifieur ne fournit pas feature_importances_.")
    df = pd.DataFrame({"feature": feature_cols, "importance": imp})
    return df.sort_values("importance", ascending=False).reset_index(drop=True)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Entraîne le modèle supervisé de détection de pannes."
    )
    parser.add_argument("train", help="Parquet d'entraînement (labelisé, Phase 4)")
    parser.add_argument("--val", default=None, help="Parquet de validation")
    parser.add_argument(
        "--target",
        default="failure_60s",
        choices=["failure_60s", "hot_30s"],
        help="Label cible (défaut: failure_60s)",
    )
    parser.add_argument(
        "--model",
        default="lgbm",
        choices=["lgbm", "rf"],
        help="Backend ML (défaut: lgbm)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Chemin joblib de sortie (défaut: models/<target>_<model>.joblib)",
    )
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else (
        Path("models") / f"{args.target}_{args.model}.joblib"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path = output_path.with_suffix(".meta.json")

    logger.info("Chargement train: %s", args.train)
    df_train = pd.read_parquet(args.train)
    df_val = pd.read_parquet(args.val) if args.val else None

    pipeline, meta = train_model(
        df_train,
        df_val=df_val,
        target=args.target,
        model_type=args.model,
    )

    joblib.dump(pipeline, output_path)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    logger.info("Modèle sauvegardé → %s", output_path)
    logger.info("Métadonnées      → %s", meta_path)


if __name__ == "__main__":
    main()
