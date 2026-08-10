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
from backend.api.routes.import_export.json_operations import InvestitionExport
from backend.api.routes.investitionen.crud import (
    InvestitionCreate,
    InvestitionUpdate,
    create_investition,
    get_roi_dashboard,
    update_investition,
)
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

#: Bauschritte aus dem Konzept §8, die noch **nicht** gefahren sind.
#: Wird einer gebaut, fliegt sein Eintrag hier raus **und** die zugehörige
#: OFFEN-Probe wird auf die Konzept-Erwartung umgestellt.
BAUSCHRITTE_OFFEN: dict[int, str] = {
    # 1, 2 und 3 sind gebaut (2026-08-10) — die Proben unten prüfen jetzt die
    # Konzept-Erwartung statt den Ist-Zustand.
    # 4 ist gebaut (2026-08-10) — die Probe unten prüft jetzt die
    # Konzept-Erwartung statt den Ist-Zustand.
    # 5 ist gebaut (2026-08-10): der anlagenweite Zähler wird auf die ROI-Zeilen
    # zerlegt (`core/berechnungen/ertrag_zerlegung.py`), N-228 fuhr zwangsläufig
    # mit — ohne die laufzeitgewichteten Betriebskosten ging die Summe nicht auf.
    # 6 ist gebaut (2026-08-10): die Annahme kommt aus dem Layer-SoT
    # `kapitalrechnung.annahme_dauer_text` und richtet sich nach den Daten
    # (Modell A ohne, Modell C mit gepflegten Betriebskosten).
    # 9 ist gebaut (2026-08-10): Feld `einspeise_erloes_euro` an
    # *Sonstiges/Erzeuger*, durchgereicht bis in alle vier Sichten. Eigene
    # Proben in `test_erzeuger_einspeise_erloes.py`.
    # 7 ist gebaut (2026-08-10) — als LETZTER der Bauliste: die sonstigen
    # ERTRÄGE mindern den Kapitaleinsatz, spiegelbildlich zu F-19 auf der
    # Ausgabenseite. Beide Vorbedingungen aus §9.1 waren erfüllt (Umstiegsweg
    # §8/1 + §8/9, Kommunikation §11 an #310 am 10.08.).
    # 8 ist gebaut (2026-08-10): `daten_checker/monatsdaten.py::ErfassungsortChecks`,
    # eigene Proben in `test_daten_checker_erfassungsort_positionen.py`.
}
#: ⚑ **Das Dict ist leer — die Bauliste §8 ist abgearbeitet.** Wer hier wieder
#: einen Eintrag anlegt, eröffnet einen neuen Bauschritt und trägt ihn ins
#: Konzept ein; das Papier ist der SoT, dieses Dict der Stand.

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
#: Anlagenweite Position (Monatsdaten-Zeile, §8/4) — sie hat KEINE Investition
#: und landet deshalb im nicht zurechenbaren Rest der Zerlegung (§8/5).
ALLGEMEINE_AUSGABE = 500.0
#: Dasselbe in der Ertrags-Richtung — nur DIESE erzeugt einen Rest (s. Fixture).
ALLGEMEINER_ERTRAG = 400.0
THG_ERTRAG = 200.0
BETRIEBSKOSTEN_JAHR = 180.0
ERTRAG_JAHR = 500.0


async def _anlage(
    db,
    *,
    monate: int = 12,
    jahr: int = 2025,
    mit_reparatur: bool = True,
    mit_ertrag: bool = True,
    betriebskosten: float = 0.0,
    allgemeine_ausgabe: float = 0.0,
    allgemeiner_ertrag: float = 0.0,
    ertrag_jahr: float = 0.0,
    modul_erzeugung: bool = True,
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
        if (allgemeine_ausgabe or allgemeiner_ertrag) and monat == 1:
            # §3, dritte Zeile: die Position „für mehrere Komponenten" —
            # sie liegt auf der Monatsdaten-Zeile, nicht an einer Investition.
            md.sonstige_positionen = [
                p for p in (
                    {"bezeichnung": "Zählermiete", "betrag": allgemeine_ausgabe, "typ": "ausgabe"}
                    if allgemeine_ausgabe else None,
                    # ⚑ Seit **Bauschritt 7** sind beide Richtungen symmetrisch:
                    # Ausgabe wie Ertrag stehen im Nenner und werden im Zähler
                    # herausgerechnet — sie heben sich dort auf. Bis 2026-08-10
                    # blieb der Ertrag im Zähler stehen und war deshalb der
                    # **Rest** der Zerlegung (§8/5); das ist er nicht mehr.
                    {"bezeichnung": "Förderung", "betrag": allgemeiner_ertrag, "typ": "ertrag"}
                    if allgemeiner_ertrag else None,
                ) if p
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

    if ertrag_jahr:
        # §3, Zeile 2: der Jahresbetrag an der Investition auf der
        # Ertragsseite. Bewusst mit Anschaffungskosten 0 — sonst bewegte die
        # Probe den Nenner mit und könnte den Zähler-Effekt nicht isolieren.
        db.add(Investition(
            anlage_id=anlage.id, typ="sonstiges", bezeichnung="Zweiter Erzeuger",
            anschaffungsdatum=date(jahr - 1, 1, 1),
            anschaffungskosten_gesamt=0.0,
            einsparung_prognose_jahr=ertrag_jahr,
        ))
        await db.flush()

    positionen: list[dict] = []
    if mit_reparatur:
        positionen.append({"bezeichnung": "Reparatur", "betrag": REPARATUR, "typ": "ausgabe"})
    if mit_ertrag:
        positionen.append({"bezeichnung": "THG-Quote", "betrag": THG_ERTRAG, "typ": "ertrag"})

    for monat in range(1, monate + 1):
        j, m = jahr + (monat - 1) // 12, (monat - 1) % 12 + 1
        # ⚑ `modul_erzeugung=False` bildet den Anwender ab, der nur seinen
        # Einspeisezähler pflegt: es gibt einen Einspeise-Erlös, aber **keine**
        # gemessene Erzeugung je Modul. Die Zerlegung (§8/5) hat dann keinen
        # Schlüssel und lässt den Betrag im Rest stehen, statt eine Messung zu
        # erfinden — die einzige verbliebene Rest-Quelle, seit Bauschritt 7 die
        # anlagenweiten Positionen in den Nenner gezogen hat.
        daten: dict = {"pv_erzeugung_kwh": 800.0} if modul_erzeugung else {}
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


async def test_erfuellt_schritt1_ertragsfeld_ist_pflegbar(db):
    """§8/1 — **gebaut 2026-08-10.**

    Das Feld `einsparung_prognose_jahr` existierte seit jeher und wurde vom
    ROI-Dashboard gelesen, hatte aber **keinen Schreiber**: kein Formular, kein
    Import, kein Create-/Update-Schema (N-213 — im PDF stand deshalb „—").
    Diese Probe prüft den Schreibweg, nicht die Spalte: sie geht durch
    dieselben Pydantic-Schemas wie die Route.
    """
    assert 1 not in BAUSCHRITTE_OFFEN, "Schritt 1 wieder offen? Dann Docstring anpassen."

    # Anlegen …
    daten = InvestitionCreate(
        anlage_id=await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="schreibweg"),
        typ="sonstiges", bezeichnung="Zweiter Erzeuger",
        einsparung_prognose_jahr=ERTRAG_JAHR,
    )
    inv = await create_investition(data=daten, db=db)
    assert inv.einsparung_prognose_jahr == pytest.approx(ERTRAG_JAHR)

    # … und ändern. `exclude_unset` darf den Wert nicht verschlucken.
    geaendert = await update_investition(
        investition_id=inv.id,
        data=InvestitionUpdate(einsparung_prognose_jahr=ERTRAG_JAHR * 2),
        db=db,
    )
    assert geaendert.einsparung_prognose_jahr == pytest.approx(ERTRAG_JAHR * 2)

    # Und er überlebt ein Backup: der JSON-Export trägt ihn, sonst wäre er
    # nach einem Restore wieder das, was er vorher war — leer.
    assert "einsparung_prognose_jahr" in InvestitionExport.model_fields


async def test_erfuellt_schritt2_jahresertrag_wirkt_in_der_prognose(db):
    """§8/2 · §3 Zeile 2 — **gebaut 2026-08-10.**

    Ein Jahresbetrag an der Investition ist per FORM wiederkehrend (§2/1): er
    wirkt jährlich, **ungeteilt und ohne Hochrechnung**. Geprüft werden die
    drei Sichten, die eine Jahresgröße ausweisen — sie müssen sich um genau
    denselben Betrag bewegen (die „vier Sichten, eine Zahl"-Zusicherung, hier
    auf der Zählerseite).
    """
    assert 2 not in BAUSCHRITTE_OFFEN, "Schritt 2 wieder offen? Dann Docstring anpassen."

    mit = await _anlage(db, mit_reparatur=False, mit_ertrag=False,
                        ertrag_jahr=ERTRAG_JAHR, name="ertrag")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="ohne")

    # (1) Aussichten — Jahres-Netto-Ertrag
    p_mit = await get_finanz_prognose(anlage_id=mit, monate=12, db=db)
    p_ohne = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)
    assert p_mit.jahres_netto_ertrag_euro == pytest.approx(
        p_ohne.jahres_netto_ertrag_euro + ERTRAG_JAHR
    )

    # (2) Auswertungen → ROI
    r_mit, r_ohne = await _roi(db, mit), await _roi(db, ohne)
    assert r_mit.gesamt_jahres_einsparung == pytest.approx(
        r_ohne.gesamt_jahres_einsparung + ERTRAG_JAHR
    )

    # (3) HA-Sensor `jahres_ersparnis_euro` — ohne ihn zeigte Home Assistant
    # eine andere Amortisation als die Oberfläche.
    from sqlalchemy import select
    a_mit = (await db.execute(select(Anlage).where(Anlage.id == mit))).scalar_one()
    a_ohne = (await db.execute(select(Anlage).where(Anlage.id == ohne))).scalar_one()

    def jahres_ersparnis(sensoren):
        return next(
            (s.value for s in sensoren if s.definition.key == "jahres_ersparnis_euro"),
            None,
        )

    s_mit = jahres_ersparnis(await calculate_anlage_sensors(db, a_mit))
    s_ohne = jahres_ersparnis(await calculate_anlage_sensors(db, a_ohne))
    assert s_mit is not None and s_ohne is not None
    assert s_mit == pytest.approx(s_ohne + ERTRAG_JAHR)

    # … und der Kapitaleinsatz bleibt unberührt: ein Ertrag ist kein Kapital
    # (§3, Zeile 2, Spalte „Kapitaleinsatz" = „—").
    assert r_mit.gesamt_kapitaleinsatz == pytest.approx(r_ohne.gesamt_kapitaleinsatz)


async def test_erfuellt_schritt2_typ_grenze_haelt_prognose_und_roi_zusammen(db):
    """§8/1+2, `ERTRAGSFELD_TYPEN`: derselbe Wert an einem selbst gerechneten
    Typ darf **nirgends** wirken.

    ⚠ Diese Probe gibt es, weil ein Sprengsatz stumm blieb: die Typ-Grenze
    aufzuheben veränderte keine der übrigen Proben, denn ihre Fixture pflegt
    das Feld nur an einer `sonstiges`-Investition. Ohne die Grenze zählte die
    Prognose einen Wert, den *Auswertungen → ROI* für eine PV-Zeile gar nicht
    liest — zwei Zahlen für dieselbe Größe, die Klasse aus §8/4.
    """
    mit = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="pv-ertrag")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="ohne")

    from sqlalchemy import select
    pv = (await db.execute(
        select(Investition).where(
            Investition.anlage_id == mit, Investition.typ == "pv-module"
        )
    )).scalars().first()
    pv.einsparung_prognose_jahr = ERTRAG_JAHR
    await db.commit()

    p_mit = await get_finanz_prognose(anlage_id=mit, monate=12, db=db)
    p_ohne = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)
    assert p_mit.jahres_netto_ertrag_euro == pytest.approx(p_ohne.jahres_netto_ertrag_euro)

    r_mit, r_ohne = await _roi(db, mit), await _roi(db, ohne)
    assert r_mit.gesamt_jahres_einsparung == pytest.approx(r_ohne.gesamt_jahres_einsparung)


# ===========================================================================
# OFFEN — heutiger Zustand festgehalten, Soll im Docstring
# ===========================================================================


async def test_erfuellt_schritt3_ertrag_wird_nicht_projiziert(db):
    """§8/3 · §3 Zeile 4 (Prognose ✘) — **gebaut 2026-08-10.**

    Eine Position im Monatsabschluss ist per Form **einmal** geflossen (§2/2).
    Bis dahin lief sie über den Monats-Schnitt in `jahres_sonstige_netto` und
    erhöhte damit **jedes** künftige Prognosejahr — spiegelbildlich zu F-19 auf
    der Ausgabenseite.

    ⛔ Die Reihenfolge war zwingend: vor §8/1 gab es keinen Ort für einen
    *wiederkehrenden* Ertrag (#310), und dieser Schritt hätte ihn ersatzlos
    entfernt.

    Geprüft werden beide Prognose-Sichten. Der **Fortschritt** ist bewusst
    nicht Teil der Probe: er ist Messung (§4) und trägt die Erträge weiter.
    """
    assert 3 not in BAUSCHRITTE_OFFEN, "Schritt 3 wieder offen? Dann Docstring anpassen."

    mit = await _anlage(db, mit_reparatur=False, mit_ertrag=True, name="mit")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="ohne")

    p_mit = await get_finanz_prognose(anlage_id=mit, monate=12, db=db)
    p_ohne = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)
    assert p_mit.jahres_netto_ertrag_euro == pytest.approx(p_ohne.jahres_netto_ertrag_euro)

    # Auswertungen → ROI zieht denselben Schluss …
    r_mit, r_ohne = await _roi(db, mit), await _roi(db, ohne)
    assert r_mit.gesamt_jahres_einsparung == pytest.approx(r_ohne.gesamt_jahres_einsparung)

    # … und der HA-Sensor `jahres_ersparnis_euro` ebenso: er bildet seine
    # Jahresgröße selbst und hätte die Position sonst weiter hochgerechnet.
    from sqlalchemy import select
    a_mit = (await db.execute(select(Anlage).where(Anlage.id == mit))).scalar_one()
    a_ohne = (await db.execute(select(Anlage).where(Anlage.id == ohne))).scalar_one()

    def jahres_ersparnis(sensoren):
        return next(
            (s.value for s in sensoren if s.definition.key == "jahres_ersparnis_euro"),
            None,
        )

    assert jahres_ersparnis(await calculate_anlage_sensors(db, a_mit)) == pytest.approx(
        jahres_ersparnis(await calculate_anlage_sensors(db, a_ohne))
    )


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


async def test_erfuellt_schritt7_ertrag_mindert_den_kapitaleinsatz(db):
    """§8/7 · §3, Zeile 4 — **gebaut 2026-08-10**, als letzter der Bauliste.

    SOLL (jetzt IST): der Ertrag mindert den Kapitaleinsatz, und zwar in
    **beiden** Sichten mit demselben Nenner. Der **Zähler** bleibt unberührt —
    er hat die Position seit §8/3 ohnehin nicht mehr.

    ⚠ Diese Probe hieß bis 2026-08-10 `test_offen_schritt7_…` und prüfte das
    **Gegenteil** (Nenner unberührt). Umgeschrieben statt „repariert" — genau
    so steht es in der Bauliste.
    """
    assert 7 not in BAUSCHRITTE_OFFEN, "Schritt 7 wieder offen? Dann Docstring anpassen."

    mit = await _anlage(db, mit_reparatur=False, mit_ertrag=True, name="mit")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="ohne")

    r_mit, r_ohne = await _roi(db, mit), await _roi(db, ohne)
    assert r_ohne.gesamt_kapitaleinsatz - r_mit.gesamt_kapitaleinsatz == pytest.approx(
        THG_ERTRAG
    )
    # Der Zähler bleibt gleich — die Position wirkt genau einmal (§8/3).
    assert r_mit.gesamt_jahres_einsparung == pytest.approx(r_ohne.gesamt_jahres_einsparung)

    p_mit = await get_finanz_prognose(anlage_id=mit, monate=12, db=db)
    p_ohne = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)
    assert p_ohne.kapitaleinsatz_euro - p_mit.kapitaleinsatz_euro == pytest.approx(THG_ERTRAG)
    assert p_mit.kapitaleinsatz_euro == pytest.approx(r_mit.gesamt_kapitaleinsatz)

    # Und die **Zeitraum-Bilanz** behält ihn — dort ist er ein Ertrag des
    # Zeitraums (§3, Kasten). Wäre er auch hier verschwunden, hätte Schritt 7
    # eine Zahl gelöscht statt sie zu verschieben.
    assert p_mit.bisherige_ertraege_euro > p_ohne.bisherige_ertraege_euro


async def test_erfuellt_schritt7_auch_die_anlagenweite_position(db):
    """§8/7 + §8/4: die Ertragsseite des Erfassungsorts **ohne** Komponente.

    Eine Position auf der `Monatsdaten`-Zeile hat keine Investition und kann
    auf keiner ROI-Zeile stehen — sie wirkt auf die Gesamt-Zahlen. Für die
    Ausgabenseite prüft das `test_erfuellt_schritt4_…`; hier kommt die
    Ertragsseite dazu, denn genau diese Kombination war am 10.08. die Stelle,
    an der eine Zusicherung ohne Prüfung dastand (die N-220-Klasse).
    """
    mit = await _anlage(db, mit_reparatur=False, mit_ertrag=False,
                        allgemeiner_ertrag=ALLGEMEINER_ERTRAG, name="allg-ertrag")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="ohne")

    r_mit, r_ohne = await _roi(db, mit), await _roi(db, ohne)
    p_mit = await get_finanz_prognose(anlage_id=mit, monate=12, db=db)
    p_ohne = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)

    assert r_ohne.gesamt_kapitaleinsatz - r_mit.gesamt_kapitaleinsatz == pytest.approx(
        ALLGEMEINER_ERTRAG
    )
    assert p_ohne.kapitaleinsatz_euro - p_mit.kapitaleinsatz_euro == pytest.approx(
        ALLGEMEINER_ERTRAG
    )
    # Auf keiner Zeile — sie gehört zu keiner.
    assert not [b for b in r_mit.berechnungen
                if (b.detail_berechnung or {}).get("sonstige_ertraege_euro")]


async def test_schritt5_fortschritt_je_investition_ist_zerlegung(db):
    """§8/5 — **gebaut 2026-08-10**: der Zähler liegt je ROI-Zeile vor.

    Geprüft wird die **Konstruktion**, nicht eine Beispielzahl: der
    anlagenweite Zähler wird auf die Zeilen VERTEILT. Deshalb muss

        Σ je Zeile + Rest == Zähler der Anlage

    gelten — und zwar exakt, nicht ungefähr. Läuft das auseinander, rechnet
    irgendwo eine zweite Rechenweise mit (die Klasse aus N-137/N-220).
    """
    assert 5 not in BAUSCHRITTE_OFFEN, "Schritt 5 wieder offen? Dann diese Probe umstellen."

    # ⚠ **Die Fixture muss einen Rest ERZEUGEN, sonst prüft die Probe nichts.**
    # Ein erster Anlauf lief ohne `allgemeine_ausgabe`: dort war der Rest
    # ohnehin 0, und ein Sprengsatz, der ihn fest auf 0 setzt, blieb stumm.
    #
    # ⚑ **Und die Rest-Quelle hat mit Bauschritt 7 gewechselt.** Bis
    # 2026-08-10 war es die anlagenweite Position (§8/4) — sie steht jetzt im
    # Nenner und ist im Zähler gar nicht mehr. Geblieben ist der Fall „Erlös
    # ohne gemessene Erzeugung": dort gibt es keinen Verteilschlüssel, und ein
    # erfundener (Gleichverteilung) würde eine Messung behaupten.
    anlage_id = await _anlage(
        db,
        mit_reparatur=True,
        mit_ertrag=True,
        betriebskosten=BETRIEBSKOSTEN_JAHR,
        allgemeiner_ertrag=ALLGEMEINER_ERTRAG,
        modul_erzeugung=False,
    )
    roi = await _roi(db, anlage_id)
    p = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    assert roi.berechnungen[0].kapitaleinsatz > 0, "der Nenner je Zeile liegt vor"
    assert p.ertraege_je_investition, "und jetzt auch der Zähler"
    assert p.ertraege_nicht_zurechenbar_euro != 0, (
        "ohne Rest prüft die Identität unten nichts — Fixture defekt"
    )

    summe = sum(e.bisherige_ertraege_euro for e in p.ertraege_je_investition)
    # Der Zähler der Kapitalrechnung ist die angezeigte Bilanz PLUS die
    # sonstigen Ausgaben (F-19) MINUS die sonstigen Erträge (Bauschritt 7):
    # beide stehen im Nenner und dürfen den Zähler nicht zusätzlich bewegen.
    zaehler = p.bisherige_ertraege_euro + REPARATUR - THG_ERTRAG - ALLGEMEINER_ERTRAG
    assert summe + p.ertraege_nicht_zurechenbar_euro == pytest.approx(zaehler, abs=0.02)


async def test_schritt5_betriebskosten_nur_ueber_die_eigene_laufzeit(db):
    """N-228 — eine Komponente trägt Betriebskosten nur, solange sie läuft.

    Gemessen wird an **derselben Zeile zweier sonst identischer Anlagen**: die
    Komponente läuft in beiden ab Juli (6 von 12 beobachteten Monaten), nur
    eine trägt ``betriebskosten_jahr``. Die Differenz der Zeilen-Beträge muss
    deshalb **die Hälfte** des Jahresbetrags sein — rechnet der Zähler
    anlagenweit über den ganzen Zeitraum ab (der Zustand bis 2026-08-10), steht
    dort der volle Betrag.

    ⚠ **Zwei Vorgänger-Fassungen zeigten aufs falsche Objekt.** Die erste
    verglich zwei Anlagen mit ``>`` und blieb grün, weil der Unterschied
    überwiegend aus der PV-Historie kam (die N-221-Klasse). Die zweite prüfte
    den **Rest** der Zerlegung gegen die anlagenweite Position — die steht
    seit **Bauschritt 7** im Nenner, der Rest ist dort jetzt 0, und
    ``0 == 0`` hätte still grün gemeldet. Deshalb hier eine exakte Zahl an der
    Zeile selbst.
    """
    from datetime import date as _date

    from sqlalchemy import select as _select

    from backend.models import Investition as _Inv

    async def _ab_juli(**kwargs) -> int:
        anlage_id = await _anlage(
            db, monate=12, jahr=2025, mit_reparatur=False, mit_ertrag=False, **kwargs
        )
        invs = (
            await db.execute(_select(_Inv).where(_Inv.anlage_id == anlage_id))
        ).scalars().all()
        for inv in invs:
            inv.anschaffungsdatum = _date(2025, 7, 1)
        await db.commit()
        return anlage_id

    mit = await _ab_juli(betriebskosten=BETRIEBSKOSTEN_JAHR, name="bk-juli")
    ohne = await _ab_juli(name="ohne-juli")

    p_mit = await get_finanz_prognose(anlage_id=mit, monate=12, db=db)
    p_ohne = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)

    def _pv_zeile(p) -> float:
        # Genau eine Zeile trägt einen Betrag — die PV-Investition.
        assert p.ertraege_je_investition, "Fixture liefert keine Zerlegung"
        return max(e.bisherige_ertraege_euro for e in p.ertraege_je_investition)

    differenz = _pv_zeile(p_ohne) - _pv_zeile(p_mit)
    assert differenz == pytest.approx(BETRIEBSKOSTEN_JAHR / 2, abs=0.02), (
        "die Zeile trägt die Betriebskosten nur über IHRE Laufzeit — steht der "
        f"volle Jahresbetrag ({BETRIEBSKOSTEN_JAHR}) darin, rechnet der Zähler "
        "Monate ab, in denen es die Komponente noch nicht gab (N-228)"
    )


async def test_schritt6_jede_dauer_nennt_ihre_annahme(db):
    """§8/6 — **gebaut 2026-08-10**: eine Dauer ohne genannte Annahme gibt es nicht.

    §4 sagt es als Tabellenzeile: der Amortisations-*Fortschritt* trifft
    **keine** Annahme über die Zukunft, die *Dauer* zwingend eine. §5 wählt
    Modell A und verlangt ausdrücklich, dass das ausgeschrieben wird.

    Geprüft werden alle **vier** Quellen, die eine Dauer ausliefern — die
    Bauliste nannte nur „die Dauer-Anzeige", tatsächlich sind es neun Stellen
    in fünf Dateien, gespeist aus diesen vieren. Fehlt eine, steht dort eine
    Zukunftsaussage ohne Voraussetzung.
    """
    assert 6 not in BAUSCHRITTE_OFFEN, "Schritt 6 wieder offen? Dann diese Probe umstellen."

    from sqlalchemy import select

    from backend.services.pdf.builders.finanzbericht import build_finanzbericht_context

    anlage_id = await _anlage(db, mit_reparatur=True, mit_ertrag=False)
    roi = await _roi(db, anlage_id)
    assert roi.gesamt_amortisation_jahre, "ohne Dauer prüft diese Probe nichts — Fixture defekt"

    # 1 · ROI-Dashboard, Gesamt (KPI-Kachel · Break-Even-Kurve · Summenzeile)
    assert roi.amortisation_annahme == "ohne künftige Instandhaltung"
    # 2 · dieselbe Response je Zeile (Tabellen-Spalte „Amortisation")
    assert [b for b in roi.berechnungen if b.amortisation_jahre], "keine Zeile mit Dauer"
    for b in roi.berechnungen:
        assert b.amortisation_annahme, f"Zeile ohne Annahme: {b.investition_bezeichnung}"
    # 3 · PDF-Finanzbericht
    ctx = await build_finanzbericht_context(db, anlage_id)
    assert ctx["amortisation_annahme"] == "ohne künftige Instandhaltung"
    # 4 · HA-Sensor `amortisation_jahre` — kein Tooltip, also im Rechenweg
    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    sensoren = await calculate_anlage_sensors(db, anlage)
    amort = next(s for s in sensoren if s.definition.key == "amortisation_jahre")
    assert "ohne künftige Instandhaltung" in (amort.berechnung or "")
    # 5 · die Restlaufzeit der Fortschritts-Kachel. ⚠ Sie stand zunächst NICHT
    # auf der Liste: §4 sagt für den Fortschritt „Annahme über die Zukunft:
    # keine" — das gilt für den **Prozentwert**. Das „voraussichtlich JJJJ"
    # daneben rechnet den offenen Rest mit der Jahres-Prognose hoch und ist
    # damit selbst eine Dauer-Aussage.
    p = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)
    assert p.amortisation_annahme == "ohne künftige Instandhaltung"


async def test_schritt6_annahme_folgt_den_daten_nicht_dem_modellnamen(db):
    """§5: mit gepflegten Betriebskosten rechnet eedc **Modell C**, nicht A.

    Der Betrag steht dann als Abzug im Zähler (`jahres_ersparnis_euro`) —
    „ohne künftige Instandhaltung" wäre eine falsche Aussage über die eigene
    Rechnung. Diese Probe ist der Grund, warum der Text ein SoT im Layer ist
    und keine Konstante an neun Anzeigestellen.
    """
    assert 6 not in BAUSCHRITTE_OFFEN, "Schritt 6 wieder offen? Dann diese Probe umstellen."

    mit = await _anlage(db, mit_reparatur=False, mit_ertrag=False,
                        betriebskosten=BETRIEBSKOSTEN_JAHR, name="modell-c")
    ohne = await _anlage(db, mit_reparatur=False, mit_ertrag=False, name="modell-a")

    r_mit, r_ohne = await _roi(db, mit), await _roi(db, ohne)

    assert r_ohne.amortisation_annahme == "ohne künftige Instandhaltung"
    assert r_mit.amortisation_annahme != r_ohne.amortisation_annahme
    # Dieselbe Unterscheidung an der Restlaufzeit — sonst stünden auf einer
    # Seite zwei Dauern mit verschiedenen Voraussetzungen.
    p_mit = await get_finanz_prognose(anlage_id=mit, monate=12, db=db)
    assert p_mit.amortisation_annahme == r_mit.amortisation_annahme
    # Der Betrag selbst steht darin — sonst wäre die Aussage wieder eine
    # Behauptung ohne Zahl (dieselbe Klasse wie N-212).
    assert "180,00 €/Jahr" in (r_mit.amortisation_annahme or "")
    # Und die Zeile der Investition, an der die Kosten hängen, sagt dasselbe.
    zeile = next(b for b in r_mit.berechnungen if b.amortisation_jahre)
    assert "180,00 €/Jahr" in (zeile.amortisation_annahme or "")


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
