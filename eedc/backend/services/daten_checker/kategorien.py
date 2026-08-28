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
    # #349 (OliS2811): Messwerte einzelner Komponenten (InvestitionMonatsdaten)
    # für einen Monat, dessen Zählerzeile (Monatsdaten) gelöscht wurde. Der
    # Monat verschwindet damit aus allen Listen — die Gerätewerte bleiben aber
    # stehen und weisen einen erneuten Import ab („Felder durch manuell
    # gepflegte Werte geschützt"), ohne dass der Anwender sehen kann, woran es
    # liegt. Trägt die Reparatur-Action `geraetewerte_loeschen`: ohne sie wäre
    # es ein Hinweis, den niemand auflösen kann (die Zeile, über die man den
    # Monat sonst aufräumt, existiert ja gerade nicht) — die P-6-Falle.
    GERAETEWERTE_OHNE_MONATSZEILE = "geraetewerte_ohne_monatszeile"
    # Issue #135: Deckungsgrad kumulativer kWh-Zähler für Energieprofil
    ENERGIEPROFIL_ABDECKUNG = "energieprofil_abdeckung"
    # Issue #134: Drift-Schutz Publisher (HA-Automation) ↔ Konsument (field_definitions.py)
    MQTT_TOPIC_ABDECKUNG = "mqtt_topic_abdeckung"
    # N-341 (28.08.2026): Ein zugeordneter Zähler springt zurück — ein
    # „…heute"-Feld statt eines fortlaufenden Standes. eedc liefert für so einen
    # Zähler bewusst KEINEN Wert (`reader.delta`), und ohne diesen Hinweis sieht
    # der Anwender nur ein leeres Feld. Der Daten-Checker rät beim **Anlegen**
    # längst zum richtigen Sensor (`sensoren.py`, „Zurücksetzen nie") — wer den
    # falschen bereits zugeordnet hat, erfuhr es nie. Dieselbe Klasse wie W-18:
    # ein erkannter Zustand, der nur als Logzeile existierte.
    ZAEHLER_RUECKSPRUNG = "zaehler_ruecksprung"
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
    # N-186: gespeicherte Tage, in denen Wallbox UND E-Auto denselben
    # Ladevorgang tragen — die Hinterlassenschaft von F-14 (#356). Der Fix hat
    # die Regel für NEUE Tage gebaut; bereits geschriebene `komponenten_kwh`
    # bleiben stehen und zeichnen die Ladung weiter doppelt.
    # ⚠ Bewusst ein Checker mit Reparatur-Knopf und **keine Start-Migration**
    # ([[feedback_kein_grosser_heiler_knopf]]): der Lauf überschreibt Tageswerte
    # und muss eine bewusste Entscheidung des Anwenders bleiben.
    EMOB_DOPPELZAEHLUNG_TAGE = "emob_doppelzaehlung_tage"
    # #331 Phase 4: Ein Fahrzeug trägt einen gepflegten Verbrenner-Verbrauch
    # (`eigener_verbrauch_l_100km`), aber eedc kann den elektrischen Anteil
    # nicht bestimmen — weder ist der monatliche Fahrverbrauch (`verbrauch_kwh`)
    # erfasst noch ein `elektrischer_fahranteil_prozent` gepflegt. Dann rechnet
    # eedc **still 100 % elektrisch**, und Ersparnis wie CO₂ fallen zu gut aus.
    # Das ist genau die Sorte stiller Annahme, die diese Diagnose-Linie
    # sichtbar machen soll — melden und erklären, kein „Akzeptiert"-Knopf und
    # keine stille Datenänderung.
    PHEV_ANTEIL_UNBESTIMMT = "phev_anteil_unbestimmt"
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
    # v3.45.9: Alt-Tage, die VOR dem Batterie-Vorzeichen-Fix (v3.45.7/8, SoT
    # batterie_kw_spalte: ENTLADUNG positiv) aggregiert wurden, tragen das
    # gespeicherte Batterie-Tagesnetto noch in vertauschter Richtung. Erkennung
    # per Daten-Signal: gespeichertes Netto (summe_batterie_netto_kwh aus
    # TagesZusammenfassung.komponenten_kwh) gegen einen frischen HA-LTS-Read mit
    # aktueller Konvention — entgegengesetztes Vorzeichen bei beidseitig
    # nennenswertem Betrag = Alt-Tag. Bietet einen MANUELLEN Re-Aggregations-
    # Trigger (Einzeltag + Bereich, max 31 Tage/Lauf) — NIE als Start-Migration
    # (feedback_migration_startup_kein_http: der v3.45.7-Versuch hat das Add-on
    # gebrickt). Nur HA-LTS-Modus; Standalone hat keine Referenz zum Vergleich.
    BATTERIE_VORZEICHEN_HISTORIE = "batterie_vorzeichen_historie"
    # N-239 (2026-08-12): Anlagen mit MEHREREN Speichern, deren Historie vor
    # dem Fix aggregiert wurde. Bis dahin nahm `_get_soc_history` den ERSTEN
    # gemappten SoC-Sensor und brach ab — `soc_prozent` trug den Ladestand
    # eines Geräts, während Vollzyklen, SoC-Hübe, Potential-Heatmap und
    # Sizing-Kalibrierung ihn als anlagenweit lasen. Erkennung ohne HA-Read
    # und ohne Heuristik: ≥ 2 Speicher mit gemapptem SoC-Sensor UND Stunden
    # mit `soc_je_speicher IS NULL` — die Spalte gibt es erst seit dem Fix,
    # ihr Fehlen IST die Signatur. Aktion = dieselbe Neu-Aggregation wie beim
    # Vorzeichen-Befund, user-getriggert, NIE als Start-Migration
    # (feedback_migration_startup_kein_http, feedback_kein_grosser_heiler_knopf).
    # Anlagen mit EINEM Speicher tauchen hier nie auf — dort war die alte
    # Rechnung wertgleich (s. `anlagen_soc_prozent`).
    SOC_NUR_EIN_SPEICHER = "soc_nur_ein_speicher"
    # v4.0.4 (Nachlauf v4.0.3): Tage, an denen ein Zähler zugeordnet ist und
    # HA-Statistics einen Wert liefert, die gespeicherte Tageszeile aber leer
    # bzw. 0 ist. Genau die Lücke, in der drei Melder nach dem v4.0.3-Fix
    # hängenblieben: die Zuordnung ist geheilt, die Historie bleibt leer, und
    # „Zähler-Abdeckung: OK" ist technisch richtig, für den Anwender aber
    # irreführend. Erkennung per Daten-Signal (frischer HA-LTS-Read gegen die
    # gespeicherte TagesZusammenfassung), Aktion = Bereichs- + Einzeltag-
    # Reparatur — user-getriggert, NIE als Start-Migration
    # (feedback_migration_startup_kein_http, feedback_kein_grosser_heiler_knopf).
    # Abgrenzung: PV auf bestehenden Tageszeilen gehört DATENQUELLE_DRIFT —
    # kein zweiter Turm über denselben Sachverhalt.
    TAGESWERTE_FEHLEN = "tageswerte_fehlen"
    # v4.0.10 (N-161): eedc und Home Assistant laufen in verschiedenen Zeitzonen.
    # eedc mischt zwei Zeitwelten — 28 Stellen rechnen hart in
    # `ZoneInfo("Europe/Berlin")`, 85 Stellen nehmen die Systemzeit
    # (`date.today()`). Solange der Container auf der HA-Zeitzone steht, sind
    # beide deckungsgleich; auf UTC — dem Docker-Default ohne `TZ` — driften sie
    # **an der Tageskante**, also genau dort, wo Tageszeilen entstehen.
    # Verglichen wird der aktuelle **UTC-Offset**, nicht der Zonenname: Wien,
    # Zürich und Amsterdam teilen sich Berlins Offset, ein Namensvergleich
    # meldete dort einen Fehler, den es nicht gibt. Ohne erreichbares HA
    # schweigt der Check (kein Hinweis, den niemand auflösen kann — P-6).
    # Bereits schief gespeicherte Tage heilt er NICHT und behauptet das auch
    # nicht: er misst den Zustand von jetzt.
    ZEITZONE_ABWEICHUNG = "zeitzone_abweichung"
    # Konzept-Wirtschaftlichkeit §8.1, Regel 1: dieselbe Bezeichnung taucht an
    # einer Komponente in mehreren Monaten als sonstige Position auf. Das Modell
    # verlagert die Entscheidung „einmalig oder wiederkehrend" vom Code zum
    # **Erfassungsort** (§2) — genau dort kann ein Anwender es verfehlen, und
    # nur dort ist es erkennbar. Erkannt wird die **Wiederholung**, nie die
    # Bedeutung eines Wortes: aus „Restwert" oder „Förderung" auf einen
    # Kapitalzufluss zu schließen wäre eine erfundene Regel über Freitext
    # (§8.1, ⛔-Kasten; dieselbe Klasse wie das verworfene Feld `art`).
    POSITION_WIEDERKEHREND = "position_wiederkehrend"
    # §8.1, Regel 2: der Jahresbetrag ist an der Komponente gepflegt **und**
    # derselbe Posten wird zusätzlich monatlich gebucht. Im Monatsabschluss
    # gehört nur die **Abweichung** vom Plan (§2/3) — sonst zählt der Betrag
    # doppelt. Beide Regeln sind Hinweise, keine Fehler, und beide nennen einen
    # Weg zur Behebung statt eines „Akzeptiert"-Knopfs
    # ([[feedback_daten_checker_kein_akzeptiert]]).
    POSITION_DOPPELERFASSUNG = "position_doppelerfassung"
    # #263 K-2: Eine Split-Klimaanlage (`wp_art = luft_luft`) heizt und kühlt
    # über DENSELBEN Zähler. Ohne zugeordneten Modus-Sensor kann eedc nicht
    # sagen, welcher Teil des Stroms ins Heizen ging — die Aufteilung ist aus
    # keinem vorhandenen Feld rekonstruierbar. INFO, nie WARNING: das Feld ist
    # optional, ohne es rechnet alles weiter wie bisher, nur ohne Aufteilung.
    #
    # ⚠ **Nur bei `luft_luft`, obwohl das FELD jeder Wärmepumpe angeboten wird**
    # (Konzept §7 E-E). Das ist kein Widerspruch, sondern dieselbe Trennlinie
    # wie bei F-41: *Messbarkeit hängt an der Bauart, Bewertbarkeit an der
    # Pflege.* Ob ein Gerät überhaupt kühlen kann, ist Bauart — eine
    # Luft-Wasser-Wärmepumpe bekäme sonst einen Hinweis auf eine Aufteilung,
    # die sie nicht hat. Wer trotzdem eine Kühlfunktion hat, findet das Feld
    # auf der Zuordnungs-Fläche.
    KLIMA_MODUS_SENSOR = "klima_modus_sensor"
    # #377 / N-294 (D3, 22.08.2026): Ein Zählerstand ist eine BESTANDSgröße und
    # läuft nicht rückwärts. Fällt er doch, ist nicht die Menge negativ — die
    # **Reihe** ist gebrochen: Zähler getauscht ohne Stilllegung, Sensor
    # ersetzt, oder der gemischte Fall aus Sensor und Handeingabe.
    #
    # **Eigene Kategorie, nicht MONATSDATEN_PLAUSIBILITAET** (Entscheid Gernot
    # 22.08.): Der Bruch hat mit der Monatszeile nichts zu tun — er kann
    # zwischen zwei Stunden-Snapshots liegen, und die Kategorie trägt außerdem
    # die beiden anderen Zähler-Aussagen (gar keine Quelle, auf inaktiv
    # gesetzt), die auch keine Monatsdaten-Fragen sind.
    #
    # ⛔ **Ohne Reparatur-Action, und das ist der Punkt** (Konzept #377 §4):
    # eedc kann den Bruch nicht heilen, ohne zu raten, welcher der beiden
    # Stände „richtig" ist. Es gibt einen Weg, und der ist eine Entscheidung
    # des Anwenders — **erklären und den Weg danebenstellen, nicht heilen**
    # ([[feedback_kein_grosser_heiler_knopf]] ·
    # [[feedback_daten_checker_kein_akzeptiert]]).
    ZAEHLERSTAND_REIHE = "zaehlerstand_reihe"
    # Discussion #394 (gruaGit, 23.08.2026): Der Monatsdurchschnitts-Benzinpreis
    # aus dem EU Weekly Oil Bulletin fehlt in einer Monatszeile. Er ist die
    # Grundlage des E-Auto-Alternativvergleichs (Fortschritt, kumulierte
    # Ersparnis) — fehlt er, rechnet die Kette still mit dem Modellwert
    # (Investitions-Parameter bzw. 1,65 €/L) weiter, und im Monatsabschluss
    # steht ein leeres Feld ohne Erklärung.
    #
    # ⭐ **MIT Reparatur-Action, anders als ZAEHLERSTAND_REIHE darüber:** Hier muss
    # nichts geraten werden — die Wochenpreise sind öffentlich, das
    # Nachpflegen ist eindeutig, und der Pfad existiert seit Etappe 3d
    # (RepairOperationType.KRAFTSTOFFPREIS_BACKFILL). Er war nur von nirgends
    # aus erreichbar außer über die Reparatur-Werkbank.
    VERGLEICHSPREIS_FEHLT = "vergleichspreis_fehlt"


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

# Ziel aller „hier zuordnen"-Verweise. Der frühere Sensor-Mapping-Wizard ist mit
# v4.0.0 durch die Datenquellen-Fläche abgelöst; `/einstellungen/sensor-mapping`
# leitet zwar um (`routeManifest.ts`), stand aber weiter als sichtbarer Link in
# den Meldungen. Eine Konstante, damit die sechs Fundstellen nicht wieder
# auseinanderlaufen.
LINK_DATENQUELLEN = "/einstellungen/datenquellen"

# Ziel der Connector-Hinweise (F-51, #390). Der Ausweg bei fehlenden Snapshots
# ist „Jetzt ablesen" im Geräte-Connector-Assistenten — der liegt unter
# Integration → Import-Assistenten, NICHT auf der Datenquellen-Fläche. Dorthin
# zeigte der Hinweis bis v4.0.22 und ließ den Melder ohne Weg stehen.
LINK_INTEGRATION = "/einstellungen/integration"

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
