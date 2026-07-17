/**
 * DatenquellenHaPicker — HA-Sensor-Auswahl für die Datenquellen-Zuordnung (Schritt B).
 *
 * SoT: docs/drafts/KONZEPT-DATENQUELLEN-V4.md §2b1. Listet die Entities der
 * aktiven HA-Verbindung (Supervisor ODER Remote-HA per LL-Token — verbindungs-
 * transparent über `/datenquellen/{id}/ha/sensoren`) mit Suche; Klick wählt die
 * Entity. Welche Quell-Kennung (`ha_app`/`ha_connector`) persistiert wird,
 * bestimmt der Server anhand der aktiven Verbindung.
 */
import { useState, useEffect, useMemo } from 'react'
import { Search, Loader2, Check, AlertTriangle } from 'lucide-react'
import { Modal, Input, Button, Alert } from '../ui'
import { datenquellenApi, type HaSensor } from '../../api/datenquellen'

interface Props {
  isOpen: boolean
  anlageId: number
  feldLabel: string
  /** Erwartete Feld-Einheit (§2i-Einheiten-Warnung beim Wählen). */
  feldEinheit?: string
  initialEntity: string | null
  onClose: () => void
  onSpeichern: (entityId: string) => void
}

// Dimensions-Klasse (Spiegel von core.field_definitions.einheit_klasse) — nur
// Leistung↔Energie, um die #200-Verwechslung beim Wählen sichtbar zu machen.
function einheitKlasse(unit: string | null | undefined): 'leistung' | 'energie' | null {
  if (unit === 'W' || unit === 'kW' || unit === 'MW') return 'leistung'
  if (unit === 'kWh' || unit === 'Wh' || unit === 'MWh') return 'energie'
  return null
}

export default function DatenquellenHaPicker({
  isOpen, anlageId, feldLabel, feldEinheit, initialEntity, onClose, onSpeichern,
}: Props) {
  const erwartet = einheitKlasse(feldEinheit)
  const [sensoren, setSensoren] = useState<HaSensor[]>([])
  const [loading, setLoading] = useState(true)
  const [fehler, setFehler] = useState<string | null>(null)
  const [suche, setSuche] = useState('')

  useEffect(() => {
    if (!isOpen) return
    setLoading(true)
    setFehler(null)
    datenquellenApi.haSensoren(anlageId)
      .then((r) => {
        if (r.fehler) setFehler(r.fehler)
        setSensoren(r.sensoren)
      })
      .catch((e) => setFehler(e instanceof Error ? e.message : 'Laden fehlgeschlagen'))
      .finally(() => setLoading(false))
  }, [isOpen, anlageId])

  const gefiltert = useMemo(() => {
    const q = suche.trim().toLowerCase()
    if (!q) return sensoren
    return sensoren.filter((s) =>
      s.entity_id.toLowerCase().includes(q) || (s.friendly_name ?? '').toLowerCase().includes(q))
  }, [sensoren, suche])

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`HA-Sensor für „${feldLabel}"`} size="xl">
      <div className="space-y-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-gray-500" />
          <Input
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
            placeholder="Entity oder Name suchen …"
            className="pl-9"
            aria-label="HA-Sensor suchen"
          />
        </div>

        {loading && (
          <p className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Sensoren werden geladen …
          </p>
        )}
        {fehler && <Alert type="error">{fehler}</Alert>}
        {!loading && !fehler && gefiltert.length === 0 && (
          <p className="text-sm text-gray-500 dark:text-gray-400">Keine passenden Sensoren gefunden.</p>
        )}

        {!loading && gefiltert.length > 0 && (
          <div className="max-h-96 divide-y divide-gray-100 overflow-y-auto rounded-lg border border-gray-200 dark:divide-gray-800 dark:border-gray-700">
            {gefiltert.map((s) => {
              const aktiv = s.entity_id === initialEntity
              // §2i: Dimensions-Mismatch (kWh-Sensor für W-Feld etc.) beim Wählen.
              const sensorKlasse = einheitKlasse(s.unit)
              const mismatch = erwartet != null && sensorKlasse != null && sensorKlasse !== erwartet
              return (
                <Button
                  key={s.entity_id}
                  type="button"
                  variant="ghost"
                  onClick={() => onSpeichern(s.entity_id)}
                  className="!w-full !justify-start !rounded-none"
                >
                  <Check className={`h-4 w-4 flex-shrink-0 ${aktiv ? 'text-green-600 dark:text-green-400' : 'text-transparent'}`} />
                  <span className="ml-2 min-w-0 flex-1 text-left">
                    <span className="block truncate font-mono text-xs text-gray-800 dark:text-gray-200">{s.entity_id}</span>
                    <span className="block truncate text-xs text-gray-500 dark:text-gray-400">
                      {s.friendly_name ?? '—'}{s.unit ? ` · ${s.unit}` : ''}{s.state != null ? ` · ${s.state}` : ''}
                    </span>
                    {mismatch && (
                      <span className="mt-0.5 flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                        <AlertTriangle className="h-3 w-3 shrink-0" />
                        Einheit {s.unit} passt nicht zu {feldEinheit} ({erwartet === 'leistung' ? 'Leistungssensor erwartet' : 'kWh-Zähler erwartet'})
                      </span>
                    )}
                  </span>
                </Button>
              )
            })}
          </div>
        )}

        <div className="flex justify-end">
          <Button type="button" variant="secondary" onClick={onClose}>Abbrechen</Button>
        </div>
      </div>
    </Modal>
  )
}
