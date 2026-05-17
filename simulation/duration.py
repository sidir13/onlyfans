"""Utilitaire de parsing de durées humaines vers secondes.

Exemples supportés : "0", "30s", "5m", "1h", "1h30m", "2h15m30s"
"""
from __future__ import annotations

import re

_PATTERN = re.compile(
    r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"
)


def parse_duration(value: str) -> float:
    """Convertit une chaîne de durée en secondes (float).

    Args:
        value: Durée sous forme de chaîne. "0" signifie durée infinie
               (retourne 0.0). Exemples : "30s", "5m", "1h30m", "2h15m30s".

    Returns:
        Nombre de secondes (0.0 pour durée infinie).

    Raises:
        ValueError: Si le format n'est pas reconnu.
    """
    value = value.strip()

    if value == "0" or value == "":
        return 0.0

    # Essai de parsing comme nombre pur (secondes)
    try:
        return float(value)
    except ValueError:
        pass

    match = _PATTERN.match(value)
    if not match or not any(match.groups()):
        raise ValueError(
            f"Format de durée non reconnu : '{value}'. "
            "Exemples valides : '0', '30s', '5m', '1h', '1h30m', '2h15m30s'"
        )

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return float(hours * 3600 + minutes * 60 + seconds)
