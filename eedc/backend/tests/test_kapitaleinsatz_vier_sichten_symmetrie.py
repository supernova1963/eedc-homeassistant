"""Vier Sichten, ein Nenner: der Kapitaleinsatz (F-19).

*Auswertungen → ROI*, die **HA-Sensoren**, die **Aussichten** und der
**PDF-Finanzbericht** rechnen ihre Amortisation gegen denselben Nenner:
relevante Kosten **plus die kumulierten sonstigen Ausgaben, minus die
kumulierten sonstigen Erträge** — und zwar aus **beiden** Erfassungsorten: an
einer Investition *und* auf der ``Monatsdaten``-Zeile (Monatsabschluss ohne
Komponente).

⚠ **Die zweite Hälfte trug erst ab 2026-08-10** (Bauschritt 4 des Konzepts §8).
Bis dahin behauptete dieser Docstring „vier Sichten, ein Nenner", während eine
anlagenweit erfasste Ausgabe **nur** die HA-Sensoren erreichte — gemessen
18.000 € gegen 15.000 €. Gesehen hat es keine Probe dieser Datei, weil die
Fixture die Position komponentengebunden anlegt.

⚠ **Was dieser Test bewusst NICHT prüft: gleiche Endwerte.** Die vier Sichten
meinen nicht dieselbe Größe, und das ist so gewollt und in
`docs/BERECHNUNGEN.md` ausgeschrieben (N-211, gemessen 09.08.):

- *Auswertungen → ROI* und das PDF rechnen ein **MODELL** — Kapitaleinsatz ÷
  hochgerechnete Jahres-Einsparung;
- die *Aussichten* rechnen eine **MESSUNG** — bisherige Erträge ÷ derselbe
  Nenner, plus Restlaufzeit;
- die **HA-Sensoren** annualisieren die **gemessene Historie** je Posten.

Ein Test auf „vier gleiche Jahreszahlen" wäre deshalb aus Gründen rot, die mit
F-19 nichts zu tun haben. Was sie teilen **müssen**, ist der Nenner — sonst
lässt sich keine der Zahlen in eine andere überführen. Genau das ist die
Zusicherung, die `test_amortisation_nenner_symmetrie.py` für die relevanten
Kosten trifft; hier kommt die Ausgaben-Seite dazu.

**Die zweite Zusicherung: beide Seiten des Monatsabschlusses stehen im
Nenner** — Ausgaben erhöhen ihn, Erträge mindern ihn, beide **kumuliert** und
keine von beiden im Zähler. Begründung und Rechnung in
`core/berechnungen/kapitalrechnung.py`.

⚑ **Bis 2026-08-10 stand hier das Gegenteil**, und zwar als ausdrücklicher
Zwischenstand: die Erträge blieben im Zähler, solange es keinen Ort für
*wiederkehrende* Erträge gab. Mit **Bauschritt 7** (Konzept §8) ist die
Vollkostenrechnung vollständig; die Probe
`test_ertrag_mindert_den_nenner_wie_die_ausgabe_ihn_erhoeht` unten ist die
umgeschriebene Fassung der alten `test_ertrag_bleibt_im_zaehler_…` — sie wurde
**umgeschrieben, nicht der Code repariert**, genau wie die Bauliste es
vorgesehen hat.

⚠ **Wer diesen Test „korrigieren" will, liest zuerst
`docs/KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md` §7.** Mehrere naheliegende
Umbauten (alles in den Nenner · Kennzeichen „einmalig" · Feld `art` ·
IST-Hochrechnung in die Prognose) sind durchgerechnet und verworfen — nicht
vergessen.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.api.routes.ha_export import calculate_anlage_sensors
from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.services.pdf.builders.finanzbericht import build_finanzbericht_context
from backend.services.pdf.formatierung import fmt_zahl

#: PV 10.000 + Speicher 5.000 = 15.000 relevante Kosten …
RELEVANTE_KOSTEN = 15000.0
#: … plus eine einmalige Reparatur von 3.000 € = Kapitaleinsatz.
REPARATUR = 3000.0
#: Ein sonstiger Ertrag (THG-Quote) — er MINDERT den Nenner (Bauschritt 7).
THG_ERTRAG = 200.0
ERWARTETER_KAPITALEINSATZ = RELEVANTE_KOSTEN + REPARATUR - THG_ERTRAG


async def _anlage(db) -> int:
    anlage = Anlage(anlagenname="KapitaleinsatzSymmetrie", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    for monat in (4, 5):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=monat,
                           einspeisung_kwh=600.0, netzbezug_kwh=100.0))

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=10000.0)
    speicher = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
                           anschaffungsdatum=date(2024, 1, 1),
                           anschaffungskosten_gesamt=5000.0,
                           parameter={"kapazitaet_kwh": 10.0})
    db.add_all([pv, speicher])
    await db.flush()

    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2025, monat=4,
        verbrauch_daten={
            "pv_erzeugung_kwh": 600.0,
            "sonstige_positionen": [
                {"bezeichnung": "Reparatur Wechselrichter", "betrag": REPARATUR, "typ": "ausgabe"},
                {"bezeichnung": "THG-Quote", "betrag": THG_ERTRAG, "typ": "ertrag"},
            ],
        },
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2025, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 600.0},
    ))
    await db.commit()
    return anlage.id


async def _roi(db, anlage_id: int):
    # Query-Defaults explizit: beim direkten Funktionsaufruf sind die
    # `Query(None)`-Objekte sonst die Argumente (N-111).
    return await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )


async def test_roi_dashboard_nennt_den_kapitaleinsatz(db):
    anlage_id = await _anlage(db)
    roi = await _roi(db, anlage_id)

    assert roi.gesamt_relevante_kosten == pytest.approx(RELEVANTE_KOSTEN)
    assert roi.gesamt_sonstige_ausgaben_euro == pytest.approx(REPARATUR)
    assert roi.gesamt_kapitaleinsatz == pytest.approx(ERWARTETER_KAPITALEINSATZ)
    # Und die Amortisation rechnet wirklich damit, nicht mit den relevanten Kosten.
    # ⚠ **Ohne `if`** (N-221): ein Guard auf denselben Wert, den die Probe prüft,
    # schaltet genau dann auf Grün, wenn die Zahl fehlt — also im Fehlerfall.
    # Die Fixture liefert sie nachweislich (13,9 Jahre, gemessen 10.08.).
    assert roi.gesamt_amortisation_jahre is not None
    assert roi.gesamt_amortisation_jahre == pytest.approx(
        roi.gesamt_kapitaleinsatz / roi.gesamt_jahres_einsparung, rel=0.02
    )


async def test_aussichten_teilen_den_kapitaleinsatz(db):
    anlage_id = await _anlage(db)
    roi = await _roi(db, anlage_id)
    prognose = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    # Die Mehrkosten-Größe bleibt unberührt (N-137) …
    assert prognose.investition_gesamt_euro == pytest.approx(roi.gesamt_relevante_kosten)
    # … und der Kapitaleinsatz ist derselbe wie im ROI-Dashboard.
    assert prognose.kapitaleinsatz_euro == pytest.approx(ERWARTETER_KAPITALEINSATZ)
    assert prognose.kapitaleinsatz_euro == pytest.approx(roi.gesamt_kapitaleinsatz)


async def test_ha_sensoren_teilen_den_kapitaleinsatz(db):
    anlage_id = await _anlage(db)
    roi = await _roi(db, anlage_id)
    from sqlalchemy import select as _select
    anlage = (await db.execute(_select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    sensor_values = await calculate_anlage_sensors(db, anlage)
    sensoren = {sv.definition.key: sv for sv in sensor_values}

    # ⚠ **Kein `skip`** (N-221): „Anlage liefert keinen bewertbaren ROI-Sensor"
    # ist nicht der Sonderfall, sondern der **Befund** — am Stand vor F-19 hat
    # genau dieser Zweig gegriffen und die Probe still übersprungen. Die Fixture
    # liefert den Sensor (gemessen 10.08.); fehlt er, ist das rot.
    assert "roi_prozent" in sensoren, "Fixture liefert keinen ROI-Sensor mehr"
    assert sensoren["roi_prozent"].value, "ROI-Sensor ohne Wert"

    # Aus den ausgelieferten Sensoren zurückgerechnet — der Nenner ist nicht
    # selbst ein Sensor, aber er bestimmt beide Werte.
    nenner = sensoren["jahres_ersparnis_euro"].value / sensoren["roi_prozent"].value * 100
    assert nenner == pytest.approx(ERWARTETER_KAPITALEINSATZ, rel=0.01)
    assert nenner == pytest.approx(roi.gesamt_kapitaleinsatz, rel=0.01)


async def test_pdf_finanzbericht_teilt_den_kapitaleinsatz(db):
    anlage_id = await _anlage(db)
    roi = await _roi(db, anlage_id)
    ctx = await build_finanzbericht_context(db, anlage_id)

    # N-213: das PDF hatte bis 09.08. gar keinen Zähler
    # (`einsparung_prognose_jahr` ist ein Feld ohne Schreiber) und rechnete
    # gegen die GESAMT-Anschaffung. Jetzt nennt es dieselbe Zahl wie die Sicht.
    # ⚠ **Ohne `if`** (N-221): am Stand vor dem Bau war
    # `gesamt_amortisation_jahre` falsy, und diese Probe lief deshalb **grün
    # durch, ohne etwas zu prüfen** — sie hätte N-213 nicht gemeldet.
    assert roi.gesamt_amortisation_jahre is not None
    # N-234 (30.08.): Der Erwartungswert baute die Formatierung als englischen
    # f-String NACH und hielt sie damit fest. Über den SoT gebildet prüft die
    # Probe jetzt Zahl UND Schreibweise — die Symmetrie-Aussage ist unberührt.
    assert ctx["amortisation_jahre"] == f"{fmt_zahl(roi.gesamt_amortisation_jahre, 1)} Jahre"
    assert "Kapitaleinsatz" in ctx["amortisation_berechnung"]


async def test_anlagenweite_ausgabe_erreicht_alle_vier_sichten(db):
    """Die Probe, die dieser Datei bis 2026-08-10 **fehlte** — und der Grund
    dafür, dass sie eine Zusicherung trug, die sie nicht prüfte.

    Die Fixture oben legt die Reparatur an einer **Investition** an. Steht
    dieselbe Position auf der **Monatsdaten-Zeile** (Monatsabschluss ohne
    Komponente, G19-1 — der Ort, den das Handbuch für „mehrere Komponenten"
    vorsieht), war der Nenner am 10.08. gemessen: HA-Sensor **18.000 €**,
    *Auswertungen → ROI* und *Aussichten* **15.000 €**. Der Docstring dieser
    Datei behauptete trotzdem „vier Sichten, ein Nenner".

    ⚠ *Ein Wächter deckt nur ab, was seine Fixture überhaupt herstellt* — die
    Lehre steht schon weiter unten für F-20 und traf hier eine Ebene höher.
    Behoben mit Bauschritt 4 des Konzepts §8.
    """
    from sqlalchemy import select as _select

    anlage = Anlage(anlagenname="AnlagenweiteAusgabe", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    # ⚑ Die Ausgabe steht auf der ANLAGE, nicht an einer Investition.
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=4,
        einspeisung_kwh=600.0, netzbezug_kwh=100.0,
        sonstige_positionen=[{"bezeichnung": "Dachreparatur",
                              "betrag": REPARATUR, "typ": "ausgabe"}],
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=5,
                       einspeisung_kwh=600.0, netzbezug_kwh=100.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=10000.0)
    db.add(pv)
    await db.flush()
    for monat in (4, 5):
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=monat,
                                      verbrauch_daten={"pv_erzeugung_kwh": 600.0}))
    await db.commit()

    erwartet = 10000.0 + REPARATUR
    roi = await _roi(db, anlage.id)
    prognose = await get_finanz_prognose(anlage_id=anlage.id, monate=12, db=db)
    anlage_row = (await db.execute(_select(Anlage).where(Anlage.id == anlage.id))).scalar_one()
    sensoren = {sv.definition.key: sv for sv in await calculate_anlage_sensors(db, anlage_row)}

    assert roi.gesamt_kapitaleinsatz == pytest.approx(erwartet)
    assert prognose.kapitaleinsatz_euro == pytest.approx(erwartet)
    if sensoren.get("roi_prozent") and sensoren["roi_prozent"].value:
        nenner = sensoren["jahres_ersparnis_euro"].value / sensoren["roi_prozent"].value * 100
        assert nenner == pytest.approx(erwartet, rel=0.01)
    # Und sie steht auf KEINER Investitionszeile — sie gehört zu keiner.
    assert not [b for b in roi.berechnungen
                if (b.detail_berechnung or {}).get("sonstige_ausgaben_euro")]


async def test_ertrag_mindert_den_nenner_wie_die_ausgabe_ihn_erhoeht(db):
    """Die zweite Zusicherung — beide Seiten des Bruchs, an einer Anlage.

    **Bauschritt 7 (2026-08-10):** eine Position im Monatsabschluss ist per
    Form einmal geflossen (§2/2) — als eingesetztes Kapital (Ausgabe) oder als
    Minderung desselben (Ertrag). Eine Förderung ist Geld, das nie eingesetzt
    wurde.

    ⚠ **Diese Probe stand bis 2026-08-10 auf dem Kopf** (`test_ertrag_bleibt_
    im_zaehler_…`) und war als Zwischenstand gekennzeichnet: solange es keinen
    Ort für *wiederkehrende* Erträge gab, hätte `(K − E·n) ÷ Z` jedes Jahr
    geschrumpft und wäre irgendwann negativ geworden. Den Ort gibt es seit
    §8/1 („Ertrag/Jahr" an der Investition) und §8/9 (€-Feld je Erzeuger,
    per HA-Sensor befüllbar) — #310 rilmor-mhrs wurde vorher informiert (§11).
    """
    anlage_id = await _anlage(db)
    roi = await _roi(db, anlage_id)

    # Der Ertrag hat den Nenner gemindert — um genau seinen Betrag …
    assert roi.gesamt_sonstige_ertraege_euro == pytest.approx(THG_ERTRAG)
    assert roi.gesamt_kapitaleinsatz == pytest.approx(
        RELEVANTE_KOSTEN + REPARATUR - THG_ERTRAG
    )
    # … und nicht etwa gar nicht (der Zustand vor Bauschritt 7).
    assert roi.gesamt_kapitaleinsatz != pytest.approx(RELEVANTE_KOSTEN + REPARATUR)

    # Beide Seiten stehen auf der Zeile, die sie trägt. Die Fixture hat
    # bewusst KEINEN Wechselrichter, das PV-Modul läuft deshalb über den
    # Orphan-Zweig — einen der drei Zweige, die `_sonstige_*_fuer` bedienen.
    zeilen_mit_ausgaben = [
        b for b in roi.berechnungen
        if b.detail_berechnung.get("sonstige_ausgaben_euro")
    ]
    assert len(zeilen_mit_ausgaben) == 1, "genau eine Zeile trägt die Reparatur"
    assert zeilen_mit_ausgaben[0].detail_berechnung["sonstige_ausgaben_euro"] == pytest.approx(REPARATUR)
    assert zeilen_mit_ausgaben[0].detail_berechnung["sonstige_ertraege_euro"] == pytest.approx(THG_ERTRAG)
    assert zeilen_mit_ausgaben[0].kapitaleinsatz == pytest.approx(
        10000.0 + REPARATUR - THG_ERTRAG
    )


async def test_ertrag_ueber_dem_kapital_liefert_keine_dauer(db):
    """Der Randfall, den Bauschritt 7 erst möglich macht: Nenner ≤ 0.

    Übersteigen die Erträge das eingesetzte Kapital, gibt es keine
    Amortisationsdauer — und eedc **rät** dort nicht (weder 0 Jahre noch eine
    negative Zahl). Geprüft wird die ausgelieferte Antwort, nicht nur der
    Layer: `berechne_roi` und `berechne_amortisations_fortschritt` klemmen
    beide bei `kosten <= 0`.
    """
    from sqlalchemy import select as _select

    anlage = Anlage(anlagenname="VollGefoerdert", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    for monat in (4, 5):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=monat,
                           einspeisung_kwh=600.0, netzbezug_kwh=100.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=5000.0)
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2025, monat=4,
        verbrauch_daten={
            "pv_erzeugung_kwh": 600.0,
            # Förderung über den Anschaffungskosten.
            "sonstige_positionen": [
                {"bezeichnung": "Förderung", "betrag": 6000.0, "typ": "ertrag"},
            ],
        },
    ))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 600.0}))
    await db.commit()

    roi = await _roi(db, anlage.id)
    assert roi.gesamt_kapitaleinsatz < 0, "Fixture erzeugt den Randfall nicht"
    assert roi.gesamt_amortisation_jahre is None
    assert roi.gesamt_roi_prozent is None

    prognose = await get_finanz_prognose(anlage_id=anlage.id, monate=12, db=db)
    assert prognose.amortisations_fortschritt_prozent == pytest.approx(0.0)
    assert prognose.amortisation_prognose_jahr is None

    anlage_row = (await db.execute(_select(Anlage).where(Anlage.id == anlage.id))).scalar_one()
    sensoren = {sv.definition.key: sv for sv in await calculate_anlage_sensors(db, anlage_row)}
    assert not (sensoren.get("amortisation_jahre") and sensoren["amortisation_jahre"].value)


# ============================================================================
# F-20 — jeder Posten mit SEINER Monatszahl
# ============================================================================
# ⚠ Diese Proben fehlten im ersten Wurf, und der Sprengsatz war deshalb STUMM:
# der Symmetrie-Test oben prüft den **Nenner**, F-20 sitzt im **Zähler** — und
# die Fixture dort hat weder Wärmepumpe noch E-Auto. Ein Wächter deckt nur ab,
# was seine Fixture überhaupt herstellt.


def test_layer_annualisiert_jeden_posten_einzeln():
    """Der Kern von F-20, ohne DB: zwei Posten, zwei Zeitbasen."""
    from backend.core.berechnungen.kapitalrechnung import (
        ErsparnisPosten,
        jahres_ersparnis_euro,
    )

    posten = [
        ErsparnisPosten("Anlage", 1200.0, 12),   # 1.200 €/Jahr
        ErsparnisPosten("Neue WP", 600.0, 6),    # 1.200 €/Jahr — läuft erst 6 Monate
    ]
    # Richtig: jeder Posten auf seiner eigenen Basis.
    assert jahres_ersparnis_euro(posten) == pytest.approx(2400.0)
    # Falsch wäre der gemeinsame Divisor der Anlage: (1800 ÷ 12) × 12 = 1800.
    assert jahres_ersparnis_euro(posten) != pytest.approx(1800.0)


def test_layer_monate_null_teilt_nicht_durch_null():
    from backend.core.berechnungen.kapitalrechnung import (
        ErsparnisPosten,
        jahres_ersparnis_euro,
    )

    assert jahres_ersparnis_euro([ErsparnisPosten("Leer", 500.0, 0)]) == pytest.approx(0.0)


def test_layer_erklaerung_nennt_die_betriebskosten():
    """N-212: ein Rechenweg, der einen Summanden verschweigt, ist keiner."""
    from backend.core.berechnungen.kapitalrechnung import (
        ErsparnisPosten,
        erklaerung_jahres_ersparnis,
        jahres_ersparnis_euro,
    )

    posten = [ErsparnisPosten("Anlagenbilanz", 1200.0, 12)]
    text = erklaerung_jahres_ersparnis(posten, betriebskosten_jahr_euro=500.0)
    assert "500.00" in text and "Betriebskosten" in text
    # Und der Text beschreibt wirklich den gelieferten Wert.
    assert jahres_ersparnis_euro(posten, betriebskosten_jahr_euro=500.0) == pytest.approx(700.0)


async def test_ha_sensor_verduennt_juengere_komponente_nicht(db):
    """F-20 an der Route: die WP läuft die halbe Anlagenzeit, zählt aber voll.

    Vorher lief die WP-Ersparnis durch `len(monatsdaten)` — die Monatszahl der
    **Anlage** —, während ihre Kosten voll im Nenner standen.
    """
    from sqlalchemy import select as _select

    anlage = Anlage(anlagenname="F20", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    # Anlage: 12 Monate Historie.
    for monat in range(1, 13):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=monat,
                           einspeisung_kwh=300.0, netzbezug_kwh=100.0,
                           gaspreis_cent_kwh=12.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=10000.0)
    # Wärmepumpe: erst ab Juli 2025, also 6 der 12 Monate.
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
                     anschaffungsdatum=date(2025, 7, 1),
                     anschaffungskosten_gesamt=18000.0,
                     anschaffungskosten_alternativ=8000.0)
    db.add_all([pv, wp])
    await db.flush()
    for monat in range(1, 13):
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=monat,
                                      verbrauch_daten={"pv_erzeugung_kwh": 800.0}))
    for monat in range(7, 13):
        db.add(InvestitionMonatsdaten(
            investition_id=wp.id, jahr=2025, monat=monat,
            verbrauch_daten={"stromverbrauch_kwh": 300.0, "waerme_kwh": 1000.0},
        ))
    await db.commit()

    anlage_row = (await db.execute(_select(Anlage).where(Anlage.id == anlage.id))).scalar_one()
    sensoren = {sv.definition.key: sv for sv in await calculate_anlage_sensors(db, anlage_row)}

    berechnung = sensoren["jahres_ersparnis_euro"].berechnung or ""
    # Der Rechenweg weist die WP mit IHREN 6 Monaten aus, nicht mit 12.
    assert "÷ 6)" in berechnung, berechnung
    assert "Wärmepumpe" in berechnung
    # Und die Anlagenbilanz mit ihren 12.
    assert "÷ 12)" in berechnung, berechnung
