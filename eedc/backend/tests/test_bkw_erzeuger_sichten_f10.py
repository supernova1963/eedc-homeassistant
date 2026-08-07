"""Ein Balkonkraftwerk ist in den Erzeuger-Sichten eine Zeile wie ein String (F-10).

**Melder:** azywietz-web, Discussion #366 (Reply 05.08.2026) — *„In dem Bereich
Soll/Ist pro PV-String ist keine Prognose vorhanden. Aktueller Stand: Keine
PV-Module gefunden."* Seine Anlage ist eine Anker Solarbank 3 (4 × 500 Wp).

**Warum es das noch gab, obwohl #367 als erledigt galt.** Dessen Issue-Text
sprach von „zwei Endpunkten, die auf `pv-module` filtern"; es waren **fünf**.
Die beiden PVGIS-Routen sind seit v4.0.9 über ``PVGIS_ERZEUGER_TYPEN``
erweitert — der Melder bestätigt das ausdrücklich —, aber die *String*-Sichten
hängen an anderen Queries: ``/pv-strings``, ``/pv-strings-gesamtlaufzeit`` und
Abschnitt 10 des Jahresbericht-PDF. Dieselbe Klasse wie #236: *ein Filter auf
einer Schicht reicht nicht, wenn parallele Pfade existieren.*

**Die Falle, die dieser Test festhält.** Die bloße Typ-Erweiterung im PDF hätte
eine Zeile mit **0 kWh IST** erzeugt — also 100 % Abweichung nach unten, was
schlimmer ist als die leere Tabelle vorher. Grund: das BKW steht **nicht** in
``ErzeugungFakten.pv_je_modul``; dort stehen ausschließlich ``pv-module``, weil
deren Σ ``pv_module_kwh`` in die ROI-Rechnung geht, wo das BKW eine **eigene**
Zeile hat (``investitionen/crud.py::get_pv_erzeugung``) und sonst doppelt
zählte. Sein IST kommt deshalb aus ``BkwFakten.erzeugung_je_investition``.

Die Abgrenzungen unten sind daher der eigentliche Beleg des Pakets: ``pv_kwh``
muss das BKW enthalten, ``pv_module_kwh`` darf es **nicht**.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.cockpit.pv_strings import (
    get_pv_strings,
    get_pv_strings_gesamtlaufzeit,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.monats_fakten import lade_monats_fakten


# Anker Solarbank 3 E2700 Pro, wie der Melder sie betreibt: 4 × 500 Wp = 2,0 kWp
# DC an einem 800-W-Wechselrichter. Das Formular schreibt `leistung_wp`/`anzahl`
# ins `parameter`-JSON, die Spalte `leistung_kwp` bleibt leer — genau deshalb
# braucht der Nenner `get_erzeuger_kwp` und nicht `get_pv_kwp`.
BKW_PARAMS = {
    "leistung_wp": 500,
    "anzahl": 4,
    "ausrichtung": "Süd",
    "neigung_grad": 30,
    "wechselrichter_leistung_w": 800,
}


async def _bkw_anlage(db, *, ist_kwh: float | None = 150.0, mit_prognose=True) -> tuple[int, int]:
    """Reine Balkonkraftwerk-Anlage, Mai 2026. Kein einziges `pv-module`.

    Returns:
        ``(anlage_id, bkw_id)``.
    """
    anlage = Anlage(anlagenname="Nur BKW", leistung_kwp=2.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=40.0, netzbezug_kwh=120.0))
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Solarbank",
        anschaffungsdatum=date(2024, 1, 1), parameter=dict(BKW_PARAMS),
    )
    db.add(bkw)
    await db.flush()
    if ist_kwh is not None:
        db.add(InvestitionMonatsdaten(
            investition_id=bkw.id, jahr=2026, monat=5,
            verbrauch_daten={"pv_erzeugung_kwh": ist_kwh},
        ))
    if mit_prognose:
        db.add(PVGISPrognose(
            anlage_id=anlage.id, abgerufen_am=datetime(2026, 1, 1),
            latitude=48.0, longitude=11.0, neigung_grad=30.0, ausrichtung_grad=0.0,
            jahresertrag_kwh=2000.0, spezifischer_ertrag_kwh_kwp=1000.0,
            gesamt_leistung_kwp=2.0,
            monatswerte=[{"monat": m, "e_m": 166.0} for m in range(1, 13)],
        ))
    await db.commit()
    return anlage.id, bkw.id


# ── Der gemeldete Befund ───────────────────────────────────────────────────

async def test_reines_bkw_bekommt_eine_zeile_statt_leerer_antwort(db):
    """Der gemeldete Fall: die Sicht war leer, der Client schrieb „Keine
    PV-Module gefunden" — obwohl das BKW kWp, Ausrichtung, Neigung und ein
    PVGIS-SOLL trägt."""
    anlage_id, bkw_id = await _bkw_anlage(db)

    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)

    assert len(resp.strings) == 1, "Das Balkonkraftwerk fehlt in der String-Sicht"
    assert resp.strings[0].investition_id == bkw_id
    assert resp.strings[0].bezeichnung == "Solarbank"


async def test_reines_bkw_auch_in_der_gesamtlaufzeit(db):
    """Block ③ „Mehrjahres-Performance" hängt am zweiten Endpunkt — er war
    **nicht** gemeldet und wäre bei einem Fix nur der ersten Query stehen
    geblieben."""
    anlage_id, bkw_id = await _bkw_anlage(db)

    resp = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)

    assert [s.investition_id for s in resp.strings] == [bkw_id]


async def test_bkw_kwp_kommt_aus_leistung_wp_mal_anzahl(db):
    """Der Nenner der SOLL-Verteilung. Mit ``get_pv_kwp`` stünde hier 0 — das
    BKW-Formular füllt weder die Spalte noch ``parameter["kwp"]``."""
    anlage_id, _ = await _bkw_anlage(db)

    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)

    assert resp.strings[0].leistung_kwp == pytest.approx(2.0)


async def test_bkw_zeile_traegt_ihren_ist_wert(db):
    """Ohne eigenen Zweig stünde hier 0 — die Zeile behauptete dann 100 %
    Abweichung nach unten statt gar nicht zu erscheinen."""
    anlage_id, _ = await _bkw_anlage(db, ist_kwh=150.0)

    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)

    assert resp.strings[0].ist_jahr_kwh == pytest.approx(150.0)


# ── Abgrenzung: das BKW darf nirgends doppelt zählen ────────────────────────

async def test_pv_kwh_traegt_das_bkw_pv_module_kwh_nicht(db):
    """**Die tragende Abgrenzung des Pakets.**

    ``pv_kwh`` = Module + BKW (PV-Achse, Finanz-Eingang P9).
    ``pv_module_kwh`` = **nur** Module — diese Summe geht in die ROI-Rechnung,
    wo das BKW eine eigene Zeile hat. Wer das BKW in ``pv_je_modul`` aufnähme,
    um die PDF-Zeile zu füllen, verschöbe genau diese Grenze und erzeugte eine
    Doppelzählung im ROI.
    """
    anlage_id, _ = await _bkw_anlage(db, ist_kwh=150.0)

    fakten = await lade_monats_fakten(db, anlage_id, von=(2026, 5), bis=(2026, 5))

    assert len(fakten) == 1
    erz = fakten[0].erzeugung
    assert erz.pv_kwh == pytest.approx(150.0), "BKW fehlt in der PV-Achse"
    assert not erz.pv_je_modul, "Ein BKW gehört nicht in die Modul-Auflösung"
    assert (erz.pv_module_kwh or 0.0) == pytest.approx(0.0), (
        "pv_module_kwh trägt das BKW — das doppelt im ROI"
    )


async def test_bkw_erzeugung_steht_je_investition_bereit(db):
    """Der Ersatzweg für die PDF-Zeile: dieselbe Erzeugung, nur nicht summiert."""
    anlage_id, bkw_id = await _bkw_anlage(db, ist_kwh=150.0)

    fakten = await lade_monats_fakten(db, anlage_id, von=(2026, 5), bis=(2026, 5))

    je_inv = fakten[0].bkw.erzeugung_je_investition
    assert je_inv == {bkw_id: pytest.approx(150.0)}
    assert sum(je_inv.values()) == pytest.approx(fakten[0].bkw.erzeugung_kwh)


async def test_gemischte_anlage_zeigt_modul_und_bkw_getrennt(db):
    """Dach + Balkon: zwei Zeilen, und die Modul-Summe bleibt frei vom BKW."""
    anlage_id, bkw_id = await _bkw_anlage(db, ist_kwh=150.0)
    modul = Investition(anlage_id=anlage_id, typ="pv-module", bezeichnung="Dach Süd",
                        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=8.0)
    db.add(modul)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=modul.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 900.0},
    ))
    await db.commit()

    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    fakten = await lade_monats_fakten(db, anlage_id, von=(2026, 5), bis=(2026, 5))

    assert {s.investition_id for s in resp.strings} == {bkw_id, modul.id}
    assert fakten[0].erzeugung.pv_module_kwh == pytest.approx(900.0)
    assert fakten[0].erzeugung.pv_kwh == pytest.approx(1050.0)


# ── Dritte Ausgabe derselben Sicht: das Jahresbericht-PDF ──────────────────

async def test_pdf_string_vergleich_zeigt_das_bkw_mit_seinem_ist(db):
    """Abschnitt 10 des Jahresbericht-PDF.

    **Die Falle:** eine bloße Typ-Erweiterung hätte die Zeile mit ``ist_kwh = 0``
    gefüllt, weil das BKW nicht in ``pv_je_modul`` steht. Der Bericht behauptete
    dann 100 % Abweichung nach unten — schlimmer als die leere Tabelle, weil
    eine Zahl dasteht, die wie eine Messung aussieht.
    """
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    anlage_id, _ = await _bkw_anlage(db, ist_kwh=150.0)

    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2026)

    zeilen = {z["bezeichnung"]: z for z in ctx["string_vergleiche"]}
    assert "Solarbank" in zeilen, "Das BKW fehlt im String-Vergleich des PDF"
    assert zeilen["Solarbank"]["ist_kwh"] == pytest.approx(150.0), (
        "Die BKW-Zeile trägt 0 kWh IST — die Typ-Erweiterung ohne den "
        "erzeugung_je_investition-Zweig"
    )
    assert zeilen["Solarbank"]["leistung_kwp"] == pytest.approx(2.0)


# ── Klasse B: die einzige Stelle, deren falscher Wert das Haus verlässt ─────

async def test_community_meldet_die_echte_ausrichtung_statt_sued_30(db):
    """``prepare_community_data`` fiel bei BKW-only in den ``else``-Zweig und
    schickte dem Community-Server ``neigung_grad=30`` / ``ausrichtung="süd"``
    — erfundene Stammdaten, gegen die die Anlage dann verglichen wurde.

    Die Fixture pflegt bewusst **West/45°**: beide Werte weichen von den
    Default-Annahmen ab, sonst wäre der Test gegen den Fehler blind.
    """
    from backend.services.community_service import prepare_community_data

    anlage = Anlage(anlagenname="Nur BKW West", leistung_kwp=2.0, standort_plz="10115")
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=40.0, netzbezug_kwh=120.0))
    db.add(Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Solarbank",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={**BKW_PARAMS, "ausrichtung": "West", "neigung_grad": 45},
    ))
    await db.commit()

    daten = await prepare_community_data(db, anlage.id)

    assert daten["ausrichtung"] == "west", (
        f"Community bekommt {daten['ausrichtung']!r} statt der gepflegten Ausrichtung"
    )
    assert daten["neigung_grad"] == 45, (
        f"Community bekommt {daten['neigung_grad']}° statt der gepflegten 45°"
    )


# ── Klasse C ───────────────────────────────────────────────────────────────

async def test_sensor_mapping_gesamt_kwp_zaehlt_bkw_und_die_spalte(db, monkeypatch):
    """Zwei Befunde in einer Zeile: `balkonkraftwerk` fehlte, **und** gelesen
    wurde nur das ``parameter``-JSON — ein Modul mit gepflegter *Spalte* zählte
    0 (die #229-Klasse mit vertauschten Rollen).

    ⚠ ``gesamt_kwp`` hat baumweit keinen Leser; der Test hält die Rechnung
    fest, nicht eine Anzeige.

    Der Endpunkt holt seine Session selbst über ``get_session()`` — ohne den
    Patch liefe er an der Test-DB vorbei und der Test wäre grün, ohne etwas zu
    beweisen (Muster aus ``test_mqtt_export_toggle_b7_5b.py``).
    """
    from contextlib import asynccontextmanager

    from backend.api.routes import sensor_mapping as sm

    anlage_id, _ = await _bkw_anlage(db)          # BKW: 2,0 kWp nur im parameter
    db.add(Investition(anlage_id=anlage_id, typ="pv-module", bezeichnung="Dach",
                       anschaffungsdatum=date(2024, 1, 1), leistung_kwp=8.0))
    await db.commit()

    @asynccontextmanager
    async def fake_session():
        yield db

    monkeypatch.setattr(sm, "get_session", fake_session)

    resp = await sm.get_sensor_mapping(anlage_id=anlage_id)

    assert resp.gesamt_kwp == pytest.approx(10.0), (
        "Erwartet 8,0 (Spalte) + 2,0 (BKW aus leistung_wp × anzahl)"
    )
