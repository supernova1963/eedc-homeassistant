"""Sensorwechsel Weg B, Sitzung B3a (Bauplan Nr. 184/2): die Werkbank «Werte vor dem Sensorbeginn verwerfen» nach einem verzeichneten
Wechsel «Bisherige Werte bleiben» — sie hebt die Wechsel des Felds bis zum Ende der ersten Stunde ab ihrem Zeitpunkt auf (derselbe
Baustein wie «löschen», ``feld_loeschen.loesche_wechsel``). Danach rechnet eedc wie ohne verzeichneten Wechsel (Bestand, v4.3.1):
«Aus HA laden» liest vor dem Zeitpunkt die heutige Entität statt des verworfenen alten Sensors. Ein späterer Wechsel bleibt.

Welt und Helfer wie ``test_werkbank_verwerfen_kommt_nicht_zurueck.py`` (HA-Langzeitstatistik im echten Recorder-Schema,
Datei-Datenbank; ``sensor.einsp`` → ``sensor.einsp_neu``, den HA zwei Tage vor dem Wechsel kennt).

Schwesterdateien: test_werkbank_verwerfen_kommt_nicht_zurueck.py, test_werkbank_verwerfen_vor_quellbeginn.py,
test_sensorwechsel_wegb_loeschen_proben.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import and_, select

from backend.models.zuordnung_wechsel import ANSATZ_SCHNITT, GRUND_FORTSETZUNG, HERKUNFT_WECHSEL, ZuordnungWechsel
from backend.services.kanal.nachfuellen import nachfuellen_anlage, nachfuellen_spiegel
from backend.services.repair_orchestrator import _reset_state_for_tests
from backend.tests import test_sensorwechsel_u3b_proben as U3B  # lädt alle Modelle, bevor die ``db``-Fixture das Schema anlegt
from backend.tests.test_kanal_nachfuellen import (  # noqa: F401 — Fixtures
    datei,
    ha,
)
from backend.tests.test_werkbank_verwerfen_kommt_nicht_zurueck import (
    EINSP,
    STUNDENLAUF,
    TAUSCH,
    _kanal,
    _neuer_sensor,
    _quellen,
    _stundenlauf,
    _verwerfen,
    _zuordnung,
)

ALT = {"art": "ha", "entity_id": "sensor.einsp"}
NEU = {"art": "ha", "entity_id": "sensor.einsp_neu"}


@pytest.fixture(autouse=True)
def _leer(monkeypatch):
    _reset_state_for_tests()
    monkeypatch.setattr("backend.services.zuordnung_wechsel.korrektur.ha_eingerichtet", lambda: False)


async def _aus_ha_laden(sitzungen, aid: int, svc, monkeypatch) -> float:
    """«Aus HA laden» für den Monat des Wechsels (Route ``/ha-statistics/monatswerte``), Feld Einspeisung."""
    import backend.services.ha_statistics_service as hss
    from backend.api.routes.ha_statistics import get_monatswerte
    from backend.services.zuordnung_wechsel.zeitpunkt import vergiss

    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    async with sitzungen() as s:
        vergiss(s, aid)
        r = await get_monatswerte(aid, TAUSCH.year, TAUSCH.month, s)
    return next(round(f.differenz, 3) for f in r.basis if f.feld == "einspeisung_kwh")


async def _wechsel(sitzungen, aid: int) -> list[tuple]:
    async with sitzungen() as s:
        return [(w.ab_ts, (w.vorher or {}).get("entity_id"), (w.nachher or {}).get("entity_id")) for w in (await s.execute(
            select(ZuordnungWechsel).where(and_(ZuordnungWechsel.anlage_id == aid, ZuordnungWechsel.sensor_key == EINSP))
            .order_by(ZuordnungWechsel.ab_ts))).scalars().all()]


@pytest.mark.parametrize("mit_zeile", [False, True], ids=["bestand_ohne_zeile", "nach_bleiben"])
async def test_werkbank_nach_bleiben_rechnet_wie_ohne_zeile(ha, datei, monkeypatch, mit_zeile):
    """Ohne Zeile (Bestand) und nach «bleiben» (Zeile ab der vollen Stunde nach dem Beginn der neuen Kanal-Quelle, wie
    ``zuordnung_wechsel/ansatz``: ``ab_ts`` = G + 1 h) liefert «Aus HA laden» nach der Werkbank dieselbe Zahl — die des neuen
    Sensors ab seiner ersten Zeile in HA; die Zeile «bleiben» ist aufgehoben, ein späterer Wechsel bleibt. Vor der Werkbank
    liest «Aus HA laden» mit der Zeile vor dem Wechsel den alten Sensor (andere Zahl)."""
    svc, _ = ha
    sitzungen, _pfad, aid, _gid = datei
    _neuer_sensor(svc, "sensor.einsp_neu", TAUSCH - timedelta(days=2))
    await nachfuellen_spiegel(sitzungen, aid, jetzt=TAUSCH, ha_svc=svc)
    await _zuordnung(sitzungen, aid, einspeisung="sensor.einsp_neu")
    await _stundenlauf(sitzungen, aid, svc, STUNDENLAUF)
    await nachfuellen_anlage(sitzungen, aid, jetzt=STUNDENLAUF, ha_svc=svc, nur_vorhandene=True)
    k = await _kanal(sitzungen, aid, EINSP)
    t = (await _quellen(sitzungen, k.id))[-1].gueltig_ab
    ab = datetime.fromtimestamp(t) + timedelta(hours=1)
    spaeter = ab + timedelta(days=2)
    ohne = await _aus_ha_laden(sitzungen, aid, svc, monkeypatch)
    if mit_zeile:
        async with sitzungen() as s:
            s.add_all([
                ZuordnungWechsel(anlage_id=aid, sensor_key=EINSP, erklaert_ts=ab, ab_ts=ab, vorher=ALT, nachher=NEU,
                                 grund=GRUND_FORTSETZUNG, herkunft=HERKUNFT_WECHSEL, ansatz=ANSATZ_SCHNITT,
                                 stand_alt_ende=1000.0, stand_neu_null=100.0),          # angesetzt (Rand-Stände)
                ZuordnungWechsel(anlage_id=aid, sensor_key=EINSP, erklaert_ts=spaeter, ab_ts=spaeter, vorher=NEU,
                                 nachher=NEU, grund=GRUND_FORTSETZUNG, herkunft=HERKUNFT_WECHSEL),   # «Zähler getauscht»
            ])
        assert await _aus_ha_laden(sitzungen, aid, svc, monkeypatch) != ohne           # die Zeile wirkt (B-0)
    await _verwerfen(sitzungen, aid, EINSP, t)
    assert await _aus_ha_laden(sitzungen, aid, svc, monkeypatch) == ohne
    assert await _wechsel(sitzungen, aid) == ([(spaeter, "sensor.einsp_neu", "sensor.einsp_neu")] if mit_zeile else [])


async def test_werkbank_mqtt_feld_der_zaehler_getauscht_in_der_ersten_stunde_bleibt(db):
    """Dritter Fall (Korrekturrunde WEGB-K, Nachmessung B1): MQTT-Feld Netzbezug (0,5 kWh/h), «Zähler getauscht» am 08.06. um
    10:20 eingetragen (der neue Zähler steht 2 000 höher). Die Werkbank mit ihrer Vorgabe-Zeit (Beginn der jüngsten Quelle =
    die Stunde des Tauschs, 10:00) hebt den Tausch nicht auf — sein ``ab_ts`` (11:00) liegt nach dem Zeitpunkt; nach der
    Neubildung des Tags zeigt die Tagesansicht 11,958 (die Minuten zwischen dem letzten alten und dem ersten neuen Stand fehlen,
    wie ohne Werkbank), nicht 2 012,0 (der Sprung als Menge)."""
    from sqlalchemy import text

    from backend.api.routes.sensorwechsel import ZaehlerGetauschtRequest, zaehler_getauscht
    from backend.services.zuordnung_wechsel.korrektur import sitzungen_wie

    async def getauscht(db_, aid_):
        await zaehler_getauscht(aid_, U3B.NETZ_FID, ZaehlerGetauschtRequest(getauscht_am=U3B.E + timedelta(minutes=3)), db_)
        await U3B._laeufe()
        U3B.zw.vergiss(db_)

    aid = (await U3B._anlage(db)).id
    await U3B.betrieb(db, aid, U3B.Saat(lambda x: U3B.wahr(x) + (2000.0 if x >= U3B.E else 0.0),
                                       handlungen=[(U3B.E + timedelta(minutes=40), getauscht)]))
    tag = U3B.E.date()
    assert (await U3B.tagesansicht(db, aid, [tag]))[0] == pytest.approx(11.958)
    t = (await db.execute(text("select max(q.gueltig_ab) from kanal_quelle q join kanal k on k.id = q.kanal_id "
                               "where k.anlage_id = :a and k.key = :k"), {"a": aid, "k": U3B.NETZ})).scalar_one()
    assert datetime.fromtimestamp(t) == U3B.E.replace(minute=0)              # die Vorgabe-Zeit der Werkbank
    sitzungen = sitzungen_wie(db, None)
    await _verwerfen(sitzungen, aid, U3B.NETZ, t)
    db.expunge_all()
    for d in (tag, tag + timedelta(days=1)):                                 # «Tag reparieren» bzw. Nachtlauf
        await U3B._tagesabschluss(db, aid, d)
    db.expunge_all()
    assert (await U3B.tagesansicht(db, aid, [tag]))[0] == pytest.approx(11.958)
    zeilen = (await db.execute(text("select grund, ab_ts from zuordnung_wechsel where anlage_id = :a"), {"a": aid})).all()
    assert [(g, str(a)[:16]) for g, a in zeilen] == [("fortsetzung", "2026-06-08 11:00")]
