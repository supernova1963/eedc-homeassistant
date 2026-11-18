/**
 * ZaehlerGetauschtDialog — Einstieg «Zähler getauscht (gleiche Quelle)» am Feld (Sensorwechsel mit Grund, Bauplan B-2 letzter
 * Satz, G-1, §9 Nr. 26; Sitzung 3b).
 *
 * Die Quelle bleibt, der Zähler dahinter wurde getauscht. Der Dialog fragt das Backend, welcher Weg zur Stunde des Tauschs
 * gilt (`…/zaehler-getauscht/pruefen`): in der Spiegel-Zeit eines Zählers aus Home Assistant der Weg in Home Assistant
 * («Wert anpassen», eedc trägt nichts ein); bei MQTT «Eigene Summe» und ohne Spiegel trägt «Eintragen» die Fortsetzung ein
 * (`…/zaehler-getauscht`); vor dem ersten eigenen Wert und in verworfener Zeit nennt ein Satz, warum nichts einzutragen ist.
 * Sätze kommen aus dem Backend; der Client rechnet nichts.
 */
import { useEffect, useState } from 'react'
import { Alert, Button, Input, Modal } from '../ui'
import { datenquellenApi, type ZaehlerGetauschtAntwort } from '../../api/datenquellen'

export const ZG_TITEL = 'Zähler getauscht (gleiche Quelle)'
export const ZG_ZEIT_LABEL = 'Getauscht am'
export const ZG_ZEIT_HINWEIS = 'Wann der neue Zähler zu zählen begann.'
export const ZG_EINGETRAGEN = 'Eingetragen.'

/** Jetzt als Wert eines `datetime-local`-Felds (örtlich). */
function jetztLokal(): string {
  const d = new Date()
  const zwei = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${zwei(d.getMonth() + 1)}-${zwei(d.getDate())}T${zwei(d.getHours())}:${zwei(d.getMinutes())}`
}

export default function ZaehlerGetauschtDialog({ anlageId, feldId, feldLabel, onClose }: {
  anlageId: number
  feldId: string
  feldLabel: string
  onClose: () => void
}) {
  const [zeit, setZeit] = useState(jetztLokal)
  const [antwort, setAntwort] = useState<ZaehlerGetauschtAntwort | null>(null)
  const [laeuft, setLaeuft] = useState(false)
  const [fehler, setFehler] = useState<string | null>(null)

  useEffect(() => {
    let aus = false                                  // eine überholte Antwort (frühere Eingabe) wird verworfen
    setFehler(null)
    datenquellenApi.pruefeZaehlerGetauscht(anlageId, feldId, zeit || undefined)
      .then((a) => { if (!aus) setAntwort(a) })
      .catch((e) => { if (!aus) setFehler(e instanceof Error ? e.message : 'Prüfen fehlgeschlagen') })
    return () => { aus = true }
  }, [anlageId, feldId, zeit])

  const eintragen = () => {
    setLaeuft(true)
    datenquellenApi.zaehlerGetauscht(anlageId, feldId, zeit || undefined)
      .then(setAntwort)
      .catch((e) => setFehler(e instanceof Error ? e.message : 'Eintragen fehlgeschlagen'))
      .finally(() => setLaeuft(false))
  }

  // Der Weg hängt an der Quelle zur Stunde des Tauschs — der Zeitpunkt bleibt wählbar, solange das Feld Werte und eine
  // Quelle hat und nichts eingetragen ist.
  const zeitWaehlbar = !!antwort && antwort.weg !== 'ohne_werte' && antwort.weg !== 'keine_quelle' && !antwort.eingetragen
  return (
    <Modal isOpen onClose={onClose} title={`${ZG_TITEL} — ${feldLabel}`} size="md">
      <div className="space-y-3" data-zaehler-getauscht={feldId}>
        {zeitWaehlbar && (
          <Input type="datetime-local" label={ZG_ZEIT_LABEL} hint={ZG_ZEIT_HINWEIS} value={zeit}
            onChange={(e) => setZeit(e.target.value)} data-getauscht-am />
        )}
        {antwort && (
          <div className="space-y-1 text-sm text-gray-700 dark:text-gray-200" data-zg-weg={antwort.weg}>
            {antwort.saetze.map((s, i) => <p key={i}>{s}</p>)}
          </div>
        )}
        {antwort?.eingetragen && <Alert type="success">{ZG_EINGETRAGEN}</Alert>}
        {fehler && <Alert type="error">{fehler}</Alert>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Schließen</Button>
          {antwort?.eintragen && !antwort.eingetragen && (
            <Button type="button" onClick={eintragen} loading={laeuft} disabled={laeuft} data-zg-eintragen>Eintragen</Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
