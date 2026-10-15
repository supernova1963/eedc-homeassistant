/**
 * Parameter-Editor der Werkbank-Operation „Werte vor dem Sensorbeginn verwerfen" (HA-Bauform S3, E-S3-5).
 *
 * Auswahl: die Felder mit Sensortausch (mindestens zwei Quellen) aus `GET /repair/kanal-auswahl` — je Feld die Quellen
 * mit ihrem Beginn. Zeitpunkt: Tag (DatumFeld-SoT) + volle Stunde, vorbelegt mit dem Beginn der jüngsten Quelle (Backend).
 * Der Client rechnet nichts: Vorbelegung, Quellen und die Vorschau-Sätze kommen vom Backend; hier wird nur die
 * `YYYY-MM-DDTHH:MM`-Zeichenkette zerlegt und wieder zusammengesetzt.
 */
import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'

import { DatumFeld, Select } from '../ui'
import { repairApi, type KanalAuswahlEintrag } from '../../api/repair'
import { compareTyp } from '../../lib/constants'
import { formatDatumZeit } from '../../lib/datum'

export interface VerwerfenWerte {
  kanal: string
  datum: string
  stunde: string
}

export const VERWERFEN_LEER: VerwerfenWerte = { kanal: '', datum: '', stunde: '00' }

/** `{kanal, zeitpunkt}` für `/repair/plan` — die Stunde ist immer voll (`HH:00`). */
export function verwerfenParams(w: VerwerfenWerte): Record<string, unknown> {
  return { kanal: w.kanal, zeitpunkt: `${w.datum}T${w.stunde}:00` } /* de-de-allow: API-Parameter (ISO), keine Anzeige */
}

const STUNDEN = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'))

/** Anlagen-Felder (ohne Gerät) zuerst, dann die Geräte in der Typ-Reihenfolge. */
function sortiere(kanaele: KanalAuswahlEintrag[]): KanalAuswahlEintrag[] {
  return [...kanaele].sort((a, b) =>
    Number(a.typ !== null) - Number(b.typ !== null) || compareTyp(a, b) || a.label.localeCompare(b.label, 'de'))
}

function vorbelegt(eintrag: KanalAuswahlEintrag): VerwerfenWerte {
  const [datum, zeit] = eintrag.vorbelegung.split('T')
  return { kanal: eintrag.key, datum, stunde: zeit.slice(0, 2) }
}

interface Props {
  anlageId: number
  werte: VerwerfenWerte
  onChange: (w: VerwerfenWerte) => void
  disabled: boolean
}

export function VerwerfenParams({ anlageId, werte, onChange, disabled }: Props) {
  const [kanaele, setKanaele] = useState<KanalAuswahlEintrag[] | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)

  useEffect(() => {
    let aktiv = true
    setKanaele(null)
    setFehler(null)
    repairApi.kanalAuswahl(anlageId)
      .then((res) => { if (aktiv) setKanaele(sortiere(res.kanaele)) })
      .catch((e) => { if (aktiv) setFehler(e instanceof Error ? e.message : 'Auswahl konnte nicht geladen werden') })
    return () => { aktiv = false }
  }, [anlageId])

  if (fehler) return <p className="text-sm text-red-600 dark:text-red-400">{fehler}</p>
  if (kanaele === null) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        <Loader2 className="inline h-4 w-4 mr-1 animate-spin" /> Felder werden geladen …
      </p>
    )
  }
  if (kanaele.length === 0) {
    return (
      <p className="text-sm text-gray-600 dark:text-gray-400">
        Kein Feld dieser Anlage hat einen Sensortausch — es gibt keine Werte eines alten Sensors zu verwerfen.
      </p>
    )
  }
  const gewaehlt = kanaele.find((k) => k.key === werte.kanal)
  return (
    <div className="space-y-3">
      <Select
        id="verwerfen-feld"
        label="Feld"
        value={werte.kanal}
        onChange={(e) => {
          const eintrag = kanaele.find((k) => k.key === e.target.value)
          onChange(eintrag ? vorbelegt(eintrag) : VERWERFEN_LEER)
        }}
        disabled={disabled}
        placeholder="Feld mit Sensortausch wählen"
        options={kanaele.map((k) => ({ value: k.key, label: k.label }))}
      />
      {gewaehlt && (
        <ul className="text-xs text-gray-600 dark:text-gray-400 space-y-0.5">
          {gewaehlt.quellen.map((q) => (
            <li key={q.gueltig_ab}>
              <span className="font-mono">{q.statistic_id ?? q.familie}</span> ab {formatDatumZeit(q.gueltig_ab)}
              {q.verworfen_am && <> — Werte davor verworfen am {formatDatumZeit(q.verworfen_am)}</>}
            </li>
          ))}
        </ul>
      )}
      {gewaehlt && (
        <div className="grid grid-cols-2 gap-2 items-start">
          <DatumFeld
            label="Verwerfen vor (Tag)"
            value={werte.datum}
            onChange={(v) => onChange({ ...werte, datum: v })}
            disabled={disabled}
          />
          <Select
            id="verwerfen-stunde"
            label="Uhrzeit"
            value={werte.stunde}
            onChange={(e) => onChange({ ...werte, stunde: e.target.value })}
            disabled={disabled}
            options={STUNDEN.map((h) => ({ value: h, label: `${h}:00` }))}
          />
        </div>
      )}
      {gewaehlt && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Vorbelegt ist der Beginn des jüngsten Sensors. Verworfen wird nur dieses Feld; Monate mit Abschluss bleiben
          unberührt. Die Vorschau nennt Quellen, Tage und Monate, bevor etwas geändert wird.
        </p>
      )}
    </div>
  )
}
