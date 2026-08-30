"""N-136: Der Jahresbericht bildet die Mehrkosten über den Layer-SoT.

Der Builder rechnete ``Σ gesamt − Σ alternativ`` — **ungeklemmt**, über die
ganze Anlage summiert. Der Layer-SoT
``investitionskosten.relevante_kosten_aus_investitionen`` klemmt dagegen **je
Position**: ``Σ max(0, gesamt − alternativ)``. Solange keine Alternative teurer
ist als die Sache selbst, liefern beide dasselbe; sobald **eine** Position eine
teurere Alternative hat, zieht die alte Form deren Überschuss von den
Mehrkosten der **anderen** Positionen ab.

**Das ist der Regelfall, nicht die Ausnahme:** Ein E-Auto ist typischerweise
teurer als das Auto, das es ersetzt — nein, andersherum, und genau darum geht
es: Wer als Alternative einen teureren Verbrenner einträgt, bekam einen zu
kleinen Nenner und damit eine **zu hohe Rendite und Amortisation** im PDF.

**Vier Sichten rechnen die Größe über den SoT** — Cockpit → Übersicht
(``uebersicht.py:641``, dort sogar unter demselben Variablennamen), ROI
(``crud.py:1520``), Aussichten (``aussichten.py:1242``) und der Wallbox-Hub.
Der Jahresbericht war der fünfte Ort und der einzige mit einer eigenen Form.

Die Zusicherung lautet deshalb nicht „die Zahl ist 20.000", sondern **„die Zahl
ist die des SoT"** — eine künftige Neuformulierung neben dem Helfer wäre sonst
wieder grün.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen import relevante_kosten_aus_investitionen
from backend.models import Anlage, Investition, Monatsdaten
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context


async def _seed(db, *, alternative_teurer: bool) -> tuple[int, list]:
    """Anlage mit zwei Positionen; eine davon wahlweise mit teurerer Alternative.

    ``alternative_teurer=False`` ist der Gegenanker: dort sind beide Formen
    rechnerisch gleich, und der Fix darf nichts bewegen.
    """
    anlage = Anlage(anlagenname="N-136", leistung_kwp=10.0,
                    standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()

    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=m,
                           einspeisung_kwh=400.0, netzbezug_kwh=300.0))

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="PV-Dach",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=20000.0,
        anschaffungskosten_alternativ=None,
        leistung_kwp=10.0,
    )
    # Das E-Auto trägt die Alternative: ein Verbrenner, der mehr gekostet hätte.
    auto = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Stromer",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=30000.0,
        anschaffungskosten_alternativ=35000.0 if alternative_teurer else 25000.0,
    )
    db.add_all([pv, auto])
    await db.commit()
    return anlage.id, [pv, auto]


@pytest.mark.asyncio
async def test_n136_teurere_alternative_zieht_die_anderen_posten_nicht_herunter(db):
    """Der Kern des Befunds: 20.000 (geklemmt) statt 15.000 (ungeklemmt)."""
    anlage_id, invs = await _seed(db, alternative_teurer=True)

    ctx = await build_jahresbericht_context(db, anlage_id=anlage_id, jahr=2025)
    mehrkosten = ctx["kpis"]["investition_mehrkosten_euro"]

    # Σ max(0, 20000−0) + max(0, 30000−35000) = 20000 + 0
    assert mehrkosten == pytest.approx(20000.0)
    # Die ungeklemmte Form hätte 50000 − 35000 = 15000 ergeben. Der Wert steht
    # als „Investition Mehrkosten (vs. Alternative)" im PDF.
    assert mehrkosten != pytest.approx(15000.0)


@pytest.mark.asyncio
async def test_n136_mehrkosten_sind_die_zahl_des_layer_sot(db):
    """Nicht „ist 20.000", sondern „ist die des SoT" — gegen Neuformulierung.

    Diese Zusicherung ist die eigentliche Absicherung: Sie bleibt auch dann
    wahr, wenn sich die Klemm-Regel im Layer je ändert, und sie wird rot,
    sobald jemand die Formel neben dem Helfer erneut ausschreibt.
    """
    anlage_id, invs = await _seed(db, alternative_teurer=True)

    ctx = await build_jahresbericht_context(db, anlage_id=anlage_id, jahr=2025)

    assert ctx["kpis"]["investition_mehrkosten_euro"] == pytest.approx(
        relevante_kosten_aus_investitionen(invs)
    )


@pytest.mark.asyncio
async def test_n136_rendite_und_amortisation_teilen_durch_denselben_nenner(db):
    """Der Nenner ist die Wirkung — nicht die ausgewiesene Zeile allein.

    Rendite und Amortisation entstehen aus ``netto_nach_bk ÷ mehrkosten``. Ein
    Fix, der nur die ausgewiesene Zahl korrigiert und den Nenner der beiden
    Quotienten stehen lässt, wäre hier rot.
    """
    anlage_id, _ = await _seed(db, alternative_teurer=True)

    ctx = await build_jahresbericht_context(db, anlage_id=anlage_id, jahr=2025)
    kpis = ctx["kpis"]
    mehrkosten = kpis["investition_mehrkosten_euro"]
    netto_nach_bk = kpis["netto_nach_bk_euro"]

    assert mehrkosten > 0
    erwartet = netto_nach_bk / mehrkosten * 100
    assert kpis["rendite_prozent"] == pytest.approx(erwartet)
    assert kpis["amortisation_prozent"] == pytest.approx(erwartet)


@pytest.mark.asyncio
async def test_n136_ohne_teurere_alternative_bewegt_sich_nichts(db):
    """Gegenanker: der Normalfall darf sich durch den Fix NICHT ändern.

    Ohne diese Probe wäre auch ein Fix grün, der die Alternativkosten schlicht
    ignoriert — er würde hier 50.000 statt 25.000 liefern.
    """
    anlage_id, invs = await _seed(db, alternative_teurer=False)

    ctx = await build_jahresbericht_context(db, anlage_id=anlage_id, jahr=2025)

    # Σ max(0, 20000−0) + max(0, 30000−25000) = 20000 + 5000 — und die alte,
    # ungeklemmte Form liefert hier dieselben 25000.
    assert ctx["kpis"]["investition_mehrkosten_euro"] == pytest.approx(25000.0)
    assert ctx["kpis"]["investition_mehrkosten_euro"] == pytest.approx(
        relevante_kosten_aus_investitionen(invs)
    )
