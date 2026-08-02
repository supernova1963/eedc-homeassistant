"""P-11 — Arbeitspreis-Kosten getrennt vom Grundpreis + effektiver Preis.

Zwei zusammenhängende Befunde aus Forum simon42 #89667 (Algie):

1. Die Ø-Preis-Kachel in Cockpit → Monat stellte `netzbezug_kwh` und
   `netzbezug_kosten_euro` nebeneinander. Wer sie dividiert — und genau das
   tat der Melder —, kommt NICHT auf den Ø-Preis darüber, weil die Kosten den
   Grundpreis enthalten: 559 kWh · 210,45 € ⇒ 37,6 ct statt 33 ct. Dafür gibt
   es jetzt `netzbezug_arbeitspreis_kosten_euro` (reiner Ausweis).

2. Beim Nachprüfen fiel auf: der laufende Monat rechnete Geld mit dem
   TARIF-Arbeitspreis, auch wenn ein flexibler Tarif einen abweichenden
   Monatsdurchschnitt trug. Ein Kommentar versprach die Überschreibung
   („Platzhalter für spätere Überschreibung"), gebaut war sie nie — während
   der Vorjahres-Pfad und die per-Investition-Details den Durchschnitt längst
   nahmen. Derselbe Monat trug damit je nach Sicht zwei Beträge.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

JAHR, MONAT = 2026, 4

# Algies Fall, rückgerechnet: 559 × 33 ct = 184,47 € + 25,98 € Grundpreis
# = 210,45 €, und 210,45 / 559 = 37,6 ct — exakt die gemeldete Diskrepanz.
ALGIE_KWH = 559.0
ALGIE_CENT = 33.0
ALGIE_GRUNDPREIS = 25.98
ALGIE_GESAMT = 210.45
ALGIE_ARBEITSPREIS = 184.47


async def _seed(db: AsyncSession, *, netzbezug: float, grundpreis: float,
                arbeitspreis_cent: float = ALGIE_CENT,
                durchschnittspreis: float | None = None,
                eigenverbrauch_md: float | None = None) -> Anlage:
    anlage = Anlage(anlagenname="Ø-Preis", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=arbeitspreis_cent,
        einspeiseverguetung_cent_kwh=8.0,
        grundpreis_euro_monat=grundpreis,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=JAHR, monat=MONAT,
        netzbezug_kwh=netzbezug, einspeisung_kwh=0.0,
        netzbezug_durchschnittspreis_cent=durchschnittspreis,
    ))
    await db.commit()
    return anlage


# ── 1. Die Kachel geht auf ──────────────────────────────────────────────────

async def test_arbeitspreis_kosten_dividieren_auf_den_oe_preis(db):
    """Der gemeldete Fall: kWh und € der Unterzeile ergeben den Ø-Preis."""
    anlage = await _seed(db, netzbezug=ALGIE_KWH, grundpreis=ALGIE_GRUNDPREIS)
    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)

    assert res.netzbezug_kosten_euro == pytest.approx(ALGIE_GESAMT)
    assert res.netzbezug_arbeitspreis_kosten_euro == pytest.approx(ALGIE_ARBEITSPREIS)
    # Das ist die Division, die der Melder gemacht hat — jetzt kommt der
    # Kopfwert der Kachel heraus statt 37,6 ct.
    assert (res.netzbezug_arbeitspreis_kosten_euro / res.netzbezug_kwh * 100
            == pytest.approx(ALGIE_CENT, abs=0.05))
    # Gegenprobe: mit den Gesamtkosten ginge es weiterhin schief.
    assert res.netzbezug_kosten_euro / res.netzbezug_kwh * 100 == pytest.approx(37.6, abs=0.05)


async def test_beide_wege_stimmen_ueberein(db):
    """kWh × Preis == Gesamtkosten − Grundgebühr (bis auf Rundung)."""
    anlage = await _seed(db, netzbezug=ALGIE_KWH, grundpreis=ALGIE_GRUNDPREIS)
    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)

    assert res.netzbezug_arbeitspreis_kosten_euro == pytest.approx(
        ALGIE_KWH * ALGIE_CENT / 100, abs=0.01)
    assert res.netzbezug_arbeitspreis_kosten_euro == pytest.approx(
        res.netzbezug_kosten_euro - res.grundgebuehr_euro, abs=0.01)


async def test_ohne_grundpreis_sind_beide_felder_gleich(db):
    anlage = await _seed(db, netzbezug=ALGIE_KWH, grundpreis=0.0)
    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)

    assert res.netzbezug_arbeitspreis_kosten_euro == pytest.approx(res.netzbezug_kosten_euro)


async def test_grundpreis_ohne_netzbezug_zeigt_null_statt_leer(db):
    """Kein Bezug, aber Grundpreis gepflegt: Arbeitspreis-Anteil ist 0 —
    nicht None. Die Kachel darf hier nicht plötzlich „—" zeigen."""
    anlage = await _seed(db, netzbezug=0.0, grundpreis=ALGIE_GRUNDPREIS)
    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)

    assert res.netzbezug_arbeitspreis_kosten_euro == pytest.approx(0.0)
    assert res.netzbezug_kosten_euro == pytest.approx(ALGIE_GRUNDPREIS)


# ── 2. Flexibler Tarif: Geld folgt dem Monatsdurchschnitt ───────────────────

async def test_dynamischer_tarif_schlaegt_auf_die_kosten_durch(db):
    """Der Monatsdurchschnitt (28 ct) gilt, nicht der Tarif-Arbeitspreis (33 ct).

    Vor dem Fix rechnete der laufende Monat hier mit 33 ct, während die Kachel
    28 ct anzeigte — die Unterzeile konnte gar nicht aufgehen.
    """
    anlage = await _seed(db, netzbezug=ALGIE_KWH, grundpreis=ALGIE_GRUNDPREIS,
                         durchschnittspreis=28.0)
    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)

    assert res.netzbezug_durchschnittspreis_cent == pytest.approx(28.0)
    # `netzbezug_preis_cent` bleibt daneben der ausgelieferte TARIF-Wert.
    assert res.netzbezug_preis_cent == pytest.approx(ALGIE_CENT)

    assert res.netzbezug_arbeitspreis_kosten_euro == pytest.approx(
        ALGIE_KWH * 28.0 / 100, abs=0.01)
    assert res.netzbezug_kosten_euro == pytest.approx(
        ALGIE_KWH * 28.0 / 100 + ALGIE_GRUNDPREIS, abs=0.01)
    # Und die Kachel-Division geht auch hier auf.
    assert (res.netzbezug_arbeitspreis_kosten_euro / res.netzbezug_kwh * 100
            == pytest.approx(28.0, abs=0.05))


async def test_dynamischer_tarif_gilt_auch_fuer_ev_ersparnis(db):
    """Die EV-Ersparnis hing an derselben nie gebauten Überschreibung.

    Ohne sie bewertete der laufende Monat den Eigenverbrauch mit 33 ct,
    während der Vorjahres-Pfad (`_load_vorjahr`) 28 ct nahm — ein Δ, das
    ausschließlich aus der Sicht kam, nicht aus den Daten.
    """
    anlage = Anlage(anlagenname="Ø-Preis-EV", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=ALGIE_CENT, einspeiseverguetung_cent_kwh=8.0,
        grundpreis_euro_monat=0.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=JAHR, monat=MONAT,
        netzbezug_kwh=100.0, einspeisung_kwh=300.0,
        netzbezug_durchschnittspreis_cent=28.0,
    ))
    # Eigenverbrauch entsteht aus der Bilanz: 500 PV − 300 Einspeisung = 200.
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=JAHR, monat=MONAT,
                                  verbrauch_daten={"pv_erzeugung_kwh": 500.0}))
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    # Ohne echten Eigenverbrauch prüfte dieser Test nichts — deshalb erst
    # festnageln, dass die Bilanz überhaupt welchen ausweist.
    assert res.eigenverbrauch_kwh == pytest.approx(200.0)
    assert res.ev_ersparnis_euro == pytest.approx(200.0 * 28.0 / 100, abs=0.02)
    # Der Tarifpreis (33 ct) hätte 66 € ergeben — das war der alte Wert.
    assert res.ev_ersparnis_euro != pytest.approx(200.0 * ALGIE_CENT / 100, abs=0.02)


async def test_monats_durchschnitt_von_null_ct_gilt_auch(db):
    """Ø = 0,0 ct ist bei dynamischem Tarif real, nicht „kein Wert".

    Ein Monat mit vielen Negativpreis-Stunden kann rechnerisch bei 0 landen.
    Mit `durchschnitt or tarif` wäre die 0 als falsy durchgefallen und der
    Monat hätte still mit 33 ct gerechnet — die 0-Werte-Falle. Deshalb löst
    der SoT-Helper `resolve_netzbezug_preis_cent` (`is not None`) auf.
    """
    anlage = await _seed(db, netzbezug=ALGIE_KWH, grundpreis=ALGIE_GRUNDPREIS,
                         durchschnittspreis=0.0)
    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)

    assert res.netzbezug_arbeitspreis_kosten_euro == pytest.approx(0.0)
    # Nur der Grundpreis bleibt — nicht 559 × 33 ct.
    assert res.netzbezug_kosten_euro == pytest.approx(ALGIE_GRUNDPREIS)


# ── 3. Vorjahr trägt dasselbe Feld ──────────────────────────────────────────

async def test_vorjahr_traegt_arbeitspreis_kosten(db):
    """Symmetrie: die Jahres-Summe addiert Monat für Monat — fehlte das Feld
    im Vorjahres-Block, klaffte die Sicht auseinander."""
    anlage = Anlage(anlagenname="Ø-Preis-VJ", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2020, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=ALGIE_CENT, einspeiseverguetung_cent_kwh=8.0,
        grundpreis_euro_monat=ALGIE_GRUNDPREIS,
    ))
    for j in (JAHR - 1, JAHR):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=j, monat=MONAT,
                           netzbezug_kwh=ALGIE_KWH, einspeisung_kwh=0.0))
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert res.vorjahr is not None
    vj = res.vorjahr
    assert vj["netzbezug_arbeitspreis_kosten_euro"] == pytest.approx(ALGIE_ARBEITSPREIS)
    assert (vj["netzbezug_arbeitspreis_kosten_euro"]
            == pytest.approx(vj["netzbezug_kosten_euro"] - ALGIE_GRUNDPREIS, abs=0.01))
