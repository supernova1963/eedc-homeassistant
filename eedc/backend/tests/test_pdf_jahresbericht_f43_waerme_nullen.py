"""F-43: Der Jahresbericht darf einer Klimaanlage keine Wärmemengen erfinden.

`WpFakten` trägt `waerme_kwh` / `heizung_kwh` / `warmwasser_kwh` als
``float = 0.0`` — ein Default, kein Messwert. Der PDF-Builder summierte die
Defaults und übergab die Summe roh; das Makro ``fmt_kwh`` rendert nur bei
``None`` ein „–", bei ``0.0`` dagegen „0 kWh". Eine Klimaanlage ohne
Wärmemengenzähler bekam so **drei erfundene Nullen**, während der COP in
derselben Tabelle korrekt „–" sagte (er ist explizit ``None``).

**Warum das nur das PDF traf** (gemessen am 19.08., bevor gebaut wurde):
``aktueller_monat.py`` trägt einen Monatswert nur ``if wert > 0`` ein, liefert
also ``None`` — Cockpit → Monat und die daraus aggregierte Jahressicht sagen
deshalb längst „—". Das PDF war der einzige Konsument ohne diese Trennung;
deshalb sitzt die Lösung im Builder und nicht in der Fakten-Schicht.

Die Gegenrichtung steht mit im selben Modul: **eine WP mit gemessener Wärme
muss ihre Zahlen behalten.** Ohne diese zweite Probe wäre der Fix auch dann
grün, wenn er die Wärme generell unterdrückt.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context


async def _seed(db, *, mit_waerme: bool) -> int:
    """Anlage mit EINER Wärmepumpen-Investition, die Strom zieht.

    ``mit_waerme=False`` bildet die Klimaanlage nach: Stromverbrauch ja,
    Wärmemengenzähler nein.
    """
    anlage = Anlage(anlagenname="F-43", leistung_kwp=10.0,
                    standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()

    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=m,
                           einspeisung_kwh=400.0, netzbezug_kwh=300.0))

    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe",
        bezeichnung="Klimaanlage" if not mit_waerme else "Luft-Wasser",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=5000.0,
        parameter={"wp_art": "luft_luft" if not mit_waerme else "luft_wasser"},
    )
    db.add(wp)
    await db.flush()

    for m in range(1, 13):
        daten: dict[str, float] = {"stromverbrauch_kwh": 100.0}
        if mit_waerme:
            daten["heizenergie_kwh"] = 300.0
            daten["warmwasser_kwh"] = 100.0
        db.add(InvestitionMonatsdaten(
            investition_id=wp.id, jahr=2025, monat=m, verbrauch_daten=daten,
        ))
    await db.commit()
    return anlage.id


@pytest.mark.asyncio
async def test_f43_klimaanlage_ohne_waermezaehler_bekommt_keine_nullen(db):
    """Ohne Wärmemengenzähler: drei Mal ``None``, damit das PDF „–" rendert."""
    anlage_id = await _seed(db, mit_waerme=False)

    ctx = await build_jahresbericht_context(db, anlage_id=anlage_id, jahr=2025)
    wp = ctx["waermepumpe"]

    assert wp["vorhanden"] is True
    # Der Kern des Fehlers: 0.0 hätte „0 kWh" ergeben.
    assert wp["waerme_kwh"] is None
    assert wp["heizung_kwh"] is None
    assert wp["warmwasser_kwh"] is None
    # Der Strom ist gemessen und bleibt eine Zahl — sonst verschwände die
    # einzige Aussage, die über eine Klimaanlage überhaupt zu treffen ist.
    assert wp["strom_kwh"] == pytest.approx(1200.0)
    # Und der COP sagte schon immer „–": genau diese Asymmetrie war der Befund.
    assert wp["cop"] is None


@pytest.mark.asyncio
async def test_f43_waermepumpe_mit_zaehler_behaelt_ihre_zahlen(db):
    """Gegenrichtung: gemessene Wärme darf der Fix nicht unterdrücken."""
    anlage_id = await _seed(db, mit_waerme=True)

    ctx = await build_jahresbericht_context(db, anlage_id=anlage_id, jahr=2025)
    wp = ctx["waermepumpe"]

    assert wp["waerme_kwh"] == pytest.approx(4800.0)   # 12 × (300 + 100)
    assert wp["heizung_kwh"] == pytest.approx(3600.0)
    assert wp["warmwasser_kwh"] == pytest.approx(1200.0)
    assert wp["cop"] == pytest.approx(4.0)             # 4800 / 1200


@pytest.mark.asyncio
async def test_f43_template_rendert_strich_statt_null(db):
    """Die Wirkung am Ausgabemedium, nicht nur am Context.

    Der Context allein beweist nichts über das PDF: „–" entsteht erst durch
    ``fmt_kwh(None)``. Ein Fix, der ``None`` liefert, aber an einer Stelle
    landet, die ``0`` erzwingt, wäre hier rot.
    """
    # N-234 (2026-08-30): Hier stand eine NACHGEBAUTE Jinja-Umgebung. Sie hat
    # den Bericht gerendert, ohne die Umgebung zu benutzen, die ihn produktiv
    # rendert — ein Formatierer-Fehler in `engine.py` wäre hier unsichtbar
    # geblieben. Die Aussage dieser Probe („die Wirkung am Ausgabemedium")
    # trägt unverändert; sie greift jetzt nur an der echten Kette an.
    from backend.services.pdf.engine import render_html

    anlage_id = await _seed(db, mit_waerme=False)
    ctx = await build_jahresbericht_context(db, anlage_id=anlage_id, jahr=2025)

    html = render_html("jahresbericht.html", ctx)

    import re
    block = re.search(r"<h2>Wärmepumpe</h2>.*?</table>", html, re.S)
    assert block, "Wärmepumpen-Block fehlt im gerenderten Bericht"
    zeilen = dict(re.findall(r"<tr><th[^>]*>(.*?)</th><td>(.*?)</td></tr>", block.group(0)))

    assert zeilen["Wärmeenergie gesamt"] == "–"
    assert zeilen["davon Heizung"] == "–"
    assert zeilen["davon Warmwasser"] == "–"
    # Keine ZELLE darf exakt „0 kWh" sein. Bewusst über die Zellwerte statt per
    # Teilstring: „1.200 kWh" enthält „0 kWh" — der erste Entwurf dieser Probe
    # war daran rot, ohne dass am Produktcode etwas fehlte.
    assert "0 kWh" not in zeilen.values()
    # Der gemessene Strom bleibt sichtbar.
    assert zeilen["Stromverbrauch"] == "1.200 kWh"
