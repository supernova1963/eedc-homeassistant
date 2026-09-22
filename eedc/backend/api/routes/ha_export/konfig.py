"""HA-Export — MQTT-Konfiguration und Sensor-Abwahl (#400).

GET /api/mqtt/config · POST /api/mqtt/auto-publish · GET/POST /api/mqtt/abwahl
"""
# Reiner Umzug aus `api/routes/ha_export.py` (18.09.2026, Vorlage 8 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.services.activity_service import log_activity
from backend.services.ha_sensors_export import (
    AKTUELLES_SENSOR_PAKET,
    SENSOR_PAKET_LABELS,
    get_all_sensor_definitions,
)
from backend.services.mqtt_client import MQTTClient
from backend.services.mqtt_broker_settings import (
    resolve_broker_config,
    broker_aktiviert,
    broker_konfiguriert,
    export_aktiviert,
    abgewaehlte_sensoren,
    schreibe_export_settings,
    ABWAHL_FELD,
)
from backend.api.routes.ha_export.schemas import AbwahlRequest, AutoPublishRequest, MQTTConfigResponse

router = APIRouter()


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/mqtt/config", response_model=MQTTConfigResponse)
async def get_mqtt_config(db: AsyncSession = Depends(get_db)):
    """Gibt die aufgelöste MQTT-Broker-Konfiguration zurück.

    B7-5: Quelle ist jetzt der **gemeinsame Broker** (DB-Broker-Block → ENV-Fallback
    = Add-on-Optionen), nicht mehr ENV allein — sonst zeigt der Export-Block einen
    anderen Broker an als den, auf den er publiziert (#655-Klasse).

    B7-5b: ``auto_publish`` ist der **Eigenwert des Export-Toggles** (DB → ENV),
    bewusst NICHT mit ``enabled`` (Broker) verundet: der Switch im Block soll den
    eigenen Zustand zeigen und nicht umspringen, wenn jemand den Broker abschaltet.
    Die Und-Verknüpfung „darf jetzt publiziert werden" macht der Job selbst.
    """
    from backend.core.config import settings

    cfg = await resolve_broker_config(db)

    # Passwort als Maske zurückgeben wenn gesetzt
    password_masked = "••••••" if cfg.password else ""

    return MQTTConfigResponse(
        enabled=await broker_aktiviert(db),
        host=cfg.host,
        port=cfg.port,
        username=cfg.username or "",
        password=password_masked,
        auto_publish=await export_aktiviert(db),
        publish_interval_minutes=settings.mqtt_publish_interval,
        broker_konfiguriert=await broker_konfiguriert(db),
    )

@router.post("/mqtt/auto-publish")
async def set_auto_publish(payload: AutoPublishRequest, db: AsyncSession = Depends(get_db, scope="function")):
    """Schaltet den automatischen Export (Auto-Publish) ein/aus — B7-5b.

    Schreibt den DB-Settings-Key ``mqtt_export``; ENV bleibt reiner Fallback für
    Bestandsinstallationen ohne Eintrag. Wirkt sofort — der Scheduler-Job prüft
    die Einstellung bei jedem Lauf, ein Neustart ist nicht nötig.
    """
    # ⛔ Mischend schreiben, nicht ersetzend: seit #400 liegt die Abwahlliste im
    # selben Settings-Key. Das frühere `value = {"enabled": ...}` hätte sie bei
    # jedem Klick auf diesen Toggle wortlos gelöscht.
    await schreibe_export_settings(db, enabled=payload.enabled)

    return {"gespeichert": True, "enabled": payload.enabled}

# =============================================================================
# Sensor-Abwahl (#400) — welche Sensoren gehen ueberhaupt nach HA?
# =============================================================================

@router.get("/mqtt/abwahl")
async def get_sensor_abwahl(db: AsyncSession = Depends(get_db)):
    """Alle exportierbaren Sensor-Definitionen samt Abwahl-Zustand.

    ⭐ **Warum DEFINITIONEN und nicht die berechneten Werte:** Die Sensorliste im
    Export-Block zeigt nur Sensoren, die gerade einen Wert haben
    (`calculate_anlage_sensors` haengt jeden Eintrag an ein `value is not None`).
    Baute die Abwahl darauf auf, koennte man einen Sensor nicht abwaehlen, der
    heute leer ist und morgen einen Wert liefert — er erschiene dann
    unangekuendigt in HA, obwohl der Anwender die Fläche durchgesehen hat.

    ⭐ **N-545 (22.09.2026):** Jeder Eintrag sagt zusaetzlich, ob er mit dem
    AKTUELLEN Sensor-Paket dazugekommen ist (``neu``), und die Antwort traegt
    ``neues_paket`` — Nummer, Klartext-Label, die Schluessel des Pakets und
    davon die aktuell abgewaehlten. Aus dem letzten Paar entscheidet die
    Oberflaeche, ob sie den Hinweiskasten ueber der Liste zeigt: bei einer
    Bestandsinstallation stehen dort nach dem Update alle Paket-Schluessel, bei
    einer Neuinstallation keiner. **Nur Leserichtung** — diese Route schreibt
    nichts und waehlt nichts ab; das tut einmalig der Erstlauf-Schritt
    `migrations/migrate_sensor_paket_abwahl.py`.
    """
    abgewaehlt = await abgewaehlte_sensoren(db)
    definitionen = get_all_sensor_definitions()
    paket_keys = [d.key for d in definitionen if d.seit_paket == AKTUELLES_SENSOR_PAKET]

    return {
        "abgewaehlt": sorted(abgewaehlt),
        "neues_paket": {
            "paket": AKTUELLES_SENSOR_PAKET,
            "label": SENSOR_PAKET_LABELS.get(AKTUELLES_SENSOR_PAKET, ""),
            "keys": paket_keys,
            "abgewaehlt": [k for k in paket_keys if k in abgewaehlt],
        },
        "sensoren": [
            {
                "key": d.key,
                "name": d.name,
                "unit": d.unit,
                "icon": d.icon,
                "category": d.category.value,
                "formel": d.formel,
                "exportiert": d.key not in abgewaehlt,
                "neu": d.seit_paket == AKTUELLES_SENSOR_PAKET,
            }
            for d in definitionen
        ],
    }

@router.post("/mqtt/abwahl")
async def set_sensor_abwahl(payload: AbwahlRequest, db: AsyncSession = Depends(get_db, scope="function")):
    """Speichert die Abwahl und nimmt die neu abgewaehlten Topics zurueck.

    **Der Entscheid dahinter (Gernot, 28.08.):** Alle Sensoren bleiben per Default
    **an**; die Abwahl ist ausschliesslich eine bewusste Wahl des Anwenders. Weil
    sie bewusst ist, darf sie auch wirken — die Oberflaeche fragt vorher nach und
    sagt, dass die Daten in HA und auf dem Broker verloren sind.

    ⛔ **Abwaehlen heisst zuruecknehmen, nicht schweigen.** Wuerde eedc nur
    aufhoeren zu publizieren, bliebe das retained Discovery-Topic auf dem Broker
    liegen — und der Broker spielt es jedem neuen Abonnenten erneut zu. Die
    Entitaet waere nach dem naechsten HA-Neustart zurueck, und der Anwender kaeme
    nur mit einem MQTT-Client wieder heraus. Deshalb nimmt eedc **seine eigenen**
    Topics zurueck (`eedc/…` und `homeassistant/…/config`).
    """
    neu = {k for k in payload.abgewaehlt if k}
    bekannt = {d.key for d in get_all_sensor_definitions()}
    unbekannt = sorted(neu - bekannt)
    if unbekannt:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannte Sensor-Schlüssel: {', '.join(unbekannt)}",
        )

    vorher = await abgewaehlte_sensoren(db)
    await schreibe_export_settings(db, **{ABWAHL_FELD: sorted(neu)})

    # Nur das NEU Abgewaehlte muss vom Broker; was schon abgewaehlt war, ist
    # laengst weg, und was wieder angewaehlt wurde, legt der naechste Publish an.
    dazugekommen = neu - vorher
    entfernt = {"sensoren": 0, "topics": 0, "fehler": None}

    if dazugekommen:
        from backend.services.ha_mqtt_sync import belegte_sensor_eintraege

        client = MQTTClient(await resolve_broker_config(db))
        if client.is_available:
            # ⚠ Die Abwahl gilt anlagenuebergreifend (sie liegt in den globalen
            # Export-Settings) — also muss auch ueber ALLE Anlagen aufgeraeumt
            # werden. Nur die gerade gewaehlte Anlage zu raeumen liesse den
            # Sensor bei jeder weiteren Anlage stehen, obwohl er dort ebenso
            # abgewaehlt ist.
            alle_anlagen = list((await db.execute(select(Anlage))).scalars().all())
            eintraege: list = []
            for a in alle_anlagen:
                eintraege.extend(
                    await belegte_sensor_eintraege(db, a, nur_schluessel=dazugekommen)
                )
            entfernt = await client.remove_sensors(eintraege)

    await log_activity(
        kategorie="ha_export",
        aktion="MQTT-Sensor-Abwahl geändert",
        erfolg=entfernt["fehler"] is None,
        details=(
            f"{len(neu)} abgewählt ({len(dazugekommen)} neu), "
            f"{entfernt['topics']} Topics zurückgenommen"
            + (f" — {entfernt['fehler']}" if entfernt["fehler"] else "")
        ),
        db=db,
    )

    return {
        "gespeichert": True,
        "abgewaehlt": sorted(neu),
        "neu_abgewaehlt": sorted(dazugekommen),
        "entfernte_topics": entfernt["topics"],
        "fehler": entfernt["fehler"],
    }
