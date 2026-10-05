"""N-633 — dienstliche Ladekosten: ein Posten, sieben Sichten, eine Zahl (05.10.2026).

**Regel (Entscheid 31.07., ``core/berechnungen/dienstliche_ladekosten.py``):** was ein Dienstwagen zu Hause geladen
hat, kostet die Anlage — PV-Anteil zum Netzbezugspreis (nimmt die EV-Gutschrift zurück), Netzanteil zum Wallbox-Tarif.
Seit N-633 bildet die Monats-Fakten-Schicht den Betrag (``EmobFakten.dienstliche_ladekosten_euro``), und er ist ein
eigener Posten der Ergebnis-Leiter (``ergebnis.py::POSTEN``, Stufe 1, −). Bis dahin zogen ihn Übersicht, HA-Export und
Aussichten ab (sie rechneten ihn je selbst), Cockpit → Monat, Cockpit → Jahr, Auswertungen → Tabelle und das PDF nicht:
dieselbe Anlage, derselbe Monat, zwei Netto-Erträge (Matrix-Form M09: 104,40 € gegen 122,40 €).

Fixture wie ``test_dienstliche_ladekosten_drei_sichten.py::_anlage_mit_wallbox_tarif`` (Juni 2026):
PV 1.000 · Einspeisung 400 · Netzbezug 300 · Dienstwagen 200 kWh PV + 100 kWh Netz · 30/8 ct, Wallbox 18 ct.
Posten = 200 × 30 ct + 100 × 18 ct = 78,00 €; Netto-Ertrag = 400 × 8 ct + 600 × 30 ct − 78 = 134,00 €.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.tests import factories

JAHR, MONAT = 2026, 6
POSTEN_EURO = 78.0
NETTO_EURO = 134.0
ANSCHAFFUNG = date(2024, 1, 1)


async def _anlage(db, *, dienstlich: bool = True) -> int:
    anlage = await factories.anlage_mit_tarif(db, f"N633-{dienstlich}")
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=18.0, einspeiseverguetung_cent_kwh=8.0,
        verwendung="wallbox",
    ))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=ANSCHAFFUNG,
                     anschaffungskosten_gesamt=10000.0)
    wagen = Investition(anlage_id=anlage.id, typ="e-auto",
                        bezeichnung="Firmenwagen" if dienstlich else "Privatwagen",
                        anschaffungsdatum=ANSCHAFFUNG,
                        parameter={"ist_dienstlich": True} if dienstlich else {})
    db.add_all([pv, wagen])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=JAHR, monat=MONAT,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(
        investition_id=wagen.id, jahr=JAHR, monat=MONAT,
        verbrauch_daten={"ladung_kwh": 300.0, "ladung_pv_kwh": 200.0, "ladung_netz_kwh": 100.0}))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=MONAT,
                       einspeisung_kwh=400.0, netzbezug_kwh=300.0))
    await db.commit()
    return anlage.id


async def _sieben_sichten(db, anlage_id: int) -> dict[str, float]:
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.aussichten import get_finanz_prognose
    from backend.api.routes.cockpit.jahr import get_cockpit_jahr
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export import calculate_anlage_sensors
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    monat = await get_aktueller_monat(anlage_id=anlage_id, jahr=JAHR, monat=MONAT, db=db)
    jahr = await get_cockpit_jahr(anlage_id=anlage_id, jahr=JAHR, db=db)
    reihe = [z if isinstance(z, dict) else z.model_dump()
             for z in await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=JAHR, db=db)]
    pdf = await build_jahresbericht_context(db, anlage_id, jahr=JAHR)
    uebersicht = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    anlage = await db.get(Anlage, anlage_id)
    ha = {s.definition.key: s.value for s in await calculate_anlage_sensors(db, anlage)}
    aussichten = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)
    juni = next(z for z in reihe if z["monat"] == MONAT)
    pdf_juni = next(z for z in pdf["monats_zeilen"] if z["monat"] == MONAT)
    return {
        "Cockpit → Monat": monat.netto_ertrag_euro,
        "Cockpit → Jahr": jahr["kopf"]["netto_ertrag_euro"],
        "Auswertungen → Tabelle": juni["netto_ertrag_euro"],
        "PDF Monatszeile": pdf_juni["netto_ertrag_euro"],
        "PDF Kopf": pdf["kpis"]["netto_ertrag_euro"],
        "Cockpit → Übersicht": uebersicht.netto_ertrag_euro,
        "HA-Sensor": ha["netto_ertrag_euro"],
        "Aussichten → bisherige Erträge": aussichten.bisherige_ertraege_euro,
    }


async def test_sieben_sichten_eine_zahl(db):
    werte = await _sieben_sichten(db, await _anlage(db))
    abw = {k: v for k, v in werte.items() if v != pytest.approx(NETTO_EURO, abs=0.01)}
    assert not abw, f"Soll {NETTO_EURO} € — abweichend: {abw}"


async def test_ohne_dienstwagen_kein_posten(db):
    """Privatwagen: kein Posten, die Sichten der Ergebnis-Leiter 212,00 € (600 × 30 ct + 400 × 8 ct).

    Die Aussichten sind hier ausgenommen: mit einem PRIVATEN E-Auto ist ``bisherige_ertraege_euro`` nicht das
    Finanz-Aggregat allein (die Bestandsprobe ``test_dienstliche_ladekosten_drei_sichten.py`` nennt dieselbe Grenze
    für ihre Vorrichtung) — gemessen 194,00 €, vor und nach N-633 gleich.
    """
    werte = await _sieben_sichten(db, await _anlage(db, dienstlich=False))
    assert werte.pop("Aussichten → bisherige Erträge") == pytest.approx(194.0, abs=0.01)
    abw = {k: v for k, v in werte.items() if v != pytest.approx(212.0, abs=0.01)}
    assert not abw, abw


async def test_cockpit_monat_fuehrt_den_posten_in_der_leiter(db):
    """Cockpit → Monat: eigenes Antwortfeld, Herleitung mit dem Namen, Hauptbuch der Herleitung == Netto-Ertrag;
    die Sonstigen Positionen tragen ihn NICHT (sie sind Eingang des Kapitaleinsatzes, F-19)."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    d = await get_aktueller_monat(anlage_id=await _anlage(db), jahr=JAHR, monat=MONAT, db=db)
    assert d.dienstliche_ladekosten_euro == pytest.approx(POSTEN_EURO)
    # A6: die eingesetzten Werte führen auf den Betrag (200 × 30 ct + 100 × 18 ct = 78 €).
    assert d.dienstliche_ladekosten_berechnung == "200,0 kWh PV × 30,00 ct/kWh + 100,0 kWh Netz × 18,00 ct/kWh"
    assert d.sonstige_ausgaben_euro == pytest.approx(0.0)
    assert d.sonstige_netto_euro == pytest.approx(0.0)
    h = d.ergebnis_herleitung.netto_ertrag
    assert "Dienstliche Ladekosten" in h.formel
    posten = {w.name: w.betrag_euro for w in h.eingesetzte_werte}
    assert posten["Dienstliche Ladekosten"] == pytest.approx(-POSTEN_EURO)
    assert sum(posten.values()) == pytest.approx(d.netto_ertrag_euro, abs=1e-9)
    # Das Ergebnis (Stufe 3) zieht ihn ebenso ab.
    erg = {w.name: w.betrag_euro for w in d.ergebnis_herleitung.ergebnis.eingesetzte_werte}
    assert erg["Dienstliche Ladekosten"] == pytest.approx(-POSTEN_EURO)


async def test_ohne_dienstwagen_steht_der_posten_nicht_in_der_herleitung(db):
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    d = await get_aktueller_monat(anlage_id=await _anlage(db, dienstlich=False), jahr=JAHR, monat=MONAT, db=db)
    assert d.dienstliche_ladekosten_euro == 0.0
    assert d.dienstliche_ladekosten_berechnung is None
    assert "Dienstliche Ladekosten" not in d.ergebnis_herleitung.ergebnis.formel
    assert "Dienstliche Ladekosten" not in d.fehlende_posten


async def test_monatsbericht_und_jahresbericht_tragen_die_zeile(db):
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.core.berechnungen.dienstliche_ladekosten import DIENSTLICHE_LADEKOSTEN_HINWEIS
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context
    from backend.services.pdf.builders.monatsbericht import _abschnitte_finanzen

    aid = await _anlage(db)
    d = await get_aktueller_monat(anlage_id=aid, jahr=JAHR, monat=MONAT, db=db)
    zeilen = [z for a in _abschnitte_finanzen(d) for z in a.zeilen]
    treffer = [z for z in zeilen if z.label == "Dienstliche Ladekosten"]
    assert len(treffer) == 1 and treffer[0].hinweis == DIENSTLICHE_LADEKOSTEN_HINWEIS
    pdf = await build_jahresbericht_context(db, aid, jahr=JAHR)
    assert pdf["kpis"]["dienstliche_ladekosten_euro"] == pytest.approx(POSTEN_EURO)


async def test_kapitaleinsatz_unberuehrt(db):
    """F-19: der Posten ist laufender Aufwand — Sonstige Ausgaben der Monats-Fakten (Kapitaleinsatz) bleiben 0."""
    from backend.services.monats_fakten import lade_monats_fakten

    fakten = await lade_monats_fakten(db, await _anlage(db), von=(JAHR, MONAT), bis=(JAHR, MONAT))
    assert fakten[0].emob.dienstliche_ladekosten_euro == pytest.approx(POSTEN_EURO)
    assert fakten[0].sonstiges.ausgaben_euro == pytest.approx(0.0)
