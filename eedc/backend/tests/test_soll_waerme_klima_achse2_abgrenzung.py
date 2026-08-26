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

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_FREMDSTROM,
    GRUND_FREMDWAERME,
    GRUND_GERAETE_OHNE_WAERME,
    GRUND_ZEITRAUM,
    abgrenzungs_grund,
    arbeitszahl,
)
from backend.core.investition_parameter import abgrenzung_stoerung
from backend.services.monats_fakten import WpFakten

#: SOLL-Regeln, die noch **nicht** gebaut sind.
REGELN_OFFEN: dict[str, str] = {}
#: ⭐ **Leer seit dem 26.08.2026 — Achse II ist gebaut.** Die vier Lagen des
#: SOLL §4.2 tragen jetzt alle ihren Grund: `waerme_deckt_nicht_alle_geraete`
#: (aus den Daten erkannt), `abgrenzung_stoerung` (Anwender-Angabe, zwei
#: Vorzeichen), der Zeitraum-Versatz (aus `teilzeitraum` in der Route) und die
#: abgeleitete Wärme (`jaz_belastbar`, unverändert).


def _wp(**kw) -> WpFakten:
    """WpFakten mit den Mengen einer realen Anlage."""
    return WpFakten(**kw)


# ══ II-1 · OFFEN — R2: fremder Strom auf dem Zähler (Fall H-C) ══════════════

def test_ii1_heizstab_strom_auf_dem_wp_zaehler():
    """**ERFÜLLT (R2/W-7, gebaut 2026-08-26).** Fall H-C aus SOLL §2.2.1 — der
    einzige echte Fehlerfall unter den drei Heizstab-Lagen.

    Lage: Der Heizstab hängt am WP-Zähler, seine Wärme läuft **nicht** über den
    Wärmemengenzähler. E ist damit zu groß für das Q, zu dem es gehört.

    SOLL §4.2/R2: *„eedc zeigt die Mengen und lässt die Kennzahl weg — mit dem
    Grund daneben. Nicht ‚—', sondern ‚keine Arbeitszahl: auf diesem Zähler
    liegt auch der Heizstab.'"*

    ⛔ **Dieser Befund stand in Fassung 1 des Etappe-2-Plans NICHT auf der
    Bauliste** — gestrichen mit der Begründung „kein bestätigter Betroffener".
    Das war der Methodenfehler, den Gernot am 26.08. beanstandet hat: Die
    Abwesenheit eines Melders ist kein Beleg. Der Fall ist physikalisch
    definiert, und ein Modell, das ihn nicht ausdrücken kann, ist später nicht
    nachrüstbar.
    """
    assert "R2/W-7" not in REGELN_OFFEN
    # 900 kWh Strom (WP + Heizstab), 2000 kWh gemessene Wärme (nur WP-Kreis).
    wp = _wp(strom_kwh=900.0, waerme_kwh=2000.0, waerme_abgeleitet_kwh=0.0,
             abgrenzung_stoerung="fremdstrom")

    # ⚠ `jaz_belastbar` bleibt UNVERÄNDERT True — es prüft die Herkunft der
    # Wärme, und die ist hier gemessen. Die R2-Prüfung tritt DANEBEN, nicht an
    # seine Stelle (Auftragsvorgabe, s. II-3).
    assert wp.jaz_belastbar is True

    gesperrt = arbeitszahl(
        wp.waerme_kwh, wp.strom_kwh,
        abgrenzung_verletzt=abgrenzungs_grund(
            abgrenzung_stoerung=wp.abgrenzung_stoerung,
        ),
    )
    assert gesperrt.wert is None
    assert gesperrt.grund == GRUND_FREMDSTROM
    # Die Mengen bleiben — gesperrt ist der Quotient, nicht die Messung.
    assert (wp.strom_kwh, wp.waerme_kwh) == (900.0, 2000.0)


# ══ II-2 · ERFÜLLT — R2: fremde Wärme im Nutzen (bivalent) ═════════════════

def test_ii2_bivalent_fremde_waerme_im_nutzen():
    """**ERFÜLLT (R2/F12, gebaut 2026-08-26).** Die Gegenrichtung von II-1 — und
    der Prüfstein der Regel.

    Lage: Ein Gaskessel speist unter dem Bivalenzpunkt denselben Heizkreis. Der
    Wärmemengenzähler sitzt am Kreis und misst **beide** Erzeuger; der
    Stromzähler kennt nur die Wärmepumpe. **Q ist zu groß**, die Arbeitszahl zu
    hoch — vorher wies die Anlage 5,0 aus, eine Zahl, die es nicht gibt.

    ⭐ **Dieser Fall ist der Beleg, dass R2 die richtige Abstraktionshöhe hat.**
    Er hat **keinen Melder** und stand in **keiner** der vier Lagen von §4.2. Er
    ist erst sichtbar geworden, als die Fallsammlung zu einer Regel
    verallgemeinert wurde — eine Aufzählung hätte ihn nie hervorgebracht.

    ⚠ **Und deshalb trägt er dieselbe Größe wie II-1, nicht eine eigene.** Ein
    Flag je Beispiel hätte die Fallsammlung in den Code geholt; ein Feld mit zwei
    Werten hält die eine Regel zusammen.
    """
    assert "R2/F12" not in REGELN_OFFEN
    # 400 kWh WP-Strom, 2000 kWh Wärme am Kreis — davon ein Teil vom Gaskessel.
    wp = _wp(strom_kwh=400.0, waerme_kwh=2000.0, waerme_abgeleitet_kwh=0.0,
             abgrenzung_stoerung="fremdwaerme")

    assert wp.jaz_belastbar is True
    gesperrt = arbeitszahl(
        wp.waerme_kwh, wp.strom_kwh,
        abgrenzung_verletzt=abgrenzungs_grund(
            abgrenzung_stoerung=wp.abgrenzung_stoerung,
        ),
    )
    assert gesperrt.wert is None
    assert gesperrt.grund == GRUND_FREMDWAERME


def test_ii2a_ohne_angabe_bleibt_die_kennzahl():
    """**ERFÜLLT.** Gegenprobe zu II-1/II-2: Ohne Angabe ändert sich nichts.

    ⚠ **Die wichtigste der drei Proben dieses Blocks.** Die neue Größe ist eine
    **Anwender-Angabe**, und der Default gilt für jede bestehende Anlage im Feld.
    Eine Sperre, die schon bei `None` oder bei einem unbekannten Wert griffe,
    hätte jeder Anlage still ihre Arbeitszahl genommen — ohne dass jemand etwas
    geändert hätte.

    `None` heißt **„keine bekannte Abweichung"**, nicht „geprüft und in Ordnung":
    Was eedc nicht sehen kann, behauptet es auch nicht.
    """
    ohne = _wp(strom_kwh=500.0, waerme_kwh=2000.0)
    assert ohne.abgrenzung_stoerung is None
    assert arbeitszahl(
        ohne.waerme_kwh, ohne.strom_kwh,
        abgrenzung_verletzt=abgrenzungs_grund(
            abgrenzung_stoerung=ohne.abgrenzung_stoerung,
        ),
    ).wert == 4.0

    # Ein unbekannter Wert (Altbestand, Import-Tippfehler) sperrt ebenfalls
    # nicht — eine Sperre auf einen Wert zu stützen, den niemand gesetzt haben
    # kann, wäre eine erfundene Auskunft.
    assert abgrenzung_stoerung({"abgrenzung": "haus"}) is None


def test_ii2d_die_anwender_angabe_schlaegt_die_selbsterkennung():
    """**ERFÜLLT (Entscheid Gernot, 26.08.2026).** Wenn zwei Gründe zutreffen,
    gewinnt der konkretere.

    Eine Anlage kann beides sein: zwei Geräte auf einem Block, von denen nur
    eines Wärme meldet (erkennt eedc selbst) **und** ein Heizstab auf dem
    WP-Zähler (weiß nur der Anwender). Beide Gründe wären richtig; die Kachel
    trägt aber einen.

    ⭐ **Wer etwas eingetragen hat, soll seinen Satz wiederfinden.** „Nicht alle
    Geräte melden Wärme" wäre auf dieselbe Anlage anwendbar und trotzdem die
    schlechtere Auskunft — sie erklärt nicht, was er selbst gemeldet hat
    (SOLL §3.3/**S3**).
    """
    assert abgrenzungs_grund(
        abgrenzung_stoerung="fremdstrom", geraete_ohne_waerme=True,
    ) == GRUND_FREMDSTROM
    # Ohne Angabe greift die Selbsterkennung unverändert.
    assert abgrenzungs_grund(geraete_ohne_waerme=True) == GRUND_GERAETE_OHNE_WAERME


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


# ══ II-5 · ERFÜLLT — R2: Q und E aus verschiedenen Zeiträumen ═════════════

def test_ii5_zeitraum_versatz_sperrt_die_kennzahl():
    """**ERFÜLLT (R2/Zeitraum, gebaut 2026-08-26).** SOLL §4.2 Fall 3.

    Lage: Die Wärme ist im Monatsabschluss gepflegt (ein Wert für den ganzen
    Monat), der Strom kommt aus einem Connector-Delta, das erst mitten im Monat
    zu zählen begann. Zähler und Nutzen stehen für **verschiedene Zeiträume**.

    ⭐ **Die Größe dafür musste nicht erfunden werden — sie war schon da.**
    `teilzeitraum_felder` (`core/berechnungen/datenquellen.py`) weist genau die
    Felder aus, deren Endwert nur einen Ausschnitt des Monats misst; gebaut für
    #361/coolxmad #353, wo ein frisch eingerichteter Connector mit 0 kWh eine
    vollständige HA-Summe verdrängte. Steht **genau eine** der beiden Seiten
    darin, ist die Abgrenzung verletzt.

    ⛔ **Der naheliegende Weg wäre falsch gewesen, und das ist der Kern.** Der
    ursprüngliche Entwurf sah eine Abdeckungs-Größe in `WpFakten` vor — „an wie
    vielen Tagen des Monats gab es einen Wert?". Zwei Gründe sprechen dagegen:

    1. `WpFakten` faltet **IMD-Monatszeilen** und kennt die Herkunft der Werte
       gar nicht; die Vier-Quellen-Auflösung passiert eine Ebene höher.
    2. Eine Tages-Zählung kann *„kein Wert, weil das Gerät stand"* nicht von
       *„kein Wert, weil der Sensor fehlte"* unterscheiden. Bei einer
       Wärmepumpe im Juli ist Ersteres der Normalfall — der Wächter meldete
       jeden Sommer bei jeder Anlage. Genau die Fehlalarm-Klasse, die §2i-6
       schon einmal eingefangen hat (dort 3 von 3 Meldungen).
    """
    assert "R2/Zeitraum" not in REGELN_OFFEN
    from backend.core.berechnungen.datenquellen import teilzeitraum_felder

    def _versatz(teilzeitraum: set[str]) -> bool:
        return sum(
            1 for f in ("wp_waerme_kwh", "wp_strom_kwh") if f in teilzeitraum
        ) == 1

    assert _versatz({"wp_strom_kwh"}) is True
    assert _versatz({"wp_waerme_kwh"}) is True
    # ⚠ **Beide Seiten unvollständig ist KEIN Versatz.** Im laufenden Monat
    # misst jede Sensor-Größe naturgemäß „bis heute" — solange das für Q und E
    # gleichermaßen gilt, tragen sie denselben Zeitraum und der Quotient steht.
    assert _versatz({"wp_waerme_kwh", "wp_strom_kwh"}) is False
    assert _versatz(set()) is False

    gesperrt = arbeitszahl(
        2000.0, 500.0,
        abgrenzung_verletzt=abgrenzungs_grund(zeitraum_versetzt=True),
    )
    assert gesperrt.wert is None
    assert gesperrt.grund == GRUND_ZEITRAUM

    # Die Quelle der Wahrheit existiert und liefert die erwartete Form.
    leer = teilzeitraum_felder(
        saved={}, connector={}, mqtt_energy={}, ha_stats={},
        ist_aktueller_monat=True,
    )
    assert leer == set()


def test_ii5b_die_zeitraum_pruefung_sitzt_wo_die_quellen_bekannt_sind():
    """**ERFÜLLT.** Nur `aktueller_monat` kann den Versatz überhaupt sehen.

    ⚠ **Das ist keine Lücke, sondern die Wahrheit über die drei Sichten.** Hub
    und Tagesansicht lesen jeweils **eine** Quelle; ein Versatz zwischen zwei
    Quellen kann dort nicht entstehen. Ihn dort zu „prüfen" hieße, eine
    Bedingung zu behaupten, die nie zutreffen kann — der Prüfer wäre grün und
    wertlos ([[feedback_probe_unerreichbarer_zustand]]).
    """
    import inspect as _inspect

    from backend.api.routes import aktueller_monat

    quelle = _inspect.getsource(aktueller_monat)
    assert "teilzeitraum" in quelle
    assert "zeitraum_versetzt" in quelle


# ══ II-6 · ERFÜLLT — R2: passive Kühlung wird nicht verglichen ═════════════

def test_ii6_passive_kuehlung_ist_markierbar():
    """**ERFÜLLT (R2/PassivKühlung, gebaut 2026-08-26).** SOLL §3.2b und §4.1.

    Eine Sole-Wasser-Anlage kühlt oft **passiv** — nur Umwälzpumpen, kein
    Kompressor. Der EER liegt dann um ein Vielfaches über dem einer aktiv
    gekühlten Anlage. **Die Kennzahl selbst ist korrekt** (Q/E stimmt); was eine
    Falschaussage wäre, ist ein **Vergleich** oder ein Rang gegen aktiv gekühlte
    Anlagen — insbesondere im Community-Benchmark.

    ⛔ **Kein bekannter Anwender** (SOLL §7/A5) — die Probe steht trotzdem hier.
    Sie prüft, ob das **Modell** die Unterscheidung tragen kann; eine Ansicht
    darf warten, ein Modell nicht.

    ⚠ **Eine Markierung, keine Menge.** `kuehlung_art` sperrt nichts und
    korrigiert nichts — es nimmt die Anlage aus dem Ranking.
    """
    assert "R2/PassivKuehlung" not in REGELN_OFFEN
    from backend.core.investition_parameter import (
        KUEHLUNG_AKTIV, KUEHLUNG_KEINE, KUEHLUNG_PASSIV, PARAM_WAERMEPUMPE,
        kuehlt_passiv,
    )

    assert PARAM_WAERMEPUMPE["KUEHLUNG_ART"] == "kuehlung_art"
    assert kuehlt_passiv({"kuehlung_art": KUEHLUNG_PASSIV}) is True
    assert kuehlt_passiv({"kuehlung_art": KUEHLUNG_AKTIV}) is False
    assert kuehlt_passiv({"kuehlung_art": KUEHLUNG_KEINE}) is False
    # Altbestand ohne Angabe ist NICHT passiv — unbekannt heißt unbekannt.
    assert kuehlt_passiv({}) is False
    assert kuehlt_passiv(None) is False


def test_ii6b_die_markierung_erreicht_den_community_payload():
    """**ERFÜLLT (R2/PassivKühlung).** Die Markierung nützt nur, wenn sie ankommt.

    ⭐ **Der Server rechnet nichts nach** — er hat die Rohdaten nie gesehen
    (CLAUDE.md, Community-Datenfluss). Eine Unterscheidung, die eedc trifft und
    nicht überträgt, existiert für den Benchmark nicht. Die Auswertung selbst
    liegt im Schwester-Repo (`eedc-community`: `berechne_community_avg_jaz`
    nimmt passiv gekühlte Anlagen aus dem Durchschnitt, und wer passiv kühlt,
    bekommt keinen `community_avg` gegen einen Schnitt, in dem er nicht
    vorkommt).
    """
    import inspect as _inspect

    from backend.services import community_service

    quelle = _inspect.getsource(community_service)
    assert '"kuehlung_art": kuehlung_art' in quelle
    # W-14 fährt auf demselben Weg mit: der Kühlstrom als Teilmenge.
    assert "wp_strom_kuehlen_kwh" in quelle


# ══ II-7 · ERFÜLLT — R2/W-14: Kühlstrom gehört nicht in den Nenner ═════════

def test_ii7_kuehlstrom_faellt_aus_der_arbeitszahl():
    """**ERFÜLLT (W-14, gebaut 2026-08-26).** SOLL §4.2 **Fall 4** — *„wenn eine
    Funktion fehlt"*.

    Lage: Eine Anlage heizt **und** kühlt über denselben Zähler. Ihr Kühlstrom
    steht im Nenner der Arbeitszahl, die zugehörige **Kältemenge** in keinem
    Zähler — eedc führt sie nicht als Wärme, und die wenigsten Anlagen haben
    einen Kältemengenzähler. Wer kühlt, stand damit systematisch schlechter da
    als wer es nicht tut.

    ⭐ **Das ist keine neue Entscheidung, sondern die dritte Anwendung einer
    bereits getroffenen** (#263 K-2, Entscheid **E-B**): `berechne_wp_ersparnis`
    und `berechne_co2_bilanz` rechnen den Kühlstrom seit v4.0.5 heraus, mit
    gemessener Begründung — an einer realen Anlage standen 26,4 kWh Heizen gegen
    158,4 kWh Kühlen und ergaben **−45,04 €** Ersparnis und **−52 kg** CO₂. Die
    Arbeitszahl war die einzige der drei Größen, die den Kategorienfehler
    behielt.

    ⚠ **Abziehen hier, sperren bei `waerme_abgeleitet_kwh` — kein Widerspruch.**
    Dort enthält der **Zähler** einen aus dem Nenner gerechneten Anteil; ihn
    abzuziehen ergäbe *falsch statt unbekannt*. Hier enthält der **Nenner** einen
    separat bekannten Anteil einer anderen Funktion; ihn abzuziehen stellt die
    Abgrenzung überhaupt erst her. Beide Male gewinnt dieselbe Regel: Q und E
    müssen dasselbe meinen.
    """
    # dietmars Juli-Größenordnung, um 200 kWh Kühlbetrieb ergänzt.
    mit_kuehlung = arbeitszahl(2000.0, 700.0, strom_funktionsfremd_kwh=200.0)
    ohne_kuehlung = arbeitszahl(2000.0, 500.0)

    assert mit_kuehlung.wert == ohne_kuehlung.wert == 4.0, (
        "derselbe Heizbetrieb, dieselbe Arbeitszahl — Kühlen darf sie nicht drücken"
    )
    # Ohne den Abzug wären es 2,86 gewesen: eine kühlende Anlage sähe aus wie
    # eine schlechte Heizung.
    assert round(2000.0 / 700.0, 2) == 2.86


def test_ii7b_reiner_kuehlbetrieb_sagt_was_er_ist():
    """**ERFÜLLT (W-14).** Ein Sommermonat ohne Heizbetrieb ist kein Datenausfall.

    ⚠ **Der Grund musste ein eigener sein.** Zieht man den ganzen Strom ab,
    bliebe ein Nenner von 0 — und der bestehende Zweig hätte „kein
    Stromverbrauch erfasst" gemeldet. Das wäre die falsche Auskunft: Der Zähler
    lief, nur nicht fürs Heizen. Am **Tag** wiegt das am schwersten, dort kann
    ein Sommertag fast reiner Kühlbetrieb sein.
    """
    nur_kuehlen = arbeitszahl(0.0, 158.4, strom_funktionsfremd_kwh=158.4)

    assert nur_kuehlen.wert is None
    assert nur_kuehlen.grund == "nur Kühlbetrieb in diesem Zeitraum"
    assert len(nur_kuehlen.grund) <= 40
    # Gegenprobe: OHNE Verbrauch gilt weiterhin der andere Satz.
    assert arbeitszahl(2000.0, 0.0).grund == "kein Stromverbrauch erfasst"


def test_ii7c_die_restmenge_bleibt_im_nenner():
    """**ERFÜLLT (W-14).** Abgezogen wird nur, was als andere **Funktion**
    gemessen ist — nicht die Restmenge.

    `modus_nicht_aufgeteilt_kwh` (Standby, Lüften, Entfeuchten, Unbestimmt) ist
    keine gemessene Funktion, sondern das, was übrig bleibt. Der
    Bereitschaftsverbrauch einer Heizung gehört legitim in ihre Arbeitszahl —
    ihn herauszurechnen würde die Anlage besser aussehen lassen, als sie ist.

    ⚠ **Damit ist auch die Grenze dieses Baus benannt:** Lüften und Entfeuchten
    sind zwar über eigene Betriebsart-Zähler **erfassbar**, werden aber in keine
    Fakten-Größe gefaltet (`ImdTypBeitrag` führt nur Heizen und Kühlen) und
    landen stumm in der Restmenge. Das ist die unfertige Ausführung von SOLL
    **E4**, nicht Teil von W-14.
    """
    wp = _wp(strom_kwh=1000.0, waerme_kwh=3000.0,
             modus_strom_bezug_kwh=1000.0,
             modus_strom_heizen_kwh=700.0, modus_strom_kuehlen_kwh=200.0)

    assert wp.modus_nicht_aufgeteilt_kwh == 100.0
    # Nenner = 1000 − 200 (Kühlen), NICHT 1000 − 200 − 100 (Restmenge).
    assert arbeitszahl(
        wp.waerme_kwh, wp.strom_kwh,
        strom_funktionsfremd_kwh=wp.modus_strom_kuehlen_kwh,
    ).wert == 3000.0 / 800.0
