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
- **Freie Card-/Widget-Anordnung pro Seite** — Dashboard-Builder / „My-Sites" mit frei wählbaren, neu zu bildenden Bausteinen. **Nicht** gemeint: das Umsortieren eines *festen* Sektionssatzes (siehe Klarstellung unten).
- Font-Größen-Schieber, Layout-Slider.

> **⚠️ Korrektur (2026-06-01): „Reorder" war fälschlich mit „freie Card-Anordnung" gleichgesetzt.** Die 31.05.-Entscheidung hat zwei verschiedene Dinge in einen Topf geworfen: den verbotenen **Widget-Builder/My-Sites** (frei wählbare Bausteine — bleibt aus dem Scope) und das harmlose **Umsortieren eines festen Sektionssatzes** (die immer gleichen Sektionen per ↑↓ in eine persönliche Reihenfolge bringen). Letzteres ist **kein** Cap-Verstoß und wird **rehabilitiert** — das Muster kam bei den Testern gut an (Monatsbericht).
>
> **✅ Neu-Entscheidung (2026-06-01):** Sektions-Reorder bleibt als bewusst *enge* Personalisierung erhalten, aber **vereinheitlicht**: nicht die heutige Doppel-Logik (`CollapsibleSection` + `SortableSection` mit je eigenem Key) fortschleppen, sondern **ein** Persistenz-SoT, der Auf/Zu **und** Reihenfolge zusammen merkt (Auflage „neu bauen statt flicken"). **Differenziert nach Ort:** Cockpit-Zeitsichten (Monatsbericht & Geschwister) klapp- **und** sortierbar; **Komponenten-Hub bleibt fix** (lineare Reihenfolge ist dort eine eigene Designentscheidung, siehe IA-V4 Variante C). detLAN (#175) bleibt damit bedient statt nur „informiert".

Spätere Tester-Wünsche nach „mehr Optionen" verweisen auf diesen Cap. Begründung dokumentiert, kein Trägheits-Argument.

---

## Teil A — Visuelle Sprache (Querschnitt)

Diese Abschnitte definieren das gemeinsame Fundament, auf dem alle Komponenten in Teil B aufsetzen.

### A0 — Design-Tokens (Pflicht-Vorarbeit vor v4.0.0-IA-Refactor)

> **⚠️ Update 2026-06-12 (Fundament-P1):** Der `lib/design-tokens.ts`-Verweis in dieser A0-Sektion ist **überholt** — es gibt **kein** separates `design-tokens`-Modul. **Farb-SoT = `lib/colors.ts`** (vervollständigte Zentrale, app-weit durchgesetzt + Wächter `npm run check:design`, P1 `9730d414`). A0 = „Farben" ist damit **geshippt**. Die übrigen Token (Typo A1, Animation A4, Spacing/Radius/Schatten C1) werden in **Fundament-P6** als konkrete **Doc-Tabellen** befüllt — **Doc-Pflicht vor E3, nicht „bei Bedarf"**; Heimat = bestehende lib-Module / Tailwind-Theme bei echtem Klassen-Bedarf, **kein** neues Schicht-Modul, **kein** `lib/spacing.ts`. Der untenstehende A0-Liefer-Artefakt-Text (`design-tokens.ts`, „Spacing geht im A0-Artefakt auf") gilt entsprechend angepasst.

> **Inhalt:** Konkrete Token-Werte für Typografie, Farben, Spacing, Schatten, Radius — als Tailwind-Theme-Extension; Farb-SoT = `lib/colors.ts` (s. Update-Banner oben).
> **Scope:** Tokens + Theme. **Keine Komponenten-Refactors, keine sichtbare UI-Änderung.** Bestehende Klassen werden Schritt für Schritt in den Folge-Wellen auf die Tokens umgestellt.
> **Warum vor dem IA-Refactor:** der v4.0.0-Schnitt (siehe [`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md)) bringt viele neue Seiten (Komponenten-Hub, Einstellungs-Kachel-Grid, Cockpit-Sub-Tabs). Ohne vorab fixierte Tokens improvisiert jeder neue View seine Werte → sofort Drift, kein Marken-Versprechen.

**Liefer-Artefakt:**

- `eedc/frontend/tailwind.config.js` mit konkreten Token-Werten in `theme.extend`.
- Chart-Farben / dynamische Inline-Styles (kein Tailwind möglich): **`lib/colors.ts`** als SoT (ersetzt das ursprünglich geplante `design-tokens.ts` — s. Update-Banner).
- Dunkel-Mode-Linien-Logik definiert (Kontrast-Stufen, Schatten-Inversion).

**Konkrete Tabellen** werden mit der Umsetzung in A1, A2, A4, C1 hier befüllt — A0 ist der Sammel-Marker, dass diese Sektionen **vor** dem IA-Refactor konkret sein müssen.

> **✅ Vorab-Entscheidungen (2026-05-31):**
> 1. **Farb-Kanon — revidiert 2026-06-11: die Ist-Palette ist normativ** (battery=blau, consumption=lila — der 05-31-Tausch beruhte auf einem unbegründeten Doc-Vorschlag, s. A2-Revisions-Block). **Einzige Wert-Änderung: Netzbezug → Dunkelrot `#b91c1c`**, damit Signal-Rot `#ef4444` exklusiv für Kosten/negativ/Fehler wird (der Rot-Konflikt war der reale Kern des Befunds). `lib/colors.ts` ist die Zentrale (Bestandswerte kodifiziert, Duplikate tailwind / KPICard-`COLOR_CLASSES` daraus abgeleitet, Status-Achse ergänzt); der Netzbezug-Wechsel ist **mit Fundament-P1 sofort geshippt** (F2, nicht erst am Flip — Update 2026-06-12).
> 2. **Spacing-SoT — überholt (s. Update-Banner):** **kein** `design-tokens.ts`; die konkrete C1-Spacing-Tabelle füllt **Fundament-P6** als Doc-Norm (Tailwind-Theme nur bei echtem Klassen-Bedarf). `lib/spacing.ts` entfällt weiterhin.

> **A0-Grundsatz — vollenden, nicht abtippen:** „normativ" (Farben seit Revision 2026-06-11: Ist-Palette + Rot-Differenzierung; analog A1/A4/C1) heißt, das semantische *System* ist die Quelle — **nicht** der heutige, teils lückenhafte Doc-Text. A0 baut das System **fertig**, statt einen unvollständigen Stand einzufrieren (das wäre wieder Flicken). Konkret für Farben: alle Energie-/Komponenten-Rollen (PV, Speicher, Verbrauch, Netzbezug, Einspeisung, Kosten, Umwelt) **und** die getrennte Status-Achse (OK/Warning/Error/Info) bekommen definierte Token-Werte; die tailwind-Palette **und** die heute duplizierten `KPICard`-/`komponentenStyle`-Farb-Enums werden daraus **abgeleitet** (eine Quelle), nicht parallel gepflegt. Dasselbe Prinzip gilt für Typo (A1), Animation (A4), Spacing (C1): die Token-Tabelle wird in A0 vollständig gemacht, nicht aus dem Ist-Stand zusammengeklaubt.

---

### A1 — Typografie-System

> **Skala (semantisch, nicht Pixel):** Display · Title-XL · Title-L · Title-M · Title-S · Body-L · Body-M · Body-S · Caption.
> Tokens statt ad-hoc Tailwind-Klassen. Schriftfamilie, Line-Heights, Letter-Spacing pro Token.

*Konkrete Tabelle folgt mit erster Umsetzungs-Welle.*

**Betroffene Issues (Datenpunkte):** #258 P4 (Textgestaltung-Unruhe), #256 (Schriftgrößen-Inkonsistenz).

---

### A2 — Farb-Palette + semantische Farb-Codes

> **Semantik (revidiert 2026-06-11 — Ist-Palette + Rot-Differenzierung, s. Revisions-Block unten):** Datentyp → Farbe. PV/Energie = gelb, **Speicher = blau `#3b82f6`, Verbrauch = lila `#8b5cf6`, Einspeisung = grün `#10b981`, Netzbezug = Dunkelrot `#b91c1c`**, Umwelt = grün; **Signal-Rot `#ef4444` exklusiv für Kosten/negativ/Fehler.** Status-Farben (OK/Warning/Error/Info) getrennt. **SoT der konkreten Werte: `lib/colors.ts`** (keine Farbtabelle im Doc — s. Revisions-Block unten).
> Dunkel- vs. Hell-Mode mit eigener Linien-Logik (Kontrast, Schatten, Saturation).

> **⚠️ Drift-Befund + offene Entscheidung (2026-05-31):** Die ausgelieferte `tailwind.config.js:25-31`-`energy`-Palette weicht von dieser Semantik ab — `battery=#3b82f6 (blau)` und `consumption=#8b5cf6 (violett)` sind gegenüber „Verbrauch=blau / Speicher=lila" **vertauscht**, und `grid=#ef4444 (rot, Netzbezug)` kollidiert mit „Kosten=rot". Zusätzlich definieren **`lib/colors.ts`** (`COLORS`/`CHART_COLORS`/`SOLL_IST_COLORS` — Chart-Farben mit derselben Vertauschung, 5 Konsumenten; Befund nachgetragen 2026-06-11), `ui/KPICard.tsx` + `komponentenStyle.ts` die Farb-Enums dupliziert, nicht aus A2 abgeleitet. ~~**✅ Entschieden (2026-05-31): A2 ist normativ** — A0 migriert den Code an diese Semantik (Speicher→lila, Verbrauch→blau), der visuelle Bruch an den Charts ist akzeptiert.~~ **⚠️ REVIDIERT (2026-06-11, Gernot — zweigeteilt):** (1) **blau↔lila-Tausch gekippt, die Ist-Palette bleibt** (battery=blau `#3b82f6`, consumption=lila `#8b5cf6`): die 05-31-Fassung machte die Semantik-Zeile aus dem Konzept-Skelett vom 23.05. normativ, für die die Archäologie **keinen dokumentierten Produkt-Grund** fand („Konkrete Farbliste folgt", Begründung fehlte; Entscheidung fiel im 7er-Batch unter dem generellen Aufräum-Prinzip). (2) **Der Rot-Konflikt war dagegen real** (Gernot-Erinnerung + Befund: Rot heute 4-fach belegt — Netzbezug-Serie, WP-Wärme, CO₂-WP und `text-red`-Negativwerte in denselben Finanz-Sichten) → **Netzbezug → Dunkelrot `#b91c1c`**, Signal-Rot `#ef4444` wird **exklusiv** für Kosten/negativ/Fehler. Einziger sichtbarer Serien-Wechsel, gebündelt am v4.0.0-Flip. **A0-To-do:** Bestand als Token kodifizieren (Mini-Wert-Drifts wie solar `#fbbf24` vs. `#f59e0b` je Rolle kanonisieren; Fehlfarben wie `wpErsparnis`=rot — eine *Ersparnis* in Rot — auf die Geld-Logik grün/rot bereinigen), Status-Achse ergänzen. Die Datentyp-Achse bildet die 8-Wert-`COLOR_CLASSES` ab; die Status-Achse (OK/Warning/Error/Info) braucht noch eigene Token-Werte.

> **✅ Update 2026-06-12 (F2 / Fundament-P1):** Der Netzbezug-Wechsel `#ef4444` → `#b91c1c` wurde mit **Fundament-P1 GESHIPPT** (nicht erst am v4-Flip); **Signal-Rot `#ef4444` ab sofort exklusiv** für Kosten/negativ/Fehler. **Farb-SoT = `lib/colors.ts`** (vervollständigte Zentrale + Wächter `npm run check:design`), **NICHT** ein `design-tokens`-Modul; der A0-Liefer-Artefakt-Text gilt entsprechend angepasst. Die übrigen Token-Tabellen (A1 Typo / A4 Animation / C1 Spacing-Radius-Schatten) werden in **Fundament-P6** als Doc-Tabellen befüllt (Doc-Pflicht vor E3).

**Keine Farbtabelle im Doc** — die verbindlichen Werte stehen in `lib/colors.ts` (SoT); Doc-Tabellen driften (§9-Lehre). A2 bleibt **Pointer** (löst den Doc-Konflikt K1 mit Fundament-P6.1 auf).

**Betroffene Issues:** *(noch keine direkten)*

---

### A3 — Datenzustand-Vokabular

> **Unterscheidung:** `—` (echte Datenlücke) · *N/A* (strukturell nicht zutreffend, z. B. Komponente nicht vorhanden) · `…` (in Berechnung) · `?` (unsicher / Schätzung).
> Display-Token `—` bereits etabliert (v3.29.1 #239). **Ist-Stand (2026-05-31, aktualisiert 2026-06-12):** `fmtKpi`-Helfer + `/dev/design-preview`-Galerie (rendert alle vier Tokens) existieren. **Update P1 (Entscheid Nr. 5):** SoT-Heimat geklärt — `fmtKpi` ist nach **`lib/formatting.ts`** umgezogen (kein `design-tokens.ts`); offen bleibt nur die durchgängige Anwendung.

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
> **Komponenten-Typ-Icons:** via `lib/komponentenStyle.ts` (Records für alle Typen angelegt P1; reale Nutzung bisher WP/Speicher, übrige Dashboards folgen — Disc #163, s. Update unten).
> **A5 in zwei Schritten (2026-05-31, durch P1 erledigt — s. Update unten):** die vorhandenen `WP_KPI`/`SPEICHER_*`-Konstanten wurden **damals nirgends real konsumiert** (Dashboards hardcodeten title/icon/color) — also (a) zuerst WaermepumpeDashboard/SpeicherDashboard auf den SoT umstellen (SoT erstmals einziehen), (b) dann die fünf fehlenden Typen ergänzen. „PV-Anlage" ist dabei ein UI-Aggregat (pv-module/wechselrichter/balkonkraftwerk), kein eigener `InvestitionTyp`.
> **✅ Update 2026-06-12 (P1):** D2-Kanon **komplett** in `komponentenStyle.ts` — alle 7 Typen + 3 Sonstiges-Varianten als KPI-Records angelegt; Schritt (a) erledigt: **WP- + Speicher-Dashboard konsumieren die Records real**. Offen nur die Übernahme in die übrigen 5 Dashboards (B9/E1-P2). `COLOR_CLASSES` = einzige Definition, `ui/KPICard.tsx` leitet ab (keine Parallel-Pflege).
> **Status-Icons:** konsistent (Check/Warning/Error/Info).
> **Dekorative Icons** in Headern/Bannern vermeiden (Forum #206 P2-Linie).

**Betroffene Issues:** #210 (Komponenten-Icons in Finanzen), #258 P3 (Box-Icon-Position), #244 (Cockpit-Banner-Icon).

---

### A6 — Berechnungs-Transparenz (Formel-Tooltip)

> **Prinzip:** Jede *abgeleitete/aggregierte* Kennzahl (KPI, ROI, Autarkie %, Ersparnis, Wirkungsgrad, Prognose) zeigt ihre Herleitung auf Abruf — Formel + eingesetzte Werte + Datenquelle/Zeitraum. Rohe Zählerwerte und triviale Summen bleiben tooltip-frei (kein Rauschen).
> **Affordance:** konsistenter, dezenter Indikator (z. B. gepunktete Unterstreichung oder kleines ⓘ). Progressive Disclosure — versteckt bis Hover/Tap, daher **kein Profi-Modus** (dient gerade Einsteigern „woher kommt die Zahl?").
> **Architektur (SoT):** Der Berechnungs-Layer-Helfer (`core/berechnungen/`, ADR-001) liefert **neben dem Wert eine strukturierte Herleitung** `{ wert, einheit, formel, eingesetzte_werte[], quelle, zeitraum }` — Wert UND Erklärung aus *einer* Quelle, können nicht driften. Vertrag in [KONZEPT-BERECHNUNGS-LAYER.md §6](KONZEPT-BERECHNUNGS-LAYER.md); dieselbe Herleitung speist perspektivisch PDF + Daten-Checker. Bestehend: `FormelTooltip` (ROIDashboard) als Vorbild, B1 nennt den Berechnung-Tooltip.
> **A3-Kopplung:** der Tooltip erklärt auch, *warum* ein Wert `—`/`N/A`/`?` ist (Datenlücke vs. strukturell vs. Schätzung).
> **Mobile:** kein Hover auf Touch → Tap/Long-press-Popover (Touch-Target ≥ 44 px, siehe Mobile M4).

> **✅ Tooltip-Kanon (visuell, Fundament-P3, 2026-06-13).** EIN dunkles Tooltip-Design für alle:
> - **Fläche:** `bg-gray-900 dark:bg-gray-950 text-white`, `rounded-lg`, `shadow-lg` — in beiden Modi dunkel. Daten-Tooltips `p-3 text-sm`, Micro-Tooltips (title-Ersatz, `SimpleTooltip`) `px-2 py-1 text-xs`.
> - **Quellen:** `ChartTooltip` (alle Recharts-Charts via `content={<ChartTooltip/>}`, de-DE-Format + Farb-Punkte), `FormelTooltip`/`SimpleTooltip` (`ui/`), `useTouchTitleTooltip` (Hook, `title=`-Ersatz auf Touch, Farbe aus `TOOLTIP_FARBEN`). Etwaige rohe `<Tooltip/>` fängt eine zentrale `index.css`-Regel (`.recharts-default-tooltip`) auf dieselbe dunkle Optik ab.
> - **z-Layer:** alle Tooltips/Tooltip-Popovers auf `z-[10000]` (über Modal `z-50`); JS-Inline-SoT `Z_TOOLTIP` (`lib/constants.ts`).
> - **Mobile:** `FormelTooltip`/`SimpleTooltip` haben Click-Toggle; `title=` via `useTouchTitleTooltip`; Recharts-Charts reagieren nativ auf Touch (Tap/Drag).

**Betroffene Issues:** #243 B9 (FormelTooltip-Konsolidierung), Disc #162 (fmtKpi/Datenzustand).

---

### A7 — Daten-Aktualität & Quelle

> **Prinzip:** Jede Datensicht zeigt konsistent **Stand** (Zeitstempel „Stand: TT.MM.JJJJ HH:MM" bzw. „Live") und **Quelle** der Werte — der Nutzer muss erkennen, wie frisch und woher eine Zahl ist.
> **Quellen-Vokabular:** HA-LTS · Live-Snapshot · Custom-/Cloud-Import · Prognose-Quelle (OpenMeteo / eedc / Solcast). Konsistente Kurzlabels/Icons.
> **Live vs. LTS:** Live-Werte (5-Min/Power) sichtbar von aggregierten LTS-Tageswerten unterscheidbar machen — die Frische-Differenz ist ein wiederkehrender Verwechslungs-Punkt.
> **Platzierung:** dezent am Sektions-/Karten-Header oder via A6-Tooltip, nicht pro Zelle.

**Betroffene Issues:** Daten-Provenance-/Daten-Checker-Linie, Live-vs-LTS-Konsistenz (#135-Folge).

---

### A8 — Hell/Dunkel-Modus (Light/Dark)

> **✅ Umgesetzt mit Fundament-P2 (2026-06-13).** Mechanismus: `ThemeContext` (`light`/`dark`/`system`, localStorage `eedc-theme`, `<html class="dark">`). Entscheid **F5(a):** Serien-/Datenfarben sind in **beiden Modi identisch** (keine aufgehellten Dark-Serienfarben — das wäre ein eigenes späteres Projekt). Dark-Anpassung betrifft nur Text-Kontrast, Chart-Infrastruktur (Achsen/Grid) und Abgrenzung (Border statt Schatten).

**Text-Paarungen (de-facto-Kanon, verbindlich):**

| Light | Dark | Rolle |
|---|---|---|
| `text-gray-900` | `dark:text-white` | Primärtext / Überschriften |
| `text-gray-700` | `dark:text-gray-300` | Fließtext |
| `text-gray-600` | `dark:text-gray-400` | Sekundärtext |
| `text-gray-500` | `dark:text-gray-400` | gedämpfter Text |
| `text-gray-400` | `dark:text-gray-500` | **Muted/Icons/Captions** (im Dark dezent *dunkler*, sonst zu hell auf Dunkelgrund) |
| `bg-white` | `dark:bg-gray-800` | Karten/Flächen |
| `border-gray-200` | `dark:border-gray-700` | Rahmen |

> Die Muted-Zeile (`text-gray-400 → dark:text-gray-500`) ist bewusst „dunkler im Dark Mode": gedämpfter Text/Icons sind auf Dunkelgrund sonst zu präsent. Das ist der dominante Bestand (P2-Sweep über 254 Stellen). Disabled-States (`text-gray-500 dark:text-gray-500`) sind eine bewusste Ausnahme (gewollt geringer Kontrast).

**Charts — zwei klar getrennte Mechanismen (Regel Nr. 0):**

1. **Recharts-TEXT** (Tick-Werte, Legende, Pie-Labels) → zentrale `html.dark .recharts-*`-Overrides in `index.css` (Catch-all, greift ohne Pro-Komponenten-Props).
2. **Recharts-STROKES/FILLS** (CartesianGrid, ReferenceLine, PolarGrid, neutrale Balken) → Hook **`useChartTheme()`** (`context/ThemeContext.tsx`), liefert `CHART_ACHSEN.{light|dark}` modusabhängig. **Kein** hartkodiertes `CHART_ACHSEN.light.*` mehr in Komponenten.

> **`CHART_ACHSEN` führt bewusst KEINEN `border`-Key.** Card-/Tabellen-Rahmen laufen über Tailwind `border` / `dark:border-gray-700` (siehe Text-Paarungen) — ein Muster pro Aufgabe. `CHART_ACHSEN` bleibt auf Recharts-Inline-Styles (`achse`/`grid`/`referenz`, je hell+dunkel) beschränkt; die Modus-Matrix ist `lib/colors.ts:CHART_ACHSEN` (SoT, keine Doc-Tabelle — A2-Pointer-Prinzip).

**Schatten-Kanon:** Light = `shadow-sm` (Tailwind-Default, **kein** eigener boxShadow-Token). Dark = **Border-Abgrenzung** statt Schatten (Schatten ist auf `gray-800` quasi unsichtbar) — **kein `dark:shadow-*`-Ausbau**. Bewusst nur diese eine Stufe.

**Betroffene Issues:** F5 (Dark-Mode-Variante), §3-Inventur (243 `text-gray-400`-Lücken).

---

## Teil B — Komponenten

### B1 — KPI-Karten

> **Layout:** Titel oben · Wert (groß) zentral · Einheit (klein) rechts vom Wert · optional Icon dezent unten/Hintergrund · optional Subtitle/Berechnung-Tooltip.
> **Einheits-Position einheitlich:** entweder rechts vom Wert ODER eigene Zeile darunter — nicht gemischt (#258 P1).
> **Inhalts-Ausrichtung horizontal:** Werte aller Karten einer Reihe auf gleicher Baseline (#258 P2).
> **Icon-Position:** alle Karten einer Sektion gleich, oder konsistent „ohne Icon" (#258 P3).
>
> **SoT-Komponente** statt der heute parallelen Implementierungen (B9 KPICard-Konsolidierung als Pflicht-Item).

**Vorbedingung:** Konsolidierung der KPICard-Implementierungen (B9 in #243). **Ist-Stand (2026-05-31, verifiziert):** nicht drei, sondern **fünf** echte `KPICard` (`components/ui/`, `components/dashboard/`, `pages/auswertung/` + inline `ROIDashboard.tsx:710` + inline `community/KomponentenTab.tsx`) **plus drei `KpiCard`-Label-Helfer** (EnergieprofilPrognose/-Monat/-Tab) = 8 Definitionen, von 29 Dateien referenziert (Stand 2026-06-11). Die Community-Variante (`community_avg`/`invertColors` Vergleichs-KPI) ist **nicht** in einen reinen Size-Varianten-SoT mergebar und bleibt ggf. eigene Komponente.
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
> **Sub-Nav:** **Unterstrich + Icons** (`components/layout/SubTabs.tsx`) als Standard. `components/ui/PillTabs.tsx` wird deprecated und in seinen Verwendern migriert (#243 B1, detLAN-Klärung #216) — als Vor-Schritt vor dem v4.0.0-IA-Refactor. **Ist-Stand (aktualisiert 2026-06-11):** PillTabs hat noch **drei** Verbraucher (Auswertung, Aussichten, Community) — DesignPreview nutzt PillTabs nicht mehr (nur Deprecated-Kommentar, Stand 05/2026: vier); EnergieprofilTab nutzt PillTabs **nicht** direkt. Achtung: **kein 1:1-Swap** — `SubTabs` ist route-/`NavLink`-getrieben, `PillTabs` state-getrieben (`onChange`/`activeKey` + `beta`-/`tooltip`-Props, die SubTabs fehlen). **✅ Entschieden (2026-05-31): Sub-Tabs auf echte URL-Routen heben** (zukunftssicher, teilbare Links, passt zur Redirect-Tabelle); die State-Features von PillTabs (beta-Badge, Tooltip) werden auf der route-getriebenen `SubTabs` nachgebaut. B1 ist damit gegen die Redirect-Tabelle isoliert testbar.
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

> **Persistenz:** Aufklapp-Status **und Reihenfolge** pro Sektion in LocalStorage (etabliert für Monatsberichte/Energieprofil-Monat — Vorbild laut detLAN #258 P5; Reorder kam gut an). Konsistente Implementierung über alle Verwender. **Drift-Befund (2026-05-31):** `CollapsibleSection` (Key `eedc-collapse-${storageKey}`) und `SortableSection` (Key `${prefix}_section_${title}`) führen je eigene State-Logik — die geforderte Konsistenz ist intern bereits gebrochen.
> **✅ Entschieden (2026-05-31, korrigiert 2026-06-01): EIN Sektions-Persistenz-SoT.** Statt `SortableSection` ersatzlos zu streichen (das war die ältere, mit dem Cap verwechselte Fassung — siehe Korrektur oben), werden Auf/Zu **und** Reihenfolge in **einem** Mechanismus zusammengeführt (`CollapsibleSection` um die Reorder-Fähigkeit erweitert, `SortableSection` darin aufgelöst). Reorder bleibt also als Funktion erhalten, nur ohne Doppel-Logik. **Geltungsbereich:** Cockpit-Zeitsichten ja; Komponenten-Hub fix (IA-V4 Variante C). detLAN (#175) bleibt bedient.
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
> SoT: **überholt (Update 2026-06-12)** — **kein** `design-tokens.ts`; die konkrete C1-Spacing-Tabelle füllt **Fundament-P6** als Doc-Norm (Tailwind-Theme nur bei echtem Klassen-Bedarf). `lib/spacing.ts` entfällt weiterhin.
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
