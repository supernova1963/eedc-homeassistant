"""Sensorwechsel U2 Lauf b «Fragen» (Rechenweg ``opus-berichte/SENSORWECHSEL-U2-RECHENWEG-2026-11-19.md`` F8, F9, F10; Bauplan
Nr. 138–145). Proben mit Sprengsatz — **über die Routen**, in der Welt der a2-Proben (``test_sensorwechsel_u2a2_proben``: Lab-
Zeilen, HA-Attrappe, Stundenlauf «:05»).

* F9 — die Prüf-Antwort ``…/quelle/pruefen`` trägt bei «bleiben» zwischen zwei HA-Sensoren ``bleiben``: seit wann HA den neuen
  führt, Überlappung, «Der neue Sensor zählt ab» (Vorgabe und Bereich nur bei Überlappung), Umfang des Neulesens — **Vorschau =
  Lauf** (dieselbe ``ansatz.lage``); ``zaehlt_ab`` außerhalb des Bereichs, ohne Überlappung, bei «verwerfen» oder bei einer
  anderen Kombination ⇒ 422.
* F10 — «Grund nachtragen» mit derselben Frage; Vorgabe für den Schnitt ist die Stunde des verzeichneten Wechsels.
* Nachlauf sichtbar — der Lauf des Ansetzens trägt ``art = ansetzen``; die Wartegründe als Sätze (Antwort der Route, Lese-Route
  ``wartende-wechsel``); der Satz zu einem offenen Lauf des Ansetzens nennt keine Korrektur.
* F8 — Live heute/gestern je Geltungsabschnitt: gestern (Tausch-Tag) 15,3, heute am Tausch-Tag wie HA.

Schwesterdateien: test_sensorwechsel_u2a2_proben.py (der Dienst), test_sensorwechsel_u2a1_proben.py (die Leser).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from backend.models import activity_log, mqtt_gateway_mapping  # noqa: F401 — Tabellen der Routen (Teil-Schema der Fixture)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.tests.test_sensorwechsel_u2a1_proben import ALT, NEU, Lab
from backend.tests.test_sensorwechsel_u2a2_proben import (
    FID, KEY, STUNDE, T1, Welt, _ep, _frisch, _ha_bis, _laeufe, _stunde, _wechsel, _wechsel_ohne_grund, _welt, _ws_dienst, ende,
    sichten, soll, _vergleich,
)

U1030 = T1 + timedelta(hours=3, minutes=30)


class _Uhr:
    """Die Uhr der Abfrage (``abfrage.datetime``) auf ``t``."""

    def __init__(self, monkeypatch, t: datetime):
        import backend.services.zuordnung_wechsel.abfrage as ab

        class Uhr(datetime):
            @classmethod
            def now(cls, tz=None):
                return t
        self.mp, self.ab = monkeypatch, ab
        monkeypatch.setattr(ab, "datetime", Uhr)

    def aus(self):
        self.mp.setattr(self.ab, "datetime", datetime)


def _body(**k):
    from backend.api.routes.datenquellen import QuelleSetRequest

    return QuelleSetRequest(quelle="ha_app", entity_id=NEU, **k)


async def _pruefen(w: Welt, monkeypatch, U: datetime, **k) -> dict:
    from backend.api.routes.datenquellen import pruefe_feld_quelle

    uhr = _Uhr(monkeypatch, U)
    try:
        return await pruefe_feld_quelle(w.a.id, FID, _body(**k), w.db)
    finally:
        uhr.aus()


async def _abgelehnt(aufruf) -> HTTPException:
    with pytest.raises(HTTPException) as e:
        await aufruf
    return e.value


async def _umstellen(w: Welt, monkeypatch, U: datetime, **k) -> list[dict]:
    """Beide Felder der Wallbox über die Feld-Route auf den neuen Sensor (Grund «bleiben», mit ``k``)."""
    from backend.api.routes.datenquellen import set_feld_quelle

    out = []
    uhr = _Uhr(monkeypatch, U)
    try:
        for fid in (FID, "inv_energy_2_ladung_pv_kwh"):
            out.append(await set_feld_quelle(w.a.id, fid, _body(grund="fortsetzung", **k), w.db))
            await _laeufe()
            _frisch(w)
    finally:
        uhr.aus()
    return out


async def _betrieb(w: Welt, von: datetime, bis: datetime, *, ansetzen: bool = True) -> None:
    for e in range(_ep(von), _ep(bis) + 1, STUNDE):
        await _stunde(w, datetime.fromtimestamp(e), ansetzen=ansetzen)


async def _bis_zur_umstellung(w: Welt, U: datetime) -> None:
    await _betrieb(w, T1 - timedelta(hours=30), U.replace(minute=0, second=0))
    _ha_bis(w, _ep(U.replace(minute=0, second=0)) - STUNDE)


# ═══ F9 — Prüf-Antwort ohne Überlappung ═════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_f9_pruef_antwort_ohne_ueberlappung_ist_der_lauf(db, monkeypatch, sprengsatz):
    """Umstellung 10:30, ohne Überlappung: die Prüf-Antwort nennt seit 07:00 (erste Zeile des neuen), keine Überlappung, kein
    Feld «zählt ab», zählt ab 07:00, 3 Stunden neu (07:00–10:00) und die Tage — **Vorschau = Lauf**: die Route setzt mit
    derselben Stunde an. Sprengsatz: ohne die Angaben (kein HA → HA) fehlt ``bleiben``."""
    import backend.services.zuordnung_wechsel.bleiben as bl

    if sprengsatz:
        monkeypatch.setattr(bl, "ist_ha_zu_ha", lambda *_a: False)
    w = await _welt(db, monkeypatch, Lab(T1))
    await _bis_zur_umstellung(w, U1030)
    p = await _pruefen(w, monkeypatch, U1030)
    assert p["grund_erforderlich"]
    if sprengsatz:
        assert p["bleiben"] is None
        return
    b = p["bleiben"]
    assert (b["wartet"], b["seit"], b["ueberlappung"], b["zaehlt_ab"]) == (None, T1.isoformat(), False, T1.isoformat())
    assert (b["zaehlt_ab_vorgabe"], b["zaehlt_ab_frueheste"], b["zaehlt_ab_spaeteste"]) == (None, None, None)
    assert b["stunden"] == 3 and b["monate"] == []
    assert b["saetze"][0] == bl.SATZ_SEIT.format(neu=NEU, seit="10.11.2026 07:00")
    assert any("zählt beide" in x for x in b["saetze"]) and b["saetze"][-1] == bl.SATZ_LOESCHEN
    r = await _umstellen(w, monkeypatch, U1030)
    row = await _wechsel(db)
    assert (row.ansatz, row.ab_ts - timedelta(hours=1)) == ("beide", T1)
    lauf = next(x for x in r[0]["korrektur"] if x["sensor_key"] == KEY)
    assert lauf["art"] == "ansetzen" and lauf["tage_neu"] == b["tage"] and r[0]["wartet"] == []


# ═══ F9 — «Der neue Sensor zählt ab» bei Überlappung ════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_f9_zaehlt_ab_bei_ueberlappung(db, monkeypatch, sprengsatz):
    """Der neue zählt schon einen Tag vorher (Überlappung). Die Prüf-Antwort nennt Vorgabe 10:00 (Stunde der Umstellung) und den
    Bereich [erste Zeile des neuen + 1 h, 10:00]; mit «zählt ab» = 07:00 (Tausch-Stunde) rechnet sie an 07:00. Die Route setzt
    die Zeile auf ``offen_schnitt`` ⇒ angesetzt ``schnitt`` mit G = 07:00; danach nennt jede Sicht HAs Zahlen «alt bis 07:00, neu
    ab 07:00». Sprengsatz: die Stände des alten zwischen 08:00 und 11:00 bleiben stehen (``_ab_alt`` = ``ab_ts``) ⇒ die Reihe
    weicht ab."""
    import backend.services.zuordnung_wechsel.ansatz as an

    if sprengsatz:
        monkeypatch.setattr(an, "_ab_alt", lambda row: row.ab_ts)
    lab = Lab(T1, vorgeschichte=True, schnitt=T1)
    w = await _welt(db, monkeypatch, lab)
    await _bis_zur_umstellung(w, U1030)
    b = (await _pruefen(w, monkeypatch, U1030))["bleiben"]
    erste = datetime.fromtimestamp(min(lab.neu))
    assert (b["ueberlappung"], b["seit"], b["zaehlt_ab"]) == (True, erste.isoformat(), (T1 + timedelta(hours=3)).isoformat())
    assert (b["zaehlt_ab_vorgabe"], b["zaehlt_ab_frueheste"], b["zaehlt_ab_spaeteste"]) == (
        (T1 + timedelta(hours=3)).isoformat(), (erste + timedelta(hours=1)).isoformat(), (T1 + timedelta(hours=3)).isoformat())
    b7 = (await _pruefen(w, monkeypatch, U1030, grund="fortsetzung", zaehlt_ab=T1 + timedelta(minutes=12)))["bleiben"]
    assert (b7["zaehlt_ab"], b7["stunden"]) == (T1.isoformat(), 3)
    await _umstellen(w, monkeypatch, U1030, zaehlt_ab=T1)
    await _betrieb(w, U1030.replace(minute=0) + timedelta(hours=1), ende(U1030))
    row = await _wechsel(db)
    assert (row.ansatz, row.ab_ts) == ("schnitt", T1 + timedelta(hours=1))
    ist, s = await sichten(w), soll(w)
    if sprengsatz:
        assert _vergleich(ist, s) != {}
        return
    assert _vergleich(ist, s) == {}, (ist, s)


async def test_f9_zaehlt_ab_abgelehnt(db, monkeypatch):
    """422: außerhalb des Bereichs (vor der ersten Zeile + 1 h, nach der Umstellung), ohne Überlappung, mit «verwerfen» und für
    eine Änderung, die kein Wechsel zwischen zwei HA-Sensoren ist (nach «Keine»: keine Frage). Prüfen und Schreiben gleich; das
    Schreiben lässt nichts stehen."""
    from backend.api.routes.datenquellen import QuelleSetRequest, pruefe_feld_quelle, set_feld_quelle
    from backend.services.zuordnung_wechsel import bleiben as bl

    lab = Lab(T1, vorgeschichte=True, schnitt=T1)
    w = await _welt(db, monkeypatch, lab)
    await _bis_zur_umstellung(w, U1030)
    erste = datetime.fromtimestamp(min(lab.neu))
    bereich = bl.SATZ_BEREICH.format(von=(erste + timedelta(hours=1)).strftime("%d.%m.%Y %H:%M"),
                                     bis=(T1 + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M"))
    for t in (erste, T1 + timedelta(hours=4)):
        e = await _abgelehnt(_pruefen(w, monkeypatch, U1030, grund="fortsetzung", zaehlt_ab=t))
        assert (e.status_code, e.detail) == (422, bereich)
        uhr = _Uhr(monkeypatch, U1030)
        try:
            e = await _abgelehnt(set_feld_quelle(w.a.id, FID, _body(grund="fortsetzung", zaehlt_ab=t), w.db))
        finally:
            uhr.aus()
        await db.rollback()
        assert (e.status_code, e.detail) == (422, bereich)
    assert (await db.execute(select(ZuordnungWechsel))).first() is None
    e = await _abgelehnt(_pruefen(w, monkeypatch, U1030, grund="korrektur", falsch_seit=T1, zaehlt_ab=T1))
    assert (e.status_code, e.detail) in ((422, bl.SATZ_NUR_BLEIBEN),)
    keine = QuelleSetRequest(quelle="keine", zaehlt_ab=T1)
    e = await _abgelehnt(pruefe_feld_quelle(w.a.id, FID, keine, w.db))
    assert (e.status_code, e.detail) == (422, bl.SATZ_NUR_HA)


async def test_f9_zaehlt_ab_ohne_ueberlappung_abgelehnt(db, monkeypatch):
    from backend.services.zuordnung_wechsel import bleiben as bl

    w = await _welt(db, monkeypatch, Lab(T1))
    await _bis_zur_umstellung(w, U1030)
    e = await _abgelehnt(_pruefen(w, monkeypatch, U1030, grund="fortsetzung", zaehlt_ab=T1 + timedelta(hours=2)))
    assert (e.status_code, e.detail) == (422, bl.SATZ_OHNE_UEBERLAPPUNG)


# ═══ F10 — «Grund nachtragen» mit derselben Frage ═══════════════════════════════════════════════════════════════════════

async def _nachtrag_pruefen(w: Welt, **k) -> dict:
    from backend.api.routes.sensorwechsel import GrundNachtragRequest, pruefe_grund_nachtragen

    zw.vergiss(w.db)
    row = (await w.db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.sensor_key == KEY,
                                                             ZuordnungWechsel.aufgehoben_durch.is_(None))
                              .order_by(ZuordnungWechsel.id.desc()))).scalars().first()
    return await pruefe_grund_nachtragen(w.a.id, row.id, GrundNachtragRequest(**k), w.db)


async def _nachtragen(w: Welt, **k) -> dict:
    from backend.api.routes.sensorwechsel import GrundNachtragRequest, grund_nachtragen

    out = {}
    for key in (KEY, "inv:2:ladung_pv_kwh"):
        zw.vergiss(w.db)
        row = (await w.db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.sensor_key == key,
                                                                 ZuordnungWechsel.aufgehoben_durch.is_(None))
                                  .order_by(ZuordnungWechsel.id.desc()))).scalars().first()
        out[key] = await grund_nachtragen(w.a.id, row.id, GrundNachtragRequest(grund="fortsetzung", **k), w.db)
        await _laeufe()
        _frisch(w)
    return out


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_f10_nachtrag_mit_zaehlt_ab(db, monkeypatch, sprengsatz):
    """Wechsel ohne Grund um 10:47 (Überlappung): die Prüfung nennt Vorgabe = Stunde des verzeichneten Wechsels (10:00) und den
    Bereich; «bleiben» mit «zählt ab» 07:00 ⇒ ``nachtrag`` ``schnitt`` an 07:00, jede Sicht = HA. Sprengsatz: «zählt ab» nicht
    durchgereicht ⇒ G bleibt 10:00."""
    import backend.services.zuordnung_wechsel.nachtrag as nt

    if sprengsatz:
        alt = nt.trage_fortsetzung_ein

        async def ohne(db_, anlage, row, zaehlt_ab=None, jetzt=None):
            return await alt(db_, anlage, row)
        monkeypatch.setattr(nt, "trage_fortsetzung_ein", ohne)
    lab = Lab(T1, vorgeschichte=True, schnitt=T1)
    w = await _welt(db, monkeypatch, lab)
    U = T1 + timedelta(hours=3, minutes=47)
    await _betrieb(w, T1 - timedelta(hours=30), U.replace(minute=0))
    await _wechsel_ohne_grund(w, U)
    await _betrieb(w, U.replace(minute=0) + timedelta(hours=1), ende(U))
    b = (await _nachtrag_pruefen(w))["bleiben"]
    assert (b["ueberlappung"], b["zaehlt_ab_vorgabe"], b["zaehlt_ab_spaeteste"]) == (
        True, (T1 + timedelta(hours=3)).isoformat(), (T1 + timedelta(hours=3)).isoformat())
    assert (await _nachtrag_pruefen(w, grund="fortsetzung", zaehlt_ab=T1))["bleiben"]["zaehlt_ab"] == T1.isoformat()
    e = await _abgelehnt(_nachtrag_pruefen(w, grund="korrektur", falsch_seit=T1 - timedelta(hours=5), zaehlt_ab=T1))
    assert e.status_code == 422
    await _nachtragen(w, zaehlt_ab=T1)
    row = await _wechsel(db)
    if sprengsatz:
        assert (row.ansatz, row.ab_ts) == ("schnitt", T1 + timedelta(hours=4))
        return
    assert (row.herkunft, row.ansatz, row.ab_ts) == ("nachtrag", "schnitt", T1 + timedelta(hours=1))
    ist, s = await sichten(w), soll(w)
    assert _vergleich(ist, s) == {}, (ist, s)


# ═══ Nachlauf sichtbar ══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_wartegrund_und_lauf_des_ansetzens(db, monkeypatch, sprengsatz):
    """Umstellung 06:40, bevor HA eine Zeile des neuen führt: die Route nennt den Wartegrund als Satz, die Lese-Route
    ``wartende-wechsel`` ebenso (auch nach dem Neuladen). Nach dem Ansetzen trägt der Lauf ``art = ansetzen`` (Fortschritt-Route,
    laufende Läufe); ein offener Lauf des Ansetzens sperrt eine Korrektur mit eigenem Satz (keine «frühere Korrektur»).
    Sprengsatz: der Lauf wird ohne Art angelegt ⇒ «korrektur»."""
    from backend.api.routes.sensorwechsel import korrektur_lauf_stand, korrektur_laeufe, wartende_wechsel
    from backend.services.zuordnung_wechsel import bleiben as bl
    from backend.services.zuordnung_wechsel import korrektur_lauf
    from backend.services.zuordnung_wechsel import nachtrag as nt
    from backend.services.zuordnung_wechsel.ansatz import setze_an

    if sprengsatz:
        alt = korrektur_lauf.anlegen

        async def ohne_art(*a, art=None, **k):
            return await alt(*a, **k)
        monkeypatch.setattr(korrektur_lauf, "anlegen", ohne_art)
    w = await _welt(db, monkeypatch, Lab(T1))
    U = T1 - timedelta(minutes=20)
    await _betrieb(w, T1 - timedelta(hours=30), T1 - timedelta(hours=1))
    _ha_bis(w, _ep(T1) - 2 * STUNDE)
    r = await _umstellen(w, monkeypatch, U)
    satz = bl.SATZ_WARTET["noch_keine_zeile"].format(neu=NEU)
    assert [x["satz"] for x in r[0]["wartet"]] == [satz] and r[0]["korrektur"] == []
    zw.vergiss(db)
    assert [x["satz"] for x in await wartende_wechsel(w.a.id, db) if x["sensor_key"] == KEY] == [satz]
    _ha_bis(w, _ep(T1))
    row = await _wechsel(db)
    e = await setze_an(w.sitzungen, row.id, jetzt=T1 + timedelta(hours=1, minutes=5), starten=False)
    _frisch(w)
    assert e["angesetzt"] and e["lauf"]
    stand = await korrektur_lauf_stand(w.a.id, e["lauf"], db)
    laufend = [x for x in await korrektur_laeufe(w.a.id, db) if x["lauf"] == e["lauf"]]
    erwartet = "korrektur" if sprengsatz else "ansetzen"
    assert stand["art"] == erwartet and [x["art"] for x in laufend] == [erwartet]
    await korrektur_lauf._schreibe(w.sitzungen, e["lauf"], fuellen={"erledigt": False})
    assert await nt.satz_lauf_offen(db, w.a.id, KEY) == (nt.SATZ_LAUF_OFFEN if sprengsatz else nt.SATZ_LAUF_OFFEN_ANSETZEN)
    assert [x for x in await wartende_wechsel(w.a.id, db) if x["sensor_key"] == KEY] == []


# ═══ F8 — Live heute/gestern je Geltungsabschnitt ═══════════════════════════════════════════════════════════════════════

async def _live(w: Welt, monkeypatch, jetzt: datetime, tage_zurueck: int) -> dict:
    """``get_tages_kwh`` mit der Uhr ``jetzt``; die Zustands-Geschichte aus denselben Zeilen (wie die Saat), dazu ein
    Leistungssensor der Wallbox (Live-Komponente)."""
    import backend.services.ha_state_service as hst
    import backend.services.live_history_service as lh

    class Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return jetzt

    async def geschichte(ids, start, end):
        hist, units = {}, {}
        with w.svc._engine.begin() as c:
            for eid in ids:
                rows = c.execute(text("SELECT s.start_ts, s.state FROM statistics s JOIN statistics_meta m ON "
                                      "m.id = s.metadata_id WHERE m.statistic_id = :e AND s.start_ts >= :a AND s.start_ts < :b "
                                      "ORDER BY s.start_ts"), {"e": eid, "a": _ep(start) - STUNDE, "b": _ep(end)}).fetchall()
                if rows:
                    hist[eid] = [(datetime.fromtimestamp(t + STUNDE), float(st)) for t, st in rows]
                    units[eid] = "kWh"
        hist["sensor.wb_w"] = [(start, 0.0), (end, 0.0)]
        units["sensor.wb_w"] = "W"
        return hist, units

    class Erreichbar:
        is_available = True
    monkeypatch.setattr(lh, "get_history_normalized", geschichte)
    monkeypatch.setattr(lh, "datetime", Uhr)
    monkeypatch.setattr(hst, "get_ha_state_service", lambda: Erreichbar())
    a = (await w.db.execute(select(Anlage).where(Anlage.id == w.a.id))).scalar_one()
    a.sensor_mapping = {**a.sensor_mapping, "investitionen": {"2": {**a.sensor_mapping["investitionen"]["2"],
                                                                     "live": {"leistung_w": "sensor.wb_w"}}}}
    try:
        return await lh.get_tages_kwh(a, w.db, tage_zurueck)
    finally:
        monkeypatch.setattr(lh, "datetime", datetime)
        await w.db.rollback()


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_f8_live_gestern_und_heute_je_abschnitt(db, monkeypatch, sprengsatz):
    """Nach dem Ansetzen (Umstellung 10:30): Live «gestern» am Folgetag = Tausch-Tag 15,3 (alter bis 08:00, neuer ab 07:00 ab 0),
    «heute» am Tausch-Tag um 12:00 = HAs Summe beider bis dahin, «heute» am Folgetag = nur der neue. Sprengsatz: ohne die
    Abschnitte (``monat.live_zeilen`` leer) zählt nur der neue ab seinem ersten Stand — 8,0 statt 15,3 (die Zahl am HEAD)."""
    import backend.services.zuordnung_wechsel.monat as mo

    if sprengsatz:
        async def keine(*_a, **_k):
            return {}
        monkeypatch.setattr(mo, "live_zeilen", keine)
    lab = Lab(T1)
    w = await _welt(db, monkeypatch, lab)
    await _bis_zur_umstellung(w, U1030)
    await _umstellen(w, monkeypatch, U1030)
    await _betrieb(w, U1030.replace(minute=0) + timedelta(hours=1), ende(U1030))
    D = T1.replace(hour=0)
    gestern = (await _live(w, monkeypatch, D + timedelta(days=1, hours=9), 1)).get("wallbox_2")
    heute = (await _live(w, monkeypatch, D + timedelta(hours=12), 0)).get("wallbox_2")
    folgetag = (await _live(w, monkeypatch, D + timedelta(days=1, hours=9), 0)).get("wallbox_2")
    soll_tag = lab.soll(lambda t: D <= t < D + timedelta(days=1))
    soll_heute = lab.soll(lambda t: D <= t < D + timedelta(hours=12))
    soll_folgetag = lab.soll(lambda t: D + timedelta(days=1) <= t < D + timedelta(days=1, hours=9))
    assert soll_tag == pytest.approx(15.3)
    if sprengsatz:
        assert gestern == pytest.approx(8.0)          # wie am HEAD: nur der neue, ab seinem ersten Stand
        return
    assert (gestern, heute, folgetag) == (pytest.approx(soll_tag), pytest.approx(round(soll_heute, 1)),
                                          pytest.approx(round(soll_folgetag, 1)))


async def test_f8_ohne_wechsel_wie_bisher(db, monkeypatch):
    """Ohne angesetzten Wechsel liest Live wörtlich wie vorher (``_energy_delta_via_statistics`` ohne Zeilen)."""
    import backend.services.live_history_service as lh

    w = await _welt(db, monkeypatch, Lab(T1))
    await _betrieb(w, T1 - timedelta(hours=30), T1 + timedelta(hours=2))
    D = T1.replace(hour=0)
    assert lh._energy_delta_via_statistics(ALT, D, D + timedelta(hours=6), []) == \
        lh._energy_delta_via_statistics(ALT, D, D + timedelta(hours=6))
    assert await lh._wechsel_der_anlage(db, (await db.execute(select(Anlage))).scalar_one()) == {}


def test_tagesmenge_aus_abschnitten():
    from backend.core.berechnungen.zaehler_naht import tagesmenge_aus_abschnitten

    assert tagesmenge_aus_abschnitten([(10.0, 16.6), (0.0, 8.7)]) == pytest.approx(15.3)
    assert tagesmenge_aus_abschnitten([(10.0, None)]) is None and tagesmenge_aus_abschnitten([]) is None
    assert tagesmenge_aus_abschnitten([(5.0, 4.0), (0.0, 1.0)]) == 1.0



# ═══ Texte aus den Vorläufen (Punkt 5) ══════════════════════════════════════════════════════════════════════════════════

def test_satz_hoehe_ungeprueft_mit_handgriff_nur_wo_falsch_seit_waehlbar_ist():
    """``SATZ_LUECKE_HOEHE`` nennt den Grund (HA führt den richtigen Sensor erst ab dem Ende der Zeit); der Handgriff «Falsch
    seit auf … setzen» steht nur, wo «Falsch seit» wählbar ist (Dialog, Nachtrag) — nicht an der Werkbank (von Beginn an) und
    nicht am Stück (feste Zeit)."""
    from types import SimpleNamespace

    from backend.services.zuordnung_wechsel import korrektur as kr

    def la(**auftrag):
        return SimpleNamespace(luecke=(datetime(2026, 6, 10, 1), datetime(2026, 6, 12)), zaehlerluecke=False,
                               hoehe_ungeprueft=True, luecke_tage=[], luecke_rand=[], zaehlerluecke_tag=None, staende_neu=None,
                               auftrag=SimpleNamespace(**auftrag))
    hand = kr.SATZ_LUECKE_HOEHE_HANDGRIFF.format(bis="12.06.2026 00:00")
    s = kr.saetze_luecke(la(falsch_seit=datetime(2026, 6, 10, 1), stueck=False))
    assert s[:2] == [kr.SATZ_LUECKE_HOEHE.format(von="10.06.2026 01:00", bis="12.06.2026 00:00"), hand]
    assert "erst ab dann" in s[0]
    assert hand not in kr.saetze_luecke(la(falsch_seit=None, stueck=False))
    assert hand not in kr.saetze_luecke(la(falsch_seit=datetime(2026, 6, 10, 1), stueck=True))


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_befund_fuellbar_nennt_die_spaeter_beginnende_geschichte(db, monkeypatch, sprengsatz):
    """Befund «Zählerstände liegen versetzt», Lage ``fuellbar``, Home Assistant führt die Quelle im Abschnitt erst ab 12.06.
    00:00: der Satz nennt diese Zeit — dieselbe wie die Vorschau des Dialogs (``SATZ_STAENDE_AB``) — und dass über die Zeit
    davor wie über jede Zählerlücke gerechnet wird. Sprengsatz: ohne die Vorschau ⇒ der gewöhnliche Satz «… auf derselben
    Höhe wie davor und danach» ohne Zeit."""
    import backend.services.daten_checker.datenquelle.versatz as vs
    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.tests import test_daten_checker_zaehler_versatz as v
    from backend.tests.test_sensorwechsel_s4b1_stueck import _body
    from backend.tests.test_sensorwechsel_u1k_proben import _ha_mit

    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)
    _ha_mit(monkeypatch, loch=range(v.SPRUNG_H, 11 * 24))
    v._kanal_tage(monkeypatch, {})
    if sprengsatz:
        async def keine(*_a, **_k):
            return None
        monkeypatch.setattr(vs.ZaehlerVersatzChecks, "_versatz_fuellbar_ab", keine)
    a, _wb, key = await v._anlage(db, spiegel=False)
    (e,) = await v._pruefe(db, a)
    assert e.werte["lage"] == vs.LAGE_FUELLBAR
    k = (await sw.pruefe_stueck(a.id, _body(key), db))["korrektur"]
    assert kr.SATZ_STAENDE_AB.format(zeit="12.06.2026 00:00") in k["saetze"]
    if sprengsatz:
        assert "auf derselben Höhe wie davor und danach." in e.details and "12.06.2026 00:00" not in e.details
        return
    assert "aber erst ab 12.06.2026 00:00 Uhr — von dort an liest eedc sie neu" in e.details
    assert e.details.endswith(vs._SATZ_FUELLBAR_AB_LUECKE)


def test_f8_live_schnitt_der_alte_zaehlt_nur_bis_g():
    """Live je Abschnitt mit Überlappung (``schnitt``): der alte Sensor zählt nach G weiter, gezählt wird er nur bis G (sein
    Stand um G), der neue ab G (sein Stand um G als Anker). Sprengsatz-Gegenstück: der Stand des alten am Fensterende zählte
    seine Menge nach G mit."""
    from backend.services.live_history_service import _delta_je_abschnitt
    from backend.services.zuordnung_wechsel.monat import unix

    D, G, E = datetime(2026, 11, 10), datetime(2026, 11, 10, 10), datetime(2026, 11, 11)

    class Stats:
        def get_value_at(self, eid, t, toleranz_minuten=120, short_term=False):
            stunden = (t - D).total_seconds() / 3600
            return {"alt": 100.0 + stunden, "neu": 500.0 + 0.5 * stunden}[eid]   # beide zählen den ganzen Tag

    teile = [("alt", unix(D), unix(G), False), ("neu", unix(G), unix(E), False)]
    assert _delta_je_abschnitt(Stats(), teile, E) == pytest.approx(10.0 + 7.0)     # alt 00–10 Uhr, neu 10–24 Uhr


# ═══ Korrekturrunde a-K ═════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("stunde", ["erste", "zweite"])
async def test_ak_n5_rand_stand_epoch_genau_in_der_doppelten_herbststunde(stunde):
    """a-K N5: ``ansatz._ha_stand`` nimmt den Stand am Ende **der Zeile in der Hand** (epoch-genau) — in der doppelten
    Herbststunde (Berlin 25.10.2026) die erste und die zweite «02:00»-Zeile je für sich; die Wand-Uhr (``fromtimestamp`` ohne
    Zone, wie vor a-K) träfe in Berlin für die erste eine andere Zeile. In jeder Zone gleich."""
    from datetime import timezone

    from backend.services.zuordnung_wechsel.ansatz import _ha_stand
    from backend.tests import ha_lts_helfer as H

    svc = H.mach_service(thread_sicher=True)
    mid = H.sensor(svc, "sensor.z", "kWh", has_sum=True)
    e = int(datetime(2026, 10, 25, 0, tzinfo=timezone.utc).timestamp())       # Berlin: die erste 02:00 (Sommerzeit)
    zeilen = {e - 3600: 5.0, e: 10.0, e + 3600: 20.0, e + 7200: 30.0}
    with svc._engine.begin() as c:
        c.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :s, :s)"),
                  [{"m": mid, "t": t, "s": s} for t, s in zeilen.items()])
    start = e if stunde == "erste" else e + 3600
    assert await _ha_stand(svc, "sensor.z", {"start_ts": float(start)}, "inv:2:ladung_kwh") == zeilen[start]
    wanduhr = await asyncio_to_thread(svc.get_value_at, "sensor.z", datetime.fromtimestamp(start + 3600), 10)
    if stunde == "erste" and time_zone_ist_berlin():
        assert wanduhr != zeilen[start]          # der Weg vor a-K: die Wand-Uhr «03:00» trifft nicht die erste Zeile


async def asyncio_to_thread(f, *a):
    import asyncio

    return await asyncio.to_thread(f, *a)


def time_zone_ist_berlin() -> bool:
    import time as _t

    return _t.tzname[0] in ("CET", "MEZ")


async def _gas_lage(db, monkeypatch, *, sum_nach_t1: float = 0.0, kanal: bool = True):
    """Stand-Feld (Gaszähler ``inv:3:zaehlerstand``), alter Sensor bis T1 (``state`` 1000 + 0,5 je Stunde), neuer ab T1 mit
    ``state`` 5,0 + 0,4 je Stunde (Nullpunkt ``state − sum`` = 5,0); Kanal ``stand`` aus dem Spiegel des alten. Returns die
    ``ansatz.lage`` einer gedachten Zeile «bleiben» (Umstellung 10:30)."""
    import backend.services.ha_statistics_service as hss
    from backend.models.kanal import FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
    from backend.services.zuordnung_wechsel.ansatz import lage
    from backend.services.zuordnung_wechsel.bleiben import pruef_zeile
    from backend.tests import ha_lts_helfer as H

    svc = H.mach_service(thread_sicher=True)
    ma, mn = H.sensor(svc, "sensor.gas_a", "m³", has_sum=True), H.sensor(svc, "sensor.gas_b", "m³", has_sum=True)
    e1 = _ep(T1)
    alt = {e1 - i * STUNDE: (1000.0 + 0.5 * (20 - i), 0.5 * (20 - i)) for i in range(0, 21)}
    for i in range(1, 6):                                        # danach: der Stand bleibt, die Summe ggf. berichtigt
        alt[e1 + i * STUNDE] = (alt[e1][0], alt[e1][1] + sum_nach_t1)
    neu = {e1 + i * STUNDE: (5.0 + 0.4 * (i + 1), 0.4 * (i + 1)) for i in range(0, 6)}
    with svc._engine.begin() as c:
        c.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :st, :su)"),
                  [{"m": m, "t": t, "st": st, "su": su} for m, reihe in ((ma, alt), (mn, neu)) for t, (st, su) in reihe.items()])
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    a = Anlage(anlagenname="Gas", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    db.add(Investition(id=3, anlage_id=a.id, typ="sonstiges", bezeichnung="Gas", anschaffungsdatum=date(2025, 1, 1)))
    if kanal:
        k = Kanal(anlage_id=a.id, key="inv:3:zaehlerstand", einheit="m³", art="stand")
        db.add(k)
        await db.flush()
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=e1 - 20 * STUNDE, familie=FAMILIE_SPIEGEL, statistic_id="sensor.gas_a",
                           offset=0.0))
        db.add_all([KanalStatistik(kanal_id=k.id, start_ts=t, state=st, sum=su, familie=FAMILIE_SPIEGEL)
                    for t, (st, su) in alt.items() if t < e1])
    await db.commit()
    zeile = pruef_zeile(a.id, "inv:3:zaehlerstand", {"art": "ha", "entity_id": "sensor.gas_a"},
                        {"art": "ha", "entity_id": "sensor.gas_b"}, ab_ts=T1 + timedelta(hours=4),
                        erklaert_ts=T1 + timedelta(hours=3, minutes=30))
    return await lage(db, zeile, ha_svc=svc, jetzt=T1 + timedelta(hours=5, minutes=5)), alt


async def test_ak_n1_stand_feld_nullpunkt_ist_state_minus_sum(db, monkeypatch):
    """a-K N1: am Stand-Feld (Gas, Wasser, Öl) erkennt das Ansetzen das Feld am Schlüssel — ``beide``, Nullpunkt des neuen
    ``state − sum`` der ersten Zeile (5,0), im Kanal ebenso (Versatz = Stand des alten am Rand − 5,0); die Überlappung
    prüft ``state``: eine in HA berichtigte Summe des alten nach T1 ist keine Überlappung (Mutanten E1, E2, E13)."""
    la, alt = await _gas_lage(db, monkeypatch, sum_nach_t1=100.0)
    assert (la.wartet, la.art, la.ueberlappung) == (None, "beide", False)
    assert la.stand_neu_null == pytest.approx(5.0)
    assert la.kanal_versatz == pytest.approx(alt[_ep(T1)][0] - 5.0)


async def test_ak_n8_e6_g_fruehestens_t1_plus_eine_stunde(db, monkeypatch):
    """E-1 (Mutante E6): mit Überlappung und einer Stunde des Wechsels vor der ersten Zeile des neuen schneidet eedc an
    T1 + 1 h, nicht an der Stunde des Wechsels."""
    from backend.services.zuordnung_wechsel.ansatz import lage
    from backend.services.zuordnung_wechsel.bleiben import pruef_zeile

    w = await _welt(db, monkeypatch, Lab(T1, vorgeschichte=True, schnitt=T1 + timedelta(hours=3)))
    _ha_bis(w, _ep(T1) + 6 * STUNDE)
    erste = T1 - timedelta(hours=31)
    zeile = pruef_zeile(w.a.id, KEY, {"art": "ha", "entity_id": ALT}, {"art": "ha", "entity_id": NEU},
                        ab_ts=erste - timedelta(hours=2), erklaert_ts=erste - timedelta(hours=3))
    la = await lage(db, zeile, ha_svc=w.svc, jetzt=T1 + timedelta(hours=7))
    assert (la.art, la.t1, la.g) == ("schnitt", erste, erste + timedelta(hours=1))


@pytest.mark.parametrize("fall", ["e7_ergaenzen", "e8_unterstunde", "e10_gespeicherter_rand"])
async def test_ak_n8_schritte_des_ansetzens(db, monkeypatch, fall):
    """Mutanten E7, E8, E10 an der Umstellung 10:30 (Lab-Zeilen, ``beide``): E7 — fehlt im Kanal die Zeile des alten vor G,
    ergänzt Schritt 1 sie aus HA (sonst fehlte die Stunde); E8 — ein Unterstunden-Stand des alten zwischen altem und neuem
    ``ab_ts`` ist danach weg; E10 — der gespeicherte Stand des alten am Rand gewinnt vor HAs Wert (die Höhe der Reihe)."""
    from backend.models.kanal import Kanal, KanalStatistik
    from backend.models.sensor_snapshot import SensorSnapshot

    lab = Lab(T1)
    w = await _welt(db, monkeypatch, lab)
    await _bis_zur_umstellung(w, U1030)
    k = (await db.execute(select(Kanal).where(Kanal.key == KEY))).scalar_one()
    if fall == "e7_ergaenzen":                                   # die Zeile 06:00 des alten fehlt im Kanal
        await db.execute(text("DELETE FROM kanal_statistik WHERE kanal_id = :k AND start_ts = :t"),
                         {"k": k.id, "t": _ep(T1) - STUNDE})
    elif fall == "e8_unterstunde":                               # ein 5-Minuten-Stand des alten um 08:30
        db.add(SensorSnapshot(anlage_id=w.a.id, sensor_key=KEY, zeitpunkt=T1 + timedelta(hours=1, minutes=30),
                              wert_kwh=999.0, quelle="ha_statistics"))
    else:                                                        # der gespeicherte Stand um 08:00 liegt 0,3 über HAs Wert
        st = (await db.execute(select(SensorSnapshot).where(SensorSnapshot.sensor_key == KEY,
                                                            SensorSnapshot.zeitpunkt == T1 + timedelta(hours=1)))).scalar_one()
        st.wert_kwh += 0.3
    await db.commit()
    await _umstellen(w, monkeypatch, U1030)
    row = await _wechsel(db)
    if fall == "e7_ergaenzen":
        z = (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id,
                                                           KanalStatistik.start_ts == _ep(T1) - STUNDE))).scalar_one_or_none()
        assert z is not None and row.ansatz == "beide"
    elif fall == "e8_unterstunde":
        assert (await db.execute(select(SensorSnapshot).where(SensorSnapshot.sensor_key == KEY,
                                                              SensorSnapshot.wert_kwh == 999.0))).first() is None
    else:
        assert row.stand_alt_ende == pytest.approx(lab.rand("beide")[0] + 0.3)


async def test_ak_n8_e11_fremder_kanal_gibt_auf_statt_zu_warten(db, monkeypatch):
    """Mutante E11 und «Ungeprüft» (a): trägt der Kanal vor G keinen Spiegel der alten oder neuen Entität, rechnet eedc den
    Wechsel wie bisher (die Zeile verliert ``offen``, eine Naht ohne Rand-Stände) — sie bliebe sonst für immer offen, und der
    Stundenlauf spiegelte den Schlüssel nie wieder."""
    from backend.models.kanal import Kanal, KanalQuelle
    from backend.services.zuordnung_wechsel.ansatz import WARTET_KANAL, offene_schluessel
    from backend.services.zuordnung_wechsel.zeitpunkt import lade_wechsel

    w = await _welt(db, monkeypatch, Lab(T1))
    await _bis_zur_umstellung(w, U1030)
    k = (await db.execute(select(Kanal).where(Kanal.key == KEY))).scalar_one()
    await db.execute(text("UPDATE kanal_quelle SET statistic_id = 'sensor.dritter' WHERE kanal_id = :k"), {"k": k.id})
    await db.commit()
    r = await _umstellen(w, monkeypatch, U1030)
    row = await _wechsel(db)
    assert row.ansatz is None and r[0]["wartet"] == []
    assert KEY not in offene_schluessel(await lade_wechsel(db, w.a.id))
    q = [x.statistic_id for x in (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars()]
    assert q == ["sensor.dritter"] and WARTET_KANAL == "kanal_nicht_ansetzbar"
    await _betrieb(w, U1030.replace(minute=0) + timedelta(hours=1), U1030.replace(minute=0) + timedelta(hours=2))
    q = [x.statistic_id for x in (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars()]
    assert NEU in q                                              # der Stundenlauf spiegelt den Schlüssel wieder


def test_ak_n8_e22_ws_erste_zeile_sieht_keine_zeile_nach_bis(monkeypatch):
    """Mutante E22: über WebSocket zählt für «erste Zeile» keine Zeile nach ``bis_ts`` — wie HA führt die Attrappe die
    Monats- und Tageszeile ab ihrem Beginn, auch wenn die Stunden darin erst nach ``bis_ts`` liegen (sonst setzte eedc an,
    bevor HA die Stunde abgeschlossen hat)."""
    from backend.services import ha_statistik_rand as hr
    from backend.services.ha_statistics_service import HAStatisticsService

    zeilen = {_ep(datetime(2026, 5, 1, 10)) + i * STUNDE: float(i) for i in range(5)}
    svc, ws = _ws_dienst(monkeypatch, zeilen)

    class WieHA:
        def statistiken(self, sids, von, bis, period="hour", types=None):
            a, b = von.timestamp(), bis.timestamp()
            if period == "hour":
                return ws.statistiken(sids, von, bis, period, types)
            gruppe = {}
            for t, s_ in sorted(zeilen.items()):
                d = datetime.fromtimestamp(t)
                k = _ep(d.replace(hour=0) if period == "day" else d.replace(day=1, hour=0))
                if a <= k < b:
                    gruppe.setdefault(k, s_)
            return {sids[0]: [{"start_ts": float(t), "sum": s_, "state": s_} for t, s_ in sorted(gruppe.items())]}
    monkeypatch.setattr(HAStatisticsService, "_ws", property(lambda self: WieHA()))
    assert hr.erste_zeile(svc, "sensor.x", float(_ep(datetime(2026, 5, 1, 8)))) is None
    assert hr.erste_zeile(svc, "sensor.x", float(_ep(datetime(2026, 5, 1, 12))))["start_ts"] == _ep(datetime(2026, 5, 1, 10))


async def _umstellen_auf(w: Welt, monkeypatch, U: datetime, eid: str) -> None:
    from backend.api.routes.datenquellen import QuelleSetRequest, set_feld_quelle

    uhr = _Uhr(monkeypatch, U)
    try:
        for fid in (FID, "inv_energy_2_ladung_pv_kwh"):
            await set_feld_quelle(w.a.id, fid, QuelleSetRequest(quelle="ha_app", entity_id=eid, grund="fortsetzung"), w.db)
            await _laeufe()
            _frisch(w)
    finally:
        uhr.aus()


async def _quellen(db) -> list:
    from backend.models.kanal import Kanal, KanalQuelle

    k = (await db.execute(select(Kanal).where(Kanal.key == KEY))).scalar_one()
    return [(q.gueltig_ab, q.statistic_id, round(q.offset, 3)) for q in
            (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id).order_by(KanalQuelle.gueltig_ab))).scalars()]


async def test_ak_n2_nachtrag_an_aelterem_wechsel_laesst_die_spaetere_quelle(db, monkeypatch):
    """a-K N2: A → B ohne Grund, später B → A «bleiben»; danach «Grund nachtragen → bleiben» an A → B. Die Kanal-Quelle des
    späteren Wechsels (A) bleibt stehen und rückt um die Änderung des Kanalwerts mit; die Tage nach dem späteren Wechsel
    zeigen dieselben Zahlen wie vorher; der Konsistenzlauf korrigiert 0 (Mutanten E4/E5)."""
    from backend.api.routes.sensorwechsel import GrundNachtragRequest, grund_nachtragen
    from backend.services.kanal import lesen
    from backend.services.kanal.konsistenz import konsistenz_anlage
    from backend.models.kanal import Kanal

    U1, U2 = T1 + timedelta(hours=3, minutes=20), T1 + timedelta(days=1, hours=8, minutes=20)
    lab = Lab(T1)
    _alt_zaehlt_wieder_ab(lab, U2.replace(minute=0))          # A zählt nach dem späteren Wechsel wieder (wie in aba_nachtrag)
    w = await _welt(db, monkeypatch, lab)
    await _betrieb(w, T1 - timedelta(hours=30), U1.replace(minute=0))
    await _wechsel_ohne_grund(w, U1)
    await _betrieb(w, U1.replace(minute=0) + timedelta(hours=1), U2.replace(minute=0))
    _ha_bis(w, _ep(U2.replace(minute=0)) - STUNDE)
    await _umstellen_auf(w, monkeypatch, U2, ALT)
    await _betrieb(w, U2.replace(minute=0) + timedelta(hours=1), U2.replace(minute=0) + timedelta(hours=6))
    k = (await db.execute(select(Kanal).where(Kanal.key == KEY))).scalar_one()
    tag2 = (T1 + timedelta(days=1)).replace(hour=0)
    vorher_q = await _quellen(db)
    vorher_tag = (await lesen.zeitraum(db, k, _ep(U2.replace(minute=0)) - STUNDE, _ep(tag2 + timedelta(days=1)))).delta
    row = (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.sensor_key == KEY,
                                                           ZuordnungWechsel.grund.is_(None)))).scalar_one()
    await grund_nachtragen(w.a.id, row.id, GrundNachtragRequest(grund="fortsetzung"), db)
    await _laeufe()
    _frisch(w)
    nachher_q = await _quellen(db)
    spaet = [q for q in vorher_q if q[1] == ALT and q[0] >= _ep(U2.replace(minute=0)) - 2 * STUNDE]
    assert spaet and [q[:2] for q in nachher_q if q[:2] == spaet[0][:2]] == [spaet[0][:2]]
    k = (await db.execute(select(Kanal).where(Kanal.key == KEY))).scalar_one()
    nachher_tag = (await lesen.zeitraum(db, k, _ep(U2.replace(minute=0)) - STUNDE, _ep(tag2 + timedelta(days=1)))).delta
    assert nachher_tag == pytest.approx(vorher_tag)
    assert (await konsistenz_anlage(w.sitzungen, w.a.id, ha_svc=w.svc)).korrigiert == []
    nachtrag = (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.sensor_key == KEY,
                                                                ZuordnungWechsel.herkunft == "nachtrag"))).scalar_one()
    assert nachtrag.ansatz == "beide"           # A zählt erst ab dem späteren Wechsel wieder: keine Überlappung mit B (Mutante D15)


def _alt_zaehlt_wieder_ab(lab: Lab, ab: datetime) -> None:
    """Der alte Sensor (A) zählt ab ``ab`` wieder 1,0 kWh/h (die Zeilen der Attrappe ab dort neu)."""
    s, neu = 0.0, {}
    for e, (z, _s) in sorted(lab.alt.items()):
        z = 1.0 if e >= _ep(ab) else z
        s += z
        neu[e] = (z, round(s, 6))
    lab.alt = neu


@pytest.mark.parametrize("stoerung", [None, "fuellen_scheitert"])
async def test_ak_n3_mitruecken_auch_wenn_das_fuellen_scheitert(db, monkeypatch, stoerung):
    """a-K N3: wie N2; scheitert das Füllen nach dem Commit des Nachtrags, holt der Lauf es nach — und rückt die spätere
    Quelle mit (Grenze, Kanalwert davor und Versätze stehen im Auftrag). In beiden Wegen zeigt der Kanal über die Grenze
    dieselbe Menge wie vor dem Nachtrag (Mutante E3)."""
    from backend.api.routes.sensorwechsel import GrundNachtragRequest, grund_nachtragen
    from backend.models.kanal import Kanal
    from backend.services.kanal import lesen
    from backend.services.zuordnung_wechsel import korrektur_lauf
    import backend.services.kanal.korrektur as kk

    w = await _welt(db, monkeypatch, Lab(T1))
    U1, U2 = T1 + timedelta(hours=3, minutes=20), T1 + timedelta(days=1, hours=8, minutes=20)
    await _betrieb(w, T1 - timedelta(hours=30), U1.replace(minute=0))
    await _wechsel_ohne_grund(w, U1)
    await _betrieb(w, U1.replace(minute=0) + timedelta(hours=1), U2.replace(minute=0))
    _ha_bis(w, _ep(U2.replace(minute=0)) - STUNDE)
    await _umstellen_auf(w, monkeypatch, U2, ALT)
    await _betrieb(w, U2.replace(minute=0) + timedelta(hours=1), U2.replace(minute=0) + timedelta(hours=4))
    fenster = (_ep(U2.replace(minute=0)) - 2 * STUNDE, _ep(U2.replace(minute=0)) + 3 * STUNDE)

    async def ueber_die_grenze():
        k = (await db.execute(select(Kanal).where(Kanal.key == KEY))).scalar_one()
        return (await lesen.zeitraum(db, k, *fenster)).delta
    vorher = await ueber_die_grenze()
    n = {"x": 0}
    if stoerung:
        echt = kk.fuelle_kanal

        async def einmal_nicht(*a, **k):
            n["x"] += 1
            if n["x"] == 1:
                raise RuntimeError("HA weg")
            return await echt(*a, **k)
        monkeypatch.setattr(kk, "fuelle_kanal", einmal_nicht)
    row = (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.sensor_key == KEY,
                                                           ZuordnungWechsel.grund.is_(None)))).scalar_one()
    await grund_nachtragen(w.a.id, row.id, GrundNachtragRequest(grund="fortsetzung"), db)
    await _laeufe()
    _frisch(w)
    for lauf in await korrektur_lauf.offene_laeufe(db):           # der stündliche Anstoß
        t = korrektur_lauf.starten(lauf, sitzungen=w.sitzungen)
        if t is not None:
            await t
    _frisch(w)
    assert vorher is not None and await ueber_die_grenze() == pytest.approx(vorher)
    assert n["x"] >= (2 if stoerung else 0)


async def test_ak_n4_zurueck_in_derselben_stunde_heben_sich_auf(db, monkeypatch):
    """a-K N4: A → B um 10:20 und zurück um 10:40, beide «bleiben», ohne eigenen Stand von B dazwischen: die zwei Zeilen
    heben sich auf — keine Naht in der Reihe, der Tag zählt nur A wie HA."""
    from backend.services.zuordnung_wechsel.zeitpunkt import fortsetzungs_naehte

    w = await _welt(db, monkeypatch, Lab(T1, vorgeschichte=True, schnitt=T1 + timedelta(hours=3)))
    U1 = T1 + timedelta(hours=3, minutes=20)
    await _bis_zur_umstellung(w, U1)
    await _umstellen_auf(w, monkeypatch, U1, NEU)
    await _umstellen_auf(w, monkeypatch, U1 + timedelta(minutes=20), ALT)
    zeilen = (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.sensor_key == KEY)
                               .order_by(ZuordnungWechsel.id))).scalars().all()
    assert [z.aufgehoben_durch for z in zeilen] == [zeilen[1].id, zeilen[0].id]
    zw.vergiss(db)
    assert await fortsetzungs_naehte(db, w.a.id, KEY) == []


async def test_ak_n8_e12_abgeleitete_kanaele_ab_g_verworfen(db, monkeypatch):
    """Mutante E12: das Ansetzen verwirft die abhängigen abgeleiteten Kanäle ab G (hier der PV-Anteil der Heimladung der
    Wallbox) — ein Wert, der aus dem alten Kanal gerechnet war, bleibt nicht stehen."""
    from backend.models.kanal import FAMILIE_ABGELEITET, Kanal, KanalStatistik

    w = await _welt(db, monkeypatch, Lab(T1))
    await _bis_zur_umstellung(w, U1030)
    k = Kanal(anlage_id=w.a.id, key="abgeleitet:inv:2:ladung_pv_kwh", einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=_ep(T1) + i * STUNDE, sum=999.0, state=None,
                               familie=FAMILIE_ABGELEITET) for i in range(-2, 3)])
    await db.commit()
    await _umstellen(w, monkeypatch, U1030)
    rest = [(z.start_ts, z.sum) for z in (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id)))
            .scalars()]
    assert all(t < _ep(T1) for t, s_ in rest if s_ == 999.0) and any(t < _ep(T1) for t, _s in rest)


async def test_ak_ungeprueft_b_beide_mit_weit_zurueckliegender_erster_zeile(db, monkeypatch):
    """«Ungeprüft» (b): der neue Sensor führt seine erste Zeile schon 7 Tage vor dem Wechsel, der alte zählte seitdem nichts
    — keine Überlappung, ``beide`` mit G = die erste Zeile des neuen: eedc zählt den neuen ab dort (wie Home Assistant mit
    zwei Sensoren); die Prüf-Antwort nennt Stunde und Tage, die eedc dafür neu liest und bildet."""
    from backend.services.zuordnung_wechsel.ansatz import lage
    from backend.services.zuordnung_wechsel.bleiben import pruef_zeile

    lab = Lab(T1)
    erste = _ep(T1) - 7 * 86400                          # nach dem Beginn der Statistik des alten (31.10.)
    s_, neu = 0.0, {}
    for e in range(erste, lab.ende, STUNDE):
        s_ += 0.5
        neu[e] = (0.5, round(s_, 6))
    lab.neu = neu
    lab.alt = {e: ((z if e < erste else 0.0), 0.0) for e, (z, _s) in lab.alt.items()}
    s_ = 0.0
    for e in sorted(lab.alt):
        s_ += lab.alt[e][0]
        lab.alt[e] = (lab.alt[e][0], round(s_, 6))
    w = await _welt(db, monkeypatch, lab)
    _ha_bis(w, _ep(T1) + 3 * STUNDE)
    zeile = pruef_zeile(w.a.id, KEY, {"art": "ha", "entity_id": ALT}, {"art": "ha", "entity_id": NEU},
                        ab_ts=T1 + timedelta(hours=4), erklaert_ts=T1 + timedelta(hours=3, minutes=30))
    la = await lage(db, zeile, ha_svc=w.svc, jetzt=T1 + timedelta(hours=4, minutes=5))
    assert (la.art, la.ueberlappung, la.g) == ("beide", False, datetime.fromtimestamp(erste))


async def test_ak_ungeprueft_c_erste_zeile_mit_grosser_summe_zeigt_was_ha_fuehrt(db, monkeypatch):
    """«Ungeprüft» (c): beginnt die Statistik des neuen mit einer großen Summe (500,7 in der ersten Zeile), zählt eedc am
    Tag des Wechsels diese erste Zeile ab 0 — so wie Home Assistant sie als ``change`` führt (Quellentreue); der Tag zeigt
    15,3 + 500. Der Befund «Zählerstand springt» (Lauf c) ist der Ort, das zu melden."""
    from backend.models.kanal import Kanal
    from backend.services.kanal import lesen

    lab = Lab(T1)
    lab.neu = {e: (z + (500.0 if e == lab.e1 else 0.0), s_ + 500.0) for e, (z, s_) in lab.neu.items()}
    w = await _welt(db, monkeypatch, lab)
    await _bis_zur_umstellung(w, U1030)
    await _umstellen(w, monkeypatch, U1030)
    await _betrieb(w, U1030.replace(minute=0) + timedelta(hours=1), ende(U1030))
    k = (await db.execute(select(Kanal).where(Kanal.key == KEY))).scalar_one()
    tag = (await lesen.zeitraum(db, k, _ep(T1.replace(hour=0)), _ep(T1.replace(hour=0) + timedelta(days=1)))).delta
    assert tag == pytest.approx(15.3 + 500.0)
