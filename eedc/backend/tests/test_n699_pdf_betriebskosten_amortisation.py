"""N-699 (12.10.2026) — der Jahresbericht-PDF rechnet Betriebskosten, Netto, Rendite und Fortschritt wie die Sichten,
die sie definieren.

Gemessen vor dem Bau (HEAD ``fa4333fa``): der Bericht rechnete ``Σ Jahresbeträge × Monatszeilen ÷ 12`` (zwei erfasste
Monate ⇒ 120 statt 20 €, Speicher ab Juli ⇒ 240 statt 120 €, Speicher bis Ende 2024 im Gesamtzeitraum ⇒ 480 statt
240 €) und nannte als „Rendite" UND „Amortisations-Fortschritt" dieselbe Zahl ``(Netto − BK) ÷ Mehrkosten`` — ohne WP-
und E-Auto-Ersparnis im Zähler (PV + E-Auto gesamt 13,44 statt 27,8 %) und ohne die sonstigen Ausgaben im Nenner des
Fortschritts (16,9 % in Auswertungen → ROI). Cockpit → Jahr rundete die Betriebskosten je Monat auf Cent und summierte
(100 €/Jahr ⇒ 99,96 statt 100,00 €).

Entscheid Gernot 12.10.2026 (Option 1): die Laufzeit-Regel N-228 als EINE Layer-Funktion (ungerundet), die PDF-Rendite
aus ``get_cockpit_uebersicht(jahr)``, der Fortschritt im Gesamtzeitraum aus ``get_finanz_prognose``.

Im **Einzeljahr** ist der Fortschritt der Stand zum 31.12. des Berichtsjahres: ``get_finanz_prognose(stichtag=…)``
(Entscheid Master 12.10.2026 nach dem Halt im Bau: im Kapitaleinsatz nur die bis zum Stichtag angeschafften
Investitionen). Am HEAD stand dort ``(Netto − BK) ÷ Mehrkosten`` des Jahres (T1: 4,04 statt 6,4 %).

Schwesterdateien: test_b6_jahresbericht_symmetrie.py (WP-Kennzahlen PDF = Übersicht),
test_konzept_wirtschaftlichkeit_konformitaet.py (N-228 an ``get_finanz_prognose``),
test_ergebnis_symmetrie_monat_jahr.py (Monat ≡ Jahr).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

WP_PARAM = {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz", "waermebedarf_kwh": 12000.0, "jaz": 3.5,
            "alter_energietraeger": "gas", "alter_preis_cent_kwh": 12.0, "alternativ_zusatzkosten_jahr": 0.0}


def _m(jahre, monate=range(1, 13)):
    return [(j, m) for j in jahre for m in monate]


async def _seed(db, *, monate, pv_bk=0.0, extra=(), sonstige=None):
    a = Anlage(anlagenname="N699", leistung_kwp=6.0, installationsdatum=date(monate[0][0], monate[0][1], 1),
               standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
                      gueltig_ab=date(2020, 1, 1)))
    for j, m in monate:
        md = Monatsdaten(anlage_id=a.id, jahr=j, monat=m, einspeisung_kwh=300.0, netzbezug_kwh=150.0,
                         kraftstoffpreis_euro=1.80, gaspreis_cent_kwh=12.0)
        if sonstige and (j, m) == monate[0]:
            md.sonstige_positionen = sonstige
        db.add(md)
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV",
                     anschaffungsdatum=date(monate[0][0], monate[0][1], 1),
                     anschaffungskosten_gesamt=10000.0, leistung_kwp=6.0, betriebskosten_jahr=pv_bk)
    db.add(pv)
    await db.flush()
    for j, m in monate:
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=j, monat=m,
                                      verbrauch_daten={"pv_erzeugung_kwh": 500.0}))
    for typ, kw, imd in extra:
        inv = Investition(anlage_id=a.id, typ=typ, bezeichnung=typ, **kw)
        db.add(inv)
        await db.flush()
        for (j, m), d in imd.items():
            db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=j, monat=m, verbrauch_daten=d))
    await db.commit()
    return a.id


def _speicher(von: date, bis=None, bk=240.0, monate=()):
    kw = dict(anschaffungsdatum=von, anschaffungskosten_gesamt=6000.0, betriebskosten_jahr=bk,
              parameter={"kapazitaet_kwh": 10.0})
    if bis is not None:
        kw["stilllegungsdatum"] = bis
    return ("speicher", kw, {jm: {"ladung_kwh": 100.0, "entladung_kwh": 90.0} for jm in monate})


#: Einzeljahr: PDF = Cockpit → Jahr (Betriebskosten, Netto nach BK) = Cockpit → Übersicht (Rendite).
EINZELJAHR = {
    "X1_zwei_monate_erfasst": (dict(monate=_m((2026,), (1, 2)), pv_bk=120.0), 2026, 20.0),
    "X3_speicher_ab_juli": (dict(monate=_m((2025,)), extra=[_speicher(date(2025, 7, 1), monate=_m((2025,), range(7, 13)))]),
                            2025, 120.0),
    "BK100_rundung": (dict(monate=_m((2025,)), pv_bk=100.0), 2025, 100.0),
}

#: Gesamtzeitraum: PDF = Cockpit → Übersicht (Rendite) = Auswertungen → ROI (Fortschritt).
GESAMT = {
    "X2_speicher_bis_ende_2024": (dict(monate=_m((2024, 2025)), extra=[
        _speicher(date(2024, 1, 1), bis=date(2024, 12, 31), monate=_m((2024,)))]), 240.0),
    "W1_waermepumpe": (dict(monate=_m((2024, 2025)), extra=[
        ("waermepumpe", dict(anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=20000.0,
                             anschaffungskosten_alternativ=8000.0, parameter=WP_PARAM),
         {jm: {"heizenergie_kwh": 800.0, "warmwasser_kwh": 200.0, "stromverbrauch_kwh": 300.0}
          for jm in _m((2024, 2025))})]), 0.0),
    "W2_e_auto": (dict(monate=_m((2024, 2025)), extra=[
        ("e-auto", dict(anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=35000.0,
                        anschaffungskosten_alternativ=30000.0, parameter={}),
         {jm: {"km_gefahren": 1000, "verbrauch_kwh": 180.0, "ladung_pv_kwh": 60.0, "ladung_netz_kwh": 90.0}
          for jm in _m((2024, 2025))})]), 0.0),
    "S_sonstige_ausgabe": (dict(monate=_m((2024, 2025)), pv_bk=120.0,
                                sonstige=[{"bezeichnung": "Reparatur", "betrag": 500.0, "typ": "ausgabe"}]), 240.0),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("fall", sorted(EINZELJAHR))
async def test_einzeljahr_pdf_wie_cockpit_jahr_und_uebersicht(db, fall):
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.services.jahres_aggregat import baue_jahr
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    seed, jahr, bk_erwartet = EINZELJAHR[fall]
    aid = await _seed(db, **seed)
    k = (await build_jahresbericht_context(db, aid, jahr))["kpis"]
    kopf = (await baue_jahr(db, aid, jahr))["kopf"]
    u = await get_cockpit_uebersicht(anlage_id=aid, jahr=jahr, db=db)

    # Betriebskosten nach der Laufzeit-Regel, ungerundet — PDF und Cockpit → Jahr dieselbe Zahl.
    assert k["betriebskosten_zeitraum_euro"] == pytest.approx(bk_erwartet), fall
    assert kopf["betriebskosten_anteilig_euro"] == pytest.approx(k["betriebskosten_zeitraum_euro"]), fall
    assert k["netto_nach_bk_euro"] == pytest.approx(
        kopf["netto_ertrag_euro"] - kopf["betriebskosten_anteilig_euro"]), fall
    # Das Jahres-T-Konto (Σ der Zeilen je Investition) trägt dieselben Betriebskosten wie der Kopf.
    assert sum(f["betriebskosten_monat_euro"] for f in kopf["investitionen_financials"]) == pytest.approx(
        kopf["betriebskosten_anteilig_euro"]), fall
    # Rendite = Cockpit → Übersicht des Berichtsjahres, mit deren Nenner.
    assert k["rendite_prozent"] == u.jahres_rendite_prozent, fall
    assert k["rendite_nenner_euro"] == u.investition_mehrkosten_euro, fall
    # Fortschritt = ROI-Sicht zum 31.12. des Berichtsjahres.
    from backend.api.routes.aussichten.finanzen import get_finanz_prognose

    roi = await get_finanz_prognose(aid, monate=12, db=db, stichtag=date(jahr, 12, 31))
    assert k["amortisation_prozent"] == roi.amortisations_fortschritt_prozent, fall
    assert k["amortisation_kapitaleinsatz_euro"] == roi.kapitaleinsatz_euro, fall


_WP_2024_25 = ("waermepumpe", dict(anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=20000.0,
                                   anschaffungskosten_alternativ=8000.0, parameter=WP_PARAM),
               {jm: {"heizenergie_kwh": 800.0, "warmwasser_kwh": 200.0, "stromverbrauch_kwh": 300.0}
                for jm in _m((2024, 2025))})


@pytest.mark.asyncio
async def test_einzeljahr_fortschritt_ist_der_stand_zum_jahresende(db):
    """T1 (Halt-Messung 12.10.2026): Bericht 2024 einer Anlage mit Daten 2024–25 — der Fortschritt ist der einer
    Anlage, die nur die Daten bis 31.12.2024 kennt (6,4 %), nicht der von heute (12,8 %) und nicht der Jahresbeitrag
    ``(Netto − BK) ÷ Mehrkosten`` (4,04 %, HEAD)."""
    from backend.api.routes.aussichten.finanzen import get_finanz_prognose
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    aid = await _seed(db, monate=_m((2024, 2025)), pv_bk=120.0, extra=[_WP_2024_25])
    nur_2024 = (_WP_2024_25[0], _WP_2024_25[1], {jm: d for jm, d in _WP_2024_25[2].items() if jm[0] == 2024})
    aid_2024 = await _seed(db, monate=_m((2024,)), pv_bk=120.0, extra=[nur_2024])

    k = (await build_jahresbericht_context(db, aid, 2024))["kpis"]
    stand_2024 = await get_finanz_prognose(aid_2024, monate=12, db=db)
    heute = await get_finanz_prognose(aid, monate=12, db=db)

    assert k["amortisation_prozent"] == pytest.approx(6.4)
    assert k["amortisation_prozent"] == stand_2024.amortisations_fortschritt_prozent
    assert k["amortisation_kapitaleinsatz_euro"] == stand_2024.kapitaleinsatz_euro
    assert heute.amortisations_fortschritt_prozent == pytest.approx(12.8)  # Gegenanker: ohne Stichtag


@pytest.mark.asyncio
async def test_einzeljahr_fortschritt_kennt_spaeter_gekaufte_investition_nicht(db):
    """T2: PV 2024–25, E-Auto erst ab 01/2025 — der Stand 31.12.2024 teilt durch den Kapitaleinsatz OHNE das Auto
    (10.000 € ⇒ 10,1 %), Entscheid Master 12.10.2026 (Anschaffungsdatum ist die Grenze)."""
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    aid = await _seed(db, monate=_m((2024, 2025)), extra=[
        ("e-auto", dict(anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=35000.0,
                        anschaffungskosten_alternativ=30000.0, parameter={}),
         {jm: {"km_gefahren": 1000, "verbrauch_kwh": 180.0, "ladung_pv_kwh": 60.0, "ladung_netz_kwh": 90.0}
          for jm in _m((2025,))})])
    k = (await build_jahresbericht_context(db, aid, 2024))["kpis"]
    assert k["amortisation_kapitaleinsatz_euro"] == pytest.approx(10000.0)
    assert k["amortisation_prozent"] == pytest.approx(10.1)


@pytest.mark.asyncio
@pytest.mark.parametrize("fall", sorted(GESAMT))
async def test_gesamtzeitraum_pdf_wie_uebersicht_und_roi(db, fall):
    from backend.api.routes.aussichten.finanzen import get_finanz_prognose
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    seed, bk_erwartet = GESAMT[fall]
    aid = await _seed(db, **seed)
    k = (await build_jahresbericht_context(db, aid, None))["kpis"]
    u = await get_cockpit_uebersicht(anlage_id=aid, jahr=None, db=db)
    roi = await get_finanz_prognose(aid, monate=12, db=db)

    assert k["betriebskosten_zeitraum_euro"] == pytest.approx(bk_erwartet), fall
    assert k["rendite_prozent"] == u.jahres_rendite_prozent, fall
    assert k["amortisation_prozent"] == roi.amortisations_fortschritt_prozent, fall
    assert k["amortisation_kapitaleinsatz_euro"] == roi.kapitaleinsatz_euro, fall
    # Ohne WP und E-Auto ist „Netto nach BK" die Zeitraum-Bilanz der ROI-Sicht (Betriebskosten über die Laufzeit).
    if not u.wp_ersparnis_euro and not u.emob_ersparnis_euro:
        assert k["netto_nach_bk_euro"] == pytest.approx(roi.bisherige_ertraege_euro), fall


@pytest.mark.asyncio
async def test_finanz_prognose_ohne_rechnung_kippt_den_bericht_nicht(db, monkeypatch):
    """Rechnet die ROI-Sicht nicht, steht der Fortschritt als „–" — der Gesamtzeitraum-Bericht entsteht trotzdem, die
    Rendite der Übersicht steht da. Bis N-699 rechnete der Bericht diese Zeile selbst und brach deshalb dort nicht ab.

    Bis 12.10.2026 war die gemessene Lage eine PVGIS-Prognose mit fehlendem Monatswert (``e_m = None`` ⇒
    ``TypeError`` in ``finanz_prognose.py``). Der Handgriff L6 (``mw.get("e_m") or 0`` in ``finanz_eingaenge.py``)
    hat sie beseitigt — die Prognose rechnet jetzt (erster Teil). Der Schutz des Berichts gilt jeder Sicht, die
    wirft; er wird deshalb mit einer gestellten Ausnahme geprüft (zweiter Teil)."""
    from datetime import datetime

    from backend.api.routes.aussichten import finanzen as aussichten_finanzen
    from backend.api.routes.aussichten.finanzen import get_finanz_prognose
    from backend.models.pvgis_prognose import PVGISPrognose
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    aid = await _seed(db, monate=_m((2025,)), pv_bk=120.0)
    mw = [{"monat": m, "e_m": 500.0, "h_m": 100.0, "sd_m": 9.0} for m in range(1, 13)]
    mw[2]["e_m"] = None
    db.add(PVGISPrognose(anlage_id=aid, latitude=48.0, longitude=11.0, neigung_grad=30.0, ausrichtung_grad=0.0,
                         system_losses=14.0, jahresertrag_kwh=6000.0, spezifischer_ertrag_kwh_kwp=1000.0,
                         gesamt_leistung_kwp=6.0, monatswerte=mw, ist_aktiv=True,
                         abgerufen_am=datetime(2025, 1, 1, 12, 0)))
    await db.commit()
    p = await get_finanz_prognose(aid, monate=12, db=db)  # Handgriff L6: kein TypeError mehr
    assert p.amortisations_fortschritt_prozent is not None

    async def _wirft(*_a, **_k):
        raise TypeError("gestellt: die Sicht rechnet nicht")

    monkeypatch.setattr(aussichten_finanzen, "get_finanz_prognose", _wirft)
    k = (await build_jahresbericht_context(db, aid, None))["kpis"]
    assert k["amortisation_prozent"] is None
    assert k["amortisation_kapitaleinsatz_euro"] is None
    assert k["rendite_prozent"] is not None
