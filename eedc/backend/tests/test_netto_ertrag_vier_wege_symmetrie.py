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

    einspeise = 400 × 0,08                       =  32,00 €
    ev        = (1.000 − 400) × 0,30             = 180,00 €
    USt       = 600 kWh × (12.000/20 × 1/12 / 1.000) × 19 %
              = 600 × 0,05 × 0,19                =   5,70 €
    netto     = 32 + 180 − 5,70                  = 206,30 €

    **Der `× 1/12` ist neu seit dem 2026-08-04** (N-130, Entscheid Gernot): die
    Fixture deckt EINEN Monat ab, also trägt sie auch nur einen Monat AfA. Bis
    dahin stand hier `68,40 €` — zwölf Monate Abschreibung gegen einen Monat
    Ertrag. Die Bemessungsgrundlage ist jetzt die Mehrkosten-Form (N-129); die
    Fixture pflegt keine Alternativkosten, deshalb bleibt sie hier bei 12.000 €.
    """
    anlage_id = await _anlage_mit_regelbesteuerung(db)

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)

    assert cockpit.ust_eigenverbrauch_euro == pytest.approx(5.7, abs=0.05)
    assert cockpit.netto_ertrag_euro == pytest.approx(206.3, abs=0.1)
    # Gegenprobe: ohne USt-Abzug wären es 212 € — das war der Stand in PDF,
    # HA-Export und den bisherigen Erträgen der Aussichten. Der Abstand ist
    # klein, weil ein Ein-Monats-Zeitraum nur ein Zwölftel der Jahres-AfA
    # trägt; deshalb wird er hier EXAKT geprüft und nicht über eine Schwelle.
    assert cockpit.netto_ertrag_euro == pytest.approx(
        212.0 - cockpit.ust_eigenverbrauch_euro, abs=0.1
    )
    assert cockpit.ust_eigenverbrauch_euro > 0, "sonst prüft der Test nichts"


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
# Achse 1b — Zeitraumlänge (N-130)
# ============================================================================


async def _anlage_ueber_zwei_jahre(db) -> int:
    """Dieselbe Anlage, aber ZWEI volle Kalenderjahre statt eines Monats.

    Die Fixture-Familie oben deckt einen Monat ab — und in einem Ein-Monats-
    Zeitraum ist „Zeitraum" == „Jahr". Genau deshalb hat der Symmetrie-Test
    **N-130 nicht gefangen**, obwohl er vier Sichten vergleicht: die Achse
    Zeitraumlänge fehlte ([[feedback_aggregator_symmetrie]]).

    Je Jahr sechs Monate mit identischen Mengen ⇒ beide Jahre tragen dieselbe
    USt, und der Gesamtbetrag muss das Doppelte eines Jahres sein.
    """
    anlage = Anlage(
        anlagenname="VierWegeUStZweiJahre", leistung_kwp=10.0,
        steuerliche_behandlung="regelbesteuerung", ust_satz_prozent=19.0,
    )
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2023, 1, 1),
                     anschaffungskosten_gesamt=12000.0)
    db.add(pv)
    await db.flush()
    for jahr in (2024, 2025):
        for monat in range(1, 7):
            db.add(Monatsdaten(anlage_id=anlage.id, jahr=jahr, monat=monat,
                               einspeisung_kwh=400.0, netzbezug_kwh=100.0))
            db.add(InvestitionMonatsdaten(
                investition_id=pv.id, jahr=jahr, monat=monat,
                verbrauch_daten={"pv_erzeugung_kwh": 1000.0},
            ))
    await db.commit()
    return anlage.id


@pytest.mark.asyncio
async def test_zwei_jahre_tragen_die_doppelte_ust_eines_jahres(db):
    """N-130: der Gesamtzeitraum darf nicht gegen EINE Jahres-AfA laufen.

    Beide Jahre sind mengengleich, also muss die USt über beide exakt doppelt
    so hoch sein wie über eines. Die Vorfassung teilte die Jahres-Abschreibung
    durch die Erzeugung **beider** Jahre und kam auf die Hälfte.
    """
    anlage_id = await _anlage_ueber_zwei_jahre(db)

    beide = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    eines = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2024, db=db)

    assert eines.ust_eigenverbrauch_euro > 0, "sonst prüft der Test nichts"
    assert beide.ust_eigenverbrauch_euro == pytest.approx(
        2 * eines.ust_eigenverbrauch_euro, abs=0.05
    )
    # Und der absolute Wert, damit ein Vorzeichenfehler in der Anteiligkeit
    # nicht durch beide Seiten der Verhältnis-Prüfung rutscht:
    # AfA 12.000/20 = 600 €/Jahr × 6/12 = 300 € auf 6.000 kWh = 0,05 €/kWh
    # ⇒ 3.600 kWh EV × 0,05 × 19 % = 34,20 € je Jahr.
    assert eines.ust_eigenverbrauch_euro == pytest.approx(34.2, abs=0.05)


@pytest.mark.asyncio
async def test_ueber_zwei_jahre_nennen_alle_vier_sichten_dasselbe(db):
    """Dieselbe Symmetrie wie oben, aber auf der Zeitachse."""
    anlage_id = await _anlage_ueber_zwei_jahre(db)

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    aussichten = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)
    pdf = await build_jahresbericht_context(db, anlage_id, jahr=None)

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
    """Netto-Ertrag aller vier Sichten für dieselbe Anlage.

    **Grenze — der Helfer taugt nur für Fixtures ohne Wärmepumpe und ohne
    gefahrene E-Auto-Kilometer.** Die vier Sichten sind nur dort vergleichbar:
    `aussichten.bisherige_ertraege_euro` nennt eine Größe, die WP- und
    eMob-Alternativkosten-Ersparnisse anders trägt als die übrigen drei. Mit
    einer WP oder gefahrenen km im Fixture meldet `_einig` deshalb eine Drift,
    die keine ist.

    Das steht hier und nicht nur in der Fixture-Doku, weil ein Symmetrie-Test
    genau die Achsen abdeckt, die seine Fixture variiert — und sonst nichts
    ([[feedback_aggregator_symmetrie]]). Wer den Helfer für eine neue Achse
    wiederverwendet, muss diese Grenze kennen, bevor er die Fixture baut.
    """
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


async def anlage_nur_mit_aggregat(db) -> int:
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
    anlage_id = await anlage_nur_mit_aggregat(db)

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
    anlage_id = await anlage_nur_mit_aggregat(db)

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
    anlage_id = await anlage_nur_mit_aggregat(db)

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


# ============================================================================
# Achse 4 — V2H und Erzeuger hinter dem Zähler (F-1, ADR-002/P10)
# ============================================================================


async def anlage_mit_v2h_und_bhkw(
    db,
    *,
    name: str = "V2H-BHKW",
    km: float = 0.0,
    eauto_parameter: dict | None = None,
) -> int:
    """PV + BHKW hinter demselben Zähler + ein E-Auto, das ins Haus entlädt.

    Die Konstellation, die Befund **F-1** sichtbar macht. Beide Zusätze wirken
    auf DERSELBEN Größe (Eigenverbrauch), aber an verschiedenen Stellen: das
    BHKW erhöht die Erzeugung hinter dem Zähler, V2H kommt wie eine
    Speicher-Entladung obendrauf.

    Das PV-Modul bekommt bewusst eine **eigene** Monatszeile: die Aggregat-Achse
    (F-5) und die N42-Teillücke sind eigene Konstellationen mit eigenen Tests —
    hier dürfen sie das Ergebnis nicht mitfärben (ADR-002/P2-A, Pflicht Nr. 4).
    Kleinunternehmer, damit die USt-Achse die Zahl nicht überlagert.

    ``km`` ist **0 by default**, und das ist keine Bequemlichkeit: die
    Aussichten nennen als „bisherige Erträge" ``netto_ertrag + WP-Ersparnis +
    E-Auto-Ersparnis`` — eine bewusst weitere Größe als der Netto-Ertrag der
    anderen drei Sichten (sie trägt den ROI-Fortschritt). Mit gefahrenen
    Kilometern verglichen der Vier-Wege-Test also zwei verschiedene Kennzahlen.
    Die km-Variante nutzt `test_co2_autarkie_sichten_symmetrie`, wo sie
    hingehört.
    """
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
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
    bhkw = Investition(anlage_id=anlage.id, typ="sonstiges", bezeichnung="Mini-BHKW",
                       anschaffungsdatum=date(2024, 1, 1),
                       anschaffungskosten_gesamt=9000.0,
                       parameter={"kategorie": "erzeuger"})
    db.add(bhkw)
    eauto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Kombi",
                        anschaffungsdatum=date(2024, 1, 1),
                        anschaffungskosten_gesamt=30000.0,
                        parameter={"nutzt_v2h": True, **(eauto_parameter or {})})
    db.add(eauto)
    await db.flush()

    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=bhkw.id, jahr=2026, monat=6,
                                  verbrauch_daten={"erzeugung_kwh": 300.0}))
    eauto_daten: dict = {"v2h_entladung_kwh": 100.0}
    if km > 0:
        # Heimladung nur zusammen mit gefahrenen Kilometern: geladen ohne
        # gefahren zu sein wäre reine Ausgabe und würde die Aussichten (die
        # zusätzlich die E-Auto-Alternativkosten tragen) um genau diese Kosten
        # verschieben.
        eauto_daten.update({
            "km_gefahren": km,
            "ladung_kwh": 200.0,
            "ladung_pv_kwh": 150.0,
            "ladung_netz_kwh": 50.0,
        })
    db.add(InvestitionMonatsdaten(investition_id=eauto.id, jahr=2026, monat=6,
                                  verbrauch_daten=eauto_daten))
    await db.commit()
    return anlage.id


@pytest.mark.asyncio
async def test_v2h_und_sonstiger_erzeuger_zaehlen_in_allen_vier_sichten_gleich(db):
    """Beide Regeln in einer Zahl — und alle vier Sichten tragen sie gleich.

    Die **Finanz**-Zeile rechnet seit 2026-09-03 mit der Erzeugung **hinter dem
    Zähler** (Module + BKW + sonstige Erzeuger), also mit derselben Achse wie
    Eigenverbrauch und Autarkie. V2H ist eingesparter Netzbezug wie eine
    Speicher-Entladung und zählt ebenfalls.

    Erzeugung hinter dem Zähler = 1.000 (PV) + 300 (BHKW)  = 1.300 kWh
    Direktverbrauch = 1.300 − 400                          =   900 kWh
    Eigenverbrauch  = 900 + 100 (V2H)                      = 1.000 kWh
    ev        = 1.000 × 0,30                               = 300,00 €
    einspeise = 400 × 0,08                                 =  32,00 €
    netto                                                  = 332,00 €

    ⭐ **332,00 € ist auf den Cent die Zahl, die die alte Fassung als
    Gegenprobe führte** („die Zahl, wenn eine Sicht das BHKW in die Bewertung
    zöge"). Sie ist jetzt der Sollwert — die Umstellung ist damit an derselben
    Rechnung ablesbar, aus der sie kommt, und keine neu erfundene Größe.

    **Der eigentliche Gegenstand dieser Probe ist die Symmetrie**, nicht die
    Höhe: dieselbe Zahl in allen vier Sichten. Die Gegenproben halten beide
    Richtungen fest — die Zahl ohne V2H und die Zahl der abgelösten PV-Achse.

    ⛔ **Bis 2026-09-03 stand hier 242,00 €** und der Satz *„Genau diese
    Verwechslung von ``pv_kwh`` und ``hinter_zaehler_kwh`` IST Befund F-1."*
    F-1 war ein **Drift**-Befund: Sichten, die verschiedene Achsen nahmen. Die
    Zuordnung „Finanz-Zeile ⇒ ``pv_kwh``" stammte aus v3.45.4 und ist vom
    Maintainer abgelöst (*„deren produzierter Strom geht vollständig in der
    EV-Ersparnis und Einspeisung auf"*). **Was F-1 wirklich schützt — dass alle
    vier Sichten DIESELBE Achse nehmen — prüft diese Probe unverändert weiter,
    nur auf dem neuen Niveau.**
    """
    anlage_id = await anlage_mit_v2h_und_bhkw(db)

    werte = await _vier_netto_ertraege(db, anlage_id)

    _einig(werte, 332.0)
    for sicht, wert in werte.items():
        assert abs(wert - 302.0) > 5.0, f"{sicht} lässt die V2H-Entladung fallen"
        assert abs(wert - 242.0) > 5.0, f"{sicht} rechnet noch auf der PV-Achse (v3.45.4)"
