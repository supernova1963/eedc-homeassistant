"""N-611 — der abgeschlossene Monat zählte ein Balkonkraftwerk doppelt, wenn ein Anlagen-PV-Wert die Lücken füllt.

Gemessen am 03.10.2026 über die echten Einstiege (Monats-Fakten, Cockpit → Monat, PV-Strings,
Daten-Checker): zwei Strings Süd 6 kWp / West 4 kWp, ein Balkonkraftwerk mit eigenem Wert
45 kWh und ein gepflegter Anlagen-PV-Wert von 1000 kWh ohne Stringwerte. Die Monats-Fakten
verteilten die vollen 1000 auf die Strings und addierten das BKW danach als eigene Zeile —
**1045**, während PV-Strings und Daten-Checker für denselben Monat 1000 nannten.

**Die eine Regel** (Bauplan N-611, Fassung 2; Entscheid Gernot: der Anlagenwert steht für
ALLE PV-Quellen): Bevor der Anlagenwert die Lücken der Module füllt, wird er um die eigenen
Werte der Balkonkraftwerke gemindert, die im Monat selbst tragen. Rest = max(0, Anlagenwert −
Σ eigene Werte), nach kWp auf die Module ohne eigenen Wert. Leseseite
(``pv_monatswerte.lade_pv_je_monat``) und Import-Vorschau rechnen dieselbe Zahl
(``eigene_bkw_erzeugung_kwh``); der Verteil-Schreibweg des Sammelimports (``_verteile_anlagen_pv``)
ist mit HA-Bauform E4b entfallen — der Import speichert den Zähler als Anlagenwert.

**Was bewusst bleibt, wie es ist** — und hier festgehalten, damit es niemand „mitrepariert":

* Ein BKW **ohne** eigenen Wert bekommt seinen Anteil nur, wo der Anlagenwert **gespeichert**
  ist — seit **N-621** (``test_n621_bkw_anteil_am_anlagenwert.py``; F5: 930 → 1000). Ohne
  gespeicherten Wert gibt es zur Lesezeit nichts zu verteilen. ⚑ Der HA-Statistik-Sammelimport
  speichert den Zähler seit HA-Bauform E4b als Anlagenwert (vorher verteilte er ihn auf die Module,
  F3 blieb 930) — ``n533=True`` sät deshalb jetzt den gespeicherten Anlagenwert 1000.
* Haben Import oder Connector die Modulwerte schon verteilt (Portal-Stand, Marke
  ``kwp_anteil``), sind sie eigene Werte; der Monat bleibt 1045 (**S2**).
* **Ohne Anlagenwert** läuft nichts davon — jede Zahl wie vorher (Fälle A, B, C, E und
  Tageswert-BKW). Das belegen die Proben unten, nicht der Golden Master: keine der Kopien
  trägt einen Anlagenwert.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.monats_fakten import lade_monats_fakten

J, M = 2025, 5
_MARKE = {"verbrauch_daten.pv_erzeugung_kwh": {
    "source": "portal_apply:x", "writer": "portal_apply:x", "abgeleitet": "kwp_anteil",
}}


async def _seed(db, *, s1=None, s2=None, bkw=None, bkw_daten=None, agg=None, marken=(), n533=False,
                tages_bkw=None, kinder=False, kind_ab=date(2024, 1, 1)):
    """Süd 6 kWp, West 4 kWp, Balkonkraftwerk 0,8 kWp; optional zwei Modul-Kinder am BKW (0,4 kWp)."""
    a = Anlage(anlagenname="N-611", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    sued = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Süd", leistung_kwp=6.0,
                       anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=6000.0)
    west = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="West", leistung_kwp=4.0,
                       anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=4000.0)
    balkon = Investition(anlage_id=a.id, typ="balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8,
                         anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=800.0)
    db.add_all([sued, west, balkon])
    await db.flush()
    ids = {"Süd": sued.id, "West": west.id, "Balkon": balkon.id}
    if kinder:
        for name in ("Kind1", "Kind2"):
            kind = Investition(anlage_id=a.id, typ="pv-module", bezeichnung=name, leistung_kwp=0.4,
                               parent_investition_id=balkon.id, anschaffungsdatum=kind_ab,
                               anschaffungskosten_gesamt=1.0)
            db.add(kind)
            await db.flush()
            ids[name] = kind.id
    if n533:
        # Der HA-Sammelimport seit E4b (Teil A): der Zähler 1000 steht als Anlagenwert in der Zählerzeile.
        agg = 1000.0
    db.add(Monatsdaten(anlage_id=a.id, jahr=J, monat=M, einspeisung_kwh=400.0, netzbezug_kwh=200.0,
                       pv_erzeugung_kwh=agg))
    for name, kwh in (("Süd", s1), ("West", s2)):
        if kwh is not None:
            db.add(InvestitionMonatsdaten(
                investition_id=ids[name], jahr=J, monat=M, verbrauch_daten={"pv_erzeugung_kwh": kwh},
                source_provenance=_MARKE if name in marken else None,
            ))
    if bkw_daten is not None or bkw is not None:
        db.add(InvestitionMonatsdaten(investition_id=balkon.id, jahr=J, monat=M,
                                      verbrauch_daten=bkw_daten if bkw_daten is not None else {"pv_erzeugung_kwh": bkw}))
    if tages_bkw is not None:
        db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(J, M, 3),
                                    komponenten_kwh={f"bkw_{balkon.id}": tages_bkw}))
    await db.commit()
    return a.id, ids


async def _fakt(db, aid, *, tageswerte=False):
    fakten = await lade_monats_fakten(db, aid, von=(J, M), bis=(J, M), inkl_nur_tageswerte=tageswerte)
    return next(f for f in fakten if (f.jahr, f.monat) == (J, M))


def _zahlen(fakt):
    e = fakt.erzeugung
    return (round(e.pv_kwh, 6), None if e.pv_module_kwh is None else round(e.pv_module_kwh, 6), round(e.bkw_kwh, 6))


def _je_modul(fakt, ids):
    namen = {v: k for k, v in ids.items()}
    return {namen[i]: (round(w.pv_erzeugung_kwh, 2), w.quelle) for i, w in fakt.erzeugung.pv_je_modul.items()}


# ── Ohne Anlagenwert: jede Zahl wie vor dem Bau ──────────────────────────────────────────────────


@pytest.mark.parametrize("seed, erwartet, je_modul_leer", [
    pytest.param(dict(s1=550.0, s2=380.0), (930.0, 930.0, 0.0), False, id="A-alle-Strings-BKW-ohne-Wert"),
    # N-626 (Gernot 04.10.2026): eine String-Lücke ohne Anlagenwert trägt nichts bei, der gemessene
    # String bleibt in der Summe — 595 / 550 / 45 (vor N-626: 45 / None / 45, N42). N-611 selbst
    # wirkt ohne Anlagenwert weiter nicht: kein Abzug, kein BKW-Anteil.
    pytest.param(dict(s1=550.0, bkw=45.0), (595.0, 550.0, 45.0), False, id="B-Stringluecke-BKW-45"),
    pytest.param(dict(bkw=45.0), (45.0, None, 45.0), True, id="C-keine-Strings-BKW-45"),
    pytest.param(dict(s1=550.0, s2=380.0, bkw_daten={"erzeugung_kwh": 45.0}), (975.0, 930.0, 45.0), False,
                 id="E-BKW-nur-Legacy-Schluessel"),
])
async def test_ohne_anlagenwert_bleibt_jede_zahl_wie_vorher(db, seed, erwartet, je_modul_leer):
    """Gemessen vor dem Bau auf `ca7bb065` mit denselben Seeds — die Zahlen sind die von damals (Fall B seit N-626
    mit der Teilsumme der vorhandenen Werte)."""
    aid, _ = await _seed(db, **seed)
    fakt = await _fakt(db, aid)
    assert _zahlen(fakt) == erwartet
    assert (fakt.erzeugung.pv_je_modul == {}) is je_modul_leer


async def test_ohne_anlagenwert_bleibt_der_tageswert_des_bkw_wie_vorher(db):
    """Ein BKW, das nur einen Tageswert hat (keine Monatszeile): ohne Tagesebene 930, mit 975 — wie vorher."""
    aid, _ = await _seed(db, s1=550.0, s2=380.0, tages_bkw=45.0)
    assert _zahlen(await _fakt(db, aid)) == (930.0, 930.0, 0.0)
    assert _zahlen(await _fakt(db, aid, tageswerte=True)) == (975.0, 930.0, 45.0)


# ── Mit Anlagenwert: das BKW mit eigenem Wert zählt einmal ───────────────────────────────────────


async def test_f4_der_anlagenwert_zaehlt_das_bkw_mit(db, monkeypatch):
    """F4: Anlagenwert 1000, keine Stringwerte, BKW 45 ⇒ 1000 (vorher 1045) — in jeder Sicht dieselbe Zahl."""
    aid, ids = await _seed(db, agg=1000.0, bkw=45.0)

    fakt = await _fakt(db, aid)
    assert _zahlen(fakt) == (1000.0, 955.0, 45.0)
    assert _je_modul(fakt, ids) == {"Süd": (573.0, "verteilt"), "West": (382.0, "verteilt")}

    import backend.api.routes.aktueller_monat as am

    async def _leer(*a, **k):
        return {}

    async def _leer_set(*a, **k):
        return set()
    for name in ("_collect_connector_data", "_collect_mqtt_inbound_data", "_collect_ha_statistics_data"):
        monkeypatch.setattr(am, name, _leer)
    monkeypatch.setattr(am, "_ha_heimlade_felder_mit_daten", _leer_set)
    monat = await am.get_aktueller_monat(anlage_id=aid, jahr=J, monat=M, db=db)
    assert (monat.pv_erzeugung_kwh, monat.eigenverbrauch_kwh) == (1000.0, 600.0)

    # Die Leser, die das BKW selbst in die Auflösung geben, nannten schon vorher 1000 — und bleiben dabei.
    from backend.api.routes.cockpit.pv_strings import get_pv_strings
    strings = await get_pv_strings(anlage_id=aid, jahr=J, db=db)
    je_string = {s.bezeichnung: [(round(w.ist_kwh, 2), w.ist_quelle) for w in s.monatswerte if w.monat == M]
                 for s in strings.strings}
    assert je_string == {"Süd": [(573.0, "verteilt")], "West": [(382.0, "verteilt")],
                         "Balkon": [(45.0, "gemessen")]}

    from backend.services.daten_checker._helpers import _CheckHelpers

    class _Helfer(_CheckHelpers):
        def __init__(self, db):
            self.db = db
    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == aid)
    )).scalar_one()
    assert (await _Helfer(db)._get_pv_erzeugung_map(anlage))[(J, M)] == pytest.approx(1000.0)


@pytest.mark.parametrize("seed, erwartet, je_modul", [
    pytest.param(dict(agg=1000.0, bkw_daten={"erzeugung_kwh": 45.0}), (1000.0, 955.0, 45.0),
                 {"Süd": (573.0, "verteilt"), "West": (382.0, "verteilt")}, id="F4-BKW-nur-Legacy-Schluessel"),
    pytest.param(dict(agg=1000.0, s1=550.0, bkw=45.0), (1000.0, 955.0, 45.0),
                 {"Süd": (550.0, "gemessen"), "West": (405.0, "verteilt")}, id="F4-ein-String-gemessen"),
])
async def test_der_abzug_liest_den_bkw_wert_wie_die_bkw_zeile(db, seed, erwartet, je_modul):
    """Abgezogen wird genau die Zahl, die `bau.py` als `bkw_erzeugung` wieder addiert — beide Schreibweisen."""
    aid, ids = await _seed(db, **seed)
    fakt = await _fakt(db, aid)
    assert _zahlen(fakt) == erwartet
    assert _je_modul(fakt, ids) == je_modul


async def test_ein_bkw_wert_ueber_dem_anlagenwert_klemmt_den_rest_bei_null(db):
    """Rest nie unter 0: BKW 1200 gegen Anlagenwert 1000 ⇒ Module 0, Monat = BKW-Wert."""
    aid, _ = await _seed(db, agg=1000.0, bkw=1200.0)
    assert _zahlen(await _fakt(db, aid)) == (1200.0, 0.0, 1200.0)


# ── Sammelimport (seit E4b gespeichert) und Portal-Stand (S2) ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("seed, erwartet", [
    # N-621 (04.10.2026): bis dahin 930 — der Anteil des BKW fiel heraus, weil kein Modul eine Lücke hatte.
    pytest.param(dict(agg=1000.0, s1=550.0, s2=380.0), (1000.0, 930.0, 0.0), id="F5-Anlagenwert-BKW-ohne-Wert"),
    # E4b Teil A: der Sammelimport speichert den Zähler — F3 rechnet jetzt wie F5 (bis dahin 930, „offen bis S1").
    pytest.param(dict(s1=550.0, s2=380.0, n533=True), (1000.0, 930.0, 0.0), id="F3-Zaehler-Sammelimport-BKW-ohne-Wert"),
])
async def test_ein_bkw_ohne_eigenen_wert_bekommt_den_anteil_nur_bei_gespeichertem_anlagenwert(db, seed, erwartet):
    """F5 (Anlagenwert gespeichert): das BKW bekommt den Rest 70 — Module 930, Monat 1000 (N-621). F3 (HA-Sammelimport):
    seit E4b steht der Zähler ebenfalls als Anlagenwert in der Zeile — dieselbe Zahl."""
    aid, _ = await _seed(db, **seed)
    assert _zahlen(await _fakt(db, aid)) == erwartet


@pytest.mark.parametrize("seed, erwartet", [
    # 1000 nach kWp auf Süd 6 · West 4 · BKW 0,8 ⇒ Module 1000 × 10/10,8.
    pytest.param(dict(n533=True), (1000.0, 925.925926, 0.0), id="F6a-keine-Strings"),
    # Rest 450 nach kWp auf West 4 · BKW 0,8 ⇒ West 375, BKW 75 ⇒ Module 550 + 375.
    pytest.param(dict(s1=550.0, n533=True), (1000.0, 925.0, 0.0), id="F6b-Sued-550"),
])
async def test_nach_dem_sammelimport_bekommt_ein_bkw_ohne_wert_seinen_anteil(db, seed, erwartet):
    """F6a/F6b: bis E4b verteilte der Sammelimport den Zähler nur auf die Module (1000 / 1000 / 0, das BKW 0). Seit E4b
    steht er als Anlagenwert in der Zeile, und das BKW ohne Wert teilt den Rest mit den Modul-Lücken (N-621)."""
    aid, _ = await _seed(db, **seed)
    assert _zahlen(await _fakt(db, aid)) == erwartet


async def test_schon_verteilte_modulwerte_sind_eigene_werte(db):
    """Portal-Stand (Modulwerte mit Marke `kwp_anteil` + BKW 45): bleibt 1045 — Import-Verteilung ist S2."""
    aid, _ = await _seed(db, agg=1000.0, s1=600.0, s2=400.0, bkw=45.0, marken=("Süd", "West"))
    assert _zahlen(await _fakt(db, aid)) == (1045.0, 1000.0, 45.0)


# ── Abtretung an Modul-Kinder (N-266) ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("seed, erwartet", [
    pytest.param(dict(kinder=True, s1=550.0, s2=380.0, bkw=930.0), (1860.0, 1860.0, 0.0),
                 id="K1-BKW-an-Kinder-ohne-Anlagenwert"),
    pytest.param(dict(kinder=True, s1=550.0, bkw=930.0, agg=2000.0), (2000.0, 2000.0, 0.0),
                 id="K2-BKW-an-Kinder-Anlagenwert-2000"),
    pytest.param(dict(kinder=True, kind_ab=date(2025, 9, 1), s1=550.0, s2=380.0, bkw=930.0),
                 (1860.0, 930.0, 930.0), id="K3-Kinder-spaeter-ohne-Anlagenwert"),
    pytest.param(dict(kinder=True, kind_ab=date(2025, 9, 1), bkw=930.0, agg=2000.0),
                 (2000.0, 1070.0, 930.0), id="K4-Kinder-spaeter-Anlagenwert-2000"),
])
async def test_abtretung(db, seed, erwartet):
    """K1–K3 wie vorher. K4 (Kinder erst später, das BKW trägt im Monat selbst): 2930 → 2000 — sein Wert
    mindert den Anlagenwert, weil es in DIESEM Monat nicht abgetreten hat (Zeitfilter vor Selektor, P11)."""
    aid, _ = await _seed(db, **seed)
    assert _zahlen(await _fakt(db, aid)) == erwartet


async def test_gemischte_historie_ein_monat_ohne_anlagenwert_bleibt_wie_vorher(db):
    """Die Abzugsdaten werden geladen, sobald IRGENDEIN Monat einen Anlagenwert trägt — ein Monat ohne eigenen
    Anlagenwert daneben bleibt unberührt von ihm: Mai (Süd 550, West Lücke, BKW 45, kein Anlagenwert) 595 / 550 / 45
    (seit N-626 die vorhandenen Werte; vorher 45 / None / 45), Juni (BKW 45, Anlagenwert 1000) 1000 / 955 / 45."""
    aid, ids = await _seed(db, s1=550.0, bkw=45.0)
    db.add(Monatsdaten(anlage_id=aid, jahr=J, monat=6, einspeisung_kwh=400.0, netzbezug_kwh=200.0,
                       pv_erzeugung_kwh=1000.0))
    db.add(InvestitionMonatsdaten(investition_id=ids["Balkon"], jahr=J, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 45.0}))
    await db.commit()

    fakten = {(f.jahr, f.monat): f for f in await lade_monats_fakten(db, aid, von=(J, 5), bis=(J, 6))}

    assert _zahlen(fakten[(J, 5)]) == (595.0, 550.0, 45.0)
    assert fakten[(J, 5)].erzeugung.pv_vollstaendig is False
    assert _zahlen(fakten[(J, 6)]) == (1000.0, 955.0, 45.0)
