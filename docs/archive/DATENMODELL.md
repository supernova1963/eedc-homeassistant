# EEDC Datenmodell-Analyse

**Stand:** 2026-02-06
**Analyse-Grund:** Umfangreiche Änderungen für HA-Integration in v0.8.x

---

## Übersicht der Datentabellen

### 1. Monatsdaten (Kern-Tabelle)
**Datei:** `backend/models/monatsdaten.py`

Speichert die aggregierten monatlichen Energie-Messwerte einer Anlage.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| einspeisung_kwh | float | Ins Netz eingespeist |
| netzbezug_kwh | float | Aus dem Netz bezogen |
| pv_erzeugung_kwh | float? | Gesamte PV-Erzeugung |
| direktverbrauch_kwh | float? | Berechnet |
| eigenverbrauch_kwh | float? | Berechnet |
| gesamtverbrauch_kwh | float? | Berechnet |
| batterie_ladung_kwh | float? | Speicher-Ladung |
| batterie_entladung_kwh | float? | Speicher-Entladung |
| batterie_ladung_netz_kwh | float? | Arbitrage |
| batterie_ladepreis_cent | float? | Arbitrage |
| globalstrahlung_kwh_m2 | float? | Wetterdaten |
| sonnenstunden | float? | Wetterdaten |
| datenquelle | string? | manual, csv, ha_import |

**Befüllung:** CSV-Import, HA-Import, manuelle Eingabe

---

### 2. InvestitionMonatsdaten (Typ-spezifisch)
**Datei:** `backend/models/investition.py` (Klasse InvestitionMonatsdaten)

Speichert monatliche Messwerte pro Investition als JSON.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| investition_id | FK | Verknüpfung zur Investition |
| jahr, monat | int | Zeitraum |
| verbrauch_daten | JSON | Typ-spezifische Daten |
| einsparung_monat_euro | float? | Berechnet |
| co2_einsparung_kg | float? | Berechnet |

**verbrauch_daten Struktur je nach Typ:**

```json
// E-Auto
{
  "km_gefahren": 1200,
  "verbrauch_kwh": 216,
  "ladung_pv_kwh": 130,
  "ladung_netz_kwh": 86,
  "v2h_entladung_kwh": 25,
  "ladevorgaenge": 12
}

// Wallbox
{
  "ladung_kwh": 150.5,
  "ladevorgaenge": 10
}

// Speicher
{
  "ladung_kwh": 200,
  "entladung_kwh": 185
}

// Wärmepumpe
{
  "strom_kwh": 450,
  "heizung_kwh": 1800,
  "warmwasser_kwh": 200
}
```

**Befüllung:** CSV-Import (seit v0.8.1)

---

### 3. StringMonatsdaten (PV-Modul-Erträge)
**Datei:** `backend/models/string_monatsdaten.py`

Speichert monatliche PV-Erträge pro String/MPPT für SOLL-IST Vergleich.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| investition_id | FK | Verknüpfung zum PV-Modul |
| jahr, monat | int | Zeitraum |
| pv_erzeugung_kwh | float | IST-Ertrag dieses Strings |

**Befüllung:** NICHT IMPLEMENTIERT (weder CSV noch HA)

---

### 4. PVGISPrognose & PVGISMonatsprognose
**Datei:** `backend/models/pvgis_prognose.py`

Speichert PVGIS-Ertragsprognosen auf Anlage-Ebene.

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| anlage_id | FK | Verknüpfung zur Anlage |
| latitude, longitude | float | Standort |
| neigung_grad | float | Modulneigung |
| ausrichtung_grad | float | Azimut (0=Süd) |
| jahresertrag_kwh | float | Prognostizierter Ertrag |
| monatswerte | JSON | Monatliche Prognose |

**Hinweis:** Prognose basiert auf Anlage-Daten, nicht auf einzelnen PV-Modulen.

---

## Identifizierte Inkonsistenzen

### 1. Parent-Child Beziehung (PV-Module → Wechselrichter)

**Ist-Zustand:**
- `parent_investition_id` Feld existiert in Investition
- Relationship `parent` und `children` definiert
- Wird NICHT validiert oder im UI genutzt

**Soll-Zustand:**
- PV-Module sollten einem Wechselrichter zugeordnet werden können
- Ermöglicht String-basierte Auswertungen
- UI sollte Zuordnung anbieten

**Empfehlung:** Entweder vollständig implementieren oder Feld entfernen.

---

### 2. Speicher-Daten Duplizierung

**Problem:**
- `batterie_ladung_kwh`, `batterie_entladung_kwh` in **Monatsdaten**
- `ladung_kwh`, `entladung_kwh` in **InvestitionMonatsdaten** (Speicher)

**CSV-Import aktuell:**
- Schreibt in BEIDE Tabellen (redundant)

**Empfehlung:**
- Entscheidung: Eine Quelle der Wahrheit festlegen
- Option A: Nur Monatsdaten (einfacher, Anlage-Aggregat)
- Option B: Nur InvestitionMonatsdaten (konsistent mit anderen Investitionen)
- Dashboards und Auswertungen entsprechend anpassen

---

### 3. Fehlende CSV-Spalten für E-Auto

**Aktuell unterstützt:**
```
EAuto_km, EAuto_Verbrauch_kWh, EAuto_Ladung_PV_kWh, EAuto_Ladung_Netz_kWh
```

**Fehlend laut InvestitionMonatsdaten-Schema:**
```
EAuto_Ladung_Extern_kWh    - Laden an öffentlichen Ladestationen
EAuto_Ladung_Extern_Euro   - Kosten für externes Laden
EAuto_V2H_Entladung_kWh    - Vehicle-to-Home Rückspeisung
```

**Empfehlung:** CSV-Spalten erweitern.

---

### 4. Parameter-Key Inkonsistenz (Wärmepumpe)

**Im Code (`import_export.py`):**
```python
"strom_kwh": wp_strom,
"heizung_kwh": wp_heizung,
"warmwasser_kwh": wp_warmwasser
```

**In Investition.parameter (Beispiel):**
```python
{
    "cop_durchschnitt": 3.5,
    "gas_kwh_preis_cent": 8,  # ← Inkonsistent
    "heizlast_kw": 12
}
```

**Empfehlung:** Parameter-Schema pro Typ dokumentieren und validieren.

---

### 5. StringMonatsdaten nicht befüllt

**Zweck:** SOLL-IST Vergleich pro PV-Modul/String

**Problem:**
- CSV-Import schreibt nicht in diese Tabelle
- HA-Import nutzt diese Tabelle nicht
- `ha_entity_id` in Investition ist vorbereitet, aber ungenutzt

**Empfehlung:**
- Kurzfristig: Als "nicht implementiert" dokumentieren
- Langfristig: HA-Import für String-Sensoren erweitern

---

### 6. PVGIS ohne PV-Modul-Zuordnung

**Ist-Zustand:**
- PVGIS-Prognose wird auf Anlage-Ebene abgerufen
- Nutzt `anlage.neigung_grad`, `anlage.ausrichtung`

**Problem:**
- PV-Module können unterschiedliche Ausrichtungen/Neigungen haben
- Prognose berücksichtigt dies nicht

**Empfehlung:**
- Design-Entscheidung: Ist Anlage-Level-Prognose ausreichend?
- Alternative: Pro PV-Modul PVGIS abrufen und summieren

---

## CSV Import-Mapping (v0.8.1)

| CSV-Spalte | Ziel-Tabelle | Ziel-Feld |
|------------|--------------|-----------|
| Jahr | Monatsdaten | jahr |
| Monat | Monatsdaten | monat |
| Einspeisung_kWh | Monatsdaten | einspeisung_kwh |
| Netzbezug_kWh | Monatsdaten | netzbezug_kwh |
| PV_Erzeugung_kWh | Monatsdaten | pv_erzeugung_kwh |
| Batterie_Ladung_kWh | Monatsdaten | batterie_ladung_kwh |
| Batterie_Entladung_kWh | Monatsdaten | batterie_entladung_kwh |
| Globalstrahlung_kWh_m2 | Monatsdaten | globalstrahlung_kwh_m2 |
| Sonnenstunden | Monatsdaten | sonnenstunden |
| Notizen | Monatsdaten | notizen |
| **Berechnete Felder** | | |
| (auto) | Monatsdaten | direktverbrauch_kwh |
| (auto) | Monatsdaten | eigenverbrauch_kwh |
| (auto) | Monatsdaten | gesamtverbrauch_kwh |
| **E-Auto** | | |
| EAuto_km | InvestitionMonatsdaten | verbrauch_daten.km_gefahren |
| EAuto_Verbrauch_kWh | InvestitionMonatsdaten | verbrauch_daten.verbrauch_kwh |
| EAuto_Ladung_PV_kWh | InvestitionMonatsdaten | verbrauch_daten.ladung_pv_kwh |
| EAuto_Ladung_Netz_kWh | InvestitionMonatsdaten | verbrauch_daten.ladung_netz_kwh |
| **Wallbox** | | |
| Wallbox_Ladung_kWh | InvestitionMonatsdaten | verbrauch_daten.ladung_kwh |
| Wallbox_Ladevorgaenge | InvestitionMonatsdaten | verbrauch_daten.ladevorgaenge |
| **Speicher** | | |
| Batterie_Ladung_kWh | InvestitionMonatsdaten | verbrauch_daten.ladung_kwh |
| Batterie_Entladung_kWh | InvestitionMonatsdaten | verbrauch_daten.entladung_kwh |
| **Wärmepumpe** | | |
| WP_Strom_kWh | InvestitionMonatsdaten | verbrauch_daten.strom_kwh |
| WP_Heizung_kWh | InvestitionMonatsdaten | verbrauch_daten.heizung_kwh |
| WP_Warmwasser_kWh | InvestitionMonatsdaten | verbrauch_daten.warmwasser_kwh |

---

## Priorisierte Empfehlungen

### Kritisch (Kurzfristig)

1. **CSV E-Auto Spalten erweitern**
   - Hinzufügen: `EAuto_Ladung_Extern_kWh`, `EAuto_V2H_Entladung_kWh`
   - Aufwand: Gering (~30 Zeilen Code)

2. **Parameter-Schema dokumentieren**
   - JSON-Schema pro Investitionstyp definieren
   - Validierung in API einbauen

### Wichtig (Mittelfristig)

3. **Speicher-Daten konsolidieren**
   - Entscheidung treffen: Monatsdaten ODER InvestitionMonatsdaten
   - Dashboards/Auswertungen anpassen

4. **StringMonatsdaten aktivieren**
   - CSV-Import erweitern (neue Spalten: String1_kWh, String2_kWh, ...)
   - Oder: Als v2.0 Feature markieren

### Nice-to-Have (Langfristig)

5. **Parent-Child implementieren**
   - UI für PV-Modul → Wechselrichter Zuordnung
   - Validierung: Child kann nicht ohne Parent existieren

6. **PVGIS pro PV-Modul**
   - Separate Prognose pro PV-Modul mit unterschiedlicher Ausrichtung
   - Summierung für Gesamtprognose

---

*Erstellt: 2026-02-06*
