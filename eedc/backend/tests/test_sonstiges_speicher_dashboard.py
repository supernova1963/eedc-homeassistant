"""``GET /investitionen/dashboard/sonstiges`` für ein Gerät der Kategorie «Speicher» (Beipack N-799 S1, Go Gernot 16.11.2026).

Bis hier las die Route für ``kategorie == 'speicher'`` die Schlüssel ``ladung_kwh``/``entladung_kwh`` — Formular,
Feld-Registry (``core/field_definitions/registry.py``, Kategorie ``speicher``, «diese Feldnamen sind bindend») und
Monats-Fakten führen die Ladung aber unter ``verbrauch_sonstig_kwh`` und die Entladung unter ``erzeugung_kwh``. Folge
(gemessen über die Route an einer Kopie): Ladung 0, Entladung 0, Wirkungsgrad leer, Ersparnis ohne Speicheranteil statt
310,0 / 240,0 kWh. Jetzt ein Ort für die Feldwahl: ``field_definitions.get_sonstiges_speicher_kwh`` (Registry zuerst,
Altschlüssel als Rückfall; beide da ⇒ Registry-Feld, auch eine gepflegte 0).

Schwesterdateien: test_n785_abgabe_dashboard.py (Kategorie «Abgabe», dieselbe Route), test_n641_n645_hub_monatsreihe.py,
test_sonstiges_dashboard_laufzeit_308.py.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.dashboard_sonstiges import get_sonstiges_dashboard
from backend.core.field_definitions import get_sonstiges_speicher_kwh
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten

REGISTRY = {1: {"verbrauch_sonstig_kwh": 100.0, "erzeugung_kwh": 80.0},
            2: {"verbrauch_sonstig_kwh": 120.0, "erzeugung_kwh": 90.0},
            3: {"verbrauch_sonstig_kwh": 90.0, "erzeugung_kwh": 70.0}}


async def _anlage_mit_speicher(db, zeilen: dict[int, dict]) -> Anlage:
    anlage = Anlage(anlagenname="Sonstiges-Speicher", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(anlage_id=anlage.id, typ="sonstiges", bezeichnung="Wärmespeicher",
                      anschaffungsdatum=date(2025, 1, 1), parameter={"kategorie": "speicher"})
    db.add(inv)
    await db.flush()
    for m, d in zeilen.items():
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=m, einspeisung_kwh=300.0, netzbezug_kwh=200.0))
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=2025, monat=m, verbrauch_daten=d))
    await db.flush()
    return anlage


async def _dashboard(db, anlage):
    [d] = await get_sonstiges_dashboard(anlage_id=anlage.id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0, db=db)
    return d


async def _zusammenfassung(db, anlage) -> dict:
    return (await _dashboard(db, anlage)).zusammenfassung


async def test_registry_felder_tragen_ladung_und_entladung(db):
    z = await _zusammenfassung(db, await _anlage_mit_speicher(db, REGISTRY))
    assert (z["gesamt_ladung_kwh"], z["gesamt_entladung_kwh"]) == (310.0, 240.0)
    assert z["effizienz_prozent"] == pytest.approx(77.4, abs=0.05)
    assert z["ersparnis_euro"] > 0          # Spread aus dem Layer (berechne_speicher_ersparnis), vorher 0


async def test_monatsreihe_fuer_verlauf_und_vergleich(db):
    """Der Hub liest Verlauf und Vergleich aus ``speicher_monatsreihe`` (eine Feldwahl im Backend, der Client wählt
    nichts) — Registry-, Alt- und gemischte Monate."""
    zeilen = {1: REGISTRY[1], 2: {"ladung_kwh": 120.0, "entladung_kwh": 90.0},
              3: {**REGISTRY[3], "ladung_kwh": 999.0}}
    d = await _dashboard(db, await _anlage_mit_speicher(db, zeilen))
    assert [(m.monat, m.ladung_kwh, m.entladung_kwh) for m in d.speicher_monatsreihe] == [
        (1, 100.0, 80.0), (2, 120.0, 90.0), (3, 90.0, 70.0)]
    assert d.monatsreihe == [] and d.abgabe_monatsreihe == []


async def test_altschluessel_wie_bisher(db):
    alt = {m: {"ladung_kwh": d["verbrauch_sonstig_kwh"], "entladung_kwh": d["erzeugung_kwh"]} for m, d in REGISTRY.items()}
    z = await _zusammenfassung(db, await _anlage_mit_speicher(db, alt))
    assert (z["gesamt_ladung_kwh"], z["gesamt_entladung_kwh"]) == (310.0, 240.0)
    assert z["effizienz_prozent"] == pytest.approx(77.4, abs=0.05) and z["ersparnis_euro"] > 0


async def test_beide_schluessel_registry_gewinnt(db):
    beide = {m: {**d, "ladung_kwh": 999.0, "entladung_kwh": 888.0} for m, d in REGISTRY.items()}
    z = await _zusammenfassung(db, await _anlage_mit_speicher(db, beide))
    assert (z["gesamt_ladung_kwh"], z["gesamt_entladung_kwh"]) == (310.0, 240.0)


def test_helfer_feldwahl():
    assert get_sonstiges_speicher_kwh({}) == (0.0, 0.0)
    assert get_sonstiges_speicher_kwh(None) == (0.0, 0.0)
    assert get_sonstiges_speicher_kwh({"verbrauch_kwh": 5.0, "ladung_kwh": 9.0}) == (5.0, 0.0)   # Legacy-Zwilling
    # eine gepflegte 0 im Registry-Feld gewinnt (sie ist ein Wert, kein «fehlt»)
    assert get_sonstiges_speicher_kwh({"erzeugung_kwh": 0.0, "entladung_kwh": 7.0}) == (0.0, 0.0)
    assert get_sonstiges_speicher_kwh({"ladung_kwh": 4.0, "entladung_kwh": 3.0}) == (4.0, 3.0)
