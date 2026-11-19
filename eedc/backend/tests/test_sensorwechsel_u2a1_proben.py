"""Sensorwechsel U2 a1 «Rand-Werte und Leser» (Rechenweg ``opus-berichte/SENSORWECHSEL-U2-RECHENWEG-2026-11-19.md`` F1, F5–F7;
Bauplan Nr. 129, 138, 139, 141, 142). Proben mit Sprengsatz.

**Regel.** Die Menge eines Zählerfelds über ein Fenster ist die Summe der Zuwächse seiner Quellen, jede in ihrer Geltungszeit.
Ein angesetzter Wechsel «bleiben» (``zuordnung_wechsel.ansatz`` ``beide``/``schnitt`` mit ``stand_alt_ende``/``stand_neu_null``)
teilt die Reihe nicht, er hebt ihre Stände ab ``ab_ts`` (F5); der Tagesabschluss aus HA-Slots zählt am Naht-Slot beide
Sensoren, die neue Entität ab 0 (F6); der Monat aus HA summiert je Geltungsabschnitt (F7). Eine Zeile **ohne** ``ansatz`` liest
wörtlich wie am ``665fa8d3b`` (Sprengsatz «ohne Ansatz» je Probe). In a1 setzt kein Produktivweg ``ansatz`` — die Proben setzen
die Zeilen von Hand.

**Lab-Zeilen** (``opus-berichte/SENSORWECHSEL-HA-WEGE-2026-11-19.md`` §2, Wege 1/4): alter Zähler 1 kWh/h, die Stunde vor dem
Tausch ohne Zuwachs, in der Tausch-Stunde noch +0,6; neuer Zähler erste Zeile in der Tausch-Stunde ``sum`` 0,7 (Nullpunkt 0),
danach 0,5 kWh/h. Soll nach HAs Regel: Σ der Zeilen-Zuwächse beider Statistiken (die erste des neuen ab 0) — Tausch-Stunde 1,3.

Die Zeiten sind Epoch-Stunden (Sommerzeit-Tage haben 23/25 Zeilen); jede Probe rechnet ihr Soll aus denselben Zeilen und
fährt in Berlin, ``Pacific/Auckland`` und ``UTC``. Keine Probe liest die Uhr.

Schwesterdateien: test_sensorwechsel_s2_naht.py (die Formen der Naht ohne Rand-Stände), test_sensorwechsel_u1k_proben.py (die
Korrektur, an der P-2 sitzt), test_reihen_leser_waechter.py (Einstufung der Leser).
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select, text

from backend.core.berechnungen import zaehler_naht as zn
from backend.models import activity_log, mqtt_gateway_mapping  # noqa: F401 — Tabellen der Routen (Teil-Schema der Fixture)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.tests import test_sensorwechsel_s2_naht as s2

ALT, NEU = "sensor.alt", "sensor.neu"
QA, QN = {"art": "ha", "entity_id": ALT}, {"art": "ha", "entity_id": NEU}
STUNDE = 3600


# ═══ F5 — die reine Regel ═══════════════════════════════════════════════════════════════════════════════════════════

def test_naht_mit_rand_hebt_und_teilt_nicht():
    t = [datetime(2026, 6, 10, h) for h in range(5)]
    f = [(t[0], 10.0), (t[1], 11.0), (t[2], 1.5), (t[3], 2.5), (t[4], 3.0)]          # neuer Zähler ab t2 (Nullpunkt 0,5)
    naht = zn.Naht(t[2], 11.0 - 0.5)                                                  # stand_alt_ende 11,0 · stand_neu_null 0,5
    assert zn.abschnitte(f, [naht]) == [[(t[0], 10.0), (t[1], 11.0), (t[2], 12.0), (t[3], 13.0), (t[4], 13.5)]]
    assert zn.stand_differenz(f, [naht]) == pytest.approx(3.5)
    assert zn.stand_differenz(f, [t[2]]) == pytest.approx(1.0 + 1.5)                  # Sprengsatz: ohne Rand teilt sie (B-3)
    assert zn.zaehlwerk_menge(f, [naht]) == pytest.approx(3.5)
    assert zn.traegt_messung(f, [naht]) and zn.trennende([naht, t[1]]) == [t[1]]
    assert zn.hebung_am(t[4], [naht, zn.Naht(t[3], 2.0)]) == pytest.approx(12.5)     # zwei Nähte: die Versätze summieren
    assert zn.gehoben(f, [t[2]]) is f and zn.gehobene_staende({0: 1.0}, lambda i: t[i], [t[2]]) == {0: 1.0}   # bitgleich
    assert naht == t[2] and hash(naht) == hash(t[2]) and sorted([t[3], naht]) == [naht, t[3]]
    assert type(naht + timedelta(hours=1)) is datetime and type(naht - timedelta(hours=1)) is datetime
    assert type(naht.replace(hour=1)) is datetime and zn.versatz_der_naht(naht + timedelta(0)) is None
    assert zn.rand_versatz(None, 0.0) is None and zn.rand_versatz(438.6, 0.0) == pytest.approx(438.6)
    assert zn.slot_beider(0.7, 1, 0.6, 1) == (pytest.approx(1.3), 1)
    assert zn.monat_aus_abschnitten([(10.0, 414.6, 0.0, 400), (0.0, 12.7, 0.0, 25)]) == (
        10.0, pytest.approx(437.3), pytest.approx(427.3), 0.0, 425)


@pytest.mark.parametrize("ansatz,rand,aufgehoben,erwartet", [
    (None, (438.6, 0.0), None, "teilt"),            # ohne Ansatz: wie am HEAD
    ("offen", (438.6, 0.0), None, "teilt"), ("offen_schnitt", None, None, "teilt"),
    ("beide", (438.6, 0.0), None, 438.6), ("schnitt", (100.0, 7.9), None, 92.1),
    ("beide", (438.6, None), None, "teilt"),        # ein Rand-Stand fehlt: teilt
    ("beide", (438.6, 0.0), 99, None),              # aufgehoben: keine Naht
])
def test_naehte_der_fortsetzung_je_ansatz(ansatz, rand, aufgehoben, erwartet):
    ab = datetime(2026, 11, 18, 8)
    alt_ende, neu_null = rand or (None, None)
    w = zw.Wechsel("k", ab, QA, QN, "fortsetzung", aufgehoben_durch=aufgehoben, id=1, ansatz=ansatz,
                   stand_alt_ende=alt_ende, stand_neu_null=neu_null)
    n = zw.naehte_der_fortsetzung([w])
    if erwartet is None:
        assert n == []
    elif erwartet == "teilt":
        assert n == [ab] and zn.versatz_der_naht(n[0]) is None
    else:
        assert n == [ab] and zn.versatz_der_naht(n[0]) == pytest.approx(erwartet)


# ═══ F5 — die Leser L1–L10 an den Formen der Sitzung 2 (s2: 1 kWh/h, ab der Naht 2 000 höher) ════════════════════════
#
# Mit Rand-Ständen (stand_alt_ende 111, stand_neu_null 2 111 ⇒ Versatz −2 000) zählt die Naht-Stunde ihren Zuwachs: 24,0
# statt 23,0. Sprengsatz je Probe: dieselbe Zeile ohne ``ansatz`` liest wie am HEAD (23,0 bzw. Naht-Slot 0).


async def _wechsel_mit_rand(db, aid: int, key: str, *, ansatz="beide", alt_ende=111.0, neu_null=2111.0):
    db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=s2.ERKLAERT, ab_ts=s2.NAHT, vorher=QA, nachher=QN,
                            grund="fortsetzung", herkunft="wechsel", ansatz=ansatz, stand_alt_ende=alt_ende,
                            stand_neu_null=neu_null))
    await db.flush()
    zw.vergiss(db)


async def _ohne_ansatz(db):
    for w in (await db.execute(select(ZuordnungWechsel))).scalars().all():
        w.ansatz = None
    await db.flush()
    zw.vergiss(db)


async def test_l1_l3_l4_tag_bereich_delta(db):
    from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE
    from backend.services.snapshot.bereichs_leser import lade_tageswerte_je_feld
    from backend.services.snapshot.reader import delta

    a = await s2._anlage(db, ["ladung_pv_kwh"])
    key = "inv:2:ladung_pv_kwh"
    await s2._reihe(db, a.id, key, {t: s2._stand(t) for t in s2._stunden(s2.TAG0 - timedelta(hours=1), s2.TAG0 + timedelta(days=1))})
    await _wechsel_mit_rand(db, a.id, key)
    invs = {"2": await db.get(Investition, 2)}
    felder = {("wallbox", "ladung_pv_kwh"): TAGESDETAIL_AUSGABE[("wallbox", "ladung_pv_kwh")]}

    async def drei():
        b = (await lade_tageswerte_je_feld(db, a, invs, s2.D, s2.D, felder))[s2.D]["emob_ladung_pv_kwh"]
        return await s2._tagesdetail(db, a), b, await delta(db, a.id, key, "sensor.x", s2.TAG0, s2.TAG0 + timedelta(days=1))

    assert await drei() == (pytest.approx(24.0), pytest.approx(24.0), pytest.approx(24.0))
    await _ohne_ansatz(db)
    assert await drei() == (pytest.approx(23.0), pytest.approx(23.0), pytest.approx(23.0))     # Sprengsatz: wie am HEAD


async def test_l5_l6_naht_slot_zaehlt_seine_menge(db):
    from backend.services.snapshot.stunden_leser import lade_stundenformen

    a = await s2._anlage(db, ["ladung_kwh", "stromverbrauch_kwh"])
    for key in ("inv:2:ladung_kwh", "inv:2:stromverbrauch_kwh"):
        await s2._reihe(db, a.id, key, {t: s2._stand(t) for t in s2.FENSTER})
        await _wechsel_mit_rand(db, a.id, key)
    invs = {"2": await db.get(Investition, 2)}

    async def zwei():
        t = await s2._tabelle(db, a, invs)
        s = (await lade_stundenformen(db, a, s2.D, [("inv:2:stromverbrauch_kwh", None)]))["inv:2:stromverbrauch_kwh"]
        return t.stunden[11]["wallbox"], t.komponenten_kwh["wallbox_2"], s[11], sum(s)

    assert await zwei() == (pytest.approx(1.0), pytest.approx(24.0), pytest.approx(1.0), pytest.approx(24.0))
    await _ohne_ansatz(db)
    assert await zwei() == (pytest.approx(0.0), pytest.approx(23.0), 0.0, pytest.approx(23.0))


async def test_l5_luecke_neben_einer_naht_mit_rand_fuellt_ueber_die_hebung(db):
    """E1 (#145) füllt fehlende Stände linear — über eine Naht mit Rand-Ständen in der gehobenen Reihe (kein Sprung)."""
    a = await s2._anlage(db, ["ladung_kwh"])
    luecke = {s2.TAG0 + timedelta(hours=10), s2.TAG0 + timedelta(hours=11)}
    await s2._reihe(db, a.id, "inv:2:ladung_kwh", {t: s2._stand(t) for t in s2.FENSTER if t not in luecke})
    await _wechsel_mit_rand(db, a.id, "inv:2:ladung_kwh")
    t = await s2._tabelle(db, a, {"2": await db.get(Investition, 2)})
    assert [t.stunden[h]["wallbox"] for h in (10, 11, 12)] == [pytest.approx(1.0)] * 3
    assert t.komponenten_kwh["wallbox_2"] == pytest.approx(24.0)


async def test_l7_l8_zaehlwerk_tag_und_stunde(db):
    from backend.services.snapshot.aggregator import get_daily_counter_deltas_by_inv, get_hourly_counter_sum_by_feld

    a = await s2._anlage(db, ["wp_starts_anzahl"], typ="waermepumpe")
    key = "inv:2:wp_starts_anzahl"
    stand = {t: (1000.0 + (t - s2.TAG0).total_seconds() / 3600) if t < s2.NAHT else 5.0 + (t - s2.NAHT).total_seconds() / 3600
             for t in s2._stunden(s2.TAG0 - timedelta(hours=1), s2.TAG0 + timedelta(days=1))}
    await s2._reihe(db, a.id, key, stand)
    await _wechsel_mit_rand(db, a.id, key, alt_ende=1010.0, neu_null=4.0)   # der alte endete bei 1010, der neue zählte 1
    invs = {"2": await db.get(Investition, 2)}

    async def zwei():
        tag = (await get_daily_counter_deltas_by_inv(db, a, invs, s2.D))["wp_starts_anzahl"]["2"]
        return tag, (await get_hourly_counter_sum_by_feld(db, a, invs, s2.D, "wp_starts_anzahl"))[11]

    assert await zwei() == (24, 1)
    await _ohne_ansatz(db)
    assert await zwei() == (23, 0)


async def test_l9_l10_zaehlerstand_gas(db):
    import backend.services.zaehlerstaende as zs
    from backend.core.field_definitions import ZAEHLERSTAND_FELD

    a = await s2._anlage(db, [ZAEHLERSTAND_FELD], typ="sonstiges", parameter={"kategorie": "zaehler"})
    key = zs.sensor_key_fuer(2)
    stand = {t: (100.0 + (t - s2.TAG0).total_seconds() / 3600 * 0.5) if t < s2.NAHT
             else 500.0 + (t - s2.NAHT).total_seconds() / 3600 for t in s2._stunden(s2.TAG0, s2.TAG0 + timedelta(days=1))}
    await s2._reihe(db, a.id, key, stand)
    await _wechsel_mit_rand(db, a.id, key, alt_ende=105.5, neu_null=500.0)          # Stand-Feld: Rand-Stände auf ``state``
    (f,) = await zs.lade_zaehlerstaende(db, a.id, s2.TAG0, s2.TAG0 + timedelta(days=1), mit_verlauf=False)
    assert f.differenz == pytest.approx(5.5 + 13.0) and not f.reihe_gebrochen
    await _ohne_ansatz(db)
    (f,) = await zs.lade_zaehlerstaende(db, a.id, s2.TAG0, s2.TAG0 + timedelta(days=1), mit_verlauf=False)
    assert f.differenz == pytest.approx(5.0 + 13.0)


def test_l15_nachbau_setzt_denselben_versatz_wie_die_reihe():
    """Stände-Nachbau aus HA-Ständen (``kanal/nachfuellen._laeufe`` + ``_offsets_rueckwaerts``): an einer Naht mit Rand-Ständen
    trägt die erste Stunde der neuen Quelle den Zuwachs beider Sensoren — Kanalwerte wie die gehobene Reihe. Sprengsatz: die
    Naht ohne Rand-Stände ⇒ die Stunde trägt keinen Zuwachs (wie am HEAD)."""
    from types import SimpleNamespace

    from backend.services.kanal import nachfuellen as nf

    ziel = SimpleNamespace(kennung=lambda h: f"k-{h}")
    t0 = datetime(2026, 6, 10, 0)
    staende = [(t0 + timedelta(hours=h), 100.0 + h if h < 5 else 0.5 * (h - 4), "ha") for h in range(9)]   # neu ab Stunde 5

    def kanal(naehte):
        ab = nf._laeufe(staende, ziel, naehte)
        for x in ab:
            x.zeilen = [{"sum": w, "state": w} for _t, w in x.staende]
        nf._offsets_rueckwaerts(ab, "sum", None)
        return [w + x.offset for x in ab for _t, w in x.staende]

    naht_zeit = t0 + timedelta(hours=6)                    # Stand um 06:00 = Ende der Zeile 05:00 (erste Zeile des neuen)
    werte = kanal([zn.Naht(naht_zeit, 104.0 + 0.6 - 0.0)])     # alter Zähler endete bei 104,6, Nullpunkt des neuen 0
    assert [round(b - a, 3) for a, b in zip(werte, werte[1:])] == [1.0, 1.0, 1.0, 1.0, pytest.approx(1.1), 0.5, 0.5, 0.5]
    werte = kanal([naht_zeit])
    assert round(werte[5] - werte[4], 3) == 0.0


async def test_l15_nachtrag_fortsetzung_mit_versatz(db):
    """``kanal/naht.nachtrag_fortsetzung`` mit ``versatz`` (Nachbau-Abschnitt, Familie Mitschrift): die Naht-Stunde trägt den
    Zuwachs beider Sensoren; ohne ``versatz`` keinen (Sprengsatz, wie am HEAD)."""
    from backend.models.kanal import ART_SUM, FAMILIE_MITSCHRIFT, Kanal, KanalQuelle, KanalStatistik
    from backend.services.kanal.naht import nachtrag_fortsetzung

    a = await s2._anlage(db, ["ladung_kwh"])
    t0 = int(time.mktime(datetime(2026, 6, 10, 0).timetuple()))
    out = []
    for versatz in (438.6, None):
        k = Kanal(anlage_id=a.id, key=f"inv:2:ladung_kwh:{versatz}", einheit="kWh", art=ART_SUM)
        db.add(k)
        await db.flush()
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=t0, familie=FAMILIE_MITSCHRIFT, statistic_id="ha", offset=0.0))
        for i, w in enumerate((437.0, 438.0, 0.7, 1.2)):          # Zeile 2 = erste des neuen (Stand 0,7)
            db.add(KanalStatistik(kanal_id=k.id, start_ts=t0 + STUNDE * i, sum=w, state=w, familie=FAMILIE_MITSCHRIFT))
        await db.flush()
        out.append(await nachtrag_fortsetzung(db, k.id, t0 + 2 * STUNDE, versatz))
    assert out[0] == pytest.approx(438.6) and 0.7 + out[0] - 438.0 == pytest.approx(1.3)
    assert out[1] == pytest.approx(438.0 - 0.7) and 0.7 + out[1] - 438.0 == pytest.approx(0.0)


# ═══ Lab-Saat: Reihe, Tagesabschluss aus HA-Slots (F6), Monat aus HA (F7) — mit Zeit-Proben ═════════════════════════

def _ep(t: datetime) -> int:
    return int(time.mktime(t.timetuple()))


class Lab:
    """Die Lab-Zeilen um ``t1`` (Beginn der Zeile, in der der neue Zähler beginnt; örtlich, erste Stunde bei doppelter
    Herbststunde). ``vorgeschichte``: der neue zählt 0,2 kWh/h schon ab einem Tag davor (Überlappung ⇒ ``schnitt`` an
    ``schnitt``-Zeit)."""

    def __init__(self, t1: datetime, *, vorgeschichte: bool = False, schnitt: datetime | None = None,
                 start: datetime | None = None):
        self.t1, self.e1 = t1, _ep(t1)
        # Beginn der Statistik des alten vor dem Vormonat des Tauschs: jeder Monat der Proben hat einen Anker (die erste Zeile
        # einer Statistik zählt in eedc nur am Wechsel ab 0 — Bauplan Nr. 139, E1 Option A).
        self.start = _ep(start or min(t1 - timedelta(days=2), datetime(t1.year, t1.month, 1) - timedelta(days=1)))
        self.ende = self.e1 + 3 * 86400
        self.vorgeschichte = vorgeschichte
        # Zählt ab: G (Epoch) — ohne Überlappung die erste Zeile des neuen, mit Überlappung der Schnitt.
        self.g = _ep(schnitt) if schnitt is not None else self.e1
        self.alt = self._reihe(lambda e: 1.0 if e < self.e1 - STUNDE else (0.6 if e == self.e1 else 0.0), self.start)
        neu_ab = self.e1 - 86400 - 7 * STUNDE if vorgeschichte else self.e1
        self.neu = self._reihe(lambda e: 0.2 if e < self.e1 else (0.7 if e == self.e1 else 0.5), neu_ab)

    def _reihe(self, zuwachs, ab: int) -> dict[int, tuple[float, float]]:
        """``{start_ts: (zuwachs, sum)}`` stündlich ab ``ab`` bis zum Ende."""
        out, s = {}, 0.0
        for e in range(ab, self.ende, STUNDE):
            s += zuwachs(e)
            out[e] = (zuwachs(e), round(s, 6))
        return out

    @property
    def ab_ts(self) -> datetime:
        """Erster Stand der neuen Quelle: Ende der Zeile G — Wand-Uhr wie ``lts_boundary_index`` (die Stunde nach G)."""
        return datetime.fromtimestamp(self.g) + timedelta(hours=1)

    def zeilen(self) -> list[tuple[int, float]]:
        """Die Zeilen, die nach HAs Regel zählen: der alte bis vor G (ohne Überlappung einschließlich G), der neue ab G
        (ohne Überlappung ab 0, mit Überlappung ab seiner Zeile vor G)."""
        beide = not self.vorgeschichte
        alt = [(e, z) for e, (z, _s) in self.alt.items() if e < self.g or (beide and e == self.g)]
        neu = [(e, z) for e, (z, _s) in self.neu.items() if e >= self.g]
        return alt + neu

    def soll(self, wo) -> float:
        return round(sum(z for e, z in self.zeilen() if wo(datetime.fromtimestamp(e))), 3)

    def stand(self, t: datetime) -> float | None:
        """Der Reihen-Stand um ``t`` (wie der Schreiber: vor ``ab_ts`` die alte Quelle, ab ``ab_ts`` die neue) — HAs ``sum``
        der Zeile ``t − 1 h``."""
        e = _ep(t) - STUNDE
        quelle = self.alt if t < self.ab_ts else self.neu
        return quelle[e][1] if e in quelle else None

    def rand(self, art: str) -> tuple[float, float]:
        """``(stand_alt_ende, stand_neu_null)`` nach F2: ohne Überlappung letzter Stand des alten und 0; mit Überlappung die
        Stände beider in der Zeile vor G."""
        if art == "beide":
            return max(s for _z, s in self.alt.values()), 0.0
        vor = self.g - STUNDE
        return self.alt[vor][1], self.neu[vor][1]


async def _lab_welt(db, monkeypatch, lab: Lab, *, art="beide", rand=None):
    """Anlage mit Wallbox (``ladung_kwh`` und ``ladung_pv_kwh`` heute ``sensor.neu``), Reihe beider Schlüssel nach ``lab.stand``,
    HA-Attrappe mit beiden Statistiken, je Schlüssel eine angesetzte Wechsel-Zeile (von Hand, wie a2 sie setzen wird)."""
    import backend.services.ha_statistics_service as hss
    from backend.tests import ha_lts_helfer as H

    svc = H.mach_service(thread_sicher=True)
    with svc._engine.begin() as c:
        for eid, reihe in ((ALT, lab.alt), (NEU, lab.neu)):
            mid = H.sensor(svc, eid, "kWh", has_sum=True)
            c.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :s, :s)"),
                      [{"m": mid, "t": e, "s": s} for e, (_z, s) in reihe.items()])
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    a = Anlage(anlagenname="Lab", leistung_kwp=10.0, sensor_mapping={"investitionen": {"2": {"felder": {
        f: {"strategie": "sensor", "sensor_id": NEU} for f in ("ladung_kwh", "ladung_pv_kwh")}}}})
    db.add(a)
    await db.flush()
    db.add(Investition(id=2, anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2025, 1, 1)))
    alt_ende, neu_null = rand or lab.rand(art)
    for key in ("inv:2:ladung_kwh", "inv:2:ladung_pv_kwh"):
        staende = {}
        for e in range(lab.start + STUNDE, lab.ende, STUNDE):
            t = datetime.fromtimestamp(e)
            if (w := lab.stand(t)) is not None:
                staende[t] = w                                  # doppelte Herbststunde: der spätere Stand bleibt
        db.add_all([SensorSnapshot(anlage_id=a.id, sensor_key=key, zeitpunkt=t, wert_kwh=w, quelle="ha_statistics")
                    for t, w in staende.items()])
        db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=lab.ab_ts, ab_ts=lab.ab_ts, vorher=QA, nachher=QN,
                                grund="fortsetzung", herkunft="wechsel", ansatz=art, stand_alt_ende=alt_ende,
                                stand_neu_null=neu_null))
    await db.commit()
    zw.vergiss(db)
    return a, svc


def _slot_tag(lab: Lab) -> tuple[date, int]:
    """Tag und Slot des Naht-Slots im Rückwärts-Raster (Slot h endet um Tag + h)."""
    return lab.ab_ts.date(), lab.ab_ts.hour


def _im_tag(tag: date):
    """Rückwärts-Fenster des Tages: die Zeilen mit Boundary-Index 0…23 (``lts_boundary_index``)."""
    from backend.core.berechnungen.slot_konvention import lts_boundary_index

    return lambda t: 0 <= lts_boundary_index(t, tag) <= 23


def _im_slot(tag: date, h: int):
    from backend.core.berechnungen.slot_konvention import lts_boundary_index

    return lambda t: lts_boundary_index(t, tag) == h


async def _sichten(db, a, lab: Lab, svc) -> dict:
    """Stunde (Naht-Slot), Tag und Monat der Saat in jeder Sicht ohne Kanal: Tagesansicht (Reihe), Bereichs-Leser,
    Tagestabelle aus der Reihe, Tagesabschluss aus HA-Slots, Monat aus HA (Hülle über alle fünf Wege: «Aus HA laden»),
    laufender Monat."""
    from backend.api.routes import aktueller_monat as am
    from backend.api.routes.ha_statistics import get_monatswerte
    from backend.services.kanal import merken
    from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE, get_tagesdetail_kwh, snapshot_tagestabelle
    from backend.services.snapshot.bereichs_leser import lade_tageswerte_je_feld
    from backend.services.snapshot.lts_aggregator import lts_tagestabelle, wechsel_kwargs

    tag, h = _slot_tag(lab)
    zw.vergiss(db)
    merken.invalidiere(a.id)
    a = (await db.execute(select(Anlage).where(Anlage.id == a.id))).scalar_one()
    invs = {"2": await db.get(Investition, 2)}
    reihe_t = await snapshot_tagestabelle(db, a, invs, tag)
    lts_t = await lts_tagestabelle(a, invs, tag, **await wechsel_kwargs(db, a.id))
    tagesdetail = (await get_tagesdetail_kwh(db, a, invs, tag, tageszeile_rueckwaerts=True)).werte.get("emob_ladung_pv_kwh")
    felder = {("wallbox", "ladung_pv_kwh"): TAGESDETAIL_AUSGABE[("wallbox", "ladung_pv_kwh")]}
    bereich = (await lade_tageswerte_je_feld(db, a, invs, tag, tag, felder, rueckwaerts_tage=frozenset({tag}),
                                             kanal_zuerst=False))[tag]["emob_ladung_pv_kwh"]
    monat = (lab.ab_ts.year, lab.ab_ts.month)
    route = await get_monatswerte(a.id, *monat, db)
    ha_laden = next((b.differenz for i in route.investitionen for b in i.felder if b.feld == "ladung_kwh"), None) \
        if hasattr(route, "investitionen") else None
    laufend = await am._collect_ha_statistics_data(a, *monat)
    return {
        "slot_reihe": reihe_t.stunden[h]["wallbox"], "slot_ha": lts_t.stunden[h]["wallbox"],
        "tag_reihe": reihe_t.komponenten_kwh.get("wallbox_2"), "tag_ha": lts_t.komponenten_kwh.get("wallbox_2"),
        "tagesansicht": tagesdetail, "bereichs_leser": bereich,
        "monat_aus_ha_laden": ha_laden,
        "monat_laufend": (laufend.get("inv_2_ladung_kwh") or laufend.get("inv_2_ladung_pv_kwh") or (None,))[0],
    }


def _soll(lab: Lab) -> dict:
    tag, h = _slot_tag(lab)
    m = (lab.ab_ts.year, lab.ab_ts.month)
    st, tg = lab.soll(_im_slot(tag, h)), lab.soll(_im_tag(tag))
    mo = lab.soll(lambda t: (t.year, t.month) == m)
    return {"slot_reihe": st, "slot_ha": st, "tag_reihe": tg, "tag_ha": tg, "tagesansicht": tg, "bereichs_leser": tg,
            "monat_aus_ha_laden": mo, "monat_laufend": mo}


ZEITEN = {
    "lab_18_11_07": datetime(2026, 11, 18, 7),          # Saat «Lab-Wechsel» (Tausch-Stunde 07)
    "herbst_doppelt": datetime(2026, 10, 25, 2),        # Berlin: erste der doppelten Stunden 02:00
    "fruehjahr_fehlt": datetime(2026, 3, 29, 1) + timedelta(hours=1),   # Berlin: 02:00 fehlt ⇒ 03:00
    "mitternacht": datetime(2026, 11, 17, 23),          # Naht-Slot = Slot 0 des Folgetags
    "monatsgrenze": datetime(2026, 10, 31, 23),         # erster Stand des neuen 01.11. 00:00
}


@pytest.mark.parametrize("zeit", list(ZEITEN), ids=list(ZEITEN))
async def test_lab_jede_sicht_nennt_stunde_tag_und_monat_wie_ha(db, monkeypatch, zeit):
    """Ohne Überlappung (``beide``): jede Sicht ohne Kanal nennt für den Naht-Slot, den Tag und den Monat dieselbe Zahl wie
    HAs Regel (Σ beider Statistiken, die erste Zeile des neuen ab 0). Lab-Zahlen am 18.11.: Stunde 1,3 · Tag (Rückwärts-Raster)
    15,8 · Monat ab dem ersten Zuwachs gerechnet."""
    lab = Lab(ZEITEN[zeit])
    a, svc = await _lab_welt(db, monkeypatch, lab)
    ist, soll = await _sichten(db, a, lab, svc), _soll(lab)
    assert ist == pytest.approx(soll), (ist, soll)
    if zeit == "lab_18_11_07" and not ist["slot_reihe"] == pytest.approx(1.3):     # die Lab-Stunde selbst
        pytest.fail(f"Lab-Stunde {ist['slot_reihe']} ≠ 1,3")


SPRENGSAETZE = {
    # Sprengsatz: (Ansatz, Rand oder None, Stellung) ⇒ welche Sicht weicht ab und wie
    "rand_alt_weggelassen": ("beide", (438.0, 0.0), None),       # Stand vor der Tausch-Stunde statt letzter: Reihe 0,7
    "nullpunkt_erste_zeile": ("beide", (438.6, 0.7), None),     # Nullpunkt = erste Zeile statt 0: Reihe 0,6
    "schnitt_statt_beide": ("schnitt", (438.6, 0.0), None),      # HA-Slot ohne den alten und ohne Anker 0
    "ohne_anker_null": ("beide", None, "ohne_anker"),           # HA-Slot nur der alte: 0,6
    "monat_nur_heute": ("beide", None, "ohne_huelle"),          # Monat nur die heutige Entität
    "ohne_ansatz": (None, None, None),                           # wie am HEAD
}


@pytest.mark.parametrize("fall", list(SPRENGSAETZE), ids=list(SPRENGSAETZE))
async def test_lab_sprengsaetze(db, monkeypatch, fall):
    """Jede Abweichung vom Rechenweg macht mindestens eine Sicht falsch (gegen das Soll der Lab-Zeilen am 18.11.)."""
    import backend.services.ha_statistics_service as hss
    import backend.services.zuordnung_wechsel.monat as mo

    art, rand, stellung = SPRENGSAETZE[fall]
    lab = Lab(ZEITEN["lab_18_11_07"])
    if stellung == "ohne_anker":
        echt = hss._slot_werte
        monkeypatch.setattr(hss, "_slot_werte", lambda p, a, n=frozenset(): echt(p, a))
    if stellung == "ohne_huelle":
        async def durch(db_, aid, antworten, monate):
            return list(antworten)
        monkeypatch.setattr(mo, "monatswerte_je_abschnitt", durch)
    a, svc = await _lab_welt(db, monkeypatch, lab, art=art or "beide", rand=rand)
    if art is None:
        await _ohne_ansatz(db)
    ist, soll = await _sichten(db, a, lab, svc), _soll(lab)
    falsch = {k for k in soll if ist[k] is None or abs(ist[k] - soll[k]) > 1e-6}
    assert soll["slot_reihe"] == pytest.approx(1.3) and falsch, (ist, soll)
    erwartet = {                                     # Sicht ⇒ Zahl (oder «falsch»: weicht vom Soll ab)
        "rand_alt_weggelassen": {"slot_reihe": 0.7}, "nullpunkt_erste_zeile": {"slot_reihe": 0.6},
        "schnitt_statt_beide": {"slot_ha": "falsch", "monat_aus_ha_laden": "falsch", "monat_laufend": "falsch"},
        "ohne_anker_null": {"slot_ha": 0.6},
        "monat_nur_heute": {"monat_aus_ha_laden": "falsch", "monat_laufend": "falsch"},
        "ohne_ansatz": {"slot_reihe": 0.0, "slot_ha": "falsch", "monat_aus_ha_laden": "falsch"},
    }[fall]
    for k, w in erwartet.items():
        assert (k in falsch) if w == "falsch" else ist[k] == pytest.approx(w), (k, ist, soll)


async def test_lab_mit_vorgeschichte_schnitt_und_sprengsatz_beide(db, monkeypatch):
    """Überlappung (der neue zählt schon einen Tag vorher 0,2 kWh/h; Schnitt an der Umstellung 10:00 wie heute): ``schnitt`` mit
    den Rand-Ständen beider in der Zeile vor G ⇒ jede Sicht = Soll (alt bis 10:00, neu ab 10:00). Sprengsatz ``beide`` mit
    Nullpunkt 0 bei derselben Saat: der Naht-Slot zählt die ganze Vorgeschichte des neuen mit."""
    t1 = datetime(2026, 11, 18, 7)
    lab = Lab(t1, vorgeschichte=True, schnitt=t1 + timedelta(hours=3))
    a, svc = await _lab_welt(db, monkeypatch, lab, art="schnitt")
    ist, soll = await _sichten(db, a, lab, svc), _soll(lab)
    assert ist == pytest.approx(soll), (ist, soll)
    for w in (await db.execute(select(ZuordnungWechsel))).scalars().all():
        w.ansatz, w.stand_neu_null = "beide", 0.0
    await db.commit()
    ist = await _sichten(db, a, lab, svc)
    assert ist["slot_reihe"] > soll["slot_reihe"] + 5.0                             # die Vorgeschichte des neuen im Naht-Slot
    assert ist["monat_aus_ha_laden"] > soll["monat_aus_ha_laden"] + 5.0              # und im Monat (Anker 0 statt Zeile vor G)
    assert ist["slot_ha"] == pytest.approx(soll["slot_ha"])          # benannt: der alte zählt dort nichts, HA-Slot gleich


def _feld(laufend: dict):
    """Der Wert der Wallbox-Ladung im laufenden Monat (beide Felder hängen am selben Sensor — einer trägt ihn)."""
    return (laufend.get("inv_2_ladung_kwh") or laufend.get("inv_2_ladung_pv_kwh") or (None,))[0]


async def test_monat_nur_mit_dem_alten_sensor_zeigt_dessen_wert(db, monkeypatch):
    """F7 (Übersehen Nr. 2): ein Monat ganz vor der ersten Zeile des neuen — der HA-Leser nennt die heutige Entität dort nicht;
    die Hülle setzt den Wert des alten unter sie. Sprengsatz: ohne angesetzten Wechsel fehlt der Monat."""
    from backend.api.routes import aktueller_monat as am

    lab = Lab(datetime(2026, 11, 3, 7), start=datetime(2026, 9, 29))     # Oktober: nur der alte Sensor
    a, _svc = await _lab_welt(db, monkeypatch, lab)
    okt = lab.soll(lambda t: (t.year, t.month) == (2026, 10))
    assert okt > 0 and _feld(await am._collect_ha_statistics_data(a, 2026, 10)) == pytest.approx(okt)
    await _ohne_ansatz(db)
    assert _feld(await am._collect_ha_statistics_data(a, 2026, 10)) is None


# ═══ P-1 — Korrektur zwischen zwei Sensoren: «Falsch seit» ist eine Wechselstelle ═══════════════════════════════════════

@pytest.mark.parametrize("vorher,erwartet", [
    (QA, True),                                          # A davor, C richtig ⇒ Naht
    ({"art": "ha", "entity_id": "sensor.c"}, False),     # dieselbe Entität ⇒ keine
    ({"art": "mqtt", "mqtt_key": "x"}, False),           # MQTT → HA: nicht in a1 (liest wie am HEAD)
    (None, False),                                       # unbekannt: wie am HEAD
])
def test_p1_falsch_seit_zwischen_zwei_sensoren_ist_eine_naht(vorher, erwartet):
    s, r = datetime(2026, 6, 10, 1), datetime(2026, 6, 14, 19)
    qc = {"art": "ha", "entity_id": "sensor.c"}
    zeilen = [zw.Wechsel("k", r, vorher, qc, None, aufgehoben_durch=2, id=1),
              zw.Wechsel("k", r, vorher, qc, "korrektur", falsch_seit_ts=s, id=2)]
    assert (s in zw.naehte_der_fortsetzung(zeilen)) is erwartet


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_p1_tag_von_falsch_seit_bildet_keine_differenz_zweier_sensoren(db, monkeypatch, sprengsatz):
    """Reihe: A bis «Falsch seit» (10.06. 01:00), danach aus C gefüllt (C = A + 500), Korrektur A → C. Tagesansicht und
    Bereichs-Leser zeigen am 10.06. nur die Teile beider Sensoren (11,5 — die Naht-Stunde ohne Rand-Stände zählt in a1 nicht),
    nie 512,0. Sprengsatz: «Falsch seit» keine Naht (HEAD) ⇒ 512,0."""
    from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE
    from backend.services.snapshot.bereichs_leser import lade_tageswerte_je_feld

    if sprengsatz:
        monkeypatch.setattr(zw, "_falsch_seit_zwischen_zwei_sensoren", lambda w: set())
    a = await s2._anlage(db, ["ladung_pv_kwh"])
    key = "inv:2:ladung_pv_kwh"
    s, r = datetime(2026, 6, 10, 1), datetime(2026, 6, 14, 19)
    t0 = datetime(2026, 6, 1)
    await s2._reihe(db, a.id, key, {t0 + timedelta(hours=h): 100.0 + 0.5 * h + (500.0 if t0 + timedelta(hours=h) >= s else 0.0)
                                    for h in range(20 * 24)})
    qc = {"art": "ha", "entity_id": "sensor.c"}
    db.add(ZuordnungWechsel(id=1, anlage_id=a.id, sensor_key=key, erklaert_ts=r, ab_ts=r, vorher=QA, nachher=qc, grund=None,
                            herkunft="altbestand", aufgehoben_durch=2))
    db.add(ZuordnungWechsel(id=2, anlage_id=a.id, sensor_key=key, erklaert_ts=r, ab_ts=r, vorher=QA, nachher=qc,
                            grund="korrektur", falsch_seit_ts=s, herkunft="nachtrag"))
    await db.flush()
    zw.vergiss(db)
    invs = {"2": await db.get(Investition, 2)}
    tag = date(2026, 6, 10)
    felder = {("wallbox", "ladung_pv_kwh"): TAGESDETAIL_AUSGABE[("wallbox", "ladung_pv_kwh")]}
    from backend.services.snapshot.aggregator import get_tagesdetail_kwh
    td = (await get_tagesdetail_kwh(db, a, invs, tag)).werte.get("emob_ladung_pv_kwh")
    bl = (await lade_tageswerte_je_feld(db, a, invs, tag, tag, felder, kanal_zuerst=False))[tag]["emob_ladung_pv_kwh"]
    if sprengsatz:
        assert (td, bl) == (pytest.approx(512.0), pytest.approx(512.0))
        return
    assert (td, bl) == (pytest.approx(11.5), pytest.approx(11.5))


# ═══ P-2 — Merkmal «Höhe ungeprüft» (Halt H-1 aus U1-K, Option A) ═══════════════════════════════════════════════════════

@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_p2_gefuelltes_nach_leerer_zeit_ohne_pruefbaren_rand_ist_ein_hoehenwechsel(db, monkeypatch, sprengsatz):
    """Fall aus dem U1-K-Bericht (``u1-k/mess.py halt_kein_rand``): A → X am Sprung (ohne Grund), Korrektur «richtig A» über
    [Sprung, Rückgang) im Dialog «bis jetzt» (kein Stand danach); Home Assistant führt A erst ab 12.06. und 1 906,5 höher —
    kein Rand-Stand ist prüfbar. Die Lücke [Sprung, 12.06.) trägt das Merkmal, ihr Rand zum Gefüllten ist ein Höhenwechsel:
    12.06. zeigt 11,5 (das zeigt auch HA, dessen Statistik dort beginnt), nie 1 942,0. Vorschau = Lauf (Merkmal und Satz).
    Sprengsatz: ohne Merkmal (U1-K) ⇒ 1 942,0."""
    from backend.services.snapshot.writer import snapshot_anlage
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.tests import test_daten_checker_zaehler_versatz as v
    from backend.tests.test_sensorwechsel_s4b1_stueck import QA as QV, RUECK, SPRUNG, _tagesansicht
    from backend.tests.test_sensorwechsel_u1k_proben import _ha_mit, _lauf

    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)
    svc = _ha_mit(monkeypatch, plus=1906.5, ab_h=11 * 24)
    v._kanal_tage(monkeypatch, {})
    if sprengsatz:
        async def nie(*_a, **_k):
            return False
        monkeypatch.setattr(kr, "_hoehe_ungeprueft", nie)
    qx = {"art": "ha", "entity_id": "sensor.x"}
    a, wb, key = await v._anlage(db, staende=v._reihe(stunden=v.RUECK_H), spiegel=False)
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=SPRUNG, ab_ts=SPRUNG, vorher=QV, nachher=qx,
                            grund=None, herkunft="altbestand"))
    await db.commit()
    au = kr.Auftrag(anlage_id=a.id, sensor_key=key, falsch_seit=SPRUNG, ab=RUECK, vorher=qx, nachher=QV)
    la = await kr.lage(db, au, ha_svc=svc)
    from backend.core.database import get_session
    erg = await kr.fuehre_aus(db, au, ha_svc=svc, jetzt=RUECK - timedelta(minutes=20))
    await db.commit()
    s = await kr.nach_dem_commit(erg, ha_svc=svc, sitzungen=kr.sitzungen_wie(db, get_session), starten=False)
    await _lauf(db, s)
    a_ = (await db.execute(select(Anlage).where(Anlage.id == a.id))).scalar_one()
    for h in range(v.RUECK_H, v.RUECK_H + 30):                          # der Stundenlauf danach (Stände ab dem Rückgang)
        await snapshot_anlage(db, a_, zeitpunkt=v.T0 + timedelta(hours=h))
    await db.commit()
    sicht = await _tagesansicht(db, a, wb.id)
    if sprengsatz:
        assert sicht[12] == pytest.approx(1942.0)
        return
    zwoelf = datetime(2026, 6, 12)
    assert la.luecke == (SPRUNG, zwoelf) and la.hoehe_ungeprueft and not la.zaehlerluecke
    assert kr.SATZ_LUECKE_HOEHE.format(von="10.06.2026 01:00", bis="12.06.2026 00:00") in kr.saetze(la)
    marke = [(w.falsch_seit_ts, w.ab_ts, w.ansatz) for w in (await db.execute(select(ZuordnungWechsel))).scalars().all()
             if zw.ist_luecken_zeile(w)]
    assert marke == [(SPRUNG, zwoelf, "hoehe_ungeprueft")]               # Vorschau = Lauf; ``nachher`` bleibt leer
    assert sicht[12] == pytest.approx(11.5) and sicht[10] == pytest.approx(0.5) and sicht[11] is None
