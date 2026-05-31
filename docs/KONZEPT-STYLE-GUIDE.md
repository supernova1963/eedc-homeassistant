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

> **✅ Entschieden (2026-05-31): Rückbau im v4.0.0-Schnitt.** Das Bestandsfeature `SortableSection`/`OrderedSections` (↑↓-Reorder + LocalStorage, live in WP-/PV-/Monatsabschluss-Dashboard, #175) wird entfernt — der Cap bleibt streng, „freie Card-Anordnung" gibt es auch nicht als Bestand. `CollapsibleSection` wird die einzige Sektions-Persistenz (siehe B6). detLAN (#175) per Release-Notes / „Wo ist X hin?" informieren. Prinzip: aufräumen + vereinheitlichen statt Sonderpfad konservieren.

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

> **✅ Vorab-Entscheidungen (2026-05-31):**
> 1. **Farb-Kanon — A2 ist normativ.** A0 migriert die ausgelieferte tailwind-`energy`-Palette an die A2-Semantik (Speicher→lila, Verbrauch→blau) und ergänzt die in A2 noch fehlenden Werte für Netzbezug/Einspeisung (Rot bleibt für Kosten reserviert). Der sichtbare Farbwechsel an den Energie-Charts ist als Preis für die saubere Semantik akzeptiert.
> 2. **Spacing-SoT — `design-tokens.ts`.** Spacing geht im A0-Artefakt (Tailwind-Theme + `design-tokens.ts`) auf; `lib/spacing.ts` entfällt.

> **A0-Grundsatz — vollenden, nicht abtippen:** „A2 normativ" (und analog A1/A4/C1) heißt, das semantische *System* ist die Quelle — **nicht** der heutige, teils lückenhafte Doc-Text. A0 baut das System **fertig**, statt einen unvollständigen Stand einzufrieren (das wäre wieder Flicken). Konkret für Farben: alle Energie-/Komponenten-Rollen (PV, Speicher, Verbrauch, Netzbezug, Einspeisung, Kosten, Umwelt) **und** die getrennte Status-Achse (OK/Warning/Error/Info) bekommen definierte Token-Werte; die tailwind-Palette **und** die heute duplizierten `KPICard`-/`komponentenStyle`-Farb-Enums werden daraus **abgeleitet** (eine Quelle), nicht parallel gepflegt. Dasselbe Prinzip gilt für Typo (A1), Animation (A4), Spacing (C1): die Token-Tabelle wird in A0 vollständig gemacht, nicht aus dem Ist-Stand zusammengeklaubt.

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

> **⚠️ Drift-Befund + offene Entscheidung (2026-05-31):** Die ausgelieferte `tailwind.config.js:25-31`-`energy`-Palette weicht von dieser Semantik ab — `battery=#3b82f6 (blau)` und `consumption=#8b5cf6 (violett)` sind gegenüber „Verbrauch=blau / Speicher=lila" **vertauscht**, und `grid=#ef4444 (rot, Netzbezug)` kollidiert mit „Kosten=rot". Zusätzlich definieren `ui/KPICard.tsx` + `komponentenStyle.ts` die Farb-Enums dupliziert, nicht aus A2 abgeleitet. **✅ Entschieden (2026-05-31): A2 ist normativ** — A0 migriert den Code an diese Semantik (Speicher→lila, Verbrauch→blau), der visuelle Bruch an den Charts ist akzeptiert. **A0-To-do:** A2 ergänzt die noch fehlenden Werte für Netzbezug + Einspeisung (Rot bleibt Kosten vorbehalten). Die Datentyp-Achse bildet die 8-Wert-`COLOR_CLASSES` ab; die Status-Achse (OK/Warning/Error/Info) braucht noch eigene Token-Werte.

*Konkrete Farbliste folgt mit der A0-Entscheidung.*

**Betroffene Issues:** *(noch keine direkten)*

---

### A3 — Datenzustand-Vokabular

> **Unterscheidung:** `—` (echte Datenlücke) · *N/A* (strukturell nicht zutreffend, z. B. Komponente nicht vorhanden) · `…` (in Berechnung) · `?` (unsicher / Schätzung).
> Display-Token `—` bereits etabliert (v3.29.1 #239). **Ist-Stand (2026-05-31):** `fmtKpi`-Helfer existiert bereits in `lib/komponentenStyle.ts:49`, die `/dev/design-preview`-Galerie rendert alle vier Tokens. Offen ist nur die SoT-Heimat von `fmtKpi` (bleibt in `komponentenStyle.ts` oder zieht ins A0-`design-tokens.ts`/ein `fmt`-Modul) und die durchgängige Anwendung.

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
> **Komponenten-Typ-Icons:** via `lib/komponentenStyle.ts` (noch unvollständig — WP/Speicher ja, E-Auto/BKW/Wallbox/Sonstiges/PV-Anlage offen, Disc #163).
> **A5 in zwei Schritten (2026-05-31):** die vorhandenen `WP_KPI`/`SPEICHER_*`-Konstanten werden heute **nirgends real konsumiert** (Dashboards hardcoden title/icon/color) — also (a) zuerst WaermepumpeDashboard/SpeicherDashboard auf den SoT umstellen (SoT erstmals einziehen), (b) dann die fünf fehlenden Typen ergänzen. „PV-Anlage" ist dabei ein UI-Aggregat (pv-module/wechselrichter/balkonkraftwerk), kein eigener `InvestitionTyp`.
> **Status-Icons:** konsistent (Check/Warning/Error/Info).
> **Dekorative Icons** in Headern/Bannern vermeiden (Forum #206 P2-Linie).

**Betroffene Issues:** #210 (Komponenten-Icons in Finanzen), #258 P3 (Box-Icon-Position), #244 (Cockpit-Banner-Icon).

---

### A6 — Berechnungs-Transparenz (Formel-Tooltip)

> **Prinzip:** Jede *abgeleitete/aggregierte* Kennzahl (KPI, ROI, Autarkie %, Ersparnis, Wirkungsgrad, Prognose) zeigt ihre Herleitung auf Abruf — Formel + eingesetzte Werte + Datenquelle/Zeitraum. Rohe Zählerwerte und triviale Summen bleiben tooltip-frei (kein Rauschen).
> **Affordance:** konsistenter, dezenter Indikator (z. B. gepunktete Unterstreichung oder kleines ⓘ). Progressive Disclosure — versteckt bis Hover/Tap, daher **kein Profi-Modus** (dient gerade Einsteigern „woher kommt die Zahl?").
> **Architektur (SoT):** Formel/Erklärung als Eigenschaft des Berechnungs-Layer-Helfers (`core/berechnungen/`, ADR-001) — Wert UND Erklärung aus *einer* Quelle, können nicht driften. Bestehend: `FormelTooltip` (ROIDashboard) als Vorbild, B1 nennt den Berechnung-Tooltip.
> **A3-Kopplung:** der Tooltip erklärt auch, *warum* ein Wert `—`/`N/A`/`?` ist (Datenlücke vs. strukturell vs. Schätzung).
> **Mobile:** kein Hover auf Touch → Tap/Long-press-Popover (Touch-Target ≥ 44 px, siehe Mobile M4).

**Betroffene Issues:** #243 B9 (FormelTooltip-Konsolidierung), Disc #162 (fmtKpi/Datenzustand).

---

### A7 — Daten-Aktualität & Quelle

> **Prinzip:** Jede Datensicht zeigt konsistent **Stand** (Zeitstempel „Stand: TT.MM.JJJJ HH:MM" bzw. „Live") und **Quelle** der Werte — der Nutzer muss erkennen, wie frisch und woher eine Zahl ist.
> **Quellen-Vokabular:** HA-LTS · Live-Snapshot · Custom-/Cloud-Import · Prognose-Quelle (OpenMeteo / eedc / Solcast). Konsistente Kurzlabels/Icons.
> **Live vs. LTS:** Live-Werte (5-Min/Power) sichtbar von aggregierten LTS-Tageswerten unterscheidbar machen — die Frische-Differenz ist ein wiederkehrender Verwechslungs-Punkt.
> **Platzierung:** dezent am Sektions-/Karten-Header oder via A6-Tooltip, nicht pro Zelle.

**Betroffene Issues:** Daten-Provenance-/Daten-Checker-Linie, Live-vs-LTS-Konsistenz (#135-Folge).

---

## Teil B — Komponenten

### B1 — KPI-Karten

> **Layout:** Titel oben · Wert (groß) zentral · Einheit (klein) rechts vom Wert · optional Icon dezent unten/Hintergrund · optional Subtitle/Berechnung-Tooltip.
> **Einheits-Position einheitlich:** entweder rechts vom Wert ODER eigene Zeile darunter — nicht gemischt (#258 P1).
> **Inhalts-Ausrichtung horizontal:** Werte aller Karten einer Reihe auf gleicher Baseline (#258 P2).
> **Icon-Position:** alle Karten einer Sektion gleich, oder konsistent „ohne Icon" (#258 P3).
>
> **SoT-Komponente** statt der heute parallelen Implementierungen (B9 KPICard-Konsolidierung als Pflicht-Item).

**Vorbedingung:** Konsolidierung der KPICard-Implementierungen (B9 in #243). **Ist-Stand (2026-05-31, verifiziert):** nicht drei, sondern **fünf** echte `KPICard` (`components/ui/`, `components/dashboard/`, `pages/auswertung/` + inline `ROIDashboard.tsx:710` + inline `community/KomponentenTab.tsx`) **plus drei `KpiCard`-Label-Helfer** (EnergieprofilPrognose/-Monat/-Tab) = 8 Definitionen, von ~26 Dateien referenziert. Die Community-Variante (`community_avg`/`invertColors` Vergleichs-KPI) ist **nicht** in einen reinen Size-Varianten-SoT mergebar und bleibt ggf. eigene Komponente.
**Betroffene Issues:** #243 B9, #247 P1, #258 P1+P2+P3.

---

### B2 — Tabellen + Listen

> **Spalten-Header:** Stil-Konvention folgt (Casing + Einheit im Header, siehe unten).
> **Sortierung:** `INVESTITION_TYP_ORDER` aus `lib/constants.ts` als SoT (etabliert v3.27.1, in v3.29.2 weiter ausgerollt). Suffix-Typen-Sortierung über Präfix-Match. **Zeitreihen-Default aktuell→alt.**
> **Leerwert-Darstellung:** `—` aus A3.
> **Einheits-Anzeige:** Spalten-Header mit Einheit (z. B. „Strom (kWh)"), nicht pro Zelle (#237).
> **Einheitliches Spalten-Auswahl-Pattern (#292):** Drop-Down mit „Standard wiederherstellen", Anzahl-Badge, konsistente CSV-Beschriftung — heute über mehrere Tabellen gedriftet (fünf belegte Befunde aus #292).

**Betroffene Issues:** #243 B8, #210, #237, #292.

---

### B3 — Navigation

> **Hauptnav:** Reihenfolge + Inhalte sind in [`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md) festgelegt (Cockpit / Komponenten / Auswertungen / Community / Einstellungen).
> **Mobile:** Hamburger-Menü mit voller Liste (Standard-Pattern). Bottom-Tab-Bar bewusst nicht in v4.0.0.
> **Sub-Nav:** **Unterstrich + Icons** (`components/layout/SubTabs.tsx`) als Standard. `components/ui/PillTabs.tsx` wird deprecated und in seinen Verwendern migriert (#243 B1, detLAN-Klärung #216) — als Vor-Schritt vor dem v4.0.0-IA-Refactor. **Ist-Stand (2026-05-31, verifiziert):** PillTabs hat **vier** Verbraucher (Auswertung, Community, Aussichten, DesignPreview), nicht drei; EnergieprofilTab nutzt PillTabs **nicht** direkt. Achtung: **kein 1:1-Swap** — `SubTabs` ist route-/`NavLink`-getrieben, `PillTabs` state-getrieben (`onChange`/`activeKey` + `beta`-/`tooltip`-Props, die SubTabs fehlen). **✅ Entschieden (2026-05-31): Sub-Tabs auf echte URL-Routen heben** (zukunftssicher, teilbare Links, passt zur Redirect-Tabelle); die State-Features von PillTabs (beta-Badge, Tooltip) werden auf der route-getriebenen `SubTabs` nachgebaut. B1 ist damit gegen die Redirect-Tabelle isoliert testbar.
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

> **Schwebend** auf langen Scroll-Seiten (Sticky `top: 0` mit Backdrop-Blur). Reusable `<FloatingSelector>` (#243 B3) — **existiert noch nicht (zu bauen, 2026-05-31)**, Phase-Zuordnung (Phase-0-Vorarbeit vs. Teil des v4.0.0-Schnitts) offen. **Namensraum-Hinweis:** dieses B5 (Selektoren) ist nicht der Mobile-Tracker B5a–B5e (#243-Sub-Tracker für M1/M2/M3).
> **Single-Anlage-Selektor:** ausblenden wenn ohne Auswahl-Sinn (#243 B12 — Audit).
> Mobile-Sticky-Verhalten in [KONZEPT-MOBILE.md M2](KONZEPT-MOBILE.md).

**Betroffene Issues:** #243 B3+B12, #206 P3, #208 P2+P6.

---

### B6 — Aufklapp-Verhalten (`CollapsibleSection`)

> **Persistenz:** Aufklapp-Status pro Sektion in LocalStorage (etabliert für Monatsberichte/Energieprofil-Monat — Vorbild laut detLAN #258 P5). Konsistente Implementierung über alle Verwender. **Drift-Befund (2026-05-31):** `CollapsibleSection` (Key `eedc-collapse-${storageKey}`) und `SortableSection` (Key `${prefix}_section_${title}`) führen je eigene Open-State-Logik — die geforderte Konsistenz ist intern bereits gebrochen. **✅ Entschieden (2026-05-31): `CollapsibleSection` ist der alleinige Persistenz-SoT;** `SortableSection` wird im v4.0.0-Schnitt zurückgebaut (Cap-Entscheidung oben).
> **Default-Open** pro Sektion definieren (datenreich → standardmäßig offen; sekundär → standardmäßig zu).
> **Mobile-Default** abweichend siehe [KONZEPT-MOBILE.md M1](KONZEPT-MOBILE.md).

**Betroffene Issues:** #258 P5, #148.

---

### B7 — Diagramme / Charts

> **Achsen + Legende:** beschriftete Achsen mit Einheit (siehe C3), Legende konsistent platziert; Zeitachse nach der etablierten Slot-Konvention (backward).
> **Farb-Mapping:** Serien-Farben **aus den A2-Tokens** (PV = gelb, Speicher = lila, Verbrauch = blau, …) — nicht ad-hoc pro Chart. Eine Datenrolle = überall dieselbe Farbe.
> **Hover/Tap-Tooltip:** Wert + Einheit + Zeitpunkt am Datenpunkt; auf Touch tap-bar (Mobile M4).
> **Chart-Typ pro Datenart:** Verlauf → Linie/Fläche, Zusammensetzung → gestapelt, Vergleich → Balken, Anteil → Donut. Konvention, nicht Seiten-Einzelfall.
> **Leerzustand:** keine Daten → klare Leer-Darstellung (siehe B8), keine leeren Achsenkreuze.

**Betroffene Issues:** neue Norm; eedc ist chart-dicht, bislang ungeregelt.

---

### B8 — Leer- / Lade- / Fehler-Zustände

> **Laden:** Skeleton-Platzhalter in Karten-/Chart-/Tabellen-Form (kein Layout-Sprung beim Nachladen), kein nackter Vollseiten-Spinner.
> **Leer (echte Datenlücke):** erklärender Leerzustand mit **CTA** („Noch keine Daten — jetzt einrichten/importieren"), nicht nur `—`. Abgrenzung: A3 ist *wert*-level, B8 ist *sektions-/seiten*-level.
> **Strukturell N/A:** Sektion ausblenden statt leer zeigen (Komponente nicht vorhanden), vgl. A3 + IA-V4-Tab-Filter.
> **Fehler:** einheitlicher Fehlerzustand (was ist schief, was tun) statt stiller Leere oder roher Exception; Retry-Affordance wo sinnvoll.

**Betroffene Issues:** neue Norm; heute behandelt jede Seite Leer/Laden/Fehler eigen.

---

## Teil C — Layout + Texte

### C1 — Spacing-Standards

> **Tokens:** `--page-padding-top` · `--nav-content-gap` · `--section-spacing` · `--card-padding` · `--card-gap`.
> SoT: **✅ entschieden (2026-05-31)** — Spacing geht im A0-Artefakt (`design-tokens.ts` + Tailwind-Theme) auf; ein eigenes `lib/spacing.ts` entfällt.
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

### C3 — Einheiten & Präzision

> **Einheit immer präsent:** kein nackter Zahlenwert ohne Einheit; im Tabellen-Header (siehe B2), nicht pro Zelle.
> **Größen-Umschaltung:** kWh ↔ MWh (bzw. W ↔ kW) ab definierter Schwelle einheitlich, nicht gemischt in derselben Sicht.
> **Nachkommastellen pro Größe:** kWh 1, € 2, % 1 (Vorschlag) — pro Größenart fix, nicht ad-hoc.
> **`%` mit Leerzeichen** („84,2 %", aus C2), deutsches Komma + Tausender-Punkt.
> **kW ≠ kWh:** Leistung vs. Energie nie vermischen (#200-Linie) — die Einheit folgt der Größe.

**Betroffene Issues:** #237 (Einheiten-Header), #200 (kW/kWh), #258 P6 (%-Drift).

---

## Querverweise

- **Informationsarchitektur v4.0.0** → [`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md)
- **Mobile-Konzept** → [`KONZEPT-MOBILE.md`](KONZEPT-MOBILE.md)
- **Aggregations- und Berechnungs-Themen** → [`BERECHNUNGEN.md`](BERECHNUNGEN.md)
- **Sensor-Themen** → [`SENSOR-REFERENZ.md`](SENSOR-REFERENZ.md)
- **Architektur-Überblick** → [`ARCHITEKTUR.md`](ARCHITEKTUR.md)
- **Konzept-Issue mit Sub-Trackern** → [#243](https://github.com/supernova1963/eedc-homeassistant/issues/243)
