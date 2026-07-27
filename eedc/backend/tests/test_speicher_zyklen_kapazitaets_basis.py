"""Vollzyklen rechnen überall gegen dieselbe Kapazitäts-Basis: BRUTTO.

R22-4 (PN 89768, Rainer): „eedc nimmt 100 % SOC an" — tatsächlich rechnet eedc
die Zyklen aus GEMESSENEN Werten, teilt sie aber durch die BRUTTO-Kapazität.
`nutzbare_kapazitaet_kwh` (DoD-Reserve, bei Rainers 10/90-Fahrweise also 8 von
10 kWh) wirkt bewusst NUR auf das η-SoC-Delta, nicht auf die Zyklen.

Ein Kommentar in `ha_export.py` behauptete das Gegenteil („optionaler
User-Override") — wer ihm folgte und die `or`-Kette drehte, hätte den HA-Sensor
gegen Dashboard und Monatsbericht laufen lassen, ohne dass ein Test angeschlagen
hätte. Genau diese Basis pinnen die Tests hier.

NICHT gepinnt, sondern nur festgehalten: die beiden Pfade zählen unterschiedliche
GRÖSSEN — Dashboard/Monatsbericht die Ladung, der HA-Sensor die Entladung. Bei
95 % Wirkungsgrad sind das ~5 % Unterschied auf derselben Anlage. Das ist ein
offener Punkt (R22-4 Nebenbefund), keine beschlossene Konvention; der letzte Test
hält den Ist-Zustand fest, damit eine Angleichung eine sichtbare Entscheidung
wird und kein stiller Nebeneffekt (docs/BERECHNUNGEN.md §Speicher).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.api.routes.investitionen.dashboards import get_speicher_dashboard
from backend.api.routes.ha_export import calculate_anlage_sensors

# 10 kWh brutto, 8 kWh nutzbar (Rainers 10/90). Ladung 1100, Entladung 1000 kWh.
_BRUTTO_KWH = 10.0
_NUTZBAR_KWH = 8.0
_LADUNG_KWH = 1100.0
_ENTLADUNG_KWH = 1000.0
# Erwartungen gegen Brutto …
_ZYKLEN_LADUNG_BRUTTO = 110.0
_ZYKLEN_ENTLADUNG_BRUTTO = 100.0
# … und die Werte, die bei einer Netto-Basis herauskämen (dürfen NICHT auftreten).
_ZYKLEN_LADUNG_NETTO = 137.5
_ZYKLEN_ENTLADUNG_NETTO = 125.0


async def _lade(db, anlage_id: int) -> Anlage:
    """Mit Relationships — `calculate_anlage_sensors` liest Investitionen + IMD."""
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage_id)
    )).scalar_one()


async def _seed(db) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=4,
        netzbezug_kwh=100.0, einspeisung_kwh=200.0,
    ))
    inv = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Huawei 10 kWh",
        anschaffungsdatum=date(2023, 7, 1),
        parameter={
            "kapazitaet_kwh": _BRUTTO_KWH,
            "nutzbare_kapazitaet_kwh": _NUTZBAR_KWH,
            "wirkungsgrad_prozent": 95,
        },
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"ladung_kwh": _LADUNG_KWH, "entladung_kwh": _ENTLADUNG_KWH},
    ))
    await db.commit()
    return await _lade(db, anlage.id)


async def test_speicher_dashboard_teilt_durch_die_bruttokapazitaet(db):
    anlage = await _seed(db)

    result = await get_speicher_dashboard(
        anlage_id=anlage.id, strompreis_cent=None,
        einspeiseverguetung_cent=None, db=db,
    )

    zus = result[0].zusammenfassung
    assert zus["kapazitaet_kwh"] == _BRUTTO_KWH
    assert zus["vollzyklen"] == _ZYKLEN_LADUNG_BRUTTO, (
        f"Zyklen gegen die nutzbare Kapazität gerechnet? {zus['vollzyklen']} "
        f"(brutto {_ZYKLEN_LADUNG_BRUTTO}, netto {_ZYKLEN_LADUNG_NETTO})"
    )


async def test_ha_sensor_teilt_durch_die_bruttokapazitaet(db):
    anlage = await _seed(db)

    sensoren = await calculate_anlage_sensors(db, anlage)

    zyklen = [s for s in sensoren if s.definition.key == "speicher_zyklen"]
    assert len(zyklen) == 1, "Zyklen-Sensor fehlt im Export"
    assert zyklen[0].value == _ZYKLEN_ENTLADUNG_BRUTTO, (
        f"HA-Sensor auf Netto-Basis? {zyklen[0].value} "
        f"(brutto {_ZYKLEN_ENTLADUNG_BRUTTO}, netto {_ZYKLEN_ENTLADUNG_NETTO})"
    )


async def test_ohne_bruttowert_faellt_der_export_auf_die_nutzbare_kapazitaet_zurueck(db):
    """Fallback, kein Override: nur wenn Brutto fehlt, zählt der Netto-Wert.

    Sonst hätte eine Anlage, die ausschließlich die nutzbare Kapazität gepflegt
    hat, gar keinen Zyklen-Sensor.
    """
    anlage = await _seed(db)
    speicher = next(i for i in anlage.investitionen if i.typ == "speicher")
    speicher.parameter = {"nutzbare_kapazitaet_kwh": _NUTZBAR_KWH, "wirkungsgrad_prozent": 95}
    await db.commit()

    sensoren = await calculate_anlage_sensors(db, await _lade(db, anlage.id))

    zyklen = [s for s in sensoren if s.definition.key == "speicher_zyklen"]
    assert len(zyklen) == 1
    assert zyklen[0].value == _ZYKLEN_ENTLADUNG_NETTO


async def test_zaehlgroesse_dashboard_vs_export_ist_bekannt_verschieden(db):
    """Ist-Zustand, keine Billigung: Dashboard zählt Ladung, der Sensor Entladung.

    Fällt dieser Test, wurde eine der beiden Seiten angefasst — dann gehört die
    Entscheidung dokumentiert (welche Größe ist ein „Vollzyklus"?) statt still
    übernommen. Ein Angleichen ändert sichtbare Zahlen bei jedem Nutzer.
    """
    anlage = await _seed(db)

    dash = (await get_speicher_dashboard(
        anlage_id=anlage.id, strompreis_cent=None,
        einspeiseverguetung_cent=None, db=db,
    ))[0].zusammenfassung["vollzyklen"]
    sensor = [
        s for s in await calculate_anlage_sensors(db, await _lade(db, anlage.id))
        if s.definition.key == "speicher_zyklen"
    ][0].value

    assert dash == _ZYKLEN_LADUNG_BRUTTO and sensor == _ZYKLEN_ENTLADUNG_BRUTTO
    assert dash != sensor, "Angleichung passiert? Dann bitte bewusst + dokumentiert."
