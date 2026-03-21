/**
 * ShareTextModal: Social-Media-Text generieren und kopieren
 */

import { useState, useEffect } from 'react'
import { Copy, Check } from 'lucide-react'
import { Modal, LoadingSpinner } from '../../components/ui'
import { MONAT_NAMEN } from '../../lib'
import { cockpitApi } from '../../api'
import type { AggregierteMonatsdaten } from '../../api/monatsdaten'

export default function ShareTextModal({ anlageId, availableYears, monatsdaten, onClose }: {
  anlageId: number
  availableYears: number[]
  monatsdaten: AggregierteMonatsdaten[]
  onClose: () => void
}) {
  // Default: letzter verfügbarer Monat
  const sorted = [...monatsdaten].sort((a, b) =>
    a.jahr !== b.jahr ? b.jahr - a.jahr : b.monat - a.monat
  )
  const letzter = sorted[0]

  const [monat, setMonat] = useState(letzter?.monat || new Date().getMonth() + 1)
  const [jahr, setJahr] = useState(letzter?.jahr || new Date().getFullYear())
  const [variante, setVariante] = useState<'kompakt' | 'ausfuehrlich'>('kompakt')
  const [text, setText] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  // Verfügbare Monate für das gewählte Jahr
  const verfuegbareMonate = monatsdaten
    .filter(m => m.jahr === jahr)
    .map(m => m.monat)
    .sort((a, b) => a - b)

  // Text laden wenn sich Parameter ändern
  useEffect(() => {
    setLoading(true)
    setError(null)
    setText(null)
    cockpitApi.getShareText(anlageId, monat, jahr, variante)
      .then(res => setText(res.text))
      .catch(() => setError('Text konnte nicht generiert werden'))
      .finally(() => setLoading(false))
  }, [anlageId, monat, jahr, variante])

  // Jahr-Wechsel: Monat auf verfügbaren Monat setzen
  useEffect(() => {
    const monate = monatsdaten.filter(m => m.jahr === jahr).map(m => m.monat)
    if (monate.length > 0 && !monate.includes(monat)) {
      setMonat(Math.max(...monate))
    }
  }, [jahr])

  const handleCopy = async () => {
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Fallback
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <Modal isOpen onClose={onClose} title="Social-Media-Text" size="lg">
      <div className="space-y-4">
        {/* Auswahl */}
        <div className="flex flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <label htmlFor="share-monat" className="text-sm text-gray-500 dark:text-gray-400">Monat:</label>
            <select
              id="share-monat"
              value={monat}
              onChange={e => setMonat(parseInt(e.target.value))}
              className="input py-1.5 text-sm"
            >
              {verfuegbareMonate.map(m => (
                <option key={m} value={m}>{MONAT_NAMEN[m]}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="share-jahr" className="text-sm text-gray-500 dark:text-gray-400">Jahr:</label>
            <select
              id="share-jahr"
              value={jahr}
              onChange={e => setJahr(parseInt(e.target.value))}
              className="input py-1.5 text-sm"
            >
              {availableYears.map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-1 ml-auto">
            <button
              onClick={() => setVariante('kompakt')}
              className={`px-3 py-1.5 text-sm rounded-l-lg border transition-colors ${
                variante === 'kompakt'
                  ? 'bg-primary-500 text-white border-primary-500'
                  : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600'
              }`}
            >
              Kompakt
            </button>
            <button
              onClick={() => setVariante('ausfuehrlich')}
              className={`px-3 py-1.5 text-sm rounded-r-lg border-t border-r border-b transition-colors ${
                variante === 'ausfuehrlich'
                  ? 'bg-primary-500 text-white border-primary-500'
                  : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600'
              }`}
            >
              Ausführlich
            </button>
          </div>
        </div>

        {/* Vorschau */}
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 min-h-[200px]">
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <LoadingSpinner text="Generiere Text..." />
            </div>
          ) : error ? (
            <p className="text-sm text-red-500">{error}</p>
          ) : text ? (
            <pre className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap font-sans leading-relaxed">{text}</pre>
          ) : null}
        </div>

        {/* Kopieren */}
        <div className="flex justify-end">
          <button
            onClick={handleCopy}
            disabled={!text || loading}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              copied
                ? 'bg-green-500 text-white'
                : 'bg-primary-500 hover:bg-primary-600 text-white disabled:opacity-50 disabled:cursor-not-allowed'
            }`}
          >
            {copied ? (
              <>
                <Check className="h-4 w-4" />
                Kopiert!
              </>
            ) : (
              <>
                <Copy className="h-4 w-4" />
                In Zwischenablage kopieren
              </>
            )}
          </button>
        </div>
      </div>
    </Modal>
  )
}
