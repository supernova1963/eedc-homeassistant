"""Die drei Befunde aus Knallfroschs Meldung (Forum T89667 #163, 15.08.2026).

Sein Screenshot zeigte in *Cockpit → Tag* einen Speicher-Wirkungsgrad von
**100,5 %** — kommentarlos. Im selben Faden hat rapahl (#164) die richtige
Erklärung geliefert: *„Da es am Tage schon vorkommen kann, dass mehr aus der
Batterie entnommen wird, als geladen, ergibt sich ein solcher Wirkungsgrad."*
Genau diese Auskunft gab eedc nicht — der Monat unterdrückt seit F-22 alles über
100 % und nennt die Quelle, die Tagessicht tat beides nicht.

Beim Nachmessen kamen zwei weitere Widersprüche auf derselben Seite dazu, beide
aus derselben Ursache: den fünf ``round(…, 2)`` auf den Finanz-Feldern des
Tages, die es im Monatspfad nicht gibt.

1. **η ohne Einordnung** — hier: Layer-Formel + Durchreichung der Quelle.
2. **Netto-Ertrag ≠ Summe der Finanz-Bilanz-Tabelle** (16,05 gegen 16,04):
   Summe der Gerundeten gegen gerundete Summe.
3. **„Ø-Preis Netz" aus zwei gerundeten Zahlen** — 31,6 ct statt der ~29,5 ct,
   mit denen dieselbe Seite die Eigenverbrauchs-Ersparnis rechnet.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen import (
    delta_soc_kwh,
    speicher_wirkungsgrad,
)
from backend.models import Anlage, Investition, Strompreis
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.energie_profil.tage_werte import baue_tage_werte


# ── Layer: eine Formel, drei benannte Fälle ─────────────────────────────────


def test_ohne_ladestand_und_ueber_100_prozent_gibt_es_keinen_wert():
    """Knallfroschs Fall: mehr entnommen als geladen, kein SoC am Rand.

    Über 100 % kann kein Speicher — und ohne Ladestand lässt sich nicht sagen,
    wie viel davon Übertrag aus der Vornacht war. Also kein Wert, aber ein Grund.
    """
    eta = speicher_wirkungsgrad(10.0, 10.05, None)
    assert eta.prozent is None
    assert eta.quelle == "nicht-ermittelbar"


def test_mit_ladestand_wird_der_uebertrag_herausgerechnet():
    """Voll begonnen, leer geendet: ΔSoC ist negativ und macht η plausibel."""
    eta = speicher_wirkungsgrad(10.0, 10.05, -1.5)
    assert eta.quelle == "soc_korrigiert"
    assert eta.prozent == pytest.approx(85.5)


def test_unter_100_prozent_bleibt_der_rohe_wert_stehen():
    """P4: Ohne SoC-Sensor ist der rohe Quotient die einzige Aussage, die es
    gibt — sie wird ausgewiesen, nicht verschwiegen."""
    eta = speicher_wirkungsgrad(10.0, 8.6, None)
    assert eta.quelle == "roh-unkorrigiert"
    assert eta.prozent == pytest.approx(86.0)


def test_ohne_ladung_keine_aussage():
    assert speicher_wirkungsgrad(0.0, 0.0, None).quelle == "keine-ladung"
    assert speicher_wirkungsgrad(0.05, 4.0, None).prozent is None


def test_geklemmt_auch_mit_ladestand():
    """Messfehler dürfen den korrigierten Wert nicht über 100 % heben."""
    assert speicher_wirkungsgrad(10.0, 9.0, 5.0).prozent == 100.0
    assert speicher_wirkungsgrad(10.0, 0.0, -50.0).prozent == 0.0


def test_delta_soc_braucht_zwei_messwerte_und_eine_kapazitaet():
    """Aus einem einzelnen Stand folgt keine Differenz — und ohne Kapazität
    keine Energie. Beides ergibt ``None`` (= keine Korrektur), nicht 0."""
    assert delta_soc_kwh([None, 80.0, None], 10.0) is None
    assert delta_soc_kwh([90.0, None, 30.0], 0) is None
    # Erster und letzter GEMESSENER Stand, nicht 0 und 23 Uhr.
    assert delta_soc_kwh([None, 90.0, 50.0, 30.0, None], 10.0) == pytest.approx(-6.0)


# ── Tagesebene: derselbe Maßstab wie im Monat ───────────────────────────────


async def _anlage_mit_speicher(db, *, mit_soc: bool) -> int:
    anlage = Anlage(anlagenname="EtaTag", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0,
        parameter={"nutzbare_kapazitaet_kwh": 10.0},
    ))
    # Der Tag: 6 kWh geladen, 6,3 kWh entnommen — der rohe Quotient steht bei
    # 105 %. Mit SoC-Messung erklärt sich die Differenz aus dem Übertrag.
    tag = date(2026, 5, 10)
    db.add_all([
        TagesEnergieProfil(
            anlage_id=anlage.id, datum=tag, stunde=h,
            pv_kw=2.0, verbrauch_kw=3.0, einspeisung_kw=0.0, netzbezug_kw=1.0,
            batterie_kw=(-3.0 if h < 12 else 3.15),
            soc_prozent=(soc if mit_soc else None),
        )
        for h, soc in ((10, 90.0), (11, 95.0), (13, 40.0), (14, 20.0))
    ])
    await db.flush()
    return anlage.id


@pytest.mark.asyncio
async def test_tag_ohne_ladestand_schweigt_statt_ueber_100_zu_zeigen(db):
    aid = await _anlage_mit_speicher(db, mit_soc=False)
    anlage = await db.get(Anlage, aid)

    tage = await baue_tage_werte(db, anlage, date(2026, 5, 1), date(2026, 5, 31))

    assert tage[0].speicher_effizienz is None
    assert tage[0].speicher_effizienz_quelle == "nicht-ermittelbar"


@pytest.mark.asyncio
async def test_tag_mit_ladestand_rechnet_den_uebertrag_heraus(db):
    """ΔSoC = (20 − 90) % × 10 kWh = −7 kWh ⇒ η = (6,3 − 7) ÷ 6 < 0 ⇒ 0 %.

    Der Zahlenwert ist hier zweitrangig; entscheidend ist, dass die Quelle
    ``soc_korrigiert`` heißt und der Wert die Grenze nicht mehr reißt.
    """
    aid = await _anlage_mit_speicher(db, mit_soc=True)
    anlage = await db.get(Anlage, aid)

    tage = await baue_tage_werte(db, anlage, date(2026, 5, 1), date(2026, 5, 31))

    assert tage[0].speicher_effizienz_quelle == "soc_korrigiert"
    assert tage[0].speicher_effizienz is not None
    assert 0.0 <= tage[0].speicher_effizienz <= 100.0


# ── Finanzen: eine Zahl, egal welche Anzeige sie summiert ───────────────────


async def _anlage_mit_tarif(db) -> int:
    """Ein Tag mit krummen Beträgen — genau dort trennt sich gerundete Summe
    von Summe der Gerundeten."""
    anlage = Anlage(anlagenname="FinanzTag", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=29.53,
        einspeiseverguetung_cent_kwh=8.11,
    ))
    tag = date(2026, 5, 10)
    db.add_all([
        TagesEnergieProfil(
            anlage_id=anlage.id, datum=tag, stunde=h,
            pv_kw=pv, verbrauch_kw=0.7, einspeisung_kw=eins, netzbezug_kw=netz,
        )
        for h, pv, eins, netz in (
            (10, 3.31, 2.61, 0.0),
            (11, 4.17, 3.47, 0.0),
            (20, 0.0, 0.0, 0.19),
        )
    ])
    await db.flush()
    return anlage.id


@pytest.mark.asyncio
async def test_netto_ertrag_ist_die_summe_seiner_angezeigten_summanden(db):
    """Die Netto-Ertrag-Kachel und die Finanz-Bilanz-Tabelle stehen auf
    derselben Seite. Vorher zeigte die eine 16,05 und die andere 16,04."""
    aid = await _anlage_mit_tarif(db)
    anlage = await db.get(Anlage, aid)

    zeile = (await baue_tage_werte(db, anlage, date(2026, 5, 1), date(2026, 5, 31)))[0]

    assert zeile.netto_ertrag == pytest.approx(
        zeile.einspeise_erloes + zeile.ev_ersparnis, abs=1e-9
    )
    # Und die Rundung ist NICHT vorweggenommen: sonst wäre der Cent-Bruchteil
    # schon weg und der Vergleich oben trivial erfüllt.
    assert round(zeile.einspeise_erloes, 2) != pytest.approx(zeile.einspeise_erloes)


@pytest.mark.asyncio
async def test_oe_preis_netz_bleibt_der_tarif_auch_bei_kleiner_menge(db):
    """0,19 kWh Netzbezug: Kosten ÷ Menge ergab mit gerundeten Kosten 31,6 ct.

    Der Client zeigt den Tarif aus dem Tagesdetail; diese Probe sichert die
    Backend-Hälfte — der Quotient trifft ihn jetzt auch als Rückfall.
    """
    aid = await _anlage_mit_tarif(db)
    anlage = await db.get(Anlage, aid)

    zeile = (await baue_tage_werte(db, anlage, date(2026, 5, 1), date(2026, 5, 31)))[0]

    assert zeile.netzbezug == pytest.approx(0.19)
    assert (zeile.netzbezug_kosten / zeile.netzbezug) * 100 == pytest.approx(29.53)
