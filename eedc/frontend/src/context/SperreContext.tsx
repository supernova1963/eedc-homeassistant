/**
 * Einstellungs-Sperre — Zustand und Entsperr-Dialog für die ganze Anwendung.
 *
 * Zwei Aufgaben, die zusammengehören:
 *
 * 1. **Der Zustand**, damit Bedienelemente gar nicht erst angeboten werden, die
 *    ohnehin abgewiesen würden. Ein Knopf, der zuverlässig eine Fehlermeldung
 *    erzeugt, ist schlechter als kein Knopf.
 * 2. **Der Dialog**, den `api/client.ts` und `api/fetchApi.ts` bei einem 423 öffnen
 *    lassen — ohne eine React-Komponente importieren zu müssen. Die Anmeldung läuft
 *    über `lib/sperreSpeicher.ts`.
 *
 * Ist keine PIN gesetzt — der Auslieferungszustand —, tut dieser Context nichts und
 * meldet alles als entsperrt.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { sperreApi } from '../api/sperre'
import { entsperrDialogAnmelden, nachweisLoeschen } from '../lib/sperreSpeicher'
import { Alert, Button, Input, Modal } from '../components/ui'

interface SperreContextType {
  /** Ist überhaupt eine PIN eingerichtet? */
  pinGesetzt: boolean
  /** Darf diese Sitzung schreiben? Ohne PIN immer `true`. */
  entsperrt: boolean
  /** Öffnet den Dialog; löst auf, sobald entsperrt oder abgebrochen wurde. */
  entsperren: () => Promise<boolean>
  /** Wieder sperren. */
  sperren: () => Promise<void>
  /** Nach dem Setzen/Entfernen einer PIN den Zustand neu holen. */
  aktualisieren: () => Promise<void>
}

const SperreContext = createContext<SperreContextType | undefined>(undefined)

export function SperreProvider({ children }: { children: ReactNode }) {
  const [pinGesetzt, setPinGesetzt] = useState(false)
  const [entsperrt, setEntsperrt] = useState(true)
  const [offen, setOffen] = useState(false)
  const [pin, setPin] = useState('')
  const [fehler, setFehler] = useState<string | null>(null)
  const [laeuft, setLaeuft] = useState(false)

  // Der Dialog wird aus nicht-React-Code geöffnet und muss dort auflösen, sobald der
  // Anwender entschieden hat. Die Auflöse-Funktion liegt deshalb in einer Ref.
  const aufloesen = useRef<((ok: boolean) => void) | null>(null)

  const aktualisieren = useCallback(async () => {
    try {
      const s = await sperreApi.status()
      setPinGesetzt(s.pin_gesetzt)
      setEntsperrt(s.entsperrt)
    } catch {
      // Kein Status heißt: nicht sperren. Eine Anwendung, die sich bei einem
      // Netzwerkfehler selbst aussperrt, wäre schlimmer als eine offene.
      setPinGesetzt(false)
      setEntsperrt(true)
    }
  }, [])

  useEffect(() => {
    void aktualisieren()
  }, [aktualisieren])

  const entsperren = useCallback((): Promise<boolean> => {
    setPin('')
    setFehler(null)
    setOffen(true)
    return new Promise<boolean>((resolve) => {
      aufloesen.current = resolve
    })
  }, [])

  useEffect(() => {
    entsperrDialogAnmelden(entsperren)
    return () => entsperrDialogAnmelden(null)
  }, [entsperren])

  const schliessen = (ok: boolean) => {
    setOffen(false)
    aufloesen.current?.(ok)
    aufloesen.current = null
  }

  const absenden = async () => {
    setLaeuft(true)
    setFehler(null)
    try {
      await sperreApi.entsperren(pin)
      setEntsperrt(true)
      schliessen(true)
    } catch (e) {
      setFehler(e instanceof Error ? e.message : 'PIN stimmt nicht.')
    } finally {
      setLaeuft(false)
    }
  }

  const sperren = useCallback(async () => {
    nachweisLoeschen()
    setEntsperrt(false)
    try {
      await sperreApi.sperren()
    } catch {
      // Der Nachweis ist bereits verworfen — mehr braucht „sperren" nicht.
    }
  }, [])

  return (
    <SperreContext.Provider
      value={{ pinGesetzt, entsperrt, entsperren, sperren, aktualisieren }}
    >
      {children}
      <Modal isOpen={offen} onClose={() => schliessen(false)} title="Einstellungen entsperren" size="sm">
        <div className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Für diese Anlage ist eine PIN hinterlegt. Ansehen geht ohne — zum Ändern
            brauchst du sie einmal pro Browser-Sitzung.
          </p>
          <Input
            type="password"
            value={pin}
            autoFocus
            onChange={(e) => setPin(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && pin && !laeuft) void absenden()
            }}
            placeholder="PIN"
          />
          {fehler && <Alert type="error">{fehler}</Alert>}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => schliessen(false)}>
              Abbrechen
            </Button>
            <Button variant="primary" onClick={() => void absenden()} disabled={!pin} loading={laeuft}>
              Entsperren
            </Button>
          </div>
        </div>
      </Modal>
    </SperreContext.Provider>
  )
}

export function useSperre(): SperreContextType {
  const ctx = useContext(SperreContext)
  if (!ctx) {
    // Außerhalb des Providers (z. B. in einem isolierten Test-Render) ist nichts
    // gesperrt — sonst blendete ein Test Bedienelemente aus, die es real gibt.
    return {
      pinGesetzt: false,
      entsperrt: true,
      entsperren: async () => false,
      sperren: async () => {},
      aktualisieren: async () => {},
    }
  }
  return ctx
}
