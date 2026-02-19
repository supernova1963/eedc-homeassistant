"""
EEDC Community API Routes

Endpunkte für die anonyme Datenübertragung an den Community-Server.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models import Anlage
from backend.services.community_service import (
    prepare_community_data,
    get_community_preview,
    COMMUNITY_SERVER_URL,
)

router = APIRouter(prefix="/community", tags=["Community"])


class ShareResponse(BaseModel):
    """Antwort nach erfolgreicher Übertragung."""
    success: bool
    message: str
    anlage_hash: str | None = None
    anzahl_monate: int | None = None
    benchmark: dict | None = None


class PreviewResponse(BaseModel):
    """Vorschau der zu teilenden Daten."""
    vorschau: dict
    anzahl_monate: int
    community_url: str
    bereits_geteilt: bool = False


class DeleteResponse(BaseModel):
    """Antwort nach erfolgreicher Löschung."""
    success: bool
    message: str
    anzahl_geloeschte_monate: int


@router.get("/preview/{anlage_id}", response_model=PreviewResponse)
async def get_share_preview(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt eine Vorschau der Daten zurück, die geteilt werden würden.

    Ermöglicht dem Benutzer zu sehen, welche anonymisierten Daten
    an den Community-Server gesendet werden.
    """
    preview = await get_community_preview(db, anlage_id)

    if not preview:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Prüfen ob bereits geteilt
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    bereits_geteilt = bool(anlage and anlage.community_hash)

    return PreviewResponse(**preview, bereits_geteilt=bereits_geteilt)


@router.post("/share/{anlage_id}", response_model=ShareResponse)
async def share_to_community(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Überträgt anonymisierte Anlagendaten an den Community-Server.

    Die Daten werden anonymisiert:
    - Kein Name, keine Adresse
    - PLZ wird auf Bundesland reduziert
    - Nur aggregierte Monatswerte

    Returns:
        Erfolgsmeldung mit optionalen Benchmark-Daten
    """
    # Daten vorbereiten
    data = await prepare_community_data(db, anlage_id)

    if not data:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    if not data.get("monatswerte"):
        raise HTTPException(
            status_code=400,
            detail="Keine Monatsdaten vorhanden. Bitte zuerst Daten erfassen."
        )

    if data.get("kwp", 0) <= 0:
        raise HTTPException(
            status_code=400,
            detail="Anlagenleistung (kWp) muss größer als 0 sein."
        )

    # An Community-Server senden
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{COMMUNITY_SERVER_URL}/api/submit",
                json=data,
            )

            if response.status_code == 200:
                result = response.json()
                anlage_hash = result.get("anlage_hash")

                # Hash in der Anlage speichern für späteren Delete
                if anlage_hash:
                    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
                    anlage = anlage_result.scalar_one_or_none()
                    if anlage:
                        anlage.community_hash = anlage_hash
                        await db.commit()

                return ShareResponse(
                    success=True,
                    message="Daten erfolgreich geteilt!",
                    anlage_hash=anlage_hash,
                    anzahl_monate=result.get("anzahl_monate"),
                    benchmark=result.get("benchmark"),
                )
            elif response.status_code == 429:
                raise HTTPException(
                    status_code=429,
                    detail="Zu viele Anfragen. Bitte später erneut versuchen."
                )
            elif response.status_code == 400:
                error = response.json().get("detail", "Ungültige Daten")
                raise HTTPException(status_code=400, detail=error)
            else:
                raise HTTPException(
                    status_code=502,
                    detail=f"Community-Server Fehler: {response.status_code}"
                )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Community-Server antwortet nicht. Bitte später erneut versuchen."
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Verbindung zum Community-Server fehlgeschlagen: {str(e)}"
        )


@router.get("/status")
async def get_community_status():
    """
    Prüft ob der Community-Server erreichbar ist.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{COMMUNITY_SERVER_URL}/api/health")

            if response.status_code == 200:
                return {
                    "online": True,
                    "url": COMMUNITY_SERVER_URL,
                    "version": response.json().get("version"),
                }
            else:
                return {
                    "online": False,
                    "url": COMMUNITY_SERVER_URL,
                    "error": f"Status {response.status_code}",
                }

    except Exception as e:
        return {
            "online": False,
            "url": COMMUNITY_SERVER_URL,
            "error": str(e),
        }


@router.delete("/delete/{anlage_id}", response_model=DeleteResponse)
async def delete_from_community(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Löscht die geteilten Daten vom Community-Server.

    Verwendet den gespeicherten Anlage-Hash zur Authentifizierung.
    Nur wer die Daten geteilt hat, kann sie auch löschen.
    """
    # Anlage mit Hash laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    if not anlage.community_hash:
        raise HTTPException(
            status_code=400,
            detail="Diese Anlage wurde noch nicht mit der Community geteilt."
        )

    # Delete-Request an Community-Server senden
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{COMMUNITY_SERVER_URL}/api/submit/{anlage.community_hash}"
            )

            if response.status_code == 200:
                result_data = response.json()

                # Hash aus Anlage entfernen
                anlage.community_hash = None
                await db.commit()

                return DeleteResponse(
                    success=True,
                    message=result_data.get("message", "Daten erfolgreich gelöscht."),
                    anzahl_geloeschte_monate=result_data.get("anzahl_geloeschte_monate", 0),
                )
            elif response.status_code == 404:
                # Daten wurden bereits gelöscht oder existieren nicht mehr
                anlage.community_hash = None
                await db.commit()

                return DeleteResponse(
                    success=True,
                    message="Daten waren bereits gelöscht oder nicht vorhanden.",
                    anzahl_geloeschte_monate=0,
                )
            elif response.status_code == 429:
                raise HTTPException(
                    status_code=429,
                    detail="Zu viele Anfragen. Bitte später erneut versuchen."
                )
            else:
                raise HTTPException(
                    status_code=502,
                    detail=f"Community-Server Fehler: {response.status_code}"
                )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Community-Server antwortet nicht. Bitte später erneut versuchen."
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Verbindung zum Community-Server fehlgeschlagen: {str(e)}"
        )
