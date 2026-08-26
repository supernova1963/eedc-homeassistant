"""SOLL Wärme/Klima — **Achse I: Erfassungswege.** Welche Größe darf welche entwerten?

Maschinelle Fassung von `soll-waerme-klima.md` §3.2 (**K3**) und §3.2a (**R1**).
Schwesterdatei zu `test_komponenten_beitraege.py`: Dort liegt die Probe für den
**korrekten** Fall (Kennzeichen an, beide feinen Zähler vorhanden ⇒ Gesamtzähler
verworfen, sonst Doppelzählung). **Sie bleibt unverändert und hat recht** — die
Abgrenzung zwischen ihr und den Proben hier ist der eigentliche Testgegenstand
und nur im Paar lesbar.

## Zwei Sorten von Proben, bewusst getrennt

Dieselbe Bauform wie `test_konzept_wirtschaftlichkeit_konformitaet.py`:

* **ERFÜLLT** — die Erwartung des SOLL ist gebaut. Harte Assertion.
* **OFFEN** — der Bauschritt steht aus. Die Probe hält den **heutigen** Zustand
  fest und nennt im Docstring den Soll-Zustand samt Regel. Wird gebaut,
  **schlägt sie fehl** — genau dort, wo die Umstellung stattfindet. Sie ist dann
  auf die SOLL-Erwartung umzustellen und ihr Eintrag aus ``REGELN_OFFEN`` zu
  entfernen.

⚠ **Eine fehlschlagende OFFEN-Probe ist kein Alarm, sondern eine Quittung.**
Wer sie „repariert", ohne den Eintrag zu entfernen, hat den Schritt halb gefahren.

Kein ``xfail``: Das Muster gibt es im Baum nicht, die klassifizierte Offen-Liste
schon.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.field_definitions import (
    get_alle_felder_fuer_investition,
    get_felder_fuer_investition,
)
from backend.services.snapshot.komponenten_beitraege import investition_beitraege

#: SOLL-Regeln, die noch **nicht** gebaut sind. Wird eine gebaut, fliegt ihr
#: Eintrag hier raus **und** die zugehörige OFFEN-Probe wird umgestellt.
REGELN_OFFEN: dict[str, str] = {}
#: ⭐ **Leer seit dem 26.08.2026 — Achse I ist gebaut.** Die Liste bleibt stehen,
#: weil sie der Ort ist, an dem eine künftige Regel dieser Achse notiert wird,
#: und weil die Proben unten sie namentlich abfragen: `assert "…" not in
#: REGELN_OFFEN` ist die Quittung dafür, dass eine ERFÜLLT-Probe wirklich zu
#: einem gebauten Schritt gehört und nicht bloß grün gerechnet wurde.


def _inv(inv_id=7, parameter=None):
    return SimpleNamespace(
        id=inv_id, typ="waermepumpe",
        parameter=parameter or {}, parent_investition_id=None,
    )


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _felder(beitraege) -> set[str]:
    return {b.feld for b in beitraege}


def _pflegbar(parameter: dict, belegt: set[str] | None = None) -> set[str]:
    """Die Feldnamen, die der **Monatsabschluss** zur Eingabe anbietet.

    ⚠ **Nicht dasselbe wie {@link _zuordenbar}, und der Unterschied ist der
    Testgegenstand.** Bis zum 26.08.2026 hieß dieser Helfer `_zuordenbar` und
    rief trotzdem `get_felder_fuer_investition` — den Monatsabschluss-Weg. Die
    **Zuordnungs-Fläche** liest eine andere Funktion, und genau dort saß Befund
    **W-12**: Sie bot einer Split-Klimaanlage `warmwasser_kwh` und
    `strom_warmwasser_kwh` an, während die Probe I-6 daneben grün meldete, es
    gebe sie dort nicht. *Ein Prüfer, der aufs falsche Objekt zeigt, belegt eine
    Aussage über eine Fläche, die er nie gesehen hat.*
    """
    return {
        f["feld"] for f in get_felder_fuer_investition(
            "waermepumpe", parameter, belegte_felder=belegt,
        )
    }


def _zuordenbar(parameter: dict, quellen: dict | None = None) -> dict[str, bool]:
    """Die **Zuordnungs-Fläche**: Feldname → steht es unter „Weitere Größen"?

    Registry **plus** der Filter, den die Route darüberlegt — beides zusammen
    ist, was der Anwender sieht.

    ⚠ **Die Registry allein zu messen wäre die halbe Wahrheit.** Sie *markiert*
    nur; entfernt wird in `ohne_nicht_zuordenbare`, und zwar mit der Ausnahme,
    die N-304 verlangt: Ein Feld MIT Quelle bleibt stehen, damit eine bestehende
    Zuordnung löschbar ist. Wer nur die Registry prüft, hält eine Fläche für
    aufgeräumt, die es nicht ist — und umgekehrt.
    """
    from backend.api.routes.datenquellen import ohne_nicht_zuordenbare

    roh = [
        {**f, "match_key": ("inv_energy", "7", f["feld"])}
        for f in get_alle_felder_fuer_investition("waermepumpe", parameter)
    ]
    return {
        f["feld"]: bool(f.get("erweitert"))
        for f in ohne_nicht_zuordenbare(roh, quellen or {})
    }


# ══ I-1 · ERFÜLLT — K3: nur der Gesamtzähler ist zugeordnet ════════════════

def test_i1_kennzeichen_an_nur_gesamtzaehler():
    """**ERFÜLLT (K3/W-1, gebaut 2026-08-26).**

    SOLL §6/K3: *„Ein Erfassungsweg, den es nicht gibt, entwertet keinen, den es
    gibt."* Der Gesamtzähler bleibt die Bilanzgröße, weil die feinen Zähler
    fehlen — das Kennzeichen allein entwertet ihn nicht mehr.

    Vorher: **leer**. Der Block *Wärme/Klima* verschwand vollständig; genau das
    hat OB73-gif gemeldet (#263) und selbst aufgelöst, indem er das Kennzeichen
    wieder ausschaltete.
    """
    assert "K3/W-1" not in REGELN_OFFEN
    inv = _inv(parameter={"getrennte_strommessung": True})
    sm = {"felder": {"stromverbrauch_kwh": _sensor("sensor.wp_gesamt")}}

    assert _felder(investition_beitraege(inv, sm)) == {"stromverbrauch_kwh"}


# ══ I-2 · ERFÜLLT — K3: die Aufteilung ist erst halb gepflegt ══════════════

def test_i2_kennzeichen_an_gesamt_plus_nur_heizen():
    """**ERFÜLLT (K3/W-1b, gebaut 2026-08-26).**

    SOLL §3.2/K1: *„Die Gesamtmenge ist immer die Wahrheit. Jede Aufteilung steht
    daneben, nie an ihrer Stelle."* Die Aufteilung ist unvollständig, also trägt
    der Gesamtzähler die Bilanz. ``strom_heizen_kwh`` geht dadurch nicht
    verloren — es steht als eigener Ausgabe-Key im Detail-Pfad
    (`aggregator.get_tagesdetail_kwh`), also **daneben** statt an der Stelle der
    Gesamtmenge.

    Vorher: **nur Heizen**. Der Warmwasser-Anteil fehlte still — in der WP-Zahl,
    in den Kosten, im Anteil am Haushalt und in jeder daraus gerechneten
    Kennzahl.

    ⭐ **Das war der teurere der beiden Fälle.** I-1 ließ den Block
    verschwinden — das fällt auf und wurde gemeldet. Hier erschien eine **zu
    niedrige Zahl, die wie eine richtige aussah**, und getroffen war der
    normale Einrichtungsweg: erst Heizen zuordnen, dann Warmwasser.
    """
    assert "K3/W-1b" not in REGELN_OFFEN
    inv = _inv(parameter={"getrennte_strommessung": True})
    sm = {"felder": {
        "stromverbrauch_kwh": _sensor("sensor.wp_gesamt"),
        "strom_heizen_kwh": _sensor("sensor.wp_heizen"),
    }}

    assert _felder(investition_beitraege(inv, sm)) == {"stromverbrauch_kwh"}


# ══ I-2b · ERFÜLLT — K3 in der Gegenrichtung: Kennzeichen AUS ══════════════

def test_i2b_kennzeichen_aus_feiner_zaehler_traegt():
    """**ERFÜLLT (K3, dritte Stufe — gebaut 2026-08-26).**

    K3 gilt ausdrücklich **in beide Richtungen**: *„Wer feine Zähler hat, bekommt
    die feine Aufteilung; wer sie nicht hat, behält die grobe Wahrheit."* Also
    auch: Kennzeichen **aus**, kein Gesamtzähler, aber ein feiner Zähler
    zugeordnet ⇒ er trägt.

    Vorher trug er **nicht** — dieselbe Klasse wie W-1, nur mit umgekehrtem
    Kennzeichen-Zustand. Sie hatte keinen Melder und stand in keiner Fallliste;
    sichtbar wurde sie erst, als die Regel „der Zähler entscheidet" ausformuliert
    war (Entscheid Gernot 26.08.: Vollständigkeit vor Auftragsrand).

    ⚠ **Eine unvollständige Aufteilung ist die einzige Messung, die es hier
    gibt.** Sie zu verwerfen hieße, den Block verschwinden zu lassen — genau der
    Befund, der mit W-1 repariert wurde.
    """
    inv = _inv(parameter={"getrennte_strommessung": False})
    sm = {"felder": {"strom_heizen_kwh": _sensor("sensor.wp_heizen")}}

    assert _felder(investition_beitraege(inv, sm)) == {"strom_heizen_kwh"}


# ══ I-2c · ERFÜLLT — die Klimaanlage fällt nicht auf eine halbe Achse ══════

def test_i2c_luft_luft_kann_nie_vollstaendig_aufgeteilt_sein():
    """**ERFÜLLT (K3, Registry statt Bauart).**

    Eine Split-Klimaanlage hat **keinen Warmwasserkreis** (N-304/B5:
    ``strom_warmwasser_kwh`` trägt ``!luft_luft``). Ihre feine Aufteilung kann
    deshalb nie vollständig sein — folglich greift Stufe 1 dort nie und der
    Gesamtzähler trägt.

    ⭐ **Und das ist keine Ausnahme, sondern der Beleg, dass die Regel am
    richtigen Objekt fragt.** ``strom_heizen_kwh`` ist an einem Luft-Luft-Gerät
    kein Summand einer zweiteiligen Achse, sondern ein Ausschnitt neben Kühlen,
    Lüften und Standby. Ihn als Bilanzgröße zu buchen wäre W-1b in neuer Form.

    ⚠ Genau diese Konstellation hatte OB73-gif: Midea Portasplit, Kennzeichen
    gesetzt, Gesamtzähler vorhanden.
    """
    inv = _inv(parameter={"wp_art": "luft_luft", "getrennte_strommessung": True})
    sm = {"felder": {
        "stromverbrauch_kwh": _sensor("sensor.klima_gesamt"),
        "strom_heizen_kwh": _sensor("sensor.klima_heizen"),
    }}

    assert _felder(investition_beitraege(inv, sm)) == {"stromverbrauch_kwh"}


# ══ I-3 · ERFÜLLT — die Abgrenzung, die heute schon richtig ist ═════════════

def test_i3_kennzeichen_an_beide_feinen_zaehler_da():
    """**ERFÜLLT.** Sind beide feinen Zähler zugeordnet, wird der Gesamtzähler
    verworfen — sonst zählte derselbe Strom doppelt.

    ⚠ **Diese Probe ist der Grund, warum I-1 und I-2 keine Rücknahme dieser Regel
    verlangen dürfen.** Sie hält denselben Schalter in seinem **berechtigten**
    Fall fest. Der Unterschied ist nicht das Kennzeichen, sondern ob die feinen
    Zähler **existieren**.

    ⭐ **Und daraus folgt die Fundstelle:** `keys.py::_categorize_counter` sieht
    immer nur **ein** Feld und kann die Feldmenge nicht kennen — K3 ist dort
    nicht formulierbar. Sie gehört auf diese Ebene, die alle Felder sieht.
    """
    inv = _inv(parameter={"getrennte_strommessung": True})
    sm = {"felder": {
        "stromverbrauch_kwh": _sensor("sensor.wp_gesamt"),
        "strom_heizen_kwh": _sensor("sensor.wp_heizen"),
        "strom_warmwasser_kwh": _sensor("sensor.wp_ww"),
    }}

    assert _felder(investition_beitraege(inv, sm)) == {
        "strom_heizen_kwh", "strom_warmwasser_kwh",
    }


def test_i3b_kennzeichen_aus_gesamtzaehler_traegt():
    """**ERFÜLLT.** Ohne Kennzeichen trägt der Gesamtzähler — der Normalfall.

    Gegenprobe zu I-1: Sie zeigt, dass dort **allein das Kennzeichen** den
    Unterschied macht, nicht etwa eine fehlende Zuordnung.
    """
    inv = _inv(parameter={"getrennte_strommessung": False})
    sm = {"felder": {"stromverbrauch_kwh": _sensor("sensor.wp_gesamt")}}

    assert _felder(investition_beitraege(inv, sm)) == {"stromverbrauch_kwh"}


# ══ I-4 · OFFEN — R1: die Kühl-Achse hängt an der Geräteklasse ══════════════

def test_i4_kuehl_achse_an_jeder_bauart_zuordenbar():
    """**ERFÜLLT (R1/W-2, gebaut 2026-08-26).**

    SOLL §3.2a/R1: *„Angeboten wird jede Größe, die das Gerät liefern kann — und
    was es liefern kann, sagt der zugeordnete Zähler, nicht seine Bauart."*

    **Melder MartyBr** (T89667 #200, 25.08.): *„Ich habe getrennte Zähler für
    Heizung, Warmwassererwärmung … und seit dem Sommer auch für den
    Kühlbetrieb."* **pipp086** (#199) fragt nach derselben Größe. Vorher trugen
    alle acht Betriebsart-Felder `bedingung: luft_luft` **hart** und wurden für
    jede andere Bauart vollständig entfernt — sein Kühlzähler hatte nirgends
    einen Platz.

    ⭐ **Der berechtigte Kern der alten Begründung ist NICHT gestrichen, sondern
    eingelöst:** Heizen/Warmwasser sind **Summanden**, Betriebsarten
    **Teilmengen**; acht unbeschriftete Felder daneben haben schon einmal einen
    Tester zum Addieren verleitet (#89667/62). Das spricht gegen acht Felder in
    der **ersten Reihe** — nicht gegen die Kühl-Achse dort, wo ein Zähler sie
    belegt. Beides zusammen ist die weiche Bedingung: zuordenbar, aber unter
    „Weitere Größen erfassen".
    """
    assert "R1/W-2" not in REGELN_OFFEN
    flaeche = _zuordenbar({"wp_art": "sole_wasser", "getrennte_strommessung": True})

    assert flaeche["betriebsart_strom_kuehlen_kwh"] is True, (
        "zuordenbar, aber als erweiterte Größe"
    )
    # Alle acht, nicht nur die Kühl-Achse: die Regel fragt nach dem Zähler,
    # nicht nach einer neuen, kürzeren Liste erlaubter Betriebsarten.
    betriebsart = {f for f in flaeche if f.startswith("betriebsart_")}
    assert len(betriebsart) == 8
    assert all(flaeche[f] for f in betriebsart)


def test_i4c_erweitertes_feld_erreicht_den_monatsabschluss_nur_wenn_belegt():
    """**ERFÜLLT (R1/W-2).** Der Zähler entscheidet — und zwar wörtlich.

    Der Monatsabschluss ist eine **Eingabe**-Fläche: ein leeres Feld dort ist
    eine Aufforderung. Ohne Beleg bleibt die Kühl-Achse deshalb weg; sobald ein
    Wert oder eine Zuordnung existiert, steht sie da.

    ⚠ **Das ist die Gegenprobe zu I-4** und der Grund, warum die beiden Flächen
    verschiedene Helfer haben: dieselbe Bauart, dieselbe Regel, zwei richtige
    und verschiedene Antworten.
    """
    p = {"wp_art": "sole_wasser", "getrennte_strommessung": True}

    assert "betriebsart_strom_kuehlen_kwh" not in _pflegbar(p)
    assert "betriebsart_strom_kuehlen_kwh" in _pflegbar(
        p, {"betriebsart_strom_kuehlen_kwh"},
    )


def test_i4d_die_kuehlleistung_hat_ein_feld():
    """**ERFÜLLT (W-13, gebaut 2026-08-26).**

    MartyBr nennt in #200 **beide** Größen: *„sowohl die Live-Werte (Power in W)
    als auch die kumulierten Werte (Energy in kWh)."* `leistung_heizen_w` und
    `leistung_warmwasser_w` gab es an jeder Wärmepumpe — für den Kühlbetrieb
    **an keiner**.

    ⛔ **Ohne dieses Feld hätte R1 seinen Fall nur zur Hälfte erreicht.** Der
    Befund stand in keiner Fassung des Auftrags; gefunden wurde er beim
    vollständigen Lesen seines Beitrags ([[feedback_webfetch_forum_bilder]] —
    dieselbe Regel, ein Kanal weiter).
    """
    from backend.core.field_definitions import get_live_felder_fuer_investition

    for art in ("luft_wasser", "sole_wasser", "luft_luft", "brauchwasser"):
        keys = {f["key"] for f in get_live_felder_fuer_investition(
            "waermepumpe", {"wp_art": art},
        )}
        assert "leistung_kuehlen_w" in keys, art
        # Symmetrie zu den beiden Nachbarn — sie tragen ebenfalls keine Bedingung.
        assert {"leistung_heizen_w", "leistung_warmwasser_w"} <= keys, art


def test_i4b_luft_luft_hat_die_betriebsart_achsen():
    """**ERFÜLLT.** Am Klimagerät sind die Betriebsart-Achsen zuordenbar.

    Gegenprobe zu I-4: Der Unterschied ist heute **allein die Bauart**, nicht die
    Frage, ob ein Zähler vorliegt.
    """
    flaeche = _zuordenbar({"wp_art": "luft_luft"})
    betriebsart = {f for f in flaeche if f.startswith("betriebsart_strom_")}

    assert betriebsart == {
        "betriebsart_strom_heizen_kwh",
        "betriebsart_strom_kuehlen_kwh",
        "betriebsart_strom_lueften_kwh",
        "betriebsart_strom_entfeuchten_kwh",
    }
    # ⭐ **Der Unterschied ist jetzt die Reihe, nicht das Vorhandensein:** am
    # Klimagerät stehen sie vorn (nicht erweitert), an jeder anderen Bauart
    # hinter „Weitere Größen erfassen". Genau das war der Sinn der weichen
    # Bedingung — kurze Fläche, kein ausgeschlossener Fall.
    assert not any(flaeche[f] for f in betriebsart)


# ══ I-5 · OFFEN — R1: ein Gerät mit ausschließlich Warmwasser-Achse ═════════

def test_i5_brauchwasser_waermepumpe_traegt_nur_die_warmwasser_achse():
    """**ERFÜLLT (R1/Brauchwasser, gebaut 2026-08-26).**

    SOLL §2.1: Eine **Brauchwasser-WP** heizt nicht und kühlt nicht — sie macht
    ausschließlich Warmwasser. Vorher gab es für sie keine Bauart; eine
    unbekannte `wp_art` fiel in den Nicht-Luft-Luft-Zweig und bekam **Heizen und
    Warmwasser** angeboten — eine Heiz-Achse, die das Gerät nicht hat.

    ⛔ **Für diesen Fall gibt es keinen einzigen bekannten Anwender, und er
    steht trotzdem hier** (Entscheid Gernot, 26.08.). Ein Modell, das einen
    realen Gerätetyp nicht ausdrücken kann, ist später nicht nachrüstbar: Die
    bis dahin gespeicherten Daten wären falsch, nicht bloß eine Ansicht
    unvollständig.

    ⚠ **Die Heiz-Achse ist herabgestuft, nicht entfernt** — weich, nicht hart.
    `wp_art` ist eine Anwender-Angabe; ein Gerät, das doch beides kann, behält
    seinen Zähler. Genau darin unterscheidet sich R1 von der Schubladen-Logik,
    die es ablöst: Die Bauart **schlägt vor**, der Zähler **entscheidet**.
    """
    assert "R1/Brauchwasser" not in REGELN_OFFEN
    p = {"wp_art": "brauchwasser", "getrennte_strommessung": True}

    # Der Monatsabschluss fragt nur nach dem, was das Gerät tut.
    assert _pflegbar(p) == {"strom_warmwasser_kwh", "warmwasser_kwh"}

    # Zuordenbar bleibt beides — die Heiz-Achse als erweiterte Größe.
    flaeche = _zuordenbar(p)
    assert flaeche["strom_warmwasser_kwh"] is False
    assert flaeche["warmwasser_kwh"] is False
    assert flaeche["strom_heizen_kwh"] is True
    assert flaeche["heizenergie_kwh"] is True


def test_i5b_heiz_achse_kehrt_mit_ihrem_zaehler_zurueck():
    """**ERFÜLLT (R1/Brauchwasser).** Gegenprobe zu I-5 — die weiche Grenze hält
    in **beide** Richtungen.

    Wer an seiner Brauchwasser-WP doch einen Heizzähler hinterlegt hat, bekommt
    die Achse im Monatsabschluss zurück. Ohne diese Probe bliebe offen, ob
    „weich" in der Praxis nicht doch „hart" ist — ein Feld, das man zuordnen,
    aber nie pflegen kann, wäre die P-6-Falle in neuer Form.
    """
    p = {"wp_art": "brauchwasser", "getrennte_strommessung": True}

    assert "strom_heizen_kwh" in _pflegbar(p, {"strom_heizen_kwh"})


def test_i5c_die_bauart_bleibt_eine_geraeteklasse_keine_pflicht():
    """**ERFÜLLT.** Eine klassische Wärmepumpe ist von `brauchwasser` unberührt.

    ⚠ **Die Gegenprobe zum Bedingungs-Schlüssel selbst.** Ein neuer Schlüssel in
    `_bedingungs_werte` wirkt auf **jedes** Feld, das ihn nennt — und
    `bedingung_erfuellt` ist fail-open. Ein Tippfehler (`brauchwaser`) fiele
    stillschweigend durch und ließe die Heiz-Achse überall weich werden. Hier
    steht der Beleg, dass er es nicht tut.
    """
    p = {"wp_art": "luft_wasser", "getrennte_strommessung": True}
    flaeche = _zuordenbar(p)

    assert flaeche["strom_heizen_kwh"] is False
    assert flaeche["heizenergie_kwh"] is False
    assert {"strom_heizen_kwh", "heizenergie_kwh"} <= _pflegbar(p)


# ══ I-6 · ERFÜLLT — kein Warmwasser am Luft-Luft-Gerät ══════════════════════

def test_i6_luft_luft_fordert_kein_warmwasser():
    """**ERFÜLLT.** Ein Luft-Luft-Gerät hat keinen Warmwasserkreis — und bekommt
    die Achse auch nicht angeboten.

    SOLL §2.1, belegt durch OB73-gif (#263, 25.08.): Der Daten-Check verlangte
    von seiner Split-Klimaanlage ``strom_warmwasser_kwh``. Die Zuordnungs-Fläche
    hat es nie angeboten — der Checker kannte die Ausnahme nur an zwei von drei
    Stellen (gebaut mit v4.0.28, `c82d8138`).

    Gegenprobe zu I-5: **Nicht jede Bauart-Abhängigkeit ist falsch.** Falsch ist,
    sie aus einer *Liste von Bauarten* abzuleiten statt aus dem, was das Gerät
    belegbar liefert. Das Ergebnis ist hier zufällig dasselbe — unter R1, weil
    kein Warmwasser-Zähler zuordenbar ist.
    """
    p = {"wp_art": "luft_luft", "getrennte_strommessung": True}

    assert "strom_warmwasser_kwh" not in _pflegbar(p)
    assert "strom_heizen_kwh" in _pflegbar(p)


def test_i6b_auch_die_zuordnungs_flaeche_kennt_die_harte_grenze():
    """**ERFÜLLT (W-12, gebaut 2026-08-26).** Dieselbe Anlage, zweite Fläche.

    ⛔ **Bis zum 26.08.2026 sagten die beiden Flächen Gegenteiliges.** Der Filter
    in `get_alle_felder_fuer_investition` war ein **exakter String-Vergleich**
    (`f.get("bedingung") != "luft_luft"`) und kannte weder die Negation
    `"!luft_luft"` (`warmwasser_kwh`) noch die Listenform
    `["getrennte_strommessung", "!luft_luft"]` (`strom_warmwasser_kwh`). Beide
    liefen daran vorbei — *Einstellungen → Datenquellen* bot einer
    Split-Klimaanlage also genau die zwei Warmwasser-Felder an, deren Fehlen der
    Daten-Checker bei **OB73-gif** zu Unrecht angemahnt hatte (#263). Repariert
    wurde damals der Checker (v4.0.28, `c82d8138`), nicht die Fläche.

    ⭐ **Dritte Runde der #236-Folgewellen-Klasse:** eine Regel auf einer Schicht
    reicht nicht, solange parallele Pfade dieselbe Frage eigenständig
    beantworten. Der Auswerter (`bedingungs_urteil`) ist jetzt der eine.

    ⚠ **Und die Probe I-6 daneben hat es nicht gefangen**, obwohl sie exakt diese
    Aussage trägt: Ihr Helfer hieß `_zuordenbar` und rief den
    Monatsabschluss-Weg. *Ein Prüfer, der aufs falsche Objekt zeigt, belegt eine
    Aussage über eine Fläche, die er nie gesehen hat.*
    """
    flaeche = _zuordenbar({"wp_art": "luft_luft", "getrennte_strommessung": True})

    assert "warmwasser_kwh" not in flaeche
    assert "strom_warmwasser_kwh" not in flaeche

    # ⭐ **Und die Gegenrichtung, die der erste Fix am 26.08. gebrochen hätte:**
    # Ein bereits ZUGEORDNETER Warmwasser-Sensor bleibt sichtbar — sonst wäre
    # die Zuordnung unsichtbar und damit unlöschbar. Der Fall ist real:
    # azywietz-web führt zwei Klimaanlagen als `luft_wasser` (#383); stellt er
    # die Bauart um, braucht sein Sensor einen Weg heraus.
    # `test_klima_ohne_warmwasser_n304.py` hält denselben Vertrag und hat den
    # zu groben Fix gefangen ([[feedback_keine_folge_aenderung_zurueckdrehen]]).
    mit_zuordnung = _zuordenbar(
        {"wp_art": "luft_luft", "getrennte_strommessung": True},
        {"inv_energy_7_warmwasser_kwh": {"quelle": "ha_app"}},
    )
    assert "warmwasser_kwh" in mit_zuordnung
    # Gegenprobe: die Heiz-Achse gibt es an einer Klimaanlage sehr wohl — die
    # Trennlinie ist der Warmwasserkreis, nicht die Bauart als solche (N-304).
    assert flaeche["strom_heizen_kwh"] is False
    assert flaeche["heizenergie_kwh"] is False
