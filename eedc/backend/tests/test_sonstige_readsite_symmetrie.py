"""Pflicht-Symmetrie-Test: Sonstige Erträge/Ausgaben — Monatsbericht ⟺ Komponenten.

#310 rilmor-mhrs: Manuell gepflegte „Sonstige Erträge & Ausgaben" (z. B. ein am
Wechselrichter erfasster Einspeise-Ertrag) erschienen im Cockpit-Monatsbericht,
aber NICHT in der Auswertungen-Finanzen-Sicht. Ursache war eine Aggregator-Drift:
`get_komponenten_zeitreihe` summierte Sonstige im typ-gefilterten Energie-Loop
(`all_inv_ids` ohne PV-Modul/Wechselrichter) und zusätzlich laufzeit-gefiltert,
während der Monatsbericht (`get_aktueller_monat`) über ALLE Investitionen ohne
Laufzeit-Filter zählt.

Beide Read-Sites routen ihre Sonstige-Aggregation jetzt über genau EINEN Helper
(`aggregiere_sonstige_je_monat`). Dieser Test sichert ab, dass sie für dieselbe
Anlage dieselbe Zahl liefern — inkl. der Eckfälle:
  - Position am Wechselrichter/PV-Modul (= der eigentliche #310-Bug, Typ-Ausschluss)
    zählt INNERHALB der Laufzeit in beiden Sichten.
  - Position außerhalb der Laufzeit (nach Stilllegung) bzw. auf inaktiver
    Investition (`aktiv=False` = wie gelöscht) zählt in BEIDEN NICHT — Sonstige
    folgen derselben Sichtbarkeitsregel wie alles andere (detLAN
    [[feedback_anschaffungsdatum_grenze]], #236/#308), KEINE Sonderrolle.

Lehre: [[feedback_aggregator_symmetrie]], [[feedback_aggregations_drift]].
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.utils.sonstige_positionen import aggregiere_sonstige_je_monat


def _imd(jahr, monat, positionen):
    return SimpleNamespace(
        jahr=jahr, monat=monat,
        verbrauch_daten={"sonstige_positionen": positionen},
    )


# ── A. Helfer-Kontrakt ──────────────────────────────────────────────────────

def test_aggregiere_sonstige_je_monat_summiert_und_trennt():
    """Summiert je (jahr, monat); Erträge/Ausgaben/Netto getrennt; leere Monate raus."""
    rows = [
        _imd(2026, 4, [{"bezeichnung": "THG", "betrag": 200.0, "typ": "ertrag"}]),
        _imd(2026, 4, [{"bezeichnung": "Reparatur", "betrag": 50.0, "typ": "ausgabe"}]),
        _imd(2026, 5, [{"bezeichnung": "Verkauf", "betrag": 80.0, "typ": "ertrag"}]),
        _imd(2026, 6, []),  # leer → darf nicht im Ergebnis auftauchen
        SimpleNamespace(jahr=2026, monat=7, verbrauch_daten=None),  # None-robust
    ]
    out = aggregiere_sonstige_je_monat(rows)
    assert out[(2026, 4)] == {"ertraege_euro": 200.0, "ausgaben_euro": 50.0, "netto_euro": 150.0}
    assert out[(2026, 5)] == {"ertraege_euro": 80.0, "ausgaben_euro": 0.0, "netto_euro": 80.0}
    assert (2026, 6) not in out
    assert (2026, 7) not in out


def test_aggregiere_sonstige_je_monat_filtert_selbst_nicht():
    """Der Helper ist rein und filtert NICHT — er kennt keine Investition.
    Die Sichtbarkeitsregel (aktiv + Laufzeit-Fenster) liegt beim CALLER; der
    Helper summiert genau die übergebenen Rows."""
    out = aggregiere_sonstige_je_monat([
        _imd(1999, 1, [{"bezeichnung": "egal", "betrag": 12.0, "typ": "ertrag"}]),
    ])
    assert out[(1999, 1)]["ertraege_euro"] == 12.0


# ── B. Cross-Endpoint: Monatsbericht ⟺ Komponenten-Zeitreihe ────────────────

async def _komp_monat(db, anlage_id, jahr, monat):
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    komp = await get_komponenten_zeitreihe(anlage_id=anlage_id, jahr=None, db=db)
    return next((m for m in komp.monatswerte if m.jahr == jahr and m.monat == monat), None)


async def test_sonstige_am_pv_modul_symmetrisch(db):
    """Ertrag an einer PV-Modul-Investition (Typ NICHT in all_inv_ids):
    Monatsbericht und Komponenten-Zeitreihe liefern denselben Wert (200 €)."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage = Anlage(anlagenname="Sym310", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach Süd",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2026, monat=4,
        verbrauch_daten={"pv_erzeugung_kwh": 900, "sonstige_positionen": [
            {"bezeichnung": "Stromverkauf Nachbar", "betrag": 200.0, "typ": "ertrag"},
        ]},
    ))
    await db.commit()

    am = await get_aktueller_monat(anlage_id=anlage.id, jahr=2026, monat=4, db=db)
    km = await _komp_monat(db, anlage.id, 2026, 4)
    assert am.sonstige_ertraege_euro == 200.0
    assert km is not None and km.sonstige_ertraege_euro == 200.0
    assert am.sonstige_ertraege_euro == km.sonstige_ertraege_euro


async def test_sonstige_nach_stilllegung_zaehlt_nicht(db):
    """Eine Finanzposition NACH stilllegungsdatum zählt in BEIDEN Sichten NICHT
    — Sonstige folgen dem Laufzeit-Fenster wie alles andere (detLAN/#236/#308;
    Schema: „ab Stilllegung zählt die Investition nicht mehr für Auswertungen").
    Kontroll-Position IM Fenster zählt, damit der Test nicht trivial 0 misst."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage = Anlage(anlagenname="SymStill", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="wechselrichter", bezeichnung="Alt-WR",
        anschaffungsdatum=date(2018, 1, 1), stilllegungsdatum=date(2026, 1, 31),
        aktiv=True,
    )
    db.add(inv)
    await db.flush()
    # Kontrolle: Ertrag IM Fenster (Jan 2026, = Stilllegungsmonat → noch aktiv).
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=1,
        verbrauch_daten={"sonstige_positionen": [
            {"bezeichnung": "THG im Fenster", "betrag": 120.0, "typ": "ertrag"},
        ]},
    ))
    # Außerhalb: Verkaufserlös März 2026 — zwei Monate NACH Stilllegung.
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=3,
        verbrauch_daten={"sonstige_positionen": [
            {"bezeichnung": "Verkauf Alt-WR", "betrag": 300.0, "typ": "ertrag"},
        ]},
    ))
    await db.commit()

    # Innerhalb des Fensters: beide zählen 120.
    am_in = await get_aktueller_monat(anlage_id=anlage.id, jahr=2026, monat=1, db=db)
    km_in = await _komp_monat(db, anlage.id, 2026, 1)
    assert am_in.sonstige_ertraege_euro == 120.0
    assert (km_in.sonstige_ertraege_euro if km_in else 0.0) == 120.0

    # Nach Stilllegung: beide zählen 0 (kein Row / 0,0).
    am_out = await get_aktueller_monat(anlage_id=anlage.id, jahr=2026, monat=3, db=db)
    km_out = await _komp_monat(db, anlage.id, 2026, 3)
    assert am_out.sonstige_ertraege_euro == 0.0, "Monatsbericht: nach Stilllegung nicht zählen"
    assert (km_out.sonstige_ertraege_euro if km_out else 0.0) == 0.0, "Komponenten ebenso"


async def test_sonstige_inaktive_investition_zaehlt_nicht(db):
    """`aktiv=False` = wie gelöscht: Sonstige einer inaktiven Investition tauchen
    in KEINER Sicht auf (auch wenn die Laufzeit passt)."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage = Anlage(anlagenname="SymInaktiv", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Deaktiviert",
        anschaffungsdatum=date(2024, 1, 1), aktiv=False,
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"sonstige_positionen": [
            {"bezeichnung": "Ertrag auf inaktiver Inv.", "betrag": 99.0, "typ": "ertrag"},
        ]},
    ))
    await db.commit()

    am = await get_aktueller_monat(anlage_id=anlage.id, jahr=2026, monat=4, db=db)
    km = await _komp_monat(db, anlage.id, 2026, 4)
    assert am.sonstige_ertraege_euro == 0.0, "Monatsbericht: inaktive Investition = nirgends"
    assert (km.sonstige_ertraege_euro if km else 0.0) == 0.0, "Komponenten ebenso"


async def test_reiner_sonstige_monat_erscheint_in_komponenten(db):
    """Ein Monat mit NUR einer Sonstige-Position (keine Komponenten-Energiedaten)
    erzeugt trotzdem eine Zeile in der Komponenten-Zeitreihe — sonst verschluckt
    der FinanzenTab-Lookup den Wert (Monats-Union)."""
    anlage = Anlage(anlagenname="SymRein", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2026, monat=7,
        verbrauch_daten={"sonstige_positionen": [
            {"bezeichnung": "Einmal-Erstattung", "betrag": 42.0, "typ": "ertrag"},
        ]},
    ))
    await db.commit()

    km = await _komp_monat(db, anlage.id, 2026, 7)
    assert km is not None, "reiner Sonstige-Monat muss eine Zeile erzeugen"
    assert km.sonstige_ertraege_euro == 42.0
