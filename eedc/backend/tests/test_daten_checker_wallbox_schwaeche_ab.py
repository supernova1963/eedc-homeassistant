"""Daten-Checker: Wallbox-Schwächen A+B (KONZEPT-WALLBOX-EAUTO.md »Bekannte
Schwächen«, Phase-2a-Fehlalarme).

A — `_check_emob_pool_pflege`: Ein E-Auto, das nur Fahrverbrauch (`verbrauch_kwh`)
    trägt, darf nicht als „Heimladung tragend" gewertet werden. `verbrauch_kwh`
    ist beim E-Auto der Fahrverbrauch, nicht die Heimladung — sonst feuert der
    Pflege-Check einen falschen Konflikt, obwohl die Wallbox die einzige
    Heimladungs-Quelle ist. Nur explizites `ladung_kwh` zählt als Heimladung.

B — `_check_energieprofil_abdeckung`: Deckt eine Wallbox mit gemapptem kWh-Zähler
    die Ladeenergie ab, ist ein eigener E-Auto-kWh-Zähler redundant → keine
    Abdeckungs-Warnung für das E-Auto (strukturelle Regel, Phase 2a).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, InvestitionMonatsdaten  # noqa: F401
from backend.services.daten_checker import CheckSeverity, DatenChecker


def _letzte_n_monate(n: int) -> list[tuple[int, int]]:
    heute = date.today()
    out: list[tuple[int, int]] = []
    for offset in range(n):
        jahr = heute.year + ((heute.month - 1 - offset) // 12)
        monat = ((heute.month - 1 - offset) % 12) + 1
        out.append((jahr, monat))
    return out


async def _reload(db, anlage_id: int) -> Anlage:
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage_id)
    )).scalar_one()


# ── Schwäche A ────────────────────────────────────────────────────────────────

async def test_eauto_nur_fahrverbrauch_kein_pflege_konflikt(db):
    """E-Auto trägt `verbrauch_kwh` (Fahrverbrauch), Heimladung nur an der
    Wallbox → kein Pflege-Konflikt (Schwäche A)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    db.add(anlage)
    await db.flush()
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="WB",
                     anschaffungsdatum=date(2024, 1, 1), parameter={})
    ea = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="EA",
                     anschaffungsdatum=date(2024, 1, 1), parameter={})
    db.add_all([wb, ea])
    await db.flush()
    for j, m in _letzte_n_monate(6):
        db.add(InvestitionMonatsdaten(
            investition_id=wb.id, jahr=j, monat=m,
            verbrauch_daten={"ladung_kwh": 200.0, "ladung_pv_kwh": 150.0},
        ))
        # E-Auto: nur Fahrverbrauch, KEINE Heimladung (ladung_kwh)
        db.add(InvestitionMonatsdaten(
            investition_id=ea.id, jahr=j, monat=m,
            verbrauch_daten={"verbrauch_kwh": 220.0},
        ))
    await db.commit()

    geladen = await _reload(db, anlage.id)
    ergebnisse = DatenChecker(db)._check_emob_pool_pflege(geladen)
    assert ergebnisse == [], (
        f"Fahrverbrauch am E-Auto ist keine Heimladung — kein Konflikt erwartet, fand:\n"
        + "\n".join(f"  {e.schwere}: {e.meldung}" for e in ergebnisse)
    )


async def test_eauto_echte_heimladung_weiterhin_konflikt(db):
    """Gegenprobe: trägt das E-Auto explizit `ladung_kwh`, bleibt der
    bestehende Pflege-Konflikt erhalten (PV-Inkonsistenz → WARNING)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    db.add(anlage)
    await db.flush()
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="WB",
                     anschaffungsdatum=date(2024, 1, 1), parameter={})
    ea = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="EA",
                     anschaffungsdatum=date(2024, 1, 1), parameter={})
    db.add_all([wb, ea])
    await db.flush()
    for j, m in _letzte_n_monate(6):
        db.add(InvestitionMonatsdaten(
            investition_id=wb.id, jahr=j, monat=m,
            verbrauch_daten={"ladung_kwh": 200.0, "ladung_pv_kwh": 160.0},
        ))
        db.add(InvestitionMonatsdaten(
            investition_id=ea.id, jahr=j, monat=m,
            verbrauch_daten={"ladung_kwh": 200.0, "ladung_pv_kwh": 40.0},
        ))
    await db.commit()

    geladen = await _reload(db, anlage.id)
    ergebnisse = DatenChecker(db)._check_emob_pool_pflege(geladen)
    assert len(ergebnisse) == 1
    assert ergebnisse[0].schwere == CheckSeverity.WARNING.value


# ── Schwäche B ────────────────────────────────────────────────────────────────

async def test_eauto_ohne_zaehler_aber_wallbox_deckt_ab(db):
    """E-Auto ohne kWh-Zähler-Mapping, aber Wallbox mit kWh-Zähler → keine
    Abdeckungs-Warnung für das E-Auto (Schwäche B)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="WB",
                     anschaffungsdatum=date(2024, 1, 1), parameter={})
    ea = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="EA",
                     anschaffungsdatum=date(2024, 1, 1), parameter={})
    db.add_all([wb, ea])
    await db.flush()
    anlage.sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.eins"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netz"},
        },
        "investitionen": {
            str(wb.id): {"felder": {
                "ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.wb_kwh"},
            }},
            # E-Auto: KEIN kWh-Zähler gemappt
        },
    }
    await db.commit()

    geladen = await _reload(db, anlage.id)
    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(geladen)
    warnings = [r for r in ergebnisse if "ohne vollständige kWh-Zähler-Abdeckung" in r.meldung]
    assert not warnings, (
        f"Wallbox-Zähler deckt die E-Auto-Ladung — keine Warnung erwartet, fand:\n"
        + "\n".join(f"  {w.meldung}: {w.details}" for w in warnings)
    )


async def test_eauto_ohne_zaehler_und_ohne_wallbox_warnt(db):
    """Gegenprobe: E-Auto ohne kWh-Zähler UND keine deckende Wallbox →
    Abdeckungs-Warnung bleibt (unverändertes Verhalten)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    ea = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="EA",
                     anschaffungsdatum=date(2024, 1, 1), parameter={})
    db.add(ea)
    await db.flush()
    anlage.sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.eins"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netz"},
        },
        "investitionen": {},
    }
    await db.commit()

    geladen = await _reload(db, anlage.id)
    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(geladen)
    warnings = [r for r in ergebnisse if "ohne vollständige kWh-Zähler-Abdeckung" in r.meldung]
    assert warnings, "Ohne Wallbox-Deckung muss die E-Auto-Abdeckung gewarnt werden"
