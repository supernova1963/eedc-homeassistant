"""Gespeicherter Monatswert gegen den Wert der Quelle (Sensorwechsel U3 a, Rechenweg G2) — die Regel hinter dem
Daten-Checker-Befund ``monatswert_ueberholt``.

**Regel.** Ein gespeicherter Monatswert «passt nicht mehr zur Quelle», wenn beide da sind und um mindestens
``MONATSWERT_TOLERANZ_KWH`` auseinanderliegen — dieselbe Schwelle wie die Import-Vorschau «Monatsdaten aus HA-Statistik
laden» (``api/routes/ha_statistics.py``: «abweichend» ab 1 kWh). Darunter ist es Rundung (an der Produktiv-Kopie im Monat des
Wechsels 242,9 gespeichert gegen 242,871 aus dem Kanal). Reine Funktion, keine Datenbank.

Schwesterdateien: ``services/daten_checker/datenquelle/monatswert.py`` (Erzeuger).
"""

from __future__ import annotations

from typing import Optional

#: Ab dieser Abweichung (kWh) gilt ein gespeicherter Monatswert als überholt (Toleranz der Import-Vorschau).
MONATSWERT_TOLERANZ_KWH = 1.0


def abweichung_kwh(gespeichert: Optional[float], quelle: Optional[float]) -> Optional[float]:
    """``quelle − gespeichert`` — ``None``, wenn einer fehlt."""
    if gespeichert is None or quelle is None:
        return None
    return float(quelle) - float(gespeichert)


def monatswert_weicht_ab(gespeichert: Optional[float], quelle: Optional[float],
                         toleranz_kwh: float = MONATSWERT_TOLERANZ_KWH) -> bool:
    """Liegen gespeicherter Wert und Wert der Quelle um mindestens ``toleranz_kwh`` auseinander? Fehlt einer: nein."""
    d = abweichung_kwh(gespeichert, quelle)
    return d is not None and abs(d) >= toleranz_kwh


__all__ = ["MONATSWERT_TOLERANZ_KWH", "abweichung_kwh", "monatswert_weicht_ab"]
