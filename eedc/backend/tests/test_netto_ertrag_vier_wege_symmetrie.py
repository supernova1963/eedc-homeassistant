"""Ein Netto-Ertrag, vier Sichten — Achse: Regelbesteuerung (USt).

Die #326-Inventur nannte drei Dimensionen, in denen die vier Finanz-Read-Sites
auseinanderliefen. Diese Datei schließt die USt-Dimension:

**USt-Eigenverbrauch** (nur bei ``steuerliche_behandlung == "regelbesteuerung"``)
wurde bis 2026-07-31 nur vom Cockpit und von der Aussichten-*Jahresprognose*
abgezogen — nicht vom Jahresbericht-PDF, nicht vom HA-Export-Sensor
``netto_ertrag_euro`` und auch nicht von den *bisherigen Erträgen* der
Aussichten (die den ROI-Fortschritt tragen). Betroffene Anlagen sahen dort
einen um den USt-Betrag zu hohen Ertrag.

Kein bestehender Symmetrie-Test hat das gefunden, weil alle Fixtures die Achse
konstant gehalten haben: keine einzige Anlage mit Regelbesteuerung. Ein
Symmetrie-Test deckt nur die Achsen ab, die seine Fixture variiert
([[feedback_aggregator_symmetrie]]).

**Bewusst NICHT hier geprüft — offene Dimension:** das Balkonkraftwerk. Die
Finanz-Zeile trägt zwei Eingänge, die sich **bedingt** überlappen:
``pv_erzeugung_kwh`` (bei Cockpit/PDF „PV-Module + BKW") und
``bkw_eigenverbrauch_kwh``. Schreibt ein BKW seine Erzeugung mit, steckt sein
Eigenverbrauch bereits im ersten Eingang und der zweite zählt doppelt;
schreibt es nur ``eigenverbrauch_kwh``, ist der zweite Eingang der einzige
Träger. Beides kommt im Bestand vor. Das ist eine Datenmodell-Frage und braucht
eine Entscheidung, keinen stillen Patch.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.ha_export import calculate_anlage_sensors
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context


async def _anlage_mit_regelbesteuerung(db) -> int:
    """PV-Anlage mit Regelbesteuerung, ein Monat, ein Tarif.

    Bewusst EIN Monat und EIN Tarif: geprüft wird nicht die Zeitachse (dafür
    ADR-002/P8 und `test_aussichten_finanz_aggregat_symmetrie`), sondern ob alle
    vier Sichten dieselben POSTEN in den Netto-Ertrag nehmen.
    """
    anlage = Anlage(
        anlagenname="VierWegeUSt", leistung_kwp=10.0,
        steuerliche_behandlung="regelbesteuerung", ust_satz_prozent=19.0,
    )
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=12000.0)
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
        verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    await db.commit()
    return anlage.id


@pytest.mark.asyncio
async def test_cockpit_zieht_die_ust_ab(db):
    """Die Referenzzahl, gegen die die anderen drei geprüft werden.

    einspeise = 400 × 0,08                  =  32,00 €
    ev        = (1.000 − 400) × 0,30        = 180,00 €
    USt       = 600 kWh × (12.000/20 / 1.000) × 19 %
              = 600 × 0,60 × 0,19           =  68,40 €
    netto     = 32 + 180 − 68,40            = 143,60 €
    """
    anlage_id = await _anlage_mit_regelbesteuerung(db)

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)

    assert cockpit.ust_eigenverbrauch_euro == pytest.approx(68.4, abs=0.05)
    assert cockpit.netto_ertrag_euro == pytest.approx(143.6, abs=0.1)
    # Gegenprobe: ohne USt-Abzug wären es 212 € — das war der Stand in PDF,
    # HA-Export und den bisherigen Erträgen der Aussichten.
    assert abs(cockpit.netto_ertrag_euro - 212.0) > 50.0


@pytest.mark.asyncio
async def test_alle_vier_sichten_nennen_denselben_netto_ertrag(db):
    """Cockpit == Aussichten == Jahresbericht-PDF == HA-Export."""
    anlage_id = await _anlage_mit_regelbesteuerung(db)

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    aussichten = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)
    pdf = await build_jahresbericht_context(db, anlage_id, jahr=2026)

    anlage = await db.get(Anlage, anlage_id)
    sensoren = await calculate_anlage_sensors(db, anlage)
    ha_netto = next(
        s.value for s in sensoren if s.definition.key == "netto_ertrag_euro"
    )

    referenz = cockpit.netto_ertrag_euro

    assert aussichten.bisherige_ertraege_euro == pytest.approx(referenz, abs=0.1), (
        f"Aussichten {aussichten.bisherige_ertraege_euro} ≠ Cockpit {referenz}")
    assert pdf["kpis"]["netto_ertrag_euro"] == pytest.approx(referenz, abs=0.1), (
        f"PDF {pdf['kpis']['netto_ertrag_euro']} ≠ Cockpit {referenz}")
    assert ha_netto == pytest.approx(referenz, abs=0.1), (
        f"HA-Export {ha_netto} ≠ Cockpit {referenz}")
