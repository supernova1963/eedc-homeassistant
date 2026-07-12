/**
 * EinstellungenModalHost — öffnet die bestehenden Einstellungs-Wizard-Seiten im Modal
 * (IA v4, Einstellungen-Umbau, Entscheidung 2: „Wizards im Overlay statt Route").
 *
 * Die Wizard-Seiten ziehen ihre `anlageId` selbst aus `useSelectedAnlage()` (Context, kein
 * `useParams`) → sie laufen unverändert im Overlay, ohne eigene Route. Der Host reicht nur
 * „welcher Wizard offen ist" + `onClose`. Lazy-Import je Wizard: bei Feature-Flag aus wirft
 * die DCE den ganzen v4-Baum (und damit diese Importe) weg.
 *
 * Wizard-Host-Kontext (Style-Guide Teil D, W2/W5): der Host stellt den Wizards `schliessen`
 * (Terminal-Aktion nach Commit, nie `navigate`) und `abbrechen` (Dirty-geschützter Abbruch)
 * bereit sowie `setzeBlocker`, mit dem ein Wizard ungespeicherte Eingaben meldet. Auf der
 * Standalone-Route (kein Host) liefert {@link useWizardHost} `imOverlay: false` → die Wizards
 * fallen dort auf ihr `navigate`-Verhalten zurück.
 *
 * Die Detail-Routen unter `/einstellungen/<seite>` bleiben als Deep-Link/Fallback bestehen.
 */
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
} from 'react'
import { Modal, LoadingSpinner, ConfirmDialog } from '../components/ui'
import { WizardHostContext, WizardSteuerungContext, type WizardHostCtx, type WizardKey } from './wizardHost'

// Union lebt jetzt im (komponentenfreien) wizardHost-Modul; Re-Export hält die
// bestehenden Importe (`einstellungenKatalog`, Sichten) stabil.
export type { WizardKey } from './wizardHost'

interface WizardDef {
  titel: string
  Comp: ComponentType
}

/** Standard-Registry: Titel + lazy geladene IST-Wizard-Seite je Schlüssel. */
const STANDARD_REGISTRY: Record<WizardKey, WizardDef> = {
  'sensor-mapping': { titel: 'Sensor-Zuordnung', Comp: lazy(() => import('../pages/SensorMappingWizard')) },
  'csv-import': { titel: 'CSV importieren', Comp: lazy(() => import('../pages/CsvImportWizard')) },
  'custom-import': { titel: 'Eigene Datei importieren', Comp: lazy(() => import('../pages/CustomImportWizard')) },
  'portal-import': { titel: 'Portal-Import', Comp: lazy(() => import('../pages/DataImportWizard')) },
  'cloud-import': { titel: 'Cloud-Import', Comp: lazy(() => import('../pages/CloudImportWizard')) },
  connector: { titel: 'Geräte-Connector', Comp: lazy(() => import('../pages/ConnectorSetupWizard')) },
  'ha-statistik-import': { titel: 'Statistik-Import', Comp: lazy(() => import('../pages/HAStatistikImport')) },
  einrichtung: { titel: 'Ersteinrichtung', Comp: lazy(() => import('../pages/Einrichtung')) },
  // D4 (2026-07-11): Kombi-Wizard — Schritt 1 wählt Inbound (Empfangen) / Gateway (Senden).
  'mqtt-inbound': { titel: 'Live-Daten via MQTT', Comp: lazy(() => import('../pages/MqttInboundSetup')) },
  // Monatsabschluss-V4 Bündel 6 (2026-07-12): als V4-Fläche stillgelegt — der
  // Wizard-Overlay-Eintrag ist entfernt, alle V4-Einstiege öffnen jetzt die
  // assistierte `MonatsdatenForm` (Bündel 5). Die V3-Route `/monatsabschluss/…`
  // + `pages/MonatsabschlussWizard` bleiben unberührt bis zum Flip (PLAN-IA-V4-RESTWEG).
}

/** Titel eines Wizards (für Katalog-Buttons „<Titel> öffnen"). */
export function wizardTitel(key: WizardKey, registry: Record<WizardKey, WizardDef> = STANDARD_REGISTRY): string {
  return registry[key].titel
}

export function EinstellungenModalHost({
  offen,
  onClose,
  onWechsel,
  payload,
  registry = STANDARD_REGISTRY,
}: {
  offen: WizardKey | null
  onClose: () => void
  /** Cross-Wizard-Sprung (D2/E1): ersetzt den offenen Wizard im selben Overlay. */
  onWechsel?: (key: WizardKey, payload?: unknown) => void
  /** Aufruf-Parameter für den offenen Wizard (E1-Payload-Kanal). */
  payload?: unknown
  /** Test-/Sonderfall-Seam: überschreibbare Wizard-Registry. */
  registry?: Record<WizardKey, WizardDef>
}) {
  const blockerRef = useRef(false)
  const [nachfrageOffen, setNachfrageOffen] = useState(false)

  // Beim Wizard-Wechsel/Öffnen Blocker + Nachfrage zurücksetzen.
  useEffect(() => {
    blockerRef.current = false
    setNachfrageOffen(false)
  }, [offen])

  const setzeBlocker = useCallback((aktiv: boolean) => {
    blockerRef.current = aktiv
  }, [])

  const schliessen = useCallback(() => {
    blockerRef.current = false
    setNachfrageOffen(false)
    onClose()
  }, [onClose])

  // Frame-Schluss (✕/ESC/Backdrop) und Abbrechen: bei ungespeicherten Eingaben nachfragen.
  const versuchSchliessen = useCallback(() => {
    if (blockerRef.current) setNachfrageOffen(true)
    else schliessen()
  }, [schliessen])

  const hostCtx: WizardHostCtx = {
    imOverlay: true,
    schliessen,
    abbrechen: versuchSchliessen,
    setzeBlocker,
    oeffneWizard: onWechsel ?? (() => {}),
    payload,
  }

  if (!offen) return null
  const def = registry[offen]
  const Comp = def.Comp
  return (
    <>
      <Modal isOpen title={def.titel} size="xl" onClose={versuchSchliessen}>
        <WizardHostContext.Provider value={hostCtx}>
          <Suspense fallback={<div className="py-12"><LoadingSpinner text="Wird geladen …" /></div>}>
            <Comp />
          </Suspense>
        </WizardHostContext.Provider>
      </Modal>
      <ConfirmDialog
        isOpen={nachfrageOffen}
        onClose={() => setNachfrageOffen(false)}
        onConfirm={schliessen}
        title="Assistent schließen?"
        message="Es gibt noch nicht übernommene Eingaben. Beim Schließen gehen sie verloren."
        confirmLabel="Verwerfen & schließen"
        cancelLabel="Weiter bearbeiten"
        variant="danger"
      />
    </>
  )
}

/**
 * WizardOverlayProvider — DER app-weite Overlay-Kanal (Mängelbehebung D/E).
 * Hält den EINEN offenen Wizard (+ Payload) und stellt `oeffneWizard` über den
 * {@link WizardSteuerungContext} bereit — für die StatusFusszeile, Katalog-Blöcke
 * und `*Teile` außerhalb des Overlays. Sitzt in LayoutV4, damit es genau EINEN
 * Host gibt (kein zweites Modal-Exemplar pro Sicht).
 */
export function WizardOverlayProvider({ children }: { children: ReactNode }) {
  const [offen, setOffen] = useState<{ key: WizardKey; payload?: unknown } | null>(null)
  const oeffne = useCallback((key: WizardKey, payload?: unknown) => setOffen({ key, payload }), [])
  return (
    <WizardSteuerungContext.Provider value={oeffne}>
      {children}
      <EinstellungenModalHost
        offen={offen?.key ?? null}
        payload={offen?.payload}
        onClose={() => setOffen(null)}
        onWechsel={oeffne}
      />
    </WizardSteuerungContext.Provider>
  )
}
