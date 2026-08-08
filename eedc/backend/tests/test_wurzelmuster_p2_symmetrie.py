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

**Die benannte Ausnahme N42 (§3.2) ist Teil der Regel, nicht ihr Gegner.**
Bei einer **Teil-Lücke ohne Aggregat** — ein Modul gemessen, das andere nicht,
und kein Anlagen-Gesamtwert — behält die Pro-Modul-Sicht ihren Messwert, während
die Anlagen-Summe bewusst **nichts** zeigt: eine Teilsumme als „Gesamt-PV"
auszuweisen wäre irreführend, einen Messwert wegzuwerfen wäre Datenverlust.
`Σ pv_strings ≠ Σ /aggregiert` ist dort **gewollt**. Dieser Wächter nimmt den
Fall deshalb ausdrücklich aus (`_N42_TEILLUECKE`) und prüft ihn stattdessen auf
seine eigene, asymmetrische Erwartung — sonst „repariert" der nächste Durchgang
die Regel weg. Belege: Docstring an `resolve_pv_je_modul` und der Test
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
        f"Sichten nicht mehr über `resolve_pv_je_modul`, oder es ist der "
        f"N42-Fall (Teil-Lücke OHNE Aggregat) — der gehört in `_N42_TEILLUECKE`, "
        f"nicht in diese Liste."
    )


# ── Die benannte Ausnahme N42 — gewollte Asymmetrie ────────────────────────

_N42_TEILLUECKE = {"aggregat": None, "pro_modul": {"Süd": 700.0}}


async def test_n42_teilluecke_ohne_aggregat_ist_bewusst_asymmetrisch(db):
    """**Kein Verstoß, sondern die Regel:** ein Modul gemessen, das andere nicht,
    kein Anlagen-Gesamtwert. Die Pro-Modul-Sicht behält den Messwert (700), die
    Anlagen-Summe zeigt nichts (0) — eine Teilsumme als Gesamt-PV wäre
    systematisch zu klein und sähe wie die volle Erzeugung aus.

    Wer diesen Test „grün macht", indem er eine der beiden Seiten angleicht,
    dreht die Regel um. Begründung: `resolve_pv_je_modul`-Docstring, Sweep §3.2.
    """
    anlage_id = await _anlage(db, **_N42_TEILLUECKE)

    pro_modul = await _summe_pro_modul(db, anlage_id)
    anlage = await _summe_anlage(db, anlage_id)

    assert pro_modul == pytest.approx(700.0)
    assert anlage == pytest.approx(0.0)
    assert pro_modul != pytest.approx(anlage)  # gewollt, siehe Docstring
