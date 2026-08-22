/**
 * Einstellungs-Sperre — der Schalter in den Anlagen-Stammdaten.
 *
 * **Warum hier und nicht unter „System".** Gernots Vorgabe (2026-08-22): Wenn es eine
 * PIN gibt, dann aktivierbar in den Anlagen-Stammdaten — dort, wo man ohnehin einrichtet.
 *
 * **Warum der Text „für diese eedc-Installation" sagt.** Die Sperre gilt instanzweit,
 * nicht je Anlage. Das war eine bewusste Entscheidung: Von den schreibenden Aufrufen
 * nennen 45 überhaupt keine Anlage (MQTT-Broker, HA-Verbindung, Neustart, Demo-Daten …).
 * Eine Sperre „pro Anlage" hätte für die ein Schlupfloch oder eine Ersatzregel gebraucht
 * und wäre damit ein Versprechen gewesen, das sie nur halb hält. Bei einer Anlage — dem
 * Normalfall — ist ohnehin beides dasselbe. Was bleibt, ist die Pflicht, es an dieser
 * Stelle nicht zu verschweigen.
 */

import { useState } from 'react'
import { Lock, Unlock } from 'lucide-react'

import { sperreApi } from '../../api/sperre'
import { useSperre } from '../../context/SperreContext'
import { Alert, Button, Input } from '../ui'

export default function SperreEinstellung() {
  const { pinGesetzt, entsperrt, sperren, aktualisieren } = useSperre()
  const [pin, setPin] = useState('')
  const [wiederholung, setWiederholung] = useState('')
  const [fehler, setFehler] = useState<string | null>(null)
  const [hinweis, setHinweis] = useState<string | null>(null)
  const [laeuft, setLaeuft] = useState(false)

  const zuruecksetzen = () => {
    setPin('')
    setWiederholung('')
    setFehler(null)
  }

  const speichern = async () => {
    if (pin !== wiederholung) {
      setFehler('Die beiden Eingaben stimmen nicht überein.')
      return
    }
    setLaeuft(true)
    setFehler(null)
    try {
      await sperreApi.setzePin(pin)
      await aktualisieren()
      zuruecksetzen()
      setHinweis('PIN gespeichert. Zum Ändern von Einstellungen wird sie ab jetzt einmal je Browser-Sitzung abgefragt.')
    } catch (e) {
      setFehler(e instanceof Error ? e.message : 'PIN konnte nicht gespeichert werden.')
    } finally {
      setLaeuft(false)
    }
  }

  const entfernen = async () => {
    setLaeuft(true)
    setFehler(null)
    try {
      await sperreApi.entfernePin()
      await aktualisieren()
      setHinweis('PIN entfernt. Einstellungen sind wieder ohne Abfrage änderbar.')
    } catch (e) {
      setFehler(e instanceof Error ? e.message : 'PIN konnte nicht entfernt werden.')
    } finally {
      setLaeuft(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
          {pinGesetzt ? <Lock className="h-4 w-4" /> : <Unlock className="h-4 w-4" />}
          Einstellungen mit einer PIN schützen
        </div>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
          Ohne PIN ändert sich nichts — alles bleibt wie bisher. Mit PIN kann jeder
          weiterhin alle Auswertungen ansehen, aber zum <strong>Ändern</strong> ist sie
          einmal je Browser-Sitzung nötig. Gedacht für Haushalte, in denen mehrere
          Personen auf eedc schauen. Die Darstellung (hell/dunkel) bleibt immer frei.
        </p>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-500">
          Die PIN gilt für diese eedc-Installation, nicht nur für diese Anlage.
        </p>
      </div>

      {hinweis && <Alert type="success" onClose={() => setHinweis(null)}>{hinweis}</Alert>}
      {fehler && <Alert type="error">{fehler}</Alert>}

      {pinGesetzt && !entsperrt ? (
        <Alert type="info">
          Zum Ändern oder Entfernen der PIN muss diese Sitzung entsperrt sein. Der
          nächste Änderungsversuch fragt danach.
        </Alert>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <Input
            label={pinGesetzt ? 'Neue PIN' : 'PIN'}
            type="password"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            hint="Mindestens vier Zeichen."
          />
          <Input
            label="Wiederholen"
            type="password"
            value={wiederholung}
            onChange={(e) => setWiederholung(e.target.value)}
          />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {(!pinGesetzt || entsperrt) && (
          <Button
            variant="primary"
            size="sm"
            onClick={() => void speichern()}
            disabled={pin.length < 4 || wiederholung.length < 4}
            loading={laeuft}
          >
            {pinGesetzt ? 'PIN ändern' : 'PIN setzen'}
          </Button>
        )}
        {pinGesetzt && entsperrt && (
          <>
            <Button variant="secondary" size="sm" onClick={() => void entfernen()} loading={laeuft}>
              PIN entfernen
            </Button>
            <Button variant="ghost" size="sm" onClick={() => void sperren()}>
              Jetzt sperren
            </Button>
          </>
        )}
      </div>

      {pinGesetzt && (
        <p className="text-xs text-gray-500 dark:text-gray-500">
          <strong>PIN vergessen?</strong> Im Home-Assistant-Add-on setzt die Option{' '}
          <code>einstellungen_pin_zuruecksetzen</code> sie beim nächsten Start zurück; im
          Standalone-Betrieb die Umgebungsvariable <code>EEDC_PIN_RESET=1</code>. Beides
          verlangt Zugriff auf die Maschine — bewusst, denn eine Reset-Adresse, die jeder
          aufrufen kann, wäre keine Sperre.
        </p>
      )}
    </div>
  )
}
