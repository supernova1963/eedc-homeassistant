"""B7-5b — Export-Toggle (Auto-Publish) als DB-Einstellung.

Datenquellen-V4 §2g: EIN Broker, zwei Richtungen. Die Export-Richtung war bis
hierher ausschließlich ENV-gesteuert (`MQTT_AUTO_PUBLISH`/`MQTT_ENABLED`) und für
Standalone-Nutzer damit unerreichbar. Jetzt: DB-Toggle (`mqtt_export`), ENV nur
noch Fallback für Bestandsinstallationen.

Der riskante Teil ist der **Scheduler**: der Job wurde früher nur registriert,
wenn die ENV-Flags beim Boot passten. Ein DB-Toggle hätte so erst nach einem
Neustart gewirkt. Jetzt wird der Job immer registriert und prüft zur Laufzeit —
diese Tests pinnen „läuft" und „skippt".
"""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from backend.core.config import settings as app_settings
from backend.models.anlage import Anlage
from backend.models.settings import Settings as SettingsModel
from backend.services.mqtt_broker_settings import (
    MQTT_EXPORT_SETTINGS_KEY,
    MQTT_SETTINGS_KEY,
    auto_publish_aktiv,
    broker_aktiviert,
    export_aktiviert,
    import_aktiviert,
)


async def _setze(db, key: str, value: dict) -> None:
    row = (
        await db.execute(select(SettingsModel).where(SettingsModel.key == key))
    ).scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(SettingsModel(key=key, value=value))
    await db.commit()


# ── export_aktiviert: DB vor ENV ────────────────────────────────────────────

async def test_db_toggle_schlaegt_env(db, monkeypatch):
    """Der DB-Toggle ist die Wahrheit — auch gegen ein aktives ENV-Flag."""
    monkeypatch.setattr(app_settings, "mqtt_auto_publish", True, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_enabled", True, raising=False)

    await _setze(db, MQTT_EXPORT_SETTINGS_KEY, {"enabled": False})
    assert await export_aktiviert(db) is False

    await _setze(db, MQTT_EXPORT_SETTINGS_KEY, {"enabled": True})
    assert await export_aktiviert(db) is True


async def test_db_toggle_an_trotz_env_aus(db, monkeypatch):
    """Standalone-Fall: ohne ENV-Flags war der Export bisher gar nicht aktivierbar."""
    monkeypatch.setattr(app_settings, "mqtt_auto_publish", False, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_enabled", False, raising=False)

    await _setze(db, MQTT_EXPORT_SETTINGS_KEY, {"enabled": True})
    assert await export_aktiviert(db) is True


# ── Export-Default: HA-Verbindung + Broker (B7-5d) ──────────────────────────
# Gernot 2026-07-16: „Besteht eine Verbindung zu HA (Supervisor oder remote mit
# LL-Token), dann ist das Publishen der Autodiscovery-Topics und der Werte
# Pflicht." Ohne HA nimmt niemand die Discovery-Entitäten auf → aus.

@pytest.mark.parametrize("kind", ["ha_app", "ha_connector"])
async def test_default_export_an_bei_ha_und_broker(db, monkeypatch, kind):
    monkeypatch.setattr(app_settings, "mqtt_auto_publish", False, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_enabled", False, raising=False)
    await _ha_verbindung(monkeypatch, kind)
    await _setze(db, MQTT_SETTINGS_KEY, {"enabled": False, "host": "nas", "port": 1883})

    assert await export_aktiviert(db) is True


async def test_default_export_aus_ohne_ha(db, monkeypatch):
    """Ohne HA gibt es keinen Empfänger für die Discovery-Entitäten."""
    monkeypatch.setattr(app_settings, "mqtt_enabled", False, raising=False)
    await _ha_verbindung(monkeypatch, None)
    await _setze(db, MQTT_SETTINGS_KEY, {"enabled": True, "host": "nas", "port": 1883})

    assert await export_aktiviert(db) is False


async def test_default_export_aus_ohne_broker(db, monkeypatch):
    """HA da, aber gar kein Broker hinterlegt → nichts zu publizieren."""
    monkeypatch.setattr(app_settings, "mqtt_enabled", False, raising=False)
    await _ha_verbindung(monkeypatch, "ha_app")

    assert await export_aktiviert(db) is False


async def test_addon_mqtt_env_zaehlt_als_broker(db, monkeypatch):
    """M-B-Entscheid (2026-06-10) bleibt inhaltlich: im Add-on ist Supervisor da,
    und MQTT_ENABLED erfüllt „Broker hinterlegt" → Export an. Nur der Weg dahin
    ist jetzt die Default-Regel statt eines ENV-Sonderfalls."""
    monkeypatch.setattr(app_settings, "mqtt_auto_publish", False, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_enabled", True, raising=False)
    await _ha_verbindung(monkeypatch, "ha_app")

    assert await export_aktiviert(db) is True


async def test_db_eintrag_ohne_enabled_faellt_auf_default(db, monkeypatch):
    """Ein Eintrag ohne `enabled`-Schlüssel ist keine Aussage → Default entscheidet."""
    await _ha_verbindung(monkeypatch, "ha_app")
    await _setze(db, MQTT_SETTINGS_KEY, {"host": "nas"})
    await _setze(db, MQTT_EXPORT_SETTINGS_KEY, {})

    assert await export_aktiviert(db) is True


# ── auto_publish_aktiv: Verbindung UND Richtung ─────────────────────────────

@pytest.mark.parametrize(
    "imp, export, erwartet",
    [
        (True, True, True),
        (True, False, False),
        # B7-5c: „nur Export" MUSS publizieren — das ist der Default der HA App
        # (Import über HA-Sensoren, MQTT nur zum Publizieren). Hing der Export am
        # Import-Schalter, wäre genau dieser Zustand unmöglich.
        (False, True, True),
        (False, False, False),
    ],
)
async def test_auto_publish_haengt_nur_an_der_export_richtung(db, monkeypatch, imp, export, erwartet):
    monkeypatch.setattr(app_settings, "mqtt_auto_publish", False, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_enabled", False, raising=False)
    await _setze(db, MQTT_SETTINGS_KEY, {"enabled": imp, "host": "h", "port": 1883})
    await _setze(db, MQTT_EXPORT_SETTINGS_KEY, {"enabled": export})

    assert await auto_publish_aktiv(db) is erwartet


# ── B7-5c: Richtungen getrennt + Default-Regel ──────────────────────────────

@pytest.mark.parametrize(
    "imp, export, erwartet",
    [(False, False, False), (True, False, True), (False, True, True), (True, True, True)],
)
async def test_broker_aktiviert_ist_mindestens_eine_richtung(db, monkeypatch, imp, export, erwartet):
    """Die Verbindung hat keinen eigenen Schalter — sie gilt als genutzt, sobald
    eine Richtung an ist (sonst wären widersprüchliche Zustände klickbar)."""
    monkeypatch.setattr(app_settings, "mqtt_auto_publish", False, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_enabled", False, raising=False)
    await _setze(db, MQTT_SETTINGS_KEY, {"enabled": imp, "host": "h", "port": 1883})
    await _setze(db, MQTT_EXPORT_SETTINGS_KEY, {"enabled": export})

    assert await broker_aktiviert(db) is erwartet


async def _ha_verbindung(monkeypatch, kind):
    """Patcht die HA-Verbindungs-Auflösung (Supervisor/Connector/keine)."""
    async def fake(_db):
        return ("http://ha/api", "tok", kind) if kind else (None, None, None)

    monkeypatch.setattr(
        "backend.services.ha_connection.resolve_ha_connection", fake, raising=False
    )


@pytest.mark.parametrize("kind", ["ha_app", "ha_connector"])
async def test_default_import_aus_wenn_ha_vorhanden(db, monkeypatch, kind):
    """Gernot-Weiche 2026-07-16: HA App ODER HA Connector → Import per Default AUS,
    damit die Fläche nur HA-Sensor + Keine anbietet. Schlägt sogar ein aktives
    ENV-Flag — dort war MQTT_ENABLED immer schon der Export-Schalter (M-B)."""
    monkeypatch.setattr(app_settings, "mqtt_enabled", True, raising=False)
    await _ha_verbindung(monkeypatch, kind)

    assert await import_aktiviert(db) is False


async def test_default_import_an_wenn_gar_keine_ha(db, monkeypatch):
    """Ohne HA ist MQTT der einzige Weg → Import an (F2: „Standalone ohne HA → nur MQTT")."""
    monkeypatch.setattr(app_settings, "mqtt_enabled", True, raising=False)
    await _ha_verbindung(monkeypatch, None)

    assert await import_aktiviert(db) is True


async def test_expliziter_eintrag_schlaegt_die_default_regel(db, monkeypatch):
    """Der Ausnahmefall, den Gernot benannt hat: HA App, aber ein Gerät hängt nicht
    in HA → Nutzer schaltet den Import an. Das muss halten."""
    await _ha_verbindung(monkeypatch, "ha_app")
    await _setze(db, MQTT_SETTINGS_KEY, {"enabled": True, "host": "h", "port": 1883})

    assert await import_aktiviert(db) is True


# ── Scheduler: Registrierung entkoppelt, Aktiv-Check im Job ─────────────────

async def test_job_immer_registriert_auch_ohne_env(monkeypatch):
    """Kern von B7-5b: die Registrierung darf NICHT mehr an der Einstellung hängen,
    sonst wirkt der DB-Toggle erst nach einem Neustart."""
    from backend.services.scheduler import EEDCScheduler

    monkeypatch.setattr(app_settings, "mqtt_auto_publish", False, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_enabled", False, raising=False)

    scheduler = EEDCScheduler()
    assert scheduler.start(), "Scheduler-Start fehlgeschlagen (APScheduler fehlt?)"
    try:
        assert scheduler._scheduler.get_job("mqtt_auto_publish") is not None, (
            "Job muss immer registriert sein — der Aktiv-Check läuft im Job"
        )
    finally:
        scheduler._scheduler.shutdown(wait=False)


async def _job_laeuft(db, monkeypatch) -> bool:
    """Führt den Job aus und meldet, ob er bis zum Publish durchlief.

    Der Job holt sich seine Session selbst über `get_session()` — ohne diesen
    Patch liefe er an der Test-DB vorbei und die Skip-Tests wären grün, ohne
    irgendetwas zu beweisen. Die `anlage` ist nötig, damit „läuft" überhaupt zu
    einem Publish-Aufruf führt.
    """
    from backend.services import scheduler as sched_mod

    db.add(Anlage(anlagenname="Test", leistung_kwp=10.0))
    await db.commit()

    @asynccontextmanager
    async def fake_session():
        yield db

    monkeypatch.setattr("backend.core.database.get_session", fake_session, raising=False)

    aufrufe: list[int] = []

    async def fake_publish(_db, anlage):
        aufrufe.append(anlage.id)
        return {"available": True, "no_data": False, "success": 1, "failed": 0, "errors": []}

    monkeypatch.setattr(
        "backend.services.ha_mqtt_sync.publish_anlage_sensors", fake_publish, raising=False
    )
    await sched_mod.mqtt_auto_publish_job()
    return bool(aufrufe)


async def test_job_skippt_bei_export_aus(db, monkeypatch):
    """Der Toggle wirkt zur Laufzeit — ohne Neustart."""
    monkeypatch.setattr(app_settings, "mqtt_auto_publish", True, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_enabled", True, raising=False)
    await _setze(db, MQTT_SETTINGS_KEY, {"enabled": True, "host": "h", "port": 1883})
    await _setze(db, MQTT_EXPORT_SETTINGS_KEY, {"enabled": False})

    assert await _job_laeuft(db, monkeypatch) is False


async def test_job_publiziert_bei_nur_export(db, monkeypatch):
    """„nur Export" = der Default-Zustand der HA App (Import über HA-Sensoren,
    MQTT ausschließlich zum Publizieren). Der Job MUSS hier laufen — hinge er am
    Import-Schalter, wäre genau dieser Zustand tot (B7-5c, Gernot-Korrektur)."""
    monkeypatch.setattr(app_settings, "mqtt_auto_publish", True, raising=False)
    await _setze(db, MQTT_SETTINGS_KEY, {"enabled": False, "host": "h", "port": 1883})
    await _setze(db, MQTT_EXPORT_SETTINGS_KEY, {"enabled": True})

    assert await _job_laeuft(db, monkeypatch) is True


async def test_job_publiziert_bei_beiden_an(db, monkeypatch):
    """Gegenprobe zu den Skip-Tests: ohne sie beweisen die nichts (ein Job, der
    immer skippt, bestünde sie auch)."""
    monkeypatch.setattr(app_settings, "mqtt_auto_publish", False, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_enabled", False, raising=False)
    await _setze(db, MQTT_SETTINGS_KEY, {"enabled": True, "host": "h", "port": 1883})
    await _setze(db, MQTT_EXPORT_SETTINGS_KEY, {"enabled": True})

    assert await _job_laeuft(db, monkeypatch) is True
