"""A6 — die vier Antwortfelder, aus denen die Anzeige ihre Herleitung baut (N-365).

Style-Guide **A6 (Berechnungs-Transparenz)**: *„Formel + eingesetzte Werte +
Datenquelle/Zeitraum."* Drei T-Konto-Zeilen und die Performance-Ratio-Kachel
zeigten bis zum 13.09.2026 nur ihre Formel — die Zahlen, mit denen gerechnet
wurde, standen auf keiner Fläche.

⛔ **Warum das Backend-Felder sind und keine Client-Rechnung.** Bauform aus
`fa270c6f`: die Herleitung nennt die Zahlen, mit denen der **Layer** gerechnet
hat. Ein im Client gebildetes ``monat × 12`` oder ein anderer Ø-Nenner ergäbe
eine Rechnung, die nicht auf die Zahl daneben führt — genau die Klasse, an der
ein Melder monatelang eine unmögliche Arbeitszahl nicht einordnen konnte.

Die vier Felder:

* ``InvestitionFinancialDetail.erloes_berechnung`` — Split des BKW-Textes; die
  gepflegt-Zweige bleiben ``None`` (Herkunftsangabe, keine Rechnung).
* ``InvestitionFinancialDetail.betriebskosten_jahr_euro``
* ``AktuellerMonatResponse.betriebskosten_anteilig_jahr_euro`` + ``_anzahl``
* ``MonatsAuswertung.performance_ratio_tage`` (in
  ``test_a6_performance_ratio_tage.py``, weil es ein anderer Endpunkt ist)

Geschwister: ``test_aktueller_monat_tkonto.py`` (Beträge je Typ),
``test_abgabe_geldseite_beschriftung.py`` (die Namen der Zeilen).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

JAHR, MONAT = 2024, 5


def _detail(res, inv_id):
    for d in res.investitionen_financials:
        if d.investition_id == inv_id:
            return d
    return None


async def _seed(db: AsyncSession) -> Anlage:
    anlage = Anlage(anlagenname="A6", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=MONAT,
                       netzbezug_kwh=0.0, einspeisung_kwh=0.0))
    return anlage


async def _inv(db, anlage, typ, *, vd=None, betriebskosten_jahr=None, parameter=None) -> int:
    inv = Investition(anlage_id=anlage.id, typ=typ, bezeichnung=f"{typ}-A6",
                      anschaffungsdatum=date(2024, 1, 1),
                      betriebskosten_jahr=betriebskosten_jahr, parameter=parameter)
    db.add(inv)
    await db.flush()
    if vd is not None:
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT,
                                      verbrauch_daten=vd))
    return inv.id


# ── erloes_berechnung ────────────────────────────────────────────────────────

async def test_bkw_erloes_trennt_formel_und_eingesetzte_werte(db):
    """Der gerechnete Erlös: Formel OHNE Zahlen, Zahlen im eigenen Feld."""
    anlage = await _seed(db)
    bkw_id = await _inv(db, anlage, "balkonkraftwerk",
                        vd={"eigenverbrauch_kwh": 100.0, "einspeisung_kwh": 50.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    d = _detail(res, bkw_id)
    assert d is not None
    assert d.erloes_formel == "Einspeisung × Einspeisevergütung"
    # N-555 (§11): deutsche Schreibweise über `core/zahlenformat.py`.
    assert d.erloes_berechnung == "50,0 kWh × 8,00 ct/kWh"
    # Der Wert selbst ändert sich nicht: 50 kWh × 8 ct.
    assert d.erloes_euro == 4.0


async def test_die_formel_traegt_keine_zahl_mehr(db):
    """Zweite Regelhälfte, eigene Probe.

    Die Probe darüber wäre auch grün, wenn die Zahlen ZUSÄTZLICH im Formeltext
    stünden — dann stünde dieselbe Rechnung zweimal da, einmal unter der
    falschen Überschrift. Genau das war der Zustand bis zum 13.09.2026.
    """
    anlage = await _seed(db)
    bkw_id = await _inv(db, anlage, "balkonkraftwerk",
                        vd={"eigenverbrauch_kwh": 100.0, "einspeisung_kwh": 50.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    formel = _detail(res, bkw_id).erloes_formel
    assert not any(z.isdigit() for z in formel), formel


async def test_gepflegter_erloes_bleibt_ohne_berechnung(db):
    """Konzept §9 Weg 2: ein gepflegter Betrag ist keine Rechnung.

    Die Gegenprobe zur ersten: ohne sie wäre die Regel auch dann erfüllt, wenn
    der Split pauschal irgendetwas in den Berechnungs-Slot schriebe.
    """
    anlage = await _seed(db)
    so_id = await _inv(db, anlage, "sonstiges",
                       vd={"einspeisung_kwh": 20.0, "einspeise_erloes_euro": 35.5})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    d = _detail(res, so_id)
    assert d is not None
    assert "gepflegt" in d.erloes_formel
    assert d.erloes_berechnung is None


# ── betriebskosten_jahr_euro ─────────────────────────────────────────────────

async def test_betriebskosten_jahr_kommt_aus_der_investition(db):
    anlage = await _seed(db)
    sp_id = await _inv(db, anlage, "speicher", vd={"entladung_kwh": 80.0},
                       betriebskosten_jahr=150.0)
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    d = _detail(res, sp_id)
    assert d.betriebskosten_jahr_euro == 150.0
    assert d.betriebskosten_monat_euro == 12.5


async def test_ohne_betriebskosten_steht_dort_null_und_keine_rechnung(db):
    """0,00 €/Jahr ist keine Herleitung — der Client zeigt sie deshalb nicht."""
    anlage = await _seed(db)
    bkw_id = await _inv(db, anlage, "balkonkraftwerk",
                        vd={"eigenverbrauch_kwh": 100.0}, betriebskosten_jahr=None)
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert _detail(res, bkw_id).betriebskosten_jahr_euro == 0.0


# ── betriebskosten_anteilig_jahr_euro + _anzahl ──────────────────────────────

async def test_anteilige_betriebskosten_nennen_summe_und_anzahl(db):
    """Σ Jahresbeträge und Anzahl kommen aus DERSELBEN Filtermenge wie der
    Monatsanteil — ein zweiter Durchlauf mit anderem Filter wäre eine
    Herleitung, die auf eine andere Zahl führt."""
    anlage = await _seed(db)
    await _inv(db, anlage, "speicher", vd={"entladung_kwh": 1.0}, betriebskosten_jahr=120.0)
    await _inv(db, anlage, "waermepumpe", vd={"stromverbrauch_kwh": 1.0}, betriebskosten_jahr=240.0)
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.betriebskosten_anteilig_euro == 30.0          # (120 + 240) / 12
    assert res.betriebskosten_anteilig_jahr_euro == 360.0
    assert res.betriebskosten_anteilig_anzahl == 2


async def test_investitionen_ohne_betriebskosten_zaehlen_nicht_mit(db):
    """Die Anzahl nennt die Geräte, die zur Summe BEITRAGEN — nicht alle.

    Ohne diese Probe wäre die Regel auch dann erfüllt, wenn dort schlicht die
    Zahl aller Investitionen stünde; die Herleitung „360 €/Jahr ÷ 12
    (3 Investitionen)" nennt dann ein Gerät mit, das keinen Cent beisteuert.
    """
    anlage = await _seed(db)
    await _inv(db, anlage, "speicher", vd={"entladung_kwh": 1.0}, betriebskosten_jahr=120.0)
    await _inv(db, anlage, "waermepumpe", vd={"stromverbrauch_kwh": 1.0}, betriebskosten_jahr=240.0)
    await _inv(db, anlage, "balkonkraftwerk", vd={"eigenverbrauch_kwh": 5.0}, betriebskosten_jahr=None)
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.betriebskosten_anteilig_anzahl == 2
    assert res.betriebskosten_anteilig_jahr_euro == 360.0


async def test_ohne_betriebskosten_bleiben_alle_drei_felder_leer(db):
    anlage = await _seed(db)
    await _inv(db, anlage, "balkonkraftwerk", vd={"eigenverbrauch_kwh": 5.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.betriebskosten_anteilig_euro is None
    assert res.betriebskosten_anteilig_jahr_euro is None
    assert res.betriebskosten_anteilig_anzahl is None
