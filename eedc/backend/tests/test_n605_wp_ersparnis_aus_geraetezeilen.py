"""N-605 — die Wärmepumpen-Ersparnis des Monats ist die Σ der WP-Zeilen des T-Kontos (Bauform G20-2).

Bis 03.10.2026 nahmen Kachel und Ergebnis-Leiter ein Aggregat über die Summenmengen mit dem Parametersatz der ERSTEN
Wärmepumpe, das T-Konto rechnete je Gerät mit dessen Parametern. Gemessen an der r28-Kopie (P8 des Baus
„Ergebnisgrößen"): 43 Monate, Σ 1 117,02 €; 2026-02: T-Konto 114,37 € gegen Kachel 78,82 €.

Fixture: zwei Wärmepumpen mit VERSCHIEDENEM Preis der Altheizung (10 ct und 16 ct/kWh), gleiche Mengen, Juni 2024 und
Juni 2025. Ein Aggregat mit dem ersten Parametersatz gäbe beiden Geräten 10 ct — die Σ der Zeilen nicht.

Schwesterdateien: test_g20_emob_aggregat_symmetrie.py (dieselbe Bauform für die E-Mobilität),
test_wp_ersparnis_grundmenge_n279.py.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten


async def _anlage(db) -> int:
    a = Anlage(anlagenname="Zwei WP", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, gueltig_ab=date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0))
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1))
    wps = [
        Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung=f"WP {p}", anschaffungsdatum=date(2024, 1, 1),
                    parameter={"alter_energietraeger": "gas", "alter_preis_cent_kwh": p})
        for p in (10.0, 16.0)
    ]
    db.add_all([pv, *wps])
    await db.flush()
    for jahr in (2024, 2025):
        db.add(Monatsdaten(anlage_id=a.id, jahr=jahr, monat=6, einspeisung_kwh=300.0, netzbezug_kwh=200.0))
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=jahr, monat=6,
                                      verbrauch_daten={"pv_erzeugung_kwh": 800.0}))
        for wp in wps:
            db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=jahr, monat=6, verbrauch_daten={
                "heizenergie_kwh": 900.0, "warmwasser_kwh": 0.0, "stromverbrauch_kwh": 250.0,
            }))
    await db.commit()
    return a.id


def _wp_zeilen(d):
    return [z for z in d.investitionen_financials if z.typ == "waermepumpe" and z.ersparnis_euro is not None]


@pytest.mark.asyncio
async def test_kachel_ist_die_summe_der_geraetezeilen(db):
    aid = await _anlage(db)
    d = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=6, db=db)
    zeilen = _wp_zeilen(d)
    assert len(zeilen) == 2
    assert zeilen[0].ersparnis_euro != pytest.approx(zeilen[1].ersparnis_euro), "Fixture: verschiedene Parameter"
    assert d.wp_ersparnis_euro == pytest.approx(sum(z.ersparnis_euro for z in zeilen), abs=0.01)
    # Die Herleitung nennt beide Geräte.
    assert "WP 10.0" in (d.wp_ersparnis_berechnung or "") and "WP 16.0" in (d.wp_ersparnis_berechnung or "")
    # Und die Leiter rechnet mit derselben Zahl.
    werte = {w["name"]: w["betrag_euro"] for w in d.ergebnis_herleitung.model_dump()["ergebnis"]["eingesetzte_werte"]} \
        if hasattr(d.ergebnis_herleitung, "model_dump") else {
            w.name: w.betrag_euro for w in d.ergebnis_herleitung.ergebnis.eingesetzte_werte}
    assert werte["WP-Ersparnis"] == pytest.approx(d.wp_ersparnis_euro, abs=0.01)


@pytest.mark.asyncio
async def test_vorjahr_folgt_derselben_regel(db):
    aid = await _anlage(db)
    d = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=6, db=db)
    vj = d.vorjahr if isinstance(d.vorjahr, dict) else d.vorjahr.model_dump()
    d24 = await get_aktueller_monat(anlage_id=aid, jahr=2024, monat=6, db=db)
    assert vj["wp_ersparnis_euro"] == pytest.approx(d24.wp_ersparnis_euro, abs=0.01)
    assert vj["wp_ersparnis_euro"] == pytest.approx(d.wp_ersparnis_euro, abs=0.01), "gleiche Mengen, gleiche Preise"
