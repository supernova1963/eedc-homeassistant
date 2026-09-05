"""Abgabe an Dritte — der dritte Weg der Netzpunkt-Bilanz (Konzept
KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG §9.2, Entscheid 05.09.2026, #402 / N-378).

Ein Vermieter gibt über einen Übergabe-Wechselrichter Strom an die Bewohner ab —
mit Zähler an der Übergabestelle. Bis zum Bau stand das Gerät als *Sonstiges/
Erzeuger*: sein W-Integral zählte als Erzeugung hinter dem Hauszähler und, weil es
den Zähler nie erreichte, als **Eigenverbrauch**. Gemessen an der nachgestellten
Anlage (PV 1.000, Einspeisung 200, Netzbezug 300, Abgabe 224):

    heute   Eigenverbrauch 1.024 kWh · Autarkie 77,3 %
    §9.2    Eigenverbrauch   576 kWh · Autarkie 65,8 % · Abgabe 224 als eigene Zeile

Vier Sichten, eine Bilanz: Monats-Fakten (Cockpit → Monat), Jahresroute, HA-Export
und Finanz-Aggregat (Community-Payload) — und die Gegenprobe: dasselbe Gerät als
*Erzeuger* liefert weiter 1.024 (ein echtes BHKW bleibt Erzeugung).

Schwesterdateien: test_n250_sonstiges_richtung.py (Richtungs-SoT),
test_n244_sonstiges_kategorie_sot.py (Kategorie-SoT), test_erzeuger_einspeise_erloes.py
(§9 Weg 2, der Erlös bleibt).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: F401
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung  # noqa: F401

JAHR, MONAT = 2025, 7


async def _robert(db, kategorie: str):
    a = Anlage(anlagenname=f"robert-{kategorie}", leistung_kwp=10.0,
               installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV",
                     anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=10000.0,
                     leistung_kwp=10.0)
    db.add(pv)
    await db.flush()
    so = Investition(anlage_id=a.id, typ="sonstiges", bezeichnung="Victron-EG",
                     anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1000.0,
                     parameter={"kategorie": kategorie})
    db.add(so)
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=JAHR, monat=MONAT, einspeisung_kwh=200.0,
                       netzbezug_kwh=300.0))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=JAHR, monat=MONAT,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    daten = ({"abgabe_kwh": 224.0, "einspeise_erloes_euro": 40.0} if kategorie == "abgabe"
             else {"erzeugung_kwh": 224.0, "einspeisung_kwh": 224.0, "einspeise_erloes_euro": 40.0})
    db.add(InvestitionMonatsdaten(investition_id=so.id, jahr=JAHR, monat=MONAT, verbrauch_daten=daten))
    db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0, gueltig_ab=date(2025, 1, 1)))
    await db.commit()
    return a, so


@pytest.mark.asyncio
async def test_vier_sichten_eine_bilanz(db):
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export import calculate_anlage_sensors
    from backend.services.monats_fakten import (
        finanz_zeile_eingabe, kennzahlen_aus_fakten, lade_monats_fakten,
    )
    from backend.core.berechnungen.finanz_aggregat import FinanzMonatsZeile, berechne_finanz_aggregat

    a, so = await _robert(db, "abgabe")
    fakten = await lade_monats_fakten(db, a.id, von=(JAHR, MONAT), bis=(JAHR, MONAT))
    f = fakten[0]
    # Fakten: das Gerät ist keine Erzeugung mehr, seine Abgabe steht eigens.
    assert f.erzeugung.hinter_zaehler_kwh == pytest.approx(1000.0)
    assert f.sonstiges.erzeugung_kwh == 0.0
    assert f.sonstiges.abgabe_kwh == pytest.approx(224.0)
    assert f.sonstiges.je_geraet[so.id].abgabe_kwh == pytest.approx(224.0)
    assert f.sonstiges.einspeise_erloes_euro == pytest.approx(40.0), "§9 Weg 2 bleibt"
    assert f.kennzahlen.eigenverbrauch_kwh == pytest.approx(576.0)
    assert f.kennzahlen.autarkie_prozent == pytest.approx(65.8, abs=0.05)
    assert kennzahlen_aus_fakten(fakten).eigenverbrauch_kwh == pytest.approx(576.0)

    # Cockpit → Monat (eigene Bilanz-Nachbildung der Route)
    m = await get_aktueller_monat(a.id, jahr=JAHR, monat=MONAT, db=db)
    assert m.eigenverbrauch_kwh == pytest.approx(576.0)
    assert m.autarkie_prozent == pytest.approx(65.8, abs=0.05)
    assert m.abgabe_dritte_kwh == pytest.approx(224.0)
    assert m.sonstiges_erzeugung_kwh is None
    geraet = next(g for g in m.sonstiges_geraete if g.kategorie == "abgabe")
    assert geraet.abgabe_kwh == pytest.approx(224.0) and geraet.erloes_euro == pytest.approx(40.0)

    # Cockpit → Jahr (Jahresroute)
    j = await get_cockpit_uebersicht(a.id, jahr=JAHR, db=db)
    assert j.eigenverbrauch_kwh == pytest.approx(576.0)
    assert j.autarkie_prozent == pytest.approx(65.8, abs=0.05)

    # HA-Export (anlagenweite Sensoren)
    export = {sv.definition.key: sv.value for sv in await calculate_anlage_sensors(db, a)}
    assert export["eigenverbrauch_gesamt_kwh"] == pytest.approx(576.0)
    assert export["autarkie_prozent"] == pytest.approx(65.8, abs=0.05)

    # Finanz-Aggregat (Aussichten, Community): dieselbe Menge, keine EV-Ersparnis
    # für abgegebene kWh (N-375-Klasse).
    eingabe = finanz_zeile_eingabe(f)
    assert eingabe.abgabe_dritte_kwh == pytest.approx(224.0)
    zeile = FinanzMonatsZeile(einspeisung_kwh=200.0, netzbezug_kwh=300.0, pv_erzeugung_kwh=1000.0,
                              abgabe_dritte_kwh=224.0, netzbezug_preis_cent=30.0,
                              einspeiseverguetung_cent=8.0)
    agg = berechne_finanz_aggregat([zeile])
    assert agg.eigenverbrauch_kwh == pytest.approx(576.0)
    assert agg.ev_ersparnis_euro == pytest.approx(172.80, abs=0.01), "abgegebene kWh tragen keine Ersparnis"


@pytest.mark.asyncio
async def test_gegenprobe_ein_erzeuger_bleibt_erzeugung(db):
    """Ein echtes BHKW unter *Erzeuger* zählt weiter hinter den Zähler — der
    dritte Weg ändert die zwei bestehenden nicht."""
    from backend.services.monats_fakten import lade_monats_fakten

    a, _ = await _robert(db, "erzeuger")
    f = (await lade_monats_fakten(db, a.id, von=(JAHR, MONAT), bis=(JAHR, MONAT)))[0]
    assert f.erzeugung.hinter_zaehler_kwh == pytest.approx(1224.0)
    assert f.sonstiges.abgabe_kwh == 0.0
    assert f.kennzahlen.eigenverbrauch_kwh == pytest.approx(1024.0)


def test_registry_kennt_die_kategorie_mit_eigener_richtung():
    from backend.core.field_definitions import (
        INVESTITION_FELDER, SONSTIGES_FELDER_UNGEPFLEGT, get_felder_fuer_sonstiges,
        ist_abgabe_kategorie, ist_gepflegte_sonstiges_kategorie, sonstiges_feld_reihenfolge,
    )
    from backend.core.berechnungen.energie import sonstiges_richtung

    assert ist_gepflegte_sonstiges_kategorie("abgabe") and ist_abgabe_kategorie("abgabe")
    felder = {f["feld"] for f in INVESTITION_FELDER["sonstiges"]["abgabe"]}
    assert felder == {"abgabe_kwh", "einspeise_erloes_euro"}
    assert {f["feld"] for f in get_felder_fuer_sonstiges("abgabe")} == felder
    assert sonstiges_feld_reihenfolge("abgabe") == ("abgabe_kwh",)
    assert sonstiges_richtung("abgabe", hat_erzeugung=True) == "abgabe"
    # Ein Gerät ohne gepflegte Kategorie bekommt KEIN Abgabe-Feld angeboten —
    # es würde als Verbrauch gelesen (N-244-Klasse mit anderem Vorzeichen).
    assert "abgabe_kwh" not in {f["feld"] for f in SONSTIGES_FELDER_UNGEPFLEGT}
