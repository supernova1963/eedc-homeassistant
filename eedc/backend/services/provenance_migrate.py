"""
Datenpipeline-Migrationen rund um `source_provenance` (Etappe 3d Päckchen 3).

Idempotenz wird vom Aufrufer (`core/database.py:_run_data_migrations`) über
die `migrations`-Tabelle gesteuert. Zusätzlich sind die Funktionen hier
intern idempotent: Rows mit bereits gesetzter Provenance werden übersprungen,
Doppelaufrufe sind also schadlos auch ohne Migrations-Framework.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Spalten ohne fachlichen Inhalt — Identifier, Audit, Provenance-Metadaten.
_SKIP_COLUMNS = frozenset({
    "id", "anlage_id", "investition_id", "jahr", "monat", "datum", "stunde",
    "created_at", "updated_at", "erstellt_am", "geaendert_am", "geandert_am",
    "source_provenance", "source_hash",
})

# JSON-Spalten, deren Sub-Keys per-Sub-Key Provenance bekommen sollen.
# Top-Level-Marker auf der ganzen JSON-Spalte würde die Per-Sub-Key-Hierarchie
# (`verbrauch_daten.km_gefahren` aus P2) später blockieren.
_JSON_SUBKEY_COLUMNS = frozenset({
    "verbrauch_daten",        # InvestitionMonatsdaten
    "komponenten",            # TagesEnergieProfil
    "komponenten_kwh",        # TagesZusammenfassung
    "komponenten_starts",     # TagesZusammenfassung
})


def _row_initial_provenance_args(row: Any) -> tuple[list[str], dict[str, list[str]]]:
    """Liefert (top_level_fields, json_subkeys) für `seed_provenance`.

    Top-Level: alle Spalten ungleich None und nicht in `_SKIP_COLUMNS`.
    JSON-Sub-Keys: bei Spalten in `_JSON_SUBKEY_COLUMNS` alle Sub-Keys des
    gespeicherten Dicts (None und non-Dict werden ignoriert).
    """
    top_level: list[str] = []
    json_subkeys: dict[str, list[str]] = {}
    for col in row.__table__.columns:
        name = col.name
        if name in _SKIP_COLUMNS:
            continue
        val = getattr(row, name, None)
        if val is None:
            continue
        if name in _JSON_SUBKEY_COLUMNS:
            if isinstance(val, dict) and val:
                json_subkeys[name] = list(val.keys())
            # NICHT zusätzlich als Top-Level — Sub-Keys sind feiner.
            continue
        top_level.append(name)
    return top_level, json_subkeys


async def migrate_3d_p3_initial_provenance_legacy_unknown(
    session: AsyncSession,
) -> dict[str, int]:
    """Etappe 3d P3: Initial-`source_provenance` für alle Bestandsdaten.

    Schreibt `source='legacy:unknown'`, `writer='initial_migration'` auf
    jede Aggregat-Row, deren `source_provenance` heute leer ist. Damit
    weiß der Resolver für Pre-3d-Daten, dass der erste neue Schreiber
    (egal welcher Klasse) sie automatisch schlägt — statt stillschweigend
    wegen `existing=None` zu greifen.

    Pro Row werden alle non-None Top-Level-Spalten markiert plus alle
    Sub-Keys der JSON-Spalten (`verbrauch_daten`, `komponenten`,
    `komponenten_kwh`, `komponenten_starts`).

    Batch-Verarbeitung mit Per-Batch-Commit, damit ein Crash mitten in der
    Migration den Fortschritt nicht verliert (Idempotenz im Code per
    `if existing.source_provenance: continue`).
    """
    from backend.models.investition import InvestitionMonatsdaten
    from backend.models.monatsdaten import Monatsdaten
    from backend.models.tages_energie_profil import (
        TagesEnergieProfil,
        TagesZusammenfassung,
    )
    from backend.services.provenance import seed_provenance

    counts: dict[str, int] = {
        "monatsdaten": 0,
        "investition_monatsdaten": 0,
        "tages_zusammenfassung": 0,
        "tages_energie_profil": 0,
    }
    batch_size = 1000

    for model, key in (
        (Monatsdaten, "monatsdaten"),
        (InvestitionMonatsdaten, "investition_monatsdaten"),
        (TagesZusammenfassung, "tages_zusammenfassung"),
        (TagesEnergieProfil, "tages_energie_profil"),
    ):
        offset = 0
        while True:
            result = await session.execute(
                select(model).order_by(model.id).limit(batch_size).offset(offset)
            )
            batch = list(result.scalars().all())
            if not batch:
                break

            marked_in_batch = 0
            for row in batch:
                if row.source_provenance:
                    continue  # idempotent gegen Wiederholungen

                fields, json_subkeys = _row_initial_provenance_args(row)
                if not fields and not json_subkeys:
                    continue  # leere Row — nichts zu markieren

                seed_provenance(
                    row,
                    source="legacy:unknown",
                    writer="initial_migration",
                    fields=fields,
                    json_subkeys=json_subkeys or None,
                )
                marked_in_batch += 1

            if marked_in_batch:
                await session.commit()
                counts[key] += marked_in_batch

            if len(batch) < batch_size:
                break
            offset += batch_size

    if any(counts.values()):
        logger.info(
            "Etappe 3d P3 Initial-Provenance: "
            f"monatsdaten={counts['monatsdaten']}, "
            f"investition_monatsdaten={counts['investition_monatsdaten']}, "
            f"tages_zusammenfassung={counts['tages_zusammenfassung']}, "
            f"tages_energie_profil={counts['tages_energie_profil']} Rows markiert"
        )
    else:
        logger.info(
            "Etappe 3d P3 Initial-Provenance: keine Rows ohne Provenance gefunden "
            "(frische Installation oder schon migriert)"
        )

    return counts
