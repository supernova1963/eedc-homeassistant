"""N-615 — Tagesebene: die Abtretung eines Balkonkraftwerks gilt nur an Tagen, an denen seine Kinder aktiv sind.

``snapshot/komponenten_beitraege.py::loese_pv_tageswerte_auf`` löst seit N-536
(Stufe 2) den Tageswert eines Balkonkraftwerks auf seine `pv-module`-Kinder auf.
Bis 03.10.2026 fragte ``abgetretene_bkw_ids`` dort **alle** Investitionen —
ohne Datum, während ``erwartete_erzeuger_ids`` drei Zeilen darüber mit Datum
filterte. An einem Tag vor der Anschaffung der Kinder landeten 3,0 kWh des BKW
als 1,5 + 1,5 bei Kindern, die es noch nicht gab (ADR-002/P11, Abgrenzung (a):
erst der Zeitfilter, dann der Selektor).

⚠ **Gemessene Reichweite (03.10.2026):** Kein Produktivpfad erreicht diese Stufe
mit einer ungefilterten Menge. Der Schreibpfad (`aggregate_day`, Werkbank,
Vollbackfill) lädt seine Investitionen mit `aktiv_am_tag`; die Tagestabelle
(`tages_tabelle.baue_tagestabelle`) ruft die Funktion nur im Aggregat-Fall, und
dort steht kein Geräteschlüssel des BKW im Ergebnis. Die Probe hält die Regel
deshalb an der Funktion fest — und daneben, warum der **Stundenpfad** sie
bewusst NICHT bekommt (Probe 4).

Schwesterdateien: test_n536_bkw_traegt_nur_den_rest.py (Stufe 2 und die Rest-Form),
test_n406_pv_praezedenz_je_tag.py (Tagespräzedenz), test_n614_jahresbericht_string_vergleich_je_monat.py
und test_n614_selektor_nach_zeitfilter_co2_kanon.py (dieselbe Klasse).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.core.berechnungen.energie import summe_pv_bkw_kwh
from backend.models.investition import Investition
from backend.services.snapshot.komponenten_beitraege import loese_pv_tageswerte_auf
from backend.tests import ha_lts_helfer

D0 = date(2024, 1, 1)
SEP_25 = date(2025, 9, 1)
VOR = date(2025, 5, 15)
NACH = date(2025, 10, 15)


def _invs(kind_ab: tuple[date, date] = (SEP_25, SEP_25), kind_kwp: tuple[float, float] = (0.6, 0.2)) -> dict:
    """Süd 6 + West 4 kWp, Balkon 0,8 kWp (id 3), Kinder 21/22 mit UNGLEICHEN kWp (0,6 / 0,2)."""
    def inv(i, typ, kwp, ab, parent=None):
        return Investition(id=i, anlage_id=1, typ=typ, bezeichnung=f"inv{i}", leistung_kwp=kwp,
                           anschaffungsdatum=ab, parent_investition_id=parent, aktiv=True)
    return {str(i.id): i for i in (
        inv(1, "pv-module", 6.0, D0), inv(2, "pv-module", 4.0, D0), inv(3, "balkonkraftwerk", 0.8, D0),
        inv(21, "pv-module", kind_kwp[0], kind_ab[0], 3), inv(22, "pv-module", kind_kwp[1], kind_ab[1], 3),
    )}


TAG = {"bkw_3": 3.0, "pv_1": 12.0, "pv_2": 6.0}


def test_tag_vor_den_kindern_behaelt_das_bkw_seinen_wert():
    out, marken = loese_pv_tageswerte_auf(dict(TAG), _invs(), VOR)
    assert out == {"bkw_3": 3.0, "pv_1": 12.0, "pv_2": 6.0}
    assert marken == {}
    assert summe_pv_bkw_kwh(out) == pytest.approx(21.0)


def test_tag_nach_den_kindern_verteilt_kwp_gewichtet():
    """Unverändert seit N-536: 3,0 nach 0,6 : 0,2 ⇒ 2,25 + 0,75, das BKW trägt 0."""
    out, marken = loese_pv_tageswerte_auf(dict(TAG), _invs(), NACH)
    assert out["bkw_3"] == 0.0
    assert out["pv_21"] == pytest.approx(2.25)
    assert out["pv_22"] == pytest.approx(0.75)
    assert set(marken) == {"pv_21", "pv_22"}
    assert summe_pv_bkw_kwh(out) == pytest.approx(21.0)


def test_nur_die_am_tag_aktiven_kinder_bekommen_einen_anteil():
    """Kind 21 seit Januar, Kind 22 erst ab September: im Mai trägt Kind 21 den ganzen BKW-Wert."""
    out, _ = loese_pv_tageswerte_auf(dict(TAG), _invs(kind_ab=(date(2025, 1, 1), SEP_25)), VOR)
    assert out["bkw_3"] == 0.0
    assert out["pv_21"] == pytest.approx(3.0)
    assert "pv_22" not in out
    assert summe_pv_bkw_kwh(out) == pytest.approx(21.0)


# ── 4: der Stundenpfad bleibt zeitblind — und das ist richtig ───────────────

def _svc(deltas):
    svc = MagicMock()
    svc.is_available = True

    def _get(sensor_ids, _d):
        return {e: deltas[e] for e in sensor_ids if e in deltas}
    svc.get_hourly_kwh_deltas_for_day.side_effect = _get
    svc.get_hourly_slots_for_day.side_effect = ha_lts_helfer.slots_side_effect(_get)
    return svc


def _stunden(kwh_je_stunde: float) -> dict:
    return {h: (kwh_je_stunde if 10 <= h <= 15 else 0.0) for h in range(24)}


def _s(eid):
    return {"strategie": "sensor", "sensor_id": eid}


@pytest.mark.asyncio
@pytest.mark.parametrize("menge", ["alle (Tag-Status, Werkbank-Vorschau)", "am Tag aktiv (aggregate_day)"])
async def test_stundenpfad_zaehlt_vor_den_kindern_einmal(menge):
    """Die Kinder haben Sensoren mit Historie VOR ihrer Anschaffung — der Fall, der eine Lesestelle
    ohne Tagesfilter (Tag-Status, Leere-Tage-Check, Werkbank-Vorschau) ihre Werte lesen lässt.

    Der Stundenpfad kürzt das BKW um das, was die Kinder **gemessen** haben (`bkw_restwerte`,
    N-536) — eine Rest-Form, die ohne Datum stimmt: messen die Kinder nichts, ist der Rest der ganze
    Wert. Einen Zeitfilter vor diesen Selektor zu setzen (wie in der Tagesstufe oben) machte daraus
    eine Doppelzählung: am 03.10.2026 gegengeprobt, Σ 24,0 statt 21,0.
    """
    from backend.services.snapshot.lts_aggregator import get_komponenten_tageskwh_lts

    invs = _invs(kind_kwp=(0.4, 0.4))
    if menge.startswith("am Tag"):
        invs = {k: v for k, v in invs.items() if v.ist_aktiv_an(VOR)}
    anlage = SimpleNamespace(id=1, anlagenname="N615", leistung_kwp=10.8, sensor_mapping={
        "basis": {},
        "investitionen": {
            "1": {"felder": {"pv_erzeugung_kwh": _s("sensor.sued")}},
            "2": {"felder": {"pv_erzeugung_kwh": _s("sensor.west")}},
            "3": {"felder": {"pv_erzeugung_kwh": _s("sensor.bkw")}},
            "21": {"felder": {"pv_erzeugung_kwh": _s("sensor.k1")}},
            "22": {"felder": {"pv_erzeugung_kwh": _s("sensor.k2")}},
        },
    })
    deltas = {"sensor.sued": _stunden(2.0), "sensor.west": _stunden(1.0), "sensor.bkw": _stunden(0.5),
              "sensor.k1": _stunden(0.2), "sensor.k2": _stunden(0.3)}
    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=_svc(deltas)):
        tag = await get_komponenten_tageskwh_lts(anlage, invs, VOR)
    assert summe_pv_bkw_kwh(tag) == pytest.approx(21.0)
    if menge.startswith("am Tag"):
        assert tag["bkw_3"] == pytest.approx(3.0), "der Schreibpfad sieht die Kinder nicht — das BKW trägt"
