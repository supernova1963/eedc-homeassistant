"""
Cloud-Import API Routes.

Ermöglicht den Import von historischen Energiedaten direkt aus
Hersteller-Cloud-APIs (EcoFlow, etc.).
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.cloud_import import list_providers, get_provider
from backend.services.cloud_import.quellen import (
    entferne_quelle,
    lade_quellen,
    setze_quelle,
)
from backend.services.erzeuger_ziel import ZielFehler, loese_ziel
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


class FetchStartResponse(BaseModel):
    job_id: str


class FetchStatusResponse(BaseModel):
    # running | done | error
    status: str
    result: Optional[FetchPreviewResponse] = None
    error: Optional[str] = None


class SaveCredentialsRequest(BaseModel):
    provider_id: str
    credentials: dict
    # N-229 (#349): Ein Hersteller-Konto beschreibt oft nur EIN Gerät — Solarman
    # führt je Wechselrichter eine eigene „Station". Ist das Ziel gesetzt, gilt
    # die Quelle für diesen Erzeuger; mehrere Quellen können nebeneinander
    # gespeichert werden. `None` = die Quelle beschreibt die ganze Anlage
    # (bisherige Bedeutung, davon gibt es je Provider genau eine).
    ziel_investition_id: Optional[int] = None
    bezeichnung: Optional[str] = None


class CloudQuelleResponse(BaseModel):
    """Eine gespeicherte Quelle. `schluessel` ist die Adresse zum Löschen."""

    schluessel: str
    provider_id: str
    credentials: dict = {}
    ziel_investition_id: Optional[int] = None
    ziel_bezeichnung: Optional[str] = None
    bezeichnung: Optional[str] = None


class CredentialsResponse(BaseModel):
    # Die drei Alt-Felder beschreiben die ERSTE Quelle und bleiben, damit
    # bestehende Aufrufer nicht brechen. Maßgeblich ist `quellen`.
    provider_id: Optional[str] = None
    credentials: dict = {}
    has_credentials: bool = False
    quellen: list[CloudQuelleResponse] = []


# ─── Async-Fetch-Job-Store ───────────────────────────────────────────────────
# Der Cloud-Abruf kann bei langen Zeiträumen mehrere Minuten dauern (z. B. Anker
# SOLIX: Monate × 3 Datenbereiche × Drosselung). Ein synchroner Request läuft
# dann in Browser/Ingress-Timeouts ("Failed to fetch", #328 Johnny_1993), obwohl
# das Backend weiterläuft. Daher: Abruf als Hintergrund-Job starten und den
# Status pollen. In-Memory + TTL reicht im Single-Worker-Add-on (gleiches Muster
# wie repair_orchestrator); ein Neustart verwirft laufende Jobs (Nutzer startet
# neu). Gilt für ALLE Provider, da an der gemeinsamen Route.

_IMPORT_JOB_TTL_S = 3600  # abgeschlossene/alte Jobs nach 1 h verwerfen


@dataclass
class _ImportJob:
    status: str = "running"  # running | done | error
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    # Referenz auf den Task halten, sonst kann der GC ihn mitten im Lauf einsammeln
    task: object = None


_import_jobs: dict[str, _ImportJob] = {}


def _prune_import_jobs() -> None:
    """Abgelaufene Jobs entfernen (TTL ab Erstellung)."""
    now = time.time()
    for key in [
        k for k, j in _import_jobs.items() if now - j.created_at > _IMPORT_JOB_TTL_S
    ]:
        _import_jobs.pop(key, None)


async def _run_fetch_job(
    job_id: str, provider, data: "FetchPreviewRequest", credentials: dict
) -> None:
    """Hintergrund-Abruf; Ergebnis/Fehler in den Job-Store schreiben."""
    job = _import_jobs.get(job_id)
    if job is None:  # zwischenzeitlich abgelaufen/verworfen
        return
    try:
        months = await provider.fetch_monthly_data(
            credentials,
            data.start_year, data.start_month,
            data.end_year, data.end_month,
        )
        if not months:
            job.status = "error"
            job.error = "Keine Monatsdaten im gewählten Zeitraum gefunden."
            return
        result = FetchPreviewResponse(
            provider=CloudProviderInfoResponse(**provider.info().to_dict()),
            monate=[FetchedMonthResponse(**m.to_dict()) for m in months],
            anzahl_monate=len(months),
        )
        job.result = result.model_dump()
        job.status = "done"
    except Exception as e:
        logger.exception("Fehler beim Abrufen der Cloud-Daten (async-Job)")
        job.status = "error"
        job.error = str(e)


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


def _resolve_provider_and_validate(data: "FetchPreviewRequest"):
    """Provider auflösen + Zeitraum validieren (gemeinsam für sync + async)."""
    try:
        provider = get_provider(data.provider_id)
    except ValueError:
        raise HTTPException(400, f"Unbekannter Provider: {data.provider_id}")
    if data.start_month < 1 or data.start_month > 12:
        raise HTTPException(400, "Ungültiger Startmonat")
    if data.end_month < 1 or data.end_month > 12:
        raise HTTPException(400, "Ungültiger Endmonat")
    if (data.start_year, data.start_month) > (data.end_year, data.end_month):
        raise HTTPException(400, "Startzeitraum liegt nach dem Endzeitraum")
    return provider


@router.post("/fetch-preview", response_model=FetchPreviewResponse)
async def fetch_preview(data: FetchPreviewRequest):
    """Monatsdaten aus der Cloud-API abrufen (Vorschau, ohne Speichern).

    Synchron — für kurze Zeiträume. Lange Zeiträume nutzen `fetch-async`
    (Hintergrund-Job + Polling), um Browser/Ingress-Timeouts zu vermeiden.
    """
    provider = _resolve_provider_and_validate(data)

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


@router.post("/fetch-async", response_model=FetchStartResponse)
async def fetch_async(data: FetchPreviewRequest):
    """Cloud-Abruf als Hintergrund-Job starten — gibt sofort eine job_id zurück.

    Den Fortschritt/das Ergebnis über `GET /fetch-status/{job_id}` pollen.
    Vermeidet "Failed to fetch" bei langen Zeiträumen (#328).
    """
    provider = _resolve_provider_and_validate(data)

    _prune_import_jobs()
    job_id = uuid.uuid4().hex
    _import_jobs[job_id] = _ImportJob()
    task = asyncio.create_task(
        _run_fetch_job(job_id, provider, data, _trim_credentials(data.credentials))
    )
    _import_jobs[job_id].task = task
    return FetchStartResponse(job_id=job_id)


@router.get("/fetch-status/{job_id}", response_model=FetchStatusResponse)
async def fetch_status(job_id: str):
    """Status/Ergebnis eines `fetch-async`-Jobs abrufen."""
    _prune_import_jobs()
    job = _import_jobs.get(job_id)
    if job is None:
        raise HTTPException(
            404, "Import-Job nicht gefunden oder abgelaufen. Bitte erneut starten."
        )
    return FetchStatusResponse(status=job.status, result=job.result, error=job.error)


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

    # Ziel prüfen, BEVOR gespeichert wird — eine Quelle, die auf ein
    # unauflösbares Gerät zeigt, wäre beim nächsten Monatsabruf ein stiller
    # Ausfall statt einer Fehlermeldung an der Stelle, an der man sie versteht.
    ziel_bezeichnung: Optional[str] = None
    if data.ziel_investition_id is not None:
        inv_result = await db.execute(
            select(Investition).where(Investition.anlage_id == anlage_id)
        )
        try:
            ziel = loese_ziel(
                data.ziel_investition_id, inv_result.scalars().all(), anlage_id=anlage_id
            )
        except ZielFehler as e:
            raise HTTPException(e.status_code, str(e))
        ziel_bezeichnung = ziel.bezeichnung

    config = setze_quelle(
        anlage.connector_config,
        provider_id=data.provider_id,
        credentials=_trim_credentials(data.credentials),
        ziel_investition_id=data.ziel_investition_id,
        bezeichnung=data.bezeichnung,
    )
    anlage.connector_config = config
    flag_modified(anlage, "connector_config")
    await db.flush()

    anzahl = len(lade_quellen(config))
    if ziel_bezeichnung:
        message = f"Zugangsdaten für '{ziel_bezeichnung}' gespeichert ({anzahl} Quellen)."
    else:
        message = "Credentials gespeichert."
    return {"erfolg": True, "message": message, "anzahl_quellen": anzahl}


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

    quellen = lade_quellen(anlage.connector_config)
    if not quellen:
        return CredentialsResponse(has_credentials=False)

    # Zielnamen mitliefern, damit die Liste ohne zweiten Abruf lesbar ist.
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    namen = {i.id: (i.bezeichnung or i.typ) for i in inv_result.scalars().all()}

    # Secrets maskieren — Provider-aware (type="password") + Heuristik-Fallback,
    # damit `api_key`, `app_secret`, `access_key_value` etc. nicht mehr im Klartext
    # zurückgegeben werden. Identifier (username/email/site_id/...) bleiben sichtbar.
    ausgabe = [
        CloudQuelleResponse(
            schluessel=q["schluessel"],
            provider_id=q["provider_id"],
            credentials=_maskiere_credentials(q["credentials"], q["provider_id"]),
            ziel_investition_id=q["ziel_investition_id"],
            ziel_bezeichnung=namen.get(q["ziel_investition_id"]),
            bezeichnung=q["bezeichnung"],
        )
        for q in quellen
    ]

    return CredentialsResponse(
        provider_id=ausgabe[0].provider_id,
        credentials=ausgabe[0].credentials,
        has_credentials=True,
        quellen=ausgabe,
    )


@router.delete("/credentials/{anlage_id}")
async def remove_credentials(
    anlage_id: int,
    quelle: Optional[str] = Query(
        None,
        description=(
            "Schlüssel einer einzelnen Quelle (aus GET /credentials). "
            "Ohne Angabe werden ALLE entfernt — das bisherige Verhalten."
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    """Cloud-Import Credentials entfernen — einzeln oder alle."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(404, f"Anlage {anlage_id} nicht gefunden.")

    config, entfernt = entferne_quelle(anlage.connector_config, quelle)
    if quelle is not None and entfernt == 0:
        raise HTTPException(404, f"Keine gespeicherte Quelle '{quelle}' an dieser Anlage.")

    if entfernt:
        anlage.connector_config = config
        flag_modified(anlage, "connector_config")
        await db.flush()

    return {
        "erfolg": True,
        "message": "Credentials entfernt." if entfernt else "Nichts zu entfernen.",
        "entfernt": entfernt,
        "anzahl_quellen": len(lade_quellen(config)),
    }
