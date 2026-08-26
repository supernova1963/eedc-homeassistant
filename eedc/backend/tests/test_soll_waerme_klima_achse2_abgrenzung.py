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


# ══ II-2b · ERFÜLLT — R2/Gerät: die Lage, die eedc SELBST erkennt ══════════

def test_ii2b_zwei_geraete_ein_zaehler_nur_eines_meldet_waerme():
    """**ERFÜLLT (R2, SOLL §4.2 Fall 1 — gebaut 2026-08-26).**

    Lage: Der Block *Wärme/Klima* aggregiert **alle** Wärmepumpen der Anlage.
    Trägt eines der Geräte Strom, aber keine Wärme, steht im Nenner der Strom
    von zwei Geräten und im Zähler die Wärme von einem — die Arbeitszahl ist
    systematisch zu niedrig.

    ⭐ **Von den vier Lagen des §4.2 ist das die einzige, für die eedc keine
    Angabe des Anwenders braucht.** Sie steht in den Daten: Wie viele Geräte
    haben Strom beigetragen, wie viele davon auch Wärme? Heizstab am Zähler
    (II-1), bivalenter Zweiterzeuger (II-2) und Zeitraum-Versatz (II-5) sind
    von außen unsichtbar — deshalb sind die drei weiter offen und diese hier
    ist gebaut.

    **Melder dietmar1968**, sein Screenshot nennt die Konstellation selbst:
    *„Aggregiert aus: Wärmepumpe · Klimaanlage"* bei einer JAZ von 0,92.
    ⚠ Dass genau diese Vermischung **seine** Zahl erzeugt, bleibt **ungemessen**
    (SOLL §7/A2) — der Heizstab ist die sparsamere Erklärung. Die Regel gilt
    unabhängig davon, welche Erklärung im Einzelfall zutrifft.
    """
    from backend.core.berechnungen.waermepumpe_kennzahl import (
        GRUND_GERAETE_OHNE_WAERME, arbeitszahl,
    )

    # Zwei Geräte tragen Strom, nur eines meldet Wärme.
    wp = _wp(strom_kwh=337.0, waerme_kwh=309.0,
             geraete_mit_strom=2, geraete_mit_waerme=1)
    assert wp.waerme_deckt_nicht_alle_geraete is True

    gesperrt = arbeitszahl(
        wp.waerme_kwh, wp.strom_kwh,
        abgrenzung_verletzt=GRUND_GERAETE_OHNE_WAERME,
    )
    assert gesperrt.wert is None
    assert gesperrt.grund == GRUND_GERAETE_OHNE_WAERME


def test_ii2c_jedes_geraet_meldet_waerme_die_kennzahl_bleibt():
    """**ERFÜLLT.** Melden alle Geräte Wärme, gibt es die Kennzahl.

    ⚠ **Die Gegenprobe ist hier besonders wichtig**, weil die Sperre auf einer
    *anlagenweiten* Größe sitzt: Eine zu scharfe Regel hätte jede Anlage mit
    mehreren Wärmepumpen um ihre Arbeitszahl gebracht. Verglichen wird deshalb
    **Wärme-Melder gegen Strom-Melder**, nicht gegen die Zahl der Geräte —
    ein im Monat stillstehendes Gerät trägt weder das eine noch das andere und
    verändert das Ergebnis nicht.
    """
    from backend.core.berechnungen.waermepumpe_kennzahl import arbeitszahl

    beide = _wp(strom_kwh=500.0, waerme_kwh=2000.0,
                geraete_mit_strom=2, geraete_mit_waerme=2)
    assert beide.waerme_deckt_nicht_alle_geraete is False
    assert arbeitszahl(beide.waerme_kwh, beide.strom_kwh).wert == 4.0

    # Ein drittes Gerät stand still — es trägt zu keiner der beiden Seiten bei.
    stillstand = _wp(strom_kwh=500.0, waerme_kwh=2000.0,
                     geraete_mit_strom=2, geraete_mit_waerme=2)
    assert stillstand.waerme_deckt_nicht_alle_geraete is False


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

def test_ii4_monatssicht_liefert_die_fertige_kennzahl():
    """**ERFÜLLT (R2/W-3 — gebaut 2026-08-26).**

    ``jaz_belastbar`` wird im Komponenten-Hub und in der Cockpit-Übersicht
    ausgewertet. Die Sicht, die die Melder tatsächlich ansehen — *Cockpit →
    Tag/Monat/Jahr* — bekommt das Flag gar nicht: Die Response liefert
    ``wp_waerme_kwh`` (Gesamtwärme **inklusive** abgeleiteter Anteile) und
    ``wp_strom_kwh``, sonst nichts.

    Der Client bildet daraus die JAZ selbst
    (``v4/KomponentenSektionen.tsx:311``). Er **kann** die Sperre nicht kennen.

    SOLL §3.3/S1 und ADR-001: *„Wo zwei Sichten dieselbe Frage beantworten,
    rechnet EINE Stelle — der Layer, nicht der Client."*

    **Gebaut wurde die stärkere der beiden Möglichkeiten:** nicht das Flag,
    sondern die **fertige Kennzahl samt Begründung**. Ein Flag hätte den Client
    weiterhin rechnen lassen und ihm nur eine zweite Bedingung mitgegeben — die
    Formel wäre an zwei Stellen geblieben. Jetzt liefert der Layer
    (`core/berechnungen/waermepumpe_kennzahl.arbeitszahl`) `wp_jaz`,
    `wp_jaz_grund` und `wp_jaz_hinweis`; Hub, Übersicht, Monat und Tag lesen
    dieselbe Funktion.

    **Vorher:** Dieselbe Anlage konnte im Hub „—" zeigen und im Cockpit eine
    Zahl. Zwei Sichten, zwei Antworten auf dieselbe Frage.

    ⭐ **Der Grund gehört zur Zahl, nicht daneben.** ``wp_jaz_grund`` ist der
    Unterschied zwischen „—" und „kein Wärmemengenzähler zugeordnet" — genau
    die Beschwerde, die S3 adressiert.
    """
    assert "R2/W-3" not in REGELN_OFFEN
    from backend.api.routes.aktueller_monat import AktuellerMonatResponse

    felder = set(AktuellerMonatResponse.model_fields)

    assert "wp_waerme_kwh" in felder
    assert "wp_strom_kwh" in felder
    assert "wp_jaz" in felder
    assert "wp_jaz_grund" in felder
    assert "wp_waerme_abgeleitet" in felder


def test_ii4c_der_layer_nennt_zu_jeder_sperre_ihren_grund():
    """**ERFÜLLT (R2 + S3).** Jede Sperre liefert einen **kurzen, sichtbaren**
    Grund — der Unterschied zwischen „—" und einer Auskunft.

    ⚠ **Kurz ist eine Anforderung, keine Kosmetik.** Der Text steht als sichtbare
    Zeile unter dem „—", nicht in einem Hover-Tooltip: S3 verlangt *„nicht ‚—',
    sondern der Grund"*, und ein Tooltip ist auf dem Telefon keine Auskunft.
    Die erste Fassung schrieb ganze Sätze und passte damit nirgends hin.
    """
    from backend.core.berechnungen.waermepumpe_kennzahl import arbeitszahl

    ohne_strom = arbeitszahl(2000.0, 0.0)
    ohne_waerme = arbeitszahl(0.0, 500.0)
    abgeleitet = arbeitszahl(2000.0, 500.0, waerme_abgeleitet_kwh=1.0)

    for fall in (ohne_strom, ohne_waerme, abgeleitet):
        assert fall.wert is None
        assert fall.belastbar is False
        assert fall.grund
        assert len(fall.grund) <= 40, f"zu lang für die Kachel: {fall.grund!r}"

    # Die drei Gründe sind verschieden — sonst wäre die Auskunft wertlos.
    assert len({ohne_strom.grund, ohne_waerme.grund, abgeleitet.grund}) == 3


def test_ii4d_heizstab_schwelle(monkeypatch):
    """**ERFÜLLT (§2.2.1/W-6, Fall H-B).** Eine Arbeitszahl unter 2 trägt ihren
    erklärenden Satz, eine darüber nicht.

    ⭐ **Diese Probe steht im Backend, weil die Schwelle dorthin gewandert ist.**
    Sie lag beim Bau kurz im Client — dort hätte sie neben der JAZ-Formel
    gestanden, die mit W-3 gerade aus dem Client verschwunden ist. *Eine Regel
    zieht ihre Prüfung mit.* Die Frontend-Schwester
    (`KomponentenSektionen.soll-waerme-klima.test.tsx`) prüft nur noch, dass der
    Client den gelieferten Satz auch **anzeigt**.

    ⚠ **Der Satz erklärt die Zahl, er bewertet den Anwender nicht.** Eine
    Anlage, die ihr Warmwasser über den Heizstab macht, *hat* eine Arbeitszahl
    nahe 1 — das ist die Wahrheit über sie, kein Fehler
    ([[feedback_eedc_ist_nicht_die_strom_polizei]]).
    """
    from backend.core.berechnungen.waermepumpe_kennzahl import (
        JAZ_HEIZSTAB_SCHWELLE, arbeitszahl,
    )

    # dietmars Juli: 309 kWh Wärme ÷ 337 kWh Strom = 0,92.
    dietmar = arbeitszahl(309.0, 337.0)
    assert round(dietmar.wert, 2) == 0.92
    assert dietmar.hinweis and "Heizstab" in dietmar.hinweis
    # Die Zahl bleibt unverändert — erklärt wird sie, nicht korrigiert.
    assert dietmar.belastbar is True

    unauffaellig = arbeitszahl(2000.0, 500.0)
    assert unauffaellig.wert == 4.0
    assert unauffaellig.hinweis is None

    # Genau an der Schwelle noch kein Hinweis (sie ist „unter 2", nicht „bis 2").
    assert arbeitszahl(JAZ_HEIZSTAB_SCHWELLE, 1.0).hinweis is None
    assert arbeitszahl(JAZ_HEIZSTAB_SCHWELLE - 0.01, 1.0).hinweis is not None


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
