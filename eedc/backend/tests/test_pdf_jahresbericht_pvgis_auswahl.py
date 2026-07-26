"""PDF-Jahresbericht: PVGIS-Spalte liest den richtigen Key und genau EINE Prognose (A12).

Zwei Fehler an derselben Stelle:

1. Der Monatswert wurde unter `e_month_kwh` gesucht — den Key gibt es nirgends.
   `api/routes/pvgis.py` schreibt `e_m` (so auch im Modell-Kommentar und im
   String-Vergleich desselben Builders). Folge: Spalte „PVGIS-Prognose" der
   Monatstabelle und die SOLL-Linie im PV-Chart waren immer 0.
2. Es wurde über ALLE Prognosen der Anlage summiert (kein `ist_aktiv`, kein
   `order_by`). Solange der Key falsch war, blieb das unsichtbar — mit
   korrektem Key wäre bei zwei gespeicherten Prognosen der doppelte Wert
   erschienen. Deshalb gehören beide Korrekturen zusammen.

Auswahlregel wie überall sonst (`services/prognose_kanon.py`, Cockpit,
Aussichten, HA-Export): `ist_aktiv == True`, bei mehreren die zuletzt abgerufene.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.models import Anlage, Investition, Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

AKTIV_JAHR = 18_000.0
ALT_JAHR = 9_000.0


def _monatswerte(jahressumme: float) -> list[dict]:
    return [{"monat": m, "e_m": jahressumme / 12, "h_m": 100.0, "sd_m": 10.0} for m in range(1, 13)]


async def _seed(db) -> int:
    anlage = Anlage(anlagenname="PVGIS-Auswahl", leistung_kwp=15.0,
                    standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()
    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=m,
                           einspeisung_kwh=400.0, netzbezug_kwh=300.0))
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süddach",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=15.0,
        ausrichtung="Süd", neigung_grad=30, anschaffungskosten_gesamt=15_000.0,
    ))

    gemeinsam = dict(
        anlage_id=anlage.id, latitude=48.0, longitude=11.0,
        neigung_grad=30.0, ausrichtung_grad=0.0, system_losses=14.0,
        gesamt_leistung_kwp=15.0,
    )
    # Alte, deaktivierte Prognose (z. B. vor einer Modul-Erweiterung abgerufen).
    db.add(PVGISPrognose(
        **gemeinsam,
        abgerufen_am=datetime(2024, 3, 1, 12, 0),
        jahresertrag_kwh=ALT_JAHR, spezifischer_ertrag_kwh_kwp=ALT_JAHR / 15.0,
        monatswerte=_monatswerte(ALT_JAHR), ist_aktiv=False,
    ))
    # Die aktive Prognose — nur sie darf im PDF stehen.
    db.add(PVGISPrognose(
        **gemeinsam,
        abgerufen_am=datetime(2025, 2, 1, 12, 0),
        jahresertrag_kwh=AKTIV_JAHR, spezifischer_ertrag_kwh_kwp=AKTIV_JAHR / 15.0,
        monatswerte=_monatswerte(AKTIV_JAHR), ist_aktiv=True,
    ))
    await db.flush()
    return anlage.id


def _pvgis_summe(ctx: dict) -> float:
    return sum(m["pvgis_prognose_kwh"] for m in ctx["monats_zeilen"])


async def test_pvgis_spalte_ist_nicht_null(db):
    """Mit dem richtigen Key `e_m` stehen echte Werte in der Monatstabelle."""
    anlage_id = await _seed(db)
    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    monate = [m["pvgis_prognose_kwh"] for m in ctx["monats_zeilen"]]
    assert all(w > 0 for w in monate), "PVGIS-Spalte immer noch 0 — falscher Monatswert-Key."
    assert monate[0] == pytest.approx(AKTIV_JAHR / 12, abs=0.5)


async def test_pvgis_spalte_nimmt_nur_die_aktive_prognose(db):
    """Zwei gespeicherte Prognosen ⇒ die aktive, nicht deren Summe."""
    anlage_id = await _seed(db)
    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    summe = _pvgis_summe(ctx)
    assert summe == pytest.approx(AKTIV_JAHR, abs=1)
    assert summe != pytest.approx(AKTIV_JAHR + ALT_JAHR, abs=1), (
        "PVGIS-Spalte summiert wieder über alle Prognosen der Anlage."
    )


async def test_string_soll_nutzt_dieselbe_prognose_wie_die_monatstabelle(db):
    """Monatstabelle und String-Vergleich desselben PDFs dürfen sich nicht widersprechen."""
    anlage_id = await _seed(db)
    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    soll = sum(s["prognose_kwh"] for s in ctx["string_vergleiche"])
    assert soll == pytest.approx(_pvgis_summe(ctx), abs=1)
    assert soll == pytest.approx(AKTIV_JAHR, abs=1)


async def test_aeltere_aber_aktivierte_prognose_gewinnt(db):
    """`ist_aktiv` schlägt „neueste" — der Nutzer kann bewusst eine alte aktivieren."""
    anlage_id = await _seed(db)
    from sqlalchemy import select
    res = await db.execute(
        select(PVGISPrognose).where(PVGISPrognose.anlage_id == anlage_id)
    )
    for p in res.scalars().all():
        p.ist_aktiv = p.jahresertrag_kwh == ALT_JAHR
    await db.flush()

    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    assert _pvgis_summe(ctx) == pytest.approx(ALT_JAHR, abs=1)
