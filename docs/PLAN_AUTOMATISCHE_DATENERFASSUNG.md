# Implementierungsplan: Automatische Datenerfassung

> **Status:** ✅ IMPLEMENTIERT (2026-02-17)
> **Erstellt:** 2026-02-16
> **Aktualisiert:** 2026-02-17
> **Priorität:** Enhancement
> **Geschätzter Aufwand:** ~31 Stunden

## Zusammenfassung

Dieses Dokument beschreibt die Implementierung der automatischen Datenerfassung für EEDC:

1. **Sensor-Mapping-Wizard** - Zuordnung HA-Sensoren zu EEDC-Feldern (aus YAML-Wizard übernommen)
2. **MQTT Auto-Discovery für Monatswerte** - Automatische Sensor-Erstellung in HA
3. **Monatsabschluss-Wizard** - Geführte monatliche Dateneingabe mit HA-Integration

> **Konzeptänderung (2026-02-17):** Der ursprünglich geplante YAML-Wizard wurde durch einen
> MQTT Auto-Discovery Ansatz ersetzt. Vorteile:
> - Keine YAML-Bearbeitung durch User nötig
> - Kein HA-Neustart erforderlich
> - Nahtlose Integration in bestehenden Monatsabschluss-Wizard

---

## Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MQTT Auto-Discovery                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  EEDC erstellt via MQTT:                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ number.eedc_{anlage}_mwd_{feld}_start                               │   │
│  │ → Speichert Zählerstand vom 1. des Monats (retained)                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              ↓                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ sensor.eedc_{anlage}_mwd_{feld}_monat                               │   │
│  │ → value_template: states(quell_sensor) - states(number.start)       │   │
│  │ → Zeigt aktuellen Monatsverbrauch in Echtzeit                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           Monatswechsel-Ablauf                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Am 1. des Monats 00:01 (Cron-Job):                                        │
│  ├── Liest aktuellen Zählerstand aus HA                                    │
│  ├── Speichert Snapshot in DB (Vorschlagswert)                             │
│  ├── Publiziert neuen Startwert auf MQTT (retained)                        │
│  └── Setzt Flag: "Monat X bereit zum Abschluss"                            │
│                                                                             │
│  Im Monatsabschluss-Wizard (User-gesteuert):                               │
│  ├── Zeigt Snapshot/berechnete Werte als Vorschlag                         │
│  ├── Plausibilitätsprüfung + Warnungen                                     │
│  ├── User bestätigt oder korrigiert                                        │
│  ├── Speichert finale Monatsdaten in DB                                    │
│  └── Publiziert Monatsdaten auf MQTT (retained)                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 0: HA-Integration Bereinigung ✅ ABGESCHLOSSEN

**Durchgeführt in v1.0.0-beta.13**

### Erkenntnisse

- **Auto-Discovery war ineffektiv:** Nur ~10% der HA-Sensoren wurden erkannt (prefix-basierte Erkennung)
- **StringMonatsdaten war redundant:** PV-Erzeugung wird bereits in `InvestitionMonatsdaten.verbrauch_daten["pv_erzeugung_kwh"]` gespeichert
- **ha_sensor_* Felder sind veraltet:** Werden durch MQTT Auto-Discovery Ansatz ersetzt

### Entfernte Komponenten

| Komponente | LOC | Grund |
|------------|-----|-------|
| `ha_integration.py` Discovery | ~1866 | Ineffektiv (~10% Erkennungsrate) |
| `StringMonatsdaten` Model | ~66 | Redundant mit InvestitionMonatsdaten |
| `ha_websocket.py` | ~261 | Unzuverlässig |
| `ha_yaml_generator.py` | ~18 | War nur Placeholder |
| Discovery UI-Komponenten | ~800 | Nicht mehr benötigt |

### Beibehaltene Komponenten

- MQTT Export (`mqtt_client.py`, `ha_export.py`) - funktioniert, wird erweitert
- HA Sensor Export (`ha_sensors_export.py`) - für REST API
- Basis-Endpunkte: `/ha/status`, `/ha/sensors`, `/ha/mapping`

---

## Teil 1: Sensor-Mapping-Wizard

### Motivation

Bevor EEDC automatisch Monatswerte berechnen kann, muss der User einmalig zuordnen, welche HA-Sensoren für welche EEDC-Felder verwendet werden sollen. Diese UI-Logik stammt aus dem ursprünglich geplanten YAML-Wizard, nur der Output ist anders (MQTT statt YAML).

### Wizard-Ablauf

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Sensor-Mapping-Wizard                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Schritt 1: Basis-Sensoren (Pflicht)                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Einspeisung:  [sensor.stromzaehler_einspeisung_total         ▼]    │   │
│  │ Netzbezug:    [sensor.stromzaehler_bezug_total               ▼]    │   │
│  │ PV Gesamt:    [sensor.fronius_total_energy                   ▼]    │   │
│  │               (optional - für kWp-Verteilung auf Strings)          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Schritt 2: PV-Module                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ "Süddach" (10 kWp, 55.6%)                                          │   │
│  │ ○ Eigener Sensor: [sensor.fronius_string1_energy             ▼]    │   │
│  │ ● kWp-Verteilung: 55.6% von PV Gesamt                              │   │
│  │                                                                     │   │
│  │ "Westdach" (8 kWp, 44.4%)                                          │   │
│  │ ○ Eigener Sensor: [_________________________________         ▼]    │   │
│  │ ● kWp-Verteilung: 44.4% von PV Gesamt                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Schritt 3: Speicher                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ "BYD HVS 10.2"                                                     │   │
│  │ Ladung:       [sensor.byd_charge_energy                      ▼]    │   │
│  │ Entladung:    [sensor.byd_discharge_energy                   ▼]    │   │
│  │ Netzladung:   ○ Nicht erfassen  ● Sensor: [______________    ▼]    │   │
│  │               (für Arbitrage-Auswertung)                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Schritt 4: Wärmepumpe                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ "Viessmann Vitocal"                                                │   │
│  │ Stromverbrauch: [sensor.wp_energy                            ▼]    │   │
│  │ Heizenergie:    ○ Sensor: [______________________________    ▼]    │   │
│  │                 ● COP-Berechnung: Strom × 3.5 (JAZ)                │   │
│  │ Warmwasser:     ○ Sensor: [______________________________    ▼]    │   │
│  │                 ● COP-Berechnung: Strom × 3.0                      │   │
│  │                 ○ Nicht separat erfassen                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Schritt 5: E-Auto & Wallbox                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ "VW ID.4" + "Wallbox Pulsar"                                       │   │
│  │ Ladung PV:     [sensor.wallbox_pv_energy                     ▼]    │   │
│  │ Ladung Netz:   [sensor.wallbox_grid_energy                   ▼]    │   │
│  │                oder: ● EV-Quote: Nach Anlagen-Eigenverbrauchsquote │   │
│  │ km gefahren:   ○ Sensor: [______________________________     ▼]    │   │
│  │                ● Manuell im Monatsabschluss-Wizard                 │   │
│  │ V2H-Entladung: ○ Nicht vorhanden  ● Sensor: [____________    ▼]    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Schritt 6: Zusammenfassung                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ✅ 3 Sensoren direkt zugeordnet                                    │   │
│  │ 📊 2 Felder per kWp-Verteilung                                     │   │
│  │ 🔢 2 Felder per COP-Berechnung                                     │   │
│  │ ✏️ 1 Feld manuell im Wizard                                        │   │
│  │                                                                     │   │
│  │ [Speichern & MQTT-Sensoren erstellen]                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Schätzungsstrategien

Wenn nicht für jedes Feld ein eigener Sensor existiert:

| Strategie | Anwendung | Beispiel | Formel |
|-----------|-----------|----------|--------|
| **Direkter Sensor** | Sensor vorhanden | Einspeisung | `states('sensor.xyz')` |
| **kWp-Verteilung** | PV-Strings ohne eigenen Sensor | Süddach 55.6% | `PV_Gesamt × (kWp_String / kWp_Total)` |
| **EV-Quote** | Wallbox PV/Netz-Aufteilung | 72% PV-Anteil | `Ladung × Anlagen_EV_Quote` |
| **COP-Berechnung** | WP Heizung/Warmwasser | JAZ 3.5 | `Stromverbrauch × COP` |
| **Manuell** | Keine Automatisierung | km gefahren | User gibt im Wizard ein |
| **Nicht erfassen** | Feld nicht relevant | V2H ohne Funktion | Wird übersprungen |

### Datenmodell

**Neue Tabelle oder JSON-Feld:** `Anlage.sensor_mapping`

```python
# Anlage.sensor_mapping (JSON)
{
    "basis": {
        "einspeisung": {
            "strategie": "sensor",
            "sensor_id": "sensor.stromzaehler_einspeisung_total"
        },
        "netzbezug": {
            "strategie": "sensor",
            "sensor_id": "sensor.stromzaehler_bezug_total"
        },
        "pv_gesamt": {
            "strategie": "sensor",
            "sensor_id": "sensor.fronius_total_energy"
        }
    },
    "investitionen": {
        "1": {  # Investition ID
            "typ": "pv_module",
            "bezeichnung": "Süddach",
            "felder": {
                "pv_erzeugung_kwh": {
                    "strategie": "kwp_verteilung",
                    "parameter": {"anteil": 0.556, "basis_sensor": "pv_gesamt"}
                }
            }
        },
        "2": {
            "typ": "speicher",
            "bezeichnung": "BYD HVS",
            "felder": {
                "ladung_kwh": {
                    "strategie": "sensor",
                    "sensor_id": "sensor.byd_charge_energy"
                },
                "entladung_kwh": {
                    "strategie": "sensor",
                    "sensor_id": "sensor.byd_discharge_energy"
                },
                "ladung_netz_kwh": {
                    "strategie": "keine"
                }
            }
        },
        "3": {
            "typ": "waermepumpe",
            "bezeichnung": "Viessmann",
            "felder": {
                "stromverbrauch_kwh": {
                    "strategie": "sensor",
                    "sensor_id": "sensor.wp_energy"
                },
                "heizenergie_kwh": {
                    "strategie": "cop_berechnung",
                    "parameter": {"cop": 3.5, "basis_feld": "stromverbrauch_kwh"}
                },
                "warmwasser_kwh": {
                    "strategie": "cop_berechnung",
                    "parameter": {"cop": 3.0, "basis_feld": "stromverbrauch_kwh"}
                }
            }
        },
        "4": {
            "typ": "e_auto",
            "bezeichnung": "VW ID.4",
            "felder": {
                "ladung_pv_kwh": {
                    "strategie": "sensor",
                    "sensor_id": "sensor.wallbox_pv_energy"
                },
                "ladung_netz_kwh": {
                    "strategie": "sensor",
                    "sensor_id": "sensor.wallbox_grid_energy"
                },
                "km_gefahren": {
                    "strategie": "manuell"
                }
            }
        }
    },
    "mqtt_setup_complete": true,
    "mqtt_setup_timestamp": "2026-02-01T10:30:00Z"
}
```

### Technische Umsetzung

#### Backend

**Neue Datei:** `backend/api/routes/sensor_mapping.py`

```python
router = APIRouter(prefix="/sensor-mapping", tags=["Sensor Mapping"])

class StrategieTyp(str, Enum):
    SENSOR = "sensor"
    KWP_VERTEILUNG = "kwp_verteilung"
    EV_QUOTE = "ev_quote"
    COP_BERECHNUNG = "cop_berechnung"
    MANUELL = "manuell"
    KEINE = "keine"

class FeldMapping(BaseModel):
    strategie: StrategieTyp
    sensor_id: Optional[str] = None
    parameter: Optional[dict] = None

class InvestitionMapping(BaseModel):
    investition_id: int
    felder: dict[str, FeldMapping]

class SensorMappingRequest(BaseModel):
    basis: dict[str, FeldMapping]
    investitionen: list[InvestitionMapping]

@router.get("/{anlage_id}")
async def get_sensor_mapping(anlage_id: int) -> SensorMappingResponse:
    """
    Gibt aktuelles Sensor-Mapping zurück.

    Enthält auch Liste aller Investitionen mit erwarteten Feldern
    für die Wizard-Anzeige.
    """

@router.get("/{anlage_id}/available-sensors")
async def get_available_sensors(anlage_id: int) -> list[HASensor]:
    """
    Holt verfügbare Sensoren aus HA für Dropdown-Auswahl.

    Filtert auf relevante device_classes (energy, power, etc.)
    """

@router.post("/{anlage_id}")
async def save_sensor_mapping(
    anlage_id: int,
    mapping: SensorMappingRequest
) -> SensorMappingResult:
    """
    Speichert Sensor-Mapping und erstellt MQTT Entities.

    Ablauf:
    1. Validierung (Sensor existiert in HA?)
    2. Speichern in Anlage.sensor_mapping
    3. MQTT Discovery für alle Felder mit Strategie "sensor"
    4. Return: Liste der erstellten MQTT Entities
    """

@router.delete("/{anlage_id}")
async def delete_sensor_mapping(anlage_id: int) -> dict:
    """
    Löscht Sensor-Mapping und entfernt MQTT Entities.
    """
```

#### Frontend

**Neue Datei:** `frontend/src/pages/SensorMappingWizard.tsx`

```typescript
interface WizardState {
  basis: {
    einspeisung: FeldMapping;
    netzbezug: FeldMapping;
    pv_gesamt: FeldMapping;
  };
  investitionen: Map<number, InvestitionConfig>;
}

interface FeldMapping {
  strategie: 'sensor' | 'kwp_verteilung' | 'ev_quote' | 'cop_berechnung' | 'manuell' | 'keine';
  sensorId?: string;
  parameter?: Record<string, number | string>;
}

export function SensorMappingWizard() {
  const { anlageId } = useParams();
  const [currentStep, setCurrentStep] = useState(0);
  const [state, setState] = useState<WizardState>(initialState);

  // Verfügbare HA-Sensoren laden
  const { data: availableSensors } = useQuery(
    ['available-sensors', anlageId],
    () => api.getAvailableSensors(anlageId)
  );

  // Investitionen laden
  const { data: investitionen } = useQuery(
    ['investitionen', anlageId],
    () => api.getInvestitionen(anlageId)
  );

  // Steps dynamisch aus Investitionen generieren
  const steps = useMemo(() => {
    const s = [
      { id: 'basis', title: 'Basis-Sensoren', component: BasisSensorenStep }
    ];

    // Gruppiert nach Typ
    const pvModule = investitionen?.filter(i => i.typ === 'pv_module') || [];
    const speicher = investitionen?.filter(i => i.typ === 'speicher') || [];
    const wp = investitionen?.filter(i => i.typ === 'waermepumpe') || [];
    const eAuto = investitionen?.filter(i => i.typ === 'e_auto') || [];

    if (pvModule.length > 0) {
      s.push({ id: 'pv', title: 'PV-Module', component: PVModuleStep, props: { investitionen: pvModule } });
    }
    if (speicher.length > 0) {
      s.push({ id: 'speicher', title: 'Speicher', component: SpeicherStep, props: { investitionen: speicher } });
    }
    if (wp.length > 0) {
      s.push({ id: 'wp', title: 'Wärmepumpe', component: WaermepumpeStep, props: { investitionen: wp } });
    }
    if (eAuto.length > 0) {
      s.push({ id: 'eauto', title: 'E-Auto & Wallbox', component: EAutoStep, props: { investitionen: eAuto } });
    }

    s.push({ id: 'summary', title: 'Zusammenfassung', component: MappingSummaryStep });

    return s;
  }, [investitionen]);

  const handleComplete = async () => {
    const result = await api.saveSensorMapping(anlageId, state);
    // Zeigt Erfolg: "X MQTT-Sensoren erstellt"
  };

  return (
    <WizardContainer
      title="Home Assistant Sensor-Zuordnung"
      steps={steps}
      currentStep={currentStep}
      onStepChange={setCurrentStep}
      onComplete={handleComplete}
    />
  );
}
```

**Neue Komponente:** `frontend/src/components/sensor-mapping/FeldMappingInput.tsx`

```typescript
interface FeldMappingInputProps {
  label: string;
  einheit: string;
  feld: string;
  value: FeldMapping;
  onChange: (mapping: FeldMapping) => void;
  availableSensors: HASensor[];
  strategieOptionen: StrategieOption[];  // Welche Strategien sind für dieses Feld möglich
}

export function FeldMappingInput({
  label,
  einheit,
  value,
  onChange,
  availableSensors,
  strategieOptionen
}: FeldMappingInputProps) {
  return (
    <Box>
      <Typography variant="subtitle2">{label}</Typography>

      <RadioGroup
        value={value.strategie}
        onChange={(e) => onChange({ ...value, strategie: e.target.value })}
      >
        {strategieOptionen.map((opt) => (
          <FormControlLabel
            key={opt.value}
            value={opt.value}
            control={<Radio />}
            label={
              <Box display="flex" alignItems="center" gap={1}>
                {opt.label}
                {opt.value === 'sensor' && value.strategie === 'sensor' && (
                  <SensorAutocomplete
                    sensors={availableSensors}
                    value={value.sensorId}
                    onChange={(id) => onChange({ ...value, sensorId: id })}
                  />
                )}
                {opt.value === 'cop_berechnung' && value.strategie === 'cop_berechnung' && (
                  <TextField
                    size="small"
                    type="number"
                    label="COP"
                    value={value.parameter?.cop || ''}
                    onChange={(e) => onChange({
                      ...value,
                      parameter: { ...value.parameter, cop: parseFloat(e.target.value) }
                    })}
                    sx={{ width: 80 }}
                  />
                )}
              </Box>
            }
          />
        ))}
      </RadioGroup>
    </Box>
  );
}
```

### Dateien-Übersicht Teil 1 (Sensor-Mapping)

| Datei | Aktion | Aufwand |
|-------|--------|---------|
| `backend/api/routes/sensor_mapping.py` | Neu | ~2h |
| `backend/models/anlage.py` | Erweitern (sensor_mapping JSON) | ~0.5h |
| `frontend/src/pages/SensorMappingWizard.tsx` | Neu | ~3h |
| `frontend/src/components/sensor-mapping/BasisSensorenStep.tsx` | Neu | ~1h |
| `frontend/src/components/sensor-mapping/PVModuleStep.tsx` | Neu | ~1h |
| `frontend/src/components/sensor-mapping/SpeicherStep.tsx` | Neu | ~0.5h |
| `frontend/src/components/sensor-mapping/WaermepumpeStep.tsx` | Neu | ~0.5h |
| `frontend/src/components/sensor-mapping/EAutoStep.tsx` | Neu | ~0.5h |
| `frontend/src/components/sensor-mapping/FeldMappingInput.tsx` | Neu | ~1h |
| **Gesamt Teil 1** | | **~10h** |

### Navigation

```
Einstellungen
├── Home Assistant
│   ├── Sensor-Zuordnung (NEU - Sensor-Mapping-Wizard)
│   └── MQTT-Export (bestehend)
```

Auch aufrufbar aus:
- Monatsabschluss-Wizard (wenn noch nicht konfiguriert)
- Setup-Wizard (optionaler Schritt am Ende)

---

## Teil 2: MQTT Auto-Discovery für Monatswerte

### Motivation

Nachdem der User im Sensor-Mapping-Wizard die Zuordnungen definiert hat, erstellt EEDC die benötigten MQTT-Sensoren **automatisch** - ohne YAML-Bearbeitung oder HA-Neustart.

### Konzept

**Für jeden Quell-Sensor (z.B. `sensor.stromzaehler_einspeisung_total`) erstellt EEDC:**

1. **Number Entity** - Speichert den Zählerstand vom Monatsanfang
2. **Sensor Entity** - Berechnet den aktuellen Monatswert via `value_template`

### Benennung & Device-Konsistenz

**Präfix:** `mwd_` (Monatswechseldaten) für alphabetische Gruppierung

**Device:** Gleiches Device wie bestehender MQTT-Export:
```python
"device": {
    "identifiers": ["eedc_anlage_{anlage_id}"],
    "name": "EEDC - {anlage_name}",
    "manufacturer": "EEDC",
    "model": "PV-Auswertung",
}
```

**Ergebnis in HA:**
```
EEDC - Meine PV-Anlage
├── pv_erzeugung_gesamt_kwh         (bestehend - Export)
├── autarkie_prozent                (bestehend - Export)
├── ...
├── mwd_einspeisung_start           (NEU - number)
├── mwd_einspeisung_monat           (NEU - sensor, berechnet)
├── mwd_netzbezug_start             (NEU - number)
├── mwd_netzbezug_monat             (NEU - sensor, berechnet)
├── mwd_pv_erzeugung_start          (NEU - number)
├── mwd_pv_erzeugung_monat          (NEU - sensor, berechnet)
└── ...
```

### MQTT Discovery Payloads

#### Number Entity (Monatsanfang-Speicher)

```json
{
  "name": "EEDC Einspeisung Monatsanfang",
  "unique_id": "eedc_1_mwd_einspeisung_start",
  "state_topic": "eedc/anlage/1/mwd_einspeisung_start/state",
  "command_topic": "eedc/anlage/1/mwd_einspeisung_start/set",
  "min": 0,
  "max": 9999999,
  "step": 0.01,
  "unit_of_measurement": "kWh",
  "device_class": "energy",
  "icon": "mdi:counter",
  "retain": true,
  "device": {
    "identifiers": ["eedc_anlage_1"],
    "name": "EEDC - Meine PV-Anlage",
    "manufacturer": "EEDC",
    "model": "PV-Auswertung"
  }
}
```

#### Sensor Entity (Berechneter Monatswert)

```json
{
  "name": "EEDC Einspeisung Monat",
  "unique_id": "eedc_1_mwd_einspeisung_monat",
  "state_topic": "eedc/anlage/1/mwd_einspeisung_monat/state",
  "value_template": "{{ (states('sensor.stromzaehler_einspeisung_total') | float(0) - states('number.eedc_1_mwd_einspeisung_start') | float(0)) | round(1) }}",
  "unit_of_measurement": "kWh",
  "device_class": "energy",
  "state_class": "total",
  "icon": "mdi:transmission-tower-export",
  "device": {
    "identifiers": ["eedc_anlage_1"],
    "name": "EEDC - Meine PV-Anlage",
    "manufacturer": "EEDC",
    "model": "PV-Auswertung"
  }
}
```

### MQTT Retained Strategie

Alle MQTT-Nachrichten werden mit `retain: true` publiziert:

| Topic | Inhalt | Retained |
|-------|--------|----------|
| `eedc/anlage/{id}/mwd_{feld}_start/state` | Zählerstand Monatsanfang | ✅ |
| `eedc/anlage/{id}/mwd_{feld}_monat/state` | Aktueller Monatswert | ✅ |
| `eedc/anlage/{id}/monatsdaten/{jahr}/{monat}` | Finale Monatsdaten (JSON) | ✅ |

**Vorteile:**
- HA-Dashboards zeigen EEDC-Monatswerte auch nach HA-Neustart
- HA-Automationen basierend auf Monatswerten möglich
- Persistenz auch wenn EEDC offline

### Cron-Job: Monatswechsel-Snapshot

**Zweck:** Exakte Erfassung der Zählerstände um 00:00 am 1. des Monats

**Ablauf am 1. des Monats um 00:01:**

```python
async def monthly_snapshot_job():
    """Wird am 1. jeden Monats um 00:01 ausgeführt."""

    for anlage in anlagen_mit_ha_sensoren:
        # 1. Aktuelle Zählerstände aus HA lesen
        zaehlerstaende = await ha_api.get_sensor_states(anlage.sensor_mapping)

        # 2. Snapshot in DB speichern (für Wizard-Vorschlag)
        await db.save_monatswechsel_snapshot(
            anlage_id=anlage.id,
            jahr=now.year,
            monat=now.month - 1,  # Abgeschlossener Monat
            werte=zaehlerstaende,
            erfasst_um=now
        )

        # 3. Neue Startwerte für aktuellen Monat auf MQTT publizieren
        for feld, wert in zaehlerstaende.items():
            await mqtt.publish(
                f"eedc/anlage/{anlage.id}/mwd_{feld}_start/state",
                str(wert),
                retain=True
            )

        # 4. Flag setzen: Monat bereit zum Abschluss
        await db.set_monat_bereit(anlage.id, now.year, now.month - 1)
```

**Implementierung:** APScheduler oder ähnlich, läuft als Background-Task in FastAPI.

### Technische Umsetzung

#### Backend

**Erweitern:** `backend/services/mqtt_client.py`

```python
# Neue Methoden:
async def publish_number_discovery(
    self,
    key: str,                    # z.B. "mwd_einspeisung_start"
    name: str,                   # z.B. "EEDC Einspeisung Monatsanfang"
    anlage_id: int,
    anlage_name: str,
    unit: str = "kWh",
    min_value: float = 0,
    max_value: float = 9999999,
) -> bool:
    """Erstellt eine number Entity via MQTT Discovery."""

async def publish_calculated_sensor(
    self,
    key: str,                    # z.B. "mwd_einspeisung_monat"
    name: str,                   # z.B. "EEDC Einspeisung Monat"
    anlage_id: int,
    anlage_name: str,
    source_sensor: str,          # z.B. "sensor.stromzaehler_einspeisung_total"
    start_number: str,           # z.B. "number.eedc_1_mwd_einspeisung_start"
    unit: str = "kWh",
) -> bool:
    """Erstellt einen Sensor mit value_template via MQTT Discovery."""

async def update_month_start_value(
    self,
    anlage_id: int,
    feld: str,
    wert: float,
) -> bool:
    """Publiziert neuen Startwert (retained)."""
```

**Neue Datei:** `backend/services/ha_mqtt_sync.py`

```python
class HAMqttSyncService:
    """Synchronisiert Monatsdaten zwischen HA und EEDC via MQTT."""

    def __init__(self, mqtt_client: MQTTClient, db: AsyncSession):
        self.mqtt = mqtt_client
        self.db = db

    async def setup_sensors_for_anlage(
        self,
        anlage_id: int,
        sensor_mapping: dict[str, str]  # {"einspeisung": "sensor.xyz", ...}
    ) -> SetupResult:
        """
        Erstellt alle MQTT Entities für eine Anlage.

        Für jeden Eintrag im Mapping werden erstellt:
        - number.eedc_{anlage}_mwd_{feld}_start
        - sensor.eedc_{anlage}_mwd_{feld}_monat
        """

    async def get_current_month_values(
        self,
        anlage_id: int
    ) -> dict[str, float]:
        """Liest aktuelle Monatswerte aus HA via REST API."""

    async def trigger_month_rollover(
        self,
        anlage_id: int,
        jahr: int,
        monat: int
    ) -> RolloverResult:
        """
        Monatswechsel durchführen:
        1. Snapshot speichern
        2. Neue Startwerte publizieren
        """

    async def publish_final_month_data(
        self,
        anlage_id: int,
        jahr: int,
        monat: int,
        daten: dict
    ) -> bool:
        """Publiziert finale Monatsdaten auf MQTT (retained)."""
```

**Neue Datei:** `backend/services/scheduler.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

class EEDCScheduler:
    """Background-Scheduler für periodische Tasks."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def start(self):
        # Monatswechsel-Snapshot: Am 1. jeden Monats um 00:01
        self.scheduler.add_job(
            monthly_snapshot_job,
            CronTrigger(day=1, hour=0, minute=1),
            id="monthly_snapshot",
            name="Monatswechsel Snapshot"
        )
        self.scheduler.start()

    def stop(self):
        self.scheduler.shutdown()
```

#### Frontend

**Erweiterung im Monatsabschluss-Wizard:**

```typescript
// Schritt 0: HA-Sensor-Setup (einmalig)
interface SensorMappingStep {
  // User gibt nur Quell-Sensor-IDs ein
  einspeisung: string;      // sensor.stromzaehler_einspeisung_total
  netzbezug: string;        // sensor.stromzaehler_bezug_total
  pv_erzeugung?: string;    // sensor.fronius_total_energy (optional)
  // Pro Investition mit HA-Sensor
  investitionen: {
    [investitionId: number]: {
      [feld: string]: string;  // z.B. "ladung_kwh": "sensor.wallbox_energy"
    }
  }
}

// Nach Eingabe: EEDC erstellt MQTT Entities automatisch
const handleSetupComplete = async (mapping: SensorMappingStep) => {
  await api.setupMqttSensors(anlageId, mapping);
  // Entities erscheinen sofort in HA
};
```

### Dateien-Übersicht Teil 1

| Datei | Aktion | Aufwand |
|-------|--------|---------|
| `backend/services/mqtt_client.py` | Erweitern (number, value_template) | ~3h |
| `backend/services/ha_mqtt_sync.py` | Neu | ~3h |
| `backend/services/scheduler.py` | Neu (Cron-Job) | ~2h |
| `backend/api/routes/ha_mqtt_setup.py` | Neu | ~1h |
| **Gesamt Teil 1** | | **~9h** |

---

## Teil 3: Monatsabschluss-Wizard

### Motivation

Benutzer müssen monatlich Daten erfassen, die nicht automatisch verfügbar sind:
- E-Auto: Kilometer gefahren, externe Ladekosten
- Wärmepumpe: Heizenergie, Warmwasser (falls kein Wärmemengenzähler)
- Sonderkosten: Wartung, Reparaturen
- Korrekturen: Manuelle Anpassungen automatischer Werte

Der Wizard reduziert diesen Aufwand auf **2-5 Minuten pro Monat**.

### Kernfunktionen

#### 2.1 Intelligente Vorschläge

Für jedes Feld werden Vorschläge aus verschiedenen Quellen generiert:

| Quelle | Beispiel | Konfidenz |
|--------|----------|-----------|
| **HA-Sensor (MQTT)** | "Aus HA: 485,3 kWh" | 95% |
| **Cron-Snapshot** | "Erfasst am 01.02. 00:01" | 90% |
| Vormonat | "Letzter Monat: 1.380 km" | 80% |
| Vorjahr gleicher Monat | "Februar 2025: 1.520 km" | 70% |
| Berechnung | "COP 3.5 × 485 kWh = 1.697 kWh" | 60% |
| Durchschnitt (12 Monate) | "Ø letzte 12 Monate: 1.250 km" | 50% |
| EEDC Parameter | "Jahresfahrleistung ÷ 12: 1.250 km" | 30% |

#### 2.2 Feld-Status-Anzeige

Jedes Feld zeigt seinen Status:
- ✅ **Automatisch (HA)** - Aus MQTT-Sensor berechnet
- 📸 **Snapshot** - Vom Cron-Job erfasst
- ❓ **Fehlt** - Muss eingegeben werden
- ✏️ **Manuell** - Benutzer hat Wert eingegeben
- 💡 **Vorschlag** - Vorschlag verfügbar

#### 2.3 Plausibilitätsprüfungen

| Prüfung | Beispiel | Aktion |
|---------|----------|--------|
| **Negativ-Wert** | Monatswert = -50 kWh | Fehler: "Zähler kann nicht rückwärts laufen" |
| **Unrealistisch hoch** | Einspeisung > 2× PVGIS-Prognose | Warnung: "Deutlich über Erwartung" |
| **Unrealistisch niedrig** | PV im Juli = 10 kWh bei 10 kWp | Warnung: "Sehr niedrig für Jahreszeit" |
| **Sensor unavailable** | Quell-Sensor = "unavailable" | Hinweis: "Sensor nicht erreichbar" |
| **Große Abweichung** | Monatswert vs. Vorjahr ±50% | Warnung mit Vergleichswert |

#### 2.4 Wizard-Ablauf

```
Schritt 0: HA-Setup (einmalig, wenn nicht konfiguriert)
├── "Nutzt du Home Assistant für Energie-Monitoring?"
│   ├── Ja → Sensor-IDs eingeben → MQTT Setup automatisch
│   └── Nein → Überspringen (manuelle Eingabe)
└── EEDC erstellt MQTT Entities in HA

Schritt 1: Zählerdaten (Basis)
├── Einspeisung, Netzbezug, PV-Erzeugung
├── HA verbunden: Zeigt berechnete Werte + Plausibilität
└── Standalone: Manuelle Eingabe + Vorschläge

Schritt 2-n: Pro Investitionstyp
├── E-Auto: km, externe Ladung, V2H
├── Wärmepumpe: Heizung, Warmwasser, Stromverbrauch
├── Speicher: Netzladung (Arbitrage)
└── Etc.

Letzter Schritt: Zusammenfassung + Speichern
├── Übersicht aller Werte mit Status
├── Monatsergebnis (KPIs)
├── Sonderkosten-Option
└── Speichern → Startwerte für nächsten Monat setzen
```

### Startwert-Initialisierung

Beim ersten Setup oder wenn Startwert fehlt:

```
Wizard erkennt: number.eedc_*_start = 0 oder nicht gesetzt
    ↓
EEDC holt via HA REST API den AKTUELLEN Zählerstand:
  GET /api/states/sensor.stromzaehler_einspeisung_total
  → 12.456,7 kWh
    ↓
Wizard zeigt:
  ┌─────────────────────────────────────────────────────────┐
  │ Startwert für Januar fehlt.                            │
  │ Aktueller Zählerstand: 12.456,7 kWh                    │
  │                                                         │
  │ [Übernehmen] [Manuell eingeben: ______]                │
  │                                                         │
  │ Tipp: Falls du den Wert vom 01.01. kennst              │
  │ (z.B. aus der Stromrechnung), trage ihn ein.           │
  └─────────────────────────────────────────────────────────┘
```

### Technische Umsetzung

#### Backend

**Neue Datei:** `backend/services/vorschlag_service.py`

```python
class VorschlagService:
    """Generiert intelligente Vorschläge für Monatsdaten."""

    async def get_vorschlaege(
        self,
        anlage_id: int,
        investition_id: Optional[int],
        feld: str,
        jahr: int,
        monat: int
    ) -> list[Vorschlag]:
        """
        Generiert Vorschläge für ein Feld.

        Quellen (in Prioritätsreihenfolge):
        1. HA-Sensor (MQTT) - wenn konfiguriert
        2. Cron-Snapshot - wenn vorhanden
        3. Vormonat
        4. Vorjahr
        5. Berechnungen (COP, kWp-Verteilung, etc.)
        6. Durchschnitt
        """

    async def pruefe_plausibilitaet(
        self,
        anlage_id: int,
        feld: str,
        wert: float,
        jahr: int,
        monat: int
    ) -> list[PlausibilitaetsWarnung]:
        """Prüft Wert auf Plausibilität."""
```

**Neue Datei:** `backend/api/routes/monatsabschluss.py`

```python
router = APIRouter(prefix="/monatsabschluss", tags=["Monatsabschluss"])

@router.get("/{anlage_id}/{jahr}/{monat}")
async def get_monatsabschluss(
    anlage_id: int,
    jahr: int,
    monat: int,
) -> MonatsabschlussResponse:
    """
    Gibt Status aller Felder für einen Monat zurück.

    Enthält:
    - Aktuelle Werte (HA, Snapshot, oder manuell)
    - Vorschläge für fehlende Felder
    - Plausibilitätswarnungen
    """

@router.post("/{anlage_id}/{jahr}/{monat}")
async def save_monatsabschluss(
    anlage_id: int,
    jahr: int,
    monat: int,
    daten: MonatsabschlussInput,
) -> MonatsabschlussResult:
    """
    Speichert Monatsdaten.

    Ablauf:
    1. Validierung + Plausibilitätsprüfung
    2. Speichern in Monatsdaten + InvestitionMonatsdaten
    3. Neue Startwerte auf MQTT publizieren
    4. Finale Monatsdaten auf MQTT publizieren (retained)
    """

@router.get("/naechster/{anlage_id}")
async def get_naechster_monat(anlage_id: int) -> dict:
    """Findet den nächsten unvollständigen Monat."""
```

#### Frontend

**Neue Datei:** `frontend/src/pages/MonatsabschlussWizard.tsx`

```typescript
export function MonatsabschlussWizard() {
  const { anlageId } = useParams();
  const [jahr, monat] = useNaechsterMonat(anlageId);
  const [currentStep, setCurrentStep] = useState(0);

  // Prüfen ob HA-Setup nötig
  const { data: haStatus } = useQuery(
    ['ha-setup-status', anlageId],
    () => api.getHaSetupStatus(anlageId)
  );

  // Monatsdaten laden
  const { data, isLoading } = useQuery(
    ['monatsabschluss', anlageId, jahr, monat],
    () => api.getMonatsabschluss(anlageId, jahr, monat)
  );

  // Steps dynamisch generieren
  const steps = useMemo(() => {
    const s = [];

    // HA-Setup wenn nicht konfiguriert
    if (!haStatus?.configured) {
      s.push({ id: 'ha-setup', title: 'Home Assistant', component: HASetupStep });
    }

    // Basis-Zählerdaten
    s.push({ id: 'zaehler', title: 'Zählerdaten', component: ZaehlerStep });

    // Pro Investitionstyp
    for (const inv of data?.investitionen || []) {
      s.push({
        id: `inv-${inv.id}`,
        title: inv.bezeichnung,
        component: InvestitionStep,
        props: { investition: inv }
      });
    }

    // Zusammenfassung
    s.push({ id: 'summary', title: 'Zusammenfassung', component: SummaryStep });

    return s;
  }, [haStatus, data]);

  return (
    <WizardContainer
      title={`Monatsabschluss ${monatName(monat)} ${jahr}`}
      steps={steps}
      currentStep={currentStep}
      onStepChange={setCurrentStep}
      onComplete={handleSave}
    />
  );
}
```

### Dateien-Übersicht Teil 3

| Datei | Aktion | Aufwand |
|-------|--------|---------|
| `backend/services/vorschlag_service.py` | Neu | ~3h |
| `backend/api/routes/monatsabschluss.py` | Neu | ~2h |
| `frontend/src/pages/MonatsabschlussWizard.tsx` | Neu | ~3h |
| `frontend/src/components/monatsabschluss/ZaehlerStep.tsx` | Neu | ~1h |
| `frontend/src/components/monatsabschluss/InvestitionStep.tsx` | Neu | ~1h |
| `frontend/src/components/monatsabschluss/SummaryStep.tsx` | Neu | ~1h |
| **Gesamt Teil 3** | | **~11h** |

> **Hinweis:** HASetupStep entfällt hier, da das Setup jetzt im separaten Sensor-Mapping-Wizard erfolgt.
> Der Monatsabschluss-Wizard verlinkt nur dorthin, wenn noch nicht konfiguriert.

---

## Teil 4: Integration & Navigation

### Navigation (nach Implementierung)

```
Einstellungen
├── Daten
│   ├── Monatsdaten
│   ├── Monatsabschluss-Wizard (NEU)
│   ├── Import
│   └── Demo-Daten
├── Home Assistant
│   ├── Sensor-Zuordnung (NEU - Sensor-Mapping-Wizard)
│   └── MQTT-Export (bestehend)
```

### Wizard-Verknüpfungen

```
Sensor-Mapping-Wizard
├── Aufrufbar über: Einstellungen → Home Assistant → Sensor-Zuordnung
├── Aufrufbar über: Monatsabschluss-Wizard (wenn nicht konfiguriert)
└── Aufrufbar über: Setup-Wizard (optionaler letzter Schritt)

Monatsabschluss-Wizard
├── Aufrufbar über: Einstellungen → Daten → Monatsabschluss
├── Aufrufbar über: Dashboard-Banner ("Monat X abschließen")
└── Prüft: sensor_mapping vorhanden? → Sonst Link zu Sensor-Mapping-Wizard
```

### Dashboard-Integration

```typescript
// Dashboard.tsx - Monatsabschluss-Banner
function MonatsabschlussBanner() {
  const { data } = useQuery(['naechster-monat'], api.getNaechsterMonat);

  if (!data?.monat) return null;

  return (
    <Alert
      severity="info"
      icon={<CalendarIcon />}
      action={
        <Button href={`/monatsabschluss/${data.anlageId}/${data.jahr}/${data.monat}`}>
          Jetzt erfassen
        </Button>
      }
    >
      {monatName(data.monat)} {data.jahr} ist abgeschlossen -
      Monatsdaten erfassen?
    </Alert>
  );
}
```

---

## Gesamtaufwand

| Phase | Aufwand |
|-------|---------|
| Phase 0: Bereinigung | ✅ Abgeschlossen (~4h) |
| Teil 1: Sensor-Mapping-Wizard | ~10h |
| Teil 2: MQTT Auto-Discovery | ~9h |
| Teil 3: Monatsabschluss-Wizard | ~11h |
| Teil 4: Integration | ~1h |
| **Gesamt (neu)** | **~31h** |

*Vergleich zum alten Plan (YAML-Wizard): ~25.5h → Mehr Aufwand, aber deutlich bessere UX und Wiederverwendung der Wizard-Logik*

---

## Abhängigkeiten

### Backend

| Paket | Verwendung | Status |
|-------|------------|--------|
| `aiomqtt` | MQTT Client | Bereits vorhanden |
| `apscheduler` | Cron-Jobs | Neu hinzufügen |

### Frontend

- Keine neuen Dependencies erforderlich

---

## Testplan

### Sensor-Mapping-Wizard

1. Wizard öffnen ohne vorheriges Mapping
2. Verfügbare HA-Sensoren werden im Dropdown angezeigt
3. Verschiedene Strategien auswählen (Sensor, kWp-Verteilung, COP)
4. Speichern → Mapping wird in DB gespeichert
5. MQTT Entities werden automatisch erstellt
6. Entities erscheinen in HA (ohne Neustart)

### MQTT Auto-Discovery

1. Nach Sensor-Mapping: Entities erscheinen in HA
2. number Entity manuell setzen → Wert wird gespeichert
3. Berechneter Sensor zeigt korrekten Monatswert
4. Retained Messages überleben HA-Neustart
5. value_template berechnet korrekt (aktuell - start)

### Cron-Job

1. Job manuell triggern
2. Snapshot wird in DB gespeichert
3. Neue Startwerte werden auf MQTT publiziert
4. Flag "Monat bereit" wird gesetzt

### Monatsabschluss-Wizard

1. Wizard öffnen ohne Sensor-Mapping → Link zum Mapping-Wizard
2. Wizard öffnen mit Mapping → HA-Werte als Vorschläge
3. Schätzungsstrategien werden korrekt angewendet (kWp, COP)
4. Plausibilitätswarnungen bei unrealistischen Werten
5. Werte eingeben und speichern
6. Monatsdaten + InvestitionMonatsdaten werden erstellt
7. Startwerte für nächsten Monat werden aktualisiert
8. Finale Monatsdaten auf MQTT publiziert

---

## Changelog-Eintrag (Entwurf)

```markdown
## [1.1.0] - TBD

### Neu
- **Sensor-Mapping-Wizard**: Zuordnung von HA-Sensoren zu EEDC-Feldern
  - Intuitive UI für Basis-Sensoren und Investitionen
  - Schätzungsstrategien: kWp-Verteilung, COP-Berechnung, EV-Quote
  - Mapping wird in DB gespeichert und für MQTT verwendet

- **MQTT Auto-Discovery für Monatswerte**: EEDC erstellt automatisch
  Sensoren in Home Assistant basierend auf dem Sensor-Mapping
  - Keine YAML-Bearbeitung nötig
  - Kein HA-Neustart erforderlich
  - `mwd_*` Sensoren für Zählerstände und Monatswerte
  - value_template berechnet Monatswerte in Echtzeit

- **Monatsabschluss-Wizard**: Geführte monatliche Dateneingabe
  - Automatische Werte aus HA-Sensoren (wenn Mapping konfiguriert)
  - Intelligente Vorschläge (Vormonat, Vorjahr, Berechnungen)
  - Plausibilitätsprüfungen mit Warnungen
  - Verknüpfung mit Sensor-Mapping-Wizard

- **Cron-Job für Monatswechsel**: Automatische Erfassung der
  Zählerstände am 1. des Monats um 00:01

### Technisch
- Neue Dependency: `apscheduler` für Background-Tasks
- MQTT retained Messages für Persistenz
- Neues DB-Feld: `Anlage.sensor_mapping` (JSON)
```
