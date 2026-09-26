"""Abgeleitete Karten: Labels, Einheiten, Zustandsfelder, Zaehler-/Stand-/Snapshot-Ableitungen — zur Importzeit aus der
Registry gebildet.
"""
# Reiner Umzug aus `core/field_definitions.py` (18.09.2026, Vorlage 3 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert
# alle Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from typing import Final, Optional
from backend.core.field_definitions.keys import basis_feld_key
from backend.core.field_definitions.registry import BASIS_FELDER, BASIS_LIVE_FELDER, BEDINGTE_BASIS_FELDER, INVESTITION_FELDER, LIVE_FELDER_INV, _BETRIEBSART_NUTZENERGIE_FELDNAMEN, _BETRIEBSART_STROM_FELDNAMEN


# Typen mit SoC-Live-Sensor (aus LIVE_FELDER_INV abgeleitet)
SOC_TYPEN: frozenset[str] = frozenset(
    typ for typ, felder in LIVE_FELDER_INV.items()
    if any(f["key"] == "soc" for f in felder)
)

# Live-Felder, deren Wert ein ZUSTAND ist statt einer Zahl (#263 K-2).
#
# **Warum diese Menge existiert und nicht drei verstreute Ausnahmen.** Der
# gesamte Live-Pfad ist numerisch, und zwar an drei Stellen unabhängig
# voneinander:
#
#   1. `live_power_service._states_zu_w` → `normalize_to_w(float(state))` — läuft
#      über JEDE Live-Zuordnung, alle 5 Sekunden. Ein `climate`-State ergibt dort
#      garantiert `None`; es wäre ein Dauerabruf ohne Ergebnis.
#   2. `mqtt_inbound_service` → `float(payload)`. Ein Modus über MQTT ist damit
#      nicht empfangbar — also wird er auch nicht als Topic **angeboten**, statt
#      dem Anwender eine Quelle hinzustellen, die nichts liefert (die P-6-Falle:
#      ein Hinweis bzw. hier ein Angebot, das niemand einlösen kann).
#   3. `daten_checker/sensoren.py` prüft Einheiten (kW≠kWh) — ein Feld ohne
#      Einheit hat dort nichts zu suchen.
#
# Statt an jeder dieser Stellen `if key == "betriebsmodus"` zu schreiben, steht
# die Eigenschaft **am Feld** und wird von hier gelesen. Ein zweites
# Zustandsfeld erbt damit alle drei Weichen, ohne dass jemand sie sucht.
#
# ⚠ Die Umkehrung gilt ausdrücklich: was hier NICHT steht, ist eine Zahl. Wer
# ein Feld ohne `einheit` einträgt, hat damit noch kein Zustandsfeld gebaut.
ZUSTAND_LIVE_FELDER: frozenset[tuple[str, str]] = frozenset(
    (typ, f["key"])
    for typ, felder in LIVE_FELDER_INV.items()
    for f in felder
    if f.get("zustand")
)

# Nur die Feld-Keys — für die Pfade, die ihren Investitionstyp nicht kennen
# (der Live-Poller sieht `{inv_id: {key: entity}}` ohne Typ-Kontext).
ZUSTAND_FELD_KEYS: frozenset[str] = frozenset(key for _, key in ZUSTAND_LIVE_FELDER)

def einheit_fuer(feld: str, investition=None) -> str:
    """Die Einheit, die neben diesem Wert stehen soll — **der eine Leser** (#377).

    Für fast jedes Feld steht sie fest in der Registry (`FELD_EINHEITEN`). Für
    den **Zählerstand** nicht: Er ist einheitenlos gespeichert, und was daneben
    steht (m³, l, kg, t, kWh), hängt am **Gerät** — ein Haushalt kann einen
    Gaszähler in m³ und einen Wasserzähler in m³ und einen Öltank in Litern
    führen.

    **Warum die Eigenschaft am Feld steht und nicht als `if feld ==`:**
    dieselbe Bauform wie `ZUSTAND_LIVE_FELDER`/`ist_zustand_feld` (#263 K-2) —
    *Eigenschaft am Feld, abgeleitete Menge, ein Leser*. Ein zweites Feld mit
    geräteabhängiger Einheit kostet damit einen Registry-Eintrag
    (`einheit_je_geraet: "<param>"`) und keine neue Verzweigung.

    ⚠ **Die Einheit ist Anzeige, nie Rechnung.** eedc rechnet Zählerstände
    grundsätzlich nicht um. Wer sein Gerät von m³ auf kWh umstellt, ändert das
    Wort neben der Zahl — die Zahl bleibt, wie der Zähler sie meldet.
    """
    # #263 — je-Innengerät-Keys tragen die Einheit ihres Basis-Felds.
    feld = basis_feld_key(feld)
    param_key = FELD_EINHEIT_JE_GERAET.get(feld)
    if param_key:
        if investition is not None:
            wert = (getattr(investition, "parameter", None) or {}).get(param_key)
            if wert:
                return str(wert)
        # Gerät ohne gepflegte Einheit: der Registry-Default gilt. Lokaler
        # Import, weil `investition_parameter` die Defaults führt und ein
        # Top-Level-Import dieses Basis-Modul an es binden würde.
        from backend.core.investition_parameter import PARAM_SONSTIGES_DEFAULTS

        standard = PARAM_SONSTIGES_DEFAULTS.get(param_key)
        if standard:
            return str(standard)
    return FELD_EINHEITEN.get(feld, "")

def ist_zustand_feld(feld: str, typ: Optional[str] = None) -> bool:
    """Ist dieses Live-Feld ein Zustand statt einer Zahl? — siehe {@link ZUSTAND_LIVE_FELDER}.

    `typ` schärft die Antwort, wo der Aufrufer ihn hat; ohne ihn gilt der
    Feld-Key allein. Beides ist gewollt: die Zuordnungs-Fläche kennt den Typ,
    der Live-Poller nicht.
    """
    # #263: Der Key kann eine Innengeräte-Adresse tragen
    # (`betriebsmodus-3`). Die Zustands-Eigenschaft hängt am Feld, nicht am
    # Innengerät — ohne Auflösung liefe eine `climate`-Entität in den
    # 5-Sekunden-Poller und in ein MQTT-Topic, das `float(payload)` nie
    # annehmen kann.
    basis = basis_feld_key(feld)
    if typ is not None:
        return (typ, basis) in ZUSTAND_LIVE_FELDER
    return basis in ZUSTAND_FELD_KEYS

def build_feld_labels() -> dict[str, str]:
    """
    Baut ein vollständiges Label-Dict aus der Registry auf.

    Kombiniert:
    - BASIS_FELDER (mapping_key → label)
    - INVESTITION_FELDER (feld → label, alle Typen/Kategorien)
    - LIVE_FELDER_INV (key → label)
    - Basis-Level-Extras (pv_gesamt, etc.)

    Returns:
        dict: {feldname_oder_key: anzeigelabel}
    """
    labels: dict[str, str] = {}

    # Basis-Felder (mapping_key-Form: "einspeisung", "netzbezug", ...)
    for f in BASIS_FELDER:
        labels[f["mapping_key"]] = f["label"]
        labels[f["feld"]] = f["label"]  # auch DB-Feldname → Label

    # Bedingte Basis-Felder
    for f in BEDINGTE_BASIS_FELDER:
        labels[f["feld"]] = f["label"]
        if "mapping_key" in f:
            labels[f["mapping_key"]] = f["label"]

    # Basis-Live-Felder
    for f in BASIS_LIVE_FELDER:
        labels[f["key"]] = f["label"]

    # Investitions-Felder (alle Typen)
    for typ, felder in INVESTITION_FELDER.items():
        if isinstance(felder, dict):
            # Sonstiges — Kategorien
            for kat_felder in felder.values():
                for f in kat_felder:
                    labels[f["feld"]] = f["label"]
        else:
            for f in felder:
                labels[f["feld"]] = f["label"]

    # Live-Felder (Investitions-Ebene)
    for felder in LIVE_FELDER_INV.values():
        for f in felder:
            labels[f["key"]] = f["label"]

    # Extras die nicht in oben definierter Struktur stecken
    labels["pv_gesamt"] = "PV Erzeugung Gesamt"
    # Counter-Felder (TagesEnergieProfil), erscheinen im Statistik-Import wenn
    # im Sensor-Mapping einer WP-Investition gemappt — detLAN #187/1 + #238.
    labels["wp_starts_anzahl"] = "Kompressor-Starts"
    labels["wp_betriebsstunden"] = "Betriebsstunden"

    return labels

# Vorgefertigtes Label-Dict (einmalig berechnet)
FELD_LABELS: dict[str, str] = build_feld_labels()

def build_feld_einheiten() -> dict[str, str]:
    """Baut {feldname_oder_key_oder_mapping_key: einheit} aus der Registry.

    Single Source of Truth für Einheiten-Plausibilität (Daten-Checker
    `_check_sensor_mapping_einheit`): erlaubt, zu jedem gemappten Slot die
    erwartete Einheit nachzuschlagen, statt sie aus Namenskonventionen zu raten.
    Deckt Basis-Zähler (mapping_key + feld), Basis-Live-Keys, alle
    Investitions-Felder (inkl. Sonstiges-Kategorien) und Investitions-Live-Keys
    ab. Strings kollidieren nicht über Kontexte (z. B. `einspeisung` vs.
    `einspeisung_kwh` vs. `einspeisung_w`); gleiche Strings tragen dieselbe
    Einheit.
    """
    einheiten: dict[str, str] = {}

    for f in BASIS_FELDER + BEDINGTE_BASIS_FELDER:
        if "mapping_key" in f:
            einheiten[f["mapping_key"]] = f.get("einheit", "")
        einheiten[f["feld"]] = f.get("einheit", "")

    for f in BASIS_LIVE_FELDER:
        einheiten[f["key"]] = f.get("einheit", "")

    for felder in INVESTITION_FELDER.values():
        if isinstance(felder, dict):  # sonstiges → nach Kategorie
            for kat_felder in felder.values():
                for f in kat_felder:
                    einheiten[f["feld"]] = f.get("einheit", "")
        else:
            for f in felder:
                einheiten[f["feld"]] = f.get("einheit", "")

    for felder in LIVE_FELDER_INV.values():
        for f in felder:
            einheiten[f["key"]] = f.get("einheit", "")

    return einheiten

# Vorgefertigtes Einheiten-Dict (einmalig berechnet)
FELD_EINHEITEN: dict[str, str] = build_feld_einheiten()

def _build_einheit_je_geraet() -> dict[str, str]:
    """`{feld: parameter-schlüssel}` für Felder mit **geräteabhängiger** Einheit.

    **Abgeleitet aus der Registry, nicht danebengeschrieben** — dieselbe
    Begründung wie bei `ZUSTAND_LIVE_FELDER` (#263 K-2) und `_sonstiges_felder_
    ungepflegt` (N-259): eine handgepflegte zweite Liste ist die Wette darauf,
    dass jemand sie beim nächsten Feld mitzieht.
    """
    out: dict[str, str] = {}
    for felder in INVESTITION_FELDER.values():
        listen = list(felder.values()) if isinstance(felder, dict) else [felder]
        for liste in listen:
            for f in liste:
                if f.get("einheit_je_geraet"):
                    out[f["feld"]] = f["einheit_je_geraet"]
    return out

#: Felder, deren Einheit erst am Gerät feststeht (#377). Leser: `einheit_fuer`.
FELD_EINHEIT_JE_GERAET: dict[str, str] = _build_einheit_je_geraet()

# ─── Einheiten-Dimension (SoT für Leistung↔Energie-Verwechslung) ────────────
# Gemeinsam genutzt vom Daten-Checker (`SENSOR_MAPPING_EINHEIT`) UND der
# Datenquellen-V4-Zuordnungs-Validierung (§2i, kWh-Sensor in W-Feld = #200).
# Bewusst NUR Leistung/Energie: SoC (%)/Temperatur (°C)/Preis/km sind legitime
# Einheiten-Varianten → kein Fehlalarm.
_POWER_EINHEITEN = {"W", "kW", "MW"}

_ENERGY_EINHEITEN = {"kWh", "Wh", "MWh"}

def einheit_klasse(unit: Optional[str]) -> Optional[str]:
    """Dimensions-Klasse einer Einheit: 'leistung' | 'energie' | None (egal)."""
    if unit in _POWER_EINHEITEN:
        return "leistung"
    if unit in _ENERGY_EINHEITEN:
        return "energie"
    return None

# ─── Zählerdifferenz-Felder (SoT für „darf aus HA-LTS gelesen werden?") ─────
# Zähler ohne Energie-Einheit: monoton steigend, der Monatswert ist die
# Differenz zweier Zählerstände. Energie-Felder erkennt `einheit_klasse`.
_ZAEHLER_FELDER_OHNE_ENERGIE_EINHEIT: frozenset[str] = frozenset({
    "km_gefahren",        # km-Zähler (Auto-Integration/OBD)
    "ladevorgaenge",      # Anzahl-Zähler der Wallbox
    "wp_starts_anzahl",   # #136
    "wp_betriebsstunden",  # #238
    # Basis-Mapping-Schlüssel des PV-Sammelzählers. kWh wie „einspeisung"/
    # „netzbezug", steht aber in KEINER Feld-Registry: es ist ein reiner
    # Mapping-Key, kein IMD-Feld — `FELD_EINHEITEN` kennt ihn deshalb nicht.
    # Ohne diesen Eintrag fiele der Sammelzähler still aus dem Statistik-Import
    # (gewächtert in test_zaehler_differenz_feld.py).
    "pv_gesamt",
})

def ist_zaehler_differenz_feld(feld: str) -> bool:
    """Darf der Monatswert dieses Feldes als Zählerdifferenz gelesen werden?

    Die Monatswert-Pfade aus HA (`monatsabschluss`-Vorschläge,
    HA-Statistik-Import) rechnen ausnahmslos `MAX(sum) − MIN(sum)` mit
    Fallback `MAX(state) − MIN(state)`. Das ist für einen Zählerstand richtig
    und für alles andere Unsinn: bei einem Preis-Sensor käme die **Preis-Spanne
    des Monats** heraus, bei einer Temperatur die Spreizung.

    Vorher iterierten beide Pfade ungefiltert über alles, was im Mapping stand.
    Praktisch blieb das meist folgenlos, weil ein `measurement`-Sensor weder
    `state` noch `sum` führt und still `None` liefert — aber eine Preis-Entität
    mit gefüllter `state`-Spalte schrieb ihre Monats-Spreizung als Ø Ladepreis
    in die Datenbank (Forum simon42 #89667/54, Anlass war die Sensor-Zuordnung
    an einem ct/kWh-Feld).

    Kein Gegenstück in `snapshot/keys.py`: dort geht es um den stündlichen
    Snapshot-Job, hier um den Monatswert aus HA-Langzeitstatistik. Die Mengen
    überschneiden sich, sind aber nicht dieselbe Frage — `ladung_extern_kwh`
    etwa ist ein Monatswert ohne Snapshot-Erfassung.
    """
    if einheit_klasse(FELD_EINHEITEN.get(feld)) == "energie":
        return True
    return feld in _ZAEHLER_FELDER_OHNE_ENERGIE_EINHEIT

# ─── Snapshot-Zählerfelder: die Ableitung für `services/snapshot/keys.py` ────
#
# **Warum es das gibt (N-259, Melder rapahl, 16.08.2026).** `snapshot/keys.py`
# führte `KUMULATIVE_ZAEHLER_FELDER` als **zweite, handgepflegte Liste**
# derselben Feldnamen, die hier oben in `INVESTITION_FELDER` stehen. Die beiden
# sind auseinandergelaufen, und niemand konnte es sehen:
#
# * Ein *Sonstiges*-Verbraucher heißt hier **`verbrauch_sonstig_kwh`** — die
#   Zuordnungsfläche schreibt diesen Key ins `sensor_mapping`, und
#   `mqtt_topic_registry` baut daraus das Topic
#   `…/inv/<id>_<name>/verbrauch_sonstig_kwh`. Die Snapshot-Liste kannte
#   stattdessen **`verbrauch_kwh`**, einen Namen, den es für diesen Typ gar
#   nicht gibt. Folge: `_mqtt_key_to_sensor_key` verwarf das **selbst
#   publizierte** Topic, `_add("verbrauch_kwh")` fand nie ein Mapping ⇒ ein
#   Heizstab mit eigenem Zähler existierte auf Stunden- und Tagesebene nicht.
#   Der Monat kam an, weil `get_sonstiges_verbrauch_kwh` **beide** Namen liest.
# * Der *Sonstiges*-**Erzeuger** war nie betroffen: er heißt in beiden Welten
#   `erzeugung_kwh`. Genau deshalb fiel es so lange nicht auf.
#
# **Die Ableitung ändert das heutige Verhalten NICHT** (außer dem belegten
# Fehler). Jede Abweichung zwischen Feld-Registry und Snapshot-Liste steht
# unten mit Grund — „bewusst nicht" ist von „noch nicht bewertet" unterscheidbar
# geworden, und genau das fehlte. Gewächtert in
# `test_snapshot_felder_sot_konformitaet.py`.

# (typ, feld) → Grund, warum das kWh-Feld NICHT stündlich gesnapshottet wird.
_SNAPSHOT_AUSNAHMEN: dict[tuple[str, str], str] = {
    # — Balkonkraftwerk: Kanon-Entscheid 2026-07-31 (Weg A) —
    ("balkonkraftwerk", "speicher_ladung_kwh"):
        "nur_manuell: BKW-Akku ist Kanon-Weg A eine eigene speicher-Investition "
        "mit Parent BKW; ein zweiter Zählerpfad wäre Doppelerfassung",
    ("balkonkraftwerk", "speicher_entladung_kwh"):
        "nur_manuell: siehe speicher_ladung_kwh",
    ("balkonkraftwerk", "eigenverbrauch_kwh"):
        "kein Zähler, sondern optionale Verfeinerung aus manueller Pflege/Import "
        "(Begründung: core/berechnungen/bkw_finanz.py)",
    # — Sonstiges-Erzeuger: dieselbe Klasse wie beim BKW —
    ("sonstiges", "eigenverbrauch_kwh"):
        "wie balkonkraftwerk/eigenverbrauch_kwh — Verfeinerung, kein Zähler",
    ("sonstiges", "einspeisung_kwh"):
        "Anteil der Erzeugung, optional gepflegt; die Bilanz führt der "
        "Anlagen-Einspeisezähler (basis:einspeisung)",
    # — Teilmengen des Sonstiges-Verbrauchs —
    ("sonstiges", "bezug_pv_kwh"):
        "⚠ UNBEWERTET: Teilmenge von verbrauch_sonstig_kwh. Bei der Wallbox ist "
        "das Gegenstück (ladung_pv_kwh) sehr wohl erfasst — die Ungleichheit ist "
        "gemessen, aber nicht entschieden. Beim nächsten Eingriff bewerten",
    ("sonstiges", "bezug_netz_kwh"):
        "⚠ UNBEWERTET: siehe bezug_pv_kwh",
    # — E-Auto —
    ("e-auto", "ladung_extern_kwh"):
        "Monatswert ohne Snapshot-Erfassung — auswärts geladene Energie fließt "
        "nicht durch den Hauszähler (so auch im Docstring von "
        "ist_zaehler_differenz_feld festgehalten)",
    ("e-auto", "v2h_entladung_kwh"):
        "⚠ UNBEWERTET: V2H speist ins Haus zurück und ist damit bilanzrelevant; "
        "warum das Feld nie im Snapshot-Pfad stand, ist nicht dokumentiert. "
        "Beim nächsten Eingriff am E-Auto-Pfad bewerten",
    # — Wechselrichter —
    ("wechselrichter", "pv_erzeugung_kwh"):
        "⚠ UNBEWERTET: Der Typ hat keinen Komponenten-Präfix "
        "(snapshot/komponenten_beitraege._TYP_KEY_PREFIX) und damit keinen "
        "Ziel-Key; die MQTT-Seite kennt ihn dagegen "
        "(mqtt_energy_history_service._MQTT_FIELD_TO_LIVE_KEY). Beim nächsten "
        "Eingriff am Wechselrichter-Pfad bewerten",
}

# Namen, die die Snapshot-Liste führt, obwohl es sie für diesen Typ in der
# Feld-Registry NICHT gibt. Sie bleiben stehen, weil sie in Altbeständen im
# `sensor_mapping` liegen können und ein Entfernen dort Zuordnungen unsichtbar
# machen würde — dieselbe Falle, die `nur_manuell` schon einmal gestellt hat.
# Wirkungslos sind sie nicht automatisch: `sonstiges/verbrauch_kwh` stand an der
# Stelle, an der `verbrauch_sonstig_kwh` fehlte, und täuschte Abdeckung vor.
_SNAPSHOT_KOMPATIBILITAET: dict[str, tuple[str, ...]] = {
    "wallbox": ("ladung_netz_kwh",),   # Wallbox-Registry kennt nur ladung_kwh/ladung_pv_kwh
    # ⚑ N-555 Stufe 2 (26.09.2026): `e-auto/ladung_kwh` stand hier als Alias — seitdem ist
    # es das Registry-Feld „Heim: gesamt" (E5) und damit kein Kompatibilitäts-Name mehr.
    "sonstiges": ("verbrauch_kwh",),   # Legacy-Zwilling von verbrauch_sonstig_kwh (s. get_sonstiges_verbrauch_kwh)
}

# (typ, feld) → Grund, warum das Feld zwar als **Zähler** mitgeschnitten wird,
# aber KEINEN Beitrag zu `komponenten_kwh` liefert.
#
# ⚑ **Diese Unterscheidung fehlte, und sie ist die eigentliche N-259-Lehre.**
# „Wird gesnapshottet" und „zählt in die Bilanz" sind zwei Fragen; bis hierher
# beantwortete sie eine Liste plus eine Reihe von `if typ ==`-Zweigen, zwischen
# denen niemand einen Abgleich ziehen konnte. `verbrauch_sonstig_kwh` fehlte in
# **beiden** — und weil es keine Deckungsprüfung gab, sah das aus wie Absicht.
_SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG: dict[tuple[str, str], str] = {
    ("wallbox", "ladung_pv_kwh"):
        "Teilmenge von ladung_kwh — zusätzlich addiert wäre es die "
        "Doppelzählung aus #298 (14 + 9,24 = 23,24 statt 14)",
    ("wallbox", "ladung_netz_kwh"): "Teilmenge von ladung_kwh, s. ladung_pv_kwh",
    ("e-auto", "ladung_pv_kwh"): "Teilmenge der Ladung, s. wallbox/ladung_pv_kwh",
    ("e-auto", "ladung_netz_kwh"): "Teilmenge der Ladung, s. wallbox/ladung_pv_kwh",
    ("speicher", "ladung_netz_kwh"):
        "Teilmenge von ladung_kwh — sonst Doppelzählung für Arbitrage-Anwender",
    ("waermepumpe", "heizenergie_kwh"):
        "THERMISCH (~ Strom × COP), nicht elektrisch — gehört nicht in die "
        "Energiebilanz, nur in die JAZ-Rechnung",
    ("waermepumpe", "warmwasser_kwh"): "thermisch, s. heizenergie_kwh",
    # N-391: der gemeinsame Wärmemengenzähler — thermisch wie seine beiden
    # Achsen. Er ist zusätzlich der Gesamtwert ÜBER ihnen (D1); stünde er in der
    # Energiebilanz, zählte dieselbe Wärme zweimal.
    ("waermepumpe", "waerme_kwh"): "thermisch, s. heizenergie_kwh",
}

# #263 — die gemessenen Betriebsart-Zähler, aus zwei verschiedenen Gründen:
#
# * **Strom je Betriebsart ist eine Teilmenge** von `stromverbrauch_kwh` —
#   dieselbe Klasse wie `wallbox/ladung_pv_kwh` darüber. Als eigener
#   Komponenten-Beitrag stünde der Verbrauch der Wärmepumpe in der Tages- und
#   Stundenbilanz doppelt (einmal gesamt, einmal je Betriebsart).
#   ⭐ **Seit dem 15.09.2026 gilt dieser Satz mit einer Bedingung (R-1/K3 Regel
#   4, N-486): „Teilmenge von" setzt voraus, dass es die Menge gibt.** Ist weder
#   ein Gesamtzähler noch eine feine Achse zugeordnet, tragen die
#   Betriebsart-Zähler die Menge selbst und liefern dann sehr wohl einen
#   Beitrag (`komponenten_beitraege.investition_beitraege`). Der Eintrag bleibt
#   hier stehen, weil er den **Regelfall** beschreibt — und weil ihn der
#   Wächter `test_snapshot_felder_sot_konformitaet.py` in der Lage ohne
#   Gesamtzähler ohnehin als „gedeckt" sieht.
# * **Nutzenergie je Betriebsart ist thermisch**, nicht elektrisch — dieselbe
#   Klasse wie `heizenergie_kwh`.
#
# ⚠ Der Monatswert entsteht davon unberührt: er kommt über die Vorschläge des
# Monatsabschlusses (HA-Statistik · MQTT · Connector) in die IMD-Zeile, nicht
# über den Komponenten-Beitrag. Gesnapshottet werden die Zähler weiterhin —
# nur eben ohne eigenen Eintrag in der Energiebilanz.
_SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG.update({
    **{
        ("waermepumpe", _feld):
            "Teilmenge von stromverbrauch_kwh (#263) — als eigener Beitrag "
            "stünde der WP-Verbrauch in der Tagesbilanz doppelt"
        for _feld in _BETRIEBSART_STROM_FELDNAMEN
    },
    **{
        ("waermepumpe", _feld):
            "THERMISCH, nicht elektrisch (#263) — s. heizenergie_kwh"
        for _feld in _BETRIEBSART_NUTZENERGIE_FELDNAMEN
    },
})

def kumulative_zaehler_felder_je_typ() -> dict[str, tuple[str, ...]]:
    """Je Investitionstyp die kWh-Felder, die als **kumulativer Zähler**
    stündlich gesnapshottet werden — abgeleitet aus `INVESTITION_FELDER`.

    Regel: jedes Feld mit Energie-Einheit, außer es steht in
    `_SNAPSHOT_AUSNAHMEN`. Dazu die Kompatibilitäts-Namen aus
    `_SNAPSHOT_KOMPATIBILITAET`. Bei `sonstiges` werden die Kategorien
    (erzeuger/verbraucher/speicher) vereinigt — welche Felder ein konkretes
    Gerät führt, entscheidet erst `get_felder_fuer_sonstiges`.

    Die Reihenfolge ist stabil (Registry-Reihenfolge, dann Kompatibilität),
    damit Proben sie vergleichen können.
    """
    out: dict[str, tuple[str, ...]] = {}
    for typ, felder in INVESTITION_FELDER.items():
        listen = (list(felder.values()) if isinstance(felder, dict) else [felder])
        namen: list[str] = []
        for liste in listen:
            for f in liste:
                feld = f["feld"]
                if einheit_klasse(FELD_EINHEITEN.get(feld)) != "energie":
                    continue
                if (typ, feld) in _SNAPSHOT_AUSNAHMEN:
                    continue
                if feld not in namen:
                    namen.append(feld)
        for feld in _SNAPSHOT_KOMPATIBILITAET.get(typ, ()):
            if feld not in namen:
                namen.append(feld)
        if namen:
            out[typ] = tuple(namen)
    return out

def stand_felder() -> frozenset[str]:
    """Die Felder, deren Wert ein **Stand** ist und keine Menge — abgeleitet
    aus `INVESTITION_FELDER` über den Marker ``stand: True``.

    **Warum es diese Unterscheidung gibt (F-58, 21.08.2026).** Die
    Snapshot-Schiene holt jeden gemappten Zähler über
    `ha_statistics_service.get_value_at`, und das nimmt bei einem Sensor mit
    `has_sum` **ausschließlich HAs `sum`** — die reset-bereinigte
    Verbrauchssumme seit Aufzeichnungsbeginn. Das ist für eine **Flussgröße**
    richtig und bewusst so entschieden (v3.25.18, Issue #184): ein
    utility_meter mit Tagesreset hat in `state` den Tageswert, nur `sum` ist
    die Lebensdauer-Zahl.

    Für eine **Bestandsgröße** ist dieselbe Wahl falsch. Der Zählerstand eines
    Gas-, Wasser- oder Ölzählers ist die Zahl, die auf dem Zähler steht; sie
    steht in `state`. Ein Melder sah 90 m³, wo sein Sensor 47,360 m³ meldete —
    und wir haben ihm zunächst geantwortet, eedc zeige „genau die Zahl, die
    dein Sensor meldet".

    ⚠ **Der zweite Zweig war genauso falsch:** ohne `has_sum` verlangt
    `_value_at_wert` eine Energie-Einheit und liefert sonst `None`. Ein
    Wasserzähler in m³ bekam damit **gar keinen** Snapshot. Ein Stand-Feld
    braucht beides nicht — es liest `state` und rechnet nichts um.

    ⛔ **Was hier bewusst NICHT steht: `wp_starts_anzahl` und
    `wp_betriebsstunden`.** Sie sind zwar ebenfalls Bestandsgrößen, aber ihr
    Snapshot wird **nur differenziert** (`aggregate_day`), und der
    Lebensdauer-Stand kommt aus einem eigenen Leser
    (`snapshot/reader.get_counter_lifetime`, HA-Live-State zuerst). Sie
    umzustellen hieße, eine bestehende Reihe von `sum` auf `state` zu
    verschieben — bei einer WP, deren Gerätezähler weit über HAs
    Aufzeichnungssumme liegt, ergäbe das an genau einem Tag einen Sprung in
    der Größe des Lebensdauer-Zählers. `_get_counter_deltas_for_day` kappt
    **negative** Deltas, positive nicht. Das ist als Nebenfund geführt, nicht
    als Auslassung.
    """
    namen: set[str] = set()
    for felder in INVESTITION_FELDER.values():
        listen = (list(felder.values()) if isinstance(felder, dict) else [felder])
        for liste in listen:
            for f in liste:
                if f.get("stand"):
                    namen.add(f["feld"])
    return frozenset(namen)

#: Die Stand-Felder als Konstante — einmal abgeleitet, überall dieselbe Antwort.
STAND_FELDER: Final[frozenset[str]] = stand_felder()

def ist_stand_feld(feld: str) -> bool:
    """Ist der Wert dieses Feldes ein **Stand** (Bestandsgröße)?

    Mit Innengeräte-Auflösung wie jede andere Namens-Whitelist — ein Feld-Key
    kann das Suffix `-<id>` tragen (`basis_feld_key`).
    """
    if not feld:
        return False
    return basis_feld_key(feld) in STAND_FELDER
