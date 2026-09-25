"""Lesetueren auf das `verbrauch_daten`-JSON (`get_*_kwh`).
"""
# Reiner Umzug aus `core/field_definitions.py` (18.09.2026, Vorlage 3 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert
# alle Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from typing import Optional
from backend.core.field_definitions.auswahl import ist_abgabe_kategorie, ist_zaehler_kategorie
from backend.core.field_definitions.bedingungen import groesse_gibt_es_am_geraet


# =============================================================================
# Reader-Helper für `verbrauch_daten`-JSON
#
# Drift-Audit Domäne F: bisher waren 27+ Aufrufer mit Mustern wie
# `data.get("a", 0) or data.get("b", 0)` über das Repo verstreut. Bei
# Schema-Drift (alter Key bleibt in Daten, neuer Key fehlt) führte das
# zu inkonsistentem Verhalten zwischen Endpoints.
#
# Diese Helper sind die SoT für PV/WP/E-Auto/Speicher-Energiewerte. Bei
# künftigen Schema-Wechseln nur hier anpassen.
# =============================================================================

def get_pv_erzeugung_kwh(data: dict) -> float:
    """PV-Modul- oder BKW-Erzeugung. Liest `pv_erzeugung_kwh` (kanonisch),
    Legacy-Fallback `erzeugung_kwh`.
    """
    if not data:
        return 0.0
    return float(data.get("pv_erzeugung_kwh") or data.get("erzeugung_kwh") or 0)

def get_wp_heizenergie_kwh(data: dict) -> float:
    """Wärmepumpen-Heizenergie (nicht Warmwasser).
    Liest `heizenergie_kwh` (kanonisch), Legacy-Fallback `heizung_kwh`.
    """
    if not data:
        return 0.0
    return float(data.get("heizenergie_kwh") or data.get("heizung_kwh") or 0)

def get_wp_warmwasser_kwh(data: dict, params: Optional[dict] = None) -> float:
    """Abgegebene Warmwasser-Wärme einer Wärmepumpe — **die eine Lesetür**.

    Spiegelbild zu `get_wp_heizenergie_kwh`, mit einem Zusatz: Es fragt die
    Registry, ob **dieses Gerät die Größe überhaupt hat**
    (`groesse_gibt_es_am_geraet`). Eine Split-Klimaanlage hat keinen
    Warmwasserkreis; ein dort gespeicherter Wert ist keine Wärme dieses Geräts
    und darf in keiner Summe erscheinen, die eine Abgabe behauptet.

    ⭐ **N-379 — warum es diese Funktion gibt.** N-304 hat das Feld am
    22.08.2026 aus der **Erfassung** genommen und im Docstring seiner Probe den
    Schaden wörtlich benannt: *„Ein an einer Luft-Luft-Anlage gepflegter
    Warmwasser-Wert erzeugt eine Ersparnis für Wärme, die das Gerät nie erzeugt
    hat."* Für **bereits gespeicherte** Werte galt das weiter, denn elf
    Faltstellen in sechs Dateien lasen `warmwasser_kwh` roh aus
    `verbrauch_daten` — Hub, Cockpit → Monat, Aussichten, HA-Export und der
    Gas-/CO₂-Vergleich. Gemeldet von dietmar1968 (T89667 #295): 889 kWh
    „Warmwasser" an seiner Klimaanlage, daraus „Ersparnis vs. Gas 38 €" und
    „CO₂-Ersparnis −112 kg".

    ⚠ **Vierte Runde der #236-Folgewellen-Klasse.** `ist-waerme-klima.md` §W-12
    nennt N-304 selbst die dritte: *ein Filter auf einer Schicht reicht nicht,
    wenn mehrere Pfade dieselbe Größe lesen.* Deshalb eine Tür statt fünf
    Pflaster — wer eine sechste Read-Site baut, liest hier.

    ⛔ **Der gespeicherte Wert bleibt** (keine Migration): eedc weiß nicht, was
    er ist, nur dass er an diesem Gerät keine Warmwasser-Wärme sein kann. Der
    Daten-Checker benennt ihn und nennt seinen Platz.

    ⛔ **Ohne `params` verhält sie sich wie der Rohzugriff.** Das ist kein
    Schlupfloch, sondern die Lage der Aufrufer, die keine Investition zur Hand
    haben (Import-/Schreibpfade); sie sollen nichts filtern.
    """
    if not data:
        return 0.0
    if params is not None and not groesse_gibt_es_am_geraet(
        "waermepumpe", "warmwasser_kwh", params
    ):
        return 0.0
    return float(data.get("warmwasser_kwh") or 0)

def hat_wp_warmwasser_wert(data: dict, params: Optional[dict] = None) -> bool:
    """Trägt diese Monatszeile überhaupt einen Warmwasser-Wert? — **Anwesenheit,
    nicht Menge.**

    Schwester von `get_wp_warmwasser_kwh` mit derselben Geräte-Bedingung, aber
    der anderen Frage. Die Lesetür liefert `float` und macht aus einem fehlenden
    Wert eine 0 (`data.get(...) or 0`) — für eine Summe ist das richtig, für die
    Frage *„wurde hier je etwas gemessen?"* nicht: Eine **gepflegte** 0 ist eine
    Messung, ein fehlender Eintrag ist eine Leerstelle, und beide kämen als
    `0.0` zurück. Das ist die `is not None`-Regel aus `CLAUDE.md`, hier als
    eigene Tür statt als Rohzugriff daneben.

    ⭐ **Wofür sie gebraucht wird (8ear, #404):** SOLL Wärme/Klima §3.2a **R1**
    sagt *„was ein Gerät liefern kann, sagt der zugeordnete Zähler, nicht seine
    Bauart — wer keinen zuordnet, sieht die Achse nicht."* Die Warmwasser-Achse
    im Komponenten-Hub hing bis dahin allein an der Bauart
    (`groesse_gibt_es_am_geraet`) und stand deshalb an **jeder** Luft-Wasser-WP,
    auch an einer, die nachweislich nie Warmwasser gemessen hat — dauerhaft auf
    Null, samt Balken, Spalte und Legendeneintrag.

    ⛔ **Sie ersetzt `groesse_gibt_es_am_geraet` NICHT, sie ergänzt es.** Die
    Bauart-Frage bleibt die härtere: Eine Split-Klimaanlage hat keinen
    Warmwasserkreis, dort zählt ein gespeicherter Wert auch dann nicht, wenn er
    dasteht (N-379). Diese Funktion trägt die weichere Hälfte und darf nur
    **zusätzlich** geprüft werden, nie an ihrer Stelle.

    ⚠ **Und sie entscheidet nur über die ANZEIGE einer Achse, nie über eine
    Kennzahl je Monatszeile.** Eine Arbeitszahl fragt, ob das Gerät die Größe
    hat — nicht, ob ein anderer Monat sie trug.
    """
    if not data:
        return False
    if params is not None and not groesse_gibt_es_am_geraet(
        "waermepumpe", "warmwasser_kwh", params
    ):
        return False
    return data.get("warmwasser_kwh") is not None

def get_eauto_ladung_kwh(data: dict) -> float:
    """E-Auto- oder Wallbox-Gesamtladung in kWh — **nur** `ladung_kwh`.

    ⛔ **Hier stand bis 25.09.2026 ein Ersatz: `ladung_kwh or verbrauch_kwh`** (N-555).
    Am E-Auto ist `verbrauch_kwh` der **Fahrverbrauch**, keine Ladung; der Ersatz
    stammte aus der Zeit vor der Schlüssel-Migration (v3.25.8), als die Wallbox ihre
    Ladung noch unter `verbrauch_kwh` führte. Er setzte den Fahrverbrauch still als
    Heimladung ein — auch neben einer Wallbox, die gemessen 0 kWh geladen hatte, und
    gleich neun Aufrufer weit. Die Schätzung aus dem Fahrverbrauch gibt es weiter,
    aber nur noch **ausdrücklich** und an **einer** Stelle:
    `services/eauto_wirtschaftlichkeit.entscheide_emob_heimladung` (Konzept
    Heimladung/Fahrverbrauch, Regel 1 + 6). Eine Wallbox trägt kein `verbrauch_kwh`
    mehr (die Startroutine benennt es um), für sie ändert sich nichts.
    """
    if not data:
        return 0.0
    return float(data.get("ladung_kwh") or 0)

def get_speicher_netzladung_kwh(data: dict) -> float:
    """Speicher-Netzladung (Arbitrage). Liest `ladung_netz_kwh` (kanonisch),
    Legacy-Fallback `speicher_ladung_netz_kwh`.
    """
    if not data:
        return 0.0
    return float(data.get("ladung_netz_kwh") or data.get("speicher_ladung_netz_kwh") or 0)

def get_emob_pv_netz_kwh(data: dict, total_kwh: float | None = None) -> tuple[float, float]:
    """E-Mobilitäts-PV-/Netz-Anteil aus Wallbox-/E-Auto-Monatsdaten.

    Liest `ladung_pv_kwh` direkt. Für `ladung_netz_kwh`:
    - wenn als Key vorhanden → verwenden (auch 0 ist ein gültiger gepflegter Wert)
    - sonst aus Gesamt-Ladung ableiten: `netz = max(0, total - pv)`.

    Hintergrund #262 (junky84): der evcc-Portal-Import liefert pro Session nur
    `Energie (kWh)` + `Sonne (%)` und schreibt damit `ladung_kwh` + `ladung_pv_kwh`,
    aber kein `ladung_netz_kwh`. Pool-Max-Aggregationen, die nur diese beiden Keys
    direkt lasen, sahen Netz = 0 und damit PV-Anteil = 100 %.

    `total_kwh` darf vom Aufrufer übergeben werden, wenn die Gesamt-Ladung bereits
    via `get_eauto_ladung_kwh()` bestimmt wurde — spart eine zweite Lesung.

    ⛔ Ohne `total_kwh` ist die Gesamt-Ladung **nur** `ladung_kwh` — kein
    Fahrverbrauch (N-555, Begründung an `get_eauto_ladung_kwh`). Eine Zeile, die
    nur „Heim: PV" trägt, hat damit Netz 0 statt `Verbrauch − PV`.
    """
    if not data:
        return (0.0, 0.0)
    pv = float(data.get("ladung_pv_kwh") or 0)
    if "ladung_netz_kwh" in data and data["ladung_netz_kwh"] is not None:
        return (pv, float(data["ladung_netz_kwh"]))
    if total_kwh is None:
        total_kwh = get_eauto_ladung_kwh(data)
    return (pv, max(0.0, total_kwh - pv))

# Die Verbrauchs-Felder eines *Sonstiges*-Geräts, in Präzedenz-Reihenfolge:
# `verbrauch_sonstig_kwh` ist der **kanonische** Registry-Name — so heißt der
# `sensor_mapping`-Key, und unter diesem Namen publiziert eedc auch sein
# MQTT-Topic. `verbrauch_kwh` ist der Legacy-Zwilling und bleibt nur lesbar
# (Altbestand im Mapping); er darf nie zusätzlich zählen, beide gehören
# derselben Either-Or-Gruppe an.
SONSTIGES_VERBRAUCH_FELDER: tuple[str, ...] = ("verbrauch_sonstig_kwh", "verbrauch_kwh")

def sonstiges_feld_reihenfolge(kategorie: str | None) -> tuple[str, ...]:
    """Energie-Felder eines *Sonstiges*-Geräts in **Präzedenz-Reihenfolge**.

    Ein solches Gerät hat entweder eine Erzeugung oder einen Verbrauch, nie
    beides — die gepflegte ``kategorie`` sagt, welches Feld führt. Wer keine
    gepflegt hat, wird als Verbraucher gelesen (dieselbe Lesart wie in den
    Schreibpfaden, siehe ``berechnungen.energie.sonstiges_richtung``).

    **Warum das eine Funktion ist (N-259).** Dieselbe Reihenfolge stand am
    16.08.2026 an **drei** Stellen handgeschrieben — und ein einziger
    abweichender Name hat gereicht, damit eedc ein MQTT-Topic **selbst
    publizierte und beim Einlesen wieder verwarf**: Der Snapshot suchte
    ``verbrauch_kwh``, die Zuordnungsfläche schrieb ``verbrauch_sonstig_kwh``.
    Der Monat kam trotzdem an (dieser Getter liest beide), der Tageswert nicht —
    es sah nach „Wert fehlt" aus statt nach „Feld wird nirgends gefunden".
    Eine vierte Kopie wäre dieselbe Wette noch einmal.

    ⚠ **Ein Zähler liefert `()` — und das ist kein Sonderfall, sondern die
    Antwort auf die gestellte Frage** (#377): Diese Funktion nennt die
    **Energie**-Felder eines Geräts, und ein Gaszähler hat keine. Ohne den
    leeren Rückgabewert liefe der Fallback in Zeile darunter, und der Snapshot
    suchte am Gaszähler nach `verbrauch_sonstig_kwh` — die N-259-Klasse in der
    Gegenrichtung: nicht ein falscher Name, sondern ein Feld, das es an diesem
    Gerät gar nicht geben darf.
    """
    if ist_zaehler_kategorie(kategorie):
        return ()
    if ist_abgabe_kategorie(kategorie):
        return ("abgabe_kwh",)
    if kategorie == "erzeuger":
        return ("erzeugung_kwh", *SONSTIGES_VERBRAUCH_FELDER)
    return (*SONSTIGES_VERBRAUCH_FELDER, "erzeugung_kwh")

def get_sonstiges_verbrauch_kwh(data: dict) -> float:
    """Sonstiges-Verbraucher-Energie. Liest `verbrauch_sonstig_kwh` (kanonisch),
    Legacy-Fallback `verbrauch_kwh` — Reihenfolge aus
    `SONSTIGES_VERBRAUCH_FELDER`, damit sie nicht neben dem SoT driftet.
    """
    if not data:
        return 0.0
    for feld in SONSTIGES_VERBRAUCH_FELDER:
        wert = data.get(feld)
        if wert:
            return float(wert)
    return 0.0
