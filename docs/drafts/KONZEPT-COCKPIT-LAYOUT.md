# Konzept: Auf-/Zuklappen + Sortierung in allen Cockpit-Seiten

**Status:** Draft — Umsetzungsplan für Issue #175 (detLAN: Auf-/Zuklappen + Sortierung in andere Ansichten)
**Datum:** 2026-04-30
**Auslöser:** detLAN möchte das Auf-/Zuklappen + Sortier-Feature aus *Monatsberichte* auch in den anderen Cockpits (PV / Speicher / Wärmepumpe / Wallbox / E-Auto / Balkonkraftwerk / Sonstiges).

## Bestandsaufnahme

| Cockpit | Sektionen heute | Wrapper | Sortier/Collapse? | Schema |
|---|---|---|---|---|
| **MonatsabschlussView** ✅ Vorbild | 8 sortierbare Akkordeon-Sektionen (Energie / Finanzen / Community / Speicher / WP / E-Mob / BKW / Sonstiges) | Card-Akkordeon mit ↑↓ | **JA** (localStorage `monatsberichte_section_order`) | hochhomogen |
| **Dashboard (Cockpit-Übersicht)** | 6–9 Sektionen (Bilanz / Quoten / Speicher / WP / E-Mob / Finanzen / CO₂ / Quick-Links) | `<Section icon title>` | Collapse: nein. Sortierung: nein | hochhomogen — niedriger Migrations-Aufwand |
| **PVAnlageDashboard** | 4 Bereiche (KPIs / Komponenten / Jahresübersicht / Energieverteilung) | Card-Wrapper | Nein | homogen |
| **SpeicherDashboard** | KPIs / Summary-Cards / [Optional Arbitrage] / Charts / Details | Card + farbige Boxen | Nein | mittel-heterogen |
| **WaermepumpeDashboard** | KPIs / [Optional JAZ] / Charts Row 1 + Row 2 / Monatsvergleich / CO₂ / Details | Card + KPI-Grids | Nein | mittel-heterogen |
| **WallboxDashboard** | [Optional Status] / KPIs / Charts / Erklärbox / [Optional Kosten] | Card + farbige Boxen | Nein | mittel-heterogen |
| **EAutoDashboard** | KPIs / Charts Row 1 + Row 2 / [Optional V2H] / Details | Card | Nein | homogen |
| **BalkonkraftwerkDashboard** | KPIs / Summary / Charts / [Optional Speicher] / CO₂ / Details | Card | Nein | homogen |
| **SonstigesDashboard** | 3 Sub-Layouts (Erzeuger / Verbraucher / Speicher) | Card, dreifach verzweigt | Nein | hochheterogen — schwer zu vereinheitlichen |
| **ROIDashboard** | Parameter / KPIs / Amortisation+Pie / Vergleich / Detail-Tabelle | Card durchgehend | Nein | homogen |
| **LiveDashboard** | EnergieFluss / Sidebar / Wetter / Tagesverlauf / Community-Nudge | Loose `<div>`-Grid | Nein | heterogen — nicht migrationsfähig |

**Bestehende Bausteine in `components/ui/`:** `Card.tsx`, `CollapsibleSection.tsx` (Collapse, ohne Sortierung). **Fehlt:** `SortableSection.tsx`.

## Vorgehen — SortableSection extrahieren + ausrollen

**Was:** Akkordeon-Komponente aus `MonatsabschlussView.tsx:90-238` als `components/ui/SortableSection.tsx` extrahieren, plus Helper `OrderedSections` für Reorder-Orchestrierung. Pro Cockpit ein Mini-Cut: bestehende Sektionen in `<SortableSection sectionId>` wickeln, optionale Blöcke (`if (hat_speicher) {…}`) als Sortable Section sichtbar machen, localStorage-Key pro Cockpit.

**API-Skizze** (aus MonatsabschlussView):
```tsx
<SortableSection icon={Sun} title="Energie" summary="…" sectionId="energie" color="text-amber-500">
  {…}
</SortableSection>
```

Zustand & Persistenz:
```ts
const [order, setOrder] = useSectionOrder('pv-cockpit', DEFAULT_PV_ORDER)
<OrderedSections order={order} onMove={(id, dir) => setOrder(reorder(order, id, dir))}>…</OrderedSections>
```

**Aufwand:**
- Extraktion: ~30 min (Copy-Paste + Typen)
- Pro Cockpit: 20–45 min (Block-zu-Section refactor)
- Gesamt für die 5 detLAN-Wünsche (PV/Speicher/WP/Wallbox/E-Auto): ~2½–3½ h, plus Dashboard-Cockpit-Übersicht (homogen, klein)
- BKW + Sonstiges: 1–2 h zusätzlich (Sonstiges erfordert wegen 3 Sub-Layouts mehr Aufmerksamkeit)
- LiveDashboard nicht migrieren (loses Grid-Layout, erzwingt strukturellen Refactor)

## Hybrid-Schritt­plan

**Heute (erster Stand für detLAN):**
1. SortableSection + OrderedSections + useSectionOrder-Hook extrahieren
2. MonatsabschlussView refactor auf die neuen Komponenten (Verhalten unverändert)
3. Ausrollen in **Dashboard (Cockpit-Übersicht)** und **Wärmepumpe-Cockpit** — ein homogenes + ein heterogenes Cockpit als Probe
4. Aufwand: ~1½ h

**Nach detLAN-Feedback:**
5. PV / Speicher / Wallbox / E-Auto / BKW (je nach Rückmeldung) — ~3 h
6. Sonstiges + LiveDashboard bewusst ausgeschlossen

## Offene Fragen

1. **Sonstiges-Cockpit:** trotz heterogener Sub-Layouts mit migrieren? (Vorschlag: nein — zu viel Refactor-Aufwand für ein Cockpit, das nicht im detLAN-Wunsch steht.)
2. **Persistenz pro Anlage vs. pro Browser:** Bisher localStorage (pro Browser). Sollen Sortierungen mit dem Backup-Export wandern? (Vorschlag: nein im ersten Schritt — konsistent mit Monatsberichte.)
3. **Reset-Button pro Cockpit:** „Sortierung zurücksetzen" oben rechts? (Vorschlag: ja, einheitlich. Aufwand: trivial.)
4. **Drag-and-Drop statt ↑↓-Buttons:** Mit dnd-kit nachrüsten? (Vorschlag: erst nach detLAN-Feedback — heute reichen die Buttons, sind Mobile-tauglich.)

## Nicht-Ziele

- Cross-Cockpit-Sortierung (z.B. Speicher-Sektion in PV-Cockpit zeigen)
- LiveDashboard-Migration — strukturelle Andersartigkeit
