import type { MeterSnapshot } from '../../api/connector'
import { formatKwh } from './connectorFormat'

/**
 * SnapshotTable — Zählerstände eines Connector-Snapshots als Definitionsliste
 * (aus ConnectorSetupWizard ausgelagert). Zeigt nur Felder mit Wert.
 */
export default function SnapshotTable({ snapshot }: { snapshot: MeterSnapshot }) {
  const fields = [
    { key: 'pv_erzeugung_kwh', label: 'PV-Erzeugung' },
    { key: 'einspeisung_kwh', label: 'Einspeisung' },
    { key: 'netzbezug_kwh', label: 'Netzbezug' },
    { key: 'batterie_ladung_kwh', label: 'Batterie Ladung' },
    { key: 'batterie_entladung_kwh', label: 'Batterie Entladung' },
    { key: 'wallbox_ladung_kwh', label: 'Wallbox Ladung' },
  ] as const

  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        {fields.map(({ key, label }) => {
          const val = snapshot[key]
          if (val == null) return null
          return (
            <div key={key} className="contents">
              <dt className="text-gray-500 dark:text-gray-400">{label}</dt>
              <dd className="font-medium text-gray-900 dark:text-white font-mono">
                {formatKwh(val)}
              </dd>
            </div>
          )
        })}
      </dl>
    </div>
  )
}
