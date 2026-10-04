"""N-621 — ein Balkonkraftwerk ohne eigenen Wert bekommt seinen Anteil am GESPEICHERTEN Anlagen-PV-Wert.

Gemessen am 04.10.2026 über die produktiven Einstiege (Cockpit → Monat/Übersicht/Jahr, Auswertungen → Tabelle,
Jahresbericht-PDF, Komponenten → PV-Strings, HA-Export, Community, Import-Vorschau): zwei Strings Süd 6 kWp / West
4 kWp mit 550 + 380 kWh, ein Balkonkraftwerk 0,8 kWp ohne eigenen Wert und ein gespeicherter Anlagen-PV-Wert von
1000 kWh. Die Monats-Fakten nannten **930** — der Anteil des Balkonkraftwerks fiel heraus, weil kein Modul eine
Lücke hatte, die den Rest aufnahm —, während PV-Strings, Daten-Checker, der String-Abschnitt des PDFs und der
Monat ohne Abschluss **1000** nannten. Die Zahl sprang beim Monatsabschluss.

**Die Regel** (Bauplan N-621, Entscheid Gernot 04.10.): in einem Monat MIT gespeichertem Anlagenwert ist ein
selbst tragendes Balkonkraftwerk ohne eigenen Wert eine Lücke wie ein Modul ohne Wert. Der Rest (Anlagenwert − Σ
eigene Werte aller Quellen, nie unter 0) geht nach kWp auf alle Lücken; der BKW-Anteil steht in
``ErzeugungFakten.bkw_aus_anlagenwert_kwh`` und additiv in ``pv_kwh``. Dazu: kein Ersatz-Eigenverbrauch (P9) und kein
Tageswert neben dem Anteil, Gewicht über ``get_erzeuger_kwp`` (auch ``leistung_wp × anzahl``), und ein Monat mit
Anteil „hat PV" in Tabelle und Übersicht.

**Ohne Anlagenwert** läuft nichts davon (Kandidatenregel) — die Bitgleichheit der Fälle A/B/C/E/Tageswert hält
``test_n611_anlagenwert_alle_pv_quellen.py``, die gemischte Historie steht unten. **Ausnahme bleibt** der
HA-Statistik-Sammelimport ohne gespeicherten Zähler (F3, 930): dort gibt es zur Lesezeit keinen Anlagenwert
(HA-Bauform S1).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.monats_fakten import lade_monats_fakten

J, M = 2025, 5


async def _seed(db, monate, *, bkw_wp=False, zweites_bkw=False, ohne_module=False, kinder=False,
                kind_ab=date(2024, 1, 1), tages_bkw=None):
    """Süd 6 kWp, West 4 kWp, Balkon 0,8 kWp (Spalte oder ``leistung_wp × anzahl``), optional Balkon2 0,6 kWp
    (nur ``leistung_wp × anzahl``) und zwei Modul-Kinder 0,4 kWp am Balkon.

    ``monate``: ``{(jahr, monat): {"agg", "Süd", "West", "Balkon": wert | dict}}``.
    """
    a = Anlage(anlagenname="N-621", leistung_kwp=0.8 if ohne_module else 10.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    ids: dict[str, int] = {}
    invs = []
    if not ohne_module:
        invs += [
            Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Süd", leistung_kwp=6.0,
                        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=6000.0),
            Investition(anlage_id=a.id, typ="pv-module", bezeichnung="West", leistung_kwp=4.0,
                        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=4000.0),
        ]
    if bkw_wp:
        invs.append(Investition(anlage_id=a.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                                parameter={"leistung_wp": 400, "anzahl": 2},
                                anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=800.0))
    else:
        invs.append(Investition(anlage_id=a.id, typ="balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8,
                                anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=800.0))
    if zweites_bkw:
        invs.append(Investition(anlage_id=a.id, typ="balkonkraftwerk", bezeichnung="Balkon2",
                                parameter={"leistung_wp": 300, "anzahl": 2},
                                anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=600.0))
    db.add_all(invs)
    await db.flush()
    ids.update({i.bezeichnung: i.id for i in invs})
    if kinder:
        for name in ("Kind1", "Kind2"):
            k = Investition(anlage_id=a.id, typ="pv-module", bezeichnung=name, leistung_kwp=0.4,
                            parent_investition_id=ids["Balkon"], anschaffungsdatum=kind_ab,
                            anschaffungskosten_gesamt=1.0)
            db.add(k)
            await db.flush()
            ids[name] = k.id
    for (j, m), werte in monate.items():
        db.add(Monatsdaten(anlage_id=a.id, jahr=j, monat=m, einspeisung_kwh=10.0 if ohne_module else 400.0,
                           netzbezug_kwh=200.0, pv_erzeugung_kwh=werte.get("agg")))
        for name, wert in werte.items():
            if name == "agg" or wert is None:
                continue
            db.add(InvestitionMonatsdaten(
                investition_id=ids[name], jahr=j, monat=m,
                verbrauch_daten=wert if isinstance(wert, dict) else {"pv_erzeugung_kwh": wert}))
    if tages_bkw is not None:
        for (j, m), kwh in tages_bkw.items():
            db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(j, m, 3),
                                        komponenten_kwh={f"bkw_{ids['Balkon']}": kwh}))
    await db.commit()
    return a.id, ids


async def _fakten(db, aid, *, tageswerte=False):
    return {f.schluessel: f for f in await lade_monats_fakten(db, aid, inkl_nur_tageswerte=tageswerte)}


def _zahlen(f):
    e = f.erzeugung
    return (round(e.pv_kwh, 6), None if e.pv_module_kwh is None else round(e.pv_module_kwh, 6),
            round(e.bkw_kwh, 6), round(e.bkw_aus_anlagenwert_kwh, 6))


async def _pv_strings(db, aid, jahr=J, monat=M):
    from backend.api.routes.cockpit.pv_strings import get_pv_strings
    res = await get_pv_strings(anlage_id=aid, jahr=jahr, db=db)
    return {s.bezeichnung: next(((round(w.ist_kwh, 2), w.ist_quelle) for w in s.monatswerte if w.monat == monat),
                                None)
            for s in res.strings}


F5 = {(J, M): {"agg": 1000.0, "Süd": 550.0, "West": 380.0}}


# ── F5: jeder Einstieg nennt den Anlagenwert ─────────────────────────────────────────────────────


async def test_f5_alle_einstiege_nennen_den_anlagenwert(db, monkeypatch):
    """F5: Anlagenwert 1000, Strings 550 + 380, BKW ohne Wert ⇒ 1000 in jeder Sicht (vorher 930 in den Fakten-Sichten).

    Der Anteil (70) steht in ``bkw_aus_anlagenwert_kwh`` — nicht in ``bkw_kwh``, nicht in ``pv_je_modul`` (F-10), nicht
    in ``BkwFakten`` (IST-Quelle je Typ).
    """
    aid, ids = await _seed(db, F5)
    f = (await _fakten(db, aid))[(J, M)]
    assert _zahlen(f) == (1000.0, 930.0, 0.0, 70.0)
    assert f.erzeugung.hinter_zaehler_kwh == pytest.approx(1000.0)
    assert set(f.erzeugung.pv_je_modul) == {ids["Süd"], ids["West"]}
    assert f.bkw.erzeugung_kwh == 0.0 and f.bkw.erzeugung_je_investition == {}
    assert f.kennzahlen.eigenverbrauch_kwh == pytest.approx(600.0)

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

    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    assert (await get_cockpit_uebersicht(anlage_id=aid, jahr=J, db=db)).pv_erzeugung_kwh == pytest.approx(1000.0)

    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    zeile = (await list_monatsdaten_aggregiert(anlage_id=aid, jahr=J, db=db))[0]
    # Zwei Segmente (Nacharbeit nach der Nachmessung): Module · BKW (eigene Werte + Anteil), davon verteilt 70.
    assert (zeile.pv_erzeugung_kwh, zeile.pv_module_kwh, zeile.bkw_kwh, zeile.bkw_aus_anlagenwert_kwh) == (
        1000.0, 930.0, 70.0, 70.0)

    from backend.api.routes.cockpit.jahr import get_cockpit_jahr
    jahr = await get_cockpit_jahr(anlage_id=aid, jahr=J, db=db)
    kopf = jahr["kopf"] if isinstance(jahr, dict) else jahr.kopf
    kopf_pv = kopf["pv_erzeugung_kwh"] if isinstance(kopf, dict) else kopf.pv_erzeugung_kwh
    assert kopf_pv == pytest.approx(1000.0)

    from backend.api.routes.ha_export.anlage_sensoren import calculate_anlage_sensors
    anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    ha = {s.definition.key: s.value for s in await calculate_anlage_sensors(db, anlage, skip_jitter=True)}
    assert ha["pv_erzeugung_gesamt_kwh"] == pytest.approx(1000.0)

    from backend.services.community_service import prepare_community_data
    mw = next(m for m in (await prepare_community_data(db, aid))["monatswerte"] if (m["jahr"], m["monat"]) == (J, M))
    # Plan: `ertrag_kwh` +70, `bkw_erzeugung_kwh` bleibt der eigene Wert (hier keiner).
    assert mw["ertrag_kwh"] == 1000.0 and "bkw_erzeugung_kwh" not in mw


@pytest.mark.parametrize("bkw_wp", [False, True], ids=["bkw-kwp-spalte", "bkw-kwp-leistung_wp-x-anzahl"])
async def test_f5b_der_rest_geht_nach_kwp_auf_modul_und_bkw(db, bkw_wp):
    """F5b: Anlagenwert 1000, Süd 550 gemessen, West und BKW ohne Wert ⇒ Rest 450 nach 4 : 0,8 ⇒ West 375, BKW 75.

    In beiden Pflegeformen der BKW-kWp dieselbe Zahl — vorher gewichtete die String-Sicht ein BKW mit
    ``leistung_wp × anzahl`` mit 0 (West 450, Balkon 0), und die Fakten gaben West die ganzen 450.
    """
    aid, ids = await _seed(db, {(J, M): {"agg": 1000.0, "Süd": 550.0}}, bkw_wp=bkw_wp)
    f = (await _fakten(db, aid))[(J, M)]
    assert _zahlen(f) == (1000.0, 925.0, 0.0, 75.0)
    assert round(f.erzeugung.pv_je_modul[ids["West"]].pv_erzeugung_kwh, 6) == 375.0
    assert await _pv_strings(db, aid) == {
        "Süd": (550.0, "gemessen"), "West": (375.0, "verteilt"), "Balkon": (75.0, "verteilt"),
    }


async def test_zwei_balkonkraftwerke_teilen_den_rest_nach_ihrer_kwp(db):
    """Zwei BKW ohne Wert, 0,8 kWp (Spalte) und 0,6 kWp (nur ``leistung_wp × anzahl``): Rest 70 ⇒ 40 / 30 in Fakten,
    PV-Strings und PDF-Abschnitt (vorher 70 / 0 in der String-Sicht, 0 in den Fakten)."""
    aid, ids = await _seed(db, F5, zweites_bkw=True)
    assert _zahlen((await _fakten(db, aid))[(J, M)]) == (1000.0, 930.0, 0.0, 70.0)
    strings = await _pv_strings(db, aid)
    assert (strings["Balkon"], strings["Balkon2"]) == ((40.0, "verteilt"), (30.0, "verteilt"))
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context
    ctx = await build_jahresbericht_context(db, aid, J)
    sv = {s["bezeichnung"]: round(s["ist_kwh"], 6) for s in ctx["string_vergleiche"]}
    assert (sv["Balkon"], sv["Balkon2"]) == (40.0, 30.0)


async def test_h620_pdf_abschnitt_gleich_monatstabelle_gleich_pv_strings(db):
    """Haltepunkt N-620: Anlagenwert 1100, alle Strings gemessen, BKW ohne Wert ⇒ Σ String-Abschnitt = Monatstabelle =
    PV-Strings = 1100 (vorher Monatstabelle 930 gegen Abschnitt 1100 im selben PDF)."""
    aid, _ = await _seed(db, {(J, M): {"agg": 1100.0, "Süd": 550.0, "West": 380.0}})
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context
    from backend.api.routes.cockpit.pv_strings import get_pv_strings
    ctx = await build_jahresbericht_context(db, aid, J)
    tabelle = sum((z.get("pv_erzeugung_kwh") or 0.0) for z in ctx["monats_zeilen"])
    abschnitt = sum(s["ist_kwh"] for s in ctx["string_vergleiche"])
    strings = (await get_pv_strings(anlage_id=aid, jahr=J, db=db)).ist_gesamt_kwh
    assert round(tabelle, 6) == round(abschnitt, 6) == round(strings, 6) == 1100.0


# ── Rundungsrest: die Teile ergeben den Anlagenwert (bis auf die letzte Stelle) ────────────────────────────────────────


@pytest.mark.parametrize("monat, zweites_bkw", [
    pytest.param({"agg": 1000.0}, False, id="keine-Strings-6-4-0,8"),
    pytest.param({"agg": 1000.0, "Süd": 310.0}, False, id="Sued-gemessen"),
    pytest.param({"agg": 1234.56, "Süd": 550.0, "West": 380.0}, True, id="zwei-BKW"),
])
async def test_die_teile_ergeben_den_anlagenwert(db, monat, zweites_bkw):
    """Drei Teile nach kWp ergaben in Gleitkomma 999,9999999999998 statt 1000 — `int()` in *Cockpit →
    Nachhaltigkeit* nannte daraus 1899 statt 1900 Auto-km. Der letzte BKW-Empfänger trägt die Differenz.

    Das beseitigt den systematischen Rest (gemessen 21 → 0 von 90 Formen), garantiert aber keine Bitgleichheit:
    die Nachmessung fand 2 von 496 Zufallsformen mit einer Abweichung in der letzten Stelle (208,645 →
    208,64500000000004). Deshalb Toleranz 1e-9 — die Abrundungsfolge, um die es geht, hält die Nachhaltigkeits-
    Zeile fest (1900, nicht 1899)."""
    aid, _ = await _seed(db, {(J, M): monat}, zweites_bkw=zweites_bkw)
    f = (await _fakten(db, aid))[(J, M)]
    assert f.erzeugung.pv_kwh == pytest.approx(monat["agg"], abs=1e-9)
    if monat == {"agg": 1000.0}:
        from backend.api.routes.cockpit.nachhaltigkeit import get_nachhaltigkeit
        assert (await get_nachhaltigkeit(anlage_id=aid, db=db)).aequivalent_auto_km == 1900


# ── Komponenten → PV-Anlage → Verlauf: zwei Stapel, eine Summe ───────────────────────────────────


@pytest.mark.parametrize("monat, zweites_bkw, segmente", [
    pytest.param(F5[(J, M)], None, (930.0, 70.0, 70.0), id="F5"),
    pytest.param({"agg": 1000.0, "Süd": 550.0}, None, (925.0, 75.0, 75.0), id="F5b-West-Luecke"),
    pytest.param({"agg": 1100.0, "Süd": 550.0, "West": 380.0}, None, (930.0, 170.0, 170.0), id="H620"),
    # Zwei BKW, Balkon2 (0,6 kWp) mit eigenem Wert 20: der Rest 50 geht ganz an Balkon (ohne Wert) ⇒ BKW 70, davon 50.
    pytest.param(F5[(J, M)], 20.0, (930.0, 70.0, 50.0), id="zwei-BKW-eines-mit-Wert"),
])
async def test_verlauf_stapel_module_bkw_und_anteil_ergeben_die_erzeugung(db, monat, zweites_bkw, segmente):
    """`/monatsdaten/aggregiert` liefert zwei Segmente — Module und BKW (eigene Werte + Anteil am Anlagenwert, davon
    `bkw_aus_anlagenwert_kwh` verteilt) —, ihre Summe ist `pv_erzeugung_kwh`. *Komponenten → PV-Anlage → Verlauf* stapelt
    die Module aus PV-Strings und das BKW aus `bkw_kwh`: dieselbe Summe wie der Verwendungs-Stapel (Direktverbrauch +
    Speicherladung + Einspeisung). Bis zur Nachmessung fehlte der Anteil im Erzeugungs-Stapel (930 gegen 1000; 950 gegen
    1000)."""
    if zweites_bkw is not None:
        monat = {**monat, "Balkon2": zweites_bkw}
    aid, ids = await _seed(db, {(J, M): monat}, zweites_bkw=zweites_bkw is not None)
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    from backend.api.routes.cockpit.pv_strings import get_pv_strings_gesamtlaufzeit
    z = (await list_monatsdaten_aggregiert(anlage_id=aid, jahr=None, db=db))[0]
    assert (z.pv_module_kwh, z.bkw_kwh, z.bkw_aus_anlagenwert_kwh) == segmente
    assert round(z.pv_module_kwh + z.bkw_kwh, 6) == z.pv_erzeugung_kwh
    strings = await get_pv_strings_gesamtlaufzeit(anlage_id=aid, db=db)
    module = sum(s.ist_gesamt_kwh for s in strings.strings if s.investition_id in (ids["Süd"], ids["West"]))
    erzeugung = module + z.bkw_kwh
    verwendung = z.direktverbrauch_kwh + (z.speicher_ladung_kwh or 0) + z.einspeisung_kwh
    assert round(erzeugung, 6) == round(verwendung, 6) == z.pv_erzeugung_kwh


# ── Reine BKW-Anlage ─────────────────────────────────────────────────────────────────────────────


async def test_reine_bkw_anlage_ein_monat_mit_anlagenwert_ist_sichtbar(db):
    """Nur ein Balkonkraftwerk; April eigener Wert 60, Mai nur Anlagenwert 55 ⇒ Mai 55 in Tabelle, Übersicht 115.

    Die Übersicht nennt denselben spezifischen Ertrag wie dieselbe Anlage, wenn das BKW seine 55 selbst meldet — der
    Monat mit Anteil zählt als PV-Monat (Schritt 6). Vorher: Mai „keine PV" (Tabelle ``None``), Übersicht 60.
    """
    aid, _ = await _seed(db, {(J, 4): {"Balkon": 60.0}, (J, M): {"agg": 55.0}}, ohne_module=True)
    aid_eigen, _ = await _seed(db, {(J, 4): {"Balkon": 60.0}, (J, M): {"Balkon": 55.0}}, ohne_module=True)

    f = (await _fakten(db, aid))[(J, M)]
    assert _zahlen(f) == (55.0, None, 0.0, 55.0) and f.erzeugung.pv_je_modul == {}

    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    zeilen = {z.monat: z for z in await list_monatsdaten_aggregiert(anlage_id=aid, jahr=J, db=db)}
    assert (zeilen[M].pv_erzeugung_kwh, zeilen[M].pv_module_kwh, zeilen[M].bkw_kwh,
            zeilen[M].bkw_aus_anlagenwert_kwh) == (55.0, 0.0, 55.0, 55.0)

    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    u = await get_cockpit_uebersicht(anlage_id=aid, jahr=J, db=db)
    u_eigen = await get_cockpit_uebersicht(anlage_id=aid_eigen, jahr=J, db=db)
    assert u.pv_erzeugung_kwh == pytest.approx(115.0)
    assert u.spezifischer_ertrag_kwh_kwp == pytest.approx(u_eigen.spezifischer_ertrag_kwh_kwp)


@pytest.mark.parametrize("monate, pv, spez", [
    # Gemischt: April eigener BKW-Wert, Mai nur Anlagenwert (N-621-Anteil). Vor N-621 HA 75,0; mit der HA-Bedingung
    # nur um den Anteil ergänzt (H1 Variante a) 1 105,77.
    pytest.param({(J, 4): {"Balkon": 60.0}, (J, M): {"agg": 55.0}}, 115.0, 586.7347, id="mit-Anlagenwert-gemischt"),
    # Ohne Anlagenwert: beide Monate eigener BKW-Wert. Vor H1 HA 143,75 (die Monate fehlten im Nenner).
    pytest.param({(J, 4): {"Balkon": 60.0}, (J, M): {"Balkon": 55.0}}, 115.0, 586.7347, id="ohne-Anlagenwert"),
    # Nur Anlagenwert-Monate. Vor N-621 HA 12,5.
    pytest.param({(J, M): {"agg": 55.0}}, 55.0, 528.8462, id="nur-Anlagenwert"),
])
async def test_reine_bkw_anlage_ha_spez_ertrag_wie_uebersicht(db, monate, pv, spez):
    """N-621 H1 (Entscheid des Masters 04.10.2026): der HA-Sensor „spezifischer Ertrag" und die Kachel in
    *Cockpit → Übersicht* nennen für eine reine Balkonkraftwerk-Anlage dieselbe Zahl — beide fragen
    ``monats_fakten.pv_erzeugungs_monate``. Die absolute Zahl steht dabei, damit ein Fehler in der gemeinsamen
    Funktion (beide Seiten gleich falsch) ebenfalls auffällt."""
    aid, _ = await _seed(db, monate, ohne_module=True)
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export.anlage_sensoren import calculate_anlage_sensors
    u = await get_cockpit_uebersicht(anlage_id=aid, jahr=None, db=db)
    anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    ha = {s.definition.key: s.value for s in await calculate_anlage_sensors(db, anlage, skip_jitter=True)}
    assert ha["pv_erzeugung_gesamt_kwh"] == pytest.approx(pv)
    assert ha["spezifischer_ertrag_kwh_kwp"] == pytest.approx(spez, abs=1e-3)
    assert u.spezifischer_ertrag_kwh_kwp == pytest.approx(round(spez, 1))


# ── Zusatzregeln: P9, Tageswert, Abtretung ───────────────────────────────────────────────────────


async def test_p9_ein_bkw_mit_anteil_traegt_keinen_ersatz_eigenverbrauch(db):
    """F5 + BKW-Zeile nur mit Eigenverbrauch 30: PV 1000, Ersatz-EV 0 (vorher PV 930 + Ersatz-EV 30). Der Eigenverbrauch
    des BKW steckt jetzt in der Ableitung aus ``pv_kwh`` — ein zweiter Term wäre die Doppelzählung, gegen die P9 steht."""
    aid, _ = await _seed(db, {(J, M): {"agg": 1000.0, "Süd": 550.0, "West": 380.0,
                                       "Balkon": {"eigenverbrauch_kwh": 30.0}}})
    f = (await _fakten(db, aid))[(J, M)]
    assert _zahlen(f) == (1000.0, 930.0, 0.0, 70.0)
    assert f.bkw.rest_eigenverbrauch_kwh == 0.0
    assert f.bkw.eigenverbrauch_gemessen_kwh == 30.0          # die Anzeige behält den gemessenen Wert


@pytest.mark.parametrize("agg, pv, netto", [
    # P9-Fall: Anteil 70 ⇒ PV 1000, Eigenverbrauch 600 ⇒ 600 × 0,30 + 400 × 0,08 = 212 € (vorher 191 + 30 × 0,30 = 200).
    pytest.param(1000.0, 1000.0, 212.0, id="Anteil-70"),
    # Rest 0 (Entscheid des Masters 04.10.2026): der Anlagenwert 930 ist von den Strings ganz erklärt. Das BKW ohne
    # Erzeugungswert ist trotzdem Empfänger — der Anlagenwert sagt, es hat 0 erzeugt; ein Eigenverbrauch aus nicht
    # erzeugtem Strom wäre die Doppelzählung, die P9 verbietet ⇒ 530 × 0,30 + 400 × 0,08 = 191 € (vorher 200).
    pytest.param(930.0, 930.0, 191.0, id="Rest-0"),
])
async def test_p9_ersatz_eigenverbrauch_ueber_die_einstiege(db, agg, pv, netto):
    """Strings 550 + 380, BKW-Zeile nur mit Eigenverbrauch 30, Anlagenwert gespeichert: *Auswertungen → Tabelle*
    (Netto-Ertrag des Monats) und der HA-Sensor „Netto-Ertrag" nennen dieselbe Zahl — ohne Ersatz-Eigenverbrauch."""
    aid, _ = await _seed(db, {(J, M): {"agg": agg, "Süd": 550.0, "West": 380.0,
                                       "Balkon": {"eigenverbrauch_kwh": 30.0}}})
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    from backend.api.routes.ha_export.anlage_sensoren import calculate_anlage_sensors
    z = (await list_monatsdaten_aggregiert(anlage_id=aid, jahr=J, db=db))[0]
    assert z.pv_erzeugung_kwh == pv
    assert z.netto_ertrag_euro == pytest.approx(netto)
    anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    ha = {s.definition.key: s.value for s in await calculate_anlage_sensors(db, anlage, skip_jitter=True)}
    assert ha["netto_ertrag_euro"] == pytest.approx(netto)


@pytest.mark.parametrize("monat, erwartet", [
    pytest.param({"agg": 1000.0, "Süd": 550.0, "West": 380.0}, (1000.0, 930.0, 0.0, 70.0), id="F5-plus-Tageswert"),
    pytest.param({"agg": 1000.0}, (1000.0, 925.925926, 0.0, 74.074074), id="keine-Strings-plus-Tageswert"),
])
async def test_ein_bkw_tageswert_kommt_nicht_neben_dem_anteil(db, monat, erwartet):
    """Der Anlagenwert hat das BKW schon bedacht — sein Tageswert (45) kommt mit Tagesebene nicht obendrauf (vorher
    975 bzw. 1045). Ohne Tagesebene und mit Tagesebene dieselbe Zahl."""
    aid, _ = await _seed(db, {(J, M): monat}, tages_bkw={(J, M): 45.0})
    ohne = (await _fakten(db, aid))[(J, M)]
    mit = (await _fakten(db, aid, tageswerte=True))[(J, M)]
    assert tuple(round(x, 6) if x is not None else None for x in _zahlen(ohne)) == erwartet
    assert tuple(round(x, 6) if x is not None else None for x in _zahlen(mit)) == erwartet
    assert "bkw" not in mit.meta.tageswert_gruppen


@pytest.mark.parametrize("bkw_zeile", [
    pytest.param({"pv_erzeugung_kwh": 0.0}, id="gepflegte-Null"),
    pytest.param({"erzeugung_kwh": 0.0}, id="gepflegte-Null-Altschluessel"),
])
async def test_eine_gepflegte_null_ist_ein_eigener_wert(db, bkw_zeile):
    """Meldet das BKW 0 kWh (beide Schreibweisen), ist das ein Wert (``is not None``) — kein Anteil, der Monat bleibt
    bei den Strings (930), wie vor N-621."""
    aid, _ = await _seed(db, {(J, M): {"agg": 1000.0, "Süd": 550.0, "West": 380.0, "Balkon": bkw_zeile}})
    assert _zahlen((await _fakten(db, aid))[(J, M)]) == (930.0, 930.0, 0.0, 0.0)


async def test_ein_abtretendes_bkw_ohne_wert_bekommt_keinen_anteil(db):
    """BKW mit zwei Modul-Kindern (0,4 kWp, aktiv, ohne Wert), Strings 550 + 380, Anlagenwert 1000: der Rest 70 geht an
    die KINDER (35 / 35) — das BKW hat an sie abgetreten (ADR-002/P11) und ist selbst keine Lücke."""
    aid, ids = await _seed(db, F5, kinder=True)
    f = (await _fakten(db, aid))[(J, M)]
    assert _zahlen(f) == (1000.0, 1000.0, 0.0, 0.0)
    assert [round(f.erzeugung.pv_je_modul[ids[k]].pv_erzeugung_kwh, 6) for k in ("Kind1", "Kind2")] == [35.0, 35.0]


async def test_k5_kinder_spaeter_das_bkw_traegt_selbst_und_bekommt_den_anteil(db):
    """Kinder erst ab 09/2025: im Mai trägt das BKW selbst (Zeitfilter vor Selektor) und bekommt als Lücke den Rest 70."""
    aid, _ = await _seed(db, F5, kinder=True, kind_ab=date(2025, 9, 1))
    assert _zahlen((await _fakten(db, aid))[(J, M)]) == (1000.0, 930.0, 0.0, 70.0)


async def test_gemischte_historie_ein_monat_ohne_anlagenwert_bleibt_wie_vorher(db):
    """Kandidatenregel: Juni trägt einen Anlagenwert, Mai nicht. Mai (Strings 550 + 380, BKW-Zeile nur mit
    Eigenverbrauch 30, BKW-Tageswert 45) bleibt bitgleich — 930, Ersatz-EV 30, mit Tagesebene 975, kein Anteil.
    Juni (Anlagenwert 1000, BKW ohne Wert) bekommt den Anteil 70."""
    aid, _ = await _seed(db, {
        (J, M): {"Süd": 550.0, "West": 380.0, "Balkon": {"eigenverbrauch_kwh": 30.0}},
        (J, 6): {"agg": 1000.0, "Süd": 550.0, "West": 380.0},
    }, tages_bkw={(J, M): 45.0})
    fakten = await _fakten(db, aid)
    assert _zahlen(fakten[(J, M)]) == (930.0, 930.0, 0.0, 0.0)
    assert fakten[(J, M)].bkw.rest_eigenverbrauch_kwh == 30.0
    assert _zahlen(fakten[(J, 6)]) == (1000.0, 930.0, 0.0, 70.0)
    # Die Tagesebene im Mai — eine BKW-Zeile gibt es (nur EV), deshalb greift der Tageswert dort wie vorher nicht.
    assert _zahlen((await _fakten(db, aid, tageswerte=True))[(J, M)]) == (930.0, 930.0, 0.0, 0.0)


async def test_gemischte_historie_ohne_bkw_zeile_behaelt_den_tageswert(db):
    """Wie oben, aber ohne BKW-Zeile im Mai: ohne Anlagenwert greift der BKW-Tageswert wie vorher (930 → 975)."""
    aid, _ = await _seed(db, {
        (J, M): {"Süd": 550.0, "West": 380.0},
        (J, 6): {"agg": 1000.0, "Süd": 550.0, "West": 380.0},
    }, tages_bkw={(J, M): 45.0})
    assert _zahlen((await _fakten(db, aid, tageswerte=True))[(J, M)]) == (975.0, 930.0, 45.0, 0.0)


# ── Symmetrie: Tag = Monat ohne Abschluss = Monat abgeschlossen ──────────────────────────────────


class _FesteUhr(datetime):
    """``now()`` steht — ``get_aktueller_monat`` entscheidet daran, ob der Monat läuft (N-167)."""

    @classmethod
    def now(cls, tz=None):  # noqa: D102
        return datetime(2026, 10, 15, 12, 0)


async def test_f5_tag_gleich_monat_ohne_abschluss_gleich_abgeschlossen(db, monkeypatch):
    """F5 an drei Stellen: der Monat ohne Abschluss (HA-Statistik liefert Anlagenzähler 1000 und die Strings, N-587),
    derselbe Monat abgeschlossen (gespeicherter Anlagenwert 1000 + Strings) und die Tagesregel
    (``waehle_pv_quelle``: das BKW hat keinen Wert ⇒ der Zähler) — alle 1000, EV 600. Vorher abgeschlossen 930."""
    import backend.api.routes.aktueller_monat as am
    from backend.core.berechnungen.pv_tages_praezedenz import (
        QUELLE_EINZEL, erwartete_erzeuger_ids, waehle_pv_quelle,
    )
    monkeypatch.setattr(am, "datetime", _FesteUhr)

    async def _leer(*a, **k):
        return {}

    async def _leer_set(*a, **k):
        return set()
    for name in ("_collect_connector_data", "_collect_mqtt_inbound_data"):
        monkeypatch.setattr(am, name, _leer)
    monkeypatch.setattr(am, "_ha_heimlade_felder_mit_daten", _leer_set)

    # Ohne Abschluss: keine Monatszeile, die HA-Statistik liefert alles.
    aid_offen, ids = await _seed(db, {})
    info = am.DatenquelleInfo(quelle="ha_statistics", konfidenz=92, abdeckung_von=None)
    ha = {"pv_erzeugung_kwh": (1000.0, info), "einspeisung_kwh": (400.0, info), "netzbezug_kwh": (200.0, info),
          f"inv_{ids['Süd']}_pv_erzeugung_kwh": (550.0, info), f"inv_{ids['West']}_pv_erzeugung_kwh": (380.0, info)}

    async def _ha(anlage, j, m):
        return dict(ha) if anlage.id == aid_offen else {}
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _ha)
    offen = await am.get_aktueller_monat(anlage_id=aid_offen, jahr=J, monat=M, db=db)

    aid_zu, _ = await _seed(db, F5)
    zu = await am.get_aktueller_monat(anlage_id=aid_zu, jahr=J, monat=M, db=db)

    invs = (await db.execute(select(Investition).where(Investition.anlage_id == aid_zu))).scalars().all()
    namen = {i.id: i.bezeichnung for i in invs}
    einzel = {str(i): w for i, w in ((i, {"Süd": 550.0, "West": 380.0}.get(n)) for i, n in namen.items())
              if w is not None}
    wahl = waehle_pv_quelle(erwartete_ids=erwartete_erzeuger_ids(invs, date(J, M, 15)),
                            gedeckte_ids_je_slot={0: set(einzel)}, aggregat_je_slot={0: 1000.0})
    tag = sum(einzel.values()) if wahl == QUELLE_EINZEL else 1000.0

    assert offen.pv_erzeugung_kwh == zu.pv_erzeugung_kwh == tag == 1000.0
    assert offen.eigenverbrauch_kwh == zu.eigenverbrauch_kwh == 600.0


# ── Import-Vorschau ──────────────────────────────────────────────────────────────────────────────


class _Wert:
    def __init__(self, sensor_id, differenz):
        self.sensor_id, self.differenz = sensor_id, differenz


class _Monat:
    def __init__(self, sensoren):
        self.jahr, self.monat, self.monat_name, self.sensoren = J, M, "Mai", sensoren


class _Stats:
    is_available = True
    werte = {"sensor.einsp": 400.0, "sensor.netz": 200.0, "sensor.pv_gesamt": 1000.0}

    def get_alle_monatswerte(self, sensor_ids, ab_datum=None, deckel_je_sensor=None):
        return [_Monat([_Wert(s, self.werte[s]) for s in sensor_ids if s in self.werte])]


@pytest.mark.parametrize("monat", [
    pytest.param(F5[(J, M)], id="F5-alle-Strings"),
    pytest.param({"agg": 1000.0, "Süd": 550.0}, id="F5b-West-Luecke"),
])
async def test_die_vorschau_rechnet_den_anteil_mit(db, monkeypatch, monat):
    """Die Import-Vorschau vergleicht den HA-Zähler (1000) mit derselben Zahl wie die Monats-Fakten (Module + BKW-Wert
    + BKW-Anteil). Ohne den Anteil nannte sie bei F5 930 und bei F5b nach dem Ladepfad-Umbau 925 — einen Konflikt
    für einen übereinstimmenden Monat."""
    aid, _ = await _seed(db, {(J, M): monat})
    anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    anlage.sensor_mapping = {"basis": {k: {"strategie": "sensor", "sensor_id": f"sensor.{v}"}
                                       for k, v in (("einspeisung", "einsp"), ("netzbezug", "netz"),
                                                    ("pv_gesamt", "pv_gesamt"))},
                             "investitionen": {}}
    flag_modified(anlage, "sensor_mapping")
    await db.commit()
    monkeypatch.setattr("backend.api.routes.ha_statistics.get_ha_statistics_service", lambda: _Stats())
    from backend.api.routes.ha_statistics import get_import_vorschau
    v = (await get_import_vorschau(aid, db)).monate[0]
    assert v.vorhandene_werte["PV Erzeugung Gesamt"] == pytest.approx(1000.0)
    assert v.aktion == "ueberspringen"
