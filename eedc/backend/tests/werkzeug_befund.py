"""Lesehilfe der Tests für den Handgriff eines Daten-Checker-Befunds (Etappe E5): die Altfelder `link`/`action_*` sind aus
`CheckErgebnis` und der Antwort entfernt (Wächter W-3); Tests lesen Pfad, Operation und Parameter aus `ziel`/`action` —
für ein `CheckErgebnis` wie für einen Befund der JSON-Antwort (`dict`). Kein Produktcode."""

from __future__ import annotations

from typing import Any, Optional

from backend.services.daten_checker.kategorien import Ziel, link_aus_ziel


def _feld(befund: Any, name: str) -> Any:
    return befund.get(name) if isinstance(befund, dict) else getattr(befund, name)


def befund_link(befund: Any) -> Optional[str]:
    """Der Sprung-Pfad (`link_aus_ziel`) eines Befunds, ``None`` ohne Ziel."""
    ziel = _feld(befund, "ziel")
    if isinstance(ziel, dict):
        ziel = Ziel(**ziel)
    return link_aus_ziel(ziel)


def befund_op(befund: Any) -> Optional[str]:
    """Die Operation der Aktion, ``None`` ohne Aktion."""
    aktion = _feld(befund, "action")
    if aktion is None:
        return None
    return aktion["operation"] if isinstance(aktion, dict) else aktion.operation


def befund_params(befund: Any) -> Optional[dict]:
    """Die Plan-Parameter der Aktion, ``None`` ohne Aktion."""
    aktion = _feld(befund, "action")
    if aktion is None:
        return None
    return aktion["params"] if isinstance(aktion, dict) else aktion.params
