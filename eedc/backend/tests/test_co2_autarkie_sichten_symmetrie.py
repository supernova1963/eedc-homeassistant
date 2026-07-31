"""Ein Eigenverbrauch, drei Sichten — CO₂ und Autarkie (Befund **F-1**).

`cockpit/nachhaltigkeit.py` (CO₂-Zeitreihe) und `cockpit/social.py`
(kopierfertiger Monatstext) haben bis 2026-07-31 die komplette Monats-
aggregation nachgebaut — **ohne einen einzigen Zeilen-SoT**: kein
``imd_typ_beitrag``, kein ``berechne_verbrauchs_kennzahlen``, kein E-Mob-Pool.
Beide rechneten

    direktverbrauch = max(0, pv − einspeisung − speicher_ladung)
    eigenverbrauch  = direktverbrauch + speicher_entladung

selbst. Gegenüber dem Kanon fehlten dabei **V2H** (#304), die **Erzeugung
hinter dem Zähler** (BHKW/Mini-KWK, v3.45.4), die **Attribution des E-Mob-Pools**
(#262), der **Dienstwagen-Filter** und die **PV-Auflösung** (P7) — und der
Benzin-Vergleich rechnete mit hartkodierten 7 l/100 km statt mit dem gepflegten
``vergleich_verbrauch_l_100km``.

Kein Test hat das gefunden, weil es für beide Endpoints **gar keinen** gab; die
Vier-Wege-Symmetrie prüft den Netto-Ertrag, nicht CO₂ und Autarkie. Diese Datei
schließt die Lücke auf derselben Fixture-Achse („V2H **und** Erzeuger hinter dem
Zähler", `test_netto_ertrag_vier_wege_symmetrie.anlage_mit_v2h_und_bhkw`) und
prüft gegen die **ausgerechnete** Zahl, nicht nur die drei Sichten gegeneinander
— Symmetrie allein ließe auch drei gleich falsche Werte durch
([[feedback_aggregator_symmetrie]]).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.cockpit.nachhaltigkeit import get_nachhaltigkeit
from backend.api.routes.cockpit.social import get_share_text
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.tests.test_netto_ertrag_vier_wege_symmetrie import (
    anlage_mit_v2h_und_bhkw,
)

# Erwartungswerte der Fixture mit `km=1000` — einmal ausgerechnet, dann überall
# benannt statt in jedem Test neu hingeschrieben:
#
#   Erzeugung hinter dem Zähler = 1.000 (PV) + 300 (BHKW)   = 1.300 kWh
#   Direktverbrauch             = 1.300 − 400               =   900 kWh
#   Eigenverbrauch              = 900 + 100 (V2H)           = 1.000 kWh
#   Gesamtverbrauch             = 1.000 + 100 (Netzbezug)   = 1.100 kWh
#   Autarkie                    = 1.000 / 1.100             =    90,9 %
#   CO₂ PV                      = 1.000 × 0,38 kg/kWh       =   380,0 kg
#   Benzin-Vergleich            = 1.000 km × 7,5 l/100 km   =      75 l
#   CO₂ E-Mob                   = 75 × 2,37 − 50 × 0,38     =  158,75 kg
#   CO₂ gesamt                                              =  538,75 kg
EV_KWH = 1000.0
AUTARKIE = 90.9
CO2_PV = 380.0
CO2_EMOB = 158.75
CO2_GESAMT = 538.75

# Und der Stand VOR dem Umbau, als Gegenprobe: PV 1.000 (BHKW fiel weg),
# Direktverbrauch 600, kein V2H → EV 600 kWh, Autarkie 600/700 = 85,7 %,
# CO₂ PV 228 kg; Benzin mit 7 l → 70 l → 165,9 − 19 = 146,9 kg.
ALT_EV_KWH = 600.0
ALT_AUTARKIE = 85.7
ALT_CO2_GESAMT = 374.9


@pytest.mark.asyncio
async def test_co2_und_autarkie_sind_deckungsgleich_mit_dem_cockpit(db):
    """Die CO₂-Zeitreihe nennt dieselbe Bilanz wie die Cockpit-Übersicht.

    Ein Monat, also ist die Perioden-Zahl des Cockpits exakt die Monatszahl der
    Zeitreihe — bewusst so geschnitten, damit „deckungsgleich" hier keine
    Klemm-Frage ist (`max(0, …)` monatsweise vs. über die Periode summiert ist
    nicht dasselbe, s. `kennzahlen_aus_fakten`).
    """
    anlage_id = await anlage_mit_v2h_und_bhkw(db, km=1000.0, name="CO2-V2H-BHKW")

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    co2 = await get_nachhaltigkeit(anlage_id=anlage_id, db=db)

    # 1. Gegen die ausgerechnete Zahl.
    assert cockpit.eigenverbrauch_kwh == pytest.approx(EV_KWH, abs=0.1)
    assert co2.co2_gesamt_kg == pytest.approx(CO2_GESAMT, abs=0.1)
    assert co2.co2_pv_kg == pytest.approx(CO2_PV, abs=0.1)
    assert co2.co2_emob_kg == pytest.approx(CO2_EMOB, abs=0.1)
    assert co2.autarkie_durchschnitt_prozent == pytest.approx(AUTARKIE, abs=0.1)

    # 2. Und gegen das Cockpit — auf derselben Seite dürfen nicht zwei Zahlen
    #    stehen (die N93-Klasse).
    assert co2.co2_gesamt_kg == pytest.approx(cockpit.co2_gesamt_kg, abs=0.1)
    assert co2.autarkie_durchschnitt_prozent == pytest.approx(
        cockpit.autarkie_prozent, abs=0.1
    )

    # 3. Gegenprobe auf den Stand vor dem Umbau.
    assert abs(co2.co2_gesamt_kg - ALT_CO2_GESAMT) > 5.0, (
        "V2H, BHKW oder der Benzin-Vergleich fehlen weiterhin"
    )
    assert abs(co2.autarkie_durchschnitt_prozent - ALT_AUTARKIE) > 1.0


@pytest.mark.asyncio
async def test_social_text_teilt_dieselbe_autarkie_und_co2_zahl(db):
    """Der Text geht nach außen — er darf nichts anderes behaupten als das Cockpit."""
    anlage_id = await anlage_mit_v2h_und_bhkw(db, km=1000.0, name="Social-V2H-BHKW")

    resp = await get_share_text(
        anlage_id=anlage_id, monat=6, jahr=2026, variante="ausfuehrlich", db=db,
    )

    # 91 % statt 86 %, 539 kg statt 375 kg — beide Zahlen stehen im Text.
    assert "Autarkiegrad: 91%" in resp.text, resp.text
    assert "CO₂ gespart: 539 kg" in resp.text, resp.text
    assert "86%" not in resp.text, resp.text
    assert "375 kg" not in resp.text, resp.text

    # Die PV-Achse bleibt rein: spezifischer Ertrag und der PVGIS-Vergleich
    # rechnen mit 1.000 kWh PV, nicht mit den 1.300 kWh hinter dem Zähler.
    assert "Erzeugung: 1.000 kWh (100,0 kWh/kWp)" in resp.text, resp.text


@pytest.mark.asyncio
async def test_benzin_vergleich_nutzt_den_gepflegten_verbrauch(db):
    """Der gepflegte `vergleich_verbrauch_l_100km` schlägt die alte 7-l-Konstante.

    5 l/100 km × 1.000 km            =  50 l
    CO₂ E-Mob = 50 × 2,37 − 50 × 0,38 = 118,50 − 19,00 = 99,50 kg

    Die beiden Gegenproben nennen die Werte, die der Endpoint bis 2026-07-31
    genannt hätte: **146,9 kg** mit der hartkodierten 7 und **158,75 kg**, wenn
    zwar der Parameter gelesen, aber der Default (7,5) genommen würde — der Test
    fällt also auch dann, wenn nur die Konstante getauscht wird.
    """
    anlage_id = await anlage_mit_v2h_und_bhkw(
        db, km=1000.0, name="Benzin-5l",
        eauto_parameter={"vergleich_verbrauch_l_100km": 5.0},
    )

    co2 = await get_nachhaltigkeit(anlage_id=anlage_id, db=db)

    assert co2.co2_emob_kg == pytest.approx(99.5, abs=0.1)
    assert abs(co2.co2_emob_kg - 146.9) > 1.0, "rechnet weiter mit 7 l/100 km"
    assert abs(co2.co2_emob_kg - CO2_EMOB) > 1.0, "der gepflegte Wert wird ignoriert"


@pytest.mark.asyncio
async def test_dienstwagen_zaehlt_in_keiner_der_beiden_sichten(db):
    """Dienstlich gefahrene Kilometer sind keine private CO₂-Ersparnis.

    [[feedback_dienstwagen_alle_checks]] — der Filter fehlte in
    `nachhaltigkeit.py` ganz; `social.py` hatte ihn zwar für die Roh-Faltung,
    hat ihn aber mit der eigenen Aggregation getragen. Beide bekommen ihn jetzt
    aus derselben Schicht.
    """
    anlage_id = await anlage_mit_v2h_und_bhkw(
        db, km=1000.0, name="Dienstwagen",
        eauto_parameter={"ist_dienstlich": True},
    )

    co2 = await get_nachhaltigkeit(anlage_id=anlage_id, db=db)

    assert co2.co2_emob_kg == pytest.approx(0.0, abs=0.01)
    # Die PV-Seite bleibt unberührt; nur die V2H-Entladung entfällt mit dem
    # herausgefilterten Fahrzeug (EV 900 statt 1.000 kWh).
    assert co2.co2_pv_kg == pytest.approx(900.0 * 0.38, abs=0.1)


@pytest.mark.asyncio
async def test_nur_aggregat_bekommt_ueberhaupt_eine_zeitreihe(db):
    """Der F-5-Anteil dieser Sicht: ohne Pro-Modul-Zeile gab es gar nichts.

    Die alte Faltung baute ihre Monate ausschließlich aus `InvestitionMonats-
    daten`. Eine Anlage, die ihre Erzeugung als **einen** Anlagen-Wert pflegt
    (manuell oder über einen einzigen PV-Sensor), hatte deshalb keine einzige
    Zeile in der CO₂-Zeitreihe — kein zu kleiner Wert, sondern ein leeres
    Diagramm.

    Eigenverbrauch = 1.000 − 400 = 600 kWh → 600 × 0,38 = 228,00 kg
    """
    anlage = Anlage(anlagenname="CO2-NurAggregat", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0,
                       pv_erzeugung_kwh=1000.0))
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                       leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                       anschaffungskosten_gesamt=12000.0))
    await db.commit()

    co2 = await get_nachhaltigkeit(anlage_id=anlage.id, db=db)

    assert len(co2.monatswerte) == 1, "die Zeitreihe ist leer geblieben"
    assert co2.monatswerte[0].co2_pv_kg == pytest.approx(228.0, abs=0.1)
    assert co2.co2_gesamt_kg == pytest.approx(228.0, abs=0.1)


@pytest.mark.asyncio
async def test_monat_ohne_substanz_verwaessert_den_autarkie_schnitt_nicht(db):
    """Ein Monat vor der Anschaffung erzeugt keine Null-Zeile.

    Die Schicht liefert **jeden** Monat mit einer Spur, auch einen, für den es
    nur eine Zählerzeile gibt. Ungefiltert stünde er mit 0 kg und 0 % im
    Verlauf und zöge den Ø-Autarkiegrad nach unten — die alte Faltung hat solche
    Monate mangels IMD-Zeile nie gesehen, und dabei bleibt es.
    """
    anlage = Anlage(anlagenname="CO2-Vormonat", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    # Mai: nur Netzbezug, die PV läuft noch nicht. Juni: der erste PV-Monat.
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=0.0, netzbezug_kwh=500.0))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2026, 6, 1),
                     anschaffungskosten_gesamt=12000.0)
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    await db.commit()

    co2 = await get_nachhaltigkeit(anlage_id=anlage.id, db=db)

    assert [(m.jahr, m.monat) for m in co2.monatswerte] == [(2026, 6)]
    # 600 / 700 = 85,7 % — nicht der halbierte Schnitt aus 85,7 % und 0 %.
    assert co2.autarkie_durchschnitt_prozent == pytest.approx(85.7, abs=0.1)
