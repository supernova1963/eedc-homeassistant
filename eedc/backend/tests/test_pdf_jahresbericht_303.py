"""#303 / #304-PDF: Jahresbericht matplotlib-frei + Eigenverbrauch mit Speicher.

Zwei Stränge:
1. **#303 (charts.py SVG):** Die Jahresbericht-Diagramme werden ohne
   matplotlib/numpy als inline-SVG gerendert (numpy-2.x-X86_V2-Baseline crasht
   sonst auf Proxmox-kvm64-VMs). Das echte PDF muss durch WeasyPrint laufen.
2. **#304-PDF-Teil:** Der Jahresbericht-Builder rechnete den Eigenverbrauch mit
   der naiven Formel PV − Einspeisung (Batterie ignoriert). Jetzt über den
   SoT-Helper berechne_verbrauchs_kennzahlen (PV + Speicher), V2H additiv —
   deckungsgleich mit Cockpit/HA-Export/Aussichten.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.services.pdf import charts
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context


# ── #303: charts.py ist matplotlib-/numpy-frei und liefert SVG ───────────────

def test_charts_liefern_svg_data_uris():
    a = charts.pv_erzeugung_chart(["Jan", "Feb", "Mär"], [120, 340, 600], [150, 300, 650])
    b = charts.energie_fluss_chart(["Jan", "Feb"], [100, 200], [50, 80], [300, 250])
    c = charts.autarkie_chart(["Jan", "Feb", "Mär"], [45.2, 60.1, 72.9])
    for uri in (a, b, c):
        assert uri.startswith("data:image/svg+xml;base64,")


def test_charts_modul_ohne_matplotlib_numpy():
    """Kein matplotlib/numpy-Import im Pflicht-Pfad (kvm64-Crash-Vermeidung)."""
    import backend.services.pdf.charts as ch
    src = open(ch.__file__, encoding="utf-8").read()
    # echte Import-Statements, nicht die Erwähnung im Docstring
    assert not re.search(r"^\s*import (matplotlib|numpy)", src, re.MULTILINE)
    assert not re.search(r"^\s*from (matplotlib|numpy)", src, re.MULTILINE)


def test_charts_robust_bei_leeren_daten():
    # Darf nicht crashen (Division durch 0 / leere Reihen)
    charts.pv_erzeugung_chart([], [])
    charts.autarkie_chart(["Jan"], [0])
    charts.energie_fluss_chart(["Jan"], [0], [0], [0])


# ── Fixture: Anlage mit PV + Speicher (+ optional E-Auto/V2H) ────────────────

async def _seed(db, *, mit_v2h: bool = False, mit_flex_und_sonstige: bool = False) -> int:
    anlage = Anlage(anlagenname="PDF-Test", leistung_kwp=10.0,
                    standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()
    for m in range(1, 13):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=m,
            einspeisung_kwh=400.0, netzbezug_kwh=300.0,
            # Flex-Tarif: pro Monat anderer Ø-Preis (21–32 ct), damit
            # Summary ≠ Σ(EV)×statischer Preis unterscheidbar wird.
            netzbezug_durchschnittspreis_cent=(20.0 + m) if mit_flex_und_sonstige else None,
        ))
    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0,
        anschaffungskosten_gesamt=15000.0,
    )
    sp = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=8000.0,
    )
    db.add_all([pv, sp])
    invs = [pv, sp]
    if mit_v2h:
        ea = Investition(
            anlage_id=anlage.id, typ="e-auto", bezeichnung="Auto",
            anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=30000.0,
        )
        db.add(ea)
        invs.append(ea)
    await db.flush()
    for m in range(1, 13):
        pv_daten: dict = {"pv_erzeugung_kwh": 1000.0}
        if mit_flex_und_sonstige and m == 5:
            # Sonstige Positionen: +200 € THG, −150 € Reparatur → netto +50 €
            pv_daten["sonstige_positionen"] = [
                {"bezeichnung": "THG-Quote", "betrag": 200.0, "typ": "ertrag"},
                {"bezeichnung": "Reparatur", "betrag": 150.0, "typ": "ausgabe"},
            ]
        db.add(InvestitionMonatsdaten(
            investition_id=pv.id, jahr=2025, monat=m,
            verbrauch_daten=pv_daten,
        ))
        db.add(InvestitionMonatsdaten(
            investition_id=sp.id, jahr=2025, monat=m,
            verbrauch_daten={"ladung_kwh": 300.0, "entladung_kwh": 250.0},
        ))
        if mit_v2h:
            db.add(InvestitionMonatsdaten(
                investition_id=invs[-1].id, jahr=2025, monat=m,
                verbrauch_daten={"v2h_entladung_kwh": 40.0, "km_gefahren": 1000.0},
            ))
    await db.flush()
    return anlage.id


# ── #304-PDF: Eigenverbrauch rechnet den Speicher ein ────────────────────────

async def test_jahresbericht_ev_rechnet_speicher_ein(db):
    """Pro Monat: direkt = max(0, 1000−400−300)=300; eigen = 300+250 = 550.
    Σ12 = 6600. Naive Formel (PV−Einspeisung) hätte 12×600 = 7200 geliefert."""
    anlage_id = await _seed(db)
    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    assert ctx["kpis"]["eigenverbrauch_kwh"] == pytest.approx(6600, abs=1)
    assert ctx["kpis"]["eigenverbrauch_kwh"] != pytest.approx(7200, abs=1), (
        "Eigenverbrauch ignoriert noch den Speicher (naive PV−Einspeisung) — "
        "#304-PDF-Bug zurück."
    )


async def test_jahresbericht_ev_addiert_v2h(db):
    """Mit V2H: eigen = 550 + 40 = 590/Monat → Σ12 = 7080."""
    anlage_id = await _seed(db, mit_v2h=True)
    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    assert ctx["kpis"]["eigenverbrauch_kwh"] == pytest.approx(7080, abs=1)


# ── #302: H2-Label gesamt vs. Jahr (Datenebene) ──────────────────────────────

async def test_jahresbericht_gesamtzeitraum_flag(db):
    anlage_id = await _seed(db)
    ctx_jahr = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    ctx_gesamt = await build_jahresbericht_context(db, anlage_id, jahr=None)
    assert ctx_jahr["ist_gesamtzeitraum"] is False
    assert ctx_gesamt["ist_gesamtzeitraum"] is True


# ── #303: echtes PDF durch WeasyPrint (SVG-Charts eingebettet) ───────────────

async def test_jahresbericht_pdf_rendert_durch_weasyprint(db):
    from backend.services.pdf import render_document
    anlage_id = await _seed(db, mit_v2h=True)
    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    pdf = render_document("jahresbericht.html", ctx)
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 2000  # echtes Dokument, kein leerer Stub


# ── #303 Gegencheck kingcap1: Speicher in der Komponenten-Auflistung ─────────

async def test_jahresbericht_context_investitionen_felder(db):
    """Die Komponenten-Liste trägt die Felder, die die WeasyPrint-Auflistung
    braucht (typ_label, Kosten) — Parität zum reportlab-Pfad."""
    anlage_id = await _seed(db)
    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    speicher = next(i for i in ctx["investitionen"] if i["typ"] == "speicher")
    assert speicher["typ_label"] == "Batteriespeicher"
    assert speicher["bezeichnung"] == "Akku"
    assert speicher["kosten_euro"] == pytest.approx(8000.0)


async def test_jahresbericht_html_listet_speicher_als_komponente(db):
    """kingcap1 (#303): Der Speicher fehlte komplett im WeasyPrint-Bericht, weil
    das Template keine Komponenten-Auflistung hatte. Jetzt taucht er in der
    Sektion „Investitionen & Komponenten" auf (HTML-Render, vor PDF)."""
    from backend.services.pdf.engine import _env, _STATIC_DIR

    anlage_id = await _seed(db)
    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    html = _env.get_template("jahresbericht.html").render(
        **ctx, static_dir=str(_STATIC_DIR)
    )
    assert "Investitionen &amp; Komponenten" in html or "Investitionen & Komponenten" in html
    # Speicher als eigene Komponentenzeile (Label + Bezeichnung), nicht nur die
    # Energie-Sektion „Batteriespeicher".
    assert "Akku" in html
    assert html.count("Batteriespeicher") >= 1
    # Kosten der Komponente werden ausgewiesen (8.000,00 €).
    assert "8.000,00" in html


# ── #303 Gegencheck kingcap1: interne Konsistenz Summary ⟺ Monats-Zeilen ─────
# kingcap1 (06-06) sah „Daten passen nicht übereinander". Die zwei Ursachen
# (fehlender Speicher + Summary `Σ(EV) × statischer Preis` statt per-Monat-
# Flexpreis, #326) sind gefixt. Dieser Test sichert, dass die Summary-KPIs
# im selben PDF exakt die Summe der gedruckten Monats-Zeilen sind — bei
# Speicher + Flex-Tarif + Sonstigen Positionen.

async def test_jahresbericht_summary_ist_summe_der_monats_zeilen(db):
    """Σ Monats-Zeilen == Summary-KPIs (Einspeise-Erlös, EV-Ersparnis, Netto).

    Pro Monat: EV = max(0, 1000−400−300) + 250 = 550 kWh, Flexpreis 20+m ct.
    EV-Ersparnis = Σ 550 × (20+m)/100 = 5,5 × 318 = 1.749,00 €
    Einspeise    = 12 × 400 × 0,082 (Fallback-Vergütung) = 393,60 €
    Sonstige     = +200 − 150 = +50 € — in der Sonstige-Monatszeile UND im
                   Summary (#326-Folge rilmor-mhrs: die Monats-Ertragsspalte
                   muss die Sonstigen enthalten, sonst geht sie nicht auf den
                   Summary auf und ein negativer Monat erscheint positiv).
    Netto        = 393,60 + 1.749,00 + 50 = 2.192,60 €
    """
    anlage_id = await _seed(db, mit_flex_und_sonstige=True)
    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    kpis = ctx["kpis"]
    zeilen = ctx["monats_zeilen"]

    # Summary == Σ der gedruckten Zeilen (das liest der Bericht-Empfänger nach)
    assert kpis["einspeise_erloes_euro"] == pytest.approx(
        sum(z["einsp_erloes_euro"] for z in zeilen), abs=0.01)
    assert kpis["ev_ersparnis_euro"] == pytest.approx(
        sum(z["ev_ersparnis_euro"] for z in zeilen), abs=0.01)
    # #326: Sonstige stecken jetzt pro Monat in `netto_ertrag_euro` der Zeile —
    # die Monatsspalte summiert sich direkt (ohne Sonder-Aufschlag) auf den
    # Summary-Netto.
    assert kpis["sonstige_netto_euro"] == pytest.approx(
        sum(z["sonstige_netto_euro"] for z in zeilen), abs=0.01)
    assert kpis["netto_ertrag_euro"] == pytest.approx(
        sum(z["netto_ertrag_euro"] for z in zeilen), abs=0.01)

    # #326 rilmor-mhrs: die Sonstige-Position (Monat 5) wird der richtigen
    # Monatszeile zugeordnet — nicht über alle Monate verschmiert.
    mai = next(z for z in zeilen if z["monat"] == 5)
    assert mai["sonstige_netto_euro"] == pytest.approx(50.0)
    assert all(
        z["sonstige_netto_euro"] == 0 for z in zeilen if z["monat"] != 5
    )

    # Absolutwerte (fangen symmetrische Fehler auf beiden Seiten)
    assert kpis["ev_ersparnis_euro"] == pytest.approx(1749.0, abs=0.05)
    assert kpis["einspeise_erloes_euro"] == pytest.approx(393.6, abs=0.05)
    assert kpis["sonstige_netto_euro"] == pytest.approx(50.0)
    assert kpis["netto_ertrag_euro"] == pytest.approx(2192.6, abs=0.05)
    # Gegenprobe alter Summary-Bug: Σ(EV) × statischer Preis = 6600×0,30 = 1.980 €
    assert kpis["ev_ersparnis_euro"] != pytest.approx(1980.0, abs=1.0)
