"""Sensorwechsel mit Grund, Sitzung 3a — Korrektur als ein Lauf (Bauplan B-6, §7 Nr. 6–10, Konzept S-4/S-9); seit Weg B, Sitzung
B3a, ohne die Korrektur selbst: ihre Proben (A-B-A, MQTT, neue Entität) sind mit ihr entfernt, geblieben sind der Lauf «Tage neu
bilden» und die Proben der Werkbank mit Home Assistant (S-9).

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
from backend.services.kanal.lesen import zeitraum
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


# ── A-B-A ───────────────────────────────────────────────────────────────────


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


# ── Werkbank «Werte vor dem Sensorbeginn verwerfen» mit Home Assistant (S-9) ─


# ── Home Assistant eingerichtet, aber nicht erreichbar ─────────────────────


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


