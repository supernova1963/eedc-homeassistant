"""Konformität gegen `docs/KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md`.

**Was diese Datei ist:** die maschinelle Fassung des Konzepts. Jede Zelle der
Matrix aus §3 und jede Zusicherung aus §4/§5 wird an einer echten Anlage
durchgespielt und gegen die dort festgehaltene Erwartung geprüft.

**Warum sie existiert:** Das Konzept hält Entscheidungen fest, die mehrfach
gegen naheliegende Alternativen verteidigt werden mussten (§7 listet acht
verworfene Wege). Ein Dokument allein verhindert nicht, dass jemand die
Rechenweise „verbessert" — dieser Test tut es.

## Zwei Sorten von Proben, bewusst getrennt

* **ERFÜLLT** — die Erwartung des Konzepts ist gebaut. Harte Assertion.
* **OFFEN** — ein Bauschritt aus §8 steht noch aus. Die Probe hält den
  **heutigen** Zustand fest und nennt im Docstring den Soll-Zustand samt
  Schrittnummer. Wird der Schritt gefahren, **schlägt sie fehl** — und zwar
  genau dort, wo die Umstellung stattfindet. Das ist beabsichtigt: die Probe
  ist dann von „heutiger Zustand" auf „Konzept-Erwartung" umzustellen und ihr
  Eintrag aus ``BAUSCHRITTE_OFFEN`` zu entfernen.

⚠ **Eine fehlschlagende OFFEN-Probe ist deshalb kein Alarm, sondern eine
Quittung.** Wer sie „repariert", ohne den Eintrag zu entfernen, hat den
Bauschritt nur halb gefahren.

Kein ``xfail``: Das Muster gibt es im Baum nicht, die klassifizierte Offen-Liste
schon (``test_wurzelmuster_konformitaet.py``).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.api.routes.ha_export import calculate_anlage_sensors
from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

#: Bauschritte aus dem Konzept §8, die noch **nicht** gefahren sind.
#: Wird einer gebaut, fliegt sein Eintrag hier raus **und** die zugehörige
#: OFFEN-Probe wird auf die Konzept-Erwartung umgestellt.
BAUSCHRITTE_OFFEN: dict[int, str] = {
    1: "Ertragsfeld an der Investition pflegbar machen",
    2: "Prognose zieht die Investitions-Jahreswerte",
    3: "Monatsabschluss-Positionen werden nicht projiziert",
    # 4 ist gebaut (2026-08-10) — die Probe unten prüft jetzt die
    # Konzept-Erwartung statt den Ist-Zustand.
    5: "Amortisations-Fortschritt je Investition",
    6: "Dauer-Anzeige schreibt ihre Annahme aus",
    7: "Erträge zurück in den Nenner",
    8: "Zwei Daten-Checker-Regeln (§8.1)",
}

def _konzept_pfad() -> Path | None:
    """Das Konzept liegt im **SoT-Repo** unter `docs/`, eine Ebene über `eedc/`.

    ⚠ Im Standalone-Spiegel gibt es diese Doku-Sammlung nicht — dort
    synchronisiert `release.sh` nur `backend/` und `frontend/`, und das
    vorhandene `eedc/docs/` ist ein anderer Ordner. Die Meta-Proben
    **überspringen** dort, statt rot zu werden: ein Test darf keine
    Verzeichnis-Realität voraussetzen, die es in einem der beiden Repos nicht
    gibt ([[feedback_tests_ci_hermetisch]]).
    """
    for stufe in (3, 2):
        pfad = (
            Path(__file__).resolve().parents[stufe]
            / "docs"
            / "KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md"
        )
        if pfad.exists():
            return pfad
    return None

REPARATUR = 3000.0
THG_ERTRAG = 200.0
BETRIEBSKOSTEN_JAHR = 180.0


async def _anlage(
    db,
    *,
    monate: int = 12,
    jahr: int = 2025,
    mit_reparatur: bool = True,
    mit_ertrag: bool = True,
    betriebskosten: float = 0.0,
    allgemeine_ausgabe: float = 0.0,
    name: str = "Konzept",
) -> int:
    """Eine Anlage mit einer PV-Investition und wahlweise sonstigen Positionen.

    ``monate`` steuert die Länge der Historie — nur damit lässt sich die
    Stabilitäts-Zusicherung aus §5 (Modell A) überhaupt prüfen.
    """
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    for monat in range(1, monate + 1):
        j, m = jahr + (monat - 1) // 12, (monat - 1) % 12 + 1
        md = Monatsdaten(anlage_id=anlage.id, jahr=j, monat=m,
                         einspeisung_kwh=300.0, netzbezug_kwh=100.0)
        if allgemeine_ausgabe and monat == 1:
            # §3, dritte Zeile: die Position „für mehrere Komponenten" —
            # sie liegt auf der Monatsdaten-Zeile, nicht an einer Investition.
            md.sonstige_positionen = [
                {"bezeichnung": "Zählermiete", "betrag": allgemeine_ausgabe, "typ": "ausgabe"},
            ]
        db.add(md)

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
        leistung_kwp=10.0, anschaffungsdatum=date(jahr - 1, 1, 1),
        anschaffungskosten_gesamt=10000.0,
        betriebskosten_jahr=betriebskosten or None,
    )
    db.add(pv)
    await db.flush()

    positionen: list[dict] = []
    if mit_reparatur:
        positionen.append({"bezeichnung": "Reparatur", "betrag": REPARATUR, "typ": "ausgabe"})
    if mit_ertrag:
        positionen.append({"bezeichnung": "THG-Quote", "betrag": THG_ERTRAG, "typ": "ertrag"})

    for monat in range(1, monate + 1):
        j, m = jahr + (monat - 1) // 12, (monat - 1) % 12 + 1
        daten: dict = {"pv_erzeugung_kwh": 800.0}
        if monat == 1 and positionen:
            daten["sonstige_positionen"] = positionen
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=j, monat=m,
                                      verbrauch_daten=daten))
    await db.commit()
    return anlage.id


async def _roi(db, anlage_id: int):
    # Query-Defaults explizit (N-111).
    return await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )


# ===========================================================================
# ERFÜLLT — harte Assertions gegen die Konzept-Erwartung
# ===========================================================================


async def test_erfuellt_ausgabe_wirkt_im_kapitaleinsatz_nicht_im_zaehler(db):
    """§3, Zeile 3: Monatsabschluss + `typ: ausgabe` ⇒ Nenner, nicht Zähler."""
    mit = await _anlage(db, mit_reparatur=True, mit_ertrag=False, name="mit")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="ohne")

    r_mit, r_ohne = await _roi(db, mit), await _roi(db, ohne)

    # Der Nenner steigt um genau den Betrag …
    assert r_mit.gesamt_kapitaleinsatz - r_ohne.gesamt_kapitaleinsatz == pytest.approx(REPARATUR)
    # … und der Zähler bleibt unberührt.
    assert r_mit.gesamt_jahres_einsparung == pytest.approx(r_ohne.gesamt_jahres_einsparung)


async def test_erfuellt_ausgabe_wird_nicht_projiziert(db):
    """§3, Zeile 3 (Prognose ✘) und §5, Modell A.

    Der Kern von F-19: eine einmalige Reparatur darf **kein** künftiges
    Prognosejahr belasten.
    """
    mit = await _anlage(db, mit_reparatur=True, mit_ertrag=False, name="mit")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="ohne")

    p_mit = await get_finanz_prognose(anlage_id=mit, monate=12, db=db)
    p_ohne = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)

    assert p_mit.jahres_netto_ertrag_euro == pytest.approx(p_ohne.jahres_netto_ertrag_euro)


async def test_erfuellt_betriebskosten_wirken_im_zaehler_nicht_im_nenner(db):
    """§3, Zeile 1: Jahresbetrag an der Investition ⇒ Zähler, nie Kapitaleinsatz."""
    mit = await _anlage(db, mit_reparatur=False, mit_ertrag=False,
                        betriebskosten=BETRIEBSKOSTEN_JAHR, name="bk")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="ohne")

    r_mit, r_ohne = await _roi(db, mit), await _roi(db, ohne)

    assert r_mit.gesamt_kapitaleinsatz == pytest.approx(r_ohne.gesamt_kapitaleinsatz)
    assert r_ohne.gesamt_jahres_einsparung - r_mit.gesamt_jahres_einsparung == pytest.approx(
        BETRIEBSKOSTEN_JAHR
    )


async def test_erfuellt_zeitraum_bilanz_bleibt_unberuehrt(db):
    """§3, Kasten: der Netto-Ertrag ist die Bilanz und trägt **beide** Seiten.

    Wer diese Zahl gegen die Kapitalrechnung hält, sieht eine Drift, wo keine
    ist — deshalb ist sie hier ausdrücklich festgehalten.
    """
    mit = await _anlage(db, mit_reparatur=True, mit_ertrag=True, name="mit")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="ohne")

    def netto(sensoren):
        return next(s.value for s in sensoren if s.definition.key == "netto_ertrag_euro")

    from sqlalchemy import select
    a_mit = (await db.execute(select(Anlage).where(Anlage.id == mit))).scalar_one()
    a_ohne = (await db.execute(select(Anlage).where(Anlage.id == ohne))).scalar_one()

    diff = netto(await calculate_anlage_sensors(db, a_mit)) - netto(
        await calculate_anlage_sensors(db, a_ohne)
    )
    # Bilanz = Ertrag − Ausgabe, beides voll und ohne Annualisierung.
    assert diff == pytest.approx(THG_ERTRAG - REPARATUR)


async def test_erfuellt_dauer_ist_stabil_gegen_die_beobachtungsdauer(db):
    """§5, Modell A: dieselbe Reparatur, doppelte Historie ⇒ **dieselbe** Dauer.

    Das ist die Zusicherung, an der sich A und B unterscheiden: Modell B (die
    IST-Hochrechnung) läge bei 12 und 24 Monaten Historie deutlich
    auseinander, ohne dass ein neues Ereignis eingetreten wäre.
    """
    kurz = await _anlage(db, monate=12, mit_reparatur=True, mit_ertrag=False, name="kurz")
    lang = await _anlage(db, monate=24, mit_reparatur=True, mit_ertrag=False, name="lang")

    r_kurz, r_lang = await _roi(db, kurz), await _roi(db, lang)

    assert r_kurz.gesamt_kapitaleinsatz == pytest.approx(r_lang.gesamt_kapitaleinsatz)
    if r_kurz.gesamt_amortisation_jahre and r_lang.gesamt_amortisation_jahre:
        assert r_kurz.gesamt_amortisation_jahre == pytest.approx(
            r_lang.gesamt_amortisation_jahre, rel=0.02
        )


async def test_erfuellt_fortschritt_und_dauer_teilen_den_nenner(db):
    """§4: nur auf gemeinsamem Nenner lässt sich die eine Zahl in die andere
    überführen (N-137, hier um die Ausgaben-Seite erweitert)."""
    anlage_id = await _anlage(db, mit_reparatur=True, mit_ertrag=False)

    roi = await _roi(db, anlage_id)
    prognose = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    assert prognose.kapitaleinsatz_euro == pytest.approx(roi.gesamt_kapitaleinsatz)


# ===========================================================================
# OFFEN — heutiger Zustand festgehalten, Soll im Docstring
# ===========================================================================


async def test_offen_schritt3_ertrag_wird_heute_noch_projiziert(db):
    """§8/3 — **noch nicht gebaut.**

    SOLL: Eine sonstige Position aus dem Monatsabschluss wird **nicht** in die
    Zukunft projiziert — auch kein Ertrag (§3, Zeile 4, Prognose ✘).
    IST:  Der Ertrag fließt über den Monats-Schnitt in `jahres_sonstige_netto`
          und erhöht damit die Jahresprognose.

    Wird Schritt 3 gefahren, schlägt diese Probe fehl. Dann: Assertion auf
    Gleichheit umstellen und Eintrag 3 aus ``BAUSCHRITTE_OFFEN`` entfernen.
    """
    assert 3 in BAUSCHRITTE_OFFEN, "Schritt 3 gebaut? Dann diese Probe umstellen."

    mit = await _anlage(db, mit_reparatur=False, mit_ertrag=True, name="mit")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="ohne")

    p_mit = await get_finanz_prognose(anlage_id=mit, monate=12, db=db)
    p_ohne = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)

    assert p_mit.jahres_netto_ertrag_euro > p_ohne.jahres_netto_ertrag_euro


async def test_erfuellt_schritt4_allgemeine_position_wirkt_in_allen_sichten(db):
    """§8/4 · N-216 — **gebaut 2026-08-10.**

    Der Erfassungsort, den das Handbuch für „mehrere Komponenten" vorsieht, ist
    die **Monatsdaten-Zeile** (G19-1). Eine Position dort hat keine Investition
    und kann deshalb auf keiner ROI-Zeile stehen — sie wirkt auf die
    Gesamt-Zahlen, und dort in **allen** Sichten gleich.

    ⚑ Vor dem Bau bewegte eine anlagenweite Ausgabe von 3.000 € den
    Kapitaleinsatz von *Auswertungen → ROI* und der *Aussichten* um **0 €**,
    während der HA-Sensor sie voll trug (18.000 gegen 15.000). Genau diese
    Asymmetrie konnte `test_kapitaleinsatz_vier_sichten_symmetrie.py` nicht
    sehen: seine Fixture legt die Position **komponentengebunden** an.
    """
    assert 4 not in BAUSCHRITTE_OFFEN, "Schritt 4 wieder offen? Dann Docstring anpassen."

    mit = await _anlage(db, mit_reparatur=False, mit_ertrag=False,
                        allgemeine_ausgabe=500.0, name="allgemein")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="ohne")

    p_mit = await get_finanz_prognose(anlage_id=mit, monate=12, db=db)
    p_ohne = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)
    r_mit, r_ohne = await _roi(db, mit), await _roi(db, ohne)

    # Die Aussichten tragen sie im Nenner …
    assert p_mit.kapitaleinsatz_euro == pytest.approx(p_ohne.kapitaleinsatz_euro + 500.0)
    # … und *Auswertungen → ROI* trägt denselben Nenner (die Zusicherung, die
    # der Symmetrie-Wächter für komponentengebundene Positionen trifft).
    assert r_mit.gesamt_kapitaleinsatz == pytest.approx(r_ohne.gesamt_kapitaleinsatz + 500.0)
    assert r_mit.gesamt_kapitaleinsatz == pytest.approx(p_mit.kapitaleinsatz_euro)


async def test_offen_schritt7_ertrag_steht_heute_im_zaehler(db):
    """§8/7 — **noch nicht gebaut**, und die Reihenfolge ist zwingend (§9.1).

    SOLL: Auch der Ertrag mindert den Kapitaleinsatz (volle
          Vollkostenrechnung).
    IST:  Er erhöht die Jahres-Einsparung; der Nenner bleibt unberührt. Das ist
          ein **Zwischenstand**, kein Endzustand — solange es keinen Ort für
          *wiederkehrende* Erträge gibt (Schritt 1), müssen sie hier stehen.

    ⛔ Vor dem Umstellen: §9.1 lesen. Schritt 7 ändert die Wirkung
    **bestehender** Daten und setzt eine Anwender-Kommunikation voraus.
    """
    assert 7 in BAUSCHRITTE_OFFEN, "Schritt 7 gebaut? Dann diese Probe umstellen."

    mit = await _anlage(db, mit_reparatur=False, mit_ertrag=True, name="mit")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="ohne")

    r_mit, r_ohne = await _roi(db, mit), await _roi(db, ohne)

    assert r_mit.gesamt_kapitaleinsatz == pytest.approx(r_ohne.gesamt_kapitaleinsatz)
    assert r_mit.gesamt_jahres_einsparung > r_ohne.gesamt_jahres_einsparung


async def test_offen_schritt5_kein_fortschritt_je_investition(db):
    """§8/5 — **noch nicht gebaut**, Bedingung des Maintainers für Modell C.

    SOLL: Jede ROI-Zeile trägt neben der Dauer auch ihren gemessenen
          Fortschritt.
    IST:  Nur die Anlage hat einen Fortschritt; die Zeile trägt den **Nenner**
          dafür bereits (`kapitaleinsatz`), aber keinen kumulierten Ertrag.
    """
    assert 5 in BAUSCHRITTE_OFFEN, "Schritt 5 gebaut? Dann diese Probe umstellen."

    anlage_id = await _anlage(db, mit_reparatur=True, mit_ertrag=False)
    roi = await _roi(db, anlage_id)
    zeile = roi.berechnungen[0]

    assert zeile.kapitaleinsatz > 0, "der Nenner je Zeile liegt vor"
    assert not hasattr(zeile, "fortschritt_prozent")


# ===========================================================================
# Meta — Test und Konzept dürfen nicht auseinanderlaufen
# ===========================================================================


def test_meta_offene_bauschritte_stehen_im_konzept():
    """Jeder hier als offen geführte Schritt muss im Konzept §8 vorkommen.

    Verhindert die Drift, an der Statusköpfe im Projekt schon zweimal
    gescheitert sind: eine Liste, die niemand gegen ihre Quelle hält.
    """
    konzept = _konzept_pfad()
    if konzept is None:
        pytest.skip("Konzept-Dokument nur im SoT-Repo vorhanden")
    text = konzept.read_text(encoding="utf-8")
    assert "## 8. Was noch fehlt — die Bauliste" in text, "Konzept-Abschnitt umbenannt?"

    for nummer, beschreibung in BAUSCHRITTE_OFFEN.items():
        assert f"| {nummer} |" in text, (
            f"Bauschritt {nummer} ({beschreibung}) fehlt in der Bauliste des Konzepts"
        )


def test_meta_konzept_nennt_die_verworfenen_wege():
    """§7 ist der Grund, warum es dieses Papier gibt — er darf nicht wegfallen.

    Die acht Einträge sind einzeln gemessen worden; verschwindet einer, kehrt
    der zugehörige Vorschlag beim nächsten Mal zurück.
    """
    konzept = _konzept_pfad()
    if konzept is None:
        pytest.skip("Konzept-Dokument nur im SoT-Repo vorhanden")
    text = konzept.read_text(encoding="utf-8")
    for stichwort in (
        "Restwert als sonstiger",
        "Kostenumbuchung",
        "Nullsumme",
        "`einmalig`",
        "art: aufwand",
        "Instandhaltungsrücklage",
        "Modell B",
    ):
        assert stichwort in text, f"verworfener Weg nicht mehr dokumentiert: {stichwort}"
