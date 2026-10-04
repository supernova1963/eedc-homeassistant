"""Symmetrie-Wächter P2 — Σ Pro-Modul == Σ Anlagen-Summe (A20/Paket D).

Regel P2 (Befund-Sweep `docs/drafts/archive/BEFUND-SWEEP-WURZELMUSTER.md` §3): der
kWp-Anteil ist ein **Prognose**-Schlüssel, kein Ertragsschlüssel — auf der
IST-Seite verteilt er nur, wenn kein Messwert existiert, und dann gekennzeichnet.
Woran man einen Rückfall erkennt: die Pro-Modul-Sicht
(`/cockpit/pv-strings-gesamtlaufzeit`) und die Anlagen-Summe
(`/monatsdaten/aggregiert.pv_module_kwh`) driften auseinander, weil eine der
beiden Sichten wieder selbst rechnet statt den Read-time-SoT
`resolve_pv_je_modul` zu lesen. Genau diese Drift-Form hat den kWp-Komplex über
zehn Vorfälle getragen ([[feedback_aggregations_drift]]).

**Die frühere Ausnahme N42 (§3.2) ist seit N-626 aufgehoben (Gernot 04.10.2026).**
Bei einer **Teil-Lücke ohne Aggregat** — ein Modul gemessen, das andere nicht,
und kein Anlagen-Gesamtwert — zeigte die Anlagen-Summe bis dahin bewusst
**nichts** (`Σ pv_strings ≠ Σ /aggregiert`, gewollt). Seither trägt sie die
vorhandenen Werte (``pv_teilsumme_je_monat``), sagt mit ``pv_vollstaendig=False``,
dass einer fehlt, und der Daten-Checker nennt den Monat — die Symmetrie gilt damit
auch dort. Der Fall steht an EINER Stelle: in seiner eigenen Probe
(`test_teilluecke_ohne_aggregat_ist_seit_n626_symmetrisch_und_sagt_es`), die die
Symmetrie UND das Flag prüft. Belege: `pv_monatswerte.pv_teilsumme_je_monat` und
`test_pv_strings_kwp_verteilung.py::test_teilluecke_ohne_aggregat_behaelt_messwert`.

Baseline zum Bauzeitpunkt: **0 Verstöße** über alle geprüften Konstellationen.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.cockpit.pv_strings import get_pv_strings_gesamtlaufzeit
from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose

_JAHR = 2026
_MONAT = 5


async def _anlage(db, *, aggregat=None, pro_modul=None) -> int:
    """2 PV-Strings (6 + 4 kWp), Mai 2026 — Fixture-Muster der P2-Tests."""
    anlage = Anlage(anlagenname="P2-Symmetrie", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=_JAHR, monat=_MONAT,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0,
                       pv_erzeugung_kwh=aggregat))
    sued = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
                       anschaffungsdatum=date(2024, 1, 1), leistung_kwp=6.0)
    ost = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Ost",
                      anschaffungsdatum=date(2024, 1, 1), leistung_kwp=4.0)
    db.add_all([sued, ost])
    await db.flush()
    for inv, name in ((sued, "Süd"), (ost, "Ost")):
        wert = (pro_modul or {}).get(name)
        if wert is not None:
            db.add(InvestitionMonatsdaten(
                investition_id=inv.id, jahr=_JAHR, monat=_MONAT,
                verbrauch_daten={"pv_erzeugung_kwh": wert},
            ))
    db.add(PVGISPrognose(
        anlage_id=anlage.id, abgerufen_am=datetime(2026, 1, 1),
        latitude=48.0, longitude=11.0, neigung_grad=30.0, ausrichtung_grad=0.0,
        jahresertrag_kwh=10000.0, spezifischer_ertrag_kwh_kwp=1000.0,
        gesamt_leistung_kwp=10.0, ist_aktiv=True,
        monatswerte=[{"monat": m, "e_m": 1000.0} for m in range(1, 13)],
    ))
    await db.commit()
    return anlage.id


async def _summe_pro_modul(db, anlage_id: int) -> float:
    resp = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    return sum(s.ist_gesamt_kwh or 0 for s in resp.strings)


async def _summe_anlage(db, anlage_id: int) -> float:
    """Anlagen-Summe der **Module** — das Gegenstück zu `pv_strings`, das nur
    Investitionen vom Typ `pv-module` kennt (BKW/BHKW stehen in eigenen Feldern)."""
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=None, db=db)
    return sum(r.pv_module_kwh or 0 for r in rows)


# Konstellationen, in denen die Symmetrie GILT.
_SYMMETRISCH = [
    pytest.param({"aggregat": 1000.0, "pro_modul": None},
                 id="nur-aggregat-kwp-verteilt"),
    pytest.param({"aggregat": None, "pro_modul": {"Süd": 700.0, "Ost": 300.0}},
                 id="alle-module-gemessen"),
    pytest.param({"aggregat": 9999.0, "pro_modul": {"Süd": 700.0, "Ost": 300.0}},
                 id="messwerte-schlagen-aggregat"),
    pytest.param({"aggregat": 1000.0, "pro_modul": {"Süd": 700.0}},
                 id="teilluecke-MIT-aggregat"),
    pytest.param({"aggregat": None, "pro_modul": None},
                 id="gar-keine-quelle"),
    # Die Teil-Lücke OHNE Aggregat (seit N-626 ebenfalls symmetrisch) hat ihre eigene Probe
    # unten, die zusätzlich das Flag `pv_vollstaendig=False` prüft.
]


@pytest.mark.parametrize("fall", _SYMMETRISCH)
async def test_summe_pro_modul_gleich_anlagen_summe(db, fall):
    """Σ `pv-strings-gesamtlaufzeit[].ist_gesamt_kwh` == Σ
    `/monatsdaten/aggregiert.pv_module_kwh`.

    Beide Sichten müssen dieselbe Zerlegung lesen. Rechnet eine von ihnen
    wieder selbst (kWp-Anteil im Endpoint statt `resolve_pv_je_modul`), schlägt
    dieser Test an — unabhängig davon, welche der beiden abgedriftet ist.
    """
    anlage_id = await _anlage(db, **fall)

    pro_modul = await _summe_pro_modul(db, anlage_id)
    anlage = await _summe_anlage(db, anlage_id)

    assert pro_modul == pytest.approx(anlage), (
        f"P2-Symmetrie verletzt: Σ pv_strings={pro_modul}, "
        f"Σ /aggregiert.pv_module_kwh={anlage}. Entweder liest eine der beiden "
        f"Sichten nicht mehr über `resolve_pv_je_modul`."
    )


# ── Teil-Lücke ohne Aggregat — bis 04.10.2026 die Ausnahme N42, seit N-626 symmetrisch ──

_TEILLUECKE_OHNE_AGGREGAT = {"aggregat": None, "pro_modul": {"Süd": 700.0}}


async def test_teilluecke_ohne_aggregat_ist_seit_n626_symmetrisch_und_sagt_es(db):
    """Ein Modul gemessen, das andere nicht, kein Anlagen-Gesamtwert.

    Bis 04.10.2026 (N42) war das die gewollte Asymmetrie: Pro-Modul 700, Anlagen-Summe 0.
    Seit N-626 (Gernot: „Ein möglicher Modul-Ausfall kann ja auch korrekt sein … der
    Daten-Checker muss darauf hinweisen") trägt die Anlagen-Summe die vorhandenen Werte
    (700) — und was von der Substanz bleibt: der Messwert geht nicht verloren, und die
    Zeile sagt mit `pv_vollstaendig=False`, dass die Summe eine Teilsumme ist.
    """
    anlage_id = await _anlage(db, **_TEILLUECKE_OHNE_AGGREGAT)

    pro_modul = await _summe_pro_modul(db, anlage_id)
    anlage = await _summe_anlage(db, anlage_id)

    assert pro_modul == pytest.approx(700.0)
    assert anlage == pytest.approx(700.0)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=None, db=db)
    assert [r.pv_vollstaendig for r in rows] == [False]
