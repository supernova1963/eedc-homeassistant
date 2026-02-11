# Plan: Cockpit & Auswertungen - Strukturierung

## Grundlegende Abgrenzung

### Cockpit vs. Auswertungen

| Dimension | **Cockpit** | **Auswertungen** |
|-----------|-------------|------------------|
| **Fokus** | Status & Gesamt-KPIs | Trends, Vergleiche, Details |
| **Zeitbezug** | Kumulierte Werte (Lifetime, YTD) | Zeitreihen (Monat/Jahr) |
| **Interaktion** | Lesen/Überwachen (passiv) | Erkunden/Analysieren (aktiv) |
| **Use-Case** | "Wie steht meine Anlage?" (30 Sek.) | "Warum? Was optimieren?" (10+ Min.) |
| **Charts** | Kompakte Donuts/Gauges | Vollständige Zeitreihen |
| **Daten** | Nur Anzeige | + Download (CSV/JSON/Excel) |

### Leitfragen

- **Cockpit**: "Wo stehe ich?" → Aggregierte Lifetime-Werte, schnelle Orientierung
- **Auswertungen**: "Wie entwickelt sich was?" → Zeitreihen, Drill-down, Export

---

## Cockpit-Struktur

### Tabs
| Tab | Inhalt |
|-----|--------|
| **Übersicht** | Aggregierte KPIs aller Komponenten (siehe unten) |
| **PV-Anlage** | WR + Module + DC-Speicher, String-Vergleich |
| **E-Auto** | Ladung, km, PV-Anteil, V2H |
| **Wärmepumpe** | COP, Wärme, Stromverbrauch |
| **Speicher** | Zyklen, Effizienz, Ladung/Entladung |
| **Wallbox** | Ladevorgänge, PV-Anteil |
| **Balkonkraftwerk** | Erzeugung, Eigenverbrauch |
| **Sonstiges** | Flexible Kategorien |

---

## Auswertungen-Struktur

### Tabs
| Tab | Inhalt | Datenexport |
|-----|--------|-------------|
| **Jahresvergleich** | Mehrjahres-Charts, Δ%-Indikatoren, Monatstabelle | CSV/Excel |
| **ROI-Analyse** | Amortisation, Payback, Komponenten-ROI | CSV/Excel |
| **Prognose vs. IST** | PVGIS-Prognose vs. reale Erzeugung pro String | CSV/Excel |
| **Nachhaltigkeit** | CO₂-Bilanz, Autarkie-Entwicklung, Umwelt-Impact | CSV/Excel |
| **KI-Insights** | Optimierungsvorschläge, Anomalie-Erkennung | - |

### Jahresvergleich (existiert)
- Monats-Balkendiagramme (Erzeugung, Verbrauch, Autarkie)
- Jahr-über-Jahr Δ%-Indikatoren
- Jahres-Summentabelle mit Export

### ROI-Analyse (existiert)
- Amortisationskurve pro Komponente
- Aggregierte PV-System-ROI
- Break-Even-Prognose
- Kosten nach Kategorie

### Prognose vs. IST (neu)
- PVGIS-Prognosewerte (falls hinterlegt)
- Reale Monatswerte im Vergleich
- Abweichungs-Heatmap pro String/Monat
- Performance-Ratio Berechnung

### Nachhaltigkeit (neu)
- CO₂-Einsparung kumuliert über Zeit
- Autarkie-Entwicklung als Zeitreihe
- Äquivalente (Bäume, km Auto, etc.)
- Umwelt-Zertifikat zum Download

### KI-Insights (Roadmap)
- Anomalie-Erkennung (ungewöhnliche Verbräuche)
- Optimierungsvorschläge (Lastverschiebung)
- Prognose nächster Monat
- Vergleich mit ähnlichen Anlagen (anonymisiert)

---

## PDF-Export (Querschnittsfunktion)

PDF-Export ist **kein eigener Tab**, sondern eine Funktion auf relevanten Seiten.

### Strategie (Priorisiert)

| Priorität | Ansatz | Aufwand | Beschreibung |
|-----------|--------|---------|--------------|
| **1. Kurzfristig** | Print-Styles | Gering | CSS `@media print` für alle Seiten |
| **2. Mittelfristig** | Button pro Seite | Mittel | "Als PDF exportieren" auf ROI, Jahresvergleich |
| **3. Optional** | Jahresbericht | Hoch | Generator nur wenn User-Bedarf besteht |

### Print-Styles (Sofort umsetzbar)
- Gute `@media print` CSS-Regeln
- User nutzt Browser Strg+P → "Als PDF speichern"
- Kein zusätzlicher Code nötig
- Funktioniert auf allen Seiten

### PDF-Button (Bei Bedarf)
- Nur auf Seiten wo sinnvoll: ROI-Analyse, Jahresvergleich, Cockpit-Übersicht
- Bibliothek: `html2pdf.js` oder `jspdf` + `html2canvas`
- Exportiert aktuell sichtbare Ansicht inkl. Charts

### Jahresbericht-Generator (Optional/Roadmap)
- Nur implementieren wenn echter User-Bedarf
- Problem: Muss bei jeder Änderung mitgepflegt werden
- Alternative: Gute Print-Styles + Anleitung für User

---

## Cockpit Übersicht - Detail-Design

### Zielsetzung

Die **Übersicht** im Cockpit soll eine **vollständige Zusammenfassung aller Investitionen** bieten - auf einen Blick alle wichtigen KPIs aggregiert.

Die **Detail-Dashboards** (PV-Anlage, Speicher, Wärmepumpe, etc.) zeigen dann die investitionsspezifischen Details mit Charts und Tabellen.

---

## Neue Struktur: Dashboard.tsx (Übersicht)

### Sektion 1: Energie-Bilanz
**4 KPIs im Grid - Energiefluss des Gesamtsystems**

| KPI | Wert | Formel | Icon |
|-----|------|--------|------|
| **PV-Erzeugung** | X.X MWh | Σ PV-Module + Balkonkraftwerke | Sun |
| **Gesamtverbrauch** | X.X MWh | Eigenverbrauch + Netzbezug | Home |
| **Netzbezug** | X.X MWh | Σ Netzbezug | ArrowDownToLine |
| **Einspeisung** | X.X MWh | Σ Einspeisung | ArrowUpFromLine |

### Sektion 2: Effizienz-Quoten
**4 KPIs im Grid - Wie effizient ist das System?**

| KPI | Wert | Formel | Bedeutung |
|-----|------|--------|-----------|
| **Autarkie** | XX % | Eigenverbrauch ÷ Gesamtverbrauch × 100 | Unabhängigkeit vom Netz |
| **Eigenverbrauchsquote** | XX % | Eigenverbrauch ÷ Erzeugung × 100 | Wie viel PV selbst genutzt? |
| **Direktverbrauchsquote** | XX % | Direktverbrauch ÷ Erzeugung × 100 | Ohne Speicher-Umweg |
| **Spez. Ertrag** | XXX kWh/kWp | Erzeugung ÷ Anlagenleistung | Anlageneffizienz |

### Sektion 3: Speicher (aggregiert)
**4 KPIs - Alle Speicher zusammen (AC + DC)**

| KPI | Wert | Formel |
|-----|------|--------|
| **Ladung gesamt** | X.X MWh | Σ aller Speicher |
| **Entladung gesamt** | X.X MWh | Σ aller Speicher |
| **Ø Effizienz** | XX % | Entladung ÷ Ladung × 100 |
| **Vollzyklen** | XXX | Σ Ladung ÷ Σ Kapazität |

*Klickbar → navigiert zu /cockpit/speicher*

### Sektion 4: Wärmepumpe (aggregiert)
**4 KPIs - Alle Wärmepumpen zusammen**

| KPI | Wert | Formel |
|-----|------|--------|
| **Wärme erzeugt** | X.X MWh | Σ Heizung + Warmwasser |
| **Strom verbraucht** | X.X MWh | Σ WP-Stromverbrauch |
| **Ø COP** | X.X | Wärme ÷ Strom |
| **Ersparnis vs. Gas** | XXX € | (Wärme ÷ 0.9 × Gaspreis) - Stromkosten |

*Klickbar → navigiert zu /cockpit/waermepumpe*

### Sektion 5: E-Mobilität (E-Auto + Wallbox aggregiert)
**4 KPIs - Alle E-Autos und Wallboxen**

| KPI | Wert | Formel |
|-----|------|--------|
| **Gefahrene km** | X.XXX km | Σ aller E-Autos |
| **Ladung gesamt** | X.X MWh | Heim + Extern |
| **PV-Anteil** | XX % | PV-Ladung ÷ Heimladung × 100 |
| **Ersparnis vs. Benzin** | XXX € | Benzinkosten - Stromkosten |

*Klickbar → navigiert zu /cockpit/e-auto*

### Sektion 6: Finanzen (Gesamtbilanz)
**4 KPIs - Wirtschaftlichkeit**

| KPI | Wert | Formel |
|-----|------|--------|
| **Einspeiseerlös** | XXX € | Einspeisung × Vergütung |
| **EV-Ersparnis** | X.XXX € | Eigenverbrauch × Strompreis |
| **Netto-Ertrag** | X.XXX € | Erlös + Ersparnis |
| **ROI-Fortschritt** | XX % | Kum. Ersparnis ÷ Investition × 100 |

### Sektion 7: Umwelt (CO₂-Bilanz)
**4 KPIs - Umweltbeitrag**

| KPI | Wert | Formel |
|-----|------|--------|
| **CO₂ PV** | X.XXX kg | Eigenverbrauch × 0.4 kg/kWh |
| **CO₂ Wärmepumpe** | XXX kg | vs. Gas-Heizung |
| **CO₂ E-Auto** | XXX kg | vs. Benziner |
| **CO₂ gesamt** | X.XXX kg | Σ aller Einsparungen |

---

## Backend: Neuer Endpoint

### GET /api/cockpit/uebersicht/{anlage_id}

```python
class CockpitUebersichtResponse(BaseModel):
    # Energie-Bilanz
    pv_erzeugung_kwh: float
    gesamtverbrauch_kwh: float
    netzbezug_kwh: float
    einspeisung_kwh: float
    direktverbrauch_kwh: float
    eigenverbrauch_kwh: float

    # Quoten
    autarkie_prozent: float
    eigenverbrauch_quote_prozent: float
    direktverbrauch_quote_prozent: float
    spezifischer_ertrag_kwh_kwp: float
    anlagenleistung_kwp: float

    # Speicher (aggregiert)
    speicher_ladung_kwh: float
    speicher_entladung_kwh: float
    speicher_effizienz_prozent: float
    speicher_vollzyklen: float
    speicher_kapazitaet_kwh: float
    hat_speicher: bool

    # Wärmepumpe (aggregiert)
    wp_waerme_kwh: float
    wp_strom_kwh: float
    wp_cop: float
    wp_ersparnis_euro: float
    hat_waermepumpe: bool

    # E-Mobilität (aggregiert)
    emob_km: float
    emob_ladung_kwh: float
    emob_pv_anteil_prozent: float
    emob_ersparnis_euro: float
    hat_emobilitaet: bool

    # Balkonkraftwerk (aggregiert)
    bkw_erzeugung_kwh: float
    bkw_eigenverbrauch_kwh: float
    hat_balkonkraftwerk: bool

    # Finanzen
    einspeise_erloes_euro: float
    ev_ersparnis_euro: float
    netto_ertrag_euro: float
    roi_fortschritt_prozent: float
    investition_gesamt_euro: float

    # Umwelt
    co2_pv_kg: float
    co2_wp_kg: float
    co2_emob_kg: float
    co2_gesamt_kg: float

    # Meta
    anzahl_monate: int
    zeitraum_von: str
    zeitraum_bis: str
```

---

## Frontend: Neue Dashboard.tsx Struktur

```tsx
// Sektionen als eigene Komponenten
<div className="space-y-6">
  <EnergieSection data={data} />
  <QuotenSection data={data} />

  {data.hat_speicher && (
    <SpeicherSection data={data} onClick={() => navigate('/cockpit/speicher')} />
  )}

  {data.hat_waermepumpe && (
    <WaermepumpeSection data={data} onClick={() => navigate('/cockpit/waermepumpe')} />
  )}

  {data.hat_emobilitaet && (
    <EmobilitaetSection data={data} onClick={() => navigate('/cockpit/e-auto')} />
  )}

  <FinanzenSection data={data} />
  <UmweltSection data={data} />
</div>
```

---

## Was wird entfernt/geändert

### Dashboard.tsx (aktuell)
- ❌ Einzelne Komponenten-Kacheln (werden zu Sektionen)
- ❌ Monatschart (gehört in PV-Anlage Detail)
- ❌ Redundante PV-Erzeugung KPI (nun in Energie-Bilanz)

### PVAnlageDashboard.tsx
- ❌ Eigenverbrauchsquote KPI (nun in Übersicht)
- ✓ Behält: Anlagenleistung, Erzeugung, Spez. Ertrag, Monatschart, String-Vergleich

### Detail-Dashboards (Speicher, WP, E-Auto, etc.)
- ✓ Bleiben unverändert - zeigen investitionsspezifische Details
- ✓ Werden von Übersicht verlinkt

---

## Implementierungsreihenfolge

1. **Backend:** Neuer Endpoint `/api/cockpit/uebersicht/{anlage_id}`
2. **Frontend API:** Neuer API-Call `cockpitApi.getUebersicht()`
3. **Frontend:** Dashboard.tsx komplett neu strukturieren
4. **Frontend:** PVAnlageDashboard.tsx anpassen (EV-Quote entfernen)
5. **Test:** Alle Sektionen mit Demo-Daten prüfen
6. **Dokumentation:** CLAUDE.md + CHANGELOG.md aktualisieren

---

## Zeitraum-Filter

Die Übersicht soll einen **Jahr-Filter** haben (wie ROI-Dashboard):
- "Alle Jahre" (default)
- "2024"
- "2025"
- etc.

Alle aggregierten Werte werden dann für den gewählten Zeitraum berechnet.

---

## Implementierungsreihenfolge (Gesamt)

### Phase 1: Cockpit Übersicht (Priorität hoch)
1. Backend: `/api/cockpit/uebersicht/{anlage_id}`
2. Frontend: Dashboard.tsx Redesign
3. Navigation: Klick-Navigation zu Detail-Dashboards

### Phase 2: Auswertungen Basis (Priorität hoch)
4. Jahresvergleich: Datenexport-Buttons (CSV/Excel)
5. ROI-Analyse: Datenexport-Buttons

### Phase 3: Auswertungen Erweiterung (Priorität mittel)
6. Prognose vs. IST Tab (PVGIS-Vergleich)
7. Nachhaltigkeit Tab (CO₂-Zeitreihe)

### Phase 4: Advanced Features (Priorität niedrig)
8. KI-Insights (Roadmap)

---

## Zusammenfassung

```
┌─────────────────────────────────────────────────────────────┐
│                        eedc                                 │
├─────────────────────────┬───────────────────────────────────┤
│       COCKPIT           │         AUSWERTUNGEN              │
│  "Wo stehe ich?"        │  "Wie entwickelt sich was?"       │
├─────────────────────────┼───────────────────────────────────┤
│ • Aggregierte KPIs      │ • Zeitreihen-Charts               │
│ • Lifetime-Werte        │ • Jahr-für-Jahr Vergleiche        │
│ • Schnelle Orientierung │ • Drill-down & Filter             │
│ • Komponenten-Status    │ • Datenexport (CSV/Excel)         │
│ • Klick → Detail        │ • ROI-Analysen                    │
│                         │ • Prognose vs. IST                │
│                         │ • Nachhaltigkeit                  │
│                         │ • KI-Insights (Roadmap)           │
└─────────────────────────┴───────────────────────────────────┘
```
