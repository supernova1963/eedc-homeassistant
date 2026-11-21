"""Sensorwechsel mit Grund — Routen neben der Quellen-Wahl (Bauplan B-2, §10 Nr. 40; Sitzung 3b).

* ``POST /api/datenquellen/{anlage}/felder/{feld}/zaehler-getauscht/pruefen`` und ``…/zaehler-getauscht`` — der Einstieg
  «Zähler getauscht (gleiche Quelle)» (``services/zuordnung_wechsel/zaehler_getauscht.py``: Weg je Quelle).
* ``GET /api/datenquellen/{anlage}/korrektur-lauf/{lauf}`` — Fortschritt eines Korrektur-Laufs (lesend; Dialog und Werkbank).
* ``GET /api/datenquellen/{anlage}/korrektur-laeufe`` — die laufenden Korrektur-Läufe der Anlage (lesend; die Datenquellen-
  Fläche zeigt sie beim Laden, Bauplan §11 Nr. 50 — der Fortschritt übersteht so das Neuladen).
* ``GET /api/datenquellen/{anlage}/wartende-wechsel`` — die Wechsel «bleiben» zwischen zwei HA-Sensoren, die eedc noch nicht
  wie Home Assistant rechnet, je mit dem Grund (U2 Lauf b; lesend — die Fläche zeigt sie, auch nach dem Neuladen).
* ``POST /api/datenquellen/{anlage}/zaehler-versatz/pruefen`` und ``…/zaehler-versatz`` — «Grund nachtragen» am Befund
  «Zählerstände – versetzter Abschnitt» (Sitzung 4b-1, Bauplan «Zu §14» Nr. 98; ``services/zuordnung_wechsel/stueck.py``):
  Schlüssel, Sprung und Rückgang aus ``werte`` des Befunds, serverseitig gegen die Erkennung geprüft (kein frei wählbares
  Stück); «Korrektur» über das Stück, an einer MQTT-Reihe auch «Bisherige Werte bleiben» = je ein Eintrag «Zähler getauscht»
  am Sprung und am Rückgang (U3 b, Rechenweg G7). Die Prüfung schreibt nichts (Vorschau = Lauf).

Die Quellen-Wahl selbst samt Prüf-Route steht in ``datenquellen.py`` (``…/quelle``, ``…/quelle/pruefen``). «Grund nachtragen» an
einem verzeichneten Wechsel (``…/zuordnung-wechsel/{wechsel}/grund``) ist seit Weg B entfernt (Sitzung B2).
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


def _grund(grund: Optional[str]) -> Optional[str]:
    from backend.services.zuordnung_wechsel.nachtrag import GRUENDE_NACHTRAG

    if grund is not None and grund not in GRUENDE_NACHTRAG:
        raise HTTPException(status_code=400, detail=f"Unbekannter Grund: {grund}")
    return grund


class StueckRequest(BaseModel):
    #: Schlüssel, Sprung und Rückgang aus ``werte`` des Befunds ``zaehler_versatz`` (örtliche Zeit, auf die Minute).
    sensor_key: str
    sprung: datetime
    rueckgang: datetime
    #: ``korrektur`` (an einer MQTT-Reihe auch ``fortsetzung``); leer = nur prüfen, was nachzutragen ist.
    grund: Optional[str] = None


def _ortszeit(t: datetime) -> datetime:
    return t.astimezone().replace(tzinfo=None) if t.tzinfo is not None else t


async def _stueck_lage(db: AsyncSession, anlage_id: int, body: StueckRequest):
    from backend.api.routes.datenquellen import _anlage_oder_404
    from backend.services.zuordnung_wechsel import stueck as st

    anlage = await _anlage_oder_404(db, anlage_id)
    la = await st.lage_am_befund(db, anlage, body.sensor_key, _ortszeit(body.sprung), _ortszeit(body.rueckgang))
    if la is None:
        raise HTTPException(status_code=404, detail=st.SATZ_NICHT_GEMELDET)
    return anlage, la


def _feld_id(sensor_key: str):
    from backend.services.zuordnung_wechsel.nachtrag import feld_id_aus_schluessel

    return feld_id_aus_schluessel(sensor_key)


@router.post("/{anlage_id}/zaehler-versatz/pruefen")
async def pruefe_stueck(anlage_id: int, body: StueckRequest, db: AsyncSession = Depends(get_db, scope="function")):
    """Was «Grund nachtragen» an diesem Stück täte (schreibt nichts): die Angaben des Dialogs und — mit ``grund =
    korrektur`` — die Vorschau des Korrektur-Dienstes über das Stück (Vorschau = Lauf)."""
    from backend.models.zuordnung_wechsel import GRUND_KORREKTUR
    from backend.services.zuordnung_wechsel import stueck as st
    from backend.services.zuordnung_wechsel.abfrage import vorschau_des_auftrags

    grund = _grund(body.grund)
    anlage, la = await _stueck_lage(db, anlage_id, body)
    korrektur = None
    if grund == GRUND_KORREKTUR and la.korrektur_nicht is None:
        korrektur = await vorschau_des_auftrags(db, la.auftrag(anlage_id, datetime.now()), nachtrag=True)
    return st.antwort(la, await _label(db, anlage, la.sensor_key), _feld_id(la.sensor_key), korrektur)


@router.post("/{anlage_id}/zaehler-versatz")
async def stueck_korrigieren(anlage_id: int, body: StueckRequest, db: AsyncSession = Depends(get_db, scope="function")):
    """Trägt «Korrektur» über das Stück ein (Korrektur-Dienst mit ``stueck``: füllbar ⇒ aus der Quelle davor und danach neu
    gelesen, sonst eine Lücke). Antwort wie die Prüfung, dazu ``korrektur`` = der gestartete Lauf (Fortschritt an der Fläche)."""
    from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG, GRUND_KORREKTUR
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel import stueck as st
    from backend.services.zuordnung_wechsel.nachtrag import SATZ_GRUND_FEHLT, SATZ_NUR_KORREKTUR_STUECK

    grund = _grund(body.grund)
    anlage, la = await _stueck_lage(db, anlage_id, body)
    label = await _label(db, anlage, la.sensor_key)
    if la.mqtt and grund == GRUND_FORTSETZUNG and not la.korrektur_nicht:
        return await _stueck_bleiben(db, anlage, la, label)
    try:
        if la.korrektur_nicht:
            raise ValueError(la.korrektur_nicht)
        if grund != GRUND_KORREKTUR:
            raise ValueError(SATZ_GRUND_FEHLT if grund is None else SATZ_NUR_KORREKTUR_STUECK)
        jetzt = datetime.now().replace(microsecond=0)
        svc = kr.ha_dienst(None)
        ergebnis = await kr.fuehre_aus(db, la.auftrag(anlage_id, jetzt), ha_svc=svc, jetzt=jetzt)
    except (kr.KorrekturNichtStartbar, ValueError) as e:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    s = ergebnis["summary"]
    await log_activity(
        kategorie="sensor_mapping", aktion="Grund nachgetragen",
        details=(f"{anlage.anlagenname} · {label}: Korrektur des versetzten Abschnitts vom "
                 f"{la.sprung.strftime('%d.%m.%Y %H:%M')} bis {la.rueckgang.strftime('%d.%m.%Y %H:%M')} "
                 f"({s['zaehlerstaende_geloescht']} Zählerstände verworfen, {s['tage_neu']} Tage werden neu gebildet)"),
        anlage_id=anlage_id, db=db,
    )
    await db.commit()
    await kr.nach_dem_commit(ergebnis, ha_svc=svc)
    laeufe = [{"lauf": s["lauf"], "sensor_key": la.sensor_key, "label": label, "tage_neu": s["tage_neu"],
               "zaehlerstaende_geloescht": s["zaehlerstaende_geloescht"]}]
    return {**st.antwort(la, label, _feld_id(la.sensor_key)), "eingetragen": True, "korrektur": laeufe}


async def _stueck_bleiben(db: AsyncSession, anlage, la, label: str) -> dict:
    """U3 b (G7, E1 = A): «Bisherige Werte bleiben» am Stück einer MQTT-Reihe — je ein Eintrag «Zähler getauscht» am Sprung
    und am Rückgang (``zaehler_getauscht.trage_ein`` mit den Rand-Ständen der Rohstände, G5). Lässt sich einer nicht eintragen,
    wird keiner eingetragen (422 mit dem Satz der Lage)."""
    from backend.services.zuordnung_wechsel import stueck as st
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    lagen = await st.tausch_lagen(db, anlage, la)
    gesperrt = next((x for x in lagen if x.weg != zg.WEG_FORTSETZUNG and not x.schon), None)
    if gesperrt is not None:
        raise HTTPException(status_code=422, detail=" ".join(zg.saetze(gesperrt)))
    try:
        for x in lagen:
            await zg.trage_ein(db, anlage, x)
    except ValueError:
        await db.rollback()
        raise HTTPException(status_code=422, detail=zg.satz_nicht_moeglich(lagen[0]))
    zeiten = " und ".join(x.getauscht_am.strftime("%d.%m.%Y %H:%M") for x in lagen)
    await log_activity(
        kategorie="sensor_mapping", aktion="Grund nachgetragen",
        details=(f"{anlage.anlagenname} · {label}: versetzter Abschnitt vom {la.sprung.strftime('%d.%m.%Y %H:%M')} bis "
                 f"{la.rueckgang.strftime('%d.%m.%Y %H:%M')} — bisherige Werte bleiben, Tausch am {zeiten}"),
        anlage_id=anlage.id, db=db,
    )
    await db.commit()
    return {**st.antwort(la, label, _feld_id(la.sensor_key)), "eingetragen": True, "korrektur": []}
