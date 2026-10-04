"""N-624 — im laufenden Monat entfällt die Teilzeitraum-Marke nur für den Anlagenzähler.

**Der Fund.** ``teilzeitraum_felder`` markierte JEDES Feld, das die Tagesebene kannte, als
„misst nur einen Teil des Monats" — auch dort, wo die HA-Statistik das Feld gewonnen hatte.
Ein markierter Top-Level-Wert sperrt die Aggregation der Komponenten-Werte nicht und wird
vom ersten aggregierten Beitrag ersetzt (#361). Im Betrieb gibt es im laufenden Monat immer
Tageszeilen: Cockpit → Monat zeigte für „Anlagenzähler + BKW-Zähler, Strings ohne" PV 9 statt
63 und Eigenverbrauch 0. Die Probe von N-587 lief ohne Tageszeilen und sah es nicht.

**Die Regel** (Bauplan PV-Achse T3, Fable-Gegenentwurf): ``gewinner_je_feld`` ist die eine
Präzedenz; Merge und Marke entstehen daraus. Ein Anlagenwert sperrt, wenn er den Monat bis
jetzt misst — Gewinner HA-Statistik oder MQTT ab Monatsbeginn. Ersetzbar bleiben die
Tagesebene, der MQTT-Rückfall, der Connector ohne Abdeckung; im laufenden Monat für Felder
der Tagesebene außerdem der gespeicherte Wert und der Connector mit Abdeckung — wie bisher.

**Datenstand wie im Betrieb:** Matrix-Bausteine (HA-Statistik im Recorder-Schema, Tage über
``aggregate_day``), dazu Speicher, Wärmepumpe und Wallbox mit eigenen HA-Zählern; gespeicherte
Zeilen über ``create_monatsdaten``, der Connector über ``connector_config`` (der echte
Sammelweg). Nur der MQTT-Sammler wird ersetzt: sein Eingang ist der Cache des Brokers.
Geprüft wird die VOLLE Antwort von Cockpit → Monat — außerhalb der PV-Folgen (PV, BKW,
Eigenverbrauch, Autarkie und was daraus folgt) ist jede Zahl hier festgehalten.

Juli 2026 läuft, drei Tage vorbei (``JETZT`` der Matrix): je Tag Süd 12 · West 6 · Balkon 3
(Σ 21), Einspeisung 6, Netzbezug 7,2; Akku Ladung 3 / Entladung 2 je Tag, WP Strom 7,2 /
Wärme 21,6 je Tag, Wallbox 3 je Tag.
"""

from __future__ import annotations

import shutil
import tempfile
import time as _zeit
from datetime import datetime, timedelta
from typing import Optional

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm.attributes import flag_modified

from backend.core.berechnungen.datenquellen import (
    gewinner_je_feld,
    merge_datenquellen,
    teilzeitraum_felder,
)
from backend.models import Anlage, Investition
from backend.tests import ha_lts_helfer
from backend.tests import pv_achse_matrix as mx

#: Weitere Geräte mit eigenen HA-Zählern: ``name: (typ, {feld: rate_fn})``.
EXTRA = {
    "Akku": ("speicher", {"ladung_kwh": lambda t: 0.5 if t.hour in mx.PROD_STUNDEN else 0.0,
                          "entladung_kwh": lambda t: 0.4 if 18 <= t.hour <= 22 else 0.0}),
    "WP": ("waermepumpe", {"stromverbrauch_kwh": lambda t: 0.3, "waerme_kwh": lambda t: 0.9}),
    "Wallbox": ("wallbox", {"ladung_kwh": lambda t: 1.0 if 11 <= t.hour <= 13 else 0.0}),
}


async def _seed(db, form: mx.Form):
    aid, ids = await mx.seed_anlage(db, form)
    svc = mx.seed_ha(form)
    a = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    m = dict(a.sensor_mapping)
    inv_map = dict(m.get("investitionen") or {})
    for name, (typ, felder) in EXTRA.items():
        kw = dict(anlage_id=aid, typ=typ, bezeichnung=name, anschaffungsdatum=mx.D0, anschaffungskosten_gesamt=1000.0)
        if typ == "speicher":
            kw["parameter"] = {"kapazitaet_kwh": 10.0}
        inv = Investition(**kw)
        db.add(inv)
        await db.flush()
        ids[name] = inv.id
        fm = {}
        for feld, fn in felder.items():
            sid = f"sensor.{name.lower()}_{feld}"
            fm[feld] = {"strategie": "sensor", "sensor_id": sid}
            mid = ha_lts_helfer.sensor(svc, sid, "kWh", has_sum=True)
            stand, zeilen, t = 500.0, [], mx.REIHE_VON
            while t < mx.REIHE_BIS:
                stand += fn(t)
                zeilen.append({"m": mid, "t": _zeit.mktime(t.timetuple()), "w": round(stand, 4)})
                t += timedelta(hours=1)
            with svc._engine.begin() as conn:
                conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :w, :w)"),
                             zeilen)
        inv_map[str(inv.id)] = {"felder": fm}
    m["investitionen"] = inv_map
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    return aid, ids, svc


def _putz(x):
    """Laufzeit-Zeitstempel der Quellen sind kein Wert."""
    if isinstance(x, dict):
        return {k: _putz(v) for k, v in x.items() if k != "zeitpunkt"}
    if isinstance(x, list):
        return [_putz(v) for v in x]
    return x


async def antwort(form_id: str, *, gespeichert=None, connector=None, mqtt=None, monkeypatch=None,
                  spaet_zugeordnet: bool = False, statistik_ab: Optional[datetime] = None) -> dict:
    """Die volle Antwort von ``get_aktueller_monat`` für den laufenden Juli."""
    import backend.api.routes.aktueller_monat as am

    form = mx.FORMEN[form_id]
    verz = tempfile.mkdtemp(prefix="eedc-n624-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            aid, ids, svc = await _seed(db, form)
            a = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
            if statistik_ab is not None:     # der HA-Sensor des Anlagenzählers entsteht erst im Monat
                with svc._engine.begin() as conn:
                    mid = conn.execute(text(
                        "SELECT id FROM statistics_meta WHERE statistic_id='sensor.pv_gesamt'")).scalar()
                    conn.execute(text("DELETE FROM statistics WHERE metadata_id=:m AND start_ts < :t"),
                                 {"m": mid, "t": _zeit.mktime(statistik_ab.timetuple())})
            if connector is not None:
                a.connector_config = connector
                flag_modified(a, "connector_config")
                await db.commit()
            with mx._umgebung(svc):
                if spaet_zugeordnet:          # Anlagenzähler erst am 03.07. zugeordnet
                    voll = dict(a.sensor_mapping)
                    a.sensor_mapping = {**voll, "basis": {k: v for k, v in voll["basis"].items() if k != "pv_gesamt"}}
                    flag_modified(a, "sensor_mapping")
                    await db.commit()
                    await mx.aggregiere_tage(db, form, aid, mx.TAGE_JULI[:2])
                    a.sensor_mapping = voll
                    flag_modified(a, "sensor_mapping")
                    await db.commit()
                    await mx.aggregiere_tage(db, form, aid, mx.TAGE_JULI[2:])
                else:
                    await mx.aggregiere_tage(db, form, aid, mx.TAGE_JULI)
                if gespeichert is not None:
                    from backend.api.routes.monatsdaten import MonatsdatenCreate, create_monatsdaten
                    await create_monatsdaten(MonatsdatenCreate.model_validate(gespeichert(aid, ids)), None, db)
                    await db.commit()
                if mqtt is not None:
                    async def _m(db_, anlage, investitionen, jahr, monat, bis=None):
                        return mqtt(am)
                    monkeypatch.setattr(am, "_collect_mqtt_inbound_data", _m)
                r = await am.get_aktueller_monat(anlage_id=aid, jahr=mx.JAHR, monat=mx.JULI, db=db)
            return _putz(r.model_dump(mode="json"))
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


def stand_tag_2(form_id: str, mit_gesamt: bool):
    """Gespeicherte Juli-Zeile mit dem Stand NACH ZWEI TAGEN (der Monat läuft weiter)."""
    def bau(aid, ids):
        form = mx.FORMEN[form_id]
        n = {"anlage_id": aid, "jahr": mx.JAHR, "monat": mx.JULI, "einspeisung_kwh": 12.0, "netzbezug_kwh": 14.4,
             "geprueft_gegen": {}}
        if mit_gesamt and form.gesamt is not None:
            n["pv_erzeugung_kwh"] = mx.tagesmenge(form.gesamt) * 2
        inv = {str(ids[g.name]): {"pv_erzeugung_kwh": mx.tagesmenge(g.rate) * 2} for g in form.geraete if g.zaehler}
        inv[str(ids["Akku"])] = {"ladung_kwh": 6.0, "entladung_kwh": 4.0}
        inv[str(ids["WP"])] = {"stromverbrauch_kwh": 14.4, "waerme_kwh": 43.2}
        inv[str(ids["Wallbox"])] = {"ladung_kwh": 6.0}
        n["investitionen_daten"] = inv
        return n
    return bau


#: Connector mit Abdeckung ab dem Monatsersten (letzter Snapshot vor dem Juli).
CONNECTOR_DECKT = {
    "meter_snapshots": {
        "2026-06-30T23:55:00": {"pv_erzeugung_kwh": 1000.0, "batterie_ladung_kwh": 100.0,
                                "batterie_entladung_kwh": 50.0},
        "2026-07-03T23:55:00": {"pv_erzeugung_kwh": 1060.0, "batterie_ladung_kwh": 108.0,
                                "batterie_entladung_kwh": 55.0},
    },
    "last_fetch": "2026-07-03T23:55:00",
}


def _mqtt_rueckfall(am):
    info = am.DatenquelleInfo(quelle="mqtt_inbound", konfidenz=91, abdeckung_von=datetime(mx.JAHR, mx.JULI, 2, 12),
                              abdeckung_bis=mx.JETZT)
    return {"pv_erzeugung_kwh": (30.0, info), "einspeisung_kwh": (9.0, info)}


def _mqtt_gesamt_ab_monatsbeginn(am):
    return {"pv_erzeugung_kwh": (64.0, am.DatenquelleInfo(quelle="mqtt_inbound", konfidenz=91))}


# ── Was außerhalb der PV-Folgen stehen muss ────────────────────────────────

def _ohne_pv_folgen_gleich(d: dict, *, gespeichert: bool = False):
    """Speicher, Wärmepumpe, Wallbox, Netz: unberührt von der PV-Achse (vor und nach N-624
    gemessen gleich). Mit gespeicherter Zeile (Stand Tag 2) bleiben Wärmepumpe und Wallbox auf
    dem gespeicherten Stand (14,4 / 43,2 / 6) — Bestand, nicht Gegenstand dieser Regel."""
    assert d["speicher_ladung_kwh"] == pytest.approx(9.0)
    assert d["speicher_entladung_kwh"] == pytest.approx(6.0)
    assert d["einspeisung_kwh"] == pytest.approx(18.0)
    assert d["netzbezug_kwh"] == pytest.approx(21.6)
    assert d["wp_strom_kwh"] == pytest.approx(14.4 if gespeichert else 21.6)
    assert d["wp_waerme_kwh"] == pytest.approx(43.2 if gespeichert else 64.8)
    assert d["emob_ladung_kwh"] == pytest.approx(6.0 if gespeichert else 9.0)


def _pv_folgen(d: dict) -> None:
    """PV 63 und was daraus folgt: EV = 63 − Einspeisung 18 − Ladung 9 + Entladung 6 = 42."""
    assert d["pv_erzeugung_kwh"] == pytest.approx(63.0)
    assert d["eigenverbrauch_kwh"] == pytest.approx(42.0)
    assert d["autarkie_prozent"] == pytest.approx(66.0, abs=0.05)
    assert d["direktverbrauch_kwh"] == pytest.approx(36.0)


# ── Szenarien des Plans ────────────────────────────────────────────────────


async def test_f03_ohne_zeile_anlagenzaehler_gewinnt():
    """Anlagenzähler + BKW-Zähler, Strings ohne, keine gespeicherte Zeile: 63 statt 9."""
    d = await antwort("F03")
    _pv_folgen(d)
    assert d["bkw_erzeugung_kwh"] == pytest.approx(9.0)
    assert d["feld_quellen"]["pv_erzeugung_kwh"]["quelle"] == "ha_statistics"
    _ohne_pv_folgen_gleich(d)


async def test_f04_ein_string_mit_zaehler_anlagenzaehler_gewinnt():
    """Anlagenzähler + Süd mit Zähler: 63 statt 36."""
    d = await antwort("F04")
    _pv_folgen(d)
    _ohne_pv_folgen_gleich(d)


async def test_f06_mit_gespeichertem_stand_tag_2_wie_bisher():
    """Alle Einzelzähler, gespeicherte Zeile mit dem Stand nach zwei Tagen: der gespeicherte
    Wert bleibt ersetzbar (er misst bis zum Speichern) — PV 63, EV 42, Speicher 9/6, BKW 9."""
    d = await antwort("F06", gespeichert=stand_tag_2("F06", False))
    _pv_folgen(d)
    assert d["bkw_erzeugung_kwh"] == pytest.approx(9.0)
    _ohne_pv_folgen_gleich(d, gespeichert=True)


async def test_f03_mit_gespeichertem_anlagenwert_stand_tag_2():
    """Die gespeicherte Zeile trägt den Anlagenwert nach zwei Tagen (42): die HA-Monatsstatistik
    misst bis jetzt und gewinnt (63)."""
    d = await antwort("F03", gespeichert=stand_tag_2("F03", True))
    _pv_folgen(d)
    assert d["bkw_erzeugung_kwh"] == pytest.approx(9.0)
    _ohne_pv_folgen_gleich(d, gespeichert=True)


async def test_f06_connector_mit_abdeckung_wie_bisher():
    """Connector mit Abdeckung ab dem Monatsersten (PV 60): ersetzbar, die Komponenten-Summe
    der HA-Einzelzähler steht (63)."""
    d = await antwort("F06", connector=CONNECTOR_DECKT)
    _pv_folgen(d)
    _ohne_pv_folgen_gleich(d)


async def test_f03_mqtt_rueckfall_neben_ha(monkeypatch):
    """MQTT-Rückfall (PV 30 ab 02.07. 12:00) neben dem HA-Anlagenzähler: die HA-Statistik gewinnt."""
    d = await antwort("F03", mqtt=_mqtt_rueckfall, monkeypatch=monkeypatch)
    _pv_folgen(d)
    _ohne_pv_folgen_gleich(d)


async def test_f06_mqtt_anlagenzaehler_ab_monatsbeginn_alle_strings_gemessen(monkeypatch):
    """Kein HA-Anlagenzähler, MQTT liefert ihn ab Monatsbeginn (64), alle Erzeuger messen: wie
    vor N-624 gilt die Summe der gemessenen Erzeuger (63, ADR-002/P7 — der Anlagenwert füllt
    nur Lücken)."""
    d = await antwort("F06", mqtt=_mqtt_gesamt_ab_monatsbeginn, monkeypatch=monkeypatch)
    _pv_folgen(d)
    _ohne_pv_folgen_gleich(d)


async def test_f03_anlagenzaehler_spaet_zugeordnet():
    """Der Anlagenzähler wird erst am 03.07. zugeordnet (seine HA-Statistik kennt den ganzen
    Monat): 63."""
    d = await antwort("F03", spaet_zugeordnet=True)
    _pv_folgen(d)


async def test_benannte_grenze_ha_sensor_entsteht_im_monat():
    """⚠ Benannte Grenze (Bauplan T3): entsteht der HA-Sensor des Anlagenzählers erst am
    03.07., misst seine Monatsstatistik nur den 03.07. (21) — sie trägt keine Abdeckungs-
    Auskunft. Festgehalten, damit eine Änderung hier auffällt, nicht weil 21 richtig wäre."""
    d = await antwort("F03", statistik_ab=datetime(mx.JAHR, mx.JULI, 3, 0))
    assert d["pv_erzeugung_kwh"] == pytest.approx(21.0)


# ── Layer: Gewinner, Merge, Marke ──────────────────────────────────────────


def _alter_merge(*, saved, connector, mqtt_energy, ha_stats, ist_aktueller_monat, connector_abdeckung_von=None,
                 monat_start=None, tagesebene=None):
    """Die Präzedenz in ihrer update/setdefault-Fassung bis 04.10.2026 — unabhängige Referenz."""
    r = dict(saved)
    deckt = connector_abdeckung_von is not None and monat_start is not None and connector_abdeckung_von <= monat_start
    if ist_aktueller_monat and deckt:
        r.update(connector)
    else:
        for k, v in connector.items():
            r.setdefault(k, v)
    r.update(mqtt_energy)
    if ist_aktueller_monat:
        r.update(ha_stats)
    else:
        for k, v in ha_stats.items():
            r.setdefault(k, v)
    for k, v in (tagesebene or {}).items():
        r.setdefault(k, v)
    return r


_MS = datetime(2026, 7, 1)
_FELDER = ("a", "b", "c")


def _quelle(name: str, maske: int) -> dict:
    return {f: f"{name}:{f}" for i, f in enumerate(_FELDER) if maske >> i & 1}


@pytest.mark.parametrize("laufend", [True, False])
@pytest.mark.parametrize("abdeckung", [None, datetime(2026, 6, 30), datetime(2026, 7, 5)])
def test_gewinner_und_merge_sind_eine_praezedenz(laufend, abdeckung):
    """Für jede Belegung der fünf Quellen über drei Felder: Merge == Referenz, Merge == Wert des
    Gewinners, und die Marke nennt nur Felder, deren Gewinner einen Teilzeitraum misst."""
    for s in range(8):
        for c in range(8):
            for m in range(8):
                for h in range(8):
                    for t in range(8):
                        args = dict(saved=_quelle("saved", s), connector=_quelle("connector", c),
                                    mqtt_energy=_quelle("mqtt", m), ha_stats=_quelle("ha_stats", h),
                                    ist_aktueller_monat=laufend, connector_abdeckung_von=abdeckung,
                                    monat_start=_MS, tagesebene=_quelle("tagesebene", t))
                        merge = merge_datenquellen(**args)
                        assert merge == _alter_merge(**args)
                        assert list(merge) == list(_alter_merge(**args))
                        gew = gewinner_je_feld(**args)
                        assert {k: f"{q}:{k}" for k, q in gew.items()} == merge
                        teil = teilzeitraum_felder(**args, mqtt_ab_monatsbeginn=set())
                        for k in teil:
                            assert gew[k] != "ha_stats", (args, k)


def test_ha_statistik_sperrt_auch_wenn_die_tagesebene_das_feld_kennt():
    """Der Kern von N-624 in einer Zeile: HA gewinnt ⇒ kein Teilzeitraum."""
    assert teilzeitraum_felder(
        saved={}, connector={}, mqtt_energy={}, ha_stats={"pv_erzeugung_kwh": "h"},
        ist_aktueller_monat=True, tagesebene={"pv_erzeugung_kwh": "t"},
    ) == set()


def test_gespeichert_und_connector_bleiben_im_laufenden_monat_ersetzbar():
    assert teilzeitraum_felder(
        saved={"pv_erzeugung_kwh": "s", "netzbezug_kwh": "s"}, connector={"einspeisung_kwh": "c"},
        mqtt_energy={}, ha_stats={}, ist_aktueller_monat=True,
        connector_abdeckung_von=datetime(2026, 6, 30), monat_start=_MS,
        tagesebene={"pv_erzeugung_kwh": "t", "einspeisung_kwh": "t"},
    ) == {"pv_erzeugung_kwh", "einspeisung_kwh"}
