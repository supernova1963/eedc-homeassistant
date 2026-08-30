"""Monatsbericht (#395 Punkt 4, OB73-gif) — die Proben des Konzepts.

Konzept: ``docs/KONZEPT-MONATSBERICHT.md``.

Die tragende Probe ist die erste: **das Template schreibt die Werte
unverändert**. Sie ist der Rest der Sicherung gegen **N-7** — die
zurückgebaute Social-Media-Textvorlage trug eine eigene
Netto-Ertrag-Kurzformel und ist mit dem Text *verschwunden*, statt behoben zu
werden.

⭐ **Sie hieß bis 2026-08-30 „beide Formate nennen dieselben Zahlen"** und
verglich PDF-HTML mit Markdown. Mit dem Entscheid, das Thema *Teilen* nicht zu
verfolgen, ist der Markdown-Weg entfallen — und damit die zweite
Bildungsstelle, die sie bewachte. **Die Probe ist nicht gestrichen, sondern auf
ihre Aussage umgestellt:** Ein Renderer darf eine Zahl auf dem Weg nicht
anfassen. Das ist die Hälfte, die auch mit einem Format wahr sein muss.

Die übrigen halten je eine Entscheidung fest: Themenschalter, deutsche
Schreibweise, leerer Monat, Park-Filter und — die wichtigste der drei
Park-Bedingungen — **ohne mitgeschickte Liste ist der Bericht vollständig**
(Fall „am Tablet geparkt, am PC erzeugt").
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
async def test_das_template_schreibt_die_werte_unveraendert(db):
    """Jeder Wert des Contexts steht **zeichengleich** im gerenderten Dokument.

    Der Builder liefert fertig formatierte Zeichenketten; das Template rechnet
    nichts und formatiert nichts. Rot, sobald jemand im Template ein
    ``|fmt_…`` einsetzt, rundet oder eine Einheit anhängt — genau das wäre die
    zweite Bildungsstelle, gegen die dieses Modul gebaut ist (**N-7**).

    ⭐ Diese Probe ist der Rest von „beide Formate nennen dieselben Zahlen":
    Mit dem Wegfall des Markdown-Renderers gibt es kein zweites Format mehr zu
    vergleichen — **aber die Aussage, dass der Renderer nichts anfasst, gilt
    für einen genauso.**
    """
    anlage_id = await _seed(db)
    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)
    text = _als_text(render_html("monatsbericht.html", ctx))

    werte = [
        z.wert for a in ctx["abschnitte"] for z in a.zeilen
        if z.wert and z.wert != "–"
    ]
    assert len(werte) >= 10, "Ohne Werte prüft die Probe nichts"
    fehlend = [w for w in werte if w not in text]
    assert not fehlend, f"vom Template verändert oder verschluckt: {fehlend[:5]}"

    # Gegenrichtung: die Zahlen des Dokuments sind GENAU die des Contexts —
    # sonst wäre die Probe auch grün, wenn das Template eine erfände.
    assert set(_zahlen(text)) >= set(z for w in werte for z in _zahlen(w))


# ── Probe 2: Themenschalter ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_abgewaehltes_thema_fehlt_im_dokument(db):
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

    text_ohne = _als_text(render_html("monatsbericht.html", ohne_finanzen))
    assert "Einspeise-Erlös" not in text_ohne
    assert "Einspeise-Erlös" in _als_text(render_html("monatsbericht.html", voll))


# ── Probe 3: Identität ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_der_bericht_nennt_immer_anlage_und_standort(db):
    """⛔ Hier stand bis 2026-08-30 die Gegenrichtung: `mit_identitaet=False`.

    Der Schalter „Anlagenname und Standort nennen" ist entfallen (Entscheid
    Gernot) — seine Begründung war der Forumspost, und das Thema *Teilen* wird
    nicht verfolgt. **Die Probe ist deshalb umgedreht, nicht gestrichen:** Sie
    hält jetzt fest, dass die Angaben *immer* im Dokument stehen. Ohne sie
    könnte der Kopf sie verlieren, ohne dass ein Lauf rot wird.
    """
    anlage_id = await _seed(db)
    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)
    text = _als_text(render_html("monatsbericht.html", ctx))

    assert "Haus Süd" in text
    assert "Berlin" in text
    assert "10115" in text


# ── Probe 4: deutsche Schreibweise ────────────────────────────────────────

@pytest.mark.asyncio
async def test_deutsche_schreibweise_im_dokument(db):
    """N-234 erbt sich nicht von selbst — ungeprüft ist ungeprüft.

    Gesucht wird die **englische** Form: eine Dezimalzahl mit Punkt.
    """
    anlage_id = await _seed(db)
    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)

    text = _als_text(render_html("monatsbericht.html", ctx))

    # `1.100` (Tausenderpunkt) ist deutsch, `1100.5` wäre englisch:
    # ein Punkt mit weniger oder mehr als drei Ziffern dahinter.
    # ⚠ Das Erzeugungsdatum muss VORHER heraus. „30.08.2026" enthält `0.08` und
    # `8.2026` — der erste Entwurf dieser Probe meldete es als englischen
    # Dezimalpunkt und wäre bei JEDEM Bericht rot gewesen, ohne dass eine Zahl
    # falsch geschrieben war.
    datum = re.compile(r"\d{2}\.\d{2}\.\d{4}")
    englisch = re.compile(r"\d\.\d{1,2}(?![\d.])|\d\.\d{4,}")
    treffer = englisch.findall(datum.sub(" ", text))
    assert not treffer, f"englische Dezimalpunkte {treffer}"
    # Und mindestens ein Dezimalkomma muss vorkommen, sonst prüft die Probe nichts.
    assert re.search(r"\d,\d", text)


# ── Probe 5: Monat ohne Daten ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_monat_ohne_daten_nennt_den_grund_statt_nullen(db):
    """F-43-Klasse: keine erfundene Null, wo nichts gemessen wurde."""
    anlage_id = await _seed(db, mit_werten=False)
    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)

    text = _als_text(render_html("monatsbericht.html", ctx))

    assert "liegen zu den gewählten Themen keine Werte vor" in text
    assert "0 kWh" not in text


# ── Probe 6: Park-Filter ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_geparkte_anzeige_fehlt_im_dokument(db):
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

    assert "PV-Erzeugung Vorjahr" not in _als_text(
        render_html("monatsbericht.html", geparkt)
    )


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
async def test_route_liefert_das_pdf_und_reicht_die_auswahl_durch(db):
    """Die Route ist der Ort, an dem die Auswahl des Anwenders ankommt.

    Sie wird direkt aufgerufen (kein HTTP-Client in dieser Suite) — geprüft
    wird, dass `format`, `themen` und `ohne` **wirken** und nicht nur in der
    Signatur stehen.
    """
    from backend.api.routes.dokumentation import monatsbericht

    anlage_id = await _seed(db)

    pdf = await monatsbericht(anlage_id, JAHR, MONAT, None, None, db)
    assert pdf.media_type == "application/pdf"
    assert pdf.body.startswith(b"%PDF")
    assert b"monatsbericht_2026-04" in pdf.headers["content-disposition"].encode()

    # Dass `themen` und `ohne` WIRKEN und nicht nur in der Signatur stehen,
    # prüft der Context — im fertigen PDF wäre es nur über eine
    # Textextraktion zu sehen, die WeasyPrint hier nicht anbietet.
    from backend.services.pdf.builders.monatsbericht import build_monatsbericht_context

    nur_energie = await build_monatsbericht_context(
        db, anlage_id, JAHR, MONAT, themen=["energie"]
    )
    assert {a.thema for a in nur_energie["abschnitte"]} == {"energie"}

    geparkt = await build_monatsbericht_context(
        db, anlage_id, JAHR, MONAT, geparkte_ids=["el:bilanz-vergleich"]
    )
    assert geparkt["weggelassen"] == ["Vergleich mit dem Vorjahresmonat"]


@pytest.mark.asyncio
async def test_route_meldet_unbekannte_anlage_als_404(db):
    """LookupError des Builders wird zu 404 — nicht zu einem 500er."""
    from fastapi import HTTPException
    from backend.api.routes.dokumentation import monatsbericht

    with pytest.raises(HTTPException) as exc:
        await monatsbericht(999_999, JAHR, MONAT, None, None, db)
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
    zeilen = {z.label: z.wert for a in ctx["abschnitte"] for z in a.zeilen}

    # Der Bericht ist NICHT leer — sonst prüfte diese Probe das Leer-Gate.
    assert zeilen.get("Netzbezug") == "180 kWh"
    assert zeilen.get("PV-Erzeugung") == "–"
    assert zeilen.get("Spezifischer Ertrag") == "–"
    # Gegenrichtung: die Einheit steht nirgends allein da — sonst wäre die
    # Probe auch grün, wenn der Wert nur anders formatiert wäre.
    assert "kWh/kWp" not in _als_text(render_html("monatsbericht.html", ctx))


# ═════════════════════════════════════════════════════════════════════════════
# Stufe 2 — grafische Aufbereitung + Community
#
# Die Proben hier decken das ab, was die Aufmachung NEU einführen kann: eine
# externe Abhängigkeit, ein Chart, das eine Zahl behauptet, und eine Lücke, die
# als Null durchgeht.
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_community_ausfall_kostet_den_bericht_nicht(db, monkeypatch):
    """ADR-002/**P4**: Der Community-Server ist extern — sein Ausfall ist normal.

    Nicht erreichbar, langsam, 5xx, keine Daten für den Monat: jeder dieser
    Fälle darf **nur** den Community-Abschnitt kosten, nie die übrigen. Ohne
    diese Zusicherung hinge ein Archivdokument an der Erreichbarkeit eines
    fremden Servers.
    """
    import backend.api.routes.community as community_modul

    anlage_id = await _seed(db)

    async def _faellt_aus(jahr: int, monat: int):
        raise RuntimeError("Community-Server nicht erreichbar")

    monkeypatch.setattr(community_modul, "get_monatsbenchmark", _faellt_aus)

    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)

    assert not any(a.thema == "community" for a in ctx["abschnitte"]), \
        "Bei Ausfall darf KEIN Community-Abschnitt entstehen — auch keiner mit Strichen"
    # Und der Rest steht vollständig: beide Formate rendern durch.
    assert len(ctx["abschnitte"]) >= 10
    text = _als_text(render_html("monatsbericht.html", ctx))
    assert "Community" not in text
    # Und der Rest ist wirklich da, nicht nur „nicht leer".
    assert "Kennzahlen" in text and "Finanzen" in text


@pytest.mark.asyncio
async def test_community_abschnitt_nennt_die_anzahl_der_anlagen(db, monkeypatch):
    """Ein Vergleich gegen 3 Anlagen ist etwas anderes als gegen 300.

    ⛔ Ein **Stand-Datum** steht bewusst NICHT dabei (Entscheid Gernot,
    30.08.): Der Vergleichsmonat *ist* der Berichtsmonat, damit ist der
    Vergleich definiert — wann er gezogen wurde, ändert die Aussage nicht.
    """
    import backend.api.routes.community as community_modul

    anlage_id = await _seed(db)

    async def _antwortet(jahr: int, monat: int):
        return {
            "jahr": jahr, "monat": monat, "anzahl_anlagen": 42,
            "autarkie": {"median": 55.0},
            "einspeisung": {"median": 300.0},
        }

    monkeypatch.setattr(community_modul, "get_monatsbenchmark", _antwortet)

    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)
    abschnitt = next(a for a in ctx["abschnitte"] if a.thema == "community")

    assert any(z.label == "Verglichene Anlagen" and "42" in z.wert for z in abschnitt.zeilen)
    assert any("Community-Median" in (z.hinweis or "") for z in abschnitt.zeilen)
    # Gegenrichtung: kein Datum im Abschnitt — sonst wäre der Entscheid gekippt.
    text = " ".join(f"{z.label} {z.wert} {z.hinweis or ''}" for z in abschnitt.zeilen)
    assert not re.search(r"\d{2}\.\d{2}\.\d{4}", text)

    # Im Dokument — und ohne den Schalter nicht.
    assert "Community-Vergleich" in _als_text(render_html("monatsbericht.html", ctx))
    ohne = await build_monatsbericht_context(
        db, anlage_id, JAHR, MONAT, themen=[t for t in THEMEN if t != "community"],
    )
    assert "Community-Vergleich" not in _als_text(render_html("monatsbericht.html", ohne))


@pytest.mark.asyncio
async def test_community_ohne_anlagen_erscheint_nicht(db, monkeypatch):
    """Null verglichene Anlagen ist kein Vergleich, sondern eine leere Seite."""
    import backend.api.routes.community as community_modul

    anlage_id = await _seed(db)

    async def _leer(jahr: int, monat: int):
        return {"jahr": jahr, "monat": monat, "anzahl_anlagen": 0}

    monkeypatch.setattr(community_modul, "get_monatsbenchmark", _leer)
    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)
    assert not any(a.thema == "community" for a in ctx["abschnitte"])


def test_chart_zaehlt_einen_tag_ohne_messung_nicht_als_null():
    """⛔ ``None`` ist keine Null — die Klasse aus KONZEPT-UNVOLLSTAENDIGE-WERTE.

    Ein Tag ohne gemessene Erzeugung bekommt **keinen** Balken. Ein Balken der
    Höhe 0 neben echten Werten liest sich als „an diesem Tag kam nichts", und
    genau diese Verwechslung wäre eine erfundene Aussage.
    """
    import base64

    from backend.services.pdf.charts import tagesverlauf_chart

    def _balken(svg_uri: str, farbe: str) -> int:
        svg = base64.b64decode(svg_uri.split(",", 1)[1]).decode("utf-8")
        return len(re.findall(rf'<rect[^>]*fill="{farbe}"', svg))

    PV = "#f59e0b"
    # Drei gemessene Tage, einer ohne Messung. +1 = das Legenden-Kästchen.
    mit_luecke = tagesverlauf_chart([1, 2, 3, 4], [10.0, None, 12.5, 8.0])
    assert _balken(mit_luecke, PV) == 3 + 1

    # Gegenrichtung: eine GEMESSENE Null bleibt ein Balken (der Höhe 0) und
    # verschwindet nicht — sonst unterdrückte der Fix jede Null.
    mit_null = tagesverlauf_chart([1, 2, 3, 4], [10.0, 0.0, 12.5, 8.0])
    assert _balken(mit_null, PV) == 4 + 1


def test_tagesprofil_bricht_die_linie_an_der_luecke():
    """Eine Linie, die an einer Lücke auf 0 fällt, behauptet einen Einbruch."""
    import base64

    from backend.services.pdf.charts import tagesprofil_chart

    svg = base64.b64decode(
        tagesprofil_chart([0, 1, 2, 3, 4], [1.0, 2.0, None, 3.0, 4.0]).split(",", 1)[1]
    ).decode("utf-8")
    # Zwei Segmente statt einer durchgehenden Linie.
    assert svg.count("<polyline") == 2

    ohne_luecke = base64.b64decode(
        tagesprofil_chart([0, 1, 2, 3, 4], [1.0, 2.0, 2.5, 3.0, 4.0]).split(",", 1)[1]
    ).decode("utf-8")
    assert ohne_luecke.count("<polyline") == 1


@pytest.mark.asyncio
async def test_die_aufmachung_fuegt_dem_dokument_keine_zahl_hinzu(db):
    """Kacheln, Leisten und Charts sind Darstellung — keine zweite Zahlenquelle.

    Zwei Zusicherungen: jedes Leisten-Segment hat eine **Zeile** (sonst stünde
    seine Zahl nur im Bild), und die **Legende trägt keine Zahl** (sonst stünde
    sie zweimal im Dokument — genau der Fehler des ersten Entwurfs).
    """
    anlage_id = await _seed(db)
    ctx = await build_monatsbericht_context(db, anlage_id, JAHR, MONAT)

    hat_darstellung = [
        a for a in ctx["abschnitte"]
        if a.darstellung != "tabelle" or a.balken or a.chart
    ]
    assert hat_darstellung, "Ohne einen einzigen aufbereiteten Abschnitt prüft diese Probe nichts"

    for a in hat_darstellung:
        for b in (a.balken or []):
            assert any(z.label == b.label for z in a.zeilen), \
                f"Leisten-Segment '{b.label}' hat keine Zeile — das wäre eine Zahl nur im PDF"

    # ⛔ Und die Legende der Leiste trägt KEINE Zahl.
    #
    # Das ist der konkrete Fehler, den der erste Entwurf hatte: Sie druckte
    # `{{ b.wert }}`, womit jede dieser Zahlen zweimal im Dokument stand.
    # ⚠ Hier stand zuerst eine Zusicherung, die die Zahlen des Dokuments mit
    # den Zahlen des Dokuments verglich — sie konnte per Konstruktion nicht rot
    # werden. Jetzt wird die Legende selbst gelesen.
    html = render_html("monatsbericht.html", ctx)
    legenden = re.findall(
        r'<ul class="leiste-legende">(.*?)</ul>', html, flags=re.S,
    )
    assert legenden, "keine Leiste gerendert — die Probe misst nichts"
    for legende in legenden:
        sichtbar = re.sub(r"<[^>]+>", " ", legende)
        assert not re.search(r"\d", sichtbar), \
            f"Legende trägt eine Zahl: {sichtbar.strip()[:80]}"
