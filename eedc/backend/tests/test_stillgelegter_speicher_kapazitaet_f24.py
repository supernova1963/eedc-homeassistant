"""F-24 — ein ersetzter Speicher zählt nicht mehr zur Ausstattung.

Wer sein Gerät tauscht oder nach dem Zwei-Datensatz-Weg erweitert, hat in eedc
**zwei** Speicher-Einträge: den alten mit Stilllegungsdatum, den neuen ab dem
Wechseltag. Beide bleiben `aktiv` — den Haken zu entfernen würde das Gerät auch
aus der Historie nehmen (`models/investition.py::ist_aktiv_an`).

Drei Stellen summierten trotzdem über **alle** Einträge und meldeten damit eine
Kapazität, die die Anlage nie hatte. An einer Kopie des Dev-Bestands gemessen
(11.08.2026): **15,4 + 30,8 = 46,2 kWh statt 30,8**. Im Community-Datensatz ist
das besonders teuer — der Server rechnet nichts nach, die Anlage stand mit
falscher Ausstattung im öffentlichen Benchmark und verzog die Größenklassen
für alle anderen mit.

Gedeckt sind hier der **Community-Payload** und der **Jahresbericht**. Die
dritte Stelle (`aktueller_monat.py::speicher_invs`) ist gleich gebaut, aber
nicht durch eine eigene Probe gedeckt — sie hängt an einer Route mit
umfangreichem I/O.
"""

from datetime import date

from backend.models import Anlage, Investition
from backend.services.community_service import prepare_community_data
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context


async def _anlage_mit_ersetztem_speicher(db) -> int:
    """15,4 kWh bis 30.06.2025, danach 30,8 kWh — Gesamtkapazität, nicht Differenz."""
    anlage = Anlage(
        anlagenname="Tausch-Test", leistung_kwp=10.0,
        installationsdatum=date(2023, 6, 1), standort_plz="51588",
    )
    db.add(anlage)
    await db.flush()

    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Alt 15.4",
        anschaffungsdatum=date(2023, 6, 1), stilllegungsdatum=date(2025, 6, 30),
        aktiv=True, anschaffungskosten_gesamt=12000.0,
        parameter={"kapazitaet_kwh": 15.4},
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Neu 30.8",
        anschaffungsdatum=date(2025, 7, 1), aktiv=True,
        anschaffungskosten_gesamt=8000.0,
        parameter={"kapazitaet_kwh": 30.8},
    ))
    await db.commit()
    return anlage.id


async def test_community_meldet_nur_das_heutige_geraet(db):
    anlage_id = await _anlage_mit_ersetztem_speicher(db)

    daten = await prepare_community_data(db, anlage_id, include_monatswerte=False)

    assert daten["speicher_kwh"] == 30.8, (
        "46,2 wäre die Summe der Gerätegeschichte — der Datensatz beschreibt "
        "aber die heutige Ausstattung."
    )
    assert daten["speicher_kwh"] is not None, (
        "Der Filter darf den Speicher nicht ganz verschwinden lassen — er ist "
        "vorhanden, nur eben einer statt zwei."
    )


async def test_jahresbericht_nimmt_die_kapazitaet_zum_stichtag(db):
    """Im Wechseljahr sind beide Geräte „aktiv im Jahr" — die Anlage hatte
    trotzdem nie 46,2 kWh."""
    anlage_id = await _anlage_mit_ersetztem_speicher(db)

    ctx_wechseljahr = await build_jahresbericht_context(db, anlage_id, jahr=2025)
    assert ctx_wechseljahr["speicher"]["kapazitaet_kwh"] == 30.8

    ctx_vorjahr = await build_jahresbericht_context(db, anlage_id, jahr=2024)
    assert ctx_vorjahr["speicher"]["kapazitaet_kwh"] == 15.4, (
        "2024 gab es das neue Gerät noch nicht — der Bericht eines "
        "abgelaufenen Jahres darf nicht die heutige Anlage beschreiben."
    )

    ctx_alle = await build_jahresbericht_context(db, anlage_id, jahr=None)
    assert ctx_alle["speicher"]["kapazitaet_kwh"] == 30.8, (
        "Ohne Jahresfilter gilt der heutige Bestand, nicht die Summe aller je "
        "erfassten Geräte."
    )
