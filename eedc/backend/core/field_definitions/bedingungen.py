"""Bedingungen und Urteile: der eine Bedingungs-Auswerter, Feld-Bedarf, Waerme-Achsen und
`groesse_gibt_es_am_geraet`.
"""
# Reiner Umzug aus `core/field_definitions.py` (18.09.2026, Vorlage 3 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert
# alle Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from typing import Final, Optional
from backend.core.investition_parameter import (
    ist_brauchwasser_waermepumpe,
    ist_dienstlich,
    ist_luft_luft_waermepumpe,
)
from backend.core.betriebsmodus import (
    HEIZEN as BM_HEIZEN,
    WAERME_ACHSEN as BM_WAERME_ACHSEN,
    WARMWASSER as BM_WARMWASSER,
)
from backend.core.field_definitions.keys import basis_feld_key
from backend.core.field_definitions.registry import INVESTITION_FELDER


# =============================================================================
# Bedarf je Feld — steuert die Zuordnungs-Fläche (Datenquellen-V4)
#
# EINE Tabelle statt eines Attributs an ~40 verstreuten Feld-Dicts: die
# Einstufung ist eine fachliche Festlegung und muss an einer Stelle prüfbar
# bleiben. Die Feld-TEXTE (`hinweis`) stehen weiter beim Feld — Text beschreibt,
# diese Tabelle bewertet.
#
#   "pflicht"  — ohne diesen Wert fehlt eine Kernauswertung. Die Fläche zeigt
#                das Feld rot und mit aufgeklapptem Hinweis, solange weder es
#                selbst noch ein Mitglied seiner `gruppe` eine Quelle hat.
#   "optional" — leise grau, zählt nie als offener Punkt.
#
# `gruppe` = Alternativ-Gruppe: EINE belegte Quelle in der Gruppe genügt, die
# übrigen Mitglieder gelten dann als abgedeckt (nicht als Lücke). Das löst die
# Konstellationen auf, in denen zwei Erfassungswege einander ausschließen:
#   pv_energie — Anlagen-Zählerstand ODER Zähler je PV-Modul/Balkonkraftwerk
#   pv_live    — Anlagen-Leistung ODER Leistung je Modul
#   netz_live  — „Netz kombiniert (±)" ODER Einspeisung+Netzbezug getrennt
#
# WICHTIG — „keine Quelle" ist kein Fehler: alle kWh-Felder lassen sich im
# Monatsabschluss auch manuell erfassen. Rot heißt deshalb „hier fehlt noch
# etwas", nie „falsch"; die Hinweistexte nennen die manuelle Alternative.
# =============================================================================

FELD_BEDARF: dict[tuple[str, str], tuple[str, Optional[str]]] = {
    # ── Anlage (Basis) ──────────────────────────────────────────────────────
    # Kernwerte laut Daten-Checker (`daten_checker/monatsdaten.py`: „Kernfeld —
    # ohne Einspeisung sind Eigenverbrauch und Autarkie nicht berechenbar").
    ("basis", "einspeisung_kwh"): ("pflicht", None),
    ("basis", "netzbezug_kwh"): ("pflicht", None),
    ("basis", "pv_gesamt_kwh"): ("pflicht", "pv_energie"),
    # Live-Felder sind durchweg optional: ohne sie bleibt das Live-Dashboard
    # leer, die Statistik läuft über die kWh-Zählerstände weiter.
    ("basis", "einspeisung_w"): ("optional", "netz_live"),
    ("basis", "netzbezug_w"): ("optional", "netz_live"),
    ("basis", "netz_kombi_w"): ("optional", "netz_live"),
    ("basis", "pv_gesamt_w"): ("optional", "pv_live"),
    ("basis", "aussentemperatur_c"): ("optional", None),

    # ── PV ──────────────────────────────────────────────────────────────────
    ("pv-module", "pv_erzeugung_kwh"): ("pflicht", "pv_energie"),
    ("pv-module", "leistung_w"): ("optional", "pv_live"),
    # ⛔ Kein PV-Erzeuger mehr (Gernot 24.08.2026) — und DIESE Zeile war der
    # eigentliche Schaden: als Mitglied der Gruppe `pv_energie` hat ein hier
    # belegtes Feld `basis:pv_gesamt` UND das Modul-Feld auf „bereits an
    # anderer Stelle zugeordnet" gesetzt, waehrend es selbst nirgends gelesen
    # wurde. Drei Quellen inaktiv, keine wirksam (#388/F-57). `("optional",
    # None)` statt Streichung: der Eintrag traegt die Begruendung, und ein
    # fehlender Schluessel faellt still auf FELD_BEDARF_DEFAULT zurueck.
    ("wechselrichter", "pv_erzeugung_kwh"): ("optional", None),
    ("wechselrichter", "leistung_w"): ("optional", "pv_live"),
    ("balkonkraftwerk", "pv_erzeugung_kwh"): ("pflicht", "pv_energie"),
    ("balkonkraftwerk", "leistung_w"): ("optional", "pv_live"),
    ("balkonkraftwerk", "eigenverbrauch_kwh"): ("optional", None),
    ("balkonkraftwerk", "speicher_ladung_kwh"): ("optional", None),
    ("balkonkraftwerk", "speicher_entladung_kwh"): ("optional", None),

    # ── Speicher ────────────────────────────────────────────────────────────
    # Ohne Lade-/Entlademenge bleibt die gesamte Speicher-Auswertung leer und
    # der Hausverbrauch wird falsch gerechnet (Daten-Checker warnt darauf).
    ("speicher", "ladung_kwh"): ("pflicht", None),
    ("speicher", "entladung_kwh"): ("pflicht", None),
    ("speicher", "ladung_netz_kwh"): ("optional", None),
    ("speicher", "speicher_ladepreis_cent"): ("optional", None),
    ("speicher", "leistung_w"): ("optional", None),
    ("speicher", "soc"): ("optional", None),

    # ── Wärmepumpe ──────────────────────────────────────────────────────────
    # Strom UND abgegebene Wärme: erst beide zusammen ergeben JAZ, Ersparnis
    # und CO₂. Der Strom kommt je nach Parameter aus einem oder zwei Feldern.
    ("waermepumpe", "stromverbrauch_kwh"): ("pflicht", "wp_strom"),
    ("waermepumpe", "strom_heizen_kwh"): ("pflicht", "wp_strom"),
    ("waermepumpe", "strom_warmwasser_kwh"): ("pflicht", "wp_strom"),
    # Ausnahme Split-Klimaanlage: s. KLIMA_OHNE_WAERMEMENGE unter der Tabelle.
    #
    # N-391: **eine ALTERNATIV-Gruppe** (`BEDARF_GRUPPEN_ALTERNATIV` unter der
    # Tabelle) — wer EINEN gemeinsamen Wärmemengenzähler hat, trägt seinen Wert
    # unter *Wärme gesamt* ein, und *Heizwärme* ist damit gedeckt. Beide Wege
    # führen zur selben Größe; keiner ist ein Summand des anderen.
    ("waermepumpe", "heizenergie_kwh"): ("pflicht", "wp_waerme"),
    ("waermepumpe", "waerme_kwh"): ("pflicht", "wp_waerme"),
    ("waermepumpe", "warmwasser_kwh"): ("optional", None),
    ("waermepumpe", "leistung_w"): ("optional", None),
    ("waermepumpe", "leistung_heizen_w"): ("optional", None),
    ("waermepumpe", "leistung_warmwasser_w"): ("optional", None),
    ("waermepumpe", "leistung_kuehlen_w"): ("optional", None),
    ("waermepumpe", "warmwasser_temperatur_c"): ("optional", None),
    # #263 K-2 (Konzept §7 E-E): JEDER Wärmepumpe angeboten, nicht nur
    # `wp_art = luft_luft`. Der Grund ist gemessen, nicht vorsorglich:
    # azywietz-webs zwei Klimaanlagen laufen als `luft_wasser`, weil das Feld
    # „Wärmepumpenart" als Community-Einstellung beschriftet war — wer nur
    # `luft_luft` bedient, baut an genau der Gruppe vorbei, die das Thema
    # meldet. Es gibt außerdem Luft-Wasser-Wärmepumpen MIT Kühlfunktion.
    # „optional": wer keinen Modus-Sensor zuordnet, merkt nichts.
    ("waermepumpe", "betriebsmodus"): ("optional", None),

    # ── E-Auto ──────────────────────────────────────────────────────────────
    # Kilometer sind der Bezugswert für Effizienz und Benzin-Vergleich.
    # Die Heimladungs-Felder gibt es seit N-555 Stufe 2 an jedem E-Auto; nur ein
    # Dienstwagen neben einer dienstlichen Wallbox bekommt sie nicht
    # (`bedingung_anlage: keine_dienstliche_wallbox`) — das wertet die Fläche selbst aus.
    ("e-auto", "km_gefahren"): ("pflicht", None),
    # #407: der Stand ist Hilfe, nicht Pflicht — wer die Menge kennt, trägt sie ein.
    ("e-auto", "km_stand"): ("optional", None),
    ("e-auto", "verbrauch_kwh"): ("optional", None),
    ("e-auto", "ladung_pv_kwh"): ("optional", None),
    ("e-auto", "ladung_netz_kwh"): ("optional", None),
    # N-555 Stufe 2: „Heim: gesamt" (E5) — optional wie die beiden Teile.
    ("e-auto", "ladung_kwh"): ("optional", None),
    ("e-auto", "ladung_extern_kwh"): ("optional", None),
    ("e-auto", "ladung_extern_euro"): ("optional", None),
    ("e-auto", "v2h_entladung_kwh"): ("optional", None),
    ("e-auto", "leistung_w"): ("optional", None),
    ("e-auto", "soc"): ("optional", None),

    # ── Wallbox ─────────────────────────────────────────────────────────────
    ("wallbox", "ladung_kwh"): ("pflicht", None),
    ("wallbox", "ladung_pv_kwh"): ("optional", None),
    ("wallbox", "ladevorgaenge"): ("optional", None),
    ("wallbox", "leistung_w"): ("optional", None),
}

# Default für alles, was nicht in der Tabelle steht (u. a. „sonstiges", dessen
# Felder kategorie-abhängig erzeugt werden): nie rot, nie als Lücke gezählt.
FELD_BEDARF_DEFAULT: tuple[str, Optional[str]] = ("optional", None)

# Die Gruppen, deren Mitglieder **Alternativen** sind — ein belegtes Feld deckt
# die Gruppe, die übrigen sind dann nichts mehr einzutragen.
#
# ⭐ **Warum diese Menge existiert (N-391, 14.09.2026).** Die Spalte
# `bedarf_gruppe` trug bis dahin ZWEI Bedeutungen in einem Wort:
#
# * **Alternativen** — Anlagen-Gesamtzähler *oder* Komponentenzähler
#   (`pv_energie`), kombinierter *oder* getrennter Netz-Live-Sensor
#   (`netz_live`), gemeinsamer *oder* getrennte Wärmemengenzähler (`wp_waerme`).
#   Ein belegtes Mitglied macht die Gruppe vollständig.
# * **Summanden** — `wp_strom` bei getrennter Strommessung: `strom_heizen_kwh`
#   und `strom_warmwasser_kwh` tragen **zusammen** den Verbrauch, jedes einzeln
#   nur die Hälfte. Genau das hat N-456 (13.09.) festgestellt und mit
#   `pflicht_am_geraet` abgesichert.
#
# ⛔ **Ohne die Unterscheidung an EINER Stelle wäre N-391 an N-456 gescheitert:**
# `heizenergie_kwh` und `waerme_kwh` sind an jedem Gerät beide „pflicht", also
# hätte die Regel von N-456 („zwei Pflichtfelder derselben Gruppe sind
# Summanden") sie beide gefordert — die Zuordnungs-Fläche und der Daten-Checker
# hätten einen zweiten Wärmemengenzähler angemahnt, den es nicht gibt.
# Die Alternative wären zwei Sonderregeln in zwei Konsumenten gewesen; die
# benannte Menge sagt es einmal.
BEDARF_GRUPPEN_ALTERNATIV: frozenset[str] = frozenset({
    "pv_energie", "pv_live", "netz_live", "wp_waerme",
})

# Felder, deren Pflicht bei einer Split-Klimaanlage (`wp_art="luft_luft"`) entfällt.
#
# Die Tabelle oben kennt nur (typ, feld) — für die Wärmepumpe reicht das nicht: eine
# Split-Klimaanlage hat weder Wärmemengenzähler noch Warmwasserkreis. Genau deshalb
# stellt der Daten-Checker die „Heizwärme fehlt"-Forderung dort seit K-0 NICHT mehr
# (`daten_checker/monatsdaten.py::_check_wp_monatsdaten`, Begründung dort:
# „Dauer-Falschpositiv"). Die Zuordnungs-Fläche stellte sie weiter — dieselbe Anlage,
# zwei Flächen, gegenteilige Aussage: der Checker schwieg, *Einstellungen →
# Datenquellen* zeigte „Heizwärme" rot, aufgeklappt und zählte sie als offene Pflicht
# (Fund N-86; Melder mit Klimaanlage: dietmar1968 #89667/87, kingcap1 #263).
#
# „optional" und nicht „inaktiv": inaktiv heißt „ein anderer Weg gewinnt"
# (Alternativ-Gruppe belegt, verdrängendes Gerät) — hier gewinnt kein anderer Weg,
# die Größe existiert an diesem Gerät schlicht nicht. Wer doch einen
# Wärmemengenzähler an seiner Klimaanlage hat, ordnet ihn weiterhin zu.
#
# `warmwasser_kwh` steht bewusst nicht hier: es ist ohnehin schon „optional".
KLIMA_OHNE_WAERMEMENGE: frozenset[tuple[str, str]] = frozenset({
    ("waermepumpe", "heizenergie_kwh"),
})

def get_feld_bedarf(
    typ: str, feld: str, parameter: Optional[dict] = None,
) -> tuple[str, Optional[str]]:
    """Bedarf + Alternativ-Gruppe eines Felds — siehe {@link FELD_BEDARF}.

    `parameter` ist das `Investition.parameter`-Dict des Geräts (auf Anlagen-Ebene
    None). Ohne es bleibt die reine (typ, feld)-Einstufung — Aufrufer, die keinen
    Geräte-Kontext haben, müssen nichts wissen.
    """
    # #263 — je-Innengerät-Keys erben die Einstufung ihres Basis-Felds.
    feld = basis_feld_key(feld)
    bedarf = FELD_BEDARF.get((typ, feld), FELD_BEDARF_DEFAULT)
    if (typ, feld) in KLIMA_OHNE_WAERMEMENGE and ist_luft_luft_waermepumpe(parameter):
        return ("optional", bedarf[1])
    # B2 (05.09.2026, R1): **Ein erweitertes Feld ist nie Pflicht.** Die weiche
    # Bedingung sagt „an diesem Gerät untypisch, aber möglich" — wer es
    # gepflegt hat, meint es so; wer nicht, dem fehlt nichts. Bis dahin galt
    # `strom_heizen_kwh` an einer Brauchwasser-Wärmepumpe als Pflicht, obwohl
    # dieselbe Registry es hinter „Weitere Größen erfassen" stellte: dieselbe
    # Anlage, zwei Aussagen. Die Regel steht HIER, damit jeder Frager (Checker,
    # Topic-Registry, Zuordnungs-Fläche) dieselbe Antwort bekommt.
    if parameter is not None and feld_urteil(typ, feld, parameter) == URTEIL_ERWEITERT:
        return ("optional", bedarf[1])
    return bedarf

def feld_urteil(typ: str, feld: str, parameter: Optional[dict]) -> str:
    """Gilt das Feld an diesem Gerät, ist es **erweitert**, oder gibt es die Größe nicht?

    Öffentliche Lesetür auf `bedingungs_urteil` für Frager außerhalb der
    Registry (B2, 05.09.2026). ⭐ **Sie ist die eine Antwort auf die Frage, die
    bis dahin vier Daten-Checker-Stellen selbst mit `ist_luft_luft_waermepumpe`
    beantworteten** — jede ein wenig anders (Erwartung nach Bauart, Schweigen
    nach Bauart, Label nach Bauart). SOLL Wärme/Klima R1: *was ein Gerät liefern
    kann, sagt der zugeordnete Zähler, nicht seine Bauart* — und was die Bauart
    **vorschlagen** darf, steht genau einmal, in den `bedingung`/`weich`-Einträgen
    dieser Registry. Wer fragt, fragt hier; die Bauart selbst liest er nicht mehr
    (ADR-002/P13 hält das baumweit).

    Fail-open wie `groesse_gibt_es_am_geraet`: unbekannter Typ oder unbekanntes
    Feld ⇒ ``URTEIL_GILT``.
    """
    feld = basis_feld_key(feld)
    for eintrag in INVESTITION_FELDER.get(typ) or ():
        if not isinstance(eintrag, dict) or eintrag.get("feld") != feld:
            continue
        return bedingungs_urteil(
            eintrag.get("bedingung"), eintrag.get("weich"), _bedingungs_werte(parameter),
        )
    return URTEIL_GILT

def feld_herabgestuft(typ: str, feld: str, parameter: Optional[dict]) -> bool:
    """Hat die Registry dieses Feld **für dieses Gerät** zurückgenommen?

    ``True``, wenn die Größe am Gerät nicht existiert (``URTEIL_NEIN``),
    erweitert ist (``URTEIL_ERWEITERT``) oder ihr Bedarf gegenüber dem Typ-
    Default herabgesetzt wurde (`KLIMA_OHNE_WAERMEMENGE`: Heizwärme an einer
    Split-Klimaanlage ist optional statt Pflicht). Das ist die Frage, die ein
    Hinweis stellen muss, bevor er eine Zusatz-Messstelle anmahnt: **Erwartet
    eedc diese Größe an diesem Gerät überhaupt?** — und die Antwort kommt aus
    der Registry, nicht aus der Bauart (B2, R1).
    """
    feld = basis_feld_key(feld)
    if feld_urteil(typ, feld, parameter) != URTEIL_GILT:
        return True
    return get_feld_bedarf(typ, feld, parameter)[0] != get_feld_bedarf(typ, feld, None)[0]

def pflicht_felder_am_geraet(
    typ: str, parameter: Optional[dict], gruppe: Optional[str] = None,
) -> list[str]:
    """Die Felder, die dieses Gerät **liefern muss** — Pflicht UND am Gerät geltend.

    ``gruppe`` schränkt auf eine Alternativ-Gruppe der `FELD_BEDARF`-Tabelle ein
    (z. B. ``"wp_strom"`` — die Zählerfelder, die die Energieprofil-Abdeckung
    prüft). Ohne sie kommen alle Pflichtfelder, also auch die Heizwärme, die
    keine Zählerfrage ist.

    Registry-Antwort auf „welche Zähler erwartet der Daten-Checker?" (B2). Ein
    Feld zählt, wenn sein Bedarf `pflicht` ist und sein Urteil ``URTEIL_GILT``
    (weder erweitert noch nicht vorhanden). Für die Wärmepumpe ergibt das je nach
    Parametern: ohne getrennte Strommessung ``stromverbrauch_kwh``; mit ihr
    ``strom_heizen_kwh`` + ``strom_warmwasser_kwh``; an einer Split-Klimaanlage
    entfällt die Warmwasser-Seite (kein Warmwasserkreis, N-304/B5), an einer
    Brauchwasser-Wärmepumpe die Heiz-Seite (erweitert, A6). **Kein `if wp_art`
    im Frager** — die Ausnahmen stehen in der Registry, einmal.

    ⚠ **Felder einer ALTERNATIV-Gruppe stehen hier weiterhin mit drin**
    (`heizenergie_kwh`): Die Liste sagt, was eedc an diesem Gerät **erwartet**,
    und das tut sie weiter. Ob ein belegtes Geschwisterfeld sie **verdrängen**
    darf, ist eine andere Frage — sie wird dort beantwortet, wo verdrängt wird
    (`mqtt_topic_registry` setzt `pflicht_am_geraet`, `stufe_bedarf_ein` liest
    es), und zwar an `BEDARF_GRUPPEN_ALTERNATIV`.
    """
    felder = INVESTITION_FELDER.get(typ)
    if not isinstance(felder, list):
        return []
    out: list[str] = []
    for eintrag in felder:
        if not isinstance(eintrag, dict) or eintrag.get("nur_bestand"):
            continue
        feld = eintrag["feld"]
        bedarf, bedarf_gruppe = get_feld_bedarf(typ, feld, parameter)
        if bedarf != "pflicht":
            continue
        if gruppe is not None and bedarf_gruppe != gruppe:
            continue
        if feld_urteil(typ, feld, parameter) != URTEIL_GILT:
            continue
        out.append(feld)
    return out

#: Bedingungs-Schlüssel, die eine **Geräteklasse** beschreiben statt eines
#: Schalters. Der Unterschied entscheidet auf der Zuordnungs-Fläche
#: (`get_alle_felder_fuer_investition`): Ein Schalter ist umlegbar, sein Feld
#: bleibt deshalb zuordenbar; eine Geräteklasse schließt die Größe aus, ihr Feld
#: verschwindet. Weiche Bedingungen sind von beidem unberührt — sie entfernen
#: nie, sie markieren (`bedingungs_urteil`).
GERAETEKLASSEN_SCHLUESSEL: Final[frozenset[str]] = frozenset(
    {"luft_luft", "brauchwasser"}
)

def _ist_geraeteklasse(bedingung) -> bool:
    """Trägt `bedingung` einen Geräteklassen-Schlüssel? (auch negiert, auch in Liste)"""
    if not bedingung:
        return False
    tokens = (bedingung,) if isinstance(bedingung, str) else tuple(bedingung)
    return any(t.lstrip("!") in GERAETEKLASSEN_SCHLUESSEL for t in tokens)

def _bedingungs_werte(parameter: Optional[dict]) -> dict[str, bool]:
    """Die Bedingungs-Keys einer Investition — eine Auswertung für alle Feld-Wege.

    Dieselben Keys steuern `bedingung` (Feld zeigen?) und `label_wenn` (wie heißt
    es dann?). Beide Wege lesen sie hier, damit die Zuordnungs-Fläche kein zweites,
    abweichendes Bild bekommt.
    """
    params = parameter or {}
    arbitrage_faehig = bool(params.get("arbitrage_faehig"))
    return {
        # #263: eine Betriebsart (Heizen/Kühlen/Lüften/Entfeuchten) hat nur ein
        # Klimagerät — bei der Luft-Wasser-WP heißt die Achse Heizen/Warmwasser.
        "luft_luft": ist_luft_luft_waermepumpe(params),
        # R1/A6: ein Gerät mit ausschließlich Warmwasser-Achse. Steuert die
        # WEICHE Herabstufung von Heizen — nie deren Entfernung.
        "brauchwasser": ist_brauchwasser_waermepumpe(params),
        "getrennte_strommessung": bool(params.get("getrennte_strommessung")),
        "arbitrage_faehig": arbitrage_faehig,
        # Arbitrage impliziert Netzladung — das Flag ist nur ein Erfassungs-Schalter,
        # die UI für `ladung_netz_kwh` muss auch ohne Arbitrage sichtbar sein können.
        "laedt_aus_netz": bool(params.get("laedt_aus_netz")) or arbitrage_faehig,
        "v2h_faehig": bool(params.get("v2h_faehig") or params.get("nutzt_v2h")),
        "hat_speicher": bool(params.get("hat_speicher")),
    }

#: Die drei Ausgänge von `bedingungs_urteil`.
URTEIL_GILT: Final[str] = "gilt"

URTEIL_ERWEITERT: Final[str] = "erweitert"

URTEIL_NEIN: Final[str] = "nein"

#: `bedingung_anlage` → der Investitionstyp, dessen Vorhandensein das Feld
#: verdrängt. **Der eine Ort dieser Zuordnung** (N-79).
#:
#: ⚠ Bis 2026-08-29 stand dieselbe Abbildung **zweimal** fest verdrahtet: hier
#: als `if`-Kette in `get_felder_fuer_investition` und als `_VERDRAENGT_TYP` in
#: `services/datenquellen_validierung.py`. Beide Kopien waren wertgleich — und
#: genau das ist die Falle: Ein dritter Wert, nur in eine der beiden Kopien
#: eingetragen, verdrängt das Feld auf der Datenquellen-Fläche, aber nicht im
#: Monatsabschluss (oder umgekehrt), und zwar **still**.
#:
#: ⚑ `bedingung` und `weich` hatten ihren Auswerter längst (`bedingungs_urteil`),
#: `label_wenn` wird an genau einer Stelle gelesen — `bedingung_anlage` war der
#: einzige Schlüssel der Registry ohne SoT.
#: Pseudo-Typ für die Anlagen-Typenmenge (N-555 Stufe 2, Konzept Regel 3 + 8): eine
#: **dienstliche Wallbox in Betrieb**. Sie ist die dienstliche Ladung; die Heim-Felder
#: und die Schätzung eines Dienstwagens zählen daneben nicht (die eine Funktion
#: ``entscheide_emob_heimladung`` entscheidet das, nicht das Formular — das Formular
#: bietet die Felder dort nur nicht an). Er steht in der Typenmenge nur, wenn
#: ``anlage_typen_mit_kontext`` ihn setzt.
TYP_DIENSTLICHE_WALLBOX: Final[str] = "wallbox:dienstlich"

BEDINGUNG_ANLAGE_VERDRAENGT: Final[dict[str, str]] = {
    # Bis 26.09.2026 an „Heim: PV/Netz" des E-Autos (Phase 2a). Seit N-555 Stufe 2
    # von keinem Feld mehr benutzt — der Wert bleibt im Vokabular, damit die Regel
    # wieder gesetzt werden kann, ohne sie neu herzuleiten.
    "keine_wallbox": "wallbox",
    # Von keinem Feld mehr benutzt (s. Kasten bei `ladung_pv_kwh`: die Bedingung
    # ist 2026 bewusst entfallen) — der Wert bleibt im Vokabular, damit die
    # Regel wieder gesetzt werden kann, ohne sie neu herzuleiten.
    "keine_pv_module": "pv-module",
    # N-555 Stufe 2: die Heim-Felder eines DIENSTWAGENS neben einer dienstlichen
    # Wallbox in Betrieb. Gilt nur für einen Dienstwagen — ``bedingung_anlage_fuer``
    # nimmt die Bedingung an einem privaten Auto heraus.
    "keine_dienstliche_wallbox": TYP_DIENSTLICHE_WALLBOX,
}

#: Bedingungen, die nur an einem **Dienstwagen** greifen (``bedingung_anlage_fuer``).
_NUR_AM_DIENSTWAGEN: Final[frozenset[str]] = frozenset({"keine_dienstliche_wallbox"})


def bedingung_anlage_fuer(bedingung_anlage, parameter) -> Optional[str]:
    """Die ``bedingung_anlage`` eines Felds, wie sie an DIESEM Gerät gilt.

    ``keine_dienstliche_wallbox`` gilt nur an einem Dienstwagen (Konzept Regel 3): ein
    privates Auto neben einer dienstlichen Wallbox behält seine Heim-Felder. Alle anderen
    Werte gelten unabhängig vom Gerät. Gibt ``None`` zurück, wenn am Gerät nichts gilt.
    """
    if not bedingung_anlage:
        return None
    if bedingung_anlage in _NUR_AM_DIENSTWAGEN and not ist_dienstlich(parameter):
        return None
    return bedingung_anlage


def _in_betrieb(inv, jahr: Optional[int], monat: Optional[int]) -> bool:
    """Regel 0: in Betrieb im betrachteten Monat — ohne Zeitraum: heute."""
    if jahr is not None and monat is not None and hasattr(inv, "ist_aktiv_im_monat"):
        return bool(inv.ist_aktiv_im_monat(jahr, monat))
    if hasattr(inv, "ist_aktiv_an"):
        from datetime import date as _date
        return bool(inv.ist_aktiv_an(_date.today()))
    return True  # Proben mit Platzhalter-Objekten: ohne Laufzeit gilt das Gerät


def anlage_typen_mit_kontext(
    anlage_investitionen, *, jahr: Optional[int] = None, monat: Optional[int] = None,
) -> set:
    """Die Typenmenge der Anlage für ``bedingung_anlage`` — mit den Pseudo-Typen.

    Die Investitionstypen, dazu ``TYP_DIENSTLICHE_WALLBOX``, wenn eine dienstliche
    Wallbox **in Betrieb** ist (Regel 0: im betrachteten Monat; wo kein Zeitraum da ist —
    CSV-Vorlage, Datenquellen-Fläche —, heute). Der eine Ort für beide Auswerter
    (``get_felder_fuer_investition`` und die Datenquellen-Fläche).
    """
    invs = list(anlage_investitionen or ())
    typen = {getattr(i, "typ", None) for i in invs}
    if any(
        getattr(i, "typ", None) == "wallbox"
        and ist_dienstlich(getattr(i, "parameter", None))
        and _in_betrieb(i, jahr, monat)
        for i in invs
    ):
        typen.add(TYP_DIENSTLICHE_WALLBOX)
    return typen

def verdraengender_typ(bedingung_anlage) -> Optional[str]:
    """Welcher Investitionstyp verdrängt ein Feld mit dieser `bedingung_anlage`?

    Gibt den Typ zurück (`"wallbox"`), oder `None`, wenn das Feld keine solche
    Bedingung trägt **oder der Wert unbekannt ist**.

    ⚠ **Ein unbekannter Wert verdrängt nicht** (fail-open) — dieselbe Wahl wie
    in `bedingung_erfuellt` und `bedingungs_urteil`, und aus demselben Grund:
    Die Gegenrichtung ließe ein bereits **zugeordnetes** Feld unsichtbar
    verschwinden und damit unlöschbar zurückbleiben. Ein Auswerter, der wirft,
    wäre die F-59-Klasse (latenter 500er im Lesepfad).

    Gegen den Tippfehler steht deshalb ein Wächter, kein Laufzeitfehler:
    ``test_bedingung_anlage_sot_n79.py::test_jeder_bedingung_anlage_wert_ist_bekannt``.
    """
    if not bedingung_anlage:
        return None
    return BEDINGUNG_ANLAGE_VERDRAENGT.get(bedingung_anlage)

def bedingungs_urteil(
    bedingung, weich, bedingungs_werte: dict[str, bool],
) -> str:
    """Gilt das Feld, ist es **erweitert**, oder gibt es die Größe hier nicht?

    ⭐ **Es gibt zwei Sorten Bauart-Abhängigkeit, und bis zum 26.08.2026 waren
    sie derselbe Mechanismus** — das ist die Ursache hinter Befund W-2:

    ======  ====================================  ==========================
    Sorte   Beispiel                              Folge
    ======  ====================================  ==========================
    hart    Luft-Luft hat keinen Warmwasserkreis  Feld verschwindet
    weich   Sole-Wasser-WP **mit** Kühlung        Feld ist „erweitert"
    ======  ====================================  ==========================

    MartyBr hat seit dem Sommer 2026 einen getrennten Kühlzähler an einer
    Wärmepumpe und konnte ihn **nirgends** hinterlegen; pipp086 fragt nach
    derselben Größe (Forum T89667 #199/#200). Die alte Begründung — „acht
    Betriebsart-Felder an jeder Wärmepumpe sind acht Angebote, die niemand
    einlösen kann" — bleibt richtig und wird hier eingelöst, **ohne** einen
    Fall auszuschließen: erweiterte Felder stehen auf der Zuordnungs-Fläche
    hinter einem Schritt „Weitere Größen erfassen".

    ⚠ **Hart schlägt weich.** Ein Feld kann beides tragen — `strom_heizen_kwh`
    braucht `getrennte_strommessung` **hart** (ohne Kennzeichen gibt es die
    getrennte Achse nicht) und `!brauchwasser` **weich** (an einer
    Brauchwasser-WP untypisch, aber möglich). Genau diese Kombination ist der
    Grund, warum `weich` die **Schlüssel** nennt und kein Wahrheitswert am Feld
    ist: mit einem Bool ließe sich nicht sagen, *welche* der beiden Bedingungen
    weich gemeint war.

    ⚠ **Ein unbekannter Schlüssel gilt** (fail-open) — wie in
    `bedingung_erfuellt`, und aus demselben Grund: ein Tippfehler ließe sonst
    ein **zugeordnetes** Feld unsichtbar verschwinden und damit unlöschbar
    zurückbleiben. Gewächtert wird der Tippfehler, nicht abgefangen
    (`test_b5_strom_warmwasser_luft_luft.py::
    test_jede_bedingung_der_registry_ist_ein_bekannter_schluessel`).
    """
    if not bedingung:
        return URTEIL_GILT
    weiche_schluessel = frozenset(weich or ())
    tokens = (bedingung,) if isinstance(bedingung, str) else tuple(bedingung)
    urteil = URTEIL_GILT
    for token in tokens:
        negiert = token.startswith("!")
        schluessel = token[1:] if negiert else token
        if schluessel not in bedingungs_werte:
            continue  # unbekannt → nicht filtern, s. Kasten oben
        if bedingungs_werte[schluessel] == negiert:
            if schluessel not in weiche_schluessel:
                return URTEIL_NEIN  # hart schlägt weich, sofort
            urteil = URTEIL_ERWEITERT
    return urteil

def bedingung_erfuellt(bedingung, bedingungs_werte: dict[str, bool]) -> bool:
    """Ist die `bedingung` eines Feldes erfüllt? — **der eine Auswerter**.

    ⚠ **Kennt die weiche Sorte NICHT** und beantwortet deshalb nur die harte
    Frage. Wer wissen muss, ob ein Feld „erweitert" ist, ruft
    `bedingungs_urteil`; die Aufrufer hier brauchen die Unterscheidung nicht
    (sie fragen „ist diese eine Bedingung erfüllt?", nicht „zeige ich das
    Feld?").

    Eine Bedingung ist ein Schlüssel aus `_bedingungs_werte`, optional mit `!`
    negiert. **Mehrere Bedingungen stehen als Liste und gelten alle zusammen
    (UND)** — genau das braucht `strom_warmwasser_kwh` (B5/N-304): getrennte
    Strommessung ja, Split-Klimaanlage nein. Vorher war die Auswertung eine
    Kette aus `elif bedingung == "…"`; sie konnte eine Bedingung ausdrücken und
    keine zwei, und jeder neue Schlüssel kostete dort einen Zweig.

    ⚠ **Ein unbekannter Schlüssel zeigt das Feld** (fail-open) — bitgleich zum
    früheren Verhalten, wo eine unbekannte Zeichenkette durch alle `elif` fiel.
    Die Gegenrichtung wäre schlimmer: ein Tippfehler ließe ein **zugeordnetes**
    Feld unsichtbar verschwinden, und damit unlöschbar zurückbleiben (dieselbe
    Falle, vor der `get_alle_felder_fuer_investition` warnt). Ein Auswerter, der
    stattdessen wirft, wäre die F-59-Klasse: ein latenter 500er im Lesepfad.
    Gegen den Tippfehler steht deshalb ein Wächter, kein Laufzeitfehler —
    `test_b5_strom_warmwasser_luft_luft.py::
    test_jede_bedingung_der_registry_ist_ein_bekannter_schluessel`.
    """
    if not bedingung:
        return True
    tokens = (bedingung,) if isinstance(bedingung, str) else tuple(bedingung)
    for token in tokens:
        negiert = token.startswith("!")
        schluessel = token[1:] if negiert else token
        if schluessel not in bedingungs_werte:
            continue  # unbekannt → nicht filtern, s. Kasten oben
        if bedingungs_werte[schluessel] == negiert:
            return False
    return True

#: Welches Registry-Feld **ist** die Wärme-Achse. Die Namen kommen aus dem
#: Kanon (``core/betriebsmodus.py``) — kein zweites Vokabular für dieselbe
#: Sache, das war die Ursache von N-336.
#:
#: ⚠ **Die Wärme-Seite entscheidet, nicht die Strom-Seite:**
#: ``strom_heizen_kwh`` trägt zusätzlich die **harte** Bedingung
#: ``getrennte_strommessung`` und wäre an jedem Gerät ohne dieses Kennzeichen
#: „nein" — das ist eine Aussage über die *Messung*, nicht über die *Funktion*
#: des Geräts.
#:
#: ⛔ **``kuehlen`` steht hier nicht.** Kühlen ist keine Wärme-Achse; seine
#: Kennzahl hat einen eigenen Zähler (die **Kälte**menge) und eine eigene
#: Sperre (``arbeitszahl_kuehlen``).
_WP_ACHSEN_FELD: Final[dict] = {
    BM_HEIZEN: "heizenergie_kwh",
    BM_WARMWASSER: "warmwasser_kwh",
}

#: Beide Wärme-Achsen — der Default überall dort, wo die Frage nicht gestellt
#: wird (bitgleich zum Stand vor WK-16h). **Aus dem Kanon**, nicht aus der
#: Tabelle darüber: Die beiden müssen deckungsgleich sein, und ein Feld, das
#: hier fehlte, fiele so sofort auf (``assert`` darunter).
WP_WAERME_ACHSEN_BEIDE: Final[frozenset] = BM_WAERME_ACHSEN

assert frozenset(_WP_ACHSEN_FELD) == BM_WAERME_ACHSEN, (
    "Jede Wärme-Achse des Kanons braucht ihr Registry-Feld"
)

def wp_waerme_achsen(parameter: Optional[dict]) -> frozenset:
    """Welche Wärme-Achsen hat dieses Gerät? — **die eine Achsen-Frage** (WK-16h).

    Rückgabe ist eine Teilmenge von {@link WP_WAERME_ACHSEN_BEIDE}: eine
    **Brauchwasser**-Wärmepumpe trägt nur ``warmwasser``, eine
    **Split-Klimaanlage** nur ``heizen`` (N-304: kein Warmwasserkreis), jedes
    andere Gerät beide.

    ⭐ **Warum es diese Funktion gibt.** WK-15c hat die Regel *„eine Achse, die
    am Gerät nicht gilt, trägt in keiner Rechnung und keinem Hinweis eine Zahl"*
    für ROI-Schätzung, Formular und die SCOP/COP-Hinweise durchgesetzt — die
    **Kennzahlen je Gerät** kamen einen Tag später (WK-16ab) und kannten sie
    nicht. Gemessen an der r28 (15.09.2026): die Brauchwasser-WP *Stiebel WWK
    300* hatte eine Gesamt-Arbeitszahl von 3,31 und daneben zweimal den Strich
    *„Strom nicht getrennt je Funktion gemessen"* — einmal für die Achse, deren
    Zahl 3,31 **ist**, und einmal für eine Achse, die das Gerät nicht hat
    (N-499).

    ⚠ **`feld_urteil(...) == URTEIL_GILT` und NICHT
    {@link groesse_gibt_es_am_geraet}** — dieselbe Trennlinie wie in
    ``investitionen/roi.py::_achse_gilt`` (WK-15c) und
    ``daten_checker/stammdaten.py`` (WK-15b). Jene Funktion prüft
    ``!= URTEIL_NEIN`` und liefert an der Brauchwasser-WP für die Heiz-Achse
    ``True``, weil die Bedingung dort **weich** ist („untypisch, nicht
    unmöglich": wer doch einen kleinen Heizkreis hat, darf seinen Zähler
    behalten). Für den **Lesepfad einer gemessenen Menge** ist das richtig; für
    die Frage, welche Achse eine **Kennzahl** tragen darf, ist es zu weit.

    ⛔ **Sie entscheidet nichts über Abdeckung.** „Kein Zähler zugeordnet" und
    „das Gerät hat die Achse nicht" sind verschiedene Lagen — die erste gehört
    dem Daten-Checker, die zweite hierher (derselbe Kasten wie bei
    ``groesse_gibt_es_am_geraet``).
    """
    return frozenset(
        achse for achse, feld in _WP_ACHSEN_FELD.items()
        if feld_urteil("waermepumpe", feld, parameter) == URTEIL_GILT
    )

def groesse_gibt_es_am_geraet(
    typ: str, feld: str, parameter: Optional[dict],
) -> bool:
    """Kann dieses Gerät diese Größe überhaupt haben? — **für den LESEPFAD**.

    ``False`` heißt: die Größe existiert an diesem Gerät nicht (``URTEIL_NEIN``,
    die *harte* Sorte). Ein **erweitertes** Feld gilt hier als vorhanden — es
    ist untypisch, nicht unmöglich, und wer es gepflegt hat, meint es so.

    ⭐ **Warum es diese Funktion gibt: die Erfassung kannte die Regel, der
    Lesepfad nicht.** N-304 hat ``warmwasser_kwh`` an einer Split-Klimaanlage
    aus der Erfassung genommen, weil das Gerät keinen Warmwasserkreis hat —
    der Docstring von ``test_klima_ohne_warmwasser_n304.py`` benennt den Schaden
    wörtlich: *„Ein an einer Luft-Luft-Anlage gepflegter Warmwasser-Wert erzeugt
    eine Ersparnis für Wärme, die das Gerät nie erzeugt hat."* Ein **bereits
    gespeicherter** Wert erzeugte sie weiter: elf Faltstellen in sechs Dateien
    lesen ``warmwasser_kwh`` direkt aus ``verbrauch_daten``, und
    ``ist_luft_luft_waermepumpe`` kam in keiner davon vor. Gemeldet von
    dietmar1968 (T89667 #295) mit 889 kWh „Warmwasser" an einer Klimaanlage,
    daraus eine Gas-Ersparnis von 38 € und eine CO₂-Zahl von −112 kg.

    ⚠ **Vierte Runde der #236-Folgewellen-Klasse** (``ist-waerme-klima.md``
    §W-12 nennt N-304 selbst die dritte): *ein Filter auf einer Schicht reicht
    nicht, wenn mehrere Pfade dieselbe Größe lesen.* Deshalb steht hier eine
    Frage an die **bestehende** Registry und keine zweite Regel — wer morgen
    eine Bedingung ergänzt, bekommt den Lesepfad umsonst mit.

    ⚠ **Fail-open wie die beiden Auswerter darunter.** Ein unbekannter Typ oder
    ein unbekanntes Feld liefert ``True``: Im Lesepfad wäre die Gegenrichtung
    schlimmer als hier — ein Tippfehler ließe eine **gemessene** Menge still aus
    jeder Summe fallen. Gegen den Tippfehler steht der Wächter der Registry
    (``test_b5_strom_warmwasser_luft_luft.py``), nicht diese Funktion.

    ⛔ **Sie entscheidet NICHT über Abdeckung.** „Kein Zähler zugeordnet" und
    „das Gerät hat die Größe nicht" sind verschiedene Lagen — die erste gehört
    dem Daten-Checker, die zweite hierher. Wer diese Funktion für eine fehlende
    Messung benutzt, blendet gute Daten aus (Entscheid 29.08., Total-Fall).
    """
    for eintrag in INVESTITION_FELDER.get(typ) or ():
        if not isinstance(eintrag, dict) or eintrag.get("feld") != feld:
            continue
        urteil = bedingungs_urteil(
            eintrag.get("bedingung"), eintrag.get("weich"),
            _bedingungs_werte(parameter),
        )
        return urteil != URTEIL_NEIN
    return True

def _label_aufgeloest(feld: dict, bedingungs_werte: dict[str, bool]) -> str:
    """#281: konditionelles Label — nutzt dieselben Bedingungs-Keys wie `bedingung`."""
    for cond_key, alt_label in (feld.get("label_wenn") or {}).items():
        if bedingungs_werte.get(cond_key):
            return alt_label
    return feld["label"]
