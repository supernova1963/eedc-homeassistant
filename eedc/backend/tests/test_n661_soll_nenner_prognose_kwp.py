"""N-661 (Weg C, Gernot 11.10.2026) — der SOLL-Nenner je String sind die kWp der aktiven Prognose.

Ohne Modul-Prognose verteilen *Komponenten → PV-Strings* (Gesamtlaufzeit), *Auswertungen → Prognose → PV-Strings*
(Jahr) und der Abschnitt „String-Vergleich" des Jahresbericht-PDF das Anlagen-SOLL nach kWp:
``SOLL = PVGIS × kWp_String / Nenner``. Die Prognose ist für die kWp gerechnet, die beim Abruf bestanden
(``PVGISPrognose.gesamt_leistung_kwp``); der Anteil an **diesen** kWp ist das SOLL. Bis dahin nahmen die
String-Sichten die Σ aller je vorhandenen Träger, das PDF die der im Berichtsjahr aktiven — und nannten für
dieselbe Zeile verschiedene Zahlen (gemessen am HEAD vor dem Bau, Bericht K3):

* **Zubau** (Ost 5 kWp ab 2026, Prognose für 15 kWp, Jahr 2025): PV-Strings Süd 5 112, PDF 7 668 (+50 %).
* **Stilllegung** (Ost 5 kWp still 31.12.2024, Prognose für 10 kWp, Jahr 2025): PV-Strings Süd 3 408 (−33 %),
  PDF 5 112.

Gehalten wird: in beiden Fällen nennen alle drei Sichten für Süd 5 112 kWh (852 kWh/kWp × 6 kWp). Der Rückfall ohne
Prognose-kWp (der frühere Nenner, je Monat der tragenden Menge) steht in den Schwesterdateien
``test_n613_pv_strings_abtretung_je_monat.py``, ``test_n614_jahresbericht_string_vergleich_je_monat.py`` und
``test_n616_jahresbericht_string_vergleich_monate_mit_wert.py``.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.cockpit.pv_strings import get_pv_strings, get_pv_strings_gesamtlaufzeit
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

D0 = date(2024, 1, 1)
#: 852 kWh/kWp im Jahr, ungleich über die Monate (1000 + 10·m bei 15 kWp).
E_M_JE_KWP = {m: (1000.0 + 10 * m) / 15.0 for m in range(1, 13)}


async def _anlage(db, *, ost_ab=D0, ost_still=None, prognose_kwp: float) -> int:
    a = Anlage(anlagenname="N661", leistung_kwp=15.0)
    db.add(a)
    await db.flush()
    ids = {}
    for name, kwp, ab, still in (("Süd", 6.0, D0, None), ("West", 4.0, D0, None), ("Ost", 5.0, ost_ab, ost_still)):
        inv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung=name, leistung_kwp=kwp,
                          anschaffungsdatum=ab, stilllegungsdatum=still, anschaffungskosten_gesamt=1.0)
        db.add(inv)
        await db.flush()
        ids[name] = inv.id
    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=m, einspeisung_kwh=300.0, netzbezug_kwh=200.0))
        for name in ("Süd", "West"):
            db.add(InvestitionMonatsdaten(investition_id=ids[name], jahr=2025, monat=m,
                                          verbrauch_daten={"pv_erzeugung_kwh": 500.0}))
    db.add(PVGISPrognose(
        anlage_id=a.id, abgerufen_am=datetime(2025, 1, 1), latitude=48.0, longitude=11.0,
        neigung_grad=30.0, ausrichtung_grad=0.0, jahresertrag_kwh=852.0 * prognose_kwp,
        spezifischer_ertrag_kwh_kwp=852.0, gesamt_leistung_kwp=prognose_kwp,
        monatswerte=[{"monat": m, "e_m": E_M_JE_KWP[m] * prognose_kwp} for m in range(1, 13)],
    ))
    await db.commit()
    return a.id


async def _soll_sued(db, aid) -> tuple[float, float, float]:
    jahr = await get_pv_strings(anlage_id=aid, jahr=2025, db=db)
    laufzeit = await get_pv_strings_gesamtlaufzeit(anlage_id=aid, db=db)
    ctx = await build_jahresbericht_context(db, aid, 2025)
    return (
        round(next(s.prognose_jahr_kwh for s in jahr.strings if s.bezeichnung == "Süd"), 1),
        round(next(
            w.prognose_kwh for s in laufzeit.strings if s.bezeichnung == "Süd" for w in s.jahreswerte if w.jahr == 2025
        ), 1),
        round(next(s["prognose_kwh"] for s in ctx["string_vergleiche"] if s["bezeichnung"] == "Süd"), 1),
    )


@pytest.mark.asyncio
async def test_zubau_nach_dem_jahr_alle_sichten_5112(db):
    """Ost kommt 2026 dazu, die aktive Prognose ist für 15 kWp: 2025 trägt Süd 6/15 davon."""
    aid = await _anlage(db, ost_ab=date(2026, 1, 1), prognose_kwp=15.0)
    assert await _soll_sued(db, aid) == (5112.0, 5112.0, 5112.0)


@pytest.mark.asyncio
async def test_stilllegung_vor_dem_jahr_alle_sichten_5112(db):
    """Ost ist seit 31.12.2024 still, die aktive Prognose ist für 10 kWp: 2025 trägt Süd 6/10 davon."""
    aid = await _anlage(db, ost_still=date(2024, 12, 31), prognose_kwp=10.0)
    assert await _soll_sued(db, aid) == (5112.0, 5112.0, 5112.0)


# ── N-683 · N-684 (K8, 11.10.2026): derselbe Stilllegungs-Fall, das saisonale Mittel und die Warnung ──────────────

def _saison(laufzeit, name=None) -> dict[int, float]:
    werte = (laufzeit.saisonal_aggregiert if name is None
             else next(s.saisonalwerte for s in laufzeit.strings if s.bezeichnung == name))
    return {w.monat: round(w.prognose_kwh, 1) for w in werte}


@pytest.mark.asyncio
async def test_n683_saisonales_mittel_nur_ueber_aktive_monate(db):
    """N-683 (Fachentscheid Master): je String nur die Monate, in denen er aktiv war; die Anlagen-Zeile ist je Monat
    die Σ der dann aktiven Strings. Ost still seit 31.12.2024, Prognose für 10 kWp: Süd Juni 424,0 (vorher 282,7 =
    6/15), das Jahr der Saisonwerte = der Jahreswert derselben Sicht (5 112), Anlage Juni 706,7 = PVGIS-Juni der
    10 kWp (nicht 1 060 mit dem stillgelegten Ost), Ost ohne aktiven Monat ohne Saisonal-SOLL."""
    aid = await _anlage(db, ost_still=date(2024, 12, 31), prognose_kwp=10.0)
    laufzeit = await get_pv_strings_gesamtlaufzeit(anlage_id=aid, db=db)
    jahr = await get_pv_strings(anlage_id=aid, jahr=2025, db=db)
    sued = _saison(laufzeit, "Süd")
    assert sued[6] == 424.0
    assert sued[6] == next(s.monatswerte[5].prognose_kwh for s in jahr.strings if s.bezeichnung == "Süd")
    assert round(sum(sued.values()), 0) == 5112.0
    assert _saison(laufzeit)[6] == 706.7
    assert set(_saison(laufzeit, "Ost").values()) == {0.0}


@pytest.mark.asyncio
async def test_n683_ohne_stilllegung_bleibt_das_saisonale_mittel(db):
    """Gegenrichtung: alle drei Strings aktiv, Prognose für 15 kWp — Süd Juni 424,0 und Anlage Juni 1 060,0 wie vorher."""
    aid = await _anlage(db, prognose_kwp=15.0)
    laufzeit = await get_pv_strings_gesamtlaufzeit(anlage_id=aid, db=db)
    assert (_saison(laufzeit, "Süd")[6], _saison(laufzeit)[6]) == (424.0, 1060.0)


@pytest.mark.asyncio
async def test_n684_warnung_vergleicht_gegen_die_heute_aktiven_strings(db):
    """N-684: nach der Stilllegung passt die 10-kWp-Prognose zu den heute aktiven 10 kWp — keine Warnung, in beiden
    Endpunkten. Gegenrichtung Zubau ohne neuen Abruf (Ost aktiv seit 2025, Prognose 10 kWp): die Warnung bleibt und
    nennt die heutigen 15,0 kWp."""
    still = await _anlage(db, ost_still=date(2024, 12, 31), prognose_kwp=10.0)
    assert (await get_pv_strings(anlage_id=still, jahr=2025, db=db)).prognose_warnung is None
    assert (await get_pv_strings_gesamtlaufzeit(anlage_id=still, db=db)).prognose_warnung is None
    zubau = await _anlage(db, ost_ab=date(2025, 1, 1), prognose_kwp=10.0)
    for antwort in (await get_pv_strings(anlage_id=zubau, jahr=2025, db=db),
                    await get_pv_strings_gesamtlaufzeit(anlage_id=zubau, db=db)):
        assert antwort.prognose_warnung is not None and "15.0 kWp" in antwort.prognose_warnung
