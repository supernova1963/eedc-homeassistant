"""
Repair-Orchestrator (Etappe 3d Päckchen 4).

Vereinheitlicht alle Reparatur-Operationen in einem Plan-/Execute-Modell:

  1. `plan(req, db)` simuliert die Operation und liefert einen RepairPlan
     mit Diff-Vorschau, geschätzten Änderungen und Warnungen — ohne
     etwas zu schreiben.
  2. `execute(plan_id, db)` führt den vorbereiteten Plan aus, schreibt
     in der DB und sammelt die `audit_log_ids` aus `data_provenance_log`
     für den Verlauf-Drilldown.

Der Plan-Lebenszyklus ist in-memory + asyncio.Lock + 1h-Expiry. EEDC
läuft heute single-worker via uvicorn — Multi-Worker würde einen
Plan-Lookup auf einem zweiten Worker zerbrechen (HTTP 404) und müsste
auf einen externen Cache umgestellt werden. Für die Add-on-Realität
heute ist die in-memory-Variante das Richtige.

Konzept: docs/KONZEPT-DATENPIPELINE.md Sektion 5 + 8 Päckchen 4.

Memory-Linien-Kreuzbezüge:
- `feedback_reparatur_statt_loesch_features.md`: Plan-Vorschau ist die
  zentrale UX-Antwort auf "ich will was löschen können". Bevor User
  schreibt, sieht er was geändert wird — und entscheidet dann.
- `feedback_vollbackfill_nur_additiv.md`: VOLLBACKFILL ist additiv, der
  `overwrite`-Pfad existiert hier nicht.
- `feedback_aggregations_drift.md`: Provenance-Schreib-Pfade gehen
  ausschließlich über `services/provenance.py`-Helper, nicht über
  eigene Sub-Logik.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.data_provenance_log import DataProvenanceLog
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.provenance import (
    log_delete,
    write_json_subkey_with_provenance,
    write_with_provenance,
)

logger = logging.getLogger(__name__)


# ── Enum ────────────────────────────────────────────────────────────────────


class RepairOperationType(str, Enum):
    """Welche Reparatur-Operation der Orchestrator ausführt.

    SOLCAST_REWRITE bleibt Stub für Päckchen 6 (Solcast-Doppel-Schreiber
    auflösen). plan() wirft NotImplementedError, sodass Frontend die
    Operation bewusst noch nicht anbietet.
    """
    REAGGREGATE_DAY = "reaggregate_day"
    REAGGREGATE_RANGE = "reaggregate_range"
    REAGGREGATE_TODAY = "reaggregate_today"
    VOLLBACKFILL = "vollbackfill"
    KRAFTSTOFFPREIS_BACKFILL = "kraftstoffpreis_backfill"
    DELETE_MONATSDATEN = "delete_monatsdaten"
    RESET_CLOUD_IMPORT = "reset_cloud_import"
    SOLCAST_REWRITE = "solcast_rewrite"


# Maximaler Zeitbereich für REAGGREGATE_RANGE pro Lauf.
# 31 Tage = ~30-60s je nach mit_resnap, hält uns sicher unter HTTP-Timeouts
# und beschränkt den Datenverlust-Radius bei Abbruch (Netz, Worker-Restart).
# Power-User mit längerem Bedarf rufen das in mehreren Schüben auf — jeder
# Schub gibt sofortiges Feedback statt eines Black-Box-Laufs.
REAGGREGATE_RANGE_MAX_DAYS = 31


# ── Models ──────────────────────────────────────────────────────────────────


class RepairOperationRequest(BaseModel):
    """Plan-Request — operation-spezifische Parameter im `params`-dict.

    `anlage_id` ist optional, weil REAGGREGATE_TODAY eine system-weite
    Operation ist und keine konkrete Anlage adressiert. Alle anderen
    Operationen brauchen anlage_id und schlagen mit ValueError fehl, wenn
    sie fehlt.
    """
    anlage_id: Optional[int] = None
    operation: RepairOperationType
    params: dict[str, Any] = Field(default_factory=dict)


class FieldDiff(BaseModel):
    """Ein einzelner Feld-Diff in der Plan-Vorschau.

    Anwendung: RESET_CLOUD_IMPORT zeigt pro betroffenem Feld den
    Wert-vorher / -nachher und welche Source ihn zuletzt geschrieben
    hat. Andere Operationen liefern operations-spezifische
    Vorschau-Strukturen via `RepairPlan.operation_preview` und können
    `diff_preview` leer lassen.
    """
    table: str
    row_pk: dict[str, Any]
    field: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    source_before: Optional[str] = None
    source_after: str
    decision: Literal["applied", "rejected_lower_priority", "no_op_same_value"]


class RepairPlan(BaseModel):
    """Vorschau einer Reparatur-Operation."""
    plan_id: UUID
    anlage_id: Optional[int] = None
    operation: RepairOperationType
    operation_params: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    estimated_changes: dict[str, int]
    diff_preview: list[FieldDiff] = Field(default_factory=list)
    diff_total_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    operation_preview: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class RepairResult(BaseModel):
    """Ergebnis einer ausgeführten Reparatur-Operation."""
    plan_id: UUID
    anlage_id: Optional[int] = None
    operation: RepairOperationType
    executed_at: datetime
    actual_changes: dict[str, int]
    audit_log_ids: list[int]
    operation_summary: dict[str, Any] = Field(default_factory=dict)


class RepairPlanView(BaseModel):
    """Plan + optional Result (für list_plans-Verlauf)."""
    plan: RepairPlan
    result: Optional[RepairResult] = None


# ── In-Memory Cache ─────────────────────────────────────────────────────────

_PLAN_TTL_SECONDS = 3600
_DIFF_PREVIEW_CAP = 200
_HISTORY_LIMIT = 20

# Plans-Map: dict[plan_id → RepairPlan]
# Results-Map: dict[plan_id → RepairResult] (gefüllt nach execute)
# Multi-worker Hinweis: in-memory Cache funktioniert nur in Single-Worker
# uvicorn (heutiger Add-on-Stand). Ein zweiter Worker würde fremde
# plan_ids als 404 abweisen — bewusst akzeptiert, kein Redis-Detour.
_plans: dict[UUID, RepairPlan] = {}
_results: dict[UUID, RepairResult] = {}
_lock = asyncio.Lock()


def _purge_expired_unlocked() -> None:
    """Entfernt abgelaufene Pläne (Lock muss vom Caller gehalten werden)."""
    now = datetime.now(timezone.utc)
    expired = [pid for pid, plan in _plans.items() if plan.expires_at <= now]
    for pid in expired:
        _plans.pop(pid, None)
        _results.pop(pid, None)


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _audit_id_marker(db: AsyncSession) -> int:
    """Höchste DataProvenanceLog.id vor Execute — alle danach geschriebenen
    Audit-Einträge gehören zur Operation."""
    res = await db.execute(select(func.max(DataProvenanceLog.id)))
    return int(res.scalar() or 0)


async def _audit_ids_since(db: AsyncSession, marker: int) -> list[int]:
    """Audit-IDs seit Marker, in chronologischer Reihenfolge."""
    res = await db.execute(
        select(DataProvenanceLog.id)
        .where(DataProvenanceLog.id > marker)
        .order_by(DataProvenanceLog.id)
    )
    return [int(r) for r in res.scalars().all()]


async def _load_anlage(db: AsyncSession, anlage_id: int) -> Anlage:
    res = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = res.scalar_one_or_none()
    if not anlage:
        raise LookupError(f"Anlage {anlage_id} nicht gefunden")
    return anlage


# ── Operation: REAGGREGATE_DAY ──────────────────────────────────────────────


async def _plan_reaggregate_day(
    req: RepairOperationRequest, db: AsyncSession
) -> tuple[dict[str, int], list[str], dict[str, Any]]:
    """params: {datum: 'YYYY-MM-DD', mit_resnap: bool=True}"""
    from backend.services.sensor_snapshot_service import get_reaggregate_preview

    datum_str = req.params.get("datum")
    if not datum_str:
        raise ValueError("REAGGREGATE_DAY benötigt params.datum (YYYY-MM-DD)")
    datum = date.fromisoformat(datum_str)

    anlage = await _load_anlage(db, req.anlage_id)
    inv_res = await db.execute(
        select(Investition).where(Investition.anlage_id == req.anlage_id)
    )
    invs_by_id = {str(inv.id): inv for inv in inv_res.scalars().all()}

    preview = await get_reaggregate_preview(db, anlage, invs_by_id, datum)

    boundary_changes = sum(
        1 for b in preview["boundaries"]
        if b.get("alt_kwh") != b.get("neu_kwh")
    )
    slot_changes = sum(
        1 for s in preview["slot_deltas"]
        if s.get("alt_kwh") != s.get("neu_kwh")
    )
    counter_changes = sum(
        1 for c in preview.get("counter_tagesdelta", [])
        if c.get("alt") != c.get("neu")
    )

    estimated = {
        "boundaries_changed": boundary_changes,
        "slots_changed": slot_changes,
        "counter_fields_changed": counter_changes,
    }
    warnings: list[str] = []
    if not preview.get("ha_verfuegbar"):
        warnings.append(
            "HA Long-Term Statistics nicht verfügbar — Reaggregation arbeitet "
            "nur auf bestehenden Snapshots, ohne frischen Resnap."
        )
    if boundary_changes == 0 and slot_changes == 0 and counter_changes == 0:
        warnings.append(
            "Vorschau zeigt keine Wert-Änderungen — Aggregat ist konsistent. "
            "Reaggregate würde nichts inhaltlich verändern (nur Provenance-Stempel)."
        )
    return estimated, warnings, {"preview": preview}


async def _execute_reaggregate_day(
    req: RepairOperationRequest, db: AsyncSession
) -> dict[str, Any]:
    from backend.services.energie_profil_service import aggregate_day
    from backend.services.sensor_snapshot_service import resnap_anlage_range

    datum = date.fromisoformat(req.params["datum"])
    mit_resnap = bool(req.params.get("mit_resnap", True))
    anlage = await _load_anlage(db, req.anlage_id)

    if mit_resnap:
        try:
            tag_start = datetime.combine(datum, datetime.min.time())
            von_dt = tag_start - timedelta(hours=1)
            bis_dt = tag_start + timedelta(days=1, hours=1)
            await resnap_anlage_range(
                db, anlage, von=von_dt, bis=bis_dt, include_5min=True,
            )
        except Exception as e:
            logger.warning(
                f"Reaggregate Anlage {req.anlage_id} {datum}: Resnap "
                f"fehlgeschlagen (Aggregat läuft trotzdem): "
                f"{type(e).__name__}: {e}"
            )

    zusammenfassung = await aggregate_day(anlage, datum, db, datenquelle="manuell")
    if zusammenfassung is None:
        raise RuntimeError(
            f"Aggregation für {datum} nicht möglich — keine Live-/MQTT-Daten gefunden."
        )

    return {
        "datum": datum.isoformat(),
        "stunden_verfuegbar": zusammenfassung.stunden_verfuegbar,
    }


# ── Operation: REAGGREGATE_RANGE ────────────────────────────────────────────


async def _plan_reaggregate_range(
    req: RepairOperationRequest, db: AsyncSession
) -> tuple[dict[str, int], list[str], dict[str, Any]]:
    """params: {von: 'YYYY-MM-DD', bis: 'YYYY-MM-DD', mit_resnap: bool=True}

    Hard-Cap REAGGREGATE_RANGE_MAX_DAYS (31). Vorschau zählt vorhandene
    Tageszusammenfassungen im Bereich — Per-Tag-Delta-Preview wäre zu
    teuer und überzeichnet den Knopf-Charakter. Stattdessen liefern wir
    die Liste der Warnungen, damit der UI-Pflicht-Checkbox-Schritt das
    sauber kommunizieren kann.
    """
    von_str = req.params.get("von")
    bis_str = req.params.get("bis")
    if not von_str or not bis_str:
        raise ValueError("REAGGREGATE_RANGE benötigt params.von und params.bis (YYYY-MM-DD)")
    von = date.fromisoformat(von_str)
    bis = date.fromisoformat(bis_str)
    if bis < von:
        raise ValueError(f"bis ({bis}) liegt vor von ({von})")
    if bis >= date.today():
        raise ValueError(
            f"bis ({bis}) muss vor heute liegen — laufender Tag ist Snapshot-instabil"
        )
    anzahl_tage = (bis - von).days + 1
    if anzahl_tage > REAGGREGATE_RANGE_MAX_DAYS:
        raise ValueError(
            f"Zeitbereich {anzahl_tage} Tage übersteigt Maximum von "
            f"{REAGGREGATE_RANGE_MAX_DAYS} Tagen pro Lauf. Bitte in mehreren "
            f"Schüben ausführen."
        )

    anlage = await _load_anlage(db, req.anlage_id)

    vorhandene = await db.scalar(
        select(func.count(TagesZusammenfassung.id)).where(
            TagesZusammenfassung.anlage_id == anlage.id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum <= bis,
        )
    ) or 0

    estimated = {
        "anzahl_tage": anzahl_tage,
        "tage_mit_bestehender_zusammenfassung": int(vorhandene),
    }

    warnings = [
        "Mehrere Tage werden seriell neu aggregiert. Pro Tag erfolgt ein "
        "DB-Commit — bei Abbruch sind die bereits verarbeiteten Tage drin.",
        "Per-Feld-Provenance älterer Verfahrensläufe wird überschrieben "
        "(neue Quelle: 'energieprofil:manuell').",
        "MQTT-Only-Felder ohne HA-LTS-Pendant gehen verloren, falls vorhanden.",
        "Strompreis-Sensor-Daten (Tibber etc.) ohne HA-LTS-Erfassung gehen "
        "verloren, falls vorhanden.",
        "Prognose-Felder (PV/SFML/Solcast) und Day-Ahead-Stundenprofile "
        "(Korrekturprofil-Datenbasis) bleiben erhalten — der "
        "preserved_prognose-Mechanismus greift pro Tag.",
        "Ohne Support-Anspruch auf Rekonstruktion überschriebener Felder.",
    ]
    return estimated, warnings, {
        "von": von_str,
        "bis": bis_str,
        "anzahl_tage": anzahl_tage,
    }


async def _execute_reaggregate_range(
    req: RepairOperationRequest, db: AsyncSession
) -> dict[str, Any]:
    """Seriell pro Tag: optional Resnap, dann aggregate_day(manuell), db.commit.

    Per-Tag-Commit bewusst gewählt (statt atomar): bei 31 Tagen und HTTP-
    Timeout-/Worker-Restart-Risiko ist "bereits aggregierte Tage drin"
    deutlich nutzerfreundlicher als ein finales Rollback.
    """
    from backend.services.energie_profil_service import aggregate_day
    from backend.services.sensor_snapshot_service import resnap_anlage_range

    von = date.fromisoformat(req.params["von"])
    bis = date.fromisoformat(req.params["bis"])
    mit_resnap = bool(req.params.get("mit_resnap", True))
    anlage = await _load_anlage(db, req.anlage_id)

    erfolgreich = 0
    keine_daten = 0
    fehlgeschlagen = 0
    fehler_details: list[dict[str, str]] = []

    current = von
    while current <= bis:
        try:
            if mit_resnap:
                try:
                    tag_start = datetime.combine(current, datetime.min.time())
                    von_dt = tag_start - timedelta(hours=1)
                    bis_dt = tag_start + timedelta(days=1, hours=1)
                    await resnap_anlage_range(
                        db, anlage, von=von_dt, bis=bis_dt, include_5min=True,
                    )
                except Exception as e:
                    logger.warning(
                        f"Range-Reaggregate Anlage {anlage.id} {current}: "
                        f"Resnap fehlgeschlagen (Aggregat läuft trotzdem): "
                        f"{type(e).__name__}: {e}"
                    )

            zusammenfassung = await aggregate_day(
                anlage, current, db, datenquelle="manuell"
            )
            if zusammenfassung is None:
                keine_daten += 1
                fehler_details.append({
                    "datum": current.isoformat(),
                    "grund": "keine_daten",
                })
            else:
                erfolgreich += 1
            await db.commit()
        except Exception as e:
            await db.rollback()
            fehlgeschlagen += 1
            fehler_details.append({
                "datum": current.isoformat(),
                "grund": f"{type(e).__name__}: {e}",
            })
            logger.error(
                f"Range-Reaggregate Anlage {anlage.id} {current} fehlgeschlagen: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )

        verarbeitet = erfolgreich + keine_daten + fehlgeschlagen
        gesamt = (bis - von).days + 1
        if verarbeitet % 5 == 0 or verarbeitet == gesamt:
            logger.info(
                f"Range-Reaggregate Anlage {anlage.id}: "
                f"{verarbeitet}/{gesamt} Tage verarbeitet "
                f"(erfolgreich={erfolgreich}, keine_daten={keine_daten}, "
                f"fehlgeschlagen={fehlgeschlagen})"
            )

        current += timedelta(days=1)

    return {
        "von": von.isoformat(),
        "bis": bis.isoformat(),
        "verarbeitet": erfolgreich + keine_daten + fehlgeschlagen,
        "erfolgreich": erfolgreich,
        "keine_daten": keine_daten,
        "fehlgeschlagen": fehlgeschlagen,
        # Cap die Detail-Liste, damit der Response-Body bei vielen Fehlern
        # nicht explodiert. Vollständiges Log steht im Backend-Logger.
        "fehler_details": fehler_details[:20],
    }


# ── Operation: REAGGREGATE_TODAY ────────────────────────────────────────────


async def _plan_reaggregate_today(
    req: RepairOperationRequest, db: AsyncSession
) -> tuple[dict[str, int], list[str], dict[str, Any]]:
    return (
        {"anlagen_geplant": 0},
        ["Triggert sofortige Neu-Aggregation des heutigen Tages für alle Anlagen."],
        {},
    )


async def _execute_reaggregate_today(
    req: RepairOperationRequest, db: AsyncSession
) -> dict[str, Any]:
    from backend.services.energie_profil_service import aggregate_today_all
    results = await aggregate_today_all()
    return {"anlagen": results}


# ── Operation: VOLLBACKFILL ─────────────────────────────────────────────────


async def _plan_vollbackfill(
    req: RepairOperationRequest, db: AsyncSession
) -> tuple[dict[str, int], list[str], dict[str, Any]]:
    """Vollbackfill ist additiv — Memory-Linie feedback_vollbackfill_nur_additiv.md.
    Vorschau-Tiefe ist begrenzt: ohne Pre-Scan über die HA-Statistics-Range
    können wir die echten Lücken nicht zählen, ohne den Backfill quasi
    schon zu fahren. Wir liefern die Range und einen Hinweis.
    """
    von_str = req.params.get("von")
    bis_str = req.params.get("bis")
    von = date.fromisoformat(von_str) if von_str else None
    bis = date.fromisoformat(bis_str) if bis_str else None

    days = None
    if von and bis:
        days = max(0, (bis - von).days + 1)

    estimated = {
        "tage_im_zeitraum": days if days is not None else 0,
    }
    warnings = [
        "Vollbackfill ist additiv: bestehende Tage bleiben unverändert. "
        "Nur fehlende Tage werden aus HA Long-Term Statistics nachgefüllt. "
        "Die genaue Anzahl fehlender Tage ist erst nach Ausführung sichtbar.",
    ]
    if von is None or bis is None:
        warnings.append(
            "von/bis offen — Backend wählt frühestes HA-Statistics-Datum "
            "bzw. gestern als Range-Standard."
        )
    return estimated, warnings, {"von": von_str, "bis": bis_str}


async def _execute_vollbackfill(
    req: RepairOperationRequest, db: AsyncSession
) -> dict[str, Any]:
    from backend.services.energie_profil_service import (
        resolve_and_backfill_from_statistics,
    )

    von = date.fromisoformat(req.params["von"]) if req.params.get("von") else None
    bis = date.fromisoformat(req.params["bis"]) if req.params.get("bis") else None
    anlage = await _load_anlage(db, req.anlage_id)

    backfill = await resolve_and_backfill_from_statistics(anlage, db, von=von, bis=bis)

    if backfill.status == "ha_unavailable":
        raise RuntimeError(backfill.detail)
    if backfill.status in ("no_sensors", "no_valid_sensors", "earliest_unknown", "empty_range"):
        raise ValueError(backfill.detail)

    anlage.vollbackfill_durchgefuehrt = True
    await db.commit()

    return {
        "verarbeitet": backfill.verarbeitet,
        "geschrieben": backfill.geschrieben,
        "uebersprungen_keine_daten": backfill.uebersprungen_keine_daten,
        "uebersprungen_existiert": backfill.uebersprungen_existiert,
        "von": backfill.von.isoformat(),
        "bis": backfill.bis.isoformat(),
    }


# ── Operation: KRAFTSTOFFPREIS_BACKFILL ─────────────────────────────────────


async def _plan_kraftstoffpreis_backfill(
    req: RepairOperationRequest, db: AsyncSession
) -> tuple[dict[str, int], list[str], dict[str, Any]]:
    """params: {scope: 'tages' | 'monats' | 'beides' (Default)}"""
    scope = req.params.get("scope", "beides")
    if scope not in ("tages", "monats", "beides"):
        raise ValueError(f"Ungültiger scope: {scope!r} (erlaubt: tages, monats, beides)")

    anlage = await _load_anlage(db, req.anlage_id)

    tages_offen = await db.scalar(
        select(func.count(TagesZusammenfassung.id)).where(
            TagesZusammenfassung.anlage_id == req.anlage_id,
            TagesZusammenfassung.kraftstoffpreis_euro.is_(None),
        )
    ) or 0
    monats_offen = await db.scalar(
        select(func.count(Monatsdaten.id)).where(
            Monatsdaten.anlage_id == req.anlage_id,
            Monatsdaten.kraftstoffpreis_euro.is_(None),
        )
    ) or 0

    estimated: dict[str, int] = {}
    if scope in ("tages", "beides"):
        estimated["tages_offen"] = int(tages_offen)
    if scope in ("monats", "beides"):
        estimated["monats_offen"] = int(monats_offen)

    warnings = []
    total = sum(estimated.values())
    if total == 0:
        warnings.append("Keine offenen Zeilen ohne Kraftstoffpreis — Operation ist No-Op.")
    return (
        estimated,
        warnings,
        {"scope": scope, "land": anlage.standort_land or "DE"},
    )


async def _execute_kraftstoffpreis_backfill(
    req: RepairOperationRequest, db: AsyncSession
) -> dict[str, Any]:
    from backend.services.kraftstoff_preis_service import (
        backfill_kraftstoffpreise,
        backfill_monatsdaten_kraftstoffpreise,
    )

    scope = req.params.get("scope", "beides")
    anlage = await _load_anlage(db, req.anlage_id)
    land = anlage.standort_land or "DE"

    summary: dict[str, Any] = {"land": land}
    if scope in ("tages", "beides"):
        info = await backfill_kraftstoffpreise(req.anlage_id, land, db)
        summary["tages_aktualisiert"] = info.get("aktualisiert", 0)
        summary["tages_hinweis"] = info.get("hinweis")
        summary["tages_fehler"] = info.get("fehler")
    if scope in ("monats", "beides"):
        info = await backfill_monatsdaten_kraftstoffpreise(req.anlage_id, land, db)
        summary["monats_aktualisiert"] = info.get("aktualisiert", 0)
        summary["monats_hinweis"] = info.get("hinweis")
        summary["monats_fehler"] = info.get("fehler")

    return summary


# ── Operation: DELETE_MONATSDATEN ───────────────────────────────────────────


async def _plan_delete_monatsdaten(
    req: RepairOperationRequest, db: AsyncSession
) -> tuple[dict[str, int], list[str], dict[str, Any]]:
    """params: {monatsdaten_id: int}.

    Hinweis: User-Prompt sagt DELETE_MONATSDATEN bleibt außerhalb der
    Frontend-Werkbank (Single-Click-Aktion mit eigenem UX-Pfad). Plan
    + Execute sind aber implementiert, damit der Orchestrator als
    Audit-Log-/Repair-Pfad-Vereinheitlicher konsistent ist.
    """
    md_id = req.params.get("monatsdaten_id")
    if md_id is None:
        raise ValueError("DELETE_MONATSDATEN benötigt params.monatsdaten_id")

    res = await db.execute(select(Monatsdaten).where(Monatsdaten.id == md_id))
    md = res.scalar_one_or_none()
    if md is None:
        raise LookupError(f"Monatsdaten {md_id} nicht gefunden")
    if md.anlage_id != req.anlage_id:
        raise ValueError(
            f"Monatsdaten {md_id} gehört nicht zu Anlage {req.anlage_id}"
        )

    return (
        {"rows_to_delete": 1},
        [
            f"Monatsdaten-Row {md.jahr}-{md.monat:02d} wird komplett gelöscht. "
            "Aggregate aus dieser Row gehen verloren — Audit-Log behält Spur."
        ],
        {"jahr": md.jahr, "monat": md.monat},
    )


async def _execute_delete_monatsdaten(
    req: RepairOperationRequest, db: AsyncSession
) -> dict[str, Any]:
    md_id = req.params["monatsdaten_id"]
    res = await db.execute(select(Monatsdaten).where(Monatsdaten.id == md_id))
    md = res.scalar_one_or_none()
    if md is None:
        raise LookupError(f"Monatsdaten {md_id} nicht gefunden (zwischenzeitlich gelöscht?)")

    log_delete(
        db, md,
        source="repair",
        writer="repair_orchestrator:delete_monatsdaten",
        decision_reason="repair_orchestrator delete_monatsdaten",
    )
    await db.delete(md)
    await db.commit()
    return {"deleted_id": md_id, "jahr": md.jahr, "monat": md.monat}


# ── Operation: RESET_CLOUD_IMPORT ───────────────────────────────────────────


_CLOUD_PREFIX = "external:cloud_import:"


def _is_cloud_source(source: Optional[str], filter_providers: Optional[list[str]]) -> bool:
    if not source or not source.startswith(_CLOUD_PREFIX):
        return False
    if not filter_providers:
        return True
    provider = source[len(_CLOUD_PREFIX):]
    return provider in filter_providers


def _row_pk_for(obj: Any) -> dict[str, Any]:
    """Natural-Key-PK für FieldDiff.row_pk (analog provenance._NATURAL_KEYS)."""
    if isinstance(obj, Monatsdaten):
        return {"anlage_id": obj.anlage_id, "jahr": obj.jahr, "monat": obj.monat}
    if isinstance(obj, InvestitionMonatsdaten):
        return {"investition_id": obj.investition_id, "jahr": obj.jahr, "monat": obj.monat}
    return {"id": getattr(obj, "id", None)}


async def _scan_cloud_provenance(
    db: AsyncSession, anlage_id: int, filter_providers: Optional[list[str]]
) -> list[FieldDiff]:
    """Scant Monatsdaten + InvestitionMonatsdaten der Anlage und sammelt alle
    Felder mit `external:cloud_import:*`-Provenance.
    """
    diffs: list[FieldDiff] = []

    # Monatsdaten direkt an Anlage
    md_res = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    for md in md_res.scalars().all():
        provenance = md.source_provenance or {}
        for prov_key, entry in provenance.items():
            if not _is_cloud_source(entry.get("source"), filter_providers):
                continue
            old_value, _ = _resolve_field_value(md, prov_key)
            diffs.append(FieldDiff(
                table="monatsdaten",
                row_pk=_row_pk_for(md),
                field=prov_key,
                old_value=old_value,
                new_value=_reset_value_for_field(md, prov_key),
                source_before=entry.get("source"),
                source_after="repair",
                decision="applied",
            ))

    # InvestitionMonatsdaten via Investition.anlage_id
    imd_res = await db.execute(
        select(InvestitionMonatsdaten)
        .join(Investition, InvestitionMonatsdaten.investition_id == Investition.id)
        .where(Investition.anlage_id == anlage_id)
    )
    for imd in imd_res.scalars().all():
        provenance = imd.source_provenance or {}
        for prov_key, entry in provenance.items():
            if not _is_cloud_source(entry.get("source"), filter_providers):
                continue
            old_value, _ = _resolve_field_value(imd, prov_key)
            diffs.append(FieldDiff(
                table="investition_monatsdaten",
                row_pk=_row_pk_for(imd),
                field=prov_key,
                old_value=old_value,
                new_value=_reset_value_for_field(imd, prov_key),
                source_before=entry.get("source"),
                source_after="repair",
                decision="applied",
            ))

    return diffs


def _resolve_field_value(obj: Any, prov_key: str) -> tuple[Any, bool]:
    """Liest aktuellen Wert für einen Provenance-Key.

    `prov_key` ist entweder ein Top-Level-Attribut (z. B. 'einspeisung_kwh')
    oder ein JSON-Sub-Key in 'attr.sub_key'-Notation (z. B.
    'verbrauch_daten.km_gefahren').

    Returns: (value, is_subkey).
    """
    if "." in prov_key:
        json_attr, sub_key = prov_key.split(".", 1)
        json_dict = getattr(obj, json_attr, None) or {}
        return json_dict.get(sub_key), True
    return getattr(obj, prov_key, None), False


def _reset_value_for_field(obj: Any, prov_key: str) -> Any:
    """Bestimmt den Reset-Wert für ein Feld.

    - JSON-Sub-Keys werden auf None gesetzt (None ist im JSON-Dict zulässig).
    - Top-Level Spalten mit nullable=True → None.
    - Top-Level Spalten mit nullable=False → Spalten-Default (z. B. 0 für
      `Monatsdaten.einspeisung_kwh`). Würden wir None schreiben, würde der
      DB-Constraint zuschlagen.
    """
    if "." in prov_key:
        return None
    table = getattr(obj.__class__, "__table__", None)
    if table is None:
        return None
    col = table.columns.get(prov_key)
    if col is None or col.nullable:
        return None
    # Spalten-Default: scalar oder Callable-Default
    if col.default is not None:
        if col.default.is_scalar:
            return col.default.arg
    # Sicherer Fallback für numerische Felder
    return 0


async def _plan_reset_cloud_import(
    req: RepairOperationRequest, db: AsyncSession
) -> tuple[dict[str, int], list[str], dict[str, Any], list[FieldDiff], int]:
    """params: {providers: list[str] | None — None = alle Cloud-Provider}"""
    providers = req.params.get("providers")
    if providers is not None and not isinstance(providers, list):
        raise ValueError("RESET_CLOUD_IMPORT.providers muss list[str] oder None sein")

    diffs = await _scan_cloud_provenance(db, req.anlage_id, providers)

    by_table: dict[str, int] = {}
    for d in diffs:
        by_table[d.table] = by_table.get(d.table, 0) + 1

    estimated = dict(by_table)
    estimated["fields_total"] = len(diffs)

    warnings: list[str] = []
    if not diffs:
        warnings.append(
            "Keine Cloud-Import-Provenance auf den Aggregat-Rows gefunden — "
            "Operation ist No-Op."
        )
    elif len(diffs) > _DIFF_PREVIEW_CAP:
        warnings.append(
            f"{len(diffs)} Felder betroffen — Vorschau zeigt nur die ersten "
            f"{_DIFF_PREVIEW_CAP}. Bei Bestätigung werden ALLE Felder zurückgesetzt."
        )
    warnings.append(
        "Reset durchbricht die Schreib-Hierarchie (force_override). "
        "Werte werden auf NULL gesetzt; Provenance wird auf 'repair' gestempelt. "
        "Cloud-Sync kann später wieder schreiben."
    )

    preview = diffs[:_DIFF_PREVIEW_CAP]
    return (
        estimated,
        warnings,
        {"providers": providers, "providers_filter_active": providers is not None},
        preview,
        len(diffs),
    )


async def _execute_reset_cloud_import(
    req: RepairOperationRequest, db: AsyncSession
) -> dict[str, Any]:
    """Plant erneut + führt aus. Wir nutzen NICHT den im Cache liegenden
    diff_preview, sondern scannen frisch — damit zwischenzeitliche
    Schreib-Aktivität nicht zu Stale-Diff-Schäden führt.
    """
    providers = req.params.get("providers")
    diffs = await _scan_cloud_provenance(db, req.anlage_id, providers)

    # Index für effiziente Mutation: dict[(table, row_pk_tuple)] → ORM-Row
    md_rows: dict[tuple, Monatsdaten] = {}
    imd_rows: dict[tuple, InvestitionMonatsdaten] = {}

    md_res = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == req.anlage_id)
    )
    for md in md_res.scalars().all():
        md_rows[(md.anlage_id, md.jahr, md.monat)] = md

    imd_res = await db.execute(
        select(InvestitionMonatsdaten)
        .join(Investition, InvestitionMonatsdaten.investition_id == Investition.id)
        .where(Investition.anlage_id == req.anlage_id)
    )
    for imd in imd_res.scalars().all():
        imd_rows[(imd.investition_id, imd.jahr, imd.monat)] = imd

    applied = 0
    by_table: dict[str, int] = {}
    writer = "repair_orchestrator:reset_cloud_import"

    for d in diffs:
        if d.table == "monatsdaten":
            pk = (d.row_pk["anlage_id"], d.row_pk["jahr"], d.row_pk["monat"])
            obj = md_rows.get(pk)
        else:
            pk = (d.row_pk["investition_id"], d.row_pk["jahr"], d.row_pk["monat"])
            obj = imd_rows.get(pk)
        if obj is None:
            continue

        reset_value = _reset_value_for_field(obj, d.field)
        if "." in d.field:
            json_attr, sub_key = d.field.split(".", 1)
            res = await write_json_subkey_with_provenance(
                db, obj, json_attr, sub_key, reset_value,
                source="repair", writer=writer, force_override=True,
            )
        else:
            res = await write_with_provenance(
                db, obj, d.field, reset_value,
                source="repair", writer=writer, force_override=True,
            )
        if res.applied:
            applied += 1
            by_table[d.table] = by_table.get(d.table, 0) + 1

    await db.commit()
    return {
        "fields_reset": applied,
        "by_table": by_table,
        "providers": providers,
    }


# ── Operation: SOLCAST_REWRITE (Stub für P6) ────────────────────────────────


async def _plan_solcast_rewrite(
    req: RepairOperationRequest, db: AsyncSession
) -> tuple[dict[str, int], list[str], dict[str, Any]]:
    raise NotImplementedError(
        "SOLCAST_REWRITE ist Päckchen 6 — noch nicht implementiert. "
        "Siehe docs/KONZEPT-DATENPIPELINE.md Sektion 8 Päckchen 6."
    )


# ── Public API ──────────────────────────────────────────────────────────────


async def plan(req: RepairOperationRequest, db: AsyncSession) -> RepairPlan:
    """Erstellt einen RepairPlan im in-memory-Cache und gibt ihn zurück.

    Plan ist 1h gültig, danach automatisch verworfen. Caller persistiert
    die plan_id und ruft execute(plan_id) für die eigentliche Ausführung.
    """
    diff_preview: list[FieldDiff] = []
    diff_total_count = 0

    if req.operation == RepairOperationType.REAGGREGATE_DAY:
        estimated, warnings, op_preview = await _plan_reaggregate_day(req, db)
    elif req.operation == RepairOperationType.REAGGREGATE_RANGE:
        estimated, warnings, op_preview = await _plan_reaggregate_range(req, db)
    elif req.operation == RepairOperationType.REAGGREGATE_TODAY:
        estimated, warnings, op_preview = await _plan_reaggregate_today(req, db)
    elif req.operation == RepairOperationType.VOLLBACKFILL:
        estimated, warnings, op_preview = await _plan_vollbackfill(req, db)
    elif req.operation == RepairOperationType.KRAFTSTOFFPREIS_BACKFILL:
        estimated, warnings, op_preview = await _plan_kraftstoffpreis_backfill(req, db)
    elif req.operation == RepairOperationType.DELETE_MONATSDATEN:
        estimated, warnings, op_preview = await _plan_delete_monatsdaten(req, db)
    elif req.operation == RepairOperationType.RESET_CLOUD_IMPORT:
        estimated, warnings, op_preview, diff_preview, diff_total_count = (
            await _plan_reset_cloud_import(req, db)
        )
    elif req.operation == RepairOperationType.SOLCAST_REWRITE:
        await _plan_solcast_rewrite(req, db)
        # Unreachable wegen NotImplementedError, hilft mypy
        raise NotImplementedError
    else:
        raise ValueError(f"Unbekannte Operation: {req.operation}")

    # tz-aware UTC: Pydantic serialisiert dann mit `+00:00`-Marker, damit
    # Frontend `new Date(iso)` korrekt interpretiert (sonst wird naive UTC
    # als lokale Zeit gerendert, #257 detLAN).
    now = datetime.now(timezone.utc)
    plan_obj = RepairPlan(
        plan_id=uuid.uuid4(),
        anlage_id=req.anlage_id,
        operation=req.operation,
        operation_params=dict(req.params),
        created_at=now,
        expires_at=now + timedelta(seconds=_PLAN_TTL_SECONDS),
        estimated_changes=estimated,
        diff_preview=diff_preview,
        diff_total_count=diff_total_count or len(diff_preview),
        warnings=warnings,
        operation_preview=op_preview,
    )

    async with _lock:
        _purge_expired_unlocked()
        _plans[plan_obj.plan_id] = plan_obj

    logger.info(
        "RepairOrchestrator.plan(): %s anlage=%d plan_id=%s estimated=%s",
        req.operation.value, req.anlage_id, plan_obj.plan_id, estimated,
    )
    return plan_obj


async def execute(plan_id: UUID, db: AsyncSession) -> RepairResult:
    """Führt einen vorbereiteten Plan aus.

    Raises:
        LookupError, wenn plan_id unbekannt oder bereits ausgeführt.
        TimeoutError, wenn Plan abgelaufen ist.
    """
    async with _lock:
        _purge_expired_unlocked()
        plan_obj = _plans.get(plan_id)
        if plan_obj is None:
            raise LookupError(f"Plan {plan_id} nicht gefunden (abgelaufen oder ungültig)")
        if plan_id in _results:
            raise LookupError(f"Plan {plan_id} bereits ausgeführt")
        if plan_obj.expires_at <= datetime.now(timezone.utc):
            raise TimeoutError(f"Plan {plan_id} abgelaufen")

    req = RepairOperationRequest(
        anlage_id=plan_obj.anlage_id,
        operation=plan_obj.operation,
        params=dict(plan_obj.operation_params),
    )

    audit_marker = await _audit_id_marker(db)

    if req.operation == RepairOperationType.REAGGREGATE_DAY:
        summary = await _execute_reaggregate_day(req, db)
    elif req.operation == RepairOperationType.REAGGREGATE_RANGE:
        summary = await _execute_reaggregate_range(req, db)
    elif req.operation == RepairOperationType.REAGGREGATE_TODAY:
        summary = await _execute_reaggregate_today(req, db)
    elif req.operation == RepairOperationType.VOLLBACKFILL:
        summary = await _execute_vollbackfill(req, db)
    elif req.operation == RepairOperationType.KRAFTSTOFFPREIS_BACKFILL:
        summary = await _execute_kraftstoffpreis_backfill(req, db)
    elif req.operation == RepairOperationType.DELETE_MONATSDATEN:
        summary = await _execute_delete_monatsdaten(req, db)
    elif req.operation == RepairOperationType.RESET_CLOUD_IMPORT:
        summary = await _execute_reset_cloud_import(req, db)
    elif req.operation == RepairOperationType.SOLCAST_REWRITE:
        raise NotImplementedError("SOLCAST_REWRITE ist Päckchen 6")
    else:
        raise ValueError(f"Unbekannte Operation: {req.operation}")

    audit_log_ids = await _audit_ids_since(db, audit_marker)

    actual: dict[str, int] = {}
    for k, v in summary.items():
        if isinstance(v, int):
            actual[k] = v
    actual["audit_log_count"] = len(audit_log_ids)

    result = RepairResult(
        plan_id=plan_id,
        anlage_id=plan_obj.anlage_id,
        operation=plan_obj.operation,
        executed_at=datetime.now(timezone.utc),
        actual_changes=actual,
        audit_log_ids=audit_log_ids,
        operation_summary=summary,
    )

    async with _lock:
        _results[plan_id] = result

    logger.info(
        "RepairOrchestrator.execute(): %s anlage=%d plan_id=%s audit_ids=%d actual=%s",
        plan_obj.operation.value, plan_obj.anlage_id, plan_id,
        len(audit_log_ids), actual,
    )
    return result


async def list_plans(anlage_id: int, limit: int = _HISTORY_LIMIT) -> list[RepairPlanView]:
    """Letzte N Pläne (executed + pending) für die Anlage, neueste zuerst."""
    async with _lock:
        _purge_expired_unlocked()
        plans = [
            RepairPlanView(plan=p, result=_results.get(p.plan_id))
            for p in _plans.values()
            if p.anlage_id == anlage_id
        ]
    plans.sort(key=lambda v: v.plan.created_at, reverse=True)
    return plans[:limit]


async def discard_plan(plan_id: UUID) -> None:
    """Verwirft einen offenen Plan. Bereits ausgeführte Pläne behalten ihren
    Result-Eintrag (für Verlauf) — nur Plan + Result werden zusammen entfernt."""
    async with _lock:
        _plans.pop(plan_id, None)
        _results.pop(plan_id, None)


# ── Maintenance ─────────────────────────────────────────────────────────────


async def get_plan(plan_id: UUID) -> Optional[RepairPlan]:
    """Lookup-Helper für Routes-Layer (z. B. Plan-Detail-Endpoint)."""
    async with _lock:
        _purge_expired_unlocked()
        return _plans.get(plan_id)


def _reset_state_for_tests() -> None:
    """Test-Hilfe — leert Cache zwischen Tests."""
    _plans.clear()
    _results.clear()
