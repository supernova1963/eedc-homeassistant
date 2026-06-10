"""Cockpit-Übersicht: EV-Ersparnis bei Flex-Tarif per-Monat — #326 (Teil 2).

rilmor-mhrs (#326, Folge): Nach dem Sonstige-Fix blieb eine zweite Differenz —
die **Eigenverbrauchs-Ersparnis** wich zwischen Cockpit (2.988 €) und
Auswertungen→Finanzen (4.159 €) ab, obwohl die EV-**kWh** nahezu gleich waren.

Ursache: Das Cockpit bildete EINEN netzbezug-gewichteten Ø-Netzbezugspreis und
multiplizierte ihn mit dem GESAMT-Eigenverbrauch
(`Σ(EV) × [Σ(netzbezug_m·preis_m)/Σ(netzbezug_m)]`). Die Auswertungen rechnen
korrekt `Σ(eigenverbrauch_m × preis_m)`. Bei Flex-Tarifen (Tibber/aWATTar/EPEX)
driften beide auseinander, sobald Preis und EV/Netzbezug-Split monatlich
variieren — Sommer-EV fällt aus der netzbezug-Gewichtung.

Fix (`uebersicht.py`): EV- und BKW-Ersparnis pro Monat über denselben
SoT-Helper (`berechne_verbrauchs_kennzahlen`) × Monats-Flexpreis
(`resolve_netzbezug_preis_cent`) — deckungsgleich mit der Auswertungen-Formel.

Lehre: [[feedback_aggregator_symmetrie]] — der bestehende Flex-Test prüfte nur,
dass das Preis-FELD im `/aggregiert`-Response auftaucht, nicht dass die beiden
End-zu-End-`ev_ersparnis`-Summen übereinstimmen. Dieser Test prüft die Summe.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten


async def _anlage_flex(db) -> Anlage:
    """PV-Anlage mit zwei Monaten gegenläufiger Flex-Preis-/EV-Charakteristik.

    Sommer (Mai): viel PV/EV, wenig Netzbezug, NIEDRIGER Flexpreis.
    Winter (Dez): wenig PV/EV, viel Netzbezug, HOHER Flexpreis.
    So liefern netzbezug-gewichteter Ø-Preis und per-Monat-Summe klar
    verschiedene EV-Ersparnis-Werte.
    """
    anlage = Anlage(anlagenname="Flex326", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    # Mai: pv 1000, einspeisung 600 → EV 400; netzbezug 50; Flexpreis 20 ct
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       pv_erzeugung_kwh=1000.0, einspeisung_kwh=600.0,
                       netzbezug_kwh=50.0, netzbezug_durchschnittspreis_cent=20.0))
    # Dez: pv 100, einspeisung 20 → EV 80; netzbezug 500; Flexpreis 40 ct
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=12,
                       pv_erzeugung_kwh=100.0, einspeisung_kwh=20.0,
                       netzbezug_kwh=500.0, netzbezug_durchschnittspreis_cent=40.0))

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
        leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=10000.0,
    )
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=12,
                                  verbrauch_daten={"pv_erzeugung_kwh": 100.0}))
    await db.commit()
    return anlage


async def test_cockpit_ev_ersparnis_per_monat_flexpreis(db):
    """EV-Ersparnis = Σ(eigenverbrauch_m × flexpreis_m), NICHT Gesamt-EV × Ø-Preis.

    Korrekt (per-Monat):  400·0,20 + 80·0,40 = 80 + 32 = 112,00 €
    Alt/buggy (Ø-Preis):  Ø = (50·20 + 500·40)/550 = 38,18 ct;
                          Gesamt-EV 480 · 0,3818 ≈ 183,3 €
    Der neue Wert muss 112 € sein und sich klar vom alten 183 € unterscheiden.
    """
    anlage = await _anlage_flex(db)
    r = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)

    # EV-kWh bleibt das Aggregat (helper auf Summen): 1100-620 = 480.
    assert r.eigenverbrauch_kwh == pytest.approx(480.0)

    # KERN #326 Teil 2: per-Monat-Summe.
    assert r.ev_ersparnis_euro == pytest.approx(112.0, abs=0.01)

    # Gegenprobe: NICHT der netzbezug-gewichtete Ø-Wert (~183 €).
    assert abs(r.ev_ersparnis_euro - 183.3) > 50


async def test_cockpit_ev_ersparnis_symmetrie_zu_auswertungen(db):
    """Symmetrie zur Auswertungen-Formel: die Cockpit-EV-Ersparnis muss exakt
    `Σ(eigenverbrauch_m × resolve_netzbezug_preis_cent(m))` sein — die gleiche
    Rechnung, die `createMonatsZeitreihe` im Frontend macht."""
    from backend.api.routes.strompreise import resolve_netzbezug_preis_cent
    from backend.core.berechnungen import berechne_verbrauchs_kennzahlen
    from sqlalchemy import select

    anlage = await _anlage_flex(db)
    r = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)

    md_rows = (await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all()

    erwartet = 0.0
    for m in md_rows:
        kz = berechne_verbrauchs_kennzahlen(
            pv_erzeugung_kwh=m.pv_erzeugung_kwh or 0,
            einspeisung_kwh=m.einspeisung_kwh or 0,
            netzbezug_kwh=m.netzbezug_kwh or 0,
        )
        preis = resolve_netzbezug_preis_cent(m, 30.0)
        erwartet += kz.eigenverbrauch_kwh * preis / 100

    assert r.ev_ersparnis_euro == pytest.approx(erwartet, abs=0.01)
