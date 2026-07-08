import { Card, Select, Input } from '../../ui'
import type { AnalyzeResult } from '../../../api/customImport'

/**
 * ImportOptionen — Einheit / Dezimalzeichen / kombinierte Datumsspalte
 * (CustomImportWizard, Schritt 2). Ausgelagert aus dem Wizard-Shell (Split beim
 * V4-Umbau); reine SoT-Controls.
 */

const EINHEIT_OPTIONEN = [
  { value: 'kwh', label: 'Kilowattstunden (kWh)' },
  { value: 'wh', label: 'Wattstunden (Wh) → wird in kWh umgerechnet' },
  { value: 'mwh', label: 'Megawattstunden (MWh) → wird in kWh umgerechnet' },
]

const DEZIMAL_OPTIONEN = [
  { value: 'auto', label: 'Automatisch erkennen' },
  { value: 'punkt', label: 'Punkt (1234.56)' },
  { value: 'komma', label: 'Komma (1234,56)' },
]

export default function ImportOptionen({
  einheit,
  onEinheit,
  dezimalzeichen,
  onDezimalzeichen,
  datumSpalte,
  onDatumSpalte,
  datumFormat,
  onDatumFormat,
  spalten,
}: {
  einheit: string
  onEinheit: (v: string) => void
  dezimalzeichen: string
  onDezimalzeichen: (v: string) => void
  datumSpalte: string | null
  onDatumSpalte: (v: string | null) => void
  datumFormat: string | null
  onDatumFormat: (v: string | null) => void
  spalten: AnalyzeResult['spalten']
}) {
  return (
    <Card>
      <div className="p-4">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
          Optionen
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Select
            label="Einheit der Werte"
            value={einheit}
            onChange={(e) => onEinheit(e.target.value)}
            options={EINHEIT_OPTIONEN}
          />
          <Select
            label="Dezimalzeichen"
            value={dezimalzeichen}
            onChange={(e) => onDezimalzeichen(e.target.value)}
            options={DEZIMAL_OPTIONEN}
          />
        </div>

        {/* Kombinierte Datumsspalte (optional) */}
        <div className="mt-4">
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <Select
                label="Kombinierte Datumsspalte (optional, falls Jahr+Monat in einer Spalte)"
                value={datumSpalte || ''}
                onChange={(e) => onDatumSpalte(e.target.value || null)}
                placeholder="Nicht verwendet (separate Jahr/Monat-Spalten)"
                options={spalten.map((col) => ({ value: col.name, label: col.name }))}
              />
            </div>
            {datumSpalte && (
              <div className="w-36">
                <Input
                  aria-label="Datumsformat"
                  value={datumFormat || ''}
                  onChange={(e) => onDatumFormat(e.target.value || null)}
                  placeholder="z.B. %Y-%m"
                />
              </div>
            )}
          </div>
          {datumSpalte && (
            <p className="mt-1 text-xs text-gray-500">
              Formate: %Y-%m (2024-01), %m/%Y (01/2024), %d.%m.%Y (15.01.2024)
            </p>
          )}
        </div>
      </div>
    </Card>
  )
}
