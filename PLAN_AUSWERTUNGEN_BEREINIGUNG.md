# Plan: Bereinigung und Erweiterung der Auswertungen

## Problemanalyse

### Aktueller Zustand (Chaos)

**Zwei Datenquellen werden vermischt:**

1. **`Monatsdaten`** (Anlagen-Ebene)
   - Nur 3 Kern-Messwerte: `einspeisung_kwh`, `netzbezug_kwh`, `pv_erzeugung_kwh`
   - `batterie_ladung_kwh`, `batterie_entladung_kwh` - **REDUNDANT** (Summen aus Speicher-Investitionen)
   - Berechnete Felder: `direktverbrauch`, `eigenverbrauch`, `gesamtverbrauch`
   - Sollte NUR für Anlagen-Energiebilanz genutzt werden

2. **`InvestitionMonatsdaten`** (Komponenten-Ebene)
   - **ALLE** komponentenspezifischen Daten gehören hierhin
   - Speicher: `ladung_kwh`, `entladung_kwh`, `speicher_ladung_netz_kwh` (Arbitrage)
   - E-Auto: `km_gefahren`, `verbrauch_kwh`, `ladung_pv_kwh`, `ladung_netz_kwh`, `ladung_extern_kwh`, `v2h_entladung_kwh`
   - Wärmepumpe: `stromverbrauch_kwh`, `heizenergie_kwh`, `warmwasser_kwh`
   - PV-Module: `pv_erzeugung_kwh` (pro String!)
   - Balkonkraftwerk: `pv_erzeugung_kwh`, `speicher_ladung_kwh`, `speicher_entladung_kwh`
   - Sonstiges: `erzeugung_kwh`, `verbrauch_sonstig_kwh`
   - Alle: `sonderkosten_euro`, `sonderkosten_notiz`

### ~~Fehlerhafte Nutzung in aktuellen Endpoints~~ ✅ BEHOBEN

| Endpoint | ~~Problem~~ Status |
|----------|---------|
| `get_cockpit_uebersicht` | ✅ Korrigiert - nutzt jetzt InvestitionMonatsdaten |
| `get_nachhaltigkeit` | ✅ Korrigiert - iteriert über InvestitionMonatsdaten |
| `get_komponenten_zeitreihe` | ✅ Korrigiert - nutzt nur noch InvestitionMonatsdaten |

### ~~Fehlende~~ Jetzt verfügbare Auswertungsmöglichkeiten ✅

Die InvestitionMonatsdaten werden jetzt vollständig genutzt:

| Datenfeld | Genutzt? | Auswertungspotenzial |
|-----------|----------|---------------------|
| **E-Auto** | | |
| `ladung_pv_kwh` | ✅ Ja | PV-Anteil der Ladung |
| `ladung_netz_kwh` | ✅ Ja | Netzabhängigkeit der Ladung |
| `ladung_extern_kwh` | ✅ Ja | Externe Ladungen (öffentlich) |
| `ladung_extern_euro` | ✅ Ja | Kosten externe Ladung |
| `v2h_entladung_kwh` | ✅ Ja | V2H-Nutzung, Rückspeisung ins Haus |
| **Speicher** | | |
| `speicher_ladung_netz_kwh` | ✅ Ja | Arbitrage-Volumen |
| `speicher_ladepreis_cent` | ⏳ Später | Arbitrage-Erlös berechnen |
| **Wärmepumpe** | | |
| `heizenergie_kwh` | ✅ Ja | Heizenergie getrennt |
| `warmwasser_kwh` | ✅ Ja | Warmwasser getrennt |
| **PV-Module** | | |
| `pv_erzeugung_kwh` pro String | ⏳ Später | String-Vergleich, Performance |
| **Balkonkraftwerk** | | |
| `speicher_ladung_kwh` | ✅ Ja | BKW-Speicher-Nutzung |
| `speicher_entladung_kwh` | ✅ Ja | BKW-Speicher-Nutzung |
| **Sonstiges** | | |
| Alles | ✅ Ja | BHKW, Pool, etc. |
| **Alle Typen** | | |
| `sonderkosten_euro` | ✅ Ja | Aggregiert in KomponentenZeitreihe |
| `sonderkosten_notiz` | ⏳ Später | Wartungshistorie-Ansicht |

---

## Bereinigungsplan

### Phase 1: Backend-Endpoints korrigieren

#### 1.1 `get_cockpit_uebersicht` - Speicher aus InvestitionMonatsdaten

**Aktuell (falsch):**
```python
speicher_ladung = batterie_ladung  # aus Monatsdaten!
speicher_entladung = batterie_entladung  # aus Monatsdaten!
```

**Korrekt:**
```python
# Speicher aus InvestitionMonatsdaten laden
speicher_ladung = 0.0
speicher_entladung = 0.0
for speicher in speicher_invs:
    imd = await load_investition_monatsdaten(speicher.id, jahr)
    for m in imd:
        data = m.verbrauch_daten or {}
        speicher_ladung += data.get("ladung_kwh", 0) or 0
        speicher_entladung += data.get("entladung_kwh", 0) or 0
```

#### 1.2 `get_nachhaltigkeit` - Zeitreihe aus InvestitionMonatsdaten

**Aktuell (falsch):**
```python
for md in monatsdaten_list:  # Iteriert über Monatsdaten!
    ...
```

**Korrekt:**
Zeitreihe aus InvestitionMonatsdaten generieren, analog zu `get_komponenten_zeitreihe`.

#### 1.3 PV-Erzeugung pro String hinzufügen

Neuer Response-Bereich in `CockpitUebersichtResponse`:
```python
# PV-Strings
pv_strings: list[PVStringInfo]  # [{bezeichnung, erzeugung_kwh, kwp, spez_ertrag}]
```

### Phase 2: Neue Auswertungs-Felder

#### 2.1 KomponentenZeitreihe erweitern

```python
class KomponentenMonat(BaseModel):
    # ... bestehende Felder ...

    # E-Auto erweitert
    emob_ladung_netz_kwh: float      # NEU
    emob_ladung_extern_kwh: float    # NEU
    emob_ladung_extern_euro: float   # NEU
    emob_v2h_kwh: float              # NEU

    # Speicher erweitert
    speicher_arbitrage_kwh: float    # NEU (Netzladung)
    speicher_arbitrage_preis_cent: Optional[float]  # NEU

    # Wärmepumpe erweitert
    wp_heizung_kwh: float            # NEU (getrennt)
    wp_warmwasser_kwh: float         # NEU (getrennt)

    # Sonderkosten
    sonderkosten_euro: float         # NEU (aggregiert)
```

#### 2.2 Neuer Endpoint: PV-String-Vergleich

```
GET /api/cockpit/pv-strings/{anlage_id}
```

Response:
```python
class PVStringZeitreihe(BaseModel):
    string_id: int
    bezeichnung: str
    ausrichtung: str
    neigung_grad: float
    kwp: float
    monatswerte: list[{monat, erzeugung_kwh, spez_ertrag}]
```

**Auswertungen:**
- Vergleich Süd vs. Ost vs. West
- Performance-Abweichung pro String
- Ertrag pro kWp pro String

#### 2.3 Neuer Endpoint: Arbitrage-Auswertung

```
GET /api/cockpit/arbitrage/{anlage_id}
```

Response:
```python
class ArbitrageUebersicht(BaseModel):
    hat_arbitrage: bool
    netzladung_kwh: float
    durchschnitt_ladepreis_cent: float
    durchschnitt_strompreis_cent: float
    arbitrage_gewinn_euro: float  # (Strompreis - Ladepreis) * Netzladung
    monatswerte: list[ArbitrageMonat]
```

#### 2.4 Neuer Endpoint: V2H-Auswertung

```
GET /api/cockpit/v2h/{anlage_id}
```

Response:
```python
class V2HUebersicht(BaseModel):
    hat_v2h: bool
    v2h_entladung_kwh: float
    v2h_ersparnis_euro: float  # Entladung * Strompreis
    monatswerte: list[V2HMonat]
```

#### 2.5 Neuer Endpoint: Sonderkosten-Übersicht

```
GET /api/cockpit/sonderkosten/{anlage_id}
```

Response:
```python
class SonderkostenUebersicht(BaseModel):
    gesamt_euro: float
    nach_komponente: list[{bezeichnung, typ, betrag, notizen}]
    monatswerte: list[{monat, betrag, notizen}]
```

### Phase 3: Frontend-Tabs erweitern

#### 3.1 KomponentenTab erweitern

- E-Auto: Ladequellen-Verteilung (PV/Netz/Extern) als Pie-Chart
- E-Auto: V2H-Nutzung als zusätzliche Zeile
- Speicher: Arbitrage-Sektion wenn vorhanden
- Wärmepumpe: Heizung vs. Warmwasser getrennt

#### 3.2 Neuer Tab: PV-Anlage (in Auswertungen)

- String-Vergleich als gestapeltes Bar-Chart
- Spezifischer Ertrag pro String
- Performance-Radar-Chart (wenn PVGIS-Prognose vorhanden)

#### 3.3 Erweiterung Finanzen-Tab

- Arbitrage-Gewinn
- V2H-Ersparnis
- Sonderkosten/Wartung
- Externe Ladekosten (E-Auto)

---

## Implementierungsreihenfolge

### Schritt 1: Backend bereinigen (kritisch!) ✅ ERLEDIGT
- [x] `get_cockpit_uebersicht`: Speicher aus InvestitionMonatsdaten
- [x] `get_nachhaltigkeit`: Zeitreihe aus InvestitionMonatsdaten
- [x] Feldnamen-Konsistenz geprüft

### Schritt 2: KomponentenZeitreihe erweitern ✅ ERLEDIGT
- [x] Neue Felder hinzufügen (Arbitrage, V2H, Heizung/WW, BKW-Speicher, Sonderkosten)
- [x] Frontend API-Types anpassen

### Schritt 3: Frontend KomponentenTab erweitern ✅ ERLEDIGT
- [x] E-Auto: V2H-Badge + KPI, Ladequellen (PV/Netz/Extern) als gestapeltes Chart
- [x] E-Auto: Externe Ladekosten anzeigen
- [x] Speicher: Arbitrage-Badge + KPI + Chart-Balken
- [x] Wärmepumpe: Heizung vs. Warmwasser getrennt (2. KPI-Zeile + gestapeltes Chart)
- [x] Balkonkraftwerk: Speicher-Badge + KPIs + Chart-Balken

### Schritt 4: Neue Endpoints (optional, für spätere Releases)
- [ ] `/api/cockpit/pv-strings/{anlage_id}` - String-Vergleich
- [ ] `/api/cockpit/arbitrage/{anlage_id}` - Detaillierte Arbitrage-Auswertung
- [ ] `/api/cockpit/v2h/{anlage_id}` - Detaillierte V2H-Auswertung
- [ ] `/api/cockpit/sonderkosten/{anlage_id}` - Wartungskosten-Übersicht

### Schritt 5: Weitere Frontend-Erweiterungen (optional)
- [ ] Neuer PV-Anlage Tab in Auswertungen (String-Vergleich)
- [ ] Finanzen-Tab: Arbitrage-Gewinn, V2H-Ersparnis, Sonderkosten

---

## Offene Fragen

1. **Monatsdaten.batterie_* Felder entfernen?**
   - Pro: Keine Redundanz mehr
   - Contra: Breaking Change für bestehende Daten
   - Empfehlung: Deprecated markieren, bei Import ignorieren

2. **PV-Erzeugung aus Strings summieren?**
   - Aktuell: `Monatsdaten.pv_erzeugung_kwh` kann manuell oder aus CSV
   - Ziel: Summe aus InvestitionMonatsdaten der PV-Module
   - Problem: Was wenn keine PV-Module als Investitionen angelegt?

3. **Zeitraum-Ermittlung ohne Monatsdaten?**
   - Aktuell: `zeitraum_von/bis` aus Monatsdaten
   - Ziel: Aus InvestitionMonatsdaten ermitteln (MIN/MAX Jahr+Monat)

---

## Zusammenfassung

**Das Problem:** Monatsdaten und InvestitionMonatsdaten werden inkonsistent gemischt.

**Die Lösung:**
- `Monatsdaten` = NUR für Anlagen-Energiebilanz (Einspeisung, Netzbezug, berechnete Quoten)
- `InvestitionMonatsdaten` = ALLE Komponenten-Details (Speicher, E-Auto, WP, PV-Strings, etc.)

**Der Gewinn:**
- Konsistente Datenquelle
- Viel mehr Auswertungsmöglichkeiten (Arbitrage, V2H, String-Vergleich, Sonderkosten)
- Keine "zufällig halbwegs richtigen" Werte mehr
