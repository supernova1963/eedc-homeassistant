"""Tagesstand-Reihen als Kanäle (HA-Bauform S4, Etappe E-S4-3, S4-R-3e).

Ein Stand um 00:00 wird die Kanalzeile 23:00 (Stand zur vollen Stunde ``Z`` = Stand am Ende von ``[Z − 1 h, Z)``) und liegt
seit R-3 (Kalendertag, E-S4-1) genau auf der Grenze des Kanal-Tags ``[D 00:00, D+1 00:00)``. Damit gilt ohne eine Regel
im Lese-Pfad (``lesen.py`` unverändert, Regel (c) «nicht feiner als die Spanne»):

* **Tagesstand-Reihe** (ein Stand je Tag um 00:00): Tag exakt Stand(00:00 D+1) − Stand(00:00 D), Monat exakt; die
  Stunden-Sicht zeigt EINE Zeile (Stunde 23, Beginn-Raster) mit Spanne 24 h («enthält 24 Stunden»), Regel (c) hält.
* **Paar-Reihe** (Stände um 23:00 und 00:00, mess3/skala3: 13 Reihen): Tag exakt; Stunde 22 trägt den Tag ohne die letzte
  Stunde (Spanne 23 h), Stunde 23 die letzte Stunde — HAs Lückenregel, als Spanne sichtbar.
* **Laufender Tag** mit Tagesstand: vor dem nächsten Mitternachtsstand hat der Tag keine Zeile — Abdeckung (b) der
  Lese-Schicht regelt ihn (gemessen, benannt).

Gegen eine Datei-Datenbank (Fixture ``datei`` aus ``test_kanal_eigene_summe_nachfuellen.py``): reine MQTT-Anlage, ein
MQTT-Rohstand macht den Netzbezug zum Zähler der Bilanz-Gruppe (``_snapshot_eintraege``). Keine Probe liest die Uhr.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import insert

from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.kanal import fenster, lesen
from backend.services.kanal.nachfuellen import nachfuellen_eigene_summe
from backend.services.kanal.stunden_adapter import stunden_aus_kanaelen
from backend.services.kanal.stunden_leser import kanal_stundentag
from backend.tests.test_kanal_eigene_summe_nachfuellen import _staende, _ts, datei  # noqa: F401 — Fixture

NETZ = "basis:netzbezug"
AB = datetime(2026, 6, 1, 0)
TAGE = 40
#: Tag ``i`` (ab 01.06.) verbraucht ``i + 1`` kWh; Stand um 00:00 des Tags ``i``.
STAND = {i: 1000.0 + sum(range(1, i + 1)) for i in range(TAGE + 1)}
JETZT = _ts(datetime(2026, 7, 15, 0, 30))


async def _anlage_mit_reihe(datei, folge: dict[int, float], *, quelle: str = "mqtt_inbound"):
    sitzungen, aid = await datei()
    await _staende(sitzungen, aid, NETZ, folge, quelle=quelle, ab=AB)
    async with sitzungen() as s:                     # macht den Netzbezug zum MQTT-Zähler der Bilanz-Gruppe
        await s.execute(insert(MqttEnergySnapshot), [{"anlage_id": aid, "energy_key": "netzbezug_kwh",
                                                       "timestamp": AB + timedelta(minutes=30), "value_kwh": 1.0}])
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=datetime.fromtimestamp(JETZT))
    assert erg.fehler == 0 and erg.gefuellt == 1
    return sitzungen, aid, erg


async def _netz(sitzungen, aid):
    async with sitzungen() as s:
        return (await lesen.kanaele_laden(s, aid, {NETZ}))[NETZ]


@pytest.mark.parametrize("quelle", ["mqtt_inbound", "ha_statistics"])
async def test_tagesstand_reihe_tag_exakt_eine_stunde_mit_spanne_24h(datei, quelle):
    sitzungen, aid, erg = await _anlage_mit_reihe(datei, {i * 24: STAND[i] for i in range(TAGE + 1)}, quelle=quelle)
    assert erg.tagesstand_reihen == 1
    k = await _netz(sitzungen, aid)
    async with sitzungen() as s:
        for i in (0, 4, 17, 29):
            d = AB.date() + timedelta(days=i)
            von, bis = fenster.tagesfenster(d)
            z = (await lesen.zeitraum_stapel(s, [k], von, bis, jetzt=JETZT))[NETZ]
            assert (z.voll, z.delta, z.rand_spanne) == (True, pytest.approx(STAND[i + 1] - STAND[i]), 86400), (d, z)
            st = (await lesen.stunden_stapel(s, [k], von, bis, jetzt=JETZT))[NETZ]
            assert [(datetime.fromtimestamp(w.start_ts).hour, w.change, w.spanne) for w in st.werte] == [
                (23, pytest.approx(i + 1.0), 86400)]
        von, bis = fenster.monatsfenster(2026, 6)
        juni = (await lesen.zeitraum_stapel(s, [k], von, bis, jetzt=JETZT))[NETZ]
        assert juni.voll and juni.delta == pytest.approx(STAND[30] - STAND[0]) == sum(range(1, 31))
        tag = await kanal_stundentag(s, aid, date(2026, 6, 5), jetzt=JETZT)
    assert tag.wahlen["bilanz"].quelle == "kanal"
    zeilen = [z for z in stunden_aus_kanaelen(tag).zeilen if z.netzbezug_kw]
    assert [(z.stunde, z.netzbezug_kw, z.spannen) for z in zeilen] == [(23, 5.0, {"netzbezug": 24})]


async def test_paar_reihe_tag_exakt_stunde_22_mit_spanne_stunde_23_die_letzte(datei):
    """Stände um 23:00 und 00:00 (wie mess3 Anlage 2: je Tag D die Stände D 23:00 und D+1 00:00); die letzte Stunde des
    Tags verbraucht 0,5 kWh."""
    folge = {}
    for i in range(TAGE):
        folge[i * 24 + 23] = STAND[i + 1] - 0.5
        folge[(i + 1) * 24] = STAND[i + 1]
    sitzungen, aid, erg = await _anlage_mit_reihe(datei, folge, quelle="ha_statistics")
    assert erg.tagesstand_reihen == 0                  # unterer Median der Abstände 1 h: gilt als stündlich
    k = await _netz(sitzungen, aid)
    async with sitzungen() as s:
        d = date(2026, 6, 10)
        von, bis = fenster.tagesfenster(d)
        z = (await lesen.zeitraum_stapel(s, [k], von, bis, jetzt=JETZT))[NETZ]
        assert z.voll and z.delta == pytest.approx(10.0)
        st = (await lesen.stunden_stapel(s, [k], von, bis, jetzt=JETZT))[NETZ]
        assert [(datetime.fromtimestamp(w.start_ts).hour, w.change, w.spanne) for w in st.werte] == [
            (22, pytest.approx(9.5), 23 * 3600), (23, pytest.approx(0.5), 3600)]
        tag = await kanal_stundentag(s, aid, d, jetzt=JETZT)
    zeilen = [z for z in stunden_aus_kanaelen(tag).zeilen if z.netzbezug_kw]
    assert [(z.stunde, z.netzbezug_kw, z.spannen) for z in zeilen] == [(22, 9.5, {"netzbezug": 23}), (23, 0.5, None)]


async def test_laufender_tag_mit_tagesstand_abdeckung_b(datei):
    """Um 10:30 des Tags D trägt die Reihe als letzte Zeile D−1 23:00 (Stand D 00:00): der laufende Tag ist nicht voll —
    die Lese-Schicht nennt ihn ``laufend``, ``endet_vor_bis`` mit Teil-Δ 0 (Abdeckung (b): die letzte Zeile liegt vor dem
    Soll-Ende); die Bilanz-Gruppe nimmt für ihn den Bestand. Der Vortag ist exakt."""
    sitzungen, aid, _ = await _anlage_mit_reihe(datei, {i * 24: STAND[i] for i in range(21)})
    jetzt = _ts(datetime(2026, 6, 21, 10, 30))
    k = await _netz(sitzungen, aid)
    async with sitzungen() as s:
        heute = date(2026, 6, 21)
        z = (await lesen.zeitraum_stapel(s, [k], *fenster.tagesfenster(heute), jetzt=jetzt))[NETZ]
        gestern = (await lesen.zeitraum_stapel(s, [k], *fenster.tagesfenster(heute - timedelta(days=1)),
                                               jetzt=jetzt))[NETZ]
        tag = await kanal_stundentag(s, aid, heute, jetzt=jetzt)
    assert (z.laufend, z.voll, z.grund, z.teil_delta) == (True, False, "endet_vor_bis", 0.0), z
    assert gestern.voll and gestern.delta == pytest.approx(STAND[20] - STAND[19])
    assert tag.wahlen["bilanz"].quelle == "bestand"
