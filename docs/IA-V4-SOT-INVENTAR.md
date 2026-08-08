# IA-V4 — UI-SoT-Inventar (Standardisierungs-Register)

> ## **Status (gemessen 2026-08-08): lebendes Register — kein abgeschlossenes Vorhaben**
>
> **Aus `docs/drafts/` nach `docs/` gewandert (2026-08-08).** **[`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md) verweist in Invariante I12 auf dieses Register** (eine Komponenten-Klasse = EINE Komponente). Es lebt ausdrücklich über den v4.0.0-Flip hinaus, während die Plan-Dokumente des Umbaus archiviert sind.
> Es trägt bewusst **keine Versionsnummer, nur dieses Mess-Datum** (Muster aus #359) — ein Status,
> der eine Version nennt, altert garantiert.
>
> **Nicht auf der Website und nicht in der In-App-Hilfe:** `website/scripts/sync-docs.sh` und
> `scripts/sync-help.sh` arbeiten beide mit einer **Allowlist**, in der Konzepte und ADRs bewusst
> fehlen. Dieses Dokument ist im Repository lesbar — es ist kein Anwender-Handbuch.
>
> **Offen:** die nicht-✅-Zeilen im Register — vier ⬜ Querschnitt-Patterns (Sicht-Rahmen/PageHeader · Reload-Aktion · Leer-/Fehler-/Lade-Vokabular · Cross-Link) und mehrere 🔄. **Abgrenzung:** nur UI-Regime; Berechnungen gehören in den Berechnungs-Layer ([ADR-001](ADR-001-BERECHNUNGS-LAYER.md)) mit eigenem Konformitäts-Test.


> **Rolle:** Lebendes Backlog der **UI-/Design-Standardisierung**. Jedes app-weite Darstellungs-Pattern bekommt **eine** SoT-Komponente/Regel; hier steht, was schon SoT ist und was aussteht. **Lebt über den Flip hinaus** (anders als die Plan-Docs). Prozess: [`PLAN-IA-V4-ENTWICKLUNG.md`](drafts/archive/flip-v4/PLAN-IA-V4-ENTWICKLUNG.md) §6 (UI-Standardisierungs-Schleife).
>
> **Abgrenzung:** NUR UI-Regime. Berechnungen/Aggregate gehören in den **Berechnungs-Layer** (ADR-001) mit eigenem Konformitäts-Test — **nicht hier** dupliziert.
>
> **Werkbank:** Skeleton (`components/preview/IASkeleton.tsx`, backendlos). **Heimat:** `components/` + `lib/` + [`docs/KONZEPT-STYLE-GUIDE.md`](KONZEPT-STYLE-GUIDE.md). **Wächter:** `npm run check:design` = 0, Regel 0a.
>
> Legende: ✅ SoT steht · 🔄 in Arbeit · ⬜ offen · ❓ Status vor nächstem Touch prüfen

---

## Offen-Auszug (Stand 2026-07-28) — der Rest dieses Registers

> Die Tabelle unten ist lang; das hier sind die Zeilen, die **nicht** ✅ sind. **Ihre Heimat ist
> dieses Register selbst** — seit dem Umzug nach `docs/` ist es versioniert, aus `KONZEPT-IA-V4`
> (I12) verlinkt und wird bei der Paket-Wahl mitgelesen (`EINSTIEG-laufende-runde.md`
> §Neu-Einwertung, Schritt 3). Das frühere Sammel-Backlog
> als **DOK-4** (Q). Alle vier ⬜ sind Querschnitt-Patterns, die heute je Sicht ad-hoc gelöst werden —
> genau die Klasse, aus der Drift entsteht.

| Zeile | Status | Was fehlt |
| --- | --- | --- |
| **Sicht-Rahmen / PageHeader** (Titel + Status-Badge, O5/B10) | ⬜ | keine SoT-Komponente; 17 `.tsx` mit hartem `<h1`. Identisch mit IA-V4 Phase-2-Punkt **B10** |
| **Reload-/Sicht-Aktion** (nur laufender Zeitraum) | ⬜ | lebt heute je Sicht (`MonatHeader.onReload`, `JahrHeader`) |
| **Leer-/Fehler-/Lade-Zustände** (B8) | ⬜ | Vokabular nie kanonisiert; `OnboardingLeer`/`DatenLeer` sind Einzelfälle |
| **Cross-Link / Teaser** (Zeit-Sicht → Achsen-Deep-Dive, #3d) | ⬜ | bewusst zurückgestellt: der voreilige Cross-Link-Footer wurde 2026-06-20 entfernt |
| **Block-Identität** (`lib/blockStyle.ts`, #3b) | 🔄 | angelegt, nicht flächendeckend |
| **Chart-Hover-Cursor** (`CHART_HOVER_CURSOR`) | 🔄 | Default in `eedcTooltipProps`; v3-Seiten opportunistisch |
| **Scroll-Overflow-Schatten** (`ScrollSchatten`, A9) | 🔄 → **Wächter existiert inzwischen** | `npm run check:scrollschatten` ist in `package.json` (2026-07-28 nachgezählt) — die Notiz „Wächter geplant" unten ist überholt |
| **Provenance-/Quellen-Badge** | 🔄 | Slot steht (Status-Fusszeile); Rollout je Sicht + Icon-je-Quelle offen |
| **Status-Fusszeile** (G11) | 🔄 → **faktisch ✅** | P1–P4 gebaut **und** die dort als offen notierten Deep-Links zeigen heute auf die v4-Routen (`StatusFusszeile.tsx:151,191,212,228` → `/einstellungen/{daten,stammdaten,integration}`). Rest: optionaler „alle offenen Monate"-Count (nicht nötig) |
| **`WerteTabelle`** · **Button/Badge/Modal** | ❓ | vor dem nächsten Touch am Code verifizieren — nicht aus diesem Register schließen |

---

## Register

| Pattern | SoT-Heimat | Status | Notiz |
|---|---|---|---|
| **Farb-Rollen** | `lib/colors.ts` (+ `check:design`-Wächter) | ✅ | eine Datenrolle = eine Farbe; keine Inline-Hex außerhalb. **bg-Klassen-Zwillinge `STRING_BG` + `ROLLEN_BG`** (Aufteilungs-Segmente; von `check:design` nicht erfasst → bewusst in SoT). Netzbezug `#b91c1c` shippt am Flip |
| **KPI-Karte** | `components/ui/KPICard.tsx` | ✅ | 3 Größen sm/md/lg + 8-Farben-Enum + A6-Tooltip-Slot. 8 Defs → 1 (E1-P2) |
| **KPI-Strip** | `components/blocks/KpiStrip.tsx` | ✅ | auto-fit `minmax(248px)`-Grid (#243), `subtitle`/`trend`/`parkId`/`sicht`-Durchreichung (`sicht`-Provenance-Slot mit A.5 Sub 5 ergänzt — ROI-KPIs behalten ihre Sicht-Tooltips) |
| **Block-Schale** | `components/blocks/BlockShell.tsx` | ✅ | einklappbar/Fokus + **verschiebbar (`sortierbar`, ↑↓ + Persistenz je Sicht)** — Hub + Cockpit/Monat nutzen es (K-B4 „fix" revidiert 2026-06-22); Grau-Default für struktur-neutrale Blöcke |
| **Fokus/Vollbild (⤢)** | `components/blocks/FokusVollbild.tsx` (Overlay) + `FokusKachel.tsx` (Karte ohne Block-Stack) | ✅ | EIN bildschirmfüllendes Overlay app-weit (KONZEPT Z.76); **BlockShell** (⤢ je Block) + **FokusKachel** (⤢ je Karte, z. B. Cockpit/Live) teilen es — keine zweite Kopie. FokusKachel = Karte + ⤢ ohne Einklapp-/Sortier-Beiwerk (2026-06-22) |
| **Block-Identität (Icon+Farbe je Block)** | `lib/blockStyle.ts` | 🔄 | #3b — Kennzahlen/Energie-Bilanz/Verlauf/Werte/Finanzen/Community; semantische Blöcke tragen Rollenfarbe, Struktur-Blöcke neutral |
| **Tooltip-Kanon** | Style-Guide A6 + Tooltip-Komponente | ✅ | Fundament P-Reihe; `formel=`-Stellen kanonisiert |
| **Chart-Tooltip/Legende** | `components/ui/ChartTooltip.tsx` + `ChartLegende.tsx` + `eedcTooltip.tsx` | ✅ | S1: Farbe NUR als **Viereck-Swatch**, Text **monochrom** — identisch Tooltip+Legende. `ChartLegende` = voller `content`-Renderer. **Audit-D (2026-06-25):** `eedcTooltipProps()`-Factory (eigenes Modul) setzt **Hover-Cursor + Content an EINER Stelle** → `<Tooltip {...eedcTooltipProps({…})} />` (Recharts erkennt keine Wrapper-Components → `<Tooltip>` bleibt direktes Kind). **`percentOf`-Modus** → 3 helle Custom-%-Tooltips (Speicher/BKW/E-Auto-Jahresvergleich) entfernt. `#888`→`SERIE_NEUTRAL`. Default-Label aus `CHART_LABELS` → Tooltip≡Legende |
| **Chart-Label-Kanon** | `CHART_LABELS` (`lib/colors.ts`) | ✅ | Audit-D: zentrale `dataKey → Label`-Map, Default-`nameFormatter` (ChartTooltip) + Default-`formatter` (ChartLegende) → nie Roh-Keys (`pv`/`bat_neg`/…); Charts mit dynamischen Serien übersteuern. `tag/TagVerlaufChart` nameFormatter-Sofortfix |
| **Anteils-Balken** | `components/blocks/VerteilungsBalken.tsx` | ✅ | S2: feste Wert-Spalte → Grau-Tracks gleich lang (100 %-Baseline); `rounded-sm` (klare Kanten), `gap-3` Balken↔Text. PV EV/Einspeisung · WP Heizung/WW · Lade-Mix · BKW |
| **Chart-Hover-Cursor** | `CHART_HOVER_CURSOR` (`lib/colors.ts`) | 🔄 | S3/S4/S5: eine Hover-Mechanik = niedrig-Alpha-Grau-Rect (`cursor=`); Raster durch, Balken deckend, Dark dezent. In 14 v4+Komponenten-Bar-Charts; **jetzt Default in `eedcTooltipProps`** (D4 nicht mehr vergessbar) + Cursor in Live-/Monat-TagesverlaufChart + Sparklines nachgezogen; v3-Seiten opportunistisch |
| **Prognose-/Hilfslinien-Markierung** | `PROGNOSE_DASH` + `HILFSLINIE_DASH` (`lib/colors.ts`) | ✅ | Regel C (Gernot 2026-06-25, **zweites Token**): `PROGNOSE_DASH` = gestrichelt **nur wenn IST-Serie im selben Chart** (Prognose vs. gemessen eindeutig); `HILFSLINIE_DASH` = Summen-/Overlay-/Referenz-/Basis-Modell-Linien ohne IST-Aussage. Umgestellt: PVGIS-Referenz (AussichtTeile, war PROGNOSE_DASH), „Gesamt"-Summe (PVAnlageTab), Strompreis-Overlay (Live), `gesamterzeugung` (TagVerlaufChart). PROGNOSE_DASH bleibt SOLL-vs-IST (PVString/PrognoseVergleich/PrognoseVsIst/PVAnlageTab-SOLL/AktuellerMonat/Langfrist). NICHT auf reine Vorausschau ohne IST-Kontrast (WetterWidget-Forecast) |
| **Datenrollen-Farben + Komponenten-Identität** | `DATENROLLE` + `KOMPONENTEN_FARBEN` (`lib/colors.ts`) | ✅ | **COMMITTED `ea53a52b` (Regel A/B):** Identitäts-Map `KOMPONENTEN_FARBEN` `{hex,bg,text,tint}` je Investitionstyp = SoT; `TYP_COLORS`/`TYP_TEXT_CLASS`/`KATEGORIE_FARBEN` leiten ab (kein zweiter Satz). eauto≠wallbox (teal/cyan), WP=rot, BKW=amber-400, pv-system=amber-600, Mini-BHKW=lime, Haushalt=slate; EV-Rolle bleibt violett. 3 Backend-Farbquellen kanonisiert + Guard-Test. §8 Hardcoded-Maps (Investitionen/MonatsabschlussView/6 IST-Dashboards) migriert. „Eine Datenrolle = eine Farbe" als **EINE** Quelle (Rolle → `{hex, bg}`): EV/Direktverbr.=violett · Einspeisung=emerald · Netzbezug=rot · Speicher-Ladung=orange/-Entladung=blau · PV=amber. `ROLLEN_BG` leitet ab; Bilanzen (Monat/Tag/Jahr) + `komponentenAdapter` umgestellt — vorher 3× divergent (Inline `bg-purple/green` ≠ ROLLEN_BG ≠ CHART_COLORS). **PV-Module** = `PV_MODUL_FARBEN/BG` (Amber-Schattierungen, keine Rollen-Kollision). **Regel-Scope (Gernot entschieden 2026-06-24):** Amber NUR wo Module+Rollen im selben Chart (Hub-Verlauf); eigenständige String-Charts (PVStringVergleich SOLL/IST) behalten distinkte `STRING_COLORS` (kein Kollisionsgrund, bessere String-Trennung). **Audit-E (2026-06-25):** `DATENROLLE.*` um `text`+`fill`-Tailwind-Zwillinge erweitert + `GELD_TEXT_CLASS` (Hell/Dunkel). Umgestellt: Speicher-/BKW-Tabellen, 3 Rail-PV-Bars, **Warmwasser-Kanon rot-400** (Gernot-Entscheid: WP-Familie statt blau → `CHART_COLORS.wpWarmwasser` + WP-Tabelle), **V2H** violett→cyan, **Geld-Headlines** WP/EAuto/Wallbox, **Wallbox-ROI-Box** violett→cyan, **LiveHeuteKacheln** PV/EV/Einspeisung-Kacheln. **Nur noch ③:** EnergieBilanz-Bilanz-Semantik (grün/rot bewusst), WetterWidget-Custom-Legende-Struktur, `WETTERMODELL_FARBEN`-Map (opportunistisch) |
| **Ampel-Klassen** | `AMPEL_TEXT_CLASS`/`AMPEL_BG_CLASS` + `sollIstStufe()` (`lib/colors.ts`) | ✅ | Audit-G (2026-06-25): Tailwind-Zwillinge zu `AMPEL_SKALA` + Stufen-Helper; SOLL/IST-Fortschritts-Ampel (Monat-/Jahr-Bilanz, vorher 2× hart) + LiveSocBalken-SoC auf die SoT gezogen. `GaugeChart` nutzt weiter `AMPEL_SKALA`-Hex direkt (Gauge-Geometrie) |
| **Vergleichs-Badge / Dimm-/Opazitäts-Tokens** | `VERGLEICH_BADGE`, `AREA_FILL_OPACITY`/`SERIE_GEDIMMT`/`KONFIDENZ_BAND_OPACITY` (`lib/colors.ts`) | ✅ | Audit-H (2026-06-25): `VERGLEICH_BADGE.{besser,schlechter}` (▲/▼, vorher 3× wortgleich Monat-/Jahr-Bilanz+Rahmen); benannte Opazitäts-Tokens statt roher Magic-Numbers (Tagesverlauf-Flächen, Fokus-/Teildaten-Dimm, Prognose-Konfidenzband). `RingGaugeCard` `.toFixed`→de-DE-Komma |
| **Scroll-Overflow-Schatten** | `components/ui/ScrollSchatten.tsx` | 🔄 | L1: generischer Overflow-Fade (ResizeObserver, beide Achsen), NICHT breakpoint-gated. In `IASubTabBar`, `ZeitStepper`, Table-SoT (A14-1). **Seit 2026-07-03 Pflicht-Regel Style-Guide A9** (Fade statt Scrollbalken, appweit für Neues; Wächter `check:scrollschatten` geplant) — nicht mehr „opportunistisch" |
| **Datums-/Zeit-Navigation** | `v4/ZeitStepper.tsx` (+ Adapter `{Monat,Tag,Jahr}Stepper.tsx`) | ✅ | **L2b ✅ (2026-06-25):** EINE generische `ZeitStepper`-SoT (Hülle sticky/blur + Pille Player-Controls + Dropdown-Liste + L1-`ScrollSchatten` für die überlaufende Liste); die 3 Stepper = dünne Adapter (nur Navigation/Beschriftung, Tag mit Date-Picker-Direktsprung). Eltern (CockpitMonat/Tag/Jahr) unverändert → `merkeScroll`-Wiring (B1) erhalten. L2a-Feinschliff jetzt 1× statt 3×. Fußleisten-Variante VERWORFEN (= Status-Fusszeile). **R5-F2 (`64f5e2dd`, Gernot 2026-06-26):** Tag-Auswahl — Picker/Liste = letzte 90 Tage; die **Datumsauswahl** (Date-Input mobil `TagStepper` + Desktop `TagesRail`) erreicht **ALLE** verfügbaren Tage (`min`=ältester Tag aus `verfuegbare-monate`, da `tage-werte` auf 366 Tage gedeckelt) + **Zurücksetzen**-Button (neuester Tag). Das enge 90-Fenster war vorbestehend (`6cea9f1e`), NICHT Rainers Datenspar-Limit (abgelehnt). |
| **Top-Nav-Shell** | `components/layout/IATopNav.tsx` | ✅ | dual-API (`to`→NavLink / `onClick`+`active`); Preview + /v4 konsumieren; Produktiv-`TopNavigation` bis Flip separat. **Meta-Achse (Hilfe/Einstellungen) Desktop icon-only** (Tooltip+aria-label) — spart Breite an der lg-Grenze; Labels nur im Mobile-Hamburger (2026-06-20) |
| **Anlagen-Selektor** (globaler Kontextwähler) | View: `components/layout/AnlagenSelektorView.tsx` · verbunden: `v4/AnlagenSelektor.tsx` | ✅ | links neben Marke (Slot in IATopNav), Mobile im Hamburger; **ausgeblendet bei < 2 Anlagen**; Panel-Tokens vom Einstellungen-Dropdown. View geteilt von Vorschau (Demo-Daten) + /v4 (über `useSelectedAnlage`); View liegt in `layout/` für Flag-Reinheit (Vorschau im Prod-Build) (2026-06-20) |
| **Sub-Tab-Leiste** | `components/layout/IASubTabBar.tsx` | ✅ | geteilt Preview + /v4 |
| **Theme (Hell/Dunkel/System)** | `context/ThemeContext` + Cycle-Muster | ✅ | aus Produktiv-Bestand in Shell gezogen |
| **Werte-/Daten-Tabelle** | `WerteTabelle` (+ `lib/werte/*`) | ❓ | volle Funktion (Picker/CSV/Vergleich), nur Zeiträume variieren (O1-(b)); granularitäts-agnostisch. SoT-Stand vor Touch prüfen |
| **Sicht-Rahmen / PageHeader** (Titel+Status-Badge) | — (B10) | ⬜ | universell kanonisieren (O5); heute pro Sicht |
| **Provenance-/Quellen-Badge** (HA/Connector/gespeichert) | Status-Fusszeile sicht-Zone (`SichtStatus.quelle`) — Start | 🔄 | Universeller Slot **angestoßen** in der Status-Fusszeile (P4/P5, `Database`-Symbol + Popover). Live wired (`Demo-Daten`/`Live-Sensoren`). **Offen:** je-Sicht-Quelle melden (opportunistisch), Icon-je-Quelle, Verhältnis zum speicher-spezifischen `QuelleBadge` (kind ladepreis/wirkungsgrad bleibt eigen) |
| **Reload-/Sicht-Aktion** | — | ⬜ | nur laufender Zeitraum; in Sicht-Rahmen |
| **Leer-/Fehler-/Lade-Zustände** | — (B8) | ⬜ | universell; data-gated Sektionen |
| **Cross-Link / Teaser** (Zeit-Sicht → Achsen-Deep-Dive) | — | ⬜ | Teaser-Prinzip WKW:150 (#3d). **Voreiliger Cross-Link-Footer (Werte/Tabelle + Community-Nudge) aus Cockpit/Monat entfernt 2026-06-20** (Gernot: niemand hat den alten Ort gesehen → nicht signalisieren); echtes Teaser-Pattern bleibt offen für #3d. Achsen bleiben über Top-Nav erreichbar |
| **Komponenten-Stil** (Icon/Farbe/KPI je Typ) | `lib/komponentenStyle.ts` (D2) | ✅ | Hub-weit konsumiert (D2-Status-KPIs aller 6 Typen, `79e0c578`); „Wärme/Klima" statt „Wärmepumpe" (#263); Farb-Zwilling `TYP_TEXT_CLASS` leitet jetzt aus `KOMPONENTEN_FARBEN` ab (Regel A, `ea53a52b`) |
| **Aufteilung (2..n-Wege)** | `components/blocks/VerteilungsBalken.tsx` | ✅ | Label · Balken · Wert + % — EINE Bildsprache für PV EV/Einspeisung, WP Heizung/WW, Lade-Mix, BKW. **B7-Revision 2026-06-19: Donut → Balken**; Hub-weit konsumiert (alle Typen mit `aufteilung`) |
| **Komponenten-Hub geteilte IST-Charts** | `components/<typ>/` + `v4/<Typ>HubBloecke.tsx` + `v4/komponentenAnalyse.tsx` (Registry) | ✅ | **Konvergenz: EINE Code-Wahrheit IST-Dashboard + Hub** — IST-Charts als geteilte Komponenten extrahiert, IST-Dashboards refaktoriert (`79e0c578`). Registry-Slots `verlauf`/`vergleich`/**`wirtschaftlichkeit`** (+ Hub-Block) je Typ; Modell-Felder `kennzahlen`/`hinweise`/`selektorBadge` |
| **Inline-Aktion / Disclosure** | `components/ui/InlineAktion.tsx` | ✅ | **Monatsabschluss-V4 (2026-07-12):** schlanke 11px-Inline-Aktionen (Textlinks/Aufklapper ▾/Auswahl-Chips) — füllt die Lücke unter dem `min-h-36px`-`Button`, der für Inline-Affordanzen zu schwer ist. `ton` (neutral/aktion/bestaetigen/offen/warnung) · `variant` (link/chip) · `groesse` (xs/sm) · `unterstrichen` · `ariaExpanded`. Ersetzt 9 rohe `<button>` in 5 Assist-Komponenten (AssistenzFeld 5× · KopfAmpel · ZustandLegende · AbschlussReview · InvestitionSection); rohes `<button>` = SoT-Impl (`check-v4-migration` ROH_INFRA, wie DatumPicker) |
| **Erfassungs-Zustands-Badge** | `components/ui/ErfassungZustandBadge.tsx` + `ERFASSUNG_ZUSTAND`/`ZUSTAND_META` | ✅ | **Monatsabschluss-V4:** EIN Zustands-Vokabular (6 Labels/4 Farben: gemessen·geprüft=grün · geschätzt=gelb · weicht_ab=orange · offen/optional=grau) an Feld · Kopf-Ampel · Monatsdaten-Tabelle. Pill + `iconOnly`; Icon/Label zentral in `ZUSTAND_META`, Farbe in `ERFASSUNG_ZUSTAND` (`lib/colors.ts`) |
| **Button / Badge / Modal** | bestehende `components/ui/*` | ❓ | Bestand prüfen; bei Touch kanonisieren statt zweite Kopie |
| **App-weite Status-Fusszeile / System-Statusleiste** (G11) | `v4/status/StatusFusszeile.tsx` · `AppStatusContext.tsx` · `useGlobalStatus.ts` | 🔄 | Shell-Slice in `LayoutV4`. **P1–P4 ✅** (alle UNRELEASED): Shell+`AppStatusContext` (Live-Status verlagert, Demo global) · Global-Zone `useGlobalStatus` (Versions-Update/offener Monatsabschluss/MQTT) · Daten-Checker-Aggregat (`check().zusammenfassung`, schlimmste Severity, nur bei Befunden) · **Provenance-Slot** (`SichtStatus.quelle` → `Database`-Symbol; Live erster Konsument). Zonen global/sicht/meta; Severity **zentral** aus `config/datenCheckerKategorien.ts` (info=blau·warning=amber·error=rot·ok=grün, neutral=grau). Jedes Symbol: Icon+Tap-Popover+Deep-Link. **Provenance-SoT (eigene Zeile unten) jetzt angestoßen.** **Offen:** Provenance-Rollout auf weitere Sichten (opportunistisch); Deep-Links auf v4-Einstellungen umbiegen wenn gebaut. SPEC: `SPEC-STATUS-FUSSZEILE.md` SPEC: `SPEC-STATUS-FUSSZEILE.md` |

---

## Pflege

- Beim Bauen eines Musters ein neues Pattern entdeckt → Zeile ergänzen (⬜), im Skeleton klären, dann ✅ + Heimat eintragen.
- `❓`-Zeilen: vor dem nächsten Touch des Patterns einmal den echten Code-Stand verifizieren, nicht aus diesem Register schließen.
- Bei jedem ✅: Regel **auch** im Style-Guide festschreiben (Code-SoT + geschriebene SoT gehören zusammen).
