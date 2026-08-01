"""
Stunden-Leistungskurve aus HA Long-Term Statistics — für Tage außerhalb der Historie.

`aggregate_day` braucht neben den kWh-Zählerständen eine Stunden-Leistungskurve;
im Normalfall holt es sie über `live_tagesverlauf_service.get_tagesverlauf` aus der
HA-**Historie**. Die reicht nur so weit zurück, wie der Recorder aufhebt (Default
10 Tage) — für ältere Tage kommt nichts zurück, und `aggregate_day` steigt aus,
BEVOR es die Zähler auch nur anfasst.

Der Vollbackfill hat dafür seit v3.34.2 einen zweiten Weg: die Stunden-Leistungen
gebündelt aus der **Langzeitstatistik** (`get_hourly_sensor_data`), durchgereicht
als `prefetched_tagesverlauf`. Dieses Modul ist genau dieser Weg, aus
`backfill.py` herausgelöst — damit ihn auch die Reparatur-Werkbank nutzen kann.

Auslöser Forum simon42 #89667/72 (dietmar1968): der Daten-Checker prüft 90 Tage
zurück und bot für 39 Lücken einen Reparatur-Knopf an; die Reparatur hing an der
10-Tage-Historie und meldete für alles Ältere „keine Live-/MQTT-Daten gefunden".
Die Werte lagen die ganze Zeit in der Langzeitstatistik — der Checker las sie ja
von dort, um die Lücke überhaupt zu melden.

Bewusst KEIN zweiter Aggregations-Pfad: dieses Modul beschafft nur die Kurve.
Alles Weitere (Boundary-kWh, Komponenten, Peaks, Preise, Counter, Provenance,
Invariante) bleibt in `aggregate_day` — genau ein Top-Level-Schreibpfad
(Audit §6.1, Plan v3.34 E1).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal, Optional

from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage

logger = logging.getLogger(__name__)

# Warum nichts (oder nicht alles) zurückkam. Der Aufrufer entscheidet, was er
# daraus macht — der Backfill zählt, die Reparatur sagt es dem Anwender ins
# Gesicht statt „keine Daten gefunden" zu raten.
LtsGrund = Literal["ok", "keine_live_zuordnung", "ha_nicht_verfuegbar", "keine_daten"]

_GRUND_TEXT: dict[str, str] = {
    "keine_live_zuordnung": (
        "Dieser Anlage ist kein Leistungssensor (W) zugeordnet. Der Tages-Lauf "
        "braucht neben dem Zählerstand die Stunden-Leistungskurve — zuerst unter "
        "Einstellungen → Datenquellen einen Leistungssensor zuordnen."
    ),
    "ha_nicht_verfuegbar": (
        "Die Home-Assistant-Langzeitstatistik ist gerade nicht erreichbar."
    ),
    "keine_daten": (
        "Die Home-Assistant-Langzeitstatistik hat für diesen Zeitraum keine "
        "Werte — eedc reicht nur so weit zurück wie HA selbst."
    ),
}


def grund_text(grund: LtsGrund) -> str:
    """Anwender-Satz zu einem Grund (leer bei „ok")."""
    return _GRUND_TEXT.get(grund, "")


@dataclass
class LtsTagesverlauf:
    """Ergebnis von `lade_tagesverlauf_aus_lts`.

    `tage` enthält NUR Tage mit mindestens einem Stundenwert — ein fehlender Tag
    ist bei `grund == "ok"` eine echte Lücke in HA, kein Fehler des Aufrufs.
    """

    tage: dict[date, dict] = field(default_factory=dict)
    grund: LtsGrund = "ok"


async def lade_tagesverlauf_aus_lts(
    db: AsyncSession,
    anlage: Anlage,
    von: date,
    bis: date,
    nur_tage: Optional[set[date]] = None,
) -> LtsTagesverlauf:
    """
    Baut die Stunden-Leistungskurve je Tag aus HA-LTS.

    Args:
        db: DB-Session
        anlage: Die Anlage (liefert die Live-Sensor-Zuordnung)
        von/bis: Datumsbereich (inklusiv) — EIN gebündelter LTS-Read dafür
        nur_tage: optional die Teilmenge, für die Punkte gebaut werden sollen
            (der Bulk-Read umfasst trotzdem die ganze Range — er kostet
            einmal, das Punkte-Bauen kostet pro Tag). None = alle Tage.

    Returns:
        `LtsTagesverlauf` — `tage` in der Form, die
        `aggregate_day(prefetched_tagesverlauf=…)` erwartet, plus `grund`, warum
        gegebenenfalls nichts kam. Die Unterscheidung ist keine Kosmetik: „du
        hast keinen Leistungssensor zugeordnet" und „HA reicht nicht so weit
        zurück" verlangen verschiedene Handgriffe vom Anwender.
    """
    from backend.models.investition import Investition
    from backend.utils.investition_filter import aktiv_im_zeitraum
    from backend.services.live_sensor_config import (
        baue_investitions_serien,
        extract_live_config,
    )
    from backend.services.ha_statistics_service import get_ha_statistics_service

    # Investitionen laden — alle die im Zeitraum aktiv waren (`aktiv_im_zeitraum`),
    # für den Serien-Aufbau über die Range. Die Per-Tag-Verfeinerung (genau die am
    # jeweiligen Tag aktiven) macht die `ist_aktiv_an`-Filterung unten plus der
    # `aktiv_am_tag`-Inv-Load in `aggregate_day` (Audit §6.4).
    inv_result = await db.execute(
        sa_select(Investition).where(
            Investition.anlage_id == anlage.id,
            aktiv_im_zeitraum(von, bis),
        )
    )
    investitionen: dict[str, Investition] = {
        str(inv.id): inv for inv in inv_result.scalars().all()
    }

    basis_live, inv_live_map, basis_invert, inv_invert_map = extract_live_config(anlage)

    if not basis_live and not inv_live_map:
        logger.info(f"Anlage {anlage.id}: Keine Live-Sensoren konfiguriert, LTS-Tagesverlauf übersprungen")
        return LtsTagesverlauf(grund="keine_live_zuordnung")

    # ── Serien + Entity-Mapping über die geteilte Quelle (Issue #318, M1) ──────
    # Identische Selektion (inkl. Pool-Dedup #227) wie der Live-Pfad
    # (`live_tagesverlauf_service`), damit Scheduler- und LTS-Aggregation
    # desselben Tages deckungsgleiche TEP.komponenten/Peaks liefern. Hier nur die
    # Kern-Felder; Chart-Metadaten sind Live-spezifisch.
    serien_core, serie_entities = baue_investitions_serien(inv_live_map, investitionen)
    serien: list[dict] = [
        {"key": s.key, "inv_id": s.inv_id, "kategorie": s.kategorie,
         "seite": s.seite, "bidirektional": s.bidirektional}
        for s in serien_core
    ]

    # PV Gesamt als Fallback
    has_individual_pv = any(s["kategorie"] == "pv" for s in serien)
    if not has_individual_pv and basis_live.get("pv_gesamt_w"):
        serien.append({"key": "pv_gesamt", "kategorie": "pv", "seite": "quelle", "bidirektional": False})
        serie_entities["pv_gesamt"] = [basis_live["pv_gesamt_w"]]

    # Netz-Konfiguration
    netz_kombi_eid = basis_live.get("netz_kombi_w")
    netz_einspeisung_eid = basis_live.get("einspeisung_w")
    netz_bezug_eid = basis_live.get("netzbezug_w")
    if netz_kombi_eid and not netz_einspeisung_eid and not netz_bezug_eid:
        serien.append({"key": "netz", "kategorie": "netz", "seite": "quelle", "bidirektional": True})
    elif netz_einspeisung_eid or netz_bezug_eid:
        netz_kombi_eid = None
        serien.append({"key": "netz", "kategorie": "netz", "seite": "quelle", "bidirektional": True})

    # ── Alle Entity-IDs sammeln ──────────────────────────────────────────────
    all_entity_ids: set[str] = set(eid for eids in serie_entities.values() for eid in eids)
    if netz_kombi_eid:
        all_entity_ids.add(netz_kombi_eid)
    if netz_bezug_eid:
        all_entity_ids.add(netz_bezug_eid)
    if netz_einspeisung_eid:
        all_entity_ids.add(netz_einspeisung_eid)

    # SoC wird hier NICHT vorgeholt — `aggregate_day` holt die Speicher-SoC-History
    # selbst über `_get_soc_history` (Pfad 1: HA-LTS-Hourly-Mean, dieselbe Quelle
    # wie der Bulk-Read → für historische Tage verfügbar). v3.34.2 Phase B.

    if not all_entity_ids:
        return LtsTagesverlauf(grund="keine_live_zuordnung")

    # ── HA Statistics abfragen (Executor wegen Sync-SQLAlchemy) ─────────────
    ha_service = get_ha_statistics_service()
    if not ha_service.is_available:
        logger.warning(f"Anlage {anlage.id}: HA Statistics nicht verfügbar, LTS-Tagesverlauf übersprungen")
        return LtsTagesverlauf(grund="ha_nicht_verfuegbar")

    hourly_data = await asyncio.to_thread(
        ha_service.get_hourly_sensor_data, list(all_entity_ids), von, bis
    )

    if not hourly_data:
        logger.info(f"Anlage {anlage.id}: Keine Statistics-Daten für {von}–{bis}")
        return LtsTagesverlauf(grund="keine_daten")

    # ── Vorzeichen-Invertierung anwenden (wie apply_invert_to_history) ───────
    invert_eids: set[str] = set()
    for key, should_invert in basis_invert.items():
        if should_invert and key in basis_live:
            invert_eids.add(basis_live[key])
    for inv_id, invert_flags in inv_invert_map.items():
        live = inv_live_map.get(inv_id, {})
        for key, should_invert in invert_flags.items():
            if should_invert and key in live:
                invert_eids.add(live[key])
    for eid in invert_eids:
        if eid in hourly_data:
            for datum_iso in hourly_data[eid]:
                hourly_data[eid][datum_iso] = {
                    h: -v for h, v in hourly_data[eid][datum_iso].items()
                }

    # ── Punkte je Tag bauen ─────────────────────────────────────────────────
    ergebnis: dict[date, dict] = {}
    current = von
    while current <= bis:
        if nur_tage is not None and current not in nur_tage:
            current += timedelta(days=1)
            continue

        datum_iso = current.isoformat()

        # Serien filtern: nur Investitionen, die an diesem Tag aktiv waren.
        # In-Memory-Pendant zum `aktiv_am_tag`-Inv-Load in `aggregate_day`
        # (Audit §6.4) — punkte + Serien-Metadaten bleiben so tag-konsistent.
        tages_serien = [
            s for s in serien
            if s.get("inv_id") is None  # Basis-Serien (PV Gesamt, Netz)
            or investitionen.get(s["inv_id"], None) is None  # Safety
            or investitionen[s["inv_id"]].ist_aktiv_an(current)
        ]

        # punkte (get_tagesverlauf-Form): je Stunde MIT Daten ein werte-Dict
        # {serie_key: kW}. Stunden ohne jeglichen Wert werden ausgelassen —
        # damit bleibt `stunden_verfuegbar` die Zahl der Stunden mit Daten.
        punkte: list[dict] = []
        for h in range(24):
            werte: dict[str, float] = {}

            for serie in tages_serien:
                skey = serie["key"]
                if serie["kategorie"] == "netz":
                    continue  # Netz separat
                entity_ids = serie_entities.get(skey, [])
                serie_sum_kw = 0.0
                has_data = False
                for entity_id in entity_ids:
                    val = hourly_data.get(entity_id, {}).get(datum_iso, {}).get(h)
                    if val is not None:
                        serie_sum_kw += val
                        has_data = True
                if has_data:
                    if serie["bidirektional"]:
                        raw_val = -serie_sum_kw
                    elif serie["seite"] == "senke":
                        raw_val = -abs(serie_sum_kw)
                    else:
                        raw_val = abs(serie_sum_kw)
                    werte[skey] = round(raw_val, 3)

            # Netz (Kombi-Sensor oder getrennt Bezug/Einspeisung)
            bezug_kw = 0.0
            einsp_kw = 0.0
            if netz_kombi_eid:
                val = hourly_data.get(netz_kombi_eid, {}).get(datum_iso, {}).get(h)
                if val is not None:
                    if val >= 0:
                        bezug_kw = val
                    else:
                        einsp_kw = abs(val)
            else:
                if netz_bezug_eid:
                    val = hourly_data.get(netz_bezug_eid, {}).get(datum_iso, {}).get(h)
                    if val is not None:
                        bezug_kw = max(0.0, val)
                if netz_einspeisung_eid:
                    val = hourly_data.get(netz_einspeisung_eid, {}).get(datum_iso, {}).get(h)
                    if val is not None:
                        einsp_kw = max(0.0, val)
            netto_kw = bezug_kw - einsp_kw
            if bezug_kw > 0 or einsp_kw > 0 or abs(netto_kw) > 0.001:
                werte["netz"] = round(netto_kw, 3)

            if werte:
                punkte.append({"zeit": f"{h:02d}:00", "werte": werte})

        if punkte:
            ergebnis[current] = {"serien": tages_serien, "punkte": punkte}

        current += timedelta(days=1)

    return LtsTagesverlauf(tage=ergebnis)
