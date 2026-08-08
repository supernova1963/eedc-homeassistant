# Konzept-Skizze — Tabellen zu allen Charts (ideen.md #3)

> ## **Status (gemessen 2026-08-08): Mechanik + drei Piloten ausgeliefert · Voll-Rollout offen**
>
> **Aus `docs/drafts/` nach `docs/` gewandert (2026-08-08).** Es erklärt den Roadmap-Punkt **Diagramm als Tabelle ablesen + CSV: Voll-Rollout** aus [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110).
> Es trägt bewusst **keine Versionsnummer, nur dieses Mess-Datum** (Muster aus #359) — ein Status,
> der eine Version nennt, altert garantiert.
>
> **Nicht auf der Website und nicht in der In-App-Hilfe:** `website/scripts/sync-docs.sh` und
> `scripts/sync-help.sh` arbeiten beide mit einer **Allowlist**, in der Konzepte und ADRs bewusst
> fehlen. Dieses Dokument ist im Repository lesbar — es ist kein Anwender-Handbuch.
>
> **Offen:** **CT-4** (Voll-Rollout über die Serien-Meta der übrigen Charts — billiger als ursprünglich geschätzt, weil ein Legenden-Sweep die Serien-Meta in rund 20 Charts normalisiert hat) und **CT-5** (`?ansicht=tabelle`), das absichtlich am noch nicht abgenommenen [Fokus-Deep-Link](KONZEPT-FOKUS-DEEPLINK.md) hängt.


## Maßnahmen-Register (fortschreibbar — Stand 2026-07-28)

| # | Maßnahme | Status | Beleg / Rest |
| --- | --- | --- | --- |
| **CT-1** | `ChartDatenTabelle`-SoT (Regel T) | ✅ `05734bcb`, ausgeliefert mit v4.0.0 | `components/ui/ChartDatenTabelle.tsx` (+ Test) |
| **CT-2** | Toggle „Chart ⇄ Tabelle" **nur** im Fokus-Overlay (kein Kartenkopf-Icon) | ✅ | `components/blocks/FokusVollbild.tsx`, Typ in `blocks/types.ts` |
| **CT-3** | 3 Piloten (Cockpit-Monat-Verlauf · Jahr-Verlauf · Live-Tagesverlauf) | ✅ | `v4/CockpitMonatV4.tsx` · `v4/CockpitJahrV4.tsx` · `v4/CockpitLiveV4.tsx` — **die einzigen drei Konsumenten**, 2026-07-28 nachgezählt |
| **CT-4** | **Voll-Rollout** über die Serien-Meta der übrigen V4-/geteilten Charts | ⬜ **offen** | Roadmap [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) („Diagramm als Tabelle ablesen + CSV: Voll-Rollout"). Billiger als ursprünglich geschätzt, weil der Legenden-Toggle-Sweep (`7302cc0b`) die Serien-Meta in ~20 Charts normalisiert hat. Rest-Aufwand = Charts ohne `ChartLegende` (Werteklassen-Legenden · `AnteilDonut` · `WetterWidget`) |
| **CT-5** | `?ansicht=tabelle` als Deep-Link-Parameter | ⬜ **offen, absichtlich** — gehört zum Fokus-Deep-Link, der noch Entwurf ist | [`KONZEPT-FOKUS-DEEPLINK.md`](KONZEPT-FOKUS-DEEPLINK.md) §1 — fällt mit dessen Abnahme |

**Bewusst nicht:** V3-only-Charts (Flip-Donoren) bekommen nichts mehr; keine handgeschriebene
Zweit-Tabelle je Chart; `WerteTabelle` bleibt die reiche Sicht-Tabelle.

---

> **Status: ✅ GEBAUT + COMMITTED `05734bcb` (2026-07-19, V4-dormant, nicht gepusht — mit v4.0.0 ausgeliefert).**
> Abnahme Gernot 2026-07-18: „Mechanik + Piloten vor Flip — Synergie mit dem
> Fokus-Deep-Link (`?ansicht=tabelle` wäre gratis)."
> Gebauter Umfang = beschlossener Umfang: **`ChartDatenTabelle`-SoT + Toggle NUR im
> Fokus-Overlay (kein Kartenkopf-Icon) + 3 Piloten** (Cockpit-Monat-Verlauf,
> Jahr-Verlauf, Live-Tagesverlauf); Voll-Rollout nach Flip. Bau-Detail + Gates:
> Restweg §2 Paket CT. `?ansicht=tabelle` NICHT gebaut (Fokus-Deep-Link = eigener
> Entwurf, kein Bau vor Abnahme). Quelle: `docs/drafts/tmp/ideen.md`.

## Ziel

Zu jedem Chart soll dieselbe Datenbasis auch als Tabelle lesbar sein (Zugänglichkeit,
exakte Werte, Copy/Export) — ohne je Chart eine handgebaute Zweitansicht zu pflegen.

## Ist-Stand (verifiziert)

- **Regel T / `ui/Table`-SoT** existiert (Zeilen-/Kopf-/Fuß-Kanon, `TableSortKopf`,
  `tabelleMasse`); **`CsvExportButton`**-SoT existiert.
- Es gibt bereits *gepflegte* Tabellen-Pendants auf Sicht-Ebene: **`WerteTabelle`**
  (Auswertungen→Tabelle: Zeitreihen mit Spalten-Picker, Vergleich, CSV) und
  **`EnergieprofilTageTabelle`** (Tages-Profile). Diese decken die Kern-Zeitreihen ab.
- Chart-Bestand: 63 Dateien mit Recharts-Charts — **davon ein erheblicher Teil
  V3-only** (`pages/auswertung/*`, alte Dashboards, `pages/aussichten/*` =
  Flip-Donoren). Der relevante Scope ist NUR: `src/v4/**`-Charts + die von V4
  weiterverwendeten Composites (live/, prognose/, speicher-/komponenten-Analysen,
  `ui/AnteilDonut`, Community-V4).

## Vorschlag: EIN Mechanik-SoT statt 63 Einzel-Tabellen

**„Als Tabelle"-Umschalter in der Chart-Hülle, gespeist aus den Chart-Daten:**

1. **`ChartDatenTabelle`-SoT** (neuer Baustein, Regel T): bekommt die ohnehin
   vorhandene Chart-Datenreihe (`data` + Serien-Definitionen mit Label/Einheit/
   Farbe — dieselbe Struktur, die Legende/Tooltip speisen) und rendert daraus
   generisch eine `ui/Table` (1 Zeile je X-Wert, 1 Spalte je Serie, de-DE-Formate,
   Summenzeile wo sinnvoll) + `CsvExportButton`.
2. **Zugang:** Umschalter (Chart ⇄ Tabelle) an der Stelle, wo heute schon die
   Block-/Karten-Werkzeuge sitzen — im **Fokus-/Vollbild-Overlay** (`FokusVollbild`
   bekommt den Toggle in die Kopfzeile) und optional als kleines Icon im Kartenkopf.
   Empfehlung: **nur im Fokus-Overlay** — hält die Karten ruhig, und „genau
   hinschauen" ist genau der Fokus-Anwendungsfall. Synergie mit dem
   Fokus-Deep-Link-Konzept (ein `?fokus=…&ansicht=tabelle` wäre gratis).
3. **Rollout serienweise über die Serien-Definitions-SoTs**, nicht je Datei:
   Charts, die bereits `ChartLegende`/`ChartTooltip` mit Serien-Meta nutzen,
   liefern die Tabelle fast ohne Zusatzcode. Charts ohne saubere Serien-Meta
   werden beim Anfassen (z. B. Legenden-Toggle-Sweep!) mitgezogen — **ein
   kombinierter Sweep mit `project_legend_toggle_standard` bietet sich an**
   (beide brauchen dieselbe Serien-Meta-Normalisierung).

## Bewusst NICHT

- Keine handgeschriebene Zweit-Tabelle je Chart (Drift-Klasse).
- Kein Ersatz für die kuratierten Sicht-Tabellen (`WerteTabelle` bleibt die
  reiche Tabellen-Sicht; die Chart-Tabelle ist die 1:1-Ablesung des Charts).
- V3-only-Charts (Flip-Donoren) bekommen nichts mehr.

## Offene Fragen (Gernot) — ✅ alle drei beantwortet (Abnahme 2026-07-18)

1. ~~Grundsatz-Entscheid: bauen — und wenn ja, **vor** dem Flip oder danach?~~
   → **Mechanik + Piloten vor Flip, Voll-Rollout danach** (CT-1…CT-3 ✅, CT-4 offen).
2. ~~Zugang nur im Fokus-Overlay oder zusätzlich Icon am Kartenkopf?~~
   → **nur im Fokus-Overlay** (Karten bleiben ruhig).
3. ~~Pilot-Auswahl ok?~~ → **ja**, genau diese drei.

> ~~Frage „kombinierter Sweep mit Legenden-Toggle"~~ ÜBERHOLT: Der LT-Sweep ist
> gebaut (`7302cc0b`) und hat die Serien-Meta bereits in ~20 Charts/15 Dateien
> normalisiert (`useLegendenToggle` + `ChartLegende`-Serien-Definitionen). Damit
> ist der Voll-Rollout deutlich billiger als bei Konzept-Erstellung geschätzt —
> die Tabelle speist sich aus genau dieser Meta.

## Aufwand (aktualisiert 2026-07-18, nach LT-Sweep)

Mechanik-SoT (`ChartDatenTabelle` + Fokus-Toggle) + 3 Piloten: mittel.
Voll-Rollout: pro Chart klein, da Serien-Meta durch den LT-Sweep weitgehend
normalisiert ist; Rest-Aufwand konzentriert sich auf Charts ohne `ChartLegende`
(Ausnahmen-Liste im LT-Konzept: Werteklassen-Legenden, AnteilDonut, WetterWidget).
