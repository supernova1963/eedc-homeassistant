"""
Datenquellen-V4 — HA-Zuordnungen aus dem `quellen`-Store ins `sensor_mapping` nachziehen.

Reparatur für Installationen, die ihre Sensoren ab v4.0.0 in der neuen
Datenquellen-Fläche (oder über die HA-Energy-Übernahme im Setup-Wizard)
zugeordnet haben: beide Pfade schrieben bis v4.0.2 ausschließlich
`sensor_mapping["quellen"]`. Für alle Leser ist dieser Store aber nur ein
Read-Through — aufgezählt wird über `basis`/`investitionen`. Ergebnis: die
Fläche zeigte Sensor und Live-Wert, Daten-Checker meldete „Kein Basis-Zähler
für: Einspeisung, Netzbezug", Cockpit/Tag/Monat blieben leer
(Forum simon42 #89667/36–41, Algie + CHI3fx117).

**Bewusst nur additiv:** übernommen werden ausschließlich HA-Zuordnungen
(`ha_app`/`ha_connector` mit `entity_id`), die im Mapping noch fehlen. Kein
Räumen bestehender Einträge — das ist der expliziten Nutzer-Umschaltung im
Picker vorbehalten (`datenquellen_mapping_sync`, ab sofort im Schreibpfad).

Kein HTTP, keine Aggregation, nur JSON-Umbau ([[feedback_migration_startup_kein_http]]).
Historische Tage rechnet die Migration NICHT nach: die Stundenwerte lassen sich
über „Tag neu berechnen" bzw. „Mehrere Tage neu aggregieren" in der
Reparatur-Werkbank nachziehen — die Zähler-Snapshots dafür liegen vor, weil der
Snapshot-Writer den `quellen`-Store schon immer additiv honoriert hat
([[feedback_kein_grosser_heiler_knopf]]).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.models.anlage import Anlage
from backend.services.datenquellen_mapping_sync import (
    QUELLEN_HA,
    uebernehme_quelle_ins_mapping,
)

logger = logging.getLogger(__name__)


async def migriere_quellen_ins_mapping(session: AsyncSession) -> None:
    """Zieht HA-Quellen-Einträge in `basis`/`investitionen` nach (additiv)."""
    anlagen = (await session.execute(select(Anlage))).scalars().all()
    nachgezogen = 0
    for anlage in anlagen:
        mapping = dict(anlage.sensor_mapping or {})
        quellen = mapping.get("quellen")
        if not isinstance(quellen, dict):
            continue

        geaendert = False
        for field_id, entry in quellen.items():
            if not isinstance(entry, dict):
                continue
            quelle = entry.get("quelle")
            entity_id = entry.get("entity_id")
            if quelle not in QUELLEN_HA or not entity_id:
                continue  # additiv: nur HA-Zuordnungen, nie räumen
            if uebernehme_quelle_ins_mapping(mapping, field_id, quelle, entity_id):
                geaendert = True
                nachgezogen += 1

        if geaendert:
            anlage.sensor_mapping = mapping
            flag_modified(anlage, "sensor_mapping")

    logger.info(
        "Datenquellen-Reparatur: %d HA-Zuordnungen ins sensor_mapping nachgezogen",
        nachgezogen,
    )
    # _apply_once committet.
