"""#351 — die Kopplung eines Speichers ist eine Eigenschaft, keine Folgerung.

Bis v4.0.8 leitete eedc die Kopplung ausschließlich aus `parent_investition_id`
ab: Speicher am Wechselrichter ⇒ DC, sonst AC. Als *Vorbelegung* ist das
richtig, als *Wahrheit* falsch — zwei reale Konstellationen fielen durch
(JayJay, Forum v4.0.0):

* **AC-Speicher am Hybrid-Wechselrichter** — wurde zwangsweise DC, sobald man
  ihn zuordnete;
* **DC-Speicher ohne erfassten Wechselrichter** — wurde als AC geführt.

Was diese Tests **nicht** prüfen, weil es bewusst so gebaut ist: dass sich eine
Zahl ändert. Die Gruppierung (und damit die Wirtschaftlichkeit) hängt weiter
allein an der Zuordnung; `berechne_speicher_einsparung` rechnet für beide Fälle
identisch. Geändert hat sich die **Aussage** — die Gegenprobe dazu steht unten
(`test_kopplung_aendert_die_gruppierung_nicht`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.core.field_definitions import INVESTITION_FELDER
from backend.core.investition_kennwerte import (
    get_speicher_kopplung,
    get_speicher_kopplung_gepflegt,
)
from backend.models import Anlage, Investition, Monatsdaten


def _speicher(kopplung=None, parent=None):
    """Investitions-Attrappe — der Helper liest nur `parameter` und den Parent."""
    parameter = {} if kopplung is None else {"kopplung": kopplung}
    return SimpleNamespace(parameter=parameter, parent_investition_id=parent)


# ============================================================================
# Der SoT-Helper: gepflegt schlägt abgeleitet
# ============================================================================


def test_ungepflegt_folgt_der_zuordnung():
    """Ohne gepflegtes Feld bleibt es beim bisherigen Verhalten."""
    assert get_speicher_kopplung(_speicher(parent=7)) == "dc"
    assert get_speicher_kopplung(_speicher(parent=None)) == "ac"


def test_ac_speicher_am_hybrid_wechselrichter():
    """JayJays Fall: zugeordnet (⇒ Ableitung DC), gepflegt ist aber AC."""
    inv = _speicher(kopplung="ac", parent=7)
    assert get_speicher_kopplung(inv) == "ac"
    assert get_speicher_kopplung_gepflegt(inv) == "ac"


def test_dc_speicher_ohne_erfassten_wechselrichter():
    """Die zweite Konstellation des Issues — Gegenrichtung derselben Lücke."""
    assert get_speicher_kopplung(_speicher(kopplung="dc", parent=None)) == "dc"


def test_gross_kleinschreibung_und_leerzeichen():
    """Ein Import darf nicht an „DC " scheitern."""
    assert get_speicher_kopplung(_speicher(kopplung=" DC ", parent=None)) == "dc"


def test_unbekannter_wert_faellt_in_die_ableitung():
    """Müll im Feld kippt die Auflösung nicht — er gilt als ungepflegt.

    Bewusst kein Fehler: ein Altbestand mit Tippfehler soll die Anzeige nicht
    lahmlegen, sondern in das Verhalten von vorher fallen.
    """
    inv = _speicher(kopplung="hybrid", parent=7)
    assert get_speicher_kopplung_gepflegt(inv) is None
    assert get_speicher_kopplung(inv) == "dc"


def test_gepflegt_meldet_nur_echte_pflege():
    """`get_speicher_kopplung_gepflegt` unterscheidet Aussage von Ableitung."""
    assert get_speicher_kopplung_gepflegt(_speicher(parent=7)) is None
    assert get_speicher_kopplung_gepflegt(_speicher(kopplung="dc")) == "dc"


# ============================================================================
# N-60: die Messstelle steht im Feld-Vertrag
# ============================================================================


def test_lade_und_entladefeld_nennen_die_messstelle():
    """Ohne Messstelle sind DC- und AC-Zähler beide vertragskonform (N-60).

    Genau daran hing die Anker-Beobachtung: Ladung DC-seitig, Entladung
    AC-seitig — dazwischen liegt die Wandlung, und der daraus gerechnete
    Wirkungsgrad misst die Messstelle statt den Speicher.
    """
    felder = {f["feld"]: f for f in INVESTITION_FELDER["speicher"]}
    ladung = felder["ladung_kwh"]["hinweis"]
    entladung = felder["entladung_kwh"]["hinweis"]
    assert "Kopplung" in ladung
    assert "Batterie-Wechselrichter" in ladung and "Batterie-Anschluss" in ladung
    # Die Entladung darf nicht schweigen — sonst ist genau die gemischte
    # Messung wieder vertragskonform, die den Fund ausgelöst hat.
    assert "Messstelle" in entladung


# ============================================================================
# Ausgeliefert: die ROI-Antwort behauptet nichts mehr, was niemand erhoben hat
# ============================================================================


async def _anlage_mit_speicher(db, *, parent_wr: bool, parameter: dict):
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    parent_id = None
    if parent_wr:
        wr = Investition(
            anlage_id=anlage.id, typ="wechselrichter", bezeichnung="Hybrid-WR",
            anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=2000.0,
        )
        db.add(wr)
        await db.flush()
        parent_id = wr.id
    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
        parent_investition_id=parent_id, parameter={"kapazitaet_kwh": 10.0, **parameter},
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=8000.0,
    )
    db.add(speicher)
    await db.flush()
    return anlage, speicher


async def _roi(db, anlage_id):
    return await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0,
        benzinpreis_euro=None, jahr=2026, db=db,
    )


async def test_zugeordneter_ac_speicher_meldet_ac(db):
    """Der Fall, für den das Issue geschrieben wurde — jetzt sichtbar korrekt."""
    anlage, speicher = await _anlage_mit_speicher(db, parent_wr=True, parameter={"kopplung": "ac"})
    result = await _roi(db, anlage.id)
    system = next(b for b in result.berechnungen if b.investition_typ == "pv-system")
    komp = next(k for k in system.komponenten if k.investition_id == speicher.id)
    assert komp.detail["kopplung"] == "ac"
    assert komp.detail["kopplung_gepflegt"] is True
    # Das alte Feld sagt jetzt die Wahrheit statt konstant `True`.
    assert komp.detail["dc_gekoppelt"] is False


async def test_zugeordneter_speicher_ohne_pflege_bleibt_dc(db):
    """Ohne Angabe ändert sich nichts — Bestandsverhalten, aber als Ableitung markiert."""
    anlage, speicher = await _anlage_mit_speicher(db, parent_wr=True, parameter={})
    result = await _roi(db, anlage.id)
    system = next(b for b in result.berechnungen if b.investition_typ == "pv-system")
    komp = next(k for k in system.komponenten if k.investition_id == speicher.id)
    assert komp.detail["dc_gekoppelt"] is True
    assert komp.detail["kopplung"] == "dc"
    assert komp.detail["kopplung_gepflegt"] is False


async def test_eigenstaendiger_speicher_behauptet_keine_kopplung_mehr(db):
    """Der Hinweis nannte hier „AC-gekoppelter Speicher" — eine nie erhobene Aussage.

    Er beschreibt jetzt die **Rechnung** (eigenständig geführt), die Kopplung
    steht in ihrem eigenen Feld — hier gepflegt als DC, obwohl kein
    Wechselrichter erfasst ist.
    """
    anlage, _ = await _anlage_mit_speicher(db, parent_wr=False, parameter={"kopplung": "dc"})
    result = await _roi(db, anlage.id)
    speicher_zeile = next(b for b in result.berechnungen if b.investition_typ == "speicher")
    assert "gekoppelt" not in speicher_zeile.detail_berechnung["hinweis"]
    assert speicher_zeile.detail_berechnung["kopplung"] == "dc"
    assert speicher_zeile.detail_berechnung["kopplung_gepflegt"] is True


async def test_kopplung_aendert_die_gruppierung_nicht(db):
    """Gegenprobe (absichtlich gegen beide Stände grün): die Struktur bleibt.

    Ein als AC gepflegter Speicher am Wechselrichter wird **weiterhin** als
    Komponente des PV-Systems gerechnet — die Zuordnung ist die Struktur-
    Information, die Kopplung die Bauform. Wäre das nicht so, bewegte dieses
    Paket eine ausgelieferte ROI-Zahl.
    """
    anlage, speicher = await _anlage_mit_speicher(db, parent_wr=True, parameter={"kopplung": "ac"})
    result = await _roi(db, anlage.id)
    # Keine eigene ROI-Zeile für den Speicher — er steckt im PV-System.
    assert not [b for b in result.berechnungen if b.investition_id == speicher.id]
    system = next(b for b in result.berechnungen if b.investition_typ == "pv-system")
    assert any(k.investition_id == speicher.id for k in system.komponenten)
