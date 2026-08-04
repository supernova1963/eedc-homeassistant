"""Drei Sichten, ein Nenner: die relevanten Kosten (N-137).

Der Amortisations-**Fortschritt** (aus gemessenen Erträgen) und die
Amortisations-**dauer** (aus einer hochgerechneten Jahres-Einsparung) stehen
seit N-137 in *Auswertungen → ROI* nebeneinander. Sie dürfen das nur, wenn sie
denselben Nenner benutzen — sonst widersprechen sich zwei Kacheln in einer
Sicht.

Bis 04.08. taten sie das nicht. Es gab **drei** Antworten auf „was hat die
Anlage relevant gekostet?":

- `aussichten.py` und `cockpit/uebersicht.py`: eine **Hybrid-Summe**
  `PV-System voll + WP-/eAuto-Mehrkosten + Sonstiges voll`, deren Mehrkosten aus
  `inv.parameter["alternativ_kosten_euro"]` kamen — einem Schlüssel, der
  baumweit **keinen Schreiber** hat (N-134) und deshalb immer auf die
  Festannahmen 8.000 € / 35.000 € zurückfiel;
- `investitionen/crud.py` (ROI-Sicht): `Σ (gesamt − alternativ)` aus der
  gepflegten **Spalte** `anschaffungskosten_alternativ`, ohne Klemmung je
  Position;
- die USt-Bemessung: `Σ max(0, gesamt − alternativ)` (seit N-129/N-130).

⚠ **Warum die Fixture abweichende Alternativkosten pflegt:** mit den
Default-Werten 8.000 / 35.000 liefern alte und neue Fassung dieselbe Zahl — am
Demo-Datenbestand sind beide Summen zufällig gleich (76.500 €), und genau
deshalb ist der Unterschied dort nie aufgefallen. Der Test variiert die Achse,
die er behauptet ([[feedback_aggregator_symmetrie]]): WP mit 5.000 € statt
8.000 €, E-Auto mit 20.000 € statt 35.000 €.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten


#: Was die Anlage der Fixture wirklich relevant gekostet hat:
#: PV 10.000 + Speicher 5.000 + (12.000 − 5.000) + (40.000 − 20.000) + 1.000
ERWARTETE_RELEVANTE_KOSTEN = 43000.0

#: Was die alte Hybrid-Summe geliefert hätte (Festannahmen 8.000 / 35.000):
#: 15.000 + 4.000 + 5.000 + 1.000. Steht hier, damit der Unterschied belegt ist
#: und der Test nicht versehentlich auf die alte Zahl zurückfallen kann.
ALTE_HYBRID_SUMME = 25000.0


async def _anlage(db) -> int:
    anlage = Anlage(anlagenname="NennerSymmetrie", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=600.0, netzbezug_kwh=0.0))

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=10000.0)
    speicher = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
                           anschaffungsdatum=date(2024, 1, 1),
                           anschaffungskosten_gesamt=5000.0,
                           parameter={"kapazitaet_kwh": 10.0})
    # Bewusst NICHT 8.000 — sonst wäre der Test gegen den alten Stand grün.
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
                     anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=12000.0,
                     anschaffungskosten_alternativ=5000.0)
    # Bewusst NICHT 35.000 — dito.
    eauto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="EV",
                        anschaffungsdatum=date(2024, 1, 1),
                        anschaffungskosten_gesamt=40000.0,
                        anschaffungskosten_alternativ=20000.0)
    sonstiges = Investition(anlage_id=anlage.id, typ="sonstiges", bezeichnung="Div",
                            anschaffungsdatum=date(2024, 1, 1),
                            anschaffungskosten_gesamt=1000.0)
    db.add_all([pv, speicher, wp, eauto, sonstiges])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 600.0}))
    await db.commit()
    return anlage.id


async def test_aussichten_cockpit_roi_nennen_dieselben_relevanten_kosten(db):
    anlage_id = await _anlage(db)

    prognose = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)
    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    # Query-Defaults explizit: beim direkten Funktionsaufruf sind die
    # `Query(None)`-Objekte sonst die Argumente.
    roi = await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )

    assert prognose.investition_gesamt_euro == pytest.approx(ERWARTETE_RELEVANTE_KOSTEN)
    assert cockpit.investition_gesamt_euro == pytest.approx(ERWARTETE_RELEVANTE_KOSTEN)
    assert cockpit.investition_mehrkosten_euro == pytest.approx(ERWARTETE_RELEVANTE_KOSTEN)
    assert roi.gesamt_relevante_kosten == pytest.approx(ERWARTETE_RELEVANTE_KOSTEN)

    # Und ausdrücklich NICHT die alte Hybrid-Summe.
    assert prognose.investition_gesamt_euro != pytest.approx(ALTE_HYBRID_SUMME)


async def test_gepflegte_alternativkosten_schlagen_die_festannahme(db):
    """Der Kern von N-134: das Feld, das der Daten-Checker einfordert, wirkt.

    WP 12.000 mit gepflegter Alternative 5.000 ⇒ 7.000 Mehrkosten. Die alte
    Fassung las `parameter["alternativ_kosten_euro"]` (kein Schreiber) und kam
    auf 12.000 − 8.000 = 4.000.
    """
    anlage_id = await _anlage(db)
    prognose = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    assert prognose.investition_wp_mehrkosten_euro == pytest.approx(7000.0)
    assert prognose.investition_eauto_mehrkosten_euro == pytest.approx(20000.0)


async def test_fortschritt_teilt_den_nenner_der_dauer(db):
    """Die beiden Amortisations-Kacheln rechnen gegen dieselbe Summe.

    Damit lässt sich der eine Wert in den anderen überführen — genau das war
    vorher unmöglich und der Grund, warum die Fortschritts-Anzeige beim
    V4-Flip nicht übernommen wurde.
    """
    anlage_id = await _anlage(db)
    prognose = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)
    # Query-Defaults explizit: beim direkten Funktionsaufruf sind die
    # `Query(None)`-Objekte sonst die Argumente.
    roi = await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )

    assert prognose.investition_gesamt_euro == pytest.approx(roi.gesamt_relevante_kosten)
    # Der Fortschritt ist genau der Quotient auf diesem Nenner.
    erwartet = round(
        prognose.bisherige_ertraege_euro / prognose.investition_gesamt_euro * 100, 1
    )
    assert prognose.amortisations_fortschritt_prozent == pytest.approx(erwartet)
