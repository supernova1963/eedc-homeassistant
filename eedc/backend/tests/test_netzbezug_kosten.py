"""Block 2 — Helper-Unit + Char-Netz für berechne_netzbezug_kosten.

`netzbezug_kosten_euro` war in keinem Test direkt gepinnt (nur netto_ertrag,
das den Grundpreis NICHT enthält). Daher hier ein kleines Charakterisierungs-
Netz auf den Aggregiert-Endpoint zusätzlich zum Helper-Kontrakt, bevor die
fünf Inline-Sites auf den Helper gezogen werden.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen import berechne_netzbezug_kosten
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten


# ── Helper-Kontrakt ─────────────────────────────────────────────────────────

def test_arbeitspreis_plus_grundpreis():
    assert berechne_netzbezug_kosten(1000, 30, 12.0) == pytest.approx(312.0)


def test_grundpreis_default_null():
    assert berechne_netzbezug_kosten(500, 25) == pytest.approx(125.0)


def test_null_bezug_nur_grundpreis():
    assert berechne_netzbezug_kosten(0, 30, 9.5) == pytest.approx(9.5)


def test_arithmetik_identisch_zu_inline():
    # bit-identisch zur vormaligen Inline-Form kwh * cent / 100 + grundpreis
    kwh, cent, gp = 1234.5, 31.7, 11.9
    assert berechne_netzbezug_kosten(kwh, cent, gp) == kwh * cent / 100 + gp


# ── Char-Netz: Komponenten-Zeitreihe führt netzbezug_kosten_euro pro Monat ──

async def test_charnetz_komponenten_netzbezug_kosten(db):
    """Pinnt netzbezug_kosten_euro der Komponenten-Zeitreihe (300 kWh Netzbezug
    zum Default-Tarif). Golden Master — sichert, dass der Helper-Umbau den
    bestehenden Wert byte-identisch lässt."""
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe

    a = Anlage(anlagenname="NB-Kosten", leistung_kwp=8.0)
    db.add(a)
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=4,
                       einspeisung_kwh=200.0, netzbezug_kwh=300.0))
    sp = Investition(anlage_id=a.id, typ="speicher", bezeichnung="Sp",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    db.add(sp)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=sp.id, jahr=2026, monat=4,
                                  verbrauch_daten={"ladung_kwh": 100, "entladung_kwh": 90}))
    await db.commit()

    resp = await get_komponenten_zeitreihe(anlage_id=a.id, jahr=2026, db=db)
    m = next(x for x in resp.monatswerte if (x.jahr, x.monat) == (2026, 4))
    # 300 kWh × Default-Arbeitspreis (30 ct) / 100 + Grundpreis 0 = 90.0
    assert m.netzbezug_kosten_euro == pytest.approx(90.0)
