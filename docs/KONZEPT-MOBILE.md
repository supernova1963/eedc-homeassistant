# eedc Mobile-Konzept (Konzept-Skelett)

> **Status:** Wachsendes Konzept-Dokument, **eigene Timeline** parallel zu [`KONZEPT-STYLE-GUIDE.md`](KONZEPT-STYLE-GUIDE.md). Skelett liegt vor; Umsetzungs-Wellen folgen, wenn Stakeholder-Bedarf konkret wird.
>
> **Eingangsperspektive:** eedc ist primär datendichte Desktop-App. Mobile-Erfahrung wird hier **konzeptionell eigenständig** gedacht — nicht als Responsive-Beilage in jedem Style-Guide-Bereich. Companion-App-Touchpoints (HA-Mobile-App) sind die wichtigste Anwender-Realität.
>
> **Aktuelle Stakeholder-Lage:** dünn. Rainer (rapahl) hat sich von Mobile-Nutzung zurückgezogen (siehe #243 B5-Absenkung). detLAN (#203) bleibt aktiver Mobile-Beobachter. Weitere Mobile-Bedarfsmeldungen werden als Beschleuniger gewertet.
>
> **Bezug zur IA v4.0.0:** Der v4.0.0-Schnitt (siehe [`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md)) bringt die Mobile-Top-Nav-Entscheidung **Hamburger-Menü** mit (Standard-Pattern, voller Top-Nav-Inhalt). Bottom-Tab-Bar wäre Big-Bang-Mobile-Redesign — bewusst nicht v4.0.0. Komponenten-Hub-Seiten nutzen Datums-Selektor + lineare Sektion-Reihenfolge (Variante C in IA-V4) — keine vertikalen Mega-Spalten wie Monatsberichte, weil Komponenten-Kontext zeit-übergreifend ist.

---

## Methodik

- **Wachsend** wie das Style-Guide-Dokument: pro Welle 1–2 Bereiche.
- **Stakeholder-Trigger:** Umsetzungs-Welle für einen Bereich startet, wenn ≥ 2 Anwender konkrete Bedarfsmeldungen mit reproduzierbarem Setup liefern. Memory `feedback_smoketest_braucht_release.md` mahnt: Mobile-Test ohne lokales Setup ist Tester-Roulette, deshalb keine Big-Bang-Wellen.
- **Pro Bereich:** Designentscheidung, Pattern-Beispiel (Code/Mockup), Verlinkung auf entsprechende Style-Guide-Sektion.
- **Pflicht-Querschnittsregeln** (Touch-Targets ≥ 44 px, `h-dvh`, `lib/download.ts:downloadFile()`, `overscroll-contain`, Multi-Breakpoint-Flex-Klassen) sind **aus diesem Dokument in den Style-Guide hochgezogen** (siehe Methodik dort) und gelten in **jeder** Welle, nicht nur in Mobile-Wellen. M4 + M5 hier bleiben als Referenz-Dokumentation für die Quirk-Hintergründe, **werden nicht als eigene Wellen verfolgt**.

---

## Bereiche

### M0 — Top-Nav Mobile *(Entscheidung für v4.0.0)*

> **Designentscheidung:** **Hamburger-Menü** mit voller Top-Nav-Liste (Cockpit · Komponenten · Auswertungen · Community · Einstellungen · Hilfe). Auf Touch öffnet sich ein Slide-in/Overlay mit der vollständigen Navigation.
> **Begründung:** Standard-Pattern, das jeder Mobile-User kennt. Wartbar im Solo-Maintainer-Modell. Geringes Risiko.
> **Bewusst nicht in v4.0.0:** Bottom-Tab-Bar. Native-App-Stil, aber Big-Bang-Mobile-Redesign + kostet Bildschirmplatz unten + in HA-Companion-Webview ungewohnt.
> **Cockpit-Sub-Tabs (Live · Heute · Monatsbericht · Jahr · Aussicht)** und Komponenten-Sub-Tabs erscheinen als zweite Zeile darunter. Auf Mobile horizontal scrollbar mit `scroll-snap-x`, aktiver Tab automatisch ins Sichtfeld.
>
> Bezug: [`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md) Top-Nav v4.0.0.

**Datenpunkte:** Mobile-Top-Nav-Entscheidung im IA-Refactor v4.0.0.

---

### M1 — Reduce-Logik (welche Sektionen kollabieren/verschwinden)

> **Mechanik:** `<CollapsibleSection>` mit neuem `defaultOpenMobile={false}`-Prop für datenreiche Sektionen, plus `<HideOnMobile>`-Wrapper für Sektionen die auf Mobile komplett ausgeblendet werden.
> **Designregel (Konzept-Vorschlag):** Cockpit-Übersicht + Wichtigste KPIs „immer offen". Detail-Stunden, Prognosen-Spalten, Lernfaktor-Vergleich kollabiert oder versteckt.
> **Konkrete Pro-Seite-Tabelle** wird beim Umsetzungs-Start gepflegt.
>
> Bezug: [Style-Guide B6 Aufklapp-Verhalten](KONZEPT-STYLE-GUIDE.md#b6--aufklapp-verhalten-collapsiblesection).

**Datenpunkte:** #243 B5c, #204 (Rainer-Simple-Swipe-Card-Wunsch), #203 (detLAN Mobile-Bildlaufleisten).

---

### M2 — Sticky-Header + Scroll-Verhalten

> **Designentscheidung:** Sticky-Header auf Mobile **verschiebbar** statt fixiert am Viewport. Damit verschwindet er beim Scrollen nach unten und kommt beim Scrollen nach oben zurück (Stichwort: „auto-hide on scroll down").
> **HA-Companion-Bar** auf Mobile entfallen lassen (~48 px Gewinn; Swipe-from-left holt sie ohnehin).
> **Floating-Selektoren** dürfen Mobile-Bildschirm nicht zusätzlich blockieren — falls Konflikt: Selektor wird auf Mobile zur Klapp-Schublade.
>
> Bezug: [Style-Guide B5 Selektoren](KONZEPT-STYLE-GUIDE.md#b5--selektoren).

**Datenpunkte:** #243 B5a+B5b, #203.

---

### M3 — Tabellen-Swipe-Pattern

> **Designentscheidung:** Tabellen mit `overflow-x: auto` bekommen einen Swipe-Hinweis (kleines „←→"-Indikator), Scrollbar selber ausgeblendet. Touch-Swipe ist primäre Interaktion.
> **Audit aller `<Table>`-Verwendungen** als Umsetzungs-Phase.
>
> Bezug: [Style-Guide B2 Tabellen + Listen](KONZEPT-STYLE-GUIDE.md#b2--tabellen--listen).

**Datenpunkte:** #243 B5d, #203.

---

### M4 — Touch-Targets + Mindestabstände *(Pflicht-Querschnitt — siehe Style-Guide-Methodik)*

> **Konvention:** Klickbare Elemente ≥ 44×44 px (Apple-/Google-Standard). Listen-Items mit ausreichend Padding für Daumen-Touch.
> **Tap-Konflikte:** keine überlappenden klickbaren Bereiche (z. B. Sektion-Header + Aufklapp-Chevron sollen als ein Touch-Target zählen).
>
> **Status:** keine eigene Welle. In den **Pflicht-Querschnittsregeln** des Style-Guides verankert ([`KONZEPT-STYLE-GUIDE.md`](KONZEPT-STYLE-GUIDE.md) Methodik). Gilt in jeder neuen Seite, jedem Refactor.

**Datenpunkte:** *(noch keine direkten)*

---

### M5 — Companion-App-Spezifika (iframe-Context) *(Pflicht-Querschnitt — siehe Style-Guide-Methodik)*

> **Bekannte Quirks** aus iOS Safari + HA Companion-App:
> - `h-dvh` statt `h-screen` (dynamic viewport, hat Toolbar-Berücksichtigung)
> - `lib/download.ts:downloadFile()` statt `window.open` (Companion blockiert neue Fenster)
> - `overscroll-contain` auf Sticky-Container
> - `position: sticky` in `iframe` mit `overflow:auto` ist tricky — Workaround pro Fall
> - `flex-1`/`min-h-0` in Multi-Breakpoint-Layouts mit Breakpoint-Prefix konsistent zum Direction-Switch
>
> **Status:** keine eigene Welle. In den **Pflicht-Querschnittsregeln** des Style-Guides verankert ([`KONZEPT-STYLE-GUIDE.md`](KONZEPT-STYLE-GUIDE.md) Methodik). Diese Sektion bleibt als Referenz-Dokumentation für die Hintergründe der einzelnen Quirks.

**Datenpunkte:** bestehende interne Linie aus früheren iOS-Tests.

---

### M6 — Card-Stil-Anlehnung (Beobachtung, kein Designauftrag)

> Simple-Swipe-Card-Format (Rainer #204-Screenshot) als möglicher Wunschstil für die wichtigsten Mobile-Kacheln. **Stakeholder-Druck heute dünn** (Rainer Mobile raus). Bleibt als Datenpunkt in Beobachtung, kein Designauftrag.

**Datenpunkte:** #204.

---

## Querverweise

- **Informationsarchitektur v4.0.0** → [`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md)
- **Desktop-Style-Guide** → [`KONZEPT-STYLE-GUIDE.md`](KONZEPT-STYLE-GUIDE.md)
- **Bekannte iOS/Companion-Stolperstellen** sind im Code bereits punktuell adressiert + in den Pflicht-Querschnittsregeln des Style-Guides verankert.
- **Konzept-Issue #243** mit Bausteinen B5a–B5e als Sub-Tracker.
