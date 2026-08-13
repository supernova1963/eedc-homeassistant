"""N-243: Erwartungsrahmen der Basisdaten haengt an der ANLAGE, nicht am Geraet.

Bis 2026-08-13 gab es **drei** Ableitungen fuer dieselbe Frage "welche Monate
sollen erfasst sein": `core/monats_luecken.py` (Sprung "naechster offener"),
sein Frontend-Spiegel (Tabellen-Faerbung) und eine dritte, eigene im
Daten-Checker. Die ersten beiden nahmen das frueheste Anschaffungsdatum ALLER
Investitionen, der Checker das Installationsdatum der Anlage.

Zwei Melder sind an der Geraete-Variante aufgelaufen: **fridolin22** (Forum
T77723 #773) hatte ein E-Auto von 2017 an einer PV-Anlage von 2022 und bekam
Basisdaten ab 2017 abverlangt -- er hat das Auto auf 2026 umdatiert, um die
Forderung loszuwerden, und damit dessen echte Anschaffungshistorie verloren.
**van** (PN 13.08.) sah "Naechster offener: Sep 2016".

⚠ Die Anschaffungsdatum-Grenze bleibt davon unberuehrt: Welche Investition in
welchem Monat *zaehlt*, entscheidet weiter `ist_aktiv_im_zeitraum`.
"""

from __future__ import annotations

import re
from datetime import date

from backend.models import Anlage, Investition, Monatsdaten
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity


async def _anlage(db, *, installationsdatum: date | None, geraete: list[tuple[str, date]]):
    anlage = Anlage(anlagenname="N243", leistung_kwp=10.0,
                    installationsdatum=installationsdatum)
    db.add(anlage)
    await db.flush()
    for typ, datum in geraete:
        db.add(Investition(anlage_id=anlage.id, typ=typ, bezeichnung=f"{typ}-{datum.year}",
                           anschaffungsdatum=datum, leistung_kwp=10.0))
    # Eine Zaehlerzeile, damit die Vollstaendigkeitspruefung ueberhaupt laeuft.
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    await db.commit()
    return anlage.id


def _meldungen(ergebnisse, teil: str) -> list:
    return [e for e in ergebnisse if teil in e.meldung]


def _geforderte_monate(ergebnisse) -> list[tuple[int, int]]:
    """Nur die Meldungen der Form "MM/JJJJ fehlt" -- als (jahr, monat).

    Bewusst per Muster statt per Teilstring: Ein `"2017" in meldung` trifft auch
    den Geraetenamen ("e-auto-2017") und misst damit etwas anderes als gefragt.
    """
    treffer = []
    for e in ergebnisse:
        m = re.fullmatch(r"(\d{2})/(\d{4}) fehlt", e.meldung)
        if m:
            treffer.append((int(m.group(2)), int(m.group(1))))
    return treffer


async def test_altes_eauto_zieht_den_erwarteten_bereich_nicht_zurueck(db):
    """**Der Fund**: fridolin22s Konstellation, eins zu eins."""
    anlage_id = await _anlage(
        db,
        installationsdatum=date(2022, 4, 1),
        geraete=[("e-auto", date(2017, 1, 1)), ("pv-module", date(2022, 4, 1))],
    )
    ergebnisse = (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse

    gefordert = _geforderte_monate(ergebnisse)
    # Kein einziger geforderter Monat darf vor der Anlage (04/2022) liegen.
    assert gefordert, "es muessen Monate gefordert werden"
    assert min(gefordert) >= (2022, 4), gefordert
    # Und das korrekt gepflegte E-Auto von 2017 loest KEINE Diskrepanz aus
    # (F-30-Klasse: ein zulaessiger Zustand, als Defekt gemeldet).
    assert _meldungen(ergebnisse, "Erzeuger älter als die Anlage") == []


async def test_erzeuger_aelter_als_die_anlage_wird_gemeldet(db):
    """Die Gegenprobe: Bei einem ERZEUGER vor dem Anlagendatum gab es Erzeugung,
    bevor die Anlage laut Stammdaten existierte -- eines der beiden Daten stimmt
    nicht, und der erwartete Bereich beginnt zu spaet."""
    anlage_id = await _anlage(
        db,
        installationsdatum=date(2022, 4, 1),
        geraete=[("pv-module", date(2019, 5, 1))],
    )
    ergebnisse = (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse

    treffer = _meldungen(ergebnisse, "Erzeuger älter als die Anlage")
    assert len(treffer) == 1
    assert treffer[0].schwere == CheckSeverity.WARNING
    assert "01.05.2019" in treffer[0].meldung
    assert "01.04.2022" in treffer[0].details


async def test_ohne_anlagendatum_stellt_der_aelteste_erzeuger_den_anker(db):
    """Fallback-Fall: kein Installationsdatum gepflegt. Dann zaehlt der aelteste
    ERZEUGER -- nicht das E-Auto, das noch aelter ist."""
    anlage_id = await _anlage(
        db,
        installationsdatum=None,
        geraete=[("e-auto", date(2017, 1, 1)), ("pv-module", date(2024, 3, 1))],
    )
    ergebnisse = (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse

    gefordert = _geforderte_monate(ergebnisse)
    assert gefordert, "ohne Daten seit 03/2024 muessen Monate fehlen"
    # Ab PV (03/2024) ja -- 2017-2023 nein, das E-Auto begruendet keine Zaehlerzeile.
    assert min(gefordert) == (2024, 3), gefordert
