"""N-731 — Jahresbericht-PDF: die Zeile „Investition Mehrkosten" nennt den Rendite-Nenner und sagt, welche Investitionen er zählt.

Am HEAD `7fb9b026` (Triage 12.10., R1): die Zeile zählte nur die im Berichtsjahr aktiven Investitionen (`aktiv_im_jahr`), die
Rendite-Zeile darunter teilt seit N-720 durch die Mehrkosten der bis 31.12. angeschafften — Stillgelegte eingeschlossen
(Cockpit → Übersicht). Zwei „Mehrkosten" auf einer Seite, sobald vor dem Berichtsjahr etwas stillgelegt wurde
(Golden Master Z1 2025: 120 000 gegen 130 000 €). Entscheid Master 12.10.: die Zeile nennt den Rendite-Nenner und ist so
beschriftet.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.tests.test_n699_pdf_betriebskosten_amortisation import _m, _seed


@pytest.mark.asyncio
async def test_mehrkosten_zeile_gleich_rendite_nenner_mit_stillgelegter_investition(db):
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context
    from backend.services.pdf.engine import render_html

    aid = await _seed(db, monate=_m((2024, 2025)), extra=[
        ("speicher", dict(anschaffungsdatum=date(2024, 1, 1), stilllegungsdatum=date(2024, 12, 31),
                          anschaffungskosten_gesamt=5000.0, parameter={"kapazitaet_kwh": 5.0}), {}),
    ])
    ctx = await build_jahresbericht_context(db, aid, 2025)
    k = ctx["kpis"]
    assert k["rendite_nenner_euro"] == pytest.approx(15000.0)
    assert k["investition_mehrkosten_euro"] == pytest.approx(k["rendite_nenner_euro"])

    html = render_html("jahresbericht.html", ctx)
    zeile = html[html.index("Investition Mehrkosten"):]
    zeile = zeile[:zeile.index("</tr>")]
    assert "15.000" in zeile
    assert "bis 31.12.2025 angeschafft" in zeile
    assert "stillgelegt" in zeile


@pytest.mark.asyncio
async def test_ohne_stilllegung_bleibt_die_zahl(db):
    """Gegenprobe: ohne Stilllegung sind beide Mengen gleich — die Zeile nennt dieselbe Zahl wie vorher (10 000 €)."""
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    aid = await _seed(db, monate=_m((2024, 2025)))
    k = (await build_jahresbericht_context(db, aid, 2025))["kpis"]
    assert k["investition_mehrkosten_euro"] == pytest.approx(10000.0) == pytest.approx(k["rendite_nenner_euro"])
