"""
Provenance-Helper für Aggregat-Schreib-Pfade (Etappe 3d Päckchen 1).

Single-Source-of-Truth-Funktion: alle Schreiber auf monatsdaten /
investition_monatsdaten / tages_zusammenfassung / tages_energie_profil
gehen ab Päckchen 3 ausschließlich über `write_with_provenance()`.

Verantwortlichkeiten:
1. Hierarchie-Check (SourcePriority) — höhere/gleiche Priorität schreibt,
   niedrigere wird abgewiesen.
2. No-Op-Detection bei identischem Wert + identischem input_hash —
   Re-Imports sehen ihren eigenen vorherigen Apply.
3. JSON-Spalten-Update mit flag_modified() (CLAUDE.md-Pflicht: ohne
   flag_modified persistiert SQLAlchemy JSON-Mutationen NICHT).
4. Append-Only Audit-Log in DataProvenanceLog für Diagnose.

Konzept: docs/KONZEPT-DATENPIPELINE.md Sektion 3.4 + 4.1.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.core.source_priority import SOURCE_LABELS, SourcePriority
from backend.models.data_provenance_log import DataProvenanceLog

logger = logging.getLogger(__name__)


# Natural-Key-Felder pro Aggregat-Tabelle (für row_pk_json im Audit-Log).
# Konzept Sektion 3.3: row_pk_json soll User die Frage „wer hat im Februar
# mein Investitions-Monatsdatum überschrieben?" direkt aus dem Log heraus
# beantwortbar machen — also Natural Key statt Surrogate-id.
_NATURAL_KEYS: dict[str, tuple[str, ...]] = {
    "monatsdaten": ("anlage_id", "jahr", "monat"),
    "investition_monatsdaten": ("investition_id", "jahr", "monat"),
    "tages_zusammenfassung": ("anlage_id", "datum"),
    "tages_energie_profil": ("anlage_id", "datum", "stunde"),
}


Decision = Literal["applied", "rejected_lower_priority", "no_op_same_value"]


@dataclass
class WriteResult:
    """Ergebnis eines write_with_provenance()-Aufrufs."""
    applied: bool
    decision: Decision
    reason: str
    conflicting_source: Optional[str] = None  # gesetzt bei rejected_lower_priority


def _row_pk_json(obj: Any) -> str:
    """Serialisiert die Natural-Key-Felder eines Aggregat-Objekts als JSON.

    Fällt auf `id` zurück, wenn die Tabelle keinen registrierten Natural-Key hat —
    das deckt zukünftige Aggregat-Tabellen ab, ohne den Helper zu zerbrechen.
    """
    table_name = obj.__tablename__
    natural = _NATURAL_KEYS.get(table_name)
    if natural is None:
        return json.dumps({"id": getattr(obj, "id", None)}, default=str)
    return json.dumps(
        {field: getattr(obj, field, None) for field in natural},
        default=str,
    )


def _json_safe(value: Any) -> Optional[str]:
    """JSON-encodet Diff-Werte für die Audit-Log-Spalten old_value/new_value."""
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


async def write_with_provenance(
    db: AsyncSession,
    obj: Any,
    field: str,
    value: Any,
    source: str,
    writer: str,
    input_hash: Optional[str] = None,
    *,
    force_override: bool = False,
) -> WriteResult:
    """Atomarer Aggregat-Write mit Hierarchie-Check, No-Op-Detection,
    JSON-Provenance-Update und Append-Only Audit-Log.

    Args:
        db: AsyncSession (Caller committet — der Helper schreibt nur Audit-Log
            + obj-Mutationen in die Session).
        obj: Aggregat-ORM-Objekt (Monatsdaten | InvestitionMonatsdaten |
            TagesZusammenfassung | TagesEnergieProfil).
        field: Spaltenname auf obj, z. B. "netzbezug_kwh".
        value: Neuer Wert.
        source: Label aus SOURCE_LABELS (z. B. "manual:form",
            "external:cloud_import:fronius_solarweb"). KeyError wenn unbekannt.
        writer: Identität des Schreibers (User-Email, Service-Name,
            Cloud-Account-ID, Operation-ID bei repair).
        input_hash: Optional, für No-Op-Detection bei idempotenten Re-Imports.
        force_override: NUR Repair-Orchestrator. Durchbricht Hierarchie,
            schreibt Source als "repair" — egal was als source-Argument kam.
            decision_reason im Audit-Log dokumentiert die Begründung.

    Returns:
        WriteResult mit decision-Feld:
        - "applied": Wert geschrieben + Provenance + Audit-Log.
        - "rejected_lower_priority": niedrigere Priorität gegen bestehende —
          weder Wert noch Provenance angefasst, Audit-Log dokumentiert die
          Abweisung mit conflicting_source.
        - "no_op_same_value": identischer Wert + identischer input_hash —
          weder Wert noch Provenance angefasst, Audit-Log dokumentiert No-Op.
    """
    # 1. Source-Auflösung. Bei force_override wird die effektive Source auf
    #    "repair" überschrieben — das macht repair-Läufe im Audit-Log auf den
    #    ersten Blick erkennbar.
    if force_override:
        effective_source = "repair"
    else:
        effective_source = source

    # KeyError-Stoppschuss: unbekannte Labels werden nicht stillschweigend
    # akzeptiert (Memory-Linie feedback_silent_except_logs.md).
    new_priority = SOURCE_LABELS[effective_source]

    # 2. Bestehende Provenance lesen (defensiv: kann auf Bestandsdaten None sein).
    provenance: dict[str, Any] = obj.source_provenance or {}
    existing = provenance.get(field)
    old_value = getattr(obj, field, None)

    # 3. Entscheidungsbaum.
    decision: Decision
    decision_reason: str
    conflicting_source: Optional[str] = None

    if force_override:
        # Repair-Operation — durchbricht alles.
        decision = "applied"
        decision_reason = f"force_override (writer={writer})"

    elif existing is None:
        # Initial-Write: noch nie was an dieses Feld geschrieben worden.
        decision = "applied"
        decision_reason = "initial_write"

    else:
        existing_source = existing.get("source", "")
        existing_priority = SOURCE_LABELS.get(existing_source)
        existing_hash = existing.get("input_hash")

        # 3a. No-Op-Detection: gleicher Wert + gleicher Input-Hash heißt
        #     idempotenter Re-Import. Spart sowohl flag_modified als auch
        #     Audit-Log-Spam, dokumentiert aber den Aufruf trotzdem (P2-
        #     Diagnose: „liefert der Cloud-Sync was Neues oder nicht?").
        if (
            input_hash is not None
            and existing_hash == input_hash
            and old_value == value
        ):
            decision = "no_op_same_value"
            decision_reason = f"identical value + input_hash from {effective_source}"
            conflicting_source = existing_source

        # 3b. Höhere oder gleiche Priorität → schreibt. Niedrigere Zahl =
        #     höhere Priorität (siehe SourcePriority IntEnum).
        elif existing_priority is None or new_priority <= existing_priority:
            decision = "applied"
            decision_reason = (
                f"priority {int(new_priority)} {'≤' if new_priority < existing_priority else '='} "
                f"existing {existing_source} ({int(existing_priority)})"
                if existing_priority is not None
                else f"existing source {existing_source!r} unknown to SOURCE_LABELS — applied as fallback"
            )

        # 3c. Niedrigere Priorität → abweisen.
        else:
            decision = "rejected_lower_priority"
            conflicting_source = existing_source
            decision_reason = (
                f"priority {int(new_priority)} > existing {existing_source} "
                f"({int(existing_priority)}) — protected"
            )

    # 4. Mutationen anwenden, wenn applied.
    if decision == "applied":
        setattr(obj, field, value)
        provenance[field] = {
            "source": effective_source,
            "writer": writer,
            "at": datetime.utcnow().isoformat() + "Z",
        }
        if input_hash is not None:
            provenance[field]["input_hash"] = input_hash
        obj.source_provenance = provenance
        # JSON-Falle: ohne flag_modified persistiert SQLAlchemy die Mutation NICHT
        # (CLAUDE.md Code-Patterns).
        flag_modified(obj, "source_provenance")

    # 5. Audit-Log eintragen — auch bei rejected/no_op, das ist der Diagnose-Wert.
    new_value_for_log = value if decision == "applied" else old_value
    log_entry = DataProvenanceLog(
        table_name=obj.__tablename__,
        row_pk_json=_row_pk_json(obj),
        field_name=field,
        source=effective_source,
        writer=writer,
        old_value=_json_safe(old_value),
        new_value=_json_safe(new_value_for_log),
        input_hash=input_hash,
        decision=decision,
        decision_reason=decision_reason,
    )
    db.add(log_entry)

    return WriteResult(
        applied=(decision == "applied"),
        decision=decision,
        reason=decision_reason,
        conflicting_source=conflicting_source,
    )
