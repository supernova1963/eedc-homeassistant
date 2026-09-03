"""N-256: Der fossile CO₂-Vergleich rechnet nur mit der Wärme, die Gas ersetzt hat.

Der Jahresbericht buchte die **anlagenweite** Wärmesumme als vermiedenes Gas und
sperrte das nur, wenn **keine einzige** Wärmepumpe etwas ersetzt hatte
(`alle_ersetzen_nichts`, entfallen mit diesem Paket). Die Näherung war im Layer
dokumentiert und ausdrücklich als „eigenes Paket" zurückgestellt — das ist dieses.

**Warum sie mehr als ein Randfall war.** Eine Split-Klimaanlage ist in eedc eine
Wärmepumpe mit ``wp_art="luft_luft"`` und trägt typischerweise „nichts ersetzt";
*Wärmepumpe + Klimaanlage* ist der Normalfall dieser Fläche, nicht die Ausnahme.
Ihre Wärme wurde als Gas-Vermeidung gebucht: eine Ersparnis, die es nie gab.

**Warum Teilmengen und keine Aufteilung je Gerät.** Die gemeinsame Kennzahl über
zwei Geräte wird nicht umgebaut (Entscheid 27.08.) — und sie muss es auch nicht:
Eine **Arbeitszahl** ist ein Quotient und über zwei Bauarten sinnlos, deshalb wird
sie gesperrt. Eine **CO₂-Menge** ist additiv; für sie genügt die Teilsumme über die
ersetzenden Geräte. *Kennzahlen je Bauart trennen, Mengen summieren* (Konzept
Wärme/Klima, E1). Die Symmetrie dazu auf der Kostenseite steht in
`test_wp_ersparnis_grundmenge_n279.py`.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen import ERSETZT_NICHTS
from backend.core.calculations import co2_wp_ersparnis_kg
from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
)
from backend.services.monats_fakten import lade_monats_fakten
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context


WAERME_HEIZUNG_KWH = 800.0
WAERME_WARMWASSER_KWH = 33.0
STROM_KWH = 220.0

WP_ERSETZT_GAS = {
    "alter_energietraeger": "gas",
    "alter_preis_cent_kwh": 10.0,
    "jaz": 4.0,
}
#: Split-Klimaanlage im Neubau — heizt und kühlt, hat aber nie eine Heizung
#: ersetzt. `wp_art` ist gesetzt, damit das Gerät auch fachlich das ist, was der
#: Melder-Fall beschreibt, und nicht nur ein zweiter Parametersatz.
KLIMA_ERSETZT_NICHTS = {
    "alter_energietraeger": ERSETZT_NICHTS,
    "alter_preis_cent_kwh": 10.0,
    "wp_art": "luft_luft",
    "jaz": 4.0,
}


async def _seed(db, *parametersaetze: dict) -> int:
    """Anlage mit je einem Wärmepumpen-Gerät pro Parametersatz, alle gleich groß."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, latitude=48.0)
    db.add(anlage)
    await db.flush()
    for monat in range(1, 13):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            netzbezug_kwh=100.0, einspeisung_kwh=200.0, eigenverbrauch_kwh=50.0,
        ))
    geraete = []
    for nr, parameter in enumerate(parametersaetze, start=1):
        inv = Investition(
            anlage_id=anlage.id, typ="waermepumpe", bezeichnung=f"Gerät-{nr}",
            anschaffungsdatum=date(2024, 1, 1),
            anschaffungskosten_gesamt=20000.0,
            parameter=dict(parameter),
        )
        db.add(inv)
        geraete.append(inv)
    await db.flush()
    for monat in range(1, 13):
        for inv in geraete:
            # ⛔ **N-379 (03.09.2026) — die Fixture stellte einen Zustand her, den
            # es in der Produktion nicht gibt.** Sie gab JEDEM Gerät ein
            # `warmwasser_kwh`, auch der Split-Klimaanlage — die hat seit N-304
            # (22.08.) keinen Warmwasserkreis und bekommt das Feld im
            # Monatsabschluss gar nicht mehr angeboten. Seit N-379 liest auch der
            # Lesepfad es dort nicht mehr, und die Zusicherung „beide Geräte sind
            # gleich groß" ging nicht mehr auf (9996 gegen 9798).
            #
            # ⭐ **Die Aussage der Probe bleibt unberührt** — sie prüft, dass
            # `*_mit_ersatz_kwh` nur die ersetzenden Geräte trägt, und das tut sie
            # unverändert: dieselbe Wärmemenge, nur auf der Achse, die es am Gerät
            # gibt. **Keine Zusicherung wurde angefasst.** Eine Klimaanlage GIBT
            # Wärme ab (Entscheid Gernot 21.08.), nur eben keine Warmwasser-Wärme.
            ist_klima = (inv.parameter or {}).get("wp_art") == "luft_luft"
            db.add(InvestitionMonatsdaten(
                investition_id=inv.id, jahr=2025, monat=monat,
                verbrauch_daten={
                    "heizenergie_kwh": (
                        WAERME_HEIZUNG_KWH + WAERME_WARMWASSER_KWH if ist_klima
                        else WAERME_HEIZUNG_KWH
                    ),
                    **({} if ist_klima
                       else {"warmwasser_kwh": WAERME_WARMWASSER_KWH}),
                    "stromverbrauch_kwh": STROM_KWH,
                },
            ))
    await db.flush()
    return anlage.id


# ============================================================================
# Die Schicht — WpFakten führt beide Mengen getrennt
# ============================================================================


async def test_teilmengen_zaehlen_nur_die_ersetzenden_geraete(db):
    """`*_mit_ersatz_kwh` trägt ein Gerät, `strom_kwh`/`waerme_kwh` tragen beide."""
    anlage_id = await _seed(db, WP_ERSETZT_GAS, KLIMA_ERSETZT_NICHTS)
    fakten = await lade_monats_fakten(db, anlage_id)

    waerme_gesamt = sum(f.wp.waerme_kwh for f in fakten)
    waerme_mit_ersatz = sum(f.wp.waerme_mit_ersatz_kwh for f in fakten)
    strom_gesamt = sum(f.wp.strom_kwh for f in fakten)
    strom_mit_ersatz = sum(f.wp.strom_mit_ersatz_kwh for f in fakten)

    assert waerme_gesamt > 0 and strom_gesamt > 0
    # Beide Geräte sind gleich groß ⇒ die Teilmenge ist exakt die Hälfte.
    assert waerme_mit_ersatz == pytest.approx(waerme_gesamt / 2)
    assert strom_mit_ersatz == pytest.approx(strom_gesamt / 2)


async def test_teilmenge_ist_die_gesamtmenge_wenn_alle_ersetzen(db):
    """Ohne ein „nichts ersetzt"-Gerät fallen beide Mengen zusammen.

    Die Gegenrichtung: Der Filter darf nicht generell etwas abziehen. Ohne diesen
    Fall wäre ein „Teilmenge ist immer die Hälfte" nicht auszuschließen.
    """
    anlage_id = await _seed(db, WP_ERSETZT_GAS, WP_ERSETZT_GAS)
    fakten = await lade_monats_fakten(db, anlage_id)

    assert sum(f.wp.waerme_mit_ersatz_kwh for f in fakten) == pytest.approx(
        sum(f.wp.waerme_kwh for f in fakten)
    )
    assert sum(f.wp.strom_mit_ersatz_kwh for f in fakten) == pytest.approx(
        sum(f.wp.strom_kwh for f in fakten)
    )


# ============================================================================
# Die Wirkung — der Jahresbericht weist keine erfundene Ersparnis mehr aus
# ============================================================================


async def test_klimaanlage_erzeugt_keine_gas_ersparnis(db):
    """Der Melder-Fall: Wärmepumpe (ersetzt Gas) + Split-Klimaanlage (ersetzt nichts).

    Die CO₂-Ersparnis muss dieselbe sein wie bei der Wärmepumpe allein. Vorher lag
    sie deutlich höher, weil die Wärme der Klimaanlage als vermiedenes Gas galt.
    """
    allein = await _seed(db, WP_ERSETZT_GAS)
    kontext_allein = await build_jahresbericht_context(db, allein, jahr=2025)

    gemischt = await _seed(db, WP_ERSETZT_GAS, KLIMA_ERSETZT_NICHTS)
    kontext_gemischt = await build_jahresbericht_context(db, gemischt, jahr=2025)

    co2_allein = kontext_allein["co2"]["wp_kg"]
    co2_gemischt = kontext_gemischt["co2"]["wp_kg"]

    assert co2_allein > 0, "Aufbau kaputt: die Gas-WP weist keine CO₂-Ersparnis aus"
    assert co2_gemischt == pytest.approx(co2_allein, rel=1e-6)


async def test_co2_wert_stammt_aus_dem_kanonischen_helfer(db):
    """Die Zahl ist nicht nur gleich, sie ist auch die richtige.

    Ein Vergleich zweier Berichte allein liefe auch dann grün, wenn beide
    dieselbe falsche Zahl trügen. Deshalb hier gegen `co2_wp_ersparnis_kg`
    (ADR-001/DI-1, die einzige erlaubte Konstruktions-Stelle) mit den Mengen
    **eines** Geräts nachgerechnet.
    """
    anlage_id = await _seed(db, WP_ERSETZT_GAS, KLIMA_ERSETZT_NICHTS)
    kontext = await build_jahresbericht_context(db, anlage_id, jahr=2025)

    erwartet = co2_wp_ersparnis_kg(
        12 * (WAERME_HEIZUNG_KWH + WAERME_WARMWASSER_KWH),
        12 * STROM_KWH,
    )
    assert kontext["co2"]["wp_kg"] == pytest.approx(erwartet, rel=1e-6)


async def test_alle_ersetzen_nichts_weist_keine_co2_ersparnis_aus(db):
    """Der Randfall bleibt, wie er war: gar kein Ersatz ⇒ keine Ersparnis.

    Er war früher der EINZIGE Fall, in dem gesperrt wurde. Dass er weiter gilt,
    ist die Zusicherung, dass das Paket eine Näherung ersetzt und keine Regel
    zurückgedreht hat.
    """
    anlage_id = await _seed(db, KLIMA_ERSETZT_NICHTS, KLIMA_ERSETZT_NICHTS)
    kontext = await build_jahresbericht_context(db, anlage_id, jahr=2025)

    assert kontext["co2"]["wp_kg"] == 0
