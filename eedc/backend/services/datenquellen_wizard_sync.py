"""
Datenquellen-V4 — Store-Abgleich nach dem Voll-Rewrite durch den V3-Wizard.

`POST /api/sensor-mapping/{id}` (V3-Sensor-Mapping-Wizard, bis zum Flip
erreichbar) baut `basis`/`investitionen`/`solcast_config` komplett neu auf und
kennt die V4-Stores (`quellen`, `invertieren`) nicht. Ohne Abgleich löschte ein
einziger Save die Stores — Gateway-Invert dabei irreversibel, weil die
Boot-Migrationen marker-einmalig sind und die Gateway-Zeilen bereits auf
`invertieren=False` stehen. Naives Erhalten wäre genauso falsch: HA-Einträge
speichern die `entity_id` explizit und zeigten nach einem Wizard-Edit auf stale
Entities. Zwei Schreiber brauchen EINE Schreib-Schicht
([[feedback_bypass_kombi_schreib_schicht]]) — dieser Sync ist sie für den Wizard.

Regeln (spiegeln B8-Materialisierung §2h HA-first + `set_feld_quelle`):

- **HA-Eintrag** folgt dem neuen Mapping: `entity_id` wird aktualisiert; hat das
  Feld keinen HA-Sensor mehr, fällt der Eintrag weg (Read-Through ohne Eintrag
  = implizites Altverhalten, bitgleich v3.45.9).
- **gateway/inbound-Eintrag + neu gemappter HA-Sensor → HA gewinnt** (B8
  HA-first); eine parallele Gateway-Zeile wird deaktiviert, nicht gelöscht (§2h).
- **`keine` bleibt unangetastet** (bewusste Wahl in der Datenquellen-Fläche).
- **Invert:** Die Wizard-Domäne `basis_live_*`/`inv_live_*` wird aus dem Store
  entfernt — die Wahrheit liegt danach im frisch geschriebenen `live_invert`,
  das die Laufzeit mit dem Store unioniert (`extract_live_config`). Bliebe der
  Store-Eintrag stehen, wäre ein Invert-ABWÄHLEN im Wizard wirkungslos.
  Energie-Feld-Inverts (u. a. migrierte Gateway-Herkunft) bleiben erhalten.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.core.config import HA_INTEGRATION_AVAILABLE
from backend.models.anlage import Anlage
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.services.datenquellen_resolver import (
    QUELLE_GATEWAY,
    QUELLE_HA_APP,
    QUELLE_HA_CONNECTOR,
    QUELLE_INBOUND,
    ha_entity_fuer_feld,
)
from backend.services.live_sensor_config import extract_live_config

logger = logging.getLogger(__name__)

_QUELLEN_HA = {QUELLE_HA_APP, QUELLE_HA_CONNECTOR}
_WIZARD_INVERT_PRAEFIXE = ("basis_live_", "inv_live_")


def uebernehme_fremde_mapping_keys(alt: dict | None, neu: dict) -> dict:
    """Kopiert alle Top-Level-Keys, die der Wizard NICHT besitzt, ins neue Mapping.

    Wizard-Besitz: `basis`, `investitionen`, `solcast_config` (werden von ihm
    vollständig neu geschrieben). Alles andere — `quellen`, `invertieren` und
    künftige Stores — überlebt den Rewrite und wird anschließend über
    `sync_stores_nach_wizard_save` abgeglichen.
    """
    for key, value in (alt or {}).items():
        if key not in ("basis", "investitionen", "solcast_config"):
            neu[key] = value
    return neu


async def sync_stores_nach_wizard_save(session: AsyncSession, anlage: Anlage) -> None:
    """Gleicht `quellen`/`invertieren` mit dem frisch geschriebenen Mapping ab.

    Erwartet, dass `anlage.sensor_mapping` bereits den neuen Stand inkl. der via
    `uebernehme_fremde_mapping_keys` übernommenen Stores trägt. Committet nicht
    — das macht der Aufrufer.
    """
    mapping = dict(anlage.sensor_mapping or {})
    quellen = dict(mapping.get("quellen") or {})
    invert = dict(mapping.get("invertieren") or {})
    if not quellen and not invert:
        return

    basis_live, inv_live_map, _bi, _ii = extract_live_config(anlage)
    ha_kind = QUELLE_HA_APP if HA_INTEGRATION_AVAILABLE else QUELLE_HA_CONNECTOR

    geaendert = False
    for fid, entry in list(quellen.items()):
        if not isinstance(entry, dict):
            continue
        quelle = entry.get("quelle")
        neue_entity = ha_entity_fuer_feld(fid, mapping, basis_live, inv_live_map)

        if quelle in _QUELLEN_HA:
            if not neue_entity:
                quellen.pop(fid)
                geaendert = True
            elif entry.get("entity_id") != neue_entity:
                quellen[fid] = {**entry, "entity_id": neue_entity}
                geaendert = True
        elif quelle in (QUELLE_GATEWAY, QUELLE_INBOUND) and neue_entity:
            if quelle == QUELLE_GATEWAY and entry.get("mapping_id") is not None:
                row = await session.get(MqttGatewayMapping, entry["mapping_id"])
                if row is not None and getattr(row, "aktiv", True):
                    row.aktiv = False
            quellen[fid] = {"quelle": ha_kind, "entity_id": neue_entity}
            geaendert = True
        # QUELLE_KEINE sowie gateway/inbound ohne neuen HA-Sensor: unangetastet.

    for fid in list(invert):
        if fid.startswith(_WIZARD_INVERT_PRAEFIXE):
            invert.pop(fid)
            geaendert = True

    if not geaendert:
        return

    if quellen:
        mapping["quellen"] = quellen
    else:
        mapping.pop("quellen", None)
    if invert:
        mapping["invertieren"] = invert
    else:
        mapping.pop("invertieren", None)
    anlage.sensor_mapping = mapping
    flag_modified(anlage, "sensor_mapping")
    logger.info(
        "Datenquellen-Stores nach Wizard-Save abgeglichen (anlage=%s)", anlage.id
    )
