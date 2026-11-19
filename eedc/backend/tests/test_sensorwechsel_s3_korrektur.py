"""Sensorwechsel mit Grund, Sitzung 3a — Korrektur als ein Lauf (Bauplan B-6, §7 Nr. 6–10, Konzept S-4/S-9).

Gegen die HA-Langzeitstatistik im echten Recorder-Schema und eine Datei-Datenbank (Fixtures aus ``test_kanal_nachfuellen.py``:
``sensor.einsp`` +1,25 kWh/h ab 1.4.2026, Lücke Tag 10–12). Jede Probe trägt ihren Sprengsatz im selben Test (der Prüfling mit
einem bewusst falschen Baustein muss rot werden).

* **A-B-A:** richtig ``sensor.einsp`` (A), falsch ``sensor.falsch`` (B, anderes Niveau) ab Tag 10, zurück auf A ab Tag 25. Der
  falsche Teil beginnt in A's HA-Lücke ⇒ verworfener Abschnitt Tag 10 – 12, A ab Tag 12 mit EINEM Versatz (R2).
* **MQTT:** ``basis:netzbezug`` ohne HA, ein falscher Publisher im Intervall — nichts wird gefüllt, der Stundenlauf schreibt
  nichts ins Intervall und setzt hinter ihm neu an.
* **Werkbank** «Werte vor dem Sensorbeginn verwerfen» mit Home Assistant (S-9): füllt die Geschichte des jüngsten Sensors vor ``t``.
* **Tage neu bilden** (Hintergrund): Fortsetzen, Wetter und Preis bleiben wie vorher (Korrekturrunde 3a-K, §10 Nr. 32; die
  Stundenzeilen, der Abruf und die Performance Ratio in ``test_sensorwechsel_s3ak_proben.py``), ein Fehler hält die übrigen
  Tage nicht auf.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import and_, func, insert, select, text

from backend.models.anlage import Anlage
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.settings import Settings
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.kanal import korrektur as kk
from backend.services.kanal import lesen
from backend.services.kanal.konsistenz import konsistenz_anlage
from backend.services.kanal.lesen import GRUND_VERWORFEN, zeitraum
from backend.services.kanal.nachfuellen import nachfuellen_spiegel
from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf
from backend.services.snapshot.keys import _sensor_key_to_mqtt_key
from backend.services.zuordnung_wechsel import korrektur as kr
from backend.services.zuordnung_wechsel import korrektur_lauf as kl
from backend.tests import ha_lts_helfer
from backend.tests.test_kanal_nachfuellen import (  # noqa: F401 — Fixtures
    JETZT,
    ZEIT,
    _ts,
    datei,
    ha,
)
from backend.tests.test_werkbank_verwerfen_kommt_nicht_zurueck import _kanal, _quellen, _stundenlauf, _zuordnung

EINSP = "basis:einspeisung"
NETZ = "basis:netzbezug"
F = ZEIT + timedelta(days=10)          # erste falsche Stunde = Beginn der HA-Lücke von A
AB = ZEIT + timedelta(days=25)
H0 = ZEIT + timedelta(days=12)         # erste HA-Zeile von A ab F
LAUF_JETZT = AB + timedelta(hours=3, minutes=5)
H = 3600


def _falscher_sensor(svc, sid="sensor.falsch", start=9000.0, rate=3.0) -> int:
    mid = ha_lts_helfer.sensor(svc, sid, "kWh")
    wert, t = start, ZEIT
    while t < JETZT.replace(minute=0):
        wert += rate
        ha_lts_helfer.zeile(svc, mid, t, state=wert, sum_wert=wert)
        t += timedelta(hours=1)
    return mid


async def _aba(ha, datei):
    """A bis F nachgefüllt, B (falsch) ab F, ab AB wieder A (der Stundenlauf legt beide Quellen an)."""
    svc, reihen = ha
    sitzungen, _p, aid, _g = datei
    _falscher_sensor(svc)
    await nachfuellen_spiegel(sitzungen, aid, jetzt=F, ha_svc=svc)
    await _zuordnung(sitzungen, aid, einspeisung="sensor.falsch")
    await _stundenlauf(sitzungen, aid, svc, AB)
    await _zuordnung(sitzungen, aid, einspeisung="sensor.einsp")
    await _stundenlauf(sitzungen, aid, svc, AB + timedelta(hours=3))
    k = await _kanal(sitzungen, aid, EINSP)
    assert [q.statistic_id for q in await _quellen(sitzungen, k.id)] == ["sensor.einsp", "sensor.falsch", "sensor.einsp"]
    return svc, reihen, sitzungen, aid, k


def _auftrag(aid, key=EINSP, f=F, ab=AB, nachher=None, vorher=None) -> kr.Auftrag:
    return kr.Auftrag(anlage_id=aid, sensor_key=key, falsch_seit=f, ab=ab,
                      vorher=vorher or {"art": "ha", "entity_id": "sensor.falsch"},
                      nachher=nachher if nachher is not None else {"art": "ha", "entity_id": "sensor.einsp"})


async def _korrigieren(sitzungen, a: kr.Auftrag, svc, jetzt=LAUF_JETZT) -> dict:
    async with sitzungen() as s:
        erg = await kr.fuehre_aus(s, a, ha_svc=svc, jetzt=jetzt)
        await s.commit()
    return await kr.nach_dem_commit(erg, ha_svc=svc, sitzungen=sitzungen, starten=False)


async def _alle_zeilen(sitzungen) -> dict[str, dict]:
    out = {}
    async with sitzungen() as s:
        for t in ("kanal_statistik", "sensor_snapshots", "mqtt_energy_snapshots", "tages_zusammenfassung",
                  "tages_energie_profil", "kanal"):
            spalten = [r[1] for r in (await s.execute(text(f"PRAGMA table_info({t})"))).all()]
            out[t] = {tuple(r[:2]): tuple(r) for r in (await s.execute(text(f"SELECT {', '.join(spalten)} FROM {t}"))).all()}
    return out


async def _zr(sitzungen, k, von: datetime, bis: datetime):
    from backend.services.kanal import merken

    merken.leeren()
    async with sitzungen() as s:
        return await zeitraum(s, k, _ts(von), _ts(bis), jetzt=_ts(LAUF_JETZT))


# ── A-B-A ───────────────────────────────────────────────────────────────────


async def test_aba_ein_versatz_nach_r2_und_delta_ueber_beide_grenzen_gemessen(ha, datei, monkeypatch):
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    vorher = await _alle_zeilen(sitzungen)
    s = await _korrigieren(sitzungen, _auftrag(aid), svc)
    assert s["kanal_beginn"] == _ts(H0) and s["versatz"] == pytest.approx(0.0)
    qs = [(q.gueltig_ab, q.statistic_id, q.verworfen_ts is not None) for q in await _quellen(sitzungen, k.id)]
    assert qs == [(_ts(ZEIT), "sensor.einsp", False), (_ts(F), "sensor.falsch", True), (_ts(H0), "sensor.einsp", False)]
    # Kanal = A wörtlich im ganzen richtigen Teil (Versatz 0), keine Zeile im verworfenen Teil
    nachher = await _alle_zeilen(sitzungen)
    zeilen = {key[1]: z for key, z in nachher["kanal_statistik"].items() if key[0] == k.id}
    a = reihen["sensor.einsp"]
    assert all(zeilen[t][2] == pytest.approx(a[t]["sum"]) for t in zeilen if _ts(H0) <= t < _ts(AB))
    assert not [t for t in zeilen if _ts(F) <= t < _ts(H0)]
    # Δ über ab_ts und über den Beginn der richtigen Quelle = gemessen (A +1,25 je Stunde)
    assert (await _zr(sitzungen, k, AB - timedelta(hours=1), AB + timedelta(hours=1))).delta == pytest.approx(2.5)
    assert (await _zr(sitzungen, k, H0 + timedelta(hours=1), H0 + timedelta(hours=3))).delta == pytest.approx(2.5)
    # Zeilenzählung je Tabelle: nichts außerhalb von Feld und Intervall
    for t in vorher:
        geaendert = {key for key in set(vorher[t]) | set(nachher[t]) if vorher[t].get(key) != nachher[t].get(key)}
        if t == "kanal_statistik":
            assert geaendert and all(key[0] == k.id and _ts(F) <= key[1] < _ts(AB) for key in geaendert)
        else:
            assert not geaendert, t
    async with sitzungen() as ss:
        w = (await ss.execute(select(ZuordnungWechsel))).scalars().all()
    assert [(x.grund, x.falsch_seit_ts, x.ab_ts) for x in w] == [("korrektur", F, AB)]


async def test_sprengsatz_versatz_der_spaeteren_quelle_bleibt_stehen(ha, datei, monkeypatch):
    """R1 statt R2: die richtige Quelle trägt den Versatz ihrer späteren Quellzeile ⇒ Sprung am Beginn."""
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    y = (await _quellen(sitzungen, k.id))[-1].offset
    assert abs(y) > 1.0

    async def r1(db, kanal, ref, ha_svc, eid, h0, spaeter):
        return float(spaeter.offset)

    monkeypatch.setattr(kk, "_versatz", r1)
    await _korrigieren(sitzungen, _auftrag(aid), svc)
    d = (await _zr(sitzungen, k, H0 - timedelta(hours=60), H0 + timedelta(hours=2)))
    assert d.teil_delta is not None and abs(d.teil_delta - (a_zuwachs := 2.5)) > 1.0, (d, a_zuwachs)


async def test_aba_konsistenzlauf_danach_korrigiert_nichts(ha, datei):
    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    await _korrigieren(sitzungen, _auftrag(aid), svc)
    erg = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    assert erg.fehler == 0 and erg.korrigiert == []
    async with sitzungen() as s:
        n = (await s.execute(select(func.count()).select_from(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(F), KanalStatistik.start_ts < _ts(H0))))).scalar_one()
    assert n == 0


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_konsistenzlauf_nach_stoerung_vor_f_laedt_nichts_in_den_verworfenen_abschnitt(ha, datei, monkeypatch,
                                                                                         sprengsatz):
    """§7 Nr. 8 (Messblatt S0: 336 Zeilen kamen zurück): HA korrigiert A **vor** F ⇒ der Konsistenzlauf lädt ab dort neu,
    über alle folgenden Abschnitte. Sprengsatz: ``abschnitte()`` wie bisher (verworfene Quelle als Spiegel-Abschnitt) ⇒ die
    Werte von B kommen in den verworfenen Abschnitt zurück."""
    from backend.services.kanal import konsistenz, nachfuellen
    from backend.tests.test_kanal_konsistenz import _verschiebe

    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    await _korrigieren(sitzungen, _auftrag(aid), svc)
    if sprengsatz:
        alt = nachfuellen.abschnitte

        def ohne_filter(quellen):
            return alt([SimpleNamespace(gueltig_ab=q.gueltig_ab, familie=q.familie, statistic_id=q.statistic_id,
                                        verworfen_ts=None) for q in quellen])

        monkeypatch.setattr(konsistenz, "abschnitte", ohne_filter)
        monkeypatch.setattr(nachfuellen, "abschnitte", ohne_filter)
    with svc._engine.connect() as c:
        mid = c.execute(text("SELECT id FROM statistics_meta WHERE statistic_id = 'sensor.einsp'")).scalar_one()
    _verschiebe(svc, mid, _ts(ZEIT + timedelta(days=5)), +1.0)
    erg = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    async with sitzungen() as s:
        n = (await s.execute(select(func.count()).select_from(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(F), KanalStatistik.start_ts < _ts(H0))))).scalar_one()
    assert erg.fehler == 0 and any(x["key"] == EINSP for x in erg.korrigiert)          # der Lauf hat gearbeitet …
    assert (n > 0) is sprengsatz                                                     # … aber nicht im Verworfenen


async def test_zeitraum_ueber_den_verworfenen_abschnitt_ist_nicht_voll(ha, datei, monkeypatch):
    """§7 Nr. 7 (auch die Feld-Auskunft ``kanal/feld_leser`` liest nur ``voll``) — Gegenprobe ohne die Regel ⇒ voll."""
    from backend.services.kanal.feld_leser import kanal_feldwerte

    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    await _korrigieren(sitzungen, _auftrag(aid), svc)
    von, bis = F - timedelta(hours=1), H0 + timedelta(hours=2)
    z = await _zr(sitzungen, k, von, bis)
    assert not z.voll and z.delta is None and z.grund == GRUND_VERWORFEN
    assert (await _zr(sitzungen, k, H0 + timedelta(hours=1), H0 + timedelta(hours=3))).voll
    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        assert EINSP not in await kanal_feldwerte(s, a.id, [EINSP], von, bis)
    monkeypatch.setattr(lesen, "_beruehrt_verworfen", lambda f, von, bis: False)
    z2 = await _zr(sitzungen, k, von, bis)
    assert z2.voll and z2.delta is not None


async def test_bewusst_leer_im_verworfenen_abschnitt_mit_zeilen_davor(ha, datei):
    """§7 Nr. 9 an der echten Lage: die richtigen Zeilen vor F stören nicht (je Abschnitt geprüft)."""
    from backend.services.kanal import merken
    from backend.services.kanal.bilanz_adapter import bewusst_leer

    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    await _korrigieren(sitzungen, _auftrag(aid), svc)
    merken.leeren()
    async with sitzungen() as s:
        bl = await bewusst_leer(s, aid)
    tag = _ts(F + timedelta(days=1))
    assert bl.leer(EINSP, tag, tag + 24 * H)
    assert not bl.leer(EINSP, _ts(F - timedelta(days=1)), _ts(F + timedelta(hours=2)))


# ── MQTT ────────────────────────────────────────────────────────────────────

D0 = ZEIT + timedelta(days=30)
MF, MAB = D0 + timedelta(hours=12), D0 + timedelta(hours=24)


async def _staende(sitzungen, aid, von, bis, start, rate):
    mk = _sensor_key_to_mqtt_key(NETZ)
    t, zeilen = von, []
    while t < bis:
        zeilen.append({"anlage_id": aid, "energy_key": mk, "timestamp": t,
                       "value_kwh": start + rate * (t - von).total_seconds() / H})
        t += timedelta(minutes=15)
    async with sitzungen() as s:
        await s.execute(insert(MqttEnergySnapshot), zeilen)


async def _mqtt_stundenlauf(sitzungen, aid, von, bis, monkeypatch, svc):
    monkeypatch.setattr("backend.services.ha_statistics_service.get_ha_statistics_service", lambda: svc)
    t = von
    while t <= bis:
        async with sitzungen() as s:
            a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
            await schreibe_kanaele_im_stundenlauf(s, a, t)
        t += timedelta(hours=1)


async def _mqtt_lage(ha, datei, monkeypatch):
    svc, _ = ha
    sitzungen, _p, aid, _g = datei
    await _zuordnung(sitzungen, aid, netzbezug=None)
    await _staende(sitzungen, aid, D0, MF, 100.0, 0.5)              # richtiger Publisher
    await _staende(sitzungen, aid, MF, MAB, 5000.0, 1.0)            # falscher Publisher
    await _mqtt_stundenlauf(sitzungen, aid, D0 + timedelta(hours=1), MAB, monkeypatch, svc)
    k = await _kanal(sitzungen, aid, NETZ)
    return svc, sitzungen, aid, k


def _mqtt_auftrag(aid):
    return _auftrag(aid, NETZ, MF, MAB, nachher={"art": "mqtt", "mqtt_key": _sensor_key_to_mqtt_key(NETZ), "topic": "neu"},
                    vorher={"art": "mqtt", "mqtt_key": _sensor_key_to_mqtt_key(NETZ), "topic": "alt"})


async def _im_intervall(sitzungen, k) -> int:
    async with sitzungen() as s:
        return (await s.execute(select(func.count()).select_from(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(MF),
            KanalStatistik.start_ts < _ts(MAB))))).scalar_one()


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_mqtt_stundenlauf_schreibt_danach_nichts_ins_intervall(ha, datei, monkeypatch, sprengsatz):
    svc, sitzungen, aid, k = await _mqtt_lage(ha, datei, monkeypatch)
    assert await _im_intervall(sitzungen, k) > 0
    if sprengsatz:
        # Beide Sicherungen weg: Rohstände bleiben stehen und keine verworfene Quelle (sonst scheitert der Lauf an der
        # Quellzeile an F, bevor er schreibt) ⇒ der Stundenlauf schreibt das Intervall neu.
        async def keine_rohstaende(db, a, ab):
            return 0, 0

        async def nichts(*a, **kw):
            return 0
        monkeypatch.setattr(kr, "_verwerfe_staende", keine_rohstaende)
        monkeypatch.setattr(kk, "_quellen_umschreiben", nichts)
    s = await _korrigieren(sitzungen, _mqtt_auftrag(aid), None, jetzt=MAB + timedelta(minutes=5))
    assert s["tage_neu"] == 0 and s["kanal_beginn"] is None
    assert await _im_intervall(sitzungen, k) == 0
    await _mqtt_stundenlauf(sitzungen, aid, MAB, MAB, monkeypatch, svc)
    assert (await _im_intervall(sitzungen, k) > 0) is sprengsatz


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_mqtt_hinter_dem_verworfenen_abschnitt_neu_angesetzt(ha, datei, monkeypatch, sprengsatz):
    """Ein neuer Publisher (Niveau 300) nach der Korrektur: kein Sprung von 300 − 106 über das Intervall. Sprengsatz: die
    Quellen bleiben wie sie waren (keine verworfene Quelle) ⇒ der Stundenlauf zählt den Niveau-Unterschied."""
    svc, sitzungen, aid, k = await _mqtt_lage(ha, datei, monkeypatch)
    if sprengsatz:
        async def nichts(*a, **kw):
            return 0
        monkeypatch.setattr(kk, "_quellen_umschreiben", nichts)
    await _korrigieren(sitzungen, _mqtt_auftrag(aid), None, jetzt=MAB + timedelta(minutes=5))
    await _staende(sitzungen, aid, MAB, MAB + timedelta(hours=3), 300.0, 0.5)
    await _mqtt_stundenlauf(sitzungen, aid, MAB + timedelta(hours=1), MAB + timedelta(hours=3), monkeypatch, svc)
    from backend.services.kanal import merken

    merken.leeren()
    async with sitzungen() as s:
        st = await lesen.stunden(s, k, _ts(MF - timedelta(hours=1)), _ts(MAB + timedelta(hours=2)), jetzt=_ts(JETZT))
    erste = [w for w in st.werte if w.start_ts >= _ts(MAB)][0]
    assert (erste.change is not None and erste.change > 100.0) is sprengsatz


# ── Werkbank «Werte vor dem Sensorbeginn verwerfen» mit Home Assistant (S-9) ─


@pytest.mark.parametrize("mit_ha", [True, False])
async def test_werkbank_fuellt_die_geschichte_des_juengsten_sensors(ha, datei, mit_ha, monkeypatch):
    from backend.services import verwerfen_vor_quellbeginn as vq
    from backend.services.kanal.verwerfen import text_aus_zeitpunkt

    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: False)      # «ohne»: Standalone, unabhängig vom Prozess-Zustand

    svc, _ = ha
    sitzungen, _p, aid, _g = datei
    tausch = ZEIT + timedelta(days=20)
    mid = ha_lts_helfer.sensor(svc, "sensor.einsp_neu", "kWh")
    t, wert = tausch - timedelta(days=2), 0.0
    while t < JETZT.replace(minute=0):
        wert += 2.0
        ha_lts_helfer.zeile(svc, mid, t, state=wert, sum_wert=wert)
        t += timedelta(hours=1)
    await nachfuellen_spiegel(sitzungen, aid, jetzt=tausch, ha_svc=svc)
    await _zuordnung(sitzungen, aid, einspeisung="sensor.einsp_neu")
    await _stundenlauf(sitzungen, aid, svc, tausch + timedelta(days=1))
    k = await _kanal(sitzungen, aid, EINSP)
    tt = _ts(tausch)
    async with sitzungen() as s:
        summary = await vq.fuehre_aus(s, aid, {"kanal": EINSP, "zeitpunkt": text_aus_zeitpunkt(tt)},
                                      ha_svc=svc if mit_ha else None)
    async with sitzungen() as s:
        vor_t = (await s.execute(select(func.count()).select_from(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts < tt)))).scalar_one()
    if mit_ha:
        assert vor_t == 48 and summary["kanal_neu_gespiegelt"] >= 48
        assert (await _zr(sitzungen, k, tausch - timedelta(hours=1), tausch + timedelta(hours=1))).delta == pytest.approx(4.0)
        qs = [(q.gueltig_ab, q.statistic_id, q.verworfen_ts is not None) for q in await _quellen(sitzungen, k.id)]
        assert qs == [(_ts(ZEIT), "sensor.einsp", True), (_ts(tausch - timedelta(days=2)), "sensor.einsp_neu", False)]
    else:                              # ohne Home Assistant: nur verworfen (wie bisher)
        assert vor_t == 0 and summary.get("kanal_neu_gespiegelt", 0) == 0


# ── Home Assistant eingerichtet, aber nicht erreichbar ─────────────────────


async def test_ha_nicht_erreichbar_der_lauf_startet_nicht(ha, datei, monkeypatch):
    from backend.services import verwerfen_vor_quellbeginn as vq

    svc, reihen, sitzungen, aid, k = await _aba(ha, datei)
    weg = SimpleNamespace(is_available=False)
    with pytest.raises(kr.KorrekturNichtStartbar):
        kr.ha_dienst(weg)
    assert kr.ha_dienst(svc) is svc
    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: False)
    assert kr.ha_dienst(None) is None                            # Standalone: ohne HA
    vorher = await _alle_zeilen(sitzungen)
    params = {"kanal": EINSP, "zeitpunkt": datetime.fromtimestamp((await _quellen(sitzungen, k.id))[-1].gueltig_ab)
              .strftime("%Y-%m-%dT%H:%M")}
    async with sitzungen() as s:
        _g, saetze, vorschau = await vq.plan_vorschau(s, aid, params, ha_svc=weg)
        assert vorschau["korrektur"]["startbar"] is False and "nicht erreichbar" in " ".join(saetze)
        with pytest.raises(kr.KorrekturNichtStartbar):
            await vq.fuehre_aus(s, aid, params, ha_svc=weg)
    assert await _alle_zeilen(sitzungen) == vorher


# ── Tage neu bilden (Hintergrund) ───────────────────────────────────────────


async def _tagzeile(sitzungen, aid, tag, mit_wetter=True):
    async with sitzungen() as s:
        s.add(TagesZusammenfassung(anlage_id=aid, datum=tag, komponenten_kwh={"einspeisung": 5.0},
                                   source_provenance={"komponenten_kwh.einspeisung": {"source": "external:ha_statistics:daily"}},
                                   temperatur_min_c=1.0 if mit_wetter else None, temperatur_max_c=9.0 if mit_wetter else None,
                                   boersenpreis_avg_cent=7.5 if mit_wetter else None,
                                   gti_summe_wh_m2=800.0 if mit_wetter else None, performance_ratio=0.8 if mit_wetter else None))


def _neubau_ohne_abruf(aufrufe: list):
    async def neubau(anlage, tag, db):
        aufrufe.append(tag)
        if tag == date(2026, 4, 20):
            raise RuntimeError("Abbruch an diesem Tag")
        alt = (await db.execute(select(TagesZusammenfassung).where(and_(
            TagesZusammenfassung.anlage_id == anlage.id, TagesZusammenfassung.datum == tag)))).scalar_one()
        await db.delete(alt)
        await db.flush()
        neu = TagesZusammenfassung(anlage_id=anlage.id, datum=tag, komponenten_kwh={"einspeisung": 6.0})
        db.add(neu)
        return neu, "lts"
    return neubau


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_tage_neu_bilden_wetter_und_preis_bleiben_fortgesetzt(datei, monkeypatch, sprengsatz):
    from backend.services import repair_orchestrator

    sitzungen, _p, aid, _g = datei
    tage = [date(2026, 4, 18), date(2026, 4, 19), date(2026, 4, 20), date(2026, 4, 21)]
    for t in tage:
        await _tagzeile(sitzungen, aid, t)
    aufrufe: list = []
    monkeypatch.setattr(repair_orchestrator, "_reparatur_aggregat", _neubau_ohne_abruf(aufrufe))
    if sprengsatz:
        async def nichts(*a, **kw):
            return 0
        monkeypatch.setattr(kl, "_wetter_und_preis_wie_vorher", nichts)
    async with sitzungen() as s:
        await kl.anlegen(s, "probe", aid, EINSP, tage)
        await s.execute(text("UPDATE settings SET value = json_set(value, '$.erledigt', 1) WHERE key = 'korrektur_lauf:probe'"))
    z = await kl.tage_neu_bilden(sitzungen, "probe")          # fortgesetzt nach einem «Neustart» beim zweiten Tag
    assert aufrufe == tage[1:] and z["status"] == kl.FERTIG and z["erledigt"] == 4
    assert [f["tag"] for f in z["fehler"]] == ["2026-04-20"]
    async with sitzungen() as s:
        rows = {r.datum: r for r in (await s.execute(select(TagesZusammenfassung))).scalars().all()}
    assert rows[tage[1]].komponenten_kwh == {"einspeisung": 6.0}
    if sprengsatz:
        assert rows[tage[1]].temperatur_min_c is None and rows[tage[1]].gti_summe_wh_m2 is None
    else:
        r = rows[tage[1]]
        assert (r.temperatur_min_c, r.temperatur_max_c, r.boersenpreis_avg_cent, r.gti_summe_wh_m2) == (1.0, 9.0, 7.5, 800.0)
        assert z["behalten"] == 2 * 4
    assert (await kl.tage_neu_bilden(sitzungen, "probe"))["status"] == kl.FERTIG    # zweimal = einmal
    assert len(aufrufe) == 3


async def test_offene_laeufe_nach_dem_start(datei, monkeypatch):
    sitzungen, _p, aid, _g = datei
    async with sitzungen() as s:
        await kl.anlegen(s, "offen", aid, EINSP, [])
        s.add(Settings(key="korrektur_lauf:fertig", value={"status": "fertig"}))
    async with sitzungen() as s:
        assert await kl.offene_laeufe(s) == ["offen"]
    assert await kl.fortsetzen_nach_dem_start(warte_s=0, sitzungen=sitzungen) == ["offen"]
    async with sitzungen() as s:
        assert (await kl.stand(s, "offen"))["status"] == kl.FERTIG
        assert json.dumps((await kl.stand(s, "fertig")))


async def test_neue_entitaet_ohne_geschichte_beginnt_mit_ihrer_ersten_zeile(ha, datei):
    """Die richtige Entität hat in HA erst ab dem Wechsel Zeilen (fabrikneu): verworfen bleibt [F, AB), die richtige Quelle
    beginnt an AB (ihre spätere Quellzeile des Stundenlaufs geht darin auf), Δ über AB = ihr eigener Zuwachs (+2,0 je Stunde).
    U1 Punkt 4: im Kanal beginnt das Intervall an der Zeile ``F − 1 h`` (sie trägt den Stand um F, den ersten falschen) — die
    Quelle davor (hier nicht die richtige) ist dort mit verworfen."""
    svc, reihen = ha
    sitzungen, _p, aid, _g = datei
    _falscher_sensor(svc)
    mid = ha_lts_helfer.sensor(svc, "sensor.neu", "kWh")
    t, wert = AB, 50.0
    while t < JETZT.replace(minute=0):
        wert += 2.0
        ha_lts_helfer.zeile(svc, mid, t, state=wert, sum_wert=wert)
        t += timedelta(hours=1)
    await nachfuellen_spiegel(sitzungen, aid, jetzt=F, ha_svc=svc)
    await _zuordnung(sitzungen, aid, einspeisung="sensor.falsch")
    await _stundenlauf(sitzungen, aid, svc, AB)
    await _zuordnung(sitzungen, aid, einspeisung="sensor.neu")
    await _stundenlauf(sitzungen, aid, svc, AB + timedelta(hours=3))
    k = await _kanal(sitzungen, aid, EINSP)
    s = await _korrigieren(sitzungen, _auftrag(aid, nachher={"art": "ha", "entity_id": "sensor.neu"}), svc)
    assert s["kanal_beginn"] == _ts(AB)
    qs = [(q.gueltig_ab, q.statistic_id, q.verworfen_ts is not None) for q in await _quellen(sitzungen, k.id)]
    assert qs == [(_ts(ZEIT), "sensor.einsp", False), (_ts(F) - H, "sensor.einsp", True), (_ts(F), "sensor.falsch", True),
                  (_ts(AB), "sensor.neu", False)]
    async with sitzungen() as ss:
        n = (await ss.execute(select(func.count()).select_from(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(F), KanalStatistik.start_ts < _ts(AB))))).scalar_one()
    assert n == 0
    assert (await _zr(sitzungen, k, AB + timedelta(hours=1), AB + timedelta(hours=3))).delta == pytest.approx(4.0)
    assert not (await _zr(sitzungen, k, F - timedelta(hours=1), AB + timedelta(hours=2))).voll
