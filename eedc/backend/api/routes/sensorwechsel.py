"""Sensorwechsel mit Grund — Routen neben der Quellen-Wahl (Bauplan B-2, §10 Nr. 40; Sitzung 3b).

* ``POST /api/datenquellen/{anlage}/felder/{feld}/zaehler-getauscht/pruefen`` und ``…/zaehler-getauscht`` — der Einstieg
  «Zähler getauscht (gleiche Quelle)» (``services/zuordnung_wechsel/zaehler_getauscht.py``: Weg je Quelle).
* ``GET /api/datenquellen/{anlage}/korrektur-lauf/{lauf}`` — Fortschritt eines Laufs (lesend; «löschen» und «bleiben»).
* ``GET /api/datenquellen/{anlage}/korrektur-laeufe`` — die laufenden Korrektur-Läufe der Anlage (lesend; die Datenquellen-
  Fläche zeigt sie beim Laden, Bauplan §11 Nr. 50 — der Fortschritt übersteht so das Neuladen).
* ``GET /api/datenquellen/{anlage}/wartende-wechsel`` — die Wechsel «bleiben» zwischen zwei HA-Sensoren, die eedc noch nicht
  wie Home Assistant rechnet, je mit dem Grund (U2 Lauf b; lesend — die Fläche zeigt sie, auch nach dem Neuladen).

Die Quellen-Wahl selbst samt Prüf-Route steht in ``datenquellen.py`` (``…/quelle``, ``…/quelle/pruefen``). «Grund nachtragen» an
einem verzeichneten Wechsel (Sitzung B2) und die Korrektur am versetzten Abschnitt (``…/zaehler-versatz``, Sitzung B3a) sind seit
Weg B entfernt.
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
            # Sensorwechsel U2 Lauf c (offener Punkt aus Lauf b, E-13): dieselbe Sprache wie der Dialog («bisherige Werte bleiben»).
            details=(f"{anlage.anlagenname} · {await _feld_label(db, anlage, field_id)}: bisherige Werte bleiben, Tausch am "
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
        "ende": z.get("ende"), "fuellen_offen": korrektur_lauf.fuellen_offen(z),
        # Sensorwechsel U2 Lauf b (a2 E-2): ``ansetzen`` = der Nachlauf eines Wechsels «bleiben» — die Fläche nennt ihn nicht
        # «Korrektur».
        "art": korrektur_lauf.art(z),
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


@router.get("/{anlage_id}/wartende-wechsel")
async def wartende_wechsel(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """Die Wechsel «bleiben» zwischen zwei HA-Sensoren, die eedc noch nicht wie Home Assistant rechnet (``ansatz`` offen):
    ``[{wechsel_id, sensor_key, label, wartet, satz}]`` — dieselbe ``ansatz.lage`` wie der Stundenlauf (lesend)."""
    from backend.api.routes.datenquellen import _anlage_oder_404
    from backend.services.zuordnung_wechsel.bleiben import wartende

    anlage = await _anlage_oder_404(db, anlage_id)
    out = await wartende(db, anlage_id)
    for e in out:
        e["label"] = await _label(db, anlage, e["sensor_key"])
    return out


async def _label(db: AsyncSession, anlage, sensor_key: str) -> str:
    from backend.api.routes.datenquellen import _feld_label
    from backend.services.zuordnung_wechsel.nachtrag import feld_id_aus_schluessel

    fid = feld_id_aus_schluessel(sensor_key)
    return await _feld_label(db, anlage, fid) if fid else sensor_key
