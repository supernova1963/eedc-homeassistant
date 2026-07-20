"""G20-2 (Gernot 2026-07-20): E-Auto-Ersparnis-Aggregat = Σ der Per-Fahrzeug-Zeilen.

Befund: `aktueller_monat` (und `cockpit/uebersicht`) rechneten EINEN
`berechne_eauto_ersparnis`-Lauf über die GESAMT-km ALLER E-Autos mit dem
Verbrauchs-Parameter des ERSTEN Autos → bei unterschiedlichem Verbrauch je
Fahrzeug falsch (Demo: Aggregat 167,79 € vs. Zeilen-Summe 65,37 + 85,59 =
150,96 €). Fix: Aggregat = Σ der Per-Investition-Ersparnisse (jede mit dem
Parameter IHRES Fahrzeugs).

Diese Tests fixieren:
  1. Symmetrie: `emob_ersparnis_euro` == Σ der E-Auto-Zeilen-`ersparnis_euro`
     ([[feedback_aggregator_symmetrie]]).
  2. Der frühere Referenz-Parameter-Lauf hätte ÜBERSCHÄTZT (Symmetrie war verletzt).
  3. Regression: bei GENAU EINEM E-Auto bleibt das Ergebnis bitgleich.
  4. `gesamtnettoertrag_euro` nutzt die (jetzt korrekte) Summe.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

JAHR, MONAT = 2024, 5


async def _seed_anlage(db: AsyncSession) -> Anlage:
    anlage = Anlage(anlagenname="G20", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    # Benzinpreis deterministisch (sonst Param-Default 1,65).
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=MONAT,
                       netzbezug_kwh=100.0, einspeisung_kwh=50.0,
                       kraftstoffpreis_euro=1.65))
    return anlage


async def _add_eauto(db, anlage, *, km: float, verbrauch: float) -> int:
    inv = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung=f"E-Auto {verbrauch}",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"vergleich_verbrauch_l_100km": verbrauch, "benzinpreis_euro": 1.65},
    )
    db.add(inv)
    await db.flush()
    # Nur km, keine Netzladung → Ersparnis = km × Verbrauch × Benzinpreis (isoliert
    # den Verbrauchs-Parameter, den der alte Referenz-Lauf falsch teilte).
    db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT,
                                  verbrauch_daten={"km_gefahren": km}))
    return inv.id


async def _add_pv(db, anlage, *, erzeugung: float) -> int:
    """PV-Modul, damit Eigenverbrauch (→ ev_ersparnis → gesamtnettoertrag) berechenbar ist."""
    inv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                      anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0)
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT,
                                  verbrauch_daten={"pv_erzeugung_kwh": erzeugung}))
    return inv.id


def _emob_rows(res):
    return [d for d in res.investitionen_financials
            if d.typ == "e-auto" and d.ersparnis_label == "Ersparnis vs. Verbrenner"]


async def test_aggregat_ist_summe_der_fahrzeug_zeilen(db):
    """Zwei E-Autos mit UNTERSCHIEDLICHEM Verbrauch → Aggregat == Σ Zeilen."""
    anlage = await _seed_anlage(db)
    await _add_eauto(db, anlage, km=651.0, verbrauch=7.5)
    await _add_eauto(db, anlage, km=1020.0, verbrauch=6.5)
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    zeilen = _emob_rows(res)
    assert len(zeilen) == 2
    zeilen_summe = round(sum(d.ersparnis_euro for d in zeilen), 2)
    assert res.emob_ersparnis_euro == zeilen_summe


async def test_frueherer_referenz_lauf_haette_ueberschaetzt(db):
    """Beweis, dass der Fix wirkt: Referenz-Parameter (7,5 für ALLE km) ergäbe
    einen HÖHEREN Wert als die korrekte Per-Fahrzeug-Summe (6,5 für Auto 2)."""
    anlage = await _seed_anlage(db)
    await _add_eauto(db, anlage, km=651.0, verbrauch=7.5)
    await _add_eauto(db, anlage, km=1020.0, verbrauch=6.5)
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    gesamt_km = 651.0 + 1020.0
    referenz_lauf = round(gesamt_km * 7.5 / 100 * 1.65, 2)  # alter Bug
    assert res.emob_ersparnis_euro < referenz_lauf


async def test_ein_eauto_bleibt_bitgleich(db):
    """Regression: bei EINEM E-Auto == manuelle Formel (km × Verbrauch × Preis)."""
    anlage = await _seed_anlage(db)
    await _add_eauto(db, anlage, km=651.0, verbrauch=7.5)
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    erwartet = round(651.0 * 7.5 / 100 * 1.65, 2)
    zeilen = _emob_rows(res)
    assert len(zeilen) == 1
    assert zeilen[0].ersparnis_euro == erwartet
    assert res.emob_ersparnis_euro == erwartet


async def test_gesamtnettoertrag_nutzt_summierte_emob(db):
    """`gesamtnettoertrag_euro` enthält die korrigierte eMob-Summe: der Anteil
    ohne eMob ist bei zwei vs. einem baugleichen Auto identisch, sodass die
    Differenz der gesamtnettoerträge == die Differenz der eMob-Summen ist."""
    a1 = await _seed_anlage(db)
    await _add_pv(db, a1, erzeugung=500.0)
    await _add_eauto(db, a1, km=651.0, verbrauch=7.5)
    await db.commit()
    res1 = await get_aktueller_monat(anlage_id=a1.id, jahr=JAHR, monat=MONAT, db=db)

    a2 = await _seed_anlage(db)
    await _add_pv(db, a2, erzeugung=500.0)
    await _add_eauto(db, a2, km=651.0, verbrauch=7.5)
    await _add_eauto(db, a2, km=1020.0, verbrauch=6.5)
    await db.commit()
    res2 = await get_aktueller_monat(anlage_id=a2.id, jahr=JAHR, monat=MONAT, db=db)

    # Beide haben denselben Nicht-eMob-Teil (gleiche Monatsdaten) → die Differenz
    # der gesamtnettoerträge ist exakt die Differenz der eMob-Summen.
    assert res1.gesamtnettoertrag_euro is not None
    assert res2.gesamtnettoertrag_euro is not None
    d_gesamt = round(res2.gesamtnettoertrag_euro - res1.gesamtnettoertrag_euro, 2)
    d_emob = round((res2.emob_ersparnis_euro or 0) - (res1.emob_ersparnis_euro or 0), 2)
    assert d_gesamt == d_emob


# ── Zweite Call-Site: cockpit/uebersicht (Jahr-/Übersichts-Aggregat) ──────────


async def test_uebersicht_aggregat_pro_fahrzeug_verbrauch(db):
    """cockpit/uebersicht: zwei E-Autos mit unterschiedlichem Verbrauch → das
    eMob-Aggregat nutzt je Fahrzeug den EIGENEN Verbrauch (Σ), nicht den
    Referenz-Verbrauch des ersten Autos für alle km."""
    anlage = await _seed_anlage(db)
    for km, verbrauch in ((651.0, 7.5), (1020.0, 6.5)):
        inv = Investition(
            anlage_id=anlage.id, typ="e-auto", bezeichnung=f"E-Auto {verbrauch}",
            anschaffungsdatum=date(2024, 1, 1),
            parameter={"vergleich_verbrauch_l_100km": verbrauch, "benzinpreis_euro": 1.65},
        )
        db.add(inv)
        await db.flush()
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=JAHR, monat=MONAT,
            verbrauch_daten={"km_gefahren": km, "ladung_kwh": 0.0,
                             "ladung_netz_kwh": 0.0, "ladung_pv_kwh": 0.0},
        ))
    await db.commit()

    res = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)
    # Σ der Per-Fahrzeug-Ersparnisse (kein Ladestrom → nur Benzin-Vermeidung).
    erwartet = round(651.0 * 7.5 / 100 * 1.65 + 1020.0 * 6.5 / 100 * 1.65, 2)
    referenz_lauf = round((651.0 + 1020.0) * 7.5 / 100 * 1.65, 2)  # alter Bug
    assert res.emob_ersparnis_euro == erwartet
    assert res.emob_ersparnis_euro < referenz_lauf


async def test_uebersicht_ein_eauto_bleibt_bitgleich(db):
    """Regression: bei EINEM E-Auto == manuelle Formel (100 %-Anteil = alter Lauf)."""
    anlage = await _seed_anlage(db)
    inv = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="E-Auto",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"vergleich_verbrauch_l_100km": 7.5, "benzinpreis_euro": 1.65},
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=JAHR, monat=MONAT,
        verbrauch_daten={"km_gefahren": 651.0, "ladung_kwh": 0.0,
                         "ladung_netz_kwh": 0.0, "ladung_pv_kwh": 0.0},
    ))
    await db.commit()

    res = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)
    assert res.emob_ersparnis_euro == round(651.0 * 7.5 / 100 * 1.65, 2)
