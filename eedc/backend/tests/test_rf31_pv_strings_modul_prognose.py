"""RF-31 (23.10.2026): benannte Probe für die Zweige der PV-String-Sichten, die der Golden Master nicht sieht.

Der Worktree-GM `skript-golden-master-analyse-sichten.py` (Familien «A1 pv-strings») läuft auf drei DB-Kopien, von
denen keine eine PVGIS-Prognose **je Modul** (`module_monatswerte`) und keine eine Anlage ohne Erzeuger trägt
(Zeilenspur am HEAD `365dd162`, Bericht `opus-berichte/RF-PAKET-A1.md`). Diese Datei hält genau diese Zweige fest:

* SOLL je Modul aus `module_monatswerte` statt kWp-Anteil — Jahressicht (`get_pv_strings`), Jahreswerte und
  Saisonal-SOLL der Gesamtlaufzeit (`_string_jahreswert`, `_string_saisonalwerte`, `_saisonal_aggregiert`);
* ein Modul-Schlüssel, der keine Zahl ist, wird übergangen (`_prognose_monatswerte`, `except (ValueError, TypeError)`);
* eine Anlage ohne Erzeuger liefert in beiden Sichten die leere Antwort.

Die Erwartungen sind von Hand gerechnet (volle Monate, Anschaffung 2024) und am HEAD vor dem Schnitt gegengeprüft.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.cockpit.pv_strings import get_pv_strings, get_pv_strings_gesamtlaufzeit
from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.models.pvgis_prognose import PVGISPrognose

SUED_E_M = 70.0
OST_E_M = 40.0


async def _seed_modulprognose(db) -> int:
    """Zwei Strings (Süd 6 kWp, Ost 4 kWp), IST in Mai+Juni 2025 und Mai 2026, Prognose mit SOLL je Modul."""
    anlage = Anlage(anlagenname="RF-31 Modulprognose", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    sued = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
                       anschaffungsdatum=date(2024, 1, 1), leistung_kwp=6.0)
    ost = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Ost",
                      anschaffungsdatum=date(2024, 1, 1), leistung_kwp=4.0)
    db.add_all([sued, ost])
    await db.flush()
    for jahr, monat, s, o in ((2025, 5, 800.0, 420.0), (2025, 6, 900.0, 480.0), (2026, 5, 780.0, 400.0)):
        db.add(InvestitionMonatsdaten(investition_id=sued.id, jahr=jahr, monat=monat,
                                      verbrauch_daten={"pv_erzeugung_kwh": s}))
        db.add(InvestitionMonatsdaten(investition_id=ost.id, jahr=jahr, monat=monat,
                                      verbrauch_daten={"pv_erzeugung_kwh": o}))
    db.add(PVGISPrognose(
        anlage_id=anlage.id, latitude=48.0, longitude=11.0, neigung_grad=30.0, ausrichtung_grad=0.0,
        gesamt_leistung_kwp=10.0, abgerufen_am=datetime(2024, 3, 1, 12, 0),
        jahresertrag_kwh=12_000.0, spezifischer_ertrag_kwh_kwp=1_200.0,
        monatswerte=[{"monat": m, "e_m": 1_000.0} for m in range(1, 13)],
        module_monatswerte={
            str(sued.id): [{"monat": m, "e_m": SUED_E_M} for m in range(1, 13)],
            str(ost.id): [{"monat": m, "e_m": OST_E_M} for m in range(1, 13)],
            "kein-modul": [{"monat": 1, "e_m": 999.0}],
        },
        ist_aktiv=True,
    ))
    await db.commit()
    return anlage.id


async def test_jahressicht_soll_je_modul_aus_der_modulprognose(db):
    """`get_pv_strings`: SOLL je String = Modul-Monatswert × Monate mit IST, nicht kWp-Anteil der Anlage."""
    aid = await _seed_modulprognose(db)
    resp = await get_pv_strings(anlage_id=aid, jahr=2025, db=db)
    soll = {s.bezeichnung: s.prognose_jahr_kwh for s in resp.strings}
    assert soll == {"Süd": pytest.approx(2 * SUED_E_M), "Ost": pytest.approx(2 * OST_E_M)}
    assert resp.prognose_gesamt_kwh == pytest.approx(2 * (SUED_E_M + OST_E_M))
    mai = {s.bezeichnung: s.monatswerte[4].prognose_kwh for s in resp.strings}
    assert mai == {"Süd": pytest.approx(SUED_E_M), "Ost": pytest.approx(OST_E_M)}


async def test_gesamtlaufzeit_jahreswerte_und_saisonal_aus_der_modulprognose(db):
    """`get_pv_strings_gesamtlaufzeit`: Jahreswerte und Saisonal-SOLL folgen der Modulprognose."""
    aid = await _seed_modulprognose(db)
    resp = await get_pv_strings_gesamtlaufzeit(anlage_id=aid, db=db)
    assert (resp.erstes_jahr, resp.letztes_jahr, resp.anzahl_jahre, resp.anzahl_monate) == (2025, 2026, 2, 3)
    sued = next(s for s in resp.strings if s.bezeichnung == "Süd")
    assert [(j.jahr, j.prognose_kwh) for j in sued.jahreswerte] == [(2025, pytest.approx(2 * SUED_E_M)),
                                                                     (2026, pytest.approx(SUED_E_M))]
    assert sued.prognose_gesamt_kwh == pytest.approx(3 * SUED_E_M)
    assert sued.saisonalwerte[4].prognose_kwh == pytest.approx(SUED_E_M)
    assert sued.saisonalwerte[4].anzahl_jahre == 2
    assert resp.prognose_gesamt_kwh == pytest.approx(3 * (SUED_E_M + OST_E_M))
    assert resp.saisonal_aggregiert[4].prognose_kwh == pytest.approx(SUED_E_M + OST_E_M)
    assert resp.saisonal_aggregiert[4].ist_summe_kwh == pytest.approx(800.0 + 420.0 + 780.0 + 400.0)


async def test_anlage_ohne_erzeuger_liefert_in_beiden_sichten_die_leere_antwort(db):
    anlage = Anlage(anlagenname="RF-31 ohne Erzeuger", leistung_kwp=5.0)
    db.add(anlage)
    await db.commit()
    jahr = await get_pv_strings(anlage_id=anlage.id, jahr=2025, db=db)
    assert (jahr.strings, jahr.hat_prognose, jahr.anlagen_leistung_kwp) == ([], False, 5.0)
    gesamt = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage.id, db=db)
    assert (gesamt.strings, gesamt.saisonal_aggregiert, gesamt.anzahl_jahre) == ([], [], 0)
