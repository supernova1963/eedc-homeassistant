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

import { useState } from 'react'
import { FileText, Award, Euro, BookOpen, Download, Loader2 } from 'lucide-react'
import { Modal, Alert } from './ui'
import { importApi } from '../api/import'
import type { Anlage } from '../types'

interface DokumentationsDialogProps {
  anlage: Anlage | null
  onClose: () => void
}

interface DocCard {
  icon: React.ReactNode
  titel: string
  beschreibung: string
  url: string
  filename: string
  beta?: boolean
  feedbackUrl?: string
  accent: string
}

async function downloadPdf(url: string, filename: string) {
  const res = await fetch(url)
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail || `HTTP ${res.status}`)
  }
  const blob = await res.blob()
  const blobUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(blobUrl)
}

export default function DokumentationsDialog({ anlage, onClose }: DokumentationsDialogProps) {
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (!anlage) return null

  const safeName = anlage.anlagenname.replace(/\s+/g, '_')

  const cards: DocCard[] = [
    {
      icon: <FileText className="h-8 w-8" />,
      titel: 'Jahresbericht',
      beschreibung: 'Jahresauswertung mit Charts, Ertrag, Autarkie, CO₂-Bilanz — Klassiker für Jahresabschluss und Archiv.',
      url: importApi.getPdfExportUrl(anlage.id),
      filename: `jahresbericht_${safeName}.pdf`,
      accent: 'text-orange-500 border-orange-200 dark:border-orange-900/40',
    },
    {
      icon: <BookOpen className="h-8 w-8" />,
      titel: 'Infothek-Dossier',
      beschreibung: 'Alle Einträge der Infothek (Verträge, Zähler, Kontakte, Förderungen …) in einem Nachschlagewerk.',
      url: `./api/infothek/export/pdf?anlage_id=${anlage.id}`,
      filename: `infothek_${safeName}.pdf`,
      accent: 'text-blue-500 border-blue-200 dark:border-blue-900/40',
    },
    {
      icon: <Award className="h-8 w-8" />,
      titel: 'Anlagendokumentation',
      beschreibung: 'Urkunden-Stil: Titelseite mit Anlagenfoto + Komponenten-Folgeseiten mit verknüpfter Komponenten-Akte. Ohne Geldbeträge — für Versicherung, Nachlass, Archiv.',
      url: `./api/dokumentation/anlagendokumentation/${anlage.id}`,
      filename: `anlagendokumentation_${safeName}.pdf`,
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
      beta: true,
      feedbackUrl: 'https://github.com/supernova1963/eedc-homeassistant/issues/121',
      accent: 'text-amber-600 border-amber-200 dark:border-amber-900/40',
    },
  ]

  const handleDownload = async (card: DocCard) => {
    setError(null)
    setLoading(card.titel)
    try {
      await downloadPdf(card.url, card.filename)
    } catch (err) {
      setError(`${card.titel}: ${err instanceof Error ? err.message : 'Download fehlgeschlagen'}`)
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

        {error && (
          <Alert type="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {cards.map(card => {
            const isLoading = loading === card.titel
            return (
              <div key={card.titel} className="flex flex-col">
                <button
                  type="button"
                  onClick={() => handleDownload(card)}
                  disabled={!!loading}
                  className={`
                    group flex-1 p-4 rounded-lg border-2 bg-white dark:bg-gray-800 text-left
                    hover:shadow-md hover:-translate-y-0.5 transition-all
                    disabled:opacity-60 disabled:cursor-wait
                    ${card.accent}
                    ${card.feedbackUrl ? 'rounded-b-none border-b-0' : ''}
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
                      ? <Loader2 className="h-4 w-4 text-gray-400 animate-spin" />
                      : <Download className="h-4 w-4 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-200" />
                    }
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-400 leading-snug">{card.beschreibung}</p>
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

        <p className="text-xs text-gray-500 dark:text-gray-500 mt-2">
          <strong>Beta-Hinweis:</strong> Die beiden neuen Dokumente (Anlagendokumentation, Finanzbericht) benötigen im HA-Add-on
          die Option <code className="text-xs">pdf_engine = weasyprint</code>. Standalone-Docker: Umgebungsvariable <code className="text-xs">PDF_ENGINE=weasyprint</code>.
        </p>
      </div>
    </Modal>
  )
}
