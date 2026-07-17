"""B7-5 — EIN Broker für Inbound · Gateway · Export (Datenquellen-V4 §2g).

Sichert die Auflösungs-Reihenfolge **Override → DB → ENV → Default** des zentralen
`mqtt_broker_settings`. Kern der Regression: der Export zog seinen Broker früher
ausschließlich aus ENV und konnte damit auf einen ANDEREN Broker zielen als
Inbound/Gateway (#655-Klasse „publiziert erfolgreich, aber in HA nichts sichtbar").

Der ENV-Fallback ist Bestandsschutz: Add-on-Installationen haben ihren Broker in
den Add-on-Optionen und KEINEN DB-Eintrag — sie müssen unverändert weiterlaufen.
"""

import pytest
from sqlalchemy import select

from backend.models.settings import Settings as SettingsModel
from backend.services import mqtt_broker_settings as mbs


async def _setze_broker(db, value: dict | None):
    """Broker-Settings-Row setzen (None = Row entfernen)."""
    row = (
        await db.execute(select(SettingsModel).where(SettingsModel.key == mbs.MQTT_SETTINGS_KEY))
    ).scalar_one_or_none()
    if value is None:
        if row:
            await db.delete(row)
    elif row:
        row.value = value
    else:
        db.add(SettingsModel(key=mbs.MQTT_SETTINGS_KEY, value=value))
    await db.commit()


# ── Auflösungs-Reihenfolge ───────────────────────────────────────────────────

async def test_db_broker_gewinnt_ueber_env(db, monkeypatch):
    """Der Broker-Block (DB) ist die Wahrheit — auch wenn ENV etwas anderes sagt."""
    monkeypatch.setattr(mbs.env_settings, "mqtt_host", "core-mosquitto")
    monkeypatch.setattr(mbs.env_settings, "mqtt_port", 1883)
    await _setze_broker(db, {"enabled": True, "host": "nas.local", "port": 1884,
                                     "username": "u", "password": "p"})

    cfg = await mbs.resolve_broker_config(db)

    assert (cfg.host, cfg.port, cfg.username, cfg.password) == ("nas.local", 1884, "u", "p")


async def test_ohne_db_eintrag_gilt_env_bestandsschutz(db, monkeypatch):
    """Add-on-Bestand: kein DB-Eintrag → ENV (Add-on-Optionen) bleibt wirksam."""
    monkeypatch.setattr(mbs.env_settings, "mqtt_host", "core-mosquitto")
    monkeypatch.setattr(mbs.env_settings, "mqtt_port", 1883)
    monkeypatch.setattr(mbs.env_settings, "mqtt_username", "addon")
    monkeypatch.setattr(mbs.env_settings, "mqtt_password", "geheim")
    await _setze_broker(db, None)

    cfg = await mbs.resolve_broker_config(db)

    assert (cfg.host, cfg.port, cfg.username, cfg.password) == ("core-mosquitto", 1883, "addon", "geheim")


async def test_expliziter_override_gewinnt_ueber_db(db):
    """Request-Overrides (Test-Button mit Feldern) schlagen die DB."""
    await _setze_broker(db, {"enabled": True, "host": "nas.local", "port": 1884})

    cfg = await mbs.resolve_broker_config(db, host="anderer.host", port=1885)

    assert (cfg.host, cfg.port) == ("anderer.host", 1885)


async def test_leere_db_felder_fallen_auf_env(db, monkeypatch):
    """Leerstring in der DB = „nicht gesetzt" (Formular schickt "") → ENV, nicht "".

    Sonst hätte ein Broker-Block ohne User/Passwort die Add-on-Credentials gelöscht.
    """
    monkeypatch.setattr(mbs.env_settings, "mqtt_username", "addon")
    monkeypatch.setattr(mbs.env_settings, "mqtt_password", "geheim")
    await _setze_broker(db, {"enabled": True, "host": "nas.local", "username": "", "password": ""})

    cfg = await mbs.resolve_broker_config(db)

    assert cfg.host == "nas.local"
    assert (cfg.username, cfg.password) == ("addon", "geheim")


async def test_ohne_session_gilt_env(monkeypatch):
    """`db=None` = kein DB-Kontext → ENV (nicht „DB sagt leer")."""
    monkeypatch.setattr(mbs.env_settings, "mqtt_host", "env.host")

    cfg = await mbs.resolve_broker_config(None)

    assert cfg.host == "env.host"


# ── Aktiv-Toggle (User-Intent, nicht Prozess-Zustand) ────────────────────────
# B7-5c: Diese Tests prüften `broker_aktiviert` zurück, als der Key noch
# Verbindung UND Import-Richtung in einem Schalter vermengte. Gemeint war immer
# die Richtung („der Nutzer hat den Block deaktiviert") — sie zielen deshalb
# jetzt auf `import_aktiviert`. `broker_aktiviert` = „mindestens eine Richtung"
# wird in test_mqtt_export_toggle_b7_5b.py geprüft.

async def test_import_aktiviert_liest_db_toggle(db, monkeypatch):
    monkeypatch.setattr(mbs.env_settings, "mqtt_enabled", True)
    await _setze_broker(db, {"enabled": False, "host": "nas.local"})

    # DB sagt aus → aus, obwohl ENV an ist (der Nutzer hat den Import deaktiviert).
    assert await mbs.import_aktiviert(db) is False

    await _setze_broker(db, {"enabled": True, "host": "nas.local"})
    assert await mbs.import_aktiviert(db) is True


async def test_import_aktiviert_ohne_db_eintrag_faellt_auf_env(db, monkeypatch):
    """Ohne HA-Verbindung entscheidet weiter ENV (Default-Regel greift nur, wenn
    HA vorhanden ist — siehe test_mqtt_export_toggle_b7_5b.py)."""
    await _setze_broker(db, None)

    monkeypatch.setattr(mbs.env_settings, "mqtt_enabled", True)
    assert await mbs.import_aktiviert(db) is True

    monkeypatch.setattr(mbs.env_settings, "mqtt_enabled", False)
    assert await mbs.import_aktiviert(db) is False


# ── Export ↔ Inbound: derselbe Broker (der eigentliche B7-5-Punkt) ───────────

async def test_export_publish_nutzt_denselben_broker_wie_inbound(db, monkeypatch):
    """`publish_anlage_sensors` ohne Override zieht den DB-Broker, nicht ENV.

    Das ist die Regression gegen die alte Trennung (Export=ENV, Inbound=DB): ein
    Standalone-Nutzer ohne Add-on-ENV bekam sonst `core-mosquitto` statt seines
    Brokers — genau der Mismatch aus #655.
    """
    from backend.services import ha_mqtt_sync
    import backend.api.routes.ha_export as ha_export

    monkeypatch.setattr(mbs.env_settings, "mqtt_host", "core-mosquitto")
    await _setze_broker(db, {"enabled": True, "host": "nas.local", "port": 1884})

    gesehen = {}

    class _Client:
        is_available = True

        def __init__(self, config):
            gesehen["host"], gesehen["port"] = config.host, config.port

        async def publish_all_sensors(self, *a, **k):
            return {"total": 1, "success": 1, "failed": 0, "errors": []}

    monkeypatch.setattr(ha_mqtt_sync, "MQTTClient", _Client)

    async def fake_calc(db, anlage):
        return [object()]

    monkeypatch.setattr(ha_export, "calculate_anlage_sensors", fake_calc)

    class _Anlage:
        id = 1
        anlagenname = "A"

    await ha_mqtt_sync.publish_anlage_sensors(db, _Anlage())

    assert (gesehen["host"], gesehen["port"]) == ("nas.local", 1884)
