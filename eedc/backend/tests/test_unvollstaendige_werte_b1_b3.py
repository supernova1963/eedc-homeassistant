"""Unvollständige Werte — die ausgelieferte Provenance (B1) und die Gegenrichtung (B3).

`docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md` §3 Regel 2 lautet: *„Ein Provenance-Flag
ohne Leser ist kein Provenance. Wer eines einführt, liefert es im selben Schritt
aus."* §2.4 nennt genau das den schärfsten Einzelbefund der Inventur — und
`ErzeugungFakten.pv_vollstaendig` **war** dieser Befund: gesetzt, getestet, von
keiner Route gelesen (0 Treffer in `backend/api`, gemessen 29.08.2026).

Diese Datei hält beide Richtungen der Regel fest:

* **Richtung 1** (unbekannt → 0): eine PV-Teilsumme bleibt stehen — sie ist
  additiv und damit richtungssicher zu niedrig — **und sagt es** (N-95·N-94/B1).
* **Richtung 2** (0 → unbekannt): eine **gemessene** Null bleibt eine 0 und wird
  nicht zu „—" (N-52 = N-344 Teil 1/B3).

**Schwesterdateien:** `test_konformitaet_provenance_flag_hat_leser.py` (Wächter W1
— *dass* ausgeliefert wird; hier steht, *was*), `test_tagesbilanz_pv_nicht_erfasst.py`
und `test_live_tageswerte_luecken.py` (dieselbe Regel eine Ebene tiefer, auf der
Tages- bzw. Stundenachse).

⚠ Die beiden Fundstellen von Richtung 2 standen in **zwei** Registereinträgen
(N-52 in Päckchen 14, N-344 in Päckchen 11) — derselbe Ausdruck, derselbe
Defekt. Die Dublette ist am 29.08.2026 beim Bau aufgelöst worden.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.models import Anlage, Investition, Monatsdaten
from backend.services.monats_fakten import (
    lade_monats_fakten,
    pv_unvollstaendig_hinweis,
    pv_unvollstaendig_monate,
)
from backend.services.prognose_adapter import ist_profil
from backend.tests import factories


async def _anlage_mit_zwei_strings(db) -> Anlage:
    """Zwei aktive Module — die Voraussetzung für eine *Teil*-Lücke.

    Mit nur EINEM Modul gäbe es keine Teilsumme, sondern gar keinen Wert; der
    Fall wäre ein anderer (`PV_STATUS_FEHLT`).
    """
    anlage = Anlage(anlagenname="B1", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    for name in ("Süd", "Nord"):
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=name,
            anschaffungsdatum=date(2024, 1, 1), leistung_kwp=5.0,
        ))
    await db.flush()
    return anlage


@pytest.mark.asyncio
async def test_b1_teilluecke_wird_beschriftet_und_nennt_ihre_folge(db):
    """Ein Modul ohne Wert, kein Aggregat ⇒ Hinweis, der die **Folge** nennt.

    Der Daten-Checker meldet den Zustand längst („PV-Erzeugung unvollständig in
    N Monat(en)"). Er sagt aber nicht, was daraus folgt — dass Erzeugung,
    spezifischer Ertrag und der daraus gerechnete Ertrag eine Teilsumme sind.
    Genau das ist der Unterschied zwischen *„was musst du nachtragen?"* und
    *„worauf beruht diese Zahl?"* (§4), und genau das muss der Satz leisten.
    """
    anlage = await _anlage_mit_zwei_strings(db)
    sued = (await db.execute(
        select(Investition).where(Investition.bezeichnung == "Süd")
    )).scalar_one()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    db.add(factories.mach_imd(sued.id, 2025, 6, {"pv_erzeugung_kwh": 500.0}))
    await db.commit()

    fakten = await lade_monats_fakten(db, anlage.id)
    assert [f.erzeugung.pv_vollstaendig for f in fakten] == [False]

    assert pv_unvollstaendig_monate(fakten) == [(2025, 6)]
    hinweis = pv_unvollstaendig_hinweis(fakten)
    assert hinweis is not None
    assert "06/2025" in hinweis
    # Die Folge, nicht nur der Zustand — das ist der Prüfgegenstand.
    assert "Teilsumme" in hinweis and "zu niedrig" in hinweis


@pytest.mark.asyncio
async def test_b1_vollstaendiger_monat_bekommt_keinen_hinweis(db):
    """Gegenprobe: beide Module gepflegt ⇒ `None`, die Sicht rendert nichts.

    Ohne diese Richtung wäre der Prüfer oben von einem Hinweis, der IMMER
    erscheint, nicht zu unterscheiden.
    """
    anlage = await _anlage_mit_zwei_strings(db)
    invs = (await db.execute(
        select(Investition).order_by(Investition.id)
    )).scalars().all()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    for inv in invs:
        db.add(factories.mach_imd(inv.id, 2025, 6, {"pv_erzeugung_kwh": 500.0}))
    await db.commit()

    fakten = await lade_monats_fakten(db, anlage.id)
    assert [f.erzeugung.pv_vollstaendig for f in fakten] == [True]
    assert pv_unvollstaendig_monate(fakten) == []
    assert pv_unvollstaendig_hinweis(fakten) is None


@pytest.mark.asyncio
async def test_b1_aggregat_deckt_die_luecke_und_der_hinweis_schweigt(db):
    """Ein Anlagen-Aggregat verteilt nach kWp ⇒ **vollständig**, kein Hinweis.

    Die Abgrenzung ist nicht kosmetisch: eine über kWp verteilte PV ist
    *geschätzt*, aber nicht *unvollständig* — dafür trägt die Anzeige bereits
    „geschätzt (kWp-Anteil)" (v4.0.1). Zwei Beschriftungen für denselben Monat
    wären der zweite Turm, den §4 verbietet.
    """
    anlage = await _anlage_mit_zwei_strings(db)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0,
                       pv_erzeugung_kwh=1000.0))
    await db.commit()

    fakten = await lade_monats_fakten(db, anlage.id)
    assert [f.erzeugung.pv_vollstaendig for f in fakten] == [True]
    assert pv_unvollstaendig_hinweis(fakten) is None


@pytest.mark.asyncio
async def test_b1_flag_erreicht_die_monatstabelle(db):
    """Die Auslieferung selbst — sonst bliebe es ein Flag ohne Leser.

    `/monatsdaten/aggregiert` liefert eine **nackte Liste**; die Zeile *ist* der
    Monat und trägt das Flag deshalb selbst. Ein Satz auf Seitenebene würde
    gerade die Information verlieren, welcher Monat gemeint ist.
    """
    from backend.api.routes.monatsdaten import (
        AggregierteMonatsdatenResponse,
        list_monatsdaten_aggregiert,
    )

    anlage = await _anlage_mit_zwei_strings(db)
    invs = (await db.execute(
        select(Investition).order_by(Investition.id)
    )).scalars().all()
    sued, nord = invs[0], invs[1]
    # Juni: nur Süd gepflegt ⇒ Teilsumme. Juli: beide ⇒ vollständig.
    for monat in (6, 7):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=monat,
                           einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    db.add(factories.mach_imd(sued.id, 2025, 6, {"pv_erzeugung_kwh": 500.0}))
    db.add(factories.mach_imd(sued.id, 2025, 7, {"pv_erzeugung_kwh": 500.0}))
    db.add(factories.mach_imd(nord.id, 2025, 7, {"pv_erzeugung_kwh": 400.0}))
    await db.commit()

    # Vertrag beidseitig: Default ist „vollständig", damit ein alter Client und
    # ein Monat ohne Befund identisch aussehen.
    assert AggregierteMonatsdatenResponse.model_fields["pv_vollstaendig"].default is True

    # ⭐ Und die Verdrahtung selbst — ein Schema-Feld, das die Route nie setzt,
    # wäre exakt derselbe Befund eine Ebene höher.
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2025, db=db)
    je_monat = {r.monat: r for r in rows}
    assert je_monat[6].pv_vollstaendig is False
    assert je_monat[7].pv_vollstaendig is True

    # ⚠ GEMESSEN, nicht angenommen: **diese** Route zeigt für die Teil-Lücke
    # ohne BKW schon heute „—" (`hat_pv_imd` verlangt `pv_module_kwh is not
    # None`). Das Flag ersetzt die Unterdrückung hier also nicht, es **erklärt**
    # sie — ein „—" ohne Grund war die Lehre aus dem N-346-Rückbau.
    assert je_monat[6].pv_erzeugung_kwh is None
    assert je_monat[7].pv_erzeugung_kwh == pytest.approx(900.0)


@pytest.mark.asyncio
async def test_b1_mit_balkonkraftwerk_wird_die_teilsumme_wirklich_gezeigt(db):
    """Der Fall, in dem eine Teilsumme als Zahl **dasteht** — und das ist der Befund.

    Sobald ein Balkonkraftwerk im Monat eine Zeile hat, ist `hat_pv_imd` wahr,
    obwohl die Modul-Auflösung eine Lücke hat. Die Route liefert dann
    `pv_kwh = 0 + BKW` als PV-Erzeugung der **Anlage** und `pv_module_kwh` als
    **0,0** — eine Zahl, die wie eine Messung aussieht und keine ist.

    ⛔ Ohne diesen Prüfer wäre der Fund an der falschen Stelle belegt: Die
    Route ohne BKW unterdrückt bereits von selbst. Am 29.08.2026 beim Bau
    gemessen, nachdem die erste Fassung dieses Tests aus genau diesem Grund
    rot wurde.
    """
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    anlage = await _anlage_mit_zwei_strings(db)
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
        anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(bkw)
    await db.flush()
    sued = (await db.execute(
        select(Investition).where(Investition.bezeichnung == "Süd")
    )).scalar_one()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    db.add(factories.mach_imd(sued.id, 2025, 6, {"pv_erzeugung_kwh": 500.0}))
    db.add(factories.mach_imd(bkw.id, 2025, 6, {"pv_erzeugung_kwh": 60.0}))
    await db.commit()

    fakten = await lade_monats_fakten(db, anlage.id)
    assert [f.erzeugung.pv_vollstaendig for f in fakten] == [False]

    rows = await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2025, db=db)
    juni = rows[0]
    # Die 500 kWh des Süd-Strings fehlen in beiden Zahlen — DAS ist die Teilsumme.
    assert juni.pv_erzeugung_kwh == pytest.approx(60.0)
    assert juni.pv_module_kwh == pytest.approx(0.0)
    # ... und die Zeile sagt es jetzt.
    assert juni.pv_vollstaendig is False


# ═══════════════════════════════════════════════════════════════════════
# Richtung 2 — die gemessene Null (N-52 = N-344 Teil 1, Paket B3)
# ═══════════════════════════════════════════════════════════════════════


class _Row:
    def __init__(self, stunde: int, pv_kw):
        self.stunde = stunde
        self.pv_kw = pv_kw


def test_b3_gemessene_null_ist_eine_messung():
    """24 Stunden gemessen, alle 0 (Nacht/Schnee) ⇒ `hat_messung` ist True.

    Der ausgelieferte IST-Wert ist dann **0,0**, nicht „—". Bis 29.08.2026
    entschied `ist_heute_kwh > 0` — und machte aus jeder gemessenen Null eine
    fehlende Angabe.
    """
    profil = ist_profil([_Row(h, 0.0) for h in range(24)], jetzt_stunde=23,
                        datum=date(2025, 12, 21))
    assert profil.tageswert_kwh == 0.0
    assert profil.hat_messung is True


def test_b3_ohne_jeden_zaehler_bleibt_es_eine_luecke():
    """Die Gegenprobe, und sie ist der Grund gegen `is not None`.

    `ist_profil` liefert `tageswert_kwh` **nie** als `None` — die Summe startet
    bei 0.0. Der Ansatz „`is not None` statt `> 0`" (so stand er im Fund) hätte
    eine Anlage ohne PV-Zähler mit „0,0 kWh IST" beschriftet statt mit „—":
    aus einem zu strengen Prüfer wäre ein falscher Wert geworden.
    """
    profil = ist_profil([], jetzt_stunde=12, datum=date(2025, 6, 1))
    assert profil.tageswert_kwh == 0.0        # NICHT None — das ist der Punkt
    assert profil.hat_messung is False

    nur_luecken = ist_profil([_Row(h, None) for h in range(24)], jetzt_stunde=23,
                             datum=date(2025, 6, 1))
    assert nur_luecken.tageswert_kwh == 0.0
    assert nur_luecken.hat_messung is False


def test_b3_eine_gemessene_stunde_genuegt():
    """Träger-Semantik wie `TagesBilanz.pv_erfasst`: EINE Stunde reicht."""
    profil = ist_profil(
        [_Row(h, None) for h in range(23)] + [_Row(23, 0.0)],
        jetzt_stunde=23, datum=date(2025, 6, 1),
    )
    assert profil.hat_messung is True


@pytest.mark.asyncio
async def test_b1_cockpit_jahr_summiert_die_teilsumme_und_sagt_es(db):
    """Cockpit → Jahr ist die Stelle, an der die Teilsumme **ungebremst** ankommt.

    `pv_erzeugung = sum(f.erzeugung.pv_kwh for f in fakten)` hat keinen Guard —
    ein Monat mit Modul-Lücke trägt nur bei, was messbar war. Die Kopfzahl war
    damit still zu niedrig, und daran hängen spezifischer Ertrag und SOLL/IST.

    Der Hinweis unterdrückt sie **nicht**: eine additive Summe ist
    richtungssicher zu niedrig, der Nutzer weiß also, in welche Richtung er
    korrigieren muss (§3). Er wird beschriftet.
    """
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    anlage = await _anlage_mit_zwei_strings(db)
    sued = (await db.execute(
        select(Investition).where(Investition.bezeichnung == "Süd")
    )).scalar_one()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    db.add(factories.mach_imd(sued.id, 2025, 6, {"pv_erzeugung_kwh": 500.0}))
    await db.commit()

    antwort = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=2025, db=db)

    assert antwort.pv_erzeugung_kwh == pytest.approx(0.0)   # die Teilsumme
    assert len(antwort.hinweise) == 1
    assert "06/2025" in antwort.hinweise[0]
    assert "Teilsumme" in antwort.hinweise[0]


@pytest.mark.asyncio
async def test_b1_cockpit_jahr_schweigt_wenn_alles_gepflegt_ist(db):
    """Gegenprobe zur Sicht: vollständig ⇒ `hinweise` leer, die Zeile rendert nichts."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    anlage = await _anlage_mit_zwei_strings(db)
    invs = (await db.execute(
        select(Investition).order_by(Investition.id)
    )).scalars().all()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    for inv in invs:
        db.add(factories.mach_imd(inv.id, 2025, 6, {"pv_erzeugung_kwh": 500.0}))
    await db.commit()

    antwort = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=2025, db=db)

    assert antwort.pv_erzeugung_kwh == pytest.approx(1000.0)
    assert antwort.hinweise == []
