"""
Cloud-Import API Routes.

Ermöglicht den Import von historischen Energiedaten direkt aus
Hersteller-Cloud-APIs (EcoFlow, etc.).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.services.cloud_import import list_providers, get_provider
from backend.services.activity_service import log_activity

logger = logging.getLogger(__name__)

router = APIRouter()


# #261 FrodoVDR: kopierte API-Keys/Site-IDs aus Hersteller-Portalen tragen oft
# unsichtbaren Whitespace mit — SolarEdge etwa antwortet dann mit 403. Frontend
# trimmt schon, dies ist der zweite Schild für den Fall, dass ein anderer
# Client den Endpoint anspricht (gespeicherte Credentials, externes Tooling).
def _trim_credentials(credentials: dict) -> dict:
    return {
        k: v.strip() if isinstance(v, str) else v
        for k, v in (credentials or {}).items()
    }


# Heuristik-Fallback für die Maskierung in GET /credentials/{anlage_id}.
# Greift, wenn der Provider nicht aufgelöst werden kann (entfernt/umbenannt)
# oder ein Provider neue sensible Feld-IDs einführt, ohne `type="password"`
# zu setzen. Pattern werden als Substring im Key-Lower gesucht.
_SENSITIVE_KEY_PATTERNS: tuple[str, ...] = (
    "secret", "password", "token", "api_key", "access_key",
    "private_key", "app_secret", "client_secret", "system_code",
)


def _maskiere_credentials(creds: dict, provider_id: Optional[str]) -> dict:
    """Maskiert sensible Credential-Werte für die Anzeige.

    Strategie (deny-by-default für unbekannte Felder):
      1. Felder mit Provider-Definition `type="password"` werden maskiert.
      2. Zusätzlich Heuristik: Key enthält ein bekanntes sensibles Substring
         (`secret`, `password`, `token`, `api_key`, `access_key`, ...). Greift
         auch, wenn der Provider nicht auflösbar ist (entfernt/umbenannt).
      3. Identifier (`username`, `email`, `site_id`, `region`, ...) bleiben
         lesbar, damit das Frontend die gespeicherte Konfiguration zeigen kann.

    Leere/None-Werte werden ausgelassen.
    """
    password_field_ids: set[str] = set()
    if provider_id:
        try:
            provider = get_provider(provider_id)
            password_field_ids = {
                f.id for f in provider.info().credential_fields if f.type == "password"
            }
        except Exception:
            # Unbekannter/entfernter Provider oder Info-Fehler darf nicht zur
            # Klartext-Antwort führen — Heuristik unten übernimmt dann allein.
            password_field_ids = set()

    masked: dict = {}
    for key, val in (creds or {}).items():
        if val is None or val == "":
            continue
        is_sensitive = (
            key in password_field_ids
            or any(pat in key.lower() for pat in _SENSITIVE_KEY_PATTERNS)
        )
        masked[key] = "***" if is_sensitive else val
    return masked


# ─── Schemas ─────────────────────────────────────────────────────────────────


class CredentialFieldResponse(BaseModel):
    id: str
    label: str
    type: str = "text"
    placeholder: str = ""
    required: bool = True
    options: list[dict] = []


class CloudProviderInfoResponse(BaseModel):
    id: str
    name: str
    hersteller: str
    beschreibung: str
    anleitung: str
    credential_fields: list[CredentialFieldResponse] = []
    getestet: bool = False


class TestConnectionRequest(BaseModel):
    provider_id: str
    credentials: dict


class TestConnectionResponse(BaseModel):
    erfolg: bool
    geraet_name: Optional[str] = None
    geraet_typ: Optional[str] = None
    seriennummer: Optional[str] = None
    verfuegbare_daten: Optional[str] = None
    fehler: Optional[str] = None


class FetchPreviewRequest(BaseModel):
    provider_id: str
    credentials: dict
    start_year: int
    start_month: int
    end_year: int
    end_month: int


class FetchedMonthResponse(BaseModel):
    jahr: int
    monat: int
    pv_erzeugung_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    batterie_ladung_kwh: Optional[float] = None
    batterie_entladung_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    wallbox_ladung_kwh: Optional[float] = None
    wallbox_ladung_pv_kwh: Optional[float] = None
    wallbox_ladevorgaenge: Optional[int] = None
    eauto_km_gefahren: Optional[float] = None


class FetchPreviewResponse(BaseModel):
    provider: CloudProviderInfoResponse
    monate: list[FetchedMonthResponse]
    anzahl_monate: int


class SaveCredentialsRequest(BaseModel):
    provider_id: str
    credentials: dict


class CredentialsResponse(BaseModel):
    provider_id: Optional[str] = None
    credentials: dict = {}
    has_credentials: bool = False


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/providers", response_model=list[CloudProviderInfoResponse])
async def get_providers():
    """Verfügbare Cloud-Import-Provider auflisten."""
    return [p.to_dict() for p in list_providers()]


@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(data: TestConnectionRequest):
    """Verbindung zur Cloud-API testen."""
    try:
        provider = get_provider(data.provider_id)
    except ValueError:
        raise HTTPException(400, f"Unbekannter Provider: {data.provider_id}")

    result = await provider.test_connection(_trim_credentials(data.credentials))
    await log_activity(
        kategorie="cloud_import",
        aktion=f"Cloud-Verbindungstest {data.provider_id}",
        erfolg=result.erfolg,
        details=result.fehler if not result.erfolg else f"Gerät: {result.geraet_name}",
    )
    return TestConnectionResponse(**result.to_dict())


@router.post("/fetch-preview", response_model=FetchPreviewResponse)
async def fetch_preview(data: FetchPreviewRequest):
    """Monatsdaten aus der Cloud-API abrufen (Vorschau, ohne Speichern)."""
    try:
        provider = get_provider(data.provider_id)
    except ValueError:
        raise HTTPException(400, f"Unbekannter Provider: {data.provider_id}")

    # Validierung
    if data.start_month < 1 or data.start_month > 12:
        raise HTTPException(400, "Ungültiger Startmonat")
    if data.end_month < 1 or data.end_month > 12:
        raise HTTPException(400, "Ungültiger Endmonat")
    if (data.start_year, data.start_month) > (data.end_year, data.end_month):
        raise HTTPException(400, "Startzeitraum liegt nach dem Endzeitraum")

    try:
        months = await provider.fetch_monthly_data(
            _trim_credentials(data.credentials),
            data.start_year, data.start_month,
            data.end_year, data.end_month,
        )
    except Exception as e:
        logger.exception("Fehler beim Abrufen der Cloud-Daten")
        raise HTTPException(400, f"Fehler beim Datenabruf: {str(e)}")

    if not months:
        raise HTTPException(400, "Keine Monatsdaten im gewählten Zeitraum gefunden.")

    return FetchPreviewResponse(
        provider=CloudProviderInfoResponse(**provider.info().to_dict()),
        monate=[FetchedMonthResponse(**m.to_dict()) for m in months],
        anzahl_monate=len(months),
    )


@router.post("/save-credentials/{anlage_id}")
async def save_credentials(
    anlage_id: int,
    data: SaveCredentialsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Credentials für Cloud-Import an einer Anlage speichern."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(404, f"Anlage {anlage_id} nicht gefunden.")

    config = anlage.connector_config or {}
    config["cloud_import"] = {
        "provider_id": data.provider_id,
        "credentials": _trim_credentials(data.credentials),
    }
    anlage.connector_config = config
    flag_modified(anlage, "connector_config")
    await db.flush()

    return {"erfolg": True, "message": "Credentials gespeichert."}


@router.get("/credentials/{anlage_id}", response_model=CredentialsResponse)
async def get_credentials(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Gespeicherte Cloud-Import Credentials abrufen (Secrets maskiert)."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(404, f"Anlage {anlage_id} nicht gefunden.")

    config = anlage.connector_config or {}
    cloud_config = config.get("cloud_import", {})

    if not cloud_config:
        return CredentialsResponse(has_credentials=False)

    # Secrets maskieren — Provider-aware (type="password") + Heuristik-Fallback,
    # damit `api_key`, `app_secret`, `access_key_value` etc. nicht mehr im Klartext
    # zurückgegeben werden. Identifier (username/email/site_id/...) bleiben sichtbar.
    provider_id = cloud_config.get("provider_id")
    creds = _maskiere_credentials(cloud_config.get("credentials", {}), provider_id)

    return CredentialsResponse(
        provider_id=provider_id,
        credentials=creds,
        has_credentials=True,
    )


@router.delete("/credentials/{anlage_id}")
async def remove_credentials(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Cloud-Import Credentials entfernen."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(404, f"Anlage {anlage_id} nicht gefunden.")

    config = anlage.connector_config or {}
    if "cloud_import" in config:
        del config["cloud_import"]
        anlage.connector_config = config
        flag_modified(anlage, "connector_config")
        await db.flush()

    return {"erfolg": True, "message": "Credentials entfernt."}
