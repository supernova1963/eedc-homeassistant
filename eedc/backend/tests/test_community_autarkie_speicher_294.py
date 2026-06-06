"""Regressionstest #294: Community-Submit-Autarkie ignorierte den Speicher.

Bug (kingcap1): Der Community-Submit-Pfad (`prepare_community_data`) rechnete die
Autarkie mit der naiven Formel `eigenverbrauch = PV − Einspeisung` und ignorierte
den Speicher komplett, während Cockpit und HA-Export den Speicher korrekt
einrechnen (Direktverbrauch ohne Ladungsanteil + Entladung als Eigenverbrauch).
Folge: Speicher-Anlagen — besonders mit Netzladung (Tibber-Arbitrage, Backup) —
bekamen auf dem Community-Server systematisch zu niedrige Autarkie-Werte (12 %).

Fix: Submit-Pfad nutzt denselben SoT-Helper `berechne_verbrauchs_kennzahlen`
(core/berechnungen/verbrauch.py, ADR-001) wie Cockpit/HA-Export → deckungsgleich.

Dies ist ein Symmetrie-Test im Sinne von feedback_aggregator_symmetrie: zwei Pfade
(Submit ↔ kanonischer Helper) MÜSSEN denselben Wert liefern.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen import berechne_verbrauchs_kennzahlen
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.services.community_service import prepare_community_data


async def test_community_submit_autarkie_rechnet_speicher_ein(db):
    """Submit-Autarkie == kanonischer Helper (speicher-bewusst), NICHT die naive
    PV−Einspeisung-Formel."""
    # Szenario mit deutlichem Speicher-Einfluss inkl. Netzladung
    pv_kwh = 1000.0
    einspeisung = 200.0
    netzbezug = 400.0
    speicher_ladung = 400.0    # davon Teil Netzladung (Arbitrage)
    speicher_entladung = 350.0

    anlage = Anlage(anlagenname="Speicher-Test", leistung_kwp=10.0, standort_plz="10115")
    db.add(anlage)
    await db.flush()

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=6,
        einspeisung_kwh=einspeisung, netzbezug_kwh=netzbezug,
    ))

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0,
    )
    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
        anschaffungsdatum=date(2024, 1, 1),
    )
    db.add_all([pv, speicher])
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2025, monat=6,
        verbrauch_daten={"pv_erzeugung_kwh": pv_kwh},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=speicher.id, jahr=2025, monat=6,
        verbrauch_daten={"ladung_kwh": speicher_ladung, "entladung_kwh": speicher_entladung},
    ))
    await db.flush()

    data = await prepare_community_data(db, anlage.id)
    assert data is not None
    monatswerte = data["monatswerte"]
    assert len(monatswerte) == 1
    mw = monatswerte[0]

    # Erwartung: deckungsgleich mit dem kanonischen Helper
    erwartet = berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=pv_kwh,
        einspeisung_kwh=einspeisung,
        netzbezug_kwh=netzbezug,
        speicher_ladung_kwh=speicher_ladung,
        speicher_entladung_kwh=speicher_entladung,
    )
    assert mw["autarkie_prozent"] == pytest.approx(round(erwartet.autarkie_prozent, 1))
    assert mw["eigenverbrauch_prozent"] == pytest.approx(round(erwartet.eigenverbrauchsquote_prozent, 1))

    # Gegenprobe: die alte naive Formel hätte einen anderen (zu hohen) Wert geliefert
    naiv_eigen = pv_kwh - einspeisung
    naiv_autarkie = naiv_eigen / (naiv_eigen + netzbezug) * 100
    assert mw["autarkie_prozent"] != pytest.approx(round(naiv_autarkie, 1)), (
        "Submit liefert noch den speicher-ignorierenden Wert — #294-Bug zurück."
    )


async def test_community_submit_ohne_speicher_unveraendert(db):
    """Ohne Speicher liefert der Helper denselben Wert wie die alte Formel —
    Anlagen ohne Akku dürfen sich nicht ändern."""
    pv_kwh = 1200.0
    einspeisung = 720.0
    netzbezug = 360.0

    anlage = Anlage(anlagenname="Kein-Speicher", leistung_kwp=10.0, standort_plz="10115")
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=6,
        einspeisung_kwh=einspeisung, netzbezug_kwh=netzbezug,
    ))
    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0,
    )
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2025, monat=6,
        verbrauch_daten={"pv_erzeugung_kwh": pv_kwh},
    ))
    await db.flush()

    data = await prepare_community_data(db, anlage.id)
    mw = data["monatswerte"][0]

    naiv_eigen = pv_kwh - einspeisung                       # 480
    naiv_autarkie = naiv_eigen / (naiv_eigen + netzbezug) * 100   # 480/840
    assert mw["autarkie_prozent"] == pytest.approx(round(naiv_autarkie, 1))
