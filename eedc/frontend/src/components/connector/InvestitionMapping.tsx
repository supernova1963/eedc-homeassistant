import { useState, useEffect } from 'react'
import { Loader2, CheckCircle } from 'lucide-react'
import { Card, Button, Select, Alert } from '../ui'
import { connectorApi } from '../../api/connector'
import type { MeterSnapshot, FieldInvMap } from '../../api/connector'
import type { Investition, InvestitionTyp } from '../../types'

/**
 * InvestitionMapping — ordnet gemessene Connector-Größen (PV/Speicher/Wallbox)
 * je einer Investition zu (aus ConnectorSetupWizard ausgelagert beim V4-Umbau).
 * SoT-`Select` je Mess-Kategorie; nur Kategorien, die das Gerät auch misst.
 */

type MappingKategorie = 'pv' | 'speicher' | 'wallbox'

const KATEGORIEN: {
  key: MappingKategorie
  label: string
  typen: InvestitionTyp[]
  present: (s: MeterSnapshot) => boolean
}[] = [
  { key: 'pv', label: 'PV-Erzeugung', typen: ['pv-module', 'balkonkraftwerk'], present: s => s.pv_erzeugung_kwh != null },
  { key: 'speicher', label: 'Speicher (Ladung/Entladung)', typen: ['speicher'], present: s => s.batterie_ladung_kwh != null || s.batterie_entladung_kwh != null },
  { key: 'wallbox', label: 'Wallbox (Ladung)', typen: ['wallbox'], present: s => s.wallbox_ladung_kwh != null },
]

export default function InvestitionMapping({
  anlageId,
  investitionen,
  snapshot,
  initialMap,
  onSaved,
  onError,
}: {
  anlageId: number
  investitionen: Investition[]
  snapshot: MeterSnapshot | null
  initialMap: FieldInvMap
  onSaved: (map: FieldInvMap) => void
  onError: (msg: string | null) => void
}) {
  const [map, setMap] = useState<FieldInvMap>(initialMap)
  const [isSaving, setIsSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setMap(initialMap)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(initialMap)])

  // Nur Kategorien anzeigen, die das Gerät auch misst (aus letztem Snapshot).
  // Ohne Snapshot zeigen wir alle, damit die Zuordnung trotzdem möglich ist.
  const aktiveKategorien = KATEGORIEN.filter(k => !snapshot || k.present(snapshot))

  if (aktiveKategorien.length === 0) return null

  async function handleSave() {
    setIsSaving(true)
    setSaved(false)
    onError(null)
    try {
      const res = await connectorApi.saveMapping(anlageId, map)
      onSaved(res.field_inv_map)
      setSaved(true)
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Zuordnung fehlgeschlagen')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Card>
      <div className="p-5">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
          Zuordnung zu Investitionen
        </h2>
        <Alert type="info" className="mb-4">
          Ordne jede gemessene Größe der passenden Investition zu, damit die
          kWh-Werte gerätegenau in „Heute" und den Monatsabschluss einfließen.
          Einspeisung und Netzbezug gelten anlagenweit und brauchen keine Zuordnung.
        </Alert>

        <div className="space-y-3">
          {aktiveKategorien.map(kat => {
            const optionen = investitionen.filter(i => kat.typen.includes(i.typ))
            return (
              <div key={kat.key} className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:items-center">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {kat.label}
                </span>
                {optionen.length > 0 ? (
                  <Select
                    aria-label={`Investition für ${kat.label}`}
                    value={map[kat.key] != null ? String(map[kat.key]) : ''}
                    onChange={e => {
                      const v = e.target.value ? Number(e.target.value) : null
                      setMap(prev => ({ ...prev, [kat.key]: v }))
                      setSaved(false)
                    }}
                    placeholder="— keine Zuordnung —"
                    options={optionen.map(i => ({ value: String(i.id), label: i.bezeichnung }))}
                  />
                ) : (
                  <span className="text-sm text-gray-400 dark:text-gray-500">
                    Keine passende Investition vorhanden
                  </span>
                )}
              </div>
            )
          })}
        </div>

        <div className="flex items-center gap-3 mt-4">
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving ? (
              <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Speichere…</>
            ) : (
              'Zuordnung speichern'
            )}
          </Button>
          {saved && (
            <span className="flex items-center gap-1 text-sm text-green-600 dark:text-green-400">
              <CheckCircle className="h-4 w-4" /> Gespeichert
            </span>
          )}
        </div>
      </div>
    </Card>
  )
}
