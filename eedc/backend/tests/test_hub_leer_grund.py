"""
N-247 — der Komponenten-Hub nennt den Grund, statt zu schweigen.

**Gemeldet von CHI3fx117 (Forum T89667 #152, 14.08.):** Ein Speicher mit
Anschaffungsdatum im laufenden Monat erscheint in *Cockpit → Tag/Monat*, im
Reiter *Komponenten* stehen dagegen nur Nullen — kommentarlos. Der Fund ist die
Schweigsamkeit, nicht die Rechnung.

Zwei Ebenen, getrennt geprüft:

* die **reine Funktion** (:mod:`backend.core.hub_leer_grund`) — alle fünf Arten,
  ohne DB und ohne Uhr, damit derselbe Fall in jeder Zeitzone dasselbe Ergebnis
  hat (Lehre aus dem CI-Lauf zu v4.0.14);
* der **Endpoint** — er darf sich nicht auf die Behauptung des Clients
  verlassen, sondern zählt selbst nach, und zwar mit **demselben Aktiv-Filter
  wie die Dashboards**. Sonst stünde der Hinweis neben gefüllten Blöcken.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.dashboards import get_hub_leer_grund
from backend.core.hub_leer_grund import LeerGrundArt, bestimme_leer_grund
from backend.models import Anlage, Investition, InvestitionMonatsdaten

HEUTE = date(2026, 8, 14)


# ---------------------------------------------------------------- reine Funktion


def test_zu_jung_ist_der_gemeldete_fall():
    """Anschaffung im LAUFENDEN Monat ⇒ es gibt schlicht noch nichts."""
    g = bestimme_leer_grund(
        aktiv=True,
        anschaffungsdatum=date(2026, 8, 1),
        stilllegungsdatum=None,
        heute=HEUTE,
    )
    assert g.art is LeerGrundArt.ZU_JUNG
    # Der Kern: kein Knopf zum Monatsabschluss — es gibt keinen Monat zum
    # Abschließen (P-6). Stattdessen die Sicht, die das Gerät heute schon zeigt.
    assert g.link == "/cockpit/monat"
    assert "Monatsabschluss steht noch aus" in (g.details or "")


def test_anschaffung_in_der_zukunft_zaehlt_ebenfalls_als_zu_jung():
    """Die Grenze ist der Monat, nicht der Tag — sonst kippte sie am Monatsersten."""
    g = bestimme_leer_grund(
        aktiv=True,
        anschaffungsdatum=date(2026, 11, 1),
        stilllegungsdatum=None,
        heute=HEUTE,
    )
    assert g.art is LeerGrundArt.ZU_JUNG


def test_vormonat_ist_bereits_erfassung_fehlt():
    """Ein Monat ist abgeschlossen ⇒ andere Art, anderer Weg, andere Grammatik."""
    g = bestimme_leer_grund(
        aktiv=True,
        anschaffungsdatum=date(2026, 7, 1),
        stilllegungsdatum=None,
        heute=HEUTE,
    )
    assert g.art is LeerGrundArt.ERFASSUNG_FEHLT
    assert g.link == "/einstellungen/daten"
    assert "liegt ein abgeschlossener Monat" in (g.details or "")


def test_erfassung_fehlt_zaehlt_die_abgeschlossenen_monate():
    g = bestimme_leer_grund(
        aktiv=True,
        anschaffungsdatum=date(2025, 8, 1),
        stilllegungsdatum=None,
        heute=HEUTE,
    )
    assert "liegen 12 abgeschlossene Monate" in (g.details or "")


def test_drei_achsen_bleiben_getrennt():
    """`aktiv`, Stilllegung und Anschaffung sind drei Achsen, nicht eine."""
    inaktiv = bestimme_leer_grund(
        aktiv=False,
        anschaffungsdatum=date(2025, 1, 1),
        stilllegungsdatum=None,
        heute=HEUTE,
    )
    stillgelegt = bestimme_leer_grund(
        aktiv=True,
        anschaffungsdatum=date(2024, 1, 1),
        stilllegungsdatum=date(2025, 3, 1),
        heute=HEUTE,
    )
    assert inaktiv.art is LeerGrundArt.NICHT_AKTIV
    assert stillgelegt.art is LeerGrundArt.STILLGELEGT
    assert inaktiv.meldung != stillgelegt.meldung


def test_ohne_anschaffungsdatum_wird_nichts_behauptet():
    """Altbestand ohne Datum: kein erfundener Zeitbezug, aber ein Weg."""
    g = bestimme_leer_grund(
        aktiv=True, anschaffungsdatum=None, stilllegungsdatum=None, heute=HEUTE
    )
    assert g.art is LeerGrundArt.UNBEKANNT
    assert "Anschaffungsdatum" in (g.details or "")


def test_grund_haengt_nicht_an_der_prozess_zeitzone():
    """`heute` ist Parameter — dieselbe Lage ergibt immer dieselbe Art."""
    arten = {
        bestimme_leer_grund(
            aktiv=True,
            anschaffungsdatum=date(2026, 8, 1),
            stilllegungsdatum=None,
            heute=HEUTE,
        ).art
        for _ in range(3)
    }
    assert arten == {LeerGrundArt.ZU_JUNG}


# -------------------------------------------------------------------- Endpoint


async def _seed(db, *, anschaffung: date, mit_monatswert: tuple[int, int] | None):
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id,
        typ="speicher",
        bezeichnung="Frisch gekauft",
        anschaffungsdatum=anschaffung,
        parameter={"kapazitaet_kwh": 10},
    )
    db.add(inv)
    await db.flush()
    if mit_monatswert is not None:
        jahr, monat = mit_monatswert
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=jahr, monat=monat,
            verbrauch_daten={"ladung_kwh": 10.0, "entladung_kwh": 9.0},
        ))
    await db.flush()
    return anlage.id, inv.id


async def test_endpoint_nennt_den_grund_beim_frisch_angeschafften_geraet(db):
    anlage_id, inv_id = await _seed(
        db, anschaffung=date.today().replace(day=1), mit_monatswert=None
    )
    r = await get_hub_leer_grund(anlage_id, inv_id, db=db)
    assert r.leer is True
    assert r.art == LeerGrundArt.ZU_JUNG.value
    assert r.meldung


async def test_endpoint_schweigt_wenn_es_werte_gibt(db):
    """Gegenprobe: mit Monatswert darf KEIN Hinweis entstehen."""
    heute = date.today()
    anlage_id, inv_id = await _seed(
        db, anschaffung=date(2023, 1, 1), mit_monatswert=(heute.year, heute.month)
    )
    r = await get_hub_leer_grund(anlage_id, inv_id, db=db)
    assert r.leer is False
    assert r.meldung is None


async def test_endpoint_zaehlt_mit_dem_aktiv_filter_der_dashboards(db):
    """
    Die eigentliche Gefahrenstelle: eine Monatszeile VOR der Anschaffung zählen
    die Dashboards nicht (`ist_aktiv_im_monat`). Zählte der Endpoint sie mit,
    bliebe der Hub stumm, obwohl jeder Block auf Null steht.
    """
    anlage_id, inv_id = await _seed(
        db, anschaffung=date(2026, 8, 1), mit_monatswert=(2020, 5)
    )
    r = await get_hub_leer_grund(anlage_id, inv_id, db=db)
    assert r.leer is True


async def test_endpoint_kennt_fremde_anlagen_nicht(db):
    anlage_id, inv_id = await _seed(
        db, anschaffung=date(2026, 8, 1), mit_monatswert=None
    )
    with pytest.raises(Exception):
        await get_hub_leer_grund(anlage_id + 999, inv_id, db=db)
