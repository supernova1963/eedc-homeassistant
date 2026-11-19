"""Daten-Checker «Zählerstände – versetzter Abschnitt» (``zaehler_versatz``, Verdacht N-803, Go Gernot 16.11.2026).

Die Regel (``core/berechnungen/zaehler_versatz.py``): Sprung um +X, später Rückgang um ≈ −X in eedcs Standreihe; zwei Läufe
mit einem Loch ≤ 24 h sind einer. Der Erzeuger (``services/daten_checker/datenquelle/versatz.py``) meldet nur bei Wirkung
(ein Schritt trifft einen Tageswert, den die Tagesansicht über die Standreihe bildet) mit einem Handgriff, «Grund
nachtragen» (seit Sitzung 4b-1 ein Sprung in die Datenquellen, Lagen ``fuellbar`` · ``ohne_home_assistant`` ·
``staende_passen_nicht`` · ``verschiedene_quellen``). Keine Probe liest die Uhr; die Zeitpunkte liegen im Juni, fern jeder
Umstellung (die Suite fährt auch in ``Pacific/Auckland`` und ``UTC``).

Schwesterdateien: test_daten_checker_codes.py (W-1), test_daten_checker_loesungswege.py (W-13),
test_sensorwechsel_s4b1_stueck.py (die Korrektur über das Stück, Routen am Befund), test_n586_checker_ha_zaehlersprung.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.core.berechnungen.zaehler_versatz import finde_versatz_laeufe, stand_passt_zum_spiegel
from backend.models import activity_log, mqtt_gateway_mapping  # noqa: F401 — Tabellen der Quellen-Auskunft (Teil-Schema der Fixture)
from backend.services.daten_checker.datenquelle.versatz import (
    GRUND_OHNE_HA, GRUND_STAENDE_PASSEN_NICHT, LAGE_FUELLBAR, ZaehlerVersatzChecks,
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
    """Die Tageswahl der Kanal-Schicht gestellt: ``{datum: Schlüssel aus den Kanälen}`` (ohne Eintrag: keiner) — seit
    Sensorwechsel S2 (B-5) auch die Feld-Auskunft «Kanal vor Reihe» (``feld_leser.feld_aus_kanal_am_tag``): der Spiegel der
    Proben deckt jeden Tag, ohne die Stellung schwiege jeder Befund. Die Wirkung der echten Feld-Auskunft hält
    ``test_sensorwechsel_s2_kanal_vor_reihe.py::test_versatz_schweigt_wo_der_eigene_kanal_den_tag_traegt``."""
    import backend.services.energie_profil.kanal_stunden as ks
    import backend.services.kanal.feld_leser as fl

    async def _schluessel(_db, _aid, datum):
        return frozenset(je_tag.get(datum, ()))

    async def _feld(_db, _anlage, _typ, key, datum):
        return key in je_tag.get(datum, ())

    monkeypatch.setattr(ks, "kanal_schluessel_des_tages", _schluessel)
    monkeypatch.setattr(fl, "feld_aus_kanal_am_tag", _feld)


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


def _ha_verschoben(monkeypatch, plus: float):
    """HA erreichbar, aber seine Summe ist verschoben (Produktiv ``ladung_kwh``: 1 906,5 kWh seit 16.11.2025) — die Reihe
    außerhalb des Abschnitts passt zu keiner Summe, die HA führt."""
    from sqlalchemy import text

    import backend.services.ha_statistics_service as hss
    from backend.tests import ha_lts_helfer as h

    svc = h.mach_service(thread_sicher=True)
    mid = h.sensor(svc, SENSOR, "kWh", has_sum=True)
    ab = int(T0.timestamp()) - 3600
    with svc._engine.begin() as conn:
        conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :w, :w)"),
                     [{"m": mid, "t": ab + 3600 * i, "w": _ha(i) + plus} for i in range(29 * 24)])
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    return svc


async def test_lage_fuellbar_traegt_grund_nachtragen(db, ha, monkeypatch):
    """Sitzung 4b-1 (Bauplan «Zu §14» Nr. 95 (2), Nr. 98): ein Handgriff «Grund nachtragen» als Sprung in die Datenquellen
    (``stueck=<schlüssel>~<sprung>~<rückgang>``) statt «Tage neu aufbauen»; WARNING in jeder Lage."""
    _kanal_tage(monkeypatch, {})
    a, wb, key = await _anlage(db)
    (e,) = await _pruefe(db, a)
    assert (e.code, e.kategorie, e.schwere, e.klasse, e.knopf, e.action) == (
        "zaehler_versatz", "zaehler_versatz", "warning", "sprung", "Grund nachtragen", None)
    assert e.werte["lage"] == LAGE_FUELLBAR and e.werte["schluessel"] == key
    assert (e.werte["sprung"], e.werte["rueckgang"]) == ("2026-06-10T01:00", "2026-06-14T19:00")
    assert e.ziel.params["stueck"] == f"{key}~2026-06-10T01:00~2026-06-14T19:00"
    assert e.meldung == ("Ladepunkt – Ladung PV: Zählerstände vom 10.06.2026 bis 14.06.2026 um 80,5 kWh versetzt — "
                         "Tageswerte an den Rändern falsch")
    assert "am 10.06.2026 ist er deshalb zu hoch, am 14.06.2026 fehlt er" in e.details
    assert "„Grund nachtragen“ verwirft die Zählerstände des Abschnitts; eedc liest sie danach aus Home Assistant neu" in e.details
    assert "Tage neu aufbauen" not in e.details


async def test_staende_passen_nicht_wenn_ha_summe_verschoben(db, monkeypatch):
    """Die Rand-Stände passen zu keiner Summe, die HA führt ⇒ Lage ``staende_passen_nicht`` mit demselben Handgriff (die
    Korrektur verwirft, das Stück bleibt eine Lücke)."""
    _ha_verschoben(monkeypatch, 1906.5)
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db)
    (e,) = await _pruefe(db, a)
    assert (e.schwere, e.klasse, e.knopf, e.werte["lage"]) == ("warning", "sprung", "Grund nachtragen", GRUND_STAENDE_PASSEN_NICHT)
    assert "passen zu keiner Summe, die Home Assistant für sensor.pv_ladung führt" in e.details


async def test_andere_entitaet_ohne_geschichte_passt_nicht(db, ha, monkeypatch):
    """Die Reihe trägt am Rand eine Entität, die HA nicht kennt ⇒ nicht füllbar."""
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, quelle_sensor="sensor.alter_zaehler")
    assert [e.werte["lage"] for e in await _pruefe(db, a)] == [GRUND_STAENDE_PASSEN_NICHT]


async def test_offset_der_quelle_ist_fuellbar(db, ha, monkeypatch):
    """Messblatt 4b-0 c: die Reihe trägt HAs Rohsumme, der Versatz des Kanals spielt keine Rolle — die Enge «Versatz 0» der
    alten Lage «heilbar» ist entfallen."""
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, offset=-208.214)
    assert [e.werte["lage"] for e in await _pruefe(db, a)] == [LAGE_FUELLBAR]


async def test_ohne_kanal_fuellt_aus_der_heutigen_quelle(db, ha, monkeypatch):
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, spiegel=False)
    assert [e.werte["lage"] for e in await _pruefe(db, a)] == [LAGE_FUELLBAR]


async def test_standalone_ohne_ha(db, ohne_ha, monkeypatch):
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db)
    (e,) = await _pruefe(db, a)
    assert (e.schwere, e.knopf, e.werte["lage"]) == ("warning", "Grund nachtragen", GRUND_OHNE_HA)
    # Bauplan «Zu §14» Nr. 119/120 (4b-1-K2): davor und danach dieselbe Quelle ⇒ wie jede Zählerlücke
    assert "Ohne Verbindung zu Home Assistant" in e.details and "wie über jede Zählerlücke" in e.details


async def test_rand_tage_aus_den_kanaelen_ohne_befund(db, ha, monkeypatch):
    a, wb, key = await _anlage(db)
    _kanal_tage(monkeypatch, {date(2026, 6, 10): {key}, date(2026, 6, 14): {key}})
    assert await _pruefe(db, a) == []
    # Ein Rand-Tag über die Standreihe genügt.
    _kanal_tage(monkeypatch, {date(2026, 6, 10): {key}})
    assert len(await _pruefe(db, a)) == 1


async def test_abschnitt_endet_heute_hat_denselben_handgriff(db, ha, monkeypatch):
    """Bis 4b-1 die Lage «endet_heute» ohne Knopf (der laufende Tag ließ sich nicht neu aufbauen); die Korrektur über das
    Stück braucht keinen vergangenen Tag — dieselbe Lage wie an jedem anderen Tag."""
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, staende=_reihe(sprung=19 * 24 + 3, rueck=20 * 24 + 9))      # 20.06. 03:00 … 21.06. 09:00
    (e,) = await _P(db)._check_zaehler_versatz(a, jetzt=datetime(2026, 6, 21, 12))
    assert (e.knopf, e.werte["lage"]) == ("Grund nachtragen", LAGE_FUELLBAR)


async def test_zerteilter_lauf_nennt_nur_die_schritte_mit_wirkung(db, ha, monkeypatch):
    """Nr. 91 b: jeder Sprung und jeder Rückgang eines zerteilten Laufs wird geprüft (12.06. zu hoch, 11.06. ohne Wert);
    ein Tag aus den Kanälen fällt aus Text und ``werte``."""
    loch = range(10 * 24 + 20, 11 * 24 + 2)                     # 11.06. 20:00 … 12.06. 01:00 richtig
    a, wb, key = await _anlage(db, staende=_reihe(loch=loch))
    _kanal_tage(monkeypatch, {})
    (e,) = await _pruefe(db, a)
    assert (e.werte["tage_zu_hoch"], e.werte["tage_ohne_wert"]) == (["2026-06-10", "2026-06-12"], ["2026-06-11", "2026-06-14"])
    _kanal_tage(monkeypatch, {date(2026, 6, 10): {key}, date(2026, 6, 11): {key}})
    (e,) = await _pruefe(db, a)
    assert (e.werte["tage_zu_hoch"], e.werte["tage_ohne_wert"]) == (["2026-06-12"], ["2026-06-14"])
    assert "am 12.06.2026 ist er deshalb zu hoch, am 14.06.2026 fehlt er" in e.details


# ── Kein Saldo je Tag (Bauplan «Zu §14» Nr. 100; Nachmessung 4b-1 F1) ───────────────────────────────────────────────

async def _tagesansicht(db, a, wb, tage) -> dict[int, object]:
    """«Ladung PV» der Tagesansicht je Tag (Wert oder der Grund ohne Wert) — dieselbe Sicht, an der der Befund misst (die
    Proben ohne Spiegel: die Tagesansicht liest die Reihe)."""
    from backend.services.snapshot.aggregator import get_tagesdetail_kwh
    from backend.services.zuordnung_wechsel import zeitpunkt as zw

    zw.vergiss(db)
    out = {}
    for d in tage:
        e = await get_tagesdetail_kwh(db, a, {str(wb.id): wb}, date(2026, 6, d), tageszeile_rueckwaerts=True)
        w = e.werte.get("emob_ladung_pv_kwh")
        out[d] = round(w, 2) if w is not None else e.grund_je_feld.get("emob_ladung_pv_kwh")
    return out


async def test_rueckgang_und_sprung_im_selben_fenster_der_tag_hat_keinen_wert(db, ha, monkeypatch):
    """Zerteilter Lauf, 12.06. 05–10 Uhr richtig: Rückgang und Sprung im Fenster des 12.06. — die Tagesansicht zeigt dort
    keinen Wert («Zähler zurückgesprungen»), der Befund nennt den Tag (am HEAD ebenso; ein Saldo nannte ihn nicht)."""
    _kanal_tage(monkeypatch, {})
    a, wb, _key = await _anlage(db, staende=_reihe(loch=range(11 * 24 + 5, 11 * 24 + 11)), spiegel=False)
    sicht = await _tagesansicht(db, a, wb, (10, 11, 12, 13, 14))
    assert sicht == {10: 92.0, 11: 12.0, 12: "zaehler_ruecksprung", 13: 12.0, 14: "zaehler_ruecksprung"}
    (e,) = await _pruefe(db, a)
    assert (e.werte["tage_zu_hoch"], e.werte["tage_ohne_wert"]) == (["2026-06-10"], ["2026-06-12", "2026-06-14"])
    assert "am 10.06.2026 ist er deshalb zu hoch, am 12.06.2026 und 14.06.2026 fehlt er" in e.details


async def test_abschnitt_innerhalb_eines_tages_wird_gemeldet(db, ha, monkeypatch):
    """Sprung und Rückgang im Fenster des 10.06. (03:00 … 20:00): die Tagesansicht zeigt am 10.06. keinen Wert — der
    Befund meldet ihn (keine OK-Zeile), der Tag gilt als «fehlt», nicht als «zu hoch»."""
    _kanal_tage(monkeypatch, {})
    a, wb, _key = await _anlage(db, staende=_reihe(sprung=9 * 24 + 3, rueck=9 * 24 + 20), spiegel=False)
    assert (await _tagesansicht(db, a, wb, (9, 10, 11)))[10] == "zaehler_ruecksprung"
    (e,) = await _pruefe(db, a)
    assert (e.schwere, e.werte["tage_zu_hoch"], e.werte["tage_ohne_wert"]) == ("warning", [], ["2026-06-10"])
    assert e.meldung.startswith("Ladepunkt – Ladung PV: Zählerstände vom 10.06.2026 bis 10.06.2026 um")
    assert "Zählerständen: am 10.06.2026 fehlt er" in e.details


async def test_sprung_hinter_einer_datenluecke_trifft_den_tag_danach(db, ha, monkeypatch):
    """Stände 09.06. 12:00 … 10.06. 00:00 fehlen: der Sprung reicht von 09.06. 11:00 bis 10.06. 01:00 über die Fenstergrenze —
    die Tagesansicht zeigt am 10.06. 92,0 (zu hoch), der Befund nennt den Tag (am HEAD ebenso)."""
    _kanal_tage(monkeypatch, {})
    weg = {T0 + timedelta(hours=h) for h in range(8 * 24 + 12, 9 * 24 + 1)}
    a, wb, _key = await _anlage(db, staende=[s for s in _reihe() if s[0] not in weg], spiegel=False)
    assert (await _tagesansicht(db, a, wb, (9, 10)))[10] == 92.0
    (e,) = await _pruefe(db, a)
    assert (e.werte["tage_zu_hoch"], e.werte["tage_ohne_wert"]) == (["2026-06-10"], ["2026-06-14"])


@pytest.mark.parametrize("mit_ha", [True, False])
async def test_rueckgang_hinter_einer_datenluecke_ueber_23_uhr(db, monkeypatch, mit_ha, request):
    """Stände 13.06. 20:00 … 14.06. 18:00 fehlen, der Rückgang reicht von 13.06. 19:00 bis 14.06. 19:00. Mit Home Assistant
    heilt die Tagesansicht den Rand 13.06. 23:00 auf das Niveau außerhalb — der 13.06. hat keinen Wert; ohne rückt der Rand
    des 14.06. auf den Stand 13.06. 19:00 zurück — dann der 14.06. Der Befund nennt jeweils den Tag ohne Wert."""
    request.getfixturevalue("ha" if mit_ha else "ohne_ha")
    _kanal_tage(monkeypatch, {})
    weg = {T0 + timedelta(hours=h) for h in range(12 * 24 + 20, 13 * 24 + 19)}
    a, wb, _key = await _anlage(db, staende=[s for s in _reihe() if s[0] not in weg], spiegel=False)
    (e,) = await _pruefe(db, a)                     # vor der Tagesansicht: sie heilt den Rand und schriebe ihn in die Reihe
    sicht = await _tagesansicht(db, a, wb, (13, 14))
    tag = 13 if mit_ha else 14
    assert sicht[tag] == "zaehler_ruecksprung"
    assert e.werte["tage_ohne_wert"] == [f"2026-06-{tag}"]


async def test_rand_um_mitternacht_trifft_im_fenster_ab_23_uhr_den_folgetag(db, ha, monkeypatch):
    """Messblatt 4b-0 h: ein Bestandstag der Wallbox liest rückwärts (Fenster ab 23:00 des Vortags) — ein Rückgang mit der
    Zeile 15.06. 00:00 trifft den Tageswert des 15.06., nicht den des 14.06. (Kalendertag des Schritts)."""
    _kanal_tage(monkeypatch, {})
    a, *_ = await _anlage(db, staende=_reihe(rueck=14 * 24))
    (e,) = await _pruefe(db, a)
    assert e.werte["tage_ohne_wert"] == ["2026-06-15"]
    assert "am 15.06.2026 fehlt er" in e.details


async def test_nur_ein_rand_an_einer_naht_nennt_nur_den_anderen(db, ha, monkeypatch):
    """Nr. 91 b: ein Rand an einer verzeichneten Fortsetzung ist ohne Wirkung — Text und ``werte`` nennen nur den anderen."""
    from backend.models.zuordnung_wechsel import ZuordnungWechsel

    _kanal_tage(monkeypatch, {})
    a, wb, key = await _anlage(db)
    q = {"art": "ha", "entity_id": SENSOR}
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=T0 + timedelta(hours=SPRUNG_H),
                            ab_ts=T0 + timedelta(hours=SPRUNG_H), vorher=q, nachher={"art": "ha", "entity_id": "sensor.x"},
                            grund="fortsetzung", herkunft="nachtrag"))
    await db.commit()
    (e,) = await _pruefe(db, a)
    assert (e.werte["tage_zu_hoch"], e.werte["tage_ohne_wert"]) == ([], ["2026-06-14"])
    assert "eedc bildet einen Tageswert aus zwei Zählerständen: am 14.06.2026 fehlt er" in e.details


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
