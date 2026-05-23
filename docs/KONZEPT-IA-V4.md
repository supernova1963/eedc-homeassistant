# eedc Informationsarchitektur v4.0.0

> **Status:** Konzept-Fundament für den großen IA-Schnitt zur Version 4.0.0. Bewusste Abkehr von der wachsend-Linie für **diesen einen** Refactor — die Achsen-Struktur lässt sich nicht inkrementell migrieren, ohne zwischenzeitlich noch unstrukturierter zu wirken als heute.
>
> **Eingangsperspektive:** Heutige Top-Nav (Cockpit / Live / Auswertungen / Aussichten / Community) vermischt drei Achsen — Zeit, Komponente, analytischer Schnitt. Folge: jeder Anwender-Frage entsprechen mehrere plausible Klick-Pfade, „lange gesucht, nicht gefunden" wird zur wiederkehrenden Tester-Rückmeldung. v4.0.0 trennt die Achsen.
>
> **Verwandte Dokumente:** [KONZEPT-STYLE-GUIDE.md](KONZEPT-STYLE-GUIDE.md) (visuelle Sprache) · [KONZEPT-MOBILE.md](KONZEPT-MOBILE.md) (Mobile-Verhalten) · [#243](https://github.com/supernova1963/eedc-homeassistant/issues/243) (operativer Bausteine-Tracker).

---

## Leitprinzip: Drei orthogonale Achsen

| Achse | Anwender-Frage | Top-Eintrag |
|---|---|---|
| **Zeit** | „Was passiert/passierte/passiert noch?" | **Cockpit** |
| **Was** | „Wie geht's meinem X?" | **Komponenten** |
| **Wie** | „Wie viel hab ich gespart / wann amortisiert / wie ist die CO₂-Bilanz?" | **Auswertungen** |

Jede Anwender-Frage hat genau **eine** kanonische Heimat. Cross-Links verbinden die Achsen, ohne sie zu duplizieren (siehe „Cross-Linking-Pattern" unten).

---

## Top-Nav v4.0.0

```
Live-Indikator  ·  Cockpit  ·  Komponenten  ·  Auswertungen  ·  Community  |  Hilfe  Einstellungen
```

- **5 Inhalts-Einträge** plus Hilfe und Einstellungen — passt auf Desktop ohne Engpass.
- **Mobile:** Hamburger-Menü mit voller Liste (Standard-Pattern). Bottom-Tab-Bar wäre Big-Bang-Mobile-Redesign — bewusst nicht v4.0.0.
- **Standard-Landing:** `/` → `/cockpit/live`. Live bleibt Erstkontakt — es ist eedcs Highlight.

---

## Cockpit (Zeit-Achse)

Sub-Tabs in chronologischer Reihenfolge:

| Tab | Inhalt | Heute entspricht |
|---|---|---|
| **Live** | Echtzeit-Verläufe, Live-Tiles pro Komponente | `LiveDashboard.tsx` |
| **Heute** | Tages-KPIs + heutiger Verlauf bis jetzt | NEU — heutiger Stand kondensiert |
| **Monatsbericht** | Aktueller Monatsstand mit allen Sektionen | `MonatsabschlussView.tsx` |
| **Jahr** | Jahres-KPIs + Monats-Vergleichs-Verlauf | Teile aus `Auswertung.tsx` Tab „Energie" |
| **Aussicht** | Kurzfrist / Prognosen / Langfrist / Trend | `Aussichten.tsx` (interne 5 Tabs konsolidiert) |

**Cockpit-Innenseiten-Pattern (Top-Down):**

1. KPI-Strip oben — die 3–4 wichtigsten Zahlen der Zeitebene
2. Visueller Hauptblock (Chart, Tile-Grid, Verlauf)
3. Detail-Sektionen darunter, jeweils mit Cross-Link zur entsprechenden Komponenten-Seite

**Aussicht-Konsolidierung:** Die heutigen Aussichten-Sub-Tabs (Kurzfristig / Prognosen / Langfristig / Trend / Finanzen) werden im Cockpit/Aussicht-Tab zu einer linearen Seite mit Zeit-Horizont-Selektor (7 Tage / 14 Tage / Monat / Jahr) und Sektionen. „Finanzen-Prognose" wandert nach Auswertungen/Finanzen — analytischer Schnitt, gehört dort hin.

---

## Komponenten (Was-Achse)

Sub-Tabs pro Komponententyp:

```
PV-Anlage  ·  Speicher  ·  Wärmepumpe  ·  E-Auto  ·  Wallbox  ·  BKW  ·  Sonstiges
```

Tabs erscheinen nur, wenn die Anlage die jeweilige Komponente hat (strukturell N/A → Tab ausgeblendet, vgl. Style-Guide A3 Datenzustand-Vokabular).

**Innenstruktur pro Komponenten-Seite (Variante C):**

```
/komponenten/speicher

[Datums-Selektor: Mai 2026 ▾]                           (sticky)

▼ Aktueller Status
  [KPI-Strip: SoC · Energie heute · Zyklen · Verfügbarkeit]
  [Live-Verlauf-Chart]

▼ Verlauf im Zeitraum
  [Tages-/Monatschart je nach Datums-Selektor]
  [Detailtabelle, default zu]

▼ Vergleich
  [Vorjahr / Vormonat]

▼ Aussicht
  [Komponentenspezifische Prognose: wann voll/leer, Empfehlung]
```

**Designentscheidungen:**

- **Datums-Selektor statt Sub-Sub-Tabs:** Eine Achsen-Kontrolle oben, alle Sektionen folgen dem Datum. Mobile-tauglich (kein Sub-Sub-Tab-Layout, keine doppelte Zeit-Achse zur Cockpit-Zeit-Achse).
- **Lineare Sektion-Reihenfolge:** Status → Verlauf → Vergleich → Aussicht. Vier Sektionen sind genug und stabil über alle Komponententypen — keine komponentenspezifische Sondersortierung.
- **Energieprofil verschwindet als eigenständige Seite:** Stündlicher Verlauf wird Teil der „Verlauf im Zeitraum"-Sektion, komponentenspezifisch (Strom-Profil bei PV-Anlage, Wärme-Profil bei Wärmepumpe).
- **Komponentenspezifische KPIs** via `lib/komponentenStyle.ts` als SoT (Style-Guide A5 + B9). Erweiterung auf E-Auto/BKW/Wallbox/Sonstiges/PV-Anlage ist Pflicht-Voraussetzung — heute nur WP+Speicher (Disc #163).

---

## Auswertungen (Wie-Achse)

Sub-Tabs als analytische Schnitte über die ganze Anlage:

| Tab | Inhalt | Heute entspricht |
|---|---|---|
| **Finanzen** | Ersparnis, Erlös, Strompreis-Historie, Finanzen-Prognose | `Auswertung.tsx`/finanzen + `Aussichten.tsx`/finanzen |
| **CO₂** | Bilanz, Vermeidung, **CO₂-Amortisation** (#284) | `Auswertung.tsx`/co2 |
| **ROI** | Investitions-ROI, Kumuliert, Aussichten | `ROIDashboard.tsx` |
| **Tabelle** | Rohdaten-Übersicht, CSV-Export | `Auswertung.tsx`/tabelle |
| **Prognose-vs-IST** | Genauigkeits-Tracking, Bias, Quellen-Vergleich | `PrognoseVsIst.tsx` |

**Was aus heutigem Auswertungen wegfällt:**

- Tab „Komponenten" → wandert in den **Komponenten**-Top-Eintrag.
- Tab „PV-Anlage" → wandert in **Komponenten/PV-Anlage**.
- Tab „Investitionen" → reine Pflege-Übersicht, gehört nach **Einstellungen/Investitionen** (ist es bereits).
- Tab „Energie" → die Jahres-Verlauf-Anteile wandern in **Cockpit/Jahr**, die Aggregate-Tabelle bleibt als **Auswertungen/Tabelle**.
- Tab „Energieprofil" (beta) → siehe Komponenten-Hub-Auflösung oben.

---

## Einstellungen (Konfigurations-Hub)

Bleibt als Sammelpunkt aller Pflege- und Setup-Routen, wird visuell modernisiert:

```
/einstellungen

[🔍 Suchen in Einstellungen …]

ANLAGE              → Anlage · Strompreise · Investitionen · Solarprognose
DATEN               → Monatsdaten · Energieprofil-Pflege · Daten-Checker · Einrichtung
INTEGRATION         → Sensor-Zuordnung · Statistik-Import · MQTT-Export · Import-Wizards
SYSTEM              → Allgemein · Backup · Protokolle
DATEN TEILEN        → Community-Share
```

**Designentscheidungen:**

- **Kachel-Grid statt linearer Sub-Nav-Liste** als Landing. Klick auf Kachel → Detail-Seite (URL unverändert, `/einstellungen/anlage` etc.).
- **Fuzzy-Such-Feld** über alle Einstellungs-Routen (Vorläufer der globalen Cmd+K-Suche, siehe Bausteine-Tracker B14).
- **Status-Indikator pro Kachel:** `✓` eingerichtet · `⚠` unvollständig · `🆕` noch nicht eingerichtet. Nutzt vorhandenes Backend-Wissen (Anlage-geprüft-Flag, Sensor-Mapping-Vollständigkeit, …).
- **Import-Wizards bündeln** in einer Kachel mit Sub-Liste (Portal-Import / Cloud-Import / Custom-Import / Connector / HA-Statistik). Heute fünf einzelne Routen, eine Kachel reicht.
- **Detail-Seiten behalten linke Sticky-Sub-Nav** auf Desktop (schnelles Springen zwischen Einstellungen ohne Hub-Rücksprung). Mobile: Hamburger.

---

## Cross-Linking-Pattern

Verbindet die drei Achsen ohne Doppelung der Inhalte.

| Klick auf | Springt zu |
|---|---|
| Komponenten-Tile in Cockpit/Live | `/komponenten/<typ>` |
| KPI-Kachel im Cockpit/Heute | entsprechende Auswertung (Finanzen-KPI → Auswertungen/Finanzen) |
| Zeile in Auswertungen/Tabelle für Monat M | `/cockpit/monatsbericht` mit Datum M |
| Komponenten-KPI „Erlös" | `/auswertungen/finanzen` |
| Komponenten-KPI „CO₂" | `/auswertungen/co2` |
| Vorschau in Cockpit/Aussicht für Komponente X | `/komponenten/<x>` Sektion „Aussicht" |

**Regel:** Jede Anwender-relevante Zahl, die in mehr als einem Kontext sinnvoll wäre, hat genau **eine** Detail-Heimat und wird von den anderen Kontexten verlinkt — nicht dupliziert.

Cross-Links visuell dezent (Pfeil-Icon rechts neben KPI-Wert oder Sektion-Header), kein primärer Button-Stil.

---

## Migrations-Plan

**Strategie:** Großer Schnitt zur Version 4.0.0, vorbereitet durch Token- und Komponenten-Pflicht-Arbeiten.

### Phase 0 — Vorbereitung (kein UI-Change, vor v4.0.0)

| Schritt | Inhalt |
|---|---|
| **A0** | Design-Tokens (Typo · Farben · Spacing · Schatten · Radius) als Tailwind-Theme + `lib/design-tokens.ts`. Keine sichtbare UI-Änderung. |
| **B1** | PillTabs → SubTabs-Migration (3 Verwender: Aussichten, Auswertung, Community). Vereinheitlicht Sub-Nav-Komponente, die in Cockpit-Sub-Tabs + Komponenten-Hub gebraucht wird. |
| **B9-Vorbereitung** | KPICard-SoT-Komponente mit `size: 'sm' \| 'md' \| 'lg'` + Color-Enum. Drei alte Versionen migrieren. Pflicht-Item, weil v4.0.0 saubere KPI-Strips überall braucht. |
| **A5-Vorbereitung** | `lib/komponentenStyle.ts` auf E-Auto, BKW, Wallbox, Sonstiges, PV-Anlage erweitern (Disc #163). Vorbedingung für konsistente Komponenten-Seiten. |

### Phase 1 — v4.0.0 IA-Refactor (ein Release)

1. Top-Nav umstellen: Live raus (wird Cockpit/Live), Aussichten raus (wird Cockpit/Aussicht), Komponenten als neuer Top-Eintrag.
2. Cockpit-Sub-Tabs Live/Heute/Monatsbericht/Jahr/Aussicht implementieren.
3. Komponenten-Hub-Seiten pro Typ implementieren (lineare Variante C).
4. Auswertungen entrümpeln (Tabs Komponenten/PV-Anlage/Investitionen/Energie/Energieprofil raus, Tabs Finanzen/CO2/ROI/Tabelle/Prognose-vs-IST).
5. Einstellungs-Landing als Kachel-Grid mit Suche + Status.
6. URL-Redirects für alle Bestandspfade (siehe Tabelle unten).
7. Release-Notes mit Migrations-Hinweisen, in-App-Hilfe-Eintrag „Wo ist X hin?".

### Phase 2 — Folge-Wellen (post-v4.0.0)

- **B10** PageHeader-Konsolidierung (39 Seiten von hardcoded `<h1>` migrieren)
- **B14** Globale Cmd+K-Suchpalette
- **B5** Mobile-Reduce-Etappen (M1 Reduce-Logik, M2 Sticky-Header auto-hide, M3 Tabellen-Swipe)
- **B12** Single-Anlage-Selektor-Audit

---

## URL-Redirect-Tabelle

Alle Bestandspfade müssen redirected werden — Foren-Posts, Memory-Pfade, Issue-Links sollen nicht brechen.

| Alt | Neu |
|---|---|
| `/live` | `/cockpit/live` |
| `/cockpit` | `/cockpit/live` (Default-Landing) |
| `/cockpit/aktueller-monat` | `/cockpit/monatsbericht` |
| `/cockpit/monatsberichte` | `/cockpit/monatsbericht` |
| `/cockpit/pv-anlage` | `/komponenten/pv-anlage` |
| `/cockpit/e-auto` | `/komponenten/e-auto` |
| `/cockpit/waermepumpe` | `/komponenten/waermepumpe` |
| `/cockpit/speicher` | `/komponenten/speicher` |
| `/cockpit/wallbox` | `/komponenten/wallbox` |
| `/cockpit/balkonkraftwerk` | `/komponenten/bkw` |
| `/cockpit/sonstiges` | `/komponenten/sonstiges` |
| `/aussichten` | `/cockpit/aussicht` |
| `/auswertungen` | `/auswertungen/finanzen` (oder erste verfügbare Sub) |
| `/auswertungen/prognose` | `/auswertungen/prognose-vs-ist` |

Konventions-Regel: jede Bestandsroute kriegt einen `Navigate replace` in `App.tsx`. Keine 404s.

---

## Was bewusst NICHT im v4.0.0-Scope ist

- **Funktionale Erweiterungen** — v4.0.0 ist reine Struktur + Designsprache. Inhalts-Features (z. B. CO₂-Amortisation #284) sind eigene Bündel.
- **Theme-Editor / freie Card-Anordnung / Dichte-Profile** — siehe Style-Guide „Einstellbarkeits-Cap" (Hell/Dunkel-Mode + Mobile-Reduce-Default sind die einzigen Achsen).
- **Backend-Refactor** — Achsen-Trennung passiert rein im Frontend. Routen + Read-Sites verlinken, sonst keine Berechnungs-Änderungen.
- **Performance-Optimierung** (Code-Splitting, Lazy Loading) — separater Refactor-Sprint.
- **Bottom-Tab-Bar auf Mobile** — Hamburger reicht.

---

## Risiken + Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| Bestandstester sucht Aussichten als Top-Eintrag | Release-Notes prominent, Hilfe-Eintrag „Wo ist Aussichten hin?", evtl. einmaliger Toast „Aussichten findest du jetzt im Cockpit unter Aussicht" |
| Foren-Links brechen | Vollständige Redirect-Tabelle in `App.tsx`, automatischer Test der alten Pfade |
| Komponenten-Hub-Seite zu lang auf Mobile | CollapsibleSections mit `defaultOpenMobile={false}` für Verlauf/Vergleich, Sektion „Aktueller Status" bleibt initial offen |
| HA-Companion-App-Quirks (Sticky-Header, Downloads, `h-dvh`) | Querschnittsregeln aus Mobile-Konzept M4+M5 in Pflicht-Checkliste pro neuer Seite |
| Tab-Inflation kehrt zurück (Auswertungen hatte 8 Tabs) | Pro Top-Eintrag ≤ 5 Sub-Tabs als Designregel. Tab-Zuwachs braucht explizite Genehmigung in #243 |

---

## Querverweise

- **Visuelle Sprache (Tokens, Komponenten, Layout)** → [`KONZEPT-STYLE-GUIDE.md`](KONZEPT-STYLE-GUIDE.md)
- **Mobile-Verhalten** → [`KONZEPT-MOBILE.md`](KONZEPT-MOBILE.md)
- **Operativer Bausteine-Tracker** → [#243](https://github.com/supernova1963/eedc-homeassistant/issues/243)
- **Speicher-Auswertungs-Inhalte (B11 alt → Komponenten-Hub-Inhalt)** → [#142](https://github.com/supernova1963/eedc-homeassistant/issues/142) · [`KONZEPT-SPEICHER-AUSWERTUNG.md`](KONZEPT-SPEICHER-AUSWERTUNG.md)
- **CO₂-Amortisation** → [#284](https://github.com/supernova1963/eedc-homeassistant/issues/284)
