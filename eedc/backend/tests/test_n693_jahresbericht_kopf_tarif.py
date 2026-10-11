"""N-693 (Teil PDF-Kopf) — der Jahresbericht nennt den Allgemeintarif, mit dem seine Monate rechnen.

Gemessen am HEAD `ee222ed7`: der Kopf „Stromtarif" war der jüngste Tarif-Eintrag der Anlage, ohne `verwendung` und
ohne Stichtag. Mit „Alt 28 ct bis 06/2025 · Neu 32,5 ct ab 07/2025 · WP-Werk 22 ct (Wärmepumpe) ab 10/2025" stand in
den Berichten 2024, 2025 und im Gesamtzeitraum derselbe **WP-Tarif** — der Bericht 2024 nannte einen Tarif, der erst
fünfzehn Monate nach seinem Ende galt, und keiner nannte einen Tarif, mit dem eine Zeile gerechnet war.

Soll (Auftrag D, RF-9-B1-Nachtrag): Stichtag je Monat des Berichts wie die Monats-Fakten (Monatserster, P8),
Allgemeintarif; wechselt er im Zeitraum, nennt der Kopf jeden Abschnitt.

Schwesterdateien: test_n693_ersatzpreis_vor_dem_ersten_tarif.py (derselbe Fund im HA-Export),
test_pdf_jahresbericht_f43_waerme_nullen.py (der Bericht mit dem echten Template gerendert).
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten


async def _anlage(db, tarife, monate):
    a = Anlage(anlagenname="N693-Kopf", leistung_kwp=6.0, installationsdatum=date(monate[0][0], monate[0][1], 1),
               standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(a)
    await db.flush()
    for anbieter, preis, ab, bis, verwendung in tarife:
        db.add(Strompreis(anlage_id=a.id, anbieter=anbieter, tarifname=f"{anbieter}-Tarif", verwendung=verwendung,
                          netzbezug_arbeitspreis_cent_kwh=preis, einspeiseverguetung_cent_kwh=8.1,
                          gueltig_ab=ab, gueltig_bis=bis))
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV", anschaffungsdatum=date(monate[0][0], monate[0][1], 1),
                     anschaffungskosten_gesamt=10000.0, leistung_kwp=6.0)
    db.add(pv)
    await db.flush()
    for j, m in monate:
        db.add(Monatsdaten(anlage_id=a.id, jahr=j, monat=m, einspeisung_kwh=300.0, netzbezug_kwh=150.0))
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=j, monat=m, verbrauch_daten={"pv_erzeugung_kwh": 500.0}))
    await db.commit()
    return a.id


B1 = [
    ("Alt", 28.0, date(2024, 1, 1), date(2025, 6, 30), "allgemein"),
    ("Neu", 32.5, date(2025, 7, 1), None, "allgemein"),
    ("WP-Werk", 22.0, date(2025, 10, 1), None, "waermepumpe"),
]
MONATE_B1 = [(2024, m) for m in range(1, 13)] + [(2025, m) for m in range(1, 12)]


@pytest.mark.asyncio
async def test_bericht_2024_nennt_den_tarif_von_2024(db):
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    aid = await _anlage(db, B1, MONATE_B1)
    tarif = (await build_jahresbericht_context(db, aid, 2024))["tarif"]
    assert (tarif["anbieter"], tarif["netzbezug_cent"]) == ("Alt", 28.0), f"am HEAD: WP-Werk 22,0 — {tarif}"
    assert tarif["zeitraeume"] == [], "ein Tarif im ganzen Jahr — keine Abschnitte"


@pytest.mark.asyncio
async def test_bericht_2025_nennt_den_wechsel_und_keinen_wp_tarif(db):
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context
    from backend.services.pdf.engine import render_html

    aid = await _anlage(db, B1, MONATE_B1)
    ctx = await build_jahresbericht_context(db, aid, 2025)
    tarif = ctx["tarif"]
    assert (tarif["anbieter"], tarif["netzbezug_cent"]) == ("Neu", 32.5), f"Ende des Zeitraums — {tarif}"
    assert [(z["von"], z["bis"], z["anbieter"], z["netzbezug_cent"]) for z in tarif["zeitraeume"]] == [
        ("01/2025", "06/2025", "Alt", 28.0),
        ("07/2025", "11/2025", "Neu", 32.5),
    ]
    html = render_html("jahresbericht.html", ctx)
    kopf = re.search(r"<th>Stromtarif</th><td>(.*?)</td>", html, re.S).group(1)
    assert "WP-Werk" not in kopf
    assert re.search(r"01/2025–06/2025:\s*Alt – Alt-Tarif", kopf), kopf
    assert re.search(r"07/2025–11/2025:\s*Neu – Neu-Tarif", kopf), kopf


@pytest.mark.asyncio
async def test_gesamtzeitraum_nennt_beide_abschnitte(db):
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    aid = await _anlage(db, B1, MONATE_B1)
    tarif = (await build_jahresbericht_context(db, aid, None))["tarif"]
    assert [(z["von"], z["bis"], z["anbieter"]) for z in tarif["zeitraeume"]] == [
        ("01/2024", "06/2025", "Alt"), ("07/2025", "11/2025", "Neu"),
    ]


@pytest.mark.asyncio
async def test_monate_vor_dem_ersten_tarif_stehen_mit_der_vorbelegung_da(db):
    """Die Monate vor dem ersten Tarif rechnen die Monats-Fakten mit 30 ct — der Kopf sagt es."""
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context
    from backend.services.pdf.engine import render_html

    aid = await _anlage(db, [("Werk", 35.0, date(2025, 3, 1), None, "allgemein")], [(2025, m) for m in range(1, 7)])
    ctx = await build_jahresbericht_context(db, aid, 2025)
    z = ctx["tarif"]["zeitraeume"]
    assert [(x["von"], x["bis"], x["ohne_tarif"], x["netzbezug_cent"]) for x in z] == [
        ("01/2025", "02/2025", True, 30.0),
        ("03/2025", "06/2025", False, 35.0),
    ]
    kopf = re.search(r"<th>Stromtarif</th><td>(.*?)</td>", render_html("jahresbericht.html", ctx), re.S).group(1)
    assert re.search(r"01/2025–02/2025:\s*kein Tarif hinterlegt \(Vorbelegung\)", kopf), kopf
