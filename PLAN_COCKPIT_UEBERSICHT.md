# Plan: Cockpit Übersicht - Vollständige Investitionsaggregation

## Zielsetzung

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
