"""F-58 — ein Zählerstand ist der **Stand**, nicht HAs Verbrauchssumme.

**Der Fehler, den diese Datei bewacht** (dietmar1968, Forum T89667 #185,
21.08.2026): Sein Wasserzähler meldete in Home Assistant **47,360 m³**, eedc
zeigte **90**. Der stündliche Snapshot-Job holte den Zählerstand über
`get_value_at`, und das nimmt bei einem Sensor mit `has_sum` **ausschließlich
`sum`** — HAs reset-bereinigte Verbrauchssumme seit Aufzeichnungsbeginn. Für
einen Energiezähler ist das richtig und ausdrücklich so entschieden (v3.25.18,
Issue #184); für eine **Bestandsgröße** ist es die falsche Größe.

⚠ **Der zweite Zweig war genauso falsch und fiel niemandem auf, weil er
schweigt:** Ohne `has_sum` verlangt `_value_at_wert` eine Einheit aus
`_ENERGY_UNIT_TO_KWH`. „m³" steht dort nicht ⇒ ein Wasserzähler bekam **gar
keinen** Snapshot. Die Probe `test_4_*` hält genau diesen Zweig.

**Warum die Bestandsproben ihn nicht gefangen haben** — die neun Proben in
`test_377_zaehlerstaende.py` prüfen, was eedc mit der Zahl *tut* (kein
Energiefeld, keine Community, keine Rundung); **keine** prüft, woher sie kommt.
Deshalb misst diese Datei den **Schreibpfad** und nicht das Ergebnis einer
selbst gesetzten Fixture ([[feedback_probe_unerreichbarer_zustand]]).

Die Zeilen unten tragen `sum != state` — ohne diesen Unterschied wäre jede
Behauptung über die Spaltenwahl unbeweisbar.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from backend.core.field_definitions import STAND_FELDER, ist_stand_feld
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.ha_statistics_service import HAStatisticsService
from backend.services.snapshot.keys import ist_stand_sensor_key
from backend.services.zaehlerstaende import lade_zaehlerstaende, sensor_key_fuer


# ---------------------------------------------------------------- Testdoubles

#: Ein Zeitpunkt, für den eine Stundenzeile existiert.
ZEITPUNKT = datetime(2026, 8, 21, 12, 0, 0)

#: Die beiden Spalten laufen **absichtlich** auseinander — 90 gegen 47,36 ist
#: genau der gemeldete Abstand. Eine Zeile mit `sum == state` könnte die Frage
#: „welche Spalte?" gar nicht beantworten.
SUM_WERT = 90.0
STATE_WERT = 47.36


def _service(unit: str, has_sum: bool) -> HAStatisticsService:
    """Statistikdienst über einen In-Memory-Recorder mit **einer** Zeile.

    Die Zeile sitzt bei `ZEITPUNKT - 1h`: HA führt in `start_ts` den Beginn der
    Periode, der Wert gilt an deren **Ende** (so liest `get_value_at`).

    ⚠ `StaticPool` ist nicht Kosmetik: Der Snapshot-Job ruft den synchronen
    Leser über `asyncio.to_thread` auf, und eine In-Memory-SQLite ist **pro
    Verbindung** eine eigene Datenbank. Ohne die eine geteilte Verbindung sähe
    der Job eine leere Statistik — der Prüfer würde messen, dass nichts da ist.
    """
    svc = HAStatisticsService()
    svc._initialized = True
    svc._engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with svc._engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE statistics_meta (id INTEGER PRIMARY KEY, statistic_id TEXT, "
            "unit_of_measurement TEXT, has_sum INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE statistics (metadata_id INTEGER, start_ts REAL, sum REAL, "
            "state REAL, mean REAL, min REAL, max REAL)"
        ))
        conn.execute(
            text("INSERT INTO statistics_meta VALUES (1, 'sensor.wasser', :u, :h)"),
            {"u": unit, "h": 1 if has_sum else 0},
        )
        conn.execute(
            text("INSERT INTO statistics VALUES (1, :ts, :s, :st, NULL, NULL, NULL)"),
            {
                "ts": (ZEITPUNKT.timestamp() - 3600),
                "s": SUM_WERT,
                "st": STATE_WERT,
            },
        )
        conn.commit()
    return svc


# ------------------------------------------------------- 1. Der Kern: `state`


def test_1_ein_stand_kommt_aus_state_nicht_aus_sum():
    """**Der gemeldete Fall.** `m³`, `has_sum` — heute lieferte das 90."""
    svc = _service("m³", has_sum=True)
    wert = svc.get_value_at("sensor.wasser", ZEITPUNKT, toleranz_minuten=10, als_stand=True)
    assert wert == pytest.approx(STATE_WERT), (
        f"Der Zählerstand muss der Sensor-`state` sein ({STATE_WERT}), "
        f"nicht HAs Verbrauchssumme ({SUM_WERT}) — geliefert wurde {wert}."
    )


def test_2_gegenprobe_eine_menge_kommt_weiter_aus_sum():
    """Die andere Hälfte derselben Regel — sonst wäre der Fix eine Regression.

    Ein Tagesreset-Zähler hat in `state` den **Tageswert**; nur `sum` ist die
    Lebensdauer-Zahl. Wer F-58 „großzügig" auf alles anwendet, bricht #184.
    """
    svc = _service("kWh", has_sum=True)
    wert = svc.get_value_at("sensor.wasser", ZEITPUNKT, toleranz_minuten=10)
    assert wert == pytest.approx(SUM_WERT), (
        f"Ohne `als_stand` bleibt `sum` die Quelle ({SUM_WERT}) — geliefert: {wert}."
    )


def test_3_ein_stand_wird_nicht_umgerechnet():
    """Modell §3: eedc rechnet Zählerstände **nie** um.

    Der Energie-Zweig skaliert `Wh`/`MWh` nach kWh. Ein Gaszähler, der seinen
    Stand in „MWh" meldet, soll seinen Stand zeigen — nicht das Tausendfache.
    """
    svc = _service("MWh", has_sum=True)
    wert = svc.get_value_at("sensor.wasser", ZEITPUNKT, toleranz_minuten=10, als_stand=True)
    assert wert == pytest.approx(STATE_WERT), (
        f"Ein Stand darf nicht mit dem Einheitenfaktor multipliziert werden — {wert}."
    )


def test_4_ohne_has_sum_kommt_der_stand_trotzdem_an():
    """Der stille Zweig: `has_sum=0` **und** eine Einheit ohne Energie-Klasse.

    Vor F-58 verlangte `_value_at_wert` hier eine kWh-Einheit und lieferte
    sonst `None` — der Wasserzähler bekam **gar keinen** Snapshot, ohne eine
    einzige Meldung.
    """
    svc = _service("m³", has_sum=False)
    wert = svc.get_value_at("sensor.wasser", ZEITPUNKT, toleranz_minuten=10, als_stand=True)
    assert wert == pytest.approx(STATE_WERT), (
        f"Auch ohne `has_sum` ist der Stand da — geliefert wurde {wert}."
    )


# --------------------------------------------- 5.–6. Wer entscheidet die Wahl


def test_5_die_entscheidung_haengt_am_feld_nicht_am_aufrufer():
    """Der Marker steht in der Registry; der Schreibpfad fragt ihn nur.

    Die Untergrenze gehört dazu: Wäre `STAND_FELDER` leer, liefe jede
    Behauptung darüber ins Leere und die Datei bliebe trotzdem grün.
    """
    assert len(STAND_FELDER) >= 1, "Kein einziges Stand-Feld — der Prüfer misst nichts."
    assert ist_stand_feld("zaehlerstand") is True
    assert ist_stand_sensor_key("inv:7:zaehlerstand") is True
    # Mit Innengeräte-Suffix, wie jede andere Namens-Whitelist.
    assert ist_stand_feld("zaehlerstand-3") is True


def test_6_gegenprobe_energiefelder_sind_keine_staende():
    """Sonst hätte der Fix die ganze Energiebilanz auf `state` umgestellt."""
    for feld in ("pv_erzeugung_kwh", "ladung_kwh", "verbrauch_sonstig_kwh"):
        assert ist_stand_feld(feld) is False, f"{feld} ist eine Menge, kein Stand."
    for key in ("basis:netzbezug", "basis:einspeisung", "inv:4:pv_erzeugung_kwh"):
        assert ist_stand_sensor_key(key) is False, key
    # ⛔ Bewusst NICHT umgestellt (Begründung in `stand_felder`): ihr Snapshot
    # wird nur differenziert, der Lebensdauer-Stand kommt aus einem eigenen
    # Leser. Eine Umstellung ergäbe an einem Tag einen Sprung in der Größe des
    # Gerätezählers, und positive Counter-Deltas werden nicht gekappt.
    assert ist_stand_feld("wp_starts_anzahl") is False
    assert ist_stand_feld("wp_betriebsstunden") is False


# ------------------------------------------- 7.–8. Der Bruch in der Reihe


async def _zaehler_mit_staenden(db, werte: list[tuple[date, float]]):
    a = Anlage(anlagenname="Testanlage", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    inv = Investition(
        anlage_id=a.id, typ="sonstiges", bezeichnung="Wasserzähler",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={"kategorie": "zaehler", "zaehler_art": "wasser", "zaehler_einheit": "m³"},
    )
    db.add(inv)
    await db.flush()
    for tag, wert in werte:
        db.add(SensorSnapshot(
            anlage_id=a.id, sensor_key=sensor_key_fuer(inv.id),
            zeitpunkt=datetime.combine(tag, datetime.min.time()),
            wert_kwh=wert, quelle="ha_statistics",
        ))
    await db.commit()
    return a


@pytest.mark.asyncio
async def test_7_ein_fallender_stand_ist_keine_negative_menge(db):
    """Der F-58-Übergang erzeugt genau einen Rücksprung: 90 → 47,36.

    Ohne diese Probe stünde bei dietmar im August **−42,6 m³** als
    „Verbrauch" — eine Zahl, die aussieht wie eine Messung.
    """
    a = await _zaehler_mit_staenden(db, [
        (date(2026, 8, 1), SUM_WERT),      # noch die alte Skala (HAs `sum`)
        (date(2026, 8, 21), STATE_WERT),   # ab jetzt der Stand
    ])
    fenster = await lade_zaehlerstaende(
        db, a.id, datetime(2026, 8, 1), datetime(2026, 8, 31, 23, 59, 59),
    )
    assert len(fenster) == 1
    f = fenster[0]
    assert f.differenz is None, (
        f"Ein gefallener Stand ist keine Menge — differenz={f.differenz}."
    )
    assert f.reihe_gebrochen is True, "Der Bruch muss ausgewiesen werden (P4)."
    # Die Stände selbst bleiben sichtbar: der Anwender soll sehen, was passiert
    # ist, statt zwei leere Zellen vorzufinden.
    assert f.stand_anfang == pytest.approx(SUM_WERT)
    assert f.stand_ende == pytest.approx(STATE_WERT)


@pytest.mark.asyncio
async def test_8_gegenprobe_die_normale_reihe_rechnet_weiter(db):
    """Sonst hätte der Wächter jede Differenz abgeschaltet."""
    a = await _zaehler_mit_staenden(db, [
        (date(2026, 8, 1), 47.0),
        (date(2026, 8, 21), 47.36),
    ])
    fenster = await lade_zaehlerstaende(
        db, a.id, datetime(2026, 8, 1), datetime(2026, 8, 31, 23, 59, 59),
    )
    f = fenster[0]
    assert f.differenz == pytest.approx(0.36)
    assert f.reihe_gebrochen is False


# ------------------------------------------- 9.–10. Der Schreibpfad selbst
#
# ⚑ **Die Proben 1–8 hätten den Fehler NICHT gefangen.** Sie prüfen den Leser
# und das Ergebnis; der Defekt saß in der **Wahl** — `snapshot_anlage` rief
# `get_value_at` ohne die Frage, was für eine Größe da geholt wird. Ein Prüfer,
# der nur den Leser kennt, bliebe grün, während der Job weiter die Summe
# schreibt.


async def _anlage_mit_gemapptem_zaehler(db):
    a = Anlage(anlagenname="Testanlage", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    inv = Investition(
        anlage_id=a.id, typ="sonstiges", bezeichnung="Wasserzähler",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={"kategorie": "zaehler", "zaehler_art": "wasser", "zaehler_einheit": "m³"},
    )
    db.add(inv)
    await db.flush()
    a.sensor_mapping = {
        "investitionen": {
            str(inv.id): {
                "felder": {
                    "zaehlerstand": {"strategie": "sensor", "sensor_id": "sensor.wasser"},
                }
            }
        }
    }
    await db.commit()
    return a, inv


@pytest.mark.asyncio
async def test_9_der_snapshot_job_schreibt_den_stand(db, monkeypatch):
    """**Der Fehler, wie er wirklich passiert ist** — Ende zu Ende.

    Kein gesetzter Snapshot, sondern der echte Job gegen einen Recorder, in dem
    `sum` und `state` auseinanderlaufen. In der Tabelle muss der **Stand**
    landen.
    """
    from backend.services.snapshot import writer as writer_mod

    a, inv = await _anlage_mit_gemapptem_zaehler(db)
    svc = _service("m³", has_sum=True)
    monkeypatch.setattr(writer_mod, "get_ha_statistics_service", lambda: svc)

    geschrieben = await writer_mod.snapshot_anlage(db, a, zeitpunkt=ZEITPUNKT)
    await db.commit()

    assert geschrieben >= 1, "Der Job hat gar nichts geschrieben — der Prüfer misst nichts."
    from sqlalchemy import select
    wert = (await db.execute(
        select(SensorSnapshot.wert_kwh).where(
            SensorSnapshot.anlage_id == a.id,
            SensorSnapshot.sensor_key == sensor_key_fuer(inv.id),
            SensorSnapshot.zeitpunkt == ZEITPUNKT,
        )
    )).scalar_one_or_none()
    assert wert == pytest.approx(STATE_WERT), (
        f"Der Snapshot trägt {wert} — erwartet ist der Stand {STATE_WERT}, "
        f"nicht HAs Verbrauchssumme {SUM_WERT}."
    )


@pytest.mark.asyncio
async def test_10_gegenprobe_ein_energiezaehler_bekommt_weiter_die_summe(db, monkeypatch):
    """Derselbe Job, dasselbe Recorder-Doppel — nur ein anderes Feld.

    Ohne diese Zeile wäre der Fix auch dann grün, wenn er **jeden** Zähler auf
    `state` umgestellt hätte.
    """
    from backend.services.snapshot import writer as writer_mod

    a = Anlage(anlagenname="Testanlage", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    inv = Investition(
        anlage_id=a.id, typ="pv-modul", bezeichnung="Südstring",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True, leistung_kwp=5.0,
    )
    db.add(inv)
    await db.flush()
    a.sensor_mapping = {
        "investitionen": {
            str(inv.id): {
                "felder": {
                    "pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.wasser"},
                }
            }
        }
    }
    await db.commit()

    svc = _service("kWh", has_sum=True)
    monkeypatch.setattr(writer_mod, "get_ha_statistics_service", lambda: svc)
    await writer_mod.snapshot_anlage(db, a, zeitpunkt=ZEITPUNKT)
    await db.commit()

    from sqlalchemy import select
    wert = (await db.execute(
        select(SensorSnapshot.wert_kwh).where(
            SensorSnapshot.anlage_id == a.id,
            SensorSnapshot.sensor_key == f"inv:{inv.id}:pv_erzeugung_kwh",
            SensorSnapshot.zeitpunkt == ZEITPUNKT,
        )
    )).scalar_one_or_none()
    assert wert == pytest.approx(SUM_WERT), (
        f"Ein kWh-Zähler muss weiter HAs `sum` tragen ({SUM_WERT}) — geliefert: {wert}."
    )
