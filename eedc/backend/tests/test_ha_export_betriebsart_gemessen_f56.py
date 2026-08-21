"""F-56 — die HA-/MQTT-Sensoren kennen die **gemessene** Betriebsart-Aufteilung.

**Was schiefging.** Mit v4.0.24 kann eine Split-Klimaanlage ihren Verbrauch je
Betriebsart als Zähler mitbringen (``betriebsart_strom_heizen_kwh`` …), statt
ihn aus dem Betriebsmodus ableiten zu lassen. Cockpit, Komponenten-Hub und
Monats-Fakten gehen über die Weiche *gemessen schlägt abgeleitet*; der Export
faltet seine IMD-Zeilen je Investition (P10-Restschuld) und hatte die Weiche
**daneben nachgebaut — ohne den Gemessen-Zweig**:

    float(d.get(MODUS_ABDECKUNG_FELD) or 0) > 0        # Export, F-56
    … > 0 or hat_gemessene_betriebsart(daten)          # monats_fakten.py:706

Folge: Wer die neuen Zähler zuordnete — also genau der Anwender, an den sich
das Release richtet — sah die Aufteilung in eedc und bekam in Home Assistant
**keinen Wert**. Zwei Zahlen für dieselbe Größe, und die Sensorseite schwieg.

⚑ **Der Modul-Kopf von ``modus_split_monat.py`` warnt seit F-52 wörtlich davor**
(*„eine Regel, die an zwei Stellen nachgebaut wird, driftet"*) — sie ist im
selben Paket ein zweites Mal gedriftet. Die Weiche liegt jetzt als **eine**
Formel im Layer (``modus_strom_zeile``), und dieser Wächter prüft sie **am
Endpunkt**, nicht am Layer: ein grüner Layer-Test hätte F-56 nicht gefunden,
denn der Layer war nie falsch.

Die Matrix ist der Kern — **gemessen · abgeleitet · beides · keins**. Ohne die
Zeile „keins" wäre der Test auch grün, wenn der Sensor immer erschiene.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.ha_export import calculate_investition_sensors
from backend.core.betriebsmodus import (
    BETRIEBSART_STROM_FELD,
    HEIZEN,
    KUEHLEN,
    MODUS_ABDECKUNG_FELD,
    MODUS_STROM_FELD,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.strompreis import Strompreis

JAHR, MONAT = 2024, 6
STROM_GESAMT = 300.0

#: Nur die Zähler — so sieht eine Zeile aus, die v4.0.24 ermöglicht hat.
GEMESSEN = {
    "stromverbrauch_kwh": STROM_GESAMT,
    BETRIEBSART_STROM_FELD[HEIZEN]: 120.0,
    BETRIEBSART_STROM_FELD[KUEHLEN]: 180.0,
}
#: Der Weg über den Betriebsmodus, wie ihn v4.0.21 gebaut hat.
ABGELEITET = {
    "stromverbrauch_kwh": STROM_GESAMT,
    MODUS_STROM_FELD[HEIZEN]: 90.0,
    MODUS_STROM_FELD[KUEHLEN]: 210.0,
    MODUS_ABDECKUNG_FELD: 700.0,
}
#: Weder noch — die Sensoren müssen schweigen statt „0 kWh geheizt" zu behaupten.
OHNE = {"stromverbrauch_kwh": STROM_GESAMT}


async def _sensoren(db, verbrauch_daten: dict) -> dict[str, float]:
    anlage = Anlage(
        anlagenname="F-56", leistung_kwp=5.0, installationsdatum=date(JAHR - 1, 1, 1)
    )
    db.add(anlage)
    await db.flush()
    wp = Investition(
        anlage_id=anlage.id,
        typ="waermepumpe",
        bezeichnung="Klima",
        anschaffungsdatum=date(JAHR - 1, 1, 1),
        anschaffungskosten_gesamt=5000.0,
        aktiv=True,
        parameter={"wp_art": "luft_luft"},
    )
    db.add(wp)
    await db.flush()
    db.add(
        InvestitionMonatsdaten(
            investition_id=wp.id,
            jahr=JAHR,
            monat=MONAT,
            verbrauch_daten=dict(verbrauch_daten),
            source_provenance={},
        )
    )
    tarif = Strompreis(
        anlage_id=anlage.id,
        netzbezug_arbeitspreis_cent_kwh=30.0,
        einspeiseverguetung_cent_kwh=8.0,
        gueltig_ab=date(JAHR - 1, 1, 1),
    )
    db.add(tarif)
    await db.commit()

    werte = await calculate_investition_sensors(db, wp, tarif)
    return {sv.definition.key: sv.value for sv in werte}


@pytest.mark.asyncio
async def test_gemessene_betriebsart_erreicht_die_sensoren(db):
    """Der eigentliche F-56-Fall: nur Zähler, keine Modus-Abdeckung.

    Vor dem Fix fehlten **beide** Sensoren, weil die Sichtbarkeit allein an
    ``modus_abdeckung_h > 0`` hing — und die ist bei gemessenen Zählern zu
    Recht 0: sie ist die Zeitbasis des *abgeleiteten* Wegs.
    """
    werte = await _sensoren(db, GEMESSEN)
    assert werte.get("wp_strom_heizen_modus_kwh") == pytest.approx(120.0)
    assert werte.get("wp_strom_kuehlen_modus_kwh") == pytest.approx(180.0)


@pytest.mark.asyncio
async def test_abgeleiteter_weg_bleibt_unveraendert(db):
    """Gegenrichtung — der v4.0.21-Weg darf sich durch den Fix nicht bewegen."""
    werte = await _sensoren(db, ABGELEITET)
    assert werte.get("wp_strom_heizen_modus_kwh") == pytest.approx(90.0)
    assert werte.get("wp_strom_kuehlen_modus_kwh") == pytest.approx(210.0)


@pytest.mark.asyncio
async def test_gemessen_schlaegt_abgeleitet_und_addiert_nicht(db):
    """Beides in einer Zeile: die Zähler gewinnen — **ohne** zu addieren.

    Das ist die Doppelzählungs-Probe. 120 + 90 = 210 wäre die Klasse, die
    dieses Projekt beim BKW, beim Speicher und beim Wallbox/E-Auto-Pool je
    einmal getroffen hat.
    """
    werte = await _sensoren(db, {**ABGELEITET, **GEMESSEN})
    assert werte.get("wp_strom_heizen_modus_kwh") == pytest.approx(120.0)
    assert werte.get("wp_strom_kuehlen_modus_kwh") == pytest.approx(180.0)


@pytest.mark.asyncio
async def test_ohne_aufteilung_schweigen_die_sensoren(db):
    """Ohne beides bleibt der Sensor **weg** — nicht 0.

    Eine 0 hieße „hat nicht geheizt" und lebte in der HA-Langzeitstatistik
    weiter. Ohne diese Probe wäre der Test oben auch grün, wenn der Sensor
    immer erschiene — dann bewiese er nichts.
    """
    werte = await _sensoren(db, OHNE)
    assert "wp_strom_heizen_modus_kwh" not in werte
    assert "wp_strom_kuehlen_modus_kwh" not in werte
