"""PV-String-Sichten lesen IST über den Read-time-SoT `resolve_pv_je_modul`.

A4/b1 (Rainer/rapahl 2026-07-25): `/cockpit/pv-strings*` las die Pro-Modul-Werte
roh aus den IMD und kannte die Aggregat-Präzedenz nicht — wer nur EINEN
Gesamtsensor hat, sah 0 bzw. eine leere Antwort. Jetzt liefern beide Endpoints
dieselbe Zerlegung wie `/monatsdaten/aggregiert`:

  Σ Pro-Modul (pv_strings) == PV-Summe (/aggregiert)   ← Symmetrie-Pflicht
  [[feedback_aggregator_symmetrie]] · [[project_kwp_verteilung_aggregator]]

Dazu die Ranking-Sperre: verteilte Werte geben per Konstruktion für jedes Modul
denselben spezifischen Ertrag — dann darf keine Platzierung behauptet werden.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.cockpit.pv_strings import (
    get_pv_strings,
    get_pv_strings_gesamtlaufzeit,
)
from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.core.berechnungen import (
    PV_QUELLE_GEMESSEN,
    PV_QUELLE_VERTEILT,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose


async def _anlage_mit_zwei_strings(db, *, aggregat=None, pro_modul=None, mit_prognose=True) -> int:
    """Fixture-Muster aus `test_aggregiert_kwp_verteilung.py`: 2 Strings 6/4 kWp,
    Mai 2026. `aggregat` = Anlagen-Gesamtwert, `pro_modul` = gemessene Werte."""
    anlage = Anlage(anlagenname="Zwei-Strings", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0,
                       pv_erzeugung_kwh=aggregat))
    sued = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
                       anschaffungsdatum=date(2024, 1, 1), leistung_kwp=6.0)
    ost = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Ost",
                      anschaffungsdatum=date(2024, 1, 1), leistung_kwp=4.0)
    db.add_all([sued, ost])
    await db.flush()
    for inv, name in ((sued, "Süd"), (ost, "Ost")):
        wert = (pro_modul or {}).get(name)
        if wert is not None:
            db.add(InvestitionMonatsdaten(
                investition_id=inv.id, jahr=2026, monat=5,
                verbrauch_daten={"pv_erzeugung_kwh": wert},
            ))
    if mit_prognose:
        db.add(PVGISPrognose(
            anlage_id=anlage.id, abgerufen_am=datetime(2026, 1, 1),
            latitude=48.0, longitude=11.0, neigung_grad=30.0, ausrichtung_grad=0.0,
            jahresertrag_kwh=10000.0, spezifischer_ertrag_kwh_kwp=1000.0,
            gesamt_leistung_kwp=10.0,
            monatswerte=[{"monat": m, "e_m": 1000.0} for m in range(1, 13)],
        ))
    await db.commit()
    return anlage.id


def _ist_je_string(resp) -> dict[str, float]:
    return {s.bezeichnung: s.ist_jahr_kwh for s in resp.strings}


async def _pv_summe_aggregiert(db, anlage_id: int) -> float:
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=2026, db=db)
    return sum(r.pv_erzeugung_kwh or 0 for r in rows)


# ── Symmetrie gegen /monatsdaten/aggregiert ────────────────────────────────

async def test_nur_aggregat_summe_gleich_aggregiert(db):
    """Nur ein Gesamtwert (1000 kWh), keine Pro-Modul-Sensoren: der Nutzer sah
    hier bisher 0 bzw. eine leere Antwort. Jetzt 600/400 — Σ == /aggregiert."""
    anlage_id = await _anlage_mit_zwei_strings(db, aggregat=1000.0)

    jahr = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    assert _ist_je_string(jahr) == {"Süd": 600.0, "Ost": 400.0}
    assert sum(_ist_je_string(jahr).values()) == pytest.approx(
        await _pv_summe_aggregiert(db, anlage_id))

    gesamt = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    assert {s.bezeichnung: s.ist_gesamt_kwh for s in gesamt.strings} == {"Süd": 600.0, "Ost": 400.0}
    assert gesamt.ist_gesamt_kwh == pytest.approx(1000.0)
    assert gesamt.anzahl_monate == 1


async def test_gemischt_ein_modul_gemessen_summe_gleich_aggregiert(db):
    """Ein Modul gemessen, eines nicht, Aggregat vorhanden → Aggregat verteilt
    (Σ == Aggregat), nicht nur der eine Messwert."""
    anlage_id = await _anlage_mit_zwei_strings(
        db, aggregat=1000.0, pro_modul={"Süd": 700.0})

    jahr = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    assert _ist_je_string(jahr) == {"Süd": 600.0, "Ost": 400.0}
    assert sum(_ist_je_string(jahr).values()) == pytest.approx(
        await _pv_summe_aggregiert(db, anlage_id))
    assert all(s.ist_quelle == PV_QUELLE_VERTEILT for s in jahr.strings)

    gesamt = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    assert gesamt.ist_gesamt_kwh == pytest.approx(1000.0)


async def test_gemessen_hat_vorrang_vor_aggregat(db):
    """Alle Strings gemessen → 700/300 (nicht 600/400), Aggregat ignoriert."""
    anlage_id = await _anlage_mit_zwei_strings(
        db, aggregat=9999.0, pro_modul={"Süd": 700.0, "Ost": 300.0})

    jahr = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    assert _ist_je_string(jahr) == {"Süd": 700.0, "Ost": 300.0}
    assert all(s.ist_quelle == PV_QUELLE_GEMESSEN for s in jahr.strings)
    assert sum(_ist_je_string(jahr).values()) == pytest.approx(
        await _pv_summe_aggregiert(db, anlage_id))


async def test_teilluecke_ohne_aggregat_behaelt_messwert(db):
    """Ein Modul gemessen, kein Aggregat: die ANLAGEN-Summe bleibt leer (eine
    Teilsumme wäre als Gesamt-PV irreführend) — der gemessene MODULWERT bleibt
    aber stehen. Kein Datenverlust durch den SoT-Umbau."""
    anlage_id = await _anlage_mit_zwei_strings(db, pro_modul={"Süd": 700.0})

    jahr = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    assert _ist_je_string(jahr) == {"Süd": 700.0, "Ost": 0.0}
    assert await _pv_summe_aggregiert(db, anlage_id) == 0


# ── Ranking-Sperre bei verteilten Werten ───────────────────────────────────

async def test_verteilte_werte_kein_ranking(db):
    """Verteilt = jedes Modul hat rechnerisch denselben spezifischen Ertrag.
    Dann keine Platzierung, sondern der Erklärsatz."""
    anlage_id = await _anlage_mit_zwei_strings(db, aggregat=1000.0)

    for resp in (await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db),
                 await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)):
        assert resp.bester_string is None
        assert resp.schlechtester_string is None
        assert resp.vergleich_hinweis is not None
        assert "nicht möglich" in resp.vergleich_hinweis
        assert resp.ist_quelle == PV_QUELLE_VERTEILT

    # Gegenprobe: der spezifische Ertrag IST bei verteilten Werten identisch —
    # genau deshalb sperrt die Sicht den Vergleich.
    jahr = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    spez = {s.spezifischer_ertrag_kwh_kwp for s in jahr.strings}
    assert len(spez) == 1


async def test_gemessene_werte_erlauben_ranking(db):
    """Gemessen → Platzierung wie bisher, kein Hinweis."""
    anlage_id = await _anlage_mit_zwei_strings(
        db, pro_modul={"Süd": 700.0, "Ost": 100.0})

    jahr = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    assert jahr.bester_string == "Süd"
    assert jahr.schlechtester_string == "Ost"
    assert jahr.vergleich_hinweis is None

    gesamt = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    assert gesamt.bester_string == "Süd"
    assert gesamt.vergleich_hinweis is None


async def test_anschaffungsdatum_grenze_bleibt(db):
    """#236: ein Modul, das im Monat noch nicht existiert, bekommt auch aus dem
    Aggregat nichts — das Aggregat geht vollständig an das aktive Modul."""
    anlage = Anlage(anlagenname="Späterer String", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5, pv_erzeugung_kwh=1000.0))
    db.add_all([
        Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Alt",
                    anschaffungsdatum=date(2024, 1, 1), leistung_kwp=6.0),
        Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Neu",
                    anschaffungsdatum=date(2026, 8, 1), leistung_kwp=4.0),
    ])
    await db.commit()

    jahr = await get_pv_strings(anlage_id=anlage.id, jahr=2026, db=db)
    assert _ist_je_string(jahr) == {"Alt": 1000.0, "Neu": 0.0}
