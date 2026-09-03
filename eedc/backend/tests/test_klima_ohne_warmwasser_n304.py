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


# ============================================================================
# N-379 — **die andere Hälfte: der LESEPFAD** (03.09.2026, dietmar1968 #295)
# ============================================================================
#
# ⭐ **Der Docstring oben beschrieb den Schaden — und er trat weiter ein.**
# N-304 hat das Feld aus der *Erfassung* genommen; ein VORHER gepflegter Wert
# blieb in der Zeile stehen und wurde von elf Faltstellen in sechs Dateien roh
# aus `verbrauch_daten` gelesen. `ist_luft_luft_waermepumpe` kam in keiner davon
# vor. Gemeldet: 889 kWh „Warmwasser" an einer Split-Klimaanlage, daraus
# „Wärme erzeugt 889 kWh", eine Arbeitszahl von 1,09, „Ersparnis vs. Gas 38 €"
# und „CO₂-Ersparnis −112 kg" (T89667 #295).
#
# ⚠ **Vierte Runde der #236-Folgewellen-Klasse**: N-86 (nur `get_feld_bedarf`)
# → N-304 (Monatsabschluss) → W-12 (Zuordnungs-Fläche) → hier der Lesepfad.
# *Ein Filter auf einer Schicht reicht nicht, wenn mehrere Pfade dieselbe Größe
# lesen.* Deshalb prüft der erste Test die **Registry-Frage** und der zweite die
# **eine Lesetür** — nicht sechs Aufrufer einzeln.

from backend.core.berechnungen.imd_monatsaggregat import imd_typ_beitrag
from backend.core.field_definitions import (
    get_wp_warmwasser_kwh,
    groesse_gibt_es_am_geraet,
)

ZEILE = {"heizenergie_kwh": 800.0, "warmwasser_kwh": 889.0,
         "stromverbrauch_kwh": 300.0}


class _Inv:
    """Nur so viel Investition, wie `imd_typ_beitrag` liest."""
    def __init__(self, parameter):
        self.typ = "waermepumpe"
        self.parameter = parameter


def test_registry_sagt_dem_lesepfad_dass_es_die_groesse_nicht_gibt():
    """Die Frage, aus der alles Übrige folgt — an derselben Registry."""
    assert groesse_gibt_es_am_geraet("waermepumpe", "warmwasser_kwh", KLIMA) is False
    assert groesse_gibt_es_am_geraet("waermepumpe", "warmwasser_kwh", LUFT_WASSER) is True


def test_lesetuer_gibt_an_der_klimaanlage_null_und_an_der_wp_den_wert():
    """`get_wp_warmwasser_kwh` — die eine Tür für alle sechs Read-Sites."""
    assert get_wp_warmwasser_kwh(ZEILE, KLIMA) == 0.0
    assert get_wp_warmwasser_kwh(ZEILE, LUFT_WASSER) == 889.0


def test_ohne_parameter_bleibt_die_tuer_ein_rohzugriff():
    """Schreib-/Importpfade haben keine Investition zur Hand und filtern nichts.

    ⛔ Kein Schlupfloch: Es ist die Lage der Aufrufer, die gar nicht wissen
    können, um welches Gerät es geht — sie dürfen nichts wegnehmen.
    """
    assert get_wp_warmwasser_kwh(ZEILE) == 889.0


def test_die_waermesumme_der_klimaanlage_traegt_kein_warmwasser():
    """Die Wirkung dort, wo sie zählt: im Layer-SoT der Monatszeile.

    ⭐ **Das ist der Test, der den gemeldeten Fall trifft.** `wp_waerme` speist
    `gas_kosten_altanlage` und die CO₂-Bilanz — genau die zwei Zahlen, die auf
    dietmars Bildschirm standen.
    """
    klima = imd_typ_beitrag(_Inv(KLIMA), ZEILE)
    assert klima.wp_warmwasser == 0.0
    assert klima.wp_waerme == 800.0, "nur die Heizwärme, die es am Gerät gibt"

    wp = imd_typ_beitrag(_Inv(LUFT_WASSER), ZEILE)
    assert wp.wp_warmwasser == 889.0
    assert wp.wp_waerme == 1689.0


def test_der_strom_der_klimaanlage_bleibt_unangetastet():
    """⛔ **Die Gegenrichtung, und sie ist der eigentliche Schutz.**

    `strom_warmwasser_kwh` trägt dieselbe Registry-Bedingung — und wird
    ausdrücklich **nicht** gefiltert. Diese Kilowattstunden sind über den Zähler
    geflossen; sie herauszurechnen machte das Gerät billiger und sauberer, als
    es ist, und `get_wp_strom_kwh` zählt sie im getrennten Zweig weiter in die
    Gesamtsumme. Ohne diese Probe wäre eine „konsequente" Ausweitung auf den
    Strom grün — und die Aufteilung ginge auf ihr eigenes Gesamt nicht mehr auf.
    """
    zeile = dict(ZEILE, strom_heizen_kwh=200.0, strom_warmwasser_kwh=100.0)
    klima = imd_typ_beitrag(_Inv(KLIMA), zeile)
    assert klima.wp_strom_warmwasser == 100.0
