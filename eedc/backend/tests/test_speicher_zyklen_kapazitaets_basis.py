"""Vollzyklen: EINE Definition für alle Sichten — Entladung ÷ Brutto-Kapazität.

Erhebung zur Rainer-PN 89768 (2026-07-28) förderte drei parallele Definitionen
unter demselben Namen „Vollzyklen" zutage:

* Komponenten-Hub, Cockpit-Monat/Jahr, PDF-Jahresbericht → ``Ladung ÷ Kapazität``
* HA-Sensor ``speicher_zyklen``                          → ``Entladung ÷ Kapazität``
* Cockpit-**Tag** (dieselbe KPI-Kachel!)                 → ``ΣΔSoC ÷ 200``

Auf derselben Anlage standen dadurch zwei Zahlen unter einem Namen, die genau
um den Speicher-Wirkungsgrad auseinanderlagen (gemessen an der Demo-Anlage:
10,97 gegen 8,57 bei η 78 %) — und die Tages-Kachel summierte sich systematisch
nicht auf den Monatswert, weil ΔSoC ein Bestandsmaß ist und kein Durchsatz.

Entscheidung Gernot 2026-07-28: Kanon ist **Entladung ÷ Brutto-Kapazität**
(`core/berechnungen/speicher.vollzyklen`, docs/BERECHNUNGEN.md §3.3). Die
ΔSoC-Größe bleibt als eigene Kennzahl „SoC-Hübe" erhalten — sie ist die
einzige, die eine 10/90-Fahrweise abbildet.

Diese Tests sichern beides: den Nenner (brutto, nicht `nutzbare_kapazitaet_kwh`)
und die Symmetrie der Pfade. Fällt einer, ist eine Sicht ausgeschert.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.core.berechnungen import vollzyklen
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.api.routes.investitionen.dashboards import get_speicher_dashboard
from backend.api.routes.ha_export import calculate_anlage_sensors
from backend.api.routes.aktueller_monat import get_aktueller_monat

# 10 kWh brutto, 8 kWh nutzbar (Rainers 10/90). Ladung 1100, Entladung 1000 kWh
# ⇒ Kanon 100,0 Zyklen. Die verworfenen Lesarten lägen bei 110,0 (Ladung) bzw.
# 125,0 (Entladung ÷ nutzbar) — weit genug auseinander, um jede Verwechslung
# auffallen zu lassen.
_BRUTTO_KWH = 10.0
_NUTZBAR_KWH = 8.0
_LADUNG_KWH = 1100.0
_ENTLADUNG_KWH = 1000.0
_KANON = 100.0
_LADUNGS_LESART = 110.0
_NETTO_LESART = 125.0


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


def test_helper_rechnet_gegen_die_entladung():
    assert vollzyklen(_ENTLADUNG_KWH, _BRUTTO_KWH) == _KANON
    # Ohne Kapazität oder ohne Entladung: None statt 0 — „nicht gepflegt" darf
    # nicht wie „nie zyklisiert" aussehen.
    assert vollzyklen(_ENTLADUNG_KWH, 0) is None
    assert vollzyklen(None, _BRUTTO_KWH) is None
    assert vollzyklen(0, _BRUTTO_KWH) is None


async def test_speicher_dashboard_folgt_dem_kanon(db):
    anlage = await _seed(db)

    result = await get_speicher_dashboard(
        anlage_id=anlage.id, strompreis_cent=None,
        einspeiseverguetung_cent=None, db=db,
    )

    zus = result[0].zusammenfassung
    assert zus["kapazitaet_kwh"] == _BRUTTO_KWH
    assert zus["vollzyklen"] == _KANON, (
        f"{zus['vollzyklen']} — Ladungs-Lesart wäre {_LADUNGS_LESART}, "
        f"Netto-Nenner {_NETTO_LESART}"
    )


async def test_monatsbericht_folgt_dem_kanon(db):
    anlage = await _seed(db)

    result = await get_aktueller_monat(anlage_id=anlage.id, jahr=2026, monat=4, db=db)

    assert result.speicher_vollzyklen == _KANON, (
        f"{result.speicher_vollzyklen} — Ladungs-Lesart wäre {_LADUNGS_LESART}"
    )


async def test_ha_sensor_folgt_dem_kanon(db):
    anlage = await _seed(db)

    sensoren = await calculate_anlage_sensors(db, anlage)

    zyklen = [s for s in sensoren if s.definition.key == "speicher_zyklen"]
    assert len(zyklen) == 1, "Zyklen-Sensor fehlt im Export"
    assert zyklen[0].value == _KANON


async def test_alle_pfade_liefern_dieselbe_zahl(db):
    """Der eigentliche Punkt: eine Anlage, eine Zahl — egal welche Sicht.

    Vor dem 2026-07-28-Kanon lieferten Dashboard und HA-Sensor hier 110 gegen
    100, ohne dass ein Test angeschlagen hätte.
    """
    anlage = await _seed(db)

    dash = (await get_speicher_dashboard(
        anlage_id=anlage.id, strompreis_cent=None,
        einspeiseverguetung_cent=None, db=db,
    ))[0].zusammenfassung["vollzyklen"]
    monat = (await get_aktueller_monat(
        anlage_id=anlage.id, jahr=2026, monat=4, db=db,
    )).speicher_vollzyklen
    sensor = [
        s for s in await calculate_anlage_sensors(db, await _lade(db, anlage.id))
        if s.definition.key == "speicher_zyklen"
    ][0].value

    assert dash == monat == sensor == _KANON, f"{dash} / {monat} / {sensor}"


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
    assert zyklen[0].value == _NETTO_LESART
