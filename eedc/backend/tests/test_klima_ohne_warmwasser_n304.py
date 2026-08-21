"""N-304 — eine Split-Klimaanlage wird nicht nach Warmwasser gefragt.

**Warum das kein Kosmetik-Fund ist.** `warmwasser_kwh` fließt in dieselbe Summe
``wp_waerme`` wie die Heizwärme (``imd_monatsaggregat``, Regel D1:
``waerme = waerme_kwh or (heizung + warmwasser)``), und diese Summe speist
``gas_kosten_altanlage`` sowie die CO₂-Bilanz. Ein an einer Luft-Luft-Anlage
gepflegter Warmwasser-Wert erzeugt damit eine **Ersparnis für Wärme, die das
Gerät nie erzeugt hat** — eine Split-Klimaanlage hat keinen Warmwasserkreis.

⚠ **`heizenergie_kwh` bleibt ausdrücklich stehen.** Eine Klimaanlage *gibt*
Wärme ab, und genau daran hängen Gas- und CO₂-Ersparnis, die vor dem
#263-Konzept ganz fehlten (Gernot, 2026-08-21). Nur die Warmwasser-Achse gibt es
am Gerät nicht. Die Probe unten hält das fest, damit es niemand „aufräumt".

⚑ **Die Entscheidung ist älter als dieser Test.** `64826a40` (N-86, 16.08.) hat
die Klimaanlage von der Heizwärme-**Pflicht** befreit — begründet mit *„die
Größe existiert am Gerät nicht"* —, aber nur in ``get_feld_bedarf``, also auf
der Zuordnungs-Fläche. Der Monatsabschluss liest ``get_felder_fuer_investition``
und kannte die Unterscheidung nicht. Genau das Muster, das jener Commit selbst
beklagt: *„dieselbe Anlage, zwei Flächen, gegenteilige Aussage."*
"""

from __future__ import annotations

from backend.core.field_definitions import (
    get_alle_felder_fuer_investition,
    get_felder_fuer_investition,
    get_live_felder_fuer_investition,
)

KLIMA = {"wp_art": "luft_luft"}
LUFT_WASSER = {"wp_art": "luft_wasser"}


def _felder(parameter: dict) -> list[str]:
    return [f["feld"] for f in get_felder_fuer_investition("waermepumpe", parameter)]


def test_klimaanlage_bekommt_kein_warmwasser_feld():
    """Der Kern: im Monatsabschluss gibt es die Warmwasser-Achse nicht."""
    assert "warmwasser_kwh" not in _felder(KLIMA)


def test_klimaanlage_behaelt_die_heizwaerme():
    """Die Gegenrichtung — und sie ist der eigentliche Schutz.

    Ohne diese Probe wäre der Test oben auch grün, wenn jemand „konsequent"
    auch die Heizwärme entfernt. Damit fielen Gas- und CO₂-Ersparnis der
    Klimaanlage weg — genau die Lücke, die #263 geschlossen hat.
    """
    assert "heizenergie_kwh" in _felder(KLIMA)


def test_luft_wasser_bleibt_unveraendert():
    """Negativprobe: an der Luft-Wasser-Wärmepumpe ändert sich nichts."""
    felder = _felder(LUFT_WASSER)
    assert "warmwasser_kwh" in felder
    assert "heizenergie_kwh" in felder


def test_altbestand_ohne_wp_art_behaelt_warmwasser():
    """Wer `wp_art` nie gepflegt hat, gilt nicht als Klimaanlage.

    Ein Bestandsgerät darf durch diese Regel keine Eingabe verlieren — die
    Unterscheidung ist eine Aussage über die Bauform, keine Vermutung.
    """
    assert "warmwasser_kwh" in _felder({})
    assert "warmwasser_kwh" in _felder({"wp_art": None})


def test_zuordnungsflaeche_zeigt_das_feld_weiter():
    """Ein bereits zugeordneter Sensor darf nicht unsichtbar werden.

    Das ist der Vertrag von ``get_alle_felder_fuer_investition``: verschwände
    das Feld dort, bliebe eine bestehende Zuordnung stehen und wäre **nicht
    mehr löschbar**. Die Pflicht-Einstufung regelt bereits, dass niemand danach
    gefragt wird (``get_feld_bedarf`` → optional, seit N-86).
    """
    alle = [f["feld"] for f in get_alle_felder_fuer_investition("waermepumpe", KLIMA)]
    assert "warmwasser_kwh" in alle


def test_live_felder_kennen_die_negierte_bedingung():
    """``!luft_luft`` darf nirgends still verschluckt werden.

    ``get_live_felder_fuer_investition`` baut seine Liste als **Whitelist**:
    Was auf keinen Zweig passt, fällt heraus — an *beiden* Gerätearten. Ohne
    den ergänzten Zweig verlöre eine Luft-Wasser-Wärmepumpe künftige
    ``!luft_luft``-Felder klanglos. Heute trägt kein Live-Feld die Bedingung;
    dieser Test hält den Mechanismus fest, bevor es eines tut.
    """
    from backend.core.field_definitions import INVESTITION_FELDER  # noqa: F401

    vorher = {f.get("key") for f in get_live_felder_fuer_investition("waermepumpe", LUFT_WASSER)}
    assert vorher, "Luft-Wasser muss Live-Felder haben — sonst prüft der Test nichts"
    nur_klima = {f.get("key") for f in get_live_felder_fuer_investition("waermepumpe", KLIMA)}
    # Die luft_luft-Felder kommen hinzu, die anderen bleiben erhalten.
    assert vorher <= nur_klima
