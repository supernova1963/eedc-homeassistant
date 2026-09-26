"""Feldauswahl: die Felder je Investition/Anlage, Sonstiges-Kategorien, Live-Felder, Feld-Hinweise.
"""
# Reiner Umzug aus `core/field_definitions.py` (18.09.2026, Vorlage 3 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert
# alle Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from typing import Final, Optional
from backend.core.field_definitions.bedingungen import URTEIL_ERWEITERT, URTEIL_NEIN, _bedingungs_werte, _ist_geraeteklasse, _label_aufgeloest, anlage_typen_mit_kontext, bedingung_anlage_fuer, bedingungs_urteil, verdraengender_typ
from backend.core.field_definitions.keys import _mit_innengeraeten, basis_feld_key
from backend.core.field_definitions.registry import BASIS_FELDER, BEDINGTE_BASIS_FELDER, INVESTITION_FELDER, LIVE_FELDER_INV, OPTIONALE_FELDER


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def get_feld_hinweise() -> dict[str, dict[str, str]]:
    """Liefert die Feld-Hilfetexte als ``{kontext: {schluessel: hinweis}}``.

    Single Source of Truth für alle Hilfetexte (Sensor-Zuordnungs-Wizard,
    künftiger MQTT-Inbound-Wizard, manuelle Monatsdaten-Eingabe). Speist sich
    ausschließlich aus den ``hinweis``-Attributen der Felddefinitionen.

    Kontext-Schlüssel:
      - ``"basis"``            → keyed by ``mapping_key`` (so adressiert der
                                 BasisSensorenStep, z. B. ``"einspeisung"``)
      - Investitionstyp        → keyed by ``feld`` (z. B. ``"e-auto"``)
      - ``"sonstiges:<kat>"``  → keyed by ``feld``, je Sonstiges-Kategorie
                                 (Feldname allein ist mehrdeutig: Verbraucher
                                 vs. Speicher)
    """
    result: dict[str, dict[str, str]] = {}

    basis: dict[str, str] = {}
    for e in (*BASIS_FELDER, *BEDINGTE_BASIS_FELDER):
        mk, hinweis = e.get("mapping_key"), e.get("hinweis")
        if mk and hinweis:
            basis[mk] = hinweis
    result["basis"] = basis

    for typ, val in INVESTITION_FELDER.items():
        if isinstance(val, dict):  # sonstiges → nach Kategorie aufgeschlüsselt
            for kat, felder in val.items():
                result[f"sonstiges:{kat}"] = {
                    e["feld"]: e["hinweis"] for e in felder if e.get("hinweis")
                }
        else:
            result[typ] = {e["feld"]: e["hinweis"] for e in val if e.get("hinweis")}

    return result

def get_felder_fuer_investition(
    typ: str,
    parameter: Optional[dict],
    anlage_investitionen: Optional[list] = None,
    belegte_felder: Optional[set[str]] = None,
    jahr: Optional[int] = None,
    monat: Optional[int] = None,
) -> list[dict]:
    """
    Gibt die relevanten Felder für eine Investition zurück (Bedingungen aufgelöst).

    Filtert konditionelle Felder basierend auf:
    - Investitions-Parametern ("bedingung", z.B. "arbitrage_faehig")
    - Anlage-Kontext ("bedingung_anlage", z.B. "keine_pv_module")

    Für Typ "sonstiges" bitte get_felder_fuer_sonstiges() verwenden.

    Args:
        typ: Investitionstyp (z.B. "speicher", "e-auto")
        parameter: Investitions-Parameter-Dict (inv.parameter)
        anlage_investitionen: Alle Investitionen der Anlage (für bedingung_anlage).
                              None → bedingung_anlage wird nicht ausgewertet.
        belegte_felder: Feldnamen, für die es an diesem Gerät bereits einen Wert
                        oder eine Zuordnung gibt. Sie entscheiden über die
                        **erweiterten** Felder (R1, `weich` — s.
                        `bedingungs_urteil`): ein erweitertes Feld erscheint hier
                        nur, wenn es belegt ist.

                        ⭐ **Das ist R1 wörtlich:** *„was ein Gerät liefern kann,
                        sagt der zugeordnete Zähler, nicht seine Bauart."* Ohne
                        das Argument (Import, Checker) bleibt es beim harten
                        Bild — dort ändert sich nichts.
        jahr, monat: Der betrachtete Monat (Monatsabschluss) — „in Betrieb" einer
                     verdrängenden Investition gilt dann für ihn (N-555 Stufe 2,
                     Konzept Regel 0). Ohne: heute.

    Returns:
        Liste von Feld-Dicts ohne "bedingung"-Keys (bereits aufgelöst)
    """
    params = parameter or {}
    alle_felder = INVESTITION_FELDER.get(typ, [])

    if isinstance(alle_felder, dict):
        # Sonstiges — Kategorie-abhängig. Ohne gepflegte Kategorie wird hier
        # NICHT geraten (N-244); die Entscheidung liegt im SoT darunter.
        return get_felder_fuer_sonstiges(params.get("kategorie"))

    # Anlage-Kontext vorberechnen (einmalig, nicht pro Feld)
    anlage_typen: set[str] = set()
    if anlage_investitionen is not None:
        # N-555 Stufe 2: mit dem Pseudo-Typ „dienstliche Wallbox in Betrieb".
        anlage_typen = anlage_typen_mit_kontext(
            anlage_investitionen, jahr=jahr, monat=monat,
        )

    result = []
    bedingungs_werte = _bedingungs_werte(params)

    # Steuer-Schlüssel — hier ausgewertet bzw. nur für die Zuordnungs-Fläche
    # relevant, gehören nicht in die Eingabe-Antwort.
    SKIP_KEYS = {"bedingung", "weich", "bedingung_anlage", "label_wenn",
                 "nur_manuell", "nur_bestand", "je_innengeraet",
                 "label_je_innengeraet"}
    belegt = belegte_felder or set()

    for feld in alle_felder:
        # ⛔ `nur_bestand`: gar nicht mehr pflegbar — siehe Kopf dieser Datei.
        # Es bleibt allein in der Registry, damit eine BESTEHENDE Zuordnung auf
        # der Zuordnungs-Flaeche sichtbar und entfernbar ist; dort entscheidet
        # `ohne_nicht_zuordenbare` ueber `nur_manuell`. Hier faellt es immer.
        if feld.get("nur_bestand"):
            continue
        bedingung = feld.get("bedingung")
        # N-555 Stufe 2: `keine_dienstliche_wallbox` gilt nur an einem Dienstwagen.
        bedingung_anlage = bedingung_anlage_fuer(feld.get("bedingung_anlage"), params)

        # ── Anlage-Kontext-Bedingung ─────────────────────────────────────────
        # Hier wird gefiltert (Monatsabschluss/Import-Kontext). Die Datenquellen-
        # Fläche nutzt bewusst `get_alle_felder_fuer_investition` und wertet
        # `bedingung_anlage` selbst aus — sie muss ein bereits ZUGEORDNETES Feld
        # weiter zeigen, sonst verschwindet die Zuordnung unsichtbar und lässt
        # sich nicht mehr entfernen (`_bedarf_einstufung` in routes/datenquellen.py).
        if bedingung_anlage and anlage_investitionen is not None:
            # N-79: die Zuordnung Wert → verdrängender Typ steht im SoT
            # `BEDINGUNG_ANLAGE_VERDRAENGT`, nicht als `if`-Kette hier.
            # Unbekannter Wert ⇒ `None` ⇒ verdrängt nichts (fail-open).
            if verdraengender_typ(bedingung_anlage) in anlage_typen:
                continue  # Feld ausblenden: der verdrängende Typ ist da

        # ── Investment-Parameter-Bedingung ───────────────────────────────────
        urteil = bedingungs_urteil(bedingung, feld.get("weich"), bedingungs_werte)
        if urteil == URTEIL_NEIN:
            continue
        if urteil == URTEIL_ERWEITERT and basis_feld_key(feld["feld"]) not in belegt:
            # Erweitert und unbelegt: die Größe ist an diesem Gerät untypisch und
            # nichts deutet darauf hin, dass es sie gibt. Sie bleibt erreichbar —
            # über die Zuordnungs-Fläche, die erweiterte Felder ausdrücklich
            # zeigt. Hier stünde sie als leeres Eingabefeld in der ersten Reihe.
            continue

        aufgeloest = dict(feld)
        if urteil == URTEIL_ERWEITERT:
            aufgeloest["erweitert"] = True
        aufgeloest["label"] = _label_aufgeloest(feld, bedingungs_werte)
        result.append(aufgeloest)

    # #263 — je Innengerät eine Kopie, VOR dem Abstreifen der Steuer-Schlüssel:
    # `je_innengeraet` ist selbst einer, und ohne ihn wüsste die Erweiterung
    # nicht mehr, welche Felder sie vervielfältigen soll.
    result = _mit_innengeraeten(result, params, "feld")

    return [{k: v for k, v in f.items() if k not in SKIP_KEYS} for f in result]

def get_alle_felder_fuer_investition(typ: str, parameter: Optional[dict] = None) -> list[dict]:
    """
    Gibt ALLE Felder für einen Investitionstyp zurück — ohne Bedingungsfilter.

    Für Import-Kontext: alle Felder anbieten, unabhängig von aktuellen Parametern.
    Der Import soll nie Daten stillschweigend ignorieren. Dasselbe gilt für die
    Datenquellen-Fläche: ein bereits zugeordnetes Feld darf nicht unsichtbar
    verschwinden, sobald ein Parameter kippt.

    Das **Label** wird trotzdem an der konkreten Investition aufgelöst
    (`label_wenn`) — die Steuer-Keys (`bedingung`, `nur_manuell`, …) bleiben im
    Dict, weil die Aufrufer sie selbst auswerten. Ohne diese Auflösung hieß das
    Speicher-Feld auf der Fläche nur „Ladung", während im Monatsabschluss daneben
    „Ladung (gesamt, inkl. Netz)" stand — genau die Zweideutigkeit, an der ein
    Tester PV-Ladung und Netzladung addiert im Gesamt-Feld ablegte UND als
    Netzladung nochmal (Forum simon42 #89667/62 + /71, MartyBr).

    Args:
        typ: Investitionstyp
        parameter: Investitions-Parameter-Dict (Sonstiges-Kategorie + `label_wenn`)

    Returns:
        Liste aller Feld-Dicts (inkl. konditioneller Felder), Labels aufgelöst
    """
    alle_felder = INVESTITION_FELDER.get(typ, [])

    if isinstance(alle_felder, dict):
        # Sonstiges — Kategorie-abhängig. Ohne gepflegte Kategorie wird hier
        # NICHT geraten (N-244); die Entscheidung liegt im SoT darunter.
        params = parameter or {}
        return list(get_felder_fuer_sonstiges(params.get("kategorie")))

    # Kopie je Feld: die Dicts sind Modul-Konstanten, ein direktes Setzen des
    # Labels würde die Definition für alle folgenden Aufrufe umschreiben.
    bedingungs_werte = _bedingungs_werte(parameter)
    # ⚠ **Diese Funktion filtert NICHTS — sie markiert.** Drei Stufen, drei
    # Marken, und die Entscheidung fällt die Fläche
    # (`routes/datenquellen.py::ohne_nicht_zuordenbare`).
    #
    # Die Schalter (`getrennte_strommessung`, `arbitrage_faehig`, …) sind
    # umlegbar; bis dahin soll das Feld zuordenbar bleiben. Eine **harte**
    # Geräteklassen-Bedingung schließt die Größe dagegen aus: eine
    # Split-Klimaanlage hat keinen Warmwasserkreis, und das Feld dort anzubieten
    # wäre ein Angebot, das niemand einlösen kann (die P-6-Falle). Dazwischen
    # steht seit dem 26.08.2026 die **weiche** Bedingung: die Größe ist an
    # dieser Bauart untypisch, aber möglich — sie wird mit `erweitert` markiert,
    # die Fläche stellt sie hinter „Weitere Größen erfassen" (R1/W-2).
    #
    # ⛔ **Warum auch die harte Verletzung nur MARKIERT und nicht entfernt wird
    # — das ist der teuerste Teil dieser Funktion.** Ein Feld hier verschwinden
    # zu lassen, hieße: eine **bestehende Zuordnung** wird unsichtbar und damit
    # **unlöschbar**. Der Fall ist real und belegt: azywietz-web führt zwei
    # Klimaanlagen als `luft_wasser` (#383, weil das Feld „Wärmepumpenart" wie
    # eine Community-Einstellung beschriftet war). Stellt er sie um, hätte ein
    # zugeordneter `warmwasser_kwh`-Sensor keinen Weg mehr heraus.
    # `test_klima_ohne_warmwasser_n304.py::test_zuordnungsflaeche_zeigt_das_feld_weiter`
    # hält genau das fest — und hat am 26.08. einen ersten, zu groben Fix dieser
    # Stelle gefangen, der die Marke gegen ein `return None` getauscht hatte.
    #
    # ⛔ **Hier stand bis dahin ein exakter String-Vergleich**
    # (`f.get("bedingung") != "luft_luft"`), und der war die Ursache von **W-12**:
    # Er kannte weder die Negation `"!luft_luft"` (`warmwasser_kwh`) noch die
    # Listenform `["getrennte_strommessung", "!luft_luft"]`
    # (`strom_warmwasser_kwh`). Beide liefen daran vorbei — die Zuordnungs-Fläche
    # bot einer Split-Klimaanlage also **genau die zwei Warmwasser-Felder** an,
    # deren Fehlen der Daten-Checker bei OB73-gif zu Unrecht angemahnt hatte
    # (#263, repariert mit v4.0.28 — im Checker, nicht hier). Dritte Runde der
    # #236-Klasse: eine Regel auf einer Schicht reicht nicht bei parallelen
    # Pfaden. Der Auswerter (`bedingungs_urteil`) kennt beide Formen, und die
    # Fläche nimmt das markierte Feld heraus — **außer** es hat eine Quelle.
    # Dieselbe Bauform wie `nur_manuell`: Registry markiert, Fläche entscheidet.
    def _mit_urteil(feld: dict) -> dict:
        urteil = bedingungs_urteil(
            feld.get("bedingung"), feld.get("weich"), bedingungs_werte,
        )
        aufgeloest = {**feld, "label": _label_aufgeloest(feld, bedingungs_werte)}
        if urteil == URTEIL_ERWEITERT:
            aufgeloest["erweitert"] = True
        elif urteil == URTEIL_NEIN and _ist_geraeteklasse(feld.get("bedingung")):
            aufgeloest["nicht_an_dieser_bauart"] = True
        return aufgeloest

    return _mit_innengeraeten(
        [_mit_urteil(f) for f in alle_felder], parameter, "feld",
    )

def get_basis_felder(
    hat_dynamischen_tarif: bool = False,
    aktive_inv_typen: Optional[set[str]] = None,
    hat_variable_einspeisung: bool = False,
) -> list[dict]:
    """
    Gibt alle Basis-Felder für eine Anlage zurück (inkl. aufgelöster bedingter Felder).

    Kombiniert BASIS_FELDER + BEDINGTE_BASIS_FELDER, wobei letztere nur bei
    erfüllter Bedingung enthalten sind.

    Args:
        hat_dynamischen_tarif: True wenn die Anlage einen dynamischen Stromtarif hat
        aktive_inv_typen: Set der aktiven Investitionstypen (z.B. {"pv-module", "e-auto"})
        hat_variable_einspeisung: True wenn der (zum Stichtag gültige) allgemeine
            Tarif „Einspeisevergütung wechselt monatlich" trägt (#392)

    Returns:
        Liste von Feld-Dicts (ohne bedingung_basis-Key)
    """
    typen = aktive_inv_typen or set()
    result = list(BASIS_FELDER)

    for feld in BEDINGTE_BASIS_FELDER:
        bedingung = feld.get("bedingung_basis")
        if bedingung == "dynamischer_tarif" and not hat_dynamischen_tarif:
            continue
        if bedingung == "variable_einspeisung" and not hat_variable_einspeisung:
            continue
        if bedingung == "hat_eauto" and "e-auto" not in typen:
            continue
        if bedingung == "hat_waermepumpe" and "waermepumpe" not in typen:
            continue
        # bedingung_basis nicht an Consumer durchreichen
        result.append({k: v for k, v in feld.items() if k != "bedingung_basis"})

    return result

# Alle Monatsdaten-Feldnamen (Basis + Bedingte + Optionale) für generisches Speichern.
# Beim Save müssen keine Bedingungen geprüft werden — gespeichert wird was gesendet wurde.
ALLE_MONATSDATEN_FELDNAMEN: set[str] = {
    f["feld"] for f in BASIS_FELDER + BEDINGTE_BASIS_FELDER + OPTIONALE_FELDER
}

# Die Richtung, als die ein *Sonstiges*-Gerät **ohne gepflegte** `kategorie`
# gelesen wird — die eine benannte Stelle für eine Annahme, die am 17.08.2026
# an sechs Stellen als String-Literal `"verbraucher"` und an drei weiteren als
# `"erzeuger"` stand (N-244).
#
# **Warum ausgerechnet Verbraucher?** Weil beide Tages-Schreibpfade den Wert
# unter dieser Annahme überhaupt erst erzeugen (`live_sensor_config` ·
# `snapshot/komponenten_beitraege`) — wer ihn danach anders liest, liest an
# seiner eigenen Schreibweise vorbei. Begründung im Volltext:
# `berechnungen.energie.sonstiges_kwh_je_richtung`.
#
# ⚠ **Kein Ersatz für `energie.sonstiges_richtung`.** Diese Konstante gilt, wenn
# **kein Wert** vorliegt (Feldauswahl, Schlüsselbildung, Serienaufbau). Liegt
# einer vor, entscheidet er — das ist eine andere Frage und hat ihre eigene
# Funktion (N-250).
SONSTIGES_KATEGORIE_UNGEPFLEGT: Final[str] = "verbraucher"

# ─── Der dritte Zustand: Kategorien OHNE Stromrichtung (#377 / N-294) ────────
#
# *Sonstiges* war bis v4.0.22 **binär**: eine Kategorie ist entweder Erzeuger
# oder Verbraucher, und wer keine gepflegt hat, wird als Verbraucher gelesen
# (`SONSTIGES_KATEGORIE_UNGEPFLEGT`, neun Stellen — N-244). Ein **Zähler** ist
# weder das eine noch das andere: er trägt gar keine Stromrichtung, weil er gar
# keinen Strom führt. Ihn in eine der beiden Schubladen zu legen, hieße Gas oder
# Wasser in die Hausstrom-Aufschlüsselung zu geben.
#
# **Diese Konstante ist DER EINE ORT dafür.** Jede Stelle, die „ist das ein
# Erzeuger oder ein Verbraucher?" fragt, fragt zuerst hier — statt an neun
# Stellen `if kategorie == "zaehler"` zu schreiben, was die N-244-Wette ein
# zweites Mal wäre. Präzedenz im Baum: die Kategorie `speicher`, die
# `berechnungen.energie.sonstiges_kwh_je_richtung` bereits überspringt.
#
# ⚠ Eine Kategorie hier einzutragen heißt: sie taucht in **keiner**
# Energie-Rechnung auf. Wer eine hinzufügt, prüft die Stellen aus
# `test_377_zaehlerstaende.py` mit.
SONSTIGES_ZAEHLER_KATEGORIEN: Final[frozenset[str]] = frozenset({"zaehler"})

#: Der dritte Weg der Netzpunkt-Bilanz (§9.2): eine Kategorie mit EIGENER
#: Richtung — weder Erzeuger noch Verbraucher. Ihr Feld darf einem Gerät ohne
#: gepflegte Kategorie NICHT angeboten werden: dort liest jeder wertführende
#: Pfad „Verbraucher", und eine Abgabe als Verbrauch gelesen ist die N-244-Klasse
#: mit anderem Vorzeichen (dieselbe Begründung wie beim Verbrauchszähler).
SONSTIGES_ABGABE_KATEGORIE: Final[str] = "abgabe"

def ist_abgabe_kategorie(kategorie: Optional[str]) -> bool:
    """Gibt dieses *Sonstiges*-Gerät Strom an Dritte ab (§9.2)?"""
    return kategorie == SONSTIGES_ABGABE_KATEGORIE

#: Anzeigename der Kategorie — **ein** Wort für alle drei Zeilen, die dasselbe
#: Gerät nennen: die Energiezeile der Verwendungsseite, die Geldzeile im T-Konto
#: (`erloes_label`) und der Posten der Kapitalrechnung
#: (`BEZEICHNUNG_ABGABE = "Erlös aus " + dieser Name`). Regel 0: wer im T-Konto
#: „Einspeisung" liest, sucht in der Bilanz ein Wort, das dort nicht steht.
#: ⚑ Der **Schlüssel** bleibt `einspeise_erloes_euro` — §9.2: der Schlüssel ist
#: Code, der Anzeigename kommt aus der Kategorie.
SONSTIGES_ABGABE_LABEL: Final[str] = "Abgabe an Dritte"

#: Der eine Feldname der Kategorie — ausgeschrieben statt aus der Registry
#: gezogen, weil dieses Projekt von der Grep-Barkeit lebt. Dass beide
#: übereinstimmen, hält `test_377_zaehlerstaende.py` fest.
ZAEHLERSTAND_FELD: Final[str] = "zaehlerstand"

def ist_zaehler_kategorie(kategorie: Optional[str]) -> bool:
    """Trägt diese *Sonstiges*-Kategorie einen Zählerstand statt Strom?

    Die eine Frage hinter {@link SONSTIGES_ZAEHLER_KATEGORIEN} — als Funktion,
    damit die Aufrufer nicht das Set importieren und dabei die Prüfung selbst
    formulieren (dieselbe Begründung wie bei `ist_zustand_feld`).
    """
    return kategorie in SONSTIGES_ZAEHLER_KATEGORIEN

def ist_gepflegte_sonstiges_kategorie(kategorie: Optional[str]) -> bool:
    """Ist ``kategorie`` eine **gepflegte** Kategorie eines *Sonstiges*-Geräts?

    Abgeleitet aus der Registry, damit eine vierte Kategorie nicht an einer
    handgeschriebenen Aufzählung vorbeiläuft. Gegenstück zu
    ``berechnungen.energie.sonstiges_richtung``: die dort getroffene
    Entscheidung kennt nur die zwei **Richtungen**, diese Frage kennt alle
    Kategorien — auch ``speicher``, der keine Richtung hat.
    """
    return kategorie in INVESTITION_FELDER.get("sonstiges", {})

def _sonstiges_felder_ungepflegt() -> list[dict]:
    """Alle Richtungen eines *Sonstiges*-Geräts, dedupliziert — **abgeleitet**.

    Verbraucher-Felder zuerst: das ist die Richtung, die jeder wertführende Pfad
    ohne gepflegte Kategorie annimmt (`SONSTIGES_KATEGORIE_UNGEPFLEGT`), also
    die wahrscheinlichere Eingabe. `speicher` bringt keinen eigenen Feldnamen
    mit und steht deshalb nicht extra in der Liste — die Ableitung nimmt ihn
    trotzdem mit, damit eine künftige Erweiterung der Kategorie nicht still
    danebenfällt.

    **Abgeleitet statt geschrieben, aus demselben Grund wie N-259:** eine
    handgepflegte vierte Feldliste wäre wieder die Wette darauf, dass jemand
    sie beim nächsten neuen Feld mitzieht.

    ⛔ **Zähler-Kategorien sind ausgenommen** (#377): Diese Liste beantwortet
    „welche Felder könnte ein Gerät führen, dessen Kategorie noch **nicht
    gepflegt** ist?" — und ein Zählerstand gehört nie dazu. Ohne die Ausnahme
    böte die Zuordnungsfläche eines kategorielosen Geräts `zaehlerstand` neben
    den Strom-Feldern an, und der Anwender ordnete einen Gassensor einem Gerät
    zu, das eedc anschließend als Verbraucher liest: **N-244 ein zweites Mal.**
    """
    sonstiges = INVESTITION_FELDER.get("sonstiges", {})
    reihenfolge = [SONSTIGES_KATEGORIE_UNGEPFLEGT] + [
        k for k in sonstiges
        if (
            k != SONSTIGES_KATEGORIE_UNGEPFLEGT
            and not ist_zaehler_kategorie(k)
            and not ist_abgabe_kategorie(k)
        )
    ]
    gesehen: set[str] = set()
    out: list[dict] = []
    for kat in reihenfolge:
        for feld in sonstiges.get(kat, []):
            if feld["feld"] in gesehen:
                continue
            gesehen.add(feld["feld"])
            out.append(feld)
    return out

def get_felder_fuer_sonstiges(kategorie: Optional[str]) -> list[dict]:
    """
    Gibt Felder für eine Sonstiges-Investition nach Kategorie zurück.

    Args:
        kategorie: "erzeuger", "verbraucher", "speicher" — oder ``None``/leer/
                   unbekannt für ein Gerät **ohne gepflegte Kategorie**.

    Returns:
        Liste von Feld-Dicts. Ohne gepflegte Kategorie **alle Richtungen**
        (`SONSTIGES_FELDER_UNGEPFLEGT`), nicht eine geratene.

    **Warum hier nicht mehr geraten wird (N-244).** Bis 17.08.2026 stand hier
    ``sonstiges.get(kategorie, sonstiges.get("erzeuger", []))`` — ein Gerät ohne
    gepflegte Kategorie bekam also **Erzeuger**-Felder angeboten
    (``erzeugung_kwh`` · ``eigenverbrauch_kwh`` · ``einspeisung_kwh`` ·
    ``einspeise_erloes_euro``), während **jeder** wertführende Pfad denselben
    Zustand als *Verbraucher* liest und ``verbrauch_sonstig_kwh`` ·
    ``bezug_pv_kwh`` · ``bezug_netz_kwh`` erwartet (`sonstiges_feld_reihenfolge`
    28 Zeilen weiter unten, die beiden Tages-Schreibpfade,
    `berechnungen.energie.sonstiges_kwh_je_richtung`). Die **Schnittmenge beider
    Feldlisten ist leer** — die Zuordnungsfläche bot damit ausschließlich Felder
    an, die der Snapshot-Pfad für dieses Gerät nie sucht. Das ist die
    **N-259-Klasse**: nicht „Wert fehlt", sondern „Feld wird nirgends gefunden".
    """
    if ist_gepflegte_sonstiges_kategorie(kategorie):
        return INVESTITION_FELDER["sonstiges"][kategorie]
    return SONSTIGES_FELDER_UNGEPFLEGT

# Modul-Konstante statt Aufruf je Leser: die Ableitung ist rein und die
# Feld-Dicts sind ohnehin geteilte Modul-Objekte (wie in `INVESTITION_FELDER`).
SONSTIGES_FELDER_UNGEPFLEGT: Final[list[dict]] = _sonstiges_felder_ungepflegt()

def get_live_felder_fuer_investition(typ: str, parameter: Optional[dict] = None) -> list[dict]:
    """
    Gibt die Live-Felder (W/kW/%) für einen Investitionstyp zurück.

    Bedingungen werden anhand der Parameter aufgelöst (gleiche Semantik wie
    get_felder_fuer_investition). Gibt immer eine leere Liste zurück wenn der
    Typ keine Live-Felder hat.

    Args:
        typ: Investitionstyp
        parameter: Investitions-Parameter-Dict (für konditionelle Felder)

    Returns:
        Liste von Live-Feld-Dicts (key, label, einheit)
    """
    params = parameter or {}
    alle = LIVE_FELDER_INV.get(typ, [])
    bedingungs_werte = _bedingungs_werte(params)

    # ⛔ **Hier stand bis zum 26.08.2026 eine eigene `elif`-Kette** — der dritte
    # Nachbau derselben Frage, neben `bedingung_erfuellt` und dem
    # String-Vergleich in `get_alle_felder_fuer_investition` (W-12). Sie konnte
    # weder Listen noch neue Schlüssel: `brauchwasser` hätte sie stillschweigend
    # ignoriert, und zwar fail-open in die falsche Richtung. Jetzt liest auch sie
    # `bedingungs_urteil`.
    result = []
    for feld in alle:
        urteil = bedingungs_urteil(
            feld.get("bedingung"), feld.get("weich"), bedingungs_werte,
        )
        if urteil == URTEIL_NEIN:
            continue
        eintrag = {k: v for k, v in feld.items() if k not in ("bedingung", "weich")}
        if urteil == URTEIL_ERWEITERT:
            eintrag["erweitert"] = True
        result.append(eintrag)

    return _mit_innengeraeten(result, params, "key")
