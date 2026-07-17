"""B7-5c — HA-Verbindung aktivieren setzt den MQTT-Import auf den Default.

Gernot-Weiche 2026-07-16: „Auch bei bestehenden Standalone-Installationen sollte
sich nach Aktivierung der HA-Verbindung der Default einstellen (MQTT nur für
Export + HA-Discovery). Erst nach explizitem Einschalten von Import über MQTT
sollte die MQTT-Auswahl wieder sichtbar werden."

**Evidenz-Schranke = aktive Gateway-Mappings** (seine Präzisierung): nur dort geht
echte Konfiguration verloren (Fremd-Topic/Transform/JSON-Pfad). Der Inbound-Pfad
ist immer derselbe Standard-Topic-Satz und mit einem Klick wiederhergestellt.
"""

from sqlalchemy import select

from backend.api.routes.ha_remote import save_ha_remote_settings
from backend.models.anlage import Anlage
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.models.settings import Settings as SettingsModel
from backend.services.mqtt_broker_settings import MQTT_SETTINGS_KEY, import_aktiviert

HA_KEY = "ha_remote"
TOKEN = "t" * 20
# CI-hermetisch: private IP-LITERAL statt DNS-Name — der SSRF-Guard
# (_validate_connector_host) löst Hostnamen echt via getaddrinfo auf; ein nur
# im Heimnetz existierender Name (hass.iot) schlug im GitHub-Runner mit
# gaierror fehl (Run 29559960668). IP-Literale brauchen keine DNS-Query,
# private LAN-Bereiche sind im Guard ausdrücklich erlaubt.
URL = "http://192.168.1.13:8123"


async def _setze(db, key, value):
    row = (
        await db.execute(select(SettingsModel).where(SettingsModel.key == key))
    ).scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(SettingsModel(key=key, value=value))
    await db.commit()


async def _import_an(db):
    await _setze(db, MQTT_SETTINGS_KEY, {"enabled": True, "host": "nas", "port": 1883})


async def _aktiviere_ha(db, enabled=True):
    return await save_ha_remote_settings({"enabled": enabled, "base_url": URL, "token": TOKEN}, db)


async def _gateway(db, aktiv: bool):
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.commit()
    db.add(
        MqttGatewayMapping(
            anlage_id=anlage.id,
            quell_topic="shellies/em/power",
            ziel_key="live/pv_gesamt_w",
            aktiv=aktiv,
        )
    )
    await db.commit()


async def test_aktivierung_schaltet_import_ab(db):
    await _import_an(db)

    res = await _aktiviere_ha(db)

    assert res["mqtt_import"]["abgeschaltet"] is True
    assert await import_aktiviert(db) is False


async def test_zugangsdaten_bleiben_erhalten(db):
    """Der Export nutzt dieselbe Verbindung — Host/Port dürfen nicht verschwinden."""
    await _import_an(db)

    await _aktiviere_ha(db)

    wert = (
        await db.execute(select(SettingsModel).where(SettingsModel.key == MQTT_SETTINGS_KEY))
    ).scalar_one_or_none().value
    assert wert["host"] == "nas" and wert["port"] == 1883


async def test_aktives_gateway_mapping_blockt_den_default(db):
    """Gateway-Zuordnungen tragen echte Konfiguration → Import bleibt an."""
    await _import_an(db)
    await _gateway(db, aktiv=True)

    res = await _aktiviere_ha(db)

    assert res["mqtt_import"]["abgeschaltet"] is False
    assert res["mqtt_import"]["grund"] == "gateway_in_benutzung"
    assert res["mqtt_import"]["gateway_mappings"] == 1
    assert await import_aktiviert(db) is True, "Gateway-Zuordnung stumm entwertet"


async def test_inaktives_gateway_mapping_blockt_nicht(db):
    """Ein deaktiviertes Mapping ist nicht „in Benutzung" (§2h: deaktiviert ≠ gelöscht)."""
    await _import_an(db)
    await _gateway(db, aktiv=False)

    res = await _aktiviere_ha(db)

    assert res["mqtt_import"]["abgeschaltet"] is True
    assert await import_aktiviert(db) is False


async def test_erneutes_speichern_schaltet_nicht_erneut_ab(db):
    """NUR beim Übergang inaktiv→aktiv. Sonst würde ein Token-Wechsel den bewusst
    wieder eingeschalteten Import abwürgen — der Ausnahmefall, den Gernot benannt hat."""
    await _import_an(db)
    await _aktiviere_ha(db)              # schaltet ab
    await _import_an(db)                 # Nutzer schaltet bewusst wieder ein

    res = await _aktiviere_ha(db)        # z. B. Token korrigieren

    assert res["mqtt_import"] is None, "kein Übergang → keine Default-Anwendung"
    assert await import_aktiviert(db) is True


async def test_deaktivieren_der_ha_verbindung_ruehrt_import_nicht_an(db):
    await _import_an(db)

    res = await save_ha_remote_settings({"enabled": False, "base_url": "", "token": ""}, db)

    assert res["mqtt_import"] is None
    assert await import_aktiviert(db) is True


async def test_import_schon_aus_meldet_keine_abschaltung(db):
    await _setze(db, MQTT_SETTINGS_KEY, {"enabled": False, "host": "nas"})

    res = await _aktiviere_ha(db)

    assert res["mqtt_import"]["abgeschaltet"] is False
    assert res["mqtt_import"]["grund"] == "import_war_schon_aus"
