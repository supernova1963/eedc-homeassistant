"""Was eine Entladung wert ist, entscheidet ihre Stunde (F3, Nutzenseite).

Schwesterdateien: ``test_speicher_arbitrage_ladepreis.py`` (die Ladeseite
derselben Rechnung), ``test_speicher_dyn_tarif_und_soc.py`` (der Helper),
``test_speicher_wirtschaftlichkeit_netzanteil.py`` (die Layer-Formel).

**Der Befund** (SOLL Flex-Tarife **P-5**, 17.09.2026): Ein Spread ist eine
Differenz, und beide Seiten müssen dieselbe Auflösung tragen. Die **Ladeseite**
war seit #264 slot-scharf, die **Nutzenseite** blieb der Lebensdauer-Ø des
Bezugs. Bei einem Flex-Tarif ist das systematisch **zu niedrig**: Entladen wird
abends, wenn der Strom teuer ist — genau darum lohnt sich der Speicher.

⭐ Der Entladewert gilt **beide** Anteile der Ersparnis (PV-Anteil und
Arbitrage), weil beide dieselbe Frage beantworten: *Was hätte diese kWh aus dem
Netz gekostet?* Nur den Netz-Anteil umzustellen hieße, zwei Auflösungen in eine
Kachel zu schreiben.

⚠ **Kosten: keine.** Der Entladewert entsteht in demselben Durchgang wie der
Ladepreis — die Abfrage liest ohnehin jede Batterie-Stundenzeile des Zeitraums.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.dashboards import get_speicher_dashboard
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.tests.slot_saat import tep_zeilen

JAHR, MONAT = 2026, 5
TAG = date(2026, 5, 10)
STAMM_CENT = 30.0
EINSPEISE_CENT = 8.0
ENTLADUNG_ABEND_CENT = 50.0
LADUNG, ENTLADUNG = 500.0, 400.0


async def _anlage(db, *, mit_stundenpreisen: bool) -> int:
    """Speicher, der mittags aus PV lädt und abends teuer entlädt."""
    anlage = Anlage(anlagenname="Entladewert", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=STAMM_CENT,
        einspeiseverguetung_cent_kwh=EINSPEISE_CENT,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=JAHR, monat=MONAT,
        einspeisung_kwh=300.0, netzbezug_kwh=200.0,
    ))
    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=8000.0,
        parameter={"kapazitaet_kwh": 10.0},
    )
    db.add(speicher)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=speicher.id, jahr=JAHR, monat=MONAT,
        verbrauch_daten={"ladung_kwh": LADUNG, "entladung_kwh": ENTLADUNG},
    ))
    # Mittags laden (aus PV, kein Netzbezug), abends entladen.
    preis_mittag = 10.0 if mit_stundenpreisen else None
    preis_abend = ENTLADUNG_ABEND_CENT if mit_stundenpreisen else None
    # ⭐ **N-387: der Stundenpreis steht in der Zeile davor.** `batterie_kw` und
    # `netzbezug_kw` einer Stunde liegen backward, `strompreis_cent` forward —
    # `tep_zeilen` verteilt beides so, wie die Produktion es ablegt. Die Aussage
    # der Probe ist unverändert: die Entladestunde 19 gilt 50 ct.
    db.add_all(tep_zeilen(anlage.id, [
        {"datum": TAG, "stunde": 12,
         "pv_kw": 5.0, "verbrauch_kw": 1.0, "einspeisung_kw": 2.0, "netzbezug_kw": 0.0,
         "batterie_kw": -2.0, "strompreis_cent": preis_mittag},
        {"datum": TAG, "stunde": 19,
         "pv_kw": 0.0, "verbrauch_kw": 3.0, "einspeisung_kw": 0.0, "netzbezug_kw": 1.0,
         "batterie_kw": 2.0, "strompreis_cent": preis_abend},
    ]))
    await db.commit()
    return anlage.id


async def _dash(db, anlage_id: int) -> dict:
    return (await get_speicher_dashboard(anlage_id=anlage_id, db=db))[0].zusammenfassung


@pytest.mark.asyncio
async def test_entladung_wird_mit_dem_preis_ihrer_stunde_bewertet(db):
    """⭐ Der Kern: Abends entladen ist mehr wert als der Lebensdauer-Ø.

    Entladen wird zu 50 ct, der Stammpreis ist 30 ct. Der PV-Anteil der
    Ersparnis muss dem Spread gegen die **50** folgen, nicht gegen die 30 —
    sonst rechnet eedc den Speicher systematisch schlechter, als er ist.
    """
    aid = await _anlage(db, mit_stundenpreisen=True)

    dash = await _dash(db, aid)

    erwartet = ENTLADUNG * (ENTLADUNG_ABEND_CENT - EINSPEISE_CENT) / 100
    assert dash["pv_anteil_euro"] == pytest.approx(erwartet, abs=0.5)
    # Die Gegenprobe im selben Test: mit dem Stammpreis wären es 88 € statt 168 €.
    assert dash["pv_anteil_euro"] != pytest.approx(
        ENTLADUNG * (STAMM_CENT - EINSPEISE_CENT) / 100, abs=0.5
    )


@pytest.mark.asyncio
async def test_ohne_stundenpreise_bleibt_der_lebensdauer_oe(db):
    """SOLL §10, Prüfstein 2 — die Regression.

    Ohne Mitschrift liefert der Helper keinen Entladewert, und es gilt
    unverändert der bisherige Ø. Für eine Festpreis-Anlage bewegt dieser Bau
    damit **keine** Zahl.
    """
    aid = await _anlage(db, mit_stundenpreisen=False)

    dash = await _dash(db, aid)

    assert dash["pv_anteil_euro"] == pytest.approx(
        ENTLADUNG * (STAMM_CENT - EINSPEISE_CENT) / 100, abs=0.5
    )
