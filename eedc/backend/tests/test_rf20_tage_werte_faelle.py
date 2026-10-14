"""RF-20 — vier Weichen von ``baue_tage_werte``, die weder die übrige Suite noch die Golden-Master-Bestände unterscheiden.

Der Schnitt von ``baue_tage_werte`` (RF-20, Serie „Funktion vor Datei", 14.10.2026) ist ein reiner Umzug in derselben Datei:
der Orchestrator lädt, je Tag baut ``_tageszeile`` die Zeile aus ``_tagesbilanz``, ``_abgabe_und_quoten``, ``_geld_spalten``,
``_energie_spalten`` und ``_tagnative_spalten``. Gemessen in der Gegenprobe der Vorlage RF-20 (13.10.2026): die Sprengsätze
S17, S20, S21 und S22 ändern dort keine einzige Antwort der aufrufenden Tests und der DB-Kopien. Jeder Fall unten baut genau
den Bestand, an dem die Weiche eine andere Zahl liefert:

* **F1** — Tages-Vollzyklen zählen nur den Speicher, der an dem Tag lief (``ist_aktiv_an``, S17).
* **F2** — die Netto-Bilanz erbt die Lücke des Netzbezugs, auch wenn der Netto-Ertrag feststeht (S20).
* **F3** — die V2H-Spalte bleibt ohne Regelmarke (Altbestand) leer, auch mit ``v2h_<id>`` im Rollup (S21).
* **F4** — eine gespeicherte Performance Ratio ohne erfasste PV des Tages ist keine Aussage (S22).

Schwesterdateien: test_tage_werte_symmetrie.py (Tag ↔ Monat derselben Funktion; Vollzyklen und Netto-Bilanz je Tag),
test_v2h_tageswert.py (#110 V2H-Tageswert mit Regelmarke und am Kanal-Tag), test_speicher_zyklen_kapazitaets_basis.py
(Vollzyklen-Definition), test_a6_performance_ratio_tage.py (PR der Tage im Monat), test_rf19_stammdaten_investitionen_faelle.py
(dieselbe Fall-Probe für den Investitions-Check).
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Strompreis
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil.tage_werte import baue_tage_werte

TAG = date(2026, 5, 10)


async def _anlage(db, name: str) -> Anlage:
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    return anlage


@pytest.mark.asyncio
async def test_f1_vollzyklen_zaehlen_nur_den_speicher_der_an_dem_tag_lief(db):
    """S17: ein zweiter Speicher, erst 2027 angeschafft, gehört nicht in den Nenner der Tages-Vollzyklen."""
    anlage = await _anlage(db, "RF20-F1")
    for bez, ab in (("Alt", date(2024, 1, 1)), ("Neu", date(2027, 1, 1))):
        db.add(Investition(anlage_id=anlage.id, typ="speicher", bezeichnung=bez, anschaffungsdatum=ab,
                           parameter={"kapazitaet_kwh": 10.0, "nutzbare_kapazitaet_kwh": 10.0}))
    db.add_all([
        TagesEnergieProfil(anlage_id=anlage.id, datum=TAG, stunde=h, pv_kw=0.0, verbrauch_kw=3.0,
                           einspeisung_kw=0.0, netzbezug_kw=0.0, batterie_kw=3.0)
        for h in (18, 19)
    ])
    await db.flush()

    (zeile,) = await baue_tage_werte(db, anlage, TAG, TAG)

    assert zeile.speicher_entladung == pytest.approx(6.0)
    assert zeile.speicher_vollzyklen == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_f2_netto_bilanz_erbt_die_luecke_des_netzbezugs(db):
    """S20: ohne erfassten Netzbezug gibt es keine Netzbezugskosten — und damit keine Netto-Bilanz, auch wenn der
    Netto-Ertrag feststeht."""
    anlage = await _anlage(db, "RF20-F2")
    db.add(Strompreis(anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    db.add_all([
        TagesEnergieProfil(anlage_id=anlage.id, datum=TAG, stunde=h, pv_kw=4.0, verbrauch_kw=1.0,
                           einspeisung_kw=3.0, netzbezug_kw=None)
        for h in (11, 12)
    ])
    await db.flush()

    (zeile,) = await baue_tage_werte(db, anlage, TAG, TAG)

    assert zeile.netzbezug is None and zeile.netzbezug_kosten is None
    assert zeile.netto_ertrag is not None
    assert zeile.netto_bilanz is None


@pytest.mark.asyncio
async def test_f3_v2h_spalte_bleibt_leer_ohne_regelmarke(db):
    """S21: Altbestand (Tageszeile ohne `verworfen`) rechnet die Bilanz ohne V2H — die Spalte zeigt dann auch keinen
    V2H-Wert, selbst wenn der Rollup einen `v2h_<id>`-Schlüssel trägt."""
    anlage = await _anlage(db, "RF20-F3")
    db.add_all([
        TagesEnergieProfil(anlage_id=anlage.id, datum=TAG, stunde=h, pv_kw=2.0, verbrauch_kw=3.0,
                           einspeisung_kw=0.0, netzbezug_kw=1.0)
        for h in (10, 11)
    ])
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=TAG, verworfen=None,
                                komponenten_kwh={"v2h_5": 2.0}))
    await db.flush()

    (zeile,) = await baue_tage_werte(db, anlage, TAG, TAG)

    assert zeile.v2h_entladung is None


@pytest.mark.asyncio
async def test_f4_performance_ratio_braucht_erfasste_pv(db):
    """S22: eine gespeicherte PR ohne PV-Messung des Tages ist keine Aussage."""
    anlage = await _anlage(db, "RF20-F4")
    db.add_all([
        TagesEnergieProfil(anlage_id=anlage.id, datum=TAG, stunde=h, pv_kw=None, verbrauch_kw=1.0,
                           einspeisung_kw=0.0, netzbezug_kw=1.0)
        for h in (10, 11)
    ])
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=TAG, performance_ratio=0.8))
    await db.flush()

    (zeile,) = await baue_tage_werte(db, anlage, TAG, TAG)

    assert zeile.erzeugung is None
    assert zeile.performance_ratio is None
