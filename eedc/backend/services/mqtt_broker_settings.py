"""MQTT-Broker-Einstellungen — die EINE Wahrheit (Datenquellen-V4 §2g / B7-5).

Konzept-SoT: „**EIN Broker** für Inbound · Gateway · Export" (§2a/§2g). Vorher gab
es dafür zwei getrennte Wahrheiten:

* **Inbound/Gateway** lasen den DB-Settings-Key ``mqtt_inbound`` (Broker-Block in
  den Einstellungen, vom Nutzer gepflegt).
* **Export** (``ha_mqtt_sync``) löste seinen Broker ausschließlich aus **ENV**
  (``MQTT_HOST``/``MQTT_PORT``/… = HA-Add-on-Optionen) — der Broker-Block war für
  ihn unsichtbar. Darum war der Export ``haOnly``: ohne Add-on-ENV kein Broker.

Zwei Wahrheiten über denselben Broker sind die bekannte Mismatch-Klasse (#655:
„publiziert erfolgreich, aber in HA nichts sichtbar" — Publish-Route zog einen
anderen Broker als der Auto-Publish). Dieses Modul führt sie zusammen, analog zu
``services/ha_connection.resolve_ha_connection`` für die HA-Seite.

**Auflösungs-Reihenfolge (überall gleich):** expliziter Override → **DB**
(``mqtt_inbound``) → **ENV** (``settings.mqtt_*``) → kanonischer Default. Der
ENV-Fallback ist bewusst erhalten: bestehende Add-on-Installationen haben ihren
Broker in den Add-on-Optionen und keinen DB-Eintrag — sie laufen unverändert
weiter (kein Migrationszwang, [[feedback_vollbackfill_nur_additiv]]-Geist).
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings as env_settings
from backend.services.mqtt_client import MQTTConfig

# Der DB-Settings-Key des Broker-Blocks. Historisch „mqtt_inbound" (der Block hieß
# mal so); er trägt seit B1 die Verbindung für ALLE Richtungen — nicht umbenennen,
# bestehende Installationen tragen ihn.
MQTT_SETTINGS_KEY = "mqtt_inbound"

# B7-5b: Der DB-Settings-Key des Export-Toggles („Werte automatisch publizieren"
# im Export-Block), symmetrisch zum Broker-Toggle. Bis B7-5b war der Auto-Publish
# ausschließlich ENV-gesteuert (`MQTT_AUTO_PUBLISH`/`MQTT_ENABLED`) und damit für
# Standalone-Nutzer unerreichbar — ENV ist jetzt nur noch Fallback.
MQTT_EXPORT_SETTINGS_KEY = "mqtt_export"


async def _lade_settings(db: Optional[AsyncSession], key: str) -> Optional[dict]:
    """Roher Wert eines Settings-Keys aus der DB (``None`` = kein Eintrag).

    ``db=None`` ist zulässig und heißt „kein DB-Kontext" (Aufrufer ohne Session):
    dann gibt es keine DB-Wahrheit und die Auflösung fällt auf ENV zurück — nicht
    zu verwechseln mit „DB sagt leer".
    """
    if db is None:
        return None
    from backend.models.settings import Settings as SettingsModel

    row = (
        await db.execute(select(SettingsModel).where(SettingsModel.key == key))
    ).scalar_one_or_none()
    return row.value if row and row.value else None


async def lade_broker_settings(db: Optional[AsyncSession]) -> Optional[dict]:
    """Roher Wert des Broker-Settings aus der DB (``None`` = kein Eintrag)."""
    return await _lade_settings(db, MQTT_SETTINGS_KEY)


async def import_aktiviert(db: Optional[AsyncSession]) -> bool:
    """Werden Daten über MQTT **empfangen** (Import-Richtung)? — B7-5c.

    ``mqtt_inbound.enabled`` vermengte bis hierher **Verbindung** und **Import-
    Richtung** in einem Schalter. Damit war „nur Export" unerreichbar: Broker aus
    hieß zwangsläufig auch kein Export. Der Key trägt jetzt genau eine Bedeutung —
    die Import-Richtung; die Zugangsdaten (Host/Port/…) gelten richtungs-neutral
    für Import UND Export. Für Bestandsinstallationen ändert sich dabei nichts:
    ``enabled=true`` hieß schon immer „Inbound-Subscriber läuft".

    **Default ohne expliziten Eintrag (Gernot-Weiche 2026-07-16):** liegt eine
    HA-Verbindung vor (Supervisor ODER HA Connector), ist der Import **aus** —
    auf der HA App sind HA-Sensoren der Weg, MQTT-Import ist der Ausnahmefall
    (F2: „HA-Sensor Vorrang, MQTT = Notstopfen"). Nur ganz ohne HA ist MQTT der
    einzige Weg → Import an (ENV wie bisher).

    Bewusst **einstellungs**- und nicht prozessbasiert: ein beim Boot verbundener
    Service darf die Quellen-Optionen nicht offen halten, wenn der Nutzer den
    Import inzwischen deaktiviert hat (Gernot-Fund 2026-07-16).
    """
    value = await _lade_settings(db, MQTT_SETTINGS_KEY)
    if value is not None and "enabled" in value:
        return bool(value["enabled"])
    if await _ha_vorhanden(db):
        return False
    return bool(env_settings.mqtt_enabled)


async def broker_aktiviert(db: AsyncSession) -> bool:
    """Wird die Broker-Verbindung überhaupt genutzt? = mindestens eine Richtung.

    Die Verbindung hat bewusst KEINEN eigenen Aktiv-Schalter (Gernot-Weiche
    2026-07-16): er sagte nichts, was „beide Richtungen aus" nicht schon sagt,
    und ließe sich widersprüchlich klicken (Verbindung aus, Export an).
    """
    return await import_aktiviert(db) or await export_aktiviert(db)


async def _ha_vorhanden(db: Optional[AsyncSession]) -> bool:
    """Besteht eine HA-Verbindung? (Supervisor ODER Remote-HA per LL-Token)."""
    if db is None:
        from backend.core.config import settings as cfg

        return bool(cfg.supervisor_token)
    from backend.services.ha_connection import resolve_ha_connection

    _, _, kind = await resolve_ha_connection(db)
    return kind is not None


async def broker_konfiguriert(db: Optional[AsyncSession]) -> bool:
    """Ist überhaupt ein Broker hinterlegt? (DB-Host gesetzt ODER Add-on-MQTT an)

    Bewusst NICHT über ``resolve_broker_config``: das liefert IMMER einen Host
    (Default ``core-mosquitto``) und könnte „konfiguriert" nie verneinen.
    """
    value = await _lade_settings(db, MQTT_SETTINGS_KEY) or {}
    if value.get("host"):
        return True
    return bool(env_settings.mqtt_enabled)


async def export_aktiviert(db: Optional[AsyncSession]) -> bool:
    """Ist der **Auto-Publish** (Export-Richtung) eingeschaltet? — B7-5b/B7-5d.

    Der Toggle schaltet ausschließlich den periodischen Publish-Job (Gernot-Weiche
    2026-07-16). Manuelles Publizieren/Testen/Entfernen bleibt immer möglich: das
    sind Nutzer-Aktionen, und „Sensoren entfernen" braucht man gerade *nach* dem
    Abschalten zum Aufräumen ([[feedback_reparatur_statt_loesch_features]]).

    **Default ohne expliziten Eintrag (Gernot 2026-07-16):** besteht eine
    HA-Verbindung (Supervisor ODER LL-Token) und ist ein Broker hinterlegt, dann
    ist der Export **an** — „das Publishen der HA-MQTT-Autodiscovery-Topics und
    der Werte ist Pflicht", sonst legt eedc seine Sensoren am HA-Gerät nie an.
    Ohne HA gibt es niemanden, der die Discovery-Entitäten aufnimmt → aus.

    ⚠️ Der frühere ENV-Fallback (``mqtt_auto_publish or mqtt_enabled``) ist damit
    ERSETZT, nicht bloß ergänzt: er war ein reines Add-on-Phänomen und ließ den
    Default auf Standalone-/LL-Token-Boxen — also genau dort, wo der HA Connector
    gedacht ist — nie greifen. Der M-B-Entscheid (2026-06-10, „Export an ⇒
    Auto-Publish an") bleibt inhaltlich erhalten: im Add-on ist Supervisor immer
    da, und ``mqtt_enabled`` erfüllt ``broker_konfiguriert`` → Default an.
    Bestandsinstallationen mit aktivem Export sind zusätzlich durch die Migration
    (`migrate_mqtt_richtungen`) explizit festgeschrieben.
    """
    value = await _lade_settings(db, MQTT_EXPORT_SETTINGS_KEY)
    if value is not None and "enabled" in value:
        return bool(value["enabled"])
    return await _ha_vorhanden(db) and await broker_konfiguriert(db)


# ── Abwahl einzelner Sensoren (#400) ─────────────────────────────────────────
#
# **Entscheid Gernot (28.08.):** Jeder Sensor wird weiterhin **aktiviert**
# ausgeliefert — `enabled_by_default: false` faellt als Weg weg. Der Grund ist die
# Zeitreihe: eine Voreinstellung waere eine Wette darauf, welchen Wert ein
# Anwender spaeter braucht, und wer verliert, merkt es erst, wenn die Historie
# fehlt. Die Abwahl ist deshalb ausschliesslich eine **bewusste** Wahl.
#
# ⭐ **Abgewaehlt wird je Sensor-DEFINITION, nicht je Geraet** (Entscheid Gernot
# 28.08.). Wer „Ladezyklen" abwaehlt, waehlt sie an allen Speichern ab. Beide
# Melder (rapahl per PN, Knallfrosch T89667 #236) richten sich gegen Sensor-
# *Sorten* („ohne erkennbaren Nutzen"), nicht gegen einzelne Geraete.
ABWAHL_FELD = "abgewaehlte_sensoren"


async def abgewaehlte_sensoren(db: Optional[AsyncSession]) -> set[str]:
    """Welche Sensor-Schluessel hat der Anwender vom Export ausgenommen?

    Leere Menge = alles wird exportiert (der Default, s. Kasten oben). Ohne
    DB-Kontext gibt es keine Wahrheit ueber die Abwahl — dann exportiert eedc
    alles, statt still zu schweigen.
    """
    value = await _lade_settings(db, MQTT_EXPORT_SETTINGS_KEY) or {}
    roh = value.get(ABWAHL_FELD)
    if not isinstance(roh, list):
        return set()
    return {str(k) for k in roh if k}


async def schreibe_export_settings(db: AsyncSession, **felder) -> dict:
    """Schreibt Felder in ``mqtt_export`` — **mischend**, nicht ersetzend.

    ⛔ **Warum mischend (gemessen 28.08.):** Der Auto-Publish-Toggle schrieb
    ``setting.value = {"enabled": ...}`` und ersetzte damit den ganzen Dict. Ein
    zweites Feld im selben Key — die Abwahlliste — waere beim naechsten Klick auf
    den Toggle spurlos verschwunden, und zwar ohne Fehlermeldung: der Anwender
    haette seine abgewaehlten Sensoren wortlos zurueckbekommen. *Ein Schreiber,
    der den ganzen Datensatz ersetzt, ist erst dann ein Fehler, wenn ein zweites
    Feld dazukommt — deshalb faellt er beim Bau des zweiten Feldes auf und nicht
    beim Bau des ersten.*
    """
    from backend.models.settings import Settings as SettingsModel
    from sqlalchemy.orm.attributes import flag_modified

    setting = (
        await db.execute(
            select(SettingsModel).where(SettingsModel.key == MQTT_EXPORT_SETTINGS_KEY)
        )
    ).scalar_one_or_none()

    if setting:
        wert = dict(setting.value or {})
        wert.update(felder)
        setting.value = wert
        flag_modified(setting, "value")
    else:
        wert = dict(felder)
        db.add(SettingsModel(key=MQTT_EXPORT_SETTINGS_KEY, value=wert))
    await db.commit()
    return wert


async def auto_publish_aktiv(db: AsyncSession) -> bool:
    """Darf der Auto-Publish-Job jetzt publizieren? = allein die Export-Richtung.

    ⚠️ Hing kurzzeitig zusätzlich am Broker-/Import-Schalter („Broker aus = alles
    aus"). Das war die Folge der alten Vermengung von Verbindung und Import — und
    hätte den wichtigsten Zustand unmöglich gemacht: **„nur Export"** ist der
    Default der HA App (Import über HA-Sensoren, MQTT nur zum Publizieren). Die
    Richtungen sind unabhängig; geteilt sind nur die Zugangsdaten.

    Bewusst zur **Laufzeit** ausgewertet, nicht bei der Job-Registrierung: der
    Scheduler startet einmal beim Boot, ein DB-Toggle würde sonst erst nach einem
    Neustart wirken.
    """
    return await export_aktiviert(db)


async def resolve_broker_config(
    db: Optional[AsyncSession],
    host: Optional[str] = None,
    port: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> MQTTConfig:
    """Broker-Verbindung auflösen: Override → DB → ENV → Default.

    Genutzt von Inbound/Gateway (Boot) UND Export (Publish/Test/Remove) — damit
    zielen alle Richtungen garantiert auf denselben Broker (#655).
    """
    value = await lade_broker_settings(db) or {}

    def waehle(explizit, db_key: str, env_wert):
        if explizit is not None:
            return explizit
        db_wert = value.get(db_key)
        # Leerstring in der DB = „nicht gesetzt" (Formular schickt ""), nicht „leer erzwingen".
        if db_wert not in (None, ""):
            return db_wert
        return env_wert

    return MQTTConfig(
        host=waehle(host, "host", env_settings.mqtt_host),
        port=int(waehle(port, "port", env_settings.mqtt_port)),
        username=waehle(username, "username", env_settings.mqtt_username) or None,
        password=waehle(password, "password", env_settings.mqtt_password) or None,
    )
