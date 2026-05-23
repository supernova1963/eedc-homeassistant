"""Aussichten / Finanz-Prognose mit mehreren E-Autos.

Vorher gab es drei verkettete Drift-Bugs bei Mehrfach-E-Autos:

- **Bug A** (`bisherige_eauto_ersparnis`-Schleife): `eauto_vergleich_l_100km`
  und `eauto_benzinpreis` waren globale Variablen, in einer `for ea`-Schleife
  last-write-wins überschrieben. Bei 2 E-Autos mit unterschiedlichen Parametern
  wurden BEIDE mit den Werten des LETZTEN gerechnet.
- **Bug B** (Jahresprognose): gleiche last-write-wins-Variablen flossen in
  die hochgerechnete Benzin-Kosten-Jahr-Schätzung ein.
- **Bug C** (KomponentenBeitragSchema): Beschreibungstext zeigte
  `{eauto_vergleich_l_100km}L/100km Benziner` (last-write-wins) für jedes
  E-Auto in dessen Karte; alle E-Autos zeigten zudem dieselbe globale
  `jahres_eauto_km_ersparnis` statt ihres anteiligen Beitrags.

Fix: `eauto_aggregate[ea.id]` mit per-E-Auto-Werten. Aggregat-Größen
(`eauto_vergleich_l_100km_agg`, `eauto_benzinpreis_default_agg`) jetzt
km-gewichteter Durchschnitt statt last-write-wins. Komponenten-Anzeige
nutzt per-E-Auto-`vergleich_l_100km` und km-anteilige `jahres_ersparnis`.
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.aussichten import get_finanz_prognose
from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
)


async def _seed_zwei_eautos_unterschiedliche_params(db) -> int:
    """Anlage + 2 E-Autos mit deutlich unterschiedlichen Vergleichsverbräuchen.

    EA-1 (Klein-EV): vergleich 6 L/100km, benzinpreis-default 1,80 €
    EA-2 (SUV-EV):   vergleich 10 L/100km, benzinpreis-default 2,00 €
    Beide fahren je 10.000 km über 12 Monate. Bei korrekter Per-EA-Rechnung
    ersparen sie deutlich unterschiedliche Beträge.
    """
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, latitude=48.0)
    db.add(anlage)
    await db.flush()

    # Monatsdaten ohne `kraftstoffpreis_euro` — erzwingt den per-Inv-Fallback,
    # womit der Bug deutlich messbar wird. Mit EU-OB-Preis kämen beide Autos
    # auf denselben Monatspreis und der Bug wäre maskiert.
    for monat in range(1, 13):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            netzbezug_kwh=100.0, einspeisung_kwh=200.0,
            eigenverbrauch_kwh=50.0,
        ))

    ea1 = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Klein-EV",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=30000.0,
        parameter={
            "jahresfahrleistung_km": 10000,
            "verbrauch_kwh_100km": 15,
            "pv_ladeanteil_prozent": 50,
            "vergleich_verbrauch_l_100km": 6.0,
            "benzinpreis_euro": 1.80,
            "alternativ_kosten_euro": 25000,
        },
    )
    ea2 = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="SUV-EV",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=50000.0,
        parameter={
            "jahresfahrleistung_km": 10000,
            "verbrauch_kwh_100km": 22,
            "pv_ladeanteil_prozent": 50,
            "vergleich_verbrauch_l_100km": 10.0,
            "benzinpreis_euro": 2.00,
            "alternativ_kosten_euro": 45000,
        },
    )
    db.add(ea1)
    db.add(ea2)
    await db.flush()

    # Pro EA: ~833 km × 12 Monate = 10.000 km/Jahr (linear)
    for monat in range(1, 13):
        for ea in (ea1, ea2):
            db.add(InvestitionMonatsdaten(
                investition_id=ea.id, jahr=2025, monat=monat,
                verbrauch_daten={
                    "km_gefahren": 833.33,
                    "ladung_netz_kwh": 50.0,
                    "ladung_pv_kwh": 50.0,
                    "verbrauch_kwh": 150.0,
                },
            ))

    await db.flush()
    return anlage.id


async def test_pro_eauto_komponenten_zeigt_eigene_vergleich_l_100km(db):
    """Bug C: Beschreibungstext muss pro E-Auto den jeweils gepflegten
    Vergleichsverbrauch zeigen — nicht den last-write-wins-Wert."""
    anlage_id = await _seed_zwei_eautos_unterschiedliche_params(db)
    result = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    benzin_komponenten = [
        k for k in result.komponenten_beitraege if k.typ == "e-auto-benzin"
    ]
    assert len(benzin_komponenten) == 2

    # Klein-EV-Karte muss 6 L/100km referenzieren, SUV-EV-Karte 10 L/100km
    klein = next(k for k in benzin_komponenten if "Klein-EV" in k.bezeichnung)
    suv = next(k for k in benzin_komponenten if "SUV-EV" in k.bezeichnung)
    assert "6.0L/100km" in klein.beschreibung or "6L/100km" in klein.beschreibung
    assert "10.0L/100km" in suv.beschreibung or "10L/100km" in suv.beschreibung


async def test_pro_eauto_jahresersparnis_unterscheidet_sich(db):
    """Bug B + C: Die per-E-Auto-`beitrag_euro_jahr` muss sich für E-Autos mit
    deutlich unterschiedlichen Vergleichsverbräuchen klar unterscheiden.

    Bei gleichen km schlägt 10 L/100km × 2,00 €/L deutlich teurer zu Buche
    als 6 L/100km × 1,80 €/L → SUV-EV-Ersparnis > Klein-EV-Ersparnis.
    """
    anlage_id = await _seed_zwei_eautos_unterschiedliche_params(db)
    result = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    benzin_komponenten = [
        k for k in result.komponenten_beitraege if k.typ == "e-auto-benzin"
    ]
    klein = next(k for k in benzin_komponenten if "Klein-EV" in k.bezeichnung)
    suv = next(k for k in benzin_komponenten if "SUV-EV" in k.bezeichnung)
    # SUV-EV: 10.000 km / 100 × 10 L × 2,00 € = 2000 € Benzin-Vergleich
    # Klein-EV: 10.000 km / 100 × 6 L × 1,80 € = 1080 € Benzin-Vergleich
    # Vor dem Bugfix waren beide gleich (jeweils mit Werten des LETZTEN E-Autos).
    assert suv.beitrag_euro_jahr > klein.beitrag_euro_jahr * 1.5, (
        f"Per-EA-Ersparnis differenziert nicht: Klein={klein.beitrag_euro_jahr}, "
        f"SUV={suv.beitrag_euro_jahr}"
    )


async def test_bisherige_ersparnis_summe_konsistent(db):
    """Bug A: Die Summe der per-E-Auto bisherige_ersparnis muss in die
    gesamten bisherigen Erträge eingehen. Indirekter Smoke-Test: Endpoint
    rechnet durch und liefert plausible Werte (positive Ersparnis, weil
    Benzin teurer als Strom)."""
    anlage_id = await _seed_zwei_eautos_unterschiedliche_params(db)
    result = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    # Beide E-Autos summiert haben jährlich:
    # Klein: 10.000 km / 100 × 6 L × 1,80 € = 1080 € Benzin-Alternative
    # SUV:   10.000 km / 100 × 10 L × 2,00 € = 2000 € Benzin-Alternative
    # Σ = 3080 € — Netzstrom-Kosten (≈ 1200 kWh × Bezugspreis).
    # Aggregat-jahres_eauto_km_ersparnis_euro muss spürbar > 0 sein, sonst
    # ist der Bugfix kaputt.
    assert result.eauto_alternativ_ersparnis_euro > 500, (
        f"Jahres-E-Auto-Ersparnis unplausibel klein: "
        f"{result.eauto_alternativ_ersparnis_euro}"
    )


async def test_einzelnes_eauto_keine_verhaltensaenderung(db):
    """Sicherstellen, dass der Refactor bei nur 1 E-Auto kein anderes
    Ergebnis liefert: Aggregat-Werte = einziger E-Auto-Wert."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, latitude=48.0)
    db.add(anlage)
    await db.flush()
    for monat in range(1, 13):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            netzbezug_kwh=100.0, einspeisung_kwh=200.0,
            eigenverbrauch_kwh=50.0,
        ))
    ea = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Solo-EV",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=40000.0,
        parameter={
            "jahresfahrleistung_km": 15000,
            "verbrauch_kwh_100km": 18,
            "pv_ladeanteil_prozent": 60,
            "vergleich_verbrauch_l_100km": 7.5,
            "benzinpreis_euro": 1.90,
        },
    )
    db.add(ea)
    await db.flush()
    for monat in range(1, 13):
        db.add(InvestitionMonatsdaten(
            investition_id=ea.id, jahr=2025, monat=monat,
            verbrauch_daten={
                "km_gefahren": 1250.0,
                "ladung_netz_kwh": 100.0,
                "ladung_pv_kwh": 150.0,
                "verbrauch_kwh": 225.0,
            },
        ))
    await db.flush()

    result = await get_finanz_prognose(anlage_id=anlage.id, monate=12, db=db)
    benzin_komponenten = [
        k for k in result.komponenten_beitraege if k.typ == "e-auto-benzin"
    ]
    assert len(benzin_komponenten) == 1
    # Description muss den gepflegten Wert zeigen, nicht den globalen Default
    assert "7.5L/100km" in benzin_komponenten[0].beschreibung


async def test_bisherige_ersparnis_filtert_nach_stilllegungsdatum(db):
    """Active-Filter-Konsistenz: die bisherige-Ersparnis-Schleife muss
    nur Monate zählen, in denen die Investition aktiv war.

    Vorher filterte die erste Aggregation (für `gesamt_eauto_pv`/`gesamt_v2h`)
    auf `ist_aktiv_im_monat`, die Ersparnis-Schleife aber nicht — Datenmüll
    aus Monaten nach Stilllegung floss in `bisherige_eauto_ersparnis` ein.
    """
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, latitude=48.0)
    db.add(anlage)
    await db.flush()
    for monat in range(1, 13):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            netzbezug_kwh=100.0, einspeisung_kwh=200.0, eigenverbrauch_kwh=50.0,
        ))
    # E-Auto: aktiv Jan–Jun 2025, stilllegung Juli
    ea = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Stilllegungs-EV",
        anschaffungsdatum=date(2024, 1, 1),
        stilllegungsdatum=date(2025, 6, 30),
        anschaffungskosten_gesamt=30000.0,
        parameter={
            "jahresfahrleistung_km": 10000,
            "verbrauch_kwh_100km": 18,
            "pv_ladeanteil_prozent": 50,
            "vergleich_verbrauch_l_100km": 7.5,
            "benzinpreis_euro": 1.80,
        },
    )
    db.add(ea)
    await db.flush()
    # IMD für alle 12 Monate (auch Juli–Dezember nach Stilllegung — Datenmüll)
    for monat in range(1, 13):
        db.add(InvestitionMonatsdaten(
            investition_id=ea.id, jahr=2025, monat=monat,
            verbrauch_daten={
                "km_gefahren": 1000.0,
                "ladung_netz_kwh": 50.0,
                "ladung_pv_kwh": 50.0,
            },
        ))
    await db.flush()

    result = await get_finanz_prognose(anlage_id=anlage.id, monate=12, db=db)

    # Mit Filter werden nur 6 Monate (Jan–Jun) gezählt: 6000 km × 7,5 L/100 ×
    # 1,80 €/L ≈ 810 € Benzin-Alternative minus Netzstrom.
    # Ohne Filter wären es 12 Monate ≈ 1620 € Benzin-Alternative.
    # Schwelle 1200 € liegt sicher zwischen beiden Werten.
    assert result.eauto_alternativ_ersparnis_euro < 1200, (
        f"Stilllegungsdatum-Filter greift nicht: "
        f"eauto_alternativ_ersparnis_euro = {result.eauto_alternativ_ersparnis_euro} "
        f"(erwartet < 1200 € bei 6 aktiven Monaten, vorher ~1620 € bei 12)"
    )
