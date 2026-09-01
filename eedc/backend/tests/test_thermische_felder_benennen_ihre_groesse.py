"""Ein thermisches Energiefeld benennt seine Größe im **Label**, nicht nur im Hinweis.

Schwesterdateien: `test_soll_waerme_klima_achse1_erfassung.py` (dort steht, *welches*
Feld an welcher Bauart überhaupt angeboten wird) und
`test_datenquellen_speicher_felder.py` (dieselbe Bauform an der Speicher-Achse:
ein Label, das seine Größe trägt, wird per Probe festgehalten). Der Gegenstand
hier ist ausschließlich die **Beschriftung** — nicht das Angebot, nicht die
Rechnung.

## Warum das eine eigene Regel ist

Eine Wärmepumpe führt zwei Sorten kWh nebeneinander: **elektrisch** (was sie
verbraucht) und **thermisch** (was sie abgibt). Wer die beiden verwechselt,
bekommt eine Arbeitszahl, die um den Faktor der Arbeitszahl danebenliegt — und
zwar lautlos, weil beide Größen dieselbe Einheit tragen.

⚠ **Der Hinweis allein genügt nicht, und das ist der belegte Fall.** Alle sechs
Felder unten führen seit jeher einen `hinweis`, der das Wort „thermisch" enthält.
Die **Zuordnungs-Fläche des Custom-Imports** baut ihre Auswahl aber aus `label`
plus Einheit (`api/routes/custom_import/analyze.py::_build_investition_felder`)
— der Hinweis erreichte sie bis zum 01.09.2026 nicht. Ein Melder (dietmar1968,
simon42 T89667 #283) ordnete dort eine Umgebungswärme-Spalte auf
`warmwasser_kwh` zu, weil die Option nur „WP: <Gerät> – Warmwasser (kWh)" sagte.
Beim Nachbarfeld „Heizwärme (kWh)" ist ihm dasselbe **nicht** passiert.

⭐ Die Schärfung gab es schon einmal: **#120** hat `heizenergie_kwh` von
„Heizenergie" auf **„Heizwärme"** gehoben, ausdrücklich mit der Begründung
„abgegebene thermische Wärme, nicht Strom". Das Schwesterfeld blieb dabei
stehen. Diese Datei sorgt dafür, dass die Regel nicht wieder an einem einzelnen
Feld hängenbleibt.

## Woher die Liste kommt — und warum sie keine Pflegeliste ist

Nicht aus einer Aufzählung hier, sondern aus dem bestehenden SoT
`field_definitions._SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG`: dort steht bei jedem
Feld, **warum** es keinen Beitrag zur Energiebilanz liefert, und bei genau diesen
sechs lautet der Grund „thermisch". Ein siebtes thermisches Feld erbt die Regel
damit automatisch — es muss niemand daran denken.
"""

from __future__ import annotations

import pytest

from backend.core.field_definitions import (
    INVESTITION_FELDER,
    _SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG,
)

#: Wörter, mit denen ein Label die **abgegebene** Größe benennen darf.
#:
#: „Wärme" deckt Heizwärme und Warmwasser-Wärme ab. „Nutzenergie" ist der
#: Oberbegriff der Betriebsart-Felder und trägt dieselbe Abgrenzung — er ist
#: dort sogar nötig, weil eine „Nutzenergie Kühlbetrieb" gerade **keine** Wärme
#: ist und „Kältemenge" nicht zu „Lüften"/„Entfeuchten" passt.
#:
#: ⚠ Der Vergleich läuft **ohne Groß-/Kleinschreibung**, und das ist gemessen,
#: nicht vorsorglich: die erste Fassung verglich exakt und meldete ausgerechnet
#: „Heizwärme" als regelwidrig — dort steht das Wort klein am Wortende.
GROESSEN_WOERTER = ("wärme", "nutzenergie", "kälte", "wärmemenge")

#: Was in einem thermischen Label nichts zu suchen hat: es würde die
#: Verwechslung, gegen die diese Datei gebaut ist, ausdrücklich einladen.
VERBOTENE_WOERTER = ("strom", "elektrisch")


def _thermische_felder() -> list[tuple[str, str, str]]:
    """`(typ, feld, label)` für jedes Feld, das der SoT als thermisch führt.

    Die Wahrheit steht in `_SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG`, nicht hier —
    siehe Modul-Docstring.
    """
    out: list[tuple[str, str, str]] = []
    for (typ, feld), grund in _SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG.items():
        if "thermisch" not in grund.lower():
            continue
        for eintrag in INVESTITION_FELDER.get(typ, []):
            if eintrag["feld"] == feld:
                out.append((typ, feld, eintrag["label"]))
                break
    return sorted(out)


def test_die_erhebung_findet_ueberhaupt_etwas():
    """Negativ-Absicherung der Quelle selbst.

    Ohne sie wären alle Proben darunter **grün, weil sie über eine leere Liste
    laufen** — genau die Bauform, vor der der Beweis-Familien-Sammler warnt.
    Sechs Felder waren es am 01.09.2026; die Schranke ist bewusst `>= 4` und
    kein exakter Wert, damit ein neu hinzukommendes Feld die Probe nicht rot
    macht, ein **weggefallener SoT** aber schon.
    """
    felder = _thermische_felder()
    assert len(felder) >= 4, f"SoT liefert nur {len(felder)} thermische Felder: {felder}"
    assert ("waermepumpe", "warmwasser_kwh") in {(t, f) for t, f, _ in felder}


@pytest.mark.parametrize("typ,feld,label", _thermische_felder())
def test_thermisches_label_nennt_die_abgegebene_groesse(typ: str, feld: str, label: str):
    """Das Label trägt eines der Größen-Wörter — der Hinweis reicht nicht.

    Er erreicht die Custom-Import-Zuordnung nicht (s. Modul-Docstring); das
    Label ist dort die einzige Beschriftung.
    """
    assert any(w in label.lower() for w in GROESSEN_WOERTER), (
        f"{typ}/{feld}: Label {label!r} benennt die abgegebene Größe nicht. "
        f"Erwartet wird eines von {GROESSEN_WOERTER} — sonst steht eine "
        f"thermische kWh-Zahl ununterscheidbar neben einer elektrischen."
    )


@pytest.mark.parametrize("typ,feld,label", _thermische_felder())
def test_thermisches_label_behauptet_nicht_strom(typ: str, feld: str, label: str):
    """Die Gegenrichtung — ein thermisches Feld nennt sich nicht „Strom …".

    Zweite Regelhälfte, eigene Probe: Die erste ließe ein Label
    „Strom Warmwasser-Wärme" durch (es enthält „Wärme"), obwohl es genau die
    Verwechslung behauptet, gegen die diese Datei gebaut ist.
    """
    assert not any(w in label.lower() for w in VERBOTENE_WOERTER), (
        f"{typ}/{feld}: Label {label!r} nennt Strom, das Feld ist aber thermisch."
    )


def test_die_elektrischen_schwesterfelder_sagen_es_ebenso():
    """Gegenprobe an der anderen Seite der Achse — sonst prüft die Datei nur eine Hälfte.

    `strom_heizen_kwh` und `strom_warmwasser_kwh` liegen im Formular direkt
    neben den thermischen Feldern und tragen dieselbe Einheit. Dass **sie** ihre
    Größe benennen, ist die Voraussetzung dafür, dass die Trennung überhaupt
    lesbar ist; fiele sie weg, wäre die Regel oben allein wirkungslos.
    """
    wp = {f["feld"]: f["label"] for f in INVESTITION_FELDER["waermepumpe"]}
    for feld in ("stromverbrauch_kwh", "strom_heizen_kwh", "strom_warmwasser_kwh"):
        assert "Strom" in wp[feld], (
            f"{feld}: Label {wp[feld]!r} benennt die elektrische Größe nicht."
        )
