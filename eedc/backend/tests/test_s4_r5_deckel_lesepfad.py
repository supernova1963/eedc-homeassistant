"""HA-Bauform S4-R-5: kein Deckel auf HA-Werten im Lesepfad der Monate — Probe je Weg mit einem Sprung OHNE Nacht.

**Was geprüft wird.** Ein Sprung von 250 kWh mitten im Ertrag (15.06. 12:00, keine Nullstunden davor — anders als M03,
dessen Sprung nach der Nacht als N-567-Nachtrag durch das Deckel-Fenster läuft; E-S4-0 `deckel_sprung_mittags.txt`:
mit Deckel 179, ohne 430) auf Einspeisung UND PV-Gesamt, PV-Form F01, HA-Datenstand (``kanal_bilanz_gleichheit.
datenstand``). Je Weg nennt der Juni HAs Zahl (Einspeisung 430 = 180 + 250) und das Kanal-Δ (Fassung (b)) dieselbe:

  (a) Cockpit → Monat (HA-Weg), (b) «Aus HA laden», (c) alle Monatswerte, (d) Import-Vorschau, (e) Sammelimport,
  (f) Monatsabschluss-Vorschlag —

in zwei Lesarten: ``voll`` (die Spiegel decken den Kalendermonat, ``monatswerte_mit_kanaelen`` ersetzt den HA-Leser
durch das Kanal-Δ — dort war schon vor S4 kein Deckel) und ``lesart1`` (der Netzbezug-Spiegel beginnt erst am
02.06. ⇒ die Bilanz-Gruppe ist nicht gedeckt, alle sechs Wege nehmen den HA-Monatsleser — hier fiel der Deckel weg,
HEAD `08a52dc2` nannte 179). Dazu: Tag 15.06. (Cockpit → Tag, Kanal-Tag Weg 2) = HAs Tag = 256, Σ der Juni-Tage =
Monat = 430 (N-586-Lesart: Tag = Monat auch im Lesart-1-Monat), und der Daten-Checker ``ha_zaehlersprung`` benennt den
Sprung (bestehende Regel).

**Seed.** HAs ``sum`` trägt den Sprung; HAs ``state`` NICHT — 11:00 steht ``state`` auf 0, ab 12:00 ist ``state`` =
``sum`` − 250: das Muster «Reset und Rückkehr», das der Checker sucht (Phantommenge = Zuwachs von ``sum`` minus Zuwachs
von ``state`` = 250). Die Monatswerte lesen nur ``sum`` (der ``state``-Zweig greift nur ohne ``sum`` im Monat, §10a H-1).

Schwesterdateien: test_zaehlerluecken_monatswert_aufrufer.py (die Aufrufer reichen keinen Deckel), test_kanal_bilanz_
gleichheit.py (Kalendermonats-Wege mit Rücksprung), test_n586_checker_ha_zaehlersprung.py (der Checker selbst).
"""

from __future__ import annotations

import time as _zeit
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select, text

from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

SPRUNG = datetime(2026, 6, 15, 12)
SPRUNG_KWH = 250.0
SPRUNG_SENSOREN = ("sensor.einsp", "sensor.pv_gesamt")
JUNI_TAGE = tuple(date(2026, 6, d) for d in range(1, 31))


def _phantom_im_state(seed_ha):
    """``seed_ha`` der PV-Matrix, danach in HAs Statistik: ``state`` 11:00 = 0, ab 12:00 ``state`` = ``sum`` − Sprung."""
    def seed(form, *, abweichung=None):
        svc = seed_ha(form, abweichung=abweichung)
        t12 = _zeit.mktime(SPRUNG.timetuple())
        with svc._engine.begin() as conn:
            for sid in SPRUNG_SENSOREN:
                mid = conn.execute(text("SELECT id FROM statistics_meta WHERE statistic_id = :s"), {"s": sid}).scalar_one()
                conn.execute(text("UPDATE statistics SET state = 0 WHERE metadata_id = :m AND start_ts = :t"),
                             {"m": mid, "t": t12 - 3600})
                conn.execute(text("UPDATE statistics SET state = state - :k WHERE metadata_id = :m AND start_ts >= :t"),
                             {"m": mid, "t": t12, "k": SPRUNG_KWH})
        return svc
    return seed


@asynccontextmanager
async def _datenstand_sprung(lesart: str):
    """F01, HA, Sprung 250 kWh am 15.06. 12:00 auf Einspeisung und PV-Gesamt; ``lesart1``: Netzbezug-Spiegel ab 02.06."""
    form = mx.MATRIX_FORMEN["F01"]
    rate = {sid: fn for sid, (fn, _o, _k) in mx._reihen(form).items()}
    abw = {sid: ((lambda t, f=rate[sid]: f(t) + (SPRUNG_KWH if t == SPRUNG else 0.0)), None) for sid in SPRUNG_SENSOREN}
    with patch.object(mx, "seed_ha", _phantom_im_state(mx.seed_ha)):
        async with kg.datenstand("pv", "F01", "HA", ha_abweichung=abw) as ds:
            if lesart == "lesart1":
                n = (await ds.db.execute(text(
                    "DELETE FROM kanal_statistik WHERE start_ts < :t AND kanal_id = (SELECT id FROM kanal WHERE "
                    "anlage_id = :a AND key = 'basis:netzbezug')"),
                    {"t": int(datetime(2026, 6, 2).timestamp()), "a": ds.aid})).rowcount
                assert n > 0
                await ds.db.commit()
            yield ds


async def _miss_wege(ds) -> dict:
    """Juni je Weg (Einspeisung, PV-Gesamt wo sichtbar), HA-Leser mit/ohne Deckel, Kanal-Δ, Tag 15.06., Σ Tage, Checker."""
    from backend.api.routes import aktueller_monat as amr
    from backend.api.routes.ha_statistics import (
        ImportRequest, MonatFeldAuswahl, get_alle_monatswerte, get_import_vorschau, get_monatswerte,
        import_ha_statistics,
    )
    from backend.api.routes.monatsabschluss import views
    from backend.models.anlage import Anlage
    from backend.models.monatsdaten import Monatsdaten
    from backend.services.daten_checker.datenquelle.ha_sprung import HaZaehlersprungChecks
    from backend.services.energie_profil.tage_werte import baue_tage_werte
    from backend.services.kanal.bilanz_adapter import FASSUNG_WIE_HA, sensor_monatswerte_aus_kanaelen

    out: dict = {}
    with mx._umgebung(ds.svc):
        sids, deckel = await kg.zaehler_sensoren(ds.db, ds.aid)
        mit = {w.sensor_id: w.differenz for w in ds.svc.get_monatswerte(sids, 2026, 6, deckel_je_sensor=deckel).sensoren}
        ohne = {w.sensor_id: w.differenz for w in ds.svc.get_monatswerte(sids, 2026, 6).sensoren}
        kanal = {w.sensor_id: w.differenz for w in (await sensor_monatswerte_aus_kanaelen(
            ds.db, ds.aid, list(SPRUNG_SENSOREN), 2026, 6, fassung=FASSUNG_WIE_HA, jetzt=kg.JETZT_TS)).sensoren}
        out["ha_leser_mit_deckel"] = {s: mit.get(s) for s in SPRUNG_SENSOREN}
        out["ha_leser_ohne_deckel"] = {s: ohne.get(s) for s in SPRUNG_SENSOREN}
        out["kanal_delta"] = {s: kanal.get(s) for s in SPRUNG_SENSOREN}
        out["deckel_kwh_h"] = {s: deckel.get(s) for s in SPRUNG_SENSOREN}

        cockpit = await amr.get_aktueller_monat(anlage_id=ds.aid, jahr=2026, monat=6, db=ds.db)
        out["a_cockpit_monat"] = {"einsp": cockpit.einspeisung_kwh, "pv": cockpit.pv_erzeugung_kwh,
                                  "quelle_einsp": _quelle(cockpit, "einspeisung_kwh")}
        route = await get_monatswerte(ds.aid, 2026, 6, ds.db)
        out["b_aus_ha_laden"] = {b.sensor_id: b.differenz for b in route.basis}
        alle = next(r for r in await get_alle_monatswerte(ds.aid, None, None, ds.db) if (r.jahr, r.monat) == (2026, 6))
        out["c_alle_monatswerte"] = {b.sensor_id: b.differenz for b in alle.basis}
        vorschau = next(m for m in (await get_import_vorschau(ds.aid, ds.db)).monate if (m.jahr, m.monat) == (2026, 6))
        out["d_import_vorschau"] = dict(vorschau.ha_werte or {})
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        abschluss = await views.get_monatsabschluss(ds.aid, 2026, 6, db=ds.db)
        out["f_monatsabschluss_vorschlag"] = {
            f.feld: [(v["quelle"], v["wert"]) for v in (x if isinstance(x, dict) else x.model_dump() for x in f.vorschlaege)
                     if v["quelle"] == "ha_statistics"]
            for f in abschluss.basis_felder if f.feld in ("einspeisung_kwh", "pv_gesamt_kwh", "netzbezug_kwh")}
        tw = {z.datum: z for z in await baue_tage_werte(ds.db, anlage, JUNI_TAGE[0], JUNI_TAGE[-1])}
        out["tag_15_einsp"] = tw[date(2026, 6, 15)].einspeisung
        out["tag_15_erzeugung"] = tw[date(2026, 6, 15)].erzeugung
        out["summe_tage_einsp"] = round(sum(z.einspeisung or 0.0 for z in tw.values()), 3)
        out["summe_tage_erzeugung"] = round(sum(z.erzeugung or 0.0 for z in tw.values()), 3)
        out["tage_juni"] = len(tw)
        out["ha_tag_15_einsp"] = _ha_tag(ds.svc, "sensor.einsp", date(2026, 6, 15))

        class _Pruefer(HaZaehlersprungChecks):
            def __init__(self, db):
                self.db = db
        befunde = await _Pruefer(ds.db)._check_ha_zaehlersprung(anlage, jetzt=datetime(2026, 7, 4, 0, 30))
        out["checker_ha_zaehlersprung"] = [(e.kategorie, e.meldung, e.details) for e in befunde]

        await import_ha_statistics(ds.aid, ImportRequest(monate=[MonatFeldAuswahl(jahr=2026, monat=6)]), ds.db)
        await ds.db.commit()
        md = (await ds.db.execute(select(Monatsdaten).where(
            Monatsdaten.anlage_id == ds.aid, Monatsdaten.jahr == 2026, Monatsdaten.monat == 6))).scalar_one()
        out["e_sammelimport"] = {"einsp": md.einspeisung_kwh, "pv": md.pv_erzeugung_kwh}
    return out


def _quelle(cockpit, feld: str):
    q = (cockpit.feld_quellen or {}).get(feld)
    return q.get("quelle") if isinstance(q, dict) else getattr(q, "quelle", None)


def _ha_tag(svc, sid: str, tag: date) -> float:
    """HAs Tageszahl aus ``sum``: Stand der Zeile Vortag 23:00 (Ende 00:00) bis Zeile Tag 23:00 (Ende 24:00)."""
    von = _zeit.mktime((datetime.combine(tag, datetime.min.time()) - timedelta(hours=1)).timetuple())
    bis = von + 24 * 3600
    with svc._engine.begin() as conn:
        mid = conn.execute(text("SELECT id FROM statistics_meta WHERE statistic_id = :s"), {"s": sid}).scalar_one()
        s0, s1 = (conn.execute(text("SELECT sum FROM statistics WHERE metadata_id = :m AND start_ts = :t"),
                               {"m": mid, "t": t}).scalar_one() for t in (von, bis))
    return round(s1 - s0, 3)


# ── Proben ──────────────────────────────────────────────────────────────────

#: Juni ohne Sprung: Einspeisung 6 kWh × 30 Tage, PV-Gesamt 3,5 kWh × 6 h × 30 Tage (F01) — plus der Sprung.
SOLL = {"sensor.einsp": 180.0 + SPRUNG_KWH, "sensor.pv_gesamt": 630.0 + SPRUNG_KWH}


@pytest.mark.parametrize("lesart", ["voll", "lesart1"])
async def test_jeder_monatsweg_nennt_has_zahl_und_das_kanal_delta(lesart):
    """(a)–(f) nennen 430 bzw. 880 = HA-Leser ohne Deckel = Kanal-Δ; der Deckel hätte hier gebissen (179 / 626,5)."""
    async with _datenstand_sprung(lesart) as ds:
        m = await _miss_wege(ds)
    einsp, pv = SOLL["sensor.einsp"], SOLL["sensor.pv_gesamt"]
    assert m["ha_leser_mit_deckel"] == {"sensor.einsp": 179.0, "sensor.pv_gesamt": 626.5}   # die Probe ist scharf
    assert m["ha_leser_ohne_deckel"] == SOLL
    assert m["kanal_delta"] == SOLL
    assert (m["a_cockpit_monat"]["einsp"], m["a_cockpit_monat"]["pv"]) == (einsp, pv)
    for weg in ("b_aus_ha_laden", "c_alle_monatswerte"):
        assert (m[weg]["sensor.einsp"], m[weg]["sensor.pv_gesamt"]) == (einsp, pv), weg
    assert (m["d_import_vorschau"]["Einspeisung"], m["d_import_vorschau"]["PV Erzeugung Gesamt"]) == (einsp, pv)
    assert m["f_monatsabschluss_vorschlag"]["einspeisung_kwh"] == [("ha_statistics", einsp)]
    assert (m["e_sammelimport"]["einsp"], m["e_sammelimport"]["pv"]) == (einsp, pv)


@pytest.mark.parametrize("lesart", ["voll", "lesart1"])
async def test_tag_gleich_monat_gleich_ha_und_der_checker_nennt_den_sprung(lesart):
    """N-586-Lesart: der Kanal-Tag 15.06. trägt HAs Tag (6 + 250), Σ der Juni-Tage = Monat — auch im Lesart-1-Monat;
    ``ha_zaehlersprung`` nennt beide Sensoren mit Stunde und Menge."""
    async with _datenstand_sprung(lesart) as ds:
        m = await _miss_wege(ds)
    assert m["tage_juni"] == 30
    assert m["tag_15_einsp"] == m["ha_tag_15_einsp"] == 6.0 + SPRUNG_KWH
    assert m["summe_tage_einsp"] == SOLL["sensor.einsp"] == m["b_aus_ha_laden"]["sensor.einsp"]
    assert m["summe_tage_erzeugung"] == SOLL["sensor.pv_gesamt"] == m["a_cockpit_monat"]["pv"]
    ((kat, meldung, details),) = m["checker_ha_zaehlersprung"]
    assert kat == "ha_zaehlersprung" and meldung.startswith("2 Zählersprung")
    for sid in SPRUNG_SENSOREN:
        assert f"{sid} am 15.06.2026, Stunde ab 12:00: +250,0 kWh" in details
