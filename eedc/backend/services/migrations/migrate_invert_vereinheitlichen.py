"""
Datenquellen-V4 — Vereinheitlichung der Vorzeichen-Umkehr (Invert).

Führt die drei bisher getrennten, quellen-GEKOPPELTEN Invert-Speicher in EINEN
feld-/wert-level Store `sensor_mapping.invertieren = {field_id: true}` zusammen
(quellen-unabhängig, am Read-Endwert angewendet):

1. Legacy `sensor_mapping.basis.live_invert` + `investitionen[id].live_invert`
   → `invertieren["basis_live_{key}"]` / `invertieren["inv_live_{id}_{key}"]`.
   (Bleibt zusätzlich stehen — `extract_live_config` unioniert; Invert idempotent.)
2. `quellen[field_id].invertieren` → `invertieren[field_id]`; das Sub-Flag wird aus
   dem quellen-Eintrag entfernt (Invert ist nicht mehr Teil der Quellen-Wahl).
3. `mqtt_gateway_mappings.invertieren=True` → `invertieren[field_id]` (field_id via
   ziel_key↔Topic-Suffix); die Gateway-Zeile wird auf `invertieren=False` gesetzt
   (Republish invertiert nicht mehr → der Read-Endwert-Pass übernimmt, kein Doppel).

**Additiv + idempotent**, DB-only, kein HTTP ([[feedback_migration_startup_kein_http]],
[[feedback_vollbackfill_nur_additiv]]). Zweitlauf findet keine offenen Flags mehr.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.services.datenquellen_resolver import topic_suffix
from backend.services.mqtt_topic_registry import build_expected_topics
from backend.utils.investition_filter import aktiv_jetzt

logger = logging.getLogger(__name__)


def _feld_id(match_key) -> str:
    return "_".join(str(x) for x in match_key)


async def migrate_invert_vereinheitlichen(session: AsyncSession) -> None:
    """Faltet Legacy-/Quellen-/Gateway-Invert in `sensor_mapping.invertieren`."""
    anlagen = (await session.execute(select(Anlage))).scalars().all()
    gefaltet = 0
    for anlage in anlagen:
        mapping = dict(anlage.sensor_mapping or {})
        invert = dict(mapping.get("invertieren") or {})
        vorher = dict(invert)

        # 1. Legacy live_invert (basis + je Investition).
        basis = mapping.get("basis") or {}
        for key, flag in (basis.get("live_invert") or {}).items():
            if flag:
                invert[f"basis_live_{key}"] = True
        for inv_id, inv_data in (mapping.get("investitionen") or {}).items():
            if not isinstance(inv_data, dict):
                continue
            for key, flag in (inv_data.get("live_invert") or {}).items():
                if flag:
                    invert[f"inv_live_{inv_id}_{key}"] = True

        # 2. quellen[field_id].invertieren → Store; Sub-Flag entfernen.
        quellen = mapping.get("quellen")
        quellen_geaendert = False
        if isinstance(quellen, dict):
            for fid, entry in quellen.items():
                if isinstance(entry, dict) and entry.get("invertieren"):
                    invert[fid] = True
                    entry.pop("invertieren", None)
                    quellen_geaendert = True

        # 3. Gateway-Mappings mit invertieren=True → Store (field_id via ziel_key),
        #    Zeile auf invertieren=False (Republish invertiert nicht mehr).
        gw_true = (await session.execute(
            select(MqttGatewayMapping).where(
                MqttGatewayMapping.anlage_id == anlage.id,
                MqttGatewayMapping.invertieren == True,  # noqa: E712
            )
        )).scalars().all()
        if gw_true:
            invs = (await session.execute(
                select(Investition).where(
                    Investition.anlage_id == anlage.id, aktiv_jetzt()
                )
            )).scalars().all()
            felder = await build_expected_topics(session, anlage, investitionen=invs)
            suffix_to_fid = {
                topic_suffix(e["topic"]): _feld_id(e["match_key"]) for e in felder
            }
            for row in gw_true:
                fid = suffix_to_fid.get(row.ziel_key)
                if fid:
                    invert[fid] = True
                row.invertieren = False

        if invert != vorher or quellen_geaendert:
            mapping["invertieren"] = invert
            anlage.sensor_mapping = mapping
            flag_modified(anlage, "sensor_mapping")
            gefaltet += 1

    logger.info("Invert-Vereinheitlichung: %d Anlagen migriert", gefaltet)
    # _apply_once committet.
