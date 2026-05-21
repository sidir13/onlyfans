"""Phase 4 — Baseline heuristique de détection de pannes.

Deux règles à seuils simples servent de référence (upper-bound facile
à battre) pour évaluer les modèles supervisés :

HeuristicBaseline (règle principale)
    Active l'alarme si la température dépasse ``t_warn_c`` **depuis au
    moins** ``n_consecutive_s`` secondes consécutives.

ThresholdBaseline (règle naïve)
    Active l'alarme dès que la température dépasse ``t_warn_c``
    (zéro persistance requise).

Les deux classes exposent une interface scikit-learn-compatible
(``fit`` / ``predict`` / ``predict_proba``) pour s'insérer dans le
pipeline d'évaluation commun défini dans ``evaluate.py``.

Usage Python ::

    from juste_ventilateurs.models.baseline import HeuristicBaseline
    clf = HeuristicBaseline(t_warn_c=80.0, n_consecutive_s=10)
    clf.fit(X_train, y_train)          # no-op, règle déterministe
    y_pred = clf.predict(X_test)
    y_score = clf.predict_proba(X_test)[:, 1]
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ── Baseline naïve (seuil immédiat) ──────────────────────────────────────────

class ThresholdBaseline:
    """Alarme dès que la température dépasse le seuil.

    Parameters
    ----------
    t_warn_c :
        Seuil d'alarme en °C.
    """

    def __init__(self, t_warn_c: float = 80.0) -> None:
        self.t_warn_c = t_warn_c

    # scikit-learn API (no-op)
    def fit(self, X: pd.DataFrame, y=None) -> "ThresholdBaseline":
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        temp = X["temperature_c"].to_numpy(dtype=float)
        return (temp > self.t_warn_c).astype(int)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        temp = X["temperature_c"].to_numpy(dtype=float)
        # score continu : normalise la température par rapport au seuil
        score = np.clip((temp - self.t_warn_c + 10.0) / 20.0, 0.0, 1.0)
        return np.column_stack([1.0 - score, score])


# ── Baseline heuristique (persistance) ───────────────────────────────────────

class HeuristicBaseline:
    """Alarme si T > t_warn_c depuis au moins n_consecutive_s secondes.

    La règle s'appuie sur la feature ``time_in_hot_zone_s`` produite par
    ``features.engineer`` (si disponible) ou la recalcule à partir de
    ``temperature_c``.

    Parameters
    ----------
    t_warn_c :
        Seuil d'alarme en °C.
    n_consecutive_s :
        Durée minimale de séjour au-dessus du seuil avant alarme.
    margin_c :
        Marge de sortie d'alarme (hysteresis) : l'alarme se désactive
        seulement si T < t_warn_c - margin_c.
    """

    def __init__(
        self,
        t_warn_c: float = 80.0,
        n_consecutive_s: int = 10,
        margin_c: float = 2.0,
    ) -> None:
        self.t_warn_c = t_warn_c
        self.n_consecutive_s = n_consecutive_s
        self.margin_c = margin_c

    def fit(self, X: pd.DataFrame, y=None) -> "HeuristicBaseline":
        return self

    def _score(self, X: pd.DataFrame) -> np.ndarray:
        """Retourne un score continu dans [0, 1] par tick."""
        temp = X["temperature_c"].to_numpy(dtype=float)

        # Utilise time_in_hot_zone_s si disponible, sinon recalcule
        if "time_in_hot_zone_s" in X.columns:
            time_hot = X["time_in_hot_zone_s"].to_numpy(dtype=float)
        else:
            time_hot = np.zeros(len(temp))
            consec = 0.0
            for i, t in enumerate(temp):
                if t > self.t_warn_c:
                    consec += 1.0
                elif t < self.t_warn_c - self.margin_c:
                    consec = 0.0
                time_hot[i] = consec

        # score : fraction de la fenêtre requise dépassée
        score = np.clip(time_hot / max(self.n_consecutive_s, 1), 0.0, 1.0)
        return score

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        score = self._score(X)
        return (score >= 1.0).astype(int)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        score = self._score(X)
        return np.column_stack([1.0 - score, score])


# ── Grille de recherche des hyperparamètres heuristiques ─────────────────────

def tune_heuristic(
    X_val: pd.DataFrame,
    y_val: pd.Series,
    t_warn_grid: list[float] | None = None,
    n_consec_grid: list[int] | None = None,
    metric: str = "f1",
) -> dict:
    """Balayage en grille des hyperparamètres de HeuristicBaseline.

    Parameters
    ----------
    X_val, y_val :
        Données de validation (sans fuite de labels).
    t_warn_grid :
        Liste de seuils T (°C) à tester.
    n_consec_grid :
        Liste de durées de persistance (s) à tester.
    metric :
        ``'f1'``, ``'precision'`` ou ``'recall'``.

    Returns
    -------
    dict
        ``{'best_params': {...}, 'best_score': float, 'results': [...]}``.
    """
    from sklearn.metrics import f1_score, precision_score, recall_score

    if t_warn_grid is None:
        t_warn_grid = [72.0, 75.0, 78.0, 80.0, 83.0]
    if n_consec_grid is None:
        n_consec_grid = [5, 10, 15, 20, 30]

    score_fn = {"f1": f1_score, "precision": precision_score, "recall": recall_score}[
        metric
    ]

    results = []
    best_score = -1.0
    best_params: dict = {}

    for t_warn in t_warn_grid:
        for n_consec in n_consec_grid:
            clf = HeuristicBaseline(t_warn_c=t_warn, n_consecutive_s=n_consec)
            y_pred = clf.predict(X_val)
            s = score_fn(y_val, y_pred, zero_division=0)
            results.append({"t_warn_c": t_warn, "n_consecutive_s": n_consec, metric: s})
            if s > best_score:
                best_score = s
                best_params = {"t_warn_c": t_warn, "n_consecutive_s": n_consec}

    return {"best_params": best_params, "best_score": best_score, "results": results}
