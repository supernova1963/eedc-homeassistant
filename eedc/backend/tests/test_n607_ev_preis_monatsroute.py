"""N-607 — Cockpit → Monat bewertet die Eigenverbrauchs-Ersparnis mit dem Preis der VERMIEDENEN Stunden (A-2).

SOLL Flex-Tarife A-2 (`docs/KONZEPT-FLEX-TARIFE.md`, gebaut 18.09.2026 für die Monats-Fakten): Eigenverbrauch ersetzt
Bezug zu den Stunden, in denen er anfällt — bewertet wird mit dem EV-gewichteten Ø der gemessenen Stundenpreise. Die
Monatsroute nahm bis 03.10.2026 den bezugsgewichteten Ø; gemessen im Bau „Ergebnisgrößen" (P13) und am Altstand
v4.1.1 identisch: Monat 160,00 € gegen Übersicht und Monatsreihe 40,00 €.

Fixture: Juli 2024 und Juli 2025, jede Stunde mit Preis — 10–15 Uhr 10 ct (PV 5 kW, Einspeisung 3 kW, kein Bezug), sonst
40 ct (Bezug 0,5 kW). Zähler: EV 400 kWh, Netzbezug 200 kWh. Erwartet: EV-Ersparnis 400 × 10 ct = 40,00 €, die
Stromrechnung bleibt beim Bezugspreis (200 × 40 ct + 10 € = 90,00 €).

Schwesterdateien: test_preis_aggregat_symmetrie.py (die Messung), test_ergebnis_symmetrie_monat_jahr.py (W3).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.tests.slot_saat import tep_zeilen


async def _anlage(db) -> int:
    a = Anlage(anlagenname="Flex", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, gueltig_ab=date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=10.0))
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1))
    db.add(pv)
    await db.flush()
    stunden = []
    for jahr in (2024, 2025):
        db.add(Monatsdaten(anlage_id=a.id, jahr=jahr, monat=7, einspeisung_kwh=600.0, netzbezug_kwh=200.0))
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=jahr, monat=7,
                                      verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
        for tag in range(1, 32):
            for h in range(24):
                mittag = 10 <= h <= 15
                stunden.append({"datum": date(jahr, 7, tag), "stunde": h,
                                "strompreis_cent": 10.0 if mittag else 40.0,
                                "netzbezug_kw": 0.0 if mittag else 0.5,
                                "pv_kw": 5.0 if mittag else 0.0, "einspeisung_kw": 3.0 if mittag else 0.0})
    db.add_all(tep_zeilen(a.id, stunden))
    await db.commit()
    return a.id


@pytest.mark.asyncio
async def test_monat_bewertet_den_eigenverbrauch_mit_dem_preis_der_vermiedenen_stunden(db):
    aid = await _anlage(db)
    m = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=7, db=db)
    assert m.eigenverbrauch_kwh == pytest.approx(400.0)
    assert m.ev_ersparnis_euro == pytest.approx(40.0), "bezugsgewichtet wären es 160,00 € (N-607)"
    assert m.ev_preis_cent == pytest.approx(10.0)
    assert m.ev_preis_herkunft == "ev_gemessen"
    # Die Stromrechnung bleibt beim Bezugspreis (40 ct gemessen) + Grundpreis.
    assert m.netzbezug_preis_effektiv_cent == pytest.approx(40.0)
    assert m.netzbezug_kosten_euro == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_monat_uebersicht_und_monatsreihe_nennen_dieselbe_ersparnis(db):
    aid = await _anlage(db)
    m = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=7, db=db)
    ue = await get_cockpit_uebersicht(anlage_id=aid, jahr=2025, db=db)
    reihe = [z if isinstance(z, dict) else z.model_dump()
             for z in await list_monatsdaten_aggregiert(anlage_id=aid, jahr=2025, db=db)]
    assert len(reihe) == 1
    assert reihe[0]["ev_ersparnis_euro"] == pytest.approx(m.ev_ersparnis_euro, abs=0.01)
    assert m.netto_ertrag_euro == pytest.approx(ue.netto_ertrag_euro, abs=0.01) == pytest.approx(88.0)
    assert reihe[0]["netto_ertrag_euro"] == pytest.approx(m.netto_ertrag_euro, abs=0.01)


@pytest.mark.asyncio
async def test_vorjahr_folgt_derselben_regel(db):
    aid = await _anlage(db)
    m = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=7, db=db)
    vj = m.vorjahr if isinstance(m.vorjahr, dict) else m.vorjahr.model_dump()
    assert vj["ev_ersparnis_euro"] == pytest.approx(40.0)
    assert vj["netto_ertrag_euro"] == pytest.approx(m.netto_ertrag_euro, abs=0.01)


@pytest.mark.asyncio
async def test_n608_vorjahr_bezugspreis_aus_derselben_kaskade(db):
    """N-608: der Vorjahresmonat holt seinen Bezugspreis über `aufgeloester_monatspreis` (gepflegt → gemessen →
    Zeitfenster → Stamm) wie der Monat selbst. Bis 03.10.2026 fehlte ihm die Stufe „gemessen": Juli 2024 als Vorjahr
    70,00 € Stromrechnung (Stamm 30 ct) gegen 90,00 € direkt (gemessen 40 ct), Ergebnis 18,00 € gegen −2,00 €."""
    aid = await _anlage(db)
    m = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=7, db=db)
    vj = m.vorjahr if isinstance(m.vorjahr, dict) else m.vorjahr.model_dump()
    direkt = await get_aktueller_monat(anlage_id=aid, jahr=2024, monat=7, db=db)
    assert direkt.netzbezug_kosten_euro == pytest.approx(90.0)
    assert vj["netzbezug_kosten_euro"] == pytest.approx(direkt.netzbezug_kosten_euro)
    assert direkt.ergebnis_euro == pytest.approx(-2.0)
    assert vj["ergebnis_euro"] == pytest.approx(direkt.ergebnis_euro)


@pytest.mark.asyncio
async def test_n607_bkw_zeile_im_t_konto_traegt_den_ev_preis(db):
    """Die Balkonkraftwerk-Zeile des T-Kontos ist ein Teil der Eigenverbrauchs-Ersparnis (sie wird dort herausgeschnitten)
    und trägt deshalb denselben Preis — den EV-gewichteten (10 ct), nicht den Bezugs-Ø (40 ct). Nachmessung C5:
    bis dahin ungesichert (`_p = netz_p` blieb grün)."""
    aid = await _anlage(db)
    bkw = Investition(anlage_id=aid, typ="balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8,
                      anschaffungsdatum=date(2024, 1, 1))
    db.add(bkw)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2025, monat=7, verbrauch_daten={"pv_erzeugung_kwh": 50.0}))
    await db.commit()
    m = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=7, db=db)
    zeile = next(z for z in m.investitionen_financials if z.typ == "balkonkraftwerk")
    assert m.ev_preis_cent == pytest.approx(10.0)
    assert zeile.ersparnis_euro == pytest.approx(5.0), "50 kWh × 10 ct — mit dem Bezugs-Ø wären es 20,00 €"
    assert "vermiedenen Stunden" in (zeile.formel or "")
