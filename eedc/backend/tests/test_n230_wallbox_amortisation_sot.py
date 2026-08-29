"""N-230/N-140 — der Wallbox-Hub rechnet nicht selbst, und ein `Optional` wird geprüft.

**N-230.** Die Amortisationsdauer im Komponenten-Hub der Wallbox entstand im
Client aus ``anschaffungskosten_gesamt ÷ Jahres-Ersparnis``. Der Nenner der
Wirtschaftlichkeitsrechnung ist aber der **Kapitaleinsatz**
(``core/berechnungen/kapitalrechnung.py``): relevante Kosten — also nach Abzug
der Alternativkosten — plus kumulierte sonstige Ausgaben, **minus** die
sonstigen Erträge. Eine geförderte Wallbox bekam damit eine zu lange Dauer,
direkt neben der Zahl des ROI-Dashboards.

Der **Zähler** bleibt bewusst die gemessene Heimlade-Ersparnis (die ROI-Zeile
einer Wallbox rechnet mit ``einsparung_prognose_jahr``, „Manuelle Prognose
verwendet"). Diese Proben decken deshalb den Nenner, den Betriebskosten-Abzug
und den Annahme-Text — nicht die Frage, welcher Zähler der richtige ist.

**N-140.** ``aggregiere_speicher_ist`` ist dokumentiert ``Optional`` und
liefert ``None`` im völlig normalen Fall „weniger als drei Monate Historie".
Der Speicher-Hub griff ungeprüft auf ``.jahres_faktor`` zu; der breite
``except`` machte daraus die Log-Warnung „η-IST fehlgeschlagen:
AttributeError". Der Schwesterpfad in ``crud.py`` prüft dort seit jeher.
"""

from __future__ import annotations

from datetime import date

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.api.routes.investitionen.dashboards import (
    get_speicher_dashboard,
    get_wallbox_dashboard,
)

# Zwölf Monate mit je 100 kWh Heimladung; extern 100 kWh für 50 €
# (0,50 €/kWh) ⇒ die Heimladung „als extern" kostet 600 €.
MONATE = 12
HEIM_KWH_JE_MONAT = 100.0


async def _seed(
    db,
    *,
    anschaffung: float = 2000.0,
    alternativ: float | None = None,
    foerderung: float | None = None,
    betriebskosten: float | None = None,
) -> tuple[int, int]:
    """Anlage + E-Auto (liefert die Heimladung) + eine Wallbox."""
    anlage = Anlage(anlagenname="N-230", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    for monat in range(1, MONATE + 1):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            netzbezug_kwh=200.0, einspeisung_kwh=300.0,
        ))

    eauto = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="E-Auto",
        anschaffungsdatum=date(2024, 12, 1), parameter={},
    )
    wallbox = Investition(
        anlage_id=anlage.id, typ="wallbox", bezeichnung="Wallbox",
        anschaffungsdatum=date(2024, 12, 1),
        anschaffungskosten_gesamt=anschaffung,
        anschaffungskosten_alternativ=alternativ,
        betriebskosten_jahr=betriebskosten,
        parameter={},
    )
    db.add_all([eauto, wallbox])
    await db.flush()

    for monat in range(1, MONATE + 1):
        db.add(InvestitionMonatsdaten(
            investition_id=eauto.id, jahr=2025, monat=monat,
            verbrauch_daten={
                "ladung_pv_kwh": HEIM_KWH_JE_MONAT,
                "ladung_netz_kwh": 0.0,
                "extern_ladung_kwh": 10.0,
                "extern_kosten_euro": 5.0,
            },
        ))
    if foerderung is not None:
        # Sonstige Position am GERÄT — sie mindert den Kapitaleinsatz.
        db.add(InvestitionMonatsdaten(
            investition_id=wallbox.id, jahr=2025, monat=1,
            verbrauch_daten={"sonstige_positionen": [
                {"bezeichnung": "Förderung", "betrag": foerderung, "typ": "ertrag"},
            ]},
        ))
    await db.flush()
    return anlage.id, wallbox.id


async def _zusammenfassung(db, anlage_id: int) -> dict:
    # `strompreis_cent` explizit — beim DIREKTEN Aufruf löst FastAPI den
    # `Query(None)`-Default nicht auf (dasselbe Muster wie in
    # `test_speicher_dashboard_attribut_bug.py`).
    ergebnis = await get_wallbox_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, db=db
    )
    assert ergebnis, "keine Wallbox im Ergebnis — Fixture defekt"
    return ergebnis[0].zusammenfassung


async def test_die_antwort_traegt_die_dauer_ueberhaupt(db):
    """Ohne diese Felder bliebe dem Client nichts, als selbst zu rechnen."""
    anlage_id, _ = await _seed(db)
    z = await _zusammenfassung(db, anlage_id)
    assert z["amortisation_jahre"] is not None
    assert z["amortisation_annahme"]
    assert z["kapitaleinsatz_euro"] == 2000.0
    # Zähler = gemessene Ersparnis, annualisiert mit IHRER eigenen Monatszahl.
    assert z["jahres_ersparnis_euro"] == round(z["ersparnis_vs_extern_euro"], 2)


async def test_alternativkosten_verkuerzen_die_dauer(db):
    """Der Nenner sind die **relevanten** Kosten, nicht die Anschaffung.

    Der Client teilte durch `anschaffungskosten_gesamt` und sah die
    Alternativkosten nie.
    """
    ohne, _ = await _seed(db, anschaffung=2000.0)
    mit, _ = await _seed(db, anschaffung=2000.0, alternativ=800.0)

    z_ohne = await _zusammenfassung(db, ohne)
    z_mit = await _zusammenfassung(db, mit)

    assert z_mit["kapitaleinsatz_euro"] == 1200.0
    assert z_mit["amortisation_jahre"] < z_ohne["amortisation_jahre"]


async def test_foerderung_verkuerzt_die_dauer(db):
    """Eine Förderung ist Geld, das nie eingesetzt wurde (Konzept §8/7).

    Das ist der Fall, der N-230 zum Fehler macht: geförderte Wallboxen sind
    der Regelfall, und der Client kannte die Position nicht.
    """
    ohne, _ = await _seed(db, anschaffung=2000.0)
    mit, _ = await _seed(db, anschaffung=2000.0, foerderung=500.0)

    z_ohne = await _zusammenfassung(db, ohne)
    z_mit = await _zusammenfassung(db, mit)

    assert z_mit["kapitaleinsatz_euro"] == 1500.0
    assert z_mit["amortisation_jahre"] < z_ohne["amortisation_jahre"]


async def test_betriebskosten_aendern_zahl_und_annahmetext(db):
    """Bauschritt 6: der Annahme-Text folgt den DATEN, nicht dem Modellnamen.

    Der Client hielt hier eine feste Konstante („ohne künftige
    Instandhaltung") — bei gepflegten Betriebskosten hätte sie die eigene
    Rechnung falsch beschrieben.
    """
    ohne, _ = await _seed(db, anschaffung=2000.0)
    mit, _ = await _seed(db, anschaffung=2000.0, betriebskosten=120.0)

    z_ohne = await _zusammenfassung(db, ohne)
    z_mit = await _zusammenfassung(db, mit)

    assert z_ohne["amortisation_annahme"] == "ohne künftige Instandhaltung"
    assert z_mit["amortisation_annahme"] != z_ohne["amortisation_annahme"]
    assert "120,00 €/Jahr" in z_mit["amortisation_annahme"]
    # Die Betriebskosten stehen im ZÄHLER — die Dauer wird länger.
    assert z_mit["amortisation_jahre"] > z_ohne["amortisation_jahre"]


async def test_ohne_bewertbaren_nenner_keine_zahl_statt_einer_null(db):
    """`None` heißt „nicht bewertbar" und ist nicht 0 (ADR-002/P4).

    Vollständig gefördert ⇒ Kapitaleinsatz ≤ 0 ⇒ keine Dauer. Der Client
    zeigte in seinem Zweig „∞", sobald die Ersparnis ≤ 0 war, und hatte für
    diesen Fall gar keine Regel.
    """
    anlage_id, _ = await _seed(db, anschaffung=1000.0, foerderung=1000.0)
    z = await _zusammenfassung(db, anlage_id)
    assert z["kapitaleinsatz_euro"] <= 0
    assert z["amortisation_jahre"] is None


# ─────────────────────────── N-140 ───────────────────────────

async def _seed_speicher_kurze_historie(db, monate: int) -> int:
    anlage = Anlage(anlagenname="N-140", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=1,
                       netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    sp = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Neuer Speicher",
        anschaffungsdatum=date(2025, 12, 1),
        parameter={"kapazitaet_kwh": 10, "nutzbare_kapazitaet_kwh": 9.5},
    )
    db.add(sp)
    await db.flush()
    for monat in range(1, monate + 1):
        db.add(InvestitionMonatsdaten(
            investition_id=sp.id, jahr=2026, monat=monat,
            verbrauch_daten={"ladung_kwh": 300.0, "entladung_kwh": 270.0},
        ))
    await db.flush()
    return anlage.id


async def test_frische_anlage_erzeugt_keine_fehlerwarnung(db, caplog):
    """Zwei Monate Historie sind der Normalfall, kein Fehler.

    `aggregiere_speicher_ist` liefert dort `None`; der ungeprüfte Zugriff auf
    `.jahres_faktor` schrieb „η-IST fehlgeschlagen: AttributeError" ins Log —
    bei **jedem** Abruf, für einen Fehler, den es nicht gab.
    """
    import logging

    anlage_id = await _seed_speicher_kurze_historie(db, monate=2)
    with caplog.at_level(logging.WARNING):
        ergebnis = await get_speicher_dashboard(
            anlage_id=anlage_id, strompreis_cent=None,
            einspeiseverguetung_cent=None, db=db,
        )

    assert ergebnis, "kein Speicher im Ergebnis — Fixture defekt"
    assert not [r for r in caplog.records if "AttributeError" in r.getMessage()], (
        "der Optional-Zugriff ist zurück: "
        f"{[r.getMessage() for r in caplog.records]}"
    )
