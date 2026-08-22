"""#392 (gruaGit, OeMAG): variable Einspeisevergütung — ein Wert je Monat.

Die Wächter aus dem freigegebenen Auftrag (`auftrag-monatswert-einspeiseverguetung.md`):

1. **Der Monatswert schlägt den Stammwert, und 0 ist ein Wert** — Resolver-Unit.
2. **Ohne Häkchen kein Feld** — Registry-Probe an `get_basis_felder`.
3. **Symmetrie mit BEWEGTER Vergütungsachse**: derselbe Monat, derselbe Wert —
   Cockpit ≡ Aussichten-bisherige ≡ Jahresbericht ≡ HA-Export, auf den Cent,
   UND gegen den Absolutwert (Symmetrie allein ließe vier gleich falsche
   Zahlen durch). Die Bestands-Fixtures der Vier-Wege-Datei halten die
   Vergütung konstant bei 8,0 ct ([[feedback_aggregator_symmetrie]] — ein
   Symmetrie-Test deckt nur die Achsen ab, die seine Fixture variiert);
   diese hier bewegt sie und hält dafür den Arbeitspreis fest.
4. **Gegenprobe Zukunft**: die Hochrechnung nach vorn nimmt den Stammwert,
   auch wenn alle erfassten Monate Monatswerte tragen.
5. **CSV-Rundlauf der Basis-Spalte** — der F-55-Wächter nimmt nur
   Investitions-Spalten automatisch mit (Handlisten-Befund, Kartierung
   2026-08-22), deshalb hier die eigene Probe: Vorlage → Import → Spalte
   kommt an, auch mit dem Wert **0**; Export liefert die 0 zurück.

Self-contained:

    eedc/backend/venv/bin/python -m pytest eedc/backend/tests/test_einspeise_monatswert_392.py
"""

from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.api.routes.aussichten import get_finanz_prognose
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.ha_export import calculate_anlage_sensors
from backend.api.routes.import_export.csv_operations import (
    get_csv_template_info,
    import_csv,
)
from backend.api.routes.strompreise import resolve_einspeise_preis_cent
from backend.core.field_definitions import get_basis_felder
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context


# ============================================================================
# 1. Resolver — Monatswert schlägt Stammwert, 0 ist ein Wert
# ============================================================================

def test_resolver_monatswert_schlaegt_stammwert():
    md = SimpleNamespace(einspeise_durchschnittspreis_cent=4.2)
    assert resolve_einspeise_preis_cent(md, 8.0) == 4.2


def test_resolver_null_ist_ein_wert():
    """0 ct gepflegt (z. B. unvergüteter Monat) gewinnt — `is not None`, nicht truthy."""
    md = SimpleNamespace(einspeise_durchschnittspreis_cent=0.0)
    assert resolve_einspeise_preis_cent(md, 8.0) == 0.0


def test_resolver_ohne_monatswert_faellt_auf_stammwert():
    assert resolve_einspeise_preis_cent(
        SimpleNamespace(einspeise_durchschnittspreis_cent=None), 8.0
    ) == 8.0
    assert resolve_einspeise_preis_cent(None, 8.0) == 8.0
    # duck-typed: Objekt ohne das Attribut (z. B. ein dict-Ersatz) → Stammwert
    assert resolve_einspeise_preis_cent(SimpleNamespace(), 8.0) == 8.0


# ============================================================================
# 2. Registry — ohne Häkchen kein Feld
# ============================================================================

def test_feld_erscheint_nur_mit_haekchen():
    ohne = {f["feld"] for f in get_basis_felder()}
    mit = {f["feld"] for f in get_basis_felder(hat_variable_einspeisung=True)}
    assert "einspeise_durchschnittspreis_cent" not in ohne
    assert "einspeise_durchschnittspreis_cent" in mit


# ============================================================================
# 3. + 4. Vier Wege, bewegte Vergütungsachse + Zukunfts-Gegenprobe
# ============================================================================

async def _anlage_mit_variabler_verguetung(db) -> int:
    """Zwei Monate: 05/2026 trägt den Monatssatz 4,0 ct, 06/2026 keinen.

    Erwartung (Stammwert 8,0 ct · Arbeitspreis 30 ct, konstant):
      Mai:  einspeise = 400 × 0,04 = 16,00 €   ev = (1000−400) × 0,30 = 180,00 €
      Juni: einspeise = 200 × 0,08 = 16,00 €   ev = (500−200)  × 0,30 =  90,00 €
      netto = 302,00 €
    Mit Stammwert überall wären es 334,00 € — der Abstand (32 €) ist die Achse.
    """
    anlage = Anlage(anlagenname="VariableVerguetung", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
        einspeisung_variabel=True,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0,
                       einspeise_durchschnittspreis_cent=4.0))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=200.0, netzbezug_kwh=50.0))

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=12000.0)
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 500.0}))
    await db.commit()
    return anlage.id


ERWARTET_NETTO = 302.0


@pytest.mark.asyncio
async def test_cockpit_rechnet_den_monatssatz(db):
    anlage_id = await _anlage_mit_variabler_verguetung(db)
    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    assert cockpit.netto_ertrag_euro == pytest.approx(ERWARTET_NETTO, abs=0.1)
    # Gegenprobe gegen die Achse: mit Stammwert überall wären es 334,00 €.
    assert cockpit.netto_ertrag_euro != pytest.approx(334.0, abs=0.1)


@pytest.mark.asyncio
async def test_alle_vier_sichten_nennen_denselben_betrag(db):
    anlage_id = await _anlage_mit_variabler_verguetung(db)

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    aussichten = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)
    pdf = await build_jahresbericht_context(db, anlage_id, jahr=2026)
    anlage = await db.get(Anlage, anlage_id)
    sensoren = await calculate_anlage_sensors(db, anlage)
    ha_netto = next(
        s.value for s in sensoren if s.definition.key == "netto_ertrag_euro"
    )

    referenz = cockpit.netto_ertrag_euro
    assert referenz == pytest.approx(ERWARTET_NETTO, abs=0.1)
    assert aussichten.bisherige_ertraege_euro == pytest.approx(referenz, abs=0.1), (
        f"Aussichten {aussichten.bisherige_ertraege_euro} ≠ Cockpit {referenz}")
    assert pdf["kpis"]["netto_ertrag_euro"] == pytest.approx(referenz, abs=0.1), (
        f"PDF {pdf['kpis']['netto_ertrag_euro']} ≠ Cockpit {referenz}")
    assert ha_netto == pytest.approx(referenz, abs=0.1), (
        f"HA-Export {ha_netto} ≠ Cockpit {referenz}")


@pytest.mark.asyncio
async def test_zukunft_nimmt_den_stammwert(db):
    """Die Hochrechnung nach vorn bleibt beim Stammwert (künftige Monate haben
    keinen Monatswert) — auch wenn ein erfasster Monat 4,0 ct trägt."""
    anlage_id = await _anlage_mit_variabler_verguetung(db)
    aussichten = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)
    assert aussichten.einspeiseverguetung_cent_kwh == pytest.approx(8.0)


@pytest.mark.asyncio
async def test_monatssatz_null_ist_ein_wert_ende_zu_ende(db):
    """Ein Monat mit gepflegtem Satz **0,0** rechnet 0 € Einspeise-Erlös —
    nicht den Stammwert (die 0-Werte-Falle, gegen die der Resolver gebaut ist)."""
    anlage = Anlage(anlagenname="NullSatz", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
        einspeisung_variabel=True,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0,
                       einspeise_durchschnittspreis_cent=0.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1))
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    await db.commit()

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)
    # Nur die EV-Ersparnis bleibt: (1000 − 400) × 0,30 = 180,00 €.
    assert cockpit.netto_ertrag_euro == pytest.approx(180.0, abs=0.1)


# ============================================================================
# 5. CSV-Rundlauf der Basis-Spalte (inkl. 0)
# ============================================================================

class _FakeUpload:
    def __init__(self, text: str) -> None:
        self._data = text.encode("utf-8")

    async def read(self) -> bytes:
        return self._data


@pytest.mark.asyncio
async def test_csv_rundlauf_einspeiseverguetung_spalte(db):
    """Vorlage bietet die Spalte nur mit Häkchen an; ein importierter Wert —
    ausdrücklich auch die 0 — kommt in `Monatsdaten` an."""
    anlage = Anlage(anlagenname="CsvRundlauf", leistung_kwp=5.0,
                    installationsdatum=date(2023, 1, 1))
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
        einspeisung_variabel=True,
    ))
    await db.commit()

    vorlage = await get_csv_template_info(anlage.id, db)
    assert "Einspeiseverguetung_Cent" in vorlage.spalten

    werte = {"Jahr": "2024", "Monat": "3", "Einspeisung_kWh": "111",
             "Netzbezug_kWh": "222", "Einspeiseverguetung_Cent": "0"}
    out = StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(vorlage.spalten)
    writer.writerow([werte.get(s, "") for s in vorlage.spalten])

    ergebnis = await import_csv(
        anlage_id=anlage.id, file=_FakeUpload(out.getvalue()),
        ueberschreiben=True, auto_wetter=False, db=db,
    )
    assert ergebnis.erfolg, ergebnis.fehler

    md = (await db.execute(select(Monatsdaten).where(
        Monatsdaten.anlage_id == anlage.id,
        Monatsdaten.jahr == 2024, Monatsdaten.monat == 3,
    ))).scalar_one()
    assert md.einspeise_durchschnittspreis_cent == 0.0


@pytest.mark.asyncio
async def test_csv_vorlage_ohne_haekchen_ohne_spalte(db):
    """Gegenprobe ohne Häkchen: die Vorlage bleibt exakt wie heute."""
    anlage = Anlage(anlagenname="CsvOhne", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    await db.commit()

    vorlage = await get_csv_template_info(anlage.id, db)
    assert "Einspeiseverguetung_Cent" not in vorlage.spalten
