/**
 * EinstellungenModalHost — öffnet die bestehenden Einstellungs-Wizard-Seiten im Modal
 * (IA v4, Einstellungen-Umbau, Entscheidung 2: „Wizards im Overlay statt Route").
 *
 * Die Wizard-Seiten ziehen ihre `anlageId` selbst aus `useSelectedAnlage()` (Context, kein
 * `useParams`) → sie laufen unverändert im Overlay, ohne eigene Route. Der Host reicht nur
 * „welcher Wizard offen ist" + `onClose`. Lazy-Import je Wizard: bei Feature-Flag aus wirft
 * die DCE den ganzen v4-Baum (und damit diese Importe) weg.
 *
 * Die Detail-Routen unter `/einstellungen/<seite>` bleiben als Deep-Link/Fallback bestehen.
 */
import { lazy, Suspense, type ComponentType } from 'react'
import { Modal, LoadingSpinner } from '../components/ui'

export type WizardKey =
  | 'sensor-mapping'
  | 'custom-import'
  | 'portal-import'
  | 'cloud-import'
  | 'connector'
  | 'ha-statistik-import'
  | 'einrichtung'
  | 'mqtt-inbound'

interface WizardDef {
  titel: string
  Comp: ComponentType
}

/** Standard-Registry: Titel + lazy geladene IST-Wizard-Seite je Schlüssel. */
const STANDARD_REGISTRY: Record<WizardKey, WizardDef> = {
  'sensor-mapping': { titel: 'Sensor-Zuordnung', Comp: lazy(() => import('../pages/SensorMappingWizard')) },
  'custom-import': { titel: 'Eigene Datei importieren', Comp: lazy(() => import('../pages/CustomImportWizard')) },
  'portal-import': { titel: 'Portal-Import', Comp: lazy(() => import('../pages/DataImportWizard')) },
  'cloud-import': { titel: 'Cloud-Import', Comp: lazy(() => import('../pages/CloudImportWizard')) },
  connector: { titel: 'Geräte-Connector', Comp: lazy(() => import('../pages/ConnectorSetupWizard')) },
  'ha-statistik-import': { titel: 'Statistik-Import', Comp: lazy(() => import('../pages/HAStatistikImport')) },
  einrichtung: { titel: 'Ersteinrichtung', Comp: lazy(() => import('../pages/Einrichtung')) },
  'mqtt-inbound': { titel: 'MQTT-Inbound', Comp: lazy(() => import('../pages/MqttInboundSetup')) },
}

/** Titel eines Wizards (für Katalog-Buttons „<Titel> öffnen"). */
export function wizardTitel(key: WizardKey, registry: Record<WizardKey, WizardDef> = STANDARD_REGISTRY): string {
  return registry[key].titel
}

export function EinstellungenModalHost({
  offen,
  onClose,
  registry = STANDARD_REGISTRY,
}: {
  offen: WizardKey | null
  onClose: () => void
  /** Test-/Sonderfall-Seam: überschreibbare Wizard-Registry. */
  registry?: Record<WizardKey, WizardDef>
}) {
  if (!offen) return null
  const def = registry[offen]
  const Comp = def.Comp
  return (
    <Modal isOpen title={def.titel} size="xl" onClose={onClose}>
      <Suspense fallback={<div className="py-12"><LoadingSpinner text="Wird geladen …" /></div>}>
        <Comp />
      </Suspense>
    </Modal>
  )
}
