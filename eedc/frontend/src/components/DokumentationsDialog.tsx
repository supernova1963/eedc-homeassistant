/**
 * DokumentationsDialog — zentraler Download-Hub für alle PDFs einer Anlage.
 *
 * Bündelt Jahresbericht, Infothek-Dossier, Anlagendokumentation (Beta),
 * Finanzbericht (Beta) und Monatsbericht in einer einzigen Stelle. Die beiden
 * Beta-Dokumente wurden in v3.15.0 eingeführt (Issue #121).
 *
 * Der **Monatsbericht** (#395 Punkt 4, OB73-gif) ist der einzige mit eigenen
 * Erzeugungs-Optionen: genau ein Monat, vier Themenschalter, Identität und —
 * falls in der Monatsansicht etwas geparkt ist — der Schalter „wie in meiner
 * Monatsansicht". Er ist bewusst **nicht** ZIP-fähig: Ein Bündel „alle
 * Dokumente dieser Anlage" hat keinen Monat, und ein stiller Vorgabemonat wäre
 * eine Entscheidung, die niemand getroffen hat.
 *
 * Wächter-Ausnahme: die Download-Karten-KACHEL ist ein roher <button> (ganze
 * Karte als Klickfläche, Akzent-Rahmen-Optik — kein ui/Button-Fall) —
 * check:v4-migration-Fall-3-Allowlist (Regel 0a Fall 3, Gernot-Freigabe 2026-07-11).
 *
 * PDFs werden per fetch() geladen und als Blob-Download angeboten,
 * damit der HA-Ingress-Auth-Token nicht verloren geht (Mobile 401-Fix).
 */

import { useState, useEffect } from 'react'
import { FileText, Award, Euro, BookOpen, CalendarDays, Download, FolderArchive, Loader2, Copy, Check } from 'lucide-react'
import { Modal, Alert, Button, Checkbox, Select } from './ui'
import { importApi } from '../api/import'
import { infothekApi } from '../api/infothek'
import { monatsdatenApi } from '../api/monatsdaten'
import { downloadFile } from '../lib'
import { useCopyFeedback } from '../hooks'
import { geparkteElemente } from './park'
import { MONAT_PARK_KEY } from '../v4/monatParkScope'
import type { Anlage } from '../types'

interface DokumentationsDialogProps {
  anlage: Anlage | null
  onClose: () => void
}

type BerichtKey = 'jahresbericht' | 'infothek' | 'anlagendokumentation' | 'finanzbericht'

/** Die vier Themenschalter des Monatsberichts — Reihenfolge = Reihenfolge im
 *  Dokument. Spiegel von `services/pdf/builders/monatsbericht.py::THEMEN`. */
const MONATSBERICHT_THEMEN = [
  { key: 'energie', label: 'Energie' },
  { key: 'komponenten', label: 'Komponenten' },
  { key: 'finanzen', label: 'Finanzen' },
  { key: 'co2', label: 'CO₂' },
] as const
type MonatsberichtThema = typeof MONATSBERICHT_THEMEN[number]['key']

const MONAT_NAMEN = [
  '', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
]

interface DocCard {
  icon: React.ReactNode
  titel: string
  beschreibung: string
  url: string
  filename: string
  /** Fehlt, wenn der Bericht nicht ins Sammel-ZIP gehört (Monatsbericht). */
  zipKey?: BerichtKey
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

  // ── Monatsbericht (#395 Punkt 4) ────────────────────────────────────────
  const [verfuegbareMonate, setVerfuegbareMonate] = useState<{ jahr: number; monat: number }[]>([])
  const [monatsberichtRef, setMonatsberichtRef] = useState<string>('')
  const [themen, setThemen] = useState<Set<MonatsberichtThema>>(
    () => new Set(MONATSBERICHT_THEMEN.map(t => t.key)),
  )
  const [mitIdentitaet, setMitIdentitaet] = useState(true)
  const [ohneGeparkte, setOhneGeparkte] = useState(true)
  // Der Park-Zustand lebt NUR im localStorage dieses Browsers. Einmal beim
  // Öffnen gelesen — er ändert sich nicht, während der Dialog offen ist, und
  // ein Abo darauf gibt es bewusst nicht (der Dialog hängt nicht im Render-Baum
  // der Monatssicht).
  const [geparkt, setGeparkt] = useState<{ id: string; titel: string }[]>([])
  const { istKopiert, kopiere } = useCopyFeedback()

  // Nur die ID ist der Trigger — das Anlage-Objekt selbst wird hier nicht gelesen.
  const anlageId = anlage?.id
  useEffect(() => {
    if (!anlageId) return
    let abgebrochen = false
    setGeparkt(geparkteElemente(MONAT_PARK_KEY))
    monatsdatenApi.list(anlageId)
      .then(monate => {
        if (abgebrochen) return
        const jahre = Array.from(new Set(monate.map(m => m.jahr))).sort((a, b) => b - a)
        setVerfuegbareJahre(jahre)
        // Neueste zuerst — dieselbe Doktrin wie die Jahresliste darüber und
        // wie die Datums-Listen des Style-Guides (Default absteigend).
        const refs = monate
          .map(m => ({ jahr: m.jahr, monat: m.monat }))
          .sort((a, b) => (a.jahr !== b.jahr ? b.jahr - a.jahr : b.monat - a.monat))
        setVerfuegbareMonate(refs)
        if (refs.length > 0) setMonatsberichtRef(`${refs[0].jahr}-${refs[0].monat}`)
      })
      .catch(() => { /* Jahres-/Monatsauswahl bleibt leer */ })
    // aktiv=true zählt dieselbe Menge wie der Dossier-Export
    infothekApi.getCount(anlageId, true)
      .then(count => { if (!abgebrochen) setInfothekAnzahl(count) })
      .catch(() => { /* unbekannt → Karte bleibt aktiv, Backend-Meldung greift */ })
    return () => { abgebrochen = true }
  }, [anlageId])

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

  const [mbJahr, mbMonat] = monatsberichtRef
    ? monatsberichtRef.split('-').map(n => parseInt(n, 10))
    : [0, 0]
  const monatsberichtLabel = mbMonat ? `${MONAT_NAMEN[mbMonat]} ${mbJahr}` : ''

  /**
   * Adresse des Monatsberichts. `format=md` liefert denselben Bericht als Text.
   *
   * ⚑ `ohne` trägt die Park-IDs aus DIESEM Browser. Ist der Schalter aus oder
   * nichts geparkt, geht der Parameter gar nicht mit — und das Backend liefert
   * den vollständigen Bericht. Genau so muss der Fall „am Tablet geparkt, am PC
   * erzeugt" ausgehen: nichts weglassen, was der Erzeuger hier nicht wegnimmt.
   */
  const monatsberichtUrl = (format: 'pdf' | 'md') => {
    const q = new URLSearchParams()
    q.set('jahr', String(mbJahr))
    q.set('monat', String(mbMonat))
    q.set('format', format)
    q.set('mit_identitaet', String(mitIdentitaet))
    MONATSBERICHT_THEMEN.forEach(t => { if (themen.has(t.key)) q.append('themen', t.key) })
    if (ohneGeparkte) geparkt.forEach(g => q.append('ohne', g.id))
    return `./api/dokumentation/monatsbericht/${anlage.id}?${q.toString()}`
  }
  const monatsberichtDatei = (endung: string) =>
    `monatsbericht_${mbJahr}-${String(mbMonat).padStart(2, '0')}_${safeName}.${endung}`

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
      accent: 'text-orange-500',
    },
    {
      icon: <BookOpen className="h-8 w-8" />,
      titel: 'Infothek-Dossier',
      beschreibung: 'Alle Einträge der Infothek (Verträge, Zähler, Kontakte, Förderungen …) in einem Nachschlagewerk.',
      url: `./api/infothek/export/pdf?anlage_id=${anlage.id}`,
      filename: `infothek_${safeName}.pdf`,
      zipKey: 'infothek',
      accent: 'text-blue-500',
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
      accent: 'text-emerald-600',
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
      accent: 'text-amber-600',
    },
    {
      icon: <CalendarDays className="h-8 w-8" />,
      titel: 'Monatsbericht',
      beschreibung: monatsberichtLabel
        ? `Die Monatsdaten aus ${monatsberichtLabel} im Stil der Cockpit-Monatsansicht — zum Ablegen als PDF, zum Posten als Text. Auswahl darunter.`
        : 'Die Monatsdaten eines einzelnen Monats im Stil der Cockpit-Monatsansicht. Sobald ein Monat erfasst ist, lässt er sich hier auswählen.',
      url: monatsberichtUrl('pdf'),
      filename: monatsberichtDatei('pdf'),
      accent: 'text-indigo-500',
      disabled: verfuegbareMonate.length === 0,
      disabledHint: 'Noch kein Monat erfasst — es gäbe nichts zu berichten. Monatsabschluss unter Cockpit → Monat.',
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

  /** Markdown holen — geteilt von „Text herunterladen" und „In die Zwischenablage". */
  const holeMarkdown = async (): Promise<string> => {
    const res = await fetch(monatsberichtUrl('md'))
    if (!res.ok) {
      const detail = await res.json().catch(() => null)
      throw new Error(detail?.detail || `HTTP ${res.status}`)
    }
    return res.text()
  }

  const handleMarkdownKopieren = async () => {
    setError(null)
    setLoading('Text kopieren')
    try {
      await kopiere(await holeMarkdown(), 'monatsbericht')
    } catch (err) {
      setError(`Monatsbericht: ${err instanceof Error ? err.message : 'Kopieren fehlgeschlagen'}`)
    } finally {
      setLoading(null)
    }
  }

  const handleMarkdownDownload = async () => {
    setError(null)
    setLoading('Text laden')
    try {
      await downloadFile(monatsberichtUrl('md'), monatsberichtDatei('md'))
    } catch (err) {
      setError(`Monatsbericht: ${err instanceof Error ? err.message : 'Download fehlgeschlagen'}`)
    } finally {
      setLoading(null)
    }
  }

  const toggleThema = (key: MonatsberichtThema) => {
    setThemen(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
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
  const zipBerichte = cards
    .map(c => c.zipKey)
    .filter((k): k is BerichtKey => !!k && zipAuswahl.has(k))

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
            <Select
              id="jahresbericht-jahr"
              compact
              value={jahresberichtJahr ?? ''}
              onChange={(e) => setJahresberichtJahr(e.target.value ? parseInt(e.target.value, 10) : null)}
              options={[
                { value: '', label: 'Gesamtzeitraum (alle Jahre)' },
                ...verfuegbareJahre.map(jahr => ({ value: String(jahr), label: String(jahr) })),
              ]}
            />
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
                {/* D19-2 (detlan): Checkbox OHNE Kreis-Badge direkt auf der Karte;
                    Karten-Ränder neutral (Typ-Farbe nur noch am Icon) und ohne
                    Hover-Lift — dezenter Rahmen-Hover statt Schweben. */}
                {!isDisabled && card.zipKey && (
                  <div className="absolute top-2 right-2 z-10" title="Für ZIP-Download auswählen">
                    <Checkbox
                      id={`zip-${card.zipKey}`}
                      label={<span className="sr-only">{card.titel} für ZIP-Download auswählen</span>}
                      checked={zipAuswahl.has(card.zipKey)}
                      onChange={() => toggleZipAuswahl(card.zipKey!)}
                    />
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => handleDownload(card)}
                  disabled={!!loading || isDisabled}
                  className={`
                    group flex-1 p-4 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-left
                    ${card.feedbackUrl ? 'rounded-b-none border-b-0' : ''}
                    ${isDisabled
                      ? 'opacity-50 cursor-not-allowed disabled:cursor-not-allowed'
                      : 'hover:border-gray-300 dark:hover:border-gray-600 transition-colors disabled:opacity-60 disabled:cursor-wait'}
                  `}
                >
                  <div className="flex items-start gap-3 mb-2">
                    <div className={card.accent}>{card.icon}</div>
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
                  <div className="px-4 py-2 border border-t-0 border-gray-200 dark:border-gray-700 rounded-b-lg bg-white dark:bg-gray-800">
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

        {verfuegbareMonate.length > 0 && (
          <div className="rounded-lg border border-indigo-200 dark:border-indigo-900/40 bg-indigo-50/50 dark:bg-indigo-900/10 px-3 py-3 space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center gap-2">
              <label htmlFor="monatsbericht-monat" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Monatsbericht für:
              </label>
              <Select
                id="monatsbericht-monat"
                compact
                value={monatsberichtRef}
                onChange={(e) => setMonatsberichtRef(e.target.value)}
                options={verfuegbareMonate.map(m => ({
                  value: `${m.jahr}-${m.monat}`,
                  label: `${MONAT_NAMEN[m.monat]} ${m.jahr}`,
                }))}
              />
            </div>

            {/* Vier Themenschalter — voreingestellt alle an. Sie bestimmen, WAS
                für ein Bericht entsteht; der Park-Schalter darunter feilt
                INNERHALB. Zwei Ebenen, bewusst nicht vermischt. */}
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {MONATSBERICHT_THEMEN.map(t => (
                <Checkbox
                  key={t.key}
                  id={`monatsbericht-thema-${t.key}`}
                  label={t.label}
                  checked={themen.has(t.key)}
                  onChange={() => toggleThema(t.key)}
                />
              ))}
            </div>

            <div className="flex flex-wrap gap-x-4 gap-y-1">
              <Checkbox
                id="monatsbericht-identitaet"
                label="Anlagenname und Standort nennen"
                checked={mitIdentitaet}
                onChange={() => setMitIdentitaet(v => !v)}
              />
              {/* Eine Frage ohne Gegenstand ist schlechter als keine Frage:
                  ohne geparkte Anzeigen erscheint der Schalter gar nicht. */}
              {geparkt.length > 0 && (
                <Checkbox
                  id="monatsbericht-ohne-geparkte"
                  label={`Wie in meiner Monatsansicht (${geparkt.length} geparkte Anzeigen weglassen)`}
                  checked={ohneGeparkte}
                  onChange={() => setOhneGeparkte(v => !v)}
                />
              )}
            </div>

            {/* Der PDF-Weg liegt auf der Karte oben; hier stehen die zwei
                Text-Wege — wer postet, kopiert. */}
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={handleMarkdownKopieren}
                disabled={!!loading}
                loading={loading === 'Text kopieren'}
              >
                {loading !== 'Text kopieren' && (
                  istKopiert('monatsbericht')
                    ? <Check className="h-4 w-4 mr-2" />
                    : <Copy className="h-4 w-4 mr-2" />
                )}
                {istKopiert('monatsbericht') ? 'Kopiert' : 'Als Text in die Zwischenablage'}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={handleMarkdownDownload}
                disabled={!!loading}
                loading={loading === 'Text laden'}
              >
                {loading !== 'Text laden' && <Download className="h-4 w-4 mr-2" />}
                Als Text herunterladen (.md)
              </Button>
            </div>

            <p className="text-xs text-gray-500 dark:text-gray-400">
              Der Bericht deckt <strong>genau einen Monat</strong> ab. Eine Spanne
              über mehrere Monate ist der Jahresbericht oben.
              {mitIdentitaet && ' Anlagenname und Standort stehen im Dokument — vor dem Teilen abwählen.'}
            </p>
          </div>
        )}

        {zipBerichte.length >= 2 && (
          <Button
            type="button"
            className="w-full"
            onClick={handleZipDownload}
            disabled={!!loading}
            loading={loading === 'ZIP'}
          >
            {loading !== 'ZIP' && <FolderArchive className="h-4 w-4 mr-2" />}
            Als ZIP herunterladen ({zipBerichte.length} Berichte)
          </Button>
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
