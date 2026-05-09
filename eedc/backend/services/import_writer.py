"""
Import-Writer: gemeinsamer Provenance-Wrapper für Cloud + CSV + Portal-Import
+ JSON-Backup + Demo-Data (Etappe 3d Päckchen 2).

Alle Pfade, die `InvestitionMonatsdaten.verbrauch_daten` als JSON-Dict
beschreiben, gehen durch diesen Wrapper. Single Source of Truth für:

1. **Payload-Hash** über canonical JSON: erkennt idempotente Re-Imports
   (gleicher Anbieter liefert gleichen Monat erneut → No-Op statt Audit-
   Spam), kein zusätzlicher DB-Write.
2. **Per-Sub-Key Hierarchie-Anschluss**: ein Cloud-Sync, der versehentlich
   `km_gefahren` mitliefert, das der User manuell pflegt, wird
   blockiert — aber `ladung_kwh` aus demselben Payload landet legitim.
3. **Skip-Verhalten bei `ueberschreiben=False`** wie im Status-quo-Helper
   `_upsert_investition_monatsdaten`: bestehende Sub-Keys werden nicht
   überschrieben, nur fehlende ergänzt. Memory-Linie
   `feedback_release_bundling.md`: kein Verhaltens-Diff für Bestands-
   Anwender außerhalb des Akzeptanz-Versprechens.

Konzept: docs/KONZEPT-DATENPIPELINE.md Sektion 6.2.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.models.investition import InvestitionMonatsdaten
from backend.services.provenance import (
    WriteResult,
    log_payload_noop,
    write_json_subkey_with_provenance,
)

logger = logging.getLogger(__name__)


def payload_hash(payload: dict[str, Any]) -> str:
    """SHA-256 über canonical JSON (sortierte Keys, separators ohne Whitespace).

    Zwei Aufrufe mit identischen Sub-Keys-Werten in unterschiedlicher
    Insert-Reihenfolge liefern denselben Hash — das ist der Witz: Cloud-
    APIs liefern Payloads in beliebiger Reihenfolge, die No-Op-Detection
    soll trotzdem greifen.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class UpsertResult:
    """Aggregiertes Ergebnis eines Upsert-Aufrufs.

    Felder:
        inserted: True bei frischer Row, False bei UPDATE-Pfad.
        no_op_full_payload: True wenn payload_hash dem bestehenden source_hash
            entsprach — keine einzelnen write_json_subkey-Aufrufe gemacht.
        skipped_existing: bei ueberschreiben=False die Sub-Keys, die im
            bestehenden Dict schon einen Wert hatten und deshalb nicht angefasst
            wurden (heutiges Skip-Verhalten).
        field_results: pro tatsächlich durchgegangenem Sub-Key das WriteResult.
    """
    inserted: bool
    no_op_full_payload: bool = False
    skipped_existing: list[str] = field(default_factory=list)
    field_results: dict[str, WriteResult] = field(default_factory=dict)

    @property
    def applied_count(self) -> int:
        return sum(1 for r in self.field_results.values() if r.applied)

    @property
    def rejected_count(self) -> int:
        return sum(
            1 for r in self.field_results.values()
            if r.decision == "rejected_lower_priority"
        )

    @property
    def rejected_fields(self) -> list[str]:
        """Sub-Keys, die durch Hierarchie geschützt waren (für Wizard-Hinweis
        „X von Y Feldern durch manuelle Werte geschützt")."""
        return [
            sub_key for sub_key, r in self.field_results.items()
            if r.decision == "rejected_lower_priority"
        ]

    @property
    def no_op_subkey_count(self) -> int:
        return sum(
            1 for r in self.field_results.values()
            if r.decision == "no_op_same_value"
        )


async def upsert_investition_monatsdaten_with_provenance(
    db: AsyncSession,
    *,
    investition_id: int,
    jahr: int,
    monat: int,
    verbrauch_daten: dict[str, Any],
    source: str,
    writer: str,
    ueberschreiben: bool = False,
) -> UpsertResult:
    """Provenance-Variante des heutigen `_upsert_investition_monatsdaten`.

    Verhaltens-Spezifikation (Konzept Sektion 6.2):

    - **Doppel-Klick mit unverändertem Payload:** war schon idempotent
      (UNIQUE-Constraint), ist jetzt zusätzlich im Audit-Log als
      `no_op_same_value` sichtbar — auf Payload-Ebene EIN Eintrag, nicht
      pro Sub-Key.
    - **`ueberschreiben=True` auf manuell gepflegtem Sub-Key:** war bisher
      destruktiv, wird jetzt durch Hierarchie blockiert. UpsertResult.
      rejected_fields liefert den Wizard-Hinweis.
    - **`ueberschreiben=True` auf Cloud-/CSV-Wert (gleiche Source-Klasse):**
      erlaubt wie heute (Last-Writer-Wins innerhalb gleicher Priorität).
    - **`ueberschreiben=False`:** Status-quo — Sub-Keys, die schon einen
      Wert haben, werden nicht angefasst. Nur fehlende werden ergänzt.

    Args:
        verbrauch_daten: Payload-Dict (z. B.
            {"km_gefahren": 1200, "ladung_kwh": 130}).
        source: SOURCE_LABELS-Eintrag (z. B. "manual:csv_import",
            "external:portal_import"). KeyError wenn unbekannt.
        writer: Identität des Schreibers (User-Email, Cloud-Account-ID, ...).
        ueberschreiben: Wizard-Flag, wirkt wie Status quo aber zusätzlich
            durch Hierarchie gefiltert (Memory-Linie
            `feedback_aggregations_drift.md`).
    """
    if not verbrauch_daten:
        return UpsertResult(inserted=False)

    new_hash = payload_hash(verbrauch_daten)

    existing = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == investition_id,
            InvestitionMonatsdaten.jahr == jahr,
            InvestitionMonatsdaten.monat == monat,
        )
    )).scalar_one_or_none()

    # ─── INSERT-Pfad ─────────────────────────────────────────────────────────
    if existing is None:
        imd = InvestitionMonatsdaten(
            investition_id=investition_id,
            jahr=jahr,
            monat=monat,
            verbrauch_daten={},  # write_json_subkey_with_provenance füllt das
            source_provenance={},
            source_hash=new_hash,
        )
        db.add(imd)
        # flush damit imd.id existiert + die Row in dieser Session sichtbar ist
        await db.flush()

        result = UpsertResult(inserted=True)
        for sub_key, value in verbrauch_daten.items():
            result.field_results[sub_key] = await write_json_subkey_with_provenance(
                db, imd, "verbrauch_daten", sub_key, value,
                source=source, writer=writer, input_hash=new_hash,
            )
        return result

    # ─── UPDATE-Pfad ─────────────────────────────────────────────────────────
    result = UpsertResult(inserted=False)

    # Full-Payload-No-Op: Cloud-Sync schickt denselben Payload erneut.
    # Wir loggen das als ein einzelnes no_op_same_value-Audit-Event auf
    # einem Sentinel-Subkey "__payload__", damit Diagnose („liefert der
    # Cloud-Sync was Neues oder nicht?") beantwortbar ist, OHNE pro
    # Sub-Key spammen zu müssen.
    if existing.source_hash == new_hash:
        result.no_op_full_payload = True
        # EIN Audit-Event auf Payload-Ebene statt pro Sub-Key spammen.
        log_payload_noop(
            db, existing,
            source=source, writer=writer, input_hash=new_hash,
        )
        return result

    existing_dict: dict[str, Any] = existing.verbrauch_daten or {}

    for sub_key, value in verbrauch_daten.items():
        # Status-quo-Skip: bei ueberschreiben=False werden vorhandene
        # Sub-Keys nicht angefasst (auch nicht durch Hierarchie geprüft).
        if not ueberschreiben and sub_key in existing_dict:
            result.skipped_existing.append(sub_key)
            continue

        result.field_results[sub_key] = await write_json_subkey_with_provenance(
            db, existing, "verbrauch_daten", sub_key, value,
            source=source, writer=writer, input_hash=new_hash,
        )

    # source_hash nur aktualisieren, wenn mindestens ein Sub-Key applied wurde
    # (sonst hat sich nichts geändert — Hash würde lügen). Bei vollem skip-Pfad
    # bleibt der alte Hash stehen, was für No-Op-Detection beim nächsten Cloud-
    # Sync wieder relevant werden kann.
    if result.applied_count > 0:
        existing.source_hash = new_hash

    return result
