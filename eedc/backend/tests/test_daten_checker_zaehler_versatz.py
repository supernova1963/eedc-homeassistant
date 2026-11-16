"""Daten-Checker «Zählerstände – versetzter Abschnitt» (``zaehler_versatz``, Verdacht N-803, Go Gernot 16.11.2026).

Die Regel (``core/berechnungen/zaehler_versatz.py``): Sprung um +X, später Rückgang um ≈ −X in eedcs Standreihe; zwei Läufe
mit einem Loch ≤ 24 h sind einer. Der Erzeuger (``services/daten_checker/datenquelle/versatz.py``) meldet nur bei Wirkung
(ein Rand-Tag rechnet das Feld über die Standreihe) und kennt zwei Lagen: heilbar (WARNING, «Tage neu aufbauen»
= ``reaggregate_range``) und sonst (INFO, «Was gilt»). Keine Probe liest die Uhr (Naht ``jetzt``); die Zeitpunkte liegen
im Juni, fern jeder Umstellung (die Suite fährt auch in ``Pacific/Auckland`` und ``UTC``).

Schwesterdateien: test_daten_checker_codes.py (W-1), test_daten_checker_loesungswege.py (W-13),
test_daten_checker_handgriff_wirkt.py (W-11, Beleg ``test_w11_zaehler_versatz_wirkt``), test_n586_checker_ha_zaehlersprung.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.core.berechnungen.zaehler_versatz import finde_versatz_laeufe, stand_passt_zum_spiegel
from backend.services.daten_checker.datenquelle.versatz import (
    GRUND_ENDET_HEUTE, GRUND_OHNE_HA, GRUND_STAENDE_PASSEN_NICHT, LAGE_HEILBAR, ZaehlerVersatzChecks, aktions_bereich,
)
from backend.services.daten_checker.handgriffe import MECHANIK_WOERTER

T0 = datetime(2026, 6, 1, 0)
JETZT = datetime(2026, 7, 1, 12)
SENSOR = "sensor.pv_ladung"
SPRUNG_H = 9 * 24 + 1          # 10.06. 01:00
RUECK_H = 13 * 24 + 19         # 14.06. 19:00
VERSATZ = 80.0


def _ha(h: int) -> float:
    """Der Stand, den Home Assistant führt: 100 kWh + 0,5 kWh je Stunde."""
    return 100.0 + 0.5 * h


def _reihe(stunden: int = 29 * 24, *, sprung=SPRUNG_H, rueck=RUECK_H, versatz=VERSATZ, loch=()):
    """Stündliche Stände; zwischen ``sprung`` und ``rueck`` (exklusiv) um ``versatz`` versetzt, außer in ``loch``."""
    return [(T0 + timedelta(hours=h), _ha(h) + (versatz if sprung is not None and sprung <= h < rueck and h not in loch
                                                else 0.0)) for h in range(stunden)]


# ── Regel (rein) ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_paar_ist_ein_lauf_mit_rand_tagen():
    (lauf,) = finde_versatz_laeufe(_reihe())
    assert lauf.versatz_kwh == pytest.approx(VERSATZ + 0.5)
    assert lauf.rand_tage == (date(2026, 6, 10), date(2026, 6, 14))
    assert (lauf.tage_zu_hoch, lauf.tage_ohne_wert) == ([date(2026, 6, 10)], [date(2026, 6, 14)])
    assert lauf.beginn.von == T0 + timedelta(hours=SPRUNG_H - 1) and lauf.ende.bis == T0 + timedelta(hours=RUECK_H)


def test_ein_schritt_um_mitternacht_gehoert_zum_vortag():
    (lauf,) = finde_versatz_laeufe(_reihe(rueck=14 * 24))      # Rückgang mit der Zeile 15.06. 00:00
    assert lauf.ende.tag == date(2026, 6, 14)


def test_zerteilter_lauf_ist_ein_lauf():
    """15.07.2026 an der Produktiv-Anlage: fünf richtige Stunden mitten im Lauf (lesender Abruf) — ein Lauf, zwei Teile."""
    loch = range(11 * 24, 11 * 24 + 6)                          # 12.06. 00:00 … 05:00 richtig
    (lauf,) = finde_versatz_laeufe(_reihe(loch=loch))
    assert len(lauf.spruenge) == 2 and len(lauf.rueckgaenge) == 2
    assert lauf.rand_tage == (date(2026, 6, 10), date(2026, 6, 14))
    assert lauf.tage_zu_hoch == [date(2026, 6, 10), date(2026, 6, 12)]
    assert lauf.tage_ohne_wert == [date(2026, 6, 11), date(2026, 6, 14)]


def test_ein_loch_ueber_24_stunden_trennt_zwei_laeufe():
    loch = range(11 * 24, 12 * 24 + 6)
    assert len(finde_versatz_laeufe(_reihe(loch=loch))) == 2


def test_reset_auf_null_ist_kein_versatz():
    st = [(t, w) for t, w in _reihe(sprung=None)]
    st = st[:200] + [(t, w - 2000.0 + 0.2) for t, w in st[200:]]   # Zähler startet neu (Stand < 1 kWh)
    st = [(t, w if w > 0 else 0.2) for t, w in st]
    assert finde_versatz_laeufe(st) == []


def test_einzelner_stufen_rueckgang_ohne_sprung_ist_kein_versatz():
    """Speicher-Netzladung der Produktiv-Anlage (April/Mai 2026): Stufen −19 … −26 kWh ohne Gegen-Sprung."""
    st = _reihe(sprung=None)
    st = st[:300] + [(t, w - 23.3) for t, w in st[300:]]
    assert finde_versatz_laeufe(st) == []


def test_grosser_ladevorgang_ohne_rueckgang_ist_kein_versatz():
    st = _reihe(sprung=None)
    st = st[:300] + [(t, w + 33.0) for t, w in st[300:]]
    assert finde_versatz_laeufe(st) == []


def test_datenluecke_von_14_tagen_ist_kein_versatz():
    st = _reihe(sprung=None)
    st = st[:100] + [(t, w + 60.0) for t, w in st[100 + 14 * 24:]]
    assert finde_versatz_laeufe(st) == []


def test_rueckgang_anderer_groesse_ist_kein_versatz():
    st = _reihe(sprung=None)
    st = (st[:SPRUNG_H] + [(t, w + 80.0) for t, w in st[SPRUNG_H:RUECK_H]]
          + [(t, w + 40.0) for t, w in st[RUECK_H:]])
    assert finde_versatz_laeufe(st) == []


def test_stand_und_spiegel():
    assert stand_passt_zum_spiegel(511.641, 511.6414, 0.0)
    assert stand_passt_zum_spiegel(303.0, 511.0, -208.0)
    assert not stand_passt_zum_spiegel(1415.586, 3322.086, 0.0)
    assert not stand_passt_zum_spiegel(1.0, None, 0.0)


def test_bereich_hoechstens_31_tage_und_bis_gestern():
    (lauf,) = finde_versatz_laeufe(_reihe(stunden=60 * 24, rueck=50 * 24 + 5))
    assert aktions_bereich(lauf, date(2026, 9, 1)) == (date(2026, 6, 10), date(2026, 7, 10))
    assert aktions_bereich(lauf, date(2026, 6, 20)) == (date(2026, 6, 10), date(2026, 6, 19))


# ── Erzeuger (Wegwerf-Datenbank) ─────────────────────────────────────────────────────────────────────────────────────

class _P(ZaehlerVersatzChecks):
    def __init__(self, db):
        self.db = db


async def _anlage(db, *, staende=None, spiegel=True, spiegel_plus=0.0, quelle_sensor=SENSOR, offset=0.0, quelle="ha_statistics",
                  feld="ladung_pv_kwh"):
    from backend.models.anlage import Anlage
    from backend.models.investition import Investition
    from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
    from backend.models.sensor_snapshot import SensorSnapshot

    a = Anlage(anlagenname="Versatz", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="Ladepunkt", anschaffungsdatum=date(2025, 1, 1))
    db.add(wb)
    await db.flush()
    a.sensor_mapping = {"investitionen": {str(wb.id): {"felder": {feld: {"strategie": "sensor", "sensor_id": SENSOR}}}}}
    key = f"inv:{wb.id}:{feld}"
    db.add_all([SensorSnapshot(anlage_id=a.id, sensor_key=key, zeitpunkt=t, wert_kwh=w, quelle=quelle)
                for t, w in (staende if staende is not None else _reihe())])
    if spiegel:
        k = Kanal(anlage_id=a.id, key=key, einheit="kWh", art=ART_SUM)
        db.add(k)
        await db.flush()
        ab = int(T0.timestamp()) - 3600
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=ab, familie=FAMILIE_SPIEGEL, statistic_id=quelle_sensor, offset=offset))
        db.add_all([KanalStatistik(kanal_id=k.id, start_ts=ab + 3600 * h, sum=_ha(h) + spiegel_plus - offset, state=_ha(h),
                                   familie=FAMILIE_SPIEGEL) for h in range(29 * 24)])
    await db.commit()
    return a, wb, key


@pytest.fixture
def ha(monkeypatch):
    """HA erreichbar: ein Recorder im HA-Schema mit der Statistik des Sensors (``start_ts`` trägt das Stundenende)."""
    from sqlalchemy import text

    import backend.services.ha_statistics_service as hss
    from backend.tests import ha_lts_helfer as h

    svc = h.mach_service(thread_sicher=True)
    mid = h.sensor(svc, SENSOR, "kWh", has_sum=True)
    ab = int(T0.timestamp()) - 3600
    with svc._engine.begin() as conn:
        conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :w, :w)"),
                     [{"m": mid, "t": ab + 3600 * i, "w": _ha(i)} for i in range(29 * 24)])
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    return svc


@pytest.fixture
def ohne_ha(monkeypatch):
    import backend.services.ha_statistics_service as hss
    from backend.tests.pv_achse_matrix import _ha_aus

    monkeypatch.setattr(hss, "_ha_statistics_service", _ha_aus())


def _kanal_tage(monkeypatch, je_tag: dict):
    """Die Tageswahl der Kanal-Schicht gestellt: ``{datum: Schlüssel aus den Kanälen}`` (ohne Eintrag: keiner)."""
    import backend.services.energie_profil.kanal_stunden as ks

    async def _schluessel(_db, _aid, datum):
        return frozenset(je_tag.get(datum, ()))

    monkeypatch.setattr(ks, "kanal_schluessel_des_tages", _schluessel)


async def _pruefe(db, a):
    """Die Befunde mit Fund (ohne die OK-Zeile, die der Befund ohne Fund liefert — N-799 S3, K7)."""
    return [e for e in await _P(db)._check_zaehler_versatz(a, jetzt=JETZT) if e.schwere != "ok"]


async def test_ohne_fund_eine_ok_zeile(db, ha, monkeypatch):
    """N-799 S3, K7: ohne Fund liefert der Befund eine OK-Zeile desselben Codes — der Knopf «Zum Daten-Checker» im Hinweis
    nach einer geänderten Zuordnung (``befund=zaehler_versatz``) öffnet damit immer den Lösungsweg. Mit Fund keine
    OK-Zeile daneben."""
    from backend.services.daten_checker.datenquelle.versatz import OK_MELDUNG

    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, feld="ladung_kwh")                     # Feld nicht in der Tagesansicht ⇒ kein Fund
    (e,) = await _P(db)._check_zaehler_versatz(a, jetzt=JETZT)
    assert (e.code, e.schwere, e.meldung, e.knopf, e.action) == ("zaehler_versatz", "ok", OK_MELDUNG, None, None)
    b, *_ = await _anlage(db)
    alle = await _P(db)._check_zaehler_versatz(b, jetzt=JETZT)
    assert [x.schwere for x in alle] == ["warning"]


async def test_lage_heilbar_traegt_tage_neu_aufbauen(db, ha, monkeypatch):
    _kanal_tage(monkeypatch, {})
    a, wb, key = await _anlage(db)
    (e,) = await _pruefe(db, a)
    assert (e.code, e.kategorie, e.schwere, e.klasse, e.knopf) == (
        "zaehler_versatz", "zaehler_versatz", "warning", "aktion", "Tage neu aufbauen")
    assert (e.action.operation, e.action.params) == ("reaggregate_range", {"von": "2026-06-10", "bis": "2026-06-14"})
    assert e.werte["lage"] == LAGE_HEILBAR and e.werte["schluessel"] == key
    assert e.meldung == ("Ladepunkt – Ladung PV: Zählerstände vom 10.06.2026 bis 14.06.2026 um 80,5 kWh versetzt — "
                         "Tageswerte an den Rändern falsch")
    assert "am 10.06.2026 ist er deshalb zu hoch, am 14.06.2026 fehlt er" in e.details
    assert "„Tage neu aufbauen“ holt die Zählerstände vom 10.06.2026 bis 14.06.2026" in e.details
    assert "Rest" not in e.details


async def test_staende_passen_nicht_ist_auskunft(db, ha, monkeypatch):
    """Der Spiegel trägt andere Stände als die Reihe außerhalb des Abschnitts (Wallbox-Ladung der Produktiv-Anlage:
    1 415,586 gegen 3 322,086) ⇒ INFO ohne Knopf, der schreibt."""
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, spiegel_plus=1906.5)
    (e,) = await _pruefe(db, a)
    assert (e.schwere, e.klasse, e.knopf, e.action) == ("info", "auskunft", "Was gilt", None)
    assert e.werte["lage"] == GRUND_STAENDE_PASSEN_NICHT
    assert "nicht selbst richtig" in e.details


async def test_andere_entitaet_oder_versatz_der_quelle_ist_auskunft(db, ha, monkeypatch):
    """⚑ Der Lauf holt mit der heutigen Zuordnung ohne Versatz — gilt am Rand eine andere Entität oder ein Versatz, heilt er
    nicht (der Sprung wanderte nur, gemessen an ``inv:2:ladung_kwh``)."""
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, quelle_sensor="sensor.alter_zaehler")
    assert [e.werte["lage"] for e in await _pruefe(db, a)] == [GRUND_STAENDE_PASSEN_NICHT]


async def test_offset_der_quelle_ist_auskunft(db, ha, monkeypatch):
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, offset=-208.214)
    assert [e.werte["lage"] for e in await _pruefe(db, a)] == [GRUND_STAENDE_PASSEN_NICHT]


async def test_ohne_kanal_ist_auskunft(db, ha, monkeypatch):
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, spiegel=False)
    assert [e.werte["lage"] for e in await _pruefe(db, a)] == [GRUND_STAENDE_PASSEN_NICHT]


async def test_standalone_ohne_ha_ist_auskunft(db, ohne_ha, monkeypatch):
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db)
    (e,) = await _pruefe(db, a)
    assert (e.schwere, e.action, e.werte["lage"]) == ("info", None, GRUND_OHNE_HA)
    assert "Ohne Verbindung zu Home Assistant" in e.details


async def test_rand_tage_aus_den_kanaelen_ohne_befund(db, ha, monkeypatch):
    a, wb, key = await _anlage(db)
    _kanal_tage(monkeypatch, {date(2026, 6, 10): {key}, date(2026, 6, 14): {key}})
    assert await _pruefe(db, a) == []
    # Ein Rand-Tag über die Standreihe genügt.
    _kanal_tage(monkeypatch, {date(2026, 6, 10): {key}})
    assert len(await _pruefe(db, a)) == 1


async def test_abschnitt_endet_heute_ohne_knopf(db, ha, monkeypatch):
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, staende=_reihe(sprung=20 * 24 + 3, rueck=20 * 24 + 9))
    (e,) = await _P(db)._check_zaehler_versatz(a, jetzt=datetime(2026, 6, 21, 12))
    assert (e.action, e.werte["lage"]) == (None, GRUND_ENDET_HEUTE)


async def test_langer_abschnitt_nennt_den_rest(db, ha, monkeypatch):
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, staende=_reihe(sprung=2, rueck=28 * 24 + 2) + [])
    (e,) = await _pruefe(db, a)
    assert e.action.params == {"von": "2026-06-01", "bis": "2026-06-29"}
    lang, *_ = finde_versatz_laeufe(_reihe(stunden=60 * 24, rueck=50 * 24 + 5))
    from backend.services.daten_checker.datenquelle.versatz import _texte
    from backend.services.daten_checker.kategorien import Aktion

    _, details = _texte("X", lang, Aktion("reaggregate_range", {"von": "2026-06-10", "bis": "2026-07-10"}), LAGE_HEILBAR)
    assert "Danach nennt dieser Befund den Rest bis 21.07.2026 — dann noch einmal klicken." in details


async def test_feld_nicht_in_der_tagesansicht_ohne_befund(db, ha, monkeypatch):
    """Entscheid Master 16.11.2026: «Ladung gesamt» der Wallbox zeigt die Tagesansicht aus der Tageszeile, nicht aus der
    Standreihe (gemessen an ``tag-detail`` der Produktiv-Sicherung: 01.07. ohne +2 114 kWh) ⇒ derselbe Abschnitt, kein Befund."""
    from backend.services.daten_checker.datenquelle.versatz import in_tagesansicht

    _kanal_tage(monkeypatch, {})
    a, wb, key = await _anlage(db, feld="ladung_kwh")
    assert await _pruefe(db, a) == []
    assert not in_tagesansicht({str(wb.id): wb}, key)
    assert in_tagesansicht({str(wb.id): wb}, f"inv:{wb.id}:ladung_pv_kwh")
    assert not in_tagesansicht({str(wb.id): wb}, "basis:netzbezug")


async def test_mqtt_reihe_bleibt_bei_zaehler_ruecksprung(db, ha, monkeypatch):
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, quelle="mqtt_inbound")
    assert await _pruefe(db, a) == []


async def test_texte_ohne_mechanik(db, ha, monkeypatch):
    """Meldung und Details in Anwender-Sprache: kein «Snapshot», «Resnap», «Schlüssel», «Spiegel», «Kanal»."""
    _kanal_tage(monkeypatch, {})
    for kw in ({}, {"spiegel_plus": 5.0}):
        a, *_ = await _anlage(db, **kw)
        for e in await _pruefe(db, a):
            text = (e.meldung + " " + e.details).lower()
            assert not [w for w in (*MECHANIK_WOERTER, "schlüssel") if w in text], text


# ── W-11: der Knopf wirkt (plan → execute mit den Parametern des Befunds) ────────────────────────────────────────────

async def test_w11_zaehler_versatz_wirkt(db, ha, monkeypatch):
    """Der Abschnitt 10.–14.06. trägt die Stände eines anderen Sensors (+80 kWh) ⇒ Befund mit «Tage neu aufbauen»;
    der Lauf holt die Stände der Tage neu aus Home Assistant ⇒ die Reihe ist stetig, der Befund weg."""
    from sqlalchemy import select

    import backend.services.live_power_service as lps
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.repair_orchestrator import (
        RepairOperationRequest, RepairOperationType, _reset_state_for_tests, execute, plan,
    )
    from backend.tests.werkzeug_befund import befund_op, befund_params

    class _OhneVerlauf:
        async def get_tagesverlauf(self, *_a, **_k):
            return {"serien": [], "punkte": []}

    monkeypatch.setattr(lps, "get_live_power_service", lambda: _OhneVerlauf())
    _reset_state_for_tests()
    _kanal_tage(monkeypatch, {})
    a, wb, key = await _anlage(db)
    aid = a.id
    (e,) = await _pruefe(db, a)
    p = await plan(RepairOperationRequest(anlage_id=aid, operation=RepairOperationType(befund_op(e)),
                                          params=befund_params(e)), db)
    r = await execute(p.plan_id, db)
    assert r.operation_summary["verarbeitet"] == 5 and r.operation_summary["fehlgeschlagen"] == 0, r.operation_summary
    db.expire_all()
    staende = (await db.execute(select(SensorSnapshot.zeitpunkt, SensorSnapshot.wert_kwh).where(
        SensorSnapshot.sensor_key == key).order_by(SensorSnapshot.zeitpunkt))).all()
    falsch = [t for t, w in staende if t.minute == 0 and abs(w - _ha(int((t - T0).total_seconds() // 3600))) > 1e-6]
    assert falsch == []
    from backend.models.anlage import Anlage

    a = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    assert await _pruefe(db, a) == []
