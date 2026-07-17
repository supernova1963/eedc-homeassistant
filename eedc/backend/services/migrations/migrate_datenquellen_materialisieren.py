"""
Datenquellen-V4 B8 — Materialisierung der effektiven Quelle je Feld.

Überführt das implizite „kein `quellen`-Eintrag = heutiges Merge-Verhalten"
(C2a/C2b-Read-Through-Sicherheitsnetz) in EXPLIZITE Zuordnungen (§2h, HA-first).
Damit bekommt jedes Feld eine benannte Quelle → Fundament für den späteren
keine-Default-Flip (B8-2), und die Datenquellen-Fläche zeigt die reale Quelle
statt des impliziten Defaults.

**Additiv + idempotent:** Felder MIT bestehendem `quellen`-Eintrag bleiben
unberührt — auch die bewusste „keine"-Wahl. Läuft einmalig via `_apply_once`.

**Konservativ** (Gernot-Entscheidung 2026-07-15): Feld ohne HA-Sensor UND ohne
Gateway-Mapping → `mqtt_inbound_standard` (bricht keine Bestandsinstallation;
Standalone-Connector-Felder, die auf Standard-Topics publishen, bleiben Inbound).

**Kein HTTP/Blocking** ([[feedback_migration_startup_kein_http]]): liest nur
`sensor_mapping`, `mqtt_gateway_mappings` und `build_expected_topics` (DB-only).
Reihenfolge je Feld: HA (sensor_mapping) → Gateway (mqtt_gateway_mappings) →
Inbound. Bei HA-Wahl wird ein paralleles Gateway-Mapping **deaktiviert, nicht
gelöscht** (§2h, verlustfrei rückholbar).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.core.config import HA_INTEGRATION_AVAILABLE
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.services.datenquellen_resolver import (
    ha_entity_fuer_feld as _ha_entity_fuer_feld,
    topic_suffix as _topic_suffix,
)
from backend.services.live_sensor_config import extract_live_config
from backend.services.mqtt_topic_registry import build_expected_topics
from backend.utils.investition_filter import aktiv_jetzt

logger = logging.getLogger(__name__)


def _feld_id(match_key) -> str:
    """Stabile Feld-Kennung aus dem match_key — identisch zu datenquellen._feld_id."""
    return "_".join(str(x) for x in match_key)


# `_ha_entity_fuer_feld` + `_topic_suffix` leben jetzt in datenquellen_resolver
# (gemeinsam mit der lazy B8-2-Auflösung) und werden hier re-exportiert — die
# B8-1-Materialisierung behält ihre KONSERVATIVE Stufe 3 (immer Inbound), während
# B8-2 (Fläche) Inbound nur bei tatsächlichem Wert wählt. Eine HA-Erkennung.


async def materialisiere_datenquellen(session: AsyncSession) -> None:
    """Materialisiert die effektive Quelle jedes noch nicht zugeordneten Feldes."""
    # Transport-Kennung ohne HTTP: Add-on = ha_app, sonst Remote-HA = ha_connector.
    # Die reale Verbindung löst der Read-Pfad (resolve_ha_connection) ohnehin auf.
    ha_kind = "ha_app" if HA_INTEGRATION_AVAILABLE else "ha_connector"

    anlagen = (await session.execute(select(Anlage))).scalars().all()
    materialisiert = 0
    for anlage in anlagen:
        mapping = dict(anlage.sensor_mapping or {})
        quellen = dict(mapping.get("quellen") or {})
        basis_live, inv_live_map, _bi, _ii = extract_live_config(anlage)

        gw_rows = (await session.execute(
            select(MqttGatewayMapping).where(MqttGatewayMapping.anlage_id == anlage.id)
        )).scalars().all()
        gw_by_zielkey = {r.ziel_key: r for r in gw_rows if getattr(r, "aktiv", True)}

        invs = (await session.execute(
            select(Investition).where(
                Investition.anlage_id == anlage.id, aktiv_jetzt()
            )
        )).scalars().all()

        felder = await build_expected_topics(session, anlage, investitionen=invs)
        geaendert = False
        for e in felder:
            fid = _feld_id(e["match_key"])
            if fid in quellen:
                continue  # explizit zugeordnet (auch „keine") → unberührt (additiv)

            suffix = _topic_suffix(e["topic"])
            ha_entity = _ha_entity_fuer_feld(fid, mapping, basis_live, inv_live_map)
            if ha_entity:
                quellen[fid] = {"quelle": ha_kind, "entity_id": ha_entity}
                # §2h: paralleles Gateway-Mapping desselben Feldes deaktivieren.
                row = gw_by_zielkey.get(suffix) if suffix else None
                if row is not None and getattr(row, "aktiv", True):
                    row.aktiv = False
            elif suffix and suffix in gw_by_zielkey:
                quellen[fid] = {"quelle": "mqtt_gateway", "mapping_id": gw_by_zielkey[suffix].id}
            else:
                quellen[fid] = {"quelle": "mqtt_inbound_standard"}
            geaendert = True
            materialisiert += 1

        if geaendert:
            mapping["quellen"] = quellen
            anlage.sensor_mapping = mapping
            flag_modified(anlage, "sensor_mapping")

    logger.info("B8-Materialisierung: %d Feld-Quellen explizit gemacht", materialisiert)
    # _apply_once committet.
