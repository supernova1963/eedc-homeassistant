/**
 * DokumentationsDialog — zentraler Download-Hub für alle PDFs einer Anlage.
 *
 * Bündelt Jahresbericht, Infothek-Dossier, Anlagendokumentation (Beta)
 * und Finanzbericht (Beta) in einer einzigen Stelle. Die beiden neuen
 * Dokumente werden in v3.15.0 als Beta eingeführt (Issue #121).
 *
 * PDFs werden per fetch() geladen und als Blob-Download angeboten,
 * damit der HA-Ingress-Auth-Token nicht verloren geht (Mobile 401-Fix).
 */

import { useState, useEffect } from 'react'
import { FileText, Award, Euro, BookOpen, Download, FolderArchive, Loader2 } from 'lucide-react'
import { Modal, Alert } from './ui'
import { importApi } from '../api/import'
import { infothekApi } from '../api/infothek'
import { monatsdatenApi } from '../api/monatsdaten'
import { downloadFile } from '../lib'
import type { Anlage } from '../types'

interface DokumentationsDialogProps {
  anlage: Anlage | null
  onClose: () => void
}

type BerichtKey = 'jahresbericht' | 'infothek' | 'anlagendokumentation' | 'finanzbericht'

interface DocCard {
  icon: React.ReactNode
  titel: string
  beschreibung: string
  url: string
  filename: string
  zipKey: BerichtKey
  beta?: boolean
  feedbackUrl?: string
  accent: string
  disabled?: boolean
  disabledHint?: string
}

export default function DokumentationsDialog({ anlage, onClose }: DokumentationsDialogProps) {
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // ZIP-Mehrfachauswahl (#121-Rest): angekreuzte Berichte
  const [zipAuswahl, setZipAuswahl] = useState<Set<BerichtKey>>(new Set())
  // null = Gesamtzeitraum (alle Jahre). Backend/Builder unterscheiden ueber den jahr-Query-Param.
  const [jahresberichtJahr, setJahresberichtJahr] = useState<number | null>(null)
  const [verfuegbareJahre, setVerfuegbareJahre] = useState<number[]>([])
  // Leere Infothek: Dossier-Karte deaktivieren statt ZIP-Komplettfehler
  // (Dirk-PN 2026-06-12). null = unbekannt/lädt → Karte bleibt aktiv.
  const [infothekAnzahl, setInfothekAnzahl] = useState<number | null>(null)

  useEffect(() => {
    if (!anlage) return
    let abgebrochen = false
    monatsdatenApi.list(anlage.id)
      .then(monate => {
        if (abgebrochen) return
        const jahre = Array.from(new Set(monate.map(m => m.jahr))).sort((a, b) => b - a)
        setVerfuegbareJahre(jahre)
      })
      .catch(() => { /* Jahresauswahl bleibt leer -> nur Gesamtzeitraum */ })
    // aktiv=true zählt dieselbe Menge wie der Dossier-Export
    infothekApi.getCount(anlage.id, true)
      .then(count => { if (!abgebrochen) setInfothekAnzahl(count) })
      .catch(() => { /* unbekannt → Karte bleibt aktiv, Backend-Meldung greift */ })
    return () => { abgebrochen = true }
  }, [anlage?.id])

  // Falls die Infothek-Karte bereits angekreuzt war, Auswahl bereinigen
  useEffect(() => {
    if (infothekAnzahl !== 0) return
    setZipAuswahl(prev => {
      if (!prev.has('infothek')) return prev
      const next = new Set(prev)
      next.delete('infothek')
      return next
    })
  }, [infothekAnzahl])

  if (!anlage) return null

  const safeName = anlage.anlagenname.replace(/\s+/g, '_')

  const cards: DocCard[] = [
    {
      icon: <FileText className="h-8 w-8" />,
      titel: 'Jahresbericht',
      beschreibung: jahresberichtJahr
        ? `Jahresauswertung ${jahresberichtJahr} mit Charts, Ertrag, Autarkie, CO₂-Bilanz — Klassiker für Jahresabschluss und Archiv.`
        : 'Gesamtauswertung über alle Jahre mit Charts, Ertrag, Autarkie, CO₂-Bilanz. Oben ein einzelnes Jahr wählbar.',
      url: importApi.getPdfExportUrl(anlage.id, jahresberichtJahr),
      filename: jahresberichtJahr
        ? `jahresbericht_${safeName}_${jahresberichtJahr}.pdf`
        : `jahresbericht_${safeName}.pdf`,
      zipKey: 'jahresbericht',
      accent: 'text-orange-500 border-orange-200 dark:border-orange-900/40',
    },
    {
      icon: <BookOpen className="h-8 w-8" />,
      titel: 'Infothek-Dossier',
      beschreibung: 'Alle Einträge der Infothek (Verträge, Zähler, Kontakte, Förderungen …) in einem Nachschlagewerk.',
      url: `./api/infothek/export/pdf?anlage_id=${anlage.id}`,
      filename: `infothek_${safeName}.pdf`,
      zipKey: 'infothek',
      accent: 'text-blue-500 border-blue-200 dark:border-blue-900/40',
      disabled: infothekAnzahl === 0,
      disabledHint: 'Keine Infothek-Einträge vorhanden — das Dossier hätte keinen Inhalt. Einträge anlegen unter Einstellungen → Infothek.',
    },
    {
      icon: <Award className="h-8 w-8" />,
      titel: 'Anlagendokumentation',
      beschreibung: 'Urkunden-Stil: Titelseite mit Anlagenfoto + Komponenten-Folgeseiten mit verknüpfter Komponenten-Akte. Ohne Geldbeträge — für Versicherung, Nachlass, Archiv.',
      url: `./api/dokumentation/anlagendokumentation/${anlage.id}`,
      filename: `anlagendokumentation_${safeName}.pdf`,
      zipKey: 'anlagendokumentation',
      beta: true,
      feedbackUrl: 'https://github.com/supernova1963/eedc-homeassistant/issues/121',
      accent: 'text-emerald-600 border-emerald-200 dark:border-emerald-900/40',
    },
    {
      icon: <Euro className="h-8 w-8" />,
      titel: 'Finanzbericht',
      beschreibung: 'Investitionen, Amortisation, Förderungen, Versicherung, Steuerdaten — alle Kennzahlen zum Geld-Aspekt der Anlage.',
      url: `./api/dokumentation/finanzbericht/${anlage.id}`,
      filename: `finanzbericht_${safeName}.pdf`,
      zipKey: 'finanzbericht',
      beta: true,
      feedbackUrl: 'https://github.com/supernova1963/eedc-homeassistant/issues/121',
      accent: 'text-amber-600 border-amber-200 dark:border-amber-900/40',
    },
  ]

  const handleDownload = async (card: DocCard) => {
    setError(null)
    setLoading(card.titel)
    try {
      await downloadFile(card.url, card.filename)
    } catch (err) {
      setError(`${card.titel}: ${err instanceof Error ? err.message : 'Download fehlgeschlagen'}`)
    } finally {
      setLoading(null)
    }
  }

  const toggleZipAuswahl = (key: BerichtKey) => {
    setZipAuswahl(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // Karten-Reihenfolge beibehalten, damit das ZIP stabil sortiert ist
  const zipBerichte = cards.filter(c => zipAuswahl.has(c.zipKey)).map(c => c.zipKey)

  const handleZipDownload = async () => {
    setError(null)
    setLoading('ZIP')
    try {
      await downloadFile(
        importApi.getPdfZipExportUrl(anlage.id, zipBerichte, jahresberichtJahr),
        `eedc_dokumente_${safeName}.zip`,
      )
    } catch (err) {
      setError(`ZIP-Download: ${err instanceof Error ? err.message : 'Download fehlgeschlagen'}`)
    } finally {
      setLoading(null)
    }
  }

  return (
    <Modal isOpen={!!anlage} onClose={onClose} title={`Dokumente — ${anlage.anlagenname}`} size="lg">
      <div className="space-y-3">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Download-Hub für alle generierten PDF-Dokumente zu dieser Anlage.
        </p>

        {verfuegbareJahre.length > 0 && (
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-lg border border-orange-200 dark:border-orange-900/40 bg-orange-50/50 dark:bg-orange-900/10 px-3 py-2">
            <label htmlFor="jahresbericht-jahr" className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Jahresbericht-Zeitraum:
            </label>
            <select
              id="jahresbericht-jahr"
              value={jahresberichtJahr ?? ''}
              onChange={(e) => setJahresberichtJahr(e.target.value ? parseInt(e.target.value, 10) : null)}
              className="px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
            >
              <option value="">Gesamtzeitraum (alle Jahre)</option>
              {verfuegbareJahre.map(jahr => (
                <option key={jahr} value={jahr}>{jahr}</option>
              ))}
            </select>
          </div>
        )}

        {error && (
          <Alert type="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {cards.map(card => {
            const isLoading = loading === card.titel
            const isDisabled = !!card.disabled
            return (
              <div key={card.titel} className="relative flex flex-col">
                {!isDisabled && (
                  <label
                    className="absolute -top-2 -right-2 z-10 flex items-center justify-center h-7 w-7 rounded-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 shadow-sm cursor-pointer"
                    title="Für ZIP-Download auswählen"
                  >
                    <input
                      type="checkbox"
                      checked={zipAuswahl.has(card.zipKey)}
                      onChange={() => toggleZipAuswahl(card.zipKey)}
                      className="h-4 w-4 accent-orange-500 cursor-pointer"
                      aria-label={`${card.titel} für ZIP-Download auswählen`}
                    />
                  </label>
                )}
                <button
                  type="button"
                  onClick={() => handleDownload(card)}
                  disabled={!!loading || isDisabled}
                  className={`
                    group flex-1 p-4 rounded-lg border-2 bg-white dark:bg-gray-800 text-left
                    ${card.accent}
                    ${card.feedbackUrl ? 'rounded-b-none border-b-0' : ''}
                    ${isDisabled
                      ? 'opacity-50 cursor-not-allowed disabled:cursor-not-allowed'
                      : 'hover:shadow-md hover:-translate-y-0.5 transition-all disabled:opacity-60 disabled:cursor-wait'}
                  `}
                >
                  <div className="flex items-start gap-3 mb-2">
                    <div className={card.accent.split(' ')[0]}>{card.icon}</div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-gray-900 dark:text-white">{card.titel}</h3>
                        {card.beta && (
                          <span className="inline-block px-1.5 py-0.5 text-[10px] font-bold rounded bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 uppercase tracking-wide">
                            Beta
                          </span>
                        )}
                      </div>
                    </div>
                    {isLoading
                      ? <Loader2 className="h-4 w-4 text-gray-400 dark:text-gray-500 animate-spin" />
                      : !isDisabled && <Download className="h-4 w-4 text-gray-400 dark:text-gray-500 group-hover:text-gray-600 dark:group-hover:text-gray-200" />
                    }
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-400 leading-snug">{card.beschreibung}</p>
                  {isDisabled && card.disabledHint && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 leading-snug mt-2">
                      {card.disabledHint}
                    </p>
                  )}
                </button>
                {card.feedbackUrl && (
                  <div className={`px-4 py-2 border-2 border-t-0 rounded-b-lg bg-white dark:bg-gray-800 ${card.accent}`}>
                    <a
                      href={card.feedbackUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[11px] text-amber-600 dark:text-amber-400 hover:underline inline-flex items-center gap-1"
                    >
                      Feedback zum Beta auf Issue #121
                    </a>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {zipBerichte.length >= 2 && (
          <button
            type="button"
            onClick={handleZipDownload}
            disabled={!!loading}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg
              bg-orange-500 hover:bg-orange-600 text-white font-medium text-sm
              transition-colors disabled:opacity-60 disabled:cursor-wait"
          >
            {loading === 'ZIP'
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : <FolderArchive className="h-4 w-4" />
            }
            Als ZIP herunterladen ({zipBerichte.length} Berichte)
          </button>
        )}

        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
          <strong>Tipp:</strong> Über die Kästchen an den Karten lassen sich mehrere Berichte
          auswählen und gesammelt als ZIP herunterladen (ab 2 Berichten).
          {' '}<strong>Beta-Hinweis:</strong> Anlagendokumentation und Finanzbericht sind als Beta gekennzeichnet —
          Rückmeldungen gerne über den Feedback-Link.
        </p>
      </div>
    </Modal>
  )
}
