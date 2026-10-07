"""
Monatsabschluss-Nachlauf (Etappe 3d P3 Refactoring-Tail; zurückgeschnitten HA-Bauform E4f, R-13).

Kapselt die Energie-Profil-Auto-Aggregation, die nach jedem Wizard-Save
im Background-Task läuft (`_post_save_hintergrund`). Die Schritte tragen ihre
Nummern aus Bauplan §9 B1 / Konzept R-13 (Schritt 3 ist entfallen) und laufen in
fester Reihenfolge:

1. **Fehlende Tage nachrechnen** — `backfill_range(..., nur_fehlende=True)` ruft
   `aggregate_day` NUR für Tage des Monats ohne Tageszeile (`TagesZusammenfassung`)
   und nur, solange Home Assistant sie im Verlauf hat (Grenze der
   Recorder-Aufbewahrung, erkannt an derselben Stelle wie N-596: eine Kurve ohne
   Leistungswert ⇒ der Tag wird nicht angelegt). **Ein vorhandener Tag wird nie neu
   gerechnet** — bis E4f schrieb dieser Schritt jeden Tag des Monats neu und damit
   gepurgte Tage leer (#422, N-596). Source `auto:monatsabschluss`.
2. **Monats-Rollup** — `rollup_month()` aggregiert `TagesZusammenfassung`
   in fünf `Monatsdaten`-Top-Level-Felder (Vollzyklen, Spitzen, PR hängen an
   Stundenwerten — bleibt bis S3). Source `auto:monatsabschluss`.
4. **Modus-Split festschreiben** (#263 K-2, S3) — `schreibe_modus_split_monat`
   schreibt die zwei Teilmengen, die Abdeckung und ggf. die abgeleitete Heizwärme;
   deckt die WP-Gruppe den Monat aus den Kanälen, kommt der Split seit E4d aus dem
   abgeleiteten Kanal „Strom je Betriebsart", sonst aus den Stundenzeilen.
   Source `auto:monatsabschluss`.

   ⚠ **Die Reihenfolge ist Bedingung, nicht Geschmack:** auf dem Bestandsweg liest
   Schritt 4 die Stundenzeilen, die Schritt 1 für einen fehlenden Tag gerade erst
   geschrieben hat.

⛔ **Schritt 3 ist mit E4f entfallen — der einmalige Auto-Vollbackfill** (
`resolve_and_backfill_from_statistics` beim ersten Abschluss nach einem Upgrade,
Flag `Anlage.vollbackfill_durchgefuehrt`). Die Historie der Summen kommt aus den
Kanälen (Spiegel-Nachfüllen); Lücken der Tageszeilen füllt weiter die Werkbank
„Lücken aus HA-LTS nachfüllen" auf Knopfdruck. Die Spalte bleibt (Bestand), der
Nachlauf liest sie nicht mehr.

MQTT-Publish, Community-Share und Aktivitätseintrag sind disjunkt zur Auto-Aggregation
und bleiben im Background-Orchestrator (`_post_save_hintergrund` in
`routes/monatsabschluss.py`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.services.energie_profil import (
    backfill_range,
    rollup_month,
)
from backend.services.energie_profil.modus_split_schreiben import (
    schreibe_modus_split_monat,
)

logger = logging.getLogger(__name__)


@dataclass
class MonatsabschlussAggregationResult:
    """Ergebnis-Bundle der Auto-Aggregation (Diagnose-/Telemetrie-Zwecke)."""
    #: Zahl der neu angelegten (vorher fehlenden) Tage.
    backfill_count: int = 0
    rollup_ok: bool = False
    #: #263 K-2 (S3): Geräte, für die eine Modus-Aufteilung geschrieben wurde.
    modus_split_geschrieben: int = 0
    #: Geräte, deren Aufteilung der Teilmengen-Invariante widersprach und
    #: deshalb NICHT geschrieben wurde (s. `modus_split_schreiben`).
    modus_split_widerspruch: int = 0


async def run_post_monatsabschluss_aggregation(
    anlage: Anlage,
    jahr: int,
    monat: int,
    db: AsyncSession,
) -> MonatsabschlussAggregationResult:
    """
    Auto-Aggregations-Pipeline nach Monatsabschluss-Wizard-Save.

    Schritt 1+2 in einem Try-Block (Rollup nur wenn Schritt 1 nicht crasht),
    Schritt 4 im eigenen. Seit E4f rechnet Schritt 1 nur fehlende Tage innerhalb der
    Recorder-Aufbewahrung, und es gibt keinen Auto-Vollbackfill mehr (Modul-Kopf).
    """
    erster_tag = date(jahr, monat, 1)
    letzter_tag = (
        date(jahr + 1, 1, 1) - timedelta(days=1) if monat == 12
        else date(jahr, monat + 1, 1) - timedelta(days=1)
    )

    result = MonatsabschlussAggregationResult()

    # 1+2. Fehlende Tage nachrechnen + Monats-Rollup
    try:
        result.backfill_count = await backfill_range(
            anlage, erster_tag, letzter_tag, db, nur_fehlende=True,
        )
        if result.backfill_count > 0:
            await db.commit()
        result.rollup_ok = await rollup_month(anlage.id, jahr, monat, db)
        await db.commit()
    except Exception as e:
        logger.warning(f"Energie-Profil Rollup fehlgeschlagen: {type(e).__name__}: {e}")

    # (3. Auto-Vollbackfill — entfallen mit HA-Bauform E4f, Modul-Kopf.)

    # 4. Modus-Split festschreiben (#263 K-2, S3). Nach Schritt 1, weil er auf
    # dem Bestandsweg dessen Stundenzeilen liest. Eigener Try-Block: eine Anlage
    # ohne Modus-Sensor ist der Normalfall, und ein Fehler hier darf den Rollup
    # nicht nachträglich entwerten.
    try:
        split = await schreibe_modus_split_monat(db, anlage.id, jahr, monat)
        result.modus_split_geschrieben = split.geschrieben
        result.modus_split_widerspruch = len(split.widerspruch)
        if split.geschrieben or split.widerspruch:
            await db.commit()
    except Exception as e:
        logger.warning(f"Modus-Split fehlgeschlagen: {type(e).__name__}: {e}")
        await db.rollback()

    return result
