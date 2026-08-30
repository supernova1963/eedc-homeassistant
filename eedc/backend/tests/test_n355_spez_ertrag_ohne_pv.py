"""N-355: Ohne gemessene PV-Zahl gibt es keinen spezifischen Ertrag — auch keine 0.

**Der Befund**, gefunden beim Bau des Monatsberichts (#395): `aktueller_monat.py`
reichte ``pv or 0`` in ``spezifischer_ertrag_kwh_kwp`` hinein. Der Helfer prüfte
nur den **Nenner** (`leistung_kwp`), nahm die 0 als Zähler und lieferte
``0.0``. Ein Monat, für den keine PV-Zahl vorliegt, bekam damit
**„0,0 kWh/kWp"** — eine Zahl, die wie eine Messung aussieht, direkt neben einer
PV-Erzeugung „—".

Das ist genau die Lage, für die die Anzeige-Doktrin *unterdrücken* vorschreibt:
**nie gemessen ⇒ kein Wert**. Sie gilt aber nur, wenn die Schicht darunter die
Lücke auch als Lücke ausliefert — hier tat sie es nicht.

**Warum die Ursache im Helfer sitzt und nicht nur am Aufruf:** Eine Division
braucht **beide** Operanden. Ein Helfer, der nur den Nenner prüft, verlässt sich
darauf, dass jeder Aufrufer den Zähler selbst absichert — und genau dieser
Aufrufer tat es mit ``or 0`` in die falsche Richtung.

⚠ **Die Gegenrichtung steht in `test_kennzahlen.py`**: eine **gemessene** 0
(die Anlage hat nachweislich nichts geliefert) bleibt 0. Ohne sie wäre der Fix
auch dann grün, wenn er jede Null unterdrückt.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten

JAHR, MONAT = 2026, 4


async def _seed(db, *, mit_pv_wert: bool) -> int:
    """Anlage mit einem PV-Modul und einer Zählerzeile im April 2026.

    ``mit_pv_wert=False`` ist der Befund-Fall: Der Monat trägt Netzbezug und
    Einspeisung, aber **keinen** PV-Wert. Die Anlage hat trotzdem kWp — der
    Nenner ist also da, und nur deshalb kam überhaupt eine Zahl heraus.
    """
    anlage = Anlage(anlagenname="N-355", leistung_kwp=10.0,
                    standort_plz="10115", latitude=52.5, longitude=13.4)
    db.add(anlage)
    await db.flush()

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süddach",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True, leistung_kwp=10.0,
        anschaffungskosten_gesamt=15000.0,
    )
    db.add(pv)
    await db.flush()

    db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=MONAT,
                       netzbezug_kwh=180.0, einspeisung_kwh=520.0))
    if mit_pv_wert:
        db.add(InvestitionMonatsdaten(
            investition_id=pv.id, jahr=JAHR, monat=MONAT,
            verbrauch_daten={"pv_erzeugung_kwh": 900.0},
        ))
    await db.commit()
    return anlage.id


@pytest.mark.asyncio
async def test_ohne_pv_wert_kein_spezifischer_ertrag(db):
    """Der Befund: `0.0` sah aus wie eine Messung. Jetzt ist es `None`."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage_id = await _seed(db, mit_pv_wert=False)
    d = await get_aktueller_monat(anlage_id, JAHR, MONAT, db)

    # Die Voraussetzung des Befunds — sonst prüft die Probe einen anderen Fall:
    # keine PV-Zahl, aber ein vorhandener Nenner.
    assert d.pv_erzeugung_kwh is None
    assert d.spez_ertrag is None


@pytest.mark.asyncio
async def test_mit_pv_wert_bleibt_die_zahl_stehen(db):
    """Gegenrichtung: Der Fix darf den spezifischen Ertrag nicht generell kosten."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage_id = await _seed(db, mit_pv_wert=True)
    d = await get_aktueller_monat(anlage_id, JAHR, MONAT, db)

    assert d.pv_erzeugung_kwh == pytest.approx(900.0)
    assert d.spez_ertrag == pytest.approx(90.0)   # 900 kWh ÷ 10 kWp
