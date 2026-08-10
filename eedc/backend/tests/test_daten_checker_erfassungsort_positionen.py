"""Daten-Checker §8.1 — der Erfassungsort ist die einzige Fehleingabe-Stelle.

Das Wirtschaftlichkeits-Modell rät nichts: die **Form** der Zahl sagt, ob sie
wiederkehrt (Jahresbetrag an der Investition) oder einmal wirkt (Position im
Monatsabschluss, ``docs/KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md`` §2). Genau
deshalb kann ein Anwender das Modell **nur dort** verfehlen — und nur dort ist
es erkennbar.

⚠ **Erkannt wird Wiederholung, nie Bedeutung.** Aus „Restwert", „Verkauf" oder
„Förderung" auf einen Kapitalzufluss zu schließen wäre eine erfundene Regel
über Freitext (§8.1, ⛔-Kasten) — dieselbe Klasse, die das Konzept mit ``art``
und ``einmalig`` bereits verworfen hat (§7). Die letzte Probe hält das fest.

Gesichert wird:
- Wiederholung ohne Jahresbetrag ⇒ Hinweis „gehört als Jahresbetrag".
- Jahresbetrag + Wiederholung ⇒ Hinweis „Doppelerfassung" — und **nur** dieser
  (ein Sachverhalt, eine Meldung).
- Unter der Schwelle ⇒ Schweigen (eine einmalige Reparatur ist kein Muster).
- **Kein Hinweis ohne Ort (P-6):** das Ertragsfeld gibt es nur bei Wallbox und
  Sonstiges; bei allen anderen Typen bliebe die Anleitung im Leeren.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.services.daten_checker import CheckKategorie, CheckSeverity, DatenChecker


async def _anlage_mit(
    db,
    *,
    typ: str = "waermepumpe",
    betriebskosten: float | None = None,
    ertrag_jahr: float | None = None,
    bezeichnung: str = "Wartung",
    richtung: str = "ausgabe",
    monate: int = 3,
    kategorie: str | None = None,
) -> int:
    anlage = Anlage(anlagenname="Erfassungsort", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    inv = Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung="Gerät",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=10000.0,
        betriebskosten_jahr=betriebskosten,
        einsparung_prognose_jahr=ertrag_jahr,
        parameter={"kategorie": kategorie} if kategorie else {},
    )
    db.add(inv)
    await db.flush()

    for monat in range(1, monate + 1):
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2025, monat=monat,
            verbrauch_daten={"sonstige_positionen": [
                {"bezeichnung": bezeichnung, "betrag": 60.0, "typ": richtung},
            ]},
        ))
    await db.commit()
    return anlage.id


async def _befunde(db, anlage_id: int, kategorie: CheckKategorie):
    ergebnis = await DatenChecker(db).check_anlage(anlage_id)
    return [e for e in ergebnis.ergebnisse if e.kategorie == kategorie.value]


async def test_wiederkehrende_position_wird_gemeldet(db):
    """§8.1 Regel 1: dieselbe Bezeichnung in ≥ 3 Monaten, kein Jahresbetrag."""
    anlage_id = await _anlage_mit(db, monate=3)

    treffer = await _befunde(db, anlage_id, CheckKategorie.POSITION_WIEDERKEHREND)

    assert len(treffer) == 1
    assert treffer[0].schwere == CheckSeverity.INFO
    assert "Wartung" in treffer[0].meldung
    # Der Weg zur Behebung steht dabei — kein „Akzeptiert"-Knopf.
    assert "Betriebskosten/Jahr" in (treffer[0].details or "")
    # Der Komponenten-Hub filtert je Gerät (IA-V4 #243).
    assert treffer[0].investition_id is not None


async def test_einmaliges_bleibt_still(db):
    """Zwei Monate sind kein Muster — sonst meldete jede zweite Reparatur.

    Das ist die P-6-Linie: ein Hinweis, der keinen Fehler beschreibt, ist
    schlimmer als keiner.
    """
    anlage_id = await _anlage_mit(db, monate=2)

    assert await _befunde(db, anlage_id, CheckKategorie.POSITION_WIEDERKEHREND) == []
    assert await _befunde(db, anlage_id, CheckKategorie.POSITION_DOPPELERFASSUNG) == []


async def test_doppelerfassung_schlaegt_die_wiederholungs_meldung(db):
    """§8.1 Regel 2 — und **nur** sie: ein Sachverhalt, eine Meldung.

    Mit gepflegtem Jahresbetrag ist der Rat „trag es als Jahresbetrag ein"
    falsch — er ist längst eingetragen. Richtig ist: im Monatsabschluss gehört
    nur die Abweichung vom Plan (§2/3).
    """
    anlage_id = await _anlage_mit(db, betriebskosten=180.0, monate=3)

    doppel = await _befunde(db, anlage_id, CheckKategorie.POSITION_DOPPELERFASSUNG)
    assert len(doppel) == 1
    # Deutsche Schreibweise — die Meldung ist Anzeige (Regel 0a). ⚠ Der
    # Wächter `check:de-de` liest nur `frontend/src` und kann sie nicht sehen
    # (N-203), deshalb steht die Probe hier.
    assert "180,00 €" in (doppel[0].details or "")
    assert "Abweichung" in (doppel[0].details or "")
    assert await _befunde(db, anlage_id, CheckKategorie.POSITION_WIEDERKEHREND) == []


async def test_doppelerfassung_greift_schon_ab_zwei_monaten(db):
    """Bei gepflegtem Jahresbetrag ist die zweite Buchung bereits das Muster.

    ⚠ Das Konzept nennt für diese Regel **keine** Schwelle („gleichnamige
    Monatsposition"). Ohne Schwelle meldete sie jede einzelne Reparatur neben
    einer gepflegten Versicherung — deshalb ≥ 2, während die Regel ohne
    Jahresbetrag bei ≥ 3 bleibt.
    """
    anlage_id = await _anlage_mit(db, betriebskosten=180.0, monate=2)

    assert len(await _befunde(db, anlage_id, CheckKategorie.POSITION_DOPPELERFASSUNG)) == 1


@pytest.mark.parametrize("typ,erwartet", [("sonstiges", 1), ("waermepumpe", 0)])
async def test_ertragsseite_nur_wo_es_das_feld_gibt(db, typ, erwartet):
    """P-6: kein Hinweis, den niemand auflösen kann.

    „Ertrag/Jahr" gibt es nur bei Wallbox und Sonstiges
    (``models/investition.py::ERTRAGSFELD_TYPEN``) — bei allen anderen Typen
    rechnet eedc die Jahres-Einsparung selbst, und der Rat verwiese auf ein
    Feld, das der Anwender im Formular nicht findet.
    """
    anlage_id = await _anlage_mit(db, typ=typ, richtung="ertrag",
                                  bezeichnung="Einspeisung WR 2", monate=4)

    treffer = await _befunde(db, anlage_id, CheckKategorie.POSITION_WIEDERKEHREND)
    assert len(treffer) == erwartet
    if erwartet:
        assert "Ertrag/Jahr" in (treffer[0].details or "")


async def test_bedeutung_wird_nicht_geraten(db):
    """§8.1, ⛔-Kasten: „Restwert" ist ein Wort, kein Signal.

    Eine einzelne Position mit einer bedeutungsschweren Bezeichnung löst
    nichts aus — was zählt, ist ausschließlich die Wiederholung.
    """
    anlage_id = await _anlage_mit(db, bezeichnung="Restwert alter Speicher",
                                  richtung="ertrag", typ="sonstiges", monate=1)

    assert await _befunde(db, anlage_id, CheckKategorie.POSITION_WIEDERKEHREND) == []
    assert await _befunde(db, anlage_id, CheckKategorie.POSITION_DOPPELERFASSUNG) == []


async def test_erzeuger_wird_auf_den_einspeise_erloes_verwiesen(db):
    """Bauschritt 9 hat den besseren Ort geschaffen — der Hinweis nennt ihn.

    Für einen Erzeuger ist „Ertrag/Jahr" nur die zweitbeste Antwort: das Feld
    **Einspeise-Erlös (€)** nimmt den echten Monatswert aus einem HA-Sensor,
    statt einen Jahresbetrag schätzen zu lassen. Genau der Fall aus Konzept §9
    (zweiter Erzeuger mit eigenem Einspeisetarif) darf nicht auf den
    Schätzweg geschickt werden.
    """
    anlage_id = await _anlage_mit(db, typ="sonstiges", kategorie="erzeuger",
                                  richtung="ertrag", bezeichnung="Einspeisung WR 2",
                                  monate=4)

    treffer = await _befunde(db, anlage_id, CheckKategorie.POSITION_WIEDERKEHREND)
    assert len(treffer) == 1
    assert "Einspeise-Erlös" in (treffer[0].details or "")
    assert "Ertrag/Jahr" not in (treffer[0].details or "")
