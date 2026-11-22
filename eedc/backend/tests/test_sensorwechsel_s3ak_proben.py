"""Sensorwechsel mit Grund, Korrekturrunde 3a-K — Proben der tragenden Stellen (Bauplan §10 Nr. 32–38). Seit Weg B, Sitzung B3a,
ohne die Proben der Korrektur selbst (Zählerstände und Kanal im Intervall, R2, Tage-Liste, Merker, Leser «verworfen», Vorschau =
Lauf, Sätze); geblieben: die abhängigen abgeleiteten Kanäle je Feld, «Tage neu bilden» ohne Abruf und die Vorschau der Werkbank.

Je Probe ein Sprengsatz im selben Test (der Prüfling mit einem bewusst falschen Baustein muss rot werden). Feste Zeit
(``ZEIT``/``JETZT`` aus ``test_kanal_nachfuellen``), keine Uhr. Lagen und Helfer aus ``test_sensorwechsel_s3_korrektur``
(A-B-A an ``basis:einspeisung``: richtig ``sensor.einsp``, falsch ``sensor.falsch`` ab F, zurück ab AB; MQTT an
``basis:netzbezug``).

Äquivalente Mutanten (benannt, nicht beprobt):

* ``vergiss`` allein bzw. ``merke_neu`` allein weg (Schritt 1): ``vergiss`` erzwingt ein Neuladen der Wechsel aus der
  Datenbank (die Zeile ist geflusht), ``merke_neu`` hängt sie in die geladene Liste — eins von beiden genügt; beide weg
  ist beprobt (``test_merker_*``).
* ``fuehre_aus`` ohne die Bedingung «nur mit Home Assistant» bei ``tage``: ``lage`` bildet ohne Home Assistant keine
  Tage-Liste (beprobt) — die zweite Sicherung ändert nichts, solange die erste steht.
* ``_wie_vorher`` ohne Zählung: die Zahl steht nur im Zustand ``behalten``.

Schwesterdateien: test_sensorwechsel_s3_korrektur.py, test_werkbank_verwerfen_vor_quellbeginn.py,
test_kanal_verworfen_bewusst_leer.py.
"""

from __future__ import annotations

import dataclasses
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import and_, delete, func, insert, select

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import ART_SUM, FAMILIE_ABGELEITET, Kanal, KanalQuelle, KanalStatistik
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services import verwerfen_vor_quellbeginn as vq
from backend.services.kanal import korrektur as kk
from backend.services.kanal import lesen, merken
from backend.services.kanal.nachfuellen import nachfuellen_spiegel
from backend.services.snapshot.keys import _sensor_key_to_mqtt_key
from backend.services.zuordnung_wechsel import korrektur as kr
from backend.services.zuordnung_wechsel import korrektur_lauf as kl
from backend.tests import ha_lts_helfer
from backend.tests.test_kanal_nachfuellen import (  # noqa: F401 — Fixtures
    ZEIT,
    _ts,
    datei,
    ha,
)
from backend.tests.test_sensorwechsel_s3_korrektur import AB, EINSP, F, _aba
from backend.tests.test_werkbank_verwerfen_kommt_nicht_zurueck import _quellen

H = 3600


async def _anlage(s, aid) -> Anlage:
    return (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()


async def _snapshots(sitzungen, aid, key, zeiten, werte=None) -> None:
    async with sitzungen() as s:
        await s.execute(insert(SensorSnapshot), [
            {"anlage_id": aid, "sensor_key": key, "zeitpunkt": z, "wert_kwh": (werte or {}).get(z, 1.0 + i), "quelle": "probe"}
            for i, z in enumerate(zeiten)])


# ── Zählerstände: [falsch_seit, ab) — beide Grenzen ─────────────────────────


# ── Tage-Liste (§7 Nr. 10, §10 Nr. 35) ─────────────────────────────────────


# ── Bestand: nur Tage, deren Fenster ganz im Intervall liegt (von_tag) ──────


# ── Wechsel-Zeile: aufgehoben_durch und sein Fenster ───────────────────────


# ── Kanal: Fortsetzung nach ab (MQTT, Zeilen nach ab schon geschrieben) ─────


# ── Kanal: R2-Referenz mit dem Versatz ihres Abschnitts, Rückfall auf h0, spätere andere Quellen ──


# ── Kanal: nur falsche Abschnitte, Teil im Intervall, Beginn des falschen Teils ─


# ── Füllen bis zum Soll-Ende (bis_ts), auch ohne Spiegelzeile danach ───────


# ── Merker (Schritt 5) und die Wechsel-Merkliste der Sitzung ───────────────


# ── Leser: «gilt hier» und die Grenze bis ──────────────────────────────────


# ── BewusstLeer: die erste Zeile je Abschnitt (Lader) ──────────────────────


# ── Vorschau = Lauf (Zählerstände bis zum wirksamen ab, Tage) ──────────────


async def _async(wert):
    return wert


# ── Abhängige abgeleitete Kanäle (§10 Nr. 34) ──────────────────────────────


async def _invs(sitzungen, aid) -> dict[str, int]:
    async with sitzungen() as s:
        out = {}
        for typ, param in (("wallbox", None), ("e-auto", None), ("waermepumpe", None), ("speicher", None),
                           ("pv-module", None)):
            i = Investition(anlage_id=aid, typ=typ, bezeichnung=typ, parameter=param)
            s.add(i)
            await s.flush()
            out[typ] = i.id
    return out


async def test_abhaengige_abgeleitete_je_feld(datei):
    """Die Tabelle der Abhängigkeit (Bauplan §10 Nr. 34) — und welche Kanal-Schlüssel zu einer Familie gehören."""
    sitzungen, _p, aid, gas = datei
    ids = await _invs(sitzungen, aid)
    wb, ea, wp, sp, pv = (ids[t] for t in ("wallbox", "e-auto", "waermepumpe", "speicher", "pv-module"))
    erwartet = {
        "basis:einspeisung": {kk.PV_ANTEIL, kk.KOSTEN}, "basis:netzbezug": {kk.PV_ANTEIL, kk.KOSTEN},
        "basis:pv_gesamt": {kk.KOSTEN}, "basis:strompreis": {kk.KOSTEN},
        f"inv:{wb}:ladung_kwh": {kk.PV_ANTEIL}, f"inv:{ea}:ladung_pv_kwh": {kk.PV_ANTEIL},
        f"inv:{wp}:stromverbrauch_kwh": {f"{kk.MODUS_STROM}{wp}"}, f"inv:{wp}:strom_heizen_kwh": {f"{kk.MODUS_STROM}{wp}"},
        f"inv:{sp}:ladung_kwh": set(), f"inv:{pv}:pv_erzeugung_kwh": {kk.KOSTEN},
        f"inv:{wb}:ladung_pv_kwh": None, f"inv:{gas}:zaehlerstand": None, "inv:9999:ladung_kwh": None,
        "basis:gaszaehler": None, "zustand:inv:1:x": None,
    }
    async with sitzungen() as s:
        ist = {key: await kk.abhaengige_abgeleitete(s, aid, key) for key in erwartet}
    assert {k: (set(v) if v is not None else None) for k, v in ist.items()} == erwartet
    f = frozenset({kk.PV_ANTEIL, f"{kk.MODUS_STROM}{wp}"})
    assert kk.gehoert_zu(f, f"abgeleitet:inv:{wb}:ladung_pv_kwh")
    assert kk.gehoert_zu(f, f"abgeleitet:inv:{wp}:modus_strom_heizen_kwh")
    assert not kk.gehoert_zu(f, "abgeleitet:basis:kosten_netzbezug")
    assert not kk.gehoert_zu(f, f"abgeleitet:inv:{wp + 1}:modus_strom_heizen_kwh")
    assert not kk.gehoert_zu(frozenset(), f"abgeleitet:inv:{wb}:ladung_pv_kwh")
    assert kk.gehoert_zu(None, "abgeleitet:irgendwas")


# ── Tage neu bilden: Wetter und Börsenpreis bleiben, kein Abruf, Performance Ratio aus ihnen (§10 Nr. 32) ──


TAG = date(2026, 3, 20)                      # vor dem Kanal (Bestandstag)
STUNDE_VORHER = {h: {"temperatur_c": 5.0 + h / 10, "globalstrahlung_wm2": float(10 * h), "bewoelkung_prozent": 50.0,
                     "niederschlag_mm": 0.0 if h % 2 else None, "wetter_code": 3,
                     "boersenpreis_cent": (None if h == 5 else (-1.5 if h in (11, 12) else 8.25))} for h in range(24)}
TAG_VORHER = {"temperatur_min_c": 4.9, "temperatur_max_c": 7.4, "strahlung_summe_wh_m2": 2760.0,
              "gti_summe_wh_m2": 800.0, "boersenpreis_avg_cent": 7.0, "boersenpreis_min_cent": None,
              "negative_preis_stunden": 2}


async def _tag_mit_wetter(sitzungen, aid):
    async with sitzungen() as s:
        a = await _anlage(s, aid)
        a.latitude, a.longitude = 51.0, 7.0
        s.add(TagesZusammenfassung(anlage_id=aid, datum=TAG, komponenten_kwh={"einspeisung": 5.0}, performance_ratio=0.5,
                                   einspeisung_neg_preis_kwh=9.9, **TAG_VORHER))
        for h, w in STUNDE_VORHER.items():
            s.add(TagesEnergieProfil(anlage_id=aid, datum=TAG, stunde=h, pv_kw=1.0, einspeisung_kw=0.4, **w))


def _neubau_wie_aggregator(abrufe: dict):
    """Fake von ``_reparatur_aggregat``: holt Wetter und Preise über dieselben Helfer wie der Aggregator, schreibt die Zeilen
    neu (PV 0,5 kW in 16 Stunden = 8 kWh) — ohne Schalter mit dem, was der Abruf liefert."""
    async def neubau(anlage, tag, db):
        from backend.services import live_tagesverlauf_service
        from backend.services.energie_profil import _helpers

        # wie ``hole_tagesverlauf`` → ``get_tagesverlauf`` (Börsenpreis-Rückfall der Kurve) und ``lade_stammdaten``
        abrufe["kurve_boerse"] = await live_tagesverlauf_service._boersenpreis_ha(anlage, datetime.combine(tag, datetime.min.time()))
        wetter = await _helpers._get_wetter_ist(anlage, tag)
        preise = await _helpers._get_strompreis_stunden(anlage, {}, tag)
        await db.execute(delete(TagesEnergieProfil).where(TagesEnergieProfil.datum == tag))
        await db.execute(delete(TagesZusammenfassung).where(TagesZusammenfassung.datum == tag))
        for h in range(24):
            w = wetter.get(h, {})
            db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=tag, stunde=h, pv_kw=0.5 if h < 16 else None,
                                      temperatur_c=w.get("temperatur_c"), globalstrahlung_wm2=w.get("globalstrahlung_wm2"),
                                      bewoelkung_prozent=w.get("bewoelkung_prozent"), niederschlag_mm=w.get("niederschlag_mm"),
                                      wetter_code=w.get("wetter_code"), boersenpreis_cent=preise.boerse.get(h)))
        werte = [v for v in preise.boerse.values() if v is not None]
        tz = TagesZusammenfassung(anlage_id=anlage.id, datum=tag, komponenten_kwh={"einspeisung": 6.0},
                                  temperatur_min_c=min((w["temperatur_c"] for w in wetter.values()), default=None),
                                  boersenpreis_min_cent=min(werte) if werte else None, gti_summe_wh_m2=None)
        db.add(tz)
        abrufe["boerse_gesehen"] = dict(preise.boerse)
        return tz, "lts"
    return neubau


@pytest.mark.parametrize("sprengsatz", [None, "abruf_an", "nichts_zurueck", "nur_leere_fuellen", "pr_alt"])
async def test_tage_neu_bilden_wetter_und_preis_wie_vorher_ohne_abruf(datei, monkeypatch, sprengsatz):
    from backend.services import repair_orchestrator, strompreis_markt_service
    from backend.services.energie_profil import _helpers

    sitzungen, _p, aid, _g = datei
    await _tag_mit_wetter(sitzungen, aid)
    abrufe = {"wetter": 0, "boerse": 0}

    async def wetter_abruf(anlage, url, base_params, pv_module=None, timeout=15.0, *, streng=False):
        abrufe["wetter"] += 1
        return {TAG: {h: {"temperatur_c": 99.0, "globalstrahlung_wm2": 999.0, "bewoelkung_prozent": 1.0,
                          "niederschlag_mm": 9.0, "wetter_code": 99, "gti_wm2": 50.0} for h in range(24)}}

    async def boerse_abruf(datum, markt="DE"):
        abrufe["boerse"] += 1
        return {h: -5.0 for h in range(24)}

    monkeypatch.setattr(_helpers, "_fetch_wetter", wetter_abruf)
    monkeypatch.setattr(strompreis_markt_service, "fetch_marktpreise", boerse_abruf)
    monkeypatch.setattr(repair_orchestrator, "_reparatur_aggregat", _neubau_wie_aggregator(abrufe))
    if sprengsatz in ("abruf_an", "nur_leere_fuellen"):
        monkeypatch.setattr(_helpers, "ohne_abruf", lambda boerse: nullcontext())
    if sprengsatz == "nichts_zurueck":
        async def nichts(*a, **kw):
            return 0
        monkeypatch.setattr(kl, "_wetter_und_preis_wie_vorher", nichts)
    elif sprengsatz == "nur_leere_fuellen":                # die Regel von 3a: nur was der Abruf nicht lieferte
        def nur_leere(row, alt, spalten):
            for x in spalten:
                if getattr(row, x) is None and alt.get(x) is not None:
                    setattr(row, x, alt[x])
            return 0
        monkeypatch.setattr(kl, "_wie_vorher", nur_leere)
    elif sprengsatz == "pr_alt":
        async def keine_pr(*a, **kw):
            return None
        monkeypatch.setattr(kl, "_performance_ratio", keine_pr)
    async with sitzungen() as s:
        await kl.anlegen(s, "wetter", aid, EINSP, [TAG])
    z = await kl.tage_neu_bilden(sitzungen, "wetter")
    async with sitzungen() as s:
        tz = (await s.execute(select(TagesZusammenfassung).where(TagesZusammenfassung.datum == TAG))).scalar_one()
        std = {r.stunde: {x: getattr(r, x) for x in kl.STUNDE_ABRUF} for r in (await s.execute(
            select(TagesEnergieProfil).where(TagesEnergieProfil.datum == TAG))).scalars().all()}
    assert z["status"] == kl.FERTIG and not z["fehler"] and tz.komponenten_kwh == {"einspeisung": 6.0}
    kein_abruf = abrufe["wetter"] == 0 and abrufe["boerse"] == 0
    wie_vorher = std == STUNDE_VORHER and {x: getattr(tz, x) for x in kl.TAG_ABRUF} == TAG_VORHER
    pr_neu = tz.performance_ratio is not None and abs(tz.performance_ratio - 8.0 / (800.0 * 10.0 / 1000)) < 1e-9
    erwartet = {None: (True, True, True), "abruf_an": (False, True, True), "nichts_zurueck": (True, False, False),
                "nur_leere_fuellen": (False, False, True), "pr_alt": (True, True, False)}[sprengsatz]
    assert (kein_abruf, wie_vorher, pr_neu) == erwartet, (abrufe, tz.performance_ratio)
    if sprengsatz is None:
        # der Aggregator sah die gespeicherten Börsenpreise der Stunden (für die Einspeisung bei negativem Preis)
        gespeichert = {h: w["boersenpreis_cent"] for h, w in STUNDE_VORHER.items() if w["boersenpreis_cent"] is not None}
        assert abrufe["boerse_gesehen"] == gespeichert and abrufe["kurve_boerse"] == gespeichert


async def test_ohne_abruf_gilt_nur_im_block(datei):
    """Der Schalter gilt nur im Block (Normalbetrieb unverändert) — danach ruft der Helfer wieder ab."""
    from backend.services.energie_profil import _helpers

    with _helpers.ohne_abruf({TAG: {3: 1.5}}):
        assert _helpers._GESPEICHERTE_BOERSE.get() == {TAG: {3: 1.5}}
    assert _helpers._GESPEICHERTE_BOERSE.get() is None


# ── Wortlaute der Vorschau mit und ohne Home Assistant (§10 Nr. 37) ────────


