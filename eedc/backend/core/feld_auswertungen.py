"""Wo ein zugeordnetes Feld **ausgewertet** wird — die eine Liste (WK-16f, R-A).

## Warum es diese Datei gibt

**Gernots Prinzip F-7 (14.09.2026):** *„Bitte achte auch darauf, dass alle
zugeordneten Sensoren in mindestens einer Auswertung verarbeitet werden, da man
sich anderenfalls die Frage stellt, wofür habe ich diesen Sensor zugeordnet."*

Eine Zuordnung ist ein **Versprechen an den Anwender**. Ein Feld, das die
Datenquellen-Fläche anbietet und das nirgends erscheint, bricht es still — und
still ist hier das Problem: Der Anwender sieht eine 0 oder einen Strich und
sucht den Fehler bei sich. Das ist dieselbe Klasse wie ADR-002/**P4** (*eine
unvollständige Antwort sagt es*), nur eine Ebene früher: Nicht die Zahl fehlt,
sondern jede Zahl.

**Der Anlass war N-398:** ``betriebsart_nutzenergie_heizen_kwh`` war seit dem
26.08.2026 zuordenbar (Registry-Feld, je Innengerät, auf der Fläche angeboten)
und hatte **keinen Leser**. Wer es pflegte, sah im Komponenten-Hub
``gesamt_heizenergie_kwh`` = 0 und dazu den **falschen** Grund *„kein
Wärmemengenzähler zugeordnet"*. Der Zähler war zugeordnet; eedc las ihn nur nie.

## Was hier steht — und was nicht

Je Registry-Feld (``typ``, ``feld``) die Liste der Stellen, die es
**auswerten**: eine **Sicht** (Cockpit · Komponenten · Auswertungen ·
Monatsbericht) oder ein **HA-Sensor/MQTT-Publish**.

⛔ **Daten-Checker und Vorschlags-Logik zählen NICHT als Auswertung.** Sie
*prüfen* einen Wert bzw. schlagen ihn zur Übernahme vor — beides beantwortet
die Frage des Anwenders („wofür habe ich das zugeordnet?") gerade nicht. Ein
Feld, das nur der Checker liest, ist ein Feld ohne Auswertung; es steht dann in
{@link FELDER_OHNE_AUSWERTUNG_BEKANNT} mit Begründung.

⚠ **Die Liste ist eine Behauptung — der Wächter misst sie.**
``test_jedes_feld_hat_eine_auswertung.py`` prüft drei Dinge: (1) jedes
Registry-Feld hat ≥ 1 Eintrag oder steht in der Ausnahmeliste, (2) jede genannte
Datei existiert und definiert das genannte Symbol, (3) der **Feldname** (oder
die in {@link Auswertung.ueber} genannten Trägertoken) kommt im Quelltext genau
dieser Funktion vor. *Ein Symbol, das das Feld nicht liest, ist kein Leser.*

⭐ **Warum ``ueber`` existiert und keine Bequemlichkeit ist.** Mehrere Leser sind
über einen Parameter generisch: ``betriebsart_nutzenergie_kwh(daten, modus)``
liest **jede** der vier Betriebsarten, je nachdem, womit man sie ruft. Würde der
Wächter „die Konstante ``BETRIEBSART_NUTZENERGIE_FELD`` kommt vor" als Beleg
nehmen, gälte jedes der vier Felder als ausgewertet, **obwohl nur Kühlen je
gerufen wurde** — genau der Blindfleck, gegen den diese Datei gebaut wird. Ein
Eintrag nennt deshalb den **Aufrufer** und darin beide Token: den Leser *und*
den Modus.

## Die Regel selbst

Sie steht im Konzept: ``docs/KONZEPT-WAERME-KLIMA.md`` Kap. 9.1, Punkt
**„Kein Feld ohne Auswertung" (R-A)**, Wächter-Zeile in Kap. 11.4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Optional

from backend.core.field_definitions import (
    BASIS_FELDER,
    BASIS_LIVE_FELDER,
    BASIS_PREIS_FELDER,
    BEDINGTE_BASIS_FELDER,
    INVESTITION_FELDER,
    LIVE_FELDER_INV,
    ZUSTAND_LIVE_FELDER,
    basis_feld_key,
)

__all__ = [
    "Auswertung",
    "FELD_AUSWERTUNGEN",
    "FELDER_OHNE_AUSWERTUNG_BEKANNT",
    "TYP_ANLAGE",
    "alle_registry_felder",
    "auswertungen_fuer",
    "sichten_fuer",
]

#: Der Typ-Schlüssel der Anlagen-Ebene. Er heißt ``basis`` und nicht ``anlage``,
#: weil die Datenquellen-Route ihre Einträge genau so beschriftet
#: (``build_expected_topics`` → ``"typ": "basis"``). Ein zweiter Name hier
#: müsste an der Route übersetzt werden — und eine Übersetzung ist eine Stelle,
#: an der etwas driften kann.
TYP_ANLAGE: Final[str] = "basis"


# =============================================================================
# Die Sicht-Namen — genau die, die der Anwender in der Navigation liest
# =============================================================================
#
# ⚠ **Konstanten statt Freitext.** Der Satz auf der Fläche lautet *„ausgewertet
# in: Cockpit → Monat · Komponenten → Wärmepumpe"*; er ist eine Wegbeschreibung
# und nur dann eine, wenn er die Menüpunkte wörtlich trifft. Frei getippt
# entstünden „Cockpit/Monat", „Cockpit → Monatsansicht" und „Monat" nebeneinander.

COCKPIT_LIVE: Final[str] = "Cockpit → Live"
COCKPIT_TAG: Final[str] = "Cockpit → Tag"
COCKPIT_MONAT: Final[str] = "Cockpit → Monat"
COCKPIT_JAHR: Final[str] = "Cockpit → Jahr"
COCKPIT_AUSSICHT: Final[str] = "Cockpit → Aussicht"
COCKPIT_ZAEHLERSTAENDE: Final[str] = "Cockpit → Zählerstände"

KOMP_PV: Final[str] = "Komponenten → PV-Module"
KOMP_SPEICHER: Final[str] = "Komponenten → Speicher"
KOMP_WP: Final[str] = "Komponenten → Wärmepumpe"
KOMP_EAUTO: Final[str] = "Komponenten → E-Auto"
KOMP_WALLBOX: Final[str] = "Komponenten → Wallbox"
KOMP_BKW: Final[str] = "Komponenten → Balkonkraftwerk"
KOMP_SONSTIGES: Final[str] = "Komponenten → Sonstiges"

AUSW_TABELLE: Final[str] = "Auswertungen → Tabelle"
AUSW_FINANZEN: Final[str] = "Auswertungen → Finanzen"
AUSW_CO2: Final[str] = "Auswertungen → CO₂"
AUSW_PROGNOSE: Final[str] = "Auswertungen → Prognose-vs-IST"

MONATSBERICHT: Final[str] = "Monatsbericht (PDF)"
JAHRESBERICHT: Final[str] = "Jahresbericht (PDF)"
HA_SENSOREN: Final[str] = "HA-Sensoren"


@dataclass(frozen=True)
class Auswertung:
    """**Eine** Stelle, die ein Feld auswertet — Sicht, Datei und Symbol.

    Args:
        sicht: Der Weg dorthin, wie er in der Navigation steht (Konstanten oben).
        datei: Pfad **relativ zu ``eedc/backend``** — derselbe Bezug, den die
            Wächter-Tabelle des Konzepts verwendet.
        symbol: Funktion, Methode oder Klasse in dieser Datei. Verschachtelte
            Namen mit Punkt (``get_aktueller_monat._wp_waerme_d1``).
        ueber: Optionale Trägertoken, wenn der Feldname im Quelltext des Symbols
            **nicht wörtlich** steht — etwa weil eine Lesetür oder ein
            modus-generischer Leger dazwischensteht. **Alle** Token müssen
            vorkommen; ``None`` heißt „der Feldname selbst steht da".
    """

    sicht: str
    datei: str
    symbol: str
    ueber: Optional[tuple[str, ...]] = None


def _a(sicht: str, datei: str, symbol: str, *ueber: str) -> Auswertung:
    """Kurzform für die Tabelle unten — ``ueber`` variadisch statt als Tupel."""
    return Auswertung(sicht, datei, symbol, ueber or None)


# =============================================================================
# Die Tabelle
# =============================================================================
#
# Gelesen als: *(Investitionstyp bzw. `basis`, Feldname) → wo es erscheint.*
# Der Feldname ist der **Basis**-Key: Ein Feld je Innengerät (`…-2`) wird über
# `basis_feld_key` auf seinen Basis-Key zurückgeführt, bevor hier gesucht wird —
# die Auswertung eines Innengeräte-Felds ist dieselbe wie die des Gerätefelds
# (`geraetefeld_oder_innengeraete`).

FELD_AUSWERTUNGEN: dict[tuple[str, str], tuple[Auswertung, ...]] = {

    # ── Anlagen-Ebene: Monatswerte ───────────────────────────────────────────
    (TYP_ANLAGE, "einspeisung_kwh"): (
        _a(COCKPIT_MONAT, "api/routes/aktueller_monat/__init__.py", "_berechne_monat"),
        _a(COCKPIT_JAHR, "api/routes/cockpit/uebersicht.py", "get_cockpit_uebersicht"),
        _a(AUSW_TABELLE, "api/routes/monatsdaten.py", "list_monatsdaten_aggregiert"),
        _a(HA_SENSOREN, "api/routes/ha_export/anlage_energie.py", "monatsfakten_und_energie"),
    ),
    (TYP_ANLAGE, "netzbezug_kwh"): (
        _a(COCKPIT_MONAT, "api/routes/aktueller_monat/__init__.py", "_berechne_monat"),
        _a(COCKPIT_JAHR, "api/routes/cockpit/uebersicht.py", "get_cockpit_uebersicht"),
        _a(AUSW_TABELLE, "api/routes/monatsdaten.py", "list_monatsdaten_aggregiert"),
        _a(HA_SENSOREN, "api/routes/ha_export/anlage_energie.py", "monatsfakten_und_energie"),
    ),
    (TYP_ANLAGE, "pv_gesamt_kwh"): (
        # ADR-002/**P7**: das Anlagen-Aggregat ist ausschliesslich EINGANG der
        # Modul-Aufloesung — es fuellt die Luecken der Module ohne eigenen Wert.
        _a(COCKPIT_TAG, "services/snapshot/komponenten_beitraege.py",
           "loese_pv_tageswerte_auf", "PV_AGGREGAT_BASIS_FELD"),
        _a(COCKPIT_MONAT, "services/snapshot/aggregator.py",
           "get_komponenten_tageskwh", "pv_gesamt"),
    ),
    (TYP_ANLAGE, "globalstrahlung_kwh_m2"): (
        _a(COCKPIT_AUSSICHT, "api/routes/aussichten/prognose.py", "get_langfrist_prognose"),
        _a(AUSW_TABELLE, "api/routes/monatsdaten.py", "MonatsdatenBase"),
    ),
    (TYP_ANLAGE, "sonnenstunden"): (
        _a(COCKPIT_AUSSICHT, "api/routes/aussichten/prognose.py", "get_kurzfrist_prognose"),
        _a(AUSW_TABELLE, "api/routes/monatsdaten.py", "MonatsdatenBase"),
    ),
    (TYP_ANLAGE, "durchschnittstemperatur"): (
        # E8 — kWh je Heizgradtag: die Monatsmitteltemperatur ist der Eingang.
        _a(KOMP_WP, "services/mitteltemperatur.py", "lade_monatsmittel_temperatur"),
        _a(AUSW_TABELLE, "api/routes/monatsdaten.py", "list_monatsdaten_aggregiert"),
    ),

    # ── Anlagen-Ebene: Preise je Monat (ADR-002/P8) ──────────────────────────
    (TYP_ANLAGE, "netzbezug_durchschnittspreis_cent"): (
        _a(COCKPIT_MONAT, "api/routes/aktueller_monat/__init__.py", "_berechne_monat"),
        # ADR-002/P8 — der wirksame Arbeitspreis DIESES Monats, nicht der heutige.
        _a(AUSW_FINANZEN, "services/strompreis_aggregator.py", "wirksamer_arbeitspreis_cent"),
    ),
    (TYP_ANLAGE, "einspeise_durchschnittspreis_cent"): (
        _a(AUSW_FINANZEN, "api/routes/strompreise.py", "resolve_einspeise_preis_cent"),
        _a(AUSW_TABELLE, "api/routes/monatsdaten.py", "list_monatsdaten_aggregiert"),
    ),
    (TYP_ANLAGE, "kraftstoffpreis_euro"): (
        _a(KOMP_EAUTO, "services/eauto_wirtschaftlichkeit.py", "berechne_eauto_ersparnis"),
        _a(COCKPIT_JAHR, "api/routes/cockpit/uebersicht.py", "get_cockpit_uebersicht"),
    ),
    (TYP_ANLAGE, "gaspreis_cent_kwh"): (
        _a(KOMP_WP, "services/wp_wirtschaftlichkeit.py", "berechne_wp_ersparnis"),
        _a(COCKPIT_MONAT, "api/routes/aktueller_monat/finanzen.py", "finanzen_des_monats"),
    ),
    (TYP_ANLAGE, "strompreis"): (
        # Der dynamische Börsenpreis — Live-Kachel und die stündliche Mitschrift,
        # aus der ADR-002/P8 den Monats-Ø bildet.
        _a(COCKPIT_LIVE, "api/routes/live_dashboard.py", "_endpreis_jetzt_cent"),
    ),

    # ── Anlagen-Ebene: Live ──────────────────────────────────────────────────
    (TYP_ANLAGE, "einspeisung_w"): (
        _a(COCKPIT_LIVE, "services/live_power_service.py", "LivePowerService._collect_values"),
        _a(COCKPIT_TAG, "services/live_tagesverlauf_service.py", "get_tagesverlauf"),
    ),
    (TYP_ANLAGE, "netzbezug_w"): (
        _a(COCKPIT_LIVE, "services/live_power_service.py", "LivePowerService._collect_values"),
        _a(COCKPIT_TAG, "services/live_tagesverlauf_service.py", "get_tagesverlauf"),
    ),
    (TYP_ANLAGE, "netz_kombi_w"): (
        _a(COCKPIT_LIVE, "services/live_power_service.py", "LivePowerService._collect_values"),
        _a(COCKPIT_TAG, "services/live_tagesverlauf_service.py", "get_tagesverlauf"),
    ),
    (TYP_ANLAGE, "pv_gesamt_w"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
        _a(COCKPIT_TAG, "services/live_tagesverlauf_service.py", "get_tagesverlauf"),
    ),
    (TYP_ANLAGE, "aussentemperatur_c"): (
        _a(COCKPIT_LIVE, "api/routes/live_wetter.py", "get_live_wetter"),
    ),

    # ── PV-Module ────────────────────────────────────────────────────────────
    ("pv-module", "pv_erzeugung_kwh"): (
        _a(KOMP_PV, "api/routes/cockpit/pv_strings.py", "_lade_ist_je_modul"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(HA_SENSOREN, "api/routes/ha_export/anlage_energie.py", "monatsfakten_und_energie"),
    ),
    ("pv-module", "leistung_w"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
    ),

    # ── Wechselrichter ───────────────────────────────────────────────────────
    # `pv_erzeugung_kwh` steht bewusst in FELDER_OHNE_AUSWERTUNG_BEKANNT.
    ("wechselrichter", "leistung_w"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
    ),

    # ── Speicher ─────────────────────────────────────────────────────────────
    ("speicher", "ladung_kwh"): (
        _a(KOMP_SPEICHER, "services/speicher_wirtschaftlichkeit.py", "berechne_ist_wirkungsgrad"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(HA_SENSOREN, "api/routes/ha_export/anlage_energie.py", "monatsfakten_und_energie"),
    ),
    ("speicher", "entladung_kwh"): (
        _a(KOMP_SPEICHER, "services/speicher_wirtschaftlichkeit.py", "berechne_ist_wirkungsgrad"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(HA_SENSOREN, "api/routes/ha_export/anlage_energie.py", "monatsfakten_und_energie"),
    ),
    ("speicher", "ladung_netz_kwh"): (
        # Arbitrage: Netzladung × Ladepreis gegen den Entladewert.
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag",
           "get_speicher_netzladung_kwh"),
        _a(KOMP_SPEICHER, "api/routes/investitionen/dashboard_speicher.py", "get_speicher_dashboard"),
    ),
    ("speicher", "speicher_ladepreis_cent"): (
        _a(KOMP_SPEICHER, "api/routes/investitionen/dashboard_speicher.py", "get_speicher_dashboard"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
    ),
    ("speicher", "leistung_w"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
    ),
    ("speicher", "soc"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
    ),

    # ── Wärmepumpe / Klima: Strom ────────────────────────────────────────────
    ("waermepumpe", "stromverbrauch_kwh"): (
        _a(KOMP_WP, "services/waermepumpe_kennzahlen_je_geraet.py", "mengen_aus_monatszeilen",
           "get_wp_strom_kwh"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag",
           "get_wp_strom_kwh"),
        _a(HA_SENSOREN, "api/routes/ha_export/investition_sensoren.py", "calculate_investition_sensors",
           "get_wp_strom_kwh"),
    ),
    ("waermepumpe", "strom_heizen_kwh"): (
        _a(KOMP_WP, "services/waermepumpe_kennzahlen_je_geraet.py", "mengen_aus_monatszeilen"),
        _a(COCKPIT_TAG, "services/energie_profil/waerme_verlauf.py", "lade_waerme_verlauf_beitraege"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
    ),
    ("waermepumpe", "strom_warmwasser_kwh"): (
        _a(KOMP_WP, "services/waermepumpe_kennzahlen_je_geraet.py", "mengen_aus_monatszeilen"),
        _a(COCKPIT_TAG, "services/energie_profil/waerme_verlauf.py", "lade_waerme_verlauf_beitraege"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
    ),

    # ── Wärmepumpe / Klima: Wärme (D1) ───────────────────────────────────────
    ("waermepumpe", "waerme_kwh"): (
        _a(KOMP_WP, "core/berechnungen/waermepumpe_kennzahl.py", "waerme_gesamt_kwh"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(HA_SENSOREN, "api/routes/ha_export/investition_sensoren.py", "calculate_investition_sensors"),
    ),
    ("waermepumpe", "heizenergie_kwh"): (
        _a(KOMP_WP, "core/berechnungen/waermepumpe_kennzahl.py", "heizwaerme_kwh"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag",
           "heizwaerme_kwh"),
        _a(AUSW_FINANZEN, "core/berechnungen/alternativkosten.py",
           "berechne_wp_alternativkosten_ersparnis", "heizwaerme_kwh"),
    ),
    ("waermepumpe", "warmwasser_kwh"): (
        _a(KOMP_WP, "services/waermepumpe_kennzahlen_je_geraet.py", "mengen_aus_monatszeilen",
           "get_wp_warmwasser_kwh"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag",
           "get_wp_warmwasser_kwh"),
    ),

    # ── Wärmepumpe / Klima: Betriebsart-Strom (#263 K-2, Teilmengen) ─────────
    #
    # ⚠ **Der Aufrufer, nicht die Lesetür** — `betriebsart_strom_kwh` ist über
    # `modus` generisch; erst `modus_strom_zeile` sagt, welche der vier
    # Betriebsarten wirklich gelesen wird (s. Modulkopf, `ueber`).
    ("waermepumpe", "betriebsart_strom_heizen_kwh"): (
        _a(KOMP_WP, "core/berechnungen/betriebsart_gemessen.py", "modus_strom_zeile",
           "betriebsart_strom_kwh", "HEIZEN"),
        _a(COCKPIT_TAG, "core/berechnungen/waerme_verteilung.py", "verteile_geraet_strom",
           "modus_heizen_kwh"),
    ),
    ("waermepumpe", "betriebsart_strom_kuehlen_kwh"): (
        _a(KOMP_WP, "core/berechnungen/betriebsart_gemessen.py", "modus_strom_zeile",
           "betriebsart_strom_kwh", "KUEHLEN"),
        _a(COCKPIT_TAG, "core/berechnungen/waerme_verteilung.py", "verteile_geraet_strom",
           "modus_kuehlen_kwh"),
    ),
    ("waermepumpe", "betriebsart_strom_lueften_kwh"): (
        _a(KOMP_WP, "core/berechnungen/betriebsart_gemessen.py", "modus_strom_zeile",
           "betriebsart_strom_kwh", "LUEFTEN"),
        _a(COCKPIT_TAG, "core/berechnungen/waerme_verteilung.py", "verteile_geraet_strom",
           "modus_lueften_kwh"),
    ),
    ("waermepumpe", "betriebsart_strom_entfeuchten_kwh"): (
        _a(KOMP_WP, "core/berechnungen/betriebsart_gemessen.py", "modus_strom_zeile",
           "betriebsart_strom_kwh", "ENTFEUCHTEN"),
        _a(COCKPIT_TAG, "core/berechnungen/waerme_verteilung.py", "verteile_geraet_strom",
           "modus_entfeuchten_kwh"),
    ),

    # ── Wärmepumpe / Klima: Betriebsart-Nutzenergie ──────────────────────────
    ("waermepumpe", "betriebsart_nutzenergie_heizen_kwh"): (
        # N-398, gebaut mit WK-16f: die Heizwärme des Betriebs trägt D1, wenn
        # kein Gerätefeld `heizenergie_kwh` dasteht.
        _a(KOMP_WP, "core/berechnungen/waermepumpe_kennzahl.py", "heizwaerme_kwh",
           "betriebsart_nutzenergie_kwh", "HEIZEN"),
    ),
    ("waermepumpe", "betriebsart_nutzenergie_kuehlen_kwh"): (
        _a(KOMP_WP, "services/waermepumpe_kennzahlen_je_geraet.py", "mengen_aus_monatszeilen",
           "betriebsart_nutzenergie_kwh", "KUEHLEN"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag",
           "betriebsart_nutzenergie_kwh", "KUEHLEN"),
    ),
    ("waermepumpe", "betriebsart_nutzenergie_lueften_kwh"): (
        # R-C: eine **Mengenzeile**, keine Kennzahl (E4 bleibt).
        _a(KOMP_WP, "core/berechnungen/betriebsart_gemessen.py",
           "nutzenergie_ohne_kennzahl_kwh", "betriebsart_nutzenergie_kwh", "LUEFTEN"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag",
           "nutzenergie_ohne_kennzahl_kwh", "wp_nutzenergie_lueften"),
    ),
    ("waermepumpe", "betriebsart_nutzenergie_entfeuchten_kwh"): (
        _a(KOMP_WP, "core/berechnungen/betriebsart_gemessen.py",
           "nutzenergie_ohne_kennzahl_kwh", "betriebsart_nutzenergie_kwh", "ENTFEUCHTEN"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag",
           "nutzenergie_ohne_kennzahl_kwh", "wp_nutzenergie_entfeuchten"),
    ),

    # ── Wärmepumpe / Klima: Live und Zustand ─────────────────────────────────
    ("waermepumpe", "leistung_w"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
    ),
    ("waermepumpe", "leistung_heizen_w"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
        _a(COCKPIT_TAG, "services/live_tagesverlauf_service.py", "_get_tagesverlauf_mqtt"),
    ),
    ("waermepumpe", "leistung_warmwasser_w"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
        _a(COCKPIT_TAG, "services/live_tagesverlauf_service.py", "_get_tagesverlauf_mqtt"),
    ),
    ("waermepumpe", "leistung_kuehlen_w"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
        _a(COCKPIT_TAG, "services/live_tagesverlauf_service.py", "_get_tagesverlauf_mqtt"),
    ),
    ("waermepumpe", "warmwasser_temperatur_c"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
    ),
    ("waermepumpe", "soll_temperatur_c"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "_innengeraete_live"),
    ),
    ("waermepumpe", "ist_temperatur_c"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "_innengeraete_live"),
    ),
    ("waermepumpe", "betriebsmodus"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
        _a(KOMP_WP, "services/betriebsmodus_live.py", "lade_betriebsmodus_live"),
    ),

    # ── Wärmepumpe: Counter (KUMULATIVE_COUNTER_FELDER) ──────────────────────
    ("waermepumpe", "wp_starts_anzahl"): (
        _a(KOMP_WP, "api/routes/investitionen/dashboard_waermepumpe.py", "get_waermepumpe_dashboard"),
        _a(JAHRESBERICHT, "services/pdf/builders/jahresbericht.py", "build_jahresbericht_context"),
    ),
    ("waermepumpe", "wp_betriebsstunden"): (
        _a(KOMP_WP, "api/routes/investitionen/dashboard_waermepumpe.py", "get_waermepumpe_dashboard"),
    ),

    # ── E-Auto ───────────────────────────────────────────────────────────────
    ("e-auto", "km_gefahren"): (
        _a(KOMP_EAUTO, "services/eauto_wirtschaftlichkeit.py", "berechne_eauto_ersparnis"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(HA_SENSOREN, "api/routes/ha_export/investition_sensoren.py", "calculate_investition_sensors"),
    ),
    ("e-auto", "verbrauch_kwh"): (
        _a(KOMP_EAUTO, "api/routes/investitionen/dashboard_eauto.py", "get_eauto_dashboard"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
    ),
    ("e-auto", "ladung_pv_kwh"): (
        _a(KOMP_EAUTO, "api/routes/investitionen/dashboard_eauto.py", "get_eauto_dashboard"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(COCKPIT_JAHR, "api/routes/cockpit/uebersicht.py", "get_cockpit_uebersicht"),
    ),
    ("e-auto", "ladung_netz_kwh"): (
        _a(KOMP_EAUTO, "api/routes/investitionen/dashboard_eauto.py", "get_eauto_dashboard"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(AUSW_FINANZEN, "core/berechnungen/dienstliche_ladekosten.py", "berechne_dienstliche_ladekosten"),
    ),
    # N-555 Stufe 2 (E5): „Heim: gesamt" — gelesen von der einen Funktion (Regel 2
    # Schritt 1), über sie von allen Sichten; am Tag über die Tagesauswahl.
    ("e-auto", "ladung_kwh"): (
        _a(KOMP_EAUTO, "api/routes/investitionen/dashboard_eauto.py", "get_eauto_dashboard"),
        _a(COCKPIT_MONAT, "services/eauto_wirtschaftlichkeit.py", "entscheide_emob_heimladung"),
        _a(COCKPIT_JAHR, "api/routes/cockpit/uebersicht.py", "get_cockpit_uebersicht"),
    ),
    ("e-auto", "ladung_extern_kwh"): (
        _a(KOMP_EAUTO, "api/routes/investitionen/dashboard_eauto.py", "get_eauto_dashboard"),
        _a(COCKPIT_MONAT, "api/routes/aktueller_monat/__init__.py", "_berechne_monat"),
    ),
    ("e-auto", "ladung_extern_euro"): (
        _a(KOMP_EAUTO, "api/routes/investitionen/dashboard_eauto.py", "get_eauto_dashboard"),
        _a(COCKPIT_JAHR, "api/routes/cockpit/uebersicht.py", "get_cockpit_uebersicht"),
    ),
    ("e-auto", "v2h_entladung_kwh"): (
        _a(KOMP_EAUTO, "api/routes/investitionen/dashboard_eauto.py", "get_eauto_dashboard"),
        _a(COCKPIT_JAHR, "api/routes/cockpit/uebersicht.py", "get_cockpit_uebersicht"),
        _a(HA_SENSOREN, "api/routes/ha_export/anlage_energie.py", "monatsfakten_und_energie"),
    ),
    ("e-auto", "leistung_w"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
    ),
    ("e-auto", "soc"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
    ),

    # ── Wallbox ──────────────────────────────────────────────────────────────
    ("wallbox", "ladung_kwh"): (
        _a(KOMP_WALLBOX, "api/routes/investitionen/dashboard_wallbox.py", "get_wallbox_dashboard"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
    ),
    ("wallbox", "ladung_pv_kwh"): (
        _a(KOMP_WALLBOX, "api/routes/investitionen/dashboard_wallbox.py", "get_wallbox_dashboard"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
    ),
    ("wallbox", "ladevorgaenge"): (
        _a(KOMP_WALLBOX, "api/routes/investitionen/dashboard_wallbox.py", "get_wallbox_dashboard"),
    ),
    ("wallbox", "leistung_w"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
    ),

    # ── Balkonkraftwerk ──────────────────────────────────────────────────────
    ("balkonkraftwerk", "pv_erzeugung_kwh"): (
        _a(KOMP_BKW, "api/routes/investitionen/dashboard_balkonkraftwerk.py", "get_balkonkraftwerk_dashboard"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag",
           "get_pv_erzeugung_kwh"),
    ),
    ("balkonkraftwerk", "eigenverbrauch_kwh"): (
        _a(KOMP_BKW, "api/routes/investitionen/dashboard_balkonkraftwerk.py", "get_balkonkraftwerk_dashboard"),
        _a(AUSW_FINANZEN, "core/berechnungen/bkw_finanz.py", "bkw_finanz_beitrag"),
    ),
    ("balkonkraftwerk", "speicher_ladung_kwh"): (
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(KOMP_BKW, "api/routes/investitionen/dashboard_balkonkraftwerk.py", "get_balkonkraftwerk_dashboard"),
    ),
    ("balkonkraftwerk", "speicher_entladung_kwh"): (
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(KOMP_BKW, "api/routes/investitionen/dashboard_balkonkraftwerk.py", "get_balkonkraftwerk_dashboard"),
    ),
    ("balkonkraftwerk", "leistung_w"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
    ),

    # ── Sonstiges ────────────────────────────────────────────────────────────
    ("sonstiges", "erzeugung_kwh"): (
        _a(KOMP_SONSTIGES, "api/routes/investitionen/dashboard_sonstiges.py", "get_sonstiges_dashboard"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
    ),
    ("sonstiges", "eigenverbrauch_kwh"): (
        _a(KOMP_SONSTIGES, "api/routes/investitionen/dashboard_sonstiges.py", "get_sonstiges_dashboard"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
    ),
    ("sonstiges", "einspeisung_kwh"): (
        _a(KOMP_SONSTIGES, "api/routes/investitionen/dashboard_sonstiges.py", "get_sonstiges_dashboard"),
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
    ),
    ("sonstiges", "einspeise_erloes_euro"): (
        _a(AUSW_FINANZEN, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(KOMP_SONSTIGES, "api/routes/investitionen/dashboard_sonstiges.py", "get_sonstiges_dashboard"),
    ),
    ("sonstiges", "verbrauch_sonstig_kwh"): (
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag",
           "get_sonstiges_verbrauch_kwh"),
        _a(KOMP_SONSTIGES, "api/routes/investitionen/dashboard_sonstiges.py", "get_sonstiges_dashboard",
           "get_sonstiges_verbrauch_kwh"),
    ),
    ("sonstiges", "bezug_pv_kwh"): (
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(KOMP_SONSTIGES, "api/routes/investitionen/dashboard_sonstiges.py", "get_sonstiges_dashboard"),
    ),
    ("sonstiges", "bezug_netz_kwh"): (
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(KOMP_SONSTIGES, "api/routes/investitionen/dashboard_sonstiges.py", "get_sonstiges_dashboard"),
    ),
    ("sonstiges", "abgabe_kwh"): (
        _a(COCKPIT_MONAT, "core/berechnungen/imd_monatsaggregat.py", "imd_typ_beitrag"),
        _a(COCKPIT_JAHR, "api/routes/cockpit/uebersicht.py", "get_cockpit_uebersicht"),
    ),
    ("sonstiges", "zaehlerstand"): (
        _a(COCKPIT_ZAEHLERSTAENDE, "services/zaehlerstaende.py", "_gepflegte_monatsstaende",
           "ZAEHLERSTAND_FELD"),
    ),
    ("sonstiges", "leistung_w"): (
        _a(COCKPIT_LIVE, "services/live_komponenten_builder.py", "build_komponenten"),
    ),
}


#: Felder, die heute **keine** Auswertung haben — mit Begründung, nicht als
#: Lücke im Schweigen.
#:
#: ⛔ **Bauform wie ``P10_NOCH_NICHT_MIGRIERT``: Die Liste darf nicht wachsen.**
#: Der Wächter prüft ihre Länge gegen die Obergrenze; wer ein Feld hinzufügt,
#: hebt sie bewusst und trägt die Begründung ein. Jeder Eintrag ist zugleich ein
#: Nebenfund für den Master — hier steht der Sachverhalt, nicht die Lösung.
#:
#: ⚠ **Baseline 0 für Wärme/Klima** (``waermepumpe``): Diese Fläche hat keinen
#: Gegenprüfer (Konzept Kap. 11.6), deshalb gilt dort kein „noch nicht".
FELDER_OHNE_AUSWERTUNG_BEKANNT: dict[tuple[str, str], str] = {
    ("wechselrichter", "pv_erzeugung_kwh"): (
        "Der Wechselrichter ist KEIN PV-Erzeuger (Entscheid Gernot 24.08.2026). "
        "Das Monatsfeld steht nur noch als `nur_manuell` in der Registry, damit "
        "eine BESTEHENDE Zuordnung sichtbar und entfernbar bleibt; "
        "`imd_typ_beitrag` hat für diesen Typ bewusst keinen Zweig. Wer den Wert "
        "pflegt, sieht ihn nirgends — das ist der gewollte Rückbau, aber die "
        "Fläche sagt es heute nicht."
    ),
    ("e-auto", "km_stand"): (
        "Der Tachostand (#407, 8ear) ist `nur_manuell` und steht deshalb nicht "
        "auf der Datenquellen-Fläche. Ausgewertet wird die **Differenz** als "
        "Vorschlag für `km_gefahren` (`services/vorschlag_service.py`) — und ein "
        "Vorschlag ist nach R-A keine Auswertung. Die gefahrenen Kilometer haben "
        "ihre Sichten; der Stand selbst erscheint nur in der CSV-Spalte "
        "`Tachostand`."
    ),
}

#: Obergrenze für die Liste darüber — sie darf **schrumpfen**, nicht wachsen.
FELDER_OHNE_AUSWERTUNG_MAX: Final[int] = 2


# =============================================================================
# Zugriff
# =============================================================================

def alle_registry_felder() -> set[tuple[str, str]]:
    """Die Referenzmenge des Wächters: **jedes** zuordenbare Registry-Feld.

    ⚠ **Abgeleitet, nicht getippt** — die Menge entsteht aus den Registries
    selbst. Ein neues Feld erscheint dadurch am Tag seiner Einführung im
    Wächter, ohne dass jemand daran denken muss; genau das ist der Unterschied
    zwischen einem Wächter und einer Gedächtnisstütze.

    ⛔ **Was NICHT enthalten ist, und warum:**

    * ``OPTIONALE_FELDER`` (Sonderkosten, Beschreibung, Notizen) — reine
      Handeingaben ohne Quelle; sie stehen nie auf der Zuordnungs-Fläche, die
      Frage „wofür habe ich das zugeordnet?" stellt sich für sie nicht.
    * ``kumulative_zaehler_felder_je_typ()`` — es ist aus
      ``INVESTITION_FELDER`` **abgeleitet** und fügt nur die
      Kompatibilitäts-Aliase aus ``_SNAPSHOT_KOMPATIBILITAET`` hinzu
      (``wallbox/ladung_netz_kwh``, ``sonstiges/verbrauch_kwh``). Ein Alias ist
      ein zweiter Name für einen Wert, kein zweites Feld — er wird nirgends
      angeboten und braucht keine eigene Auswertung.
    * ``STAND_FELDER`` — ebenfalls abgeleitet (Marker ``stand: True`` in
      ``INVESTITION_FELDER``) und damit bereits enthalten.
    """
    felder: set[tuple[str, str]] = set()
    for typ, eintraege in INVESTITION_FELDER.items():
        listen = list(eintraege.values()) if isinstance(eintraege, dict) else [eintraege]
        for liste in listen:
            for f in liste:
                felder.add((typ, f["feld"]))
    for typ, eintraege in LIVE_FELDER_INV.items():
        for f in eintraege:
            felder.add((typ, f["key"]))
    for f in BASIS_FELDER:
        felder.add((TYP_ANLAGE, f["feld"]))
    for f in BEDINGTE_BASIS_FELDER:
        felder.add((TYP_ANLAGE, f["feld"]))
    for f in BASIS_LIVE_FELDER:
        felder.add((TYP_ANLAGE, f["key"]))
    for f in BASIS_PREIS_FELDER:
        felder.add((TYP_ANLAGE, f["key"]))
    felder |= set(ZUSTAND_LIVE_FELDER)
    # ⭐ **Die vierte Registry, und sie wäre fast durchgefallen.** Die
    # Zählerstände der Anlage (``pv_gesamt_kwh`` · ``einspeisung_kwh`` ·
    # ``netzbezug_kwh``) stehen **nicht** in ``BASIS_FELDER``, sondern in
    # ``mqtt_topic_registry.BASIS_ENERGY_TOPICS`` — und die Fläche bietet sie
    # an. Gemessen am 14.09.2026: ``pv_gesamt_kwh`` fiel bei der ersten Fassung
    # dieser Funktion durch, obwohl es der Anlagen-PV-Zähler ist (P7).
    # *Eine Referenzmenge ist nur so vollständig wie die Registries, die sie
    # kennt.*
    from backend.services.mqtt_topic_registry import BASIS_ENERGY_TOPICS
    for key, *_rest in BASIS_ENERGY_TOPICS:
        felder.add((TYP_ANLAGE, key))
    # Kompressor-Starts und Betriebsstunden: eigene Liste, weil sie keine
    # kWh-Semantik haben (s. `snapshot/keys.py`). Lokaler Import — `services`
    # darf `core` lesen, nicht umgekehrt.
    from backend.services.snapshot.keys import KUMULATIVE_COUNTER_FELDER
    for typ, namen in KUMULATIVE_COUNTER_FELDER.items():
        for name in namen:
            felder.add((typ, name))
    return felder


def auswertungen_fuer(typ: Optional[str], feld: Optional[str]) -> tuple[Auswertung, ...]:
    """Die Auswertungen eines Feldes — leer, wenn es keine gibt.

    ``feld`` darf das Innengeräte-Suffix tragen (``…-2``); es wird über
    ``basis_feld_key`` aufgelöst. Ein Innengeräte-Feld hat keine eigene
    Auswertung: Es ist die Aufschlüsselung des Gerätefelds und wird von
    derselben Stelle gelesen (``geraetefeld_oder_innengeraete``).
    """
    if not typ or not feld:
        return ()
    return FELD_AUSWERTUNGEN.get((typ, basis_feld_key(feld)), ())


def sichten_fuer(typ: Optional[str], feld: Optional[str]) -> list[str]:
    """Die Sicht-Namen eines Feldes, ohne Dubletten, in Tabellen-Reihenfolge.

    Das ist die Form, die die Datenquellen-Route ausliefert (``ausgewertet_in``)
    — **eine** Quelle, kein zweiter Turm: Der Client bekommt fertige Sätze und
    hält keine eigene Tabelle.
    """
    gesehen: list[str] = []
    for a in auswertungen_fuer(typ, feld):
        if a.sicht not in gesehen:
            gesehen.append(a.sicht)
    return gesehen
