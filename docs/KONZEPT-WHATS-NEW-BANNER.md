# Konzept: What's-new-Banner nach Update

> **Status: verworfen, ersetzt durch eine Pull-Variante in v3.24.5+** — eigene Hilfe-Seite *„Was ist neu"* unter `docs/WAS-IST-NEU.md`, sichtbar in der In-App-Hilfe-Sidebar (Kategorie *Einstieg*). Begründung: HA-Add-on-Nutzer sehen den Changelog ohnehin schon im Add-on-Store, GitHub-Releases haben einen eigenen — ein zusätzlicher Banner wäre die dritte Stimme zur selben Information („Meldungsorgie"). Pull statt Push spart außerdem die ganze localStorage-/Versionsvergleich-/Bestand-vs-Neuinstall-Mechanik. Dokument unten bleibt als Entscheidungs-Beleg erhalten.
>
> **Quelle der ursprünglichen Anfrage:** Discussion #130 (Safi105) Folge-Reply 2026-04-24
> **Konzept-Datum:** 2026-04-28 | **Verwerf-Datum:** 2026-04-29 | **Vorbereitung:** „Was ist neu seit v3.16?"-Tabelle in `BENUTZERHANDBUCH.md` als statische Vorlage (jetzt zur Detail-Seite `WAS-IST-NEU.md` ausgebaut)

## Motivation

Safi105 schrieb in Discussion #130 (nach der Zusage zur In-App-Hilfe):

> „Ausserdem ein Banner mit dem man nach einem Update auf neue Funktionen aufmerksam gemacht wird. Beim darauf klicken wird man dann zur neuen Funktion geleitet. Da es in letzter Zeit schon viel Neuerungen gab. Ist es schwierig hier den Überblick zu behalten."

Der Punkt ist berechtigt — auch der Add-on-Store-Changelog (rapahls Beobachtung in Issue [#40](https://github.com/supernova1963/eedc-homeassistant/issues/40)) zeigt bei schnellen Folge-Releases nur den ersten Changelog. EEDC braucht eine **anwender-zentrierte Sicht auf das, was sich seit der vorherigen genutzten Version geändert hat** — nicht den vollen technischen CHANGELOG.

Mit der In-App-Hilfe (#130, v3.24.0) und der „Was ist neu seit v3.16?"-Tabelle im `BENUTZERHANDBUCH.md` (v3.24.x Sweep) liegen die kuratierten Inhalte in der nötigen Form bereits vor. Der Banner ist die UI-Konsequenz daraus.

## Anforderungen

1. **Versionsbezogen** — der Banner zeigt die Highlights **seit der zuletzt vom Nutzer gesehenen Version**, nicht das aktuelle Release. Wer 3 Updates verpasst hat, soll alle drei Highlight-Sets sehen.
2. **Klickbar** — jeder Eintrag öffnet die zugehörige Funktion in der App (Deep-Link in Aussichten, Auswertung, Energieprofil-Seite usw.) oder die passende Hilfe-Sektion.
3. **Ein-Mal-Verhalten** — nach Schließen oder Anklicken aller Punkte verschwindet der Banner. Per-User-Persistenz (`localStorage`).
4. **Verfügbar im Hauptmenü** — auch wer den Banner geschlossen hat, soll die Liste später wieder öffnen können (z. B. „Hilfe → Was ist neu" oder ein kleiner Stern-Indikator in der Top-Navigation).
5. **Kuratiert, nicht generiert** — keine automatische Extraktion aus CHANGELOG.md. Die Highlights sind redaktionell auf Anwenderperspektive zugeschnitten (vgl. die „Was ist neu"-Tabelle vs. den vollen CHANGELOG).

## Datenquelle: kuratierte Highlights pro Release

Pro Release pflegt der Maintainer eine Liste mit:

```ts
type Highlight = {
  version: string         // z.B. "3.21.0"
  bereich: 'live' | 'cockpit' | 'auswertung' | 'aussichten' | 'einstellungen' | 'sensor-mapping' | 'hilfe'
  titel: string           // kurz, anwenderfreundlich
  beschreibung: string    // 1-2 Sätze
  link: { typ: 'route' | 'hilfe', target: string }
  icon?: string           // Lucide-Icon-Name
}
```

**Speicherort:** Statische TypeScript-Datei im Frontend (`eedc/frontend/src/data/highlights.ts`). Keine DB-Änderung, keine API. Die Liste wird beim Release zusammen mit dem Versions-Bump gepflegt — analog zur CHANGELOG-Pflege.

**Migration:** Die existierende „Was ist neu seit v3.16?"-Tabelle im `BENUTZERHANDBUCH.md` ist die initiale Befüllung — dort sind ~13 Highlights v3.16 → v3.24 mit Deep-Links bereits redaktionell vorbereitet.

## Auslöser & Persistenz

```ts
// localStorage Key
const KEY = 'eedc.lastSeenVersion'

// Beim App-Start
const lastSeen = localStorage.getItem(KEY)         // z.B. "3.20.0", null bei Neuinstallation
const current = APP_VERSION                         // aus version.ts
if (lastSeen !== current) {
  const neueHighlights = highlights.filter(
    h => isNewerOrEqual(h.version, lastSeen ?? '0.0.0') &&
         isNewerOrEqual(current, h.version)
  )
  // → Banner anzeigen mit neueHighlights, gruppiert nach Version
}
```

**Schließen:** Klick auf „Alles verstanden, danke" setzt `localStorage[KEY] = current`. Klick auf einen einzelnen Highlight-Link navigiert zur Funktion und markiert nur diesen Eintrag als gelesen — der Banner bleibt mit den verbleibenden Punkten sichtbar.

**Neuinstallation:** `lastSeen === null` → Banner zeigt nichts (man kann nicht „neu" sein, was man noch nie gesehen hat). Stattdessen verweist die Welcome-Tour des Setup-Wizards auf die In-App-Hilfe.

## UI-Skizze

```
┌──────────────────────────────────────────────────────────────┐
│  ✨  Neu seit deinem letzten Besuch (v3.20.0 → v3.24.1)      │
│                                                          ⨯   │
│  ──────────────────────────────────────────────────────────  │
│  v3.24.0                                                     │
│   ☑  In-App-Hilfe — vollständiges Handbuch direkt in EEDC    │
│      [Hilfe öffnen →]                                        │
│   ☑  WP-Kompressor-Starts als Stunden-/Tages-/Monats-KPI     │
│      [Im Sensor-Mapping einrichten →]                        │
│                                                              │
│  v3.23.x                                                     │
│   ☑  Mobile-Hinweis im Prognosen-Tab statt überlappender …   │
│      [Prognosen öffnen →]                                    │
│   …                                                          │
│                                                              │
│  v3.22.0                                                     │
│   ☑  Genauigkeits-Tracking: MAE und Bias getrennt            │
│      [Prognosen → Genauigkeit →]                             │
│   …                                                          │
│                                                              │
│  v3.21.0                                                     │
│   ☑  Energieprofil-Seite (Tages-Tabelle, Datenverwaltung)    │
│      [Öffnen →]                                              │
│   …                                                          │
│                                                              │
│  [ Alle als gelesen markieren ]                              │
└──────────────────────────────────────────────────────────────┘
```

**Position:** Modal-Overlay beim ersten App-Öffnen nach Update. Nicht-modal, klickbar nebenher (User kann arbeiten und Banner offen lassen).

**Re-Open:** Hauptmenü → Hilfe → „Was ist neu" (eigener Eintrag in der Hilfe-Sidebar, Kategorie *Einstieg*, links neben „Übersicht"). Damit auch nach Schließen jederzeit wieder erreichbar.

## Was bewusst nicht gebaut wird

- **Keine automatische CHANGELOG-Extraktion.** Der CHANGELOG ist technisch (Bug-Refs, Code-Pfade), der Banner anwender-zentriert. Beides parallel pflegen.
- **Keine pro-Highlight-Persistenz mit IDs in der DB.** localStorage reicht — wer Browser wechselt, sieht den Banner halt einmal mehr. Keine Synchronisation über Geräte.
- **Kein E-Mail/Push-Notifier.** Reine In-App-Sicht.
- **Keine A/B-Tests, keine Analytics.** Klick-Tracking pro Highlight wäre interessant, aber widerspricht der „Lokal-only, keine Telemetry"-Linie von EEDC.

## Aufwand

- TypeScript-Highlight-Datenstruktur + Initial-Befüllung aus „Was ist neu"-Tabelle: ~halber Tag.
- React-Komponente (Modal + Hilfe-Sidebar-Eintrag): ~halber Tag.
- localStorage-Logik + Versionsvergleich-Helper: ~ein paar Stunden.
- **Pflege pro Release:** Liste in `highlights.ts` ergänzen — 5 Min pro Highlight, Teil des Release-Workflows analog zum CHANGELOG.

Insgesamt ~1–1,5 Tage Implementierung + dauerhafte Pflege-Disziplin.

## Trigger

- **Nach** dem nächsten ruhigen Forum-Bündel oder
- **Spätestens** mit dem nächsten Major-Versions-Sprung (v3.25 oder v4.0), weil die Tester sonst dieselbe Anfrage erneut stellen.

Die statische „Was ist neu seit v3.16?"-Tabelle im `BENUTZERHANDBUCH.md` ist als Brücke ausreichend — wer in die Hilfe schaut, findet den Überblick. Der Banner ist die proaktivere Variante, die Safi105 ursprünglich angefragt hat.

## Verweise

- [Discussion #130](https://github.com/supernova1963/eedc-homeassistant/discussions/130) — Originale Anfrage von Safi105
- [Issue #40](https://github.com/supernova1963/eedc-homeassistant/issues/40) — rapahls Beobachtung zum Add-on-Store-Changelog
- `docs/BENUTZERHANDBUCH.md` — „Was ist neu seit v3.16?"-Tabelle als initiale Datenquelle
- `eedc/frontend/src/config/version.ts` — Versions-String aus dem Release-Workflow
