import { useState } from 'react'
import { Plus, Trash2, ChevronDown, ChevronRight, ExternalLink } from 'lucide-react'
import { Button, Input } from '../ui'
import type { VersorgerDaten, Versorger, Zaehler } from '../../types'

interface VersorgerSectionProps {
  value: VersorgerDaten
  onChange: (data: VersorgerDaten) => void
}

type VersorgerTyp = 'strom' | 'gas' | 'wasser'

const VERSORGER_TYPEN: { key: VersorgerTyp; label: string; icon: string }[] = [
  { key: 'strom', label: 'Strom', icon: '⚡' },
  { key: 'gas', label: 'Gas', icon: '🔥' },
  { key: 'wasser', label: 'Wasser', icon: '💧' },
]

const emptyVersorger = (): Versorger => ({
  name: '',
  kundennummer: '',
  portal_url: '',
  notizen: '',
  zaehler: [],
})

const emptyZaehler = (): Zaehler => ({
  bezeichnung: '',
  nummer: '',
  notizen: '',
})

export default function VersorgerSection({ value, onChange }: VersorgerSectionProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const toggleExpand = (key: string) => {
    setExpanded(prev => ({ ...prev, [key]: !prev[key] }))
  }

  const updateVersorger = (typ: VersorgerTyp, versorger: Versorger | undefined) => {
    const newData = { ...value }
    if (versorger) {
      newData[typ] = versorger
    } else {
      delete newData[typ]
    }
    onChange(newData)
  }

  const addVersorger = (typ: VersorgerTyp) => {
    updateVersorger(typ, emptyVersorger())
    setExpanded(prev => ({ ...prev, [typ]: true }))
  }

  const removeVersorger = (typ: VersorgerTyp) => {
    updateVersorger(typ, undefined)
  }

  const updateVersorgerField = (typ: VersorgerTyp, field: keyof Versorger, fieldValue: string) => {
    const current = value[typ] || emptyVersorger()
    updateVersorger(typ, { ...current, [field]: fieldValue })
  }

  const addZaehler = (typ: VersorgerTyp) => {
    const current = value[typ] || emptyVersorger()
    updateVersorger(typ, {
      ...current,
      zaehler: [...current.zaehler, emptyZaehler()],
    })
  }

  const updateZaehler = (typ: VersorgerTyp, index: number, zaehler: Zaehler) => {
    const current = value[typ] || emptyVersorger()
    const newZaehler = [...current.zaehler]
    newZaehler[index] = zaehler
    updateVersorger(typ, { ...current, zaehler: newZaehler })
  }

  const removeZaehler = (typ: VersorgerTyp, index: number) => {
    const current = value[typ] || emptyVersorger()
    const newZaehler = current.zaehler.filter((_, i) => i !== index)
    updateVersorger(typ, { ...current, zaehler: newZaehler })
  }

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-gray-900 dark:text-white">
        Versorger & Zähler
      </h3>

      <div className="space-y-3">
        {VERSORGER_TYPEN.map(({ key, label, icon }) => {
          const versorger = value[key]
          const isExpanded = expanded[key]

          if (!versorger) {
            return (
              <button
                key={key}
                type="button"
                onClick={() => addVersorger(key)}
                className="w-full p-3 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg text-gray-500 dark:text-gray-400 hover:border-blue-400 hover:text-blue-500 transition-colors flex items-center justify-center gap-2"
              >
                <Plus className="w-4 h-4" />
                <span>{icon} {label}-Versorger hinzufügen</span>
              </button>
            )
          }

          return (
            <div
              key={key}
              className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
            >
              {/* Header */}
              <div
                className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 cursor-pointer"
                onClick={() => toggleExpand(key)}
              >
                <div className="flex items-center gap-2">
                  {isExpanded ? (
                    <ChevronDown className="w-4 h-4 text-gray-500" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-gray-500" />
                  )}
                  <span className="text-lg">{icon}</span>
                  <span className="font-medium text-gray-900 dark:text-white">
                    {versorger.name || label}
                  </span>
                  {versorger.zaehler.length > 0 && (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      ({versorger.zaehler.length} Zähler)
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    removeVersorger(key)
                  }}
                  className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                  title="Versorger entfernen"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              {/* Content */}
              {isExpanded && (
                <div className="p-4 space-y-4">
                  {/* Versorger-Daten */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <Input
                      label="Versorger-Name"
                      value={versorger.name}
                      onChange={(e) => updateVersorgerField(key, 'name', e.target.value)}
                      placeholder={`z.B. Stadtwerke ${label}`}
                    />
                    <Input
                      label="Kundennummer"
                      value={versorger.kundennummer}
                      onChange={(e) => updateVersorgerField(key, 'kundennummer', e.target.value)}
                      placeholder="z.B. 12345678"
                    />
                    <div className="md:col-span-2">
                      <Input
                        label="Kundenportal-URL"
                        value={versorger.portal_url || ''}
                        onChange={(e) => updateVersorgerField(key, 'portal_url', e.target.value)}
                        placeholder="https://kundenportal.beispiel.de"
                      />
                      {versorger.portal_url && (
                        <a
                          href={versorger.portal_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 mt-1 text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400"
                        >
                          <ExternalLink className="w-3 h-3" />
                          Portal öffnen
                        </a>
                      )}
                    </div>
                    <div className="md:col-span-2">
                      <Input
                        label="Notizen"
                        value={versorger.notizen || ''}
                        onChange={(e) => updateVersorgerField(key, 'notizen', e.target.value)}
                        placeholder="Optionale Anmerkungen..."
                      />
                    </div>
                  </div>

                  {/* Zähler */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Zähler
                      </h4>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => addZaehler(key)}
                      >
                        <Plus className="w-4 h-4 mr-1" />
                        Zähler
                      </Button>
                    </div>

                    {versorger.zaehler.length === 0 ? (
                      <p className="text-sm text-gray-500 dark:text-gray-400 italic">
                        Noch keine Zähler erfasst
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {versorger.zaehler.map((zaehler, index) => (
                          <div
                            key={index}
                            className="flex items-start gap-2 p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg"
                          >
                            <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-2">
                              <Input
                                label="Bezeichnung"
                                value={zaehler.bezeichnung}
                                onChange={(e) =>
                                  updateZaehler(key, index, { ...zaehler, bezeichnung: e.target.value })
                                }
                                placeholder={key === 'strom' ? 'z.B. Einspeisung' : 'z.B. Hauptzähler'}
                              />
                              <Input
                                label="Zählernummer"
                                value={zaehler.nummer}
                                onChange={(e) =>
                                  updateZaehler(key, index, { ...zaehler, nummer: e.target.value })
                                }
                                placeholder="z.B. 1EMH0012345678"
                              />
                              <Input
                                label="Notizen"
                                value={zaehler.notizen || ''}
                                onChange={(e) =>
                                  updateZaehler(key, index, { ...zaehler, notizen: e.target.value })
                                }
                                placeholder="Optional..."
                              />
                            </div>
                            <button
                              type="button"
                              onClick={() => removeZaehler(key, index)}
                              className="p-2 text-gray-400 hover:text-red-500 transition-colors mt-6"
                              title="Zähler entfernen"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
