"""Daten-Checker: Leistung↔Energie-Verwechslung über alle gemappten Slots.

Triggers:
- #674 (mameier1234): kWh-Zählerstand in einem Live-W-Slot → als Momentanleistung
  gelesen (7130 kWh → 7130 W), live berechneter Hausverbrauch klemmt auf 0.
- #200: Leistungssensor in einem kWh-Slot → state-Differenz ist keine kWh.

Der Check ist einheiten-getrieben (FELD_EINHEITEN, SoT field_definitions) und
deckt BEIDE Richtungen über alle Slots (Live + Zähler, basis + Investition) ab.
Nur Leistung↔Energie; %/°C/Preis/km bleiben außen vor.

Tests sichern:
- ERROR: Energie-Sensor (kWh) im Live-W-Slot (basis einspeisung_w) — #674.
- WARNING: Leistungssensor (W) im kWh-Slot (basis einspeisung) — #200.
- ERROR: Investitions-Live leistung_w mit kWh-Sensor (mit Bezeichnung).
- WARNING: Investitions-kWh-Feld mit Leistungssensor.
- KEIN Eintrag wenn alle Einheiten passen.
- SoC (%)/Temperatur (°C)/Preis (ct/kWh) werden nicht geprüft (keine Fehlalarme).
- Stiller Skip wenn HA keine Einheiten liefert.
"""

from __future__ import annotations

from sqlalchemy.orm.attributes import flag_modified

from backend.models import Anlage, Investition
from backend.services.daten_checker import (
    CheckKategorie,
    CheckSeverity,
    DatenChecker,
)


# ── Helper ────────────────────────────────────────────────────────────────────

async def _seed_anlage(db, *, sensor_mapping: dict) -> Anlage:
    anlage = Anlage(
        anlagenname="Test", leistung_kwp=10.0, standort_land="DE",
        sensor_mapping=sensor_mapping,
    )
    db.add(anlage)
    await db.flush()
    await db.commit()
    return anlage


async def _add_inv(db, anlage_id: int, typ: str, bez: str) -> Investition:
    inv = Investition(anlage_id=anlage_id, typ=typ, bezeichnung=bez)
    db.add(inv)
    await db.flush()
    await db.commit()
    return inv


def _sensor(eid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": eid}


class _FakeHaState:
    def __init__(self, units):
        self._units = units

    async def get_sensor_units(self, entity_ids):
        return {eid: self._units[eid] for eid in entity_ids if eid in self._units}


def _patch_units(monkeypatch, units):
    import backend.services.ha_state_service as hss
    monkeypatch.setattr(hss, "get_ha_state_service", lambda: _FakeHaState(units))


async def _run_check(db, anlage):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
    )
    geladen = result.scalar_one()
    return await DatenChecker(db)._check_sensor_mapping_einheit(geladen)


# ── Tests ───────────────────────────────────────────────────────────────────


async def test_kwh_sensor_im_live_w_slot_error(db, monkeypatch):
    """#674: Energie-Sensor (kWh) im Live-Einspeise-W-Slot → ERROR."""
    anlage = await _seed_anlage(db, sensor_mapping={
        "basis": {"live": {"einspeisung_w": "sensor.einsp_zaehler"}},
    })
    _patch_units(monkeypatch, {"sensor.einsp_zaehler": "kWh"})
    ergebnisse = await _run_check(db, anlage)
    assert len(ergebnisse) == 1
    assert ergebnisse[0].kategorie == CheckKategorie.SENSOR_MAPPING_EINHEIT
    assert ergebnisse[0].schwere == CheckSeverity.ERROR
    assert "Einspeisung (Live)" in ergebnisse[0].meldung


async def test_leistungssensor_im_kwh_slot_warning(db, monkeypatch):
    """#200: Leistungssensor (W) im kWh-Zähler-Slot (basis) → WARNING."""
    anlage = await _seed_anlage(db, sensor_mapping={
        "basis": {"einspeisung": _sensor("sensor.einsp_leistung")},
    })
    _patch_units(monkeypatch, {"sensor.einsp_leistung": "W"})
    ergebnisse = await _run_check(db, anlage)
    assert len(ergebnisse) == 1
    assert ergebnisse[0].schwere == CheckSeverity.WARNING
    assert "Einspeisung" in ergebnisse[0].meldung


async def test_investitions_live_leistung_mit_kwh_error(db, monkeypatch):
    """Investitions-Live leistung_w mit kWh-Sensor → ERROR inkl. Bezeichnung."""
    anlage = await _seed_anlage(db, sensor_mapping={})
    wp = await _add_inv(db, anlage.id, "waermepumpe", "Nibe WP")
    anlage.sensor_mapping = {
        "investitionen": {str(wp.id): {"live": {"leistung_w": "sensor.wp_energie"}}},
    }
    flag_modified(anlage, "sensor_mapping")
    await db.commit()

    _patch_units(monkeypatch, {"sensor.wp_energie": "kWh"})
    ergebnisse = await _run_check(db, anlage)
    assert len(ergebnisse) == 1
    assert ergebnisse[0].schwere == CheckSeverity.ERROR
    assert "Nibe WP" in ergebnisse[0].meldung


async def test_investitions_kwh_feld_mit_leistung_warning(db, monkeypatch):
    """Investitions-kWh-Feld (pv_erzeugung_kwh) mit Leistungssensor → WARNING."""
    anlage = await _seed_anlage(db, sensor_mapping={})
    pv = await _add_inv(db, anlage.id, "pv-module", "Dach")
    anlage.sensor_mapping = {
        "investitionen": {str(pv.id): {"felder": {"pv_erzeugung_kwh": _sensor("sensor.pv_leistung")}}},
    }
    flag_modified(anlage, "sensor_mapping")
    await db.commit()

    _patch_units(monkeypatch, {"sensor.pv_leistung": "kW"})
    ergebnisse = await _run_check(db, anlage)
    assert len(ergebnisse) == 1
    assert ergebnisse[0].schwere == CheckSeverity.WARNING
    assert "Dach" in ergebnisse[0].meldung


async def test_alle_einheiten_passen_kein_eintrag(db, monkeypatch):
    """W-Slots tragen W/kW, kWh-Slots tragen kWh → kein Eintrag."""
    anlage = await _seed_anlage(db, sensor_mapping={
        "basis": {
            "live": {"einspeisung_w": "sensor.einsp_w", "netzbezug_w": "sensor.bezug_w"},
            "einspeisung": _sensor("sensor.einsp_kwh"),
            "netzbezug": _sensor("sensor.bezug_kwh"),
        },
    })
    _patch_units(monkeypatch, {
        "sensor.einsp_w": "W", "sensor.bezug_w": "kW",
        "sensor.einsp_kwh": "kWh", "sensor.bezug_kwh": "kWh",
    })
    assert await _run_check(db, anlage) == []


async def test_soc_temp_preis_nicht_geprueft(db, monkeypatch):
    """SoC (%)/Temperatur (°C)/Preis (ct/kWh) sind weder Leistung noch Energie → ignoriert."""
    anlage = await _seed_anlage(db, sensor_mapping={})
    sp = await _add_inv(db, anlage.id, "speicher", "Speicher")
    anlage.sensor_mapping = {
        "basis": {
            "live": {"aussentemperatur_c": "sensor.temp"},
            "strompreis": _sensor("sensor.preis"),
        },
        "investitionen": {str(sp.id): {"live": {"soc": "sensor.soc"}}},
    }
    flag_modified(anlage, "sensor_mapping")
    await db.commit()

    # Bewusst „falsche" Einheiten — dürfen trotzdem nicht gemeldet werden,
    # weil diese Slots nicht Leistung/Energie erwarten.
    _patch_units(monkeypatch, {
        "sensor.temp": "°C", "sensor.preis": "ct/kWh", "sensor.soc": "%",
    })
    assert await _run_check(db, anlage) == []


async def test_keine_ha_einheiten_skip(db, monkeypatch):
    """HA liefert keine Einheiten (Standalone) → stiller Skip."""
    anlage = await _seed_anlage(db, sensor_mapping={
        "basis": {"live": {"einspeisung_w": "sensor.irgendwas"}},
    })
    _patch_units(monkeypatch, {})
    assert await _run_check(db, anlage) == []
