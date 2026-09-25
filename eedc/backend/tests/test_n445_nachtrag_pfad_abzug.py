"""**Der Nachtrag-Pfad zieht denselben Abzug wie der Abschluss** (WK-06, Nachbesserung 1).

## Warum es diese Datei gibt — und warum sie nicht in der Schwesterdatei steht

`test_n445_kuehlstrom_im_f5_heizstrom.py` misst die Regel **SOLL-§9-E7/Option A**
(*„abgezogen wird nur, was im Nenner steht"*) auf der Layer-Ebene: rein, ohne
Datenbank, an `funktionsfremd_abzug_kwh` und ihren zwei Faltungen. Sie deckt die
**Regel** vollständig ab.

⛔ **Was sie nicht deckt, ist die VERDRAHTUNG des zweiten Wegs.** Ein Monat ohne
Abschluss hat keine `modus_strom_*`-Felder in seiner IMD-Zeile — seine Aufteilung
wird aus der Tagesebene **nachgetragen** (F-52,
`lade_modus_split_ohne_abschluss`). Diesen Weg gehen **zwei** Stellen, und beide
mussten für Option A eigens angefasst werden:

* `services/monats_fakten/laden.py::_ergaenze_modus_split_ohne_abschluss` — für
  Komponenten-Hub, Cockpit Monat/Jahr und die Auswertungs-Tabelle;
* `api/routes/ha_export/investition_sensoren.py`, WP-Zweig — er faltet seine IMD-Zeilen **je
  Investition** (bekannte P10-Restschuld) und geht deshalb nicht über die
  Monats-Fakten.

⭐ **Der Anlass ist ein Fehler in genau dieser Verdrahtung, und er war stumm.**
Beim Bau von Option A stand im Monats-Nachtrag zunächst
`inv_by_id.get(inv_id)` — die Split-Abbildung ist aber nach Investitions-ID als
**Zeichenkette** gekeyt, `inv_by_id` nach `int`. Der Nachschlag wäre still ins
Leere gelaufen (`None` ⇒ keine Parameter ⇒ „keine getrennte Strommessung"), und
der Abzug wäre für **jede** Anlage gezogen worden — also genau der Defekt, den
Option A beseitigt, nur unbemerkt wieder eingebaut. Gefunden beim Lesen, nicht
von einer Probe. **Diese Datei ist die Probe, die es hätte sein müssen.**

## Die Anlage

Dieselben Zahlen wie in der Schwesterdatei, damit die Fälle vergleichbar bleiben:
Heizen 750 kWh Strom · Warmwasser 200 · Wärme 3000 + 600 = 3600 kWh. Die
IMD-Zeile trägt **keine** `modus_*`-Felder (kein Abschluss); die Aufteilung
entsteht aus einer Tagesspur, die auf 100 kWh normiert wird ⇒ Heizen 70 ·
**Kühlen 30**.

| | Nenner | Arbeitszahl |
| --- | --- | --- |
| F5, **vor** Option A (Abzug 30) | 920 | 3,91 |
| F5, **nach** Option A (Abzug 0) | **950** | **3,79** |
| ohne getrennte Strommessung (Abzug 30, richtig — W-14) | **920** | **3,91** |

Die zwei Zeilen unterscheiden sich um **eine** Bedingung; jede Probe hier misst
genau sie.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.betriebsmodus import AUS, HEIZEN, KUEHLEN
from backend.models import Anlage, Investition
from backend.models.investition import InvestitionMonatsdaten
from backend.models.tages_energie_profil import (
    TagesEnergieProfil,
    TagesZusammenfassung,
)

JAHR, MONAT = 2025, 6
TAG = date(JAHR, MONAT, 10)

#: F5 — die zwei gemessenen Zähler plus die Wärme. **Ohne** `modus_*`-Felder:
#: Das ist der reale Zustand eines Monats ohne Abschluss.
IMD_F5 = {
    "strom_heizen_kwh": 750.0,
    "strom_warmwasser_kwh": 200.0,
    "heizenergie_kwh": 3000.0,
    "warmwasser_kwh": 600.0,
}
#: Dasselbe Gerät mit **einem** Gesamtzähler — derselbe Strom, andere Ablage.
IMD_OHNE_SPLIT = {
    "stromverbrauch_kwh": 950.0,
    "heizenergie_kwh": 3000.0,
    "warmwasser_kwh": 600.0,
}


async def _anlage(db, *, getrennt: bool, imd: dict) -> tuple[Anlage, Investition]:
    """Anlage + eine Wärmepumpe, IMD-Zeile ohne Split, Tagesspur mit Kühlanteil."""
    anlage = Anlage(anlagenname="WK06-Nachtrag", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Wärmepumpe",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=20000.0,
        parameter={"getrennte_strommessung": True} if getrennt else {},
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=JAHR, monat=MONAT,
        verbrauch_daten=dict(imd), source_provenance={},
    ))
    # Die Tagesspur — sie ist die EINZIGE Quelle der Aufteilung dieses Monats.
    # ⚠ `komponenten` führt die Wärmepumpe negativ (Leistungspfad, Senke); die
    # Tages-Zählersumme daneben ist positiv. Der Split wird auf sie normiert.
    for stunde, (modus, kwh) in enumerate([
        (HEIZEN, 7.0), (KUEHLEN, 3.0), (AUS, 0.0),
    ]):
        db.add(TagesEnergieProfil(
            anlage_id=anlage.id, datum=TAG, stunde=stunde,
            komponenten={f"waermepumpe_{inv.id}": -kwh},
            betriebsmodus_je_wp={str(inv.id): modus},
        ))
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=TAG,
        komponenten_kwh={f"waermepumpe_{inv.id}": 100.0},
    ))
    await db.commit()
    return anlage, inv


# ═══════════════════════════════════════════════════════════════════════════
# 1 · Monats-Nachtrag — `monats_fakten._ergaenze_modus_split_ohne_abschluss`
# ═══════════════════════════════════════════════════════════════════════════


async def _wp_fakten(db, anlage_id):
    from backend.services.monats_fakten import lade_monats_fakten

    fakten = await lade_monats_fakten(
        db, anlage_id, von=(JAHR, MONAT), bis=(JAHR, MONAT),
    )
    assert fakten, "Der Monat fehlt ganz — die Fixture trägt nicht."
    return fakten[0].wp


async def test_nachtrag_der_abgeleitete_kuehlanteil_kuerzt_den_f5_nenner_nicht(db):
    """**Der Kern: Option A gilt auch auf dem Nachtrag-Weg.**

    Kein Abschluss, kein `modus_strom_*`-Feld in der Zeile — die Aufteilung
    kommt allein aus der Tagesebene. Sie ist damit **immer** abgeleitet, und an
    einer F5-Anlage darf sie den gemessenen Nenner nicht kürzen.

    ⛔ Genau hier saß der `int(inv_id)`-Fehler: Ohne die Umwandlung findet der
    Nachschlag die Investition nicht, hält sie für „nicht getrennt messend" und
    zieht ab.
    """
    anlage, _inv = await _anlage(db, getrennt=True, imd=IMD_F5)
    wp = await _wp_fakten(db, anlage.id)

    assert wp.hat_split is True
    assert wp.hat_modus_split, "Die Tagesspur ist nicht angekommen."
    assert wp.modus_strom_kuehlen_kwh == pytest.approx(30.0), (
        "Die MENGE steht unverändert — sie trägt Aufteilung und Balken (K1)."
    )
    assert wp.modus_strom_funktionsfremd_abzug_kwh == pytest.approx(0.0), (
        "Der ABZUG ist 0: eine Verteilung kürzt keinen gemessenen F5-Nenner."
    )


async def test_nachtrag_ohne_getrennte_strommessung_bleibt_der_abzug(db):
    """**Die Gegenprobe, ohne die die erste nichts beweist** (W-14).

    Derselbe Weg, dieselbe Tagesspur, ein Gesamtzähler statt zweier: Hier
    steckt der Kühlbetrieb im Nenner, und der Abzug ist richtig.
    """
    anlage, _inv = await _anlage(db, getrennt=False, imd=IMD_OHNE_SPLIT)
    wp = await _wp_fakten(db, anlage.id)

    assert wp.hat_split is False
    assert wp.modus_strom_kuehlen_kwh == pytest.approx(30.0)
    assert wp.modus_strom_funktionsfremd_abzug_kwh == pytest.approx(30.0), (
        "Ohne getrennte Messung ist der Nenner der Zählerstand des ganzen "
        "Geräts — der Kühlbetrieb steckt darin."
    )


async def test_nachtrag_die_arbeitszahl_beider_anlagen(db):
    """Die Zahlen, die daraus entstehen — an den Einzelwerten belegt.

    Dieselbe Physik, dieselbe Tagesspur, eine andere Strom-Ablage:
    **3,79** gegen **3,91**. Der Unterschied ist ausschließlich der Nenner.
    """
    from backend.core.berechnungen.waermepumpe_kennzahl import arbeitszahl

    a_f5, _ = await _anlage(db, getrennt=True, imd=IMD_F5)
    a_ohne, _ = await _anlage(db, getrennt=False, imd=IMD_OHNE_SPLIT)

    wp_f5 = await _wp_fakten(db, a_f5.id)
    wp_ohne = await _wp_fakten(db, a_ohne.id)

    az_f5 = arbeitszahl(
        wp_f5.waerme_kwh, wp_f5.strom_kwh,
        strom_funktionsfremd_kwh=wp_f5.modus_strom_funktionsfremd_abzug_kwh,
    )
    az_ohne = arbeitszahl(
        wp_ohne.waerme_kwh, wp_ohne.strom_kwh,
        strom_funktionsfremd_kwh=wp_ohne.modus_strom_funktionsfremd_abzug_kwh,
    )

    assert wp_f5.strom_kwh == pytest.approx(950.0)
    assert wp_ohne.strom_kwh == pytest.approx(950.0)
    assert az_f5.nenner_kwh == pytest.approx(950.0)
    assert az_ohne.nenner_kwh == pytest.approx(920.0)
    assert az_f5.wert == pytest.approx(3.789, abs=0.001)
    assert az_ohne.wert == pytest.approx(3.913, abs=0.001)


# ═══════════════════════════════════════════════════════════════════════════
# 2 · HA-Export — derselbe Nachtrag, eigener Faltweg (P10-Restschuld)
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠ **Warum das eine zweite Probe braucht und nicht dieselbe ist:**
# `ha_export.py` geht **nicht** über die Monats-Fakten. Er summiert seine
# IMD-Zeilen selbst und ruft `lade_modus_split_ohne_abschluss` eigenständig —
# eine zweite Verdrahtung derselben Regel. Genau davor warnt der Modul-Kopf von
# `modus_split_monat.py` seit F-52: *„eine Regel, die an zwei Stellen nachgebaut
# wird, driftet."* Der Sensor verlässt eedc; eine Drift hier lebt in fremden
# Dashboards und in der Langzeitstatistik weiter.


async def _wp_arbeitszahl_sensor(db, inv):
    """Der Wert des Sensors `wp_cop_durchschnitt` — der ausgelieferte Weg.

    ⚠ Bewusst über `calculate_investition_sensors` statt über eine eigens
    freigelegte Zwischengröße: Was in `arbeitszahl(...)` als
    `strom_funktionsfremd_kwh` ankommt, ist an der **Zahl** messbar, und ein
    Produktfeld nur für eine Probe wäre die falsche Richtung.
    """
    from backend.api.routes.ha_export import calculate_investition_sensors

    sensoren = await calculate_investition_sensors(db, inv, None)
    treffer = [s for s in sensoren if s.definition.key == "wp_cop_durchschnitt"]
    assert len(treffer) == 1, (
        f"Sensor wp_cop_durchschnitt nicht eindeutig: {len(treffer)}"
    )
    return treffer[0]


async def test_ha_export_nachtrag_kuerzt_den_f5_nenner_nicht(db):
    """**Der HA-Sensor rechnet wie das Cockpit** — 3,79, nicht 3,91.

    Bis zum 12.09.2026 zog auch dieser Zweig den abgeleiteten Kühlanteil ab.
    Der Sensor geht nach Home Assistant und dort in Automationen und
    Langzeitstatistik; eine Abweichung hier ist teurer als in jeder Sicht.
    """
    _anl, inv = await _anlage(db, getrennt=True, imd=IMD_F5)
    sv = await _wp_arbeitszahl_sensor(db, inv)

    assert sv.value == pytest.approx(3.789, abs=0.001), (
        f"Der Sensor rechnet mit dem falschen Nenner: {sv.value}"
    )
    # N-555 (§12): deutsche Schreibweise über `core/zahlenformat.py`.
    assert sv.berechnung == "3.600 / 950"


async def test_ha_export_nachtrag_ohne_f5_bleibt_der_abzug(db):
    """Gegenprobe im selben Weg: ohne getrennte Messung bleibt der Abzug."""
    _anl, inv = await _anlage(db, getrennt=False, imd=IMD_OHNE_SPLIT)
    sv = await _wp_arbeitszahl_sensor(db, inv)

    assert sv.value == pytest.approx(3.913, abs=0.001)
    assert sv.berechnung == "3.600 / 920"


async def test_ha_export_und_monats_fakten_sagen_dasselbe(db):
    """**S1 (SOLL §3.3): dieselbe Größe trägt überall denselben Wert.**

    Zwei Faltwege, eine Zahl. Ohne diese Probe könnte einer der beiden für sich
    grün sein und trotzdem etwas anderes ausliefern als der andere — die
    F-56-Klasse, und sie ist an genau dieser Stelle schon einmal eingetreten.
    """
    from backend.core.berechnungen.waermepumpe_kennzahl import arbeitszahl

    anlage, inv = await _anlage(db, getrennt=True, imd=IMD_F5)

    wp = await _wp_fakten(db, anlage.id)
    aus_fakten = arbeitszahl(
        wp.waerme_kwh, wp.strom_kwh,
        strom_funktionsfremd_kwh=wp.modus_strom_funktionsfremd_abzug_kwh,
    )
    aus_sensor = await _wp_arbeitszahl_sensor(db, inv)

    assert aus_sensor.value == pytest.approx(aus_fakten.wert, abs=0.001)
