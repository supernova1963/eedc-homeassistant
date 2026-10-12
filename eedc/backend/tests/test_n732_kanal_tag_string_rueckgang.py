"""N-732 — Cockpit → Tag am Kanal-Tag: ein String-Zähler, dessen HA-``sum`` fällt, verteilt den Gesamtzähler nicht mehr falsch.

Am HEAD `7fb9b026` gemessen (Form F05 der PV-Achsen-Matrix: Gesamtzähler, Süd und West mit Zähler, Balkon ohne; echte
HA-Statistik, Kanal-Spiegel, ``aggregate_day``, ``baue_tage_werte``): Süd-``sum`` fällt am 15.06. um 50 kWh ⇒ Tages-Δ −38.
Der negative Wert ging als Messung in die Auflösung des Gesamtzählers (`kanal/bilanz_adapter.py`), der Rest
``21 − (−38) − 6 = 53`` landete als kWp-Lücke beim Balkonkraftwerk, Süd fiel aus der Anzeige: **West 6 · Balkon 53**,
PV-Anlage + Balkon = 59 ≠ Erzeugung 21.

Entscheid Master 12.10. (Fund P4): dieselbe Regel wie der Bestandspfad für einen Rücksprung (R4, ``gesperrt`` in
``gemessene_tageswerte``) — ein Erzeuger, dessen Kanal am Tag eine fallende Stunde hat, ist am Tag **ohne Aussage**
(kein Messwert) und wird zur Lücke: er bekommt seinen kWp-Anteil am Rest, wie in der gespeicherten Tageszeile
(Süd 13,24 · West 6 · Balkon 1,76). Benannt wird der Rückgang weiter vom Daten-Checker (N-639, ``ha_rueckgang``). Ein
Sprung nach OBEN bleibt „wie HA" (Zählerlücken wie HA, entschieden) — Gegenprobe.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import date, datetime

import pytest

from backend.tests import pv_achse_matrix as mx

SPRUNG_T = datetime(2026, 6, 15, 3)
TAGE = (date(2026, 6, 14), date(2026, 6, 15), date(2026, 6, 16))


def _rate(kwh):
    return lambda t: (2.0 if t.hour in mx.PROD_STUNDEN else 0.0) + (kwh if t == SPRUNG_T else 0.0)


async def _tage(sprung: float) -> dict:
    form = mx.FORMEN["F05"]
    verz = tempfile.mkdtemp(prefix="eedc-n732-")
    engine, db = await mx._neue_db(f"{verz}/m.db")
    try:
        aid, ids = await mx.seed_anlage(db, form)
        svc = mx.seed_ha(form, abweichung={"sensor.pv_sued": (_rate(sprung), None)})
        with mx._umgebung(svc):
            await mx.fuelle_spiegel(engine, aid, svc)
            await mx.aggregiere_tage(db, form, aid, TAGE)
            return await mx.miss_tage(db, aid, ids, TAGE)
    finally:
        await db.close()
        await engine.dispose()
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.asyncio
async def test_fallender_string_wird_luecke_statt_den_rest_zu_verschieben():
    out = await _tage(-50.0)
    tag = out["2026-06-15"]
    assert tag["tw_erzeugung"] == pytest.approx(21.0)
    assert tag["tw_bkw"] == pytest.approx(1.76, abs=0.01)                    # am HEAD 53
    assert tag["tw_erzeuger"].get("Balkon") == pytest.approx(1.76, abs=0.01)
    assert tag["tw_erzeuger"].get("Süd") == pytest.approx(13.24, abs=0.01)   # Lücke: kWp-Anteil, kein Messwert
    assert tag["tw_pv_anlage"] + tag["tw_bkw"] == pytest.approx(tag["tw_erzeugung"], abs=0.01)
    # Bilanz unberührt (sie kommt aus dem Gesamtzähler), Nachbartage unverändert.
    assert (tag["tw_eigenverbrauch"], tag["tw_autarkie"]) == (pytest.approx(15.0), pytest.approx(67.6))
    for t in ("2026-06-14", "2026-06-16"):
        assert out[t]["tw_erzeuger"] == {"Süd": 12.0, "West": 6.0, "Balkon": 3.0}


@pytest.mark.asyncio
async def test_sprung_nach_oben_bleibt_wie_ha():
    """Gegenprobe: +500 kWh am Süd-Zähler steht wie in HA beim Süd-String (Zählerlücken wie HA) — unverändert."""
    tag = (await _tage(500.0))["2026-06-15"]
    assert tag["tw_erzeuger"].get("Süd") == pytest.approx(512.0)
    assert tag["tw_erzeugung"] == pytest.approx(518.0)
