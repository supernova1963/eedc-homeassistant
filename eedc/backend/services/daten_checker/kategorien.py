"""
Daten-Checker — Enums, Dataclasses & gemeinsame Labels.

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ─── Enums & Dataclasses ────────────────────────────────────────────────────

class CheckSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    OK = "ok"


class CheckKategorie(str, Enum):
    STAMMDATEN = "stammdaten"
    STROMPREISE = "strompreise"
    INVESTITIONEN = "investitionen"
    MONATSDATEN_VOLLSTAENDIGKEIT = "monatsdaten_vollstaendigkeit"
    MONATSDATEN_PLAUSIBILITAET = "monatsdaten_plausibilitaet"
    # Issue #135: Deckungsgrad kumulativer kWh-Zähler für Energieprofil
    ENERGIEPROFIL_ABDECKUNG = "energieprofil_abdeckung"
    # Issue #134: Drift-Schutz Publisher (HA-Automation) ↔ Konsument (field_definitions.py)
    MQTT_TOPIC_ABDECKUNG = "mqtt_topic_abdeckung"
    # v3.24.1: Sensoren im Mapping, die nicht in HA-Long-Term-Statistics landen
    # (kein state_class) — Korrektur-Werkzeuge in der Datenverwaltung wirken
    # auf solche Sensoren nicht (Vollbackfill, Verlauf nachrechnen,
    # Per-Tag-Reaggregation lesen alle aus HA's LTS).
    SENSOR_MAPPING_LTS = "sensor_mapping_lts"
    # v3.25.x: Counter-Spikes im Tagesprofil (z. B. nach Update-Restarts mit
    # Off-by-one-Bug). Erkennt Stundenwerte, die physikalisch unmöglich sind
    # (> Anlagenleistung × 1.5). Behebung über "Tag neu aggregieren" oder
    # "Verlauf nachrechnen" — beide rufen seit v3.25.x intern Resnap auf.
    ENERGIEPROFIL_PLAUSIBILITAET = "energieprofil_plausibilitaet"
    # Etappe 3d P3: Felder mit ≥ 2 distinct sources im Audit-Log der letzten
    # 30 Tage. Hinweis-Charakter ohne Quittier-Knopf — Diagnose für die
    # Reparatur-Werkbank (P4). Memory-Linie feedback_daten_checker_kein_akzeptiert.md.
    PROVENANCE_CONFLICT = "provenance_conflict"
    # Etappe 4 v3.31.0: zeigt, welcher Datenquellen-Pfad für die
    # Energie-Aggregate aktiv ist (HA-LTS direkt vs Sensor-Snapshot-Fallback
    # vs Standalone-MQTT). Info-Charakter, transparent für den Anwender.
    DATENQUELLE_STATUS = "datenquelle_status"
    # Etappe 6 v3.31.1: Per-Tag-Drift zwischen TagesZusammenfassung-PV und
    # HA-LTS-Daily-Read. Pro betroffenem Tag ein eigener Eintrag mit
    # Reparatur-Action (reaggregate_day). Schließt die Anwender-Lücke aus
    # Etappe 4: bestehende Tage bleiben nach Update auf ihren alten
    # Mix-Source-Werten, ohne dieses Werkzeug sieht der Anwender das nicht.
    DATENQUELLE_DRIFT = "datenquelle_drift"
    # PR-Plausi v3.31.5 (rapahl-PN 2026-05-19): Performance Ratio > 1.05 oder
    # spez. Tagesertrag > kwp × 7 kWh über mehrere Tage hindurch — beides
    # physikalisch implausibel und typisches Symptom einer Doppelerfassung
    # (z. B. BKW-Sensor im WR-Smart-Meter schon enthalten + zusätzlich
    # gemappt). Diagnose statt stillem Cap — feedback_grenze_externe_daten_diagnose.
    PV_UEBER_ERFASSUNG = "pv_ueber_erfassung"
    # Wallbox/E-Auto Phase 2a aus KONZEPT-WALLBOX-EAUTO.md: wenn EAuto-
    # Investition UND Wallbox-Investition beide Heimladungs-Werte tragen,
    # messen sie häufig denselben Stromfluss aus zwei Perspektiven. Die
    # Read-Sites wählen die Quelle strukturell (Wallbox vorhanden → Wallbox),
    # die einmalige Migration konsolidiert Bestände in den Wallbox-Slot. Was
    # die Migration NICHT verlustfrei auflösen kann (Total auf der einen,
    # PV-Split nur auf der anderen Seite) bleibt stehen — dieser Diagnose-
    # Eintrag lenkt den Anwender dann auf eine bewusste Entscheidung: nur eine
    # Quelle pflegen.
    EMOB_POOL_PFLEGE = "emob_pool_pflege"
    # Sensor-Mapping-Einheit (mameier1234 #674 + #200): prüft Leistung↔Energie
    # in BEIDE Richtungen über ALLE gemappten Slots, einheiten-getrieben aus
    # field_definitions (FELD_EINHEITEN). Energie-Sensor (kWh) in einem
    # Leistungs-Slot (W) → der Zählerstand wird als Momentanleistung gelesen
    # (7130 kWh → 7130 W), der Live-Hausverbrauch klemmt auf 0 (#674, ERROR).
    # Leistungssensor (W) in einem kWh-Slot → state-Differenz ist keine kWh
    # (#200, WARNING; Laufzeit fällt auf Trapez-Integration zurück). Nur die
    # eindeutig gefährliche Leistung/Energie-Verwechslung; %/°C/Preis/km bewusst
    # ausgenommen (legitime Einheiten-Varianten → Fehlalarm-Risiko).
    SENSOR_MAPPING_EINHEIT = "sensor_mapping_einheit"


@dataclass
class CheckErgebnis:
    kategorie: str
    schwere: str
    meldung: str
    details: Optional[str] = None
    link: Optional[str] = None
    # Etappe 6 v3.31.1: optionale Inline-Reparatur-Action.
    # action_kind="reaggregate_day" + action_params={"anlage_id", "datum"}
    # → Frontend rendert Knopf, der `/api/energie-profil/{id}/reaggregate-tag`
    # ruft. Alle anderen Kategorien lassen diese Felder None.
    action_kind: Optional[str] = None
    action_params: Optional[dict] = None
    action_label: Optional[str] = None
    # IA-V4 #243: optionale Komponenten-Zuordnung. Nur komponenten-bezogene
    # Checks (Stammdaten/Monatsdaten/Energieprofil-Abdeckung/E-Mob-Pflege je
    # Investition) füllen das Feld, damit der Komponenten-Hub seine Befunde
    # sauber je Gerät filtern kann. Anlagen-aggregierte Werte-Anomalien
    # (Plausibilität, Drift, Provenance) lassen es bewusst None — die gehören
    # in den Reparatur-Pfad, nicht in den Hub.
    investition_id: Optional[int] = None


@dataclass
class MonatsdatenAbdeckung:
    vorhanden: int
    erwartet: int
    prozent: float


@dataclass
class DatenCheckResult:
    anlage_id: int
    anlage_name: str
    ergebnisse: list[CheckErgebnis]
    zusammenfassung: dict
    monatsdaten_abdeckung: Optional[MonatsdatenAbdeckung] = None


# ─── Konstanten / Labels ───────────────────────────────────────────────────

# Sprechende Kurz-Labels für Provenance-Quellen (Daten-Checker Detail-Zeile,
# Safi105 #301). Die technischen Source-Strings aus core/source_priority.py
# (z. B. "manual:form", "external:cloud_import:fronius_solarweb") sollen dem
# Anwender als „manuell" / „Cloud-Import (Fronius)" begegnen.
def _quelle_label(source: str) -> str:
    s = (source or "").strip()
    if not s:
        return ""
    if s == "repair":
        return "Reparatur"
    if s.startswith("manual:"):
        return "manuell"
    if s.startswith("external:ha_statistics"):
        return "HA-Statistik"
    if s.startswith("external:cloud_import:"):
        provider = s.split(":")[-1].split("_")[0].capitalize()
        return f"Cloud-Import ({provider})"
    if s.startswith("external:"):
        return s.split(":", 1)[1].replace("_", " ")
    return s
