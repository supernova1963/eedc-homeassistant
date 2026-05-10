"""
Reparatur-Werkbank — Plan + Execute + Verlauf API (Etappe 3d Päckchen 4).

Drei Endpoints für die zentrale Reparatur-Werkbank:

  POST   /api/repair/plan                   → erstellt RepairPlan, gibt
                                              plan_id + Diff-Vorschau zurück
  POST   /api/repair/execute/{plan_id}      → führt vorbereiteten Plan aus,
                                              gibt RepairResult mit
                                              audit_log_ids zurück
  GET    /api/repair/plans?anlage_id=…      → letzte 20 Pläne (executed +
                                              pending) für die Anlage,
                                              neueste zuerst
  DELETE /api/repair/plans/{plan_id}        → verwirft offenen Plan

Konzept: docs/KONZEPT-DATENPIPELINE.md Sektion 5.

Hinweis: Plan-Lebenszyklus ist in-memory + 1h-Expiry (siehe
`services/repair_orchestrator.py`). Plan-Lookup auf einem zweiten
uvicorn-Worker würde 404 — single-worker Add-on-Realität.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.services import repair_orchestrator as orch
from backend.services.repair_orchestrator import (
    RepairOperationRequest,
    RepairPlan,
    RepairPlanView,
    RepairResult,
)

router = APIRouter()


class PlanResponse(BaseModel):
    """Plan-API-Antwort.

    Frontend zeigt diff_preview + warnings + estimated_changes als
    Vorschau. Bei Bestätigung: POST /execute/{plan_id} → RepairResult.
    """
    plan: RepairPlan
    expires_in_seconds: int


@router.post("/plan", response_model=PlanResponse)
async def create_plan(
    req: RepairOperationRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Erstellt einen RepairPlan und liefert die Vorschau zurück.

    Plan ist 1h gültig, danach automatisch verworfen. Caller persistiert
    die plan_id (z. B. im Frontend-State) und ruft `/execute/{plan_id}`
    für die eigentliche Ausführung.
    """
    try:
        plan_obj = await orch.plan(req, db)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))

    expires = int((plan_obj.expires_at - plan_obj.created_at).total_seconds())
    return PlanResponse(plan=plan_obj, expires_in_seconds=expires)


@router.post("/execute/{plan_id}", response_model=RepairResult)
async def execute_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Führt einen vorbereiteten Plan aus.

    HTTP-Status:
      404 — plan_id unbekannt oder bereits ausgeführt
      410 — Plan abgelaufen
      400 — Operation rejected ValueError
      501 — Operation noch nicht implementiert (z. B. SOLCAST_REWRITE)
      500 — sonstige Operations-Fehler
    """
    try:
        result = await orch.execute(plan_id, db)
    except TimeoutError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except RuntimeError as e:
        msg = str(e)
        status = 503 if "ha" in msg.lower() and "unavailable" in msg.lower() else 500
        raise HTTPException(status_code=status, detail=msg)

    return result


class PlansListResponse(BaseModel):
    """Verlauf-API-Antwort."""
    plans: list[RepairPlanView]


@router.get("/plans", response_model=PlansListResponse)
async def list_plans(
    anlage_id: int = Query(..., description="Anlage-ID, deren Verlauf abgefragt wird"),
    limit: int = Query(20, ge=1, le=100, description="Maximal N Plan-Einträge"),
):
    """
    Letzte N Pläne (executed + pending) für die Anlage, neueste zuerst.

    Pro Eintrag: Plan-Vorschau-Snapshot + Result (None wenn noch nicht
    ausgeführt). Nutzt in-memory Cache — Pläne älter als 1h fehlen.
    """
    plans = await orch.list_plans(anlage_id, limit=limit)
    return PlansListResponse(plans=plans)


@router.delete("/plans/{plan_id}")
async def discard(plan_id: UUID):
    """Verwirft einen offenen Plan. Idempotent — unbekannte plan_id ist OK."""
    await orch.discard_plan(plan_id)
    return {"status": "discarded", "plan_id": str(plan_id)}
