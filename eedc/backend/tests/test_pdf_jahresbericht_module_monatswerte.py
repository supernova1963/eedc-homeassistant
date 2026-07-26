"""PDF-Jahresbericht: String-SOLL aus den exakten Pro-Modul-PVGIS-Werten (A3/a3).

Seit v2.3.2 speichert der PVGIS-Abruf pro Modulfeld eigene Monatswerte
(`module_monatswerte`) — mit dessen echter Ausrichtung/Neigung gerechnet. Der
API-Pfad (`api/routes/cockpit/pv_strings.py`) nutzt sie seither; der PDF-Pfad
verteilte den Anlagen-Gesamtwert weiter nach kWp und trug damit den v2.3.2-
Fehler weiter (bei Ost-West-Dächern ~20–25 % zu hohe SOLL-Werte).

Fixture spiegelt die Demo-Anlage (Süd 12 / Ost 5 / West 3 kWp) mit dem
typischen Ost-West-Kontrast: die kWp-Verteilung gibt dem Ostdach 25 % des
Gesamtwerts, PVGIS selbst nur 21 %.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context


# Anlagen-Gesamtprognose: 20 000 kWh/Jahr, gleichmäßig auf 12 Monate.
GESAMT_JAHR = 20_000.0
# Exakte Pro-Modul-Prognosen (Σ == Gesamt): Süd bekommt mehr als seinen
# kWp-Anteil, Ost/West weniger — genau der Ausrichtungseffekt aus v2.3.2.
MODUL_JAHR = {"Süddach": 13_000.0, "Ostdach": 4_200.0, "Westdach": 2_800.0}
# Was die kWp-Verteilung (12/5/3 von 20 kWp) daraus machen würde:
KWP_JAHR = {"Süddach": 12_000.0, "Ostdach": 5_000.0, "Westdach": 3_000.0}


def _monatswerte(jahressumme: float) -> list[dict]:
    return [{"monat": m, "e_m": jahressumme / 12, "h_m": 100.0, "sd_m": 10.0} for m in range(1, 13)]


async def _seed(db, *, mit_module_monatswerte: bool) -> int:
    anlage = Anlage(anlagenname="String-SOLL", leistung_kwp=20.0,
                    standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()
    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=m,
                           einspeisung_kwh=400.0, netzbezug_kwh=300.0))

    module: dict[str, Investition] = {}
    for bez, kwp, ausrichtung in (("Süddach", 12.0, "Süd"), ("Ostdach", 5.0, "Ost"), ("Westdach", 3.0, "West")):
        inv = Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=bez,
            anschaffungsdatum=date(2024, 1, 1), leistung_kwp=kwp,
            ausrichtung=ausrichtung, neigung_grad=30,
            anschaffungskosten_gesamt=1000.0 * kwp,
        )
        db.add(inv)
        module[bez] = inv
    await db.flush()

    for bez, inv in module.items():
        for m in range(1, 13):
            db.add(InvestitionMonatsdaten(
                investition_id=inv.id, jahr=2025, monat=m,
                verbrauch_daten={"pv_erzeugung_kwh": MODUL_JAHR[bez] / 12},
            ))

    db.add(PVGISPrognose(
        anlage_id=anlage.id, latitude=48.0, longitude=11.0,
        neigung_grad=30.0, ausrichtung_grad=0.0, system_losses=14.0,
        jahresertrag_kwh=GESAMT_JAHR, spezifischer_ertrag_kwh_kwp=GESAMT_JAHR / 20.0,
        gesamt_leistung_kwp=20.0,
        monatswerte=_monatswerte(GESAMT_JAHR),
        module_monatswerte=(
            {str(module[bez].id): _monatswerte(jahr) for bez, jahr in MODUL_JAHR.items()}
            if mit_module_monatswerte else None
        ),
        ist_aktiv=True,
    ))
    await db.flush()
    return anlage.id


def _soll(ctx: dict) -> dict[str, float]:
    return {s["bezeichnung"]: s["prognose_kwh"] for s in ctx["string_vergleiche"]}


async def test_string_soll_nutzt_exakte_modulprognosen(db):
    """Mit `module_monatswerte` steht je String der PVGIS-Wert seiner Ausrichtung."""
    anlage_id = await _seed(db, mit_module_monatswerte=True)
    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    soll = _soll(ctx)
    for bez, erwartet in MODUL_JAHR.items():
        assert soll[bez] == pytest.approx(erwartet, abs=1), bez
        assert soll[bez] != pytest.approx(KWP_JAHR[bez], abs=1), (
            f"{bez}: SOLL ist noch die kWp-Verteilung — v2.3.2-Fehler zurück im PDF."
        )
    # Σ bleibt die Anlagenprognose (keine Verschiebung der Gesamtsumme).
    assert sum(soll.values()) == pytest.approx(GESAMT_JAHR, abs=1)


async def test_string_soll_faellt_ohne_modulwerte_auf_kwp_zurueck(db):
    """Ältere Prognosen ohne `module_monatswerte`: Verhalten unverändert."""
    anlage_id = await _seed(db, mit_module_monatswerte=False)
    ctx = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    soll = _soll(ctx)
    for bez, erwartet in KWP_JAHR.items():
        assert soll[bez] == pytest.approx(erwartet, abs=1), bez


async def test_gesamtzeitraum_skaliert_exakte_modulprognosen_mit_jahren(db):
    """Gesamtzeitraum multipliziert wie bisher mit der Anzahl Datenjahre."""
    anlage_id = await _seed(db, mit_module_monatswerte=True)
    ctx = await build_jahresbericht_context(db, anlage_id, jahr=None)
    soll = _soll(ctx)
    # Nur 2025 hat Daten → anzahl_jahre = 1
    assert soll["Ostdach"] == pytest.approx(MODUL_JAHR["Ostdach"], abs=1)
