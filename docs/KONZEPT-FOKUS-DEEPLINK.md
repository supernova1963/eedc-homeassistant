# Konzept — Fokus-/Vollbild-Ansicht per Deep-Link + HA-Einbettung (ideen.md #2)

> ## **Status (gemessen 2026-08-08): ENTWURF — nichts davon ist gebaut**
>
> **Aus `docs/drafts/` nach `docs/` gewandert (2026-08-08).** Es erklärt den Roadmap-Punkt **Fokus-Deep-Link + HA-Einbettung** aus [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110); wer dort liest, was geplant ist, soll den Umfang nachlesen können.
> Es trägt bewusst **keine Versionsnummer, nur dieses Mess-Datum** (Muster aus #359) — ein Status,
> der eine Version nennt, altert garantiert.
>
> **Nicht auf der Website und nicht in der In-App-Hilfe:** `website/scripts/sync-docs.sh` und
> `scripts/sync-help.sh` arbeiten beide mit einer **Allowlist**, in der Konzepte und ADRs bewusst
> fehlen. Dieses Dokument ist im Repository lesbar — es ist kein Anwender-Handbuch.
>
> **Offen: alles.** Vor dem Bau stehen **vier unbeantwortete Abnahme-Fragen** (Timing · Auth · Polling · Schema). Leitplanke des Maintainers: **kein Teil-Bau** — wenn, dann für V4 vollständig und benutzerfreundlich. Die HACS-Card (FD-7) ist ausdrücklich ein eigenes Vorhaben und käme nur bei echter Nachfrage.


## Maßnahmen-Register (fortschreibbar — Stand 2026-07-28)

> **Nichts davon ist gebaut** — dieses Dokument ist reiner Entwurf. Die Zeilen stehen hier, damit der
> Umfang beim Bau nicht neu erhoben werden muss (Leitplanke 2: **kein Teil-Bau**).

| # | Maßnahme | Status | Notiz |
| --- | --- | --- | --- |
| **FD-1** | URL-Vertrag `#/v4/<sicht>?fokus=<blockId>[&kiosk=1][&theme=…]` | ⬜ | Query statt eigener Route; Block-IDs werden damit **öffentlicher Vertrag** |
| **FD-2** | Hook `useFokusUrl(persistKey)` zentral in `BlockShell` + `FokusKachel` | ⬜ | gilt dann sofort für ALLE V4-Sichten |
| **FD-3** | „Link kopieren / In HA einbetten"-Aktion in der `FokusVollbild`-Kopfzeile | ⬜ | **der Benutzerfreundlichkeits-Kern** — Nutzer baut nie eine URL von Hand |
| **FD-4** | Kiosk-Modus (`&kiosk=1`): Chrome weg + read-only | ⬜ | „Chart ⇄ Tabelle" bleibt (reine Ablesung, CT-5) |
| **FD-5** | Degradation bei totem `?fokus=`-Ziel | ⬜ | Pflicht-Testfall, nicht optional |
| **FD-6** | Hilfe-Abschnitt „eedc im HA-Dashboard" in `HANDBUCH_BEDIENUNG` | ⬜ | erst wenn gebaut; Mixed-Content-Grenze ehrlich nennen |
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
> kann: Heatmap Monat × Ladestand, Sizing-Kurve, Prognose-vs-IST. Wer ihn als Dashboard-Ersatz
> verkauft, verspricht einen Fremdkörper: kein Theme, kein Karten-Layout, eigenes Scrolling.

**Vorbedingung:** von den 4 Abnahme-Fragen unten (Timing · Auth · Polling · Schema) ist
**Timing** mit dem Entscheid vom 13.08. beantwortet; **Auth · Polling · Schema** sind offen,
und **Auth wird zuerst gemessen** (Kasten oben).
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
- App ist faktisch single-light (`darkMode:'class'` konfiguriert, kein Toggle).

## Vorschlag

### 1. URL-Vertrag (Query-Parameter, nicht neue Route)

`#/v4/<sicht>?fokus=<blockId>[&kiosk=1][&theme=…]` — z. B.
`#/v4/cockpit/live?fokus=energiefluss&kiosk=1`.

- **Query statt eigener Route:** die Seite unter dem Overlay muss ohnehin mounten
  (Datenladung, Kopf-Slot) — eigene Route = zweite Mount-Wahrheit. Muster wie
  `?erfassen=` (B5). ⤢ öffnen/schließen synchronisiert den Param (replaceState)
  → Bookmark/Teilen/Reload funktionieren automatisch.
- **Vertrag = öffentlich + rückwärtskompatibel:** unbekannte Params ignorieren,
  bekannte nie umdeuten (HACS-Card würde unabhängig vom Add-on aktualisiert).
  `theme` von Tag 1 reserviert (HA-Dashboards sind oft dunkel; liefert erst mit
  dem Farbpaletten-Thema echtes Dark). `poll` als spätere Reserve notiert.

### 2. „Einbetten"-Aktion = der Benutzerfreundlichkeits-Kern

In der `FokusVollbild`-Kopfzeile eine Aktion **„Link kopieren / In HA einbetten"**:
kopiert die absolute Kiosk-URL (aus `window.location` — unter Ingress läuft der
Browser bereits auf dem HA-Origin, die URL stimmt automatisch) + Kurzhinweis
„In HA: Dashboard → Karte → Webseite (Webpage-Karte), URL einfügen". Der Nutzer
sieht nie das URL-Schema.

### 3. Kiosk-Verhalten

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

## Offene Entscheide (Gernot)

1. **Timing:** nach Flip einplanen (Empfehlung; Roadmap-#110-Kandidat) — ok?
2. **Auth:** Ingress-Session bzw. Standalone-Erreichbarkeit reicht (Empfehlung:
   ja — kein neuer Auth-Mechanismus); tokenisierter Read-only-Zugang erst ggf.
   mit der HACS-Card.
3. **Polling im Kiosk:** Intervall gleich lassen (Empfehlung), `poll`-Param als
   Reserve; bekannte Grenze: N Cards = N iframes = N-faches Polling.
4. **Schema ok?** `?fokus=<blockId>&kiosk=1` + Reserve `theme`/`poll`.
