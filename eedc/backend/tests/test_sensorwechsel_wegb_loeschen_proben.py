"""Sensorwechsel Weg B, Bau-Sitzung B1 (Bauplan Nr. 176–180) — Proben zu «Daten vor der Änderung löschen» und zur Lese-Regel
«Anfangsstand 0 am Beginn einer HA-Statistik».

**Welt** (wie die Messung der Stufe A2, ``golden-master/sensorwechsel-saat/wegb/``, kürzer): Anlage 10 kWp mit drei HA-Feldern —
Feld B = PV-Modul 1 (``sensor.alt`` 0,6 kWh/h), Kontroll-PV Modul 3 (2,0) und Wallbox (1,32) — und einem MQTT-Feld Netzbezug
(Rohstände alle 15 min, 0,9 kWh/h), Raten unter dem Plausibilitätsdeckel; HA-Attrappe (``ha_lts_helfer``, eine Zeile erst, wenn
ihre Stunde vorbei ist), stehende Uhr, echter Stundenlauf zu :05 (Reihe, Kanal, Nachfüllen wie der Scheduler, offene Läufe),
Tagesabschluss 00:15 und Self-Healing 02:15; Monatsabschluss Oktober gespeichert; Wechsel **mitten im Monat** (04.11. 10:20) über
die echte Feld-Route mit ``grund = loeschen``. Gelesen wird über die Routen der Oberfläche (Tageswerte, Monatssicht, «Aus HA
laden», Monatsabschluss-Vorschlag) und den Daten-Checker.

**Soll** (Tabelle A2, Halt-Kriterium der Sitzung): der Tag der ersten HA-Zeile des neuen Sensors = HA; der Monat in Monatssicht,
«Aus HA laden» und Vorschlag dreimal gleich = HA; die anderen Felder = HA (auch mittags am Tag des Wechsels); Kanal-Deckung an
jedem Tag; kein neuer Befund außer der Auskunft ``daten_vor_aenderung_geloescht``; der gespeicherte Oktober bleibt. Lagen: junger
Sensor, Sensor ab dem Vormonat, Sensor ab Beginn, zwei Vorquellen (A «bleiben» B, dann «löschen» auf C), Monatserster, Sensor
ab der laufenden Stunde, nur dieses Feld (F2: bewusst leere Tage ohne Befund), MQTT-Feld; dazu (a) importierte Statistik (erste
Zeile ``sum`` 1 000 — eedc zeigt denselben Sprung wie HA, kein Befund nennt ihn: benannte Grenze), (b) Home Assistant im
Augenblick von «löschen» nicht erreichbar (die Geschichte kommt mit dem nächsten Stundenlauf), (c) MQTT-Feld allein (sichtbare
Netz-Tageswerte).

Die Datei liest keine Wanduhr (stehende Uhr) und läuft auch mit ``TZ=Pacific/Auckland`` und ``TZ=UTC`` (keine Zeitumstellung im
Zeitraum der Welt).

Schwesterdateien: test_sensorwechsel_labk_proben.py (Welt mit HA-Attrappe), test_sensorwechsel_u3b_proben.py (MQTT),
test_werkbank_verwerfen_kommt_nicht_zurueck.py (Platzhalter nur bei «löschen»: die Werkbank bleibt ein Halt fürs Nachfüllen),
test_ha_lts_monatswerte_lookup.py (Regel «Anfangsstand 0» am HA-Monatsleser), test_kanal_lesen.py.
"""

from __future__ import annotations

import datetime as _dtm
import importlib
import pkgutil
import sys
import time as _time
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select, text

import backend.models as _modelle

for _m in pkgutil.iter_modules(_modelle.__path__):        # alle Tabellen an ``Base``, bevor die ``db``-Fixture das Schema anlegt
    importlib.import_module(f"backend.models.{_m.name}")

STUNDE = 3600
ALT, NEU, C, PVC, WB = "sensor.alt", "sensor.neu", "sensor.c", "sensor.pv_kontrolle", "sensor.wb"
#: Feld → (Investition, Feld-Schlüssel, sensor_key, Komponenten-Schlüssel)
FELDER = {"pv": ("1", "pv_erzeugung_kwh", "inv:1:pv_erzeugung_kwh", "pv_1"),
          "wb": ("2", "ladung_kwh", "inv:2:ladung_kwh", "wallbox_2"),
          "pvk": ("3", "pv_erzeugung_kwh", "inv:3:pv_erzeugung_kwh", "pv_3")}
NETZ_MK, NETZ_KEY, NETZ_FID = "netzbezug_kwh", "basis:netzbezug", "basis_energy_netzbezug_kwh"
START = datetime(2026, 10, 27)
#: Die HA-Statistiken der Welt beginnen am Vortag um 19:00 (fünf Stunden vor ``START``).
WELTBEGINN = date(2026, 10, 26)
T0 = datetime(2026, 11, 4, 10, 20)


def ep(t: datetime) -> int:
    return int(_time.mktime(t.timetuple()))


def r3(x):
    return None if x is None else round(float(x), 3)


# ── Stehende Uhr (kein freezegun): ``datetime``/``date``/``time.time`` in allen geladenen backend-Modulen ────────────────

_REAL_DT, _REAL_D, _REAL_TIME = _dtm.datetime, _dtm.date, _time.time


class _Uhr:
    ts: float | None = None

    def stelle(self, t: datetime) -> None:
        self.ts = float(_time.mktime(t.timetuple()))


UHR = _Uhr()


class _MetaDT(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _REAL_DT)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, _REAL_DT)


class _MetaD(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _REAL_D)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, _REAL_D)


class _FDT(_REAL_DT, metaclass=_MetaDT):
    def __new__(cls, *a, **k):
        return _REAL_DT(*a, **k)

    @classmethod
    def now(cls, tz=None):
        return _REAL_DT.now(tz) if UHR.ts is None else _REAL_DT.fromtimestamp(UHR.ts, tz)

    @classmethod
    def utcnow(cls):
        return _REAL_DT.utcnow() if UHR.ts is None else _REAL_DT.utcfromtimestamp(UHR.ts)

    @classmethod
    def today(cls):
        return cls.now()


class _FD(_REAL_D, metaclass=_MetaD):
    def __new__(cls, *a, **k):
        return _REAL_D(*a, **k)

    @classmethod
    def today(cls):
        return _REAL_D.today() if UHR.ts is None else _REAL_DT.fromtimestamp(UHR.ts).date()


def _alle_module_laden() -> None:
    import backend

    for m in pkgutil.walk_packages(backend.__path__, "backend."):
        if ".tests" in m.name or m.name.endswith("__main__"):
            continue
        try:
            importlib.import_module(m.name)
        except Exception:  # noqa: BLE001 — optionale Module dürfen fehlen
            pass


def _tausche(alt_dt, neu_dt, alt_d, neu_d) -> None:
    for name, mod in list(sys.modules.items()):
        if mod is None or not (name == "backend" or name.startswith("backend.")) or ".tests" in name:
            continue
        for k, v in list(vars(mod).items()):
            if v is alt_dt:
                setattr(mod, k, neu_dt)
            elif v is alt_d:
                setattr(mod, k, neu_d)


@pytest.fixture
def stehende_uhr():
    _alle_module_laden()
    _tausche(_REAL_DT, _FDT, _REAL_D, _FD)
    _time.time = lambda: _REAL_TIME() if UHR.ts is None else float(UHR.ts)
    try:
        yield UHR
    finally:
        _tausche(_FDT, _REAL_DT, _FD, _REAL_D)
        _time.time = _REAL_TIME
        UHR.ts = None


# ── Welt ────────────────────────────────────────────────────────────────────────────────────────────────────────────

class Welt:
    def __init__(self, db, svc, a, serien, mqtt_neu: datetime | None, mit_mqtt: bool):
        self.db, self.svc, self.a, self.serien = db, svc, a, serien
        self.mids, self.summe, self.naechste = {}, {}, {}
        self.mqtt_neu, self.mit_mqtt = mqtt_neu, mit_mqtt

    @property
    def sitzungen(self):
        from backend.services.zuordnung_wechsel.korrektur import sitzungen_wie

        return sitzungen_wie(self.db, None)

    def ha_bis(self, bis: int) -> None:
        """HA führt je Sensor die Stundenzeilen mit ``start_ts ≤ bis`` (``sum`` = ``state`` = laufende Summe)."""
        zeilen = []
        for eid, (ab, fn) in self.serien.items():
            e = self.naechste.get(eid, ab)
            while e <= bis:
                self.summe[eid] = round(self.summe.get(eid, 0.0) + fn(e), 6)
                zeilen.append({"m": self.mids[eid], "t": e, "s": self.summe[eid]})
                e += STUNDE
            self.naechste[eid] = e
        if zeilen:
            with self.svc._engine.begin() as c:
                c.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :s, :s)"), zeilen)

    def ha_summe(self, eid: str, von: datetime, bis: datetime):
        """HAs Zuwachs in ``[von, bis)`` (erste Zeile einer Statistik ab 0, wie HAs Energie-Dashboard)."""
        with self.svc._engine.begin() as c:
            rows = c.execute(text("select s.start_ts, s.sum from statistics s join statistics_meta m on m.id = s.metadata_id "
                                  "where m.statistic_id = :e order by s.start_ts"), {"e": eid}).all()
        vor = [s for t, s in rows if t < ep(von)]
        drin = [s for t, s in rows if ep(von) <= t < ep(bis)]
        return None if not drin else r3(drin[-1] - (vor[-1] if vor else 0.0))

    def mqtt_stand(self, t: datetime) -> float:
        null = START - timedelta(hours=5)
        if self.mqtt_neu is not None and t >= self.mqtt_neu:
            return round(0.9 * (t - self.mqtt_neu).total_seconds() / 3600, 6)
        return round(3000.0 + 0.9 * (t - null).total_seconds() / 3600, 6)


async def mach_welt(db, monkeypatch, serien: dict, zuordnung: dict, *, mqtt: bool, live: bool = True,
                    mqtt_neu: datetime | None = None) -> Welt:
    import backend.services.ha_statistics_service as hss
    import backend.services.zuordnung_wechsel.korrektur as kr
    from backend.models.anlage import Anlage
    from backend.models.investition import Investition
    from backend.services.live_power_service import LivePowerService
    from backend.tests import ha_lts_helfer as H

    svc = H.mach_service(thread_sicher=True)
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)

    async def kurve(self, anlage, db_, tage_zurueck=0, **_k):
        return {"serien": [], "punkte": [{"zeit": f"{h:02d}:00", "werte": {}} for h in range(24)],
                "vortagsrand": [{"zeit": "23:00", "werte": {}}]}
    monkeypatch.setattr(LivePowerService, "get_tagesverlauf", kurve)
    inv = {i: {"felder": {f: {"strategie": "sensor", "sensor_id": zuordnung[k]}}} for k, (i, f, _key, _komp) in FELDER.items()
           if k in zuordnung}
    mapping = {"basis": {"live": {"netzbezug_w": "sensor.netz_w"}} if live else {}, "investitionen": inv}
    if mqtt:
        mapping["quellen"] = {NETZ_FID: {"quelle": "mqtt_inbound_standard"}}
    a = Anlage(anlagenname="Weg B", leistung_kwp=10.0, sensor_mapping=mapping)
    db.add(a)
    await db.flush()
    db.add(Investition(id=1, anlage_id=a.id, typ="pv-module", bezeichnung="PV Feld", leistung_kwp=5.0,
                       anschaffungsdatum=date(2024, 1, 1)))
    db.add(Investition(id=2, anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1)))
    db.add(Investition(id=3, anlage_id=a.id, typ="pv-module", bezeichnung="PV Kontrolle", leistung_kwp=5.0,
                       anschaffungsdatum=date(2024, 1, 1)))
    await db.commit()
    w = Welt(db, svc, a, serien, mqtt_neu, mqtt)
    for eid in serien:
        w.mids[eid] = H.sensor(svc, eid, "kWh", has_sum=True)
    return w


async def anlage(w):
    from backend.models.anlage import Anlage

    return (await w.db.execute(select(Anlage).where(Anlage.id == w.a.id))).scalar_one()


async def laeufe() -> None:
    from backend.services.zuordnung_wechsel import korrektur_lauf

    for t in list(korrektur_lauf._AUFGABEN.values()):
        if not t.done():
            await t


def frisch(w) -> None:
    from backend.services.zuordnung_wechsel import zeitpunkt as zw

    w.db.expunge_all()
    zw.vergiss(w.db)


async def lauf_05(w, h: datetime) -> None:
    """Der Stundenlauf um ``h``:05 wie ``scheduler.sensor_snapshot_job``: MQTT-Rohstände der Stunde, Reihe, Kanäle, offene
    Wechsel ansetzen, Nachfüllen (Kanäle ohne Marke), offene Läufe."""
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.services.kanal.nachfuellen import nachfuellen_spiegel
    from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf
    from backend.services.sensor_snapshot_service import snapshot_anlage
    from backend.services.zuordnung_wechsel import korrektur_lauf
    from backend.services.zuordnung_wechsel.ansatz import offene_ansetzen

    if w.mit_mqtt:
        for m in (-45, -30, -15, 0):
            t = h + timedelta(minutes=m)
            if t >= START - timedelta(hours=5):
                w.db.add(MqttEnergySnapshot(anlage_id=w.a.id, timestamp=t, energy_key=NETZ_MK, value_kwh=w.mqtt_stand(t)))
        await w.db.commit()
    UHR.stelle(h + timedelta(minutes=5))
    w.ha_bis(ep(h) - STUNDE)
    a = await anlage(w)
    await snapshot_anlage(w.db, a, zeitpunkt=h)
    await w.db.commit()
    await schreibe_kanaele_im_stundenlauf(w.db, a, h)
    await w.db.commit()
    await offene_ansetzen(w.sitzungen, jetzt=_FDT.now())
    await laeufe()
    frisch(w)
    await nachfuellen_spiegel(w.sitzungen, w.a.id, jetzt=_FDT.now(), ha_svc=w.svc, nur_vorhandene=True)
    frisch(w)
    await korrektur_lauf.offene_anstossen(sitzungen=w.sitzungen)
    await laeufe()
    frisch(w)


async def aggregiere(w, t: datetime, tag: date) -> None:
    from backend.services.energie_profil._helpers import ohne_abruf
    from backend.services.energie_profil.aggregator import aggregate_day
    from backend.services.energie_profil.source import Source

    UHR.stelle(t)
    frisch(w)
    with ohne_abruf({}):
        await aggregate_day(await anlage(w), tag, w.db, source=Source.SCHEDULER)
    await w.db.commit()


async def betrieb_bis(w, von: datetime, bis: datetime, *, heute: bool = False) -> None:
    h = von
    while h <= bis:
        await lauf_05(w, h)
        if h.hour in (0, 2):
            await aggregiere(w, h + timedelta(minutes=15), h.date() - timedelta(days=1))
        if heute:
            await aggregiere(w, h + timedelta(minutes=15), h.date())
        h += timedelta(hours=1)


async def monatsabschluss_oktober(w) -> None:
    from fastapi import BackgroundTasks

    from backend.api.routes.monatsabschluss.views import get_monatsabschluss
    from backend.api.routes.monatsabschluss.wizard import FeldWert, InvestitionWerte, MonatsabschlussInput, save_monatsabschluss

    frisch(w)
    ma = await get_monatsabschluss(w.a.id, 2026, 10, w.db)
    invs = [InvestitionWerte(investition_id=i.id, felder=fw) for i in ma.investitionen
            if (fw := [FeldWert(feld=x.feld, wert=x.vorschlaege[0].wert) for x in i.felder if x.vorschlaege])]
    await save_monatsabschluss(w.a.id, 2026, 10, MonatsabschlussInput(investitionen=invs), BackgroundTasks(), w.db)
    await w.db.commit()
    frisch(w)


async def gespeichert_okt(w) -> dict:
    frisch(w)
    rows = (await w.db.execute(text("select investition_id, verbrauch_daten from investition_monatsdaten "
                                    "where jahr = 2026 and monat = 10"))).all()
    return {str(i): v for i, v in rows}


async def loeschen(w, T: datetime, feld_id: str, **body):
    """«Daten vor der Änderung löschen» über die Feld-Route (Prüf-Route vorher, wie der Client)."""
    from backend.api.routes.datenquellen import QuelleSetRequest, pruefe_feld_quelle, set_feld_quelle

    UHR.stelle(T)
    w.ha_bis(ep(T.replace(minute=0)) - STUNDE)
    p = await pruefe_feld_quelle(w.a.id, feld_id, QuelleSetRequest(**body), w.db)
    frisch(w)
    r = await set_feld_quelle(w.a.id, feld_id, QuelleSetRequest(**body, grund="loeschen"), w.db)
    await laeufe()
    frisch(w)
    return p, r


async def sichten(w, feld: str, tage: list[date], monat: tuple[int, int]) -> dict:
    """Tageswerte (``/energie-profil/…/tage``), Monatssicht, «Aus HA laden» und Monatsabschluss-Vorschlag eines Felds."""
    from backend.api.routes.energie_profil.monat import get_monatsauswertung
    from backend.api.routes.energie_profil.tage import get_tages_zusammenfassungen
    from backend.api.routes.ha_statistics import get_monatswerte
    from backend.api.routes.monatsabschluss.views import get_monatsabschluss
    from backend.services.kanal import merken

    inv, f, _key, komp = FELDER[feld]
    frisch(w)
    merken.invalidiere(w.a.id)
    tz = {t.datum: t for t in await get_tages_zusammenfassungen(w.a.id, min(tage), max(tage), w.db)}
    out = {"tage": {d: (None if d not in tz else r3((tz[d].komponenten_kwh or {}).get(komp))) for d in tage}}
    mon = await get_monatsauswertung(w.a.id, monat[0], monat[1], 10, w.db)
    out["monatssicht"] = next((r3(k.kwh) for k in mon.komponenten if k.key == komp), None)
    hs = await get_monatswerte(w.a.id, monat[0], monat[1], w.db)
    out["aus_ha_laden"] = next((r3(x.differenz) for i in hs.investitionen if str(i.investition_id) == inv
                                for x in i.felder if x.feld == f), None)
    ma = await get_monatsabschluss(w.a.id, monat[0], monat[1], w.db)
    out["vorschlag"] = next((r3(x.vorschlaege[0].wert) if x.vorschlaege else None for i in ma.investitionen if str(i.id) == inv
                             for x in i.felder if x.feld == f), None)
    await w.db.commit()
    merken.invalidiere(w.a.id)
    return out


async def netz_tage(w, tage: list[date]) -> dict:
    from backend.services.energie_profil.tage_werte import baue_tage_werte
    from backend.services.kanal import merken

    merken.invalidiere(w.a.id)
    frisch(w)
    z = {x.datum: x.netzbezug for x in await baue_tage_werte(w.db, await anlage(w), min(tage), max(tage))}
    await w.db.commit()
    return {d: r3(z.get(d)) for d in tage}


async def kanal_deckung(w, von: date, bis: date) -> list[date]:
    """Die Tage in ``[von, bis]`` ohne Kanal-Tag der Bilanz-Gruppe."""
    from backend.services.kanal import merken
    from backend.services.kanal.bilanz_leser import kanal_tage

    merken.invalidiere(w.a.id)
    kt = await kanal_tage(w.db, w.a.id, von, bis)
    return [von + timedelta(days=i) for i in range((bis - von).days + 1) if von + timedelta(days=i) not in kt]


async def befunde(w) -> dict[str, list[str]]:
    from backend.services.daten_checker import DatenChecker

    frisch(w)
    res = await DatenChecker(w.db).check_anlage(w.a.id)
    out: dict[str, list[str]] = {}
    for e in res.ergebnisse:
        if "ok" not in str(getattr(e, "schwere", "")).lower():
            out.setdefault(e.code, []).append(f"{e.meldung} || {e.details}")
    await w.db.rollback()
    frisch(w)
    return out


#: Befunde, die der Wechsel nicht auslösen darf (Halt-Kriterium «kein neuer Befund außer der Auskunft»).
VERBOTEN = ("tage_ohne_kanal_deckung", "drift_tag", "drift_komponente", "monatswert_ueberholt", "zaehler_zeit_verworfen",
            "zuordnung_grund_fehlt", "zaehler_versatz", "ha_zaehlersprung", "ha_zaehlerstand_springt", "zaehler_ruecksprung",
            "erfassung_stillstand", "tageswerte_fehlen_tag", "tageswerte_fehlen_tage")


# ── Lagen ──────────────────────────────────────────────────────────────────────────────────────────────────────────

LAGEN = {
    #: name → (T, erste HA-Zeile des neuen Sensors, Art)
    "jung": (T0, datetime(2026, 11, 4, 8), "ha"),
    "vormonat": (T0, datetime(2026, 10, 30, 8), "ha"),
    "ab_beginn": (T0, None, "ha"),
    "zwei_vorquellen": (T0, datetime(2026, 11, 4, 8), "vorquellen"),
    "monatserster": (datetime(2026, 11, 1, 10, 20), datetime(2026, 11, 1, 8), "ha"),
    "laufende_stunde": (T0, datetime(2026, 11, 4, 10), "ha"),
    "nur_ein_feld": (T0, datetime(2026, 11, 4, 8), "nur_b"),
    "import_1000": (T0, datetime(2026, 11, 4, 8), "import"),
    "ha_weg": (T0, datetime(2026, 10, 30, 8), "ha_weg"),
}


async def _welt_der_lage(db, monkeypatch, lage: str) -> tuple[Welt, datetime, datetime, str]:
    T, e_neu, art = LAGEN[lage]
    v = ep(START) - 5 * STUNDE
    e = v if e_neu is None else ep(e_neu)
    serien = {ALT: (v, lambda _e: 0.6)}
    zuo = {"pv": ALT}
    neu = NEU
    if art == "vorquellen":
        serien[NEU] = (v, lambda _e: 0.5)
        serien[C] = (e, lambda _e: 0.4)
        neu = C
    elif art == "import":
        serien[NEU] = (e, lambda x: 1000.4 if x == e else 0.4)
    else:
        serien[NEU] = (e, lambda _e: 0.4)
    if art != "nur_b":
        serien[PVC] = (v, lambda _e: 2.0)
        serien[WB] = (v, lambda _e: 1.32)
        zuo.update({"pvk": PVC, "wb": WB})
    w = await mach_welt(db, monkeypatch, serien, zuo, mqtt=art != "nur_b")
    return w, T, datetime.fromtimestamp(e), neu


async def _bis_zum_wechsel(w, T: datetime, *, vorquellen: bool = False) -> dict:
    abschluss = datetime(2026, 11, 2, 1) if T.day > 2 else datetime(2026, 11, 1, 1)
    await betrieb_bis(w, START, abschluss)
    UHR.stelle(abschluss + timedelta(minutes=20))
    await monatsabschluss_oktober(w)
    if vorquellen:                                            # A «bleiben» B am 02.11. 12:20, danach «löschen» auf C
        from backend.api.routes.datenquellen import QuelleSetRequest, set_feld_quelle

        tb = datetime(2026, 11, 2, 12, 20)
        await betrieb_bis(w, abschluss + timedelta(hours=1), tb.replace(minute=0))
        UHR.stelle(tb)
        w.ha_bis(ep(tb.replace(minute=0)) - STUNDE)
        await set_feld_quelle(w.a.id, "inv_energy_1_pv_erzeugung_kwh",
                              QuelleSetRequest(quelle="ha_app", entity_id=NEU, grund="fortsetzung"), w.db)
        await laeufe()
        frisch(w)
        await betrieb_bis(w, tb.replace(minute=0) + timedelta(hours=1), T.replace(minute=0))
    else:
        await betrieb_bis(w, abschluss + timedelta(hours=1), T.replace(minute=0))
    return await gespeichert_okt(w)


def _folgetag(T: datetime) -> datetime:
    return datetime.combine(T.date() + timedelta(days=1), datetime.min.time()) + timedelta(hours=3)


async def _nach_dem_wechsel(w, T: datetime, *, mittag: bool = False) -> dict:
    """Stundenläufe bis zum Folgetag 03:00 (bei ``mittag`` mit Bild um 12:20 am Tag des Wechsels), Heute-Lauf, Uhr 03:20."""
    out = {}
    weiter = T.replace(minute=0) + timedelta(hours=1)
    if mittag:
        m = T.replace(hour=12, minute=0)
        await betrieb_bis(w, weiter, m, heute=True)
        UHR.stelle(m.replace(minute=20))
        out["mittag"] = {f: (await sichten(w, f, [T.date()], (T.year, T.month)))["tage"][T.date()] for f in ("pv", "pvk", "wb")}
        out["mittag_ha"] = {eid: w.ha_summe(eid, datetime.combine(T.date(), datetime.min.time()), m) for eid in w.serien}
        weiter = m + timedelta(hours=1)
    folge = _folgetag(T)
    await betrieb_bis(w, weiter, folge)
    await aggregiere(w, folge + timedelta(minutes=15), folge.date())
    UHR.stelle(folge + timedelta(minutes=20))
    return out


def _tage(T: datetime, e_neu: datetime) -> list[date]:
    return sorted({START.date() + timedelta(days=1), T.date() - timedelta(days=1), T.date(), T.date() + timedelta(days=1),
                   e_neu.date(), max(START.date(), e_neu.date() - timedelta(days=1))})


async def _pruefe_soll(w, T: datetime, e_neu: datetime, neu: str, okt_vorher: dict, *, felder=("pv", "pvk", "wb"),
                      drift_tage: tuple[date, ...] = (), erwartet: tuple[str, ...] = ()) -> dict:
    """Das Soll der Tabelle A2 — über die Sichten gegen HA (die anderen Felder: ihre HA-Sensoren). ``erwartet``: Befund-Codes
    aus ``VERBOTEN``, die in dieser Lage stehen müssen (Fund-Päckchen B: «Zählerstand springt» an der importierten Statistik)."""
    tage = _tage(T, e_neu)
    monate = sorted({(T.year, T.month), (e_neu.year, e_neu.month)})
    ha_eid = {"pv": neu, "pvk": PVC, "wb": WB}
    bild = {}
    for feld in felder:
        for jm in monate:
            s = await sichten(w, feld, tage, jm)
            bild[(feld, jm)] = s
            von = datetime(jm[0], jm[1], 1)
            bis = datetime(jm[0] + (jm[1] == 12), jm[1] % 12 + 1, 1)
            ha_monat = w.ha_summe(ha_eid[feld], von, bis)
            sicht = ha_monat
            if feld == "wb" and jm == (WELTBEGINN.year, WELTBEGINN.month):
                # Weltrand (benannte Grenze, kein Wechsel-Thema): am ersten Tag der Welt beginnt auch der abgeleitete Kanal
                # «PV-Anteil der Heimladung» — die Regel «Anfangsstand 0» gilt nur für den HA-Spiegel, die Gruppe
                # E-Mobilität liest den Tag aus dem Bestand und verliert an der Naht zum Kanal-Tag eine Stunde (S4-R-3c).
                sicht = r3(ha_monat - 1.32)
            assert (s["monatssicht"], s["aus_ha_laden"], s["vorschlag"]) == (sicht, ha_monat, round(ha_monat, 1)), \
                (feld, jm, s, ha_monat)
            for d in tage:
                if (d.year, d.month) != jm or (feld == "wb" and d == WELTBEGINN):
                    continue
                tag_ha = w.ha_summe(ha_eid[feld], datetime.combine(d, datetime.min.time()),
                                    datetime.combine(d + timedelta(days=1), datetime.min.time()))
                assert s["tage"][d] == tag_ha, (feld, d, s["tage"][d], tag_ha)
    assert await kanal_deckung(w, START.date(), _folgetag(T).date()) == []
    b = await befunde(w)
    # Benannte Grenze (Lösungsweg ``drift_tag``): am ersten Tag der Welt beginnen alle Statistiken um 19:00 — die Prüfung liest
    # HAs Tageswert im Fenster [Vortag 23:00, 23:00) und nennt den Tag (PV 10,0 → HA 8,0), obwohl Tag und HA gleich sind.
    drift = [x for x in b.get("drift_tag", []) if not x.startswith(WELTBEGINN.isoformat())]
    assert sorted(x[:10] for x in drift) == sorted(d.isoformat() for d in drift_tage), drift
    b["drift_tag"] = None
    b = {c: v for c, v in b.items() if v}
    assert all(c in b for c in erwartet), (erwartet, sorted(b))
    assert not [c for c in VERBOTEN if c in b and c not in erwartet], {c: b[c] for c in VERBOTEN if c in b}
    assert len(b.get("daten_vor_aenderung_geloescht", [])) == 1, b.get("daten_vor_aenderung_geloescht")
    assert await gespeichert_okt(w) == okt_vorher
    return {"bild": bild, "befunde": b}


@pytest.mark.parametrize("lage", ["jung", "vormonat", "ab_beginn", "zwei_vorquellen", "monatserster", "laufende_stunde"])
async def test_loeschen_tag_und_monat_wie_ha_andere_felder_unberuehrt(db, monkeypatch, stehende_uhr, lage):
    w, T, e_neu, neu = await _welt_der_lage(db, monkeypatch, lage)
    okt = await _bis_zum_wechsel(w, T, vorquellen=lage == "zwei_vorquellen")
    p, r = await loeschen(w, T, "inv_energy_1_pv_erzeugung_kwh", quelle="ha_app", entity_id=neu)
    assert p["grund_erforderlich"] and p["loeschen"]["monate"] == ["2026-10"]
    assert [x["art"] for x in r["korrektur"]] == ["loeschen"]
    # gelöscht: die Zählerstände des Schlüssels vor dem Wechsel und seine Wechsel-Zeilen (auch die von «bleiben»)
    for sql in ("select count(*) from sensor_snapshots where sensor_key = :k and zeitpunkt < :t",
                "select count(*) from zuordnung_wechsel where sensor_key = :k"):
        assert (await w.db.execute(text(sql), {"k": FELDER["pv"][2], "t": T})).scalar_one() == 0, sql
    await _nach_dem_wechsel(w, T)
    erg = await _pruefe_soll(w, T, e_neu, neu, okt)
    # nur dieses Feld ist gelöscht: vor der ersten HA-Zeile des neuen Sensors «—»
    vortag = e_neu.date() - timedelta(days=1)
    if lage != "ab_beginn" and vortag >= START.date():
        assert (await sichten(w, "pv", [vortag], (vortag.year, vortag.month)))["tage"][vortag] is None


async def test_loeschen_junger_sensor_zahlen_der_tabelle(db, monkeypatch, stehende_uhr):
    """Die Zahlen der Tabelle A2 (Lage «jung»): Tag des Wechsels 6,4 (16 Stunden zu 0,4 ab 08:00, die erste zählt ab 0 wie HA),
    Monat 7,6 in drei Sichten; mittags am Tag des Wechsels die anderen Felder wie HA."""
    w, T, e_neu, neu = await _welt_der_lage(db, monkeypatch, "jung")
    okt = await _bis_zum_wechsel(w, T)
    await loeschen(w, T, "inv_energy_1_pv_erzeugung_kwh", quelle="ha_app", entity_id=neu)
    mittag = await _nach_dem_wechsel(w, T, mittag=True)
    assert mittag["mittag"] == {"pv": 1.6, "pvk": 24.0, "wb": 15.84}
    assert (mittag["mittag_ha"][neu], mittag["mittag_ha"][PVC], mittag["mittag_ha"][WB]) == (1.6, 24.0, 15.84)
    erg = await _pruefe_soll(w, T, e_neu, neu, okt)
    pv = erg["bild"][("pv", (2026, 11))]
    assert (pv["tage"][T.date()], pv["monatssicht"], pv["aus_ha_laden"], pv["vorschlag"]) == (6.4, 7.6, 7.6, 7.6)
    meldung, details = erg["befunde"]["daten_vor_aenderung_geloescht"][0].split(" || ")
    assert meldung == "PV Feld – PV-Erzeugung: Daten vor dem 04.11.2026 10:20 Uhr gelöscht"
    assert "Home Assistant führt den neuen Sensor seit dem 04.11.2026 08:00 Uhr" in details
    assert "Der 04.11.2026 ist für dieses Feld deshalb nicht vollständig: eedc zählt ihn, wie Home Assistant, erst ab 08:00 Uhr." \
        in details
    assert "Für 10/2026 ist ein Monatswert gespeichert. Er bleibt, wie er ist." in details


async def test_f2_nur_dieses_feld_bewusst_leere_tage_ohne_befund(db, monkeypatch, stehende_uhr):
    w, T, e_neu, neu = await _welt_der_lage(db, monkeypatch, "nur_ein_feld")
    okt = await _bis_zum_wechsel(w, T)
    await loeschen(w, T, "inv_energy_1_pv_erzeugung_kwh", quelle="ha_app", entity_id=neu)
    await _nach_dem_wechsel(w, T)
    s = await sichten(w, "pv", _tage(T, e_neu), (2026, 11))
    assert (s["tage"][T.date()], s["monatssicht"], s["aus_ha_laden"], s["vorschlag"]) == (6.4, 7.6, 7.6, 7.6)
    assert s["tage"][T.date() - timedelta(days=1)] is None
    b = await befunde(w)
    assert "tage_ohne_kanal_deckung" not in b and len(b["daten_vor_aenderung_geloescht"]) == 1
    from backend.services.kanal.bilanz_leser import GRUND_BEWUSST_LEER, bewusst_leere_tage, tage_bilanz

    leer = await bewusst_leere_tage(w.db, w.a.id, [START.date() + timedelta(days=i) for i in range(8)])
    assert leer == {START.date() + timedelta(days=i) for i in range(8)}
    tb = await tage_bilanz(w.db, w.a.id, START.date() + timedelta(days=1), START.date() + timedelta(days=1))
    assert tb[START.date() + timedelta(days=1)].wahl.gruende.get("") == GRUND_BEWUSST_LEER
    assert await gespeichert_okt(w) == okt


async def test_a_importierte_statistik_zeigt_den_sprung_wie_ha(db, monkeypatch, stehende_uhr):
    """(a) Die erste Zeile der neuen Statistik trägt ``sum`` 1 000 (importiert): Tag, Monatssicht, «Aus HA laden» und Vorschlag
    zählen sie ab dem Anfangsstand 0 — wie HA. Seit Fund-Päckchen B (22.11.2026) nennt «Zählerstand springt» die erste Stunde
    (Fall «Beginn nicht bei 0»; bis dahin kein Befund, benannte Grenze 2)."""
    w, T, e_neu, neu = await _welt_der_lage(db, monkeypatch, "import_1000")
    okt = await _bis_zum_wechsel(w, T)
    p, _r = await loeschen(w, T, "inv_energy_1_pv_erzeugung_kwh", quelle="ha_app", entity_id=neu)
    assert p["stand_neu"] == 1000.8                        # der Dialog zeigt den Stand der neuen Quelle
    await _nach_dem_wechsel(w, T)
    # Gemessen (Lage a): die Drift-Prüfung nennt den Tag — ihr LTS-Tagesweg verwirft die Stunde mit 1 000 kWh als
    # unplausibel (PV 1.054,4 → HA 53,6), Tagesansicht und Monat zählen sie wie HAs Energie-Dashboard.
    erg = await _pruefe_soll(w, T, e_neu, neu, okt, drift_tage=(T.date(),), erwartet=("ha_zaehlerstand_springt",))
    assert "+1.000,4 kWh (Stand 0,0 → 1.000,4, die Statistik beginnt mit diesem Stand statt bei 0)" in \
        erg["befunde"]["ha_zaehlerstand_springt"][0]
    pv = erg["bild"][("pv", (2026, 11))]
    assert (pv["tage"][T.date()], pv["monatssicht"], pv["aus_ha_laden"], pv["vorschlag"]) == (1006.4, 1007.6, 1007.6, 1007.6)


async def test_b_ha_nicht_erreichbar_die_geschichte_kommt_mit_dem_naechsten_stundenlauf(db, monkeypatch, stehende_uhr):
    """(b) Ist Home Assistant im Augenblick von «löschen» nicht erreichbar, löscht eedc trotzdem; der Lauf bleibt offen
    (Füllen gescheitert), der nächste Stundenlauf holt die Geschichte des neuen Sensors (Nachfüllen), der Lauf endet."""
    from backend.services.ha_statistics_service import HAStatisticsService
    from backend.services.zuordnung_wechsel import korrektur_lauf

    w, T, e_neu, neu = await _welt_der_lage(db, monkeypatch, "ha_weg")
    okt = await _bis_zum_wechsel(w, T)
    echt = HAStatisticsService.is_available
    monkeypatch.setattr(HAStatisticsService, "is_available", property(lambda self: False))
    await loeschen(w, T, "inv_energy_1_pv_erzeugung_kwh", quelle="ha_app", entity_id=neu)
    lauf = (await w.db.execute(text("select key from settings where key like 'korrektur_lauf:%'"))).scalar_one()
    z = await korrektur_lauf.stand(w.db, lauf[len(korrektur_lauf.PRAEFIX):])
    assert z["status"] == korrektur_lauf.LAEUFT and korrektur_lauf.fuellen_offen(z)
    monkeypatch.setattr(HAStatisticsService, "is_available", echt)
    await _nach_dem_wechsel(w, T)
    z = await korrektur_lauf.stand(w.db, lauf[len(korrektur_lauf.PRAEFIX):])
    assert z["status"] == korrektur_lauf.FERTIG and not korrektur_lauf.fuellen_offen(z)
    erg = await _pruefe_soll(w, T, e_neu, neu, okt)
    assert erg["bild"][("pv", (2026, 10))]["monatssicht"] == 16.0          # 30.10. ab 08:00 (6,4) + 31.10. (9,6)


async def test_mqtt_feld_beginnt_mit_dem_ersten_stand_danach(db, monkeypatch, stehende_uhr):
    """MQTT-Feld in einer Anlage mit HA-Feldern: «löschen» beim Wechsel Standard → Gateway (neuer Zähler ab 0) — Kanal, Stände
    und Rohstände des Schlüssels vor dem Wechsel sind weg, der Kanal beginnt mit dem ersten Stand danach; die HA-Felder bleiben."""
    w = await mach_welt(db, monkeypatch, {ALT: (ep(START) - 5 * STUNDE, lambda _e: 0.6),
                                          PVC: (ep(START) - 5 * STUNDE, lambda _e: 2.0)},
                        {"pv": ALT, "pvk": PVC}, mqtt=True, mqtt_neu=T0)
    await _bis_zum_wechsel(w, T0)
    p, r = await loeschen(w, T0, NETZ_FID, quelle="mqtt_gateway", quell_topic="neu/zaehler/netz")
    assert p["grund_erforderlich"] and r["korrektur"][0]["art"] == "loeschen"
    for sql in ("select count(*) from sensor_snapshots where sensor_key = :k and zeitpunkt < :t",
                "select count(*) from mqtt_energy_snapshots where energy_key = :m and timestamp < :t",
                "select count(*) from kanal_statistik s join kanal k on k.id = s.kanal_id where k.key = :k"):
        assert (await w.db.execute(text(sql), {"k": NETZ_KEY, "m": NETZ_MK, "t": T0})).scalar_one() == 0, sql
    await _nach_dem_wechsel(w, T0)
    kanal = (await w.db.execute(text("select min(s.start_ts) from kanal_statistik s join kanal k on k.id = s.kanal_id "
                                     "where k.key = :k"), {"k": NETZ_KEY})).scalar_one()
    assert datetime.fromtimestamp(kanal) == T0.replace(minute=0)
    s = await sichten(w, "pv", [T0.date()], (2026, 11))
    assert s["tage"][T0.date()] == w.ha_summe(ALT, datetime.combine(T0.date(), datetime.min.time()),
                                              datetime.combine(T0.date() + timedelta(days=1), datetime.min.time()))
    assert "daten_vor_aenderung_geloescht" in await befunde(w)


async def test_c_mqtt_feld_allein_sichtbare_netz_tageswerte(db, monkeypatch, stehende_uhr):
    """(c) Nur das MQTT-Feld ist zugeordnet (die Tagesansicht zeigt den Netzbezug): nach «löschen» zeigen die Tage davor «—»,
    der Tag des Wechsels zählt ab dem ersten gespeicherten Stand der neuen Quelle (wie jede neue MQTT-Zuordnung: Rohstände
    ab 10:20 von 0, gespeicherte Stände ab 11:00 ⇒ 11:00 … 23:00 = 12 × 0,9), der Folgetag bis 03:00 wie ohne Wechsel."""
    w = await mach_welt(db, monkeypatch, {}, {}, mqtt=True, live=False, mqtt_neu=T0)
    await _bis_zum_wechsel(w, T0)
    tage = [T0.date() - timedelta(days=1), T0.date(), T0.date() + timedelta(days=1)]
    assert (await netz_tage(w, tage))[tage[0]] == 21.6
    await loeschen(w, T0, NETZ_FID, quelle="mqtt_gateway", quell_topic="neu/zaehler/netz")
    await _nach_dem_wechsel(w, T0)
    assert await netz_tage(w, tage) == {tage[0]: None, tage[1]: 10.8, tage[2]: 2.7}
    b = await befunde(w)
    meldung, details = b["daten_vor_aenderung_geloescht"][0].split(" || ")
    assert meldung == "Netzbezug: Daten vor dem 04.11.2026 10:20 Uhr gelöscht"
    # WEGB-K (Nachmessung B3): «die neue Quelle» statt «der neue Sensor», die Zeit des ersten gespeicherten Stands (11:00), nicht
    # die volle Stunde davor (10:00, Beginn der ersten Kanal-Zeile = Nullpunkt)
    assert "als wäre die neue Quelle von Anfang an zugeordnet." in details
    assert ("eedc zählt die neue Quelle ab ihrem ersten gespeicherten Zählerstand am 04.11.2026 11:00 Uhr; davor zeigt das Feld "
            "«—»." in details)


async def test_dialog_zwei_antworten_und_kein_verwerfen(db, monkeypatch, stehende_uhr):
    """Der Abfrage-Vertrag: «löschen» und «bleiben»; «korrektur» (verwerfen) ist an der Feld-Route kein Grund mehr (400),
    ohne Antwort 422 mit dem Satz, der beide Antworten nennt; «Der neue Sensor zählt ab» gehört zu «bleiben» (422)."""
    from fastapi import HTTPException

    from backend.api.routes.datenquellen import QuelleSetRequest, set_feld_quelle

    w, T, _e_neu, neu = await _welt_der_lage(db, monkeypatch, "jung")
    await betrieb_bis(w, START, START + timedelta(days=1))
    UHR.stelle(START + timedelta(days=1, hours=1, minutes=20))
    w.ha_bis(ep(START + timedelta(days=1)))
    fid = "inv_energy_1_pv_erzeugung_kwh"
    assert "falsch_seit" not in QuelleSetRequest.model_fields
    for body, status, satz in (
        ({"grund": "korrektur"}, 400, "Unbekannter Grund: korrektur"),
        ({}, 422, "Sag eedc, ob die bisherigen Werte bleiben oder die Daten vor der Änderung gelöscht werden."),
        ({"grund": "loeschen", "zaehlt_ab": START + timedelta(days=1)}, 422, None),
    ):
        with pytest.raises(HTTPException) as e:
            await set_feld_quelle(w.a.id, fid, QuelleSetRequest(quelle="ha_app", entity_id=neu, **body), w.db)
        await w.db.rollback()
        assert e.value.status_code == status, (body, e.value.detail)
        assert satz is None or satz in str(e.value.detail), (body, e.value.detail)


def test_put_monatsdaten_leerer_netzbezug_ist_422_nicht_typeerror():
    """Bauplan Nr. 178 (Kleineres): ``PUT /monatsdaten/{id}`` mit ``netzbezug_kwh: null`` endete in ``TypeError`` beim Ableiten
    (``gesamtverbrauch_kwh``) — jetzt lehnt das Schema ab (FastAPI antwortet 422); ein nicht gesendetes Feld bleibt erlaubt."""
    from pydantic import ValidationError

    from backend.api.routes.monatsdaten import MonatsdatenUpdate

    for feld in ("netzbezug_kwh", "einspeisung_kwh"):
        with pytest.raises(ValidationError, match="kann nicht leer sein"):
            MonatsdatenUpdate(**{feld: None})
    assert MonatsdatenUpdate(notizen="x").model_dump(exclude_unset=True) == {"notizen": "x"}
    assert MonatsdatenUpdate(netzbezug_kwh=0.0).netzbezug_kwh == 0.0
