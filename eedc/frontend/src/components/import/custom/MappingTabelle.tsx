import { ArrowRight, ArrowUpDown } from 'lucide-react'
import { Card, Select } from '../../ui'
import type { AnalyzeResult } from '../../../api/customImport'
import { mappingZielOptionen } from '../customFelder'

/**
 * MappingTabelle — Spalten-zu-eedc-Feld-Zuordnung (CustomImportWizard, Schritt 2).
 * Ausgelagert aus dem Wizard-Shell (Split beim V4-Umbau). SoT-`Select` je Zeile,
 * Zielfeld-Optionen aus {@link mappingZielOptionen}; der Invertieren-Schalter
 * dreht das Vorzeichen einer Wertspalte.
 */
export default function MappingTabelle({
  analysis,
  mappings,
  invertierungen,
  onSetMapping,
  onToggleInvert,
}: {
  analysis: AnalyzeResult
  mappings: Record<string, string>
  invertierungen: Record<string, boolean>
  onSetMapping: (spalte: string, feld: string) => void
  onToggleInvert: (spalte: string) => void
}) {
  return (
    <Card>
      <div className="p-4">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
          Spalten zuordnen
        </h3>
        {(analysis.investitions_spalten?.length ?? 0) > 0 ? (
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            Spalten die weiter unten als <span className="text-green-600 dark:text-green-400 font-medium">eedc-Investitions-Spalten erkannt</span> sind,
            stehen hier auf <em>– Ignorieren –</em> und müssen nicht zugeordnet werden — sie werden automatisch importiert.
            Alle anderen Spalten können hier manuell zugeordnet werden.
          </p>
        ) : (
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            Weise jeder Spalte ein eedc-Zielfeld zu. Nicht benötigte Spalten auf <em>– Ignorieren –</em> lassen.
          </p>
        )}
        <div className="space-y-2">
          {analysis.spalten.map((col) => {
            const currentMapping = mappings[col.name] || ''
            return (
              <div key={col.name} className="flex items-center gap-3 py-2 border-b border-gray-100 dark:border-gray-800 last:border-0">
                {/* Quelltitel + Samples */}
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm text-gray-900 dark:text-white truncate">
                    {col.name}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                    {col.sample_values.slice(0, 3).join(' | ')}
                  </div>
                </div>

                <ArrowRight className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />

                {/* Vorzeichen invertieren */}
                {currentMapping && currentMapping !== 'jahr' && currentMapping !== 'monat' && (
                  <button
                    type="button"
                    onClick={() => onToggleInvert(col.name)}
                    title={invertierungen[col.name] ? 'Vorzeichen wird invertiert (±→+) — klicken zum Deaktivieren' : 'Vorzeichen invertieren (negative Werte werden positiv)'}
                    className={`flex-shrink-0 p-1 rounded transition-colors ${
                      invertierungen[col.name]
                        ? 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/30'
                        : 'text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400'
                    }`}
                  >
                    <ArrowUpDown className="w-4 h-4" />
                  </button>
                )}

                {/* Zielfeld-Auswahl (SoT) */}
                <div className="w-56 shrink-0">
                  <Select
                    value={currentMapping}
                    onChange={(e) => onSetMapping(col.name, e.target.value)}
                    placeholder="– Ignorieren –"
                    options={mappingZielOptionen(analysis, mappings, currentMapping)}
                    aria-label={`Zielfeld für ${col.name}`}
                    className={currentMapping ? 'border-primary-400 dark:border-primary-600' : ''}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </Card>
  )
}
