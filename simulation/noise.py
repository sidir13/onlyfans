"""Fonctions de génération de bruit pour la simulation de capteurs.

Toutes les fonctions utilisent numpy pour la reproductibilité
(numpy.random.seed peut être fixé dans les tests).
"""
from __future__ import annotations

import numpy as np


def gaussian_noise(value: float, std: float) -> float:
    """Ajoute un bruit gaussien centré à une valeur.

    Args:
        value: Valeur de base.
        std:   Écart-type du bruit (0 = pas de bruit).

    Returns:
        Valeur bruitée.
    """
    if std <= 0.0:
        return value
    return float(value + np.random.normal(0.0, std))


def add_spike(
    value: float,
    probability: float,
    magnitude: float,
) -> float:
    """Applique un spike stochastique sur une valeur.

    À chaque appel, avec probabilité `probability`, la valeur est augmentée
    de `magnitude` (spike positif).

    Args:
        value:       Valeur de base.
        probability: Probabilité d'apparition du spike par appel [0, 1].
        magnitude:   Amplitude du spike (même unité que value).

    Returns:
        Valeur potentiellement augmentée du spike.
    """
    if probability <= 0.0:
        return value
    if np.random.random() < probability:
        return float(value + magnitude)
    return value


def accumulate_drift(
    current_drift: float,
    rate_per_s: float,
    dt: float,
) -> float:
    """Accumule une dérive progressive sur un capteur.

    Args:
        current_drift: Dérive cumulée actuelle (même unité que la valeur capteur).
        rate_per_s:    Taux de dérive par seconde.
        dt:            Pas de temps (s).

    Returns:
        Nouvelle dérive cumulée.
    """
    return current_drift + rate_per_s * dt


def weibull_event(
    shape: float,
    scale_s: float,
    elapsed_s: float,
    dt: float,
) -> bool:
    """Tire un événement selon une distribution de Weibull.

    Approche par taux de défaillance instantané h(t) = (β/η)(t/η)^(β-1).
    La probabilité d'événement sur dt est : P ≈ h(t) * dt.

    Args:
        shape:     Paramètre de forme β (Weibull).
        scale_s:   Paramètre d'échelle η (MTBF approx.), en secondes.
        elapsed_s: Temps écoulé depuis la dernière remise à zéro (s).
        dt:        Pas de temps (s).

    Returns:
        True si l'événement se produit pendant ce tick.
    """
    if elapsed_s <= 0 or scale_s <= 0:
        return False
    t = elapsed_s
    hazard_rate = (shape / scale_s) * ((t / scale_s) ** (shape - 1))
    probability = 1.0 - np.exp(-hazard_rate * dt)
    return bool(np.random.random() < probability)


def exponential_event(scale_s: float, dt: float) -> bool:
    """Tire un événement selon une distribution exponentielle (processus de Poisson).

    P(événement sur dt) = 1 - exp(-dt / scale_s)

    Args:
        scale_s: Temps moyen entre événements (s).
        dt:      Pas de temps (s).

    Returns:
        True si l'événement se produit pendant ce tick.
    """
    if scale_s <= 0:
        return False
    probability = 1.0 - np.exp(-dt / scale_s)
    return bool(np.random.random() < probability)


def uniform_event(probability_per_tick: float) -> bool:
    """Tire un événement selon une probabilité uniforme par tick.

    Args:
        probability_per_tick: Probabilité d'occurrence par tick [0, 1].

    Returns:
        True si l'événement se produit.
    """
    if probability_per_tick <= 0.0:
        return False
    return bool(np.random.random() < probability_per_tick)
