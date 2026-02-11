# EEDC Zielbild v0.9

**Stand:** 2026-02-06
**Status:** Entwurf zur Abstimmung

---

## Grundprinzipien

1. **Mehrere Investitionen pro Typ** - z.B. 2 Speicher, 3 Wechselrichter, n PV-Module
2. **Hierarchie: PV-Module → Wechselrichter** - für SOLL-IST Vergleich pro String
3. **Anlage-Monatsdaten = Summenfelder** - berechnet aus Investitions-Monatsdaten wo vorhanden
4. **Datenerfassung: CSV/manuell** - HA nur für Discovery, nicht für Monatsdaten
5. **PVGIS pro PV-Modul** - mit unterschiedlicher Ausrichtung/Neigung

---

## Datenmodell

```
┌─────────────────────────────────────────────────────────────────┐
│                           ANLAGE                                │
│  Stammdaten, Standort, Strompreise                             │
│  Monatsdaten (Summenfelder, berechnet wo Investitionsdaten da) │
└─────────────────────────────────────────────────────────────────┘
                               │
                               │ 1:n
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       INVESTITIONEN                             │
│  Typ: Wechselrichter, PV-Module, Speicher, E-Auto, Wallbox,    │
│       Wärmepumpe, Balkonkraftwerk, Sonstiges                   │
│  + Stammdaten (Bezeichnung, Kaufpreis, Datum)                  │
│  + Typ-spezifische Parameter (JSON)                            │
│  + parent_investition_id (PV-Module → Wechselrichter)          │
└─────────────────────────────────────────────────────────────────┘
                               │
                               │ 1:n
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                  INVESTITION-MONATSDATEN                        │
│  Jahr, Monat, verbrauch_daten (JSON)                           │
│  Typ-spezifische Felder je nach Investitionstyp                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Monatsdaten-Logik

### Anlage-Monatsdaten (Summenfelder)

| Feld | Quelle | Berechnung |
|------|--------|------------|
| pv_erzeugung_kwh | Manuell ODER Summe | Wenn PV-Module Monatsdaten: Summe, sonst manuell |
| einspeisung_kwh | Manuell | - |
| netzbezug_kwh | Manuell | - |
| batterie_ladung_kwh | Summe Speicher | Wenn Speicher Monatsdaten vorhanden |
| batterie_entladung_kwh | Summe Speicher | Wenn Speicher Monatsdaten vorhanden |
| direktverbrauch_kwh | Berechnet | pv_erzeugung - einspeisung |
| eigenverbrauch_kwh | Berechnet | direktverbrauch + batterie_entladung |
| gesamtverbrauch_kwh | Berechnet | netzbezug + eigenverbrauch |

### Investition-Monatsdaten (verbrauch_daten JSON)

**PV-Module (String):**
```json
{
  "pv_erzeugung_kwh": 450.5
}
```

**Speicher:**
```json
{
  "ladung_kwh": 200,
  "entladung_kwh": 185
}
```

**E-Auto:**
```json
{
  "km_gefahren": 1200,
  "verbrauch_kwh": 216,
  "ladung_pv_kwh": 130,
  "ladung_netz_kwh": 86,
  "ladung_extern_kwh": 50,
  "ladung_extern_euro": 25.50,
  "v2h_entladung_kwh": 25
}
```

**Wallbox:**
```json
{
  "ladung_kwh": 150.5,
  "ladevorgaenge": 10
}
```

**Wärmepumpe:**
```json
{
  "strom_kwh": 450,
  "heizung_kwh": 1800,
  "warmwasser_kwh": 200
}
```

**Balkonkraftwerk (All-in-One):**
```json
{
  "pv_erzeugung_kwh": 45.5,
  "speicher_ladung_kwh": 12.0,
  "speicher_entladung_kwh": 10.5
}
```

---

## Entfallende Komponenten

| Komponente | Grund |
|------------|-------|
| HA-Import Monatsdaten | Zu fehleranfällig (Long-Term Statistics, Entity-Zuordnung) |
| StringMonatsdaten-Tabelle | Ersetzt durch InvestitionMonatsdaten für PV-Module |
| ha_entity_id in Investition | Nicht mehr benötigt ohne HA-Import |
| Batterie-Felder direkt in Monatsdaten | Ersetzt durch Summe aus Speicher-Investitionen |

---

## Parent-Child Beziehung

### Hierarchie

```
Wechselrichter
  ├── PV-Module (Pflicht: jedes PV-Modul braucht einen Wechselrichter)
  └── Speicher (Optional: für Hybrid-Wechselrichter/DC-gekoppelt)

Eigenständig (kein Parent):
  - Balkonkraftwerk (All-in-One: Module + Micro-Inverter + opt. Speicher)
  - E-Auto
  - Wallbox
  - Wärmepumpe
  - Sonstiges
```

### Regeln

**PV-Module → Wechselrichter (Pflicht):**
- Jedes PV-Modul MUSS einem Wechselrichter zugeordnet sein
- Wechselrichter kann mehrere PV-Module haben
- UI zeigt Dropdown bei PV-Modul-Erstellung

**Speicher → Wechselrichter (Optional):**
- Hybrid-Wechselrichter: Speicher dem WR zuordnen
- AC-gekoppelte Speicher: Eigenständig (kein Parent)
- UI zeigt optionales Dropdown bei Speicher-Erstellung

**Balkonkraftwerk (Eigenständig):**
- All-in-One Typ für einfache Nutzer
- Hat eigene Monatsdaten (Erzeugung)
- Optional: Integrierter Speicher als Parameter
- Keine Child-Elemente, keine Parent-Zuordnung
- Wer Detailauswertung will → stattdessen PV-Module + Speicher anlegen

### Nutzen

- String-basierte Auswertungen (PV-Module pro Wechselrichter)
- PVGIS-Prognose pro String vs. IST-Ertrag
- Übersichtliche Darstellung im Dashboard
- Hybrid-WR Kontext für Speicher-Auswertungen

---

## PVGIS-Prognose

**Änderung:** Pro PV-Modul statt pro Anlage

| Vorher | Nachher |
|--------|---------|
| 1 Prognose pro Anlage | 1 Prognose pro PV-Modul |
| Nutzt Anlage-Koordinaten | Nutzt Anlage-Koordinaten + Modul-Ausrichtung |
| Keine String-Vergleiche | SOLL-IST pro String möglich |

**Anlage-Prognose:** Summe aller PV-Modul-Prognosen

---

## CSV-Import (erweitert)

### Basis-Spalten (Anlage)
```
Jahr, Monat, Einspeisung_kWh, Netzbezug_kWh, PV_Erzeugung_kWh
```

### PV-Module/Strings (wenn vorhanden)
```
String1_kWh, String2_kWh, String3_kWh, ...
```
Zuordnung: String1 = erstes PV-Modul nach ID sortiert

### Speicher (wenn vorhanden)
```
Speicher1_Ladung_kWh, Speicher1_Entladung_kWh
Speicher2_Ladung_kWh, Speicher2_Entladung_kWh
```

### E-Auto
```
EAuto_km, EAuto_Verbrauch_kWh, EAuto_Ladung_PV_kWh, EAuto_Ladung_Netz_kWh
EAuto_Ladung_Extern_kWh, EAuto_Ladung_Extern_Euro, EAuto_V2H_kWh
```

### Wallbox
```
Wallbox_Ladung_kWh, Wallbox_Ladevorgaenge
```

### Wärmepumpe
```
WP_Strom_kWh, WP_Heizung_kWh, WP_Warmwasser_kWh
```

---

## Migrationspfad v0.8 → v0.9

### Phase 1: Bereinigung
- [ ] HA-Import Monatsdaten aus UI entfernen
- [ ] HA-Import Route als deprecated markieren oder entfernen
- [ ] ha_entity_id Feld ungenutzt lassen (DB-Migration vermeiden)

### Phase 2: Parent-Child
- [ ] Validierung aktivieren: PV-Modul braucht Wechselrichter
- [ ] UI: Dropdown für Wechselrichter bei PV-Modul
- [ ] Bestehende PV-Module: Migration-Hinweis wenn kein Parent

### Phase 3: Monatsdaten-Logik
- [ ] Summenberechnung für Batterie-Felder implementieren
- [ ] pv_erzeugung aus PV-Modul-Summe wenn vorhanden
- [ ] CSV-Import für String-Spalten erweitern

### Phase 4: PVGIS
- [ ] PVGIS-Abruf pro PV-Modul ermöglichen
- [ ] Anlage-Prognose = Summe PV-Modul-Prognosen
- [ ] Dashboard: SOLL-IST Vergleich pro String

### Phase 5: Aufräumen
- [ ] StringMonatsdaten-Tabelle entfernen (DB-Migration)
- [ ] Batterie-Direktfelder in Monatsdaten deprecaten

---

## Entscheidungen

1. **CSV-Spalten für mehrere Investitionen gleichen Typs**
   - **Lösung:** Personalisierte CSV-Vorlage basierend auf angelegten Investitionen
   - Spaltenname = Investitions-Bezeichnung (z.B. `Speicher_Keller_Ladung_kWh`)
   - Export-Funktion generiert Vorlage mit allen Investitionen

2. **Rückwärtskompatibilität CSV**
   - **Nicht notwendig** - sauberer Schnitt mit v0.9
   - Alte CSVs müssen ggf. angepasst werden

---

## CSV-Vorlage (dynamisch generiert)

Beispiel für Anlage mit 2 PV-Modulen, 1 Speicher, 1 E-Auto:

```csv
Jahr;Monat;Einspeisung_kWh;Netzbezug_kWh;PV_Sued_kWh;PV_Ost_kWh;Speicher_Keller_Ladung_kWh;Speicher_Keller_Entladung_kWh;Tesla_km;Tesla_Verbrauch_kWh;Tesla_Ladung_PV_kWh;Tesla_Ladung_Netz_kWh;Tesla_Ladung_Extern_kWh;Tesla_Ladung_Extern_Euro
2025;1;150,5;200,3;450,2;180,5;95,0;88,5;1200;216;130;60;26;15,50
```

**Spalten-Generierung:**
- Basis: `Jahr`, `Monat`, `Einspeisung_kWh`, `Netzbezug_kWh`
- Pro PV-Modul: `{Bezeichnung}_kWh`
- Pro Speicher: `{Bezeichnung}_Ladung_kWh`, `{Bezeichnung}_Entladung_kWh`
- Pro E-Auto: `{Bezeichnung}_km`, `{Bezeichnung}_Verbrauch_kWh`, `{Bezeichnung}_Ladung_PV_kWh`, `{Bezeichnung}_Ladung_Netz_kWh`, `{Bezeichnung}_Ladung_Extern_kWh`, `{Bezeichnung}_Ladung_Extern_Euro`
- Pro Wallbox: `{Bezeichnung}_Ladung_kWh`, `{Bezeichnung}_Ladevorgaenge`
- Pro Wärmepumpe: `{Bezeichnung}_Strom_kWh`, `{Bezeichnung}_Heizung_kWh`, `{Bezeichnung}_Warmwasser_kWh`
- Pro Balkonkraftwerk: `{Bezeichnung}_kWh`, `{Bezeichnung}_Speicher_Ladung_kWh`, `{Bezeichnung}_Speicher_Entladung_kWh`

---

*Erstellt: 2026-02-06*
