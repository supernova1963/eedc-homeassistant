"""#443 / N-785 (Päckchen DD, 10.11.2026): ``GET /investitionen/dashboard/sonstiges`` kennt die Kategorie «Abgabe an Dritte».

Bis 4.2.2 fiel ein Abgabe-Gerät in den Speicher-Zweig der Route (``else:  # speicher``): ``gesamt_ladung_kwh`` 0,
``gesamt_entladung_kwh`` 0, ``effizienz_prozent`` leer, ``ersparnis_euro`` 0 — vier Zahlen über ein Gerät, das weder lädt
noch spart (gemessen auf der Scratch-Kopie r28-abgabe, Master 10.11.2026). Jetzt ein eigener Zweig: Abgabe und gepflegter
Erlös aus den Monats-Fakten (P10), keine ``ersparnis_*``/``co2_*``-Größen, ``bewertet`` nur mit Erlös.
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.investitionen.dashboard_sonstiges import ABGABE_NICHT_BEWERTET_GRUND, get_sonstiges_dashboard
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten


async def _anlage_mit_abgabe(db, zeilen: dict[tuple[int, int], dict]) -> Anlage:
    anlage = Anlage(anlagenname="N785", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(anlage_id=anlage.id, typ="sonstiges", bezeichnung="Mieterstrom",
                      anschaffungsdatum=date(2025, 1, 1), parameter={"kategorie": "abgabe"})
    db.add(inv)
    await db.flush()
    for (j, m), d in zeilen.items():
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=j, monat=m, einspeisung_kwh=300.0, netzbezug_kwh=200.0))
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=j, monat=m, verbrauch_daten=d))
    await db.flush()
    return anlage


async def _dashboard(db, anlage):
    [d] = await get_sonstiges_dashboard(anlage_id=anlage.id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0, db=db)
    return d


async def test_abgabe_mit_erloes(db):
    anlage = await _anlage_mit_abgabe(db, {
        (2025, 1): {"abgabe_kwh": 210.0, "einspeise_erloes_euro": 12.5},
        (2025, 2): {"abgabe_kwh": 190.0, "einspeise_erloes_euro": 0.0},     # gepflegte 0 = unentgeltlich, eine Aussage
        (2025, 3): {"abgabe_kwh": 160.0},                                  # ohne Erlös
    })
    d = await _dashboard(db, anlage)
    z = d.zusammenfassung
    assert z["kategorie"] == "abgabe"
    assert z["gesamt_abgabe_kwh"] == 560.0
    assert z["erloes_abgabe_euro"] == 12.5
    assert z["monate_mit_erloes"] == 2 and z["monate_mit_abgabe"] == 3 and z["anzahl_monate"] == 3
    assert z["bewertet"] is True and "nicht_bewertet_grund" not in z
    # Keine Größe des Speicher-Zweigs, keine Ersparnis, kein CO₂ — eine 0 wäre eine Behauptung.
    assert not any(k.startswith(("gesamt_ladung", "gesamt_entladung", "effizienz", "ersparnis", "co2")) for k in z)
    assert [(m.monat, m.abgabe_kwh, m.erloes_euro) for m in d.abgabe_monatsreihe] == [
        (1, 210.0, 12.5), (2, 190.0, 0.0), (3, 160.0, None)]
    assert d.monatsreihe == []


async def test_abgabe_ohne_erloes_nicht_bewertet(db):
    anlage = await _anlage_mit_abgabe(db, {(2025, 1): {"abgabe_kwh": 210.0}})
    z = (await _dashboard(db, anlage)).zusammenfassung
    assert z["erloes_abgabe_euro"] is None and z["monate_mit_erloes"] == 0
    assert z["bewertet"] is False and z["nicht_bewertet_grund"] == ABGABE_NICHT_BEWERTET_GRUND


async def test_alt_monat_mit_erzeugung_zaehlt_nicht_als_abgabe(db):
    """Roberts Fall (#443): Monate vor der Umstellung tragen ihren Wert in ``erzeugung_kwh`` — wie in der Bilanz 0."""
    anlage = await _anlage_mit_abgabe(db, {
        (2025, 4): {"erzeugung_kwh": 95.0},
        (2025, 5): {"abgabe_kwh": 80.0},
    })
    d = await _dashboard(db, anlage)
    assert [(m.monat, m.abgabe_kwh) for m in d.abgabe_monatsreihe] == [(4, 0.0), (5, 80.0)]
    assert d.zusammenfassung["gesamt_abgabe_kwh"] == 80.0 and d.zusammenfassung["monate_mit_abgabe"] == 1
