"""Abgabe an Dritte (§9.2) — Anzeige, Berichte und Daten-Checker (Commit 3/3).

Die Zeile „Abgabe an Dritte" steht auf der Verwendungsseite (Werte-Tabelle,
Monatsbericht, Jahresbericht) nur dort, wo es die Abgabe gibt; der Daten-
Checker weist auf einen *Erzeuger* hin, der nach einer Abgabe aussieht
(Einspeisung UND Erlös, keine Erzeugung über die Einspeisung hinaus — Roberts
Konstellation), ohne etwas umzustellen.

Schwesterdateien: test_abgabe_an_dritte_vier_sichten.py (Bilanz),
test_abgabe_an_dritte_tag_live.py (Tag/Live), test_daten_checker_bkw_kind_deckt_f39.py
(Daten-Checker-Muster).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: F401
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung  # noqa: F401

JAHR, MONAT = 2025, 7


async def _anlage(db, kategorie: str, daten: dict):
    a = Anlage(anlagenname=f"anz-{kategorie}", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1),
               standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(a)
    await db.flush()
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV", anschaffungsdatum=date(2025, 1, 1),
                     anschaffungskosten_gesamt=10000.0, leistung_kwp=10.0)
    db.add(pv)
    await db.flush()
    so = Investition(anlage_id=a.id, typ="sonstiges", bezeichnung="Victron-EG",
                     anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1000.0,
                     parameter={"kategorie": kategorie})
    db.add(so)
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=JAHR, monat=MONAT, einspeisung_kwh=200.0, netzbezug_kwh=300.0))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=JAHR, monat=MONAT,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=so.id, jahr=JAHR, monat=MONAT, verbrauch_daten=daten))
    db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
                      gueltig_ab=date(2025, 1, 1)))
    await db.commit()
    return a, so


ABGABE = {"abgabe_kwh": 224.0, "einspeise_erloes_euro": 40.0}
ERZEUGER_WIE_ABGABE = {"erzeugung_kwh": 224.0, "einspeisung_kwh": 224.0, "einspeise_erloes_euro": 40.0}
ECHTER_ERZEUGER = {"erzeugung_kwh": 500.0, "einspeisung_kwh": 100.0, "einspeise_erloes_euro": 40.0}


@pytest.mark.asyncio
async def test_tabelle_monatsbericht_und_jahresbericht_tragen_die_zeile(db):
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context
    from backend.services.pdf.builders.monatsbericht import _abschnitte_energie
    from backend.services.pdf.engine import render_html

    a, _ = await _anlage(db, "abgabe", ABGABE)
    zeile = (await list_monatsdaten_aggregiert(anlage_id=a.id, jahr=JAHR, db=db))[0]
    assert zeile.abgabe_dritte_kwh == pytest.approx(224.0)
    assert zeile.eigenverbrauch_kwh == pytest.approx(576.0)

    d = await get_aktueller_monat(a.id, jahr=JAHR, monat=MONAT, db=db)
    labels = [z.label for ab in _abschnitte_energie(d) for z in (vars(ab).get("zeilen") or [])]
    assert "Abgabe an Dritte" in labels

    ctx = await build_jahresbericht_context(db, a.id, JAHR)
    assert ctx["kpis"]["abgabe_dritte_kwh"] == pytest.approx(224.0)
    assert ctx["kpis"]["eigenverbrauch_kwh"] == pytest.approx(576.0)
    html = render_html("jahresbericht.html", ctx)
    assert "Abgabe an Dritte" in html


@pytest.mark.asyncio
async def test_ohne_abgabe_keine_zeile(db):
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context
    from backend.services.pdf.builders.monatsbericht import _abschnitte_energie

    a, _ = await _anlage(db, "erzeuger", ECHTER_ERZEUGER)
    zeile = (await list_monatsdaten_aggregiert(anlage_id=a.id, jahr=JAHR, db=db))[0]
    assert zeile.abgabe_dritte_kwh is None
    d = await get_aktueller_monat(a.id, jahr=JAHR, monat=MONAT, db=db)
    labels = [z.label for ab in _abschnitte_energie(d) for z in (vars(ab).get("zeilen") or [])]
    assert "Abgabe an Dritte" not in labels
    ctx = await build_jahresbericht_context(db, a.id, JAHR)
    assert ctx["kpis"]["abgabe_dritte_kwh"] is None


@pytest.mark.asyncio
async def test_daten_checker_weist_auf_einen_erzeuger_hin_der_wie_eine_abgabe_aussieht(db):
    """Roberts Konstellation: Einspeisung 224 = Erzeugung 224, Erlös 40 € →
    INFO mit Handlung. Ein echtes BHKW (Erzeugung 500 > Einspeisung 100) nicht."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from backend.services.daten_checker import DatenChecker

    async def _geladen(anlage_id: int):
        return (await db.execute(
            select(Anlage)
            .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
            .where(Anlage.id == anlage_id)
        )).scalar_one()

    def _treffer(ergebnisse):
        return [e for e in ergebnisse if "Strom an Dritte" in (e.meldung or "")]

    a, so = await _anlage(db, "erzeuger", ERZEUGER_WIE_ABGABE)
    treffer = _treffer(DatenChecker(db)._check_investitionen(await _geladen(a.id), []))
    assert len(treffer) == 1, treffer
    assert "Victron-EG" in treffer[0].meldung
    assert "Abgabe an Dritte" in (treffer[0].details or "")

    b, _ = await _anlage(db, "erzeuger", ECHTER_ERZEUGER)
    assert not _treffer(DatenChecker(db)._check_investitionen(await _geladen(b.id), []))

    c, _ = await _anlage(db, "abgabe", ABGABE)
    assert not _treffer(DatenChecker(db)._check_investitionen(await _geladen(c.id), [])), "umgestellt = erledigt"
