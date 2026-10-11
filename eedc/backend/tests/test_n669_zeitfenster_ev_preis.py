"""N-669 — Zeitfenster-Tarif (HT/NT): der Monat bewertet den Eigenverbrauch mit dem Preis seiner Stunden, wie der Tag.

**Der Fund** (Kandidat 32, Konzept Flex-Tarife A-2): ``aufgeloester_monatspreis`` lieferte in Stufe 3 (Zeitfenster) kein
``ev_cent`` — den EV-Ø gab es nur aus gemessenen Stundenpreisen. ``finanz_aggregat`` fiel deshalb auf den Bezugs-Ø zurück,
während der Tag (``lade_slot_kosten_je_tag``) den vermiedenen Bezug mit dem HT/NT-Preis seiner Stunde bewertet ⇒ Σ Tage ≠
Monat. Gemessen am HEAD 8b759a70: 12 kWh EV mittags (HT 30 ct), Bezug abends (NT 15 ct) ⇒ Monat 1,80 €, Σ Tage 3,60 €.

**Bauweg A1** (Entscheid Master 11.10.2026): der EV-Ø des Monats aus denselben Stundenzeilen und derselben Slot-Regel wie
der Tag (``strompreis_aggregator.ev_preis_zeitfenster_cent``); ohne Stundenzeilen bleibt der Rückfall auf den Bezugs-Ø.
Die Matrix-Form T4 (``test_achsen_matrix``, Größe ``geld``) prüft dasselbe über alle Monats-Sichten.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models.strompreis import StrompreisZeitfenster
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.strompreis_aggregator import aufgeloester_monatspreis, lade_slot_kosten_je_tag
from backend.tests import factories

TAGE = (date(2026, 7, 1), date(2026, 7, 2))


async def _anlage(db, *, stunden: bool):
    a = await factories.anlage(db)
    await db.flush()
    tarif = await factories.strompreis(db, a.id, date(2020, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                                       einspeiseverguetung_cent_kwh=8.0)
    # Slot 20 = 19–20 Uhr im NT.
    tarif.zeitfenster = [StrompreisZeitfenster(von_stunde=19, bis_stunde=20, arbeitspreis_cent_kwh=15.0,
                                               wochentage="0123456")]
    await db.commit()
    if stunden:
        for tag in TAGE:
            for slot in (11, 12, 13):   # mittags: PV 3, Einspeisung 1 ⇒ 2 kWh vermiedener Bezug zu 30 ct
                db.add(TagesEnergieProfil(anlage_id=a.id, datum=tag, stunde=slot, netzbezug_kw=0.0, pv_kw=3.0,
                                          einspeisung_kw=1.0))
            db.add(TagesEnergieProfil(anlage_id=a.id, datum=tag, stunde=20, netzbezug_kw=2.0, pv_kw=0.0,
                                      einspeisung_kw=0.0))
        await db.commit()
    return a, tarif


@pytest.mark.asyncio
async def test_monat_ev_preis_ist_der_der_vermiedenen_stunden(db):
    a, tarif = await _anlage(db, stunden=True)
    p = await aufgeloester_monatspreis(db, a.id, 2026, 7, None, tarif)
    assert (p.cent, p.herkunft, p.ev_cent) == (15.0, "zeitfenster", 30.0), p
    # Σ Tage = Monat: dieselben Zeilen, dieselbe Slot-Regel.
    je_tag = await lade_slot_kosten_je_tag(db, a.id, von=TAGE[0], bis=date(2026, 7, 31), tarif_fuer=lambda _t: tarif)
    tage = sum(sk.ev_mittel_cent * sk.ev_menge_kwh / 100 for sk in je_tag.values())
    assert round(tage, 2) == round(12.0 * p.ev_cent / 100, 2) == 3.6


@pytest.mark.asyncio
async def test_ohne_stundenzeilen_bleibt_der_rueckfall(db):
    a, tarif = await _anlage(db, stunden=False)
    p = await aufgeloester_monatspreis(db, a.id, 2026, 7, None, tarif)
    assert p.ev_cent is None, p
