"""H-3 zu HA-Bauform E4f (Fachentscheid Master Wärme/Klima, 07.10.2026): „kein Heizbetrieb" geht „Wärme nicht je
Funktion gemessen" vor.

**Die Regel.** Ist der Strom einer Funktion (Heizen bzw. Warmwasser) im Zeitraum bekannt und 0, gilt die Zeitraum-
Aussage „kein Heizbetrieb in diesem Zeitraum" bzw. „keine Warmwasserbereitung in diesem Zeitraum" (Klasse Zeitraum,
stilles „—") — auch dann, wenn die Wärme nur als Gesamtwert gemessen ist (``waerme_kwh``, ein Wärmemengenzähler über
beide Funktionen). Begründung an der Kategorie: ein Zeitraum ohne Betrieb hat keinen Handgriff, den der Anwender tun
könnte; der Ausstattungs-Satz „Wärme nicht je Funktion gemessen" (mit Handgriff „zweiten Zähler setzen") wäre dort falsch.
Konzept Wärme/Klima §4.3: die Datenlage geht der Abgrenzung vor (Stufe 2/3 vor 5/6).

**Was bleibt:** Fließt Strom der Funktion, bleibt „Wärme nicht je Funktion gemessen" (N-391). Fehlt die Wärme ganz (kein
Wärmemengenzähler), bleibt Stufe 5 mit dem Wärme-Grund (Bauplan §8a, Nachtrag E4d).

**Anlass:** der Golden Master v4.1.2 ↔ E4f an der Prüfstand-Anlage (Sommermonate, Vaillant mit getrennter Strommessung,
Heizstrom 0, Gesamt-Wärmezähler): seit E4d stand dort „Wärme nicht je Funktion gemessen" statt „kein Heizbetrieb".

Schwesterdateien: test_n391_gesamtwaerme.py (die Lage B, Heizstrom > 0), test_r2_je_funktion.py (Helfer),
test_e4f_nachlauf_nur_fehlende_tage.py.
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_KEIN_HEIZBETRIEB,
    GRUND_KEINE_WAERMEMESSUNG,
    GRUND_WAERME_NICHT_JE_FUNKTION,
    arbeitszahl,
    arbeitszahl_je_funktion,
)
from backend.tests.test_n391_gesamtwaerme import _lage
from backend.tests.test_r2_je_funktion import _jahr, _monat

#: Sommer mit EINEM Wärmemengenzähler über Heizung und Warmwasser, Strom getrennt: Heizstrom gemessen 0.
SOMMER = {"strom_heizen_kwh": 0.0, "strom_warmwasser_kwh": 28.3, "waerme_kwh": 109.1}


# ── Layer ───────────────────────────────────────────────────────────────────


def test_funktions_strom_null_mit_gesamtwaerme_ist_kein_heizbetrieb():
    az = arbeitszahl(None, 0.0, waerme_fehlt_grund=GRUND_WAERME_NICHT_JE_FUNKTION,
                     kein_betrieb_grund=GRUND_KEIN_HEIZBETRIEB)
    assert az.wert is None and az.grund == GRUND_KEIN_HEIZBETRIEB


def test_funktions_strom_ueber_null_mit_gesamtwaerme_bleibt_nicht_je_funktion():
    az = arbeitszahl(None, 5.0, waerme_fehlt_grund=GRUND_WAERME_NICHT_JE_FUNKTION,
                     kein_betrieb_grund=GRUND_KEIN_HEIZBETRIEB)
    assert az.grund == GRUND_WAERME_NICHT_JE_FUNKTION


def test_ohne_waermezaehler_bleibt_stufe_5():
    """§8a-Nachtrag (E4d) unverändert: Strom gemessen 0, Wärme nicht erfasst ⇒ der Wärme-Grund."""
    az = arbeitszahl(None, 0.0, kein_betrieb_grund=GRUND_KEIN_HEIZBETRIEB)
    assert az.grund == GRUND_KEINE_WAERMEMESSUNG


def test_je_funktion_sommer():
    je = arbeitszahl_je_funktion(
        heizung_kwh=None, strom_heizen_kwh=0.0, warmwasser_kwh=None, strom_warmwasser_kwh=28.3,
        hat_split=True, waerme_ist_gesamt=True, null_ist_gemessen=True,
    )
    assert je.heizen.grund == GRUND_KEIN_HEIZBETRIEB
    assert je.warmwasser.grund == GRUND_WAERME_NICHT_JE_FUNKTION


# ── Sichten ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cockpit_monat_im_sommer(db):
    """Ein Gerät, Sommer: Heizstrom gemessen 0, Gesamt-Wärmezähler ⇒ „kein Heizbetrieb" (bis E4f: „kein
    Stromverbrauch erfasst" — die gemessene Gesamtwärme zählte nicht als „Wärme gemessen"). Warmwasser mit Strom
    bleibt „Wärme nicht je Funktion gemessen".

    ⚠ Der Komponenten-Hub (Gerät über den Zeitraum) reicht keinen Zeitraum-Grund herein (N-479 gilt dort nicht) und
    bleibt bei „kein Stromverbrauch erfasst" — unverändert seit v4.1.2, nicht Teil von H-3."""
    a = await _lage(db, SOMMER, name="H-3")
    m = await _monat(db, a.id)
    j = await _jahr(db, a.id)
    assert m.wp_jaz_heizen is None and m.wp_jaz_heizen_grund == GRUND_KEIN_HEIZBETRIEB
    assert m.wp_jaz_warmwasser_grund == GRUND_WAERME_NICHT_JE_FUNKTION
    assert j.wp_jaz_heizen_grund == GRUND_KEIN_HEIZBETRIEB, "das Jahr aus genau diesem Monat sagt dasselbe"


@pytest.mark.asyncio
async def test_pruefstand_zwei_geraete_im_sommer(db):
    """Die Lage des Golden Masters: zwei Geräte mit getrennter Strommessung, Heizstrom beider gemessen 0; eines misst
    die Wärme gesamt, das andere je Funktion (Heizwärme 0). Seit E4d nannte der Monat „Wärme nicht je Funktion
    gemessen"; v4.1.2 und jetzt: „kein Heizbetrieb"."""
    from backend.tests.test_r2_je_funktion import _WP, _anlage, _geraet

    a = await _anlage(db, "H-3 Prüfstand")
    await _geraet(db, a, "Vaillant", dict(_WP), {"strom_heizen_kwh": 0.0, "strom_warmwasser_kwh": 28.3,
                                                 "waerme_kwh": 109.1})
    await _geraet(db, a, "Nibe", dict(_WP), {"strom_heizen_kwh": 0.0, "heizenergie_kwh": 0.0,
                                             "strom_warmwasser_kwh": 24.7, "warmwasser_kwh": 89.4})
    await db.commit()
    m = await _monat(db, a.id)
    assert m.wp_jaz_heizen_grund == GRUND_KEIN_HEIZBETRIEB


@pytest.mark.asyncio
async def test_cockpit_monat_mit_heizstrom_bleibt_nicht_je_funktion(db):
    a = await _lage(db, {**SOMMER, "strom_heizen_kwh": 4.0}, name="H-3b")
    m = await _monat(db, a.id)
    assert m.wp_jaz_heizen_grund == GRUND_WAERME_NICHT_JE_FUNKTION
