"""Daten-Checker meldet ein überbelegtes BKW ohne gepflegte Wechselrichter-Leistung.

Gegenstück zu #347: `get_wr_grenze_kw` liefert ohne Pflege bewusst `None` und
kappt dann nicht — ein Default wäre die ADR-002-Klasse „aus *nicht gepflegt*
wird eine Zahl, die wie eine Messung aussieht". Damit das kein stiller Verzicht
ist, muss der fehlende Wert **gemeldet** werden; dieselbe Konstruktion wie bei
der Speicher-Kapazität (E16/N127).

Die Regel ist bewusst schwellenbehaftet: erst oberhalb der typischen
Einspeisegrenze (`BKW_EINSPEISEGRENZE_W_TYPISCH` = 800 W) ist Überbelegung so
wahrscheinlich, dass der Hinweis trägt. Darunter wäre er Nörgeln — deshalb steht
jedem „Befund"-Fall ein „kein Befund"-Fall gegenüber.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity

_MELDUNG = "Wechselrichter-Leistung fehlt"


async def _anlage_mit_bkw(db, parameter: dict) -> Anlage:
    anlage = Anlage(anlagenname="BKW-Test", leistung_kwp=1.26)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Vorgarten",
        anschaffungsdatum=date(2024, 4, 1), parameter=parameter,
    ))
    await db.commit()
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()


async def test_ueberbelegtes_bkw_ohne_grenze_wird_gemeldet(db):
    """Rainers Fall: 3 × 420 Wp = 1.260 W, kein Wechselrichter-Wert gepflegt."""
    anlage = await _anlage_mit_bkw(db, {"leistung_wp": 420, "anzahl": 3})

    ergebnisse = DatenChecker(db)._check_investitionen(anlage, [])

    treffer = [r for r in ergebnisse if _MELDUNG in r.meldung]
    assert len(treffer) == 1, f"Befund erwartet, war: {[r.meldung for r in ergebnisse]}"
    assert treffer[0].schwere == CheckSeverity.WARNING
    assert "Vorgarten" in treffer[0].meldung
    assert "1260 W" in treffer[0].details
    assert "stündlich gekappt" in treffer[0].details


async def test_gepflegte_grenze_schweigt(db):
    """Derselbe Bestand mit gepflegtem Wert — die Prognose kappt, kein Befund."""
    anlage = await _anlage_mit_bkw(
        db, {"leistung_wp": 420, "anzahl": 3, "wechselrichter_leistung_w": 600},
    )

    ergebnisse = DatenChecker(db)._check_investitionen(anlage, [])

    assert not [r for r in ergebnisse if _MELDUNG in r.meldung]


async def test_bkw_unter_der_schwelle_wird_nicht_genoergelt(db):
    """2 × 300 Wp = 600 W: keine Überbelegung zu erwarten ⇒ kein Hinweis."""
    anlage = await _anlage_mit_bkw(db, {"leistung_wp": 300, "anzahl": 2})

    ergebnisse = DatenChecker(db)._check_investitionen(anlage, [])

    assert not [r for r in ergebnisse if _MELDUNG in r.meldung]


async def test_genau_auf_der_schwelle_schweigt(db):
    """2 × 400 Wp = 800 W: nur ECHT darüber wird gemeldet."""
    anlage = await _anlage_mit_bkw(db, {"leistung_wp": 400, "anzahl": 2})

    ergebnisse = DatenChecker(db)._check_investitionen(anlage, [])

    assert not [r for r in ergebnisse if _MELDUNG in r.meldung]
