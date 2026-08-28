"""N-279: Zähler und Abzug des WP-Alternativvergleichs stehen auf DERSELBEN Menge.

`get_finanz_prognose` vergleicht, was die Wärme mit Gas/Öl gekostet hätte, mit dem,
was der Wärmepumpen-Strom kostet. Die Gaskosten-Seite (`gas_kosten_jahr`) rechnet
seit N-88/F2b korrekt nur über `wp_mit_ersatz` — die Stromkosten-Seite
(`wp_stromkosten_netz_jahr`) las bis 2026-08-29 dagegen `jahres_wp_verbrauch`, also
den Strom **aller** Wärmepumpen.

Folge: Eine zweite Wärmepumpe, die **nichts** ersetzt (Neubau, `alter_energietraeger
= "nichts"`), brachte keine Wärme in den Zähler, aber ihren vollen Strom in den
Abzug. Sie schmälerte damit die ausgewiesene Ersparnis der Wärmepumpe, die
tatsächlich eine Gasheizung ersetzt hat.

⚠ **Was hier NICHT geprüft wird — und warum das Absicht ist.** Die Anzeige-Größen
`wp_verbrauch_kwh` (je Monat) und `wp_stromverbrauch_kwh` (Jahr) meinen weiterhin
**alle** Wärmepumpen: Sie beschreiben den Verbrauch der Anlage, nicht die Grundmenge
eines Vergleichs. Der zweite Test unten hält genau diese Trennung fest — ohne ihn
wäre der Fix von einem „zieht die Neubau-WP überall ab" nicht zu unterscheiden.

Abgrenzung zu `test_wp_ersetzt_nichts_n88.py`: Dort steht das **Prädikat** und der
per-Gerät-Pfad. Hier steht die **anlagenweite Jahresprognose**, die das Prädikat
bis heute nur auf einer der beiden Seiten der Differenz angewandt hat.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.core.berechnungen import ERSETZT_NICHTS
from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
)


# Eine Wärmepumpe, ein Monat: 833 kWh Wärme, 220 kWh Strom.
WAERME_HEIZUNG_KWH = 800.0
WAERME_WARMWASSER_KWH = 33.0
STROM_KWH = 220.0

GAS_ERSATZ = {
    "alter_energietraeger": "gas",
    "alter_preis_cent_kwh": 10.0,
    "alternativ_zusatzkosten_jahr": 300,
    "jaz": 4.0,
}
#: Neubau — es gab nie eine Heizung, die ersetzt worden wäre. Der Preis steht
#: bewusst trotzdem im Parametersatz: Er ist gepflegt, aber gegenstandslos, und
#: genau diese Lage muss der Filter aushalten.
KEIN_ERSATZ = {
    "alter_energietraeger": ERSETZT_NICHTS,
    "alter_preis_cent_kwh": 10.0,
    "alternativ_zusatzkosten_jahr": 300,
    "jaz": 4.0,
}


async def _seed(db, *parametersaetze: dict) -> int:
    """Anlage mit je einer Wärmepumpe pro übergebenem Parametersatz.

    Alle Geräte sind bewusst **gleich groß** (gleiche Wärme, gleicher Strom) —
    dann ist jede Abweichung zwischen den beiden Anlagen unten allein eine Folge
    der Grundmenge und nicht der Gerätedaten.
    """
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, latitude=48.0)
    db.add(anlage)
    await db.flush()
    for monat in range(1, 13):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            netzbezug_kwh=100.0, einspeisung_kwh=200.0, eigenverbrauch_kwh=50.0,
        ))
    wps = []
    for nr, parameter in enumerate(parametersaetze, start=1):
        wp = Investition(
            anlage_id=anlage.id, typ="waermepumpe", bezeichnung=f"WP-{nr}",
            anschaffungsdatum=date(2024, 1, 1),
            anschaffungskosten_gesamt=20000.0,
            parameter=dict(parameter),
        )
        db.add(wp)
        wps.append(wp)
    await db.flush()
    for monat in range(1, 13):
        for wp in wps:
            db.add(InvestitionMonatsdaten(
                investition_id=wp.id, jahr=2025, monat=monat,
                verbrauch_daten={
                    "heizenergie_kwh": WAERME_HEIZUNG_KWH,
                    "warmwasser_kwh": WAERME_WARMWASSER_KWH,
                    "stromverbrauch_kwh": STROM_KWH,
                },
            ))
    await db.flush()
    return anlage.id


def _wp_ersparnis_euro(result) -> float:
    """Die ausgewiesene Alternativkosten-Ersparnis der Wärmepumpen.

    Sie steht als Komponenten-Beitrag; bei mehreren Geräten wiederholt sich
    derselbe anlagenweite Betrag je Gerät (eigener Befund N-277, hier nicht
    Gegenstand) — deshalb der erste Eintrag und nicht die Summe.
    """
    beitraege = [
        b for b in result.komponenten_beitraege
        if b.typ == "waermepumpe-ersparnis"
    ]
    return beitraege[0].beitrag_euro_jahr if beitraege else 0.0


async def test_neubau_wp_schmaelert_die_ersparnis_der_ersetzenden_nicht(db):
    """Die Kernaussage: dieselbe Gas-WP, einmal allein, einmal neben einem Neubau.

    Beide Seiten der Differenz stehen jetzt auf `wp_mit_ersatz`. Die zweite
    Wärmepumpe bringt weder Wärme in den Zähler noch Strom in den Abzug — die
    ausgewiesene Ersparnis muss daher **unverändert** sein.

    Vor dem Fix lag der zweite Wert deutlich niedriger, weil der Strom der
    Neubau-WP (220 kWh/Monat, hochgerechnet und zur Hälfte als Netzbezug
    bepreist) von der Gaskosten-Ersparnis abgezogen wurde.
    """
    allein = await _seed(db, GAS_ERSATZ)
    ergebnis_allein = await get_finanz_prognose(anlage_id=allein, monate=12, db=db)

    gemischt = await _seed(db, GAS_ERSATZ, KEIN_ERSATZ)
    ergebnis_gemischt = await get_finanz_prognose(anlage_id=gemischt, monate=12, db=db)

    ersparnis_allein = _wp_ersparnis_euro(ergebnis_allein)
    ersparnis_gemischt = _wp_ersparnis_euro(ergebnis_gemischt)

    # Ohne einen echten Betrag prüfte der Vergleich zwei Nullen gegeneinander.
    assert ersparnis_allein > 0, "Aufbau kaputt: die Gas-WP weist keine Ersparnis aus"
    assert ersparnis_gemischt == pytest.approx(ersparnis_allein, rel=1e-6)


async def test_anzeige_verbrauch_meint_weiter_alle_waermepumpen(db):
    """Die Gegenrichtung — der Fix darf nicht überall greifen.

    `wp_stromverbrauch_kwh` beschreibt, was die **Anlage** verbraucht. Dort
    gehören beide Geräte hinein, auch das, dessen Strom im Alternativvergleich
    nichts zu suchen hat. Ohne diesen Test wäre der Fix von einem „rechnet die
    Neubau-WP generell heraus" nicht zu unterscheiden — und genau das wäre die
    nächste falsche Zahl, nur in der Gegenrichtung.
    """
    allein = await _seed(db, GAS_ERSATZ)
    ergebnis_allein = await get_finanz_prognose(anlage_id=allein, monate=12, db=db)

    gemischt = await _seed(db, GAS_ERSATZ, KEIN_ERSATZ)
    ergebnis_gemischt = await get_finanz_prognose(anlage_id=gemischt, monate=12, db=db)

    assert ergebnis_allein.wp_stromverbrauch_kwh > 0
    assert ergebnis_gemischt.wp_stromverbrauch_kwh == pytest.approx(
        2 * ergebnis_allein.wp_stromverbrauch_kwh, rel=1e-6
    )


async def test_alle_ersetzen_nichts_weist_keine_ersparnis_aus(db):
    """Der Randfall darunter: ist gar nichts ersetzt worden, gibt es nichts zu
    vergleichen — weder Gaskosten noch einen Stromabzug.

    Er hält die Schwelle des Fixes fest: `wp_mit_ersatz` ist leer, damit ist auch
    die neue Stromgröße 0 und die Ersparnis entfällt vollständig, statt negativ
    zu werden (was sie täte, wenn nur der Zähler entfiele).
    """
    anlage_id = await _seed(db, KEIN_ERSATZ, KEIN_ERSATZ)
    ergebnis = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    assert _wp_ersparnis_euro(ergebnis) == 0.0
    # Der Verbrauch der Anlage bleibt davon unberührt — beide Geräte laufen ja.
    assert ergebnis.wp_stromverbrauch_kwh > 0
