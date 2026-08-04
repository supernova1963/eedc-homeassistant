"""Ein Speicher, drei Sichten — Achsen: Vollzyklen-Basis · Spread · Netzladung.

Zwei Kanons, die es seit längerem gibt, waren nicht überall durchgesetzt. Diese
Datei nagelt beide über die Read-Sites hinweg fest — und zwar **mit absoluten
Erwartungen**, nicht nur mit Gleichheit: vier gleich falsche Zahlen wären auch
symmetrisch ([[feedback_aggregator_symmetrie]], Lehre aus N-130).

**Achse 1 — Vollzyklen zählen die ENTLADUNG** (Kanon-Entscheid Gernot
2026-07-28, Rainer-PN 89768; Layer-SoT `core/berechnungen/speicher.vollzyklen`).
`cockpit/uebersicht.py` rechnete bis zum 2026-08-04 mit der **Ladung** — die
eine Route, die der Sweep übersah. Die zwei Zahlen liegen genau um den
Speicher-Wirkungsgrad auseinander (hier: 10,0 gegen 8,0 bei η 80 %). Der Wert
hatte damals keinen Client-Leser; mit dem Speicher-Block in Cockpit → Jahr
(#358 Phase 1) bekommt er einen, und dann wäre die Drift sichtbar geworden.

**Achse 2 — der Nutzen ist der SPREAD, nicht der Voll-Netzbezugspreis**
(Drift-Audit A3, im Docstring von `speicher_wirtschaftlichkeit` seit jeher
dokumentiert; von Gernot am 2026-08-04 für #358 bestätigt). Das T-Konto in
`aktueller_monat.py` rechnete `Entladung × Netzbezug` und lag damit bei 30/8 ct
**36 %** über der Zahl, die dieselbe Anlage in der ROI-Sicht trug.

**Achse 3 — netzgeladene Energie bekommt den PV-Spread NICHT.** Sie hätte nie
eingespeist werden können; ihr Vorteil ist `Bezug − Ladepreis`. Das
Speicher-Dashboard rechnete den Spread auf die **gesamte** Entladung und wies
den Arbitrage-Gewinn zusätzlich aus — der Komponenten-Hub addiert beide Posten,
also wurde dieselbe kWh doppelt gutgeschrieben.

Bewusst EINE Anlage, EIN Monat, EIN Tarif: geprüft wird nicht die Zeitachse
(dafür ADR-002/P8), sondern ob die Sichten dieselbe FORMEL benutzen.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.investitionen.dashboards import get_speicher_dashboard
from backend.core.berechnungen import auslastung_prozent, auslastungs_basis_kwh
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

JAHR, MONAT = 2026, 6
# η = 80 % — bewusst deutlich unter 100, sonst wäre „Ladung statt Entladung"
# nicht unterscheidbar (die Falle, in der der Kanon-Sweep die Route übersah).
LADUNG, ENTLADUNG = 500.0, 400.0
KAPAZITAET = 50.0
BEZUG_CENT, EINSPEISE_CENT = 30.0, 8.0


async def _anlage_mit_speicher(db, *, netzladung: float = 0.0,
                               ladepreis: float | None = None) -> int:
    """PV + Speicher, ein Monat, ein Tarif."""
    anlage = Anlage(anlagenname="SpeicherKanon", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=BEZUG_CENT,
        einspeiseverguetung_cent_kwh=EINSPEISE_CENT,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=MONAT,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=12000.0)
    db.add(pv)
    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=8000.0,
        # Kanon-Schlüssel `kapazitaet_kwh` (PARAM_SPEICHER) — NICHT
        # `batteriekapazitaet_kwh`, das ist der E-Auto-Schlüssel, und
        # `get_speicher_kapazitaet_kwh` liefert dafür korrekt None. Die Spalte
        # `leistung_kwp` bleibt bewusst leer: beim Speicher füllt sie kein
        # Schreibpfad, und der Helper liest sie nicht.
        parameter={"kapazitaet_kwh": KAPAZITAET},
    )
    db.add(speicher)
    await db.flush()

    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=JAHR, monat=MONAT,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    vd: dict = {"ladung_kwh": LADUNG, "entladung_kwh": ENTLADUNG}
    if netzladung:
        vd["ladung_netz_kwh"] = netzladung
    if ladepreis is not None:
        vd["speicher_ladepreis_cent"] = ladepreis
    db.add(InvestitionMonatsdaten(investition_id=speicher.id, jahr=JAHR,
                                  monat=MONAT, verbrauch_daten=vd))
    await db.commit()
    return anlage.id


# ── Achse 1: Vollzyklen ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vollzyklen_zaehlen_die_entladung_in_beiden_sichten(db):
    """400 kWh Entladung ÷ 50 kWh = **8,0** Zyklen — in Cockpit-Übersicht UND
    Monatssicht.

    Die Gegenzahl wäre 500 ÷ 50 = **10,0** (Ladung). Sie wird hier ausdrücklich
    ausgeschlossen, nicht nur die Gleichheit geprüft: bis zum 2026-08-04 lieferte
    `/cockpit/uebersicht` genau diese 10,0.
    """
    anlage_id = await _anlage_mit_speicher(db)

    uebersicht = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    monat = await get_aktueller_monat(anlage_id=anlage_id, jahr=JAHR, monat=MONAT, db=db)

    assert uebersicht.speicher_vollzyklen == pytest.approx(8.0, abs=0.05)
    assert monat.speicher_vollzyklen == pytest.approx(8.0, abs=0.05)
    assert uebersicht.speicher_vollzyklen == pytest.approx(
        monat.speicher_vollzyklen, abs=0.05
    )
    # Die alte Ladungs-Zahl darf nicht mehr auftauchen.
    assert uebersicht.speicher_vollzyklen != pytest.approx(10.0, abs=0.05)


# ── Achse 2: Spread ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t_konto_und_dashboard_rechnen_denselben_spread(db):
    """400 kWh × (30 − 8) ct = **88,00 €** — T-Konto wie Speicher-Dashboard.

    Der Voll-Netzbezugspreis ergäbe 400 × 30 ct = 120,00 €; das war der Stand
    des T-Kontos, und die Differenz von 36 % ist genau die aus dem Drift-Audit.
    """
    anlage_id = await _anlage_mit_speicher(db)

    monat = await get_aktueller_monat(anlage_id=anlage_id, jahr=JAHR, monat=MONAT, db=db)
    speicher_zeile = next(
        d for d in monat.investitionen_financials if d.typ == "speicher"
    )
    dashboards = await get_speicher_dashboard(anlage_id=anlage_id, db=db)
    dash = dashboards[0].zusammenfassung

    assert speicher_zeile.ersparnis_euro == pytest.approx(88.0, abs=0.5)
    assert dash["ersparnis_euro"] == pytest.approx(88.0, abs=0.5)
    # Die Voll-Preis-Zahl ist ausgeschlossen — sonst prüft der Test nur Gleichheit.
    assert speicher_zeile.ersparnis_euro != pytest.approx(120.0, abs=0.5)
    # Und die Kachel zeigt dieselbe Zahl wie die Zeile darunter (#358).
    assert monat.speicher_ersparnis_euro == pytest.approx(
        speicher_zeile.ersparnis_euro, abs=0.01
    )


# ── Achse 3: Netzladung ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_netzgeladene_energie_bekommt_keinen_pv_spread(db):
    """100 kWh aus dem Netz zu 10 ct, η 80 % ⇒ 80 kWh der Entladung sind Netz.

    PV-Anteil  : (400 − 80) × (30 − 8) = 70,40 €
    Netz-Anteil:        80  × (30 − 10) = 16,00 €
    Summe                               = 86,40 €

    Die alte Rechnung gab dem Netz-Anteil den PV-Spread (400 × 22 = 88,00 €)
    **und** wies die 16,00 € zusätzlich als Arbitrage-Gewinn aus — die
    Aufstellung im Hub addiert beide Posten und kam damit auf 104,00 €.
    """
    anlage_id = await _anlage_mit_speicher(db, netzladung=100.0, ladepreis=10.0)

    dashboards = await get_speicher_dashboard(anlage_id=anlage_id, db=db)
    dash = dashboards[0].zusammenfassung

    assert dash["ersparnis_euro"] == pytest.approx(86.4, abs=0.5)
    assert dash["arbitrage_gewinn_euro"] == pytest.approx(16.0, abs=0.5)
    assert dash["pv_anteil_euro"] == pytest.approx(70.4, abs=0.5)
    # Die beiden Posten der Hub-Aufstellung sind DISJUNKT und ergeben zusammen
    # die ausgewiesene Ersparnis — das ist die Invariante, an der die
    # Doppelzählung scheiterte.
    assert dash["pv_anteil_euro"] + dash["arbitrage_gewinn_euro"] == pytest.approx(
        dash["ersparnis_euro"], abs=0.01
    )


# ── Auslastung: additive Basis ──────────────────────────────────────────────

def test_auslastungs_basis_ist_additiv_ueber_monate():
    """Der Grund, warum die Basis ein eigenes Feld ist (#358).

    Ein Prozent-Mittelwert über Monate wäre falsch — der Februar wiegt weniger
    als der Juli. Über die Summen gerechnet stimmt es: 31 + 28 Tage à 10 kWh
    ergeben 590 kWh Basis, und 295 kWh Entladung sind darauf 50 %.
    """
    jan = auslastungs_basis_kwh(10.0, 31)
    feb = auslastungs_basis_kwh(10.0, 28)
    assert jan == 310.0 and feb == 280.0

    # Januar 40 %, Februar ~61,1 % — das arithmetische Mittel wäre 50,55 %.
    assert auslastung_prozent(124.0, jan) == pytest.approx(40.0, abs=0.1)
    assert auslastung_prozent(171.0, feb) == pytest.approx(61.07, abs=0.1)
    # Korrekt ist der Quotient der SUMMEN.
    assert auslastung_prozent(124.0 + 171.0, jan + feb) == pytest.approx(50.0, abs=0.1)


def test_auslastung_ohne_kapazitaet_ist_unbekannt_nicht_null():
    """P4-Haltung: fehlende Basis ⇒ `None`, keine 0 („nie genutzt")."""
    assert auslastungs_basis_kwh(None, 31) is None
    assert auslastungs_basis_kwh(0, 31) is None
    assert auslastung_prozent(100.0, None) is None
