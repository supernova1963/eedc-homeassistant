"""Sensorwechsel U3 Lauf b «MQTT» (Rechenweg ``opus-berichte/SENSORWECHSEL-U3-RECHENWEG-2026-11-19.md`` G4, G5, G7; Bauplan
Nr. 150, Entscheide E1 = A, E2, E3, E4, E5, E6) — Proben mit Sprengsatz.

* **G4** ``mqtt_zaehlerstand_springt``: der Kern aus U2 c mit dem Arm «Rückgang» je Quell-Abschnitt eines MQTT-Kanals; je
  Stunde eine Warnung mit dem Sprung «Zähler getauscht» (``getauscht=<Zeit>``); still bei Nachholstunde, Tageszähler, stummem
  Publisher, Nachbau aus HA-Ständen und nach dem Eintrag (Quellzeile an der Stunde); ``zaehler_ruecksprung`` lässt einen
  Rückgang aus, den G4 nennt.
* **G5** Rand-Stände aus Rohständen: «Zähler getauscht» (später und sofort, Neubeginn, Rückgang), «bleiben» zwischen zwei
  MQTT-Quellen (im Stundenlauf und im Nachtrag) — Naht-Stunde 0,458, Tag 11,958 in Kanal **und** Reihe; ein Zeitpunkt ohne
  Sprung wird abgelehnt; ohne Rohstände wie bisher (11,5).
* **G7** versetzter Abschnitt einer MQTT-Reihe: Befund mit beiden Antworten; «bleiben» = zwei Einträge (11,958 · 12,0 ·
  11,958); «verwerfen» = Korrektur über das Stück mit Kanal-Beginn eine Stunde vor «Falsch seit» und Brücke ohne Höhenwechsel
  (08. 5,0 · 09. «—» · 10. 31,0; drei Tage zusammen 36,0); G4 schweigt für die Schritte des Abschnitts; die Auskunft «Zeit
  verworfen» sagt danach «wie eine Zählerlücke» (P-1 aus U3 a).
* **Zeit-Proben:** Tausch über Mitternacht, an der Monatsgrenze, genau zur vollen Stunde, Publisher im 15-Minuten-Takt, am Tag
  der Herbstumstellung; die Datei liest keine Uhr und läuft auch mit ``TZ=Pacific/Auckland`` und ``TZ=UTC``. Der Tausch IN der
  doppelten Herbststunde bleibt benannte Grenze (BERECHNUNGEN; die Rohstände tragen örtliche Zeit ohne Zone).

Saat: reine MQTT-Anlage, Netzbezug 0,5 kWh je Stunde ab 5 000 kWh, Rohstände im 5-Minuten-Raster wie der Scheduler
(``mqtt_energy_snapshots``), je volle Stunde um :05 der Stundenlauf (Reihe ``snapshot_anlage`` + Kanäle
``schreibe_kanaele_im_stundenlauf``) — dieselbe Saat wie die Messung des Rechenwegs (``golden-master/sensorwechsel-saat/u3/``), mit
festen Tagen. Schwesterdateien: test_sensorwechsel_u2c_proben.py (Kern, HA-Spiegel), test_sensorwechsel_s2_naht.py (Naht im
Kanal), test_sensorwechsel_s3bk_proben.py («Zähler getauscht»), test_sensorwechsel_u3a_proben.py (Auskunft «Zeit verworfen»),
test_daten_checker_zaehler_versatz.py (versetzter Abschnitt), test_s4_r7_tagesreset_zaehler.py (Tageszähler).
"""

from __future__ import annotations

import importlib
import pkgutil
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import delete, insert, select

import backend.models as _m

for _mod in pkgutil.iter_modules(_m.__path__):
    importlib.import_module(f"backend.models.{_mod.name}")

from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik  # noqa: E402
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot  # noqa: E402
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: E402
from backend.models.zuordnung_wechsel import ZuordnungWechsel  # noqa: E402
from backend.services.zuordnung_wechsel import zeitpunkt as zw  # noqa: E402
from backend.tests import factories  # noqa: E402

NETZ = "basis:netzbezug"
NETZ_FID = "basis_energy_netzbezug_kwh"
MK = "netzbezug_kwh"
BASIS = 5000.0
RATE = 0.5
START = datetime(2026, 6, 7)
ENDE = datetime(2026, 6, 11)
E = datetime(2026, 6, 8, 10, 20)
TAG_E = E.date()
QUELLE = {"art": "mqtt", "mqtt_key": MK, "topic": None}


def wahr(t: datetime, start: datetime = START) -> float:
    """Wahrer Stand um ``t`` — über die Epoche (die zweite Herbststunde trägt ``fold = 1`` und zählt mit)."""
    return round(BASIS + RATE * (t.timestamp() - start.timestamp()) / 3600, 6)


# ═══ G4 — Kern und Erzeuger an Kanal-Zeilen (ohne Stundenlauf) ════════════════════════════════════════════════════════

K0 = datetime(2026, 6, 1)
KE = datetime(2026, 6, 17, 10)          # die Stunde mit dem Sprung (16 Tage mit Zuwachs davor)


def _kanal_zeilen(art_des_falls: str) -> list[tuple[int, float, float]]:
    """(start_ts, state, sum) je Stunde vom 01.06. bis 18.06.; in der Stunde ``KE`` der Fall."""
    out, s, summe = [], BASIS, 0.0
    t = K0
    while t < datetime(2026, 6, 19):
        neu = s + RATE
        if t == KE and art_des_falls == "sprung":
            neu = s + 2000.0 + RATE
        elif t == KE and art_des_falls == "neubeginn":
            neu = 300.0 + RATE
        elif t == KE and art_des_falls == "rueckgang":
            neu = 0.96 * s + RATE
        zuwachs = neu if (art_des_falls == "neubeginn" and t == KE) else neu - s     # HAs Regel: Neubeginn zählt den Stand
        summe += zuwachs
        out.append((int(t.timestamp()), round(neu, 6), round(summe, 6)))
        s = neu
        t += timedelta(hours=1)
    return out


async def _g4_anlage(db, zeilen, *, statistic_id: str = MK, quellen_ab: tuple = ()):
    a = await factories.anlage(db, anlagenname="U3b", sensor_mapping={"basis": {}, "investitionen": {}})
    k = Kanal(anlage_id=a.id, key=NETZ, einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=zeilen[0][0], familie="mitschrift", statistic_id=statistic_id, offset=0.0))
    for ab in quellen_ab:
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=ab, familie="mitschrift", statistic_id=statistic_id, offset=0.0))
    await db.execute(insert(KanalStatistik), [{"kanal_id": k.id, "start_ts": ts, "state": st, "sum": su,
                                               "familie": "mitschrift"} for ts, st, su in zeilen])
    await db.commit()
    return a


async def _g4(db, a):
    from backend.services.daten_checker import DatenChecker

    zw.vergiss(db)
    return await DatenChecker(db)._check_mqtt_zaehlerstand_springt(a)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_rueckgang_arm"])
@pytest.mark.parametrize("fall,menge", [("sprung", 2000.5), ("neubeginn", 300.5), ("rueckgang", -207.38)])
async def test_g4_je_arm_eine_zeile_mit_sprung_getauscht(db, monkeypatch, fall, menge, sprengsatz):
    from backend.core.berechnungen import zaehlerstand_sprung as kern
    from backend.services.daten_checker.datenquelle import mqtt_standsprung as ms

    if sprengsatz:
        echt = kern.finde_standspruenge
        monkeypatch.setattr(ms, "finde_standspruenge", lambda z, **kw: echt(z, **{**kw, "rueckgang": False}))
    erg = await _g4(db, await _g4_anlage(db, _kanal_zeilen(fall)))
    if sprengsatz and fall == "rueckgang":
        assert erg == []                                     # Sprengsatz: −206,5 still
        return
    assert len(erg) == 1
    e = erg[0]
    assert e.code == "mqtt_zaehlerstand_springt" and e.schwere == "warning" and e.knopf == "Zähler getauscht"
    assert e.werte["art"] == fall and e.werte["menge"] == pytest.approx(menge, abs=0.01)
    assert e.meldung == "Anlage · Netzbezug: Zählerstand springt am 17.06.2026 um 10:00 Uhr"
    assert e.ziel.bereich == "datenquellen" and e.ziel.params == {"feld": "netzbezug_kwh", "getauscht": "2026-06-17T10:00"}
    assert "Live-Anzeige" in e.details and "„Zähler getauscht“" in e.details


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_paar_ueber_quellgrenze"])
async def test_g4_nach_dem_eintrag_beginnt_an_der_stunde_eine_quelle_kein_befund(db, monkeypatch, sprengsatz):
    from backend.services.daten_checker.datenquelle import mqtt_standsprung as ms

    if sprengsatz:                                # ein Abschnitt je Kanal statt je Quelle
        monkeypatch.setattr(ms, "_SQL", ms._SQL.replace("AND (q.gueltig_bis IS NULL OR s.start_ts < q.gueltig_bis)", "")
                            .replace("JOIN q ON q.kanal_id = k.id", "JOIN (SELECT * FROM q WHERE gueltig_bis IS NULL) q "
                                     "ON q.kanal_id = k.id").replace("AND s.start_ts >= q.gueltig_ab", ""))
    a = await _g4_anlage(db, _kanal_zeilen("sprung"), quellen_ab=(int(KE.timestamp()),))
    assert len(await _g4(db, a)) == (1 if sprengsatz else 0)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_schwelle_0_5"])
async def test_g4_nachholstunde_nach_stillem_publisher_ist_kein_befund(db, monkeypatch, sprengsatz):
    """Der Publisher schweigt 20 Stunden (keine Zeilen); die erste Stunde danach trägt deren 10,5 kWh — Maß 10,5/12 = 0,875
    (Ruhe unter einem Tag zählt 1); eine Nachholstunde nach Tagen Stille bleibt bei 1,0."""
    from backend.core.berechnungen import zaehlerstand_sprung as kern

    if sprengsatz:
        monkeypatch.setattr(kern, "SCHWELLE_SPRUNG", 0.5)
        monkeypatch.setattr(kern, "reif", lambda *_a: True)          # U3-K (B2): der junge Abschnitt gilt als reif
    zeilen = [z for z in _kanal_zeilen("keiner") if not (KE.timestamp() - 20 * 3600 <= z[0] < KE.timestamp())]
    assert len(await _g4(db, await _g4_anlage(db, zeilen))) == (1 if sprengsatz else 0)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_kurz_tiefer"])
async def test_g4_kurz_tiefer_und_zurueck_ist_kein_befund(db, monkeypatch, sprengsatz):
    """Der Stand fällt eine Stunde um 5 % und ist in der nächsten wieder auf der Höhe davor (S4-R-7 «dip»): der Tag zählt Fall und
    Rückkehr, in Summe nichts — kein Höhenwechsel; ``zaehler_ruecksprung`` nennt das Zurückfallen wie bisher."""
    from backend.services.daten_checker.datenquelle import mqtt_standsprung as ms

    if sprengsatz:
        monkeypatch.setattr(ms, "_kurz_tiefer", lambda z: set())
    zeilen = _kanal_zeilen("keiner")
    i = next(j for j, z in enumerate(zeilen) if z[0] == int(KE.timestamp()))
    ts, st, su = zeilen[i]
    tief = round(0.95 * zeilen[i - 1][1], 6)
    zeilen[i] = (ts, tief, su - RATE + (tief - zeilen[i - 1][1]))
    zeilen[i + 1:] = [(t, a, b + (zeilen[i][2] - su)) for t, a, b in zeilen[i + 1:]]
    zeilen[i + 1] = (zeilen[i + 1][0], zeilen[i + 1][1], zeilen[i][2] + (zeilen[i + 1][1] - tief))
    for j in range(i + 2, len(zeilen)):
        zeilen[j] = (zeilen[j][0], zeilen[j][1], zeilen[j - 1][2] + RATE)
    arten = sorted(e.werte["art"] for e in await _g4(db, await _g4_anlage(db, zeilen)))
    assert arten == (["rueckgang", "sprung"] if sprengsatz else [])


async def test_g4_tageszaehler_stummer_publisher_und_nachbau_sind_kein_befund(db):
    # Tageszähler: um Mitternacht auf 0 (HAs Regel: Neubeginn, die Stunde zählt nur ihren Verbrauch)
    tz, s, summe = [], 0.0, 0.0
    t = K0
    while t < datetime(2026, 6, 19):
        neu = RATE if t.hour == 0 else s + RATE
        summe += RATE
        tz.append((int(t.timestamp()), neu, summe))
        s, t = neu, t + timedelta(hours=1)
    assert await _g4(db, await _g4_anlage(db, tz)) == []
    # stumm drei Tage, danach derselbe Stand weiter (die Menge der Zeit in einer Stunde, Ruhe 3 Tage)
    stumm = [z for z in _kanal_zeilen("keiner") if not (KE.timestamp() - 72 * 3600 <= z[0] < KE.timestamp())]
    assert await _g4(db, await _g4_anlage(db, stumm)) == []
    # Nachbau aus gespeicherten HA-Ständen (``sensor_snapshots:…``) prüft «Zählerstand springt» in HA, nicht diese Prüfung
    assert await _g4(db, await _g4_anlage(db, _kanal_zeilen("sprung"), statistic_id="sensor_snapshots:" + NETZ)) == []


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_abgrenzung"])
@pytest.mark.parametrize("fall", ["rueckgang", "tageszaehler"])
async def test_g4_zaehler_ruecksprung_laesst_den_rueckgang_aus_den_g4_nennt(db, monkeypatch, fall, sprengsatz):
    """``zaehler_ruecksprung`` (Reihe der MQTT-Stände, 30 Tage) nennt einen Rückgang, den «Zählerstand springt» nennt, nicht noch
    einmal; den Tageszähler (G4 still) nennt er wie bisher."""
    from backend.services.daten_checker import DatenChecker
    from backend.services.daten_checker.datenquelle import mqtt_standsprung as ms

    if sprengsatz:
        async def nichts(db, aid):
            return {}
        monkeypatch.setattr(ms, "benannte_stunden", nichts)
    if fall == "rueckgang":
        zeilen = _kanal_zeilen("rueckgang")
    else:
        zeilen, s, summe, t = [], 0.0, 0.0, K0
        while t < datetime(2026, 6, 19):
            neu = RATE if t.hour == 0 else s + RATE
            summe += RATE
            zeilen.append((int(t.timestamp()), neu, summe))
            s, t = neu, t + timedelta(hours=1)
    a = await _g4_anlage(db, zeilen)
    # Reihe (Stand zur vollen Stunde = Stand am Ende der Zeile davor) und Rohstände (Aktiv-Fenster)
    db.add_all([SensorSnapshot(anlage_id=a.id, sensor_key=NETZ, zeitpunkt=datetime.fromtimestamp(ts) + timedelta(hours=1),
                               wert_kwh=st, quelle="mqtt_inbound") for ts, st, _su in zeilen])
    db.add(MqttEnergySnapshot(anlage_id=a.id, timestamp=datetime(2026, 6, 18, 23), energy_key=MK, value_kwh=zeilen[-1][1]))
    await db.commit()
    zw.vergiss(db)
    rs = await DatenChecker(db)._check_zaehler_ruecksprung(a, jetzt=datetime(2026, 6, 19))
    if fall == "tageszaehler":
        assert len(rs) == 1                      # wie bisher, mit und ohne Abgrenzung
    else:
        assert len(rs) == (1 if sprengsatz else 0)
        assert len(await _g4(db, a)) == 1


def test_g4_kern_rueckgang_arm_nur_mit_schalter_und_schwelle():
    from backend.core.berechnungen.zaehlerstand_sprung import RUECKGANG, finde_standspruenge

    z = [(0, 10.0, 0.0), (3600, 10.5, 0.5), (7200, 10.495, 0.495), (10800, 10.4, 0.4)]
    assert finde_standspruenge(z) == []                                       # HA-Spiegel: kein Arm
    funde = finde_standspruenge(z, rueckgang=True)
    assert [(f.start_ts, f.art) for f in funde] == [(10800, RUECKGANG)]       # −0,005 bleibt unter −0,01


# ═══ Saat mit Stundenlauf (G5, G7) ═══════════════════════════════════════════════════════════════════════════════════

class Saat:
    """Der Publisher (``stand``), der Takt seiner Rohstände (``takt`` Minuten; dazwischen wiederholt der Scheduler den letzten
    gemeldeten Stand) und die Handlungen des Anwenders ``(zeit, coroutine-fabrik)``; späte Handlungen nach dem Lauf."""

    def __init__(self, stand, *, start=START, ende=ENDE, takt=5, handlungen=(), spaet=()):
        self.stand, self.start, self.ende, self.takt = stand, start, ende, takt
        self.handlungen, self.spaet = sorted(handlungen, key=lambda h: h[0]), list(spaet)


async def _anlage(db):
    a = await factories.anlage(db, anlagenname="U3b", leistung_kwp=10.0, sensor_mapping={"basis": {}, "investitionen": {}})
    await db.commit()
    return a


async def _anlage_frisch(db, aid):
    from backend.models.anlage import Anlage

    return (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()


async def _laeufe():
    from backend.services.zuordnung_wechsel import korrektur_lauf

    for t in list(korrektur_lauf._AUFGABEN.values()):
        await t


async def betrieb(db, aid: int, saat: Saat) -> list:
    """5-Minuten-Raster: Rohstand · fällige Handlungen · um :05 der Stundenlauf der Stunde davor (Reihe + Kanäle)."""
    from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf
    from backend.services.snapshot.writer import snapshot_anlage

    antworten, offen = [], list(saat.handlungen)
    epoche, ende = saat.start.timestamp(), (saat.ende + timedelta(minutes=5)).timestamp()
    while epoche <= ende:
        t = datetime.fromtimestamp(epoche)           # örtlich ohne Zone, wie der Scheduler (die doppelte Herbststunde zweimal)
        gemeldet = t - timedelta(minutes=(t.minute % saat.takt))     # der Scheduler wiederholt den zuletzt gemeldeten Stand
        db.add(MqttEnergySnapshot(anlage_id=aid, timestamp=t, energy_key=MK, value_kwh=saat.stand(gemeldet)))
        await db.commit()
        while offen and offen[0][0] < t + timedelta(minutes=5):
            antworten.append(await offen.pop(0)[1](db, aid))
            await _laeufe()
        if t.minute == 5 and t > saat.start + timedelta(hours=1):
            h = t.replace(minute=0)
            a = await _anlage_frisch(db, aid)
            await snapshot_anlage(db, a, zeitpunkt=h)
            await db.commit()
            await schreibe_kanaele_im_stundenlauf(db, a, h)
            await db.commit()
            if h.hour == 0 and h.date() > saat.start.date():
                await _tagesabschluss(db, aid, h.date() - timedelta(days=1))
            db.expunge_all()
            zw.vergiss(db)
        epoche += 300
    for f in saat.spaet:
        antworten.append(await f(db, aid))
        await _laeufe()
    db.expunge_all()
    zw.vergiss(db)
    return antworten


async def _tagesabschluss(db, aid: int, d: date) -> None:
    from backend.services.energie_profil._helpers import ohne_abruf
    from backend.services.energie_profil.aggregator import aggregate_day
    from backend.services.energie_profil.source import Source

    with ohne_abruf({}):
        await aggregate_day(await _anlage_frisch(db, aid), d, db, source=Source.SCHEDULER)
    await db.commit()


async def tagesansicht(db, aid: int, tage: list[date]) -> list:
    """Netzbezug je Tag, wie die Tagestabelle ihn zeigt (``tage_werte``) — die sichtbare Zahl."""
    from backend.services.energie_profil.tage_werte import baue_tage_werte
    from backend.services.kanal import merken

    merken.invalidiere(aid)
    zw.vergiss(db)
    zeilen = {z.datum: z.netzbezug for z in await baue_tage_werte(db, await _anlage_frisch(db, aid), tage[0], tage[-1])}
    return [None if zeilen.get(d) is None else round(zeilen[d], 3) for d in tage]


async def kanal_tag(db, aid: int, d: date):
    from backend.services.kanal import lesen, merken

    merken.invalidiere(aid)
    k = (await db.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == NETZ))).scalar_one()
    z = await lesen.zeitraum(db, k, int(datetime.combine(d, datetime.min.time()).timestamp()),
                             int(datetime.combine(d + timedelta(days=1), datetime.min.time()).timestamp()))
    return None if z.delta is None else round(z.delta, 3)


async def kanal_stunde(db, aid: int, h: datetime):
    from backend.services.kanal import lesen

    k = (await db.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == NETZ))).scalar_one()
    z = await lesen.zeitraum(db, k, int(h.timestamp()), int((h + timedelta(hours=1)).timestamp()))
    return None if z.delta is None else round(z.delta, 3)


async def reihe_tag(db, aid: int, d: date):
    from backend.services.snapshot import reader

    zw.vergiss(db)
    v = await reader.delta(db, aid, NETZ, "", datetime.combine(d, datetime.min.time()),
                           datetime.combine(d + timedelta(days=1), datetime.min.time()))
    return None if v is None else round(v, 3)


def getauscht(zeit: datetime):
    async def f(db, aid):
        from backend.api.routes import sensorwechsel as sw

        req = sw.ZaehlerGetauschtRequest(getauscht_am=zeit)
        p = await sw.pruefe_zaehler_getauscht(aid, NETZ_FID, req, db)
        r = await sw.zaehler_getauscht(aid, NETZ_FID, req, db)
        return {"pruefen": p, "eintragen": r}
    return f


def _hoch(versatz=2000.0, ab=E):
    return lambda t: wahr(t) + (versatz if t >= ab else 0.0)


def _reset300(t):
    return 300.0 + wahr(t) - wahr(E) if t >= E else wahr(t)


def _tiefer(t):
    return 0.96 * wahr(E) + wahr(t) - wahr(E) if t >= E else wahr(t)


async def _wechsel_zeilen(db, aid):
    return (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.anlage_id == aid)
                             .order_by(ZuordnungWechsel.id))).scalars().all()


# ═══ G5 — Rand-Stände aus Rohständen ══════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_menge_der_naht"])
@pytest.mark.parametrize("stand", [_hoch(), _reset300, _tiefer], ids=["sprung_2000", "neubeginn_300", "minus_4_prozent"])
async def test_g5_spaet_eingetragen_kanal_und_reihe_11958(db, monkeypatch, stand, sprengsatz):
    from backend.services.kanal import naht

    if sprengsatz:                          # die Naht-Stunde bleibt ohne Zuwachs (wie vor U3)
        monkeypatch.setattr(naht, "_menge", lambda *a: None)
    aid = (await _anlage(db)).id
    antw = await betrieb(db, aid, Saat(stand, spaet=[getauscht(E)]))
    p = antw[0]["pruefen"]
    assert p["weg"] == "fortsetzung" and p["eintragen"] is True
    assert p["getauscht_am"] == "2026-06-08T10:20:00"
    assert any("rechnet sie neu aus den Zählerständen" in s for s in p["saetze"]) != sprengsatz
    w = (await _wechsel_zeilen(db, aid))[0]
    assert (w.ansatz, w.stand_alt_ende, w.erklaert_ts) == ("schnitt", pytest.approx(wahr(E - timedelta(minutes=5))), E)
    assert w.stand_neu_null == pytest.approx(stand(E))
    k, r = await kanal_tag(db, aid, TAG_E), await reihe_tag(db, aid, TAG_E)
    assert r == pytest.approx(11.958, abs=0.001)
    assert k == pytest.approx(11.5 if sprengsatz else 11.958, abs=0.001)
    if not sprengsatz:
        assert await kanal_stunde(db, aid, E.replace(minute=0)) == pytest.approx(0.458, abs=0.001)
        assert await kanal_tag(db, aid, TAG_E + timedelta(days=1)) == pytest.approx(12.0)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_eintragen_ohne_neuen_stand"])
async def test_g5_sofort_vor_dem_ersten_neuen_stand_setzt_der_stundenlauf_die_rand_staende(db, monkeypatch, sprengsatz):
    """Um 10:18, bevor der neue Zähler einen Stand gemeldet hat: Sitzung 5 (Bauplan Nr. 168, neue Erwartung — bis U3-K4 trug der
    Dialog ein und der Stundenlauf setzte die Rand-Stände): der Dialog trägt noch nicht ein und sagt es; nach dem Betrieb (der
    neue Zähler hat um 10:20 gemeldet) trägt er ein — Kanal und Reihe 11,958. Sprengsatz: der Weg gälte als eintragbar."""
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    if sprengsatz:
        monkeypatch.setattr(zg, "WEG_NOCH_NICHT_GEMELDET", zg.WEG_FORTSETZUNG)
    t = E - timedelta(minutes=2)
    aid = (await _anlage(db)).id
    antw = await betrieb(db, aid, Saat(_hoch(), handlungen=[(t, getauscht(t))]))
    if sprengsatz:
        assert antw[0]["pruefen"]["eintragen"] is True
        return
    assert antw[0]["pruefen"]["weg"] == "noch_nicht_gemeldet" and antw[0]["eintragen"]["eingetragen"] is False
    assert antw[0]["pruefen"]["saetze"][0].startswith("Seit 08.06.2026 10:18 Uhr ist kein anderer Zählerstand gespeichert")
    assert (await getauscht(t)(db, aid))["eintragen"]["eingetragen"] is True
    assert await kanal_tag(db, aid, TAG_E) == pytest.approx(11.958, abs=0.001)
    assert await reihe_tag(db, aid, TAG_E) == pytest.approx(11.958, abs=0.001)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_zeit_wie_eingegeben"])
async def test_g5_getauscht_am_rueckt_auf_den_sprung_der_stunde(db, monkeypatch, sprengsatz):
    """«Getauscht am» 10:40, der Stand springt um 10:20 — eingetragen um 10:42, bevor der Stundenlauf die Stunde schreibt: eedc
    trägt den Tausch um 10:20 ein (dort teilt der Stundenlauf die Periode); wie eingegeben zählte der Kanal den Sprung."""
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg

    if sprengsatz:
        echt = zg.lage

        async def wie_eingegeben(db, anlage, key, t, **kw):
            la = await echt(db, anlage, key, t, **kw)
            if la.rand is not None:
                la.getauscht_am = t
            return la
        monkeypatch.setattr(zg, "lage", wie_eingegeben)
    t, eingabe = E + timedelta(minutes=22), E + timedelta(minutes=20)
    aid = (await _anlage(db)).id
    antw = await betrieb(db, aid, Saat(_hoch(), handlungen=[(t, getauscht(eingabe))]))
    w = (await _wechsel_zeilen(db, aid))[0]
    if sprengsatz:
        assert w.erklaert_ts == eingabe and await kanal_tag(db, aid, TAG_E) == pytest.approx(2011.958, abs=0.01)
        return
    assert w.erklaert_ts == E and "am 08.06.2026 10:20 Uhr ein" in antw[0]["pruefen"]["saetze"][0]
    assert await kanal_tag(db, aid, TAG_E) == pytest.approx(11.958, abs=0.001)
    assert await reihe_tag(db, aid, TAG_E) == pytest.approx(11.958, abs=0.001)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_jeder_schritt_hebt_sich_ab"])
async def test_g5_eine_stunde_daneben_mit_hinweis(db, monkeypatch, sprengsatz):
    """«Getauscht am» eine Stunde vor dem Sprung (09:20): U3-K4 (Bauplan Nr. 166, neue Erwartung — bis U3-K3 abgelehnt) — der
    Dialog nimmt den nächsten anderen Stand (der Stand um 09:20 selbst), sagt «Einen Sprung sieht eedc an dieser Zeit nicht.» und trägt auf das Wort
    des Anwenders ein; der Sprung um 10:20 zählt weiter (der Anwender hat die falsche Zeit gewählt). Sprengsatz: jeder Schritt
    höbe sich ab ⇒ der Hinweis «Ob das ein Tausch ist …»."""
    from backend.core.berechnungen import rohstand_rand

    if sprengsatz:
        monkeypatch.setattr(rohstand_rand, "abgehoben", lambda *_a, **_k: True)
    aid = (await _anlage(db)).id
    antw = await betrieb(db, aid, Saat(_hoch(), spaet=[getauscht(E - timedelta(hours=1))]))
    p, r = antw[0]["pruefen"], antw[0]["eintragen"]
    assert p["weg"] == "fortsetzung" and p["eintragen"] is True and r["eingetragen"] is True
    assert p["getauscht_am"] == "2026-06-08T09:20:00"
    assert p["saetze"][1] == ("Ob das ein Tausch ist oder eine gezählte Menge, erkennt eedc nicht." if sprengsatz
                              else "Einen Sprung sieht eedc an dieser Zeit nicht.")
    assert await kanal_tag(db, aid, TAG_E) > 2000.0


async def test_g5_ohne_rohstaende_wie_bisher(db):
    """Älter als 31 Tage: die Rohstände sind gelöscht — der Eintrag gilt wie vor U3 (Naht-Stunde ohne Zuwachs, Tag 11,5)."""
    async def loeschen(db, aid):
        await db.execute(delete(MqttEnergySnapshot))
        await db.commit()
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(_hoch(), spaet=[loeschen, getauscht(E)]))
    w = (await _wechsel_zeilen(db, aid))[0]
    assert w.ansatz is None and w.stand_alt_ende is None
    assert await kanal_tag(db, aid, TAG_E) == pytest.approx(11.5) and await reihe_tag(db, aid, TAG_E) == pytest.approx(11.5)


def _wechsel_topic(zeit: datetime, grund):
    async def f(db, aid):
        db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=NETZ, erklaert_ts=zeit, ab_ts=zw.ab_ts_aus(zeit),
                                vorher={**QUELLE, "topic": "pub/a"}, nachher={**QUELLE, "topic": "pub/b"}, grund=grund,
                                herkunft="wechsel"))
        await db.commit()
        zw.vergiss(db)
    return f


@pytest.mark.parametrize("weg", ["stundenlauf"])
async def test_g5_bleiben_zwischen_zwei_mqtt_quellen(db, weg):
    """Topic-Wechsel um 10:22 (der neue Publisher beginn um 10:20 mit +2 000): «bleiben» sofort (der Stundenlauf setzt die
    Rand-Stände) — Kanal und Reihe 11,958 (Rechenweg: 11,958/11,5). Der Weg «ohne Grund und später nachgetragen» ist mit
    «Grund nachtragen» entfernt (Weg B, Sitzung B2)."""
    u = E + timedelta(minutes=2)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(_hoch(ab=u), handlungen=[(u, _wechsel_topic(u, "fortsetzung"))]))
    w = [z for z in await _wechsel_zeilen(db, aid) if z.aufgehoben_durch is None][0]
    assert w.ansatz == "schnitt" and w.stand_neu_null == pytest.approx(wahr(E + timedelta(minutes=5)) + 2000.0)
    assert await kanal_tag(db, aid, TAG_E) == pytest.approx(11.958, abs=0.001)
    assert await reihe_tag(db, aid, TAG_E) == pytest.approx(11.958, abs=0.001)


def test_g5_e5_satz_zu_bleiben_je_quellenpaar():
    from backend.services.zuordnung_wechsel.rohstand import SATZ_BLEIBEN_HA_MQTT, SATZ_BLEIBEN_MQTT, bleiben_satz

    ha = {"art": "ha", "entity_id": "sensor.netz"}
    assert bleiben_satz(QUELLE, {**QUELLE, "topic": "pub/b"}, NETZ) == SATZ_BLEIBEN_MQTT
    assert bleiben_satz(ha, QUELLE, NETZ) == bleiben_satz(QUELLE, ha, NETZ) == SATZ_BLEIBEN_HA_MQTT
    assert bleiben_satz(ha, {"art": "ha", "entity_id": "sensor.neu"}, NETZ) is None


def test_g5_regel_rein():
    from backend.core.berechnungen.rohstand_rand import menge_der_naht, sprung_der_stunde, verschiebung_der_naht

    # Neubeginn bei 300: der rohe Versatz (alt_ende − neu_null) allein zählte die Stunde falsch (Rechenweg: +4 885)
    assert menge_der_naht(5100.0, 5099.9, 300.3, 300.0) == pytest.approx(0.4)
    assert verschiebung_der_naht(0.4, 300.3 + 5099.9, 5099.9) == pytest.approx(0.4 - 300.3)
    roh = [(datetime(2026, 6, 8, 9, 0) + timedelta(minutes=5 * i), 100.0 + 0.04 * i) for i in range(24)]
    roh[16:] = [(t, w + 50.0) for t, w in roh[16:]]                       # Sprung um 10:20
    a, b = sprung_der_stunde(roh, datetime(2026, 6, 8, 10))
    assert (a[0], b[0]) == (datetime(2026, 6, 8, 10, 15), datetime(2026, 6, 8, 10, 20))
    assert sprung_der_stunde(roh, datetime(2026, 6, 8, 9)) is None


# ═══ Zeit-Proben (G5) ═══════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("fall,zeit,takt,tag,soll,folgetag", [
    ("ueber_mitternacht", datetime(2026, 6, 8, 23, 55), 5, date(2026, 6, 8), 11.958, 12.0),
    ("monatsgrenze", datetime(2026, 6, 30, 23, 55), 5, date(2026, 6, 30), 11.958, 12.0),
    ("volle_stunde", datetime(2026, 6, 8, 10, 0), 5, date(2026, 6, 8), 11.958, 12.0),
    ("takt_15_minuten", datetime(2026, 6, 8, 10, 15), 15, date(2026, 6, 8), 11.875, 12.0),
])
async def test_zeit_proben_g5(db, fall, zeit, takt, tag, soll, folgetag):
    start = datetime.combine(tag - timedelta(days=1), datetime.min.time())
    aid = (await _anlage(db)).id

    def stand(t):
        return wahr(t, start) + (2000.0 if t >= zeit else 0.0)
    await betrieb(db, aid, Saat(stand, start=start, ende=start + timedelta(days=3), takt=takt, spaet=[getauscht(zeit)]))
    w = (await _wechsel_zeilen(db, aid))[0]
    assert w.erklaert_ts == zeit and w.ansatz == "schnitt"
    assert await kanal_tag(db, aid, tag) == pytest.approx(soll, abs=0.001)
    assert await reihe_tag(db, aid, tag) == pytest.approx(soll, abs=0.001)
    assert await kanal_tag(db, aid, tag + timedelta(days=1)) == pytest.approx(folgetag, abs=0.001)
    assert await reihe_tag(db, aid, tag + timedelta(days=1)) == pytest.approx(folgetag, abs=0.001)


async def test_zeit_probe_tag_der_herbstumstellung(db):
    """Tausch am Tag der Herbstumstellung (Berlin 25 Stunden), nicht in der doppelten Stunde: Kanal und Reihe zählen den Tag
    ohne die fünf Minuten zwischen den Rand-Ständen (12,458; HEAD 12,0). In ``TZ=Pacific/Auckland`` und ``UTC`` ist der Tag
    gewöhnlich. **Benannte Grenze** (BERECHNUNGEN): ein Tausch IN der doppelten Stunde — die Rohstände tragen die örtliche
    Zeit ohne Zone, beide Durchläufe der Stunde mischen sich (Kanal am HEAD 7 025,5, mit U3 b 7 025,9)."""
    zeit = datetime(2026, 10, 25, 10, 20)
    tag = zeit.date()
    start = datetime(2026, 10, 24)
    stunden = (datetime(2026, 10, 26).timestamp() - datetime(2026, 10, 25).timestamp()) / 3600
    aid = (await _anlage(db)).id

    def stand(t):
        return wahr(t, start) + (2000.0 if t >= zeit else 0.0)
    await betrieb(db, aid, Saat(stand, start=start, ende=datetime(2026, 10, 27), spaet=[getauscht(zeit)]))
    soll = round(RATE * stunden - RATE * 5 / 60, 3)
    assert await kanal_tag(db, aid, tag) == pytest.approx(soll, abs=0.001)
    assert await reihe_tag(db, aid, tag) == pytest.approx(soll, abs=0.001)


# ═══ G7 — versetzter Abschnitt in einer MQTT-Reihe ══════════════════════════════════════════════════════════════════

ST_VON = datetime(2026, 6, 8, 10, 20)
ST_BIS = datetime(2026, 6, 10, 10, 20)


def _stueck(versatz=2000.0):
    return lambda t: wahr(t) + (versatz if ST_VON <= t < ST_BIS else 0.0)


async def _versatz(db, aid):
    from backend.services.daten_checker import DatenChecker

    zw.vergiss(db)
    return [e for e in await DatenChecker(db)._check_zaehler_versatz(await _anlage_frisch(db, aid)) if e.schwere != "ok"]


def _stueck_route(grund):
    async def f(db, aid):
        from backend.api.routes import sensorwechsel as sw

        b = [e for e in await _versatz(db, aid)][0]
        req = sw.StueckRequest(sensor_key=b.werte["schluessel"], sprung=datetime.fromisoformat(b.werte["sprung"]),
                               rueckgang=datetime.fromisoformat(b.werte["rueckgang"]), grund=grund)
        p = await sw.pruefe_stueck(aid, req, db)
        r = await sw.stueck_korrigieren(aid, req, db)
        return {"befund": b, "pruefen": p, "eintragen": r}
    return f


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_nur_der_sprung"])
async def test_g7_bleiben_zwei_eintraege_11958_12_11958(db, monkeypatch, sprengsatz):
    if sprengsatz:
        from backend.services.zuordnung_wechsel import stueck as st

        echt = st.tausch_lagen

        async def nur_erste(db, anlage, la):
            return (await echt(db, anlage, la))[:1]
        monkeypatch.setattr(st, "tausch_lagen", nur_erste)
    aid = (await _anlage(db)).id
    antw = await betrieb(db, aid, Saat(_stueck(), ende=datetime(2026, 6, 12), spaet=[_stueck_route("fortsetzung")]))
    b, p = antw[0]["befund"], antw[0]["pruefen"]
    assert b.code == "zaehler_versatz" and b.werte["lage"] == "mqtt" and b.schwere == "warning"
    assert b.werte["sprung"] == "2026-06-08T11:00" and b.werte["rueckgang"] == "2026-06-10T11:00"
    assert p["gruende"] == ["fortsetzung", "korrektur"] and "zwei" in p["bleiben_satz"]
    tage = [date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10)]
    ansicht = await tagesansicht(db, aid, tage)
    if sprengsatz:                                          # der Rückgang zählt als Neubeginn (+5 000)
        assert ansicht[:2] == [pytest.approx(11.958, abs=0.001), pytest.approx(12.0)] and ansicht[2] > 5000
        return
    assert ansicht == [pytest.approx(11.958, abs=0.001), pytest.approx(12.0), pytest.approx(11.958, abs=0.001)]
    for d, soll in zip(tage, (11.958, 12.0, 11.958)):
        assert await kanal_tag(db, aid, d) == pytest.approx(soll, abs=0.001)
        assert await reihe_tag(db, aid, d) == pytest.approx(soll, abs=0.001)
    if not sprengsatz:
        assert await _versatz(db, aid) == []                     # der Befund ist weg


@pytest.mark.parametrize("sprengsatz", ["gebaut", "ohne_kanal_beginn_davor", "ohne_bruecke"])
async def test_g7_verwerfen_monat_vollstaendig(db, monkeypatch, sprengsatz):
    from backend.services.kanal import korrektur as kk
    from backend.services.zuordnung_wechsel import korrektur as kr

    if sprengsatz == "ohne_kanal_beginn_davor":
        monkeypatch.setattr(kr, "_kanal_beginn", lambda a: int(a.falsch_seit.timestamp()))
    if sprengsatz == "ohne_bruecke":
        async def keine(*a, **k):
            return None
        monkeypatch.setattr(kk, "bruecken_versatz", keine)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(_stueck(), ende=datetime(2026, 6, 12), spaet=[_stueck_route("korrektur")]))
    tage = await tagesansicht(db, aid, [date(2026, 6, d) for d in (8, 9, 10)])
    soll = {"gebaut": [5.0, None, 31.0], "ohne_kanal_beginn_davor": [2005.5, None, -1969.5], "ohne_bruecke": [5.0, None, 6.0]}
    assert tage == [pytest.approx(x, abs=0.001) if x is not None else None for x in soll[sprengsatz]]
    if sprengsatz == "gebaut":
        assert await _versatz(db, aid) == []


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_kanal_ohne_bruecke_gelesen"])
async def test_g7_p1_auskunft_zeit_verworfen_wie_zaehlerluecke(db, monkeypatch, sprengsatz):
    from backend.services.daten_checker import DatenChecker
    from backend.services.kanal import korrektur as kk

    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(_stueck(), ende=datetime(2026, 6, 12), spaet=[_stueck_route("korrektur")]))
    if sprengsatz:
        async def nie(*a, **k):
            return False
        monkeypatch.setattr(kk, "ist_ueberbrueckt", nie)
    zw.vergiss(db)
    erg = await DatenChecker(db)._check_zaehler_zeit_verworfen(await _anlage_frisch(db, aid))
    assert len(erg) == 1
    if sprengsatz:
        assert "keine Differenz" in erg[0].details
    else:
        assert "wie über jede Zählerlücke" in erg[0].details and "10.06.2026" in erg[0].details


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["gebaut", "sprengsatz_ohne_ausnahme_g7"])
async def test_g7_g4_schweigt_fuer_die_schritte_des_abschnitts(db, monkeypatch, sprengsatz):
    """Ein Abschnitt +100: der Rückgang (5 100 → 5 000, über 90 %) zählt im Kanal −100 — G4 nennt ihn nicht, weil der versetzte
    Abschnitt ihn nennt (G7); ``zaehler_ruecksprung`` ebenso nicht."""
    from backend.services.daten_checker import DatenChecker
    from backend.services.daten_checker.datenquelle import versatz_mqtt

    if sprengsatz:
        async def keine(db, aid):
            return {}
        monkeypatch.setattr(versatz_mqtt, "mqtt_versatz_stunden", keine)
    aid = (await _anlage(db)).id
    await betrieb(db, aid, Saat(_stueck(100.0), ende=datetime(2026, 6, 12)))
    a = await _anlage_frisch(db, aid)
    assert [e.werte["lage"] for e in await _versatz(db, aid)] == ["mqtt"]
    g4 = await DatenChecker(db)._check_mqtt_zaehlerstand_springt(a)
    assert [e.werte["art"] for e in g4] == (["rueckgang"] if sprengsatz else [])
    zw.vergiss(db)
    assert await DatenChecker(db)._check_zaehler_ruecksprung(a, jetzt=datetime(2026, 6, 12)) == [] or sprengsatz
