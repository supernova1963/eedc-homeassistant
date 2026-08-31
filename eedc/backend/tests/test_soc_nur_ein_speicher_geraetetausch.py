"""Der SoC-Check zieht die Aktiv-Grenze **pro Tag** — die fünfte N-313-Stelle.

**Der gemeldete Fall** (Radiocarbonat, simon42 T89667 #273, 2026-08-31): Er hat
seinen Speicher im Mai aufgerüstet und dabei die dokumentierte Anleitung befolgt
(``HANDBUCH_EINSTELLUNGEN`` §3.2, **Weg B**: altes Gerät stilllegen, neues mit
der Gesamtkapazität anlegen). Danach meldete der Daten-Checker:

    114 Tag(e) kennen nur den Ladestand eines von 2 Speichern
    (2026-01-18 … 2026-05-11)

Das Fenster endet am Tag nach der Anschaffung des neuen Speichers. **An allen
114 Tagen gab es objektiv nur einen Speicher** — ein zweiter Ladestand konnte
gar nicht entstehen.

**Die Ursache.** ``_check_soc_nur_ein_speicher`` bildete ``mit_soc`` aus der
**heutigen** Ausstattung (``select(_Inv).where(typ == "speicher")``, ohne
Zeitfilter) und meldete dann **jeden** Tag ohne ``soc_je_speicher`` als defekt.

⚠ **Warum ein Aktiv-Filter allein nicht genügt** — und das ist der Unterschied
zu N-313: Ein ersetztes Gerät wird per ``stilllegungsdatum`` beendet, **nicht**
über den Haken ``aktiv``; die Anleitung verbietet den Haken sogar ausdrücklich
(*„Niemals stattdessen den Haken ‚aktiv' entfernen — das nimmt die Komponente
auch aus der Historie"*). Es braucht die Tages-Ebene, ``ist_aktiv_an``.

⛔ **Es ist die P-6-Falle aus N-313 im Wortlaut.** Der angebotene Knopf
„Zeitraum neu aggregieren" kann den zweiten Ladestand nicht erzeugen, den es
nie gab. Der Melder beschreibt genau das: *„rödelt eine Weile und da steht es
wieder genau so da."*

⛔ **Was hier NICHT geprüft wird:** die übrigen ``select(_Inv)``-Stellen
derselben Datei. Sie sind je Stelle gemessen (die Regel aus N-313s ``ansatz``:
*nicht im Vorbeigehen alle filtern — das wäre Wortlaut statt Ursache*) und
tragen den Befund nicht: ``:363`` und ``:996`` filtern selbst mit
``ist_aktiv_an``, ``:670`` in ``erwartete_komponenten_keys``, ``:1748`` ist
begründet ohne Filter. Die **zweite** getroffene Stelle ist der Klima-Check —
sie hat unten ihren eigenen Fall.

Schwesterdateien: ``test_n313_batterie_vorzeichen_aktiv_filter.py`` (dieselbe
Klasse, dieselbe Datei, der Präzedenzfall) und
``test_stillgelegter_speicher_kapazitaet_f24.py`` (F-24 — ein ersetztes Gerät
zählt nicht zur heutigen Ausstattung).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.models.investition import Investition
from backend.services.daten_checker import DatenChecker, CheckKategorie

_KAT = CheckKategorie.SOC_NUR_EIN_SPEICHER.value

#: Feste Daten statt Prozessuhr (N-167): Die Suite läuft in mehreren Zeitzonen.
_WECHSEL = date(2026, 5, 10)          # der neue Speicher startet
_VOR_WECHSEL = date(2026, 3, 1)       # nur EIN Gerät aktiv
_NACH_WECHSEL = date(2026, 6, 1)      # beide aktiv


def _anlage():
    """Beide Speicher haben einen SoC-Sensor — sonst greift der Check nie."""
    return SimpleNamespace(id=1, sensor_mapping={
        "investitionen": {
            "5": {"live": {"soc": "sensor.speicher_alt_soc"}},
            "6": {"live": {"soc": "sensor.speicher_neu_soc"}},
        },
    })


def _speicher_paar():
    """Der Bestand nach Weg B: alt stillgelegt am Tag VOR dem Wechsel."""
    return [
        Investition(
            id=5, anlage_id=1, typ="speicher", parameter={}, aktiv=True,
            anschaffungsdatum=date(2025, 2, 1),
            stilllegungsdatum=date(2026, 5, 9),
        ),
        Investition(
            id=6, anlage_id=1, typ="speicher", parameter={}, aktiv=True,
            anschaffungsdatum=_WECHSEL, stilllegungsdatum=None,
        ),
    ]


def _speicher_parallel():
    """Der andere Bestand: ein ZUSAETZLICHER Speicher, beide laufen weiter.

    ⭐ Das ist die einzige Konstellation, in der dieser Check ueberhaupt etwas
    zu melden hat — und der Unterschied zum Tausch ist der ganze Punkt: Bei
    Weg B endet das alte Geraet am Tag VOR dem neuen, es gibt also **nie** zwei
    gleichzeitig aktive Speicher. Nach dem Fix schweigt der Check bei einem
    reinen Tausch daher vollstaendig; er gilt fuer parallel betriebene Geraete.
    """
    return [
        Investition(
            id=5, anlage_id=1, typ="speicher", parameter={}, aktiv=True,
            anschaffungsdatum=date(2025, 2, 1), stilllegungsdatum=None,
        ),
        Investition(
            id=6, anlage_id=1, typ="speicher", parameter={}, aktiv=True,
            anschaffungsdatum=_WECHSEL, stilllegungsdatum=None,
        ),
    ]


async def _run(alt_tage: list[date], speicher: list[Investition]):
    """Erste Query liefert die Speicher, zweite die Tage ohne `soc_je_speicher`."""
    db = MagicMock()
    ruf = {"n": 0}

    async def _execute(_stmt):
        ruf["n"] += 1
        scalars = MagicMock()
        scalars.all = MagicMock(
            return_value=speicher if ruf["n"] == 1 else alt_tage
        )
        result = MagicMock()
        result.scalars = MagicMock(return_value=scalars)
        return result

    db.execute = _execute
    return await DatenChecker(db)._check_soc_nur_ein_speicher(_anlage())


async def test_tage_vor_dem_geraetetausch_sind_kein_befund():
    """Der gemeldete Fall: nur Tage, an denen ein Gerät aktiv war ⇒ keine Warnung.

    Ohne den Tagesfilter meldete der Check hier „2 Tag(e) kennen nur den
    Ladestand eines von 2 Speichern" samt Reparatur-Knopf — für Tage, an denen
    der zweite Speicher noch gar nicht gekauft war.
    """
    ergebnisse = await _run([_VOR_WECHSEL, date(2026, 4, 15)], _speicher_paar())

    warnungen = [e for e in ergebnisse if e.schwere == "warning"]
    assert not warnungen, (
        "Tage vor dem Gerätetausch dürfen keinen Befund erzeugen — an ihnen "
        f"war nur ein Speicher aktiv. Gemeldet: {[w.meldung for w in warnungen]}"
    )
    assert any(e.schwere == "ok" for e in ergebnisse)


async def test_tage_mit_zwei_aktiven_speichern_bleiben_ein_befund():
    """Die Gegenprobe: der Fix darf den echten Fall nicht mit wegräumen.

    Hier laufen beide Geräte **parallel** (Zusatz-Speicher, kein Tausch). Ein
    Tag danach ohne `soc_je_speicher` ist ein echter Alt-Datenbestand und wird
    weiterhin gemeldet, samt Reparatur-Knopf, den der Lauf diesmal auch
    einlösen kann.
    """
    ergebnisse = await _run([_NACH_WECHSEL], _speicher_parallel())

    warnungen = [e for e in ergebnisse if e.schwere == "warning"]
    assert len(warnungen) == 1, "der echte Alt-Bestand muss gemeldet bleiben"
    assert "1 Tag(e)" in warnungen[0].meldung
    assert warnungen[0].action_kind == "reaggregate_range"


async def test_gemischte_menge_zaehlt_nur_die_tage_nach_dem_wechsel():
    """Drei Tage vor dem zweiten Gerät, einer danach ⇒ genau einer wird gemeldet.

    Der Fall des Melders in klein, an der parallelen Konstellation gebaut: Die
    Meldung muss von **1** sprechen, nicht von 4. Bei ihm waren es 114 Tage
    vor dem Wechsel — nach dem Fix bleibt davon keiner übrig.
    """
    ergebnisse = await _run(
        [_VOR_WECHSEL, date(2026, 4, 1), date(2026, 4, 2), _NACH_WECHSEL],
        _speicher_parallel(),
    )

    warnungen = [e for e in ergebnisse if e.schwere == "warning"]
    assert len(warnungen) == 1
    assert "1 Tag(e)" in warnungen[0].meldung, warnungen[0].meldung


async def test_ohne_geraetetausch_bleibt_alles_wie_bisher():
    """Zwei durchgehend aktive Speicher: der Filter ändert nichts.

    Wer nie getauscht hat, sieht exakt dasselbe wie vor dem Fix — der Fix darf
    keine Anlage betreffen, die den Fall gar nicht hat.
    """
    dauerhaft = [
        Investition(id=5, anlage_id=1, typ="speicher", parameter={}, aktiv=True,
                    anschaffungsdatum=date(2025, 1, 1), stilllegungsdatum=None),
        Investition(id=6, anlage_id=1, typ="speicher", parameter={}, aktiv=True,
                    anschaffungsdatum=date(2025, 1, 1), stilllegungsdatum=None),
    ]
    ergebnisse = await _run([_VOR_WECHSEL, _NACH_WECHSEL], dauerhaft)

    warnungen = [e for e in ergebnisse if e.schwere == "warning"]
    assert len(warnungen) == 1
    assert "2 Tag(e)" in warnungen[0].meldung
