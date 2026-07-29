"""Cockpit-Finanzen: Monate vor der Pro-String-Umstellung zählen wieder mit.

`cockpit/uebersicht.py` wählte die PV-Quelle je Monat über ein **globales**
Flag: `use_inv_pv = pv_erzeugung_inv > 0`, danach
`pv_erzeugung_inv_by_ym.get(m_key, 0.0)`. Sobald IRGENDEIN Monat
InvestitionMonatsdaten hatte, stand damit für **alle anderen** Monate 0 in der
Finanzzeile — auch dort, wo ein Anlagen-Aggregat (`Monatsdaten.pv_erzeugung_kwh`)
gepflegt war.

Betroffen ist genau der Fall, für den das Aggregat existiert: eine Anlage, deren
Integration früher nur Gesamtwerte lieferte und die später auf Pro-String-Messung
umgestellt hat. Ihre Vorgeschichte fiel in Eigenverbrauchs-Ersparnis und
Netto-Ertrag auf 0. `ha_export.py` trug dieselbe Zeile ein zweites Mal
([[feedback_aggregations_drift]]); beide laden jetzt über
`services/pv_monatswerte.py`.

**Testschnitt:** zwei Anlagen mit **identischer Energie**, nur unterschiedlich
erfasst — einmal Januar als Anlagen-Aggregat, einmal Januar als gemessener
Pro-Modul-Wert. Beide müssen dieselben Euro liefern; die Buchführung darf das
Ergebnis nicht ändern. Vor dem Fix wich die Aggregat-Variante ab, weil ihr
Januar auf 0 fiel.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten


async def _anlage(db, name: str, *, januar_gemessen: bool) -> Anlage:
    """Jan + Feb je 800 kWh PV. Februar immer gemessen, Januar je nach Schalter.

    `januar_gemessen=False` bildet die Umstellungs-Anlage ab: der Januar liegt
    nur als Anlagen-Aggregat vor, der Februar bereits pro String.
    """
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
        leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=10000.0,
    )
    db.add(pv)
    await db.flush()

    for monat in (1, 2):
        gemessen = monat == 2 or januar_gemessen
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2026, monat=monat,
            einspeisung_kwh=300.0, netzbezug_kwh=100.0,
            # Aggregat nur dort, wo NICHT pro Modul gemessen wird — sonst wäre
            # es ohnehin wirkungslos (Messung hat Vorrang).
            pv_erzeugung_kwh=None if gemessen else 800.0,
        ))
        if gemessen:
            db.add(InvestitionMonatsdaten(
                investition_id=pv.id, jahr=2026, monat=monat,
                verbrauch_daten={"pv_erzeugung_kwh": 800.0},
            ))
    await db.flush()
    return anlage


@pytest.mark.asyncio
async def test_aggregat_januar_zaehlt_wie_ein_gemessener_januar(db):
    """Gleiche Energie, gleiche Euro — unabhängig von der Erfassungsform."""
    a_aggregat = await _anlage(db, "Umstellung", januar_gemessen=False)
    a_gemessen = await _anlage(db, "Referenz", januar_gemessen=True)
    await db.commit()

    r_agg = await get_cockpit_uebersicht(anlage_id=a_aggregat.id, jahr=None, db=db)
    r_gem = await get_cockpit_uebersicht(anlage_id=a_gemessen.id, jahr=None, db=db)

    assert r_agg.pv_erzeugung_kwh == pytest.approx(r_gem.pv_erzeugung_kwh)
    assert r_agg.ev_ersparnis_euro == pytest.approx(r_gem.ev_ersparnis_euro), (
        "der Aggregat-Januar fiel in der Finanzzeile auf 0, sobald der Februar "
        "gemessene Werte hatte"
    )
    assert r_agg.netto_ertrag_euro == pytest.approx(r_gem.netto_ertrag_euro)
