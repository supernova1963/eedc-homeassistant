"""B5/X-3 (05.09.2026) — ein Sensor, der seinen Wert verliert, bleibt in Home
Assistant nicht stehen; eine gesperrte Kennzahl sagt, warum sie leer ist.

Gemessen vor dem Bau: die Rechner lieferten nur Sensoren MIT Wert, der
Publisher publizierte genau diese Liste mit `retain=True`, die Discovery setzte
kein `expire_after`. Wurde die Arbeitszahl gesperrt (Fremdanteil, zweiter
Erzeuger, geschätzte Wärme), fehlte der Sensor im Lauf — und HA zeigte den
letzten Wert weiter und schrieb ihn stündlich in die Langzeitstatistik. Der
einzige Leerwert-Pfad im Publisher sendete zudem `"unknown"`; der HA-Leerwert
ist `"None"` (`PAYLOAD_NONE`, `homeassistant/components/mqtt/const.py`).

Schwesterdateien: test_400_mqtt_sensor_abwahl.py (derselbe Sync-Job, die Abwahl),
test_mqtt_export_rundung_je_groessenart.py (dasselbe aiomqtt-Doppel),
test_b5_export_matrix.py (die Sprossen, an denen die Arbeitszahl gesperrt ist).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: F401
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung  # noqa: F401
from backend.services.ha_sensors_export import SensorValue, get_sensor_definition
from backend.services.mqtt_broker_settings import ABWAHL_FELD, schreibe_export_settings
from backend.tests.test_b3_hub_matrix import SPROSSEN, JAHR, MONAT


# ── Publisher: der Leerwert heißt "None" ─────────────────────────────────────

class _FakeSession:
    def __init__(self, sink):
        self._sink = sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def publish(self, topic, payload=None, retain=False, **kwargs):
        self._sink.append((topic, payload))


class _FakeAiomqtt:
    def __init__(self):
        self.published = []

    def Client(self, **kwargs):  # noqa: N802
        return _FakeSession(self.published)


@pytest.mark.asyncio
async def test_publisher_sendet_fuer_none_den_ha_leerwert_mit_grund(monkeypatch):
    import json
    import backend.services.mqtt_client as mqtt_mod
    fake = _FakeAiomqtt()
    monkeypatch.setattr(mqtt_mod, "aiomqtt", fake)
    monkeypatch.setattr(mqtt_mod, "MQTT_AVAILABLE", True)
    client = mqtt_mod.MQTTClient()
    definition = get_sensor_definition("wp_cop_durchschnitt")
    sv = SensorValue(definition=definition, value=None,
                     zusatz_attribute={"grund": "Heizstab-Strom auf dem WP-Zähler"})
    assert await client.publish_all_sensors([sv], 1, "Test", 7, "WP") == {
        "total": 1, "success": 1, "failed": 0, "errors": []}
    zustand = {t: p for t, p in fake.published if t.endswith("/wp_cop_durchschnitt")}
    attribute = {t: p for t, p in fake.published if t.endswith("/wp_cop_durchschnitt/attributes")}
    assert list(zustand.values()) == ["None"], zustand
    assert json.loads(list(attribute.values())[0])["grund"] == "Heizstab-Strom auf dem WP-Zähler"


# ── Produzent: gesperrte Arbeitszahl = leerer Sensor mit Grund ───────────────

async def _wp(db, name, sprosse):
    parameter, daten, prov = SPROSSEN[sprosse]
    a = Anlage(anlagenname=name, leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    inv = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP",
                      anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
                      parameter=parameter)
    db.add(inv)
    await db.flush()
    if daten is not None:
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT,
                                      verbrauch_daten=daten, source_provenance=prov or {}))
    db.add(Monatsdaten(anlage_id=a.id, jahr=JAHR, monat=MONAT, einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0, gueltig_ab=date(2025, 1, 1)))
    await db.commit()
    return a, inv


@pytest.mark.asyncio
async def test_gesperrte_arbeitszahl_ist_ein_leerer_sensor_mit_grund(db):
    from backend.api.routes.ha_export import calculate_investition_sensors
    _, inv = await _wp(db, "f11", "F11_fremdstrom")
    export = {sv.definition.key: sv for sv in await calculate_investition_sensors(db, inv, None)}
    sv = export["wp_cop_durchschnitt"]
    assert sv.value is None
    assert sv.zusatz_attribute["grund"] == "Heizstab-Strom auf dem WP-Zähler"


@pytest.mark.asyncio
async def test_ein_geraet_ohne_messung_bekommt_weiter_keinen_sensor(db):
    """F1: keine Eingänge — kein Sensor, keine Entität in HA (#400-Klasse)."""
    from backend.api.routes.ha_export import calculate_investition_sensors
    _, inv = await _wp(db, "f1", "F1_nur_leistung")
    keys = {sv.definition.key for sv in await calculate_investition_sensors(db, inv, None)}
    assert "wp_cop_durchschnitt" not in keys


@pytest.mark.asyncio
async def test_rest_laesst_leere_werte_weg(db):
    """Die Export-Fläche bleibt, wie sie war: nur Sensoren mit Wert."""
    from backend.api.routes.ha_export import get_all_sensors
    a, inv = await _wp(db, "rest", "F11_fremdstrom")
    antwort = await get_all_sensors(db)
    geraet = next(i for i in antwort.investitionen if i.investition_id == inv.id)
    assert "wp_cop_durchschnitt" not in {s.key for s in geraet.sensors}


# ── Sync-Job: was verschwindet, wird geleert ─────────────────────────────────

class _FakeMqttClient:
    def __init__(self):
        self.is_available = True
        self.laeufe: list[tuple[int | None, list[str]]] = []
        self.geleert: list[tuple[int | None, str, object]] = []

    async def publish_all_sensors(self, sensor_values, anlage_id, anlage_name,
                                  investition_id=None, investition_name=None):
        self.laeufe.append((investition_id, [s.definition.key for s in sensor_values]))
        return {"total": len(sensor_values), "success": len(sensor_values),
                "failed": 0, "errors": []}

    async def publish_sensor_value(self, sensor_value, anlage_id, investition_id=None):
        self.geleert.append((investition_id, sensor_value.definition.key, sensor_value.value))
        return True

    async def remove_sensors(self, eintraege):
        return {"sensoren": len(eintraege), "topics": len(eintraege) * 3, "fehler": None}


def _haenge_klient_ein(monkeypatch, klient):
    from backend.services import ha_mqtt_sync
    monkeypatch.setattr(ha_mqtt_sync, "MQTTClient", lambda *a, **k: klient)

    async def _broker(_db):
        return None
    monkeypatch.setattr(ha_mqtt_sync, "resolve_broker_config", _broker)


@pytest.mark.asyncio
async def test_sync_leert_was_nicht_mehr_geliefert_wird(db, monkeypatch):
    from backend.services import ha_mqtt_sync
    a, inv = await _wp(db, "sync", "F6_wmz_gesamt")
    klient = _FakeMqttClient()
    _haenge_klient_ein(monkeypatch, klient)

    lauf1 = await ha_mqtt_sync.publish_anlage_sensors(db, a)
    geraet1 = {k for i, keys in klient.laeufe if i == inv.id for k in keys}
    assert "wp_cop_durchschnitt" in geraet1 and "wp_ersparnis_euro" in geraet1
    assert lauf1["geleert"] == []

    # Die Messung verschwindet (Monat gelöscht) — die Ersparnis ist abgewählt.
    await db.execute(delete(InvestitionMonatsdaten).where(InvestitionMonatsdaten.investition_id == inv.id))
    await db.commit()
    await schreibe_export_settings(db, **{ABWAHL_FELD: ["wp_ersparnis_euro"]})
    klient.laeufe.clear()
    lauf2 = await ha_mqtt_sync.publish_anlage_sensors(db, a)
    geleert = {(i, k) for i, k, v in klient.geleert if v is None}
    assert (inv.id, "wp_cop_durchschnitt") in geleert
    assert (inv.id, "wp_ersparnis_euro") not in geleert, "abgewählt nimmt die Abwahl-Route zurück"
    assert "wp_cop_durchschnitt" in lauf2["geleert"]

    # Dritter Lauf: nichts Neues zu leeren — der Job merkt sich den Stand.
    klient.geleert.clear()
    lauf3 = await ha_mqtt_sync.publish_anlage_sensors(db, a)
    assert lauf3["geleert"] == []
    assert klient.geleert == []


@pytest.mark.asyncio
async def test_sync_publiziert_die_gesperrte_arbeitszahl_als_leeren_sensor(db, monkeypatch):
    """Die Sperre kommt vom Produzenten: der Sensor ist im Lauf, mit None + Grund."""
    from backend.services import ha_mqtt_sync
    a, inv = await _wp(db, "sperre", "F11_fremdstrom")
    klient = _FakeMqttClient()
    _haenge_klient_ein(monkeypatch, klient)
    await ha_mqtt_sync.publish_anlage_sensors(db, a)
    geraet = {k for i, keys in klient.laeufe if i == inv.id for k in keys}
    assert "wp_cop_durchschnitt" in geraet
