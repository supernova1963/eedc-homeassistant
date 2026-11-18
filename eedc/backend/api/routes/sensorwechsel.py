"""Sensorwechsel mit Grund — Routen neben der Quellen-Wahl (Bauplan B-2, §10 Nr. 40; Sitzung 3b).

* ``POST /api/datenquellen/{anlage}/felder/{feld}/zaehler-getauscht/pruefen`` und ``…/zaehler-getauscht`` — der Einstieg
  «Zähler getauscht (gleiche Quelle)» (``services/zuordnung_wechsel/zaehler_getauscht.py``: Weg je Quelle).
* ``GET /api/datenquellen/{anlage}/korrektur-lauf/{lauf}`` — Fortschritt eines Korrektur-Laufs (lesend; Dialog und Werkbank).
* ``GET /api/datenquellen/{anlage}/korrektur-laeufe`` — die laufenden Korrektur-Läufe der Anlage (lesend; die Datenquellen-
  Fläche zeigt sie beim Laden, Bauplan §11 Nr. 50 — der Fortschritt übersteht so das Neuladen).
* ``POST /api/datenquellen/{anlage}/zuordnung-wechsel/{wechsel}/grund/pruefen`` und ``…/grund`` — «Grund nachtragen» an einem
  verzeichneten Wechsel (Sitzung 4, Bauplan B-7; ``services/zuordnung_wechsel/nachtrag.py``): die Prüfung schreibt nichts und
  liefert mit ``grund = korrektur`` und ``falsch_seit`` die Vorschau des Korrektur-Dienstes (Vorschau = Lauf).

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


class GrundNachtragRequest(BaseModel):
    #: ``fortsetzung`` | ``korrektur``; leer = nur prüfen, was nachzutragen ist.
    grund: Optional[str] = None
    #: Nur bei «Korrektur»: erste falsche Stunde (örtliche Zeit).
    falsch_seit: Optional[datetime] = None


async def _nachtrag_lage(db: AsyncSession, anlage_id: int, wechsel_id: int):
    from backend.api.routes.datenquellen import _anlage_oder_404
    from backend.services.zuordnung_wechsel import nachtrag as nt

    anlage = await _anlage_oder_404(db, anlage_id)
    la = await nt.lage(db, anlage, wechsel_id)
    if la is None:
        raise HTTPException(status_code=404, detail="Wechsel nicht gefunden")
    return anlage, la


async def _label(db: AsyncSession, anlage, sensor_key: str) -> str:
    from backend.api.routes.datenquellen import _feld_label
    from backend.services.zuordnung_wechsel.nachtrag import feld_id_aus_schluessel

    fid = feld_id_aus_schluessel(sensor_key)
    return await _feld_label(db, anlage, fid) if fid else sensor_key


def _grund(body: GrundNachtragRequest) -> Optional[str]:
    from backend.services.zuordnung_wechsel.abfrage import GRUENDE

    if body.grund is not None and body.grund not in GRUENDE:
        raise HTTPException(status_code=400, detail=f"Unbekannter Grund: {body.grund}")
    return body.grund


def _falsch_seit(body: GrundNachtragRequest) -> Optional[datetime]:
    t = body.falsch_seit
    if t is not None and t.tzinfo is not None:
        t = t.astimezone().replace(tzinfo=None)
    return t


@router.post("/{anlage_id}/zuordnung-wechsel/{wechsel_id}/grund/pruefen")
async def pruefe_grund_nachtragen(
    anlage_id: int, wechsel_id: int, body: GrundNachtragRequest, db: AsyncSession = Depends(get_db, scope="function"),
):
    """Was an diesem Wechsel nachzutragen ist (schreibt nichts): die Angaben des Dialogs, die zulässigen Gründe und — mit
    ``grund = korrektur`` und ``falsch_seit`` — die Vorschau des Korrektur-Dienstes."""
    from backend.models.zuordnung_wechsel import GRUND_KORREKTUR
    from backend.services.zuordnung_wechsel import nachtrag as nt
    from backend.services.zuordnung_wechsel.abfrage import vorschau_des_auftrags

    grund = _grund(body)
    anlage, la = await _nachtrag_lage(db, anlage_id, wechsel_id)
    korrektur = None
    falsch_seit = _falsch_seit(body)
    if grund == GRUND_KORREKTUR and falsch_seit is not None and GRUND_KORREKTUR in la.gruende:
        try:
            korrektur = await vorschau_des_auftrags(db, nt.korrektur_auftrag(la.row, falsch_seit, datetime.now()),
                                                    nachtrag=True)
        except nt.NachtragAbgelehnt as e:
            raise HTTPException(status_code=422, detail=str(e))
    return nt.antwort(la, await _label(db, anlage, la.row.sensor_key), korrektur)


@router.post("/{anlage_id}/zuordnung-wechsel/{wechsel_id}/grund")
async def grund_nachtragen(
    anlage_id: int, wechsel_id: int, body: GrundNachtragRequest, db: AsyncSession = Depends(get_db, scope="function"),
):
    """Trägt den Grund nach: «Fortsetzung» als Zeile ``herkunft = nachtrag`` (die alte wird aufgehoben, im Kanal der Nachtrag
    der Mitschrift); «Korrektur» über den Korrektur-Dienst (falsch in ``[falsch_seit, Wechsel)``). Antwort wie die Prüfung,
    dazu ``korrektur`` = die gestarteten Läufe (Fortschritt an der Fläche)."""
    from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel import nachtrag as nt
    from backend.services.zuordnung_wechsel.abfrage import SATZ_FALSCH_SEIT_FEHLT

    grund = _grund(body)
    anlage, la = await _nachtrag_lage(db, anlage_id, wechsel_id)
    key = la.row.sensor_key
    label = await _label(db, anlage, key)
    zeit = la.row.erklaert_ts.strftime("%d.%m.%Y %H:%M")
    try:
        nt.pruefe_grund(la, grund)
        if grund == GRUND_FORTSETZUNG:
            await nt.trage_fortsetzung_ein(db, anlage, la.row)
            ergebnis, text = None, f"{anlage.anlagenname} · {label}: Fortsetzung (Wechsel vom {zeit})"
        else:
            falsch_seit = _falsch_seit(body)
            if falsch_seit is None:
                raise nt.NachtragAbgelehnt(SATZ_FALSCH_SEIT_FEHLT.format(feld=label))
            jetzt = datetime.now().replace(microsecond=0)
            svc = kr.ha_dienst(None)
            ergebnis = await kr.fuehre_aus(db, nt.korrektur_auftrag(la.row, falsch_seit, jetzt), ha_svc=svc, jetzt=jetzt)
            s = ergebnis["summary"]
            text = (f"{anlage.anlagenname} · {label}: Korrektur seit {falsch_seit.strftime('%d.%m.%Y %H:%M')} "
                    f"(Wechsel vom {zeit}; {s['zaehlerstaende_geloescht']} Zählerstände verworfen, {s['tage_neu']} Tage "
                    "werden neu gebildet)")
    except (nt.NachtragAbgelehnt, kr.KorrekturNichtStartbar, ValueError) as e:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    await log_activity(kategorie="sensor_mapping", aktion="Grund nachgetragen", details=text, anlage_id=anlage_id, db=db)
    await db.commit()
    laeufe = []
    if ergebnis is not None:
        await kr.nach_dem_commit(ergebnis, ha_svc=svc)
        s = ergebnis["summary"]
        laeufe = [{"lauf": s["lauf"], "sensor_key": key, "label": label, "tage_neu": s["tage_neu"],
                   "zaehlerstaende_geloescht": s["zaehlerstaende_geloescht"]}]
    _anlage, neu = await _nachtrag_lage(db, anlage_id, wechsel_id)
    return {**nt.antwort(neu, label), "eingetragen": True, "korrektur": laeufe}
