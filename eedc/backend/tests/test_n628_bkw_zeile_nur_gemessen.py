"""N-628 — die BKW-Zeile des laufenden Monats nennt nur Gemessenes.

**Der Fund.** Trägt der Anlagenzähler den Tag, bekommt ein Balkonkraftwerk ohne eigenen
Zähler seinen kWp-Anteil am Rest als Tages-Key ``bkw_<id>`` — mit der Marke ``kwp_anteil``
(#406). Cockpit → Monat las im laufenden Monat Σ aller ``bkw_``-Keys als eigene
BKW-Erzeugung (4,68 kWh für drei Tage), im abgeschlossenen Monat steht dort nichts und der
Anteil in ``bkw_aus_anlagenwert_kwh`` (``monats_fakten/fakten.py``, IST-Quelle je Typ).

**Die Regel.** ``core/berechnungen/energie.py::bkw_gemessen_kwh_je_investition`` — Σ der
``bkw_``-Keys je Gerät ohne Marke; ``TagesMonatsSumme.bkw_gemessen_je_inv`` trägt sie in den
Monat, ``_collect_tagesebene_data`` bildet die Zeile daraus. Die PV-Summe bleibt unberührt.

Datenstand: Matrix-Bausteine (HA-Statistik + Tageszeilen über ``aggregate_day``; Standalone
über ``sensor_snapshots``), Cockpit → Monat über die echte Route.
"""

from __future__ import annotations

import shutil
import tempfile

import pytest

from backend.core.berechnungen import bkw_gemessen_kwh_je_investition
from backend.tests import pv_achse_matrix as mx


async def _laufend(form_id: str, *, standalone: bool = False) -> dict:
    form = mx.FORMEN[form_id]
    verz = tempfile.mkdtemp(prefix="eedc-n628-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            aid, ids = await mx.seed_anlage(db, form)
            if standalone:
                await mx.seed_snapshots(db, form, aid, ids)
                svc = mx._ha_aus()
            else:
                svc = mx.seed_ha(form)
            with mx._umgebung(svc):
                await mx.aggregiere_tage(db, form, aid, mx.TAGE_JULI)
                return await mx.miss_cockpit_monat(db, aid, mx.JULI)
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.parametrize("standalone", [False, True], ids=["HA", "Standalone"])
async def test_bkw_ohne_zaehler_hat_keine_eigene_zeile(standalone):
    """Anlagenzähler + Süd mit Zähler, West und Balkon ohne (F04): die Zeile ist leer, die PV 63."""
    m = await _laufend("F04", standalone=standalone)
    assert not m["bkw"]
    assert m["pv"] == pytest.approx(63.0)


@pytest.mark.parametrize("standalone", [False, True], ids=["HA", "Standalone"])
async def test_bkw_mit_zaehler_behaelt_seine_zeile(standalone):
    """Anlagenzähler + BKW-Zähler (F03): die Zeile ist die Messung, 3 × 3 kWh."""
    m = await _laufend("F03", standalone=standalone)
    assert m["bkw"] == pytest.approx(9.0)


def test_layer_marke_trennt_messung_und_anteil():
    komp = {"bkw_7": 1.56, "bkw_8": 3.0, "pv_1": 10.0, "pv_gesamt": 21.0}
    prov = {"komponenten_kwh.bkw_7": {"abgeleitet": "kwp_anteil"}, "komponenten_kwh.pv_1": {"abgeleitet": "kwp_anteil"}}
    assert bkw_gemessen_kwh_je_investition(komp, prov) == {"8": 3.0}
    assert bkw_gemessen_kwh_je_investition(komp, None) == {"7": 1.56, "8": 3.0}
    assert bkw_gemessen_kwh_je_investition(None, prov) == {}
