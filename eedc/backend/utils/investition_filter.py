"""
Stilllegungsdatum-aware Filter-Helper für Investitionen (Issue #123).

Unterscheidung:
- `aktiv_jetzt()` — SQL-Filter für Live/Current-State-Queries (Prognose, Live-Dashboard,
  Sensor-Mapping). Respektiert sowohl `aktiv`-Flag (manueller Override) als auch
  `stilllegungsdatum` (finaler End-Marker).
- `aktiv_im_zeitraum(start, end)` — SQL-Filter für historische Aggregate
  (Monatsdaten-Aggregation, Cockpit-Historie, PDF-Jahresbericht). Ignoriert
  `aktiv`-Flag bewusst, weil vergangene Daten auch nach manuellem Pausieren
  erhalten bleiben müssen. Nur `stilllegungsdatum` und `anschaffungsdatum`
  begrenzen den Einsatzzeitraum.

Für In-Memory-Checks (wenn Investitionen bereits geladen sind und pro Monat
gefiltert werden müssen): siehe Model-Methoden `Investition.ist_aktiv_an()`,
`ist_aktiv_im_zeitraum()`, `ist_aktiv_im_monat()`.
"""

from calendar import monthrange
from datetime import date
from typing import Iterable, TypeVar

from sqlalchemy import and_, or_

from backend.models.investition import Investition


# Anzeige-Reihenfolge der DB-Investitions-Typen — Single Source of Truth.
# Reihenfolge: Wechselrichter → PV-Module → Speicher → Balkonkraftwerk →
# Verbraucher nach Wirkung auf Hausverbrauch (#214 detLAN: WP vor Wallbox).
# `pv-system` ist nicht enthalten — virtueller Aggregat-Typ in der ROI-Tabelle
# mit eigenem Container, wird nicht in dieser Reihe sortiert.
# Spiegel im Frontend: `frontend/src/lib/constants.ts:INVESTITION_TYP_ORDER`.
INVESTITION_TYP_ORDER: list[str] = [
    "wechselrichter",
    "pv-module",
    "speicher",
    "balkonkraftwerk",
    "waermepumpe",
    "wallbox",
    "e-auto",
    "sonstiges",
]


_T = TypeVar("_T")


def sort_investitionen_nach_typ(items: Iterable[_T]) -> list[_T]:
    """Sortiert Investitionen nach `INVESTITION_TYP_ORDER`, Tiebreaker ID.

    Erwartet Objekte mit `.typ`-Attribut. Unbekannte Typen landen ans Ende.
    """
    order_len = len(INVESTITION_TYP_ORDER)

    def key(it: _T) -> tuple[int, int]:
        typ = getattr(it, "typ", None)
        idx = INVESTITION_TYP_ORDER.index(typ) if typ in INVESTITION_TYP_ORDER else order_len
        return (idx, getattr(it, "id", 0) or 0)

    return sorted(items, key=key)


def aktiv_jetzt():
    """SQL-Filter: Investition ist heute aktiv (Live-Sicht)."""
    today = date.today()
    return and_(
        Investition.aktiv.is_(True),
        or_(
            Investition.stilllegungsdatum.is_(None),
            Investition.stilllegungsdatum > today,
        ),
    )


def aktiv_im_zeitraum(start: date, end: date):
    """SQL-Filter: Investition war irgendwann im Zeitraum [start, end] aktiv (historisch).

    Ignoriert `aktiv`-Flag bewusst — historische InvestitionMonatsdaten bleiben
    auch nach manuellem Pausieren gültig.
    """
    return and_(
        or_(
            Investition.anschaffungsdatum.is_(None),
            Investition.anschaffungsdatum <= end,
        ),
        or_(
            Investition.stilllegungsdatum.is_(None),
            Investition.stilllegungsdatum >= start,
        ),
    )


def aktiv_im_monat(jahr: int, monat: int):
    """SQL-Filter: Investition war im gegebenen Kalendermonat (teilweise) aktiv."""
    start = date(jahr, monat, 1)
    end = date(jahr, monat, monthrange(jahr, monat)[1])
    return aktiv_im_zeitraum(start, end)


def aktiv_im_jahr(jahr: int):
    """SQL-Filter: Investition war im gegebenen Kalenderjahr (teilweise) aktiv."""
    return aktiv_im_zeitraum(date(jahr, 1, 1), date(jahr, 12, 31))
