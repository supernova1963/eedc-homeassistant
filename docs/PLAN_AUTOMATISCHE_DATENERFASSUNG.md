# Implementierungsplan: Automatische Datenerfassung

> **Status:** Phase 0 (Bereinigung) abgeschlossen, Phase 1+2 geplant
> **Erstellt:** 2026-02-16
> **Aktualisiert:** 2026-02-17
> **Priorität:** Enhancement
> **Geschätzter Aufwand:** ~25 Stunden (reduziert nach Bereinigung)

## Zusammenfassung

Dieses Dokument beschreibt zwei komplementäre Features zur Vereinfachung der monatlichen Datenerfassung in EEDC:

1. **HA YAML-Wizard** (Priorität 1) - Generierung von Home Assistant Utility Meter Konfiguration
2. **Monatsabschluss-Wizard** (Priorität 2) - Geführte monatliche Dateneingabe mit intelligenten Vorschlägen

> **Hinweis:** Die Reihenfolge wurde nach der HA-Integration Bereinigung (v1.0.0-beta.13) angepasst.
> Der YAML-Wizard sollte zuerst implementiert werden, da er die Utility Meters generiert,
> die dann vom Monatsabschluss-Wizard genutzt werden können.

---

## Phase 0: HA-Integration Bereinigung ✅ ABGESCHLOSSEN

**Durchgeführt in v1.0.0-beta.13**

### Erkenntnisse

- **Auto-Discovery war ineffektiv:** Nur ~10% der HA-Sensoren wurden erkannt (prefix-basierte Erkennung)
- **StringMonatsdaten war redundant:** PV-Erzeugung wird bereits in `InvestitionMonatsdaten.verbrauch_daten["pv_erzeugung_kwh"]` gespeichert
- **ha_sensor_* Felder sind veraltet:** Manuelles Sensor-Mapping wird durch Utility Meter Ansatz ersetzt

### Entfernte Komponenten

| Komponente | LOC | Grund |
|------------|-----|-------|
| `ha_integration.py` Discovery | ~1866 | Ineffektiv (~10% Erkennungsrate) |
| `StringMonatsdaten` Model | ~66 | Redundant mit InvestitionMonatsdaten |
| `ha_websocket.py` | ~261 | Unzuverlässig |
| `ha_yaml_generator.py` | ~18 | War nur Placeholder |
| Discovery UI-Komponenten | ~800 | Nicht mehr benötigt |

### Beibehaltene Komponenten

- MQTT Export (`mqtt_client.py`, `ha_export.py`) - funktioniert
- HA Sensor Export (`ha_sensors_export.py`) - für REST API
- Basis-Endpunkte: `/ha/status`, `/ha/sensors`, `/ha/mapping`

### DEPRECATED Felder (Anlage Model)

```python
ha_sensor_pv_erzeugung      # DEPRECATED - nicht mehr verwenden
ha_sensor_einspeisung       # DEPRECATED - nicht mehr verwenden
ha_sensor_netzbezug         # DEPRECATED - nicht mehr verwenden
ha_sensor_batterie_ladung   # DEPRECATED - nicht mehr verwenden
ha_sensor_batterie_entladung # DEPRECATED - nicht mehr verwenden
```

Diese Felder bleiben für Rückwärtskompatibilität erhalten, werden aber nicht mehr aktiv genutzt.

---

## Teil 1: Monatsabschluss-Wizard

### Motivation

Benutzer müssen monatlich Daten erfassen, die nicht automatisch verfügbar sind:
- E-Auto: Kilometer gefahren, externe Ladekosten
- Wärmepumpe: Heizenergie, Warmwasser (falls kein Wärmemengenzähler)
- Sonderkosten: Wartung, Reparaturen
- Korrekturen: Manuelle Anpassungen automatischer Werte

Der Wizard reduziert diesen Aufwand auf **2-5 Minuten pro Monat**.

### Kernfunktionen

#### 1.1 Intelligente Vorschläge

Für jedes fehlende Feld werden Vorschläge aus verschiedenen Quellen generiert:

| Quelle | Beispiel | Konfidenz |
|--------|----------|-----------|
| Vormonat | "Letzter Monat: 1.380 km" | 80% |
| Vorjahr gleicher Monat | "Februar 2025: 1.520 km" | 70% |
| Berechnung | "COP 3.5 × 485 kWh = 1.697 kWh" | 60% |
| Durchschnitt (12 Monate) | "Ø letzte 12 Monate: 1.250 km" | 50% |
| EEDC Parameter | "Jahresfahrleistung ÷ 12: 1.250 km" | 30% |

#### 1.2 Feld-Status-Anzeige

Jedes Feld zeigt seinen Status:
- ✅ **Automatisch** - Aus HA oder bereits erfasst
- ❓ **Fehlt** - Muss eingegeben werden
- ✏️ **Manuell** - Benutzer hat Wert eingegeben
- 💡 **Vorschlag** - Vorschlag verfügbar

#### 1.3 Wizard-Ablauf

```
Schritt 1: Zählerdaten (Basis)
├── Einspeisung, Netzbezug, PV-Erzeugung
└── Meist automatisch aus HA

Schritt 2-n: Pro Investitionstyp
├── E-Auto: km, externe Ladung
├── Wärmepumpe: Heizung, Warmwasser
├── Speicher: Netzladung (Arbitrage)
└── Etc.

Letzter Schritt: Zusammenfassung
├── Übersicht aller Werte
├── Monatsergebnis (KPIs)
└── Sonderkosten-Option
```

### Technische Umsetzung

#### Backend

**Neue Datei:** `backend/services/vorschlag_service.py`

```python
class VorschlagService:
    """Generiert intelligente Vorschläge für Monatsdaten."""

    async def get_vorschlaege(
        self,
        investition_id: int,
        feld: str,
        jahr: int,
        monat: int
    ) -> list[Vorschlag]:
        """
        Generiert Vorschläge für ein Feld.

        Returns:
            Liste von Vorschlägen, sortiert nach Konfidenz
        """
        vorschlaege = []

        # Vormonat
        vormonat = await self._get_vormonat(investition_id, feld, jahr, monat)
        if vormonat:
            vorschlaege.append(Vorschlag(
                wert=vormonat,
                label=f"Letzter Monat: {vormonat}",
                quelle="vormonat",
                konfidenz=0.8
            ))

        # Vorjahr
        vorjahr = await self._get_vorjahr(investition_id, feld, jahr, monat)
        if vorjahr:
            vorschlaege.append(Vorschlag(
                wert=vorjahr,
                label=f"{self._monat_name(monat)} {jahr-1}: {vorjahr}",
                quelle="vorjahr",
                konfidenz=0.7
            ))

        # Durchschnitt
        durchschnitt = await self._get_durchschnitt(investition_id, feld, 12)
        if durchschnitt:
            vorschlaege.append(Vorschlag(
                wert=durchschnitt,
                label=f"Ø 12 Monate: {durchschnitt}",
                quelle="durchschnitt",
                konfidenz=0.5
            ))

        # Typ-spezifische Berechnungen
        berechnet = await self._berechne_feld(investition_id, feld, jahr, monat)
        if berechnet:
            vorschlaege.append(berechnet)

        return sorted(vorschlaege, key=lambda x: -x.konfidenz)

    async def _berechne_feld(
        self,
        investition_id: int,
        feld: str,
        jahr: int,
        monat: int
    ) -> Optional[Vorschlag]:
        """Typ-spezifische Berechnungen."""
        investition = await self._get_investition(investition_id)

        if feld == "km_gefahren" and investition.parameter.get("km_jahr"):
            km_monat = investition.parameter["km_jahr"] / 12
            return Vorschlag(
                wert=round(km_monat),
                label=f"Jahresfahrleistung ÷ 12: {round(km_monat)} km",
                quelle="berechnet",
                konfidenz=0.3
            )

        if feld == "heizenergie_kwh":
            stromverbrauch = await self._get_feld_wert(
                investition_id, "stromverbrauch_kwh", jahr, monat
            )
            cop = investition.parameter.get("jaz") or investition.parameter.get("cop_heizung")
            if stromverbrauch and cop:
                berechnet = round(stromverbrauch * cop)
                return Vorschlag(
                    wert=berechnet,
                    label=f"Berechnet (COP {cop}): {berechnet} kWh",
                    quelle="berechnet",
                    konfidenz=0.6
                )

        return None
```

**Neue Datei:** `backend/api/routes/monatsabschluss.py`

```python
router = APIRouter(prefix="/monatsabschluss", tags=["Monatsabschluss"])

class FeldStatus(str, Enum):
    AUTOMATISCH = "automatisch"
    MANUELL = "manuell"
    FEHLT = "fehlt"
    VORSCHLAG = "vorschlag"

class MonatsabschlussResponse(BaseModel):
    """Antwort mit Status aller Felder."""
    anlage_id: int
    jahr: int
    monat: int
    vollstaendig: bool
    felder: dict[str, FeldInfo]
    zusammenfassung: dict

@router.get("/{anlage_id}/{jahr}/{monat}")
async def get_monatsabschluss(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db)
) -> MonatsabschlussResponse:
    """
    Gibt Status aller Felder für einen Monat zurück.

    Enthält:
    - Aktuelle Werte (automatisch oder manuell)
    - Vorschläge für fehlende Felder
    - Zusammenfassung (wie viele fehlen)
    """
    ...

@router.post("/{anlage_id}/{jahr}/{monat}")
async def save_monatsabschluss(
    anlage_id: int,
    jahr: int,
    monat: int,
    daten: MonatsabschlussInput,
    db: AsyncSession = Depends(get_db)
) -> MonatsabschlussResult:
    """
    Speichert die manuell eingegebenen Felder.

    Merged automatische und manuelle Werte.
    """
    ...

@router.get("/naechster/{anlage_id}")
async def get_naechster_monat(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Findet den nächsten unvollständigen Monat."""
    ...
```

#### Frontend

**Neue Datei:** `frontend/src/pages/MonatsabschlussWizard.tsx`

```typescript
interface WizardStep {
  id: string;
  title: string;
  type: 'basis' | 'investition';
  investitionId?: number;
  investitionTyp?: string;
  felder: FeldConfig[];
}

export function MonatsabschlussWizard() {
  const { anlageId, jahr, monat } = useParams();
  const [currentStep, setCurrentStep] = useState(0);
  const [daten, setDaten] = useState<MonatsabschlussDaten | null>(null);

  // API-Daten laden
  const { data, isLoading } = useQuery(
    ['monatsabschluss', anlageId, jahr, monat],
    () => api.getMonatsabschluss(anlageId, jahr, monat)
  );

  // Steps dynamisch aus Investitionen generieren
  const steps = useMemo(() => generateSteps(data), [data]);

  return (
    <Box>
      <Typography variant="h4">
        Monatsabschluss {monatName(monat)} {jahr}
      </Typography>

      <Stepper activeStep={currentStep}>
        {steps.map((step) => (
          <Step key={step.id}>
            <StepLabel>{step.title}</StepLabel>
          </Step>
        ))}
      </Stepper>

      <StepContent step={steps[currentStep]} />

      <WizardNavigation
        onBack={() => setCurrentStep(s => s - 1)}
        onNext={() => setCurrentStep(s => s + 1)}
        onSave={handleSave}
        isLastStep={currentStep === steps.length - 1}
      />
    </Box>
  );
}
```

**Neue Komponente:** `frontend/src/components/monatsabschluss/FeldMitVorschlag.tsx`

```typescript
interface FeldMitVorschlagProps {
  label: string;
  einheit: string;
  status: FeldStatus;
  wert: number | null;
  vorschlaege: Vorschlag[];
  onChange: (wert: number) => void;
}

export function FeldMitVorschlag({
  label,
  einheit,
  status,
  wert,
  vorschlaege,
  onChange
}: FeldMitVorschlagProps) {
  return (
    <Box>
      <Box display="flex" alignItems="center" gap={1}>
        <StatusIcon status={status} />
        <Typography>{label}</Typography>
      </Box>

      {status === 'automatisch' ? (
        <Typography color="success.main">
          {wert} {einheit} (aus HA)
        </Typography>
      ) : (
        <>
          <TextField
            type="number"
            value={wert ?? ''}
            onChange={(e) => onChange(parseFloat(e.target.value))}
            InputProps={{
              endAdornment: <InputAdornment position="end">{einheit}</InputAdornment>
            }}
          />

          {vorschlaege.length > 0 && (
            <Box mt={1}>
              <Typography variant="caption" color="text.secondary">
                Vorschläge:
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap">
                {vorschlaege.map((v) => (
                  <Chip
                    key={v.quelle}
                    label={v.label}
                    size="small"
                    icon={<LightbulbIcon />}
                    onClick={() => onChange(v.wert)}
                  />
                ))}
              </Stack>
            </Box>
          )}
        </>
      )}
    </Box>
  );
}
```

### Dateien-Übersicht Teil 1

| Datei | Aktion | Aufwand |
|-------|--------|---------|
| `backend/services/vorschlag_service.py` | Neu | ~3h |
| `backend/api/routes/monatsabschluss.py` | Neu | ~2h |
| `frontend/src/pages/MonatsabschlussWizard.tsx` | Neu | ~3h |
| `frontend/src/components/monatsabschluss/FeldMitVorschlag.tsx` | Neu | ~1h |
| `frontend/src/components/monatsabschluss/StepContent.tsx` | Neu | ~1h |
| `frontend/src/components/monatsabschluss/Zusammenfassung.tsx` | Neu | ~1h |
| `frontend/src/pages/Dashboard.tsx` | Banner hinzufügen | ~0.5h |
| **Gesamt Teil 1** | | **~11.5h** |

---

## Teil 2: HA YAML-Wizard

### Motivation

Für Benutzer mit Home Assistant kann die Datenerfassung teilweise automatisiert werden. Der YAML-Wizard generiert eine vollständige, kopierfähige HA-Konfiguration mit Utility Meters für monatliche Aggregation.

### Kernfunktionen

#### 2.1 EEDC-integrierte Generierung

Der Wizard liest die vorhandenen Investitionen und generiert pro Komponente passende Utility Meters:

```yaml
utility_meter:
  # Investition ID: 1 - "Süddach" (10 kWp)
  eedc_pv_1_sueddach_monat:
    source: sensor.fronius_string1_energy
    name: "EEDC PV Süddach Monat"
    cycle: monthly
```

#### 2.2 Schätzungs-Strategien

Wenn nicht alle Sensoren verfügbar sind:

| Strategie | Anwendung | Beispiel |
|-----------|-----------|----------|
| kWp-Verteilung | PV-Strings | 55.6% von Gesamt für 10kWp String |
| EV-Quote | Wallbox PV/Netz | 72% PV-Anteil nach Anlagen-Quote |
| COP-Berechnung | WP Heizung | Strom × COP = Wärme |
| Jahreswert ÷ 12 | E-Auto km | Gleichverteilung |

#### 2.3 Generiertes YAML enthält

1. **Utility Meters** - Pro Sensor monatliche Aggregation
2. **Template Sensors** - Für Schätzungen und Berechnungen
3. **JSON-Sensor** - Aggregiert alle Werte für EEDC-Import
4. **Optional: MQTT Automation** - Push bei Monatswechsel

### Technische Umsetzung

#### Backend

**Neue Datei:** `backend/services/ha_yaml_generator.py` (Inhalt ersetzen)

```python
from jinja2 import Environment, BaseLoader
from dataclasses import dataclass
from typing import Optional
from enum import Enum

class SchaetzungsStrategie(str, Enum):
    SENSOR = "sensor"           # Direkter Sensor
    KWP_ANTEIL = "kwp_anteil"   # Verteilung nach kWp
    EV_QUOTE = "ev_quote"       # Nach Eigenverbrauchsquote
    COP = "cop"                 # COP-Berechnung
    KONSTANT = "konstant"       # Fester Monatswert
    KEINE = "keine"             # Nicht erfassen

@dataclass
class SensorConfig:
    """Konfiguration für einen Sensor im YAML."""
    feld: str
    sensor_id: Optional[str]
    strategie: SchaetzungsStrategie
    parameter: dict  # z.B. {"anteil": 0.556} oder {"cop": 3.5}

@dataclass
class InvestitionYAMLConfig:
    """YAML-Konfiguration für eine Investition."""
    investition_id: int
    bezeichnung: str
    typ: str
    sensoren: list[SensorConfig]

class HAYamlGenerator:
    """Generiert Home Assistant YAML für EEDC."""

    UTILITY_METER_TEMPLATE = """
  # Investition ID: {{ inv.investition_id }} - "{{ inv.bezeichnung }}"
  eedc_{{ inv.typ }}_{{ inv.investition_id }}_{{ inv.slug }}_monat:
    source: {{ sensor.sensor_id }}
    name: "EEDC {{ inv.bezeichnung }} Monat"
    cycle: monthly
"""

    TEMPLATE_SENSOR_KWP = """
      # {{ inv.bezeichnung }} ({{ sensor.parameter.anteil_prozent }}% von Gesamt)
      - name: "EEDC {{ inv.bezeichnung }} Monat (berechnet)"
        unique_id: eedc_{{ inv.typ }}_{{ inv.investition_id }}_monat_calc
        unit_of_measurement: "kWh"
        device_class: energy
        state: >
          {{ "{{" }} (states('sensor.eedc_pv_gesamt_monat') | float(0) * {{ sensor.parameter.anteil }}) | round(1) {{ "}}" }}
        attributes:
          anteil_prozent: {{ sensor.parameter.anteil_prozent }}
          basis: "kWp-Verteilung"
          investition_id: {{ inv.investition_id }}
"""

    def generate(self, config: list[InvestitionYAMLConfig]) -> str:
        """Generiert vollständiges YAML."""
        yaml_parts = [self._header()]

        # Utility Meters
        yaml_parts.append("\nutility_meter:")
        for inv in config:
            for sensor in inv.sensoren:
                if sensor.strategie == SchaetzungsStrategie.SENSOR:
                    yaml_parts.append(self._render_utility_meter(inv, sensor))

        # Template Sensors für Schätzungen
        yaml_parts.append("\ntemplate:")
        yaml_parts.append("  - sensor:")
        for inv in config:
            for sensor in inv.sensoren:
                if sensor.strategie == SchaetzungsStrategie.KWP_ANTEIL:
                    yaml_parts.append(self._render_template_kwp(inv, sensor))
                elif sensor.strategie == SchaetzungsStrategie.EV_QUOTE:
                    yaml_parts.append(self._render_template_ev_quote(inv, sensor))

        # JSON-Aggregations-Sensor
        yaml_parts.append(self._render_json_sensor(config))

        return "\n".join(yaml_parts)

    def _header(self) -> str:
        return """# ══════════════════════════════════════════════════════════════════
# EEDC Utility Meters - Automatisch generiert
# Kopiere diesen Block in deine configuration.yaml
# Generiert am: {{ now }}
# ══════════════════════════════════════════════════════════════════
"""
```

**Neue Datei:** `backend/api/routes/ha_yaml_wizard.py`

```python
router = APIRouter(prefix="/ha/yaml-wizard", tags=["HA YAML Wizard"])

class YAMLWizardRequest(BaseModel):
    """Anfrage für YAML-Generierung."""
    anlage_id: int
    basis_sensoren: BasisSensoren
    investition_configs: list[InvestitionSensorConfig]

class BasisSensoren(BaseModel):
    """Pflicht-Sensoren."""
    einspeisung: str  # sensor.grid_export_energy
    netzbezug: str    # sensor.grid_import_energy

class InvestitionSensorConfig(BaseModel):
    """Sensor-Konfiguration pro Investition."""
    investition_id: int
    sensoren: dict[str, SensorEingabe]  # feld -> config

class SensorEingabe(BaseModel):
    """Eingabe für ein Sensor-Feld."""
    strategie: SchaetzungsStrategie
    sensor_id: Optional[str] = None
    parameter: Optional[dict] = None

@router.get("/investitionen/{anlage_id}")
async def get_investitionen_fuer_wizard(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
) -> list[InvestitionFuerWizard]:
    """
    Gibt alle Investitionen mit erwarteten Feldern zurück.

    Pro Investitionstyp werden die möglichen Sensor-Felder
    und Schätzungs-Optionen zurückgegeben.
    """
    ...

@router.post("/generate")
async def generate_yaml(
    request: YAMLWizardRequest,
    db: AsyncSession = Depends(get_db)
) -> YAMLResponse:
    """
    Generiert YAML basierend auf Benutzer-Konfiguration.

    Speichert auch die ha_entity_id in den Investitionen.
    """
    ...

@router.get("/template")
async def get_yaml_template() -> dict:
    """
    Gibt eine leere YAML-Vorlage mit Dokumentation zurück.
    """
    ...
```

#### Frontend

**Neue Datei:** `frontend/src/pages/HAYamlWizard.tsx`

```typescript
interface WizardState {
  basisSensoren: {
    einspeisung: string;
    netzbezug: string;
  };
  investitionen: Map<number, InvestitionConfig>;
}

interface InvestitionConfig {
  [feld: string]: {
    strategie: 'sensor' | 'kwp_anteil' | 'ev_quote' | 'konstant' | 'keine';
    sensorId?: string;
    parameter?: Record<string, number>;
  };
}

export function HAYamlWizard() {
  const { anlageId } = useParams();
  const [state, setState] = useState<WizardState>(initialState);
  const [generatedYaml, setGeneratedYaml] = useState<string | null>(null);

  // Investitionen laden
  const { data: investitionen } = useQuery(
    ['ha-wizard-investitionen', anlageId],
    () => api.getInvestitionenFuerWizard(anlageId)
  );

  // YAML generieren
  const handleGenerate = async () => {
    const yaml = await api.generateYaml({
      anlage_id: anlageId,
      basis_sensoren: state.basisSensoren,
      investition_configs: Array.from(state.investitionen.entries()).map(
        ([id, config]) => ({ investition_id: id, sensoren: config })
      )
    });
    setGeneratedYaml(yaml);
  };

  return (
    <Box>
      <Typography variant="h4">
        Home Assistant YAML-Wizard
      </Typography>

      <Alert severity="info" sx={{ mb: 3 }}>
        Dieser Wizard generiert YAML-Konfiguration für Home Assistant
        Utility Meters. Das YAML kann in deine <code>configuration.yaml</code>
        kopiert werden.
      </Alert>

      {/* Schritte */}
      <BasisSensorenStep ... />

      {investitionen?.map((inv) => (
        <InvestitionSensorStep
          key={inv.id}
          investition={inv}
          config={state.investitionen.get(inv.id)}
          onChange={(config) => updateInvestition(inv.id, config)}
        />
      ))}

      <Button variant="contained" onClick={handleGenerate}>
        YAML generieren
      </Button>

      {generatedYaml && (
        <YamlPreview
          yaml={generatedYaml}
          onCopy={() => navigator.clipboard.writeText(generatedYaml)}
          onDownload={() => downloadAsFile(generatedYaml, 'eedc_ha.yaml')}
        />
      )}
    </Box>
  );
}
```

### Dateien-Übersicht Teil 2

| Datei | Aktion | Aufwand |
|-------|--------|---------|
| `backend/services/ha_yaml_generator.py` | Neu schreiben | ~4h |
| `backend/api/routes/ha_yaml_wizard.py` | Neu | ~2h |
| `frontend/src/pages/HAYamlWizard.tsx` | Neu | ~4h |
| `frontend/src/components/ha-wizard/BasisSensorenStep.tsx` | Neu | ~1h |
| `frontend/src/components/ha-wizard/InvestitionSensorStep.tsx` | Neu | ~2h |
| `frontend/src/components/ha-wizard/YamlPreview.tsx` | Neu | ~1h |
| **Gesamt Teil 2** | | **~14h** |

---

## Teil 3: Integration & Cleanup ✅ GRÖßTENTEILS ABGESCHLOSSEN

> **Status:** Die meisten Cleanup-Aufgaben wurden in Phase 0 (v1.0.0-beta.13) erledigt.

### Bereits durchgeführt (v1.0.0-beta.13)

| Datei | Aktion | Status |
|-------|--------|--------|
| `frontend/src/pages/HAImportSettings.tsx` | Umbenannt zu `DatenerfassungGuide.tsx` | ✅ |
| `backend/api/routes/ha_integration.py` | Discovery entfernt, nur Basis-Endpoints | ✅ |
| `backend/models/string_monatsdaten.py` | Gelöscht (redundant) | ✅ |
| `backend/services/ha_websocket.py` | Gelöscht (unzuverlässig) | ✅ |
| `backend/services/ha_yaml_generator.py` | Gelöscht (war Placeholder) | ✅ |
| Discovery UI-Komponenten | Gelöscht | ✅ |

### Noch offen

| Datei | Aktion |
|-------|--------|
| `frontend/src/pages/HAExportSettings.tsx` | Wizard verlinken wenn implementiert |
| `frontend/src/pages/DatenerfassungGuide.tsx` | Aktualisieren mit Links zu neuen Wizards |

### Navigation (aktuell)

```
Einstellungen
├── Daten
│   ├── Monatsdaten
│   ├── Import
│   ├── Datenerfassung (aktuell: Guide)
│   └── Demo-Daten
├── Optional
│   └── HA-Export (MQTT)
```

### Navigation (nach Implementierung)

```
Einstellungen
├── Daten
│   ├── Monatsdaten
│   ├── Monatsabschluss-Wizard (NEU)
│   ├── Import
│   └── Demo-Daten
├── Home Assistant
│   ├── YAML-Wizard (NEU)
│   └── MQTT-Export
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
      action={
        <Button href={`/monatsabschluss/${data.jahr}/${data.monat}`}>
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

## Priorisierung (AKTUALISIERT)

### Phase 0: HA-Integration Bereinigung ✅ ABGESCHLOSSEN (v1.0.0-beta.13)

- ~2000 LOC toter Code entfernt
- Klare Basis für neue Features
- Aufwand: ~4h

### Phase 1: HA YAML-Wizard (Release v1.1)

**Priorität: HOCH** (vorher Phase 2)

- Generiert Utility Meter Konfiguration für HA
- Utility Meters liefern dann automatisch monatliche Daten
- Muss VOR dem Monatsabschluss-Wizard implementiert werden
- Aufwand: ~14h

### Phase 2: Monatsabschluss-Wizard (Release v1.1 oder v1.2)

**Priorität: HOCH** (vorher Phase 1)

- Löst das Kernproblem (monatliche Dateneingabe)
- Funktioniert standalone (ohne HA)
- Kann HA-Daten aus Utility Meters nutzen (wenn Phase 1 implementiert)
- Aufwand: ~11.5h

### Phase 3: Integration & Cleanup ✅ GRÖßTENTEILS ABGESCHLOSSEN

- Alte HA-Integration bereits bereinigt
- Nur noch kleinere Anpassungen nötig
- Aufwand: ~1h (reduziert von ~2h)

---

## Offene Fragen

1. **Benachrichtigungen:** Soll EEDC E-Mail/Push-Benachrichtigungen senden wenn ein neuer Monat verfügbar ist?

2. **Bulk-Import:** Soll der Monatsabschluss-Wizard auch mehrere Monate gleichzeitig unterstützen?

3. **Validierung:** Wie streng soll die Validierung sein? (Warnungen vs. Fehler bei unplausiblen Werten)

4. **MQTT vs. REST:** Soll der HA-Import per MQTT Push oder REST Pull erfolgen?

---

## Abhängigkeiten

### Backend

- Keine neuen Dependencies erforderlich
- Jinja2 bereits in FastAPI enthalten

### Frontend

- Optional: `react-syntax-highlighter` für YAML-Vorschau
- Alternativ: Einfaches `<pre>` mit Copy-Button

---

## Testplan

### Monatsabschluss-Wizard

1. Wizard öffnen für Monat ohne Daten
2. Vorschläge werden korrekt angezeigt
3. Werte eingeben und speichern
4. Monatsdaten + InvestitionMonatsdaten werden erstellt
5. Wizard für gleichen Monat öffnen → zeigt gespeicherte Daten

### HA YAML-Wizard

1. Wizard öffnen, Sensoren eingeben
2. YAML wird korrekt generiert
3. YAML in HA configuration.yaml testen
4. Utility Meters funktionieren nach HA-Neustart

---

## Changelog-Eintrag (Entwurf)

```markdown
## [1.1.0] - TBD

### Neu
- **Monatsabschluss-Wizard**: Geführte monatliche Dateneingabe mit
  intelligenten Vorschlägen basierend auf Vormonat, Vorjahr und
  berechneten Werten

## [1.2.0] - TBD

### Neu
- **HA YAML-Wizard**: Generiert Home Assistant Utility Meter
  Konfiguration basierend auf EEDC-Investitionen
- Unterstützung für Schätzungsstrategien (kWp-Verteilung, EV-Quote, etc.)

### Entfernt
- Veraltete HA-Import Funktionen (waren bereits deaktiviert)
```
