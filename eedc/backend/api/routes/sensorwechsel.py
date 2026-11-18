"""Sensorwechsel mit Grund — Routen neben der Quellen-Wahl (Bauplan B-2, §10 Nr. 40; Sitzung 3b).

* ``POST /api/datenquellen/{anlage}/felder/{feld}/zaehler-getauscht/pruefen`` und ``…/zaehler-getauscht`` — der Einstieg
  «Zähler getauscht (gleiche Quelle)» (``services/zuordnung_wechsel/zaehler_getauscht.py``: Weg je Quelle).
* ``GET /api/datenquellen/{anlage}/korrektur-lauf/{lauf}`` — Fortschritt eines Korrektur-Laufs (lesend; Dialog und Werkbank).
* ``GET /api/datenquellen/{anlage}/korrektur-laeufe`` — die laufenden Korrektur-Läufe der Anlage (lesend; die Datenquellen-
  Fläche zeigt sie beim Laden, Bauplan §11 Nr. 50 — der Fortschritt übersteht so das Neuladen).

Die Quellen-Wahl selbst samt Prüf-Route steht in ``datenquellen.py`` (``…/quelle``, ``…/quelle/pruefen``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.services.activity_service import log_activity

router = APIRouter()


class ZaehlerGetauschtRequest(BaseModel):
    #: Zeitpunkt des Tauschs (örtliche Zeit); leer = jetzt.
    getauscht_am: Optional[datetime] = None


def _zeitpunkt(body: ZaehlerGetauschtRequest) -> datetime:
    t = body.getauscht_am or datetime.now()
    if t.tzinfo is not None:
        t = t.astimezone().replace(tzinfo=None)
    if t > datetime.now():
        raise HTTPException(status_code=400, detail="Der Tausch kann nicht in der Zukunft liegen.")
    return t.replace(microsecond=0)


async def _lage(db: AsyncSession, anlage_id: int, field_id: str, body: ZaehlerGetauschtRequest):
    from backend.api.routes.datenquellen import _anlage_oder_404
    from backend.services.snapshot.keys import _energy_field_id_to_sensor_key
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    anlage = await _anlage_oder_404(db, anlage_id)
    return anlage, await zg.lage(db, anlage, _energy_field_id_to_sensor_key(field_id), _zeitpunkt(body))


@router.post("/{anlage_id}/felder/{field_id}/zaehler-getauscht/pruefen")
async def pruefe_zaehler_getauscht(
    anlage_id: int, field_id: str, body: ZaehlerGetauschtRequest, db: AsyncSession = Depends(get_db, scope="function"),
):
    """Was «Zähler getauscht» an diesem Feld täte (schreibt nichts): ``weg``, ``saetze``, ``eintragen``."""
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    _anlage, la = await _lage(db, anlage_id, field_id, body)
    return zg.antwort(la)


@router.post("/{anlage_id}/felder/{field_id}/zaehler-getauscht")
async def zaehler_getauscht(
    anlage_id: int, field_id: str, body: ZaehlerGetauschtRequest, db: AsyncSession = Depends(get_db, scope="function"),
):
    """Trägt den Tausch als Fortsetzung ein (nur Weg ``fortsetzung``; sonst nichts geschrieben, die Antwort sagt den Weg)."""
    from backend.api.routes.datenquellen import _feld_label
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    anlage, la = await _lage(db, anlage_id, field_id, body)
    try:
        row = await zg.trage_ein(db, anlage, la)
    except ValueError:
        # Der Kanal kann den Nachtrag zu dieser Zeit nicht tragen (Bauplan §11 Nr. 44) — Satz statt 500, nichts bleibt stehen.
        await db.rollback()
        raise HTTPException(status_code=422, detail=zg.satz_nicht_moeglich(la))
    if row is not None:
        await log_activity(
            kategorie="sensor_mapping", aktion="Zähler getauscht (gleiche Quelle)",
            details=(f"{anlage.anlagenname} · {await _feld_label(db, anlage, field_id)}: Fortsetzung ab "
                     f"{la.getauscht_am.strftime('%d.%m.%Y %H:%M')}"),
            anlage_id=anlage_id, db=db,
        )
    await db.commit()
    return {**zg.antwort(la), "eingetragen": row is not None}


@router.get("/{anlage_id}/korrektur-lauf/{lauf}")
async def korrektur_lauf_stand(anlage_id: int, lauf: str, db: AsyncSession = Depends(get_db)):
    """Fortschritt eines Korrektur-Laufs (Bauplan §10 Nr. 40): Tage gesamt und erledigt, Fehler je Tag, Nachlauf."""
    from backend.services.zuordnung_wechsel import korrektur_lauf

    z = await korrektur_lauf.stand(db, lauf)
    if z is None or z.get("anlage_id") != anlage_id:
        raise HTTPException(status_code=404, detail="Korrektur-Lauf nicht gefunden")
    f = z.get("fuellen") if isinstance(z.get("fuellen"), dict) else None
    return {
        "lauf": lauf, "sensor_key": z.get("sensor_key"), "status": z.get("status"), "tage": len(z.get("tage") or []),
        "erledigt": int(z.get("erledigt") or 0), "fehler": list(z.get("fehler") or []), "beginn": z.get("beginn"),
        "ende": z.get("ende"), "fuellen_offen": bool(f is not None and not f.get("erledigt")),
    }


@router.get("/{anlage_id}/korrektur-laeufe")
async def korrektur_laeufe(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """Die laufenden Korrektur-Läufe der Anlage (``status = laeuft``, auch ein Lauf, der nur noch auf das Füllen wartet):
    ``[{lauf, sensor_key, label, beginn}]`` — die Datenquellen-Fläche zeigt je Lauf den Fortschritt (Bauplan §11 Nr. 50)."""
    from backend.api.routes.datenquellen import _anlage_oder_404, _feld_labels
    from backend.services.snapshot.keys import _energy_field_id_to_sensor_key
    from backend.services.zuordnung_wechsel import korrektur_lauf

    anlage = await _anlage_oder_404(db, anlage_id)
    laeufe = await korrektur_lauf.laufende_der_anlage(db, anlage_id)
    if not laeufe:
        return []
    labels = {k: label for fid, label in (await _feld_labels(db, anlage)).items()
              if (k := _energy_field_id_to_sensor_key(fid)) is not None}
    return [{**e, "label": labels.get(e["sensor_key"], e["sensor_key"])} for e in laeufe]
