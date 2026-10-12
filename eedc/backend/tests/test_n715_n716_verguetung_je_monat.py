"""N-715 + N-716 — die Hubs lesen die Einspeisevergütung je Monat aus den Monats-Fakten (eine Quelle, ADR-002/P8 + P10).

Gemessen am HEAD `0c3a89fa` (Allgemeintarif 30 ct, acht Monate 07/2025–02/2026; Speicher 100 kWh Entladung je Monat,
E-Auto 50 kWh V2H je Monat, Sonstiges-Erzeuger 40 kWh Einspeisung je Monat, Sonstiges-Speicher 100 kWh Entladung je
Monat). Werte in €:

| Fall | Vergütung je Monat (Monats-Fakten) | Speicher-Hub | Σ T-Konto Speicher | V2H (E-Auto-Hub) | Erlös Sonstiges-Erzeuger | Sonstiges-Speicher |
| --- | --- | --- | --- | --- | --- | --- |
| Lücke: Tarif ab 09/2025, Vergütung 6,0 | 8,2 · 8,2 · 6,0 × 6 | **192,00** | 187,60 | **96,00** | **19,20** | **192,00** |
| #392: Vergütung 8,0, Monatssatz 3,0 gepflegt | 3,0 × 8 | 216,00 | 216,00 | **88,00** | **25,60** | **176,00** |

N-715: vor dem ersten Tarif nahmen Speicher-, V2H- und Sonstiges-Hub die HEUTIGE Vergütung statt der Vorbelegung 8,2 ct
der Monats-Fakten. N-716: V2H- und Sonstiges-Hub übergingen den gepflegten Monatssatz der Vergütung (#392). Soll: alle
wie die Monats-Fakten (`TarifFakten.einspeiseverguetung_cent`, über `tarife_der_monate`) — Hub = Σ T-Konto.

Soll von Hand (Bezug 30 ct in allen Monaten — vor dem ersten Tarif die Vorbelegung 30):
  Lücke  Speicher 2 × 100 × (30 − 8,2) + 6 × 100 × (30 − 6) = 187,60 · V2H 100 × 21,8 + 300 × 24 = 93,80 ·
         Erlös 80 × 8,2 + 240 × 6 = 20,96
  #392   Speicher 800 × (30 − 3) = 216,00 · V2H 400 × 27 = 108,00 · Erlös 320 × 3 = 9,60

Der Wallbox-Hub liest keine Vergütung (nur die Bezugsseite) — er steht mit seiner Hand-Zahl daneben und darf sich
nicht bewegen.

Schwesterdateien: test_n712_n713_symmetrie_monatspreis.py (die Bezugsseite derselben Hubs, I1),
test_netto_ertrag_vier_wege_symmetrie.py.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

MONATE = [(2025, m) for m in range(7, 13)] + [(2026, 1), (2026, 2)]

#: (Tarif ab, Vergütung des Tarifs, Monatssatz #392) → (Speicher, V2H, Erlös Sonstiges-Erzeuger) von Hand.
FAELLE = {
    "luecke": ((date(2025, 9, 1), 6.0, None), (187.60, 93.80, 20.96)),
    "m392": ((date(2025, 7, 1), 8.0, 3.0), (216.00, 108.00, 9.60)),
}
#: Vergütung der Monats-Fakten je Monat (ct/kWh), von Hand.
VERGUETUNG = {
    "luecke": [8.2, 8.2] + [6.0] * 6,
    "m392": [3.0] * 8,
}


async def _anlage(db, fall):
    (ab, verg, satz), _ = FAELLE[fall]
    a = Anlage(anlagenname=f"N715 {fall}", leistung_kwp=10.0, installationsdatum=date(2025, 7, 1),
               standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=verg,
                      gueltig_ab=ab, verwendung="allgemein", anbieter="Werk", tarifname="Allgemein 30"))
    for j, m in MONATE:
        db.add(Monatsdaten(anlage_id=a.id, jahr=j, monat=m, einspeisung_kwh=200.0, netzbezug_kwh=150.0,
                           kraftstoffpreis_euro=1.80, einspeise_durchschnittspreis_cent=satz))
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV", anschaffungsdatum=date(2025, 7, 1),
                     anschaffungskosten_gesamt=12000.0, leistung_kwp=10.0)
    sp = Investition(anlage_id=a.id, typ="speicher", bezeichnung="SP", anschaffungsdatum=date(2025, 7, 1),
                     anschaffungskosten_gesamt=8000.0, parameter={"kapazitaet_kwh": 10.0})
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="EA", anschaffungsdatum=date(2025, 7, 1),
                     anschaffungskosten_gesamt=35000.0, anschaffungskosten_alternativ=30000.0, parameter={})
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2025, 7, 1),
                     anschaffungskosten_gesamt=1500.0, parameter={})
    erz = Investition(anlage_id=a.id, typ="sonstiges", bezeichnung="BHKW", anschaffungsdatum=date(2025, 7, 1),
                      anschaffungskosten_gesamt=5000.0, parameter={"kategorie": "erzeuger"})
    ssp = Investition(anlage_id=a.id, typ="sonstiges", bezeichnung="Kiste", anschaffungsdatum=date(2025, 7, 1),
                      anschaffungskosten_gesamt=3000.0, parameter={"kategorie": "speicher"})
    db.add_all([pv, sp, ea, wb, erz, ssp])
    await db.flush()
    for j, m in MONATE:
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=j, monat=m,
                                      verbrauch_daten={"pv_erzeugung_kwh": 500.0}))
        db.add(InvestitionMonatsdaten(investition_id=sp.id, jahr=j, monat=m,
                                      verbrauch_daten={"ladung_kwh": 110.0, "entladung_kwh": 100.0}))
        db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=j, monat=m, verbrauch_daten={
            "km_gefahren": 1000, "verbrauch_kwh": 180.0, "ladung_pv_kwh": 60.0, "ladung_netz_kwh": 90.0,
            "v2h_entladung_kwh": 50.0}))
        db.add(InvestitionMonatsdaten(investition_id=erz.id, jahr=j, monat=m, verbrauch_daten={
            "erzeugung_kwh": 100.0, "eigenverbrauch_kwh": 60.0, "einspeisung_kwh": 40.0}))
        db.add(InvestitionMonatsdaten(investition_id=ssp.id, jahr=j, monat=m,
                                      verbrauch_daten={"ladung_kwh": 110.0, "entladung_kwh": 100.0}))
    await db.commit()
    return a


@pytest.mark.asyncio
@pytest.mark.parametrize("fall", sorted(FAELLE))
async def test_verguetung_der_monats_fakten_je_monat(db, fall):
    """Die Quelle selbst: `tarife_der_monate` nennt je Monat die Vergütung von Hand (Vorbelegung bzw. Monatssatz)."""
    from backend.services.monats_fakten import tarife_der_monate

    a = await _anlage(db, fall)
    t = await tarife_der_monate(db, a.id, MONATE)
    assert [t[k].einspeiseverguetung_cent for k in MONATE] == VERGUETUNG[fall]


@pytest.mark.asyncio
@pytest.mark.parametrize("fall", sorted(FAELLE))
async def test_hubs_bewerten_die_verguetung_wie_die_monats_fakten(db, fall):
    from backend.api.routes import aktueller_monat as amr
    from backend.api.routes.investitionen.dashboard_eauto import get_eauto_dashboard
    from backend.api.routes.investitionen.dashboard_sonstiges import get_sonstiges_dashboard
    from backend.api.routes.investitionen.dashboard_speicher import get_speicher_dashboard

    _, (speicher_soll, v2h_soll, erloes_soll) = FAELLE[fall]
    a = await _anlage(db, fall)

    speicher_hub = (await get_speicher_dashboard(
        a.id, strompreis_cent=None, einspeiseverguetung_cent=None, db=db,
    ))[0].zusammenfassung["ersparnis_euro"]
    tkonto = 0.0
    for j, m in MONATE:
        r = await amr.get_aktueller_monat(anlage_id=a.id, jahr=j, monat=m, db=db)
        tkonto += sum(f.ersparnis_euro or 0.0 for f in r.investitionen_financials if f.typ == "speicher")
    eauto = (await get_eauto_dashboard(a.id, strompreis_cent=None, db=db))[0].zusammenfassung
    sonstige = {d.investition.bezeichnung: d.zusammenfassung
                for d in await get_sonstiges_dashboard(a.id, strompreis_cent=None, einspeiseverguetung_cent=None,
                                                       db=db)}

    ist = {
        "Speicher-Hub": speicher_hub,
        "Σ T-Konto Speicher": round(tkonto, 2),
        "V2H": eauto["v2h_ersparnis_euro"],
        "Erlös Sonstiges-Erzeuger": sonstige["BHKW"]["erloes_einspeisung_euro"],
        "Sonstiges-Speicher": sonstige["Kiste"]["ersparnis_euro"],
    }
    soll = {
        "Speicher-Hub": speicher_soll,
        "Σ T-Konto Speicher": speicher_soll,
        "V2H": v2h_soll,
        "Erlös Sonstiges-Erzeuger": erloes_soll,
        "Sonstiges-Speicher": speicher_soll,
    }
    abweichend = {k: (v, soll[k]) for k, v in ist.items() if v is None or v != pytest.approx(soll[k], abs=0.005)}
    assert not abweichend, f"{fall}: Sicht (ist, von Hand) {abweichend}"


@pytest.mark.asyncio
@pytest.mark.parametrize("fall", sorted(FAELLE))
async def test_gewichtete_monatspreise_tragen_die_verguetung_der_schicht(db, fall):
    """`_gewichtete_monatspreise` (V2H, Sonstiges): die Vergütungsseite ist der gewichtete Ø der Monats-Fakten — der
    Fallback (heutige Vergütung) nur ohne Gewichte."""
    from backend.api.routes.investitionen.dashboard_basis import _gewichtete_monatspreise

    a = await _anlage(db, fall)
    erg = await _gewichtete_monatspreise(
        db, a.id, "allgemein", {k: 1.0 for k in MONATE}, fallback_bezug=99.0, fallback_einspeise=99.0,
    )
    assert erg.einspeise_cent == pytest.approx(sum(VERGUETUNG[fall]) / len(MONATE)), (fall, erg.einspeise_cent)
    leer = await _gewichtete_monatspreise(db, a.id, "allgemein", {}, fallback_bezug=99.0, fallback_einspeise=77.0)
    assert (leer.bezug_cent, leer.einspeise_cent) == (99.0, 77.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("fall", sorted(FAELLE))
async def test_wallbox_hub_liest_keine_verguetung(db, fall):
    """Gegenprobe: der Wallbox-Hub bewertet nur bezogenen Strom — Heimladung 8 × 150 kWh zum Default-Preis extern
    (0,50 €/kWh, keine externe Ladung erfasst) minus Netzladung 8 × 90 kWh × 30 ct = 600 − 216 = 384,00 €, in beiden
    Fällen gleich."""
    from backend.api.routes.investitionen.dashboard_wallbox import get_wallbox_dashboard
    from backend.core.wirtschaftlichkeit_defaults import EXTERNE_LADUNG_DEFAULT_EURO_KWH

    a = await _anlage(db, fall)
    wb = (await get_wallbox_dashboard(a.id, strompreis_cent=None, db=db))[0].zusammenfassung
    assert wb["ersparnis_vs_extern_euro"] == pytest.approx(
        round(1200 * EXTERNE_LADUNG_DEFAULT_EURO_KWH - 720 * 0.30, 2), abs=0.005), wb
