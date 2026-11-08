"""
N-780 (Päckchen U, 8.11.2026) — Inbound-Stempel an Energie-Feldern ohne Leser auf „Keine".

Acht Energie-Felder nimmt der MQTT-Inbound an, verarbeitet sie aber nicht (`mqtt_topic_registry.energie_topic_ohne_leser`:
BKW-/Sonstiges-Eigenverbrauch, Sonstiges-Einspeisung, -Erlös und -Bezugsaufteilung, externe Ladung in kWh und €). Die
B8-Materialisierung (`migrate_datenquellen_materialisieren`) hat beim einmaligen Start-Lauf jedes Feld ohne HA-Sensor und
ohne Gateway-Zeile auf `mqtt_inbound_standard` gestempelt, Pass 1 der `/felder`-Route bei einem Cache-Wert ebenso — auch
diese acht. Die Fläche zeigte dort das Standard-Topic (amber), also eine Zusage, die kein Leser einlöst.

**Was die Migration tut:** ein `quellen`-Eintrag mit genau `quelle == mqtt_inbound_standard` an einem `ohne_leser`-Feld wird
`{"quelle": "keine"}` — wie die Wahl „Keine" auf der Fläche (`set_feld_quelle`). Ein solcher Eintrag ist immer ein Stempel:
die Wahl „Inbound" auf der Fläche legt keinen Eintrag an (sie entfernt ihn). Nichts geht verloren — der Wert wurde nie
gelesen. **Gateway-Zeilen bleiben** (vom Anwender angelegt, sichtbar und löschbar; der Riegel in `set_feld_quelle` verhindert
neue). HA-Zuordnungen bleiben. Kein Historie-Vermerk: keine Tages- oder Stundenzahl ändert sich.

Die klassische Struktur (`basis`/`investitionen`, Schreib-Schicht `datenquellen_mapping_sync`) bleibt bewusst unberührt:
Inbound → „Keine" ist ein Wechsel zwischen zwei Nicht-HA-Quellen, dort steht für beide nichts. `uebernehme_quelle_ins_mapping`
mit „Keine" entwertete zudem einen dort liegenden HA-Sensor — den liest der Monatsabschluss-Vorschlag, er muss bleiben.

Idempotent (ein zweiter Lauf findet keinen Stempel mehr), läuft einmal über `_apply_once`. Kein HTTP, nur JSON-Umbau.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.datenquellen_mapping_sync import feld_id
from backend.services.mqtt_topic_registry import build_expected_topics

logger = logging.getLogger(__name__)

QUELLE_INBOUND = "mqtt_inbound_standard"
QUELLE_KEINE = "keine"


async def ohne_leser_inbound_stempel_auf_keine(session: AsyncSession) -> int:
    """Setzt Inbound-Stempel an `ohne_leser`-Feldern auf „Keine"; Rückgabe: Anzahl der umgestellten Felder."""
    umgestellt = 0
    for anlage in (await session.execute(select(Anlage))).scalars().all():
        mapping = dict(anlage.sensor_mapping or {})
        quellen = mapping.get("quellen")
        if not isinstance(quellen, dict) or not quellen:
            continue
        invs = (await session.execute(
            select(Investition).where(Investition.anlage_id == anlage.id)
        )).scalars().all()
        ohne_leser = {
            feld_id(e["match_key"])
            for e in await build_expected_topics(session, anlage, investitionen=list(invs))
            if e.get("ohne_leser")
        }
        neu = dict(quellen)
        for fid in ohne_leser:
            eintrag = neu.get(fid)
            if isinstance(eintrag, dict) and eintrag.get("quelle") == QUELLE_INBOUND:
                neu[fid] = {"quelle": QUELLE_KEINE}
                umgestellt += 1
        if neu != quellen:
            mapping["quellen"] = neu
            anlage.sensor_mapping = mapping
            flag_modified(anlage, "sensor_mapping")

    logger.info("N-780: %d Inbound-Stempel an Feldern ohne Leser auf „Keine“ gesetzt", umgestellt)
    return umgestellt  # _apply_once committet.
