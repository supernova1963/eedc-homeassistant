"""N-352: Der HA-Export bildet die relevanten Kosten über den Layer-SoT.

Dieselbe Formel, die N-136 im Jahresbericht-PDF behoben hat — hier trug sie die
**ausgelieferten Sensoren** ``roi_prozent`` und ``amortisation_jahre``:

    relevante_kosten = investition_gesamt - alternativ_gesamt   # ungeklemmt

Der Layer klemmt **je Position** (``Σ max(0, gesamt − alternativ)``). Trägt eine
Position eine teurere Alternative — ein Verbrenner gegen ein E-Auto ist der
Regelfall —, zog ihr Überschuss die Mehrkosten der **anderen** Positionen
herunter: Nenner zu klein, **ROI zu hoch, Amortisation zu kurz**, und beide
Sensoren widersprachen Cockpit, ROI-Seite, Aussichten, Wallbox-Hub und dem
Jahresbericht-PDF.

⚑ **Die Wertänderung an den zwei Sensoren ist gewollt und gemeldet** (Zeile im
Nachlauf) — sie ist die Korrektur, nicht ein Nebeneffekt.

Die Zusicherung lautet **„die Zahl des SoT"**, nicht „die Zahl 20.000": eine
künftige Neuformulierung neben dem Helfer wäre sonst wieder grün.
"""

from __future__ import annotations

from datetime import date

import pytest

from sqlalchemy import select

from backend.api.routes.ha_export import calculate_anlage_sensors
from backend.core.berechnungen import relevante_kosten_aus_investitionen
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten


async def _sensoren(db, anlage_id: int) -> dict:
    """Die Sensorwerte je Key — die Probe greift an der AUSGELIEFERTEN Größe an.

    ``calculate_anlage_sensors`` nimmt ein ``Anlage``-Objekt und liefert eine
    Liste; der Nenner selbst ist eine lokale Variable und von außen nicht
    lesbar. Genau deshalb misst diese Probe die zwei Sensoren, die ihn tragen —
    das ist die Stelle, an der der Fehler beim Anwender ankommt.
    """
    anlage = (await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )).scalar_one()
    return {s.definition.key: s.value for s in await calculate_anlage_sensors(db, anlage)}


async def _seed(db, *, alternative_teurer: bool) -> tuple[int, list]:
    """PV ohne Alternative + E-Auto, dessen Alternative wahlweise teurer ist.

    ⚠ Strompreis UND PV-Erzeugung je Modul gehören dazu: ohne Ersparnis setzt
    ``calculate_anlage_sensors`` ``roi_prozent`` und ``amortisation_jahre`` gar
    nicht erst — die Probe wäre dann mit ``KeyError`` rot, ohne den Befund zu
    berühren. (Genau so ist ihr erster Entwurf gescheitert.)
    """
    anlage = Anlage(anlagenname="N-352", leistung_kwp=10.0,
                    standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=m,
                           einspeisung_kwh=500.0, netzbezug_kwh=300.0))

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="PV-Dach",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=20000.0,
        anschaffungskosten_alternativ=None,
        leistung_kwp=10.0,
    )
    auto = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Stromer",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=30000.0,
        anschaffungskosten_alternativ=35000.0 if alternative_teurer else 25000.0,
    )
    db.add_all([pv, auto])
    await db.flush()

    for m in range(1, 13):
        db.add(InvestitionMonatsdaten(
            investition_id=pv.id, jahr=2025, monat=m,
            verbrauch_daten={"pv_erzeugung_kwh": 900.0},
        ))
    await db.commit()
    return anlage.id, [pv, auto]


@pytest.mark.asyncio
async def test_n352_teurere_alternative_verkuerzt_die_amortisation_nicht(db):
    """Der Kern: der Nenner ist die geklemmte Summe, nicht die anlagenweite Differenz.

    Gemessen wird über ``relevante_kosten_euro`` — das Feld, das die Rechnung
    an ``kapitaleinsatz_euro`` weitergibt und das die Sensoren tragen.
    """
    anlage_id, invs = await _seed(db, alternative_teurer=True)

    s = await _sensoren(db, anlage_id)
    ersparnis = s["jahres_ersparnis_euro"]
    assert ersparnis and ersparnis > 0, "ohne Ersparnis sagt die Amortisation nichts"

    # Σ max(0, 20000−0) + max(0, 30000−35000) = 20000 + 0 — ohne sonstige
    # Positionen ist der Kapitaleinsatz genau diese Summe.
    assert s["amortisation_jahre"] == pytest.approx(20000.0 / ersparnis)
    # Die ungeklemmte Form hätte 50000 − 35000 = 15000 ergeben: ein um ein
    # Viertel zu kleiner Nenner ⇒ Amortisation zu kurz, ROI zu hoch.
    assert s["amortisation_jahre"] != pytest.approx(15000.0 / ersparnis)
    assert s["roi_prozent"] == pytest.approx(ersparnis / 20000.0 * 100)


@pytest.mark.asyncio
async def test_n352_relevante_kosten_sind_die_zahl_des_layer_sot(db):
    """Gegen Neuformulierung: nicht der Wert, sondern die Quelle wird zugesichert."""
    anlage_id, invs = await _seed(db, alternative_teurer=True)

    s = await _sensoren(db, anlage_id)
    erwartet = relevante_kosten_aus_investitionen(invs)

    assert s["amortisation_jahre"] == pytest.approx(
        erwartet / s["jahres_ersparnis_euro"]
    )


@pytest.mark.asyncio
async def test_n352_ohne_teurere_alternative_bewegt_sich_nichts(db):
    """Gegenanker: der Normalfall darf sich durch den Fix nicht ändern.

    Ohne diese Probe wäre auch ein Fix grün, der die Alternativkosten schlicht
    ignoriert — er lieferte hier 50.000 statt 25.000.
    """
    anlage_id, invs = await _seed(db, alternative_teurer=False)

    s = await _sensoren(db, anlage_id)
    # Σ max(0, 20000−0) + max(0, 30000−25000) = 25000 — und die alte,
    # ungeklemmte Form liefert hier dieselben 25000.
    assert relevante_kosten_aus_investitionen(invs) == pytest.approx(25000.0)
    assert s["amortisation_jahre"] == pytest.approx(
        25000.0 / s["jahres_ersparnis_euro"]
    )
