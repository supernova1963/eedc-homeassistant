"""Ein Netto-Ertrag, vier Sichten — Achsen: USt · BKW · nur Anlagen-Aggregat.

Die #326-Inventur nannte drei Dimensionen, in denen die vier Finanz-Read-Sites
auseinanderliefen. Diese Datei schließt die USt-Dimension:

**USt-Eigenverbrauch** (nur bei ``steuerliche_behandlung == "regelbesteuerung"``)
wurde bis 2026-07-31 nur vom Cockpit und von der Aussichten-*Jahresprognose*
abgezogen — nicht vom Jahresbericht-PDF, nicht vom HA-Export-Sensor
``netto_ertrag_euro`` und auch nicht von den *bisherigen Erträgen* der
Aussichten (die den ROI-Fortschritt tragen). Betroffene Anlagen sahen dort
einen um den USt-Betrag zu hohen Ertrag.

Kein bestehender Symmetrie-Test hat das gefunden, weil alle Fixtures die Achse
konstant gehalten haben: keine einzige Anlage mit Regelbesteuerung. Ein
Symmetrie-Test deckt nur die Achsen ab, die seine Fixture variiert
([[feedback_aggregator_symmetrie]]).

**Und die BKW-Dimension** (ADR-002/P9, 2026-07-31). Die Finanz-Zeile trägt zwei
Eingänge, die sich **bedingt** überlappen: ``pv_erzeugung_kwh`` (Erzeugung
hinter dem Hauszähler, also Module **und** BKW) und ``bkw_eigenverbrauch_kwh``.
Der Kanon: Erzeugung erfasst → sie trägt, der zweite Eingang ist 0; keine
Erzeugung erfasst (Datenlücke) → der gemessene Eigenverbrauch trägt allein.
``bkw_finanz_beitrag`` entscheidet das je (BKW, Monat).

Alle vier Sichten hatten die Kombination unterschiedlich gewählt: Aussichten
zählten den Eigenverbrauch **zusätzlich** zur mitgezählten Erzeugung, Cockpit
und PDF ließen die Datenlücken-Zeile ganz fallen, der HA-Export hielt seine
Finanz-PV rein und trug die BKW-Ersparnis nur im ROI-Pfad (mit statischem
Preis), nicht im Sensor. Geprüft wird deshalb **beides**: dass die vier Sichten
übereinstimmen UND dass die genannte Zahl stimmt — Symmetrie allein würde auch
vier gleich falsche Zahlen durchlassen.

**Und die Aggregat-Dimension** (Befund **F-5**, ADR-002/P10, 2026-07-31): eine
Anlage, deren PV-Erzeugung **nur** als Anlagen-Aggregat gepflegt ist — das PV-
Modul hat gar keine eigene Monatszeile. Das ist der Normalfall bei manueller
Pflege und beim Import mit einem einzigen Gesamt-PV-Sensor, und genau der Fall,
für den ``resolve_pv_je_modul`` (P7) gebaut wurde. Cockpit und HA-Export nutzten
die Auflösung; Aussichten, Jahresbericht-PDF und der Investitions-ROI summierten
stattdessen roh ``verbrauch_daten["pv_erzeugung_kwh"]`` und kamen damit auf
0 kWh PV — **32,00 € statt 212,00 €**, eine Abweichung von 85 %, die auf ROI-
Fortschritt, Amortisation und den kompletten Jahresbericht durchschlug.

Auch diese Achse hat die Fixture bisher konstant gehalten: **jede** Anlage in
dieser Datei bekam eine Pro-Modul-Zeile. Dieselbe Blindstelle wie beim Flex-Ø
und beim Basistarif — ein Symmetrie-Test deckt nur die Achsen ab, die seine
Fixture variiert ([[feedback_aggregator_symmetrie]]).

**N42 ist ausdrücklich NICHT Teil dieser Achse** (ADR-002/P2-A, Pflicht Nr. 4).
Die Teil-Lücke *ohne* Aggregat — ein Modul gemessen, das andere nicht, kein
Anlagen-Gesamtwert — ist eine andere Konstellation mit einer anderen, bewusst
asymmetrischen Erwartung: dort gibt es nichts, worauf zurückgefallen werden
könnte, und die Anlagen-Summe zeigt bewusst nichts. Der letzte Test dieser Datei
nagelt diese Abgrenzung fest, statt sie stumm auszulassen.

Alle drei Achsen laufen über dieselbe Fixture-Familie: ein Monat, ein Tarif.
Geprüft wird nicht die Zeitachse (dafür ADR-002/P8 und
`test_aussichten_finanz_aggregat_symmetrie`), sondern ob alle vier Sichten
dieselben POSTEN in den Netto-Ertrag nehmen.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.ha_export import calculate_anlage_sensors
from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context


async def _anlage_mit_regelbesteuerung(db) -> int:
    """PV-Anlage mit Regelbesteuerung, ein Monat, ein Tarif.

    Bewusst EIN Monat und EIN Tarif: geprüft wird nicht die Zeitachse (dafür
    ADR-002/P8 und `test_aussichten_finanz_aggregat_symmetrie`), sondern ob alle
    vier Sichten dieselben POSTEN in den Netto-Ertrag nehmen.
    """
    anlage = Anlage(
        anlagenname="VierWegeUSt", leistung_kwp=10.0,
        steuerliche_behandlung="regelbesteuerung", ust_satz_prozent=19.0,
    )
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=12000.0)
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
        verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    await db.commit()
    return anlage.id


@pytest.mark.asyncio
async def test_cockpit_zieht_die_ust_ab(db):
    """Die Referenzzahl, gegen die die anderen drei geprüft werden.

    einspeise = 400 × 0,08                  =  32,00 €
    ev        = (1.000 − 400) × 0,30        = 180,00 €
    USt       = 600 kWh × (12.000/20 / 1.000) × 19 %
              = 600 × 0,60 × 0,19           =  68,40 €
    netto     = 32 + 180 − 68,40            = 143,60 €
    """
    anlage_id = await _anlage_mit_regelbesteuerung(db)

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)

    assert cockpit.ust_eigenverbrauch_euro == pytest.approx(68.4, abs=0.05)
    assert cockpit.netto_ertrag_euro == pytest.approx(143.6, abs=0.1)
    # Gegenprobe: ohne USt-Abzug wären es 212 € — das war der Stand in PDF,
    # HA-Export und den bisherigen Erträgen der Aussichten.
    assert abs(cockpit.netto_ertrag_euro - 212.0) > 50.0


@pytest.mark.asyncio
async def test_alle_vier_sichten_nennen_denselben_netto_ertrag(db):
    """Cockpit == Aussichten == Jahresbericht-PDF == HA-Export."""
    anlage_id = await _anlage_mit_regelbesteuerung(db)

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    aussichten = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)
    pdf = await build_jahresbericht_context(db, anlage_id, jahr=2026)

    anlage = await db.get(Anlage, anlage_id)
    sensoren = await calculate_anlage_sensors(db, anlage)
    ha_netto = next(
        s.value for s in sensoren if s.definition.key == "netto_ertrag_euro"
    )

    referenz = cockpit.netto_ertrag_euro

    assert aussichten.bisherige_ertraege_euro == pytest.approx(referenz, abs=0.1), (
        f"Aussichten {aussichten.bisherige_ertraege_euro} ≠ Cockpit {referenz}")
    assert pdf["kpis"]["netto_ertrag_euro"] == pytest.approx(referenz, abs=0.1), (
        f"PDF {pdf['kpis']['netto_ertrag_euro']} ≠ Cockpit {referenz}")
    assert ha_netto == pytest.approx(referenz, abs=0.1), (
        f"HA-Export {ha_netto} ≠ Cockpit {referenz}")


# ============================================================================
# Achse 2 — Balkonkraftwerk (ADR-002/P9)
# ============================================================================


async def _anlage_mit_bkw(db, *, bkw_daten: dict, name: str) -> int:
    """PV-Anlage + ein BKW, ein Monat, ein Tarif, Kleinunternehmer (keine USt).

    `bkw_daten` ist das `verbrauch_daten`-JSON der BKW-Monatszeile — über diese
    eine Stelle variieren die drei Erfassungsformen.
    """
    anlage = Anlage(anlagenname=name, leistung_kwp=10.8)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=12000.0)
    db.add(pv)
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                      anschaffungsdatum=date(2024, 1, 1),
                      anschaffungskosten_gesamt=800.0,
                      parameter={"leistung_wp": 800})
    db.add(bkw)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=6,
                                  verbrauch_daten=bkw_daten))
    await db.commit()
    return anlage.id


async def _vier_netto_ertraege(db, anlage_id: int) -> dict[str, float]:
    """Netto-Ertrag aller vier Sichten für dieselbe Anlage."""
    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    aussichten = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)
    pdf = await build_jahresbericht_context(db, anlage_id, jahr=2026)

    anlage = await db.get(Anlage, anlage_id)
    sensoren = await calculate_anlage_sensors(db, anlage)
    ha_netto = next(
        s.value for s in sensoren if s.definition.key == "netto_ertrag_euro"
    )

    return {
        "Cockpit": cockpit.netto_ertrag_euro,
        "Aussichten": aussichten.bisherige_ertraege_euro,
        "PDF": pdf["kpis"]["netto_ertrag_euro"],
        "HA-Export": ha_netto,
    }


def _einig(werte: dict[str, float], erwartet: float) -> None:
    for sicht, wert in werte.items():
        assert wert == pytest.approx(erwartet, abs=0.1), (
            f"{sicht} nennt {wert:.2f} €, erwartet {erwartet:.2f} € — "
            f"alle vier: { ({k: round(v, 2) for k, v in werte.items()}) }"
        )


@pytest.mark.asyncio
async def test_bkw_mit_erzeugung_zaehlt_einmal(db):
    """Normalfall: BKW schreibt nur seine Erzeugung (Pflichtfeld) mit.

    PV-Summe = 1.000 + 200                  = 1.200 kWh
    Eigenverbrauch = 1.200 − 400            =   800 kWh
    ev        = 800 × 0,30                  = 240,00 €
    einspeise = 400 × 0,08                  =  32,00 €
    netto                                   = 272,00 €
    """
    anlage_id = await _anlage_mit_bkw(
        db, bkw_daten={"pv_erzeugung_kwh": 200.0}, name="BKW-P9-Erzeugung")

    _einig(await _vier_netto_ertraege(db, anlage_id), 272.0)


@pytest.mark.asyncio
async def test_bkw_mit_erzeugung_und_eigenverbrauch_zaehlt_trotzdem_einmal(db):
    """Der Doppelzählungs-Fall — dieselbe Zahl wie ohne den Zusatzwert.

    Der gemessene Eigenverbrauch (150 kWh) ist ein TEIL der 200 kWh Erzeugung
    und steckt damit schon in den 800 kWh der Ableitung. Bis 2026-07-31
    addierten die Aussichten ihn ein zweites Mal: 272 + 150 × 0,30 = 317 €.
    """
    anlage_id = await _anlage_mit_bkw(
        db,
        bkw_daten={"pv_erzeugung_kwh": 200.0, "eigenverbrauch_kwh": 150.0},
        name="BKW-P9-Beides",
    )

    werte = await _vier_netto_ertraege(db, anlage_id)

    _einig(werte, 272.0)
    # Gegenprobe: der doppelt gezählte Wert wäre 317 € — keine Sicht nennt ihn.
    for sicht, wert in werte.items():
        assert abs(wert - 317.0) > 5.0, f"{sicht} zählt den BKW-EV doppelt"


@pytest.mark.asyncio
async def test_bkw_ohne_erzeugung_wird_von_allen_vier_getragen(db):
    """Datenlücke: nur `eigenverbrauch_kwh` gepflegt (manuell/Import — der
    Sensor-Pfad kann dieses Feld gar nicht schreiben).

    PV-Summe = 1.000 kWh (das BKW fehlt darin)
    Eigenverbrauch = 1.000 − 400            =   600 kWh
    ev        = 600 × 0,30                  = 180,00 €
    bkw       = 150 × 0,30                  =  45,00 €
    einspeise = 400 × 0,08                  =  32,00 €
    netto                                   = 257,00 €

    Cockpit und Jahresbericht-PDF ließen diese 45 € bis 2026-07-31 fallen.
    """
    anlage_id = await _anlage_mit_bkw(
        db, bkw_daten={"eigenverbrauch_kwh": 150.0}, name="BKW-P9-Datenluecke")

    _einig(await _vier_netto_ertraege(db, anlage_id), 257.0)


# ============================================================================
# Achse 3 — nur das Anlagen-Aggregat gepflegt (F-5, ADR-002/P7 + P10)
# ============================================================================


async def _anlage_nur_mit_aggregat(db) -> int:
    """PV-Anlage, deren Erzeugung NUR als Anlagen-Aggregat gepflegt ist.

    Der Unterschied zu `_anlage_mit_regelbesteuerung` ist genau eine Zeile: das
    PV-Modul bekommt **keine** `InvestitionMonatsdaten`, die 1.000 kWh stehen
    stattdessen in `Monatsdaten.pv_erzeugung_kwh`. Kleinunternehmer, damit die
    USt-Achse hier nicht mitspielt und die Zahl direkt nachrechenbar bleibt.
    """
    anlage = Anlage(anlagenname="NurAggregat", leistung_kwp=10.0)
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
    return anlage.id


@pytest.mark.asyncio
async def test_nur_aggregat_alle_vier_sichten_nennen_212_euro(db):
    """Der F-5-Beweis — gegen die ausgerechnete Zahl, nicht nur gegeneinander.

    PV        = 1.000 kWh (aus dem Anlagen-Aggregat auf das eine Modul verteilt)
    ev        = (1.000 − 400) × 0,30        = 180,00 €
    einspeise = 400 × 0,08                  =  32,00 €
    netto                                   = 212,00 €

    Aussichten und Jahresbericht-PDF nannten bis 2026-07-31 **32,00 €**: ihre
    rohe IMD-Summe fand keine Pro-Modul-Zeile und setzte die PV auf 0, womit die
    komplette Eigenverbrauchs-Ersparnis fehlte.
    """
    anlage_id = await _anlage_nur_mit_aggregat(db)

    werte = await _vier_netto_ertraege(db, anlage_id)

    _einig(werte, 212.0)
    # Gegenprobe: 32 € wäre der Stand ohne die PV-Auflösung — keine der vier
    # Sichten darf ihn noch nennen.
    for sicht, wert in werte.items():
        assert abs(wert - 32.0) > 5.0, (
            f"{sicht} nennt {wert:.2f} € — die PV-Auflösung (P7) fehlt dort"
        )


@pytest.mark.asyncio
async def test_nur_aggregat_pv_menge_ist_im_jahresbericht_sichtbar(db):
    """Nicht nur der Euro-Betrag: der Bericht zeigte 0 kWh Erzeugung.

    Die KPI-Kachel „PV-Erzeugung" und die Monatstabelle des PDFs standen bei
    dieser Anlage auf 0 — ein Bericht, der die Anlage als tot auswies.
    """
    anlage_id = await _anlage_nur_mit_aggregat(db)

    pdf = await build_jahresbericht_context(db, anlage_id, jahr=2026)

    assert pdf["kpis"]["pv_erzeugung_kwh"] == pytest.approx(1000.0, abs=0.1)
    juni = next(z for z in pdf["monats_zeilen"] if z["monat"] == 6)
    assert juni["pv_erzeugung_kwh"] == pytest.approx(1000.0, abs=0.1)
    assert juni["eigenverbrauch_kwh"] == pytest.approx(600.0, abs=0.1)
    # Der String-Vergleich liest dieselbe Auflösung — sonst stünde dort eine
    # Abweichung von −100 % gegen die PVGIS-Prognose.
    assert pdf["string_vergleiche"][0]["ist_kwh"] == pytest.approx(1000.0, abs=0.1)


@pytest.mark.asyncio
async def test_nur_aggregat_investitions_roi_traegt_die_ev_ersparnis(db):
    """Die fünfte Sicht: ROI-Fortschritt und Break-Even je Investition.

    `get_roi_dashboard` rechnet den einen erfassten Monat auf ein Jahr hoch
    (Faktor 12, `methode == 'linear'`), also 12 × 212,00 € = **2.544,00 €**:

    Erzeugung  = 12 × 1.000                 = 12.000 kWh
    Einspeisung= 12 ×   400                 =  4.800 kWh
    ev         = (12.000 − 4.800) × 0,30    =  2.160,00 €
    einspeise  = 4.800 × 0,08               =    384,00 €
    Summe                                   =  2.544,00 €

    Vorher: Erzeugung 0 → Eigenverbrauch 0 → 384,00 € (12 × 32 €). Das ist die
    Zahl, aus der Amortisation und Break-Even-Jahr abgeleitet werden.
    """
    anlage_id = await _anlage_nur_mit_aggregat(db)

    roi = await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=2026, db=db,
    )

    assert roi.gesamt_jahres_einsparung == pytest.approx(2544.0, abs=1.0)
    assert abs(roi.gesamt_jahres_einsparung - 384.0) > 50.0, (
        "Der ROI rechnet weiter mit 0 kWh PV — die Auflösung fehlt"
    )


@pytest.mark.asyncio
async def test_n42_teilluecke_ohne_aggregat_gehoert_nicht_zu_dieser_achse(db):
    """Abgrenzung nach ADR-002/**P2-A** (Pflicht Nr. 4) — bewusst geprüft.

    Zwei Module, eines gemessen (600 kWh), das andere ohne Wert, und **kein**
    Anlagen-Aggregat. Das ist NICHT der F-5-Fall: es gibt nichts, worauf
    zurückgefallen werden könnte. `pv_summe_je_monat` liefert hier bewusst
    `None` („mindestens ein aktives Modul ohne Wert und ohne Aggregat"), eine
    Teilsumme als Anlagenerzeugung wäre irreführend.

    Geprüft wird deshalb nur das, was diese Achse zusichern kann: die vier
    Sichten bleiben **untereinander einig** und nennen den Einspeise-Erlös
    allein (400 × 0,08 = 32,00 €). Die asymmetrische Erwartung zwischen
    Pro-Modul-Sicht und Anlagen-Summe gehört zu P2-A und wird dort geprüft
    (`test_pv_strings_kwp_verteilung.py`), nicht hier.

    **Auch hier bewegt sich eine Zahl** — nach unten: Aussichten und PDF nahmen
    bis 2026-07-31 die Teilsumme (600 kWh) als Anlagenerzeugung und kamen auf
    92,00 €. Cockpit und HA-Export haben diesen Fall nie mitgerechnet.
    """
    anlage = Anlage(anlagenname="N42-Teilluecke", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    gemessen = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Ost",
                           leistung_kwp=5.0, anschaffungsdatum=date(2024, 1, 1),
                           anschaffungskosten_gesamt=6000.0)
    db.add(gemessen)
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="West",
                       leistung_kwp=5.0, anschaffungsdatum=date(2024, 1, 1),
                       anschaffungskosten_gesamt=6000.0))
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=gemessen.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 600.0}))
    await db.commit()

    _einig(await _vier_netto_ertraege(db, anlage.id), 32.0)
