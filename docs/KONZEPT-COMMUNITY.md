# Konzept: Community-Site — Datenqualität & Attraktivität

> ## **Status (gegen den Code gemessen 2026-08-13): Säule 1 zur Hälfte gebaut · Säule 2 unangetastet**
>
> Der Kopf sagte bis heute „Kein Code" — das stimmt so nicht mehr, und die Differenz ist die
> Aktualitäts-Prüfung wert:
>
> * **Min-N / k-Anonymität: teilweise gebaut.** `eedc-community/backend/api/components.py:76`
>   trägt `MIN_ANLAGEN_FUER_AGGREGAT = 3` und liefert darunter **keinen** Wert (Commit `4808662`,
>   entstanden als Folge von **F-23**). ⚠ **Es gilt nur für die Komponenten-Aggregate** —
>   `statistics.py` und `aggregations.py` haben weiterhin keine Schwelle, die Policy des Konzepts
>   („Gruppen-Statistik erst ab N ≥ 3") ist also **nicht** durchgesetzt, sondern an einer Stelle
>   vorweggenommen. Verwandt: der offene Fund **N-233** (die Verteilungs-Route antwortet für
>   unbekannte Metriken still leer statt mit 404).
> * **Aktiv-/Passiv-Zählung: nicht gebaut.** `aktualisiert_am` wird in keiner API-Datei
>   ausgewertet (Negativ-Grep über `backend/api/*.py`) — die Headline ist unverändert der rohe
>   Gesamt-Count. ⚑ **Am 2026-08-13 gemessen: 100 Anlagen in 16 Regionen.** Damit ist die
>   Größenordnung eine andere als bei der Konzept-Erstellung, und die Frage „wie viele davon
>   liefern noch?" wiegt schwerer als im Mai.
> * **Säule 2 vollständig offen:** kein Schnellvergleich, keine Share-Buttons, `sitemap.xml` und
>   `robots.txt` liegen weiterhin **statisch** unter `backend/static/`, keine server-gerenderten
>   Landing-Pages.
>
> ⚑ **Zwei Punkte sind am 2026-08-13 hier eingezogen**, weil das archivierte
> [`archive/KONZEPT-UMFRAGE.md`](archive/KONZEPT-UMFRAGE.md) ihre einzige Heimat war:
> **Gruppen-Vergleich (2–5 Nutzer)** — mittlerer bis hoher Aufwand, ausdrücklich nur bei starker
> Nachfrage — und ein **Akkudoktor-Tools-Link** für Neueinsteiger. Beide gehören zur
> Community-Site, beide sind reine Kandidaten ohne Trigger.
>
> Status davor: **Entwurf / Diskussionsgrundlage** (2026-05-28). Betrifft Repo `eedc-community` (energy.raunet.eu). Bündelt zwei Stoßrichtungen aus Roadmap #110: **(1) Datenqualität** (QS-Wunsch Gernot — aktive vs. aufgegebene Anlagen) und **(2) Attraktivität & Reichweite** (Schnellvergleich, Share, SEO).
>
> **Bewusster Zielkonflikt:** Säule 1 macht die Headline-Zahl *ehrlich-kleiner*, Säule 2 will sie *größer*. Auflösung: Headline bleibt der warme Gesamt-Wert, „davon N aktuell liefernd" als Vertrauenssignal daneben — beides koexistiert.

---

# Säule 1 — Datenqualität: Aktiv/Passiv-Zählung & Min-N-Schutz

## Problem

Der Headline-Zähler ist ein roher Gesamt-Count über *alle* je eingereichten Anlagen — `func.count(Anlage.id)` in `backend/api/stats.py` (~Z. 31), angezeigt als „Was unsere **{anzahl_anlagen} Anlagen** zusammen erreicht haben" (`frontend/src/sections/CommunityImpact.tsx:38`). Eine Anlage, die einmal vor einem Jahr eingereicht und nie wieder geliefert hat, zählt voll mit.

Nuance: **Passive Anlagen verzerren die Monats-Benchmarks kaum** — die laufen nach `jahr/monat`, eine aufgegebene Anlage trägt nur zu den Monaten bei, die sie geliefert hat. Spürbar ist „passiv" daher fast nur bei **(a)** der Headline und **(b)** den Ausstattungs-/Regionen-Verteilungen.

Das Signal existiert bereits: `Anlage.aktualisiert_am` (`backend/models.py:50`, `onupdate` bei jedem Submit), wird aber nirgends ausgewertet.

## Definition „aktiv"

| Signal | Pro | Contra |
|---|---|---|
| **A) `aktualisiert_am` innerhalb X Tagen** | Trivial, ein Feld | Einmal-Einreicher mit aktuellem Timestamp aber altem Datenmonat gilt fälschlich als aktiv |
| **B) jüngster `Monatswert` in den letzten K abgeschlossenen Monaten** | Spiegelt „liefert laufend" — der eigentliche Sinn | Ein Join mehr |

**Empfehlung: B**, Schwelle **K = 2 abgeschlossene Monate** (Config-Konstante, nicht hartkodiert — Einreich-Verzug berücksichtigen).

## UI-Wirkung

Ergänzend, nicht ersetzend: Headline bleibt Gesamt; daneben „N liefern aktuell Daten" (statt wertendem „aktiv/passiv"). Verteilungen default auf allen Anlagen (größere Stichprobe), Stand klar labeln; optionaler Toggle „nur aktuell liefernde" als spätere Ausbaustufe.

## Min-N / k-Anonymität (verwandt)

In `aggregations.py`/`stats.py` **keine** Mindest-N-Schwelle gefunden. Region/Komponenten-Zelle mit n=1 zeigt trotzdem Ø-Werte → De-Anonymisierungs-/DSGVO-Risiko. **Policy:** Gruppen-Statistik erst ab **N_MIN ≥ 3** (konservativer 5); darunter „zu wenige Anlagen". Globale Aggregate + Headline (großes N) unberührt.

## Nicht-Ziele

Keine Löschung passiver Anlagen, keine Exklusion aus Pro-Monats-Benchmarks. Reines Anzeige-/Labeling- + Privacy-Thema.

## Offene Entscheidungen Säule 1

1. „aktiv"-Signal B (empfohlen) vs A?
2. Schwelle K = 2 oder 3 Monate?
3. N_MIN = 3 oder 5?
4. Verteilungen: nur Gesamt + Label, oder Toggle?
5. Wording: „aktiv" vs. „liefert aktuell Daten"?

---

# Säule 2 — Attraktivität & Reichweite

## Ist-Stand (verifiziert 2026-05-28)

- **Architektur:** client-gerenderte **SPA** (React/Vite, statisch aus `backend/static`), hand-gerolltes Routing (`main`/`impressum`/`datenschutz` via pushState in `App.tsx`), Personalized View über `?anlage=HASH`. Daten komplett client-seitig aus `/api`.
- **Schon vorhanden:** MonthlyHighlightBanner, CommunityHighlights, RegionenRanking, TopPerformer, AusstattungVergleich, GroessenVerteilung, MonatsvergleichTab, GermanyHeatmap, CommunityImpact, MitmachenTab + statische `sitemap.xml` (nur 3 URLs) + `robots.txt`.
- **Noch nicht vorhanden:** Schnellvergleich-Eingabe, Share-Buttons, dynamische/SEO-Permalink-Seiten, einbettbares Widget.

## Architektur-Weiche (zentral)

Weil die Site client-gerendert ist, sehen Suchmaschinen + Link-Previews nur die leere Shell. **Jede echte SEO-/Sharing-Maßnahme braucht server-gerendertes HTML** (Inhalt + Meta/OG). Pragmatischster Weg: **FastAPI-gerenderte Landing-Pages** als eigene HTML-Routes *neben* der SPA — nicht über SPA-Routing/Prerendering. Das ist die Voraussetzung für SEO-Ranking *und* Rich-Previews beim Teilen.

## Vorschläge (priorisiert nach Aufwand/Wirkung)

1. **Schnellvergleich auf der Startseite** — *klein, höchster Engagement-Hebel.* Eingabe „Jahresertrag kWh + kWp + Region" → sofort Perzentil-Einordnung gegen die Community, **ohne Installation**. Rein Frontend gegen vorhandene `/api`-Daten (ggf. Mini-Benchmark-Endpoint). Conversion-Anker: „automatisch & laufend mit dem Add-on".
2. **Share-Buttons** — *klein.* Web Share API (mobil) + WhatsApp/Link-kopieren-Fallback. Primär auf PersonalizedView (eigenen Benchmark teilen) + Highlight-Banner. Synergie mit Punkt 4 (OG-Meta für hübsche Previews).
3. **Dynamische Sitemap** — *klein, Backend.* FastAPI-Route `/sitemap.xml` statt 3 statischer URLs; listet verfügbare Monate + Regionen (sobald Punkt 4 existiert).
4. **SEO-Landing-Pages (server-gerendert)** — *mittel, Backend.* FastAPI-HTML-Routes mit echten Zahlen + Meta/OG + Canonical + Links in die App:
   - `/monat/{jahr}/{monat}` → „PV-Ertrag {Monat} {Jahr} im Community-Schnitt" (Median/IQR, n, Verteilung).
   - `/region/{BL}` → „PV-Ertrag {Bundesland}".
   - Min-N-Schutz aus Säule 1 greift hier mit.
5. **Einbettbares Widget** — *strategisch, mittel/groß.* iFrame/JS-Snippet für Foren/Blogs → jeder Einbau = Backlink. Später.

## Empfohlene Reihenfolge Säule 2

Schnellvergleich → Share-Buttons → (SEO-Landing-Pages **+** dynamische Sitemap zusammen, da SEO ohne Server-HTML wirkungslos) → Widget.

## Offene Entscheidungen Säule 2

1. SEO-Landing-Pages via FastAPI-HTML (empfohlen) vs SPA-Prerendering vs Verzicht?
2. Schnellvergleich: rein client-seitig gegen `/api/stats` oder eigener Benchmark-Endpoint?
3. Share: Web Share API + Fallback, oder nur Link-kopieren?

---

# Verwandte / bewusst getrennte Punkte

- ~~**Community-Umfrage** — zurückgestellt bis ≥30 geteilte Anlagen, eigenes Konzept `docs/KONZEPT-UMFRAGE.md`.~~ ⛔ **ARCHIVIERT am 2026-08-13** (`docs/archive/KONZEPT-UMFRAGE.md`, Entscheid Gernot: kein akuter Bedarf mehr). ⚠ Nicht weil die Schwelle unerreicht blieb — **sie ist mit 100 Anlagen mehr als dreifach überschritten** —, sondern weil der fertige Fragebogen nach Funktionen fragte, die seither gebaut wurden.
- **Ausreißer-/Plausibilitäts-Guard beim Submit** (kWh/kWp-Band) — eigene QS-Maßnahme; Median/IQR (Commit `dfe6739`) mildert bereits.
- Vorgänger-Brainstorm (2026-04-17) lebt in Memory `project_community_attraktivitaet`; dieses Dokument erdet es im aktuellen Code-Stand.
