"""B7-5c — Migration „MQTT-Richtungen materialisieren".

Der Zweck ist Bestandsschutz, nicht Kosmetik: der neue Import-Default (HA
vorhanden → Import aus) darf NICHT rückwirkend greifen. Ein Bestands-Add-on mit
`MQTT_ENABLED=true` und ohne DB-Eintrag importiert heute über MQTT — ohne diese
Migration verstummte es beim nächsten Start still (dieselbe Falle wie bei B8).
"""

from sqlalchemy import select

from backend.core.config import settings as app_settings
from backend.models.settings import Settings as SettingsModel
from backend.services.migrations.migrate_mqtt_richtungen import migriere_mqtt_richtungen
from backend.services.mqtt_broker_settings import (
    MQTT_EXPORT_SETTINGS_KEY,
    MQTT_SETTINGS_KEY,
    import_aktiviert,
)


async def _wert(db, key: str):
    row = (
        await db.execute(select(SettingsModel).where(SettingsModel.key == key))
    ).scalar_one_or_none()
    return row.value if row else None


async def _ha_verbindung(monkeypatch, kind):
    async def fake(_db):
        return ("http://ha/api", "tok", kind) if kind else (None, None, None)

    monkeypatch.setattr(
        "backend.services.ha_connection.resolve_ha_connection", fake, raising=False
    )


async def test_bestands_addon_mit_env_import_verstummt_nicht(db, monkeypatch):
    """DER Kern: Add-on mit MQTT_ENABLED=true, kein DB-Eintrag, HA vorhanden.
    Vor der Migration würde der neue Default den Import abschalten."""
    monkeypatch.setattr(app_settings, "mqtt_enabled", True, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_host", "core-mosquitto", raising=False)
    await _ha_verbindung(monkeypatch, "ha_app")

    # Ohne Migration hätte der Default zugeschlagen:
    assert await import_aktiviert(db) is False

    await migriere_mqtt_richtungen(db)

    assert await import_aktiviert(db) is True, "Bestands-Import stumm verloren"
    assert (await _wert(db, MQTT_SETTINGS_KEY))["host"] == "core-mosquitto"


async def test_frische_installation_bekommt_keinen_eingefrorenen_zustand(db, monkeypatch):
    """Ohne ENV-Import gibt es nichts zu retten → kein Eintrag anlegen, sonst
    bekäme eine Neuinstallation ein eingefrorenes „aus" statt des Defaults."""
    monkeypatch.setattr(app_settings, "mqtt_enabled", False, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_auto_publish", False, raising=False)
    await _ha_verbindung(monkeypatch, None)

    await migriere_mqtt_richtungen(db)

    assert await _wert(db, MQTT_SETTINGS_KEY) is None
    # Default greift weiter (keine HA → Import an, sobald ENV/Broker da ist).
    monkeypatch.setattr(app_settings, "mqtt_enabled", True, raising=False)
    assert await import_aktiviert(db) is True


async def test_expliziter_eintrag_bleibt_unberuehrt(db, monkeypatch):
    monkeypatch.setattr(app_settings, "mqtt_enabled", True, raising=False)
    db.add(SettingsModel(key=MQTT_SETTINGS_KEY, value={"enabled": False, "host": "nas"}))
    await db.commit()

    await migriere_mqtt_richtungen(db)

    assert (await _wert(db, MQTT_SETTINGS_KEY))["enabled"] is False


async def test_eintrag_ohne_richtung_wird_aus(db, monkeypatch):
    """Ein Eintrag ohne `enabled` startete den Subscriber nie (`.get("enabled")`)
    → die heutige Wirkung ist „aus", und die frieren wir ein."""
    monkeypatch.setattr(app_settings, "mqtt_enabled", True, raising=False)
    db.add(SettingsModel(key=MQTT_SETTINGS_KEY, value={"host": "nas", "port": 1883}))
    await db.commit()

    await migriere_mqtt_richtungen(db)

    wert = await _wert(db, MQTT_SETTINGS_KEY)
    assert wert["enabled"] is False
    assert wert["host"] == "nas", "Zugangsdaten dürfen nicht verloren gehen"


async def test_export_uebernimmt_alte_scheduler_bedingung(db, monkeypatch):
    """M-B: `mqtt_auto_publish or mqtt_enabled` war die effektive Export-Wahrheit."""
    monkeypatch.setattr(app_settings, "mqtt_auto_publish", False, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_enabled", True, raising=False)

    await migriere_mqtt_richtungen(db)

    assert (await _wert(db, MQTT_EXPORT_SETTINGS_KEY))["enabled"] is True


async def test_export_ohne_env_wird_nicht_eingefroren(db, monkeypatch):
    """Läuft der Export heute nicht, gibt es nichts zu erhalten → KEIN Eintrag.

    Eine erste Fassung schrieb hier `enabled=False` fest und hätte damit den
    Export-Default („HA-Verbindung + Broker → an", Gernot: Publishen ist Pflicht)
    für jede Neuinstallation dauerhaft tot geschrieben — expliziter Eintrag
    schlägt Default. Symmetrisch zum Import.
    """
    monkeypatch.setattr(app_settings, "mqtt_auto_publish", False, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_enabled", False, raising=False)

    await migriere_mqtt_richtungen(db)

    assert await _wert(db, MQTT_EXPORT_SETTINGS_KEY) is None

    # …und der Default greift danach ungehindert:
    await _ha_verbindung(monkeypatch, "ha_app")
    db.add(SettingsModel(key=MQTT_SETTINGS_KEY, value={"enabled": False, "host": "nas"}))
    await db.commit()
    from backend.services.mqtt_broker_settings import export_aktiviert

    assert await export_aktiviert(db) is True


async def test_idempotent(db, monkeypatch):
    monkeypatch.setattr(app_settings, "mqtt_enabled", True, raising=False)
    await _ha_verbindung(monkeypatch, "ha_app")

    await migriere_mqtt_richtungen(db)
    vorher = (await _wert(db, MQTT_SETTINGS_KEY), await _wert(db, MQTT_EXPORT_SETTINGS_KEY))
    await migriere_mqtt_richtungen(db)

    assert (await _wert(db, MQTT_SETTINGS_KEY), await _wert(db, MQTT_EXPORT_SETTINGS_KEY)) == vorher
