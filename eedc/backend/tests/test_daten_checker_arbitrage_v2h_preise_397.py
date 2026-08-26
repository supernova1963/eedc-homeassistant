"""#397 — drei Preisfelder, die der Checker forderte und niemand pflegen konnte.

Schwesterdateien: ``test_daten_checker_eauto_ladung_pv_wallbox.py`` (F-64 — der
gleiche unaufloesbare Hinweis eine Ebene tiefer, auf einem **Monatsfeld** statt
einem Stammdaten-Parameter) und ``test_konformitaet_legacy_parameter_keys.py``
(der Waechter aus `4e97cc56`, der die hier scharf gewordenen Pruefer ueberhaupt
erst zum Melden gebracht hat). Die Client-Haelfte steht im Frontend unter
``src/components/forms/sections/InvestitionTypFelder/SpeicherFelder.test.tsx``.

**Der Anlass.** MeinerB (GitHub Issue #397, 26.08.2026): *„ich bekomme einen
Hinweis dass ich die Felder bearbeiten soll, kann sie aber nicht finden."* Sein
AC-Speicher hat „Arbitrage-faehig" an; der Daten-Checker forderte daraufhin
Ø Lade- und Ø Entladepreis — beide gab es in **keinem** Formular und in keinem
Wizard, nur in der Konstanten-Map. Der „Beheben"-Knopf fuehrte in ein Formular
ohne die Felder. Dieselbe Sackgasse wie F-64, eine Ebene versetzt: dort ein
**Monatsfeld** (`field_definitions.py`), hier ein **Stammdaten-Parameter**.

**Sichtbar gemacht hat es unsere eigene Arbeit.** Bis 2026-08-23 standen die
Bedingungen auf den Vor-Kanon-Namen (`nutzt_arbitrage`, `nutzt_v2h`); die
Pruefer haben deshalb **nie** gemeldet. Erst `4e97cc56` machte sie scharf —
und damit einen Mangel sichtbar, den es schon vorher gab.

⭐ **Die Messung hat zwei verschiedene Antworten ergeben, und das ist der Kern
dieser Datei.** Beide Faelle sehen gleich aus (Schalter an, Preisfeld leer,
Checker meldet), sind es aber nicht:

* **Speicher — der Parameter ist die EINZIGE Quelle.** Arbitrage lebt davon,
  dass dieselbe Kilowattstunde zu **verschiedenen Uhrzeiten** verschieden viel
  kostet: nachts geladen, abends entladen. Ein eedc-Tarif kennt keine Uhrzeit
  (Discussion #380, an denselben Melder). Der gepflegte Bezugspreis ist fuer
  beide Enden der falsche Wert — zu hoch fuers Laden, zu niedrig fuers
  Entladen. Deshalb wurden die **Felder pflegbar gemacht** und die Pruefer
  bleiben. Wo eedc die Zeitachse doch hat, benutzt es sie: `_aufloesen_ladepreis`
  zieht den stundengenauen TEP-Preis (Tibber/aWATTar/EPEX) vor und faellt nur
  ohne dynamischen Tarif auf den Parameter zurueck.
* **V2H — der Parameter ist ein OVERRIDE.** Ohne ihn rechnet `dashboards.py`
  ueber `berechne_v2h_ersparnis` mit dem Spread aus den **gepflegten** Tarifen
  (Bezug − Einspeiseverguetung). Das ist die belastbarere Grundlage; wer dem
  Hinweis folgte, ersetzte eine Messung durch eine Schaetzung. Der Pruefer ist
  deshalb **ersatzlos entfallen**.

⚠ **Beide Richtungen stehen als Probe.** Ohne die Speicher-Gegenproben waere
auch die ersatzlose Streichung *aller drei* Pruefer gruen — und ohne die
V2H-Probe waere die Streichung dort von einem Versehen nicht zu unterscheiden.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, Monatsdaten
from backend.services.daten_checker import DatenChecker
from backend.tests import factories

JAHR = 2026


async def _anlage_mit_investition(db, *, typ: str, bezeichnung: str, parameter: dict) -> Anlage:
    anlage = await factories.anlage(db, standort_land="DE")
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=1))
    db.add(Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung=bezeichnung,
        anschaffungsdatum=date(JAHR - 1, 1, 1),
        anschaffungskosten_alternativ=30000.0,
        parameter=parameter,
    ))
    await db.commit()
    return anlage


async def _meldungen(db, anlage: Anlage, teilstring: str) -> list[str]:
    geladen = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())

    ergebnisse = DatenChecker(db)._check_investitionen(geladen, monatsdaten)
    return [e.meldung for e in ergebnisse if teilstring in e.meldung]


# ---------------------------------------------------------------------------
# V2H — der Pruefer ist entfallen, weil seine Aussage falsch war
# ---------------------------------------------------------------------------

async def test_v2h_entladepreis_ist_kein_mangel_397(db):
    """Ein V2H-faehiges E-Auto ohne Entladepreis wird NICHT bemaengelt.

    `v2h_entlade_preis_cent` ist ein Override. Ohne ihn rechnet eedc mit dem
    Spread aus den gepflegten Tarifen — der besseren Grundlage. Ein Hinweis
    darauf forderte den Anwender auf, eine Messung durch eine Schaetzung zu
    ersetzen, und war ueberdies nirgends abstellbar.
    """
    anlage = await _anlage_mit_investition(
        db, typ="e-auto", bezeichnung="VW ID.3",
        parameter={
            "jahresfahrleistung_km": 15000,
            "verbrauch_kwh_100km": 17.0,
            "v2h_faehig": True,
            # `v2h_entlade_preis_cent` fehlt bewusst — das ist der Normalfall.
        },
    )

    meldungen = await _meldungen(db, anlage, "Entladepreis")

    assert meldungen == [], (
        "Der Checker bemaengelt einen fehlenden V2H-Entladepreis. Er wird nicht "
        "benoetigt: ohne ihn rechnet `berechne_v2h_ersparnis` mit Bezug minus "
        f"Einspeiseverguetung. Bekommen: {meldungen}"
    )


# ---------------------------------------------------------------------------
# Speicher — die Pruefer BLEIBEN, die Felder sind jetzt pflegbar
# ---------------------------------------------------------------------------

async def _speicher_anlage(db, *, parameter: dict) -> Anlage:
    return await _anlage_mit_investition(
        db, typ="speicher", bezeichnung="BYD HVS", parameter=parameter,
    )


async def test_arbitrage_ohne_preise_wird_weiterhin_gemeldet(db):
    """Gegenprobe zur V2H-Streichung — hier ist der Hinweis richtig.

    Ohne diese Probe koennte der Fix alle drei Pruefer ersatzlos streichen und
    saemtliche Proben waeren gruen. Der Unterschied zum V2H-Fall ist die
    Zeitachse: fuer den Niedrigtarif-Ladepreis hat eedc keine Quelle ausser
    dem Anwender.
    """
    anlage = await _speicher_anlage(db, parameter={
        "kapazitaet_kwh": 10.0,
        "arbitrage_faehig": True,
    })

    lade = await _meldungen(db, anlage, "Ladepreis fehlt")
    entlade = await _meldungen(db, anlage, "Entladepreis fehlt")

    assert len(lade) == 1, f"Ladepreis gehoert gemeldet, bekam: {lade}"
    assert len(entlade) == 1, f"Entladepreis gehoert gemeldet, bekam: {entlade}"


async def test_arbitrage_mit_gepflegten_preisen_meldet_nichts(db):
    """MeinerBs Fall NACH dem Fix: die Felder sind pflegbar, der Hinweis geht weg.

    Das ist die eigentliche Zusicherung des Pakets — vorher war dieser Zustand
    ueber die Oberflaeche gar nicht erreichbar.
    """
    anlage = await _speicher_anlage(db, parameter={
        "kapazitaet_kwh": 10.0,
        "arbitrage_faehig": True,
        "lade_durchschnittspreis_cent": 15.0,
        "entlade_vermiedener_preis_cent": 38.0,
    })

    assert await _meldungen(db, anlage, "Ladepreis fehlt") == []
    assert await _meldungen(db, anlage, "Entladepreis fehlt") == []


async def test_ohne_arbitrage_kein_hinweis(db):
    """Ein Speicher ohne Arbitrage braucht die Preise nicht — und wird nicht gefragt."""
    anlage = await _speicher_anlage(db, parameter={
        "kapazitaet_kwh": 10.0,
        "arbitrage_faehig": False,
    })

    assert await _meldungen(db, anlage, "preis fehlt") == []
