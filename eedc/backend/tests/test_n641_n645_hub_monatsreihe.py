"""N-641 … N-645 — Hub-Verläufe von Speicher, Wärmepumpe (samt Aussicht) und Sonstiges lesen die bewertete Monatsreihe.

Bauform N-638 (Balkonkraftwerk): Die Komponenten-Route liefert je Gerät ein Feld ``monatsreihe`` aus DERSELBEN Rechnung
wie ihre Kopfzahlen; der Frontend-Verlauf liest es statt ``monatsdaten[].verbrauch_daten``. Bis 4.1.3 lasen die
Verläufe die Rohfelder:

* **N-641** Speicher — Vollzyklen je Monat = Ladung ÷ Kapazität; Kopf und Layer nehmen die Entladung.
* **N-642** Speicher — Netzladung aus dem Legacy-Schlüssel ``speicher_ladung_netz_kwh``; die Zeile trägt den Kanon.
* **N-643/N-644** Wärmepumpe und Aussicht — ``heizenergie_kwh``/``warmwasser_kwh``/``stromverbrauch_kwh`` roh: ein
  gemeinsamer Wärmezähler, Betriebsart-Nutzenergie und getrennte Strommessung standen als 0 da.
* **N-645** Sonstiges — Vergleich aus dem Legacy-Zwilling ``verbrauch_kwh``; ein Verbraucher ohne PV-/Netz-Messung
  hatte im Verlauf gar kein Segment (Fachentscheid Master 09.10.: ein Segment „nicht aufgeteilt").

Die Abnahme-Matrix prüft dieselben Sichten über ihre Formen (``test_achsen_matrix.py``, Größen ``hub_*``); hier
stehen die Fälle als einzelne Proben mit Σ Reihe = Kopf, dazu, was die Matrix nicht sät (Legacy-Schlüssel der
Netzladung, Speicher ohne Kapazität, Verbraucher mit Teilmessung, Erzeuger ohne Reihe).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.dashboard_sonstiges import get_sonstiges_dashboard
from backend.api.routes.investitionen.dashboard_speicher import get_speicher_dashboard
from backend.api.routes.investitionen.dashboard_waermepumpe import get_waermepumpe_dashboard
from backend.models import Anlage, Investition, Strompreis
from backend.models.investition import InvestitionMonatsdaten

ANSCHAFFUNG = date(2024, 1, 1)


async def _anlage(db, name: str) -> Anlage:
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, gueltig_ab=date(2023, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=0.0))
    return anlage


async def _inv(db, anlage, typ: str, name: str, **parameter) -> Investition:
    inv = Investition(anlage_id=anlage.id, typ=typ, bezeichnung=name, anschaffungsdatum=ANSCHAFFUNG,
                      anschaffungskosten_gesamt=1000.0, parameter=parameter or None)
    db.add(inv)
    await db.flush()
    return inv


def _zeile(inv, monat: int, **vd) -> InvestitionMonatsdaten:
    return InvestitionMonatsdaten(investition_id=inv.id, jahr=2026, monat=monat, verbrauch_daten=vd)


# ── Speicher (N-641, N-642) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_n641_vollzyklen_je_monat_aus_der_entladung_summe_gleich_kopf(db):
    """M02-Lage: Ladung 90, Entladung 60, 10 kWh — der Verlauf las 9,0 je Monat (Ladung), der Kopf 6,0 (Entladung).
    Jetzt trägt die Reihe den Layer-Wert ``berechne_vollzyklen`` je Monat, und Σ Monate = Kopf."""
    anlage = await _anlage(db, "Zyklen")
    akku = await _inv(db, anlage, "speicher", "Akku", kapazitaet_kwh=10.0)
    db.add(_zeile(akku, 6, ladung_kwh=90.0, entladung_kwh=60.0))
    db.add(_zeile(akku, 7, ladung_kwh=50.0, entladung_kwh=40.0))
    await db.commit()

    (karte,) = await get_speicher_dashboard(anlage_id=anlage.id, strompreis_cent=None,
                                            einspeiseverguetung_cent=None, db=db)
    assert [(m.monat, m.vollzyklen) for m in karte.monatsreihe] == [(6, pytest.approx(6.0)), (7, pytest.approx(4.0))]
    assert round(sum(m.vollzyklen for m in karte.monatsreihe), 1) == karte.zusammenfassung["vollzyklen"] == 10.0
    assert round(sum(m.ladung_kwh for m in karte.monatsreihe), 1) == karte.zusammenfassung["gesamt_ladung_kwh"]
    assert round(sum(m.entladung_kwh for m in karte.monatsreihe), 1) == karte.zusammenfassung["gesamt_entladung_kwh"]


@pytest.mark.asyncio
async def test_n641_ohne_kapazitaet_keine_zyklenzahl_wie_der_kopf(db):
    """N127 je Monat: ohne gepflegte Kapazität gibt es keine Zyklenzahl — ``None`` wie im Kopf, nicht 0 und nicht
    eine erfundene 10-kWh-Basis. Ein Monat ohne Entladung bei gepflegter Kapazität ist 0 (wie der Kopf ``or 0``)."""
    anlage = await _anlage(db, "ohne Kapazität")
    ohne = await _inv(db, anlage, "speicher", "ohne")
    mit = await _inv(db, anlage, "speicher", "mit", kapazitaet_kwh=5.0)
    db.add(_zeile(ohne, 6, ladung_kwh=30.0, entladung_kwh=20.0))
    db.add(_zeile(mit, 6, ladung_kwh=10.0, entladung_kwh=0.0))
    await db.commit()

    karten = {k.investition.bezeichnung: k for k in await get_speicher_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, einspeiseverguetung_cent=None, db=db)}
    assert karten["ohne"].zusammenfassung["vollzyklen"] is None
    assert [m.vollzyklen for m in karten["ohne"].monatsreihe] == [None]
    assert [m.vollzyklen for m in karten["mit"].monatsreihe] == [0.0]


@pytest.mark.asyncio
async def test_n642_netzladung_ueber_die_lesetuer_kanon_und_legacy(db):
    """M04-Lage: die Zeile trägt den Kanon ``ladung_netz_kwh`` (30) — der Verlauf las den Legacy-Schlüssel (0) und
    zeigte 120 als PV-Ladung. Jetzt die Lesetür ``get_speicher_netzladung_kwh``: Kanon zuerst, Legacy als Rückfall;
    PV-Ladung = Ladung − Netzladung. Σ Netzladung = Kopf ``arbitrage_kwh``."""
    anlage = await _anlage(db, "Netzladung")
    akku = await _inv(db, anlage, "speicher", "Akku A", kapazitaet_kwh=10.0)
    db.add(_zeile(akku, 6, ladung_kwh=120.0, entladung_kwh=60.0, ladung_netz_kwh=30.0))
    db.add(_zeile(akku, 7, ladung_kwh=40.0, entladung_kwh=30.0, speicher_ladung_netz_kwh=10.0))
    await db.commit()

    (karte,) = await get_speicher_dashboard(anlage_id=anlage.id, strompreis_cent=None,
                                            einspeiseverguetung_cent=None, db=db)
    juni, juli = karte.monatsreihe
    assert (juni.netzladung_kwh, juni.pv_ladung_kwh) == (30.0, 90.0)
    assert (juli.netzladung_kwh, juli.pv_ladung_kwh) == (10.0, 30.0)
    assert round(sum(m.netzladung_kwh for m in karte.monatsreihe), 1) == karte.zusammenfassung["arbitrage_kwh"] == 40.0


# ── Wärmepumpe (N-643, N-644) ───────────────────────────────────────────────


async def _wp_karten(db, anlage) -> dict:
    return {k.investition.bezeichnung: k for k in await get_waermepumpe_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, db=db)}


def _wp_summen_wie_kopf(karte) -> None:
    z, r = karte.zusammenfassung, karte.monatsreihe
    assert round(sum(m.strom_kwh for m in r), 1) == z["gesamt_stromverbrauch_kwh"]
    assert round(sum(m.heizung_kwh for m in r), 1) == z["gesamt_heizenergie_kwh"]
    assert round(sum(m.warmwasser_kwh for m in r), 1) == z["gesamt_warmwasser_kwh"]
    assert round(sum(m.waerme_kwh for m in r), 1) == z["gesamt_waerme_kwh"]


@pytest.mark.asyncio
async def test_n643_gemeinsamer_waermezaehler_traegt_die_gesamtwaerme(db):
    """W1 (M05): Gesamtstrom + EIN Wärmezähler ``waerme_kwh`` — keine Heiz-/Warmwasser-Achse. Der Verlauf las
    ``heizenergie_kwh`` (0), der Kopf nennt 648. Die Reihe trägt die Gesamtwärme (D1: Gesamtwert vor Summanden),
    Heizwärme und Warmwasser bleiben 0 wie im Kopf — die Wärme hat keine dritte Achse (Konzept Wärme/Klima §3)."""
    anlage = await _anlage(db, "W1")
    wp = await _inv(db, anlage, "waermepumpe", "WP", alter_energietraeger="gas", alter_preis_cent_kwh=10.0)
    db.add(_zeile(wp, 6, stromverbrauch_kwh=216.0, waerme_kwh=648.0))
    await db.commit()

    karte = (await _wp_karten(db, anlage))["WP"]
    (m,) = karte.monatsreihe
    assert (m.strom_kwh, m.heizung_kwh, m.warmwasser_kwh, m.waerme_kwh) == (216.0, 0.0, 0.0, 648.0)
    assert karte.zusammenfassung["hat_warmwasser_achse"] is False
    _wp_summen_wie_kopf(karte)


@pytest.mark.asyncio
async def test_n643_betriebsart_nutzenergie_und_getrennte_strommessung(db):
    """M06: ein Klimagerät mit Betriebsart-Zählern (Heizwärme aus ``betriebsart_nutzenergie_heizen_kwh``, N-398) und
    eine Wärmepumpe mit getrennter Strommessung (die Rohspalte ``stromverbrauch_kwh`` ist leer). Der Verlauf las
    Heizung 0 bzw. die Aussicht Strom 0; die Reihe nennt die Werte der Lesetüren."""
    anlage = await _anlage(db, "M06")
    hw = await _inv(db, anlage, "waermepumpe", "WP HW", alter_energietraeger="gas", alter_preis_cent_kwh=10.0,
                    getrennte_strommessung=True)
    klima = await _inv(db, anlage, "waermepumpe", "Klima", wp_art="luft_luft", alter_energietraeger="strom",
                       alter_preis_cent_kwh=30.0)
    db.add(_zeile(hw, 6, strom_heizen_kwh=180.0, strom_warmwasser_kwh=36.0, heizenergie_kwh=540.0,
                  warmwasser_kwh=108.0))
    db.add(_zeile(klima, 6, betriebsart_strom_heizen_kwh=18.0, betriebsart_strom_kuehlen_kwh=36.0,
                  betriebsart_nutzenergie_heizen_kwh=54.0, betriebsart_nutzenergie_kuehlen_kwh=108.0))
    await db.commit()

    karten = await _wp_karten(db, anlage)
    (m_hw,) = karten["WP HW"].monatsreihe
    assert (m_hw.strom_kwh, m_hw.heizung_kwh, m_hw.warmwasser_kwh, m_hw.waerme_kwh) == (216.0, 540.0, 108.0, 648.0)
    (m_kl,) = karten["Klima"].monatsreihe
    assert (m_kl.strom_kwh, m_kl.heizung_kwh, m_kl.waerme_kwh) == (54.0, 54.0, 54.0)
    for karte in karten.values():
        _wp_summen_wie_kopf(karte)


# ── Sonstiges (N-645) ───────────────────────────────────────────────────────


async def _sonst_karten(db, anlage) -> dict:
    return {k.investition.bezeichnung: k for k in await get_sonstiges_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, einspeiseverguetung_cent=None, db=db)}


@pytest.mark.asyncio
async def test_n645_verbrauch_ueber_die_lesetuer_und_segment_nicht_aufgeteilt(db):
    """M07 Pool (Alt- UND Neuname: 72 Kanon, 108 Legacy) und M10 Sauna (nur Kanon 24): der Vergleich las den
    Legacy-Zwilling (108 bzw. 0). Ohne PV-/Netz-Messung trägt die Reihe den ganzen Verbrauch als „nicht aufgeteilt"
    (Fachentscheid Master 09.10.) — Σ PV + Netz + nicht aufgeteilt = Kopf ``gesamt_verbrauch_kwh``."""
    anlage = await _anlage(db, "Verbraucher")
    pool = await _inv(db, anlage, "sonstiges", "Pool", kategorie="verbraucher")
    sauna = await _inv(db, anlage, "sonstiges", "Sauna", kategorie="verbraucher")
    db.add(_zeile(pool, 6, verbrauch_sonstig_kwh=72.0, verbrauch_kwh=108.0))
    db.add(_zeile(sauna, 6, verbrauch_sonstig_kwh=24.0))
    await db.commit()

    karten = await _sonst_karten(db, anlage)
    for name, menge in (("Pool", 72.0), ("Sauna", 24.0)):
        karte = karten[name]
        (m,) = karte.monatsreihe
        assert (m.verbrauch_kwh, m.bezug_pv_kwh, m.bezug_netz_kwh, m.nicht_aufgeteilt_kwh) == (menge, 0.0, 0.0, menge)
        assert m.verbrauch_kwh == karte.zusammenfassung["gesamt_verbrauch_kwh"]


@pytest.mark.asyncio
async def test_n645_teilweise_gemessen_rest_ist_nicht_aufgeteilt_nie_negativ(db):
    """Mit PV-/Netz-Messung ist „nicht aufgeteilt" der Rest Verbrauch − PV − Netz, nie < 0 (K5-Bauform: die
    Aufteilung steht neben der Gesamtmenge, nie über ihr)."""
    anlage = await _anlage(db, "Teilmessung")
    wb = await _inv(db, anlage, "sonstiges", "Werkstatt", kategorie="verbraucher")
    db.add(_zeile(wb, 6, verbrauch_sonstig_kwh=100.0, bezug_pv_kwh=30.0, bezug_netz_kwh=50.0))
    db.add(_zeile(wb, 7, verbrauch_sonstig_kwh=40.0, bezug_pv_kwh=30.0, bezug_netz_kwh=20.0))
    await db.commit()

    karte = (await _sonst_karten(db, anlage))["Werkstatt"]
    assert [(m.monat, m.nicht_aufgeteilt_kwh) for m in karte.monatsreihe] == [(6, 20.0), (7, 0.0)]
    z = karte.zusammenfassung
    assert round(sum(m.verbrauch_kwh for m in karte.monatsreihe), 1) == z["gesamt_verbrauch_kwh"]
    assert round(sum(m.bezug_pv_kwh for m in karte.monatsreihe), 1) == z["bezug_pv_kwh"]
    assert round(sum(m.bezug_netz_kwh for m in karte.monatsreihe), 1) == z["bezug_netz_kwh"]


@pytest.mark.asyncio
async def test_n645_nur_der_verbraucher_traegt_eine_reihe(db):
    """Erzeuger, Speicher und Zähler unter *Sonstiges* lesen ihren Verlauf weiter aus den Monatszeilen (dort ist
    Kopf = Rohfeld, keine rote Zelle) — ihre Reihe bleibt leer statt eine zweite Lesart anzubieten."""
    anlage = await _anlage(db, "Erzeuger")
    bhkw = await _inv(db, anlage, "sonstiges", "BHKW", kategorie="erzeuger")
    db.add(_zeile(bhkw, 6, erzeugung_kwh=180.0))
    await db.commit()

    karte = (await _sonst_karten(db, anlage))["BHKW"]
    assert karte.monatsreihe == []
    assert karte.zusammenfassung["gesamt_erzeugung_kwh"] == 180.0
