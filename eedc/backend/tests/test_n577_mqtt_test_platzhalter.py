"""N-577 — „Verbindung testen" (MQTT-Broker) schickt nie den Platzhalter „***".

Melder rapahl, GitHub #415: GET /api/live/mqtt/settings liefert ein gespeichertes
Passwort als „***"; das Formular schickt es beim Testen unverändert zurück. Die
Test-Route ersetzte den Platzhalter nur aus der **laufenden** Inbound-Instanz — bei
ausgeschaltetem Import gibt es keine, „***" ging als echtes Passwort an den Broker,
und der Anwender bekam „Not authorized", obwohl das gespeicherte Passwort stimmte.

Jetzt löst die Route den Platzhalter über `resolve_broker_config` auf (DB → ENV) —
dieselbe Kaskade, mit der `main.py::_load_mqtt_config` den Import beim Start
verbindet. Geprüft wird, WELCHES Passwort beim Verbindungsversuch ankommt; der
Broker wird nie angesprochen (aiomqtt durch einen Mitschreiber ersetzt).
"""

import sys
import types

import pytest
from sqlalchemy import select

from backend.api.routes import live_mqtt_inbound as route
from backend.models.settings import Settings as SettingsModel
from backend.services import mqtt_broker_settings as mbs
from backend.services import mqtt_inbound_service


@pytest.fixture
def verbindungen(monkeypatch):
    """Ersetzt aiomqtt durch einen Mitschreiber; liefert die Liste der Verbindungsversuche."""
    versuche: list[dict] = []

    class _Client:
        def __init__(self, **kwargs):
            versuche.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setitem(sys.modules, "aiomqtt", types.SimpleNamespace(Client=_Client))
    # Der Melder-Zustand: Import aus ⇒ keine laufende Inbound-Instanz.
    monkeypatch.setattr(mqtt_inbound_service, "get_mqtt_inbound_service", lambda: None)
    monkeypatch.setattr(mbs.env_settings, "mqtt_password", "")
    monkeypatch.setattr(mbs.env_settings, "mqtt_username", "")
    return versuche


async def _speichere_broker(db, value: dict) -> None:
    db.add(SettingsModel(key=mbs.MQTT_SETTINGS_KEY, value=value))
    await db.commit()


async def _formular_passwort(db) -> str:
    """Was das Formular nach dem Laden im Passwortfeld trägt (GET /mqtt/settings)."""
    return (await route.get_mqtt_settings(db=db))["password"]


async def test_import_aus_platzhalter_wird_zum_gespeicherten_passwort(db, verbindungen):
    """Melder-Fall #415: Import aus, Passwort in der DB, Feld „***" ⇒ das gespeicherte kommt an."""
    await _speichere_broker(db, {"enabled": False, "host": "broker.local", "port": 1883,
                                 "username": "rainer", "password": "richtig"})
    platzhalter = await _formular_passwort(db)
    assert platzhalter == "***"  # die Vorbedingung: so steht es nach dem Laden im Feld

    antwort = await route.test_mqtt_connection(
        {"host": "broker.local", "port": 1883, "username": "rainer", "password": platzhalter},
        db=db,
    )

    assert antwort["connected"] is True
    assert [v["password"] for v in verbindungen] == ["richtig"]
    assert all(v["password"] != "***" for v in verbindungen)


async def test_neues_passwort_im_feld_gewinnt_gegen_das_gespeicherte(db, verbindungen):
    """Gegenprobe: wer ein neues Passwort eintippt, testet genau dieses."""
    await _speichere_broker(db, {"enabled": False, "host": "broker.local", "port": 1883,
                                 "username": "rainer", "password": "alt"})

    await route.test_mqtt_connection(
        {"host": "broker.local", "port": 1883, "username": "rainer", "password": "neu"},
        db=db,
    )

    assert [v["password"] for v in verbindungen] == ["neu"]


async def test_ohne_db_eintrag_kommt_der_platzhalter_aus_env(db, verbindungen, monkeypatch):
    """Add-on-Bestand ohne DB-Eintrag: GET zeigt „***" für das ENV-Passwort — der Test nimmt es auch."""
    # `route.settings` (GET) und `mbs.env_settings` (Kaskade) sind dasselbe Objekt.
    assert route.settings is mbs.env_settings
    monkeypatch.setattr(mbs.env_settings, "mqtt_password", "addon-geheim")
    assert (await db.execute(
        select(SettingsModel).where(SettingsModel.key == mbs.MQTT_SETTINGS_KEY)
    )).scalar_one_or_none() is None
    platzhalter = await _formular_passwort(db)
    assert platzhalter == "***"

    await route.test_mqtt_connection(
        {"host": "core-mosquitto", "port": 1883, "username": "addon", "password": platzhalter},
        db=db,
    )

    assert [v["password"] for v in verbindungen] == ["addon-geheim"]


# ── Speichern mit Platzhalter bei ENV-Passwort (Nebenfund, Entscheid Master: Option A) ──
#
# Add-on-Bestand: Broker-Passwort nur in den Add-on-Optionen (ENV), kein DB-Eintrag. Das
# Formular trägt „***"; wer den Block speichert, schickt den Platzhalter zurück. Gemessen
# vor dem Bau: der Import startete sofort OHNE Passwort, GET lieferte danach "" (leeres
# Feld ⇒ „Verbindung testen" ohne Passwort), obwohl Start und Export das ENV-Passwort nahmen.
# Option A: für den Sofort-Start über die Kaskade auflösen, in die DB nur, was dort stand.


@pytest.fixture
def gestartet(monkeypatch):
    """Ersetzt den Inbound-Start; liefert die Liste der `init_mqtt_inbound_service`-Aufrufe."""
    aufrufe: list[dict] = []

    class _Svc:
        async def start(self):
            return False  # kein Initialwert-Publish, kein Broker

        async def stop(self):
            pass

    def _init(**kwargs):
        aufrufe.append(kwargs)
        return _Svc()

    monkeypatch.setattr(mqtt_inbound_service, "init_mqtt_inbound_service", _init)
    return aufrufe


async def _db_passwort(db):
    row = (await db.execute(
        select(SettingsModel).where(SettingsModel.key == mbs.MQTT_SETTINGS_KEY)
    )).scalar_one()
    await db.refresh(row)
    return row.value.get("password")


async def _speichere_mit_platzhalter_aus_env(db, monkeypatch):
    monkeypatch.setattr(mbs.env_settings, "mqtt_password", "addon-geheim")
    vorher = await route.get_mqtt_settings(db=db)
    assert (vorher["password"], vorher["quelle"]) == ("***", "env")
    await route.save_mqtt_settings(
        {"enabled": True, "host": "core-mosquitto", "port": 1883,
         "username": "addon", "password": vorher["password"]},
        db=db,
    )


async def test_speichern_mit_platzhalter_startet_import_mit_env_passwort(db, verbindungen, gestartet, monkeypatch):
    """Symptom 1: der sofort gestartete Import bekommt das ENV-Passwort, nicht None."""
    await _speichere_mit_platzhalter_aus_env(db, monkeypatch)

    assert [a["password"] for a in gestartet] == ["addon-geheim"]


async def test_nach_dem_speichern_zeigt_get_weiter_den_platzhalter(db, verbindungen, gestartet, monkeypatch):
    """Symptom 2: GET liefert danach „***" (Block jetzt aus der DB), nicht ein leeres Feld."""
    await _speichere_mit_platzhalter_aus_env(db, monkeypatch)

    nachher = await route.get_mqtt_settings(db=db)
    assert (nachher["password"], nachher["quelle"]) == ("***", "db")


async def test_env_passwort_wird_nicht_in_die_db_kopiert(db, verbindungen, gestartet, monkeypatch):
    """Symptom 3: die DB trägt kein ENV-Geheimnis; die Kaskade liefert unverändert ENV."""
    await _speichere_mit_platzhalter_aus_env(db, monkeypatch)

    assert await _db_passwort(db) == ""
    assert (await mbs.resolve_broker_config(db)).password == "addon-geheim"


async def test_speichern_mit_neuem_passwort_landet_in_der_db_und_gewinnt(db, verbindungen, gestartet, monkeypatch):
    """Gegenprobe: ein eingetipptes Passwort wird gespeichert, gestartet und gewinnt gegen ENV."""
    monkeypatch.setattr(mbs.env_settings, "mqtt_password", "addon-geheim")

    await route.save_mqtt_settings(
        {"enabled": True, "host": "core-mosquitto", "port": 1883,
         "username": "addon", "password": "neu"},
        db=db,
    )

    assert await _db_passwort(db) == "neu"
    assert [a["password"] for a in gestartet] == ["neu"]
    assert (await mbs.resolve_broker_config(db)).password == "neu"
