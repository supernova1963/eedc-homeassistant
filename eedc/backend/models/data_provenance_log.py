"""
Daten-Provenance Audit-Log (Etappe 3d Päckchen 1).

Append-Only-Tabelle für historische Diagnose von Schreib-Entscheidungen:
„Wer hat im Februar mein Investitions-Monatsdatum überschrieben?"

Wird ausschließlich von `backend.services.provenance.write_with_provenance()`
geschrieben. Keine UPDATE/DELETE-Pfade — eine spätere Retention-Policy
(z. B. „älter als 24 Monate → archivieren") ist möglich, selektive Löschung
nicht.

Konzept: docs/KONZEPT-DATENPIPELINE.md Sektion 3.3.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class DataProvenanceLog(Base):
    __tablename__ = "data_provenance_log"
    __table_args__ = (
        Index("idx_provlog_lookup", "table_name", "row_pk_json", "written_at"),
        Index("idx_provlog_audit", "writer", "written_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Welche Tabelle + welche Zeile
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    row_pk_json: Mapped[str] = mapped_column(String(500), nullable=False)
    # JSON-encoded Primary-Key, z. B. {"anlage_id": 1, "jahr": 2026, "monat": 4}.
    # String(500) reicht — Aggregat-PKs sind kurz.

    # Welches Feld
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Source-Hierarchie + Identität des Schreibers
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    # SOURCE_LABELS-Wert aus backend.core.source_priority

    writer: Mapped[str] = mapped_column(String(255), nullable=False)
    # User-Email für `manual:*`, Service-Name für `auto:*`,
    # Provider-Account-ID für `external:cloud_import:*`,
    # Operation-ID für `repair`.

    written_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    # Diff-Daten (JSON-encoded, Text weil keine Längenobergrenze sinnvoll)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Idempotenz-Hash (für Cloud-/CSV-Re-Imports, P2-Lieferung)
    input_hash: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    # Resolver-Entscheidung
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    # "applied" | "rejected_lower_priority" | "no_op_same_value"
    decision_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
