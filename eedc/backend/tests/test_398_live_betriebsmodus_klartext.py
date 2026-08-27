"""Der Betriebsmodus-Klartext im Live-Bild — was er sagt und wann er schweigt.

**Anlass: MartyBr, Forum simon42 T89667 #230**, am Tag der v4.0.30-Auslieferung.
Unter seiner Wärmepumpe stand „Unbestimmt" — bei 0 W, quer über dem Gerätenamen.
Zwei Fehler in einer Kachel, und dieser Test hält den ersten fest:

⭐ **Eine Kachel, die nichts zu sagen hat, sagt nichts.** ``BETRIEBSMODUS_ICON``
zieht diese Linie seit #398 Stufe 3 ausdrücklich — ``aus`` und ``unbestimmt``
haben dort **kein** Symbol, weil *„ein Sondersymbol für ‚ich weiß es nicht' eine
Aussage wäre, die eedc nicht hat"*. Für den **Text** galt derselbe Satz und stand
trotzdem nicht da; ein Wort behauptet mehr als ein Symbol, nicht weniger.

⚠ **Der Rohwert bleibt.** ``betriebsmodus`` trägt weiterhin ``unbestimmt`` — wer
den Zustand auswertet, muss ihn sehen. Nur die **Anzeige** schweigt. Wäre auch
der Rohwert leer, verlöre der Client die Unterscheidung „kein Modus zugeordnet"
gegen „Modus zugeordnet, aber unlesbar" (ADR-002/P4).

Die zweite Hälfte des Befunds — die Überlagerung mit dem Gerätenamen — ist ein
Layout-Fehler und liegt in ``EnergieFluss.tsx``; sie wird dort geprüft
(``EnergieFluss.betriebsmodus.test.tsx``).

Schwesterdateien: ``test_398_betriebsmodus_live.py`` (dieselbe Fläche, eine
Ebene höher: Kanon · Icon-Tabelle · der 60-s-Takt der Modus-Quelle) ·
``test_263_k2_betriebsmodus_lesen_mitschreiben.py`` (der Lesepfad, aus dem der
Wert überhaupt kommt) · ``test_soll_waerme_klima_achse3_aufloesung.py`` (der
Handbuch-Wächter über derselben Werte-Tabelle).
"""

from __future__ import annotations

import pytest

from backend.core.betriebsmodus import (
    AUS,
    BETRIEBSMODUS_ICON,
    BETRIEBSMODUS_KANON,
    BETRIEBSMODUS_LABEL,
    BETRIEBSMODUS_LIVE_OHNE_KLARTEXT,
    HEIZEN,
    KUEHLEN,
    UNBESTIMMT,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.live_komponenten_builder import build_komponenten
from backend.tests import factories

_BASIS = {"pv_gesamt_w": 3000.0, "einspeisung_w": 100.0, "netzbezug_w": None}


def _anlage() -> Anlage:
    return factories.mach_anlage(leistung_kwp=5.0, standort_land="DE")


def _wp_komponente(modus: str | None, *, watt: float = 0.0) -> dict:
    """Eine Wärmepumpe mit (oder ohne) Betriebsmodus, wie das Live-Bild sie sieht."""
    investitionen = {"7": Investition(typ="waermepumpe", bezeichnung="Vitocal 333-G", parameter={})}
    result = build_komponenten(
        _anlage(),
        _BASIS,
        {"7": {"leistung_w": watt}},
        investitionen,
        {"7": {"leistung_w": "sensor.wp"}},
        modus_map={7: modus} if modus else None,
    )
    komp = next(k for k in result["komponenten"] if k["key"].endswith("_7"))
    return komp


@pytest.mark.parametrize("modus", sorted(set(BETRIEBSMODUS_KANON) - BETRIEBSMODUS_LIVE_OHNE_KLARTEXT))
def test_jeder_aussagekraeftige_modus_bekommt_seinen_klartext(modus):
    """Alles außer der Nicht-Aussage wird angezeigt — auch ``aus``.

    ``aus`` steht bewusst **nicht** auf der Schweigeliste: „Das Gerät läuft
    nicht" ist eine Auskunft, und zwar die, die MartyBrs 0 W begleiten soll.
    """
    komp = _wp_komponente(modus)
    assert komp["betriebsmodus"] == modus
    assert komp["betriebsmodus_label"] == BETRIEBSMODUS_LABEL[modus]
    assert komp["betriebsmodus_label"], "ein leerer Klartext ist keine Auskunft"


def test_unbestimmt_zeigt_keinen_klartext_aber_behaelt_den_rohwert():
    """MartyBrs Fall: `hk1_mode_raw` = 1 ⇒ `unbestimmt` ⇒ die Kachel schweigt."""
    komp = _wp_komponente(UNBESTIMMT)
    assert komp["betriebsmodus"] == UNBESTIMMT, (
        "der Rohwert muss bleiben — sonst ist 'kein Modus zugeordnet' von "
        "'Modus zugeordnet, aber unlesbar' nicht mehr zu unterscheiden"
    )
    assert komp["betriebsmodus_label"] is None


def test_ohne_modus_quelle_gibt_es_beides_nicht():
    """Wer keinen Modus-Sensor zugeordnet hat, sieht keine Zeile — kein „—"."""
    komp = _wp_komponente(None)
    assert komp["betriebsmodus"] is None
    assert komp["betriebsmodus_label"] is None


def test_die_schweigeliste_ist_eine_teilmenge_des_kanons():
    """Ein Eintrag, den der Kanon nicht kennt, wäre wirkungslos und unbemerkt."""
    assert BETRIEBSMODUS_LIVE_OHNE_KLARTEXT <= set(BETRIEBSMODUS_KANON)


def test_schweigeliste_und_icon_liste_ziehen_dieselbe_linie_oder_erklaeren_es():
    """Wer schweigt, hat auch kein Symbol — die Umkehrung gilt bewusst nicht.

    ``aus`` ist der eine Fall, in dem beide auseinandergehen: kein Symbol (es
    gäbe keins, das etwas hinzufügt), aber sehr wohl ein Text. Dieser Test hält
    genau diese eine Abweichung fest, damit sie nicht versehentlich zu zweien
    wird.
    """
    ohne_icon = set(BETRIEBSMODUS_KANON) - set(BETRIEBSMODUS_ICON)
    assert BETRIEBSMODUS_LIVE_OHNE_KLARTEXT <= ohne_icon, (
        "ein Modus mit Symbol, aber ohne Text, wäre eine halbe Aussage"
    )
    assert ohne_icon - BETRIEBSMODUS_LIVE_OHNE_KLARTEXT == {AUS}, (
        "nur `aus` darf einen Text ohne Symbol tragen; jede weitere Abweichung "
        "ist zu begründen, nicht stillschweigend zu erlauben"
    )


def test_heizen_und_kuehlen_sind_von_der_regel_unberuehrt():
    """Die Gegenprobe zum Befund: der Normalfall verliert nichts."""
    assert _wp_komponente(HEIZEN, watt=1200.0)["betriebsmodus_label"] == "Heizen"
    assert _wp_komponente(KUEHLEN, watt=900.0)["betriebsmodus_label"] == "Kühlen"
