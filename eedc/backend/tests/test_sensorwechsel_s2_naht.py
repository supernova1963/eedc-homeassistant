"""Sensorwechsel mit Grund, Sitzung 2 — B-3 «Fortsetzung in der Reihe» und B-4 «Fortsetzung bei MQTT» (Bauplan Fassung 2 §2).

**Regel B-3:** keine Differenz zweier Stände über eine Fortsetzungs-Naht (``zuordnung_wechsel`` mit ``grund = fortsetzung``,
``ab_ts`` = erster Stand der neuen Quelle) — geprüft in den vier Formen des Plans: ``tageswert_aus_reihe`` (Tageswert der
Tagesansicht, Bereichs-Leser, ``reader.delta``) · ``stunden_slot_art`` (Snapshot-Tagestabelle, Stundenform) · Zählwerke Tag
und Stunde · ``zaehlerstaende.py``. **Ein Wechsel ohne Grund liest wie heute.**
**Regel B-4:** im Kanal «Eigene Summe» (MQTT) schließen die Stände vor ``erklaert_ts`` die alte Periode; die neue beginnt am
ersten neuen Stand mit einer neuen Quellzeile (Versatz = Kanalwert der alten Periode). Der Nachtrag setzt für schon
geschriebene Zeilen eine Quellzeile, die die Naht-Stunde ohne Zuwachs lässt — keine Zeile wird umgeschrieben.

Jede Probe trägt ihren **Sprengsatz** im selben Test: ohne Naht (``fortsetzungs_naehte`` bzw. ``offene_naehte`` leer, oder
der Wechsel ohne Grund) wird der Niveau-Sprung zur Menge. Die Fälle laufen auch in ``TZ=Pacific/Auckland`` und ``TZ=UTC``
(Zeiten im Juni, fern jeder Umstellung). Korrekturrunde (Bauplan §9 Nr. 25, K-3): Nachtrag zweimal = einmal, nach einer
angewandten Naht ohne Wirkung, spätere Quellgrenzen rücken mit; aufgehobene Fortsetzung und Korrektur sind keine Naht;
Nebenwirkungen des Nachtrags (abgeleitete Kanäle, gemerkte Tage, nur eigene Summe); Stundenform und Daten-Checker.

Schwesterdateien: test_sensorwechsel_s2_kanal_vor_reihe.py (B-5), test_reihen_leser_waechter.py (Einstufung je Leser),
test_sensorwechsel_s1_zeitpunkt.py (B-0), test_kanal_eigene_summe.py (die Summenregel, unverändert).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import insert, select

from backend.core.berechnungen.zaehler_naht import abschnitte, stand_differenz, ueber_naht, zaehlwerk_menge
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus

D = date(2026, 6, 10)
TAG0 = datetime(2026, 6, 10, 0)
ERKLAERT = datetime(2026, 6, 10, 10, 47, 42)
NAHT = ab_ts_aus(ERKLAERT)                  # 11:00
SPRUNG = 2000.0


# ═══ Reine Regel ════════════════════════════════════════════════════════════════════════════════════════════════════

def test_abschnitte_und_naht_regel():
    f = [(1, 10.0), (2, 11.0), (3, 2011.5), (4, 2012.0)]
    assert abschnitte(f, [3]) == [[(1, 10.0), (2, 11.0)], [(3, 2011.5), (4, 2012.0)]]
    assert abschnitte(f, []) == [f]                     # ohne Naht: die Folge selbst
    assert abschnitte(f, [9]) == [f]
    assert ueber_naht(2, 3, [3]) and not ueber_naht(3, 4, [3]) and not ueber_naht(1, 2, [3])
    assert stand_differenz(f, [3]) == pytest.approx(1.5) and stand_differenz(f, []) == pytest.approx(2002.0)
    assert zaehlwerk_menge([(1, 1000.0), (2, 1010.0), (3, 5.0), (4, 12.0)], [3]) == pytest.approx(17.0)
    assert zaehlwerk_menge([(1, 1000.0), (2, 1010.0), (3, 5.0), (4, 12.0)], []) == 0.0     # Rückgang zählt 0


# ═══ Umgebung ═══════════════════════════════════════════════════════════════════════════════════════════════════════

def _stand(t: datetime) -> float:
    """1 kWh je Stunde ab 100; ab der Naht auf dem Niveau der neuen Quelle (+2 000)."""
    w = 100.0 + (t - TAG0).total_seconds() / 3600
    return round(w + (SPRUNG if t >= NAHT else 0.0), 3)


def _stunden(von: datetime, bis: datetime) -> list[datetime]:
    out, t = [], von
    while t <= bis:
        out.append(t)
        t += timedelta(hours=1)
    return out


async def _anlage(db, felder: dict, typ: str = "wallbox", parameter=None) -> Anlage:
    a = Anlage(anlagenname="Naht", leistung_kwp=10.0, sensor_mapping={"investitionen": {"2": {"felder": {
        f: {"strategie": "sensor", "sensor_id": f"sensor.{f}"} for f in felder}}}})
    db.add(a)
    await db.flush()
    db.add(Investition(id=2, anlage_id=a.id, typ=typ, bezeichnung="Gerät", anschaffungsdatum=date(2025, 1, 1),
                       parameter=parameter))
    await db.flush()
    return a


async def _reihe(db, aid: int, key: str, staende: dict[datetime, float]):
    db.add_all([SensorSnapshot(anlage_id=aid, sensor_key=key, zeitpunkt=t, wert_kwh=w, quelle="ha_statistics")
                for t, w in staende.items()])
    await db.flush()


async def _wechsel(db, aid: int, key: str, grund="fortsetzung", erklaert: datetime = ERKLAERT):
    db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=erklaert, ab_ts=ab_ts_aus(erklaert),
                            vorher={"art": "ha", "entity_id": "sensor.alt"}, nachher={"art": "ha", "entity_id": "sensor.neu"},
                            grund=grund, herkunft="wechsel"))
    await db.flush()
    zw.vergiss(db)


def _ohne_naht(monkeypatch):
    """Sprengsatz B-3: die Leser sehen keine Naht (= «Wechsel ohne Grund» / der Leser beachtet sie nicht)."""
    import backend.services.snapshot.aggregator as ag
    import backend.services.snapshot.bereichs_leser as bl
    import backend.services.snapshot.stunden_leser as sl   # vor dem Stellen importiert: sie binden den Namen beim Laden

    async def keine(db, anlage_id, sensor_key):
        return []
    for mod in (zw, ag, bl, sl):
        monkeypatch.setattr(mod, "fortsetzungs_naehte", keine)


# ═══ Form 1: tageswert_aus_reihe (Tagesansicht, Bereichs-Leser, reader.delta) ═══════════════════════════════════════

FENSTER = _stunden(TAG0 - timedelta(hours=1), TAG0 + timedelta(hours=23))      # rückwärts [Vortag 23:00, 23:00]
TAGESWERT = 24.0 - 1.0                                                       # 24 Stunden, die Naht-Stunde zählt nicht


async def _tagesdetail(db, a):
    from backend.services.snapshot.aggregator import get_tagesdetail_kwh

    invs = {"2": await db.get(Investition, 2)}
    return (await get_tagesdetail_kwh(db, a, invs, D, tageszeile_rueckwaerts=True)).werte.get("emob_ladung_pv_kwh")


async def test_form1_tagesdetail_summe_der_abschnitte(db, monkeypatch):
    a = await _anlage(db, ["ladung_pv_kwh"])
    await _reihe(db, a.id, "inv:2:ladung_pv_kwh", {t: _stand(t) for t in FENSTER})
    await _wechsel(db, a.id, "inv:2:ladung_pv_kwh")
    assert await _tagesdetail(db, a) == pytest.approx(TAGESWERT)
    _ohne_naht(monkeypatch)
    assert await _tagesdetail(db, a) == pytest.approx(TAGESWERT + 1.0 + SPRUNG)        # heute: der Sprung zählt


async def test_form1_wechsel_ohne_grund_liest_wie_heute(db):
    a = await _anlage(db, ["ladung_pv_kwh"])
    await _reihe(db, a.id, "inv:2:ladung_pv_kwh", {t: _stand(t) for t in FENSTER})
    await _wechsel(db, a.id, "inv:2:ladung_pv_kwh", grund=None)
    assert await _tagesdetail(db, a) == pytest.approx(TAGESWERT + 1.0 + SPRUNG)


async def test_form1_rueckgang_an_der_naht_ist_kein_ruecksprung(db, monkeypatch):
    """Neuer Zähler auf tieferem Niveau: heute «zurückgesprungen» (keine Zahl), mit Naht die Summe der Abschnitte."""
    a = await _anlage(db, ["ladung_pv_kwh"])
    await _reihe(db, a.id, "inv:2:ladung_pv_kwh", {t: _stand(t) - (2 * SPRUNG if t >= NAHT else 0) for t in FENSTER})
    await _wechsel(db, a.id, "inv:2:ladung_pv_kwh")
    assert await _tagesdetail(db, a) == pytest.approx(TAGESWERT)
    _ohne_naht(monkeypatch)
    assert await _tagesdetail(db, a) is None


async def test_form1_naht_mit_tagesstaenden(db, monkeypatch):
    """Ein Stand je Tag (00:00): die Naht liegt zwischen den beiden Rändern des Tags — beide Abschnitte tragen einen Stand,
    der Tag zählt 0 (benannte Grenze «bis 1 Tag je Seite»), nie den Sprung."""
    from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE
    from backend.services.snapshot.bereichs_leser import lade_tageswerte_je_feld

    a = await _anlage(db, ["ladung_pv_kwh"])
    key = "inv:2:ladung_pv_kwh"
    await _reihe(db, a.id, key, {TAG0 + timedelta(days=i): _stand(TAG0 + timedelta(days=i)) for i in range(-1, 3)})
    await _wechsel(db, a.id, key)
    invs = {"2": await db.get(Investition, 2)}
    felder = {("wallbox", "ladung_pv_kwh"): TAGESDETAIL_AUSGABE[("wallbox", "ladung_pv_kwh")]}
    w = await lade_tageswerte_je_feld(db, a, invs, D - timedelta(days=1), D + timedelta(days=1), felder)
    assert [w[D + timedelta(days=i)]["emob_ladung_pv_kwh"] for i in (-1, 0, 1)] == [24.0, 0.0, 24.0]
    _ohne_naht(monkeypatch)
    w = await lade_tageswerte_je_feld(db, a, invs, D, D, felder)
    assert w[D]["emob_ladung_pv_kwh"] == pytest.approx(24.0 + SPRUNG)


async def test_form1_bereichs_leser_und_delta(db, monkeypatch):
    from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE
    from backend.services.snapshot.bereichs_leser import lade_tageswerte_je_feld
    from backend.services.snapshot.reader import delta

    a = await _anlage(db, ["ladung_pv_kwh"])
    key = "inv:2:ladung_pv_kwh"
    await _reihe(db, a.id, key, {t: _stand(t) for t in _stunden(TAG0 - timedelta(hours=1), TAG0 + timedelta(days=1))})
    await _wechsel(db, a.id, key)
    invs = {"2": await db.get(Investition, 2)}
    felder = {("wallbox", "ladung_pv_kwh"): TAGESDETAIL_AUSGABE[("wallbox", "ladung_pv_kwh")]}

    async def beide():
        b = (await lade_tageswerte_je_feld(db, a, invs, D, D, felder))[D]["emob_ladung_pv_kwh"]
        return b, await delta(db, a.id, key, "sensor.x", TAG0, TAG0 + timedelta(days=1))

    assert await beide() == (pytest.approx(23.0), pytest.approx(23.0))
    _ohne_naht(monkeypatch)
    assert await beide() == (pytest.approx(24.0 + SPRUNG), pytest.approx(24.0 + SPRUNG))


async def _leer():
    return []


# ═══ Form 2: Slots (Snapshot-Tagestabelle, Stundenform) ═════════════════════════════════════════════════════════════

async def _tabelle(db, a, invs):
    from backend.services.snapshot.aggregator import snapshot_tagestabelle

    return await snapshot_tagestabelle(db, a, invs, D)


async def test_form2_naht_slot_zaehlt_nur_den_neuen_abschnitt(db, monkeypatch):
    a = await _anlage(db, ["ladung_kwh"])
    await _reihe(db, a.id, "inv:2:ladung_kwh", {t: _stand(t) for t in FENSTER})
    await _wechsel(db, a.id, "inv:2:ladung_kwh")
    invs = {"2": await db.get(Investition, 2)}
    t = await _tabelle(db, a, invs)
    assert t.stunden[11]["wallbox"] == pytest.approx(0.0) and t.stunden[12]["wallbox"] == pytest.approx(1.0)
    assert t.komponenten_kwh["wallbox_2"] == pytest.approx(23.0)
    _ohne_naht(monkeypatch)
    t = await _tabelle(db, a, invs)
    assert t.stunden[11]["wallbox"] == pytest.approx(1.0 + SPRUNG)


async def test_form2_keine_gerade_ueber_die_naht(db, monkeypatch):
    """Fehlen die Stände 9:00 und 10:00, füllt E1 (#145) linear — über eine Naht nicht: der Sprung verteilte sich sonst
    auf 9, 10 und 11 Uhr."""
    a = await _anlage(db, ["ladung_kwh"])
    luecke = {TAG0 + timedelta(hours=9), TAG0 + timedelta(hours=10)}
    await _reihe(db, a.id, "inv:2:ladung_kwh", {t: _stand(t) for t in FENSTER if t not in luecke})
    await _wechsel(db, a.id, "inv:2:ladung_kwh")
    invs = {"2": await db.get(Investition, 2)}
    t = await _tabelle(db, a, invs)
    assert max(t.stunden[h]["wallbox"] or 0.0 for h in range(24)) < 2.0
    _ohne_naht(monkeypatch)
    t = await _tabelle(db, a, invs)
    assert max(t.stunden[h]["wallbox"] or 0.0 for h in range(24)) > 600.0


async def test_form2_stundenform(db, monkeypatch):
    from backend.services.snapshot.stunden_leser import lade_stundenformen

    a = await _anlage(db, ["stromverbrauch_kwh"], typ="waermepumpe")
    key = "inv:2:stromverbrauch_kwh"
    await _reihe(db, a.id, key, {t: _stand(t) for t in FENSTER})
    await _wechsel(db, a.id, key)
    s = (await lade_stundenformen(db, a, D, [(key, None)]))[key]
    assert s[11] == 0.0 and s[12] == pytest.approx(1.0) and sum(s) == pytest.approx(23.0)
    _ohne_naht(monkeypatch)
    s = (await lade_stundenformen(db, a, D, [(key, None)]))[key]
    assert s[11] == pytest.approx(1.0 + SPRUNG)


# ═══ Form 3: Zählwerke Tag und Stunde ══════════════════════════════════════════════════════════════════════════════

async def test_form3_zaehlwerk_tag_und_stunde(db, monkeypatch):
    from backend.services.snapshot.aggregator import get_daily_counter_deltas_by_inv, get_hourly_counter_sum_by_feld

    a = await _anlage(db, ["wp_starts_anzahl"], typ="waermepumpe")
    key = "inv:2:wp_starts_anzahl"
    # alter Zähler 1000 + 1 je Stunde, neuer ab der Naht bei 5 + 1 je Stunde
    stand = {t: (1000.0 + (t - TAG0).total_seconds() / 3600) if t < NAHT else 5.0 + (t - NAHT).total_seconds() / 3600
             for t in _stunden(TAG0 - timedelta(hours=1), TAG0 + timedelta(days=1))}
    await _reihe(db, a.id, key, stand)
    await _wechsel(db, a.id, key)
    invs = {"2": await db.get(Investition, 2)}
    tag = (await get_daily_counter_deltas_by_inv(db, a, invs, D))["wp_starts_anzahl"]["2"]
    stunde = await get_hourly_counter_sum_by_feld(db, a, invs, D, "wp_starts_anzahl")
    assert tag == 23 and stunde[11] == 0 and stunde[12] == 1
    _ohne_naht(monkeypatch)
    tag = (await get_daily_counter_deltas_by_inv(db, a, invs, D))["wp_starts_anzahl"]["2"]
    assert tag == 0                                                                  # heute: Rückgang ⇒ 0 für den Tag


async def test_form3_stunde_sprung_nach_oben(db, monkeypatch):
    from backend.services.snapshot.aggregator import get_hourly_counter_sum_by_feld

    a = await _anlage(db, ["wp_starts_anzahl"], typ="waermepumpe")
    key = "inv:2:wp_starts_anzahl"
    await _reihe(db, a.id, key, {t: (1000.0 if t < NAHT else 1050.0) for t in FENSTER})
    await _wechsel(db, a.id, key)
    invs = {"2": await db.get(Investition, 2)}
    assert (await get_hourly_counter_sum_by_feld(db, a, invs, D, "wp_starts_anzahl"))[11] == 0
    _ohne_naht(monkeypatch)
    assert (await get_hourly_counter_sum_by_feld(db, a, invs, D, "wp_starts_anzahl"))[11] == 50


# ═══ Form 4: zaehlerstaende.py ══════════════════════════════════════════════════════════════════════════════════════

async def test_form4_zaehlerstand_differenz_und_bruch(db, monkeypatch):
    import backend.services.zaehlerstaende as zs
    from backend.core.field_definitions import ZAEHLERSTAND_FELD

    a = await _anlage(db, [ZAEHLERSTAND_FELD], typ="sonstiges", parameter={"kategorie": "zaehler"})
    key = zs.sensor_key_fuer(2)
    stand = {t: (100.0 + (t - TAG0).total_seconds() / 3600 * 0.5) if t < NAHT else 500.0 + (t - NAHT).total_seconds() / 3600
             for t in _stunden(TAG0, TAG0 + timedelta(days=1))}
    await _reihe(db, a.id, key, stand)
    await _wechsel(db, a.id, key)
    (f,) = await zs.lade_zaehlerstaende(db, a.id, TAG0, TAG0 + timedelta(days=1), mit_verlauf=False)
    assert f.differenz == pytest.approx(5.0 + 13.0) and not f.reihe_gebrochen
    punkte = [zs.VerlaufPunkt(t, w - (1000.0 if t >= NAHT else 0.0)) for t, w in stand.items()]
    assert zs.finde_reihen_brueche(punkte, [NAHT]) == [] and len(zs.finde_reihen_brueche(punkte)) == 1
    monkeypatch.setattr(zw, "fortsetzungs_naehte", lambda *a, **k: _leer())
    (f,) = await zs.lade_zaehlerstaende(db, a.id, TAG0, TAG0 + timedelta(days=1), mit_verlauf=False)
    assert f.differenz == pytest.approx(stand[TAG0 + timedelta(days=1)] - stand[TAG0])     # heute: über die Naht


# ═══ B-4: Fortsetzung bei MQTT ═════════════════════════════════════════════════════════════════════════════════════

T0 = datetime(2026, 6, 10, 0)
MQTT_KEY = "netzbezug_kwh"
KANAL_KEY = "basis:netzbezug"


async def _mqtt_anlage(db):
    from backend.tests import factories

    a = await factories.anlage(db, leistung_kwp=10.0, sensor_mapping={"basis": {}, "investitionen": {}})
    await factories.investition(db, typ="pv-module", anlage_id=a.id)
    await db.commit()
    return a


async def _mqtt_staende(db, aid, folge: dict[int, list[tuple[int, float]]]):
    """``{stunde: [(minute, Stand), …]}`` → ``mqtt_energy_snapshots``."""
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

    await db.execute(insert(MqttEnergySnapshot), [
        {"anlage_id": aid, "energy_key": MQTT_KEY, "value_kwh": w, "timestamp": T0 + timedelta(hours=h, minutes=m)}
        for h, werte in folge.items() for m, w in werte])
    await db.commit()


async def _mqtt_lauf(db, a, stunden):
    from backend.services.kanal.schreiber import schreibe_eigene_summe

    for h in stunden:
        await schreibe_eigene_summe(db, a, T0 + timedelta(hours=h, minutes=5))
        await db.commit()


async def _kanal_delta(db, a, von_h: int, bis_h: int) -> float:
    """Δ des Kanals über [T0 + von_h, T0 + bis_h) nach der Lese-Schicht (Wert = sum + offset der geltenden Quelle)."""
    from backend.models.kanal import Kanal
    from backend.services.kanal.lesen import zeitraum

    k = (await db.execute(select(Kanal).where(Kanal.anlage_id == a.id, Kanal.key == KANAL_KEY))).scalar_one()
    z = await zeitraum(db, k, int((T0 + timedelta(hours=von_h)).timestamp()), int((T0 + timedelta(hours=bis_h)).timestamp()),
                       jetzt=int((T0 + timedelta(days=2)).timestamp()))
    return z.delta if z.delta is not None else z.teil_delta


async def _mqtt_wechsel(db, aid, erklaert: datetime, grund="fortsetzung"):
    db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=KANAL_KEY, erklaert_ts=erklaert, ab_ts=ab_ts_aus(erklaert),
                            vorher={"art": "mqtt", "mqtt_key": MQTT_KEY}, nachher={"art": "mqtt", "mqtt_key": MQTT_KEY},
                            grund=grund, herkunft="wechsel"))
    await db.commit()
    zw.vergiss(db)


def _ohne_mqtt_naht(monkeypatch):
    async def keine(*a, **k):
        return []
    monkeypatch.setattr("backend.services.kanal.naht.offene_naehte", keine)


#: Publisher-Wechsel um 1:47 — Stände je 15 Minuten, alter Publisher bis 1:45, neuer ab 1:50.
NACH_OBEN = {0: [(0, 1000.0), (30, 1001.0)], 1: [(0, 1002.0), (45, 1003.0), (50, 3003.0)], 2: [(0, 3004.0), (30, 3005.0)],
             3: [(0, 3006.0)]}
NACH_UNTEN = {0: [(0, 1000.0), (30, 1010.0)], 1: [(0, 1020.0), (45, 1050.0), (50, 525.0)], 2: [(0, 526.0), (30, 527.0)],
              3: [(0, 528.0)]}


@pytest.mark.parametrize("folge,ohne", [(NACH_OBEN, 2.0 + 0.0 + 3.0), (NACH_UNTEN, 40.0 + 0.0 + 3.0)],
                         ids=["nach_oben_2000", "nach_unten_1050_525"])
async def test_b4_publisher_wechsel_zaehlt_den_sprung_nicht(db, monkeypatch, folge, ohne):
    """+2 000 ⇒ kein Zuwachs 2 000; 1 050 → 525 ⇒ kein Zuwachs 525 (Messblatt Konzept §10 M6). Δ über [1:00, 4:00): der alte
    Publisher bis 1:45, die neue Periode ab ihrem ersten Stand (Nullpunkt), danach 3 kWh."""
    a = await _mqtt_anlage(db)
    await _mqtt_staende(db, a.id, folge)
    await _mqtt_wechsel(db, a.id, T0 + timedelta(hours=1, minutes=47))
    await _mqtt_lauf(db, a, [1, 2, 3, 4])
    assert await _kanal_delta(db, a, 1, 4) == pytest.approx(ohne)


@pytest.mark.parametrize("folge,heute", [(NACH_OBEN, 2005.0), (NACH_UNTEN, 568.0)], ids=["oben", "unten"])
async def test_b4_ohne_grund_wie_heute(db, monkeypatch, folge, heute):
    """Ein Wechsel ohne Grund liest wie heute: +2 000 zählt ganz, 1 050 → 525 ist ein Reset und der neue Stand zählt ab 0."""
    a = await _mqtt_anlage(db)
    await _mqtt_staende(db, a.id, folge)
    await _mqtt_wechsel(db, a.id, T0 + timedelta(hours=1, minutes=47), grund=None)
    await _mqtt_lauf(db, a, [1, 2, 3, 4])
    assert await _kanal_delta(db, a, 1, 4) == pytest.approx(heute)


async def test_b4_sprengsatz_naht_nicht_angewandt(db, monkeypatch):
    _ohne_mqtt_naht(monkeypatch)
    a = await _mqtt_anlage(db)
    await _mqtt_staende(db, a.id, NACH_OBEN)
    await _mqtt_wechsel(db, a.id, T0 + timedelta(hours=1, minutes=47))
    await _mqtt_lauf(db, a, [1, 2, 3, 4])
    assert await _kanal_delta(db, a, 1, 4) == pytest.approx(2005.0)


async def test_b4_neuer_publisher_erst_nach_dem_stundenende(db):
    """Der neue Publisher sendet erst nach dem Lauf der Naht-Stunde — der nächste Lauf wendet die Naht an (kein Rohstand
    zwischen Erklärung und Laufbeginn)."""
    a = await _mqtt_anlage(db)
    await _mqtt_staende(db, a.id, {0: [(0, 1000.0)], 1: [(0, 1001.0), (45, 1002.0)]})
    await _mqtt_wechsel(db, a.id, T0 + timedelta(hours=1, minutes=47))
    await _mqtt_lauf(db, a, [1, 2])
    await _mqtt_staende(db, a.id, {2: [(10, 3002.0), (40, 3003.0)], 3: [(0, 3004.0)]})
    await _mqtt_lauf(db, a, [3, 4])
    assert await _kanal_delta(db, a, 1, 4) == pytest.approx(2.0 + 1.0 + 1.0)
    await _mqtt_lauf(db, a, [5, 6])                               # spätere Läufe wenden die Naht nicht noch einmal an
    assert await _kanal_delta(db, a, 1, 4) == pytest.approx(4.0)


async def test_b4_nachtrag_nach_40_tagen_zeilen_bitgleich(db):
    """Der Sprung ist schon geschrieben (Wechsel nicht verzeichnet), die Rohstände sind weg (31 Tage): der Nachtrag setzt
    eine Quellzeile ab der Naht-Stunde — die Kanalzeilen bleiben bitgleich, die Naht-Stunde trägt keinen Zuwachs mehr."""
    from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
    from backend.services.kanal.naht import nachtrag_fortsetzung

    a = await _mqtt_anlage(db)
    await _mqtt_staende(db, a.id, NACH_OBEN)
    await _mqtt_lauf(db, a, [1, 2, 3, 4])
    k = (await db.execute(select(Kanal).where(Kanal.anlage_id == a.id, Kanal.key == KANAL_KEY))).scalar_one()

    async def zeilen():
        return [(r.start_ts, r.sum, r.state, r.familie) for r in (await db.execute(
            select(KanalStatistik).where(KanalStatistik.kanal_id == k.id).order_by(KanalStatistik.start_ts))).scalars()]

    vorher = await zeilen()
    assert await _kanal_delta(db, a, 1, 4) == pytest.approx(2005.0)
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from sqlalchemy import delete
    await db.execute(delete(MqttEnergySnapshot))                     # 40 Tage später: keine Rohstände mehr
    await db.commit()
    h = int((T0 + timedelta(hours=1)).timestamp())
    offset = await nachtrag_fortsetzung(db, k.id, h)
    await db.commit()
    assert await zeilen() == vorher
    assert await _kanal_delta(db, a, 1, 2) == pytest.approx(0.0)
    assert await _kanal_delta(db, a, 1, 4) == pytest.approx(2.0 + 1.0)        # die Naht-Stunde trägt nichts mehr
    quellen = (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id)
                                .order_by(KanalQuelle.gueltig_ab))).scalars().all()
    assert [(q.gueltig_ab, q.offset) for q in quellen][-1] == (h, offset)


# ═══ Korrekturrunde S2 (Bauplan §9 Nr. 25, K-3): Nachtrag idempotent, Quellgrenzen, Aufhebung, Nebenwirkungen ══════════

async def _kanal_der_anlage(db, a):
    from backend.models.kanal import Kanal

    return (await db.execute(select(Kanal).where(Kanal.anlage_id == a.id, Kanal.key == KANAL_KEY))).scalar_one()


async def _quellen(db, kanal_id):
    from backend.models.kanal import KanalQuelle

    return [(q.gueltig_ab, q.offset) for q in (await db.execute(
        select(KanalQuelle).where(KanalQuelle.kanal_id == kanal_id).order_by(KanalQuelle.gueltig_ab))).scalars()]


def _h(stunde: int) -> int:
    return int((T0 + timedelta(hours=stunde)).timestamp())


async def test_b4_nachtrag_zweimal_wie_einmal(db):
    """§9 Nr. 25: der zweite Nachtrag an derselben Stunde ändert nichts (Nachmessung: Versatz −2 002 → −4 004, Naht-Stunde
    0 → −2 002). Gegenprobe im selben Test: ein Nachtrag an einer Stunde ohne Quellgrenze setzt sehr wohl einen Versatz."""
    from backend.services.kanal.naht import nachtrag_fortsetzung

    a = await _mqtt_anlage(db)
    await _mqtt_staende(db, a.id, NACH_OBEN)
    await _mqtt_lauf(db, a, [1, 2, 3, 4])
    k = await _kanal_der_anlage(db, a)
    assert await _kanal_delta(db, a, 1, 2) == pytest.approx(2002.0)
    eins = await nachtrag_fortsetzung(db, k.id, _h(1))
    await db.commit()
    nach_eins = await _quellen(db, k.id)
    zwei = await nachtrag_fortsetzung(db, k.id, _h(1))
    await db.commit()
    assert eins == zwei == pytest.approx(-2002.0)
    assert await _quellen(db, k.id) == nach_eins
    assert await _kanal_delta(db, a, 1, 2) == pytest.approx(0.0)
    assert await _kanal_delta(db, a, 1, 4) == pytest.approx(3.0)
    # Gegenprobe: an der Stunde 2 beginnt keine Quelle — dort setzt der Nachtrag einen Versatz (die Stunde trägt dann 0)
    assert await nachtrag_fortsetzung(db, k.id, _h(2)) == pytest.approx(-2002.0 - 2.0)        # Stunde 2 trug 2 kWh
    await db.commit()
    assert await _kanal_delta(db, a, 2, 3) == pytest.approx(0.0)


async def test_b4_nachtrag_nach_angewandter_naht_aendert_nichts(db):
    """Der Stundenlauf hat die verzeichnete Fortsetzung schon angewandt (Quelle ab der Naht-Stunde) — ein Nachtrag an derselben
    Stunde lässt alles stehen (Nachmessung: Δ[1,4) 5 → 6). Gegenprobe: ohne Naht des Laufs trägt dieselbe Stunde den Sprung,
    und der Nachtrag nimmt ihn heraus."""
    from backend.services.kanal.naht import nachtrag_fortsetzung

    a = await _mqtt_anlage(db)
    await _mqtt_staende(db, a.id, NACH_OBEN)
    await _mqtt_wechsel(db, a.id, T0 + timedelta(hours=1, minutes=47))
    await _mqtt_lauf(db, a, [1, 2, 3, 4])
    k = await _kanal_der_anlage(db, a)
    vorher = await _quellen(db, k.id)
    assert await _kanal_delta(db, a, 1, 4) == pytest.approx(5.0)
    await nachtrag_fortsetzung(db, k.id, _h(1))
    await db.commit()
    assert await _kanal_delta(db, a, 1, 4) == pytest.approx(5.0) and await _quellen(db, k.id) == vorher


async def test_b4_nachtrag_spaetere_quellgrenze_rueckt_mit(db):
    """Zwei Publisher-Sprünge: 1:47 unverzeichnet (der Kanal trägt ihn), 2:47 mit Grund «Fortsetzung» (der Lauf setzt eine Quelle
    ab 2:00 mit dem damaligen Kanalwert als Versatz). Der Nachtrag an 1:00 nimmt den ersten Sprung heraus — die spätere
    Quellzeile rückt um dieselbe Verschiebung mit, sonst käme der Sprung an ihrer Grenze zurück."""
    from backend.services.kanal.naht import nachtrag_fortsetzung

    a = await _mqtt_anlage(db)
    await _mqtt_staende(db, a.id, {0: [(0, 1000.0), (30, 1001.0)], 1: [(0, 1002.0), (45, 1003.0), (50, 3003.0)],
                                   2: [(0, 3004.0), (45, 3005.0), (50, 6005.0)], 3: [(0, 6006.0), (30, 6007.0)],
                                   4: [(0, 6008.0)]})
    await _mqtt_wechsel(db, a.id, T0 + timedelta(hours=2, minutes=47))
    await _mqtt_lauf(db, a, [1, 2, 3, 4, 5])
    k = await _kanal_der_anlage(db, a)
    je_stunde_vorher = [await _kanal_delta(db, a, h, h + 1) for h in (1, 2, 3)]
    assert je_stunde_vorher[0] > 2000.0 and je_stunde_vorher[1] < 10.0          # 1:00 trägt den Sprung, 2:00 ist überbrückt
    spaeter_vorher = [q for q in await _quellen(db, k.id) if q[0] > _h(1)]
    offset = await nachtrag_fortsetzung(db, k.id, _h(1))
    await db.commit()
    je_stunde = [await _kanal_delta(db, a, h, h + 1) for h in (1, 2, 3)]
    assert je_stunde == [pytest.approx(0.0), pytest.approx(je_stunde_vorher[1]), pytest.approx(je_stunde_vorher[2])]
    verschiebung = -je_stunde_vorher[0]
    assert [q for q in await _quellen(db, k.id) if q[0] > _h(1)] == [
        (ab, pytest.approx(off + verschiebung)) for ab, off in spaeter_vorher]
    assert offset == pytest.approx(verschiebung)
    # Gegenprobe: ohne das Mitrücken (die spätere Quellzeile auf ihren alten Versatz) käme der Sprung an 2:00 zurück
    from backend.models.kanal import KanalQuelle
    for ab, off in spaeter_vorher:
        q = (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id, KanalQuelle.gueltig_ab == ab))).scalar_one()
        q.offset = off
    await db.commit()
    assert await _kanal_delta(db, a, 2, 3) == pytest.approx(je_stunde_vorher[1] - verschiebung)


async def test_b4_aufgehobene_fortsetzung_ist_keine_naht(db):
    """Eine Fortsetzung, die eine spätere Zeile aufhebt (``aufgehoben_durch``), wendet der Lauf nicht an — wie ohne Grund.
    Gegenprobe im selben Test: dieselbe Lage, nicht aufgehoben ⇒ die Naht wirkt."""
    async def lauf(aufheben: bool) -> float:
        a = await _mqtt_anlage(db)
        await _mqtt_staende(db, a.id, NACH_OBEN)
        w = ZuordnungWechsel(anlage_id=a.id, sensor_key=KANAL_KEY, erklaert_ts=T0 + timedelta(hours=1, minutes=47),
                             ab_ts=ab_ts_aus(T0 + timedelta(hours=1, minutes=47)), vorher={"art": "mqtt", "mqtt_key": MQTT_KEY},
                             nachher={"art": "mqtt", "mqtt_key": MQTT_KEY}, grund="fortsetzung", herkunft="wechsel",
                             aufgehoben_durch=999 if aufheben else None)
        db.add(w)
        await db.commit()
        zw.vergiss(db)
        await _mqtt_lauf(db, a, [1, 2, 3, 4])
        return await _kanal_delta(db, a, 1, 4)

    assert await lauf(aufheben=True) == pytest.approx(2005.0)
    assert await lauf(aufheben=False) == pytest.approx(5.0)


async def test_b4_nachtrag_verwirft_abgeleitete_ab_der_stunde_und_merkt_neu(db, monkeypatch):
    """Der Nachtrag verwirft die Zeilen der abgeleiteten Kanäle ab der Naht-Stunde (die davor bleiben) und die gemerkten Tage ab
    dem Tag des Vorstands. Gegenprobe: ein Nachtrag ohne Zeile in der Stunde (nichts zu tun) verwirft und vergisst nichts."""
    from backend.models.kanal import Kanal, KanalStatistik
    from backend.services.kanal import merken
    from backend.services.kanal.naht import nachtrag_fortsetzung

    a = await _mqtt_anlage(db)
    await _mqtt_staende(db, a.id, NACH_OBEN)
    await _mqtt_lauf(db, a, [1, 2, 3, 4])
    k = await _kanal_der_anlage(db, a)
    ab = Kanal(anlage_id=a.id, key="abgeleitet:basis:netzbezug_bewertet_kwh", einheit="kWh", art="sum")
    db.add(ab)
    await db.flush()
    db.add_all([KanalStatistik(kanal_id=ab.id, start_ts=_h(h), sum=float(h), familie="abgeleitet") for h in (0, 1, 2, 3)])
    await db.commit()
    vergessen: list = []
    echt = merken.invalidiere
    monkeypatch.setattr(merken, "invalidiere", lambda aid, *x, **kw: (vergessen.append((aid, kw.get("von"))), echt(aid, *x, **kw)))

    async def abgeleitet() -> list[int]:
        return [r.start_ts for r in (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == ab.id)
                                                      .order_by(KanalStatistik.start_ts))).scalars()]

    assert await nachtrag_fortsetzung(db, k.id, _h(9)) is None              # Gegenprobe: keine Zeile in der Stunde
    assert await abgeleitet() == [_h(0), _h(1), _h(2), _h(3)] and vergessen == []
    await nachtrag_fortsetzung(db, k.id, _h(1))
    await db.commit()
    assert await abgeleitet() == [_h(0)]
    assert (a.id, T0.date()) in vergessen


async def test_b4_nachtrag_nur_fuer_die_eigene_summe(db):
    """Ein Spiegel-Kanal (HA) bekommt keinen Nachtrag — dort gilt G-1 («Summe in Home Assistant anpassen»). Gegenprobe: die
    eigene Summe desselben Laufs nimmt ihn an."""
    from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
    from backend.services.kanal.naht import nachtrag_fortsetzung

    a = await _mqtt_anlage(db)
    sp = Kanal(anlage_id=a.id, key="basis:einspeisung", einheit="kWh", art=ART_SUM)
    db.add(sp)
    await db.flush()
    db.add(KanalQuelle(kanal_id=sp.id, gueltig_ab=_h(0), familie=FAMILIE_SPIEGEL, statistic_id="sensor.e", offset=0.0))
    db.add_all([KanalStatistik(kanal_id=sp.id, start_ts=_h(h), sum=w, familie=FAMILIE_SPIEGEL)
                for h, w in ((0, 10.0), (1, 2010.0), (2, 2011.0))])
    await db.commit()
    with pytest.raises(ValueError):
        await nachtrag_fortsetzung(db, sp.id, _h(1))
    assert len(await _quellen(db, sp.id)) == 1
    await _mqtt_staende(db, a.id, NACH_OBEN)
    await _mqtt_lauf(db, a, [1, 2, 3, 4])
    assert await nachtrag_fortsetzung(db, (await _kanal_der_anlage(db, a)).id, _h(1)) == pytest.approx(-2002.0)


# ═══ K-3, B-3: welche Wechsel eine Naht sind; Stundenform; Daten-Checker ═══════════════════════════════════════════

@pytest.mark.parametrize("grund,aufgehoben,naht", [
    ("fortsetzung", None, True), ("fortsetzung", 999, False), ("korrektur", None, False), (None, None, False),
], ids=["fortsetzung", "aufgehoben", "korrektur", "ohne_grund"])
async def test_b3_nur_eine_nicht_aufgehobene_fortsetzung_ist_naht(db, grund, aufgehoben, naht):
    """Die Ladestelle der Reihen-Leser (``fortsetzungs_naehte``): nur ``grund = fortsetzung`` ohne ``aufgehoben_durch`` ist eine
    Naht — die Korrektur verwirft und füllt (Sitzung 3), eine aufgehobene Erklärung gilt nicht. Je Fall die Wirkung am
    Tageswert (Gegenprobe im selben Test: der Fall «fortsetzung» liest 23, jeder andere den Sprung)."""
    a = await _anlage(db, ["ladung_pv_kwh"])
    await _reihe(db, a.id, "inv:2:ladung_pv_kwh", {t: _stand(t) for t in FENSTER})
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key="inv:2:ladung_pv_kwh", erklaert_ts=ERKLAERT, ab_ts=NAHT,
                            vorher={"art": "ha", "entity_id": "sensor.alt"}, nachher={"art": "ha", "entity_id": "sensor.neu"},
                            grund=grund, herkunft="wechsel", aufgehoben_durch=aufgehoben,
                            falsch_seit_ts=TAG0 if grund == "korrektur" else None))
    await db.flush()
    zw.vergiss(db)
    assert (await zw.fortsetzungs_naehte(db, a.id, "inv:2:ladung_pv_kwh")) == ([NAHT] if naht else [])
    assert await _tagesdetail(db, a) == pytest.approx(TAGESWERT if naht else TAGESWERT + 1.0 + SPRUNG)


async def test_b3_stundenform_keine_gerade_ueber_die_naht(db, monkeypatch):
    """``stunden_leser.lade_stundenformen``: fehlen 9:00 und 10:00, füllt E1 linear — über die Naht nicht (sonst verteilte die
    Gerade den Sprung auf 9 und 10 Uhr). Gegenprobe: ohne Naht ⇒ Stunden über 600."""
    from backend.services.snapshot.stunden_leser import lade_stundenformen

    a = await _anlage(db, ["stromverbrauch_kwh"], typ="waermepumpe")
    key = "inv:2:stromverbrauch_kwh"
    luecke = {TAG0 + timedelta(hours=9), TAG0 + timedelta(hours=10)}
    await _reihe(db, a.id, key, {t: _stand(t) for t in FENSTER if t not in luecke})
    await _wechsel(db, a.id, key)
    s = (await lade_stundenformen(db, a, D, [(key, None)]))[key]
    assert max(v or 0.0 for v in s) < 2.0
    _ohne_naht(monkeypatch)
    s = (await lade_stundenformen(db, a, D, [(key, None)]))[key]
    assert max(v or 0.0 for v in s) > 600.0


@pytest.mark.parametrize("grund,brueche", [("fortsetzung", 0), (None, 1)], ids=["fortsetzung", "ohne_grund"])
async def test_b3_daten_checker_reihenbruch_ueber_eine_naht(db, grund, brueche):
    """Befund «Zählerstand-Reihe» (``daten_checker/zaehler.py``): ein gefallener Stand über eine verzeichnete Fortsetzung ist
    kein Bruch — der neue Zähler beginnt dort. Gegenprobe (Parameter): derselbe Wechsel ohne Grund ⇒ der Bruch wird erklärt."""
    from backend.services.daten_checker import DatenChecker
    from backend.services.zaehlerstaende import sensor_key_fuer
    from backend.tests.test_d3_zaehlerstaende_checker import _anlage as gas_anlage
    from backend.tests.test_d3_zaehlerstaende_checker import _geladen, _snapshots, _zaehler

    a = await gas_anlage(db)
    inv = await _zaehler(db, a)
    await _snapshots(db, a, inv, [(datetime(2025, 2, 1, 10), 900.0), (datetime(2025, 2, 1, 11), 905.0),
                                  (datetime(2025, 2, 1, 12), 12.0)])
    erklaert = datetime(2025, 2, 1, 11, 20)
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=sensor_key_fuer(inv.id), erklaert_ts=erklaert,
                            ab_ts=ab_ts_aus(erklaert), vorher={"art": "ha", "entity_id": "sensor.gas_alt"},
                            nachher={"art": "ha", "entity_id": "sensor.gas_neu"}, grund=grund, herkunft="wechsel"))
    await db.flush()
    zw.vergiss(db)
    erg = await DatenChecker(db)._check_zaehlerstaende(await _geladen(db, a.id))
    assert len([e for e in erg if "Bruch" in e.meldung]) == brueche, [e.meldung for e in erg]


async def test_b4_nachtrag_vergisst_gemerkte_tage_ohne_abgeleitete(db, monkeypatch):
    """Ohne abgeleitete Kanäle (``verwerfe_ab`` löscht nichts und vergisst deshalb nichts) vergisst der Nachtrag selbst die
    gemerkten Tage ab dem Tag des Vorstands — sonst zeigten Tagesansicht und Bilanz bis zum Verfall den alten Kanalwert.
    Gegenprobe im selben Test: ein Nachtrag ohne Zeile in der Stunde vergisst nichts."""
    from backend.services.kanal import merken
    from backend.services.kanal.naht import nachtrag_fortsetzung

    a = await _mqtt_anlage(db)
    await _mqtt_staende(db, a.id, NACH_OBEN)
    await _mqtt_lauf(db, a, [1, 2, 3, 4])
    k = await _kanal_der_anlage(db, a)
    vergessen: list = []
    echt = merken.invalidiere
    monkeypatch.setattr(merken, "invalidiere", lambda aid, *x, **kw: (vergessen.append((aid, kw.get("von"))), echt(aid, *x, **kw)))
    assert await nachtrag_fortsetzung(db, k.id, _h(9)) is None and vergessen == []
    await nachtrag_fortsetzung(db, k.id, _h(1))
    assert vergessen == [(a.id, T0.date())]
