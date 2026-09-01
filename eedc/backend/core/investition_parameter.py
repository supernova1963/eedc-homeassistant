"""
Single Source of Truth für die Schlüssel im `parameter`-JSON-Feld
jeder Investition.

Hintergrund: das `parameter`-Feld auf einer Investition ist ein unstrukturiertes
JSON. Über mehrere Iterationen sind Schlüsselnamen zwischen Form, Wizard und
Backend-Lese-Code gedriftet. Die damalige Inventur liegt unter
`docs/archive/INVENTUR-INVESTITIONS-PARAMETER.md` (versioniert; der Kommentar
behauptete bis 2026-07-28 fälschlich, sie sei nicht mehr vorhanden). Was von ihr
trägt, steht als Ergebnis in diesem Modul, in der Migration
`core/database.py::_migrate_investitionen_parameter_keys_v325` und im CHANGELOG
zu v3.25.0.

Dieses Modul macht die Keys statisch typisiert + auffindbar:
  - `PARAM_<TYP>` exportiert die kanonischen Schlüsselnamen pro Investitions-Typ
  - `PARAM_<TYP>_DEFAULTS` exportiert die Default-Werte (gemeinsam für Frontend
    und Backend, damit Default-Drift wie #7 in der Inventur nicht entsteht)

Das Frontend-Pendant lebt unter
  eedc/frontend/src/lib/investitionParameter.ts

Verwendung im Backend:

    from core.investition_parameter import PARAM_SPEICHER, PARAM_SPEICHER_DEFAULTS

    kapazitaet = inv.parameter.get(PARAM_SPEICHER["KAPAZITAET_KWH"], 0)
    arbitrage = inv.parameter.get(
        PARAM_SPEICHER["ARBITRAGE_FAEHIG"],
        PARAM_SPEICHER_DEFAULTS["arbitrage_faehig"],
    )
"""

from typing import Final, Optional


# ============================================================================
# E-Auto
# ============================================================================

PARAM_E_AUTO: Final[dict[str, str]] = {
    "BATTERIE_KAPAZITAET_KWH": "batteriekapazitaet_kwh",
    "VERBRAUCH_KWH_100KM": "verbrauch_kwh_100km",
    "JAHRESFAHRLEISTUNG_KM": "jahresfahrleistung_km",
    "PV_LADEANTEIL_PROZENT": "pv_ladeanteil_prozent",
    "VERGLEICH_VERBRAUCH_L_100KM": "vergleich_verbrauch_l_100km",
    # #331 (PHEV): der REAL getankte Verbrauch des Fahrzeugs — nicht zu
    # verwechseln mit `vergleich_verbrauch_l_100km` darüber, das den FIKTIVEN
    # Vergleichs-Benziner beschreibt und sieben Produktions-Leser hat. Zwei
    # Bedeutungen brauchen zwei Felder (Entscheidung 2, KONZEPT-WALLBOX-EAUTO
    # Phase 4); eine Umdeutung des Vergleichsfelds hätte Zahlen bei allen
    # Nicht-PHEV-Nutzern bewegt.
    #
    # ⚠ **Das gesetzte Feld IST die Aussage** (Entscheidung 3): ist es > 0, hat
    # das Fahrzeug einen Verbrenner; fehlt es, ist es ein BEV und jede Zahl
    # bleibt exakt wie vorher. Deshalb steht es bewusst NICHT in
    # `PARAM_E_AUTO_DEFAULTS` — ein Default würde genau die Aussage zerstören,
    # die es trägt, und aus jedem Bestands-BEV einen Hybrid machen.
    "EIGENER_VERBRAUCH_L_100KM": "eigener_verbrauch_l_100km",
    # #331: geschätzter elektrischer Fahranteil (0–100). Fallback für die
    # Prognose-Achse, die keine Messung hat, und für ein IST ohne gepflegten
    # Fahrverbrauch. Ebenfalls **ohne Default** — ein erfundener Richtwert wäre
    # eine Behauptung über ein fremdes Fahrzeug (Entscheidung 4).
    "ELEKTRISCHER_FAHRANTEIL_PROZENT": "elektrischer_fahranteil_prozent",
    "BENZINPREIS_EURO": "benzinpreis_euro",
    "V2H_FAEHIG": "v2h_faehig",
    "V2H_ENTLADELEISTUNG_KW": "v2h_entladeleistung_kw",
    "V2H_ENTLADE_PREIS_CENT": "v2h_entlade_preis_cent",
    "V2H_ENTLADUNG_KWH_JAHR": "v2h_entladung_kwh_jahr",
    "IST_DIENSTLICH": "ist_dienstlich",
    "ALTERNATIV_KOSTEN_EURO": "alternativ_kosten_euro",
}

PARAM_E_AUTO_DEFAULTS: Final[dict[str, object]] = {
    "verbrauch_kwh_100km": 18,
    "jahresfahrleistung_km": 15000,
    "pv_ladeanteil_prozent": 60,
    "vergleich_verbrauch_l_100km": 7.5,
    "benzinpreis_euro": 1.65,
    "v2h_faehig": False,
    "ist_dienstlich": False,
}


# ============================================================================
# Speicher
# ============================================================================

PARAM_SPEICHER: Final[dict[str, str]] = {
    "KAPAZITAET_KWH": "kapazitaet_kwh",
    "NUTZBARE_KAPAZITAET_KWH": "nutzbare_kapazitaet_kwh",
    "MAX_LADELEISTUNG_KW": "max_ladeleistung_kw",
    "MAX_ENTLADELEISTUNG_KW": "max_entladeleistung_kw",
    "WIRKUNGSGRAD_PROZENT": "wirkungsgrad_prozent",
    "LAEDT_AUS_NETZ": "laedt_aus_netz",
    "ARBITRAGE_FAEHIG": "arbitrage_faehig",
    "LADE_DURCHSCHNITTSPREIS_CENT": "lade_durchschnittspreis_cent",
    "ENTLADE_VERMIEDENER_PREIS_CENT": "entlade_vermiedener_preis_cent",
    # #351: die Kopplung als eigene Eigenschaft. **Fehlt der Schlüssel, ist das
    # kein Defekt**, sondern der Normalfall „nicht gepflegt" — aufgelöst wird er
    # dann aus der Wechselrichter-Zuordnung (s. `get_speicher_kopplung`). Ein
    # Default in `PARAM_SPEICHER_DEFAULTS` wäre hier falsch: er würde die
    # Ableitung zur gespeicherten Wahrheit machen und beide Konstellationen des
    # Issues wieder unerreichbar (AC-Speicher am Hybrid-WR · DC-Speicher ohne
    # erfassten WR).
    "KOPPLUNG": "kopplung",
}

# Erlaubte Werte von `kopplung` (#351). `None`/fehlend = „aus der Zuordnung
# ableiten"; ein drittes gespeichertes „unbekannt" gibt es bewusst nicht — die
# Anzeige soll nie „unbekannt" sagen müssen, sie hat immer eine Auflösung.
SPEICHER_KOPPLUNG_AC: Final[str] = "ac"
SPEICHER_KOPPLUNG_DC: Final[str] = "dc"
SPEICHER_KOPPLUNG_WERTE: Final[tuple[str, ...]] = (
    SPEICHER_KOPPLUNG_AC,
    SPEICHER_KOPPLUNG_DC,
)

PARAM_SPEICHER_DEFAULTS: Final[dict[str, object]] = {
    "wirkungsgrad_prozent": 95,
    "laedt_aus_netz": False,
    "arbitrage_faehig": False,
    "lade_durchschnittspreis_cent": 12,
    "entlade_vermiedener_preis_cent": 35,
}


# ============================================================================
# Wärmepumpe
# ============================================================================

PARAM_WAERMEPUMPE: Final[dict[str, str]] = {
    "LEISTUNG_KW": "leistung_kw",
    "WP_ART": "wp_art",
    "EFFIZIENZ_MODUS": "effizienz_modus",
    "JAZ": "jaz",
    "SCOP_HEIZUNG": "scop_heizung",
    "SCOP_WARMWASSER": "scop_warmwasser",
    "VORLAUFTEMPERATUR": "vorlauftemperatur",
    "COP_HEIZUNG": "cop_heizung",
    "COP_WARMWASSER": "cop_warmwasser",
    "GETRENNTE_STROMMESSUNG": "getrennte_strommessung",
    "HEIZWAERMEBEDARF_KWH": "heizwaermebedarf_kwh",
    "WARMWASSERBEDARF_KWH": "warmwasserbedarf_kwh",
    "WAERMEBEDARF_KWH": "waermebedarf_kwh",
    "PV_ANTEIL_PROZENT": "pv_anteil_prozent",
    "ALTER_ENERGIETRAEGER": "alter_energietraeger",
    "ALTER_PREIS_CENT_KWH": "alter_preis_cent_kwh",
    "ALTERNATIV_ZUSATZKOSTEN_JAHR": "alternativ_zusatzkosten_jahr",
    "ALTERNATIV_KOSTEN_EURO": "alternativ_kosten_euro",
    "SG_READY": "sg_ready",
    "INNENGERAETE": "innengeraete",
    # ── R2 (SOLL Wärme/Klima §3.2b) — was der Anwender über die ABGRENZUNG sagt ──
    #
    # Zwei Lagen, ein Feld, zwei Vorzeichen: Auf dem Stromzähler liegt ein
    # fremder Erzeuger, dessen Wärme fehlt (Fall H-C ⇒ E zu groß), oder am
    # Wärmemengenzähler hängt ein fremder Erzeuger, dessen Aufwand fehlt
    # (bivalent, F12 ⇒ Q zu groß). Beides ist von außen **unsichtbar** — anders
    # als „mehrere Geräte, nur eines meldet Wärme", das eedc aus den Daten selbst
    # erkennt (`WpFakten.waerme_deckt_nicht_alle_geraete`).
    #
    # ⚠ **Ein Feld und nicht zwei Kennzeichen**, weil R2 EINE Regel ist. Ein Flag
    # je Beispiel hätte die Fallsammlung in den Code geholt — genau die Bauform,
    # die den bivalenten Fall bis zum 26.08.2026 unsichtbar gelassen hat.
    "ABGRENZUNG": "abgrenzung",
    # Aktiv oder passiv gekühlt (SOLL §4.1/§7 A5). **Keine Menge, eine
    # Markierung:** Passive Kühlung läuft nur über Umwälzpumpen, ihr EER liegt
    # um ein Vielfaches über dem einer aktiv gekühlten Anlage. Die Kennzahl ist
    # dort korrekt — ein VERGLEICH gegen aktiv gekühlte Anlagen wäre die
    # Falschaussage, im Community-Benchmark ebenso wie in eedc selbst.
    "KUEHLUNG_ART": "kuehlung_art",
}

PARAM_WAERMEPUMPE_DEFAULTS: Final[dict[str, object]] = {
    "wp_art": "luft_wasser",
    # Leer heißt „keine bekannte Abweichung" — nicht „geprüft und in Ordnung".
    "abgrenzung": "",
    "kuehlung_art": "keine",
    "effizienz_modus": "gesamt_jaz",
    "jaz": 3.5,
    "scop_heizung": 4.5,
    "scop_warmwasser": 3.2,
    "vorlauftemperatur": "35",
    "cop_heizung": 3.9,
    "cop_warmwasser": 3.0,
    "getrennte_strommessung": False,
    "heizwaermebedarf_kwh": 12000,
    "warmwasserbedarf_kwh": 3000,
    "pv_anteil_prozent": 30,
    "alter_energietraeger": "gas",
    # Inventur Bug #7: aussichten.py + ha_export.py:241 hatten 10.0,
    # alle anderen 12.0. Vereinheitlicht auf 12.0 — typischer Gas-Endkundenpreis.
    "alter_preis_cent_kwh": 12,
    "alternativ_zusatzkosten_jahr": 0,
    "sg_ready": False,
}


# ============================================================================
# Wallbox
# ============================================================================

PARAM_WALLBOX: Final[dict[str, str]] = {
    "MAX_LADELEISTUNG_KW": "max_ladeleistung_kw",
    "BIDIREKTIONAL": "bidirektional",
    "PV_OPTIMIERT": "pv_optimiert",
    "IST_DIENSTLICH": "ist_dienstlich",
}

PARAM_WALLBOX_DEFAULTS: Final[dict[str, object]] = {
    "max_ladeleistung_kw": 11,
    "bidirektional": False,
    "pv_optimiert": True,
    "ist_dienstlich": False,
}


# ============================================================================
# Wechselrichter
# ============================================================================

# N-175/N-231: `wirkungsgrad_prozent` und `hybrid` sind hier bis 2026-09-01
# mitgefuehrt worden, ohne dass eine einzige Zeile sie gelesen haette — erfasst
# im Formular, leseseitig tot. Ein Formularfeld ohne Wirkung ist ein Versprechen,
# deshalb sind beide entfernt statt weiter angeboten. Bestandsdaten im
# `parameter`-JSON bleiben unberuehrt; sie waren schon vorher wirkungslos.
# `MAX_LEISTUNG_KW` wird gelesen (`investition_kennwerte.py`, Setup-Wizard) und bleibt.
PARAM_WECHSELRICHTER: Final[dict[str, str]] = {
    "MAX_LEISTUNG_KW": "max_leistung_kw",
}


# ============================================================================
# PV-Module
# ============================================================================

PARAM_PV_MODULE: Final[dict[str, str]] = {
    "ANZAHL_MODULE": "anzahl_module",
    "MODUL_LEISTUNG_WP": "modul_leistung_wp",
    "MODUL_TYP": "modul_typ",
    "AUSRICHTUNG_GRAD": "ausrichtung_grad",
    # Nennleistung: SoT ist die SPALTE `Investition.leistung_kwp`. Dieser
    # Schlüssel ist ausschließlich LESE-Fallback für Bestands- und Importdaten
    # (#229/N52/N66) — kein Schreibpfad erzeugt ihn (Formular und Setup-Wizard
    # schreiben die Spalte). Gelesen wird er NUR über
    # `core/investition_kennwerte.py` bzw. `utils/investition_value.py`, nie als
    # Literal. Der ältere Schreibweise-Variante `kwp` steht in LEGACY_PARAM_KEYS
    # und wird dort ebenfalls noch gelesen.
    #
    # ACHTUNG, die Spalte trägt NICHT überall kWp: `Investition.leistung_kwp`
    # ist ein Mehrzweckfeld — für `speicher` steht dort kWh, für
    # `wechselrichter` kW (AC), erst für den Rest kWp
    # (`services/pdf/templates/jahresbericht.html:30-33` rendert genau diese
    # drei Einheiten aus demselben Feld). Eine Regel „`leistung_kwp` ist die
    # PV-Nennleistung" gilt deshalb nur typgefiltert.
    "LEISTUNG_KWP": "leistung_kwp",
}


# ============================================================================
# Balkonkraftwerk
# ============================================================================

PARAM_BALKONKRAFTWERK: Final[dict[str, str]] = {
    "LEISTUNG_WP": "leistung_wp",
    "ANZAHL": "anzahl",
    "AUSRICHTUNG": "ausrichtung",
    "NEIGUNG_GRAD": "neigung_grad",
    "HAT_SPEICHER": "hat_speicher",
    "SPEICHER_KAPAZITAET_WH": "speicher_kapazitaet_wh",
    # AC-Grenze des BKW-Wechselrichters in Watt (#347, Rainer). Ein BKW ist
    # regelmäßig überbelegt — 3 × 420 Wp an einem 600-W-Wechselrichter —, und
    # ohne diese Grenze prognostiziert eedc die volle Modulleistung. Gelesen
    # NUR über `core/investition_kennwerte.get_wr_grenze_kw`; die Kappung ist
    # eine STÜNDLICHE (die Mittagsspitze wird gekappt, die Randstunden nicht),
    # deshalb steht sie im Kanon-Pfad und nicht als kWp-Deckel.
    # Optional: fehlt der Wert, wird nicht gekappt.
    "WECHSELRICHTER_LEISTUNG_W": "wechselrichter_leistung_w",
}

# Typische AC-Einspeisegrenze eines Balkonkraftwerks in Watt (seit 2024 in DE
# 800 W, davor 600 W). **Kein Lese-Default** — es wird nie damit gerechnet.
# Der Daten-Checker nutzt sie als Schwelle: liegt die Modulleistung darüber und
# ist keine Wechselrichter-Leistung gepflegt, ist Überbelegung so wahrscheinlich,
# dass die ungekappte Prognose gemeldet gehört (#347). Darunter lohnt der
# Hinweis nicht — die Abweichung wäre bestenfalls marginal.
BKW_EINSPEISEGRENZE_W_TYPISCH: Final[int] = 800


PARAM_BALKONKRAFTWERK_DEFAULTS: Final[dict[str, object]] = {
    # Formular-VORBELEGUNG (typisches BKW = 2 Module), KEIN Lese-Default.
    # Wer `anzahl` nie gepflegt hat, darf beim LESEN nicht stillschweigend die
    # doppelte Leistung ausgewiesen bekommen — `get_bkw_kwp` rechnet deshalb
    # mit 1 (s. `core/investition_kennwerte.py::ANZAHL_LESE_DEFAULT`).
    "anzahl": 2,
    "ausrichtung": "Süd",
    "neigung_grad": 30,
    "hat_speicher": False,
}


# ============================================================================
# Sonstiges
# ============================================================================

PARAM_SONSTIGES: Final[dict[str, str]] = {
    "KATEGORIE": "kategorie",
    "BESCHREIBUNG": "beschreibung",
    # #377 — nur für die Kategorie `zaehler`. Beide sind reine
    # **Anzeige**-Angaben und gehen in keine Rechnung ein: `ZAEHLER_ART`
    # bestimmt Label und Symbol, `ZAEHLER_EINHEIT` die Einheit, die neben dem
    # Zählerstand steht. Der Wert selbst bleibt einheitenlos (s.
    # `field_definitions.INVESTITION_FELDER["sonstiges"]["zaehler"]`).
    "ZAEHLER_ART": "zaehler_art",
    "ZAEHLER_EINHEIT": "zaehler_einheit",
}

PARAM_SONSTIGES_DEFAULTS: Final[dict[str, object]] = {
    "kategorie": "erzeuger",
    "zaehler_art": "gas",
    # ⚠ Der Default ist eine ANZEIGE-Vorbelegung, keine Umrechnung. eedc
    # rechnet Zählerstände nie um; wer m³ auf kWh stellt, ändert das Wort neben
    # der Zahl und sonst nichts.
    "zaehler_einheit": "m³",
}

#: Auswahl für `zaehler_art` — Label und Symbol, sonst ohne Wirkung (#377).
ZAEHLER_ARTEN: Final[tuple[str, ...]] = (
    "gas", "wasser", "heizoel", "pellets", "fluessiggas", "sonstiges",
)

#: Auswahl für `zaehler_einheit` — steht neben der Zahl, wird nie umgerechnet.
ZAEHLER_EINHEITEN: Final[tuple[str, ...]] = ("m³", "l", "kg", "t", "kWh")


# ============================================================================
# Legacy-Keys (deprecated, aber Migrations-Code muss sie weiter erkennen)
# ============================================================================

# Als Konstante, weil dieser eine Legacy-Key zur Laufzeit gelesen wird und der
# Lese-Helper ihn nicht als Literal wiederholen soll.
LEGACY_KWP_KEY: Final[str] = "kwp"

# In v3.25.0 entstandene Migration: Diese alten Keys werden in der
# DB-Migration auf die neuen Schlüssel umgeschrieben. Geschrieben werden darf
# hier keiner mehr.
#
# GELESEN werden sie mit EINER Ausnahme ebenfalls nicht mehr — die Liste ist
# sonst nur Bezugsanker für die einmalige Migration:
#   `kwp` wird weiterhin AKTIV gelesen (`core/investition_kennwerte.py`), weil
#   die v3.25.0-Migration ihn nie umgeschrieben hat. Ohne diesen Lesepfad
#   fielen Bestandsdaten, die die Nennleistung nur im `parameter`-JSON tragen,
#   stumm auf 0 (#229/N66).
LEGACY_PARAM_KEYS: Final[dict[str, str]] = {
    # E-Auto
    "km_jahr": "jahresfahrleistung_km",
    "pv_anteil_prozent": "pv_ladeanteil_prozent",  # nur in E-Auto-Kontext, nicht WP
    "benzin_verbrauch_liter_100km": "vergleich_verbrauch_l_100km",
    "nutzt_v2h": "v2h_faehig",
    # Speicher
    "nutzt_arbitrage": "arbitrage_faehig",
    # Wallbox
    "leistung_kw": "max_ladeleistung_kw",  # nur in Wallbox-Kontext, nicht WP
    # A27/N115: fehlte hier, während die Migration ihn sehr wohl umschreibt
    # (`core/database.py::_migrate_investitionen_parameter_keys_v325`,
    # Kommentar dort „community_service-Drift"). Genau diese Sorte Lücke hält
    # `test_p3b_kanon_deckt_die_v325_migration_ab` ab jetzt fest.
    "ladeleistung_kw": "max_ladeleistung_kw",  # nur in Wallbox-Kontext
    # Wechselrichter
    "leistung_ac_kw": "max_leistung_kw",  # nur im toten Schema
    # PV-Module / Balkonkraftwerk — Legacy-Nennleistung. Als einziger Eintrag
    # dieser Liste noch AKTIV gelesen (s. Kopfkommentar).
    LEGACY_KWP_KEY: "leistung_kwp",
}


# ============================================================================
# Robuste Flag-Lesehilfen
# ============================================================================

def ist_dienstlich(inv_or_parameter) -> bool:
    """Truthy-Check für `ist_dienstlich` mit String-Drift-Schutz.

    Akzeptiert ein Investition-Objekt oder direkt das parameter-Dict
    (oder None). Schützt vor dem Klassiker, dass das Flag als String
    `"true"` / `"false"` in der DB landet — Python wertet `"false"` sonst
    als truthy aus und filtert das Auto fälschlich als Dienstwagen.
    """
    if inv_or_parameter is None:
        return False
    params = (
        getattr(inv_or_parameter, "parameter", None)
        if hasattr(inv_or_parameter, "parameter")
        else inv_or_parameter
    ) or {}
    val = params.get(PARAM_E_AUTO["IST_DIENSTLICH"], False)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "ja")
    return bool(val)


def ist_luft_luft_waermepumpe(inv_or_parameter) -> bool:
    """Ist diese Wärmepumpe eine Split-Klimaanlage (`wp_art="luft_luft"`)?

    Akzeptiert — wie `ist_dienstlich` — ein Investition-Objekt, direkt das
    parameter-Dict oder None.

    Warum als Helper und nicht als Vergleich an der Fundstelle: die Unterscheidung
    entscheidet an mehreren Stellen, ob eine **Wärmemenge** erwartet werden darf.
    Eine Split-Klimaanlage hat weder Wärmemengenzähler noch Warmwasserkreis — das
    Investitionsformular sagt das dem Anwender auch so zu (`WaermepumpeFelder.tsx`:
    „Es genügt der Stromverbrauchs-Sensor"). Wo die Bedingung fehlte, forderte der
    Daten-Checker eine Zuordnung, die es beim Anwender nicht geben kann
    (dietmar1968, Forum #89667/87).

    Legacy-WP **ohne** `wp_art` zählt bewusst als klassische WP: die Vorbelegung
    ist `luft_wasser`, und eine fehlende Angabe darf die Wärmemengen-Erwartung
    nicht stillschweigend abschalten.
    """
    if inv_or_parameter is None:
        return False
    params = (
        getattr(inv_or_parameter, "parameter", None)
        if hasattr(inv_or_parameter, "parameter")
        else inv_or_parameter
    ) or {}
    val = params.get(PARAM_WAERMEPUMPE["WP_ART"])
    return isinstance(val, str) and val.strip().lower() == "luft_luft"


def _wp_param_text(inv_or_parameter, key: str) -> str:
    """Ein Text-Parameter der Wärmepumpe, normalisiert — oder ``""``.

    Dieselbe Aufrufer-Toleranz wie `ist_luft_luft_waermepumpe` (Objekt, Dict
    oder None). Ausgelagert, weil inzwischen **drei** Wärmepumpen-Parameter
    dieselbe Auflösung brauchen und die Kopie sonst dreimal danebenstünde.
    """
    if inv_or_parameter is None:
        return ""
    params = (
        getattr(inv_or_parameter, "parameter", None)
        if hasattr(inv_or_parameter, "parameter")
        else inv_or_parameter
    ) or {}
    val = params.get(key)
    return val.strip().lower() if isinstance(val, str) else ""


def ist_brauchwasser_waermepumpe(inv_or_parameter) -> bool:
    """Macht dieses Gerät **ausschließlich** Warmwasser (`wp_art="brauchwasser"`)?

    Eine Brauchwasser-Wärmepumpe heizt nicht und kühlt nicht. Sie steht im
    Modell, obwohl es dafür **keinen einzigen bekannten Anwender** gibt
    (SOLL §7/A6, Entscheid Gernot 26.08.2026): Ein Modell, das einen realen
    Gerätetyp nicht ausdrücken kann, ist später nicht nachrüstbar — die bis
    dahin gespeicherten Daten wären dann falsch, nicht bloß unvollständig.

    ⚠ **Sie nimmt die Heiz-Achse nicht weg, sie stuft sie herab.** Wer an
    seinem Gerät doch einen Heizzähler hat, ordnet ihn weiter zu; das Feld
    steht dann unter „Weitere Größen erfassen" statt in der ersten Reihe
    (R1: *was ein Gerät liefern kann, sagt der Zähler, nicht die Bauart*).
    Die Warmwasser-Achse bleibt hart erwartet.
    """
    return _wp_param_text(inv_or_parameter, PARAM_WAERMEPUMPE["WP_ART"]) == "brauchwasser"


#: Die Werte von `PARAM_WAERMEPUMPE["ABGRENZUNG"]` — SoT für Formular, Registry
#: und Layer. Leer ist kein Wert, sondern die Abwesenheit einer Angabe.
ABGRENZUNG_FREMDSTROM: Final[str] = "fremdstrom"
ABGRENZUNG_FREMDWAERME: Final[str] = "fremdwaerme"
ABGRENZUNG_WERTE: Final[frozenset[str]] = frozenset(
    {ABGRENZUNG_FREMDSTROM, ABGRENZUNG_FREMDWAERME}
)


def abgrenzung_stoerung(inv_or_parameter) -> Optional[str]:
    """Die vom Anwender gemeldete Abgrenzungs-Störung — oder ``None``.

    ``None`` heißt **„keine bekannte Abweichung"**, nicht „geprüft und in
    Ordnung". Unbekannte Werte (Altbestand, Tippfehler im Import) ergeben
    ebenfalls ``None``: eine Sperre auf einen Wert zu stützen, den niemand
    gesetzt haben kann, wäre eine erfundene Auskunft.
    """
    wert = _wp_param_text(inv_or_parameter, PARAM_WAERMEPUMPE["ABGRENZUNG"])
    return wert if wert in ABGRENZUNG_WERTE else None


#: Die Werte von `PARAM_WAERMEPUMPE["KUEHLUNG_ART"]`.
KUEHLUNG_PASSIV: Final[str] = "passiv"
KUEHLUNG_AKTIV: Final[str] = "aktiv"
KUEHLUNG_KEINE: Final[str] = "keine"


def kuehlt_passiv(inv_or_parameter) -> bool:
    """Kühlt dieses Gerät **passiv** (nur Umwälzpumpen, kein Kompressor)?

    Die Kennzahl einer passiv gekühlten Anlage ist **korrekt** — sie liegt nur
    um ein Vielfaches über der einer aktiv gekühlten. Was hier gesperrt wird,
    ist deshalb nie die Zahl, sondern immer nur ihr **Vergleich** (SOLL §3.2b:
    *„eine Markierung an der Kennzahl, kein Feld für eine Menge"*).
    """
    return _wp_param_text(
        inv_or_parameter, PARAM_WAERMEPUMPE["KUEHLUNG_ART"]
    ) == KUEHLUNG_PASSIV


# ── Innengeräte einer Split-Klimaanlage (#263) ───────────────────────────────
#
# **Warum eine Liste im Parameter und keine eigene Investition.** Die Werte je
# Innengerät sind eine **Teilmenge** des Anlagenverbrauchs — genau wie heute
# schon Heizen/Warmwasser Teilmengen einer Wärmepumpe sind. Ein eigenes Gerät
# wäre überall ein zusätzlicher Verbraucher und müsste an jeder Aggregation
# wieder ausgenommen werden; das ist die Doppelzählungs-Klasse, die uns beim
# BKW, beim Speicher und beim Wallbox/E-Auto-Pool je einmal getroffen hat.
#
# **Die Liste ist selbst der Schalter** (Entscheid Gernots, 2026-08-20):
# „Multisplit" wird abgeleitet (``len(...) >= 2``) und nirgends gespeichert.
# Damit kann ein Schalter nicht von seiner Liste abweichen — der
# Widerspruchsfall existiert nicht.
#
# ⚠ **Die ID wird vergeben und NIE wiederverwendet.** `sensor_mapping` speichert
# nach Feld-Key (`modus_strom_kuehlen_kwh-3`); eine Positionsnummer würde beim
# Löschen des mittleren Geräts alle folgenden Zuordnungen stillschweigend
# verschieben — jede Zuordnung zeigte danach auf den falschen Raum.

def lade_innengeraete(inv_or_parameter) -> list[dict]:
    """Die Innengeräte-Liste eines Geräts — der eine Leser.

    Akzeptiert wie `ist_luft_luft_waermepumpe` ein Investition-Objekt, das
    parameter-Dict oder None. Liefert nur wohlgeformte Einträge (ganzzahlige
    `id` > 0, `bezeichnung` als Text) in gespeicherter Reihenfolge; alles
    andere wird übergangen statt zu raten.
    """
    if inv_or_parameter is None:
        return []
    params = (
        getattr(inv_or_parameter, "parameter", None)
        if hasattr(inv_or_parameter, "parameter")
        else inv_or_parameter
    ) or {}
    roh = params.get(PARAM_WAERMEPUMPE["INNENGERAETE"])
    if not isinstance(roh, list):
        return []
    out: list[dict] = []
    gesehen: set[int] = set()
    for eintrag in roh:
        if not isinstance(eintrag, dict):
            continue
        try:
            gid = int(eintrag.get("id"))
        except (TypeError, ValueError):
            continue
        if gid <= 0 or gid in gesehen:
            continue
        gesehen.add(gid)
        bez = eintrag.get("bezeichnung")
        out.append({
            "id": gid,
            "bezeichnung": str(bez).strip() if isinstance(bez, str) and bez.strip()
                           else f"Innengerät {gid}",
        })
    return out


def naechste_innengeraet_id(innengeraete: list[dict]) -> int:
    """Die nächste freie ID — **max + 1**, nie eine Lücke auffüllen.

    Eine wiederverwendete ID erbt die Sensor-Zuordnungen des gelöschten Geräts;
    der neue Raum zeigte dann fremde Werte, ohne dass jemand etwas zugeordnet
    hätte.
    """
    hoechste = 0
    for g in innengeraete or []:
        try:
            hoechste = max(hoechste, int(g.get("id")))
        except (TypeError, ValueError):
            continue
    return hoechste + 1
