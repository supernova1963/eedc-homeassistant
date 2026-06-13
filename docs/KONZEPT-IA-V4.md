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
Cockpit  ·  Komponenten  ·  Auswertungen  ·  Community  |  Hilfe  Einstellungen
```

- **4 Inhalts-Einträge** plus Hilfe und Einstellungen — passt auf Desktop ohne Engpass.
- **Mobile:** Hamburger-Menü mit voller Liste (Standard-Pattern). Bottom-Tab-Bar wäre Big-Bang-Mobile-Redesign — bewusst nicht v4.0.0.
- **Standard-Landing:** `/` → `/cockpit/live`. Klick auf „Cockpit" im Top-Menü landet ebenfalls auf `/cockpit/live`. Live bleibt Erstkontakt — es ist eedcs Highlight.

---

## Cockpit (Zeit-Achse)

Sub-Tabs in chronologischer Reihenfolge:

| Tab | Inhalt | Heute entspricht |
|---|---|---|
| **Live** | Echtzeit-Verläufe, Live-Tiles pro Komponente | `LiveDashboard.tsx` |
| **Tag** | Tages-Bilanz im universellen Muster · **Tages-Selektor** (default heute, zurück bis Anschaffungsdatum, ‹ ›-Tagesnavigation analog Monat) | NEU — hebt die heutige Energieprofil-Tagessicht aus den Einstellungen hierher; Quelle `/energie-profil/{id}/tage`+`/stunden` |
| **Monat** *(vormals „Monatsbericht")* | Aktueller Monatsstand mit allen Sektionen | `MonatsabschlussView.tsx` |
| **Jahr/Gesamt** | Anlage-weite Bilanz im **gleichen** Seiten-Muster wie die Monat-Sicht (KPI-Strip Energie-Bilanz + Effizienz-Quoten · Verlauf · klapp-/sortierbare Komponenten-Sektionen mit Cross-Links). **Zeitraum-Selektor: einzelnes Jahr / Gesamtlaufzeit.** | `Auswertung.tsx` Tab „Energie" + die anlage-weiten KPIs der alten `Dashboard.tsx` |
| **Aussicht** | Kurzfrist / Prognosen / Langfrist / Trend | `Aussichten.tsx` (interne 5 Tabs konsolidiert) |

> **✅ Entschieden (2026-06-01): Die heutige Cockpit-Übersichts-*Seite* (`Dashboard.tsx`, Route `/cockpit`) wird aufgelöst, nicht in eine neue Sonderseite umbenannt.** Begründung: Das am Monatsbericht bewährte und [oben](#L47) als universell beschlossene Cockpit-Seiten-Muster (KPI-Strip → Hauptblock → klapp-/sortierbare Sektionen) macht eine separate „Übersicht" **redundant** — ihr Zweck („anlage-weiter Überblick") entsteht automatisch, sobald **jede** Zeit-Ansicht (Tag/Monat/Jahr) für ihren Zeitraum denselben anlage-weiten KPI-Strip + dieselben Komponenten-Sektionen zeigt. Eine eigene Aggregat-Seite mit Sonder-Layout würde genau die Inkonsistenz wieder einführen, die v4.0.0 beseitigt.
> **Inhalts-Verteilung der alten Übersicht:** anlage-weite KPIs (Energie-Bilanz, Effizienz-Quoten) werden Teil des universellen KPI-Strips **jeder** Zeit-Ansicht; pro-Komponenten-Teaser → Cross-Links nach Komponenten/`<typ>`; Amortisations-Bar → Auswertungen/ROI.
> **Gesamtlaufzeit-Horizont:** bleibt erhalten, aber **nicht** als eigene Seite — als **Zeitraum-Option im „Jahr/Gesamt"-Tab** (Jahr ↔ Gesamtlaufzeit umschaltbar), gerendert im selben universellen Muster. So überlebt die kumulierte Bilanz, ohne ein Sonder-Layout zu sein. *(Offen: ob „Gesamt" überhaupt nötig ist oder Jahr genügt — siehe unten.)*
> **Landing unverändert:** `/` und Klick auf „Cockpit" → `/cockpit/live` (ist schon heute so, `Dashboard.tsx` war nie Landing).

> **✅ Entschieden (2026-06-01): Tag-Sicht (vormals „Heute") — vollwertiges Geschwister von Monat/Jahr.** Statt „nur heute, kondensiert" eine echte Tages-Ansicht im universellen Muster mit **Tages-Selektor** (default heute, Untergrenze = Anschaffungsdatum, Tagesstreifen + Kalender + ‹ ›-Tagesnavigation analog Monat). **Strikt IST** (gemessene Tagesbilanz, keine Prognose-Elemente — der Soll-Ist-Abgleich des Tages lebt per Cross-Link in Aussicht). Datenquelle ist der Energieprofil-Pfad (`/energie-profil/{id}/tage`+`/stunden`) — bewusst **eine andere Quelle als die Monat-Sicht** (`/aktueller-monat`), gleiches Seiten-Muster darüber. Damit bekommt die heute in den Einstellungen vergrabene Tagessicht ihre kanonische Heimat in der Zeit-Achse. *(Stunde ist die innere Auflösung von Tag — kein eigener Stunden-Tab; Live bleibt der Echtzeit-Modus.)*

**Cockpit-Innenseiten-Pattern (Top-Down):**

1. KPI-Strip oben — die 3–4 wichtigsten Zahlen der Zeitebene
2. Visueller Hauptblock — **zwei umschaltbare Linsen im selben Slot:** *Verlauf* („wann?", Zeitraum → Unter-Einheit) ⇄ *Fluss* („wohin?", EnergyFlowDiagram). Default je Zeitraum getunt: Live → Fluss (Echtzeit), Tag/Monat/Jahr → Verlauf.
3. **Werte/Tabelle-Sektion** — der numerische Zwilling des Verlaufs (siehe unten)
4. Detail-Sektionen darunter, jeweils mit Cross-Link zur entsprechenden Komponenten-Seite

**Sektionen klapp- und sortierbar (an den Zeitraum gebunden):** Die Detail-Sektionen nutzen das im Monatsbericht etablierte Muster — auf-/zuklappbar **und** per ↑↓ in eine persönliche Reihenfolge bringbar, Zustand pro Sicht persistiert. Dieses Muster ist bei den Testern gut angekommen (Monatsbericht-Rückmeldung) und wird hier bewusst auf alle Cockpit-Zeitsichten ausgeweitet. **Abgrenzung:** Das ist *kein* Widget-Builder/„My-Sites" (frei wählbare Bausteine bleiben aus dem Scope, siehe Style-Guide Einstellbarkeits-Cap) — sortiert wird nur der *feste* Sektionssatz. Umgesetzt über **einen** Persistenz-SoT (Style-Guide B6), nicht die heutige Doppel-Logik.

> **✅ Entschieden (2026-06-01): Hauptblock = zwei Linsen.** Löst den Konflikt „Energiefluss vs. Verlauf" auf — beide leben als Umschalter im selben Slot statt sich auszuschließen. Revidiert die frühere „EnergyFlow-only"-Festlegung (Inventur unten).

**KPI-Strip-Belegung je Zeit-Sicht (✅ entschieden 2026-06-02):** Tag/Monat/Jahr tragen **denselben** anlage-weiten Strip — nur Zeitraum + Vergleichsbasis ändern sich (genau das macht die aufgelöste Übersicht überflüssig). Live ist der Sonderfall (Leistung statt Energie, siehe Live-Spezifik).

| Sicht | KPI-Strip (anlage-weit) | Vergleichsbasis | Auflösung |
|---|---|---|---|
| **Live** | PV-Leistung · Hausverbrauch · Netz ± · SoC — zugleich die kWh des laufenden Tages (heutige „Heute"-Kacheln) | Gestern | kW live + kWh heute |
| **Tag** | PV · Autarkie · Eigenverbrauch · Einspeisung · Netzbezug | Vergleichstag | kWh/Tag |
| **Monat** | dieselben 5 **+ Netto-Ertrag (€)** | Vormonat / Vorjahr / Ø-Monat | kWh/Monat |
| **Jahr/Gesamt** | dieselben 5 + Netto-Ertrag **+ spez. Ertrag (kWh/kWp)** | Vorjahr (Gesamt: —) | kWh / MWh |

Bewusste Schärfung gegenüber „3–4 Zahlen": die testerseitig bewährten **5 Energie-Cards** des Monatsberichts sind der Kanon; der **Finanz-KPI** (Netto-Ertrag, F2-a) kommt als kompakter Teaser **ab Monat** dazu (Tag bleibt strikt IST-Energie — Tages-Finanz wäre verrauscht), **spez. Ertrag** erst auf Jahres-Ebene (Jahres-Effizienzmaß). Mobile: Finanz-Card zuerst einklappbar.

**Live-Spezifik (✅ 2026-06-02):** Live behält bewusst sein heutiges, reiches Layout (Echtzeit-Erstkontakt, eedcs Highlight) und wird nur **lose** ins Skelett eingepasst — kein Neubau: **Hauptblock** = Energiefluss (Fluss-Linse, Default) ⇄ **Tagesverlauf in kW** als Verlauf-Linse-Toggle (nicht als separater Expander); die **„Heute"-Kacheln** (PV/EV/Netzbezug/Einspeisung in kWh + Autarkie/EV-Quote) sind der Live-KPI-Strip und tragen die kWh des laufenden Tages; **Ladezustand (SoC), Temperaturen, Wetter heute/Sonnentags-Fortschritt, 3-Tage-Solar-Vorschau** werden die klapp-/sortierbaren Sektionen (gleiches Sortier-Muster wie die übrigen Zeit-Sichten).

**Werte/Tabelle-Sektion (numerischer Zwilling):** Jede Zeit-Sicht trägt zusätzlich eine **verschiebbare, klappbare „Werte/Tabelle"-Sektion** — der numerische Zwilling des Verlaufs (gleiche Unter-Einheiten als Zeilen: Tag→Stunden, Monat→Tage, Jahr→Monate), mit der Vergleichslogik `[Zeitraum | Vergleichszeitraum | Δ]`. Es ist **dieselbe** Tabellen-Komponente wie in Auswertungen/Tabelle, nur kontext-skaliert (**eine SoT**, kein zweiter Tabellen-Code — wie KPICard B9). **Auswertungen/Tabelle bleibt die volle Werkbank** (alle Komponenten, voller Spalten-Picker, kanonischer CSV); die eingebetteten Sektionen sind scoped Lese-Ausschnitte + Cross-Link „alle Werte / Export →". **Grenze:** ein Vergleichszeitraum wählbar + Spalten-Picker — **keine** freie Mehrfachauswahl beliebiger Jahre/Monate (in #195 verworfen), kein eigener „Vergleich"-Tab. *(Bedient den durchgängigen Wunsch nach Auswertungs-Tabellen im Kontext, aus dem Forum / #195.)*

**Werte/Tabelle-SoT — Parametrisierung (✅ entschieden 2026-06-02):** Heute existieren **drei parallele** Tabellen mit je eigener Spalten-Definition (`TabelleTab` 27 Spalten/Monate · `EnergieprofilTageTabelle` 15+dyn./Tage · Stunden-Tagesdetail 13/Stunden) — überlappende Metriken, drei localStorage-Keys, kein geteilter Code. Die SoT konsolidiert das in **eine Metrik-Registry** + **eine `<WerteTabelle>`**:

- **Eine Metrik-Registry** je Metrik (`key·label·unit·format·agg·higherIsBetter·gruppe·scope`) mit **pro-Granularität-Accessor** (`get.monat/tag/stunde`) — die Komponente ist granularitäts-agnostisch, ein dünner **Granularitäts-Adapter** normalisiert die (gewollt verschiedenen) Backend-Quellen pro Sicht. **Logik-Wiederverwendung aus `TabelleTab`, kein Neubau** der Vergleichs-/CSV-/Footer-Rechnung.
- **`<WerteTabelle>`-Parameter:** `granularitaet` (stunde/tag/monat/saison/jahr) · `scope` (alle / Komponententyp, filtert die Registry über das `gruppe`-Tag) · `vergleich` (genau **ein** Zeitraum, Einheit = Zeilen-Granularität) · `modus`.
- **Zwei Modi:** **`werkbank`** (Auswertungen/Tabelle) = voller Picker + Reorder + kanonischer CSV + Vergleich; **`embed`** (Cockpit-Sichten, Komponenten-Hub) = **fix + read-only** — fester scoped Default-Spaltensatz, **kein** Picker, **kein** eigener CSV, genau ein Cross-Link „alle Werte / Export →" (vorgewählt auf denselben Scope + Zeitraum). Mobile-Embed: noch weniger Spalten, default eingeklappt.

| Kontext | Granularität | Scope | Vergleich | Modus |
|---|---|---|---|---|
| Cockpit/Tag | Stunden | alle | Vergleichstag | embed |
| Cockpit/Monat | Tage | alle | Vergleichsmonat | embed |
| Cockpit/Jahr-Gesamt | Monate / Saison | alle | Vorjahr (Gesamt: —) | embed |
| Komponenten/`<typ>` | Monate | `<typ>` | Vergleichsjahr | embed (Tabellen-Hälfte des Diagramm⇄Tabelle-Toggle) |
| Auswertungen/Tabelle | Monate → Tag/Saison/Jahr (gestaffelt) | alle (voller Picker) | ein Zeitraum | werkbank |

**Staffelung (v4.0.0):** Registry + `<WerteTabelle>` ersetzen `TabelleTab` und werden als **Monats-granulare** Embeds in Cockpit/Monat·Jahr + Komponenten/`<typ>` eingebettet (gleiche Quelle `AggregierteMonatsdaten` → **kein neuer Datenpfad**). `get.tag`/`get.stunde` + die Migration der Energieprofil-Tabellen ziehen **mit Cockpit/Tag** nach (das ohnehin in Phase 1 den `/tage`+`/stunden`-Pfad baut). Saison-Granularität + HDD bleiben **data-gated, post-v4.0.0**, sind aber vorbereitet (`granularitaet='saison'`). Die **pro-Tag-Reaggregation** ist Pflege → wandert nach Einstellungen/Daten/Energieprofil-Pflege; die Anzeige-Embeds bleiben read-only, behalten aber eine dezente Cross-Link-Row-Action „→ reaggregieren", damit der Reparatur-Pfad nicht verloren geht.

**Aussicht-Konsolidierung (✅ Mapping entschieden 2026-06-02):** Die heutigen 5 Aussichten-Sub-Tabs werden im Cockpit/Aussicht-Tab zu **einer linearen Seite** mit **Horizont-Selektor (7 Tage · 14 Tage · 12 Monate · Mehrjahr)** — der Selektor blendet die passenden Sektionen ein.

| Heute | → Aussicht-Sektion (Horizont) | Anmerkung |
|---|---|---|
| **Kurzfristig** | Wetter + PV-Ertragsprognose (7/14 Tage) | direkt |
| **Prognosen** | Forward-Quellen-Vergleich heute/morgen (kurz) | bleibt in Aussicht |
| **Langfristig** | Monatsprognose PVGIS + Saison (12 Monate) | direkt |
| **Trend** | Degradations-*Prognose* (Mehrjahr) | nur der Vorwärts-Teil |
| **Finanzen** | → **Auswertungen/Finanzen** | raus (F2-a-Linie) |

**Trennlinie (pragmatisch entschieden):** Aussicht = vorwärtsgewandt, aber der **Forward-Quellenvergleich** aus „Prognosen" (inkl. kurzem Genauigkeits-Kontext) bleibt hier — weniger Klick-Sprünge für den Nutzer. Das **vollständige** Genauigkeits-Tracking (MAE/MBE, Wetter-Stratifizierung) bleibt zusätzlich in **Auswertungen/Prognose-vs-IST** (seine kanonische Heimat). Der **historische Rückblick** aus „Trend" (Jahres-/PR-/Degradations-*Analyse* der Vergangenheit) wandert nach **Cockpit/Jahr** bzw. **Auswertungen/Tabelle**; nur die Degradations-*Prognose* bleibt in Aussicht. „Finanzen-Prognose" → **Auswertungen/Finanzen** (analytischer Schnitt).

### Auflösung der Übersichts-Seite — Inventur-Mapping (2026-06-01)

Vollständige Inventur von `Dashboard.tsx` (alte Cockpit-Übersicht, 630 Z.), damit beim Auflösen nichts verloren geht. Jedes Element hat eine Achsen-gerechte Heimat — **Komponenten ist Auffangbecken nur für die pro-Komponenten-Inhalte, nicht für anlage-weite oder analytische** (sonst würde die gerade getrennte Achsen-Vermischung nur verschoben).

| Element der alten Übersicht | Art | Heimat |
|---|---|---|
| Energie-Bilanz (PV, Verbrauch, Netzbezug, Einspeisung) | anlage-weit | Cockpit — universeller KPI-Strip jeder Zeit-Ansicht |
| Effizienz-Quoten (Autarkie, EV, Direktverbrauch, spez. Ertrag) | anlage-weit | Cockpit — KPI-Strip |
| HeroLeiste (Top-3 + Vorjahresvergleich) | anlage-weit | Cockpit — Kopf des KPI-Strips |
| **EnergyFlowDiagram** (anlage-weiter Energiefluss) | anlage-weit | Cockpit — die **Fluss-Linse** des Hauptblocks (neben der Verlauf-Linse, siehe „Hauptblock = zwei Linsen" oben), pro Zeitraum aggregiert; Default-Linse in Live |
| Speicher / Wärme/Klima / Sonstiges / E-Mobilität (je 4 KPIs) | pro-Komponente | **Komponenten/`<typ>`** (Detail) + Teaser-Cross-Link im Zeit-View |
| Finanzen (Erlös, §51-Verlust, EV-Ersparnis, Netzkosten, USt, Netto-Ertrag) | analytisch | Auswertungen/Finanzen |
| Jahres-Rendite + AmortisationsBar | analytisch | Auswertungen/ROI |
| CO₂-Bilanz (PV, WP, E-Mob, gesamt) | analytisch | Auswertungen/CO₂ |
| Jahres-/Zeitraum-Selektor + Zeitraum-Info | Steuerung | Zeitraum-Selektor der Zeit-Ansicht (Jahr ↔ Gesamt) |
| **`GettingStarted`** (Empty-State, keine Anlage) | Onboarding | Cockpit-Leerzustand (Style-Guide B8) |
| **Multi-Anlagen-Selektor** (bei >1 Anlage) | Steuerung | global/Layout — Audit unter B12 (Single-Anlage-Selektor) |
| **Social-Media-Text-Export** (Share-Button + `ShareTextModal`) | Aktion | **zeitraum-gebundene Cockpit-Aktion** (siehe unten) |
| QuickLinks (Monatsdaten/Auswertungen/Investitionen) | Navigation | entfällt — durch neue Top-Nav + Einstellungs-Kachelgrid redundant |

**Social-Media-Text-Export — zeitraum-gebunden (2026-06-01):** Der Teilen-Button wird eine **Cockpit-Aktion pro Zeit-Ansicht** (nicht Community): er teilt den jeweils gewählten Zeitraum — Tag (gewählter Tag) / Monat (gewählter Monat) / Jahr (gewähltes Jahr bzw. Gesamtlaufzeit). **Scope-Trennung (wichtig, [v4.0.0 = reine Struktur](#L233)):**
> - **In v4.0.0 (reine IA):** nur die **Platzierung** als zeitraum-gebundene Aktion, mit der **heute vorhandenen** Fähigkeit (Monat — `social.py` ist bereits monatsbasiert). Kein neuer Generierungs-Code.
> - **Eigenes Feature-Bündel (post-v4.0.0):** die **zeitraum-adaptive Text-Generierung**. Aufwand gestaffelt — Monat: vorhanden; **Jahr/Gesamt:** moderater Backend-Zusatz (Aggregations-Zweig + Vorlage); **Tag:** größer (eigener Tages-Datenpfad statt `Monatsdaten`, nur wo Tagesdaten existieren). Funktionale Erweiterung, gehört nicht in den Struktur-Schnitt.

---

## Komponenten (Was-Achse)

Sub-Tabs pro Komponententyp:

```
PV-Anlage  ·  Speicher  ·  Wärme/Klima  ·  E-Auto  ·  Wallbox  ·  BKW  ·  Sonstiges
```

Tabs erscheinen nur, wenn die Anlage die jeweilige Komponente hat (strukturell N/A → Tab ausgeblendet, vgl. Style-Guide A3 Datenzustand-Vokabular). Damit bleibt die Komponenten-Achse durch den Vorhandensein-Filter de facto bei ≤ 5 sichtbaren Tabs, obwohl bis zu 7 Typen möglich sind — das ≤5-Limit gilt strikt für die Zeit-/Wie-Achse (Cockpit/Auswertungen), wo die Tab-Inflation auftrat. **✅ Entschieden (2026-05-31):** Tab-Benennung **„Wärme/Klima"** (deckt Wärmepumpe + Split-Klimaanlagen #263 zukunftssicher ab).

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

▼ Vergleich   [Diagramm ⇄ Tabelle]
  [Diagramm: Vorjahr/Vormonat · Saison-Toggle (Winter/Heizperiode/Sommer), wetternormalisiert]
  [Tabelle: komponenten-scoped Werte – Jahr | Vergleichsjahr | Δ]

▼ Aussicht
  [Komponentenspezifische Prognose: wann voll/leer, Empfehlung]
```

**Designentscheidungen:**

- **Datums-Selektor statt Sub-Sub-Tabs:** Eine Achsen-Kontrolle oben, alle Sektionen folgen dem Datum. Mobile-tauglich (kein Sub-Sub-Tab-Layout, keine doppelte Zeit-Achse zur Cockpit-Zeit-Achse).
- **Lineare Sektion-Reihenfolge (hier bewusst fix):** Status → Verlauf → Vergleich → Aussicht. Vier Sektionen sind genug und stabil über alle Komponententypen — keine komponentenspezifische Sondersortierung. **Bewusster Unterschied zu den Cockpit-Zeitsichten:** Dort sind die Sektionen sortierbar (gut angekommenes Monatsbericht-Muster), im Komponenten-Hub *nicht* — die typ-übergreifende Stabilität ist hier der höhere Wert (man findet dieselbe Sektion bei jedem Komponententyp am selben Platz). Klappbar bleiben die Sektionen auch hier.
- **Vergleich-Sektion (Saison + Werte):** Die „Vergleich"-Sektion trägt einen **Diagramm ⇄ Tabelle-Umschalter** — *Diagramm* mit Saison-Toggle (Winter/Heizperiode/Sommer) und Wetternormalisierung (Heizgradtage, fairer Mehrjahresvergleich; #195 Punkt 3, primär Wärme/Klima), *Tabelle* = die komponenten-scoped Werte (numerischer Zwilling, eine Tabellen-SoT, siehe Cockpit). Saisonale Mehrjahres-Muster (#110) sind die datengebundene Ausbaustufe.
- **Energieprofil verschwindet als eigenständige Seite — dreifacher Zielort:** der *anlage-weite* Tagesüberblick → **Cockpit/Tag**; der *komponentenspezifische* Stundenverlauf → „Verlauf im Zeitraum"-Sektion (Strom-Profil PV, Wärme-Profil WP); die *Rohtabelle* → Auswertungen/Tabelle; die **Pflege** (Vollbackfill, Löschen, Reaggregation) → Einstellungen/Daten/Energieprofil-Pflege. **Anzeige ≠ Pflege.**
- **Komponentenspezifische KPIs** via `lib/komponentenStyle.ts` als SoT (Style-Guide A5 + B9). Erweiterung der **Konsumtion** auf E-Auto/BKW/Wallbox/Sonstiges/PV-Anlage ist Pflicht-Voraussetzung — heute konsumieren nur WP+Speicher (Disc #163). **✅ Update 2026-06-12 (P1):** Die KPI-Stil-Records sind jetzt **real konsumiert** (WP- + Speicher-Dashboard ziehen den SoT; `fmtKpi` nach `lib/formatting.ts` umgezogen). D2-Kanon **komplett angelegt** (alle 7 Typen + 3 Sonstiges-Varianten); offen nur die Übernahme in die übrigen 5 Dashboards (B9/E1-P2). Siehe Style-Guide A5.

**Status-KPIs pro Komponententyp (✅ entschieden 2026-06-02 — Kanon für A5):** Ratifiziert die heute prominenten KPIs je Typ als Soll-Satz für die „Aktueller Status"-Sektion; `komponentenStyle.ts` bekommt die passenden Stil-Records.

| Typ | KPI 1 | KPI 2 | KPI 3 | KPI 4 |
|---|---|---|---|---|
| **PV-Anlage** | Anlagenleistung (kWp) | Gesamterzeugung (MWh) | Spez. Ertrag (kWh/kWp) | Eigenverbrauch (%) |
| **Speicher** | Vollzyklen | Wirkungsgrad η (%) | Durchsatz (MWh) | Ersparnis (€) |
| **Wärme/Klima** | JAZ | Wärme erzeugt (MWh) | Strom verbraucht (MWh) | Ersparnis vs. Gas (€) |
| **E-Auto** | Gefahren (km) | Verbrauch (kWh/100km) | PV-Anteil (%) | Ersparnis vs. Benzin (€) |
| **Wallbox** | Heimladung (MWh) | PV-Anteil (%) | Ladevorgänge | Ersparnis vs. Extern (€) |
| **BKW** | Erzeugung (kWh) | Eigenverbrauch (%) | Ersparnis (€) | **Spez. Ertrag (kWh/kWp)** |
| **Sonstiges** | *3 Varianten:* Erzeuger (Erzeugung · EV-Quote · Ersparnis · CO₂→Cross-Link) / Verbraucher (Verbrauch · PV-Anteil · Netzkosten · PV-Ersparnis) / Speicher (Ladung · Entladung · Effizienz · Ersparnis) | | | |

- **BKW achsenrein (2026-06-02):** das heutige CO₂-KPI wird durch **spez. Ertrag** ersetzt — CO₂ ist Wie-Achse und lebt in Auswertungen/CO₂ (Cross-Link bleibt). Pro-Komponente-**Geld**werte (Ersparnis) bleiben als Teaser zulässig (F2-a-Konsequenz 3), nur anlage-weite Finanzen/CO₂ wandern.
- **Status ≠ Live:** Die Status-KPIs sind **zeitraum-skaliert** (folgen dem Datums-Selektor der Komponenten-Seite). Echte Live-Werte (SoC etc.) erscheinen nur dort, wo Live-Daten existieren.
- **A5-Umfang:** **✅ Records komplett angelegt (P1)** — alle 7 Typen + 3 Sonstiges-Varianten in `komponentenStyle.ts`; real konsumiert bisher WP + Speicher, die übrigen 5 Dashboards ziehen mit B9/E1-P2 nach.

---

## Auswertungen (Wie-Achse)

Sub-Tabs als analytische Schnitte über die ganze Anlage:

| Tab | Inhalt | Heute entspricht |
|---|---|---|
| **Finanzen** | Ersparnis, Erlös, Strompreis-Historie, Finanzen-Prognose **+ das anlage-weite SOLL/HABEN-T-Konto (aus dem Monatsbericht hierher verlagert), zeitraum-parametrisiert (Tag/Monat/Jahr-Selektor)** | `Auswertung.tsx`/finanzen + `Aussichten.tsx`/finanzen + `MonatsabschlussView` T-Konto |
| **CO₂** | Bilanz, Vermeidung, **CO₂-Amortisation** (#284) | `Auswertung.tsx`/co2 |
| **ROI** | Investitions-ROI, Kumuliert, Aussichten | `ROIDashboard.tsx` |
| **Tabelle** (volle Werkbank) | Rohdaten über alle Komponenten, voller Spalten-Picker, Jahr-vs-Jahr `[Wert \| Vergleichsjahr \| Δ]` (#195), kanonischer CSV-Export. *Scoped* Ausschnitte derselben Tabelle leben eingebettet in Cockpit/Komponenten (Werte/Tabelle-Sektion) | `Auswertung.tsx`/tabelle |
| **Prognose-vs-IST** | Genauigkeits-Tracking, Bias, Quellen-Vergleich | `PrognoseVsIst.tsx` |

> **✅ Entschieden (2026-06-01): Finanzen-Verortung (F2-a).** Das anlage-weite Finanz-T-Konto — heute der dominante Block des Monatsberichts — zieht **hierher** (Finanzen = analytischer Schnitt = Wie-Achse). Die Cockpit-Zeit-Sichten behalten nur einen **kompakten Finanz-KPI** (Netto-Ertrag, Ersparnis) im KPI-Strip + Cross-Link „volle Finanzrechnung →". *Auflage:* die konsolidierte Finanzrechnung muss die **sonstigen Positionen aus der Monatsauswertung** mit einsammeln (#310). Pro-Komponente-Geldwerte (z. B. WP-Ersparnis vs. Gas) bleiben Teaser in den Komponenten-Sektionen; nur das **anlage-weite** T-Konto wandert. **Folge-Entscheidung (2026-06-01):** der Cockpit-Tab heißt künftig „**Monat**" (nicht „Monatsbericht") — der namensgebende finanzielle *Abschluss* sitzt jetzt in Auswertungen/Finanzen.

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
| KPI-Kachel im Cockpit/Tag | entsprechende Auswertung (Finanzen-KPI → Auswertungen/Finanzen) |
| Zeile in Auswertungen/Tabelle für Monat M | `/cockpit/monat` mit Datum M |
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
| **A0** | Design-Tokens (Typo · Farben · Spacing · Schatten · Radius). **✅ Farben P1 geshippt** — SoT = `lib/colors.ts` (kein `design-tokens.ts`); Typo/Animation/Spacing-Tabellen via Fundament-P6. Sichtbare Farb-Vereinheitlichungen bewusst zugelassen (F8). |
| **B1** | PillTabs → SubTabs-Migration (**3 Verbraucher, Stand 2026-06-11:** Auswertung, Aussichten, Community — DesignPreview nutzt PillTabs nur noch als Deprecated-Kommentar). **Kein 1:1-Swap** — SubTabs route-getrieben, PillTabs state-getrieben (+ beta/tooltip). **✅ Entschieden:** auf **echte URL-Routen** heben (zukunftssicher, passt zur Redirect-Tabelle); beta/tooltip auf der Route-Variante nachbauen. Vereinheitlicht die Sub-Nav für Cockpit-Sub-Tabs + Komponenten-Hub. |
| **B9-Vorbereitung** | KPICard-SoT-Komponente mit `size: 'sm' \| 'md' \| 'lg'` + Color-Enum. **Nicht drei, sondern fünf** echte KPICard-Versionen + drei `KpiCard`-Label-Helfer (= 8 Definitionen, 29 referenzierende Dateien, Stand 2026-06-11) migrieren; die Community-Vergleichs-Variante bleibt ggf. eigener Sonderfall. Pflicht-Item, weil v4.0.0 saubere KPI-Strips überall braucht. |
| **A5-Vorbereitung** | `lib/komponentenStyle.ts`-Records **P1 für alle Typen angelegt**; reale Nutzung WP/Speicher, übrige Dashboards ziehen mit B9 nach (Disc #163). Vorbedingung für konsistente Komponenten-Seiten. |

### Phase 1 — v4.0.0 IA-Refactor (ein Release)

1. Top-Nav umstellen: Live raus (wird Cockpit/Live), Aussichten raus (wird Cockpit/Aussicht), Komponenten als neuer Top-Eintrag.
2. Cockpit-Sub-Tabs Live/Tag/Monat/Jahr/Aussicht implementieren (inkl. Verlauf⇄Fluss-Hauptblock + Werte/Tabelle-Sektion).
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

### Vorab-Sichtung — klickbare Vorschau (statt Design-Tool)

Auf die wiederkehrende Tester-Frage „kann man vorher sehen, was sich ändert?" ist die Antwort eine **klickbare Vorschau aus echten Komponenten**, nicht ein Design-Tool (Figma/Penpot wäre Wegwerf-Arbeit parallel zum Bau). Da Phase 0 die Bausteine ohnehin liefert (A0-Tokens, B9-KPICard-SoT, neue Top-Nav/SubTabs-Schale), ist die Vorschau das Fundament, kein Zusatzaufwand. Sie adressiert direkt das #1-Risiko Findability — Tester versuchen eine echte Aufgabe („finde deine Aussicht") auf der neuen Struktur, **bevor** der Schnitt live geht.

- **MVP:** Navigations-Skelett (neue Top-Nav + Sub-Tabs + Platzhalter-Komponenten-Hub) — beantwortet die Findability-Frage schon ohne realistische Daten. Wächst aus der bestehenden `/dev/design-preview`-Route.
- **Ausbau:** statisch gehosteter Build mit Mock-Daten (kein Backend/HA nötig), öffentlicher Link in #243 für alle Interessierten — **Richtungs-Feedback zur Navigation, nicht Korrektheits-Test**.
- **Companion-App-Spezifika** (Swipe/Sticky/`h-dvh`), die eine statische Vorschau nicht zeigt: später über einen Beta-Add-on-Kanal, sobald IA-V4 läuft.
- **Leitplanken:** temporäre Wegwerf-Vorschau, **kein** dauerhafter In-App-Schalter (Einstellbarkeits-Cap); öffentlicher Link statt bilateralem Screenshot-Pakt; kein Termin-Versprechen unter Foren-Druck. Baubar erst nach Phase C (Komponenten müssen als echter Code existieren).

---

## URL-Redirect-Tabelle

Alle Bestandspfade müssen redirected werden — Foren-Posts, Memory-Pfade, Issue-Links sollen nicht brechen.

| Alt | Neu |
|---|---|
| `/live` | `/cockpit/live` |
| `/cockpit` | `/cockpit/live` (Default-Landing) |
| `/cockpit/aktueller-monat` | `/cockpit/monat` |
| `/cockpit/monatsberichte` | `/cockpit/monat` |
| `/cockpit/monatsbericht` | `/cockpit/monat` |
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
| `/einstellungen/energieprofil` | `/cockpit/tag` (Anzeige aufgeteilt — Rohtabelle → `/auswertungen/tabelle`, Pflege → `/einstellungen/energieprofil-pflege`) |

Konventions-Regel: jede Bestandsroute kriegt einen `Navigate replace` in `App.tsx`. Keine 404s.

> **Bestand (verifiziert 2026-06-11):** `App.tsx:73-167` enthält bereits **24** `Navigate`-Redirects aus früheren Umbauten — deren **Ziele** müssen beim Schnitt mit umgebogen werden (z. B. `/cockpit/aktueller-monat` zeigt heute auf `/cockpit/monatsberichte`, künftig direkt auf `/cockpit/monat`); **keine Redirect-Ketten**. Der Eintrag `/cockpit/monatsbericht` (Singular) war nie eine echte Route — rein defensiv.

---

## Was bewusst NICHT im v4.0.0-Scope ist

- **Funktionale Erweiterungen** — v4.0.0 ist reine Struktur + Designsprache. Inhalts-Features (z. B. CO₂-Amortisation #284, **HDD-Wetternormalisierung #195 P3, saisonale Mehrjahres-Muster #110**) sind eigene, teils datengebundene Bündel — die Struktur gibt ihnen nur die Heimat.
- **Theme-Editor / freie Card-/Widget-Anordnung (Dashboard-Builder, „My-Sites") / Dichte-Profile** — siehe Style-Guide „Einstellbarkeits-Cap" (Hell/Dunkel-Mode + Mobile-Reduce-Default sind die einzigen Achsen). **Klarstellung (2026-06-01):** Das *Umsortieren des festen Sektionssatzes* in den Cockpit-Zeitsichten ist davon ausgenommen und ausdrücklich erlaubt — es ist kein Builder.
- **Eigene „Vergleich"-Rubrik / Free-Select** — Vergleich ist ein **Modus innerhalb** der Achsen (Verlauf-Linse, Saison-Toggle, Werte/Tabelle-Sektion), **kein** eigener Top-Tab; die freie Mehrfachauswahl beliebiger Jahre/Monate bleibt draußen (in #195 verworfen). „Vergleichszeitraum wählen" ist erlaubt, „beliebig viele frei anhaken" nicht.
- **Backend-Refactor** — Achsen-Trennung passiert rein im Frontend. Routen + Read-Sites verlinken, sonst keine Berechnungs-Änderungen.
- **Performance-Optimierung** (Code-Splitting, Lazy Loading) — separater Refactor-Sprint.
- **Bottom-Tab-Bar auf Mobile** — Hamburger reicht.

---

## Risiken + Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| Bestandstester sucht Aussichten als Top-Eintrag | Release-Notes prominent, Hilfe-Eintrag „Wo ist Aussichten hin?", evtl. einmaliger Toast „Aussichten findest du jetzt im Cockpit unter Aussicht". **Vorgelagert: klickbare Vorab-Vorschau** (siehe Migrations-Plan) fängt Findability-Probleme ab, solange Umräumen billig ist |
| Foren-Links brechen | Vollständige Redirect-Tabelle in `App.tsx`, automatischer Test der alten Pfade |
| Komponenten-Hub-Seite zu lang auf Mobile | CollapsibleSections mit `defaultOpenMobile={false}` für Verlauf/Vergleich, Sektion „Aktueller Status" bleibt initial offen |
| HA-Companion-App-Quirks (Sticky-Header, Downloads, `h-dvh`) | Querschnittsregeln aus Mobile-Konzept M4+M5 in Pflicht-Checkliste pro neuer Seite |
| Tab-Inflation kehrt zurück (Auswertungen hatte 8 Tabs) | Pro Top-Eintrag ≤ 5 Sub-Tabs als Designregel. Tab-Zuwachs braucht explizite Genehmigung in #243 |
| Community-Top-Eintrag hat heute 6 Sub-Tabs (> 5) | **✅ Entschieden (2026-06-02): „Übersicht" + „Statistiken" zusammenlegen** (beide = globale Community-Kennzahlen + eigene Position) → 5 Tabs: **Übersicht · PV-Ertrag · Komponenten · Regional · Trends**. (2026-05-31: konsolidieren auf ≤ 5, keine Ausnahme.) |
| Tester sucht das Finanz-T-Konto im Monatsbericht (F2-a verlagert es) | Prominenter Cross-Link aus jeder Zeit-Sicht + „Wo ist X hin?"-Eintrag; Finanz-KPI (Netto-Ertrag, Ersparnis) bleibt im KPI-Strip sichtbar |

---

## Querverweise

- **Visuelle Sprache (Tokens, Komponenten, Layout)** → [`KONZEPT-STYLE-GUIDE.md`](KONZEPT-STYLE-GUIDE.md)
- **Mobile-Verhalten** → [`KONZEPT-MOBILE.md`](KONZEPT-MOBILE.md)
- **Operativer Bausteine-Tracker** → [#243](https://github.com/supernova1963/eedc-homeassistant/issues/243)
- **Speicher-Auswertungs-Inhalte (B11 alt → Komponenten-Hub-Inhalt)** → [#142](https://github.com/supernova1963/eedc-homeassistant/issues/142) · [`KONZEPT-SPEICHER-AUSWERTUNG.md`](KONZEPT-SPEICHER-AUSWERTUNG.md)
- **CO₂-Amortisation** → [#284](https://github.com/supernova1963/eedc-homeassistant/issues/284)
- **Saison-/Mehrjahresvergleich (Werte-Tabelle, Wetternormalisierung)** → [#195](https://github.com/supernova1963/eedc-homeassistant/issues/195)
