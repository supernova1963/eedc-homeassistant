/**
 * DokumentationsDialog — zentraler Download-Hub für alle PDFs einer Anlage.
 *
 * Bündelt Jahresbericht, Infothek-Dossier, Anlagendokumentation (Beta),
 * Finanzbericht (Beta) und Monatsbericht in einer einzigen Stelle. Die beiden
 * Beta-Dokumente wurden in v3.15.0 eingeführt (Issue #121).
 *
 * Der **Monatsbericht** (#395 Punkt 4, OB73-gif) ist der einzige mit eigenen
 * Erzeugungs-Optionen: genau ein Monat, fünf Themenschalter, Identität und —
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
import { FileText, Award, Euro, BookOpen, CalendarDays, Download, FolderArchive, Loader2, CheckSquare, Square } from 'lucide-react'
import { Modal, Alert, Button, Checkbox, Select } from './ui'
import { importApi } from '../api/import'
import { infothekApi } from '../api/infothek'
import { monatsdatenApi } from '../api/monatsdaten'
import { downloadFile } from '../lib'
import { geparkteElemente } from './park'
import { MONAT_PARK_KEY } from '../v4/monatParkScope'
import type { Anlage } from '../types'

interface DokumentationsDialogProps {
  anlage: Anlage | null
  onClose: () => void
}

type BerichtKey = 'jahresbericht' | 'infothek' | 'anlagendokumentation' | 'finanzbericht'

/** Die Themenschalter des Monatsberichts — Reihenfolge = Reihenfolge im
 *  Dokument. Spiegel von `services/pdf/builders/monatsbericht.py::THEMEN`.
 *
 *  ⚠ Die Verbindung war bis 2026-08-30 **nur dieser Kommentar** — kein Test,
 *  keiner der `check:*`. Wer einen Schalter nur auf einer Seite ergänzte, bekam
 *  entweder einen Schalter, der still nichts tut (Backend filtert unbekannte
 *  Schlüssel weg), oder ein Thema, das niemand wählen kann. Seit dem
 *  Community-Schalter hält `npm run check:spiegel-backend` beide Listen
 *  zusammen. */
const MONATSBERICHT_THEMEN = [
  { key: 'energie', label: 'Energie' },
  { key: 'komponenten', label: 'Komponenten' },
  { key: 'finanzen', label: 'Finanzen' },
  { key: 'co2', label: 'CO₂' },
  { key: 'community', label: 'Community' },
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
  accent: string
  disabled?: boolean
  disabledHint?: string
  /**
   * Einstellungen **dieses** Dokuments — sie stehen IN der Karte, unter einer
   * Trennlinie.
   *
   * ⛔ Bis 2026-08-30 standen sie außerhalb: der Jahresbericht-Zeitraum in einem
   * Kasten ÜBER dem Raster, die Monatsbericht-Optionen in einem Kasten
   * DARUNTER. Beide sahen damit global aus und steuerten je genau ein Dokument
   * (Gernot: „Monatsbericht-Einstellungen sind nicht nur dem Monatsbericht
   * zuzuordnen"). Die Zuordnung ist jetzt baulich statt durch Nähe.
   */
  optionen?: React.ReactNode
  /** Über die volle Rasterbreite — für Karten mit vielen Einstellungen. */
  breit?: boolean
}

export default function DokumentationsDialog({ anlage, onClose }: DokumentationsDialogProps) {
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // ZIP-Mehrfachauswahl (#121-Rest): angekreuzte Berichte
  const [zipAuswahl, setZipAuswahl] = useState<Set<BerichtKey>>(new Set())
  /**
   * Sammel-Modus. Aus = die Karten laden ihr Dokument; ein = sie wählen aus.
   *
   * ⛔ Vorher trugen die Karten **beides gleichzeitig**: ein Kästchen
   * `absolute top-2 right-2` und darunter das Download-Symbol an derselben
   * Ecke — das Symbol war teilweise oder ganz verdeckt (Gernot, 30.08.). Ein
   * Modus löst das baulich: die zwei teilen sich die Ecke nie.
   */
  const [zipModus, setZipModus] = useState(false)
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
  const [ohneGeparkte, setOhneGeparkte] = useState(true)
  // Der Park-Zustand lebt NUR im localStorage dieses Browsers. Einmal beim
  // Öffnen gelesen — er ändert sich nicht, während der Dialog offen ist, und
  // ein Abo darauf gibt es bewusst nicht (der Dialog hängt nicht im Render-Baum
  // der Monatssicht).
  const [geparkt, setGeparkt] = useState<{ id: string; titel: string }[]>([])

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
   * Adresse des Monatsberichts.
   *
   * ⚑ `ohne` trägt die Park-IDs aus DIESEM Browser. Ist der Schalter aus oder
   * nichts geparkt, geht der Parameter gar nicht mit — und das Backend liefert
   * den vollständigen Bericht. Genau so muss der Fall „am Tablet geparkt, am PC
   * erzeugt" ausgehen: nichts weglassen, was der Erzeuger hier nicht wegnimmt.
   */
  const monatsberichtUrl = () => {
    const q = new URLSearchParams()
    q.set('jahr', String(mbJahr))
    q.set('monat', String(mbMonat))
    MONATSBERICHT_THEMEN.forEach(t => { if (themen.has(t.key)) q.append('themen', t.key) })
    if (ohneGeparkte) geparkt.forEach(g => q.append('ohne', g.id))
    return `./api/dokumentation/monatsbericht/${anlage.id}?${q.toString()}`
  }
  const monatsberichtDatei = () =>
    `monatsbericht_${mbJahr}-${String(mbMonat).padStart(2, '0')}_${safeName}.pdf`

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
      optionen: verfuegbareJahre.length > 0 ? (
        // ⛔ KEIN `compact`: das rendert den Wrapper als `shrink-0` und den
        // `<select>` als `w-auto` — er nimmt dann die Breite seiner längsten
        // Option („Gesamtzeitraum (alle Jahre)") und **weigert sich zu
        // schrumpfen**. In der Kopfleiste, für die `compact` gedacht ist, war
        // das egal; in einer Rasterspalte sprengt es die Karte (Gernot,
        // 30.08.). `min-w-0` am Container, damit die Flex-Zeile schrumpfen darf.
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 min-w-0">
          <label htmlFor="jahresbericht-jahr" className="text-sm text-gray-700 dark:text-gray-300 shrink-0">
            Zeitraum:
          </label>
          <Select
            id="jahresbericht-jahr"
            className="truncate"
            value={jahresberichtJahr ?? ''}
            onChange={(e) => setJahresberichtJahr(e.target.value ? parseInt(e.target.value, 10) : null)}
            options={[
              { value: '', label: 'Gesamtzeitraum (alle Jahre)' },
              ...verfuegbareJahre.map(jahr => ({ value: String(jahr), label: String(jahr) })),
            ]}
          />
        </div>
      ) : undefined,
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
      accent: 'text-emerald-600',
    },
    {
      icon: <Euro className="h-8 w-8" />,
      titel: 'Finanzbericht',
      beschreibung: 'Investitionen, Amortisation, Förderungen, Versicherung, Steuerdaten — alle Kennzahlen zum Geld-Aspekt der Anlage.',
      url: `./api/dokumentation/finanzbericht/${anlage.id}`,
      filename: `finanzbericht_${safeName}.pdf`,
      zipKey: 'finanzbericht',
      accent: 'text-amber-600',
    },
    {
      icon: <CalendarDays className="h-8 w-8" />,
      titel: 'Monatsbericht',
      beschreibung: monatsberichtLabel
        ? `Die Zahlen aus ${monatsberichtLabel} im Stil der Cockpit-Monatsansicht: Kennzahl-Kacheln, Anteils-Leisten, Verlauf und Tagesprofil.`
        : 'Die Zahlen eines einzelnen Monats im Stil der Cockpit-Monatsansicht. Sobald ein Monat erfasst ist, lässt er sich hier auswählen.',
      url: monatsberichtUrl(),
      filename: monatsberichtDatei(),
      accent: 'text-indigo-500',
      breit: true,
      disabled: verfuegbareMonate.length === 0,
      disabledHint: 'Noch kein Monat erfasst — es gäbe nichts zu berichten. Monatsabschluss unter Cockpit → Monat.',
      optionen: verfuegbareMonate.length > 0 ? (
        <div className="space-y-3">
          {/* Dieselbe Ursache wie beim Zeitraum darüber — hier fällt sie nur
              nicht auf, weil die Karte über die volle Breite läuft und die
              Monatsnamen kurz sind. Trotzdem gleich behandelt: ein Layout, das
              nur wegen der Textlänge hält, hält beim nächsten Text nicht. */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 min-w-0">
            <label htmlFor="monatsbericht-monat" className="text-sm text-gray-700 dark:text-gray-300 shrink-0">
              Monat:
            </label>
            <Select
              id="monatsbericht-monat"
              className="truncate"
              value={monatsberichtRef}
              onChange={(e) => setMonatsberichtRef(e.target.value)}
              options={verfuegbareMonate.map(m => ({
                value: `${m.jahr}-${m.monat}`,
                label: `${MONAT_NAMEN[m.monat]} ${m.jahr}`,
              }))}
            />
          </div>

          {/* Fünf Themenschalter — voreingestellt alle an. Sie bestimmen, WAS
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

          {/* Nur zeigen, wenn wirklich etwas geparkt ist — eine Frage ohne
              Gegenstand ist schlechter als keine Frage. */}
          {geparkt.length > 0 && (
            <Checkbox
              id="monatsbericht-ohne-geparkte"
              label={`Wie in meiner Monatsansicht (${geparkt.length} geparkte ${geparkt.length === 1 ? 'Anzeige' : 'Anzeigen'} weglassen)`}
              checked={ohneGeparkte}
              onChange={() => setOhneGeparkte(v => !v)}
            />
          )}
        </div>
      ) : undefined,
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
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Download-Hub für alle Dokumente dieser Anlage.
          </p>
          {/* Ein Modus statt zweier Bedienelemente an derselben Ecke. */}
          <Checkbox
            id="dokumente-zip-modus"
            label="Mehrere als ZIP"
            checked={zipModus}
            onChange={() => {
              setZipModus(v => !v)
              setZipAuswahl(new Set())
            }}
          />
        </div>

        {error && (
          <Alert type="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {cards.map(card => {
            const isLoading = loading === card.titel
            const isDisabled = !!card.disabled
            const waehlbar = zipModus && !!card.zipKey && !isDisabled
            const gewaehlt = !!card.zipKey && zipAuswahl.has(card.zipKey)
            return (
              <div
                key={card.titel}
                // Stabiler Anker statt einer Klassenkombination: die Probe
                // „die Einstellungen stehen IN der Karte, die sie steuern"
                // braucht die Kartengrenze, und `flex flex-col` steht auch an
                // der Options-Zeile darin.
                data-dokument={card.titel}
                className={`flex flex-col ${card.breit ? 'md:col-span-2' : ''}`}
              >
                {/* Wächter-Ausnahme: die Karten-KACHEL ist ein roher <button>
                    (ganze Fläche klickbar). Im ZIP-Modus wählt derselbe Klick
                    aus, statt zu laden — deshalb steht das Kästchen NICHT als
                    eigenes Bedienelement darin (verschachtelte interaktive
                    Elemente), sondern als Zustand am Knopf selbst. */}
                <button
                  type="button"
                  onClick={() => {
                    if (waehlbar) toggleZipAuswahl(card.zipKey!)
                    else handleDownload(card)
                  }}
                  disabled={!!loading || isDisabled || (zipModus && !card.zipKey)}
                  aria-pressed={waehlbar ? gewaehlt : undefined}
                  className={`
                    group flex-1 p-4 rounded-lg border bg-white dark:bg-gray-800 text-left
                    ${card.optionen ? 'rounded-b-none border-b-0' : ''}
                    ${gewaehlt
                      ? 'border-indigo-400 dark:border-indigo-500'
                      : 'border-gray-200 dark:border-gray-700'}
                    ${isDisabled || (zipModus && !card.zipKey)
                      ? 'opacity-50 cursor-not-allowed disabled:cursor-not-allowed'
                      : 'hover:border-gray-300 dark:hover:border-gray-600 transition-colors disabled:opacity-60 disabled:cursor-wait'}
                  `}
                >
                  <div className="flex items-start gap-3 mb-2">
                    <div className={card.accent}>{card.icon}</div>
                    <div className="flex-1">
                      <h3 className="font-semibold text-gray-900 dark:text-white">{card.titel}</h3>
                    </div>
                    {isLoading
                      ? <Loader2 className="h-4 w-4 text-gray-400 dark:text-gray-500 animate-spin" />
                      : waehlbar
                        ? (gewaehlt
                            ? <CheckSquare className="h-4 w-4 text-indigo-500" aria-label="für ZIP ausgewählt" />
                            : <Square className="h-4 w-4 text-gray-400 dark:text-gray-500" aria-label="nicht ausgewählt" />)
                        : !isDisabled && !zipModus && <Download className="h-4 w-4 text-gray-400 dark:text-gray-500 group-hover:text-gray-600 dark:group-hover:text-gray-200" />
                    }
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-400 leading-snug">{card.beschreibung}</p>
                  {isDisabled && card.disabledHint && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 leading-snug mt-2">
                      {card.disabledHint}
                    </p>
                  )}
                  {zipModus && !card.zipKey && !isDisabled && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 leading-snug mt-2">
                      Nicht im Sammel-ZIP — er deckt genau einen Monat ab, den du unten wählst.
                    </p>
                  )}
                </button>

                {/* Die Einstellungen DIESES Dokuments — in seiner Karte, unter
                    einer Trennlinie. Sie stehen außerhalb des <button>, sonst
                    lägen Select und Checkboxen in einem Knopf. */}
                {card.optionen && (
                  <div className="px-4 py-3 border border-t-0 border-gray-200 dark:border-gray-700 rounded-b-lg bg-white dark:bg-gray-800">
                    {card.optionen}
                  </div>
                )}
              </div>
            )
          })}
        </div>

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

        {zipModus && zipBerichte.length < 2 && (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Karten antippen, um sie auszuwählen — ab zwei Berichten gibt es das ZIP.
          </p>
        )}
      </div>
    </Modal>
  )
}
