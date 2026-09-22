"""N-545 — Ein NEUES Sensor-Paket startet bei **Bestands**installationen abgewählt.

**Der Anlass.** Mit v4.0.27 kamen 21 neue Export-Sensoren auf einen Schlag; binnen
24 Stunden meldeten sich zwei Anwender (rapahl per PN, Knallfrosch T89667 #236,
daraus #400). In Home Assistant lässt sich eine einmal angelegte MQTT-Entität
nicht dauerhaft loswerden — der Registry-Eintrag bleibt, und die nächste Discovery
holt sie zurück. Rainer sagte es für das nächste Paket direkt: er will **vor** dem
Update wissen, was kommt, um abwählen zu können. Ohne diesen Schritt bekäme jede
Bestandsinstallation mit aktivem Export beim ersten Auto-Publish nach dem Update
28 neue Entitäten, **bevor** irgendjemand sie ansehen konnte.

**Was hier NICHT passiert.** Der Entscheid vom 28.08. bleibt unangetastet: Sensoren
werden nicht „per Default aus" ausgeliefert. Eine **Neuinstallation** bekommt
weiterhin alles — und auch eine Bestandsinstallation behält jeden Sensor, den sie
heute schon hat. Betroffen sind ausschließlich Definitionen, die es bei dieser
Installation **noch nie** gab; für sie kann keine Zeitreihe verloren gehen, weil
sie nie publiziert wurden. Genau deshalb nimmt der Schritt auch **keine Topics
zurück**: es liegt nichts auf dem Broker.

**Bestand oder Neuinstallation?** Die Frage stellt sich nur einmal — beim ersten
Lauf, der ``SENSOR_PAKET_FELD`` noch nicht vorfindet. Die Antwort braucht ein
Kriterium, das eine frisch aufgesetzte Box sicher **nicht** erfüllt:

    Bestand := es existiert mindestens eine `Anlage`
               UND der Export wurde hier schon einmal benutzt
               (``zuletzt_publiziert`` gefüllt ODER ``abgewaehlte_sensoren``
                gefüllt ODER ``enabled`` explizit True).

⛔ **Bewusst NICHT über ``export_aktiviert(db)``** (gemessen 22.09.2026). Die
Funktion löst ohne expliziten Eintrag auf einen **Default** auf: „HA-Verbindung
vorhanden UND Broker hinterlegt ⇒ an". Im Add-on ist beides ab der ersten Minute
wahr — eine brandneue Installation wäre damit „Bestand", sobald der Anwender seine
erste Anlage angelegt hat, und bekäme die 28 Sensoren abgewählt, obwohl sie für
sie gar nicht neu sind. (Dass `resolve_ha_connection` dahinter **kein HTTP** macht,
wurde geprüft — daran liegt es also nicht; es ist die Default-Auflösung selbst.)
Die drei Kriterien oben sind dagegen **Spuren tatsächlicher Benutzung**: sie
entstehen nur, wenn schon einmal publiziert, abgewählt oder der Toggle explizit
geschrieben wurde. `migrate_mqtt_richtungen` — das **vor** diesem Schritt läuft —
schreibt genau diesen expliziten ``enabled=True`` für jede Bestandsinstallation,
deren Export heute über ENV läuft.

**Läuft bei JEDEM Start**, nicht über ``_apply_once``: der Name einer Migration
gilt einmal je Installation, dieser Schritt muss aber **jedes künftige Paket**
sehen. Seine Idempotenz trägt er selbst — im ``sensor_paket_stand``.

**Additiv, nie ersetzend.** Die Abwahlliste wird **vereinigt**. Wer einen Sensor
des Pakets wieder anhakt, hat ihn nach dem nächsten Neustart immer noch: der Stand
ist dann bereits fortgeschrieben, und der Schritt fasst die Liste nicht mehr an.

**Kein HTTP, kein MQTT, kein Blocking** ([[feedback_migration_startup_kein_http]]):
zwei Selects und höchstens ein Settings-Schreibvorgang.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.ha_sensors_export import (
    AKTUELLES_SENSOR_PAKET,
    SENSOR_PAKET_LABELS,
    get_all_sensor_definitions,
)
from backend.services.mqtt_broker_settings import (
    ABWAHL_FELD,
    MQTT_EXPORT_SETTINGS_KEY,
    SENSOR_PAKET_FELD,
    ZULETZT_FELD,
    schreibe_export_settings,
)

logger = logging.getLogger(__name__)


async def _export_settings(db: AsyncSession) -> dict:
    """Der rohe ``mqtt_export``-Dict (leer, wenn es keinen Eintrag gibt)."""
    from backend.models.settings import Settings as SettingsModel

    row = (
        await db.execute(
            select(SettingsModel).where(SettingsModel.key == MQTT_EXPORT_SETTINGS_KEY)
        )
    ).scalar_one_or_none()
    return dict(row.value) if row and row.value else {}


def _gelesener_stand(werte: dict) -> int | None:
    """Der gespeicherte Paket-Stand — ``None``, wenn nie (oder unbrauchbar) geschrieben.

    ⚠ ``0`` ist ein **Wert** (= „Bestand, noch kein Paket eingewertet") und darf
    nicht mit „nicht gesetzt" verwechselt werden; ein `bool` dagegen ist kein
    Stand, auch wenn Python ihn als `int` durchgehen ließe.
    """
    roh = werte.get(SENSOR_PAKET_FELD)
    if isinstance(roh, bool) or not isinstance(roh, int):
        return None
    return roh


async def _ist_bestandsinstallation(db: AsyncSession, werte: dict) -> bool:
    """Gab es diese Installation schon, bevor das neue Paket dazukam?"""
    from backend.models.anlage import Anlage

    anzahl = (await db.execute(select(func.count()).select_from(Anlage))).scalar_one()
    if not anzahl:
        return False

    if werte.get(ZULETZT_FELD):
        return True
    if werte.get(ABWAHL_FELD):
        return True
    return werte.get("enabled") is True


def _keys_der_neuen_pakete(stand: int) -> set[str]:
    """Alle Sensor-Schlüssel, die nach ``stand`` und bis einschließlich heute kamen."""
    return {
        d.key
        for d in get_all_sensor_definitions()
        if stand < d.seit_paket <= AKTUELLES_SENSOR_PAKET
    }


async def neue_sensoren_bei_bestand_abwaehlen(db: AsyncSession) -> None:
    """Trägt die Schlüssel neuer Sensor-Pakete bei Bestandsinstallationen in die Abwahl."""
    werte = await _export_settings(db)
    stand = _gelesener_stand(werte)

    if stand is None:
        if not await _ist_bestandsinstallation(db, werte):
            # Neuinstallation: sie bekommt ALLES (Entscheid 28.08.). Nur den Stand
            # festschreiben, damit das NÄCHSTE Paket hier als „neu" erkannt wird.
            await schreibe_export_settings(
                db, **{SENSOR_PAKET_FELD: AKTUELLES_SENSOR_PAKET}
            )
            logger.info(
                "Sensor-Paket-Stand auf %s gesetzt (Neuinstallation — alle Sensoren bleiben an)",
                AKTUELLES_SENSOR_PAKET,
            )
            return
        stand = 0

    if stand >= AKTUELLES_SENSOR_PAKET:
        # Nichts Neues (oder ein Downgrade). Ein bereits angehakter Paket-Sensor
        # bleibt angehakt — die Liste wird hier nicht mehr angefasst.
        return

    neue = _keys_der_neuen_pakete(stand)
    if not neue:
        # Ein Paket ohne neue Definitionen ist möglich; den Stand trotzdem fortschreiben.
        await schreibe_export_settings(db, **{SENSOR_PAKET_FELD: AKTUELLES_SENSOR_PAKET})
        return

    vorher = {str(k) for k in (werte.get(ABWAHL_FELD) or []) if k}
    await schreibe_export_settings(
        db,
        **{
            ABWAHL_FELD: sorted(vorher | neue),
            SENSOR_PAKET_FELD: AKTUELLES_SENSOR_PAKET,
        },
    )
    logger.info(
        "N-545: %s neue Sensoren starten abgewaehlt (Paket %s — %s); "
        "Abwahl jetzt %s Schluessel. Anhaken unter Einstellungen → Home-Assistant-Export.",
        len(neue),
        AKTUELLES_SENSOR_PAKET,
        SENSOR_PAKET_LABELS.get(AKTUELLES_SENSOR_PAKET, "ohne Label"),
        len(vorher | neue),
    )
