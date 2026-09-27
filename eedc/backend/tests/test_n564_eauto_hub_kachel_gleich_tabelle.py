"""N-564 — E-Auto-Hub: die Kachel „Heimladung" ist die Summe der Monatstabelle.

Nachmessung N-555 Stufe 2 (Fable, 26.09.2026, F3): die Kacheln summierten über
``monate_des_autos`` — auch Monate, in denen das Auto Rest der Wallbox bekommt, aber keine
eigene Monatszeile hat (Konzept Regel 2 Schritt 3, ``eauto_in_betrieb``) —, die Tabelle zeigte
nur Zeilen. An einer Wegwerf-DB: Tesla 28 Monate in der Kachel, 25 Zeilen.

Entscheid Master (Auftrag „Restfunde vor Release", Punkt 1): die Tabelle trägt für solche
Monate eine Zeile „aus Wallbox-Rest" — ohne km, ohne ID, ``ladung_*`` aus dem Entscheid
(``je_auto``), gekennzeichnet ``ladung_aus_rest``. Damit gilt Kachel = Σ Tabelle.

Schwesterdateien: test_n555_stufe2_messung_je_auto.py (der Entscheid selbst),
test_komponenten_dashboards_monats_fakten.py.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.dashboard_eauto import get_eauto_dashboard
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten

WB_400 = {"ladung_kwh": 400.0, "ladung_pv_kwh": 200.0}  # 200 PV / 200 Netz


async def _anlage(db, autos: dict[str, dict], wallbox_monate=(4, 5, 6)):
    """Anlage mit einer privaten Wallbox (400 kWh je Monat in ``wallbox_monate``) und den
    Autos ``{bezeichnung: {monat: zeile}}`` — ein Auto ohne Eintrag hat keine Zeile."""
    a = Anlage(anlagenname="N564", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB",
                     anschaffungsdatum=date(2024, 1, 1), parameter={})
    db.add(wb)
    await db.flush()
    for m in wallbox_monate:
        db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2026, monat=m,
                                      verbrauch_daten=dict(WB_400)))
    ids = {}
    for bez, zeilen in autos.items():
        dienstlich = bez.startswith("DW")
        ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung=bez,
                         anschaffungsdatum=date(2024, 1, 1),
                         parameter={"ist_dienstlich": True} if dienstlich else {})
        db.add(ea)
        await db.flush()
        ids[bez] = ea.id
        for m, z in zeilen.items():
            db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2026, monat=m,
                                          verbrauch_daten=dict(z)))
    await db.commit()
    return a, ids


def _karte(karten, bez):
    (k,) = [k for k in karten if k.investition.bezeichnung == bez]
    return k


def _summe(karte, feld):
    return sum((m.verbrauch_daten.get(feld) or 0) for m in karte.monatsdaten)


@pytest.mark.asyncio
async def test_monat_ohne_zeile_steht_als_restzeile_und_kachel_gleich_summe(db):
    """Auto mit Zeilen im April und Juni, im Mai keine: der Rest des Mai (400) ist seiner."""
    a, ids = await _anlage(db, {"A": {4: {"km_gefahren": 1000.0}, 6: {"km_gefahren": 800.0}}})
    karte = _karte(await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db), "A")
    z = karte.zusammenfassung
    assert z["ladung_heim_kwh"] == pytest.approx(1200.0)

    assert [(m.jahr, m.monat) for m in karte.monatsdaten] == [(2026, 4), (2026, 5), (2026, 6)]
    mai = karte.monatsdaten[1]
    assert mai.id is None                              # nicht gespeichert
    assert mai.verbrauch_daten.get("ladung_aus_rest") is True
    assert "km_gefahren" not in mai.verbrauch_daten    # ohne km
    assert mai.verbrauch_daten["ladung_pv_kwh"] == pytest.approx(200.0)
    assert mai.verbrauch_daten["ladung_netz_kwh"] == pytest.approx(200.0)
    assert mai.verbrauch_daten["ladung_kwh"] == pytest.approx(400.0)
    # Die gespeicherten Zeilen bleiben, was sie waren: mit ID, ohne Rest-Kennzeichen.
    assert all(m.id is not None for m in (karte.monatsdaten[0], karte.monatsdaten[2]))
    assert not any(m.verbrauch_daten.get("ladung_aus_rest")
                   for m in (karte.monatsdaten[0], karte.monatsdaten[2]))

    # Kachel = Σ Tabelle — PV, Netz und Heimladung.
    assert _summe(karte, "ladung_pv_kwh") == pytest.approx(z["ladung_pv_kwh"])
    assert _summe(karte, "ladung_netz_kwh") == pytest.approx(z["ladung_netz_kwh"])
    assert _summe(karte, "ladung_kwh") == pytest.approx(z["ladung_heim_kwh"])
    # „Monate" zählt weiter die erfassten Monate des Autos, nicht die Anzeigezeilen.
    assert z["anzahl_monate"] == 2


@pytest.mark.asyncio
async def test_auto_ganz_ohne_zeilen_neben_auto_mit_zeilen(db):
    """Zwei private Autos: A fährt, B hat gar keine Zeile. B bekommt Rest nur, wo A 0 km hat
    oder kein Empfänger fährt — hier: A fährt jeden Monat, also teilt der Rest nach km
    (B 0 km ⇒ nichts). Im Juni fährt A 0 km ⇒ beide 0 km ⇒ gleich verteilt (E6)."""
    a, ids = await _anlage(db, {
        "A": {4: {"km_gefahren": 1000.0}, 5: {"km_gefahren": 500.0}, 6: {"km_gefahren": 0.0}},
        "B": {},
    })
    karten = await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    for bez in ("A", "B"):
        k = _karte(karten, bez)
        assert _summe(k, "ladung_kwh") == pytest.approx(k.zusammenfassung["ladung_heim_kwh"]), bez
    b = _karte(karten, "B")
    assert [(m.monat, m.verbrauch_daten.get("ladung_aus_rest")) for m in b.monatsdaten] == [(6, True)]
    assert b.monatsdaten[0].verbrauch_daten["ladung_kwh"] == pytest.approx(200.0)


@pytest.mark.asyncio
async def test_dienstwagen_bekommt_keine_restzeile(db):
    """Ein Dienstwagen ist kein Empfänger des Rests (Regel 3) — keine Zeile, keine Kachel."""
    a, ids = await _anlage(db, {"A": {4: {"km_gefahren": 1000.0}}, "DW": {}})
    karten = await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    assert _karte(karten, "DW").monatsdaten == []
    k = _karte(karten, "A")
    assert _summe(k, "ladung_kwh") == pytest.approx(k.zusammenfassung["ladung_heim_kwh"])
