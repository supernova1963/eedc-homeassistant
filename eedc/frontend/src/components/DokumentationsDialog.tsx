/**
 * DokumentationsDialog — zentraler Download-Hub für alle PDFs einer Anlage.
 *
 * Bündelt Jahresbericht, Infothek-Dossier, Anlagendokumentation (Beta)
 * und Finanzbericht (Beta) in einer einzigen Stelle. Die beiden neuen
 * Dokumente werden in v3.15.0 als Beta eingeführt (Issue #121).
 */

import { FileText, Award, Euro, BookOpen, ExternalLink, Download } from 'lucide-react'
import { Modal } from './ui'
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
  beta?: boolean
  feedbackUrl?: string
  accent: string
}

export default function DokumentationsDialog({ anlage, onClose }: DokumentationsDialogProps) {
  if (!anlage) return null

  const cards: DocCard[] = [
    {
      icon: <FileText className="h-8 w-8" />,
      titel: 'Jahresbericht',
      beschreibung: 'Jahresauswertung mit Charts, Ertrag, Autarkie, CO₂-Bilanz — Klassiker für Jahresabschluss und Archiv.',
      url: importApi.getPdfExportUrl(anlage.id),
      accent: 'text-orange-500 border-orange-200 dark:border-orange-900/40',
    },
    {
      icon: <BookOpen className="h-8 w-8" />,
      titel: 'Infothek-Dossier',
      beschreibung: 'Alle Einträge der Infothek (Verträge, Zähler, Kontakte, Förderungen …) in einem Nachschlagewerk.',
      url: `./api/infothek/export/pdf?anlage_id=${anlage.id}`,
      accent: 'text-blue-500 border-blue-200 dark:border-blue-900/40',
    },
    {
      icon: <Award className="h-8 w-8" />,
      titel: 'Anlagendokumentation',
      beschreibung: 'Urkunden-Stil: Titelseite mit Anlagenfoto + Komponenten-Folgeseiten mit verknüpfter Komponenten-Akte. Ohne Geldbeträge — für Versicherung, Nachlass, Archiv.',
      url: `./api/dokumentation/anlagendokumentation/${anlage.id}`,
      beta: true,
      feedbackUrl: 'https://github.com/supernova1963/eedc-homeassistant/issues/121',
      accent: 'text-emerald-600 border-emerald-200 dark:border-emerald-900/40',
    },
    {
      icon: <Euro className="h-8 w-8" />,
      titel: 'Finanzbericht',
      beschreibung: 'Investitionen, Amortisation, Förderungen, Versicherung, Steuerdaten — alle Kennzahlen zum Geld-Aspekt der Anlage.',
      url: `./api/dokumentation/finanzbericht/${anlage.id}`,
      beta: true,
      feedbackUrl: 'https://github.com/supernova1963/eedc-homeassistant/issues/121',
      accent: 'text-amber-600 border-amber-200 dark:border-amber-900/40',
    },
  ]

  return (
    <Modal isOpen={!!anlage} onClose={onClose} title={`Dokumente — ${anlage.anlagenname}`} size="lg">
      <div className="space-y-3">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Download-Hub für alle generierten PDF-Dokumente zu dieser Anlage.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {cards.map(card => (
            <a
              key={card.titel}
              href={card.url}
              target="_blank"
              rel="noreferrer"
              className={`
                group block p-4 rounded-lg border-2 bg-white dark:bg-gray-800
                hover:shadow-md hover:-translate-y-0.5 transition-all
                ${card.accent}
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
                <Download className="h-4 w-4 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-200" />
              </div>
              <p className="text-xs text-gray-600 dark:text-gray-400 leading-snug">{card.beschreibung}</p>
              {card.feedbackUrl && (
                <div className="mt-2 pt-2 border-t border-gray-100 dark:border-gray-700">
                  <a
                    href={card.feedbackUrl}
                    target="_blank"
                    rel="noreferrer"
                    onClick={e => e.stopPropagation()}
                    className="text-[11px] text-amber-600 dark:text-amber-400 hover:underline inline-flex items-center gap-1"
                  >
                    Feedback zum Beta auf Issue #121 <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              )}
            </a>
          ))}
        </div>

        <p className="text-xs text-gray-500 dark:text-gray-500 mt-2">
          <strong>Beta-Hinweis:</strong> Die beiden neuen Dokumente (Anlagendokumentation, Finanzbericht) benötigen im HA-Add-on
          die Option <code className="text-xs">pdf_engine = weasyprint</code>. Standalone-Docker: Umgebungsvariable <code className="text-xs">PDF_ENGINE=weasyprint</code>.
        </p>
      </div>
    </Modal>
  )
}
