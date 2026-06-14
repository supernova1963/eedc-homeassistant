"""Charakterisierungs-Tests: aktueller_monat.get_aktueller_monat —
Datenquellen-Priorisierung (saved / connector / mqtt / ha_stats).

Spur 0 des Backend-Refactoring-Plans: Die Priorisierungs-Logik in
get_aktueller_monat (hart kodiert, Zeilen ~698-734) ist die subtilste Stelle
der Funktion und bislang nur einseitig getestet — test_aktueller_monat_
connector_override_325.py deckt den Connector-Override-Schutz für vergangene
Monate ab. Diese Tests fixieren die übrigen Achsen, bevor die Funktion zerlegt
wird (geplanter DatenquellenPrioritizer).

Aktuelles Verhalten (Stand v3.45.0):
  Vergangener (abgeschlossener) Monat — gespeichert ist authoritativ:
    - connector: nur setdefault (kein Override, #325)
    - ha_stats:  nur setdefault (kein Override, #118)
    - mqtt:      wird gar nicht erst gesammelt
  Laufender Monat — frischeste Quelle gewinnt, Reihenfolge der `update`s:
    saved < connector < mqtt < ha_stats  → ha_stats überschreibt zuletzt.

Geschwister-Datei (Symbol get_aktueller_monat):
  - test_aktueller_monat_connector_override_325.py (Connector-Override-Schutz)
  - test_aktueller_monat_emob_komponenten.py / test_emob_pool_komponenten.py
  - test_emob_readsite_symmetrie.py / test_sonstige_readsite_symmetrie.py
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage, Investition, Monatsdaten, Strompreis


async def _seed(db: AsyncSession, *, jahr: int, monat: int,
                einspeisung: float, netzbezug: float = 8.0) -> int:
    anlage = Anlage(anlagenname="PrioTest", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=jahr, monat=monat,
        netzbezug_kwh=netzbezug, einspeisung_kwh=einspeisung,
    ))
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                       leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                       anschaffungskosten_gesamt=10000.0))
    await db.commit()
    return anlage.id


def _info(am, quelle, konfidenz):
    return am.DatenquelleInfo(quelle=quelle, konfidenz=konfidenz)


# ---------------------------------------------------------------------------
# Vergangener Monat: gespeichert authoritativ
# ---------------------------------------------------------------------------

async def test_vergangener_monat_ha_stats_ueberschreibt_gespeichert_nicht(db, monkeypatch):
    """#118: HA-Stats darf gespeicherte Werte für abgeschlossene Monate nicht
    rückwirkend überschreiben (analog Connector #325)."""
    import backend.api.routes.aktueller_monat as am
    anlage_id = await _seed(db, jahr=2024, monat=4, einspeisung=1411.0)

    async def _fake_connector(anlage, j, m):
        return {}

    async def _fake_ha_stats(anlage, j, m):
        return {"einspeisung_kwh": (0.0, _info(am, "ha_statistics", 92))}

    monkeypatch.setattr(am, "_collect_connector_data", _fake_connector)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)

    res = await am.get_aktueller_monat(anlage_id=anlage_id, jahr=2024, monat=4, db=db)
    assert res.einspeisung_kwh == 1411.0


async def test_vergangener_monat_mqtt_wird_ignoriert(db, monkeypatch):
    """MQTT-Inbound wird für abgeschlossene Monate gar nicht gesammelt — ein
    abweichender MQTT-Wert darf nie im Ergebnis landen."""
    import backend.api.routes.aktueller_monat as am
    anlage_id = await _seed(db, jahr=2024, monat=4, einspeisung=1411.0)

    async def _fake_connector(anlage, j, m):
        return {}

    async def _fake_ha_stats(anlage, j, m):
        return {}

    async def _poison_mqtt(anlage, investitionen):
        return {"einspeisung_kwh": (9999.0, _info(am, "mqtt", 91))}

    monkeypatch.setattr(am, "_collect_connector_data", _fake_connector)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _poison_mqtt)

    res = await am.get_aktueller_monat(anlage_id=anlage_id, jahr=2024, monat=4, db=db)
    assert res.einspeisung_kwh == 1411.0  # MQTT (9999) nicht angewendet


# ---------------------------------------------------------------------------
# Laufender Monat: frischeste Quelle gewinnt
# ---------------------------------------------------------------------------

async def test_laufender_monat_ha_stats_ueberschreibt_gespeichert(db, monkeypatch):
    """Laufender Monat: HA-Stats (frischeste Quelle) überschreibt den
    gespeicherten Wert (Live-Vorschau)."""
    import backend.api.routes.aktueller_monat as am
    now = datetime.now()
    anlage_id = await _seed(db, jahr=now.year, monat=now.month, einspeisung=100.0)

    async def _fake_connector(anlage, j, m):
        return {}

    async def _fake_mqtt(anlage, investitionen):
        return {}

    async def _fake_ha_stats(anlage, j, m):
        return {"einspeisung_kwh": (555.0, _info(am, "ha_statistics", 92))}

    monkeypatch.setattr(am, "_collect_connector_data", _fake_connector)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _fake_mqtt)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)

    res = await am.get_aktueller_monat(anlage_id=anlage_id, jahr=now.year, monat=now.month, db=db)
    assert res.einspeisung_kwh == 555.0


async def test_laufender_monat_ha_stats_gewinnt_ueber_connector_und_mqtt(db, monkeypatch):
    """Reihenfolge saved < connector < mqtt < ha_stats: bei konkurrierenden
    Werten für dasselbe Feld gewinnt HA-Stats (zuletzt angewendet)."""
    import backend.api.routes.aktueller_monat as am
    now = datetime.now()
    anlage_id = await _seed(db, jahr=now.year, monat=now.month, einspeisung=100.0)

    async def _fake_connector(anlage, j, m):
        return {"einspeisung_kwh": (200.0, _info(am, "local_connector", 90))}

    async def _fake_mqtt(anlage, investitionen):
        return {"einspeisung_kwh": (300.0, _info(am, "mqtt", 91))}

    async def _fake_ha_stats(anlage, j, m):
        return {"einspeisung_kwh": (555.0, _info(am, "ha_statistics", 92))}

    monkeypatch.setattr(am, "_collect_connector_data", _fake_connector)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _fake_mqtt)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)

    res = await am.get_aktueller_monat(anlage_id=anlage_id, jahr=now.year, monat=now.month, db=db)
    assert res.einspeisung_kwh == 555.0


async def test_laufender_monat_connector_ueberschreibt_gespeichert(db, monkeypatch):
    """Laufender Monat ohne MQTT/HA-Stats: der Connector überschreibt den
    gespeicherten Wert (Konfidenz 90 % > gespeichert)."""
    import backend.api.routes.aktueller_monat as am
    now = datetime.now()
    anlage_id = await _seed(db, jahr=now.year, monat=now.month, einspeisung=100.0)

    async def _fake_connector(anlage, j, m):
        return {"einspeisung_kwh": (222.0, _info(am, "local_connector", 90))}

    async def _fake_mqtt(anlage, investitionen):
        return {}

    async def _fake_ha_stats(anlage, j, m):
        return {}

    monkeypatch.setattr(am, "_collect_connector_data", _fake_connector)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _fake_mqtt)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)

    res = await am.get_aktueller_monat(anlage_id=anlage_id, jahr=now.year, monat=now.month, db=db)
    assert res.einspeisung_kwh == 222.0
