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

from sqlalchemy import and_, or_

from backend.models.investition import Investition


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
