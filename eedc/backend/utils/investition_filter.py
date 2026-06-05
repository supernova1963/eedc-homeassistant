"""
Stilllegungsdatum-aware Filter-Helper für Investitionen (Issue #123).

Gemeinsame Regel: `aktiv=False` = wie gelöscht (ohne zu löschen) → nirgends in
Auswertungen, auch nicht historisch, bis reaktiviert wird (Gernot 2026-06-05).
ALLE Filter prüfen daher das `aktiv`-Flag; sie unterscheiden sich nur im
Datums-Fenster. Endgültiges Entfernen = Hard-Delete.

Unterscheidung:
- `aktiv_jetzt()` — Live/Current-State-Queries (Prognose, Live-Dashboard,
  Sensor-Mapping): `aktiv` + heute innerhalb des Lebensdauer-Fensters.
- `aktiv_im_zeitraum(start, end)` — historische Aggregate (Monatsdaten-Aggregation,
  Cockpit-Historie, PDF-Jahresbericht): `aktiv` + Lebensdauer-Fenster überlappt
  [start, end] (`anschaffungsdatum`/`stilllegungsdatum`).
- `aktiv_am_tag(tag)` — Per-Tag-Aggregation eines einzelnen Tages
  (`energie_profil.aggregator.aggregate_day`): Per-Tag-Variante von
  `aktiv_im_zeitraum`.

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
    """SQL-Filter: Investition ist im Zeitraum [start, end] sichtbar/aktiv.

    `aktiv=False` = wie gelöscht (ohne zu löschen): nirgends in Auswertungen
    anzeigen — auch nicht historisch — bis reaktiviert wird. Daher prüft auch
    dieser historische Filter das `aktiv`-Flag (Gernot 2026-06-05,
    [[feedback_anschaffungsdatum_grenze]]); `anschaffungsdatum`/`stilllegungsdatum`
    begrenzen zusätzlich das Lebensdauer-Fenster. Endgültig weg = Hard-Delete.
    """
    return and_(
        Investition.aktiv.is_(True),
        or_(
            Investition.anschaffungsdatum.is_(None),
            Investition.anschaffungsdatum <= end,
        ),
        or_(
            Investition.stilllegungsdatum.is_(None),
            Investition.stilllegungsdatum >= start,
        ),
    )


def aktiv_am_tag(tag: date):
    """SQL-Filter: Investition war an EINEM konkreten Tag aktiv (historisch, per-Tag).

    Dritte Variante neben `aktiv_jetzt()` (Live-Sicht) und `aktiv_im_zeitraum()`
    (Range-Sicht): der konsolidierte Tag-Aggregator (`aggregate_day`, v3.34.2
    Phase B) braucht für jeden aggregierten Tag GENAU die Investitionen, die an
    diesem Tag aktiv waren — sonst weichen Scheduler-Pfad und Vollbackfill-Pfad
    für historische Tage mit zwischenzeitlich stillgelegten Investitionen ab
    (Audit §6.4).

    Bewusst exakt die **Null-Breiten-Range** `aktiv_im_zeitraum(tag, tag)`:
    `anschaffungsdatum <= tag AND (stilllegungsdatum is None OR
    stilllegungsdatum >= tag)`. Damit ist die Stilllegungs-Grenze inklusiv —
    am Stilllegungstag selbst gilt die Investition noch als an diesem Tag aktiv,
    identisch zur In-Memory-Model-Methode `Investition.ist_aktiv_an(tag)`
    (`stilllegungsdatum < tag` → inaktiv). Diese Übereinstimmung ist wichtig:
    der Vollbackfill filtert seine Serien per `ist_aktiv_an(current)`, während
    `aggregate_day` die Inv-Last per `aktiv_am_tag(datum)` zieht — beide müssen
    am Stilllegungstag dasselbe Ergebnis liefern. Wie `aktiv_im_zeitraum` prüft
    der Filter auch das `aktiv`-Flag (aktiv=False = wie gelöscht → nirgends, bis
    reaktiviert; konsistent mit `ist_aktiv_an`, das `aktiv` ebenfalls prüft).
    """
    return aktiv_im_zeitraum(tag, tag)


def aktiv_im_monat(jahr: int, monat: int):
    """SQL-Filter: Investition war im gegebenen Kalendermonat (teilweise) aktiv."""
    start = date(jahr, monat, 1)
    end = date(jahr, monat, monthrange(jahr, monat)[1])
    return aktiv_im_zeitraum(start, end)


def aktiv_im_jahr(jahr: int):
    """SQL-Filter: Investition war im gegebenen Kalenderjahr (teilweise) aktiv."""
    return aktiv_im_zeitraum(date(jahr, 1, 1), date(jahr, 12, 31))
