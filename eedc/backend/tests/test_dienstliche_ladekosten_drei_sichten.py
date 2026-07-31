"""Dienstliche Ladekosten — eine Formel für Cockpit, Aussichten und HA-Export.

Paket **A** der Nebenfunde-Runde (N-12 · N-13 · N-18, Entscheid Gernot
2026-07-31). Drei Sichten bewerteten dieselbe Ausgabe verschieden:

- **N-18 — die Dienstwagen-PV wurde doppelt gutgeschrieben.**
  ``berechne_finanz_aggregat`` schreibt ``ev_ersparnis = Eigenverbrauch ×
  netzbezug_preis_cent`` gut, und der Eigenverbrauch ändert sich durch das
  Dienstwagen-Flag **nicht** — die weggefahrenen kWh galten als „eingesparter
  Netzbezug" (30 ct), während der Abzug nur die Einspeisevergütung (8 ct) ansetzte.
  Netto **+22 ct je verschenkter kWh**. Seit dem Entscheid bewertet der Abzug den
  PV-Anteil mit dem **Netzbezugspreis** und nimmt die Gutschrift damit zurück.
  Die entgangene Einspeisevergütung braucht keinen Buchungssatz: sie steckt
  bereits in der niedrigeren **gemessenen** Einspeisung.
- **N-12 — zwei Tarife für dieselbe Netzladung.** Cockpit nahm den effektiven
  Wallbox-Preis, ``aussichten.get_finanz_prognose`` den allgemeinen Arbeitspreis.
  Kanon ist das Cockpit: WB-Stromvertrag, wenn vorhanden, sonst Anlagentarif.
- **N-13 — der HA-Export zog gar nichts ab.** Sein Sensor ``netto_ertrag_euro``
  stand bei Dienstwagen-Anlagen über der Cockpit-Kachel, auf die er sich bezieht.

Die Formel lebt seither in ``core/berechnungen/dienstliche_ladekosten.py``
(ADR-001, Pflicht 1); der baumweite Wächter ist
``test_berechnungs_layer_konformitaet.py::test_dienstliche_ladung_nur_im_layer_bewertet``.

**Die Energiebilanz bleibt unangetastet** — das ist Teil des Entscheids und wird
hier mitgeprüft (``test_energiebilanz_bleibt_unberuehrt_vom_dienstwagen_abzug``):
energetisch IST die Ladung Eigenverbrauch hinter dem Zähler, korrigiert wird
ausschließlich die Bewertung.

Rot-Beweis, aufgeschlüsselt (gegen ``HEAD~1``, Helper hineinkopiert)
--------------------------------------------------------------------
**6 der 11 Tests fallen dort** — sie sind der Beweis:
``…vier_faelle[True-152.0]`` · ``…liegt_zwischen_privatwagen_und_gar_keinem_auto`` ·
``…cockpit_zieht_wallbox_tarif…`` · ``…aussichten_folgen_dem_cockpit…`` ·
``…ha_export_zieht_die_dienstlichen_ladekosten_ab``, dazu der Wächter
``test_dienstliche_ladung_nur_im_layer_bewertet``.

**Die übrigen 5 werden NICHT als Beweis mitgezählt** und stehen hier benannt,
statt in der Summe zu verschwinden:

- die **drei Layer-Einheitstests** prüfen neuen Code — sie *können* gegen
  ``HEAD~1`` nicht rot sein, weil das Modul dort nicht existiert;
- ``…vier_faelle[None-…]`` und ``[False-…]`` (kein Auto · Privatwagen) waren
  vorher grün und sollen es bleiben: sie belegen, dass Anlagen **ohne**
  Dienstwagen unberührt sind;
- ``…energiebilanz_bleibt_unberuehrt…`` war konstruktionsbedingt grün — die
  Bilanz hat sich nie bewegt. Genau deshalb steht der Test hier: er ist
  **Regressions-Schutz** gegen eine „Mitkorrektur", die den Entscheid
  missverstünde, kein Fix-Beweis.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.ha_export import calculate_anlage_sensors
from backend.core.berechnungen import (
    DienstlicheLadungZeile,
    berechne_dienstliche_ladekosten,
)
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

ANSCHAFFUNG = date(2024, 1, 1)


def _sensor(werte, key: str):
    """Ein Sensorwert aus der HA-Export-Liste — mit lesbarer Meldung, wenn er fehlt."""
    treffer = [w for w in werte if w.definition.key == key]
    assert treffer, (
        f"kein Sensor `{key}` — vorhanden: {sorted(w.definition.key for w in werte)}"
    )
    return treffer[0].value


# ═══════════════════════════════════════════════════════════════════════
# Der Layer-Helper selbst
# ═══════════════════════════════════════════════════════════════════════


def test_layer_bewertet_pv_zum_netzbezugspreis_und_netz_zum_wallbox_preis():
    """Die beiden Anteile hängen an **verschiedenen** Preisen.

    Das ist der ganze Inhalt von N-18 + N-12 in einer Zeile: PV-Anteil ×
    Netzbezugspreis (Rücknahme der EV-Gutschrift), Netzanteil × Wallbox-Preis
    (was der Strom gekostet hat).
    """
    kosten = berechne_dienstliche_ladekosten([
        DienstlicheLadungZeile(
            ladung_pv_kwh=200.0, ladung_netz_kwh=100.0,
            netzbezug_preis_cent=30.0, wallbox_preis_cent=20.0,
        ),
    ])

    assert kosten.pv_anteil_euro == pytest.approx(60.0)   # 200 × 30 ct
    assert kosten.netz_anteil_euro == pytest.approx(20.0)  # 100 × 20 ct
    assert kosten.gesamt_euro == pytest.approx(80.0)
    assert kosten.pv_kwh == pytest.approx(200.0)
    assert kosten.netz_kwh == pytest.approx(100.0)

    # Gegenprobe zur alten Buchung: PV zur Einspeisevergütung (8 ct) wären
    # 16 € statt 60 € — genau die 44 € Phantomgewinn aus der Messung.
    assert kosten.pv_anteil_euro - 16.0 == pytest.approx(44.0)


def test_layer_summiert_per_monat_mit_dem_tarif_des_monats():
    """Zwei Monate, zwei Preise — die Summe darf kein Ø-Preis sein (P8)."""
    kosten = berechne_dienstliche_ladekosten([
        DienstlicheLadungZeile(ladung_pv_kwh=100.0, netzbezug_preis_cent=20.0),
        DienstlicheLadungZeile(ladung_pv_kwh=100.0, netzbezug_preis_cent=40.0),
    ])
    assert kosten.gesamt_euro == pytest.approx(60.0)  # 20 + 40, nicht 200 × 30 ct


def test_layer_ohne_dienstwagen_ist_null():
    """Leere Eingabe → kein Posten (jede Anlage ohne Dienstwagen)."""
    assert berechne_dienstliche_ladekosten([]).gesamt_euro == pytest.approx(0.0)


# ═══════════════════════════════════════════════════════════════════════
# N-18 — die gemessene Vier-Fälle-Tabelle
# ═══════════════════════════════════════════════════════════════════════


async def _basis(db, name: str) -> Anlage:
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
        grundpreis_euro_monat=0.0,
    ))
    return anlage


async def _anlage_mit_wagen(db, name: str, *, dienstlich: bool | None) -> int:
    """Die Fixture der Messung: PV 1.000 · Bezug 100 · 30/8 ct.

    ``dienstlich=None`` = **gar kein Auto**; dann sind die 200 kWh eingespeist
    worden (Einspeisung 600 statt 400) — das ist die ehrliche Vergleichsbasis,
    denn ohne Wagen wäre der Strom ins Netz gegangen.
    """
    anlage = await _basis(db, name)
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=ANSCHAFFUNG,
                     anschaffungskosten_gesamt=10000.0)
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=600.0 if dienstlich is None else 400.0,
                       netzbezug_kwh=100.0))

    if dienstlich is not None:
        wagen = Investition(
            anlage_id=anlage.id, typ="e-auto",
            bezeichnung="Firmenwagen" if dienstlich else "Privatwagen",
            anschaffungsdatum=ANSCHAFFUNG,
            parameter={"ist_dienstlich": True} if dienstlich else {},
        )
        db.add(wagen)
        await db.flush()
        db.add(InvestitionMonatsdaten(
            investition_id=wagen.id, jahr=2026, monat=6,
            verbrauch_daten={"ladung_kwh": 200.0, "ladung_pv_kwh": 200.0,
                             "ladung_netz_kwh": 0.0},
        ))

    await db.commit()
    return anlage.id


@pytest.mark.parametrize("dienstlich, erwartet", [
    (None, 168.0),    # gar kein Auto:  EV 400 × 30 ct + 600 × 8 ct
    (False, 212.0),   # Privatwagen:    EV 600 × 30 ct + 400 × 8 ct
    (True, 152.0),    # Dienstwagen:    212 − 200 kWh × 30 ct
])
async def test_netto_ertrag_der_gemessenen_vier_faelle(db, dienstlich, erwartet):
    """Die Messtabelle aus dem Entscheid, Zeile für Zeile.

    Der Dienstwagen stand hier bis 2026-07-31 bei **196,00 €** — 44 € über dem
    Privatwagen-Nachbarn minus dem, was der Strom wert war, und sogar über der
    Anlage, die den Strom eingespeist hätte. Der Dienstwagen darf der Anlage
    keinen Gewinn bringen; er darf ihr nur weniger schaden als eine
    Netzladung.
    """
    anlage_id = await _anlage_mit_wagen(
        db, f"N18-{dienstlich}", dienstlich=dienstlich
    )
    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    assert cockpit.netto_ertrag_euro == pytest.approx(erwartet, abs=0.01)


async def test_dienstwagen_liegt_zwischen_privatwagen_und_gar_keinem_auto(db):
    """Die Reihenfolge ist die eigentliche Aussage — und sie war verletzt.

    Erwartung: Privatwagen (212 €) > gar kein Auto (168 €) > Dienstwagen (152 €).
    Bis 2026-07-31 stand der Dienstwagen mit 196 € **über** der Anlage ohne Auto:
    verschenkter Strom war profitabler als verkaufter.
    """
    kein = await get_cockpit_uebersicht(
        anlage_id=await _anlage_mit_wagen(db, "Ord-kein", dienstlich=None),
        jahr=None, db=db)
    privat = await get_cockpit_uebersicht(
        anlage_id=await _anlage_mit_wagen(db, "Ord-privat", dienstlich=False),
        jahr=None, db=db)
    dienst = await get_cockpit_uebersicht(
        anlage_id=await _anlage_mit_wagen(db, "Ord-dienst", dienstlich=True),
        jahr=None, db=db)

    assert privat.netto_ertrag_euro > kein.netto_ertrag_euro > dienst.netto_ertrag_euro


async def test_energiebilanz_bleibt_unberuehrt_vom_dienstwagen_abzug(db):
    """**Teil des Entscheids, nicht selbstredend:** die Bilanz darf sich nicht bewegen.

    Energetisch IST die dienstliche Ladung Eigenverbrauch hinter dem Zähler.
    Korrigiert wurde die **Bewertung** in Euro — Eigenverbrauchs-kWh, EV-Quote
    und Autarkie müssen zwischen Privat- und Dienstwagen identisch bleiben.
    Wer sie „mitkorrigiert", hat den Entscheid missverstanden.
    """
    privat = await get_cockpit_uebersicht(
        anlage_id=await _anlage_mit_wagen(db, "Bilanz-privat", dienstlich=False),
        jahr=None, db=db)
    dienst = await get_cockpit_uebersicht(
        anlage_id=await _anlage_mit_wagen(db, "Bilanz-dienst", dienstlich=True),
        jahr=None, db=db)

    assert dienst.eigenverbrauch_kwh == pytest.approx(privat.eigenverbrauch_kwh)
    assert dienst.eigenverbrauch_kwh == pytest.approx(600.0)
    assert dienst.eigenverbrauch_quote_prozent == pytest.approx(
        privat.eigenverbrauch_quote_prozent)
    assert dienst.autarkie_prozent == pytest.approx(privat.autarkie_prozent)
    assert dienst.pv_erzeugung_kwh == pytest.approx(privat.pv_erzeugung_kwh)
    # …und nur die Euro-Seite unterscheidet sich.
    assert dienst.netto_ertrag_euro < privat.netto_ertrag_euro


# ═══════════════════════════════════════════════════════════════════════
# N-12 + N-13 — dieselbe Zahl in allen drei Sichten
# ═══════════════════════════════════════════════════════════════════════


async def _anlage_mit_wallbox_tarif(db) -> int:
    """Dienstwagen mit PV- **und** Netzladung, dazu ein eigener Wallbox-Tarif.

    2026-06: PV 1.000 · Einspeisung 400 · Netzbezug 300
             Dienstwagen 200 kWh PV + 100 kWh Netz
    Tarife:  allgemein 30/8 ct · **Wallbox 18 ct**

        Abzug = 200 × 30 ct (PV, Rücknahme EV-Gutschrift)
              + 100 × 18 ct (Netz, Wallbox-Vertrag)
              = 60,00 + 18,00 = 78,00 €

    Der Wallbox-Preis ist bewusst weit vom Anlagentarif entfernt: bis
    2026-07-31 nahmen die Aussichten hier 30 ct (= 30,00 €) und lagen damit
    12 € neben dem Cockpit (N-12).
    """
    anlage = await _basis(db, "WallboxTarif")
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=18.0, einspeiseverguetung_cent_kwh=8.0,
        verwendung="wallbox",
    ))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=ANSCHAFFUNG,
                     anschaffungskosten_gesamt=10000.0)
    wagen = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Firmenwagen",
                        anschaffungsdatum=ANSCHAFFUNG,
                        parameter={"ist_dienstlich": True})
    db.add_all([pv, wagen])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(
        investition_id=wagen.id, jahr=2026, monat=6,
        verbrauch_daten={"ladung_kwh": 300.0, "ladung_pv_kwh": 200.0,
                         "ladung_netz_kwh": 100.0}))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=300.0))
    await db.commit()
    return anlage.id


async def test_cockpit_zieht_wallbox_tarif_fuer_die_netzladung(db):
    """Kanon (Gernot): WB-Stromvertrag, wenn vorhanden, sonst Anlagentarif.

    Netto = 400 × 8 ct + 600 × 30 ct − 78,00 € = 32 + 180 − 78 = 134,00 €.
    """
    anlage_id = await _anlage_mit_wallbox_tarif(db)
    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)

    assert cockpit.sonstige_netto_euro == pytest.approx(-78.0, abs=0.01)
    assert cockpit.netto_ertrag_euro == pytest.approx(134.0, abs=0.01)


async def test_aussichten_folgen_dem_cockpit_beim_wallbox_tarif(db):
    """N-12: die Aussichten nahmen für die Netzladung den allgemeinen Arbeitspreis.

    Ohne Fix stünden hier 30 ct statt 18 ct → 12 € Unterschied zwischen zwei
    Sichten derselben Anlage. Keine WP/kein privates E-Auto/keine
    Betriebskosten im Fixture — ``bisherige_ertraege_euro`` ist damit exakt das
    Finanz-Aggregat und direkt mit dem Cockpit vergleichbar.
    """
    anlage_id = await _anlage_mit_wallbox_tarif(db)
    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    aussichten = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    assert aussichten.bisherige_ertraege_euro == pytest.approx(134.0, abs=0.05)
    assert aussichten.bisherige_ertraege_euro == pytest.approx(
        cockpit.netto_ertrag_euro, abs=0.01)


async def test_ha_export_zieht_die_dienstlichen_ladekosten_ab(db):
    """N-13: der HA-Sensor stand bei Dienstwagen-Anlagen über der Kachel.

    Ohne Fix meldete ``netto_ertrag_euro`` 212,00 € (= ganz ohne Abzug), während
    die Cockpit-Kachel derselben Anlage 134,00 € zeigte.
    """
    anlage_id = await _anlage_mit_wallbox_tarif(db)
    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)

    from sqlalchemy import select
    anlage = (await db.execute(
        select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    werte = await calculate_anlage_sensors(db, anlage)

    assert _sensor(werte, "netto_ertrag_euro") == pytest.approx(134.0, abs=0.01)
    assert _sensor(werte, "netto_ertrag_euro") == pytest.approx(
        cockpit.netto_ertrag_euro, abs=0.01)
