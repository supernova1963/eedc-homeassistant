# Konzept: Prognosequellen-Wahl pro Anlage

> **Strenger Grundsatz:** Diese Doku enthält **keinerlei Vergleich** zwischen
> EEDC, Solcast und Tom-HA-SFML. Versprochen wurde explizit, nicht gegen
> „rolling" zu vergleichen. Das Konzept beschreibt ausschließlich die
> Auswahl-Funktionalität — nicht eine Bewertung.

## Kernidee

Drei nebeneinander angebotene PV-Prognosequellen pro Anlage:

- **EEDC-optimiert** — OpenMeteo × Lernfaktor (Default, läuft überall)
- **Solcast pur** — Solcast direkt, ohne Lernfaktor
- **SFML (Tom-HA Solar Forecast ML)** — direkt aus HA-Integration

Auswahl pro Anlage, Default = EEDC. Bei Datenausfall der gewählten Quelle
automatischer Fallback auf EEDC, neutral kommuniziert. Kein Marketing-
Vergleich, keine Empfehlungs-Logik, keine MAE-Tabellen gegen externe
Quellen.

## Motivation

Heute hat eedc eine implizite Quelle (EEDC = OpenMeteo × Lernfaktor).
Solcast existiert als optionale Erweiterung, kann pro Anlage als Lernfaktor-
Eingabe gewählt werden (`prognose_basis = "solcast"`). User mit anderer
Präferenz — etwa Anwender, die SFML bereits in ihrer HA installiert
haben — sollen die Wahl haben, ohne dass eedc behauptet, eine Quelle sei
„besser" als eine andere.

Standalone-User brauchen weiterhin eine Quelle, die ohne HA-Integrationen
funktioniert. Daher bleibt EEDC der Default — es funktioniert überall,
sofort, ohne Konfiguration.

## Verfügbarkeitsmatrix

| Quelle | HA-Add-on | Standalone | Voraussetzung | Default? |
|---|---|---|---|---|
| EEDC-optimiert | ✓ | ✓ | nichts | **ja — BestMatch** |
| Solcast pur | ✓ via HA-Sensor | ✓ via API-Token | Sensor oder Token | wählbar |
| SFML (Tom-HA) | ✓ via HA-Integration | — | `solar_forecast_ml` installiert | wählbar |

Standalone-Logik: SFML im Picker grayed-out mit Tooltip („nur in HA-Add-on
verfügbar — SFML basiert auf einer HA-Integration, kein API-Zugriff
außerhalb HA"). Solcast pur funktioniert standalone via API-Token.

## Setting auf Anlagenebene

**Neues Feld:** `Anlage.prognose_quelle: enum {auto, eedc, solcast, sfml}`,
default `auto` → resolved zu `eedc`.

### Eindeutige Quellen-Definition

| Quelle in der UI | Bedeutung |
|---|---|
| EEDC-optimiert | OpenMeteo × Lernfaktor — eine Eingabe, eine Logik |
| Solcast pur | Solcast direkt, **ohne** Lernfaktor |
| SFML | SFML direkt, ohne Lernfaktor |

### Bestehendes Feld `prognose_basis` wird obsolet

Heute ist `Anlage.prognose_basis` zweideutig — kann `"openmeteo"` oder
`"solcast"` sein, beides als Eingabe für den Lernfaktor. In der neuen
Architektur:

- Der Lernfaktor lebt nur noch auf OpenMeteo. Eine Eingabe, eine
  Berechnung. Vereinfacht den Code an drei Stellen
  (`live_wetter.py:_get_lernfaktor_detail`, Berechnungen in
  `aussichten.py`, Snapshot-Schreiben in `live_wetter.py`).
- Wer früher Solcast als EEDC-Basis hatte, bekommt jetzt **Solcast pur**
  als eigenständige Quelle.

**Migrations-Pfad:** Bei Anlagen mit `prognose_basis = "solcast"`
automatisch `prognose_quelle = "solcast"` setzen, `prognose_basis` als
Spalte deprecated und im selben Release entfernen.

## Solcast — Modus folgt der Umgebung

Der Solcast-Zugriffsmodus wird **nicht** vom User gewählt, sondern
automatisch nach Umgebung gesetzt — der Grund ist die Solcast-Quota-
Limitierung:

| Umgebung | Modus | Begründung |
|---|---|---|
| HA-Add-on | **Immer** HA-Integrationssensoren | HA-Integration managt Quota intelligent (Caching, Batching). Direkter API-Call aus eedc würde unnötig Quota fressen. Funktioniert mit Solcast-Free und -Paid identisch. |
| Standalone | **Immer** API-Token (Direct-Fetch) | Keine HA verfügbar. Token muss eingerichtet werden, eedc managt selbst Caching/Quota-Schonung. Funktioniert ebenfalls mit Free und Paid. |

UI-Konsequenz: Im Settings-Picker ist „Solcast" nur als *eine* Option
sichtbar. Backend wählt Modus automatisch, im Settings-Block werden
umgebungs-spezifische Felder gezeigt:

- Add-on: Sensor-IDs der HA-Integration (typischerweise schon gemappt)
- Standalone: API-Token-Eingabefeld + Status

**Voraussetzung Standalone:** User hat ein Solcast-Konto (Free oder Paid)
und gibt seinen Token ein. Solcast-Free liefert ~10 Calls/Tag, das reicht
knapp für täglich vier Updates — eedc cached aggressiv.

## SFML-Connector

**Integration:** `solar_forecast_ml` (HACS-Custom-Component, im User-HA
installiert mit `config_entry_id = 01KMA6CWKS041H5MFJ4DTDED84`). Keine
externe API, kein Token — reine HA-Sensor-Reads über die schon vorhandene
HA-Verbindung von eedc.

### Verwendete Sensoren (Tagesgranularität)

| Zweck | Sensor-ID | Einheit |
|---|---|---|
| Tagesprognose heute | `sensor.prognose_heute` | kWh |
| Heute-Rest (verbleibend) | `sensor.prognose_heute_rest` | kWh |
| Tagesprognose morgen | `sensor.prognose_morgen` | kWh |
| Tagesprognose übermorgen | `sensor.prognose_ubermorgen` | kWh |
| Nächste Stunde | `sensor.solar_forecast_ml_prognose_nachste_stunde` | kWh |

**Stündliches Profil:** SFML hat eine Option `hourly` (default `false`).
Wenn aktiviert, liefert die Integration zusätzliche Stunden-Sensoren. Für
die erste Connector-Version reichen die Tageswerte oben — Stundenprofil
als spätere Erweiterung, falls SFML-User es brauchen.

**Nicht verfügbar in SFML:** p10/p90-Konfidenzbänder. SFML liefert nur
Punkt-Schätzungen. UI zeigt einfach kein Band, nur den Mittelwert.

**Standalone:** SFML-Connector läuft nicht, weil keine HA-Verbindung. Der
Resolver liefert dann „EEDC" automatisch (Fallback).

### Fallback bei Sensor-unavailable

Bei Status `unavailable`, fehlendem State oder Stale-Werten (>1 h alt) →
automatisch EEDC verwenden. Im Frontend kleiner neutraler Hinweis: „SFML
liefert aktuell keine Daten, EEDC aktiv". Keine Wertung, keine MAE-
Vergleiche, kein „besser oder schlechter".

## Backend-Architektur

### Resolver

**Neuer Service** `services/prognose_router.py`:

```python
async def resolve_prognose_quelle(
    anlage: Anlage,
    use_case: str = "default",
) -> tuple[Quelle, dict]:
    """
    Liefert die effektive Quelle und ihre Daten für eine Anlage.

    - Liest Anlage.prognose_quelle (auto → eedc)
    - Prüft Verfügbarkeit (Standalone, HA-Sensor-Status, etc.)
    - Bei Datenausfall: Fallback auf EEDC, Hinweis in der Response
    """
```

### Endpoint-Pflicht

Alle Prognose-konsumierenden Endpoints lesen über den Resolver, nicht
direkt OpenMeteo / Lernfaktor / Solcast. Use-Cases initial nicht
differenziert (eine Quelle pro Anlage über alle Use-Cases). Use-Case-
spezifische Wahl als spätere Erweiterung, falls Bedarf entsteht.

## Frontend-Architektur

### Settings-Block in Anlagen-Verwaltung

- Picker mit drei Optionen, Verfügbarkeits-Logik
- Add-on: SFML aktiv, Standalone: SFML grayed-out mit Tooltip
- Hilfetext pro Option, neutral formuliert

### Quellen-Anzeige in Live-Dashboard / Cockpit / Aussichten

- Unauffälliger Quellennamen-Hinweis im UI-Footer der Karte / des Charts:
  z. B. „Quelle: SFML"
- **Keine** Vergleichs-Tabelle, **kein** Empfehlungs-Banner, **keine**
  Decision-Support-UI

### Prognosen-Tab (Evaluierungs-Cockpit)

- Wird **nicht** um SFML- oder Solcast-Vergleichsspalten erweitert. Strikt
  Tom-HA-Versprechen-konform, kein Quellenvergleich.
- Läuft weiter mit optimiertem EEDC + Wetter-Stratifizierung als rein
  interne EEDC-Saison-Diagnose — siehe `KONZEPT-KORREKTURPROFIL.md`.
- Wird nach Abschluss der saisonalen Beobachtungsphase (~12 Monate)
  entfernt.

## Verhältnis zur Solcast-Evaluierungsphase

Mit Verabschiedung dieses Konzepts ist die **Solcast-Evaluierungsphase**
(`KONZEPT-SOLCAST.md`, Etappen 1–3 abgeschlossen v3.16.4–v3.16.8)
**formell beendet**. Die ursprünglich geplante Etappe 4 entfällt in der
bisherigen Form:

| Etappe-4-Punkt (alt) | In neuer Welt |
|---|---|
| Solcast als zusätzliche Linie im Live-Dashboard | ersetzt durch Quellenwahl: wer Solcast will, wählt Solcast als aktive Quelle |
| Solcast-Tagesprognose im Wetter-Widget | ersetzt durch Quellenwahl: aktive Quelle liefert Wetter-Widget-Wert |
| Solcast-Balken in Kurzfrist-Aussichten | ersetzt durch Quellenwahl |
| Blended Forecast (gewichteter Mittelwert) | gestrichen — User wählt eine Quelle, kein Mischen |
| MAE-Tracking als Decision-Support | gestrichen (Tom-HA-Versprechen) |

`KONZEPT-SOLCAST.md` wird beim Schreiben dieses Konzepts auf
„Etappen 1–3 abgeschlossen, Etappe 4 durch Quellenwahl-Konzept abgelöst"
gekennzeichnet.

## Inventur betroffener Stellen

Die Quellenwahl ist eine **systemische** Änderung — alle Stellen, die
heute direkt OpenMeteo/Lernfaktor (oder Solcast) konsumieren, müssen über
den zentralen Resolver gehen. Detaillierte Code-Liste gehört ins
Implementierungs-Issue, hier nur der Bereichs-Überblick:

### Anzeige-Pfade (Frontend)

| Pfad | Was wird gezeigt | Umstellung |
|---|---|---|
| Live-Dashboard (`LiveDashboard.tsx`) | Tagesverlauf-Chart, „Heute"-Kacheln, Stundenprofil | Quelle aus Resolver |
| Live-Wetter-Widget (`WetterWidget.tsx`) | Tagesprognose, Wetter-Symbol | Quelle aus Resolver |
| Cockpit Prognose-Karten | „Heute / Morgen"-KPIs | Quelle aus Resolver |
| Aussichten / Kurzfristig (`KurzfristTab.tsx`) | 14-Tage Chart + Tabelle | Quelle aus Resolver — Solcast nur 7 Tage, ab Tag 8 Fallback EEDC |
| Aussichten / Prognosen (`PrognoseVergleichTab.tsx`) | Übergangs-Diagnose | wird auf reine EEDC-Sicht umgestellt, kein Quellenvergleich |
| Aussichten / Langfristig (`LangfristTab.tsx`) | PVGIS-basierte Jahresprognose | bleibt unverändert — andere Quelle (PVGIS), nicht Teil der Wahl |
| Aussichten / Finanzen (`FinanzenTab.tsx`) | Finanzprognose | folgt Langfristig (PVGIS), nicht betroffen |
| Auswertung / Energieprofil (`EnergieprofilPrognose.tsx`, `PrognoseVsIst.tsx`) | SOLL/IST-Vergleich auf Stundenebene | bleibt EEDC-basiert für historische Konsistenz (siehe Architektur-Klärung unten) |

### Backend-Endpoints

| Endpoint | Heute | Umstellung |
|---|---|---|
| `/api/live/*` | OpenMeteo + Lernfaktor + SFML-Logging | Resolver liefert aktive Quelle; SFML-Logging-Code wird entfernt (Schritt 1 der Roadmap) |
| `/api/wetter/solar-prognose` | OpenMeteo + Lernfaktor (string-spezifisch) | Resolver |
| `/api/aussichten/kurzfrist` | OpenMeteo + Lernfaktor | Resolver |
| `/api/aussichten/prognosen` | Vergleichs-Tab — alle drei Quellen | wird zur reinen EEDC-Diagnose (Korrekturprofil) |
| `/api/aussichten/langfrist`, `/finanzen` | PVGIS | unverändert |
| `/api/cockpit/prognose` | OpenMeteo + Lernfaktor | Resolver |

### Service-Schicht (Berechnungen)

| Service | Rolle | Umstellung |
|---|---|---|
| `services/solar_forecast_service.py` | Tagesprognose mit Lernfaktor | bleibt — ist die EEDC-Quelle |
| `services/live_wetter.py:_get_lernfaktor_detail` | Lernfaktor-Berechnung | Eingabe nur noch OpenMeteo |
| `services/solcast.py` | Solcast-Roh-Daten | bleibt — wird aber nicht mehr als EEDC-Eingabe genutzt, nur als eigene Quelle |
| `services/prognose_router.py` (neu) | Resolver `(anlage) → Quelle, Daten` mit Fallback | neu zu bauen |
| `services/sfml_connector.py` (neu) | SFML-HA-Sensor-Read mit Schema-Mapping | neu zu bauen |

### Datenmodell + Migration

| Feld | Status heute | Konsequenz |
|---|---|---|
| `Anlage.prognose_quelle` | existiert nicht | neu — enum `{auto, eedc, solcast, sfml}`, default `auto` |
| `Anlage.prognose_basis` | `"openmeteo"` \| `"solcast"` | deprecated — Migration auf `prognose_quelle`, Spalte entfernen |
| `TagesEnergieProfil.pv_prognose_kwh` | EEDC-Snapshot pro Tag | bleibt — historische SOLL-Referenz |
| `TagesEnergieProfil.solcast_prognose_kwh` + `_p10/_p90` | Solcast-Snapshot | bleibt — internes Logging |
| `TagesEnergieProfil.sfml_prognose_kwh` | existiert bereits (Live-Mitschrift in `live_wetter.py:651-701`) | **entfernt** — Spalte droppen, Logging-Code entfernen. War nur Krücke zum Einblenden, ohne Verwendung. Sauberster Stand für Tom-HA-Versprechen. |
| `TagesEnergieProfil.pv_prognose_stundenprofil` | EEDC-Stundenprofil | bleibt |
| `TagesEnergieProfil.solcast_prognose_stundenprofil` | Solcast-Stundenprofil | bleibt |

### Architektur-Klärung — Snapshots vs. Anzeige

- **DB-Snapshots** in `TagesEnergieProfil.*_prognose_kwh` bleiben quellen-
  spezifisch (EEDC, Solcast separat) — historische Nachvollziehbarkeit
  garantiert auch dann, wenn der User später die Quelle wechselt.
- **Live-Anzeige** folgt der aktiven Quelle (Resolver liefert frische
  Daten).
- **SOLL/IST-Auswertung** in Auswertung / Energieprofil bleibt EEDC-
  basiert (`pv_prognose_kwh`-Snapshot) — sonst würden historische SOLL-
  Werte „rückwirkend ersetzt", wenn jemand auf Solcast wechselt. Keine
  erwünschte Eigenschaft.

### PDF-Reports

| Report | Prognose-Anteil | Umstellung |
|---|---|---|
| Jahresbericht (`pdf/builders/jahresbericht.py`) | SOLL/IST-Charts auf Tagesbasis | bleibt EEDC-basiert (analog Architektur-Klärung) |
| Anlagendokumentation | enthält Prognose-Snapshot | prüfen, dokumentieren |

### Was nicht betroffen ist

- PVGIS-Jahresprognose (Langfrist + Finanzen) — andere Quelle, nicht Teil
  der Wahl
- Energiefluss-Anzeige — nur IST-Daten, keine Prognose
- Community-Server / Benchmark — Solcast-Daten werden zwar mitgeschickt,
  aber als Hintergrund-Information, kein Quellenwahl-Pfad

## Reihenfolge der Umsetzung

1. **Cleanup `sfml_prognose_kwh`** (~halber Tag, Voraussetzung für sauberen
   Start): Spalte aus `TagesEnergieProfil` droppen, Logging-Code in
   `live_wetter.py:651-701` entfernen, dazugehörige Pydantic-Felder
   (`sfml_today_kwh`, `sfml_tomorrow_kwh`, `sfml_accuracy_pct`) ersatzlos
   raus. Migration berücksichtigt: bestehende Datenbestände schrumpfen
   sauber.
2. **Setting + Resolver** (~1 Woche): `prognose_quelle`-Feld, Resolver in
   einer zentralen Stelle, alle bestehenden Endpoints lesen über Resolver.
   Default `auto` → `eedc` heißt: heute keine Verhaltensänderung sichtbar.
   Migration `prognose_basis="solcast"` → `prognose_quelle="solcast"`,
   `prognose_basis`-Spalte entfernen.
3. **Solcast-API-Token-Modus** (~halbe Woche): Setting für Direct-API,
   Standalone-Fähigkeit hergestellt.
4. **SFML-Connector** (~1 Woche): HA-Sensor-Read der 5 Sensoren oben,
   Schema-Mapping, Fallback-auf-EEDC bei Sensor-unavailable.
5. **Frontend-Picker** (~halbe Woche): Settings-Block in Anlagen-
   Verwaltung, Verfügbarkeits-Logik, Quellennamen-Hinweis im
   Live-Dashboard / Cockpit / Aussichten.

**Trigger / Voraussetzungen:** Schritt 1 jederzeit als „Aufräum-Release"
möglich. Schritte 2+3 jederzeit möglich. Schritt 4 braucht nur, dass die
SFML-Integration installiert ist (im User-HA bereits gegeben, im Standalone
weglassen). Schritt 5 nach 2+4.

## Was nicht zu dieser Doku gehört

- **Korrekturprofil / EEDC-Optimierung:** siehe `KONZEPT-KORREKTURPROFIL.md`.
- **Diagnose-Werkzeuge** (stündl. MAE, Wetter-Stratifizierung): nur EEDC-
  intern zur Saison-Diagnose, gehört in Korrekturprofil-Doku.
- **Vergleiche zwischen Quellen:** explizit ausgeschlossen, siehe
  Tom-HA-Versprechen.
