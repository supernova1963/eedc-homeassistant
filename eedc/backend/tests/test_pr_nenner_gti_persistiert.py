"""Der Nenner der Performance Ratio steht in der Zeile — N-384.

**Der Befund.** ``aggregate_day`` rechnet die Performance Ratio gegen die
**Modulebenen-Einstrahlung** (GTI, ``aggregator.py``: ``theoretisch_kwh =
gti_summe * kwp / 1000``). Das ist richtig und ausdrücklich entschieden — mit der
horizontalen Globalstrahlung liefen PR-Werte im Winter künstlich auf 1,5–2,8
(#139, Kommentar über der Rechnung).

Gespeichert wurde bis zum 03.09.2026 aber **nur** die horizontale Summe
(``strahlung_summe_wh_m2``), und genau die stand in der Anzeige neben der
Kennzahl: *„bei X kWh/m² Einstrahlung"* unter der Formel *„Ertrag ÷ (Einstrahlung
× kWp)"*. Die Kachel setzte damit in ihre eigene Formel eine Größe ein, die nicht
in ihr vorkommt. **Wer nachrechnete, bekam zwangsläufig eine andere Zahl — und
konnte den Widerspruch nicht auflösen, weil der echte Nenner nirgends stand.**

Aufgefallen an **coolxmad** (GitHub #353), der seit dem 30.07.2026 an dieser Zahl
misst: sein Daten-Check meldet PR 1,05–1,16 an 7 von 31 Tagen, er hat vier
Ursachen einzeln ausgeschlossen — und die Frage „ist der Zähler zu groß oder der
Nenner zu klein?" war ohne den Nenner nicht entscheidbar.

**Was diese Probe festhält, in zwei Richtungen:**

1. Der Wert wird geschrieben, und er ist **derselbe**, durch den die PR geteilt
   hat. Nicht „irgendeine Zahl steht da": ``PR × GTI × kWp / 1000`` muss den
   Ertrag zurückgeben. Ein Nenner, der nicht auf seinen eigenen Bruch führt, wäre
   schlimmer als gar keiner.
2. Ohne GTI bleibt die Spalte **NULL** — nicht 0. NULL heißt „nicht erhoben"; eine
   0 wäre eine Behauptung, und die Anzeige würde daraus eine Bezugsgröße machen,
   die es nie gab.

⛔ **An ``aggregate_day`` gehängt, nicht an eine Hilfsfunktion** — dieselbe
Begründung wie in ``test_slot_konvention_leistungspfad.py``: eine Funktion gegen
sich selbst zu prüfen ist eine Tautologie und kann nie rot werden. Geprüft wird
der echte Schreibpfad.

⛔ **Ohne Anlagendaten.** Wetter und Stundenwerte werden konstruiert; wer die Probe
liest, soll den Befund am Code nachvollziehen können, nicht an fremden Daten.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.models.investition import Investition
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil.source import Source
from backend.tests import factories

# Eine Sonnenstunde reicht: die PR ist ein Tagesquotient, kein Stundenwert.
PV_STUNDE = 8
PV_KWH = 5.0
KWP = 10.0

# GTI und GHI bewusst VERSCHIEDEN — sonst könnte die Probe nicht unterscheiden,
# welche der beiden Größen gespeichert wurde. Das ist der ganze Punkt des Funds.
GHI_WM2 = 400.0   # horizontal
GTI_WM2 = 500.0   # Modulebene (bei geneigten Modulen höher)


def _lts_nur_in_slot(slot: int, wert: float) -> dict:
    return {
        h: {
            "pv": wert if h == slot else 0.0,
            "einspeisung": 0.0,
            "netzbezug": 0.0,
            "verbrauch": 0.0,
            "wp": None,
            "wallbox": None,
            "batterie_netto": 0.0,
            "verbrauch_sonstiges": None,
        }
        for h in range(24)
    }


def _wetter(mit_gti: bool) -> dict:
    """Stundenwetter wie ``_get_wetter_ist`` es liefert — GTI abschaltbar.

    ``mit_gti=False`` bildet den Fall nach, den es real gibt: keine PV-Module mit
    Orientierung, gescheiterter GTI-Abruf, oder eine Zeile aus der Zeit vor der
    Spalte. Dann darf keine Zahl entstehen.
    """
    return {
        h: {
            "temperatur_c": 15.0,
            "globalstrahlung_wm2": GHI_WM2 if h == PV_STUNDE else 0.0,
            "gti_wm2": (GTI_WM2 if h == PV_STUNDE else 0.0) if mit_gti else None,
            "bewoelkung_prozent": 0.0,
            "niederschlag_mm": 0.0,
            "wetter_code": 0,
        }
        for h in range(24)
    }


async def _fahre_tag(db, name: str, *, mit_gti: bool) -> TagesZusammenfassung:
    anlage = factories.mach_anlage_mit_mapping(name)
    anlage.leistung_kwp = KWP
    db.add(anlage)
    await db.flush()

    db.add(Investition(
        id=None, anlage_id=anlage.id, typ="pv-module", bezeichnung="pv",
        aktiv=True, anschaffungsdatum=date(2020, 1, 1), leistung_kwp=KWP,
    ))
    # Festes Datum statt Prozessuhr: die Suite läuft in drei Zonen (N-167).
    tag = date(2026, 5, 4)
    db.add(MqttEnergySnapshot(
        anlage_id=anlage.id,
        timestamp=datetime.combine(tag, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug",
        value_kwh=100.0,
    ))
    await db.commit()

    from backend.services.energie_profil._helpers import StrompreisStunden
    from backend.services.energie_profil.aggregator import aggregate_day

    with patch(
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value=_lts_nur_in_slot(PV_STUNDE, PV_KWH)),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.energie_profil._helpers._get_strompreis_stunden",
        new=AsyncMock(return_value=StrompreisStunden(sensor={}, boerse={})),
    ), patch(
        "backend.services.energie_profil._helpers._get_wetter_ist",
        new=AsyncMock(return_value=_wetter(mit_gti)),
    ):
        await aggregate_day(anlage, tag, db, source=Source.VOLLBACKFILL_FROM_LTS)
    await db.commit()

    return (await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage.id,
            TagesZusammenfassung.datum == tag,
        )
    )).scalars().one()


@pytest.mark.asyncio
async def test_gti_summe_wird_geschrieben_und_traegt_die_pr(db) -> None:
    """Der gespeicherte Nenner ist DERSELBE, durch den die PR geteilt hat."""
    tz = await _fahre_tag(db, "PrNennerMitGti", mit_gti=True)

    assert tz.gti_summe_wh_m2 == pytest.approx(GTI_WM2), (
        "Die GTI-Tagessumme muss in der Zeile stehen (N-384) — ohne sie ist die "
        "Performance Ratio für niemanden nachrechenbar, auch nicht für uns. "
        f"Erwartet {GTI_WM2} Wh/m², gefunden {tz.gti_summe_wh_m2}."
    )

    # ⭐ Die eigentliche Zusicherung: der Nenner führt auf seinen eigenen Bruch
    # zurück. Eine Zahl, die nur DASTEHT, wäre wertlos — sie muss die sein, mit
    # der gerechnet wurde.
    assert tz.performance_ratio is not None, "Vorbedingung: die PR muss entstanden sein."
    ertrag_rueckgerechnet = tz.performance_ratio * tz.gti_summe_wh_m2 * KWP / 1000
    assert ertrag_rueckgerechnet == pytest.approx(PV_KWH, rel=1e-3), (
        "PR × GTI × kWp / 1000 muss den Ertrag zurückgeben. Tut es das nicht, "
        "steht in der Zeile ein anderer Nenner als der, durch den gerechnet "
        f"wurde — genau der Zustand, den N-384 auflöst. Ertrag {PV_KWH} kWh, "
        f"zurückgerechnet {ertrag_rueckgerechnet:.4f}."
    )


@pytest.mark.asyncio
async def test_gti_und_ghi_werden_nicht_verwechselt(db) -> None:
    """Die beiden Strahlungssummen sind verschiedene Größen und bleiben getrennt.

    Der Fund bestand genau darin, dass die Anzeige die eine für die andere hielt.
    Wären beide Werte im Test gleich, könnte diese Probe den Rückfall nicht sehen.
    """
    tz = await _fahre_tag(db, "PrNennerTrennung", mit_gti=True)

    assert tz.strahlung_summe_wh_m2 == pytest.approx(GHI_WM2), (
        "Die horizontale Summe bleibt, was sie war — sie wird nicht ersetzt, "
        "sondern ergänzt."
    )
    assert tz.gti_summe_wh_m2 != tz.strahlung_summe_wh_m2, (
        "GTI und GHI sind verschiedene Größen. Stehen hier gleiche Werte, ist "
        "entweder die eine in das Feld der anderen geschrieben worden, oder der "
        "Testaufbau hat seine Unterscheidungskraft verloren."
    )


@pytest.mark.asyncio
async def test_ohne_gti_bleibt_die_spalte_leer_statt_null_zu_behaupten(db) -> None:
    """Kein GTI ⇒ NULL, nicht 0 — und dann auch keine Performance Ratio.

    ``None`` heißt „nicht erhoben". Eine 0 wäre eine Behauptung, und die Anzeige
    machte daraus eine Bezugsgröße, die es nie gab — dieselbe Klasse wie der
    Fehler, den N-384 auflöst, nur eine Ebene tiefer.
    """
    tz = await _fahre_tag(db, "PrNennerOhneGti", mit_gti=False)

    assert tz.gti_summe_wh_m2 is None, (
        "Ohne Modulebenen-Einstrahlung darf dort NICHTS stehen — weder 0 noch "
        f"die horizontale Summe. Gefunden: {tz.gti_summe_wh_m2}."
    )
    assert tz.performance_ratio is None, (
        "Ohne GTI gibt es keine PR — das war schon vorher so (#139: ohne GTI "
        "bleibt PR None, statt einen physikalisch unsinnigen Wert zu liefern) "
        "und muss so bleiben."
    )
    # Die GHI ist trotzdem da: sie hängt nicht am GTI-Abruf.
    assert tz.strahlung_summe_wh_m2 == pytest.approx(GHI_WM2)
