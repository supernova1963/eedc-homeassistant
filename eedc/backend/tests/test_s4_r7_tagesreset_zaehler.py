"""HA-Bauform S4-R-6/R-7: ein MQTT-Zähler mit Tagesreset ergibt über die Eigene Summe richtige Kanal-Tage und -Monate.

**Was geprüft wird** (Bauplan S4 §3 R-6/R-7, §4 S4-R-7; vorher nie als Probe gemessen). Drei MQTT-Zähler einer reinen
MQTT-Anlage, Juni 2026 (Stände ab 31.05. 18:00, damit der 01.06. ganz gedeckt ist), je Stunde ein Stand am Stundenende:

* **Tagesreset** (``basis:netzbezug``, ein „heute"-Zähler): 0,4 kWh je Stunde 00–22, Stunde 23 ohne Zuwachs, um 00:00
  zurück auf 0 ⇒ Stände 0,4 … 9,2 je Tag. HAs Regel (``core/berechnungen/ha_summe.py``, Reset unter 90 %): der erste
  Stand des Tages (0,4 < 0,9 × 9,2) beginnt einen neuen Zyklus ab 0 ⇒ Stunde 0 = 0,4, Tag = 9,2, Juni = 30 × 9,2 = 276.
* **Reset mittags** (Wallbox ``ladung_kwh``, Lebensstand ab 500, 0,5 kWh je Stunde): am 15.06. steht der Stand der
  Stunde 12 auf 0,2 statt 504,0+0,5 ⇒ Reset; HA zählt «Zuwachs bis zum alten Stand» (aus EINEM Stand je Stunde: 0)
  und dann ab 0 (0,2) ⇒ 15.06. = 12 × 0,5 + 0,2 + 11 × 0,5 = 11,7; jeder andere Tag 12,0; Juni 29 × 12 + 11,7 = 359,7.
* **Dip 95 %** (Wärmepumpe ``stromverbrauch_kwh``, ab 2000, 0,3 kWh je Stunde): am 15.06. steht die Stunde 12 auf 95 %
  des Stands davor, die Stunde 13 wieder auf dem Lebensstand ⇒ kein Reset (≥ 90 %): die Summe sinkt in Stunde 12 um
  den Dip und steigt in Stunde 13 um ihn wieder ⇒ Tag = 24 × 0,3 = 7,2, Juni = 216.

Beide Rechenwege der Eigenen Summe auf DENSELBEN Ständen: der **Stundenlauf** (``schreiber.schreibe_eigene_summe`` über
``mqtt_energy_snapshots``, Stand je Stunde um H:59; Läufe wie ``kanal_bilanz_gleichheit``: erste Stunde, täglich 21:05,
am Ende) und das **Nachfüllen** (``nachfuellen.nachfuellen_eigene_summe`` über ``sensor_snapshots``, Stand zur vollen
Stunde Z = Ende der Stunde Z − 1) — Zeile für Zeile gleich (0 Abweichung). Dazu der Stundenlauf mit mehreren Ständen in
der Reset-Stunde (12:20 +0,15, 12:40 Reset 0,05, 12:59 0,2): «Zuwachs bis zum alten Stand, dann ab 0» ⇒ Stunde 12 = 0,35.

**Daten-Checker «Zählerstände – Rücksprung»** (S4-R-7): hat der Schlüssel einen Kanal mit Eigener Summe, sagt der Text, was
über die Kanäle geht (Tag, Monat, Jahr wie HA) und was nicht (Live „heute“/„gestern“, Monatsabschluss-Vorschlag,
Geräte-Tageswerte vor dem Kanal — gemessen E-S4-2 Punkt 3); ohne Kanal der Wortlaut von N-341; gemischt beides.

Keine Probe liest die Uhr. Schwesterdateien: test_kanal_eigene_summe.py (die Regel je Periode),
test_kanal_eigene_summe_nachfuellen.py (das Nachfüllen), test_n341_checker_zaehler_ruecksprung.py (der Checker-Text).
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import Kanal, KanalStatistik
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.sensor_snapshot import SensorSnapshot
from backend.tests import pv_achse_matrix as mx

VON = datetime(2026, 5, 31, 18)          # erste Stunde (Stand am Ende dieser Stunde)
BIS = datetime(2026, 7, 1, 0)            # exklusiv
JETZT = datetime(2026, 7, 1, 0, 30)
JUNI = tuple(date(2026, 6, d) for d in range(1, 31))
RESET_TAG = date(2026, 6, 15)
RESET_STUNDE = datetime(2026, 6, 15, 12)

TAGESMENGE = 9.2
SOLL_TAG = {"tagesreset": TAGESMENGE, "reset_mittags": 12.0, "dip": 7.2}
SOLL_RESET_TAG = {"tagesreset": TAGESMENGE, "reset_mittags": 11.7, "dip": 7.2}


def _stunden():
    t = VON
    while t < BIS:
        yield t
        t += timedelta(hours=1)


def stand_tagesreset(t: datetime) -> float:
    """Stand am Ende der Stunde ``t``: 0,4 je Stunde ab 00:00, Stunde 23 ohne Zuwachs (9,2), um 00:00 zurück auf 0."""
    return round(min(0.4 * (t.hour + 1), TAGESMENGE), 4)


def stand_reset_mittags(t: datetime) -> float:
    n = int((t - VON).total_seconds() // 3600)
    if t < RESET_STUNDE:
        return round(500.0 + 0.5 * (n + 1), 4)
    return round(0.2 + 0.5 * int((t - RESET_STUNDE).total_seconds() // 3600), 4)


def stand_einspeisung(t: datetime) -> float:
    """Fortlaufend (kein Reset): 2 kWh je Stunde 10–15 — nur mit ``mit_einspeisung``."""
    n = sum(1 for h in range(int((t - VON).total_seconds() // 3600) + 1) if (VON + timedelta(hours=h)).hour in range(10, 16))
    return round(3000.0 + 2.0 * n, 4)


def stand_dip(t: datetime) -> float:
    n = int((t - VON).total_seconds() // 3600)
    if t == RESET_STUNDE:
        return round(0.95 * (2000.0 + 0.3 * n), 4)        # 95 % des Stands am Ende der Stunde davor
    return round(2000.0 + 0.3 * (n + 1), 4)


@asynccontextmanager
async def datenstand(weg: str, *, mehrere_staende_in_der_resetstunde: bool = False, ohne_stunden=frozenset(),
                     mit_einspeisung: bool = False):
    """Wegwerf-Datei; Anlage ohne HA-Zuordnung, Wallbox, Wärmepumpe. ``weg``: ``stundenlauf`` (Rohstände um H:59,
    ``schreibe_eigene_summe``), ``nachfuellen`` (Stände zur vollen Stunde in ``sensor_snapshots``) oder ``beide`` (beide
    Tabellen gesät, wie der Produktbetrieb sie schreibt; der Stundenlauf legt die Kanäle an). ``ohne_stunden``:
    Stunden ohne Stand (alle Zähler). ``mit_einspeisung``: dazu ein fortlaufender Einspeisezähler (2 kWh je Stunde 10–15),
    damit die Bilanz der Anlage beide Netzrichtungen kennt (Messung «was heute liefert»). Liefert
    ``(sitzungen, anlage_id, {name: sensor_key})``."""
    from backend.services.kanal.nachfuellen import nachfuellen_eigene_summe
    from backend.services.kanal.schreiber import schreibe_eigene_summe

    verz = tempfile.mkdtemp(prefix="eedc-s4-r7-")
    engine, db = await mx._neue_db(f"{verz}/x.db")
    await db.close()
    macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sitzungen():
        async with macher() as s:
            yield s
            await s.commit()

    try:
        async with sitzungen() as s:
            a = Anlage(anlagenname="S4-R-7", leistung_kwp=10.0, sensor_mapping={"basis": {}, "investitionen": {}})
            s.add(a)
            await s.flush()
            wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="Wallbox", anschaffungsdatum=date(2025, 1, 1))
            wp = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2025, 1, 1))
            s.add_all([wb, wp])
            await s.flush()
            aid, keys = a.id, {"tagesreset": "basis:netzbezug", "reset_mittags": f"inv:{wb.id}:ladung_kwh",
                               "dip": f"inv:{wp.id}:stromverbrauch_kwh"}
            mqtt = {"tagesreset": "netzbezug_kwh", "reset_mittags": f"inv/{wb.id}/ladung_kwh",
                    "dip": f"inv/{wp.id}/stromverbrauch_kwh"}
        reihen = {"tagesreset": stand_tagesreset, "reset_mittags": stand_reset_mittags, "dip": stand_dip}
        if mit_einspeisung:
            keys["einspeisung"], mqtt["einspeisung"] = "basis:einspeisung", "einspeisung_kwh"
            reihen["einspeisung"] = stand_einspeisung
        async with sitzungen() as s:
            if weg in ("stundenlauf", "beide"):
                zeilen = [{"anlage_id": aid, "energy_key": mqtt[n], "timestamp": t + timedelta(minutes=59),
                           "value_kwh": fn(t)} for n, fn in reihen.items() for t in _stunden() if t not in ohne_stunden]
                if mehrere_staende_in_der_resetstunde:
                    alt = stand_reset_mittags(RESET_STUNDE - timedelta(hours=1))
                    zeilen += [{"anlage_id": aid, "energy_key": mqtt["reset_mittags"], "timestamp": zp,
                                "value_kwh": w} for zp, w in ((RESET_STUNDE + timedelta(minutes=20), alt + 0.15),
                                                              (RESET_STUNDE + timedelta(minutes=40), 0.05))]
                await s.execute(insert(MqttEnergySnapshot), zeilen)
            if weg in ("nachfuellen", "beide"):
                await s.execute(insert(SensorSnapshot), [
                    {"anlage_id": aid, "sensor_key": keys[n], "zeitpunkt": t + timedelta(hours=1), "wert_kwh": fn(t),
                     "quelle": "mqtt_inbound"} for n, fn in reihen.items() for t in _stunden() if t not in ohne_stunden])
        if weg in ("stundenlauf", "beide"):
            laeufe = [VON + timedelta(hours=1, minutes=5)]
            tag = VON.date()
            while tag < BIS.date():
                laeufe.append(datetime.combine(tag, datetime.min.time()) + timedelta(hours=21, minutes=5))
                tag += timedelta(days=1)
            laeufe.append(BIS + timedelta(minutes=5))
            for zp in laeufe:
                async with sitzungen() as s:
                    anlage = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
                    await schreibe_eigene_summe(s, anlage, zp)
        else:
            erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
            assert erg.fehler == 0 and erg.kanaele == len(keys), erg
        yield sitzungen, aid, keys
    finally:
        await engine.dispose()
        shutil.rmtree(verz, ignore_errors=True)


async def kanal_zeilen(sitzungen, aid: int, key: str) -> list[tuple[int, float, float]]:
    async with sitzungen() as s:
        k = (await s.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == key))).scalar_one()
        return [(z.start_ts, z.sum, z.state) for z in (await s.execute(
            select(KanalStatistik).where(KanalStatistik.kanal_id == k.id).order_by(KanalStatistik.start_ts))).scalars()]


async def tage_und_monat(sitzungen, aid: int, keys: dict[str, str]) -> dict[str, dict]:
    """Kanal-Tag je Juni-Tag (Kalendertag, ``fenster.tagesfenster``) und Kanal-Monat Juni (``monatsfenster``) über die
    Lese-Schicht (``lesen.reihe_stapel``/``zeitraum_stapel``) — je Zähler ``{"tage": {datum: Δ|None}, "monat": Δ|None}``."""
    from backend.services.kanal.fenster import monatsfenster, tagesfenster
    from backend.services.kanal.lesen import kanaele_laden, reihe_stapel, zeitraum_stapel

    jetzt = int(JETZT.timestamp())
    async with sitzungen() as s:
        kanaele = await kanaele_laden(s, aid, list(keys.values()))
        grenzen = [tagesfenster(d)[0] for d in JUNI] + [tagesfenster(JUNI[-1])[1]]
        tage = await reihe_stapel(s, list(kanaele.values()), grenzen, jetzt=jetzt)
        monat = await zeitraum_stapel(s, list(kanaele.values()), *monatsfenster(2026, 6), jetzt=jetzt)
    out = {}
    for name, key in keys.items():
        out[name] = {"tage": {d: (round(z.delta, 4) if z.voll else None) for d, z in zip(JUNI, tage[key])},
                     "monat": round(monat[key].delta, 4) if monat[key].voll else None}
    return out


# ── Proben ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("weg", ["stundenlauf", "nachfuellen"])
async def test_kanal_tag_ist_die_tagesmenge_und_der_monat_die_summe_der_tage(weg):
    """Je Weg: Kanal-Tag = 9,2 (Tagesreset), 12,0/11,7 (Reset mittags), 7,2 (Dip); Monat = Σ Tage."""
    async with datenstand(weg) as (sitzungen, aid, keys):
        werte = await tage_und_monat(sitzungen, aid, keys)
    for name, w in werte.items():
        for d, delta in w["tage"].items():
            soll = SOLL_RESET_TAG[name] if d == RESET_TAG else SOLL_TAG[name]
            assert delta == pytest.approx(soll, abs=1e-6), (weg, name, d)
        assert w["monat"] == pytest.approx(sum(w["tage"].values()), abs=1e-6), (weg, name)
    assert werte["tagesreset"]["monat"] == pytest.approx(30 * TAGESMENGE, abs=1e-6)
    assert werte["reset_mittags"]["monat"] == pytest.approx(29 * 12.0 + 11.7, abs=1e-6)
    assert werte["dip"]["monat"] == pytest.approx(30 * 7.2, abs=1e-6)


async def test_stundenlauf_und_nachfuellen_rechnen_dieselben_zeilen():
    """Dieselben Stände, zwei Wege durch ``_eigene_summe_zeilen``: jede Zeile ``(start_ts, sum, state)`` gleich."""
    zeilen = {}
    for weg in ("stundenlauf", "nachfuellen"):
        async with datenstand(weg) as (sitzungen, aid, keys):
            zeilen[weg] = {name: await kanal_zeilen(sitzungen, aid, key) for name, key in keys.items()}
    for name in SOLL_TAG:
        a, b = zeilen["stundenlauf"][name], zeilen["nachfuellen"][name]
        assert len(a) == len(b) == len(list(_stunden())), name
        abweichung = [(x, y) for x, y in zip(a, b)
                      if x[0] != y[0] or abs(x[1] - y[1]) > 1e-9 or abs(x[2] - y[2]) > 1e-9]
        assert abweichung == [], (name, abweichung[:3])


async def test_reset_stunde_nach_has_regel_und_dip_ohne_reset():
    """Stundenwerte der Reset-Stunde und des Dips nach HAs Regel (von Hand): Tagesreset-Stunde 0 = 0,4 (neuer Zyklus ab
    0); Reset mittags = 0,2; Dip: Stunde 12 = −5 % des Stands, Stunde 13 = 0,3 + Dip zurück."""
    async with datenstand("stundenlauf") as (sitzungen, aid, keys):
        z = {name: {ts: s for ts, s, _st in await kanal_zeilen(sitzungen, aid, key)} for name, key in keys.items()}

    def stunde(name: str, t: datetime) -> float:
        ts = int(t.timestamp())
        return round(z[name][ts] - z[name][ts - 3600], 6)

    assert stunde("tagesreset", datetime(2026, 6, 15, 0)) == pytest.approx(0.4)
    assert stunde("tagesreset", datetime(2026, 6, 14, 23)) == pytest.approx(0.0)
    assert stunde("reset_mittags", RESET_STUNDE) == pytest.approx(0.2)
    vor_dip = stand_dip(RESET_STUNDE - timedelta(hours=1))
    assert stunde("dip", RESET_STUNDE) == pytest.approx(-0.05 * vor_dip, abs=1e-4)
    assert stunde("dip", RESET_STUNDE + timedelta(hours=1)) == pytest.approx(0.6 + 0.05 * vor_dip, abs=1e-4)


async def test_mehrere_staende_in_der_resetstunde_zuwachs_bis_zum_alten_stand_dann_ab_null():
    """Stundenlauf, Reset-Stunde mit drei Ständen: 12:20 alter Stand + 0,15, 12:40 Reset auf 0,05, 12:59 0,2 ⇒ Stunde 12
    = 0,15 (bis zum alten Stand) + 0,2 (ab 0) = 0,35; der 15.06. = 6,0 + 0,35 + 5,5 = 11,85."""
    async with datenstand("stundenlauf", mehrere_staende_in_der_resetstunde=True) as (sitzungen, aid, keys):
        zeilen = {ts: s for ts, s, _st in await kanal_zeilen(sitzungen, aid, keys["reset_mittags"])}
        werte = await tage_und_monat(sitzungen, aid, {"reset_mittags": keys["reset_mittags"]})
    ts = int(RESET_STUNDE.timestamp())
    assert zeilen[ts] - zeilen[ts - 3600] == pytest.approx(0.35, abs=1e-9)
    assert werte["reset_mittags"]["tage"][RESET_TAG] == pytest.approx(11.85, abs=1e-6)


@pytest.mark.parametrize("weg", ["stundenlauf", "nachfuellen"])
async def test_fehlt_der_erste_stand_des_tages_bleibt_der_reset_erkannt(weg):
    """Halt-Bedingung des Auftrags (Punkt 3): am 15.06. fehlen die Stände 00–05 — der erste Stand des Tages (06:59: 2,8)
    liegt unter 90 % des letzten (9,2) ⇒ Reset, die Stunde 6 trägt 2,8 ⇒ der Tag bleibt 9,2."""
    luecke = frozenset(datetime(2026, 6, 15, h) for h in range(6))
    async with datenstand(weg, ohne_stunden=luecke) as (sitzungen, aid, keys):
        werte = await tage_und_monat(sitzungen, aid, {"tagesreset": keys["tagesreset"]})
    assert werte["tagesreset"]["tage"][RESET_TAG] == pytest.approx(TAGESMENGE, abs=1e-6)
    assert werte["tagesreset"]["monat"] == pytest.approx(30 * TAGESMENGE, abs=1e-6)


# ── Daten-Checker «Zählerstände – Rücksprung» (S4-R-7) ─────────────────────

CHECK_UHR = datetime(2026, 6, 20, 12)


async def _rueckspruenge(sitzungen, aid: int, *, ohne_eigene_summe: tuple[str, ...] = ()):
    """Der Befund von ``_check_zaehler_ruecksprung``; ``ohne_eigene_summe``: diesen Schlüsseln die Mitschrift-Quelle nehmen
    (der Kanal hat dann keine Eigene Summe mehr — der Zustand eines Zählers ohne Kanal, aus Sicht des Checkers)."""
    from sqlalchemy import text

    from backend.services.daten_checker import DatenChecker

    async with sitzungen() as s:
        for key in ohne_eigene_summe:
            await s.execute(text("DELETE FROM kanal_quelle WHERE familie = 'mitschrift' AND kanal_id = (SELECT id FROM "
                                 "kanal WHERE anlage_id = :a AND key = :k)"), {"a": aid, "k": key})
    async with sitzungen() as s:
        anlage = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        return await DatenChecker(s)._check_zaehler_ruecksprung(anlage, jetzt=CHECK_UHR)


async def test_checker_mit_eigener_summe_sagt_was_ueber_die_kanaele_geht_und_was_nicht():
    async with datenstand("beide") as (sitzungen, aid, keys):
        (b,) = await _rueckspruenge(sitzungen, aid)
    assert b.kategorie == "zaehler_ruecksprung" and b.schwere.value == "warning"
    assert b.meldung == ("3 Zähler-Feld(er) werden zwischendurch zurückgesetzt — Tag und Monat rechnet eedc über die "
                         "Kanäle, Live und Monatsabschluss nicht")
    folge, loesung = b.details.split("Folge: ")[1].split("Lösung: ")
    assert "Kanal mit eigener Summe" in folge and "Tag, Monat und Jahr rechnen darüber wie Home Assistant" in folge
    assert "Live „heute“ und „gestern“" in folge and "Vorschlag im Monatsabschluss gibt es für diese Felder nicht" in folge
    assert "keine Tages- oder Monatsmenge" not in b.details
    # Die Empfehlung an der Quelle bleibt der erste Satz der Lösung.
    assert loesung.startswith("Schicke den fortlaufenden Stand statt des Tageswerts.") and "„nie“" in loesung


async def test_checker_ohne_eigene_summe_wortlaut_wie_bisher():
    async with datenstand("beide") as (sitzungen, aid, keys):
        (b,) = await _rueckspruenge(sitzungen, aid, ohne_eigene_summe=tuple(keys.values()))
    assert b.meldung == "3 Zähler-Feld(er) werden zwischendurch zurückgesetzt — daraus entsteht keine Monatsmenge"
    assert ("Folge: eedc kann für diese Felder keine Tages- oder Monatsmenge bilden, denn die Differenz zweier Stände aus "
            "verschiedenen Zählerläufen ist keine Menge. Sie bleiben im Monatsabschluss ohne Vorschlag. Lösung: Schicke "
            "den fortlaufenden Stand statt des Tageswerts.") in b.details
    assert "Kanal" not in b.details


async def test_checker_gemischt_nennt_beide_gruppen():
    async with datenstand("beide") as (sitzungen, aid, keys):
        (b,) = await _rueckspruenge(sitzungen, aid, ohne_eigene_summe=(keys["reset_mittags"],))
    assert b.meldung == ("3 Zähler-Feld(er) werden zwischendurch zurückgesetzt — 2 davon rechnet eedc über die Kanäle, "
                         "für 1 entsteht keine Monatsmenge")
    assert "Für Wallbox – Ladung gesamt gilt: eedc kann für diese Felder keine Tages- oder Monatsmenge bilden" in b.details
    assert "eedc führt für Netzbezug, WP – Stromverbrauch einen Kanal mit eigener Summe" in b.details
