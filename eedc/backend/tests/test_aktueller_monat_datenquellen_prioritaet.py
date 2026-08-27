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

from datetime import date, datetime, timedelta

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


def _info(am, quelle, konfidenz, abdeckung_von=None):
    return am.DatenquelleInfo(quelle=quelle, konfidenz=konfidenz, abdeckung_von=abdeckung_von)


def _monatsanfang(jahr: int, monat: int) -> datetime:
    """Connector-Abdeckung, die den ganzen Monat umfasst (Snapshot davor)."""
    return datetime(jahr, monat, 1) - timedelta(minutes=5)


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

    async def _poison_mqtt(db, anlage, investitionen, jahr, monat):
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

    async def _fake_mqtt(db, anlage, investitionen, jahr, monat):
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

    async def _fake_mqtt(db, anlage, investitionen, jahr, monat):
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
    gespeicherten Wert (Konfidenz 90 % > gespeichert) — sofern sein Delta den
    Monat ab dem Ersten misst."""
    import backend.api.routes.aktueller_monat as am
    now = datetime.now()
    anlage_id = await _seed(db, jahr=now.year, monat=now.month, einspeisung=100.0)

    async def _fake_connector(anlage, j, m):
        return {
            "einspeisung_kwh": (
                222.0, _info(am, "local_connector", 90, _monatsanfang(j, m))
            )
        }

    async def _fake_mqtt(db, anlage, investitionen, jahr, monat):
        return {}

    async def _fake_ha_stats(anlage, j, m):
        return {}

    monkeypatch.setattr(am, "_collect_connector_data", _fake_connector)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _fake_mqtt)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)

    res = await am.get_aktueller_monat(anlage_id=anlage_id, jahr=now.year, monat=now.month, db=db)
    assert res.einspeisung_kwh == 222.0


async def test_laufender_monat_connector_teilzeitraum_ueberschreibt_gespeichert_nicht(
    db, monkeypatch
):
    """Frisch eingerichteter Connector: sein Delta beginnt erst mitten im Monat
    und ist damit kein Monatswert. Der gespeicherte Wert (aus dem
    Monatsdaten-Import, der einzigen Quelle für die Zeit davor) bleibt stehen —
    sonst zeigt der laufende Monat still zu wenig."""
    import backend.api.routes.aktueller_monat as am
    now = datetime.now()
    anlage_id = await _seed(db, jahr=now.year, monat=now.month, einspeisung=100.0)

    # Erster Snapshot am 28. des laufenden Monats (bzw. später als der Erste).
    spaet = datetime(now.year, now.month, 1) + timedelta(days=27)

    async def _fake_connector(anlage, j, m):
        return {
            "einspeisung_kwh": (12.0, _info(am, "local_connector", 90, spaet)),
            "netzbezug_kwh": (7.0, _info(am, "local_connector", 90, spaet)),
        }

    async def _fake_mqtt(db, anlage, investitionen, jahr, monat):
        return {}

    async def _fake_ha_stats(anlage, j, m):
        return {}

    monkeypatch.setattr(am, "_collect_connector_data", _fake_connector)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _fake_mqtt)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)

    res = await am.get_aktueller_monat(anlage_id=anlage_id, jahr=now.year, monat=now.month, db=db)
    assert res.einspeisung_kwh == 100.0, (
        f"Teil-Abdeckung des Connectors hat den Monatswert überschrieben "
        f"(war {res.einspeisung_kwh}, erwartet 100)"
    )
    # Der gespeicherte Netzbezug (8.0 aus _seed) bleibt ebenfalls maßgeblich.
    assert res.netzbezug_kwh == 8.0


# ---------------------------------------------------------------------------
# #361 (coolxmad #353): Teilzeitraum-Gesamtwert sperrt die Komponenten-
# Aggregation nicht
# ---------------------------------------------------------------------------

async def _pv_investition_id(db: AsyncSession, anlage_id: int) -> int:
    from sqlalchemy import select
    res = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id, Investition.typ == "pv-module"
        )
    )
    return res.scalars().first().id


async def test_laufender_monat_connector_teilzeitraum_sperrt_pv_aggregation_nicht(
    db, monkeypatch
):
    """#361: Der PV-Zähler hängt an der Komponente (Anlagen-Zeile „keine"), die
    HA-Statistik liefert deshalb nur `inv_<id>_pv_erzeugung_kwh`. Ein frisch
    eingerichteter Connector meldet dagegen einen Anlagen-Gesamtwert von 0 kWh
    für die wenigen Stunden seit seiner Einrichtung. Dieses Bruchstück darf die
    Aggregation der Komponenten-Werte nicht unterdrücken — sonst steht der
    Monat auf 0, sobald der Connector verbunden wird (coolxmad #353)."""
    import backend.api.routes.aktueller_monat as am
    now = datetime.now()
    anlage_id = await _seed(db, jahr=now.year, monat=now.month, einspeisung=100.0)
    inv_id = await _pv_investition_id(db, anlage_id)
    spaet = datetime(now.year, now.month, 1) + timedelta(days=27)

    async def _fake_connector(anlage, j, m):
        return {"pv_erzeugung_kwh": (0.0, _info(am, "local_connector", 90, spaet))}

    async def _fake_mqtt(db, anlage, investitionen, jahr, monat):
        return {}

    async def _fake_ha_stats(anlage, j, m):
        return {
            f"inv_{inv_id}_pv_erzeugung_kwh": (996.0, _info(am, "ha_statistics", 92))
        }

    monkeypatch.setattr(am, "_collect_connector_data", _fake_connector)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _fake_mqtt)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)

    res = await am.get_aktueller_monat(anlage_id=anlage_id, jahr=now.year, monat=now.month, db=db)
    assert res.pv_erzeugung_kwh == 996.0, (
        f"Connector-Bruchstück (0 kWh seit dem 28.) hat die Komponenten-Summe "
        f"verdrängt (war {res.pv_erzeugung_kwh}, erwartet 996) — Regression #361"
    )


async def test_laufender_monat_connector_mit_abdeckung_sperrt_pv_aggregation_weiter(
    db, monkeypatch
):
    """Gegenprobe zu #361: Deckt der Connector den Monat ab, ist sein
    Anlagen-Gesamtwert vollwertig und die Komponenten-Summe darf NICHT
    zusätzlich aufaddiert werden (das wäre Doppelzählung derselben Erzeugung)."""
    import backend.api.routes.aktueller_monat as am
    now = datetime.now()
    anlage_id = await _seed(db, jahr=now.year, monat=now.month, einspeisung=100.0)
    inv_id = await _pv_investition_id(db, anlage_id)

    async def _fake_connector(anlage, j, m):
        return {
            "pv_erzeugung_kwh": (
                900.0, _info(am, "local_connector", 90, _monatsanfang(j, m))
            )
        }

    async def _fake_mqtt(db, anlage, investitionen, jahr, monat):
        return {}

    async def _fake_ha_stats(anlage, j, m):
        return {
            f"inv_{inv_id}_pv_erzeugung_kwh": (890.0, _info(am, "ha_statistics", 92))
        }

    monkeypatch.setattr(am, "_collect_connector_data", _fake_connector)
    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _fake_mqtt)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _fake_ha_stats)

    res = await am.get_aktueller_monat(anlage_id=anlage_id, jahr=now.year, monat=now.month, db=db)
    assert res.pv_erzeugung_kwh == 900.0, (
        f"Anlagen-Gesamtwert und Komponenten-Summe wurden addiert "
        f"(war {res.pv_erzeugung_kwh}, erwartet 900)"
    )
