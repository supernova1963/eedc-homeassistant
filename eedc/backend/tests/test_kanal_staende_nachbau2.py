"""Nachbau 2 mit HA (HA-Bauform S4, E-S4-3, S4-R-N2): Stände und Spiegel in EINEM Kanal.

Gegen die HA-Langzeitstatistik im echten Recorder-Schema und eine Datei-Datenbank (Fixtures aus
``test_kanal_nachfuellen.py``: ``sensor.einsp`` ab ``ZEIT``, 40 Tage). Die Stände in ``sensor_snapshots`` kommen aus der Zeit
VOR HAs Statistik (``ha_statistics``, z. B. ein früherer Sensor desselben Felds) und reichen in HAs Zeit hinein.

* **Spiegel zuerst:** der Startlauf füllt den Spiegel aus HA, danach die Stände nur VOR der ersten Spiegel-Zeile; die Stände
  in HAs Zeit bleiben draußen, die Spiegel-Zeilen sind dieselben wie ohne Stände. Die Naht hat keinen Zuwachs.
* **Marke ohne Pingpong:** die Marke des Kanals bleibt die des Spiegels (``statistic_id`` = Entity), der Stände-Teil steht in
  ``ergebnis["staende"]``; ein zweiter Startlauf fragt weder HA noch die Stände neu.
* **H-5 (benannt):** war HA beim ersten Start nicht erreichbar, tragen die Stände den Kanal bis zur letzten Stunde; der
  Spiegel setzt danach fort, das Spiegel-Nachfüllen und der Konsistenzlauf ersetzen die Stände-Zeilen nicht.
* **Verworfen bleibt leer:** nach «Werte vor dem Sensorbeginn verwerfen» füllen die Stände die verworfene Zeit nicht wieder.

Keine Probe liest die Uhr. Schwesterdateien: test_kanal_eigene_summe_nachfuellen.py, test_kanal_nachfuellen.py,
test_werkbank_verwerfen_kommt_nicht_zurueck.py.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, delete, func, insert, select

from backend.models.kanal import Kanal, KanalNachfuellung, KanalQuelle, KanalStatistik
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.kanal.konsistenz import konsistenz_anlage
from backend.services.kanal.nachfuellen import nachfuellen_anlage, nachfuellen_eigene_summe
from backend.tests.test_kanal_konsistenz import _verschiebe
from backend.tests.test_kanal_nachfuellen import (  # noqa: F401 — Fixtures
    JETZT,
    ZEIT,
    _stundenlauf,
    _ts,
    datei,
    ha,
)

EINSP = "basis:einspeisung"
VORLAUF_TAGE = 5
_H = 3600


async def _staende_ha(sitzungen, aid: int, *, bis_tage: int = 10) -> None:
    """Stände ``ha_statistics`` ab ``ZEIT − 5 Tage`` stündlich bis ``ZEIT + bis_tage`` (Stand steigt 3 kWh je Stunde)."""
    beginn = ZEIT - timedelta(days=VORLAUF_TAGE)
    n = (VORLAUF_TAGE + bis_tage) * 24
    async with sitzungen() as s:
        await s.execute(insert(SensorSnapshot), [
            {"anlage_id": aid, "sensor_key": EINSP, "zeitpunkt": beginn + timedelta(hours=h), "wert_kwh": 7000.0 + 3 * h,
             "quelle": "ha_statistics"} for h in range(1, n)])


async def _kanal(sitzungen, aid: int, key: str = EINSP):
    async with sitzungen() as s:
        k = (await s.execute(select(Kanal).where(and_(Kanal.anlage_id == aid, Kanal.key == key)))).scalar_one()
        zeilen = list((await s.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id)
                                       .order_by(KanalStatistik.start_ts))).scalars().all())
        quellen = list((await s.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id)
                                        .order_by(KanalQuelle.gueltig_ab))).scalars().all())
        marke = (await s.execute(select(KanalNachfuellung).where(KanalNachfuellung.kanal_id == k.id))).scalar_one_or_none()
        return k, zeilen, quellen, marke


def _kanalwerte(zeilen, quellen) -> dict[int, float]:
    out = {}
    for z in zeilen:
        q = max((q for q in quellen if q.gueltig_ab <= z.start_ts), key=lambda q: q.gueltig_ab)
        out[z.start_ts] = z.sum + q.offset
    return out


async def test_spiegel_zuerst_staende_nur_davor_naht_ohne_zuwachs(ha, datei):
    svc, reihen = ha
    sitzungen, _pfad, aid, _gid = datei
    await _staende_ha(sitzungen, aid)
    erg = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    _, zeilen, quellen, marke = await _kanal(sitzungen, aid)
    erste_ha = min(reihen["sensor.einsp"])
    spiegel = [z for z in zeilen if z.familie == "spiegel"]
    staende = [z for z in zeilen if z.familie == "mitschrift"]
    # Spiegel-Zeilen = HAs Zeilen (wie ohne Stände), Stände nur davor.
    assert {z.start_ts: z.sum for z in spiegel} == {
        ts: w["sum"] for ts, w in reihen["sensor.einsp"].items() if ts <= _ts(JETZT.replace(minute=0) - timedelta(hours=1))}
    assert staende and max(z.start_ts for z in staende) < erste_ha == min(z.start_ts for z in spiegel)
    # Stände ab ZEIT − 5 Tage + 1 h ⇒ Zeilen bis vor HAs erste Zeile (je Zone: eine Umstellungsnacht hat 23 Stunden)
    beginn = ZEIT - timedelta(days=VORLAUF_TAGE)
    erwartet = {_ts(beginn + timedelta(hours=h)) - _H for h in range(1, VORLAUF_TAGE * 24 + 24)}
    assert len(staende) == len({t for t in erwartet if t < erste_ha})
    assert [(q.familie, q.statistic_id) for q in quellen] == [("mitschrift", f"sensor_snapshots:{EINSP}"),
                                                              ("spiegel", "sensor.einsp")]
    w = _kanalwerte(zeilen, quellen)
    assert w[erste_ha] == w[erste_ha - _H]                         # Naht ohne Zuwachs
    assert w[erste_ha - _H] - w[erste_ha - 2 * _H] == 3.0           # davor HAs Summen von damals wörtlich
    assert marke.statistic_id == "sensor.einsp" and marke.ergebnis["staende"] == {"zeilen": len(staende)}
    assert erg.eigene_summe.gefuellt == 1 and erg.eigene_summe.zeilen == len(staende)


async def test_zweiter_startlauf_fragt_weder_ha_noch_die_staende_neu(ha, datei):
    svc, _ = ha
    sitzungen, _pfad, aid, _gid = datei
    await _staende_ha(sitzungen, aid)
    await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    _, vorher, _, marke_vorher = await _kanal(sitzungen, aid)
    zweit = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    _, nachher, _, marke = await _kanal(sitzungen, aid)
    assert zweit.gefuellt == 0 and zweit.uebersprungen.get("schon_gefuellt", 0) >= 1
    assert zweit.eigene_summe.uebersprungen == {"schon_gefuellt": 1} and zweit.eigene_summe.zeilen == 0
    assert len(nachher) == len(vorher) and marke.ergebnis == marke_vorher.ergebnis


async def test_h5_ohne_ha_beim_start_tragen_die_staende_der_spiegel_ersetzt_sie_nicht(ha, datei):
    """H-5 (benannt): HA beim ersten Start nicht erreichbar ⇒ die Stände füllen den Kanal bis zur letzten Stunde vor
    ``jetzt``. Danach schreibt der Stundenlauf HAs Zeilen dahinter; das Spiegel-Nachfüllen findet als erste Quelle die
    Stände (``vorgeschichte_andere_quelle``), der Konsistenzlauf lädt nur Spiegel-Abschnitte neu — die Stände-Zeilen bleiben."""
    svc, _ = ha
    sitzungen, _pfad, aid, _gid = datei
    await _staende_ha(sitzungen, aid)
    start = ZEIT + timedelta(days=10)
    aus = type("Aus", (), {"is_available": False})()
    erst = await nachfuellen_anlage(sitzungen, aid, jetzt=start, ha_svc=aus)
    assert erst.eigene_summe.gefuellt == 1
    _, z1, _, _ = await _kanal(sitzungen, aid)
    staende_vorher = {z.start_ts: z.sum for z in z1}
    assert max(staende_vorher) < _ts(start) and all(z.familie == "mitschrift" for z in z1)
    await _stundenlauf(sitzungen, aid, svc, start + timedelta(days=2))
    spaeter = await nachfuellen_anlage(sitzungen, aid, jetzt=start + timedelta(days=2), ha_svc=svc)
    assert spaeter.uebersprungen.get("vorgeschichte_andere_quelle", 0) >= 1
    _verschiebe(svc, 1, _ts(ZEIT + timedelta(days=3)), +11.0)     # HA korrigiert eine Stunde in der Stände-Zeit
    k_erg = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    assert k_erg.fehler == 0
    _, z2, quellen, _ = await _kanal(sitzungen, aid)
    assert {z.start_ts: z.sum for z in z2 if z.familie == "mitschrift"} == staende_vorher
    assert [q.familie for q in quellen] == ["mitschrift", "spiegel"]


async def test_verworfene_zeit_bleibt_leer_auch_ohne_marke(ha, datei):
    """Ein HA-Feld mit Sensortausch: der alte Abschnitt wird vor ``t`` verworfen (Quelle bleibt mit ``verworfen_ts``); die
    Stände reichen über die ganze Zeit. Das Stände-Nachfüllen füllt nur VOR der ersten Quelle — die verworfene Zeit bleibt
    leer, mit und ohne Marke (Grund ``vorgeschichte_andere_quelle``)."""
    from backend.tests.test_werkbank_verwerfen_kommt_nicht_zurueck import _vor_t, _tausch_und_verwerfen

    svc, sitzungen, aid, k, t, vorher, _neu = await _tausch_und_verwerfen(ha, datei)
    async with sitzungen() as s:
        await s.execute(insert(SensorSnapshot), [
            {"anlage_id": aid, "sensor_key": EINSP, "zeitpunkt": ZEIT + timedelta(hours=h), "wert_kwh": 9000.0 + h,
             "quelle": "ha_statistics"} for h in range(1, 30 * 24)])
    await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    assert await _vor_t(sitzungen, k.id, t) == 0
    async with sitzungen() as s:
        await s.execute(delete(KanalNachfuellung).where(KanalNachfuellung.kanal_id == k.id))
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    assert erg.uebersprungen.get("vorgeschichte_andere_quelle") == 1
    assert await _vor_t(sitzungen, k.id, t) == 0
    async with sitzungen() as s:
        n = (await s.execute(select(func.count()).select_from(KanalStatistik).where(
            KanalStatistik.kanal_id == k.id, KanalStatistik.familie == "mitschrift"))).scalar_one()
    assert n == 0
