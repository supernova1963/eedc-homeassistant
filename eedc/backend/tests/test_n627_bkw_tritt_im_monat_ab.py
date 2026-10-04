"""N-627 — ein Balkonkraftwerk mit Modul-Kindern tritt im Monat ab, in jeder Form.

**Der Fund.** Im Monat ohne Abschluss (laufend oder vergangen) zählte Cockpit → Monat den
BKW-Zähler UND die gemessenen Kinder: 66,6 bzw. 72 statt 63 kWh im laufenden Juli, 666 / 720
statt 630 im Juni vor dem Abschluss — nach dem Abschluss stimmte es (630, die Monats-Fakten
lösen über ``pv_monatswerte.lade_pv_je_monat`` auf). Im abgeschlossenen Monat füllte die
HA-Statistik die BKW-Zeile (90) neben den Kindern.

**Die Regel** (ADR-002/P7 Stufe 2, P11; Bauplan PV-Achse T4): Der Monat tritt ab, in jeder
Form. Der Wert des Balkonkraftwerks füllt die Lücken seiner Kinder
(``core/berechnungen/pv_verteilung.py::bkw_kinder_luecken_kwh`` — dieselbe Formel im
abgeschlossenen Monat und in Cockpit → Monat), gemessene Kinder gewinnen, das BKW selbst trägt
weder die PV-Achse noch eine eigene Zeile. Ob es abtritt, entscheidet der Monat (im Monat
aktive Kinder). Auch der Tageswert-Rückfall der Monats-Fakten bucht sein Tages-Segment zu den
Modulen (Zusatz Master: vor = nach dem Abschluss). Der Tag bleibt bei E4.

Datenstand: Matrix-Bausteine — HA-Statistik + Tageszeilen über ``aggregate_day``, Juni über
„Aus HA laden" abgeschlossen. Raten je Tag: Süd 12 · West 6 · Balkon 3 (Kind 1: 1,2, Kind 2: 1,8).
"""

from __future__ import annotations

import shutil
import tempfile

import pytest

from backend.tests import pv_achse_matrix as mx


async def _messe(fid: str) -> dict:
    form = mx.FORMEN[fid]
    verz = tempfile.mkdtemp(prefix="eedc-n627-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            aid, ids = await mx.seed_anlage(db, form)
            svc = mx.seed_ha(form)
            with mx._umgebung(svc):
                await mx.aggregiere_tage(db, form, aid, mx.TAGE_JUNI + mx.TAGE_JULI)
                out = {
                    "laufend": await mx.miss_cockpit_monat(db, aid, mx.JULI),
                    "juni_vor": await mx.miss_cockpit_monat(db, aid, mx.JUNI),
                    "tageswert": await mx.miss_fakten(db, aid, ids, mx.JUNI, tageswerte=True),
                }
                await mx.schreibe_s1_aus_ha_laden(db, aid)
                out["juni_nach"] = await mx.miss_cockpit_monat(db, aid, mx.JUNI)
                out["fakten_nach"] = await mx.miss_fakten(db, aid, ids, mx.JUNI)
                return out
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.parametrize("fid", ["F09a-oG", "F09b-oG", "F09c-oG", "F09a-G", "F09b-G", "F09c-G"])
async def test_monat_tritt_ab_vor_und_nach_dem_abschluss(fid):
    m = await _messe(fid)
    # laufender Juli (drei Tage) — keine BKW-Zeile, PV-Achse 63
    assert m["laufend"]["pv"] == pytest.approx(63.0)
    assert not m["laufend"]["bkw"]
    # Juni vor dem Abschluss = nach dem Abschluss = 630, BKW-Zeile leer
    assert m["juni_vor"]["pv"] == pytest.approx(630.0)
    assert m["juni_nach"]["pv"] == pytest.approx(630.0)
    assert not m["juni_nach"]["bkw"]
    assert m["fakten_nach"]["bkw"] == pytest.approx(0.0)
    # Tageswert-Rückfall: das Segment des abgetretenen BKW steht bei den Modulen
    assert m["tageswert"]["pv_module"] == pytest.approx(630.0, abs=0.6)
    assert not m["tageswert"]["bkw"]


async def test_spaete_kinder_der_monat_entscheidet():
    """F10: Kinder ab 02.07. — der Juni trägt das BKW selbst (90), der Juli tritt ab (leer)."""
    m = await _messe("F10")
    assert m["juni_nach"]["bkw"] == pytest.approx(90.0)
    assert m["juni_vor"]["bkw"] == pytest.approx(90.0)
    assert not m["laufend"]["bkw"]
    assert m["laufend"]["pv"] == pytest.approx(63.0)
