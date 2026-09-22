# Konzept — Fokus-/Vollbild-Ansicht per Deep-Link + HA-Einbettung (ideen.md #2)

> ## ✅ **Status: GEBAUT 2026-09-22** — FD-1 · FD-2 · FD-3 · FD-5 · FD-6 ausgeliefert, **FD-4 (Kiosk) ⛔ nicht gebaut**, FD-7 ⏸ separat
>
> Das Dokument ist damit aus `docs/drafts/` nach `docs/` gewandert (22.09.2026) — die Regel aus
> [DEVELOPMENT.md](DEVELOPMENT.md) gilt nur für Dokumente, die **nur noch einen Bauplan** enthalten.
> Es trägt bewusst **keine Versionsnummer, nur dieses Datum**; die Release-Nummer steht im
> [CHANGELOG](../CHANGELOG.md).
>
> **Was gebaut wurde** (Bauplan `plans/vorlage-fd-fokus-deeplink-f3.md`, Zuschnitt Gernot 22.09.):
>
> | # | Maßnahme | Stand |
> | --- | --- | --- |
> | **FD-1** | URL-Vertrag `#/<sicht>?fokus=<id>[&ansicht=tabelle]` | ✅ **ohne** `kiosk=`/`theme=`/`zurueck=` |
> | **FD-2** | Ein zentraler Hook in `BlockShell` + `FokusKachel` + Energiefluss | ✅ als `hooks/useDeepLinkFokus.ts` |
> | **FD-3** | „Link / Einbetten" in der `FokusVollbild`-Kopfzeile | ✅ `components/blocks/EinbettenKnopf.tsx`, **eine** Adresse |
> | **FD-4** | Kiosk-Modus (`&kiosk=1`) | ⛔ **nicht gebaut** (Entscheid Gernot 22.09.) |
> | **FD-5** | Degradation bei totem `?fokus=`-Ziel | ✅ `components/blocks/FokusFehlt.tsx`, auch auf Cockpit/Live |
> | **FD-6** | Hilfe-Abschnitt | ✅ [HANDBUCH_BEDIENUNG §1.5](HANDBUCH_BEDIENUNG.md#15-eine-eedc-anzeige-im-home-assistant-dashboard) |
> | **FD-7** | HACS-Card | ⏸ eigenes Vorhaben, nur bei echter Nachfrage |
>
> ⛔ **Warum kein Kiosk-Modus (FD-4), obwohl §3 ihn beschreibt** (Entscheid Gernot, 22.09.2026):
> Die **Deep-Link-Ansicht IST die Einbett-Form** — sie zeigt genau eine Anzeige, ohne Zurück,
> ohne ESC, mit read-only Park und System-Theme. Ein zweiter Modus, der stattdessen eine *ganze
> Sicht* ohne Leisten zeigt, wäre eine zweite Bauform für dieselbe Absicht, und der Melder-Fall
> („von da wieder zurück geht nicht", Fesa2702) ist mit *einbetten statt verlinken* beantwortet:
> Der Rückweg ist das Dashboard drumherum. Damit entfallen auch `zurueck=` (Rückweg-Knopf) und
> `theme=` — die Karte folgt dem **System-Theme**, einen Umschalter gibt es dort nicht.
> **Nicht neu aufrollen**; wer es doch will, bringt einen Anwender mit, dem die Deep-Link-Ansicht
> nicht reicht.
>
> ⛔ **Deep-Links gibt es nur auf Block-Ebene** — keine KPI-, Chart- oder Element-IDs
> (Entscheid Gernot, 22.09.). Betroffen sind genau die Anzeigen, die heute ein ⤢ tragen:
> alle `BlockShell`-Blöcke, die fünf Live-Kacheln und der Energiefluss.
>
> ⭐ **Die Anzeige-IDs sind ab dem Release öffentlicher Vertrag** (sie stehen in fremden
> HA-Dashboards). Gewächtert von `eedc/frontend/src/test/fokus-id-vertrag.test.ts` gegen
> `fokus-ids.snapshot.json` — beim Bau gemessen: **108 IDs in 22 Dateien**. Wer eine umbenennt,
> bekommt den Test rot mit dem Hinweis, dass die Änderung eine CHANGELOG-Zeile „Breaking" braucht.
>
> **Die vier Abnahme-Fragen, abschließend:** **Timing** entschieden (13.08.) · **Auth** am 20.09.
> im HAOS-Lab positiv gemessen (Nicht-Admin `claude`: Panel lädt, Ingress-Antwort
> `X-Frame-Options: SAMEORIGIN`, keine CSP ⇒ eine HA-Webseiten-Karte auf dem HA-Origin rendert
> eedc; Standalone-HTTP in HTTPS-HA bleibt Mixed-Content-blockiert und wird im Handbuch **benannt**)
> · **Polling** unverändert gelassen (kein `poll`-Param; die bekannte Grenze „N Karten = N iframes =
> N-faches Polling" bleibt bestehen) · **Schema** = die Tabelle oben.
>
> ⚠ **Nicht auf der Website und nicht in der In-App-Hilfe:** `website/scripts/sync-docs.sh` und
> `scripts/sync-help.sh` arbeiten mit einer **Allowlist**, in der Konzepte und ADRs bewusst fehlen.
> Für Anwender steht der Inhalt in HANDBUCH_BEDIENUNG §1.5.
>
> ⚑ **Die Infra-Sperre ist am 2026-09-09 gefallen** (Infra Phase 1 abgeschlossen); der Kasten
> §Vorbedingung weiter unten ist Geschichte, nicht Vorgabe.

## Maßnahmen-Register (Stand 2026-09-22: gebaut)

> ⭐ **Der Stand steht im Kasten ganz oben.** Diese Tabelle ist die Fassung vom 28.07.2026 mit
> eingetragenem Ergebnis — sie zeigt, was geplant war und was daraus wurde.

| # | Maßnahme | Status | Notiz |
| --- | --- | --- | --- |
| **FD-1** | URL-Vertrag `#/<sicht>?fokus=<id>[&ansicht=tabelle]` (**prefix-frei**, korrigiert 21.09.) | ✅ **gebaut 22.09.** | Query statt eigener Route; Block-IDs sind damit **öffentlicher Vertrag** (Wächter `fokus-id-vertrag.test.ts`). ⛔ **ohne** `kiosk=`/`theme=`/`zurueck=` — der Parameter ist ein **Eingang, kein Spiegel**: ⤢ und Schließen schreiben die Adresse nicht |
| **FD-2** | Ein zentraler Hook in `BlockShell` + `FokusKachel` | ✅ **gebaut 22.09.** als `hooks/useDeepLinkFokus.ts` | gilt für ALLE V4-Sichten; dazu der Energiefluss (eigener Fokus-State) und `ParkProvider`/`ThemeProvider`. Liest `window.location.hash` **je Mount einmal**, kein `useSearchParams` |
| **FD-3** | „Link kopieren / In HA einbetten"-Aktion in der `FokusVollbild`-Kopfzeile | ✅ **gebaut 22.09.** (`EinbettenKnopf.tsx`) | **der Benutzerfreundlichkeits-Kern** — Nutzer baut nie eine URL von Hand. **Eine** Adresse (nicht drei), `ui/Button` + `ui/Modal` + `useCopyFeedback`; nur im normalen Betrieb, nicht in der Deep-Link-Ansicht |
| **FD-4** | Kiosk-Modus (`&kiosk=1`): Chrome weg + read-only | ⛔ **nicht gebaut** (Entscheid Gernot 22.09.) | Begründung im Kasten oben: die Deep-Link-Ansicht **ist** die Einbett-Form. „Chart ⇄ Tabelle" bleibt dort bedienbar (CT-5 über `&ansicht=tabelle`) |
| **FD-5** | Degradation bei totem `?fokus=`-Ziel | ✅ **gebaut 22.09.** (`FokusFehlt.tsx`) | Pflicht-Testfall, nicht optional — drei Fälle geprüft (unbekannte ID · Zeitraum ohne Daten · alles geparkt), **auch auf Cockpit/Live**, die keine `BlockShell` hat |
| **FD-6** | Hilfe-Abschnitt „eedc im HA-Dashboard" in `HANDBUCH_BEDIENUNG` | ✅ **gebaut 22.09.** (§1.5) | Mixed-Content-Grenze ehrlich genannt; dazu WAS-IST-NEU und CHANGELOG |
| **FD-7** | HACS-Card (iframe-Wrapper) | ⏸ **separat**, nur bei echter Tester-Nachfrage | eigenes Repo + eigenes Konzept; **nie** ein nativer Renderer |

> ## ✅ **ENTSCHIEDEN 2026-08-13 (Gernot): wird umgesetzt.**
>
> Das Dokument ist damit vom Entwurf zum **beschlossenen Vorhaben** geworden; in
> [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) steht es seit dem
> 13.08. unter *In Arbeit / als Nächstes*. Die Leitplanken bleiben **unverändert bindend** —
> insbesondere **kein Teil-Bau**.
>
> ⛔ **Bevor eine Zeile Code entsteht, wird die Abnahme-Frage „Auth" an der echten Box
> gemessen — sie entscheidet über den Nutzen des ganzen Vorhabens.** Der Deep-Link ist die
> leichte Hälfte; die schwere ist die **Adresse**, und sie sieht in den beiden Betriebsarten
> verschieden aus:
>
> * **Add-on-Betrieb: eedc läuft hinter HA-Ingress** (`eedc/config.yaml:33` `ingress: true`,
>   `ingress_port: 8099`). Eine Ingress-Adresse gehört zur HA-Sitzung — **ob sie sich stabil
>   kopieren und in eine Webpage-Card einsetzen lässt, ist eine Messung, keine Annahme.**
>   Fällt sie negativ aus, ist FD-3 („Link kopieren / In HA einbetten") kein Knopf, sondern
>   eine Anleitung — und dann muss dieses Dokument sagen, welche der beiden es wird, bevor
>   gebaut wird.
> * **Standalone-Betrieb:** eedc spricht HTTP, ein HTTPS-HA blockt das iframe (Mixed Content,
>   unten in FD-6 bereits als „ehrlich nennen" vermerkt). Diese Hälfte ist **nicht lösbar**,
>   nur benennbar.
>
> ⚑ **Der wartende Melder ist bekannt und beschreibt genau den Kiosk-Fall:** **Fesa2702**
> (Forum T89667 #140, 09.08.) betreibt Wandtablets im Kiosk-Modus — *„Link zum Dashboard ist
> kein Problem. Aber von da wieder zurück geht nicht."* Der Rückweg aus einer eingebetteten
> Ansicht gehört damit zum Umfang, nicht zur Kür.
>
> ⚠ **Was dieses Vorhaben ausdrücklich NICHT ist: der Weg, eedc-Daten in ein HA-Dashboard zu
> bekommen.** Dafür gibt es die exportierten Sensoren, und sie sind dort das bessere Mittel
> (HA-Theme, native Karten, Automationen, Historie) — rapahl baut damit sichtbar erfolgreich
> eigene Lovelace-Karten. Der Deep-Link zielt auf die Ansichten, die HA **nicht** nachbauen
> kann: Ladestands-Spannen je Monat, Sizing-Kurve, Prognose-vs-IST. Wer ihn als Dashboard-Ersatz
> verkauft, verspricht einen Fremdkörper: kein Theme, kein Karten-Layout, eigenes Scrolling.

> ## ⛔ **Vorbedingung, neu und vorgeschaltet (Entscheid Gernot, 2026-08-29): erst muss das Infrastruktur-Projekt abgeschlossen sein.**
>
> **Vor diesem Vorhaben steht das Homelab-Infra-Projekt** (`infrastrukture/INFRA-PHASE1-AUFBAU.md`,
> Status-Tracker). Solange es läuft, wird am Fokus-Deep-Link **nicht gebaut** — auch nicht
> teilweise, auch nicht „nur die Messung nebenbei".
>
> ⭐ **Der sachliche Grund steht schon im Kasten darüber, er hatte nur keinen Ort:** Die
> Abnahme-Frage **Auth** ist eine **Ingress-Messung an einer laufenden HAOS-Installation** — und
> die einzige Stelle, an der sie ohne Eingriff in die Produktion zu haben ist, ist Infra-Box
> **S6 (HAOS-Test-Lab auf `.198`, Add-on-Repo + HACS)**. Sie ist im Tracker als **nächste offene
> Box** geführt. Ohne sie hieße „Auth messen": an der Produktions-Instanz messen.
>
> **Stand des Infra-Projekts am 29.08. gemessen** (nicht abgeschrieben — `INFRA-PHASE1-AUFBAU.md`
> §Status-Tracker): geschlossen sind **S0 · S1 · S2 · S5**; offen sind **S3** (Cluster; Hürde
> `pvecm add` mit Gästen), **S4** (QDevice), **S6** (HAOS-Test-Lab, nächste Box, braucht **keinen**
> Cluster), **S7** (Replikation), **S8** (Verifikation) und **INT** (Integrations-Skelett).
>
> ⚑ **Die Gegenrichtung ist mitnotiert**, damit die Abhängigkeit nicht nur von hier aus sichtbar
> ist: [[project_infra_devlab_ausbau]] trägt den Vermerk, dass mit dem Abschluss des Projekts
> dieses Vorhaben entsperrt ist. *Ein Plan, den nur eine Seite kennt, wird von der anderen
> übersehen* — genau der Befund, mit dem dieser Ordner am 09.08. überhaupt in die
> Neu-Einwertung aufgenommen wurde (N-206).
>
> ⚠ **#110 sagt das noch nicht.** Dort steht der Punkt weiter unter *In Arbeit / als Nächstes* mit
> „entschieden: wird umgesetzt". Das Issue wird ohne ausdrückliche Aufforderung nicht angefasst;
> die Zeile ist im Nachlauf-Auftrag (§Schritt 2b) namentlich vorgemerkt.

**Vorbedingung (fachlich):** von den 4 Abnahme-Fragen unten (Timing · Auth · Polling · Schema) ist
**Timing** mit dem Entscheid vom 13.08. beantwortet; **Auth · Polling · Schema** sind offen,
und **Auth wird zuerst gemessen** (Kasten oben) — **nach** der Infra-Vorbedingung darüber, auf dem
HAOS-Test-Lab statt an der Produktion.
Nachverfolgt in der Roadmap [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) („Fokus-Deep-Link + HA-Einbettung").

---

> **Status: ENTWURF v2 (2026-07-19) — überarbeitet nach Gernot-Leitplanke:
> „Wenn, dann nur für V4 und dann aber benutzerfreundlich und zu-Ende-gedacht."**
> Kein Bau vor Abnahme. Timing-Empfehlung: **nach Flip, EIN kompletter Bau**
> (ersetzt den früheren Erststep-Wunsch „Cockpit/Live/Energiefluss vor Flip" —
> ein Teil-Bau nur für einen Block widerspräche der Leitplanke).
> Quelle: `docs/drafts/tmp/ideen.md` (2026-07-11) + Sessions 2026-07-19.

## Ziel

Die Fokus-/Vollbild-Ansicht eines Blocks (heute nur per ⤢-Klick im UI) soll direkt
per URL aufrufbar sein. Hintergrund: Einbettung in HA-Dashboards (Webpage-/iframe-
Card), später ggf. eine eigene HACS-Card, die eedc-Ansichten als Cards anbietet.

## Leitplanken (Gernot 2026-07-19 — bindend)

1. **Nur V4.** Keine V3-Verdrahtung (V3 ist Flip-Donor).
2. **Kein Teil-Bau.** Nicht „nur Energiefluss" — wenn, dann alle
   BlockShell-/FokusKachel-Sichten zentral (ein Hook, ein Anfasspunkt).
3. **Benutzerfreundlich end-to-end.** Der Nutzer baut NIE eine URL von Hand —
   die App erzeugt und erklärt den Einbettungs-Link selbst (s. Vorschlag §2).
4. **Der heutige Workaround bleibt inoffiziell.** Webpage-Card auf die ganze
   Sicht + Wegparken pro Gerät funktioniert (kein `X-Frame-Options`/CSP im
   Backend, Ingress-Session läuft mit), ist aber fragil (Chrome klickbar,
   localStorage-gebunden) — wird NICHT als Feature dokumentiert/beworben.

## Ist-Stand (SoT, verifiziert 2026-07-19)

- **`FokusVollbild`** (`components/blocks/FokusVollbild.tsx`) = DAS eine Overlay
  (Portal an body, `fixed inset-0`), genutzt von `BlockShell` (⤢ je Block) und
  `FokusKachel` (⤢ je Karte); seit v3.45.5 auch Cockpit/Live einheitlich. Seit
  Paket CT (`05734bcb`) trägt die Kopfzeile den „Chart ⇄ Tabelle"-Umschalter.
- Block-Identität existiert: `BlockShell.persistKey` + Block-`id` im Stack.
  **Kein neues Registry-Konstrukt nötig** — aber: IDs werden mit dem Deep-Link
  **öffentlicher Vertrag** (Umbenennen bricht fremde HA-Dashboards).
- Fokus-Zustand ist heute reiner Komponenten-State — nirgends in der URL.
- **Park-/Klappzustand = localStorage pro Gerät** (`eedc-park:<key>`,
  `ParkContext.tsx:21` · `eedc-bloecke:<key>`, `BlockShell.tsx:21`) — geparkte
  Elemente bleiben auch im Fokus/Kiosk unsichtbar, aber nur auf DEM Gerät.
- **Theme: light · dark · system, mit Umschalter** — `context/ThemeContext.tsx` (localStorage `eedc-theme`,
  Default `system`), Cycle in `IATopNav.tsx:91`; `darkMode:'class'` in `tailwind.config.js:13`.
  ⛔ Hier stand bis 21.09. „App ist faktisch single-light … kein Toggle" — das war vor dem Flip wahr und
  trug die Empfehlung, `theme` nur zu *reservieren*. Mit einem vorhandenen Ziel ist `theme=` **baubar**.

## Vorschlag

### 1. URL-Vertrag (Query-Parameter, nicht neue Route)

> ⭐ **Gebaut wurde `#/<sicht>?fokus=<id>[&ansicht=tabelle]`** — z. B.
> `#/cockpit/live?fokus=live:energiefluss` oder `#/cockpit/jahr?fokus=bilanz&ansicht=tabelle`.
> `kiosk=` und `theme=` sind **entfallen** (Entscheid 22.09., Kasten oben); `poll` bleibt Reserve.
> ⛔ **Und der Parameter spiegelt den Zustand NICHT:** Das ⤢ im normalen Betrieb schreibt die
> Adresse nicht, das Schließen ändert sie nicht. Der Absatz darunter empfahl 21.09. noch das
> Gegenteil („⤢ öffnen/schließen synchronisiert den Param") — dagegen sprachen zwei gemessene
> Gründe: eine Sicht, die ihre eigenen Parameter neu setzt (`datum`, `jahr`, `monat`, `h`), würde
> die eingebettete Ansicht sonst umwerfen, und unter `HashRouter` ist ein Hash-Wechsel
> same-document, die Sicht mountet dabei aber neu — ein Spiegel wäre eine zweite Zustandswahrheit
> neben dem lokalen Fokus-State.

`#/<sicht>?fokus=<blockId>[&kiosk=1][&theme=…]` — z. B.
`#/cockpit/live?fokus=energiefluss&kiosk=1`.

⛔ **Hier stand bis 21.09. das Präfix `#/v4/` — das gibt es seit dem Flip `243944e5` (23.07.) nicht mehr.**
Im Quelltext lebt es nur noch als Lesezeichen-Versicherung (`App.tsx:20-27`), und die leitet auf den
prefix-freien Pfad um. Eine Adresse aus diesem Dokument hätte funktioniert, wäre aber keine kanonische —
und der URL-Vertrag ist der Teil, der **öffentlich** wird.

- **Query statt eigener Route:** die Seite unter dem Overlay muss ohnehin mounten
  (Datenladung, Kopf-Slot) — eigene Route = zweite Mount-Wahrheit. Muster wie
  `?erfassen=` (B5). ⤢ öffnen/schließen synchronisiert den Param (replaceState)
  → Bookmark/Teilen/Reload funktionieren automatisch.
- **Vertrag = öffentlich + rückwärtskompatibel:** unbekannte Params ignorieren,
  bekannte nie umdeuten (HACS-Card würde unabhängig vom Add-on aktualisiert).
  `theme` von Tag 1 reserviert (HA-Dashboards sind oft dunkel; liefert erst mit
  dem Farbpaletten-Thema echtes Dark). `poll` als spätere Reserve notiert.

### 2. „Einbetten"-Aktion = der Benutzerfreundlichkeits-Kern

> ✅ **Gebaut** als `components/blocks/EinbettenKnopf.tsx` — mit **einer** Adresse statt einer
> Kiosk-URL, und mit dem Standalone-Satz zur Mixed-Content-Grenze, wenn eedc nicht hinter dem
> Ingress läuft.

In der `FokusVollbild`-Kopfzeile eine Aktion **„Link kopieren / In HA einbetten"**:
kopiert die absolute Kiosk-URL (aus `window.location` — unter Ingress läuft der
Browser bereits auf dem HA-Origin, die URL stimmt automatisch) + Kurzhinweis
„In HA: Dashboard → Karte → Webseite (Webpage-Karte), URL einfügen". Der Nutzer
sieht nie das URL-Schema.

### 3. Kiosk-Verhalten

> ⛔ **NICHT gebaut** (Entscheid Gernot, 22.09.2026 — Begründung im Kasten ganz oben). Was von
> diesem Absatz gilt, steckt in der **Deep-Link-Ansicht** selbst: kein Zurück, kein ESC, keine
> Unterzeile, kein Einbetten-Knopf, **Park read-only** (geparkt bleibt geparkt), System-Theme —
> „Chart ⇄ Tabelle" und die Zeitraum-Auswahl bleiben bedienbar. Was NICHT gebaut wurde, ist die
> *ganze Sicht ohne Leisten* und der Rückweg-Knopf `zurueck=`.

`&kiosk=1` (nur mit `fokus=`): Nav/Chrome komplett weg (IATopNav,
StatusFusszeile, Schließen-X) und **read-only** — Park-/Klapp-/Einstellungs-
Aktionen ausgeblendet (ein Dashboard-Widget hat keine Nebenwirkungen);
„Chart ⇄ Tabelle" bleibt (reine Ablesung). Kuratierung per Parken passiert in
der Nicht-Kiosk-Ansicht am selben Gerät (localStorage-Semantik, s. Ist-Stand).

### 4. Degradation (Pflicht-Testfall)

`?fokus=`-Ziel absent (falsche/umbenannte ID, Lücken-Tag, alle Parkbaren des
Blocks geparkt → Block-Hülle entfällt, z. B. `CockpitJahrV4.tsx:149`): freundlicher
Hinweis-Zustand statt Leerfläche/Absturz.

### 5. Hilfe

Eigener Abschnitt „eedc im HA-Dashboard" in `HANDBUCH_BEDIENUNG` (R2a-neu) —
erst wenn gebaut; Mixed-Content-Grenze ehrlich nennen (HTTPS-HA blockt
HTTP-Standalone-iframe; Ingress ist davon nicht betroffen).

## Etappen (neu geschnitten lt. Leitplanke)

- **EIN Bau (nach Flip):** Hook `useFokusUrl(persistKey)` zentral in
  `BlockShell` + `FokusKachel` → gilt sofort für ALLE V4-Sichten; Kiosk-Modus +
  Einbetten-Aktion + Degradation + Hilfe-Abschnitt. Aufwand: klein-mittel.
- **HACS-Card (separat, nur bei echter Tester-Nachfrage):** dünner
  iframe-Wrapper (Ingress-URL-Auflösung, Block-Picker im Card-Editor,
  Theme-Übergabe) — NIE ein nativer Renderer (zweite Render-Wahrheit neben den
  SoT-Komponenten; für einfache KPIs gibt es bereits den HA-Sensor-Export).
  Eigenes Repo, hacs.json, Releases. Eigenes Konzept, wenn Nachfrage da.

## Offene Entscheide (Gernot) — alle beantwortet, s. Kasten oben

1. **Timing:** nach Flip einplanen (Empfehlung; Roadmap-#110-Kandidat) — ok?
2. **Auth:** Ingress-Session bzw. Standalone-Erreichbarkeit reicht (Empfehlung:
   ja — kein neuer Auth-Mechanismus); tokenisierter Read-only-Zugang erst ggf.
   mit der HACS-Card.
3. **Polling im Kiosk:** Intervall gleich lassen (Empfehlung), `poll`-Param als
   Reserve; bekannte Grenze: N Cards = N iframes = N-faches Polling.
4. **Schema ok?** `?fokus=<blockId>&kiosk=1` + Reserve `theme`/`poll`.
