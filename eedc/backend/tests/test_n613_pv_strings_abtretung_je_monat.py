"""N-613 — *Komponenten → PV-Strings*: die Abtretung eines Balkonkraftwerks gilt je Monat.

Seit N-266 darf ein Balkonkraftwerk Parent von `pv-module` sein; es tritt dann
Erzeugung und kWp an seine Kinder ab. ``cockpit/pv_strings.py`` wandte den
Selektor ``erzeuger_traeger`` bis 03.10.2026 **einmal über alle Investitionen**
an. Ein BKW, dem später Module zugeordnet wurden, hatte damit in KEINEM Monat
eine Zeile, und in den Monaten vor der Anschaffung der Kinder fehlte seine
Erzeugung (gemessen: Σ 930 gegen 1860 kWh der Monats-Fakten; mit Anlagenwert
1070 gegen 2000). Die Regel ist ADR-002/P11 in der Reihenfolge von N-386:
erst der Zeitfilter, dann der Selektor — wie in
``services/pv_monatswerte.py::lade_pv_je_monat``.

Gehalten wird:

1. Σ der Sicht je Monat = ``pv_kwh`` der Monats-Fakten (Jahr und Gesamtlaufzeit).
2. Das BKW hat eine eigene Zeile in den Jahren, in denen es selbst trägt.
3. Der kWp-Nenner der SOLL-Verteilung zählt BKW und Kinder nie zugleich.
4. Das saisonale Mittel zählt BKW und Kinder als EINEN Erzeuger (Jahre) und das
   Anlagen-SOLL nach der heutigen Zuordnung.
5. Ohne BKW mit später zugeordneten Kindern bleibt jede Zahl wie vorher — die
   Erwartungswerte unten sind am Stand ``2758a3af`` gemessen.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.cockpit.pv_strings import get_pv_strings, get_pv_strings_gesamtlaufzeit
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.monats_fakten import lade_monats_fakten

MAI_25 = (2025, 5)


async def _anlage(db, *, module=True, bkw=True, kinder_ab=None, werte=None, agg=None, kind_kwp=0.4) -> int:
    """Süd 6 + West 4 kWp, Balkonkraftwerk 0,8 kWp, optional zwei Kinder à 0,4 kWp.

    ``werte``: ``{(jahr, monat): {name: kWh}}``, ``agg``: Anlagenwert je Monat.
    PVGIS: 1000 kWh je Monat für die Anlage (ohne Modul-Prognosen ⇒ Verteilung
    nach kWp, also genau der Nenner, um den es geht).
    """
    a = Anlage(anlagenname="N613", leistung_kwp=10.8)
    db.add(a)
    await db.flush()
    ids: dict[str, int] = {}
    if module:
        for name, kwp in (("Süd", 6.0), ("West", 4.0)):
            inv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung=name, leistung_kwp=kwp,
                              anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=1.0)
            db.add(inv)
            await db.flush()
            ids[name] = inv.id
    if bkw:
        balkon = Investition(anlage_id=a.id, typ="balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8,
                             anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=1.0)
        db.add(balkon)
        await db.flush()
        ids["Balkon"] = balkon.id
        if kinder_ab is not None:
            for name in ("Kind 1", "Kind 2"):
                kind = Investition(anlage_id=a.id, typ="pv-module", bezeichnung=name, leistung_kwp=kind_kwp,
                                   parent_investition_id=balkon.id, anschaffungsdatum=kinder_ab,
                                   anschaffungskosten_gesamt=1.0)
                db.add(kind)
                await db.flush()
                ids[name] = kind.id
    for (j, m) in sorted(set(werte or {}) | set(agg or {})):
        db.add(Monatsdaten(anlage_id=a.id, jahr=j, monat=m, einspeisung_kwh=400.0, netzbezug_kwh=200.0,
                           pv_erzeugung_kwh=(agg or {}).get((j, m))))
        for name, kwh in (werte or {}).get((j, m), {}).items():
            db.add(InvestitionMonatsdaten(investition_id=ids[name], jahr=j, monat=m,
                                          verbrauch_daten={"pv_erzeugung_kwh": kwh}))
    db.add(PVGISPrognose(
        anlage_id=a.id, abgerufen_am=datetime(2025, 1, 1), latitude=48.0, longitude=11.0,
        neigung_grad=30.0, ausrichtung_grad=0.0, jahresertrag_kwh=12000.0,
        spezifischer_ertrag_kwh_kwp=1000.0, gesamt_leistung_kwp=12.0,
        monatswerte=[{"monat": m, "e_m": 1000.0} for m in range(1, 13)],
    ))
    await db.commit()
    return a.id


async def _fakten_je_monat(db, anlage_id) -> dict[tuple[int, int], float]:
    fakten = await lade_monats_fakten(db, anlage_id, von=(2024, 1), bis=(2026, 12))
    return {(f.jahr, f.monat): round(f.erzeugung.pv_kwh, 1) for f in fakten if f.erzeugung.pv_kwh}


def _summe_je_monat(resp) -> dict[int, float]:
    return {
        m: round(sum(s.monatswerte[m - 1].ist_kwh for s in resp.strings), 1)
        for m in range(1, 13)
        if any(s.monatswerte[m - 1].ist_kwh for s in resp.strings)
    }


def _zeilen(resp) -> dict[str, tuple]:
    return {s.bezeichnung: (round(s.prognose_jahr_kwh, 1), round(s.ist_jahr_kwh, 1)) for s in resp.strings}


# ── 1–3: die gemessenen Fälle K3/K4 und der Mehrmonatsfall ───────────────────

K3 = dict(kinder_ab=date(2025, 9, 1), werte={MAI_25: {"Süd": 550.0, "West": 380.0, "Balkon": 930.0}})
K4 = dict(kinder_ab=date(2025, 9, 1), werte={MAI_25: {"Balkon": 930.0}}, agg={MAI_25: 2000.0})
K3M = dict(kinder_ab=date(2025, 9, 1), werte={
    (2025, 5): {"Süd": 550.0, "West": 380.0, "Balkon": 70.0},
    (2025, 10): {"Süd": 300.0, "West": 200.0, "Kind 1": 30.0, "Kind 2": 30.0},
    (2026, 5): {"Süd": 560.0, "West": 390.0, "Kind 1": 35.0, "Kind 2": 35.0},
})
NUR_BKW_K = dict(module=False, kinder_ab=date(2025, 9, 1), werte={
    (2025, 5): {"Balkon": 70.0}, (2026, 5): {"Kind 1": 35.0, "Kind 2": 35.0},
})


@pytest.mark.parametrize("fall", [K3, K4, K3M, NUR_BKW_K], ids=["K3", "K4", "K3M", "nur-BKW-spaete-Kinder"])
async def test_summe_der_sicht_ist_je_monat_die_der_monats_fakten(db, fall):
    anlage_id = await _anlage(db, **fall)
    fakten = await _fakten_je_monat(db, anlage_id)
    for jahr in sorted({j for (j, _) in fakten}):
        resp = await get_pv_strings(anlage_id=anlage_id, jahr=jahr, db=db)
        soll = {m: v for (j, m), v in fakten.items() if j == jahr}
        assert _summe_je_monat(resp) == soll, (jahr, _summe_je_monat(resp), soll)
        assert round(resp.ist_gesamt_kwh, 1) == round(sum(soll.values()), 1)
    gesamt = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    assert round(gesamt.ist_gesamt_kwh, 1) == round(sum(fakten.values()), 1)


async def test_k3_balkonkraftwerk_hat_vor_den_kindern_eine_eigene_zeile(db):
    anlage_id = await _anlage(db, **K3)
    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2025, db=db)
    # SOLL je Zeile = 1000 × kWp / 10,8 — BKW und Kinder NIE zugleich im Nenner
    # (sonst 11,6 kWp: Süd 517,2 · West 344,8 · Balkon 69,0).
    assert _zeilen(resp) == {
        "Süd": (555.6, 550.0), "West": (370.4, 380.0), "Balkon": (74.1, 930.0),
        "Kind 1": (0.0, 0.0), "Kind 2": (0.0, 0.0),
    }
    assert [s.bezeichnung for s in resp.strings] == ["Süd", "West", "Balkon", "Kind 1", "Kind 2"]
    assert resp.anlagen_leistung_kwp == pytest.approx(10.8)
    assert resp.prognose_gesamt_kwh == pytest.approx(1000.0, abs=0.1)


async def test_der_monatsnenner_ist_der_der_menge_die_im_monat_traegt(db):
    """Kinder größer als das BKW (2 × 0,6 kWp gegen 0,8): im Mai 2025 trägt das BKW,
    der Nenner ist 6 + 4 + 0,8 = 10,8 — nicht die heutige Zuordnung 6 + 4 + 1,2 = 11,2."""
    anlage_id = await _anlage(db, **K3, kind_kwp=0.6)
    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2025, db=db)
    soll = {s.bezeichnung: round(s.prognose_jahr_kwh, 1) for s in resp.strings}
    assert soll == {"Süd": 555.6, "West": 370.4, "Balkon": 74.1, "Kind 1": 0.0, "Kind 2": 0.0}
    # Der Anlagen-Nenner der Kopfzeile bleibt die heutige Zuordnung.
    assert resp.anlagen_leistung_kwp == pytest.approx(11.2)
    gesamt = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    assert {s.bezeichnung: round(s.prognose_gesamt_kwh, 1) for s in gesamt.strings} == soll


async def test_k4_anlagenwert_und_balkonkraftwerk_ergeben_den_anlagenwert(db):
    anlage_id = await _anlage(db, **K4)
    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2025, db=db)
    ist = {s.bezeichnung: round(s.ist_jahr_kwh, 1) for s in resp.strings}
    assert ist == {"Süd": 642.0, "West": 428.0, "Balkon": 930.0, "Kind 1": 0.0, "Kind 2": 0.0}
    assert resp.ist_gesamt_kwh == pytest.approx(2000.0)


async def test_k3m_das_bkw_steht_nur_in_dem_jahr_in_dem_es_selbst_traegt(db):
    anlage_id = await _anlage(db, **K3M)
    j25 = await get_pv_strings(anlage_id=anlage_id, jahr=2025, db=db)
    j26 = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    assert "Balkon" in _zeilen(j25) and "Balkon" not in _zeilen(j26)
    assert _zeilen(j25)["Balkon"] == (74.1, 70.0)
    # Monats-SOLL des Mai: Süd + West + Balkon tragen 1000 (gerundet je Zeile).
    mai_soll = sum(s.monatswerte[4].prognose_kwh for s in j25.strings)
    assert mai_soll == pytest.approx(1000.0, abs=0.2)


@pytest.mark.parametrize("fall, erwartet", [
    (K3M, (1000.0, 1010.0, 2)),        # Mai: (1000 + 1020) / 2 Jahre
    (NUR_BKW_K, (1000.0, 70.0, 2)),    # Mai: (70 BKW 2025 + 70 Kinder 2026) / 2 Jahre
], ids=["K3M", "nur-BKW-spaete-Kinder"])
async def test_saisonales_mittel_zaehlt_bkw_und_kinder_als_einen_erzeuger(db, fall, erwartet):
    anlage_id = await _anlage(db, **fall)
    gesamt = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    mai = gesamt.saisonal_aggregiert[4]
    assert (round(mai.prognose_kwh, 1), round(mai.ist_durchschnitt_kwh, 1), mai.anzahl_jahre) == erwartet


# ── 5: ohne später zugeordnete Kinder bitgleich (Werte gemessen auf 2758a3af) ──

BITGLEICH = {
    "K1": (dict(kinder_ab=date(2024, 1, 1), werte={MAI_25: {"Süd": 550.0, "West": 380.0, "Balkon": 930.0}}),
           {"Süd": (555.6, 550.0), "West": (370.4, 380.0), "Kind 1": (37.0, 465.0), "Kind 2": (37.0, 465.0)},
           10.8, 1860.0, 1000.0, {5: (1000.0, 1860.0, 1)}),
    "K2": (dict(kinder_ab=date(2024, 1, 1), werte={MAI_25: {"Süd": 550.0, "Balkon": 930.0}}, agg={MAI_25: 2000.0}),
           {"Süd": (555.6, 550.0), "West": (370.4, 520.0), "Kind 1": (37.0, 465.0), "Kind 2": (37.0, 465.0)},
           10.8, 2000.0, 1000.0, {5: (1000.0, 2000.0, 1)}),
    "nur-BKW": (dict(module=False, werte={MAI_25: {"Balkon": 45.0}}),
                {"Balkon": (1000.0, 45.0)}, 0.8, 45.0, 1000.0, {5: (1000.0, 45.0, 1)}),
    "nur-Module": (dict(bkw=False, werte={MAI_25: {"Süd": 550.0, "West": 380.0}}),
                   {"Süd": (600.0, 550.0), "West": (400.0, 380.0)}, 10.0, 930.0, 1000.0, {5: (1000.0, 930.0, 1)}),
    "Module+BKW": (dict(werte={MAI_25: {"Süd": 550.0, "West": 380.0, "Balkon": 45.0}}),
                   {"Süd": (555.6, 550.0), "West": (370.4, 380.0), "Balkon": (74.1, 45.0)},
                   10.8, 975.0, 1000.0, {5: (1000.0, 975.0, 1)}),
}


@pytest.mark.parametrize("name", list(BITGLEICH))
async def test_ohne_spaete_kinder_bleibt_jede_zahl_wie_vorher(db, name):
    fall, zeilen, kwp, ist, soll, saison = BITGLEICH[name]
    anlage_id = await _anlage(db, **fall)
    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2025, db=db)
    assert _zeilen(resp) == zeilen
    assert [s.bezeichnung for s in resp.strings] == list(zeilen)
    assert (resp.anlagen_leistung_kwp, round(resp.ist_gesamt_kwh, 1), round(resp.prognose_gesamt_kwh, 1)) == (
        pytest.approx(kwp), ist, soll)
    gesamt = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    assert {s.bezeichnung: (round(s.prognose_gesamt_kwh, 1), round(s.ist_gesamt_kwh, 1)) for s in gesamt.strings} == zeilen
    assert {
        sw.monat: (round(sw.prognose_kwh, 1), round(sw.ist_durchschnitt_kwh, 1), sw.anzahl_jahre)
        for sw in gesamt.saisonal_aggregiert if sw.ist_summe_kwh
    } == saison
