"""Sensorwechsel mit Grund, Korrekturrunde 3b-K (Bauplan §11 Nr. 44–55) — Proben zu den Funden der Nachmessung 3b und zu den
Mutanten, die dort unbemerkt blieben.

**Einstieg «Zähler getauscht»** (Nr. 44/45/49): der Weg folgt der Quelle des Kanals zur Stunde des Tauschs (ein früherer
Spiegel-Abschnitt eines heute über MQTT kommenden Felds ⇒ Weg in Home Assistant, nichts eingetragen, kein 500); ein Nachtrag, den
der Kanal nicht tragen kann ⇒ 422 mit Satz; vor dem ersten eigenen Wert ⇒ nichts eingetragen, der Satz nennt den ersten Wert;
verworfene Zeit ⇒ nichts; die Vorschau nennt den bisherigen Zuwachs der Stunde. **Korrektur-Lauf** (Nr. 46): offene Läufe stößt
der Stundenlauf an (nie doppelt), «Füllen: …» steht je Lauf einmal, die Werkbank holt bei offenem Lauf nach und verwirft nichts
weiter (Fall A → fälschlich B → A der Nachmessung). **Angaben des Dialogs** (Nr. 47/48/54): Zählerstand (``state``) statt
Statistik-Summe, der Kanal in der Vorschau, Vorgabe «falsch seit» = der Wechsel, der die bisherige Quelle brachte. **Lese-Route**
der laufenden Läufe (Nr. 50). **Preset** prüft den Grund (Nr. 54). Dazu je unbemerktem Mutanten der Nachmessung eine Probe
(Name im Docstring der Probe).

Schwesterdateien: test_sensorwechsel_s3b_abfrage.py (Abfrage in allen Wegen), test_sensorwechsel_s3_korrektur.py (der Dienst),
test_sensorwechsel_s2_naht.py (Naht und Nachtrag bei MQTT).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.models.activity_log import ActivityLog
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.models.settings import Settings
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import abfrage
from backend.services.zuordnung_wechsel import korrektur as kr
from backend.services.zuordnung_wechsel import korrektur_lauf as kl
from backend.services.zuordnung_wechsel import zaehler_getauscht as zg
from backend.tests import ha_lts_helfer
from backend.tests.test_kanal_nachfuellen import (  # noqa: F401 — Fixtures
    ZEIT,
    _ts,
    datei,
    ha,
)
from backend.tests.test_sensorwechsel_s1_verzeichnen import NETZ, NETZ_KEY, _anlage, _zeilen
from backend.tests.test_sensorwechsel_s3b_abfrage import GW, GW_KEY, _ablehnung, _pruefe, _setze

A = {"art": "ha", "entity_id": "sensor.a"}
B = {"art": "ha", "entity_id": "sensor.b"}
KEINE = {"art": "keine"}


def _klassisch() -> dict:
    """Klassische Zuordnung ``sensor.a`` — je Probe neu (die Routen ändern das Mapping an Ort und Stelle)."""
    return {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}}


def _wechsel(aid, ab: datetime, vorher, nachher, grund=None, aufgehoben_durch=None) -> ZuordnungWechsel:
    return ZuordnungWechsel(anlage_id=aid, sensor_key=NETZ_KEY, erklaert_ts=ab - timedelta(minutes=10), ab_ts=ab,
                            vorher=vorher, nachher=nachher, grund=grund, herkunft="wechsel",
                            aufgehoben_durch=aufgehoben_durch)


async def _kanal(db, aid, quellen, zeilen, key=NETZ_KEY) -> Kanal:
    """Ein Zähler-Kanal mit ``quellen = [(beginn, familie, kennung, verworfen?)]`` und ``zeilen = [(stunde, sum, state)]``."""
    k = Kanal(anlage_id=aid, key=key, einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    for beginn, familie, kennung, verworfen in quellen:
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=_ts(beginn), familie=familie, statistic_id=kennung, offset=0.0,
                           verworfen_ts=_ts(beginn) if verworfen else None))
    for t, s, st in zeilen:
        db.add(KanalStatistik(kanal_id=k.id, start_ts=_ts(t), sum=s, state=st, familie="spiegel"))
    await db.flush()
    return k


async def _getauscht(db, aid, t: datetime, *, eintragen: bool = False):
    from backend.api.routes.sensorwechsel import ZaehlerGetauschtRequest, pruefe_zaehler_getauscht, zaehler_getauscht

    fn = zaehler_getauscht if eintragen else pruefe_zaehler_getauscht
    return await fn(aid, NETZ, ZaehlerGetauschtRequest(getauscht_am=t), db)


# ═══ Nr. 44 — Einstieg: Weg nach der Quelle des Kanals zur Stunde des Tauschs ═════════════════════════════════════════

T0 = datetime(2026, 11, 1, 0)          # Spiegel ab hier, Mitschrift ab T0 + 6 h


async def _mqtt_heute_spiegel_frueher(db, *, spiegel_verworfen=False):
    """Feld heute MQTT-Inbound (keine HA-Zuordnung), Kanal: Spiegel ``sensor.netz_alt`` ab T0, Mitschrift ab T0 + 6 h."""
    a = await _anlage(db, werte=(NETZ_KEY,))                          # eigener Wert am 01.09.2026 12:00 (Reihe)
    zeilen = [(T0 + timedelta(hours=h), 100.0 + h, 100.0 + h) for h in range(6)]
    zeilen += [(T0 + timedelta(hours=h), 106.0 + h, 106.0 + h) for h in range(6, 10)]
    await _kanal(db, a.id, [(T0, "spiegel", "sensor.netz_alt", spiegel_verworfen),
                            (T0 + timedelta(hours=6), "mitschrift", "netzbezug_kwh", False)], zeilen)
    await db.commit()
    return a.id


async def test_einstieg_frueherer_spiegel_abschnitt_weg_home_assistant_kein_500(db):
    """F1 der Nachmessung (vorher ``ValueError`` ⇒ 500): Tausch in der Spiegel-Zeit eines heute über MQTT kommenden Felds ⇒
    Weg in Home Assistant (der Konsistenzlauf gleicht den früheren Spiegel-Abschnitt weiter gegen HA ab), nichts eingetragen.
    Mutant Z12 (Spiegel gilt nicht als Spiegel) ⇒ hier ``fortsetzung``."""
    aid = await _mqtt_heute_spiegel_frueher(db)
    p = await _getauscht(db, aid, T0 + timedelta(hours=2, minutes=20))
    assert (p["weg"], p["eintragen"], p["saetze"]) == ("home_assistant", False, [zg.SATZ_HA])
    r = await _getauscht(db, aid, T0 + timedelta(hours=2, minutes=20), eintragen=True)
    assert r["eingetragen"] is False and await _zeilen(db, aid) == []
    # Gegenprobe: in der Mitschrift-Zeit trägt derselbe Einstieg ein, mit Nachtrag an der Stunde des Tauschs
    p = await _getauscht(db, aid, T0 + timedelta(hours=8, minutes=5))
    assert (p["weg"], p["eintragen"]) == ("fortsetzung", True) and len(p["saetze"]) == 4
    assert p["saetze"][-1] == zg.SATZ_TAG_FEST                            # 4-K, «Zu §13» Nr. 87: Tausch vor dem laufenden Tag


async def test_einstieg_vor_dem_kanal_fortsetzung_ohne_nachtrag(db):
    """Vor der ersten Quelle des Kanals lesen die Leser die Reihe — Fortsetzung ohne Nachtrag (kein Satz zur Stunde)."""
    aid = await _mqtt_heute_spiegel_frueher(db)
    p = await _getauscht(db, aid, datetime(2026, 10, 15, 9, 30))
    assert (p["weg"], p["eintragen"], len(p["saetze"])) == ("fortsetzung", True, 2)
    assert p["saetze"][-1] == zg.SATZ_TAG_FEST                            # 4-K, «Zu §13» Nr. 87


async def test_einstieg_verworfene_zeit_nichts_einzutragen(db):
    aid = await _mqtt_heute_spiegel_frueher(db, spiegel_verworfen=True)
    t = T0 + timedelta(hours=2, minutes=20)
    p = await _getauscht(db, aid, t)
    assert (p["weg"], p["eintragen"]) == ("nicht_moeglich", False)
    assert p["saetze"] == [zg.SATZ_NICHT_MOEGLICH.format(zeit=t.strftime("%d.%m.%Y %H:%M"))]


async def test_einstieg_nachtrag_kann_nicht_getragen_werden_422_statt_500(db, monkeypatch):
    """Wirft der Nachtrag (der Kanal kann ihn zu dieser Zeit nicht tragen), antwortet die Route 422 mit dem Satz und lässt
    keine Wechsel-Zeile stehen."""
    from backend.services.kanal import naht

    async def wirft(*_a, **_k):
        raise ValueError("Nachtrag nur für einen Kanal der eigenen Summe")
    monkeypatch.setattr(naht, "nachtrag_fortsetzung", wirft)
    aid = await _mqtt_heute_spiegel_frueher(db)
    t = T0 + timedelta(hours=8, minutes=5)
    e = await _ablehnung(_getauscht(db, aid, t, eintragen=True))
    assert e.status_code == 422 and e.detail == zg.SATZ_NICHT_MOEGLICH.format(zeit=t.strftime("%d.%m.%Y %H:%M"))
    assert await _zeilen(db, aid) == []


async def test_einstieg_vor_dem_ersten_wert_nicht_eingetragen(db):
    """Nr. 45 (F2): «Getauscht am» vor dem ersten eigenen Wert ⇒ kein Sprung zu überbrücken, der Satz nennt den ersten Wert,
    «Eintragen» schreibt nichts."""
    aid = await _mqtt_heute_spiegel_frueher(db)
    p = await _getauscht(db, aid, datetime(2020, 1, 1, 8))
    assert (p["weg"], p["eintragen"]) == ("vor_erstem_wert", False)
    assert p["saetze"] == [zg.SATZ_VOR_ERSTEM_WERT.format(zeit="01.09.2026 12:00")]
    r = await _getauscht(db, aid, datetime(2020, 1, 1, 8), eintragen=True)
    assert r["eingetragen"] is False and await _zeilen(db, aid) == []
    # Grenze: die Stunde des ersten Werts selbst ist nichts davor (ab_ts = 12:00 ⇒ erster Wert ≥ ab)
    assert (await _getauscht(db, aid, datetime(2026, 9, 1, 11, 30)))["weg"] == "vor_erstem_wert"
    assert (await _getauscht(db, aid, datetime(2026, 9, 1, 12, 30)))["weg"] == "fortsetzung"


async def test_einstieg_ohne_quelle_und_schon_eingetragen(db):
    """Mutanten Z09 (Feld mit «Keine» trägt ein) und Z10 (``eintragen`` trotz «schon eingetragen»); Z04 nebenbei: ``ab_ts``
    ist die volle Stunde. R04: «Eintragen» schreibt eine Protokollzeile."""
    a = await _anlage(db, {"quellen": {NETZ: {"quelle": "keine"}}})
    await db.commit()
    p = await _getauscht(db, a.id, datetime(2026, 10, 1, 9, 15))
    assert (p["weg"], p["eintragen"], p["saetze"]) == ("keine_quelle", False, [zg.SATZ_KEINE_QUELLE])

    aid = await _mqtt_heute_spiegel_frueher(db)
    t = datetime(2026, 10, 15, 9, 30)
    r = await _getauscht(db, aid, t, eintragen=True)
    assert r["eingetragen"] is True
    (w,) = await _zeilen(db, aid)
    assert (w.erklaert_ts, w.ab_ts) == (t, datetime(2026, 10, 15, 10))
    log = (await db.execute(select(ActivityLog).where(ActivityLog.anlage_id == aid))).scalars().all()
    assert [x.aktion for x in log] == ["Zähler getauscht (gleiche Quelle)"] and "Fortsetzung ab 15.10.2026 09:30" in log[0].details
    nochmal = await _getauscht(db, aid, t)
    assert (nochmal["eintragen"], nochmal["saetze"]) == (False, [zg.SATZ_SCHON])


# ═══ Nr. 47 — Zählerstand statt Statistik-Summe; Nr. 54 — Vorgabe «falsch seit» ═════════════════════════════════════════

async def test_dialog_stand_alt_ist_der_zaehlerstand_und_erster_wert_aus_dem_kanal(db):
    """F4: der letzte Stand der bisherigen Quelle ist ``state`` (5 001), nicht ``sum`` (101). Mutanten A17 (erster Wert und
    Tage nie aus dem Kanal) und A18 (``stand_alt`` immer leer)."""
    a = await _anlage(db, _klassisch(), werte=())
    await _kanal(db, a.id, [(datetime(2026, 9, 30, 22), "spiegel", "sensor.a", False)],
                 [(datetime(2026, 9, 30, 22), 100.0, 5000.0), (datetime(2026, 10, 1, 3), 101.0, 5001.0),
                  (datetime(2026, 10, 1, 4), 102.0, None)])
    await db.commit()
    p = await _pruefe(db, a.id, quelle="ha_app", entity_id="sensor.b")
    assert p["grund_erforderlich"] is True
    assert (p["erster_wert"], p["tage"], p["stand_alt"]) == ("2026-09-30T22:00:00", 2, 5001.0)
    assert p["vorgabe_falsch_seit"] == "2026-09-30T22:00:00"          # Beginn der Quelle im Kanal


async def test_stand_neu_ist_der_zaehlerstand_in_der_einheit_des_kanals(ha):
    """F4: der Stand der neuen HA-Entität ist ihr ``state`` (Attrappe: ``state = sum − 300``), Wh in kWh umgerechnet."""
    from backend.services.kanal.angaben import zaehlerstand_ha_jetzt

    svc, reihen = ha
    letzte = reihen["sensor.einsp"][max(reihen["sensor.einsp"])]
    assert await zaehlerstand_ha_jetzt(svc, 0, "sum", "sensor.einsp") == pytest.approx(letzte["state"])
    assert letzte["state"] != letzte["sum"]
    wh = reihen["sensor.netz_wh"][max(reihen["sensor.netz_wh"])]
    assert await zaehlerstand_ha_jetzt(svc, 0, "sum", "sensor.netz_wh") == pytest.approx(wh["state"] / 1000.0)
    assert await abfrage._stand_neu(svc, None, "basis:einspeisung", {"art": "ha", "entity_id": "sensor.einsp"}) \
        == pytest.approx(letzte["state"])
    assert await abfrage._stand_neu(svc, None, "basis:einspeisung", {"art": "mqtt", "mqtt_key": "x"}) is None


async def test_vorgabe_falsch_seit_ist_der_wechsel_der_die_quelle_brachte(db):
    """Nr. 54: jüngster Wechsel mit ``nachher`` = bisherige Quelle — kein → «Keine», kein «Zähler getauscht» (``vorher =
    nachher``). Mutant A13 (ältester Wechsel) ⇒ 01.08.; der Stand vor 3b-K (jüngster überhaupt) ⇒ 01.09."""
    a = await _anlage(db, _klassisch())
    aid = a.id
    for ab, vorher, nachher, grund in ((datetime(2026, 8, 1, 10), {"art": "ha", "entity_id": "sensor.x"}, A, "fortsetzung"),
                                       (datetime(2026, 8, 10, 10), A, KEINE, None),
                                       (datetime(2026, 8, 20, 10), KEINE, A, None),
                                       (datetime(2026, 9, 1, 10), A, A, "fortsetzung")):
        db.add(_wechsel(aid, ab, vorher, nachher, grund))
    await db.commit()
    p = await _pruefe(db, aid, quelle="ha_app", entity_id="sensor.b")
    assert p["vorgabe_falsch_seit"] == "2026-08-20T10:00:00"


async def test_vorgabe_falsch_seit_im_kanal_ueber_fortsetzungen_derselben_kennung(db):
    """Ohne verzeichneten Wechsel: Beginn der Folge gleicher Kennung im Kanal — eine Naht oder ein Nachtrag derselben Quelle
    (neue Quellzeile) verschiebt die Vorgabe nicht; eine verworfene Quelle davor beendet die Folge."""
    a = await _anlage(db, _klassisch(), werte=())
    await _kanal(db, a.id, [(datetime(2026, 9, 1, 0), "spiegel", "sensor.alt", True),
                            (datetime(2026, 9, 5, 0), "spiegel", "sensor.a", False),
                            (datetime(2026, 9, 9, 7), "spiegel", "sensor.a", False)],
                 [(datetime(2026, 9, 5, 0) + timedelta(hours=h), 1.0 + h, 1.0 + h) for h in range(3)])
    await db.commit()
    assert (await _pruefe(db, a.id, quelle="ha_app", entity_id="sensor.b"))["vorgabe_falsch_seit"] == "2026-09-05T00:00:00"


# ═══ Wann gefragt wird — die letzte Quelle mit Werten (Mutanten A02, A04, A05, A06) ════════════════════════════════════

async def test_heute_keine_ohne_verzeichneten_wechsel_fragt(db):
    """E-7: unbekannte letzte Quelle (heute «Keine», kein Wechsel verzeichnet) ⇒ gefragt. Mutant A02."""
    a = await _anlage(db, {"quellen": {NETZ: {"quelle": "keine"}}})
    await db.commit()
    assert (await _pruefe(db, a.id, quelle="ha_app", entity_id="sensor.b"))["grund_erforderlich"] is True


async def test_letzte_quelle_mit_werten_jüngste_zeile_nachher_vor_vorher(db):
    """Heute «Keine» (ohne Zeile); Zeilen X → A (01.08.), A → B (01.09.) ⇒ die letzte Quelle mit Werten ist B: → B fragt
    nicht, → A fragt. Mutanten A04 (älteste Zeile zuerst ⇒ A) und A06 (``vorher`` vor ``nachher`` ⇒ A)."""
    aid = (await _anlage(db, {"quellen": {NETZ: {"quelle": "keine"}}})).id
    db.add(_wechsel(aid, datetime(2026, 8, 1, 10), {"art": "ha", "entity_id": "sensor.x"}, A, "fortsetzung"))
    db.add(_wechsel(aid, datetime(2026, 9, 1, 10), A, B, "fortsetzung"))
    await db.commit()
    assert (await _pruefe(db, aid, quelle="ha_app", entity_id="sensor.b"))["grund_erforderlich"] is False
    assert (await _pruefe(db, aid, quelle="ha_app", entity_id="sensor.a"))["grund_erforderlich"] is True


async def test_letzte_quelle_mit_werten_ohne_aufgehobene_zeilen(db):
    """Eine aufgehobene Zeile A → B zählt nicht: die letzte Quelle mit Werten ist A. Mutant A05."""
    aid = (await _anlage(db, {"quellen": {NETZ: {"quelle": "keine"}}})).id
    erste = _wechsel(aid, datetime(2026, 8, 1, 10), {"art": "ha", "entity_id": "sensor.x"}, A, "fortsetzung")
    db.add(erste)
    await db.flush()
    db.add(_wechsel(aid, datetime(2026, 9, 1, 10), A, B, None, aufgehoben_durch=erste.id))
    await db.commit()
    assert (await _pruefe(db, aid, quelle="ha_app", entity_id="sensor.a"))["grund_erforderlich"] is False
    assert (await _pruefe(db, aid, quelle="ha_app", entity_id="sensor.b"))["grund_erforderlich"] is True


# ═══ Korrektur mit Grund: Grenzen und Routen (Mutanten A07, A09, A10, D03, D06, D07) ════════════════════════════════════

def test_intervall_endet_an_der_naechsten_vollen_stunde_und_falsch_seit_davor():
    """A09: ``ab`` = die volle Stunde nach der Änderung (10:20 ⇒ 11:00), nicht die vergangene. A07: «falsch seit» in der
    Stunde ``ab`` ist nicht erlaubt, die Stunde davor schon (abgerundet)."""
    f = abfrage.Frage(NETZ_KEY, A, B, True)
    jetzt = datetime(2026, 10, 1, 10, 20)
    assert abfrage.korrektur_auftrag(1, f, datetime(2026, 9, 1, 7, 30), jetzt).ab == datetime(2026, 10, 1, 11)
    assert abfrage.korrektur_auftrag(1, f, datetime(2026, 9, 1, 7, 30), jetzt).falsch_seit == datetime(2026, 9, 1, 7)
    with pytest.raises(abfrage.GrundFehlt):
        abfrage._pruefe_falsch_seit(f, datetime(2026, 10, 1, 11, 0), jetzt, "x")
    abfrage._pruefe_falsch_seit(f, datetime(2026, 10, 1, 10, 59), jetzt, "x")


async def test_ungueltiger_grund_gilt_nicht_als_grund(db):
    """A10: der Dienst nimmt nur «fortsetzung»/«korrektur»; D03: die Feld-Route antwortet auf einen anderen 400."""
    from backend.services.zuordnung_wechsel.verzeichnen import momentaufnahme

    from backend.models.anlage import Anlage

    aid = (await _anlage(db, _klassisch())).id
    await db.commit()
    e = await _ablehnung(_setze(db, aid, quelle="ha_app", entity_id="sensor.b", grund="quatsch"))
    assert e.status_code == 400 and e.detail == "Unbekannter Grund: quatsch"
    await db.rollback()
    a = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    vorher = await momentaufnahme(db, a)
    a.sensor_mapping = {**_klassisch(), "quellen": {NETZ: {"quelle": "ha_app", "entity_id": "sensor.b"}}}
    with pytest.raises(abfrage.GrundFehlt):
        await abfrage.vollziehe(db, a, vorher, {abfrage.ALLE: ("quatsch", None)})


async def test_feld_route_ruft_nach_dem_commit(db, monkeypatch):
    """D06: nach dem Commit füllt ``nach_dem_commit`` den Kanal und startet den Lauf — die Feld-Route ruft es."""
    gerufen = []

    async def spion(v):
        gerufen.append(v)
    monkeypatch.setattr(abfrage, "nach_dem_commit", spion)
    a = await _anlage(db, _klassisch())
    await _setze(db, a.id, quelle="ha_app", entity_id="sensor.b", grund="korrektur", falsch_seit=datetime(2026, 8, 1))
    assert len(gerufen) == 1 and gerufen[0].korrekturen


async def test_pruef_route_korrektur_vorschau_nur_bei_frage(db):
    """D07: → «Keine» wird ohne Frage verzeichnet — die Prüf-Route liefert dafür keine Korrektur-Vorschau."""
    a = await _anlage(db, _klassisch())
    await db.commit()
    p = await _pruefe(db, a.id, quelle="keine", grund="korrektur", falsch_seit=datetime(2026, 8, 1))
    assert (p["grund_erforderlich"], p["verzeichnet"], p["korrektur"]) == (False, True, None)


async def test_dialog_vorschau_nennt_den_kanal_vor_dem_rueckweg(db, monkeypatch):
    """Nr. 48: die Vorschau des Dialogs trägt die Kanal-Sätze vor dem Satz zum Rückweg."""
    async def kanal(_la, _svc, *, bis_zum_wechsel=False):
        assert bis_zum_wechsel is False          # beim Wechsel endet das Intervall jetzt (4-K: im Nachtrag am Wechsel)
        return ["KANAL"]
    monkeypatch.setattr(kr, "kanal_saetze", kanal)
    a = await _anlage(db, _klassisch())
    await db.commit()
    p = await _pruefe(db, a.id, quelle="ha_app", entity_id="sensor.b", grund="korrektur", falsch_seit=datetime(2026, 8, 1))
    s = p["korrektur"]["saetze"]
    assert s[-2:] == ["KANAL", kr.SATZ_RUECKWEG_OHNE]


class _Kennzahlen:
    is_available = True

    def __init__(self, erste_ts):
        self.erste_ts = erste_ts

    def get_stundenzeilen_kennzahlen(self, _eid, _von, _bis):
        return {"anzahl": 0 if self.erste_ts is None else 5, "erste_ts": self.erste_ts}


def _la(nachher, *, w0=None, zeilen=0, zaehlerstaende=0):
    return SimpleNamespace(nicht_startbar=None, auftrag=SimpleNamespace(nachher=nachher),
                           kanal=SimpleNamespace(w0=w0, zeilen=zeilen), zaehlerstaende=zaehlerstaende, rohstaende=0)


async def test_kanal_saetze_ab_wann_home_assistant_die_geschichte_fuehrt():
    """Nr. 48: führt HA die Geschichte des richtigen Sensors erst nach ``w0``, nennt der Satz ab wann; ohne Geschichte der
    eigene Satz; beginnt sie bei ``w0``, kein Satz; MQTT holt nichts nach; ohne HA-Dienst kein Kanal-Satz."""
    w0 = _ts(datetime(2026, 8, 1, 0))
    spaeter = datetime(2026, 8, 5, 6)
    assert await kr.kanal_saetze(_la(B, w0=w0, zeilen=9), _Kennzahlen(_ts(spaeter))) == [
        kr.SATZ_KANAL_AB.format(zeit="05.08.2026 06:00")]
    assert await kr.kanal_saetze(_la(B, w0=w0, zeilen=9), _Kennzahlen(None)) == [kr.SATZ_KANAL_OHNE_GESCHICHTE]
    assert await kr.kanal_saetze(_la(B, w0=w0, zeilen=9), _Kennzahlen(w0)) == []
    assert await kr.kanal_saetze(_la({"art": "mqtt", "mqtt_key": "x"}, zaehlerstaende=3), None) == [kr.SATZ_KANAL_MQTT]
    assert await kr.kanal_saetze(_la({"art": "mqtt", "mqtt_key": "x"}), None) == []
    assert await kr.kanal_saetze(_la(B, w0=w0, zeilen=9), None) == []


# ═══ Preset (Mutanten P02, P03, P04, P05; Nr. 54 «Preset prüft den Grund») ═══════════════════════════════════════════════

def _preset_mapping() -> dict:
    return {"investitionen": {"2": {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.wb"}}}},
            "quellen": {GW: {"quelle": "ha_app", "entity_id": "sensor.wb"}}}


def _preset(aid, **kw):
    from backend.api.routes.mqtt_presets import ApplyPresetRequest

    return ApplyPresetRequest(preset_id="evcc_ladepunkt", anlage_id=aid, variablen={}, investition_id=2, **kw)


async def test_preset_unbekannter_grund_400(db):
    from backend.api.routes.mqtt_presets import apply_preset, pruefe_preset

    a = await _anlage(db, _preset_mapping(), werte=(GW_KEY,))
    await db.commit()
    for fn in (pruefe_preset, apply_preset):
        e = await _ablehnung(fn(_preset(a.id, gruende={GW_KEY: {"grund": "quatsch"}}), db))
        assert (e.status_code, e.detail) == (400, "Unbekannter Grund: quatsch")


async def test_preset_korrektur_traegt_falsch_seit_protokoll_und_nachlauf(db, monkeypatch):
    """P02 («falsch seit» geht verloren), P03 (kein ``nach_dem_commit``), P04 (kein Protokoll)."""
    from backend.api.routes.mqtt_presets import apply_preset

    gerufen = []

    async def spion(v):
        gerufen.append(v)
    monkeypatch.setattr(abfrage, "nach_dem_commit", spion)
    a = await _anlage(db, _preset_mapping(), werte=(GW_KEY,))
    aid = a.id
    await db.commit()
    await apply_preset(_preset(aid, gruende={GW_KEY: {"grund": "korrektur", "falsch_seit": datetime(2026, 8, 1, 7, 30)}}),
                       db)
    (w,) = [w for w in await _zeilen(db, aid) if w.sensor_key == GW_KEY]
    assert (w.grund, w.falsch_seit_ts) == ("korrektur", datetime(2026, 8, 1, 7))
    assert len(gerufen) == 1
    log = (await db.execute(select(ActivityLog.aktion).where(ActivityLog.anlage_id == aid))).scalars().all()
    assert "Preset angewendet: evcc_ladepunkt" in log


async def test_preset_korrektur_home_assistant_nicht_erreichbar_422(db, monkeypatch):
    """P05: HA eingerichtet, aber nicht erreichbar ⇒ 422 wie an der Feld-Route; nichts bleibt stehen."""
    from backend.api.routes.mqtt_presets import apply_preset

    def nicht(_svc=None):
        raise kr.KorrekturNichtStartbar("Home Assistant ist nicht erreichbar — …")
    monkeypatch.setattr(kr, "ha_dienst", nicht)
    a = await _anlage(db, _preset_mapping(), werte=(GW_KEY,))
    aid = a.id
    await db.commit()
    e = await _ablehnung(apply_preset(_preset(aid, gruende={GW_KEY: {"grund": "korrektur",
                                                                    "falsch_seit": datetime(2026, 8, 1)}}), db))
    assert e.status_code == 422 and "nicht erreichbar" in e.detail


# ═══ Korrektur-Lauf: Aufräumen, offener Lauf, Nachlauf, Fortschritt (K01–K03, K06, K09, K10, K15, K17, R03, R05) ══════════

async def _lauf(db, lauf, aid, key=NETZ_KEY, tage=(), **werte):
    """Ein Lauf-Zustand wie ``anlegen`` ihn schreibt — ohne dessen Aufräumen (die Proben stellen Alter mit festen Daten)."""
    db.add(Settings(key=kl.PRAEFIX + lauf, value={
        "anlage_id": aid, "sensor_key": key, "tage": [d.isoformat() for d in tage], "erledigt": 0, "status": kl.LAEUFT,
        "fehler": [], "behalten": 0, "beginn": "2026-11-17T08:00:00", "ende": None, "fuellen": werte.pop("fuellen", None)}))
    await db.flush()
    if werte:
        row = (await db.execute(select(Settings).where(Settings.key == kl.PRAEFIX + lauf))).scalar_one()
        row.value = {**row.value, **werte}
    await db.flush()


async def test_aufraeumen_nur_fertige_alte_auch_beim_anlegen_und_nach_dem_start(db, datei):
    """K01 (frisch fertige bleiben), K02 (laufende bleiben, auch mit einem alten ``ende``), K03 (``anlegen`` räumt auf),
    K17 (nach dem Start wird aufgeräumt). Feste Daten: «alt» liegt Jahre zurück, «frisch» einen Tag vor ``jetzt``."""
    a = await _anlage(db, werte=())
    jetzt = datetime(2026, 10, 15, 12)
    await _lauf(db, "frisch", a.id, status=kl.FERTIG, ende="2026-10-14T12:00:00")
    await _lauf(db, "laeuft", a.id, ende="2020-01-01T00:00:00")
    await _lauf(db, "alt", a.id, status=kl.FERTIG, ende="2026-09-14T12:00:00")
    await db.commit()
    assert await kl.aufraeumen(db, jetzt=jetzt) == 1
    assert [await kl.stand(db, x) is not None for x in ("frisch", "laeuft", "alt")] == [True, True, False]
    await _lauf(db, "alt2", a.id, status=kl.FERTIG, ende="2020-01-01T00:00:00")
    await db.commit()
    await kl.anlegen(db, "neu", a.id, NETZ_KEY, [])                    # K03
    assert await kl.stand(db, "alt2") is None

    sitzungen, _p, aid, _g = datei
    async with sitzungen() as s:
        await _lauf(s, "alt3", aid, status=kl.FERTIG, ende="2020-01-01T00:00:00")
    assert await kl.fortsetzen_nach_dem_start(warte_s=0, sitzungen=sitzungen) == []      # K17
    async with sitzungen() as s:
        assert await kl.stand(s, "alt3") is None


async def test_offener_lauf_prueft_anlage_und_schluessel(db):
    """K09/K15: der offene Lauf gehört zu Anlage UND Schlüssel."""
    a = await _anlage(db, werte=())
    await _lauf(db, "L", a.id, fuellen={"erledigt": False})
    await db.commit()
    assert await kl.offener_lauf(db, a.id, NETZ_KEY) == "L"
    assert await kl.offener_lauf(db, a.id + 1, NETZ_KEY) is None
    assert await kl.offener_lauf(db, a.id, "basis:einspeisung") is None


async def test_nachlauf_erledigt_mit_tagen_bleibt_laeuft(datei):
    """K10: ist der Nachlauf erledigt und stehen Tage aus, bleibt der Lauf ``laeuft`` (ohne Tage: ``fertig``)."""
    sitzungen, _p, aid, _g = datei
    async with sitzungen() as s:
        await _lauf(s, "T", aid, tage=[datetime(2026, 4, 2).date()], fuellen={"erledigt": False})
        await _lauf(s, "O", aid, fuellen={"erledigt": False})
    await kl.nachlauf_erledigt(sitzungen, "T", 3, 0)
    await kl.nachlauf_erledigt(sitzungen, "O", 3, 0)
    async with sitzungen() as s:
        assert ((await kl.stand(s, "T"))["status"], (await kl.stand(s, "O"))["status"]) == (kl.LAEUFT, kl.FERTIG)


async def test_fortschritt_route_fuellen_offen_und_erledigt(db):
    """R03 (``fuellen_offen`` verdreht) und R05 (``erledigt`` immer 0)."""
    from backend.api.routes.sensorwechsel import korrektur_lauf_stand

    a = await _anlage(db, werte=())
    await _lauf(db, "offen", a.id, tage=[datetime(2026, 4, 2).date()] * 3, fuellen={"erledigt": False}, erledigt=2)
    await _lauf(db, "gefuellt", a.id, fuellen={"erledigt": True})
    await db.commit()
    s = await korrektur_lauf_stand(a.id, "offen", db)
    assert (s["fuellen_offen"], s["erledigt"], s["tage"]) == (True, 2, 3)
    assert (await korrektur_lauf_stand(a.id, "gefuellt", db))["fuellen_offen"] is False


async def test_laufende_laeufe_der_anlage_lese_route(db):
    """Nr. 50: ``GET …/korrektur-laeufe`` nennt die laufenden Läufe dieser Anlage mit Feld-Bezeichnung — keine fertigen,
    keine fremden; 404 für eine unbekannte Anlage."""
    from backend.api.routes.sensorwechsel import korrektur_laeufe

    a = await _anlage(db, _klassisch(), werte=())
    await _lauf(db, "l1", a.id, beginn="2026-11-17T10:00:00")
    await _lauf(db, "l0", a.id, beginn="2026-11-17T09:00:00", fuellen={"erledigt": False})
    await _lauf(db, "f", a.id, status=kl.FERTIG, ende="2026-11-17T09:30:00")
    await _lauf(db, "fremd", a.id + 1)
    await db.commit()
    r = await korrektur_laeufe(a.id, db)
    assert [x["lauf"] for x in r] == ["l0", "l1"] and all(x["sensor_key"] == NETZ_KEY for x in r)
    assert r[0]["label"] and r[0]["label"] != NETZ_KEY
    with pytest.raises(HTTPException) as e:
        await korrektur_laeufe(999_999, db)
    assert e.value.status_code == 404


async def test_gleiche_korrektur_mit_anderer_richtiger_quelle_ist_eine_neue(db):
    """K06: dieselbe «falsch seit», aber eine andere richtige Quelle ⇒ eine zweite Korrektur-Zeile."""
    a = await _anlage(db, _klassisch())
    await db.commit()
    auftrag = kr.Auftrag(anlage_id=a.id, sensor_key=NETZ_KEY, falsch_seit=datetime(2026, 8, 1), ab=datetime(2026, 10, 1),
                         vorher=A, nachher=B)
    await kr.fuehre_aus(db, auftrag, ha_svc=None, jetzt=datetime(2026, 10, 1, 0, 30))
    await kr.fuehre_aus(db, kr.Auftrag(**{**auftrag.__dict__, "nachher": {"art": "ha", "entity_id": "sensor.c"}}),
                        ha_svc=None, jetzt=datetime(2026, 10, 1, 0, 40))
    assert len([w for w in await _zeilen(db, a.id) if w.grund == "korrektur" and w.nachher is not None]) == 2


# ═══ Nr. 46 — stündlicher Anstoß, ein Fehler-Eintrag, Werkbank bei offenem Lauf ════════════════════════════════════════

async def test_offene_laeufe_stuendlich_angestossen_nie_doppelt(datei, monkeypatch):
    sitzungen, _p, aid, _g = datei
    async with sitzungen() as s:
        await _lauf(s, "a", aid, fuellen={"erledigt": False})
        await _lauf(s, "b", aid, tage=[datetime(2026, 4, 2).date()])
        await _lauf(s, "f", aid, status=kl.FERTIG, ende="2026-11-17T09:30:00")
    aufrufe: list[str] = []
    halt = asyncio.Event()

    async def tage(_s, lauf):
        aufrufe.append(lauf)
        await halt.wait()
    monkeypatch.setattr(kl, "tage_neu_bilden", tage)
    try:
        assert sorted(await kl.offene_anstossen(sitzungen=sitzungen)) == ["a", "b"]
        await asyncio.sleep(0)
        assert await kl.offene_anstossen(sitzungen=sitzungen) == []        # laufen noch: nichts doppelt
        halt.set()
        for lauf in ("a", "b"):
            await kl._AUFGABEN[lauf]
        assert sorted(aufrufe) == ["a", "b"]
    finally:
        halt.set()
        kl._AUFGABEN.clear()


async def test_stundenlauf_stoesst_die_korrektur_laeufe_an(ha, datei, monkeypatch):
    import backend.core.database as dbmod
    import backend.services.ha_statistics_service as hss
    from backend.services import scheduler
    from backend.services.kanal import nachfuellen as nf

    svc, _ = ha
    sitzungen, _p, _aid, _g = datei
    gerufen = []
    monkeypatch.setattr(dbmod, "get_session", sitzungen)
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    monkeypatch.setattr(nf, "nachfuellen_anstossen", lambda: None)
    monkeypatch.setattr(kl, "offene_anstossen", lambda: gerufen.append(1))
    await scheduler.sensor_snapshot_job()
    assert gerufen == [1]


async def test_fuellen_fehler_je_lauf_einmal(datei, monkeypatch):
    """Der Fehler «Füllen: …» steht je Lauf einmal — der letzte Versuch ersetzt den vorigen; Fehler je Tag bleiben."""
    sitzungen, _p, aid, _g = datei
    versuch = iter(range(1, 10))

    async def wirft(*_a, **_k):
        raise RuntimeError(f"HA weg {next(versuch)}")
    monkeypatch.setattr(kr, "nachlauf_aus_auftrag", wirft)
    async with sitzungen() as s:
        await _lauf(s, "F", aid, fuellen={"erledigt": False}, fehler=[{"tag": "2026-04-02", "grund": "x"}])
    await kl.tage_neu_bilden(sitzungen, "F")
    z = await kl.tage_neu_bilden(sitzungen, "F")
    assert z["status"] == kl.LAEUFT
    assert z["fehler"] == [{"tag": "2026-04-02", "grund": "x"}, {"tag": None, "grund": "Füllen: RuntimeError: HA weg 2"}]


async def test_werkbank_bei_offenem_lauf_nachholen_nichts_weiter_verwerfen(ha, datei, monkeypatch):
    """Fall A → fälschlich B → zurück zu A (Nachmessung 3b, F3): das Füllen scheitert nach dem Commit; die Werkbank-Vorschau
    sagt nur, dass es aussteht (keine Zeile zum Verwerfen), und «Operation ausführen» holt es nach — die 240 gültigen Stunden
    des richtigen Sensors vor «falsch seit» bleiben. Mutant K18-Nachfolger: die Vorschau ohne den Nachhol-Satz."""
    from backend.services import verwerfen_vor_quellbeginn as vq
    from backend.services.kanal import korrektur as kk
    from backend.services.kanal.nachfuellen import nachfuellen_spiegel
    from backend.tests.test_werkbank_verwerfen_kommt_nicht_zurueck import _kanal as wk_kanal
    from backend.tests.test_werkbank_verwerfen_kommt_nicht_zurueck import _stundenlauf, _vor_t, _zuordnung

    svc, _r = ha
    sitzungen, _p, aid, _g = datei
    mid = ha_lts_helfer.sensor(svc, "sensor.falsch", "kWh")
    for i in range(24 * 40):
        ha_lts_helfer.zeile(svc, mid, ZEIT + timedelta(hours=i), state=9000.0 + i, sum_wert=9000.0 + i)
    f = ZEIT + timedelta(days=10)
    await nachfuellen_spiegel(sitzungen, aid, jetzt=f, ha_svc=svc)
    await _zuordnung(sitzungen, aid, einspeisung="sensor.falsch")
    await _stundenlauf(sitzungen, aid, svc, ZEIT + timedelta(days=20))
    monkeypatch.setattr(kr, "ha_dienst", lambda _s=None: svc)
    a = kr.Auftrag(anlage_id=aid, sensor_key="basis:einspeisung", falsch_seit=f, ab=ZEIT + timedelta(days=20),
                   vorher={"art": "ha", "entity_id": "sensor.falsch"}, nachher={"art": "ha", "entity_id": "sensor.einsp"})

    async def wirft(*_a, **_k):
        raise RuntimeError("HA weg")
    monkeypatch.setattr(kk, "fuelle_kanal", wirft)
    async with sitzungen() as s:
        erg = await kr.fuehre_aus(s, a, ha_svc=svc, jetzt=ZEIT + timedelta(days=20, hours=3))
        await s.commit()
    s1 = await kr.nach_dem_commit(erg, ha_svc=svc, sitzungen=sitzungen, starten=False)
    assert s1["fuellen_offen"] is True
    k = await wk_kanal(sitzungen, aid, "basis:einspeisung")
    async with sitzungen() as s:
        (eintrag,) = await vq.auswahl(s, aid)
        params = {"kanal": "basis:einspeisung", "zeitpunkt": eintrag["vorbelegung"]}
        t = _ts(datetime.fromisoformat(eintrag["vorbelegung"]))
        geschaetzt, saetze, daten = await vq.plan_vorschau(s, aid, params, ha_svc=svc)
    assert saetze == [vq.SATZ_FUELLEN_OFFEN] and set(geschaetzt.values()) == {0} and daten["korrektur"] is None
    vorher = await _vor_t(sitzungen, k.id, t)
    assert vorher >= 240
    gestartet: list[str] = []
    monkeypatch.setattr(kl, "starten", lambda lauf, **_k: gestartet.append(lauf))
    async with sitzungen() as s:
        aus = await vq.fuehre_aus(s, aid, params, ha_svc=svc)
    assert (aus["kanalzeilen_geloescht"], aus["fuellen_nachgeholt"], gestartet) == (0, 1, [s1["lauf"]])
    assert await _vor_t(sitzungen, k.id, t) == vorher
