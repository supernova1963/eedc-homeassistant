# eedc Style-Guide v4.0.0 (Konzept-Skelett)

> **Status:** Wachsendes Konzept-Dokument **+ gezielter Schnitt** zur Version 4.0.0. Visuelle Sprache wächst pro Welle, **die Informationsarchitektur** wird mit v4.0.0 in einem zusammenhängenden Refactor neu gesetzt (siehe [`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md)). Die Skelett-Sektionen hier füllen sich pro Umsetzungs-Welle.
>
> **Eingangsperspektive:** Maintainer-konzipiert mit eigenen Designstandards. Anwender-Feedback aus Forum und Issues fließt als **Datenpunkt** ein, ist aber nicht der einzige Treiber. Jede Regel hat eine bewusste Designentscheidung dahinter, kein Aggregat einzelner Bug-/UX-Reports.
>
> **Ziel:** Konsistente, dokumentierte UI-Sprache für eedc. Marken-Wert für v4.0.0: „strukturell sauber + konsistent".
>
> **Mobile-Verhalten** wird in einem **eigenen Konzept-Dokument** behandelt: [`KONZEPT-MOBILE.md`](KONZEPT-MOBILE.md). Bei Bereichen mit Mobile-Bezug Querverweis statt Inline-Lösung. **Pflicht-Querschnittsregeln** (Touch-Targets, Companion-App-Quirks) gelten generell — siehe Methodik unten.
>
> **Informationsarchitektur v4.0.0** → [`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md) (Top-Nav, Achsen, Cross-Linking, Migration). Der Style-Guide regelt das **Wie es aussieht**, die IA das **Wo es liegt**.

---

## Methodik

- **Wachsend statt Big-Bang — mit einer Ausnahme.** Pro Umsetzungs-Welle (typisch 1–2 Bereiche) werden die zugehörigen Abschnitte hier mit-geschrieben — fertige Regel + Vorher/Nachher-Screenshot aus dem ausgelieferten Code. **Ausnahme:** der IA-Refactor zu v4.0.0 (siehe `KONZEPT-IA-V4.md`) wird als zusammenhängender Schnitt umgesetzt, weil die Achsen-Trennung nicht inkrementell migrierbar ist.
- **Tester-Beobachtungen** (Issues, Forum-Posts) sind **Datenpunkte**. Pro Punkt bewusst entscheiden: übernehmen (weil zu unserer Linie passt) oder explizit anders (mit dokumentierter Begründung).
- **Eigene Themen einplanen**, die nicht aus Tester-Backlog kommen — siehe Teil A.
- Querverweise auf Memory-Linien (intern), nicht im Dokument.

### Pflicht-Querschnittsregeln (gelten in jeder Welle, jeder neuen Seite, jedem Refactor)

Diese Regeln werden **nicht** als eigene Wellen verfolgt, sondern in jeder Welle pflichtgemäß eingehalten. Aus Mobile-Konzept M4 + M5 hochgezogen, weil sie sonst nie zünden (Stakeholder-Trigger zu dünn).

- **Touch-Targets ≥ 44 × 44 px** für jedes klickbare Element (Apple-/Google-Standard).
- **Keine überlappenden Tap-Bereiche** (z. B. Sektion-Header + Aufklapp-Chevron als ein Target).
- **Layout-Wrapper `h-dvh` statt `h-screen`** (iOS Safari + HA Companion-App).
- **Datei-Downloads** über `lib/download.ts:downloadFile()`, nie `window.open` (Companion-App blockiert externe Tabs).
- **Sticky-/Sub-Scroll-Container** mit `overscroll-contain`.
- **`flex-1`/`min-h-0`** in Multi-Breakpoint-Layouts immer mit Breakpoint-Prefix konsistent zum Direction-Switch.

### Einstellbarkeits-Cap für v4.0.0

eedc bekommt **keine** umfangreichen Personalisierungs-Optionen. Bewusste Designentscheidung — einheitliche UX schlägt individuelle Anpassbarkeit, Solo-Maintainer-Modell verträgt keine sich vervielfachende Test-Matrix.

**Erlaubt:**

- **Hell/Dunkel-Mode-Toggle** (System-Default + manuelle Übersteuerung).
- **Mobile-Reduce-Default-Override pro Sektion** via vorhandene `<CollapsibleSection>`-LocalStorage-Persistenz.

**In v4.0.0 nicht enthalten:**

- Theme-Editor, freie Akzentfarben-Wahl.
- Dichte-Profile (kompakt / luftig).
- Freie Card-Anordnung pro Seite.
- Font-Größen-Schieber, Layout-Slider.

Spätere Tester-Wünsche nach „mehr Optionen" verweisen auf diesen Cap. Begründung dokumentiert, kein Trägheits-Argument.

---

## Teil A — Visuelle Sprache (Querschnitt)

Diese Abschnitte definieren das gemeinsame Fundament, auf dem alle Komponenten in Teil B aufsetzen.

### A0 — Design-Tokens (Pflicht-Vorarbeit vor v4.0.0-IA-Refactor)

> **Inhalt:** Konkrete Token-Werte für Typografie, Farben, Spacing, Schatten, Radius — als Tailwind-Theme-Extension + `lib/design-tokens.ts`.
> **Scope:** Tokens + Theme. **Keine Komponenten-Refactors, keine sichtbare UI-Änderung.** Bestehende Klassen werden Schritt für Schritt in den Folge-Wellen auf die Tokens umgestellt.
> **Warum vor dem IA-Refactor:** der v4.0.0-Schnitt (siehe [`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md)) bringt viele neue Seiten (Komponenten-Hub, Einstellungs-Kachel-Grid, Cockpit-Sub-Tabs). Ohne vorab fixierte Tokens improvisiert jeder neue View seine Werte → sofort Drift, kein Marken-Versprechen.

**Liefer-Artefakt:**

- `eedc/frontend/tailwind.config.js` mit konkreten Token-Werten in `theme.extend`.
- `eedc/frontend/src/lib/design-tokens.ts` mit semantischen Aliasen für Stellen, die kein Tailwind nutzen können (z. B. Chart-Farben, dynamische Inline-Styles).
- Dunkel-Mode-Linien-Logik definiert (Kontrast-Stufen, Schatten-Inversion).

**Konkrete Tabellen** werden mit der Umsetzung in A1, A2, A4, C1 hier befüllt — A0 ist der Sammel-Marker, dass diese Sektionen **vor** dem IA-Refactor konkret sein müssen.

---

### A1 — Typografie-System

> **Skala (semantisch, nicht Pixel):** Display · Title-XL · Title-L · Title-M · Title-S · Body-L · Body-M · Body-S · Caption.
> Tokens statt ad-hoc Tailwind-Klassen. Schriftfamilie, Line-Heights, Letter-Spacing pro Token.

*Konkrete Tabelle folgt mit erster Umsetzungs-Welle.*

**Betroffene Issues (Datenpunkte):** #258 P4 (Textgestaltung-Unruhe), #256 (Schriftgrößen-Inkonsistenz).

---

### A2 — Farb-Palette + semantische Farb-Codes

> **Semantik:** Datentyp → Farbe. PV/Energie = gelb, Kosten = rot/orange, Umwelt = grün, Verbrauch = blau, Speicher = lila. Status-Farben (OK/Warning/Error/Info) getrennt.
> Dunkel- vs. Hell-Mode mit eigener Linien-Logik (Kontrast, Schatten, Saturation).

*Konkrete Farbliste folgt.*

**Betroffene Issues:** *(noch keine direkten)*

---

### A3 — Datenzustand-Vokabular

> **Unterscheidung:** `—` (echte Datenlücke) · *N/A* (strukturell nicht zutreffend, z. B. Komponente nicht vorhanden) · `…` (in Berechnung) · `?` (unsicher / Schätzung).
> Display-Token `—` bereits etabliert (v3.29.1 #239). Andere Zustände noch nicht systematisch.

**Betroffene Issues:** Disc #162 (`fmtKpi`-Helfer + Datenloch vs. strukturell N/A).

---

### A4 — Animation + Übergänge

> **Animiert:** Wert-Änderungen (Zahlen-Tween), Hover-Highlights, State-Toggles.
> **Statisch:** Layout-Wechsel, Modal-Inhalt-Wechsel, Tab-Wechsel.
> **Dauer-Konvention:** 150 ms (Mikro), 300 ms (Standard), 500 ms+ (Hervorhebung). Easing `ease-out` Standard.

*Konkrete Animation-Tokens folgen.*

**Betroffene Issues:** *(noch keine direkten)*

---

### A5 — Icons + Symbol-Konventionen

> **Linien-Icons:** `lucide-react` als SoT.
> **Komponenten-Typ-Icons:** via `lib/komponentenStyle.ts` (Memory: noch unvollständig — WP/Speicher ja, E-Auto/BKW/Wallbox/Sonstiges/PV-Anlage offen, Disc #163).
> **Status-Icons:** konsistent (Check/Warning/Error/Info).
> **Dekorative Icons** in Headern/Bannern vermeiden (Forum #206 P2-Linie).

**Betroffene Issues:** #210 (Komponenten-Icons in Finanzen), #258 P3 (Box-Icon-Position), #244 (Cockpit-Banner-Icon).

---

## Teil B — Komponenten

### B1 — KPI-Karten

> **Layout:** Titel oben · Wert (groß) zentral · Einheit (klein) rechts vom Wert · optional Icon dezent unten/Hintergrund · optional Subtitle/Berechnung-Tooltip.
> **Einheits-Position einheitlich:** entweder rechts vom Wert ODER eigene Zeile darunter — nicht gemischt (#258 P1).
> **Inhalts-Ausrichtung horizontal:** Werte aller Karten einer Reihe auf gleicher Baseline (#258 P2).
> **Icon-Position:** alle Karten einer Sektion gleich, oder konsistent „ohne Icon" (#258 P3).
>
> **SoT-Komponente** statt drei parallelen Implementierungen (Memory: B9 KPICard-Konsolidierung als Pflicht-Item).

**Vorbedingung:** Konsolidierung der drei aktuellen `KPICard`-Komponenten (B9 in #243).
**Betroffene Issues:** #243 B9, #247 P1, #258 P1+P2+P3.

---

### B2 — Tabellen + Listen

> **Spalten-Header:** Stil-Konvention folgt.
> **Sortierung:** `INVESTITION_TYP_ORDER` aus `lib/constants.ts` als SoT (etabliert v3.27.1, in v3.29.2 weiter ausgerollt). Suffix-Typen-Sortierung über Präfix-Match.
> **Leerwert-Darstellung:** `—` aus A3.
> **Einheits-Anzeige:** Spalten-Header mit Einheit (z. B. „Strom (kWh)"), nicht pro Zelle (#237).

**Betroffene Issues:** #243 B8, #210, #237.

---

### B3 — Navigation

> **Hauptnav:** Reihenfolge + Inhalte sind in [`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md) festgelegt (Cockpit / Komponenten / Auswertungen / Community / Einstellungen).
> **Mobile:** Hamburger-Menü mit voller Liste (Standard-Pattern). Bottom-Tab-Bar bewusst nicht in v4.0.0.
> **Sub-Nav:** **Unterstrich + Icons** (`SubTabs.tsx`) als Standard. `PillTabs.tsx` wird deprecated und in den 3 letzten Verwendern (Aussichten, Auswertung, Community) migriert (#243 B1, detLAN-Klärung #216) — als Vor-Schritt vor dem v4.0.0-IA-Refactor.
> **Sub-Tab-Limit:** maximal 5 Sub-Tabs pro Top-Eintrag. Tab-Inflation (heute 8 in Auswertungen, 5 in Aussichten) wird durch die IA-Aufteilung gelöst und durch diese Regel verhindert.
> **Sprungmarken** in langen Seiten (TOC-Pattern). *Offen.*

**Betroffene Issues:** #243 B1+B2, #208, #209, #216.

---

### B4 — Header + Banner

> **Cockpit-Banner:** kompakt, ~88 px, `flex items-center` mit `min-height`, vertikal zentriert (#243 B4).
> **PageHeader:** alle 39 Seiten mit hardcoded `<h1>` auf `<PageHeader>` migrieren (#243 B10). Show/Hide-Default pro Seite definieren: Hide wenn `<h1>`-Text = aktives Tab-Label, sonst Show.
> **Keine dekorativen Icons** vor Selektoren in Top-Bars (#206 P2-Linie, z. B. Calendar-Icon in v3.29.2 entfernt).

**Betroffene Issues:** #243 B4+B10, #196, #206 P2, #244.

---

### B5 — Selektoren

> **Schwebend** auf langen Scroll-Seiten (Sticky `top: 0` mit Backdrop-Blur). Reusable `<FloatingSelector>` (#243 B3).
> **Single-Anlage-Selektor:** ausblenden wenn ohne Auswahl-Sinn (#243 B12 — Audit).
> Mobile-Sticky-Verhalten in [KONZEPT-MOBILE.md M2](KONZEPT-MOBILE.md).

**Betroffene Issues:** #243 B3+B12, #206 P3, #208 P2+P6.

---

### B6 — Aufklapp-Verhalten (`CollapsibleSection`)

> **Persistenz:** Aufklapp-Status pro Sektion in LocalStorage (etabliert für Monatsberichte/Energieprofil-Monat — Vorbild laut detLAN #258 P5). Konsistente Implementierung über alle Verwender.
> **Default-Open** pro Sektion definieren (datenreich → standardmäßig offen; sekundär → standardmäßig zu).
> **Mobile-Default** abweichend siehe [KONZEPT-MOBILE.md M1](KONZEPT-MOBILE.md).

**Betroffene Issues:** #258 P5, #148.

---

## Teil C — Layout + Texte

### C1 — Spacing-Standards

> **Tokens:** `--page-padding-top` · `--nav-content-gap` · `--section-spacing` · `--card-padding` · `--card-gap`.
> SoT: `lib/spacing.ts` (oder Tailwind-Custom-Theme).
> Bestehende Spacings im Code auditieren und auf Tokens migrieren.

**Betroffene Issues:** #243 B6, #209 P5.

---

### C2 — Schreibweisen + Zahlen-Format

> **Marken-Schreibung:** „eedc" lower-case in Anwendertexten (etabliert v3.29.2). „EEDC" nur in Code-Identifiern (`EEDC_Prognose`-Formel, Env-Vars). Marken-Style-Guide folgt.
> **`%`-Zeichen:** mit Leerzeichen vor `%` (deutsche Konvention, z. B. „84,2 %") (#258 P6 — Drift heute).
> **Datums-Format:** TT.MM.JJJJ in Listen; „Mai 2026" in Headern.
> **Zahlen-Format:** deutsches Komma, Tausender-Punkt.
> **Display-Token `—`** als einheitliches Leerwert-Zeichen (etabliert v3.29.1).

**Betroffene Issues:** #243 B7, #258 P6.

---

## Querverweise

- **Informationsarchitektur v4.0.0** → [`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md)
- **Mobile-Konzept** → [`KONZEPT-MOBILE.md`](KONZEPT-MOBILE.md)
- **Aggregations- und Berechnungs-Themen** → [`BERECHNUNGEN.md`](BERECHNUNGEN.md)
- **Sensor-Themen** → [`SENSOR-REFERENZ.md`](SENSOR-REFERENZ.md)
- **Architektur-Überblick** → [`ARCHITEKTUR.md`](ARCHITEKTUR.md)
- **Konzept-Issue mit Sub-Trackern** → [#243](https://github.com/supernova1963/eedc-homeassistant/issues/243)
