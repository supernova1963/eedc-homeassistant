"""N-623 — trägt der Anlagen-PV-Zähler den Tag, behalten gemessene Erzeuger ihren Tageswert.

**Der Fund.** Seit v4.0.51 verwarf die Tagesebene im Aggregat-Fall (Anlagenzähler +
Erzeuger, von denen mindestens einer keinen eigenen Zähler hat) die Messung der
Erzeuger mit eigenem Zähler und gab jedem den kWp-Anteil: ein Balkonkraftwerk mit
Zähler stand mit 1,56 statt 3,0 kWh im Tag, Süd/West mit 11,67/7,78 statt 10,8/7,2.

**Die Regel** (Bauplan N-623 Fassung 2, Fable-gegengeprüft; Layer:
``core/berechnungen/pv_tages_praezedenz.py``):

1. Tageswert eines Zählers = Σ aller seiner brauchbaren Slots des Tages (BKW mit
   Kindern: Rest je Slot, E4); er geht in keine Stunde, die Stundenachse bleibt die
   Aggregat-Summe.
2. Gemessen ist ein Erzeuger, wenn kein Slot verworfen wurde (R3, R4), er keinen
   Tagesreset trägt und seine unsichere Energie (Anlagen-Energie der Stunden ohne
   eigenen Slot + eigene Bündel-Energie) höchstens 1 % des Tages ist.
3. Auflösung auf Träger-Ebene; die übrigen Träger teilen den Rest nach kWp.
4. Abgleich statt Rückfall: Σ gemessen > Aggregat (oder keine Lücke und ≠) ⇒ die
   gemessenen Werte werden mit Aggregat / Σ gemessen skaliert, Σ Keys == Aggregat.
5. Marke ``kwp_anteil`` nur für Lücken.

**Datenstand wie im Betrieb** — die Bausteine der Abnahme-Matrix
(``pv_achse_matrix.py``): echter ``HAStatisticsService`` auf dem Recorder-Schema,
Tageszeilen über den echten ``aggregate_day``; der Snapshot-Pfad (Standalone) über
``sensor_snapshots``. Die Grundformen (Gesamt + BKW-Zähler, BKW ohne Nachtzeilen,
BKW mit Modul-Kindern) prüft die Matrix selbst je Tag (Zellen ``F03``, ``F08``,
``F09*-G`` × ``HA``/``SA`` × ``I4``); diese Datei hält die Ränder fest, die die
Matrix nicht sät: Bündel, Abriss, Sprung, Tagesreset, Über-Fall, Marken.

Raten (je Produktionsstunde 10–16 Uhr): Süd 2,0 (6 kWp) · West 1,0 (4 kWp) ·
Balkon 0,5 (0,8 kWp) · Anlagenzähler 3,5 ⇒ je Tag 12 / 6 / 3, Σ 21.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy import delete, insert, select

from backend.core.berechnungen.pv_tages_praezedenz import (
    DAEMMERUNGSREST_ANTEIL,
    gemessene_tageswerte,
    loese_aggregat_tag_auf,
)
from backend.models.investition import Investition
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.tests import pv_achse_matrix as mx

TAG = date(2026, 6, 10)
FOLGETAG = date(2026, 6, 11)


def _um(tag: date, h: int) -> datetime:
    return datetime.combine(tag, datetime.min.time()) + timedelta(hours=h)


async def _lauf(form: mx.Form, *, abweichung: Optional[dict] = None, tage=(TAG,),
                snapshot: bool = False, nach_seed=None) -> dict:
    """Seed + ``aggregate_day`` je Tag; je Tag Keys je Gerät, Σ Keys, Σ Stunden, Marken."""
    verz = tempfile.mkdtemp(prefix="eedc-n623-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            aid, ids = await mx.seed_anlage(db, form)
            if snapshot:
                await mx.seed_snapshots(db, form, aid, ids)
                svc = mx._ha_aus()
            else:
                svc = mx.seed_ha(form, abweichung=abweichung)
            if nach_seed is not None:
                await nach_seed(db, aid, ids)
            rev = {str(v): k for k, v in ids.items()}
            with mx._umgebung(svc):
                await mx.aggregiere_tage(db, form, aid, tage)
                gemessen = await mx.miss_tage(db, aid, ids, tage)
                out = {}
                for tag in tage:
                    tz = (await db.execute(select(TagesZusammenfassung).where(
                        TagesZusammenfassung.anlage_id == aid, TagesZusammenfassung.datum == tag))).scalar_one()
                    marken = set()
                    for k, eintrag in (tz.source_provenance or {}).items():
                        if not k.startswith("komponenten_kwh.") or not isinstance(eintrag, dict):
                            continue
                        if eintrag.get("abgeleitet") == "kwp_anteil":
                            marken.add(rev.get(k.rpartition("_")[2], k))
                    d = gemessen[tag.isoformat()]
                    out[tag] = {"keys": d["keys"], "summe_keys": d["summe_keys"],
                                "stunden": d["stunden_pv"], "marken": marken}
                return out
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


def _je(tag_messung: dict, **soll: float) -> None:
    for name, wert in soll.items():
        ist = tag_messung["keys"].get(name, 0.0)
        assert ist == pytest.approx(wert, abs=0.01), f"{name}: {ist} statt {wert} · {tag_messung}"


def _invariante(tag_messung: dict, summe: float = 21.0) -> None:
    assert tag_messung["summe_keys"] == pytest.approx(summe, abs=0.02), tag_messung
    assert tag_messung["stunden"] == pytest.approx(summe, abs=0.02), tag_messung


F03 = mx.FORMEN["F03"]   # Gesamt + BKW-Zähler, Strings ohne
F02 = mx.FORMEN["F02"]   # Gesamt + alle drei
F05 = mx.FORMEN["F05"]   # Gesamt + Strings mit, BKW ohne


# ── P1 Grundfall · P11 Snapshot-Pfad · P10 Marken ──────────────────────────


async def test_p1_grundfall_bkw_behaelt_seinen_zaehlerwert():
    t = (await _lauf(F03))[TAG]
    _je(t, **{"Süd": 10.8, "West": 7.2, "Balkon": 3.0})
    _invariante(t)


async def test_p10_marken_nur_fuer_luecken():
    t = (await _lauf(F03))[TAG]
    assert t["marken"] == {"Süd", "West"}


async def test_p11_snapshot_pfad_rechnet_dasselbe():
    t = (await _lauf(F03, snapshot=True))[TAG]
    _je(t, **{"Süd": 10.8, "West": 7.2, "Balkon": 3.0})
    assert t["marken"] == {"Süd", "West"}


# ── P2 Zähler mit fehlenden Zeilen ohne Erzeugung ──────────────────────────


async def test_p2_nur_22_uhr_fehlt_bkw_bleibt_gemessen():
    """Die Zeile 22:00 fehlt: die Stunde ohne eigenen Slot hat keine Anlagen-Energie —
    keine unsichere Energie, der Zähler bleibt gemessen (Deckung „jede Aggregat-Stunde"
    hätte ihn verworfen, Gegenprüfung W1)."""
    t = (await _lauf(F03, abweichung={"sensor.pv_balkon": (None, lambda u: u.hour == 22)}))[TAG]
    _je(t, **{"Süd": 10.8, "West": 7.2, "Balkon": 3.0})
    _invariante(t)


# ── P3 Bündel im Anlagenzähler ─────────────────────────────────────────────


async def test_p3_aggregat_buendel_bkw_zaehlt_alle_eigenen_slots():
    """Die Zeile 12:00 des Anlagenzählers fehlt — ihre Energie steht im Slot 13:00 (R1).
    Der BKW-Wert ist trotzdem die Σ ALLER eigenen Slots (3,0), nicht nur der Stunden, in
    denen das Aggregat einen Slot hat (2,5 — Gegenprüfung W2)."""
    t = (await _lauf(F03, abweichung={"sensor.pv_gesamt": (None, lambda u: u.hour == 12)}))[TAG]
    _je(t, **{"Süd": 10.8, "West": 7.2, "Balkon": 3.0})
    _invariante(t)


# ── P4 alle mit Zähler, zwei Bündel ────────────────────────────────────────


async def test_p4_alle_mit_zaehler_gesamt_und_sued_zeile_fehlen():
    """Gesamt- und Süd-Zeile 12:00 fehlen: der Tag fällt auf das Aggregat (Süd ohne Slot
    in einer Stunde). Süd trägt ein Bündel ⇒ unsicher ⇒ Lücke; West und Balkon behalten
    ihre Messung, Süd bekommt den Rest. Σ Keys == Σ Stunden == 21."""
    keine_12 = (None, lambda u: u.hour == 12)
    t = (await _lauf(F02, abweichung={"sensor.pv_gesamt": keine_12, "sensor.pv_sued": keine_12}))[TAG]
    _je(t, **{"Süd": 12.0, "West": 6.0, "Balkon": 3.0})
    _invariante(t)
    assert t["marken"] == {"Süd"}


# ── P5 Abriss und Folgetag mit Bündel · P6 Abriss mit kleiner Lücke ─────────


def _sued_reisst_ab(u: datetime) -> bool:
    """Der Süd-Zähler liefert am TAG ab 13:00 nichts mehr und am FOLGETAG erst ab 10:00."""
    return _um(TAG, 13) <= u < _um(FOLGETAG, 10)


async def test_p5_abriss_und_folgetag_mit_buendel():
    """TAG: Süd hat ab 13:00 keinen Slot, die Anlage erzeugt in diesen Stunden ⇒ unsicher ⇒
    Lücke. FOLGETAG: Süds erster Slot trägt die Energie von gestern Nachmittag (Bündel) ⇒
    unsicher ⇒ Lücke. An beiden Tagen 12 / 6 / 3."""
    out = await _lauf(F02, abweichung={"sensor.pv_sued": (None, _sued_reisst_ab)}, tage=(TAG, FOLGETAG))
    for tag in (TAG, FOLGETAG):
        _je(out[tag], **{"Süd": 12.0, "West": 6.0, "Balkon": 3.0})
        _invariante(out[tag])


async def test_p6_abriss_mit_kleiner_luecke_teilen_sued_und_bkw_den_rest():
    """Süd und West mit Zähler, Balkon ohne, Süd reißt 13:00 ab: West gemessen (6), Süd und
    Balkon teilen den Rest 15 nach kWp (6 : 0,8)."""
    t = (await _lauf(F05, abweichung={"sensor.pv_sued": (None, _sued_reisst_ab)}))[TAG]
    _je(t, **{"Süd": 15 * 6 / 6.8, "West": 6.0, "Balkon": 15 * 0.8 / 6.8})
    _invariante(t)


# ── P7 ohne Aussage am Tag: Rückfall auf kWp ───────────────────────────────

_ALLE_KWP = {"Süd": 21 * 6 / 10.8, "West": 21 * 4 / 10.8, "Balkon": 21 * 0.8 / 10.8}


async def test_p7_zaehlersprung_sperrt_den_tageswert():
    """Der BKW-Zähler springt um 18:00 um 5 kWh zurück (R4 verwirft den Slot): der Tag hat
    keine Aussage über das BKW — Rückfall auf den kWp-Anteil (Preis der Tageswahl)."""
    def rate(u: datetime) -> float:
        if u == _um(TAG, 18):
            return -5.0
        return 0.5 if u.hour in mx.PROD_STUNDEN else 0.0
    t = (await _lauf(F03, abweichung={"sensor.pv_balkon": (rate, None)}))[TAG]
    _je(t, **_ALLE_KWP)
    _invariante(t)


async def test_p7_reihe_beginnt_am_tag():
    """Der BKW-Zähler entsteht am TAG um 11:00 — die Stunden davor ohne eigenen Slot tragen
    Anlagen-Energie ⇒ unsicher ⇒ Rückfall auf den kWp-Anteil."""
    t = (await _lauf(F03, abweichung={"sensor.pv_balkon": (None, lambda u: u < _um(TAG, 11))}))[TAG]
    _je(t, **_ALLE_KWP)
    _invariante(t)


async def test_p7_tagesreset_im_snapshot_pfad_sperrt_den_tageswert():
    """Standalone: der BKW-Zähler ist ein Tagesreset-Zähler (utility_meter, um 00:00 auf 0)
    — der Tageswert ist abgelehnt (Rücksprung-Entscheid 28.08.), Rückfall auf kWp."""
    async def tagesreset(db, aid, ids):
        sk = f"inv:{ids['Balkon']}:pv_erzeugung_kwh"
        await db.execute(delete(SensorSnapshot).where(SensorSnapshot.sensor_key == sk))
        zeilen, t = [], mx.REIHE_VON
        stand = 0.0
        while t <= mx.REIHE_BIS:
            if t.hour == 0:
                stand = 0.0
            zeilen.append({"anlage_id": aid, "sensor_key": sk, "zeitpunkt": t, "wert_kwh": round(stand, 4),
                           "quelle": "mqtt_inbound"})
            stand += 0.5 if t.hour in mx.PROD_STUNDEN else 0.0
            t += timedelta(hours=1)
        await db.execute(insert(SensorSnapshot), zeilen)
        await db.commit()
    t = (await _lauf(F03, snapshot=True, nach_seed=tagesreset))[TAG]
    _je(t, **_ALLE_KWP)


# ── P8 Über-Fall: Abgleich mit gemeinsamem Faktor ──────────────────────────


async def test_p8_summe_gemessen_ueber_aggregat_wird_abgeglichen():
    """Süd misst 19, Balkon 3 (Σ 22), der Anlagenzähler 21, West ohne: beide gemessenen
    Werte mit 21/22 skaliert, West 0 — Σ Keys == 21, das Verhältnis Süd : Balkon bleibt."""
    form = mx.Form("P8a", "Süd 19 + Balkon 3 gegen Gesamt 21, West ohne",
                   (mx.Geraet("Süd", "pv-module", 6.0, 19 / 6, True), mx._west(), mx._bkw(True)), 3.5)
    t = (await _lauf(form))[TAG]
    _je(t, **{"Süd": 19 * 21 / 22, "West": 0.0, "Balkon": 3 * 21 / 22})
    _invariante(t)
    assert t["marken"] == {"West"}


async def test_p8_knapp_ueber_aggregat_ohne_rueckfall_auf_kwp():
    """Süd 12 + West 6,2 gegen Gesamt 18, Balkon ohne: Faktor 18/18,2 (nahe 1) statt eines
    Sprungs auf die kWp-Verteilung (10 / 6,67 / 1,33)."""
    form = mx.Form("P8b", "Süd 12 + West 6,2 gegen Gesamt 18, Balkon ohne",
                   (mx._sued(True), mx.Geraet("West", "pv-module", 4.0, 6.2 / 6, True), mx._bkw()), 3.0)
    t = (await _lauf(form))[TAG]
    _je(t, **{"Süd": 12 * 18 / 18.2, "West": 6.2 * 18 / 18.2, "Balkon": 0.0})
    _invariante(t, 18.0)


# ── P9 Balkonkraftwerk ohne Zähler, beide Kinder messen ────────────────────


async def test_p9_bkw_ohne_zaehler_kinder_messen():
    """Das BKW hat an seine Kinder abgetreten und keinen eigenen Zähler: Träger sind die
    Kinder mit ihren Messungen (1,2 / 1,8), das BKW bekommt keinen Anteil; Süd/West teilen
    den Rest 18 nach kWp."""
    form = mx.Form("P9d", "Gesamt + BKW ohne Zähler, beide Kinder mit, Strings ohne",
                   (mx._sued(), mx._west(), mx._bkw(), *mx._kinder(True, True)), 3.5)
    t = (await _lauf(form))[TAG]
    _je(t, **{"Süd": 10.8, "West": 7.2, "Balkon": 0.0, "Kind 1": 1.2, "Kind 2": 1.8})
    _invariante(t)


# ── P12 Unverändert ────────────────────────────────────────────────────────


async def test_p12_nur_gesamtzaehler_unveraendert():
    t = (await _lauf(mx.FORMEN["F01"]))[TAG]
    _je(t, **_ALLE_KWP)
    assert t["marken"] == {"Süd", "West", "Balkon"}


async def test_p12_alle_lueckenlos_unveraendert():
    t = (await _lauf(F02))[TAG]
    _je(t, **{"Süd": 12.0, "West": 6.0, "Balkon": 3.0})
    assert t["marken"] == set()


# ── P13 Layer: Σ der Auflösung == Aggregat ─────────────────────────────────


def _inv(inv_id: int, typ: str, kwp: float, parent: Optional[int] = None):
    ns = SimpleNamespace(id=inv_id, typ=typ, leistung_kwp=kwp, parameter={}, parent_investition_id=parent,
                         aktiv=True, anschaffungsdatum=None, stilllegungsdatum=None)
    ns.ist_aktiv_an = Investition.ist_aktiv_an.__get__(ns)
    return ns


_INVS = [_inv(1, "pv-module", 6.0), _inv(2, "pv-module", 4.0), _inv(3, "balkonkraftwerk", 0.8)]


@pytest.mark.parametrize("aggregat,gemessen", [
    (21.0, {}), (21.0, {"3": 3.0}), (21.0, {"1": 12.0, "3": 3.0}), (21.0, {"1": 19.0, "3": 3.0}),
    (21.0, {"1": 12.0, "2": 6.0, "3": 3.0}), (21.0, {"1": 12.0, "2": 6.2, "3": 3.0}),
    (21.0, {"1": 0.0, "2": 0.0, "3": 0.0}), (0.0, {"3": 0.4}), (5.0, {"1": 0.0}),
])
def test_p13_summe_der_aufloesung_ist_das_aggregat(aggregat, gemessen):
    r = loese_aggregat_tag_auf(aggregat_kwh=aggregat, gemessen=gemessen, mit_zaehler=set(gemessen),
                               investitionen=_INVS, datum=TAG)
    assert sum(r.werte.values()) == pytest.approx(aggregat)
    assert set(r.werte) == {1, 2, 3}
    if sum(gemessen.values()) > 0:     # Regel 5: eine Messung trägt keine Marke
        assert not r.verteilt & {int(i) for i in gemessen}


def test_p13_ohne_erzeuger_kein_key():
    r = loese_aggregat_tag_auf(aggregat_kwh=21.0, gemessen={}, mit_zaehler=set(), investitionen=[], datum=TAG)
    assert r.werte == {} and r.verteilt == frozenset()


def test_p13_gemessen_grenze_ein_prozent():
    """Unsichere Energie genau an der Grenze bleibt gemessen, knapp darüber nicht."""
    grenze = DAEMMERUNGSREST_ANTEIL * 21.0
    basis = dict(aggregat_kwh=21.0, eigen_kwh={"3": 3.0}, eigen_stunden={"3": {10, 11, 12, 13, 14, 15}},
                 eigen_buendel_kwh={}, gesperrt=set())
    assert gemessene_tageswerte(aggregat_je_stunde={9: grenze, 10: 3.5}, **basis) == {"3": 3.0}
    assert gemessene_tageswerte(aggregat_je_stunde={9: grenze + 0.01, 10: 3.5}, **basis) == {}
