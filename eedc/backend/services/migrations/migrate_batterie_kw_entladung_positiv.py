"""Migration: Batterie-Vorzeichen-Vereinheitlichung auf ENTLADUNG positiv.

Hintergrund
-----------
Die Spalte ``TagesEnergieProfil.batterie_kw`` wurde historisch als Bilanz-Netto
``ladung − entladung`` geschrieben (**LADUNG positiv**). Der dokumentierte
Feld-Vertrag und faktisch ALLE Consumer (``tagesbilanz`` →
speicher_ladung/-entladung, ``TagVerlaufChart``/``TagWerteTabelle``,
``EnergieprofilTab``-KPI, ``speicher_wirtschaftlichkeit``, der per-Stunde-
``komponenten[batterie_*]``-JSON-Pfad) erwarten jedoch **ENTLADUNG positiv**
(Quelle). Folge: persistierter Tagesverlauf-Chart zeigte Laden als Erzeugung,
``speicher_ladung``/``-entladung`` waren vertauscht, und die Achse-2-Invariante
meldete einen Dauer-Vorzeichen-Flip.

Fix (Code)
----------
- ``aggregator.py`` schreibt ``batterie_kw`` jetzt über
  ``core.berechnungen.batterie_kw_spalte`` (= ``−batt_netto`` → Entladung positiv).
- ``komponenten_beitraege.py`` (Boundary-Pfad) dreht das Batterie-Vorzeichen
  (``ladung −1 / entladung +1``) → ``komponenten_kwh[batterie_*]`` ebenfalls
  Entladung positiv, in LTS- UND Standalone-Modus gleich.

Strategie (Daten)
-----------------
**Re-Aggregation** statt blindem Spalten-Negieren: nur die Re-Aggregation hält
die Spalte ``batterie_kw`` und das ``komponenten_kwh[batterie_*]`` pro Tag im
Gleichschritt. Ein reines ``UPDATE … = −batterie_kw`` würde die Spalte flippen,
das mode-abhängige ``komponenten_kwh`` aber nicht — und damit eine NEUE
TZ-Komponenten-Drift-Warnung erzeugen. Tage ohne verfügbare Quelldaten bleiben
unverändert (Spalte + komponenten_kwh weiterhin im konsistenten Alt-Zustand →
keine neue Warnung; der sichtbare Alt-Bug bleibt dort bestehen, wird aber nicht
verschlimmert).

Idempotenz
----------
Eintrag ``batterie_kw_entladung_positiv`` in der ``migrations``-Tabelle via
``_apply_once`` — läuft genau einmal pro Installation.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil.aggregator import aggregate_day
from backend.services.energie_profil.source import Source

logger = logging.getLogger(__name__)


async def migrate_batterie_kw_entladung_positiv(session: AsyncSession) -> None:
    """Reaggregiert alle vorhandenen TZ-Tage (bis gestern) für Anlagen mit
    ``sensor_mapping`` und Speicher-Bezug, damit ``batterie_kw`` und
    ``komponenten_kwh[batterie_*]`` auf die kanonische Konvention (Entladung
    positiv) umgeschrieben werden. Der laufende Tag wird vom Aggregator selbst
    gemieden; Anlagen ohne ``sensor_mapping`` werden übersprungen.
    """
    bis = date.today() - timedelta(days=1)

    result = await session.execute(
        select(Anlage.id, Anlage.anlagenname, Anlage.sensor_mapping)
    )
    anlagen_rows = result.all()
    if not anlagen_rows:
        logger.info("Batterie-Vorzeichen-Migration: keine Anlagen gefunden.")
        return

    try:
        from backend.services.activity_service import log_activity
        await log_activity(
            kategorie="migration",
            aktion="Batterie-Vorzeichen-Vereinheitlichung gestartet",
            details=(
                "Historische Tageswerte werden neu aggregiert, damit Batterie-"
                "Lade-/Entlade-Vorzeichen in Chart, Bilanz und Speicher-"
                "Wirtschaftlichkeit einheitlich sind (Entladung positiv). "
                "Während des Laufs können Energieprofil/Cockpit kurzzeitig "
                "inkonsistente Speicher-Werte zeigen."
            ),
        )
    except Exception as e:
        logger.debug(f"Activity-Log (Start) fehlgeschlagen: {e}")

    total_aggregiert = 0
    behandelt = 0
    fehler = 0
    for anlage_id, name, sensor_mapping in anlagen_rows:
        if not sensor_mapping:
            continue
        tage_result = await session.execute(
            select(TagesZusammenfassung.datum).where(
                and_(
                    TagesZusammenfassung.anlage_id == anlage_id,
                    TagesZusammenfassung.datum <= bis,
                )
            ).order_by(TagesZusammenfassung.datum.asc())
        )
        tage = [r[0] for r in tage_result.all()]
        if not tage:
            continue
        behandelt += 1
        anlage_obj = await session.get(Anlage, anlage_id)
        if anlage_obj is None:
            continue

        anzahl_anlage = 0
        for tag in tage:
            try:
                ergebnis = await aggregate_day(
                    anlage_obj, tag, session, source=Source.MONATSABSCHLUSS_BACKFILL,
                )
                # Per-Tag-Commit: Writer-Lock kurz halten (analog #291).
                await session.commit()
                if ergebnis is not None:
                    anzahl_anlage += 1
            except Exception as e:
                logger.warning(
                    f"Batterie-Vorzeichen-Migration Anlage {anlage_id} {tag}: "
                    f"{type(e).__name__}: {e}"
                )
                await session.rollback()
                fehler += 1

        total_aggregiert += anzahl_anlage
        logger.info(
            f"Batterie-Vorzeichen-Migration: Anlage {anlage_id} ({name}) — "
            f"{anzahl_anlage}/{len(tage)} Tage neu aggregiert (bis {bis})"
        )

    if behandelt == 0:
        logger.info(
            "Batterie-Vorzeichen-Migration: keine Anlage mit TZ-Daten — "
            "nichts zu reaggregieren."
        )
        return

    try:
        from backend.services.activity_service import log_activity
        await log_activity(
            kategorie="migration",
            aktion="Batterie-Vorzeichen vereinheitlicht",
            details=(
                f"{behandelt} Anlage(n), {total_aggregiert} Tage neu aggregiert "
                f"({fehler} Fehler). Speicher-Lade-/Entlade-Vorzeichen jetzt "
                "einheitlich (Entladung positiv) in Chart, Bilanz und "
                "Speicher-Wirtschaftlichkeit."
            ),
            erfolg=fehler == 0,
        )
    except Exception as e:
        logger.warning(f"Activity-Log (Ende) fehlgeschlagen: {type(e).__name__}: {e}")
