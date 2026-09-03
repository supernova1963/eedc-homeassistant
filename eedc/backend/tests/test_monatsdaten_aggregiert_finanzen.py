"""Die Monats-Finanzzeile von `/monatsdaten/aggregiert` (Fund **N-22**).

Bis 2026-08-04 lieferte diese Route nur Energiemengen; die Finanzspalten von
*Auswertungen → Tabelle* und *Auswertungen → Finanzen* rechnete der **Client**
(`frontend/src/pages/auswertung/types.ts::createMonatsZeitreihe`) — mit eigener
Tarif-Stichtags-Auflösung, eigenem §51-Abzug und eigener EV-Ersparnis. Dieselbe
Tabelle bezog ihre **Tages**-Zeilen längst aus dem Backend-SoT
(`services/energie_profil/tage_werte.py` → `baue_finanz_zeile`).

Die drei Stellen, an denen die Client-Rechnung vom SoT abwich, sind hier
festgehalten. Sie sind **keine** Rundungsfragen:

1. Ein **Brennstoff-Erzeuger** (BHKW unter „Sonstiges") zählt in die
   Energiebilanz (v3.45.4), aber **nicht** in die Strompreis-Ersparnis — seine
   kWh kosten Gas. Der Client bewertete sie mit dem vollen Netzbezugspreis.
2. Die **USt auf Eigenverbrauch** (§ 3 Abs. 1b UStG) ziehen alle vier
   Backend-Sichten ab; der Client zog sie nicht ab.
3. Ein **BKW-Monat ohne erfasste Erzeugung** trägt seinen gemessenen
   Eigenverbrauch über den Ersatzträger (ADR-002/**P9**); im Client gab es
   diesen Weg nicht.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.core.berechnungen.ust_eigenverbrauch import (
    UstJahresanteil,
    berechne_ust_eigenverbrauch,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.strompreis import Strompreis


async def _basis_anlage(db, **anlage_kwargs) -> Anlage:
    anlage = Anlage(anlagenname="Finanz-Test", leistung_kwp=10.0, **anlage_kwargs)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2020, 1, 1), verwendung="allgemein",
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
        grundpreis_euro_monat=12.0,
    ))
    return anlage


async def _pv_monat(db, anlage_id: int, *, monat: int, pv_kwh: float,
                    einspeisung: float, netzbezug: float) -> None:
    db.add(Monatsdaten(anlage_id=anlage_id, jahr=2026, monat=monat,
                       einspeisung_kwh=einspeisung, netzbezug_kwh=netzbezug))


# ═══════════════════════════════════════════════════════════════════════════
# 1. Der Brennstoff-Erzeuger zählt in die Menge, nicht in die Ersparnis
# ═══════════════════════════════════════════════════════════════════════════


async def test_sonstiger_erzeuger_hebt_menge_und_geld_gemeinsam(db):
    """PV 1000 + BHKW 400, Einspeisung 300 ⇒ EV 1100 kWh, Ersparnis auf 1100 kWh.

    **Der geltende Vertrag** (Maintainer, 2026-09-03): *Sonstige Erzeuger werden
    nicht wirtschaftlich ausgewertet — deren produzierter Strom geht vollständig
    in der EV-Ersparnis und der Einspeisung auf.* „Nicht wirtschaftlich
    ausgewertet" meint die **Komponente**: keine eigene Zeile, Wirtschaftlichkeit
    „nicht bewertet", Ertrag über das Feld „Ertrag/Jahr". In der **Anlagen**-
    Bilanz zählt sein Strom voll — auf beiden Achsen.

    ⛔ **Diese Probe stand bis 2026-09-03 auf dem Gegenteil** („hebt den
    Eigenverbrauch, aber nicht die EV-Ersparnis", 210 € statt 330 €) und hielt
    damit den Entscheid aus v3.45.4 fest: *„ein Erdgas-BHKW verdrängt zwar
    Netzbezug, aber nicht kostenlos."* ⚑ **Diese Begründung deckte die Kategorie
    nie ab:** Ein Windrad oder eine Wasserkraftanlage hat keinen Brennstoff — dort
    schloss die Regel eine tatsächlich kostenlose Kilowattstunde ohne Grund aus
    dem Geldwert aus. Das BHKW ist hier nur die **Fixture**, nicht die Regel. Der Entscheid ist abgelöst — die Probe
    wird deshalb **umgestellt, nicht gelöscht**: ihr Gegenstand bleibt, dass
    Menge und Geldwert dieselbe Erzeugung meinen. Sie prüft das jetzt in der
    anderen Richtung, und die Gegenprobe unten nennt die alte Zahl beim Namen.

    ⚠ **Warum die alte Fassung den Bruch nie sah:** ihr BHKW speist **nichts**
    ein. `max(0, pv − Hauszähler-Einspeisung)` ergab hier zufällig den PV-reinen
    Wert. Sobald ein sonstiger Erzeuger einspeist, zog dieselbe Formel seine
    **ganze** Erzeugung von der PV ab — ein Wert, den auch der alte Entscheid
    nicht wollte. Die Fixture bekommt deshalb unten eine einspeisende Schwester.
    """
    anlage = await _basis_anlage(db)
    await _pv_monat(db, anlage.id, monat=5, pv_kwh=1000.0, einspeisung=300.0, netzbezug=200.0)
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0)
    bhkw = Investition(anlage_id=anlage.id, typ="sonstiges", bezeichnung="Mini-BHKW",
                       anschaffungsdatum=date(2024, 1, 1),
                       parameter={"kategorie": "erzeuger"})
    db.add_all([pv, bhkw])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=bhkw.id, jahr=2026, monat=5,
                                  verbrauch_daten={"erzeugung_kwh": 400.0}))
    await db.commit()

    mai = (await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db))[0]

    # Die Menge trägt das BHKW (Energiebilanz, unverändert) …
    assert mai.eigenverbrauch_kwh == pytest.approx(1100.0)
    # … und der Euro-Wert jetzt ebenfalls: 1100 × 30 ct.
    assert mai.ev_ersparnis_euro == pytest.approx(330.0)
    # Menge × Preis geht auf — das ist die eigentliche Aussage der Probe.
    assert mai.ev_ersparnis_euro == pytest.approx(mai.eigenverbrauch_kwh * 0.30)
    # Gegenprobe: 210 € war die PV-reine Zahl des abgelösten Entscheids.
    assert mai.ev_ersparnis_euro != pytest.approx(210.0), "der abgelöste v3.45.4-Wert"


async def test_einspeisender_erzeuger_zieht_der_pv_nichts_ab(db):
    """Derselbe Aufbau, aber das BHKW **speist ein** — der Fall, den die alte
    Fassung nicht kannte und an dem sie auch ihren eigenen Entscheid verfehlte.

    PV 1000, BHKW 400 (davon 250 eingespeist), Hauszähler-Einspeisung 550.
    Erzeugung hinter dem Zähler 1400 − 550 = 850 kWh Eigenverbrauch ⇒ 255,00 €.

    ⛔ Die alte Formel rechnete `max(0, 1000 − 550)` = **450 kWh / 135,00 €** —
    weder die 850 des neuen Vertrags noch die 600, die „PV-rein" bedeutet hätte
    (1000 − 300 eigene PV-Einspeisung). **Kein Entscheid ergibt 450.**
    """
    anlage = await _basis_anlage(db)
    await _pv_monat(db, anlage.id, monat=6, pv_kwh=1000.0, einspeisung=550.0, netzbezug=200.0)
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0)
    bhkw = Investition(anlage_id=anlage.id, typ="sonstiges", bezeichnung="Mini-BHKW",
                       anschaffungsdatum=date(2024, 1, 1),
                       parameter={"kategorie": "erzeuger"})
    db.add_all([pv, bhkw])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=bhkw.id, jahr=2026, monat=6,
                                  verbrauch_daten={"erzeugung_kwh": 400.0,
                                                   "einspeisung_kwh": 250.0}))
    await db.commit()

    juni = [m for m in await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db)
            if m.monat == 6][0]
    assert juni.eigenverbrauch_kwh == pytest.approx(850.0)
    assert juni.ev_ersparnis_euro == pytest.approx(255.0)
    assert juni.ev_ersparnis_euro != pytest.approx(135.0), "die alte, entscheidlose Zahl"


# ═══════════════════════════════════════════════════════════════════════════
# 2. USt auf Eigenverbrauch — nur bei Regelbesteuerung, je Monat verteilt
# ═══════════════════════════════════════════════════════════════════════════


async def _zwei_monate_mit_pv(db, anlage: Anlage) -> None:
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0,
                     anschaffungskosten_gesamt=20000.0, betriebskosten_jahr=200.0)
    db.add(pv)
    await db.flush()
    for monat, pv_kwh, einsp in ((5, 1000.0, 300.0), (6, 800.0, 200.0)):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=monat,
                           einspeisung_kwh=einsp, netzbezug_kwh=100.0))
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=monat,
                                      verbrauch_daten={"pv_erzeugung_kwh": pv_kwh}))
    await db.commit()


async def test_ohne_regelbesteuerung_keine_ust(db):
    anlage = await _basis_anlage(db, steuerliche_behandlung="keine_ust")
    await _zwei_monate_mit_pv(db, anlage)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db)
    assert [r.ust_eigenverbrauch_euro for r in rows] == [0.0, 0.0]
    # Netto-Ertrag = Erlös + EV-Ersparnis, ohne Abzug.
    for r in rows:
        assert r.netto_ertrag_euro == pytest.approx(
            r.einspeise_erloes_euro + r.ev_ersparnis_euro, abs=0.01
        )


async def test_regelbesteuerung_zieht_ust_ab_und_verteilt_sie_verlustfrei(db):
    """Σ der Monats-USt == USt der Jahressumme (die Formel ist linear im EV).

    Der Nenner der Selbstkosten je kWh ist die **Jahres**-PV der ausgelieferten
    Monate — deshalb darf die monatsweise Verteilung nichts verschieben.
    """
    anlage = await _basis_anlage(
        db, steuerliche_behandlung="regelbesteuerung", ust_satz_prozent=19.0
    )
    await _zwei_monate_mit_pv(db, anlage)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db)

    # Mai: EV = max(0, 1000 − 300) = 700; Juni: max(0, 800 − 200) = 600.
    summe_ust = sum(r.ust_eigenverbrauch_euro for r in rows)
    # Bemessungsgrundlage ist seit 04.08. die MEHRKOSTEN-Form (N-129); die
    # Fixture pflegt keine Alternativkosten, damit ist sie hier == Vollkosten.
    # `monate=2`, weil nur zwei Monate des Jahres ausgeliefert werden (N-130) —
    # AfA und Betriebskosten zählen anteilig.
    einmal = berechne_ust_eigenverbrauch(
        [UstJahresanteil(
            jahr=2026,
            eigenverbrauch_kwh=700.0 + 600.0,
            pv_kwh=1000.0 + 800.0,
            monate=2,
        )],
        bemessungsgrundlage_euro=20000.0,
        betriebskosten_jahr_euro=200.0,
        ust_satz_prozent=19.0,
    )
    assert summe_ust == pytest.approx(einmal, abs=0.02)
    assert summe_ust > 0, "sonst prüft der Test nichts"

    # Und sie steckt im Netto-Ertrag — das ist der Unterschied zur alten
    # Client-Zahl, die den Abzug gar nicht kannte.
    for r in rows:
        assert r.netto_ertrag_euro == pytest.approx(
            r.einspeise_erloes_euro + r.ev_ersparnis_euro - r.ust_eigenverbrauch_euro,
            abs=0.01,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. BKW ohne erfasste Erzeugung — der Ersatzträger (P9)
# ═══════════════════════════════════════════════════════════════════════════


async def test_bkw_datenluecke_traegt_ueber_die_bkw_ersparnis(db):
    """Nur Eigenverbrauch gepflegt, keine Erzeugung ⇒ separater Posten.

    Der Client kannte diesen Weg nicht: ohne Erzeugung leitete er aus der
    Hausbilanz keinen Eigenverbrauch ab, und der gemessene BKW-Eigenverbrauch
    tauchte in keiner Euro-Zahl auf.
    """
    anlage = await _basis_anlage(db)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=0.0, netzbezug_kwh=100.0))
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                      anschaffungsdatum=date(2024, 1, 1), leistung_kwp=0.8)
    db.add(bkw)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=5,
                                  verbrauch_daten={"eigenverbrauch_kwh": 50.0}))
    await db.commit()

    mai = (await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db))[0]
    # 50 kWh × 30 ct = 15,00 € — als eigener Posten, nicht in ev_ersparnis_euro
    # (sonst zählte derselbe Fluss zweimal, sobald die Erzeugung nachgepflegt wird).
    assert mai.bkw_ersparnis_euro == pytest.approx(15.0)
    assert mai.netto_ertrag_euro == pytest.approx(
        mai.einspeise_erloes_euro + mai.ev_ersparnis_euro + mai.bkw_ersparnis_euro, abs=0.01
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Netzbezugskosten + Bilanz — der Grundpreis ist ein Monatsposten
# ═══════════════════════════════════════════════════════════════════════════


async def test_netzbezug_kosten_tragen_den_grundpreis_und_die_bilanz_zieht_mit(db):
    anlage = await _basis_anlage(db)
    await _zwei_monate_mit_pv(db, anlage)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db)
    for r in rows:
        # 100 kWh × 30 ct = 30 € + 12 € Grundpreis
        assert r.netzbezug_kosten_euro == pytest.approx(42.0)
        assert r.netzbezug_preis_cent == pytest.approx(30.0)
        assert r.netto_bilanz_euro == pytest.approx(
            r.netto_ertrag_euro - r.netzbezug_kosten_euro, abs=0.01
        )


async def test_historischer_monatstarif_gilt_je_monat(db):
    """P8: ein Tarifwechsel wirkt ab seinem Monat, nicht rückwirkend."""
    anlage = await _basis_anlage(db)
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2026, 6, 1), verwendung="allgemein",
        netzbezug_arbeitspreis_cent_kwh=40.0, einspeiseverguetung_cent_kwh=8.0,
        grundpreis_euro_monat=12.0,
    ))
    await _zwei_monate_mit_pv(db, anlage)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db)
    mai = next(r for r in rows if r.monat == 5)
    juni = next(r for r in rows if r.monat == 6)
    assert mai.netzbezug_preis_cent == pytest.approx(30.0)
    assert juni.netzbezug_preis_cent == pytest.approx(40.0)
    assert mai.ev_ersparnis_euro == pytest.approx(700 * 0.30)
    assert juni.ev_ersparnis_euro == pytest.approx(600 * 0.40)
