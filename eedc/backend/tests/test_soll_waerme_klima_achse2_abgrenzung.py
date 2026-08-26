"""SOLL Wärme/Klima — **Achse II: Abgrenzung.** Wann darf eine Kennzahl NICHT erscheinen?

Maschinelle Fassung der Kernregel **R2** (`soll-waerme-klima.md` §3.2b):

    Eine Kennzahl Q/E erscheint nur, wenn Q und E dieselbe Abgrenzung tragen —
    dasselbe Gerät, dieselbe Funktion, denselben Zeitraum. Weicht eine der drei
    ab, zeigt eedc die Mengen und den Grund, nie den Quotienten.

⭐ **Warum eine Regel und keine Fallliste.** §4.2 zählte vier Lagen auf; drei sind
dieselbe Verletzung. Der Beweis, dass die Abstraktionshöhe stimmt, ist der
**bivalente** Fall (II-2): Er stand in **keiner** Aufzählung, hat **keinen**
Melder — und R2 fängt ihn, weil er dieselbe Regel bricht wie der Heizstab, nur
mit umgekehrtem Vorzeichen.

**Heute gibt es genau EINE Sperre:** ``WpFakten.jaz_belastbar`` deckt den Fall
*Wärme abgeleitet statt gemessen* ab. Sie ist sorgfältig gebaut und bleibt — die
Proben hier zeigen, was sie **nicht** abdeckt.

Schwesterdateien: `test_soll_waerme_klima_achse1_erfassung.py` (Erfassungswege,
R1/K3) und `test_soll_waerme_klima_achse3_aufloesung.py` (Auflösung, P4/S3) —
zusammen die drei Backend-Achsen desselben SOLL; die vierte (Aussage) liegt im
Frontend als `KomponentenSektionen.soll-waerme-klima.test.tsx`. Der
Symmetriepartner für die eine **bestehende** Sperre ist
`test_263_k2_modus_split.py` (dort wird `jaz_belastbar` positiv geprüft).

Proben-Sorten wie in den Schwesterdateien. Kein ``xfail``.
"""

from __future__ import annotations

import inspect

from backend.services.monats_fakten import WpFakten

#: SOLL-Regeln, die noch **nicht** gebaut sind.
REGELN_OFFEN: dict[str, str] = {
    "R2/W-7": (
        "Fremder Strom auf dem Zähler (Fall H-C: Heizstab-Strom auf dem "
        "WP-Zähler, seine Wärme nicht mitgemessen) ⇒ E ist zu groß, die "
        "Arbeitszahl systematisch zu niedrig. Es gibt keine Prüfung darauf — "
        "weder eine Größe, die den Fall ausdrückt, noch einen Hinweis."
    ),
    "R2/F12": (
        "Bivalent: ein zweiter Wärmeerzeuger speist denselben Kreis, sein "
        "Aufwand liegt nicht auf dem WP-Zähler ⇒ Q ist zu groß, die "
        "Arbeitszahl zu hoch. Dieselbe Verletzung wie W-7 mit umgekehrtem "
        "Vorzeichen. KEIN Melder, stand in keiner Fallliste."
    ),
    "R2/W-3": (
        "Die Sperre `jaz_belastbar` existiert im Layer, erreicht aber die "
        "Cockpit-Sichten nicht: `AktuellerMonatResponse` liefert "
        "`wp_waerme_kwh` und `wp_strom_kwh` ohne Belastbarkeits-Flag, und der "
        "Client rechnet die JAZ daraus selbst (ADR-001-Verstoß)."
    ),
    "R2/Zeitraum": (
        "Q aus dem Monatsabschluss gegen E aus laufenden Sensoren ergibt einen "
        "Quotienten aus zwei Wirklichkeiten (SOLL §4.2 Fall 3). Keine Prüfung."
    ),
    "R2/PassivKuehlung": (
        "Passive Kühlung (nur Umwälzpumpen) hat einen um ein Vielfaches "
        "höheren EER als aktive. Die Kennzahl ist korrekt, ein VERGLEICH "
        "wäre eine Falschaussage — auch im Community-Benchmark. Es gibt keine "
        "Markierung. KEIN Melder (SOLL §7/A5)."
    ),
}


def _wp(**kw) -> WpFakten:
    """WpFakten mit den Mengen einer realen Anlage."""
    return WpFakten(**kw)


# ══ II-1 · OFFEN — R2: fremder Strom auf dem Zähler (Fall H-C) ══════════════

def test_ii1_heizstab_strom_auf_dem_wp_zaehler():
    """**OFFEN (R2/W-7).** Fall H-C aus SOLL §2.2.1 — der einzige echte Fehlerfall.

    Lage: Der Heizstab hängt am WP-Zähler, seine Wärme läuft **nicht** über den
    Wärmemengenzähler. E ist damit zu groß für das Q, zu dem es gehört.

    SOLL §4.2/R2: *„eedc zeigt die Mengen und lässt die Kennzahl weg — mit dem
    Grund daneben. Nicht ‚—', sondern ‚keine Arbeitszahl: auf diesem Zähler liegt
    auch der Heizstab.'"*

    Heute: ``jaz_belastbar`` ist **True**, weil die Wärme gemessen (nicht
    abgeleitet) ist — die einzige vorhandene Sperre prüft die falsche Achse. Es
    gibt außerdem **keine Größe**, mit der der Anwender den Fall überhaupt
    ausdrücken könnte.

    ⛔ **Dieser Befund stand in Fassung 1 des Etappe-2-Plans NICHT auf der
    Bauliste** — gestrichen mit der Begründung „kein bestätigter Betroffener".
    Das war der Methodenfehler, den Gernot am 26.08. beanstandet hat: Die
    Abwesenheit eines Melders ist kein Beleg. Der Fall ist physikalisch
    definiert, und ein Modell, das ihn nicht ausdrücken kann, ist später nicht
    nachrüstbar.
    """
    assert "R2/W-7" in REGELN_OFFEN
    # 900 kWh Strom (WP + Heizstab), 2000 kWh gemessene Wärme (nur WP-Kreis).
    wp = _wp(strom_kwh=900.0, waerme_kwh=2000.0, waerme_abgeleitet_kwh=0.0)

    # Die vorhandene Sperre greift nicht — sie prüft nur die Herkunft der Wärme.
    assert wp.jaz_belastbar is True

    # Und es gibt keine Größe, die „fremder Strom auf diesem Zähler" ausdrückt.
    assert not [f for f in WpFakten.__dataclass_fields__ if "fremd" in f]


# ══ II-2 · OFFEN — R2: fremde Wärme im Nutzen (bivalent) ════════════════════

def test_ii2_bivalent_fremde_waerme_im_nutzen():
    """**OFFEN (R2/F12).** Die Gegenrichtung von II-1 — und der Prüfstein der Regel.

    Lage: Ein Gaskessel speist unter dem Bivalenzpunkt denselben Heizkreis. Der
    Wärmemengenzähler sitzt am Kreis und misst **beide** Erzeuger; der Stromzähler
    kennt nur die Wärmepumpe. **Q ist zu groß**, die Arbeitszahl zu hoch.

    SOLL §3.2b: dieselbe Sperre wie II-1, *„nur ist hier Q zu groß statt E"*.

    Heute: ``jaz_belastbar`` ist **True**, und die Anlage weist eine Arbeitszahl
    von 5,0 aus, die es nicht gibt.

    ⭐ **Dieser Fall ist der Beleg, dass R2 die richtige Abstraktionshöhe hat.**
    Er hat **keinen Melder** und stand in **keiner** der vier Lagen von §4.2. Er
    ist erst sichtbar geworden, als die Fallsammlung zu einer Regel
    verallgemeinert wurde — eine Aufzählung hätte ihn nie hervorgebracht.
    """
    assert "R2/F12" in REGELN_OFFEN
    # 400 kWh WP-Strom, 2000 kWh Wärme am Kreis — davon ein Teil vom Gaskessel.
    wp = _wp(strom_kwh=400.0, waerme_kwh=2000.0, waerme_abgeleitet_kwh=0.0)

    assert wp.jaz_belastbar is True
    assert wp.waerme_kwh / wp.strom_kwh == 5.0  # eine Zahl, die es nicht gibt

    assert not [f for f in WpFakten.__dataclass_fields__ if "bivalent" in f]


# ══ II-3 · ERFÜLLT — die eine Sperre, die es gibt, hält ═════════════════════

def test_ii3_abgeleitete_waerme_sperrt_die_kennzahl():
    """**ERFÜLLT.** Ist auch nur ein Teil der Wärme aus ``Strom × JAZ`` gerechnet,
    ist die Kennzahl gesperrt.

    ⚠ **Diese Probe hält fest, was die Lösung von II-1/II-2 nicht verschlechtern
    darf.** ``jaz_belastbar`` ist sorgfältig gebaut — insbesondere zieht es den
    abgeleiteten Teil **nicht ab** (das gäbe gemessene Wärme geteilt durch
    Gesamtstrom: falsch statt unbekannt). Eine allgemeine R2-Prüfung tritt
    **daneben**, nicht an ihre Stelle.
    """
    gemessen = _wp(strom_kwh=500.0, waerme_kwh=2000.0, waerme_abgeleitet_kwh=0.0)
    teilweise = _wp(strom_kwh=500.0, waerme_kwh=2000.0, waerme_abgeleitet_kwh=1.0)

    assert gemessen.jaz_belastbar is True
    assert teilweise.jaz_belastbar is False


# ══ II-4 · OFFEN — R2/S1: die Sperre erreicht die Cockpit-Sichten nicht ═════

def test_ii4_monatssicht_liefert_kein_belastbarkeits_flag():
    """**OFFEN (R2/W-3).**

    ``jaz_belastbar`` wird im Komponenten-Hub und in der Cockpit-Übersicht
    ausgewertet. Die Sicht, die die Melder tatsächlich ansehen — *Cockpit →
    Tag/Monat/Jahr* — bekommt das Flag gar nicht: Die Response liefert
    ``wp_waerme_kwh`` (Gesamtwärme **inklusive** abgeleiteter Anteile) und
    ``wp_strom_kwh``, sonst nichts.

    Der Client bildet daraus die JAZ selbst
    (``v4/KomponentenSektionen.tsx:311``). Er **kann** die Sperre nicht kennen.

    SOLL §3.3/S1 und ADR-001: *„Wo zwei Sichten dieselbe Frage beantworten,
    rechnet EINE Stelle — der Layer, nicht der Client."* Erwartung nach dem Bau:
    Die Response trägt das Flag (oder gleich die fertige Kennzahl).

    **Folge heute:** Dieselbe Anlage kann im Hub „—" zeigen und im Cockpit eine
    Zahl. Zwei Sichten, zwei Antworten auf dieselbe Frage.
    """
    assert "R2/W-3" in REGELN_OFFEN
    from backend.api.routes.aktueller_monat import AktuellerMonatResponse

    felder = set(AktuellerMonatResponse.model_fields)

    assert "wp_waerme_kwh" in felder
    assert "wp_strom_kwh" in felder
    assert "wp_jaz_belastbar" not in felder
    assert "wp_waerme_abgeleitet" not in felder


def test_ii4b_komponenten_hub_wertet_die_sperre_aus():
    """**ERFÜLLT.** Der Hub kennt das Flag und reicht es weiter.

    Gegenprobe zu II-4: Sie belegt, dass die Sperre **existiert und wirkt** — der
    Befund ist also eine Vertragslücke zwischen Layer und Cockpit-Route, kein
    fehlendes Konzept. Ohne diese Probe wäre W-3 nur die Beobachtung „der Client
    rechnet selbst"; erst der Kontrast macht daraus den ADR-001-Fall.
    """
    from backend.api.routes.cockpit import komponenten

    quelle = inspect.getsource(komponenten)

    assert "jaz_belastbar" in quelle
    assert "wp_waerme_abgeleitet" in quelle


# ══ II-5 · OFFEN — R2: Q und E aus verschiedenen Zeiträumen ═════════════════

def test_ii5_zeitraum_mismatch_wird_nicht_erkannt():
    """**OFFEN (R2/Zeitraum).** SOLL §4.2 Fall 3.

    Lage: Die Wärme ist im Monatsabschluss gepflegt (ein Wert für den ganzen
    Monat), der Strom kommt aus laufenden Sensoren. Fehlen dem Monat Sensortage —
    Ausfall, Nachrüstung mitten im Monat —, stehen Zähler und Nutzen für
    **verschiedene Zeiträume**.

    Erwartung nach dem Bau: Die Kennzahl entfällt mit Begründung.

    Heute: ``WpFakten`` führt keine Angabe darüber, **über welchen Zeitraum** Q
    und E jeweils entstanden sind — der Mismatch ist aus den Daten gar nicht
    ableitbar. Das ist der Grund, warum hier eine **Größe fehlt** und nicht nur
    eine Prüfung.
    """
    assert "R2/Zeitraum" in REGELN_OFFEN
    felder = set(WpFakten.__dataclass_fields__)

    assert not [f for f in felder if "abdeckung_tage" in f or "zeitraum" in f]
    # Die einzige Abdeckungs-Größe misst Modus-Stunden, nicht Mengen-Zeiträume.
    assert "modus_abdeckung_h" in felder


# ══ II-6 · OFFEN — R2: passive Kühlung darf nicht verglichen werden ═════════

def test_ii6_passive_kuehlung_ist_nicht_markierbar():
    """**OFFEN (R2/PassivKuehlung).** SOLL §3.2b und §4.1.

    Eine Sole-Wasser-Anlage kühlt oft **passiv** — nur Umwälzpumpen, kein
    Kompressor. Der EER liegt dann um ein Vielfaches über dem einer aktiv
    gekühlten Anlage. **Die Kennzahl selbst ist korrekt** (Q/E stimmt); was eine
    Falschaussage wäre, ist ein **Vergleich** oder ein Rang gegen aktiv gekühlte
    Anlagen — insbesondere im Community-Benchmark.

    Erwartung nach dem Bau: eine Markierung an der Kennzahl, kein neues Feld für
    eine Menge.

    Heute: Es gibt keine Möglichkeit, passive von aktiver Kühlung zu
    unterscheiden.

    ⛔ **Kein bekannter Anwender** (SOLL §7/A5) — die Probe steht trotzdem hier.
    Sie prüft, ob das **Modell** die Unterscheidung tragen kann; eine Ansicht
    darf warten, ein Modell nicht.
    """
    assert "R2/PassivKuehlung" in REGELN_OFFEN
    from backend.core.investition_parameter import PARAM_WAERMEPUMPE

    # Der Parameter-SoT der Wärmepumpe kennt keine Kühlart.
    assert not [k for k in PARAM_WAERMEPUMPE.values() if "passiv" in k or "kuehl" in k]

    # Und `wp_art` unterscheidet nur die Bauart, nicht die Art der Kühlung —
    # dieselbe Schubladen-Logik, die R1 an anderer Stelle ablöst.
    assert PARAM_WAERMEPUMPE["WP_ART"] == "wp_art"
