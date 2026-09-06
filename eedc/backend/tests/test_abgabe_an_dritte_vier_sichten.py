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


# ============================================================================
# Die Geldseite (§9.2 Geldseite, Entscheid 06.09.2026 / E1) — #402
# ============================================================================


@pytest.mark.asyncio
async def test_auswertungen_finanzen_traegt_den_gepflegten_erloes(db):
    """Die FÜNFTE Sicht — und die einzige, die den Erlös nicht trug.

    ``test_netto_ertrag_vier_wege_symmetrie.py`` vergleicht Cockpit ·
    Aussichten · PDF · HA-Export. Die Route hinter *Auswertungen → Finanzen*
    (``list_monatsdaten_aggregiert``) ist dort **nicht** dabei — und genau sie
    reichte ``erzeuger_erloes_euro`` nicht in ``berechne_finanz_aggregat``.
    Ergebnis: dieselbe Kachel „Netto-Ertrag (PV)" nannte in Cockpit → Jahr eine
    andere Zahl als in Auswertungen → Finanzen, und der HA-Sensor eine dritte.

    Der Melder hat genau das gesehen (#402, 06.09.2026): *„taucht jetzt auch
    als Name--Einspeisung auf … allerdings nicht mehr in den Grafen darüber"*.

    ⚠ Geprüft wird **beides** — dass der Betrag im Netto-Ertrag steckt UND dass
    er daneben einzeln ausgewiesen ist. Nur das erste wäre eine Zahl ohne
    Erklärung; nur das zweite wäre eine Erklärung ohne Wirkung.
    """
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    a, _so = await _robert(db, "abgabe")
    zeile = (await list_monatsdaten_aggregiert(anlage_id=a.id, jahr=JAHR, db=db))[0]

    # Einzeln ausgewiesen — die Sicht kann ihn benennen.
    assert zeile.erzeuger_erloes_euro == pytest.approx(40.0), (
        f"Erlös nicht ausgewiesen: {zeile.erzeuger_erloes_euro}")

    # Und er wirkt: Netto-Ertrag = Einspeise-Erlös + EV-Ersparnis + Erlös.
    erwartet = (
        zeile.einspeise_erloes_euro
        + zeile.ev_ersparnis_euro
        + zeile.bkw_ersparnis_euro
        + 40.0
        - zeile.ust_eigenverbrauch_euro
    )
    assert zeile.netto_ertrag_euro == pytest.approx(erwartet, abs=0.02), (
        f"Netto-Ertrag {zeile.netto_ertrag_euro} enthält die 40 € nicht "
        f"(erwartet {erwartet})")


@pytest.mark.asyncio
async def test_der_erloes_bleibt_aus_dem_einspeise_erloes_heraus(db):
    """Die Gegenrichtung — und die Grenze, die bleibt.

    ``einspeise_erloes_euro`` bewertet den **Anlagenzähler** mit dem EINEN Satz
    der Anlage (§8/9). Ein Gerät mit eigenem Vergütungssatz hat per Definition
    einen anderen; sein Betrag darf dort **nicht** hinein, sonst behauptet die
    Formel „Einspeisung × Einspeisevergütung" eine Rechnung, die niemand
    angestellt hat.

    Fixture: Einspeisung 200 kWh × 8 ct = 16,00 € — die 40 € stehen daneben,
    nicht darin.
    """
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    a, _so = await _robert(db, "abgabe")
    zeile = (await list_monatsdaten_aggregiert(anlage_id=a.id, jahr=JAHR, db=db))[0]

    assert zeile.einspeise_erloes_euro == pytest.approx(16.0, abs=0.02), (
        f"Einspeise-Erlös {zeile.einspeise_erloes_euro} ≠ 200 kWh × 8 ct — "
        "der gepflegte Erlös ist hineingerutscht")
