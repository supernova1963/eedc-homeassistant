"""Monatsbericht (#395 Punkt 4, OB73-gif) — die sieben Proben des Konzepts.

Konzept: ``docs/KONZEPT-MONATSBERICHT.md`` (abgenommen Gernot, 2026-08-30).

Die tragende Probe ist die erste: **beide Formate nennen dieselben Zahlen.**
Sie ist die Sicherung gegen die Wiederkehr von **N-7** — die zurückgebaute
Social-Media-Textvorlage trug eine eigene Netto-Ertrag-Kurzformel und ist mit
dem Text *verschwunden*, statt behoben zu werden. Ein zweiter Renderer mit
eigener Rechnung wäre derselbe Fehler, diesmal in einem Text fürs Forum.

Die übrigen sechs halten je eine Entscheidung des Konzepts fest: Themenschalter,
Identität, deutsche Schreibweise, leerer Monat, Park-Filter und — die
wichtigste der drei Park-Bedingungen — **ohne mitgeschickte Liste ist der
Bericht vollständig** (Fall „am Tablet geparkt, am PC erzeugt").
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    Strompreis,
)
from backend.services.pdf.builders.monatsbericht import (
    THEMEN,
    build_monatsbericht_context,
)
from backend.services.pdf.builders.monatsbericht_markdown import (
    render_monatsbericht_markdown,
)
from backend.services.pdf.engine import render_html

JAHR, MONAT = 2026, 4


async def _seed(db, *, mit_werten: bool = True) -> int:
    """Eine Anlage mit PV, Speicher und Wärmepumpe im April 2026.

    ``mit_werten=False`` lässt die Monatszeile weg — das ist der Monat ohne
    Daten aus Probe 5, nicht eine Anlage ohne Komponenten.
    """
    anlage = Anlage(
        anlagenname="Haus Süd", leistung_kwp=12.5,
        standort_plz="10115", standort_ort="Berlin",
        latitude=52.5, longitude=13.4,
        installationsdatum=date(2024, 1, 1),
    )
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=32.0,
        einspeiseverguetung_cent_kwh=8.2,
        grundpreis_euro_monat=12.0,
    ))

    # ⚠ Der Typ heißt `pv-module` (Plural). Ein erster Entwurf dieses Seeds
    # schrieb `pv-modul`; die Anlage hatte dann eine PV-Investition, die kein
    # Pfad als PV erkennt — PV-Erzeugung, Autarkie und Eigenverbrauch standen
    # auf „–", und die Probe hätte einen leeren Bericht gegen einen leeren
    # Bericht verglichen.
    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süddach",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True, leistung_kwp=8.0,
        ausrichtung="Süd", neigung_grad=30,
        anschaffungskosten_gesamt=12000.0,
    )
    pv_ost = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Ostdach",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True, leistung_kwp=4.5,
        ausrichtung="Ost", neigung_grad=30,
        anschaffungskosten_gesamt=6000.0,
    )
    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Hausspeicher",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True, leistung_kwp=10.0,
        anschaffungskosten_gesamt=8000.0,
        parameter={"kapazitaet_kwh": 10.0},
    )
    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Luft-Wasser",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        anschaffungskosten_gesamt=22000.0,
        parameter={"wp_art": "luft_wasser"},
    )
    db.add_all([pv, pv_ost, speicher, wp])
    await db.flush()

    if mit_werten:
        # Der Vorjahresmonat ist mit dabei — sonst gäbe es den Abschnitt
        # „Vergleich mit dem Vorjahresmonat" nicht, und Probe 6 hätte kein
        # geparktes Element zu prüfen.
        for jahr, faktor in ((JAHR, 1.0), (JAHR - 1, 0.9)):
            db.add(Monatsdaten(
                anlage_id=anlage.id, jahr=jahr, monat=MONAT,
                netzbezug_kwh=180.0 * faktor, einspeisung_kwh=520.0 * faktor,
            ))
            db.add(InvestitionMonatsdaten(
                investition_id=pv.id, jahr=jahr, monat=MONAT,
                verbrauch_daten={"pv_erzeugung_kwh": 780.0 * faktor},
            ))
            db.add(InvestitionMonatsdaten(
                investition_id=pv_ost.id, jahr=jahr, monat=MONAT,
                verbrauch_daten={"pv_erzeugung_kwh": 320.0 * faktor},
            ))
        db.add(InvestitionMonatsdaten(
            investition_id=speicher.id, jahr=JAHR, monat=MONAT,
            verbrauch_daten={"ladung_kwh": 240.0, "entladung_kwh": 210.0},
        ))
        db.add(InvestitionMonatsdaten(
            investition_id=wp.id, jahr=JAHR, monat=MONAT,
            verbrauch_daten={
                "stromverbrauch_kwh": 300.0,
                "heizenergie_kwh": 900.0,
                "warmwasser_kwh": 200.0,
            },
        ))
    await db.commit()
    return anlage.id


def _zahlen(text: str) -> list[str]:
    """Alle Zahlen eines Textes in deutscher Schreibweise, in Reihenfolge.

    Bewusst über die **gerenderte Ausgabe** statt über den Context: eine Probe
    auf dem Context sähe nicht, ob ein Renderer eine Zahl unterwegs noch anfasst
    — und genau das ist die Frage.
    """
    return re.findall(r"-?\d[\d.]*(?:,\d+)?", text)


def _als_text(html: str) -> str:
    """HTML-Tags und CSS entfernen — verglichen werden die sichtbaren Zahlen.

    Der ``<style>``-Block muss **vor** dem Tag-Strip fallen: er trägt Zahlen
    (``55%``, ``8.5pt``), die in keiner Tabelle stehen. Ohne diesen Schnitt
    wäre die Probe rot, ohne dass ein Wert abwiche — und wer sie dann repariert,
    repariert die Probe statt den Bericht.
    """
    ohne_style = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    ohne_head = re.sub(r"<head.*?</head>", " ", ohne_style, flags=re.S)
    return re.sub(r"<[^>]+>", " ", ohne_head)


# ── Probe 1: die N-7-Sicherung ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_beide_formate_nennen_dieselben_zahlen(db):
    """PDF-HTML und Markdown tragen dieselben Zahlen in derselben Reihenfolge.

    Rot, sobald ein Format eine Größe anders bildet oder auslässt — die
    Bedingung, unter der das Konzept den zweiten Renderer überhaupt erlaubt.
    """
    anlage_id = await _seed(db)
    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)

    html = render_html("monatsbericht.html", ctx)
    md = render_monatsbericht_markdown(ctx)

    assert _zahlen(_als_text(html)) == _zahlen(md)
    # Und die Probe darf nicht deshalb grün sein, weil beide leer sind.
    assert len(_zahlen(md)) >= 10


# ── Probe 2: Themenschalter ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_abgewaehltes_thema_fehlt_in_beiden_formaten(db):
    """Und die Zahlen der übrigen Abschnitte ändern sich dadurch nicht."""
    anlage_id = await _seed(db)

    voll = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)
    ohne_finanzen = await build_monatsbericht_context(
        db, anlage_id, JAHR, MONAT,
        themen=[t for t in THEMEN if t != "finanzen"],
    )

    assert any(a.thema == "finanzen" for a in voll["abschnitte"])
    assert not any(a.thema == "finanzen" for a in ohne_finanzen["abschnitte"])

    # Die verbleibenden Abschnitte sind Zeile für Zeile unverändert.
    rest_voll = [a for a in voll["abschnitte"] if a.thema != "finanzen"]
    assert [(a.schluessel, [(z.label, z.wert) for z in a.zeilen]) for a in rest_voll] == \
           [(a.schluessel, [(z.label, z.wert) for z in a.zeilen])
            for a in ohne_finanzen["abschnitte"]]

    md = render_monatsbericht_markdown(ohne_finanzen)
    assert "Einspeise-Erlös" not in md
    assert "Einspeise-Erlös" in render_monatsbericht_markdown(voll)


# ── Probe 3: Identität ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ohne_identitaet_stehen_name_und_standort_nirgends(db):
    """`mit_identitaet=False` — in **beiden** Formaten, nicht nur im PDF."""
    anlage_id = await _seed(db)
    ctx = await build_monatsbericht_context(
        db, anlage_id, JAHR, MONAT, mit_identitaet=False
    )
    md = render_monatsbericht_markdown(ctx)
    html = render_html("monatsbericht.html", ctx)

    for text in (md, html):
        assert "Haus Süd" not in text
        assert "Berlin" not in text
        assert "10115" not in text

    # Gegenrichtung — sonst wäre die Probe auch bei einem Bericht grün,
    # der den Namen generell verloren hat.
    mit = render_monatsbericht_markdown(
        await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)
    )
    assert "Haus Süd" in mit and "Berlin" in mit


# ── Probe 4: deutsche Schreibweise ────────────────────────────────────────

@pytest.mark.asyncio
async def test_deutsche_schreibweise_in_beiden_formaten(db):
    """N-234 erbt sich nicht von selbst — ungeprüft ist ungeprüft.

    Gesucht wird die **englische** Form: eine Dezimalzahl mit Punkt. Sie darf in
    keinem der beiden Ausgabetexte stehen.
    """
    anlage_id = await _seed(db)
    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)

    md = render_monatsbericht_markdown(ctx)
    text = _als_text(render_html("monatsbericht.html", ctx))

    # `1.100` (Tausenderpunkt) ist deutsch, `1100.5` wäre englisch:
    # ein Punkt mit weniger oder mehr als drei Ziffern dahinter.
    # ⚠ Das Erzeugungsdatum muss VORHER heraus. „30.08.2026" enthält `0.08` und
    # `8.2026` — der erste Entwurf dieser Probe meldete es als englischen
    # Dezimalpunkt und wäre bei JEDEM Bericht rot gewesen, ohne dass eine Zahl
    # falsch geschrieben war.
    datum = re.compile(r"\d{2}\.\d{2}\.\d{4}")
    englisch = re.compile(r"\d\.\d{1,2}(?![\d.])|\d\.\d{4,}")
    for ausgabe, name in ((md, "markdown"), (text, "html")):
        treffer = englisch.findall(datum.sub(" ", ausgabe))
        assert not treffer, f"{name}: englische Dezimalpunkte {treffer}"
    # Und mindestens ein Dezimalkomma muss vorkommen, sonst prüft die Probe nichts.
    assert re.search(r"\d,\d", md)


# ── Probe 5: Monat ohne Daten ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_monat_ohne_daten_nennt_den_grund_statt_nullen(db):
    """F-43-Klasse: keine erfundene Null, wo nichts gemessen wurde."""
    anlage_id = await _seed(db, mit_werten=False)
    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)

    md = render_monatsbericht_markdown(ctx)
    html = render_html("monatsbericht.html", ctx)

    assert "liegen zu den gewählten Themen keine Werte vor" in md
    assert "liegen zu den gewählten Themen keine Werte vor" in html
    assert "0 kWh" not in md


# ── Probe 6: Park-Filter ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_geparkte_anzeige_fehlt_in_beiden_formaten(db):
    """Ein Park-Zustand blendet aus — er rechnet nicht um.

    Deshalb wird nicht nur die Abwesenheit geprüft, sondern auch, dass **jede
    übrige Zeile Wort für Wort dieselbe bleibt**.
    """
    anlage_id = await _seed(db)
    voll = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)
    geparkt = await build_monatsbericht_context(
        db, anlage_id, JAHR, MONAT, geparkte_ids=["el:bilanz-vergleich"],
    )

    assert any(a.park_id == "el:bilanz-vergleich" for a in voll["abschnitte"])
    assert not any(a.park_id == "el:bilanz-vergleich" for a in geparkt["abschnitte"])
    assert geparkt["weggelassen"] == ["Vergleich mit dem Vorjahresmonat"]

    rest = [a for a in voll["abschnitte"] if a.park_id != "el:bilanz-vergleich"]
    assert [(a.schluessel, [(z.label, z.wert) for z in a.zeilen]) for a in rest] == \
           [(a.schluessel, [(z.label, z.wert) for z in a.zeilen])
            for a in geparkt["abschnitte"]]

    for text in (render_monatsbericht_markdown(geparkt),
                 _als_text(render_html("monatsbericht.html", geparkt))):
        assert "PV-Erzeugung Vorjahr" not in text


# ── Probe 7: der andere Browser ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_ohne_park_liste_ist_der_bericht_vollstaendig(db):
    """Der Fall „am Tablet geparkt, am PC erzeugt" darf **nichts** weglassen.

    Der Park-Zustand lebt nur im ``localStorage`` des jeweiligen Browsers. Eine
    Umsetzung, die im Zweifel etwas ausblendet, würde je Gerät einen anderen
    Bericht liefern — ohne Hinweis und ohne dass etwas kaputt wäre.
    """
    anlage_id = await _seed(db)
    ohne_liste = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)
    leere_liste = await build_monatsbericht_context(
        db, anlage_id, JAHR, MONAT, geparkte_ids=[],
    )

    assert ohne_liste["weggelassen"] == []
    assert [a.schluessel for a in ohne_liste["abschnitte"]] == \
           [a.schluessel for a in leere_liste["abschnitte"]]
    # Alle vier Themen sind vertreten — sonst wäre „vollständig" nicht geprüft.
    assert {a.thema for a in ohne_liste["abschnitte"]} >= {"energie", "komponenten", "finanzen"}


# ── Der Anker selbst: jede Park-ID des Berichts gibt es in der Oberfläche ──

def test_jeder_park_anker_existiert_im_render_pfad():
    """Ein Anker, den die Oberfläche nicht kennt, filtert nie — und schweigt dabei.

    Die Park-Doktrin verbietet die statische ID-Liste im Backend; jeder
    Abschnitt nennt deshalb nur seinen **eigenen** Anker. Was sie nicht
    verhindert, ist die stille Drift: benennt jemand ``el:wp-detail`` in der
    Oberfläche um, blendet der Bericht diesen Abschnitt nie wieder aus und
    niemand merkt es. Diese Probe macht daraus einen roten Lauf.
    """
    from pathlib import Path
    import inspect
    import backend.services.pdf.builders.monatsbericht as modul

    quelle = inspect.getsource(modul)
    anker = set(re.findall(r'park_id="(el:[a-z0-9-]+)"', quelle))
    assert anker, "keine Anker gefunden — die Probe misst nichts"

    src = Path(__file__).resolve().parents[2] / "frontend" / "src"
    assert src.is_dir(), f"Frontend-Quellen nicht gefunden: {src}"
    # ⚠ `.ts` MUSS mit: fünf der Bilanz-IDs stehen in `v4/bilanzParkIds.ts`, und
    # ein erster Entwurf dieser Probe suchte nur `.tsx` **und** nur einfache
    # Anführungszeichen — JSX schreibt `id="el:…"`. Beide Verengungen zusammen
    # meldeten fünf Fehlalarme; eine davon allein hätte gereicht, um die Probe
    # nutzlos zu machen, ohne dass es auffiele.
    haystack = "\n".join(
        p.read_text(encoding="utf-8")
        for muster in ("*.ts", "*.tsx")
        for p in src.rglob(muster)
        if ".test." not in p.name
    )
    # Anführungszeichen als Grenze, nicht bloße Teilzeichenkette: `el:verlauf`
    # steckt sonst in `el:verlauf-tabelle` und gälte als vorhanden, obwohl es
    # die Anzeige nicht mehr gibt.
    fehlend = sorted(
        a for a in anker
        if not re.search(rf"""["']{re.escape(a)}["']""", haystack)
    )
    assert not fehlend, f"Park-Anker ohne Gegenstück in der Oberfläche: {fehlend}"


# ── Die Ausgabewege selbst ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pdf_weg_rendert_wirklich(db):
    """WeasyPrint, nicht nur Jinja.

    Die sieben Proben oben laufen über ``render_html`` — schnell, aber blind
    für alles, was erst WeasyPrint sieht (fehlendes CSS, ein Selektor, den die
    Engine ablehnt). Ein Template-Fehler dieser Art fiele sonst erst im
    ausgelieferten Add-on auf.
    """
    anlage_id = await _seed(db)
    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)

    from backend.services.pdf import render_document
    pdf = render_document("monatsbericht.html", ctx)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2000


@pytest.mark.asyncio
async def test_route_liefert_beide_formate_und_reicht_die_auswahl_durch(db):
    """Die Route ist der Ort, an dem die Auswahl des Anwenders ankommt.

    Sie wird direkt aufgerufen (kein HTTP-Client in dieser Suite) — geprüft
    wird, dass `format`, `themen` und `ohne` **wirken** und nicht nur in der
    Signatur stehen.
    """
    from backend.api.routes.dokumentation import monatsbericht

    anlage_id = await _seed(db)

    pdf = await monatsbericht(anlage_id, JAHR, MONAT, "pdf", None, None, True, db)
    assert pdf.media_type == "application/pdf"
    assert pdf.body.startswith(b"%PDF")

    md = await monatsbericht(anlage_id, JAHR, MONAT, "md", None, None, True, db)
    assert md.media_type.startswith("text/markdown")
    text = md.body.decode("utf-8")
    assert "# Monatsbericht April 2026 — Haus Süd" in text
    assert "## Finanzen" in text

    nur_energie = await monatsbericht(
        anlage_id, JAHR, MONAT, "md", ["energie"], None, True, db
    )
    assert "## Finanzen" not in nur_energie.body.decode("utf-8")

    geparkt = await monatsbericht(
        anlage_id, JAHR, MONAT, "md", None, ["el:bilanz-vergleich"], True, db
    )
    assert "PV-Erzeugung Vorjahr" not in geparkt.body.decode("utf-8")


@pytest.mark.asyncio
async def test_route_meldet_unbekannte_anlage_als_404(db):
    """LookupError des Builders wird zu 404 — nicht zu einem 500er."""
    from fastapi import HTTPException
    from backend.api.routes.dokumentation import monatsbericht

    with pytest.raises(HTTPException) as exc:
        await monatsbericht(999_999, JAHR, MONAT, "pdf", None, None, True, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_kein_spezifischer_ertrag_ohne_gemessene_pv(db):
    """Keine „0,0 kWh/kWp" unter einer PV-Erzeugung „–".

    Die Route bildet den spezifischen Ertrag mit ``pv or 0`` und liefert für
    einen Monat ohne PV-Zahl eine **gemessene Null**. Der Monat hier trägt eine
    Zählerzeile (Netzbezug/Einspeisung), aber keinen PV-Wert — das Leer-Gate
    greift also nicht, und ohne diese Sperre stünden die beiden Zeilen
    widersprüchlich untereinander.
    """
    anlage_id = await _seed(db, mit_werten=False)
    from backend.models import Monatsdaten as MD
    db.add(MD(anlage_id=anlage_id, jahr=JAHR, monat=MONAT,
              netzbezug_kwh=180.0, einspeisung_kwh=520.0))
    await db.commit()

    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)
    md = render_monatsbericht_markdown(ctx)

    # Der Bericht ist NICHT leer — sonst prüfte diese Probe das Leer-Gate.
    assert "Netzbezug | 180 kWh" in md
    assert "| PV-Erzeugung | – |" in md
    assert "| Spezifischer Ertrag | – |" in md
    assert "kWh/kWp" not in md
