"""Benannte Proben zum Komplexitäts-Schnitt RF-56 … RF-58 (Bauplan ``bauplan-rf-40-komplexitaet.md`` S7, Regel RF-1: kein
Schnitt ohne Gate) — die Zweige, die weder die direkten Testdateien noch die Golden Master (Kanal-Dump
``skript-golden-master-kanal-modus-strom.py``, Fixture-GM ``bereichs-leser``, ``energie-profil``) betreten, gemessen am HEAD
``9fe83d32a`` (Bericht ``opus-berichte/RF-56-58-kanal-leser.md``, Abdeckungszeilen). Am HEAD grün, nach dem Schnitt grün.

* **RF-56** ``kanal/modus_strom.py::schreibe_modus_strom`` — ohne Wärmepumpe kein Zugriff; Mitschrift-Kanal ohne Zeile ⇒
  kein Beginn; Lauf mit einem Zeitpunkt VOR dem schon geschriebenen Stand ⇒ 0 (Beginn nach ``ts_bis``); geschrieben wird bis
  zur Stunde vor dem Zeitpunkt; ohne Strom-Kanal kein abgeleiteter Kanal; die Mitschrift
  endet vor den Strom-Kanälen ⇒ der Kanal endet an ihrer letzten Zeile, ein späterer Lauf schreibt weiter.
* **RF-57** ``snapshot/bereichs_leser.py::lade_tageswerte_je_geraet`` — E-Auto mit Parent und Gerät ``None`` übersprungen,
  ohne Parent gezählt; Lücke am ersten Tagesbeginn ⇒ Anker beliebig weit zurück (``letzter_stand_vor``), ohne Anker kein
  Tag; Rücksprung ⇒ kein Tag, Debug-Zeile; Rückwärts-Tag (N-435) im Fenster [Vortag 23:00, 23:00).
* **RF-58** ``api/routes/energie_profil/waerme.py::get_waerme_verlauf_stunden`` — unbekannte Anlage 404; Funktions-Stapel
  «übrige» ohne Gesamtstrom im Slot ``None``, unter Heizen + Warmwasser auf 0 geklemmt; ein Zähler, den die Route nicht
  findet (Funktions-Zähler bzw. gemessener Beitrag), hat keine Form und wird als «ohne Stundenform» genannt; eine Gesamt-Form
  ohne Wert ist ``None`` je Slot und fällt auf die Modus-Form zurück; an einem WP-Kanal-Tag ist eine Spannen-Stunde im
  Funktions-Stapel leer (S5-R5).

Schwesterdateien: ``test_kanal_modus_strom.py`` (der Schreiber am Datenstand der Matrix), ``test_zaehlerluecken_waerme_leser.py``
und ``test_waerme_verlauf_bereichs_leser.py`` (der Leser gegen SQLite), ``test_waerme_verlauf_stunden.py`` und
``test_p433_3_s3_tagessicht.py`` (die Stunden-Route).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx


# ── RF-56: schreibe_modus_strom ─────────────────────────────────────────────


class _KeinZugriff:
    """Eine Sitzung, die jeden Zugriff verbietet."""

    def __getattr__(self, name):
        raise AssertionError(f"Datenbank-Zugriff {name} ohne Wärmepumpe")


async def test_rf56_ohne_waermepumpe_kein_zugriff_und_null():
    from backend.services.kanal.modus_strom import schreibe_modus_strom

    n = await schreibe_modus_strom(_KeinZugriff(), SimpleNamespace(id=1, sensor_mapping={}), datetime(2026, 7, 3, 12),
                                   invs=[SimpleNamespace(id=1, typ="speicher"), SimpleNamespace(id=2, typ="wallbox")])
    assert n == 0


async def _reihe(db, key: str) -> list[tuple[int, float]]:
    return [(int(ts), float(s)) for ts, s in (await db.execute(text(
        "SELECT s.start_ts, s.sum FROM kanal_statistik s JOIN kanal k ON k.id = s.kanal_id "
        "WHERE k.key = :k ORDER BY s.start_ts"), {"k": key})).all()]


async def _abgeleitete_weg(db, wp: int) -> None:
    from backend.services.kanal.modus_strom import alle_keys

    ids = [r[0] for r in (await db.execute(text("SELECT id FROM kanal WHERE key IN (%s)" % ",".join(
        f"'{k}'" for k in alle_keys(wp))))).all()]
    for tab in ("kanal_statistik", "kanal_quelle"):
        await db.execute(text(f"DELETE FROM {tab} WHERE kanal_id IN ({','.join(map(str, ids))})"))
    await db.execute(text(f"DELETE FROM kanal WHERE id IN ({','.join(map(str, ids))})"))
    await db.commit()


async def _anlage(ds):
    from backend.models import Anlage

    return (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()


async def test_rf56_mitschrift_kanal_ohne_zeile_kein_beginn():
    """Ein Mitschrift-Kanal ohne eine Zeile: das Gerät ist abzuleiten, hat aber keine erste Mitschrift ⇒ kein Beginn, 0."""
    from backend.services.kanal.modus_strom import abdeckung_key, schreibe_modus_strom

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        wp = ds.ids["WP"]
        await _abgeleitete_weg(ds.db, wp)
        await ds.db.execute(text("DELETE FROM kanal_statistik WHERE kanal_id IN (SELECT id FROM kanal WHERE key LIKE :k)"),
                            {"k": f"modus:inv:{wp}:%"})
        await ds.db.commit()
        assert (await ds.db.execute(text("SELECT count(*) FROM kanal WHERE key LIKE :k"),
                                    {"k": f"modus:inv:{wp}:%"})).scalar() > 0
        n = await schreibe_modus_strom(ds.db, await _anlage(ds), mx.JETZT, ab_ts=int(mx.REIHE_VON.timestamp()))
        assert n == 0
        assert await _reihe(ds.db, abdeckung_key(wp)) == []


async def test_rf56_zeitpunkt_vor_dem_stand_schreibt_nichts():
    """Ein Lauf mit einem Zeitpunkt VOR der letzten geschriebenen Stunde, während die Mitschrift weiter reicht: der Beginn
    (letzte Zeile + 1 h) liegt nach ``ts_bis`` ⇒ 0, nichts verändert."""
    from backend.services.kanal.modus_strom import alle_keys, schreibe_modus_strom

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        wp = ds.ids["WP"]
        grenze = int(datetime(2026, 6, 25, 12).timestamp())
        await ds.db.execute(text("DELETE FROM kanal_statistik WHERE start_ts > :g AND kanal_id IN "
                                 "(SELECT id FROM kanal WHERE key LIKE :k)"), {"g": grenze, "k": f"abgeleitet:inv:{wp}:modus%"})
        await ds.db.commit()
        vorher = {k: await _reihe(ds.db, k) for k in alle_keys(wp)}
        assert vorher[alle_keys(wp)[0]][-1][0] == grenze
        n = await schreibe_modus_strom(ds.db, await _anlage(ds), datetime(2026, 6, 20, 12, 5))
        await ds.db.commit()
        assert n == 0
        assert {k: await _reihe(ds.db, k) for k in alle_keys(wp)} == vorher


async def test_rf56_schreibt_bis_zur_stunde_vor_dem_zeitpunkt():
    """Der Lauf um 12:05 schreibt bis einschließlich der Stunde 11:00 (``ts_bis`` = die Stunde vor ``zeitpunkt``), auch wenn
    Strom-Kanal und Mitschrift die Stunde 12:00 schon tragen — die laufende Stunde ist nicht abgeschlossen."""
    from backend.services.kanal.modus_strom import abdeckung_key, schreibe_modus_strom

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        wp = ds.ids["WP"]
        grenze = int(datetime(2026, 6, 19, 12).timestamp())
        await ds.db.execute(text("DELETE FROM kanal_statistik WHERE start_ts > :g AND kanal_id IN "
                                 "(SELECT id FROM kanal WHERE key LIKE :k)"), {"g": grenze, "k": f"abgeleitet:inv:{wp}:modus%"})
        await ds.db.commit()
        n = await schreibe_modus_strom(ds.db, await _anlage(ds), datetime(2026, 6, 20, 12, 5))
        await ds.db.commit()
        abd = await _reihe(ds.db, abdeckung_key(wp))
        assert n == 7 * 23
        assert abd[-1][0] == int(datetime(2026, 6, 20, 11).timestamp())


async def test_rf56_mitschrift_endet_vor_dem_strom_kanal_endet_dort_und_schreibt_spaeter_weiter():
    """Neuaufbau in einem Lauf über viele Stunden, die Mitschrift endet am 01.07. 12:00, der Strom läuft weiter: der Kanal
    endet an der letzten Mitschrift-Zeile («die Mitschrift ist noch nicht so weit»). Kommt die Mitschrift nach, schreibt
    der nächste Lauf ab dort weiter — das Ergebnis ist der ungestörte Neuaufbau."""
    from backend.services.kanal.modus_strom import abdeckung_key, alle_keys, schreibe_modus_strom

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        wp = ds.ids["WP"]
        ab = int(mx.REIHE_VON.timestamp())
        await _abgeleitete_weg(ds.db, wp)
        await schreibe_modus_strom(ds.db, await _anlage(ds), mx.JETZT, ab_ts=ab)
        await ds.db.commit()
        ungestoert = {k: await _reihe(ds.db, k) for k in alle_keys(wp)}
        await _abgeleitete_weg(ds.db, wp)
        grenze = int(datetime(2026, 7, 1, 12).timestamp())
        await ds.db.execute(text(
            "CREATE TEMP TABLE rf56_rest AS SELECT * FROM kanal_statistik WHERE start_ts > :g AND kanal_id IN "
            "(SELECT id FROM kanal WHERE key LIKE :k)"), {"g": grenze, "k": f"modus:inv:{wp}:%"})
        await ds.db.execute(text("DELETE FROM kanal_statistik WHERE start_ts > :g AND kanal_id IN "
                                 "(SELECT id FROM kanal WHERE key LIKE :k)"), {"g": grenze, "k": f"modus:inv:{wp}:%"})
        await ds.db.commit()
        n1 = await schreibe_modus_strom(ds.db, await _anlage(ds), mx.JETZT, ab_ts=ab)
        await ds.db.commit()
        abd = await _reihe(ds.db, abdeckung_key(wp))
        assert n1 > 0 and abd[-1][0] == grenze
        await ds.db.execute(text("INSERT INTO kanal_statistik SELECT * FROM rf56_rest"))
        await ds.db.commit()
        n2 = await schreibe_modus_strom(ds.db, await _anlage(ds), mx.JETZT, ab_ts=ab)
        await ds.db.commit()
        assert n2 > 0
        assert {k: await _reihe(ds.db, k) for k in alle_keys(wp)} == ungestoert


async def test_rf56_ohne_strom_kanal_kein_abgeleiteter_kanal():
    """Mitschrift und Strom-Zähler sind da, aber kein Strom-Kanal der Art ``sum`` (der Spiegel hat ihn noch nicht
    angelegt) ⇒ 0 und kein abgeleiteter Kanal."""
    from backend.services.kanal.modus_strom import abdeckung_key, schreibe_modus_strom

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        wp = ds.ids["WP"]
        await _abgeleitete_weg(ds.db, wp)
        ids = [r[0] for r in (await ds.db.execute(text("SELECT id FROM kanal WHERE key LIKE :k"),
                                                   {"k": f"inv:{wp}:%strom%"})).all()]
        assert ids
        for tab in ("kanal_statistik", "kanal_quelle"):
            await ds.db.execute(text(f"DELETE FROM {tab} WHERE kanal_id IN ({','.join(map(str, ids))})"))
        await ds.db.execute(text(f"DELETE FROM kanal WHERE id IN ({','.join(map(str, ids))})"))
        await ds.db.commit()
        n = await schreibe_modus_strom(ds.db, await _anlage(ds), mx.JETZT, ab_ts=int(mx.REIHE_VON.timestamp()))
        assert n == 0
        assert await _reihe(ds.db, abdeckung_key(wp)) == []


# ── RF-57: lade_tageswerte_je_geraet ────────────────────────────────────────
#
# Die vier Nähte des Lesers (``mqtt_zaehler_keys``, ``_reihe_ueber_bereich``, ``get_snapshot``, ``letzter_stand_vor``) sind
# gestellt — dieselbe Naht wie der Fixture-GM ``bereichs-leser``; die Regeln dahinter (Ränder, Anker, Tagesreset,
# Geräteauflösung) laufen echt.

def _stunden(von: datetime, n: int, start: float, pro_h) -> list[tuple[datetime, float]]:
    out, w = [], start
    for i in range(n):
        out.append((von + timedelta(hours=i), round(w, 3)))
        w += pro_h[i % len(pro_h)] if isinstance(pro_h, (list, tuple)) else pro_h
    return out


def _leser(monkeypatch, reihen: dict, *, anker: dict | None = None, mqtt: set | None = None):
    from backend.services.snapshot import bereichs_leser as bl

    aufrufe: list = []

    async def mq(db, anlage_id, *a, **k):
        return set(mqtt or ())

    async def reihe(db, anlage_id, sensor_key, von, bis):
        aufrufe.append(("reihe", sensor_key, von, bis))
        rand = timedelta(minutes=5)
        return [(t, w) for t, w in reihen.get(sensor_key, []) if von - rand <= t <= bis + rand]

    async def snap(db, anlage_id, sensor_key, sensor_id, zeitpunkt, **k):
        aufrufe.append(("heilung", sensor_key, zeitpunkt))
        return None

    async def vor(db, anlage_id, sensor_key, zeitpunkt, **k):
        aufrufe.append(("anker", sensor_key, zeitpunkt))
        return (anker or {}).get((sensor_key, zeitpunkt))
    monkeypatch.setattr(bl, "mqtt_zaehler_keys", mq)
    monkeypatch.setattr(bl, "_reihe_ueber_bereich", reihe)
    monkeypatch.setattr(bl, "get_snapshot", snap)
    monkeypatch.setattr(bl, "letzter_stand_vor", vor)
    return bl, aufrufe


def _anl(felder_je_inv: dict):
    return SimpleNamespace(id=7, sensor_mapping={"investitionen": {
        str(i): {"felder": {f: {"strategie": "sensor", "sensor_id": f"sensor.{i}_{f}"} for f in fe}}
        for i, fe in felder_je_inv.items()}})


EMOB = {("wallbox", "ladung_pv_kwh"): "emob_ladung_pv_kwh", ("e-auto", "ladung_pv_kwh"): "emob_ladung_pv_kwh"}
HEIZ = {("waermepumpe", "heizenergie_kwh"): "wp_heizung_kwh"}
T0 = datetime(2026, 3, 9, 20)


async def test_rf57_e_auto_mit_parent_und_geraet_none_uebersprungen(monkeypatch):
    """Die Wallbox misst die Ladung: ein E-Auto MIT Parent fehlt (sonst Doppelzählung), ohne Parent zählt es; ein
    Gerät ``None`` fehlt — beides wie ``get_tagesdetail_kwh``."""
    reihen = {"inv:5:ladung_pv_kwh": _stunden(T0, 30, 100.0, 0.5), "inv:3:ladung_pv_kwh": _stunden(T0, 30, 200.0, 0.25)}
    bl, _ = _leser(monkeypatch, reihen)
    anlage = _anl({5: ["ladung_pv_kwh"], 3: ["ladung_pv_kwh"]})
    wb = SimpleNamespace(id=5, typ="wallbox", parent_investition_id=None)
    mit = {"5": wb, "3": SimpleNamespace(id=3, typ="e-auto", parent_investition_id=5), "9": None}
    erg = await bl.lade_tageswerte_je_geraet(None, anlage, mit, date(2026, 3, 10), date(2026, 3, 10), EMOB)
    assert erg == {date(2026, 3, 10): {"emob_ladung_pv_kwh": {"5": 12.0}}}
    ohne = {"5": wb, "3": SimpleNamespace(id=3, typ="e-auto", parent_investition_id=None)}
    erg = await bl.lade_tageswerte_je_geraet(None, anlage, ohne, date(2026, 3, 10), date(2026, 3, 10), EMOB)
    assert erg == {date(2026, 3, 10): {"emob_ladung_pv_kwh": {"5": 12.0, "3": 6.0}}}


async def test_rf57_luecke_am_ersten_tagesbeginn_anker_beliebig_weit_zurueck(monkeypatch):
    """R1 auf den Tagesrand: fehlt der Stand am ersten Tagesbeginn und liegt in der Reihe nichts davor, trägt der letzte
    Stand beliebig weit zurück (``letzter_stand_vor``) — die Energie der Lücke gehört zum Tag; ohne Anker fehlt der Tag."""
    sk = "inv:4:heizenergie_kwh"
    reihe = _stunden(datetime(2026, 3, 10, 3), 30, 1000.0, 1.0)     # beginnt 03:00 — 00:00 fehlt
    bl, aufrufe = _leser(monkeypatch, {sk: reihe}, anker={(sk, datetime(2026, 3, 10)): (datetime(2026, 3, 1, 8), 990.0)})
    anlage = _anl({4: ["heizenergie_kwh"]})
    invs = {"4": SimpleNamespace(id=4, typ="waermepumpe", parent_investition_id=None)}
    erg = await bl.lade_tageswerte_je_geraet(None, anlage, invs, date(2026, 3, 10), date(2026, 3, 10), HEIZ)
    assert erg == {date(2026, 3, 10): {"wp_heizung_kwh": {"4": 1021.0 - 990.0}}}
    assert ("anker", sk, datetime(2026, 3, 10)) in aufrufe
    bl, _ = _leser(monkeypatch, {sk: reihe})
    assert await bl.lade_tageswerte_je_geraet(None, anlage, invs, date(2026, 3, 10), date(2026, 3, 10), HEIZ) == {}


async def test_rf57_ruecksprung_kein_tag_und_debug(monkeypatch, caplog):
    """Ein Zähler-Rücksprung im Tagesfenster: der Tag fehlt (keine 0), der Nachbartag bleibt; eine Debug-Zeile nennt ihn."""
    import logging

    sk = "inv:4:heizenergie_kwh"
    reihe = _stunden(T0, 60, 1000.0, [1.0] * 30 + [-500.0] + [1.0] * 40)
    bl, _ = _leser(monkeypatch, {sk: reihe})
    invs = {"4": SimpleNamespace(id=4, typ="waermepumpe", parent_investition_id=None)}
    with caplog.at_level(logging.DEBUG, logger="backend.services.snapshot.bereichs_leser"):
        erg = await bl.lade_tageswerte_je_geraet(None, _anl({4: ["heizenergie_kwh"]}), invs, date(2026, 3, 10),
                                                 date(2026, 3, 11), HEIZ)
    assert list(erg) == [date(2026, 3, 10)]
    assert any("Rücksprung" in r.getMessage() and "2026-03-11" in r.getMessage() for r in caplog.records)


async def test_rf57_rueckwaerts_tag_liest_vortag_23_bis_23(monkeypatch):
    """N-435: ein Rückwärts-Tag liest [Vortag 23:00, 23:00); die Reihe deckt beide Fenster (eine Abfrage)."""
    sk = "inv:4:heizenergie_kwh"
    reihe = _stunden(T0, 60, 1000.0, [0.5 if i % 2 else 1.5 for i in range(60)])
    bl, aufrufe = _leser(monkeypatch, {sk: reihe})
    invs = {"4": SimpleNamespace(id=4, typ="waermepumpe", parent_investition_id=None)}
    an = _anl({4: ["heizenergie_kwh"]})
    kal = await bl.lade_tageswerte_je_geraet(None, an, invs, date(2026, 3, 10), date(2026, 3, 10), HEIZ)
    rw = await bl.lade_tageswerte_je_geraet(None, an, invs, date(2026, 3, 10), date(2026, 3, 10), HEIZ,
                                            rueckwaerts_tage={date(2026, 3, 10)})
    stand = dict(reihe)
    assert kal[date(2026, 3, 10)]["wp_heizung_kwh"]["4"] == pytest.approx(stand[datetime(2026, 3, 11)] - stand[datetime(2026, 3, 10)])
    assert rw[date(2026, 3, 10)]["wp_heizung_kwh"]["4"] == pytest.approx(
        stand[datetime(2026, 3, 10, 23)] - stand[datetime(2026, 3, 9, 23)])
    assert ("reihe", sk, datetime(2026, 3, 9, 23), datetime(2026, 3, 10, 23)) in aufrufe


# ── RF-58: get_waerme_verlauf_stunden ───────────────────────────────────────


async def test_rf58_unbekannte_anlage_404(db):
    from fastapi import HTTPException

    from backend.api.routes.energie_profil.views import get_waerme_verlauf_stunden

    with pytest.raises(HTTPException) as e:
        await get_waerme_verlauf_stunden(999999, date(2026, 1, 15), db)
    assert e.value.status_code == 404


async def test_rf58_uebrige_ohne_gesamtstrom_none_und_auf_null_geklemmt(db):
    """Der Funktions-Stapel je Slot: «übrige» = max(0, Gesamt − Heizen − WW) — ohne Gesamtstrom im Slot ``None`` (keine
    Aussage, nicht 0), ein Gesamtstrom unter Heizen + WW ergibt 0,0 (nie negativ); Heizen/WW bleiben stehen."""
    from sqlalchemy import update

    from backend.api.routes.energie_profil.views import get_waerme_verlauf_stunden
    from backend.models.tages_energie_profil import TagesEnergieProfil
    from backend.tests.test_waerme_verlauf_stunden import DATUM, _anlage_funktionszaehler

    anlage, _wp = await _anlage_funktionszaehler(db)
    await db.execute(update(TagesEnergieProfil).where(
        TagesEnergieProfil.anlage_id == anlage.id, TagesEnergieProfil.stunde == 9).values(waermepumpe_kw=None))
    await db.execute(update(TagesEnergieProfil).where(
        TagesEnergieProfil.anlage_id == anlage.id, TagesEnergieProfil.stunde == 6).values(waermepumpe_kw=1.0))
    await db.commit()
    v = await get_waerme_verlauf_stunden(anlage.id, DATUM, db)
    assert v.funktions_stapel_verfuegbar is True
    s9, s6, s5 = v.stunden[9], v.stunden[6], v.stunden[5]
    assert s9.wp_strom_kwh is None and s9.wp_funktion_uebrige_kwh is None
    assert s9.wp_funktion_strom_heizen_kwh == 0.0 and s9.wp_funktion_strom_warmwasser_kwh == 0.0
    assert s6.wp_strom_kwh == pytest.approx(1.0) and s6.wp_funktion_strom_heizen_kwh == pytest.approx(6.0, abs=1e-3)
    assert s6.wp_funktion_uebrige_kwh == 0.0
    assert s5.wp_funktion_uebrige_kwh == pytest.approx(0.1, abs=1e-3)


async def test_rf58_zaehler_ohne_zuordnung_hat_keine_form_und_wird_genannt(db, monkeypatch):
    """Ein Feld, dessen Zähler die Stunden-Route nicht (mehr) findet (``feld_hat_zaehler`` falsch — etwa eine entfernte
    Zuordnung), bekommt keine Stundenform: der Warmwasser-Strom des Tages steht als ``funktion_ohne_stundenform_kwh``
    (genannt, nicht verteilt, W1), der Gesamtzähler ohne Form trägt keine Gesamt-Form (``_summe_je_slot`` ohne Reihe);
    Heizen behält seine Form, «übrige» füllt bis zur Zählerspalte."""
    from backend.api.routes.energie_profil.views import get_waerme_verlauf_stunden
    from backend.services.snapshot import keys
    from backend.tests.test_waerme_verlauf_stunden import DATUM, _anlage_funktionszaehler

    anlage, _wp = await _anlage_funktionszaehler(db)
    echt = keys.feld_hat_zaehler

    def ohne_ww_und_gesamt(cfg, key, quellen, mqtt=None):
        if key.endswith((":strom_warmwasser_kwh", ":stromverbrauch_kwh")):
            return False
        return echt(cfg, key, quellen, mqtt)
    monkeypatch.setattr(keys, "feld_hat_zaehler", ohne_ww_und_gesamt)
    v = await get_waerme_verlauf_stunden(anlage.id, DATUM, db)
    assert v.funktions_stapel_verfuegbar is True
    assert v.funktion_ohne_stundenform_kwh == 3.0
    s6, s7 = v.stunden[6], v.stunden[7]
    assert (s6.wp_funktion_strom_heizen_kwh, s6.wp_funktion_strom_warmwasser_kwh) == (6.0, 0.0)
    assert s6.wp_funktion_uebrige_kwh == pytest.approx(0.1, abs=1e-3)
    assert s7.wp_funktion_strom_warmwasser_kwh == 0.0 and s7.wp_funktion_uebrige_kwh == pytest.approx(1.1, abs=1e-3)



async def test_rf58_gemessener_zaehler_ohne_zuordnung_wird_genannt(db, monkeypatch):
    """Ein gemessener Beitrag (Betriebsart-Zähler, Gesamtzähler), dessen Zähler die Stunden-Route nicht findet: keine
    Stundenform, keine Gesamt-Form (``_summe_je_slot`` ohne Reihe) — die Menge des Geräts steht als
    ``ohne_stundenform_kwh`` (W1), der Stapel der Stunde trägt nur das zweite Gerät (Modus-Spur, 0,4 × 12/9,6)."""
    from backend.api.routes.energie_profil.views import get_waerme_verlauf_stunden
    from backend.services.snapshot import keys
    from backend.tests.test_waerme_verlauf_stunden import DATUM, _anlage as _anlage_zwei_wp

    anlage, _wp1, _wp2 = await _anlage_zwei_wp(db)
    assert (await get_waerme_verlauf_stunden(anlage.id, DATUM, db)).ohne_stundenform_kwh is None
    echt = keys.feld_hat_zaehler

    def ohne_strom(cfg, key, quellen, mqtt=None):
        if key.endswith((":betriebsart_strom_heizen_kwh", ":stromverbrauch_kwh")):
            return False
        return echt(cfg, key, quellen, mqtt)
    monkeypatch.setattr(keys, "feld_hat_zaehler", ohne_strom)
    v = await get_waerme_verlauf_stunden(anlage.id, DATUM, db)
    assert v.ohne_stundenform_kwh == 11.1
    assert v.stunden[3].wp_modus_strom_heizen_kwh == pytest.approx(0.5, abs=1e-3)
    assert v.stunden[3].wp_waerme_kwh == pytest.approx(1.5, abs=1e-3)


async def test_rf58_gesamtform_ohne_wert_faellt_auf_die_modus_form(db, monkeypatch):
    """Ein Gesamt-Zähler, dessen Stundenform keinen einzigen Wert trägt: die Gesamt-Form des Geräts ist je Slot ``None``
    (``_summe_je_slot``, keine 0), ``gesamt_form`` fällt auf die Modus-Form zurück und der Zähler-Rest verteilt sich über
    sie — nichts landet in «ohne Stundenform». (Mit Nullen statt ``None`` wäre die Form «leer gemessen», 2,4 kWh fielen
    aus den Stunden.)"""
    from backend.api.routes.energie_profil.views import get_waerme_verlauf_stunden
    from backend.services.energie_profil import kanal_stunden
    from backend.tests.test_waerme_verlauf_stunden import DATUM, _anlage as _anlage_zwei_wp

    anlage, wp1, wp2 = await _anlage_zwei_wp(db)
    echt = kanal_stunden.wp_stundenformen

    async def gesamt_ohne_wert(db_, anlage_, datum_, zaehler_):
        formen, modus = await echt(db_, anlage_, datum_, zaehler_)
        return ({**formen, f"inv:{wp1.id}:stromverbrauch_kwh": [None] * 24},
                {**modus, str(wp1.id): modus[str(wp2.id)]})
    monkeypatch.setattr(kanal_stunden, "wp_stundenformen", gesamt_ohne_wert)
    v = await get_waerme_verlauf_stunden(anlage.id, DATUM, db)
    assert v.ohne_stundenform_kwh is None
    assert v.stunden[20].wp_modus_nicht_aufgeteilt_kwh == pytest.approx(0.15, abs=1e-3)
    assert v.stunden[20].wp_modus_strom_bezug_kwh == pytest.approx(0.85, abs=1e-3)


async def test_rf58_funktions_stapel_spannen_stunde_leer_am_kanal_tag(monkeypatch):
    """S5-R5 im Funktions-Stapel: an einem WP-Kanal-Tag (Matrix-Form M06, «WP HW» mit getrennter Strommessung) verlieren die
    Strom-Kanäle die Stunden 10 und 11 — dort tragen Heizen und Warmwasser ``None`` (keine eigene Zeile, keine 0), die
    Stunde 12 trägt die Energie der Spanne; Σ Heizen bleibt der Tag."""
    from sqlalchemy import delete

    from backend.api.routes.energie_profil.waerme import get_waerme_verlauf_stunden
    from backend.models.kanal import Kanal, KanalStatistik
    from backend.services.kanal import bilanz_leser

    tag = date(2026, 6, 10)
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)
    async with kg.datenstand("achsen", "M06", "HA") as ds:
        hw = ds.ids["WP HW"]
        vorher = await get_waerme_verlauf_stunden(ds.aid, datum=tag, db=ds.db)
        ab = int(datetime.combine(tag, datetime.min.time()).timestamp()) + 10 * 3600
        ids = select(Kanal.id).where(Kanal.anlage_id == ds.aid, Kanal.key.like(f"inv:{hw}:%"))
        await ds.db.execute(delete(KanalStatistik).where(
            KanalStatistik.kanal_id.in_(ids), KanalStatistik.start_ts >= ab, KanalStatistik.start_ts < ab + 2 * 3600))
        await ds.db.commit()
        st = await get_waerme_verlauf_stunden(ds.aid, datum=tag, db=ds.db)
    assert st.raster == "beginn" and st.funktions_stapel_verfuegbar is True
    for h in (10, 11):
        assert st.stunden[h].wp_funktion_strom_heizen_kwh is None
        assert st.stunden[h].wp_funktion_strom_warmwasser_kwh is None
    assert st.stunden[12].wp_funktion_strom_heizen_kwh == pytest.approx(0.75, abs=1e-3)
    assert sum(s.wp_funktion_strom_heizen_kwh or 0.0 for s in st.stunden) == pytest.approx(
        sum(s.wp_funktion_strom_heizen_kwh or 0.0 for s in vorher.stunden), abs=1e-3)
