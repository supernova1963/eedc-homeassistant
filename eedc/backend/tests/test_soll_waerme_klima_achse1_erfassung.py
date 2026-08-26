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

from backend.core.field_definitions import get_felder_fuer_investition
from backend.services.snapshot.komponenten_beitraege import investition_beitraege

#: SOLL-Regeln, die noch **nicht** gebaut sind. Wird eine gebaut, fliegt ihr
#: Eintrag hier raus **und** die zugehörige OFFEN-Probe wird umgestellt.
REGELN_OFFEN: dict[str, str] = {
    "K3/W-1": (
        "Ein gesetztes Kennzeichen entwertet den vorhandenen Gesamtzähler: "
        "`getrennte_strommessung=True` + nur `stromverbrauch_kwh` zugeordnet "
        "⇒ die Investition trägt GAR NICHTS bei. Melder OB73-gif (#263)."
    ),
    "K3/W-1b": (
        "Derselbe Schalter verliert auch die HÄLFTE: Gesamt + nur "
        "`strom_heizen_kwh` ⇒ der Warmwasser-Anteil fehlt still. Schwerer als "
        "W-1, weil die Zahl richtig aussieht. Kein Melder — beim Ausführen "
        "der Fundstelle gefunden (26.08.)."
    ),
    "R1/W-2": (
        "Die Betriebsart-Achsen hängen an der Geräteklasse (`bedingung: "
        "luft_luft`) statt am zugeordneten Zähler. Eine kühlfähige "
        "Luft-Wasser- oder Sole-Wasser-WP kann ihren Kühlzähler nirgends "
        "zuordnen. Melder MartyBr, pipp086 (T89667 #199/#200)."
    ),
    "R1/Brauchwasser": (
        "Ein Gerät mit ausschließlich Warmwasser-Achse (Brauchwasser-WP) hat "
        "keine Bauart-Zeile. Kein bekannter Anwender — steht trotzdem hier, "
        "weil das MODELL es tragen muss (SOLL §7, Korrektur 26.08.)."
    ),
}


def _inv(inv_id=7, parameter=None):
    return SimpleNamespace(
        id=inv_id, typ="waermepumpe",
        parameter=parameter or {}, parent_investition_id=None,
    )


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _felder(beitraege) -> set[str]:
    return {b.feld for b in beitraege}


def _zuordenbar(parameter: dict) -> set[str]:
    """Die Feldnamen, die die Zuordnungs-Fläche für diese Investition anbietet."""
    return {f["feld"] for f in get_felder_fuer_investition("waermepumpe", parameter)}


# ══ I-1 · OFFEN — K3: nur der Gesamtzähler ist zugeordnet ═══════════════════

def test_i1_kennzeichen_an_nur_gesamtzaehler():
    """**OFFEN (K3/W-1).**

    SOLL §6/K3: *„Ein Erfassungsweg, den es nicht gibt, entwertet keinen, den es
    gibt."* Erwartung nach dem Bau: ``{"stromverbrauch_kwh"}`` — der
    Gesamtzähler bleibt die Bilanzgröße, weil die feinen Zähler fehlen.

    Heute: **leer**. Der Block *Wärme/Klima* verschwindet vollständig; genau das
    hat OB73-gif gemeldet und selbst aufgelöst, indem er das Kennzeichen wieder
    ausschaltete.
    """
    assert "K3/W-1" in REGELN_OFFEN
    inv = _inv(parameter={"getrennte_strommessung": True})
    sm = {"felder": {"stromverbrauch_kwh": _sensor("sensor.wp_gesamt")}}

    assert _felder(investition_beitraege(inv, sm)) == set()


# ══ I-2 · OFFEN — K3: die Aufteilung ist erst halb gepflegt ═════════════════

def test_i2_kennzeichen_an_gesamt_plus_nur_heizen():
    """**OFFEN (K3/W-1b).**

    SOLL §3.2/K1: *„Die Gesamtmenge ist immer die Wahrheit. Jede Aufteilung steht
    daneben, nie an ihrer Stelle."* Erwartung nach dem Bau: Der Gesamtzähler
    trägt die Bilanz, ``strom_heizen_kwh`` ist die Aufteilung daneben.

    Heute: **nur Heizen**. Der Warmwasser-Anteil fehlt still — in der WP-Zahl, in
    den Kosten, im Anteil am Haushalt und in jeder daraus gerechneten Kennzahl.

    ⭐ **Das ist der teurere der beiden Fälle.** I-1 lässt den Block
    verschwinden — das fällt auf und wurde gemeldet. Hier erscheint eine **zu
    niedrige Zahl, die wie eine richtige aussieht**, und getroffen ist der
    normale Einrichtungsweg: erst Heizen zuordnen, dann Warmwasser.
    """
    assert "K3/W-1b" in REGELN_OFFEN
    inv = _inv(parameter={"getrennte_strommessung": True})
    sm = {"felder": {
        "stromverbrauch_kwh": _sensor("sensor.wp_gesamt"),
        "strom_heizen_kwh": _sensor("sensor.wp_heizen"),
    }}

    assert _felder(investition_beitraege(inv, sm)) == {"strom_heizen_kwh"}


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

def test_i4_kuehl_achse_nur_an_luft_luft():
    """**OFFEN (R1/W-2).**

    SOLL §3.2a/R1: *„Angeboten wird jede Größe, die das Gerät liefern kann — und
    was es liefern kann, sagt der zugeordnete Zähler, nicht seine Bauart."*
    Erwartung nach dem Bau: Auch eine Sole-Wasser-WP kann
    ``betriebsart_strom_kuehlen_kwh`` zugeordnet bekommen.

    Heute: Die acht Betriebsart-Felder tragen ``bedingung: luft_luft`` und werden
    für jede andere Bauart vollständig aus der Zuordnungs-Fläche entfernt.
    MartyBr hat einen getrennten Kühlzähler an einer Sole-Wasser-WP und kann ihn
    nirgends hinterlegen; pipp086 fragt nach derselben Größe.

    ⭐ **Der berechtigte Kern der alten Begründung bleibt und ist keine Ausrede:**
    Heizen/Warmwasser sind **Summanden**, Betriebsarten **Teilmengen** — beide
    Familien unbeschriftet nebeneinander hat schon einmal einen Tester zum
    Addieren verleitet. Das spricht gegen *acht* Felder an jeder WP, **nicht**
    gegen die Kühl-Achse dort, wo ein Zähler sie belegt.
    """
    assert "R1/W-2" in REGELN_OFFEN
    betriebsart = {
        f for f in _zuordenbar({"wp_art": "sole_wasser", "getrennte_strommessung": True})
        if f.startswith("betriebsart_")
    }

    assert betriebsart == set()


def test_i4b_luft_luft_hat_die_betriebsart_achsen():
    """**ERFÜLLT.** Am Klimagerät sind die Betriebsart-Achsen zuordenbar.

    Gegenprobe zu I-4: Der Unterschied ist heute **allein die Bauart**, nicht die
    Frage, ob ein Zähler vorliegt.
    """
    betriebsart = {
        f for f in _zuordenbar({"wp_art": "luft_luft"})
        if f.startswith("betriebsart_strom_")
    }

    assert betriebsart == {
        "betriebsart_strom_heizen_kwh",
        "betriebsart_strom_kuehlen_kwh",
        "betriebsart_strom_lueften_kwh",
        "betriebsart_strom_entfeuchten_kwh",
    }


# ══ I-5 · OFFEN — R1: ein Gerät mit ausschließlich Warmwasser-Achse ═════════

def test_i5_brauchwasser_waermepumpe_hat_keine_bauart():
    """**OFFEN (R1/Brauchwasser).**

    SOLL §2.1: Eine **Brauchwasser-WP** heizt nicht und kühlt nicht — sie macht
    ausschließlich Warmwasser. Erwartung nach dem Bau (R1): Das Gerät trägt genau
    die Achsen, für die Zähler zugeordnet sind — hier **nur** Warmwasser.

    Heute: Es gibt für sie keine Bauart. Setzt man eine unbekannte ``wp_art``,
    fällt sie in den Nicht-Luft-Luft-Zweig und bekommt **Heizen und Warmwasser**
    angeboten — eine Heiz-Achse, die das Gerät nicht hat.

    ⛔ **Für diesen Fall gibt es keinen einzigen bekannten Anwender, und er steht
    trotzdem hier** (Entscheid Gernot, 26.08.). Ein Modell, das einen realen
    Gerätetyp nicht ausdrücken kann, ist später nicht nachrüstbar: Die bis dahin
    gespeicherten Daten wären falsch, nicht bloß eine Ansicht unvollständig.
    """
    assert "R1/Brauchwasser" in REGELN_OFFEN
    felder = _zuordenbar({"wp_art": "brauchwasser", "getrennte_strommessung": True})

    # Heute wird eine Heiz-Achse angeboten, die es an diesem Gerät nicht gibt.
    assert "strom_heizen_kwh" in felder
    assert "strom_warmwasser_kwh" in felder


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
    felder = _zuordenbar({"wp_art": "luft_luft", "getrennte_strommessung": True})

    assert "strom_warmwasser_kwh" not in felder
    assert "strom_heizen_kwh" in felder
