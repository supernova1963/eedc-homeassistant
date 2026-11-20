"""Sensorwechsel — Korrekturrunde «Lab-K» (Bauplan Nr. 152–157; Diagnose ``opus-berichte/SENSORWECHSEL-LAB-DIAGNOSE-F1-F3-2026-11-20.md``,
Lab-Durchläufe 1 und 2a). Proben mit Sprengsatz — je Probe die Variante ``gebaut`` und eine benannte Variante ohne die
Reparatur (``monkeypatch`` im Prozess), die rot sein muss; dazu der Mutanten-Lauf der Ablage.

* **F1** das Ansetzen füllt bis zur Stunde, bis zu der seine Lage liest (``kanal/korrektur.fuell_ende`` = letzte volle Stunde
  vor jetzt): im Stundenlauf um :05 steht die Tausch-Stunde sofort, im Dialog zwischen H:05 und H:10 löscht es die schon
  geschriebene Zeile nicht; die abhängigen abgeleiteten Kanäle schreibt es bis jetzt fort (auch ohne verworfene Zeile).
  Dieselbe Grenze trägt die Korrektur «Bisherige Werte verwerfen» (Messung M-V: dieselbe Klasse).
* **W9/W5** Verwerfen-Vorschau: ein Fünf-Minuten-Stand vor «Falsch seit» prüft die Höhe gegen HAs Kurzzeitstatistik
  (``stueck._ha_rohsumme``); eine Lücke, deren Ende noch vor uns liegt, endet «jetzt».
* **F2** Überführung des Altbestands: nachgefüllte Geschichte der heutigen Entität ist keine Vor-Quelle und keine «eigenen
  Werte davor»; eine Änderung zwischen H:00 und H:05 bleibt ein Wechsel (``VORLAUF_S``).
* **F4** HA-Tag mit B-0: die frühere Entität eines Zählers, die heute ein anderer Zähler trägt, liest HAs eigene Reihe
  (``lts_aggregator._plan_anwenden(orig=…)``).
* **F5** «Der neue Sensor zählt ab» nicht vor dem vorigen Wechsel des Felds (``ansatz._vorige_grenze``).
* **W1/W3/W4/W6/W2** Wortlaute der Prüf-Antwort; **H1** Bezeichnungen von Home Assistant 2026.11 in Texten und Lösungswegen.

Schwesterdateien: test_sensorwechsel_u2a2_proben.py (Ansetzen), test_sensorwechsel_u2b_proben.py (Fragen, «zählt ab»),
test_sensorwechsel_s3_korrektur.py (Korrektur), test_sensorwechsel_s1_verzeichnen.py (Überführung), test_sensorwechsel_u3b_proben.py.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from backend.models import activity_log, mqtt_gateway_mapping  # noqa: F401 — Tabellen der Routen (Teil-Schema der Fixture)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw

STUNDE = 3600
ALT, NEU, PVC = "sensor.alt", "sensor.neu", "sensor.pv_kontrolle"
T1 = datetime(2026, 11, 3, 23)           # die Tausch-Stunde
FELDER = {"pv": ("1", "pv_erzeugung_kwh", "inv:1:pv_erzeugung_kwh"), "wb": ("2", "ladung_kwh", "inv:2:ladung_kwh"),
          "pvk": ("3", "pv_erzeugung_kwh", "inv:3:pv_erzeugung_kwh")}


def _ep(t: datetime) -> int:
    return int(time.mktime(t.timetuple()))


E1 = _ep(T1)


# ── Welt: Anlage, HA-Attrappe, Stundenlauf, Feld-Route ──────────────────────────────────────────────────────────────

class Welt:
    def __init__(self, db, svc, a, serien):
        self.db, self.svc, self.a, self.serien = db, svc, a, serien
        self.mids: dict[str, int] = {}
        self.summe: dict[str, float] = {}
        self.naechste: dict[str, int] = {}

    @property
    def sitzungen(self):
        from backend.services.zuordnung_wechsel.korrektur import sitzungen_wie

        return sitzungen_wie(self.db, None)

    def ha_bis(self, bis: int) -> None:
        """HA führt die Stundenzeilen mit ``start_ts ≤ bis`` (``sum`` = ``state`` = laufende Summe)."""
        zeilen = []
        for eid, (ab, fn) in self.serien.items():
            e = self.naechste.get(eid, ab)
            while e <= bis:
                z = fn(e)
                if z is not None:
                    self.summe[eid] = round(self.summe.get(eid, 0.0) + z, 6)
                    zeilen.append({"m": self.mids[eid], "t": e, "s": self.summe[eid]})
                e += STUNDE
            self.naechste[eid] = e
        if zeilen:
            with self.svc._engine.begin() as c:
                c.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :s, :s)"), zeilen)

    def kurz(self, eid: str, von: datetime, bis: datetime) -> None:
        """HAs Kurzzeitstatistik für ``eid`` in ``[von, bis)``: der Zuwachs der Stunde gleich auf zwölf Zeilen verteilt."""
        ab, fn = self.serien[eid]
        s, zeilen = 0.0, []
        for e in range(ab, _ep(bis), STUNDE):
            z = fn(e) or 0.0
            for k in range(12):
                s = round(s + z / 12, 6)
                if _ep(von) <= e + k * 300 < _ep(bis):
                    zeilen.append({"m": self.mids[eid], "t": e + k * 300, "s": s})
        with self.svc._engine.begin() as c:
            c.execute(text("INSERT INTO statistics_short_term (metadata_id, start_ts, state, sum) VALUES (:m, :t, :s, :s)"),
                      zeilen)


async def _welt(db, monkeypatch, serien: dict, zuordnung: dict) -> Welt:
    import backend.services.ha_statistics_service as hss
    import backend.services.zuordnung_wechsel.korrektur as kr
    from backend.services.live_power_service import LivePowerService
    from backend.tests import ha_lts_helfer as H

    svc = H.mach_service(thread_sicher=True)
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)

    async def kurve(self, anlage, db_, tage_zurueck=0, **_k):
        return {"serien": [], "punkte": [{"zeit": f"{h:02d}:00", "werte": {}} for h in range(24)],
                "vortagsrand": [{"zeit": "23:00", "werte": {}}]}
    monkeypatch.setattr(LivePowerService, "get_tagesverlauf", kurve)
    inv = {i: {"felder": {f: {"strategie": "sensor", "sensor_id": zuordnung[k]}}} for k, (i, f, _key) in FELDER.items()
           if k in zuordnung}
    basis = {"live": {"netzbezug_w": "sensor.netz_w"}}
    for feld in ("einspeisung", "netzbezug"):
        if feld in zuordnung:
            basis[feld] = {"strategie": "sensor", "sensor_id": zuordnung[feld]}
    a = Anlage(anlagenname="Lab-K", leistung_kwp=10.0, sensor_mapping={"basis": basis, "investitionen": inv})
    db.add(a)
    await db.flush()
    db.add(Investition(id=1, anlage_id=a.id, typ="pv-module", bezeichnung="PV", leistung_kwp=5.0, anschaffungsdatum=date(2024, 1, 1)))
    db.add(Investition(id=2, anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1)))
    db.add(Investition(id=3, anlage_id=a.id, typ="pv-module", bezeichnung="PV2", leistung_kwp=5.0, anschaffungsdatum=date(2024, 1, 1)))
    await db.commit()
    w = Welt(db, svc, a, serien)
    for eid in serien:
        w.mids[eid] = H.sensor(svc, eid, "kWh", has_sum=True)
    return w


async def _laeufe() -> None:
    from backend.services.zuordnung_wechsel import korrektur_lauf

    for t in list(korrektur_lauf._AUFGABEN.values()):
        if not t.done():
            await t


def _frisch(w: Welt) -> None:
    w.db.expunge_all()
    zw.vergiss(w.db)


async def _anlage(w: Welt) -> Anlage:
    return (await w.db.execute(select(Anlage).where(Anlage.id == w.a.id))).scalar_one()


async def _lauf(w: Welt, h: datetime) -> list:
    """Der Stundenlauf um ``h``:05 (Reihe, Kanal-Spiegel, offene Wechsel ansetzen)."""
    from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf
    from backend.services.sensor_snapshot_service import snapshot_anlage
    from backend.services.zuordnung_wechsel.ansatz import offene_ansetzen

    w.ha_bis(_ep(h) - STUNDE)
    a = await _anlage(w)
    await snapshot_anlage(w.db, a, zeitpunkt=h)
    await w.db.commit()
    await schreibe_kanaele_im_stundenlauf(w.db, a, h)
    await w.db.commit()
    erg = await offene_ansetzen(w.sitzungen, jetzt=h + timedelta(minutes=5))
    await _laeufe()
    _frisch(w)
    return erg


async def _betrieb(w: Welt, von: datetime, bis: datetime) -> None:
    for e in range(_ep(von), _ep(bis) + 1, STUNDE):
        await _lauf(w, datetime.fromtimestamp(e))


def _uhr(monkeypatch, U: datetime) -> None:
    """Die Uhr der Routen (Abfrage, Prüf-Route, Vorschau) auf ``U``."""
    import backend.api.routes.datenquellen as dq
    import backend.services.zuordnung_wechsel.abfrage as ab
    import backend.services.zuordnung_wechsel.korrektur as kr

    class Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return U
    for m in (ab, dq, kr):
        monkeypatch.setattr(m, "datetime", Uhr)


def _uhr_aus(monkeypatch) -> None:
    import backend.api.routes.datenquellen as dq
    import backend.services.zuordnung_wechsel.abfrage as ab
    import backend.services.zuordnung_wechsel.korrektur as kr

    for m in (ab, dq, kr):
        monkeypatch.setattr(m, "datetime", datetime)


async def _umstellen(w: Welt, monkeypatch, U: datetime, feld: str, neu: str, **k):
    from backend.api.routes.datenquellen import QuelleSetRequest, set_feld_quelle

    w.ha_bis(_ep(U.replace(minute=0, second=0)) - STUNDE)
    _uhr(monkeypatch, U)
    try:
        inv, f, _key = FELDER[feld]
        out = await set_feld_quelle(w.a.id, f"inv_energy_{inv}_{f}", QuelleSetRequest(quelle="ha_app", entity_id=neu, **k), w.db)
    finally:
        _uhr_aus(monkeypatch)
    await _laeufe()
    _frisch(w)
    return out


async def _pruefen(w: Welt, monkeypatch, U: datetime, feld: str, neu: str, **k) -> dict:
    from backend.api.routes.datenquellen import QuelleSetRequest, pruefe_feld_quelle

    _uhr(monkeypatch, U)
    try:
        inv, f, _key = FELDER[feld]
        out = await pruefe_feld_quelle(w.a.id, f"inv_energy_{inv}_{f}", QuelleSetRequest(quelle="ha_app", entity_id=neu, **k),
                                       w.db)
    finally:
        _uhr_aus(monkeypatch)
    _frisch(w)
    return out


async def _kanal(w: Welt, key: str) -> dict[int, float]:
    """``{start_ts: sum + Versatz der Quelle}`` des Schlüssels."""
    k = (await w.db.execute(select(Kanal).where(Kanal.anlage_id == w.a.id, Kanal.key == key))).scalar_one_or_none()
    if k is None:
        return {}
    quellen = (await w.db.execute(select(KanalQuelle.gueltig_ab, KanalQuelle.offset).where(KanalQuelle.kanal_id == k.id)
                                  .order_by(KanalQuelle.gueltig_ab))).all()
    zeilen = (await w.db.execute(select(KanalStatistik.start_ts, KanalStatistik.sum).where(KanalStatistik.kanal_id == k.id)))
    out = {}
    for t, s in zeilen.all():
        off = max((q for q in quellen if q[0] <= t), key=lambda q: q[0], default=(0, 0.0))[1]
        out[int(t)] = None if s is None else round(float(s) + float(off), 6)
    return out


def _stunde(kanal: dict[int, float], e: int):
    """Zuwachs der Kanal-Stunde ``e`` (``None``: die Zeile fehlt)."""
    if e not in kanal or e - STUNDE not in kanal:
        return None
    return round(kanal[e] - kanal[e - STUNDE], 6)


def _soll_ende(monkeypatch) -> None:
    """Sprengsatz F1: das Füllen endet wieder am Soll-Ende der Leser (70 Minuten Verzug), die Lage des Ansetzens liest wie
    am HEAD ``7311ad345`` bis zur letzten vollen Stunde (``ansatz.lage``)."""
    import sys

    import backend.services.kanal.korrektur as kk
    from backend.services.kanal.lesen import soll_ende

    def alt(jetzt_ts: int) -> int:
        if sys._getframe(1).f_code.co_name == "lage":
            return (int(jetzt_ts) // STUNDE) * STUNDE - STUNDE
        return soll_ende(jetzt_ts)
    monkeypatch.setattr(kk, "fuell_ende", alt)


START = T1 - timedelta(days=2)
_TAUSCH = {ALT: (_ep(START) - 5 * STUNDE, lambda e: 0.6 if e < E1 else (0.2 if e == E1 else None)),
           NEU: (E1, lambda e: 0.7 if e == E1 else 0.6), PVC: (_ep(START) - 5 * STUNDE, lambda e: 2.0)}


# ── F1 ────────────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("variante", ["gebaut", "soll_ende"])
async def test_f1_ansetzen_im_stundenlauf_fuellt_die_tauschstunde(db, monkeypatch, variante):
    """Tausch-Stunde 23:00 (alt +0,2, neu +0,7), Umstellung 23:24, Ansetzen im Stundenlauf 00:05: die Kanalzeile 23:00 steht
    sofort mit 0,9 (wie HA), ``fuellen.bis_ts`` = 23:00. Sprengsatz «soll_ende» ⇒ keine Zeile 23:00."""
    if variante == "soll_ende":
        _soll_ende(monkeypatch)
    w = await _welt(db, monkeypatch, _TAUSCH, {"pv": ALT, "pvk": PVC})
    await _betrieb(w, START, T1)
    await _umstellen(w, monkeypatch, T1 + timedelta(minutes=24), "pv", NEU, grund="fortsetzung")
    w.ha_bis(E1)
    erg = await _lauf(w, T1 + timedelta(hours=1))
    stunde = _stunde(await _kanal(w, FELDER["pv"][2]), E1)
    zustand = [z for k, z in (await w.db.execute(text("SELECT key, value FROM settings WHERE key LIKE 'korrektur_lauf:%'"))).all()]
    if variante == "soll_ende":
        assert stunde is None
        return
    assert stunde == pytest.approx(0.9)
    assert [e["kanal_neu_gespiegelt"] for e in erg if e.get("angesetzt")] == [1]
    assert any(f'"bis_ts": {E1}' in (z if isinstance(z, str) else str(z)) for z in zustand)


@pytest.mark.parametrize("variante", ["gebaut", "soll_ende"])
async def test_f1_dialog_zwischen_h05_und_h10_loescht_keine_zeile(db, monkeypatch, variante):
    """Der Stundenlauf 00:05 hat die Zeile 23:00 des alten geschrieben; Umstellung um 00:07 setzt sofort an: die Zeile 23:00
    steht danach mit beiden Sensoren (0,9). Sprengsatz «soll_ende» ⇒ das Ansetzen löscht sie und füllt nur bis 22:00."""
    if variante == "soll_ende":
        _soll_ende(monkeypatch)
    w = await _welt(db, monkeypatch, _TAUSCH, {"pv": ALT, "pvk": PVC})
    await _betrieb(w, START, T1 + timedelta(hours=1))
    assert _stunde(await _kanal(w, FELDER["pv"][2]), E1) == pytest.approx(0.2)        # der alte allein, vor dem Ansetzen
    await _umstellen(w, monkeypatch, T1 + timedelta(hours=1, minutes=7), "pv", NEU, grund="fortsetzung")
    stunde = _stunde(await _kanal(w, FELDER["pv"][2]), E1)
    assert stunde is None if variante == "soll_ende" else stunde == pytest.approx(0.9)


@pytest.mark.parametrize("variante", ["gebaut", "ohne_fortschreiben"])
async def test_f1_abgeleiteter_kanal_der_tauschstunde(db, monkeypatch, variante):
    """Ladezähler der Wallbox in der Tausch-Stunde getauscht (Umstellung 23:24): der PV-Anteil der Heimladung
    (``abgeleitet:inv:2:ladung_pv_kwh``) trägt die Zeile 23:00 direkt nach dem Ansetzen um 00:05. Sprengsatz
    «ohne_fortschreiben» (``schreibe_abgeleitete_nach`` nur nach verworfenen Zeilen, wie bisher) ⇒ die Zeile fehlt."""
    import backend.services.kanal.korrektur as kk

    if variante == "ohne_fortschreiben":
        original = kk.schreibe_abgeleitete_nach

        async def wie_bisher(sitzungen, anlage_id, erg, zeitpunkt, *, immer=False):
            return await original(sitzungen, anlage_id, erg, zeitpunkt)
        monkeypatch.setattr(kk, "schreibe_abgeleitete_nach", wie_bisher)
    ab0 = _ep(START) - 5 * STUNDE
    serien = {ALT: (ab0, lambda e: 1.2 if e < E1 else (0.4 if e == E1 else None)), NEU: (E1, lambda e: 0.8 if e == E1 else 1.2),
              PVC: (ab0, lambda e: 2.0), "sensor.einsp": (ab0, lambda e: 0.5), "sensor.netz": (ab0, lambda e: 0.3)}
    w = await _welt(db, monkeypatch, serien, {"wb": ALT, "pvk": PVC, "einspeisung": "sensor.einsp", "netzbezug": "sensor.netz"})
    await _betrieb(w, START, T1)
    await _umstellen(w, monkeypatch, T1 + timedelta(minutes=24), "wb", NEU, grund="fortsetzung")
    w.ha_bis(E1)
    await _lauf(w, T1 + timedelta(hours=1))
    abgeleitet = await _kanal(w, "abgeleitet:inv:2:ladung_pv_kwh")
    assert _stunde(await _kanal(w, FELDER["wb"][2]), E1) == pytest.approx(1.2)
    assert (E1 in abgeleitet) is (variante == "gebaut")


@pytest.mark.parametrize("variante", ["gebaut", "soll_ende"])
async def test_verwerfen_zwischen_h05_und_h10_fuellt_die_letzte_stunde(db, monkeypatch, variante):
    """Messung M-V, dieselbe Klasse wie F1: «Bisherige Werte verwerfen» um 00:07 (falsch seit 03.11. 00:00) löscht die vom
    Stundenlauf 00:05 geschriebene Zeile 23:00 des falschen Sensors und füllt sie aus dem richtigen (1,0). Sprengsatz
    «soll_ende» ⇒ die Stunde fehlt bis zum nächsten Stundenlauf."""
    if variante == "soll_ende":
        _soll_ende(monkeypatch)
    ab0 = _ep(START) - 5 * STUNDE
    w = await _welt(db, monkeypatch, {ALT: (ab0, lambda e: 0.6), NEU: (ab0, lambda e: 1.0), PVC: (ab0, lambda e: 2.0)},
                    {"pv": ALT, "pvk": PVC})
    await _betrieb(w, START, T1 + timedelta(hours=1))
    await _umstellen(w, monkeypatch, T1 + timedelta(hours=1, minutes=7), "pv", NEU, grund="korrektur",
                     falsch_seit=datetime(2026, 11, 3, 0))
    stunde = _stunde(await _kanal(w, FELDER["pv"][2]), E1)
    assert stunde is None if variante == "soll_ende" else stunde == pytest.approx(1.0)


# ── W9 / W5: Verwerfen-Vorschau ────────────────────────────────────────────────────────────────────────────────────

def _at(h: int, m: int, tag: int = 4) -> datetime:
    return datetime(2026, 11, tag, h, m)


@pytest.mark.parametrize("variante", ["gebaut", "stundenzeile"])
async def test_w9_fuenf_minuten_stand_vor_falsch_seit_fuellt_aus_ha(db, monkeypatch, variante):
    """Lab P1b (20.11. 02:14): eine Stunde mit fremdem Sensor, zurück mit «verwerfen» ab 01:00; vor «Falsch seit» liegt ein
    Fünf-Minuten-Stand (00:55). Home Assistant führt den richtigen Sensor für die Zeit ⇒ keine Lücke, kein Satz «füllt
    nichts». Sprengsatz «stundenzeile» (der Stand gegen HAs Stundenzeile geprüft, wie bisher) ⇒ Lücke 01:00 bis 03:00."""
    import backend.services.zuordnung_wechsel.stueck as st
    from backend.services.snapshot.writer import snapshot_anlage_5min
    from backend.services.zuordnung_wechsel.korrektur import ha_abruf

    if variante == "stundenzeile":
        async def wie_bisher(ha_svc, eid, key, z):
            import asyncio

            return await ha_abruf(asyncio.to_thread(ha_svc.get_value_at, eid, z))
        monkeypatch.setattr(st, "_ha_rohsumme", wie_bisher)
    ab0 = _ep(START) - 5 * STUNDE
    w = await _welt(db, monkeypatch, {NEU: (ab0, lambda e: 0.6), "sensor.fremd": (ab0, lambda e: 1.08),
                                      PVC: (ab0, lambda e: 2.0)}, {"pv": NEU, "pvk": PVC})
    await _betrieb(w, START, _at(1, 0))
    w.kurz(NEU, _at(0, 0), _at(2, 30))
    await snapshot_anlage_5min(w.db, await _anlage(w), _at(0, 55))
    await w.db.commit()
    await _umstellen(w, monkeypatch, _at(1, 27), "pv", "sensor.fremd", grund="fortsetzung")
    await _lauf(w, _at(2, 0))
    k = (await _pruefen(w, monkeypatch, _at(2, 14), "pv", NEU, grund="korrektur", falsch_seit=_at(1, 0)))["korrektur"]
    luecke = any("füllt nichts" in s for s in k["saetze"])
    if variante == "stundenzeile":
        assert k["luecke"] is not None and luecke
        return
    assert k["luecke"] is None and not luecke, k["saetze"]


@pytest.mark.parametrize("variante", ["gebaut", "ende_in_der_zukunft"])
async def test_w5_vorschau_in_der_tauschstunde_nennt_keine_zukunft(db, monkeypatch, variante):
    """Lab P1b (19.11. 23:44): «verwerfen», der richtige Sensor zählt erst seit 23:28 (noch keine volle Stunde). Die Vorschau
    nennt keinen Zeitpunkt nach jetzt («bis jetzt») und sagt «noch keine Stundenwerte». Sprengsatz «ende_in_der_zukunft»
    (der Satz wie bisher) ⇒ «bis 04.11.2026 00:00 Uhr»."""
    import backend.services.zuordnung_wechsel.korrektur as kr

    if variante == "ende_in_der_zukunft":
        monkeypatch.setattr(kr, "SATZ_BIS_JETZT", "Vom {von} bis {bis} Uhr")
    ab0 = _ep(START) - 5 * STUNDE
    w = await _welt(db, monkeypatch, {ALT: (ab0, lambda e: 0.6 if e <= E1 else None), NEU: (E1, lambda e: 0.4 if e == E1 else 0.6),
                                      PVC: (ab0, lambda e: 2.0)}, {"pv": ALT, "pvk": PVC})
    await _betrieb(w, START, T1)
    s = (await _pruefen(w, monkeypatch, T1 + timedelta(minutes=44), "pv", NEU, grund="korrektur",
                        falsch_seit=START))["korrektur"]["saetze"]
    zukunft = any("04.11.2026 00:00" in x for x in s)
    assert zukunft is (variante == "ende_in_der_zukunft"), s
    if variante == "gebaut":
        assert any(x.startswith(f"Vom {START:%d.%m.%Y %H:%M} Uhr bis jetzt füllt nichts") for x in s), s
        assert kr.SATZ_KANAL_OHNE_GESCHICHTE in s and "noch keine Stundenwerte" in kr.SATZ_KANAL_OHNE_GESCHICHTE


# ── F2: Überführung des Altbestands ────────────────────────────────────────────────────────────────────────────────

async def _f2_anlage(db, quellen: list[tuple[datetime, str]], staende: tuple[datetime, ...] = ()) -> Anlage:
    """Anlage mit Wallbox, Kanal ``inv:2:ladung_kwh`` mit den Quellzeilen ``(gültig ab, Entität)`` (so legt das Nachfüllen
    von v4.3.1 die Geschichte der heutigen Entität vor den ersten Eintrag) und Ständen der Reihe zu ``staende``."""
    a = Anlage(anlagenname="Altbestand", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    db.add(Investition(id=2, anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1)))
    k = Kanal(anlage_id=a.id, key="inv:2:ladung_kwh", einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    for ab, eid in quellen:
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(ab.timestamp()), familie="spiegel", statistic_id=eid, offset=0.0))
        db.add(KanalStatistik(kanal_id=k.id, start_ts=int(ab.timestamp()), sum=1.0, familie="spiegel"))
    for t in staende:
        db.add(SensorSnapshot(anlage_id=a.id, sensor_key="inv:2:ladung_kwh", zeitpunkt=t, wert_kwh=10.0, quelle="ha_statistics"))
    await db.flush()
    return a


async def _protokoll(db, aid: int, ts: datetime, vorher, nachher) -> None:
    from backend.models.activity_log import ActivityLog

    db.add(ActivityLog(timestamp=ts, kategorie="sensor_mapping", aktion="Datenquelle zugeordnet", anlage_id=aid,
                       details_json={"field_id": "inv_energy_2_ladung_kwh", "vorher": vorher, "nachher": nachher}))
    await db.flush()


def _ha(eid: str) -> dict:
    return {"quelle": "ha_app", "entity_id": eid}


async def _ueberfuehrt(db, aid: int) -> list[tuple]:
    from backend.services.zuordnung_wechsel.ueberfuehrung import ueberfuehre

    zaehlung = await ueberfuehre(db)
    rows = (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.anlage_id == aid)
                             .order_by(ZuordnungWechsel.erklaert_ts))).scalars().all()
    return [((r.vorher or {}).get("entity_id"), (r.nachher or {}).get("entity_id")) for r in rows], dict(zaehlung)


@pytest.mark.parametrize("variante", ["gebaut", "ohne_teil1", "ohne_teil2"])
async def test_f2_nachgefuellte_geschichte_ist_kein_wechsel(db, monkeypatch, variante):
    """Lab P9 / Fall R der Diagnose: Erst-Zuordnung 10:10 auf A (Protokoll ``vorher`` leer), 10:20 auf B; das Nachfüllen von
    v4.3.1 hat B's Geschichte vor beide Einträge gelegt, die Reihe hat davor keine Stände ⇒ **keine** Zeile. Sprengsätze:
    «ohne_teil1» ⇒ die Erst-Zuordnung wird «B → A»; «ohne_teil2» ⇒ «A → B» mit «eigenen Werten» aus B's Geschichte."""
    import backend.services.zuordnung_wechsel.ueberfuehrung as ue

    if variante == "ohne_teil1":
        monkeypatch.setattr(ue, "_kanal_zeigt_wechsel", lambda *a: True)
    if variante == "ohne_teil2":
        async def nie(*a):
            return False
        monkeypatch.setattr(ue, "_nur_geschichte_des_neuen", nie)
    a = await _f2_anlage(db, [(datetime(2026, 11, 1), "sensor.b")])
    await _protokoll(db, a.id, datetime(2026, 11, 10, 10, 10), None, _ha("sensor.a"))
    await _protokoll(db, a.id, datetime(2026, 11, 10, 10, 20), _ha("sensor.a"), _ha("sensor.b"))
    zeilen, zaehlung = await _ueberfuehrt(db, a.id)
    soll = {"gebaut": [], "ohne_teil1": [("sensor.b", "sensor.a")], "ohne_teil2": [("sensor.a", "sensor.b")]}[variante]
    assert zeilen == soll, (zeilen, zaehlung)
    if variante == "gebaut":
        assert zaehlung == {"vorher_unbekannt": 1, "ohne_eigene_werte": 1}


async def test_f2_spaet_berichtigt_und_mit_staenden_bleibt_ein_wechsel(db):
    """Fall R2 bzw. N der Diagnose (Gegenprobe zu Teil 2): mit einem Stand der Reihe vor dem Eintrag sind die Werte davor
    eigene ⇒ die Zeile «A → B» entsteht (Produktiv-Kopie: genau eine Zeile)."""
    a = await _f2_anlage(db, [(datetime(2026, 11, 1), "sensor.b")], staende=(datetime(2026, 11, 9, 12),))
    await _protokoll(db, a.id, datetime(2026, 11, 10, 10, 20), _ha("sensor.a"), _ha("sensor.b"))
    zeilen, _z = await _ueberfuehrt(db, a.id)
    assert zeilen == [("sensor.a", "sensor.b")]


@pytest.mark.parametrize("variante", ["gebaut", "ohne_vorlauf"])
async def test_f2_wechsel_zwischen_h00_und_h05_bleibt_ein_wechsel(db, monkeypatch, variante):
    """«ab Stunde − 1 h»: Änderung 10:02 mit leerem ``vorher`` — der Stundenlauf um 10:05 hat die Zeile 09:00 schon aus B
    geschrieben (Quelle B ab 09:00), davor A. ⇒ «A → B». Sprengsatz «ohne_vorlauf» (``VORLAUF_S = 0``) ⇒ B gilt als
    Vor-Quelle, «wirksam unverändert», keine Zeile."""
    import backend.services.zuordnung_wechsel.ueberfuehrung as ue

    if variante == "ohne_vorlauf":
        monkeypatch.setattr(ue, "VORLAUF_S", 0)
    a = await _f2_anlage(db, [(datetime(2026, 10, 1), "sensor.a"), (datetime(2026, 11, 10, 9), "sensor.b")],
                         staende=(datetime(2026, 11, 9, 12),))
    await _protokoll(db, a.id, datetime(2026, 11, 10, 10, 2), None, _ha("sensor.b"))
    zeilen, zaehlung = await _ueberfuehrt(db, a.id)
    assert zeilen == ([("sensor.a", "sensor.b")] if variante == "gebaut" else []), zaehlung


# ── F4: HA-Tag mit B-0, eine Entität in zwei Zählern ───────────────────────────────────────────────────────────────

async def _f4_welt(db, monkeypatch, wechsel: list[tuple[str, str, str, datetime, str]], zuordnung: dict) -> tuple:
    """Anlage mit PV (inv 1) und Wallbox (inv 2), HA führt alle Sensoren stündlich vom 22. bis 26.10. (``sensor.wb_alt``
    1,08 kWh/h, ``sensor.pv_alt`` 0,36 kWh/h); ``wechsel``: ``(Schlüssel, vorher, nachher, ab_ts, ansatz)``."""
    import backend.services.ha_statistics_service as hss
    from backend.tests import ha_lts_helfer as H

    svc = H.mach_service(thread_sicher=True)
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    raten = {"sensor.wb_alt": 1.08, "sensor.pv_alt": 0.36, "sensor.wb_neu": 1.32}
    for eid, rate in raten.items():
        mid = H.sensor(svc, eid, "kWh", has_sum=True)
        s, zeilen = 0.0, []
        for e in range(_ep(datetime(2026, 10, 22)), _ep(datetime(2026, 10, 27)), STUNDE):
            s = round(s + rate, 6)
            zeilen.append({"m": mid, "t": e, "s": s})
        with svc._engine.begin() as c:
            c.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :s, :s)"), zeilen)
    inv = {"1": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": zuordnung["pv"]}}},
           "2": {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": zuordnung["wb"]}}}}
    a = Anlage(anlagenname="F4", leistung_kwp=10.0, sensor_mapping={"basis": {}, "investitionen": inv})
    db.add(a)
    await db.flush()
    db.add(Investition(id=1, anlage_id=a.id, typ="pv-module", bezeichnung="PV", leistung_kwp=5.0, anschaffungsdatum=date(2024, 1, 1)))
    db.add(Investition(id=2, anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1)))
    for key, alt, neu, ab, ansatz in wechsel:
        db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=ab, ab_ts=ab, vorher={"art": "ha", "entity_id": alt},
                                nachher={"art": "ha", "entity_id": neu}, grund="fortsetzung", herkunft="wechsel", ansatz=ansatz))
    await db.commit()
    return a, {"1": await db.get(Investition, 1), "2": await db.get(Investition, 2)}


@pytest.mark.parametrize("variante", ["gebaut", "ohne_orig"])
async def test_f4_frueherer_sensor_eines_zaehlers_ist_heute_der_eines_anderen(db, monkeypatch, variante):
    """Lab P3 (Drift-Hinweis «27,0 → 9,0 kWh am 25.10.»): die Wallbox wechselte von ``wb_alt`` auf ``wb_neu``, das PV-Feld
    danach irrtümlich von ``pv_alt`` auf ``wb_alt``. Der HA-Tag 24.10. liest für die Wallbox ``wb_alt`` (24 × 1,08 = 25,92)
    und für die PV ``pv_alt`` (8,64). Sprengsatz «ohne_orig» (Ersetzung in der schon ersetzten Reihe) ⇒ Wallbox 8,64."""
    import backend.services.snapshot.lts_aggregator as la
    from backend.services.snapshot.lts_aggregator import get_komponenten_tageskwh_lts, wechsel_kwargs

    if variante == "ohne_orig":
        original = la._plan_anwenden

        def ohne(reihen, plan, *, streng=True, orig=None):
            return original(reihen, plan, streng=streng)
        monkeypatch.setattr(la, "_plan_anwenden", ohne)
    a, invs = await _f4_welt(db, monkeypatch, [
        ("inv:2:ladung_kwh", "sensor.wb_alt", "sensor.wb_neu", datetime(2026, 11, 18, 11), "schnitt"),
        ("inv:1:pv_erzeugung_kwh", "sensor.pv_alt", "sensor.wb_alt", datetime(2026, 11, 20, 2), "schnitt")],
        {"pv": "sensor.wb_alt", "wb": "sensor.wb_neu"})
    ha = await get_komponenten_tageskwh_lts(a, invs, date(2026, 10, 24), **await wechsel_kwargs(db, a.id))
    assert ha.get("pv_1") == pytest.approx(8.64)
    assert ha.get("wallbox_2") == pytest.approx(25.92 if variante == "gebaut" else 8.64)


async def test_f4_zwei_zaehler_derselben_entitaet_mit_verschiedener_geschichte_lesen_nicht_aus_ha(db, monkeypatch):
    """Tragen zwei Zähler heute dieselbe Entität, aber an diesem Tag verschiedene (eine hatte vorher ``pv_alt``), führt die
    Tabelle je Entität nur eine Reihe — der Tag liest nicht aus HA (Snapshot-Pfad; der Drift-Hinweis schweigt für den Tag).
    Sprengsatz im Mutanten-Lauf: ohne die Prüfung in ``_slot_plan`` las ein Zähler die Geschichte des anderen."""
    from backend.services.snapshot.lts_aggregator import get_komponenten_tageskwh_lts, wechsel_kwargs

    a, invs = await _f4_welt(db, monkeypatch, [
        ("inv:1:pv_erzeugung_kwh", "sensor.pv_alt", "sensor.wb_alt", datetime(2026, 11, 20, 2), "schnitt")],
        {"pv": "sensor.wb_alt", "wb": "sensor.wb_alt"})
    assert await get_komponenten_tageskwh_lts(a, invs, date(2026, 10, 24), **await wechsel_kwargs(db, a.id)) == {}


# ── F5, W1, W3, W4: «bleiben» zwischen zwei HA-Sensoren ────────────────────────────────────────────────────────────

async def _bleiben_welt(db, monkeypatch, wechsel_vorher: bool, *, alt_endet: datetime | None = None):
    """PV-Feld heute ``sensor.p1b_neu`` (vorher ``sensor.p1b_alt``, Wechsel 19.11. 23:00 «beide», wenn ``wechsel_vorher``);
    ``sensor.fremd`` zählt seit 08.10. (Überlappung). HA bis 20.11. 01:00."""
    import backend.services.ha_statistics_service as hss
    import backend.services.zuordnung_wechsel.korrektur as kr
    from backend.tests import ha_lts_helfer as H

    svc = H.mach_service(thread_sicher=True)
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)
    bis = _ep(datetime(2026, 11, 20, 1))
    reihen = {"sensor.fremd": (_ep(datetime(2026, 10, 8)), 1.08), "sensor.p1b_neu": (_ep(datetime(2026, 11, 19, 23)), 0.36),
              "sensor.p1b_alt": (_ep(datetime(2026, 10, 8)), 0.6)}
    for eid, (ab, rate) in reihen.items():
        mid = H.sensor(svc, eid, "kWh", has_sum=True)
        ende = _ep(alt_endet) if (eid == "sensor.p1b_alt" and alt_endet) else bis
        zeilen, s = [], 0.0
        for e in range(ab, ende + 1, STUNDE):
            s = round(s + rate, 6)
            zeilen.append({"m": mid, "t": e, "s": s})
        with svc._engine.begin() as c:
            c.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :s, :s)"), zeilen)
    a = Anlage(anlagenname="F5", leistung_kwp=10.0, sensor_mapping={"basis": {}, "investitionen": {
        "1": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.p1b_neu"}}}}})
    db.add(a)
    await db.flush()
    db.add(Investition(id=1, anlage_id=a.id, typ="pv-module", bezeichnung="PV", leistung_kwp=5.0, anschaffungsdatum=date(2024, 1, 1)))
    if wechsel_vorher:
        db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=FELDER["pv"][2], erklaert_ts=datetime(2026, 11, 19, 23, 24),
                                ab_ts=datetime(2026, 11, 20, 0), vorher={"art": "ha", "entity_id": "sensor.p1b_alt"},
                                nachher={"art": "ha", "entity_id": "sensor.p1b_neu"}, grund="fortsetzung", herkunft="wechsel",
                                ansatz="beide", stand_alt_ende=1.0, stand_neu_null=0.0))
    await db.commit()
    return a, svc


async def _angaben(db, a, svc, vorher: str, nachher: str, jetzt: datetime, zaehlt_ab=None):
    from backend.services.zuordnung_wechsel import bleiben
    from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus

    zw.vergiss(db)
    return await bleiben.angaben(db, a.id, FELDER["pv"][2], {"art": "ha", "entity_id": vorher}, {"art": "ha", "entity_id": nachher},
                                 ab_ts=ab_ts_aus(jetzt), erklaert_ts=jetzt, jetzt=jetzt, zaehlt_ab=zaehlt_ab, ha_svc=svc)


@pytest.mark.parametrize("variante", ["gebaut", "ohne_untergrenze"])
async def test_f5_zaehlt_ab_nicht_vor_dem_vorigen_wechsel(db, monkeypatch, variante):
    """Lab P1b → ``p3_alt`` (20.11. 01:27): der fremde Sensor zählt seit 08.10., das Feld führte bis 19.11. 23:00 ``p1b_alt``
    und danach ``p1b_neu``. Frühestens zulässig ist 20.11. 00:00 (der vorige Wechsel, ``ab_ts``); eine Stunde davor lehnt
    eedc mit dem Satz des Bereichs ab (422 an den Routen). Sprengsatz «ohne_untergrenze» ⇒ frühestens 08.10. 01:00."""
    import backend.services.zuordnung_wechsel.ansatz as an
    from backend.services.zuordnung_wechsel.bleiben import ZaehltAbAbgelehnt

    if variante == "ohne_untergrenze":
        monkeypatch.setattr(an, "_vorige_grenze", lambda *a: None)
    a, svc = await _bleiben_welt(db, monkeypatch, wechsel_vorher=True)
    jetzt = datetime(2026, 11, 20, 1, 27)
    b = await _angaben(db, a, svc, "sensor.p1b_neu", "sensor.fremd", jetzt)
    soll = "2026-11-20T00:00:00" if variante == "gebaut" else "2026-10-08T01:00:00"
    assert (b["ueberlappung"], b["zaehlt_ab_frueheste"], b["zaehlt_ab_spaeteste"]) == (True, soll, "2026-11-20T01:00:00")
    if variante == "gebaut":
        with pytest.raises(ZaehltAbAbgelehnt) as e:
            await _angaben(db, a, svc, "sensor.p1b_neu", "sensor.fremd", jetzt, zaehlt_ab=datetime(2026, 11, 19, 22))
        assert "zwischen 20.11.2026 00:00 und 20.11.2026 01:00 Uhr" in str(e.value)


async def test_w4_nach_der_wahl_steht_kein_hinweis_auf_das_feld(db, monkeypatch):
    """W4: ohne Wahl nennt der Satz das Feld «Der neue Sensor zählt ab», nach der Wahl einer Stunde nicht mehr."""
    from backend.services.zuordnung_wechsel import bleiben

    a, svc = await _bleiben_welt(db, monkeypatch, wechsel_vorher=False)
    jetzt = datetime(2026, 11, 20, 1, 27)
    ohne = await _angaben(db, a, svc, "sensor.p1b_neu", "sensor.fremd", jetzt)
    mit = await _angaben(db, a, svc, "sensor.p1b_neu", "sensor.fremd", jetzt, zaehlt_ab=datetime(2026, 11, 20, 0))
    assert any("wählst du unter «Der neue Sensor zählt ab»" in s for s in ohne["saetze"])
    assert not any("Der neue Sensor zählt ab" in s for s in mit["saetze"]), mit["saetze"]
    assert bleiben.SATZ_SCHNITT_GEWAEHLT.format(alt="sensor.p1b_neu", neu="sensor.fremd", g="20.11.2026 00:00") in mit["saetze"]


@pytest.mark.parametrize("alt_endet", [None, datetime(2026, 11, 19, 22)], ids=["alt_zaehlt_in_g", "alt_endet_vorher"])
async def test_w3_zaehlt_beide_nur_wenn_ha_den_alten_in_der_stunde_fuehrt(db, monkeypatch, alt_endet):
    """W3 (Lab P6: der alte endet 31.10. 23:51, die Stunde 00:00 zählt nur der neue): führt HA für den alten in der Stunde G
    (19.11. 23:00) keine Zeile, sagt die Antwort «zählt nur …» statt «zählt beide». Gegenprobe: der alte zählt in G mit."""
    from backend.services.zuordnung_wechsel import bleiben

    a, svc = await _bleiben_welt(db, monkeypatch, wechsel_vorher=False, alt_endet=alt_endet)
    b = await _angaben(db, a, svc, "sensor.p1b_alt", "sensor.p1b_neu", datetime(2026, 11, 20, 0, 21))
    satz = bleiben.SATZ_BEIDE if alt_endet is None else bleiben.SATZ_BEIDE_NUR_NEU
    assert satz.format(alt="sensor.p1b_alt", neu="sensor.p1b_neu", g="19.11.2026 23:00") in b["saetze"], b["saetze"]


@pytest.mark.parametrize("variante", ["gebaut", "ohne_mehrzahlregel"])
def test_w1_einzahl_und_laufende_stunde(monkeypatch, variante):
    """W1: «(1 Stunde)», «1 Tag»; zählt der neue ab der laufenden Stunde, kein «(0 Stunden)». Sprengsatz «ohne_mehrzahlregel»
    (immer Mehrzahl, wie bisher) ⇒ «1 Stunden»."""
    import backend.core.zahlenformat as zf
    from backend.services.zuordnung_wechsel import bleiben

    if variante == "ohne_mehrzahlregel":
        monkeypatch.setattr(zf, "fmt_anzahl", lambda n, e, m: f"{n} {m}")
    la = SimpleNamespace(t1=datetime(2026, 11, 19, 23), g=datetime(2026, 11, 19, 23), art="beide", alt_in_g=True, alt_von_ha=True)
    eins = bleiben._saetze(la, "a", "b", {"stunden": 1, "tage": 1}, [])
    null = bleiben._saetze(la, "a", "b", {"stunden": 0, "tage": 0}, [])
    if variante == "ohne_mehrzahlregel":
        assert "(1 Stunden)" in eins[2]
        return
    assert "(1 Stunde) und bildet 1 Tag im Hintergrund neu" in eins[2]
    assert null[2] == bleiben.SATZ_UMFANG_LAUFEND.format(g="19.11.2026 23:00")


# ── W6, W2: Stände und erster Wert der Prüf-Antwort ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("variante", ["gebaut", "nur_stundenzeile"])
async def test_w6_stand_jetzt_aus_der_kurzzeitstatistik(monkeypatch, variante):
    """W6: in der Stunde des Tauschs führt HA für den neuen Sensor nur Fünf-Minuten-Zeilen — der Dialog nennt seinen Stand
    jetzt (0,5). Sprengsatz «nur_stundenzeile» ⇒ keine Angabe."""
    import backend.services.kanal.angaben as ag
    from backend.tests import ha_lts_helfer as H

    if variante == "nur_stundenzeile":
        monkeypatch.setattr(ag, "_stand_kurzzeit", lambda *a: None)
    jetzt = datetime(2026, 11, 19, 23, 44)

    class Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return jetzt
    monkeypatch.setattr(ag, "datetime", Uhr)
    svc = H.mach_service(thread_sicher=True)
    mid = H.sensor(svc, NEU, "kWh", has_sum=True)
    for k in range(1, 6):
        H.zeile(svc, mid, jetzt - timedelta(minutes=5 * k + 5), state=0.5 - 0.1 * (k - 1), sum_wert=0.5 - 0.1 * (k - 1),
                tabelle="statistics_short_term")
    stand = await ag.zaehlerstand_ha_jetzt(svc, 0, "sum", NEU)
    assert stand == (pytest.approx(0.5) if variante == "gebaut" else None)


async def test_w2_erster_eigener_wert_aus_kanal_oder_reihe(db):
    """W2: «Eigene Werte seit …» nennt den frühesten eigenen Wert — der Kanal (seit 08.10.) vor der Reihe (seit 29.10.)."""
    from backend.services.zuordnung_wechsel.abfrage import Frage, _details

    a = Anlage(anlagenname="W2", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    db.add(Investition(id=2, anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1)))
    k = Kanal(anlage_id=a.id, key="inv:2:ladung_kwh", einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    for d in range(8, 31):
        db.add(KanalStatistik(kanal_id=k.id, start_ts=int(datetime(2026, 10, d, 12).timestamp()), sum=float(d), state=float(d),
                              familie="spiegel"))
    db.add(SensorSnapshot(anlage_id=a.id, sensor_key="inv:2:ladung_kwh", zeitpunkt=datetime(2026, 10, 29, 12), wert_kwh=1.0,
                          quelle="ha_statistics"))
    await db.flush()
    f = Frage("inv:2:ladung_kwh", {"art": "keine"}, {"art": "keine"}, True)
    await _details(db, a.id, f, None, datetime(2026, 11, 20, 1))
    assert (f.erster_wert.date(), f.tage) == (date(2026, 10, 8), 23)


# ── H1: Bezeichnungen von Home Assistant 2026.11 ───────────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[3]
_ORTE = (REPO / "docs" / "daten-checker", REPO / "eedc" / "backend" / "services", REPO / "eedc" / "frontend" / "src")


def _h1_verstoesse(texte: list[tuple[str, str]]) -> list[str]:
    """«Wert anpassen» gibt es in HA nicht; «Entwicklerwerkzeuge → Statistik» nur als älterer Weg neben dem neuen."""
    aus = []
    for name, t in texte:
        if "Wert anpassen" in t:
            aus.append(f"{name}: «Wert anpassen»")
        for teil in t.split("Entwicklerwerkzeuge → Statistik")[:-1]:
            if "Werkzeuge → Statistik" not in teil[-200:] and "Werkzeuge →\n" not in teil[-200:]:
                aus.append(f"{name}: «Entwicklerwerkzeuge → Statistik» ohne den Weg von HA 2026.11")
    return aus


def _h1_texte() -> list[tuple[str, str]]:
    out = []
    for ort in _ORTE:
        for p in ort.rglob("*"):
            if p.suffix in (".py", ".ts", ".tsx", ".md") and "test" not in p.name and p.is_file():
                out.append((p.name, p.read_text(encoding="utf-8").replace("*", "")))
    return out


def test_h1_bezeichnungen_von_home_assistant_2026_11():
    """H1 (Übersetzung des Lab-Frontends, HA 2026.11.2): Weg «Einstellungen → Werkzeuge → Statistik», Symbol «Summe anpassen»;
    der ältere Weg nur in Klammern daneben. Sprengsatz: ein eingeschobener Satz alter Fassung wird gefunden."""
    texte = _h1_texte()
    assert len(texte) > 300
    assert _h1_verstoesse(texte) == []
    alt = "Lösung in Home Assistant: Entwicklerwerkzeuge → Statistik → den Sensor suchen → beim Symbol „Wert anpassen“."
    assert len(_h1_verstoesse([("eingeschoben", alt)])) == 2
