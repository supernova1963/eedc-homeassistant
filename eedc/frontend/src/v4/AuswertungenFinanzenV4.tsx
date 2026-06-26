/**
 * AuswertungenFinanzenV4 — Finanz-Auswertung (A.5, substanzieller Sub-Bereich).
 *
 * Drei Blöcke (Muster, BlockShell):
 *  ① „Finanz-Übersicht" — IST-Tab `FinanzenTab` unverändert wiederverwendet
 *     (KPIs/Erlöse-Kosten-Netto-Chart/kumulierter Ertrag/historische Monatstarife;
 *     Jahr-Filter im Kopf, eine Code-Wahrheit).
 *  ② „SOLL/HABEN-T-Konto" — der geteilte `TKonto`-SoT mit EIGENEM Zeit-Selektor:
 *     Monat (kanonische Monats-Antwort) · Jahr (Σ-12 via `baueJahrAlsMonat`,
 *     kein Backend — Gernot-Entscheid D2; Tag entfällt, Finanzen sind monatlich).
 *  ③ „Berichte & Dokumente" — Cross-Link-Teaser auf den PDF-Finanzbericht (G10;
 *     zentrale Berichtsverwaltung folgt in Einstellungen, Phase C).
 */
import { useEffect, useMemo, useState } from 'react'
import { Wallet, FileText } from 'lucide-react'
import { LoadingSpinner, Card } from '../components/ui'
import { BlockShell } from '../components/blocks/BlockShell'
import type { Block } from '../components/blocks/types'
import { FinanzenTab } from '../pages/auswertung/FinanzenTab'
import { TKonto } from '../components/finanzen/TKonto'
import { baueJahrAlsMonat } from './JahrAggregat'
import { aktuellerMonatApi, type AktuellerMonatResponse } from '../api/aktuellerMonat'
import { cockpitApi } from '../api/cockpit'
import { importApi } from '../api/import'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import { MONAT_NAMEN } from '../lib/constants'
import { useSelectedAnlage } from '../hooks'
import { useAuswertungBasis } from './useAuswertungBasis'
import { AuswertungKopf } from './AuswertungKopf'

const MONATE_1_12 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

/** Segment-Button für den Monat/Jahr-Umschalter. */
function SegBtn({ aktiv, onClick, children }: { aktiv: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1.5 text-sm font-medium transition-colors ${
        aktiv
          ? 'bg-primary-600 text-white'
          : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
      }`}
    >
      {children}
    </button>
  )
}

/** T-Konto mit eigenem Zeit-Selektor (Monat | Jahr). Lädt die Period-Daten
 *  selbst: Monat = `getData`, Jahr = Σ-12 (`baueJahrAlsMonat`). */
function TKontoPeriode({ anlageId, daten, jahre }: {
  anlageId: number | undefined | null
  daten: AggregierteMonatsdaten[]
  jahre: number[]
}) {
  const [modus, setModus] = useState<'monat' | 'jahr'>('monat')
  const [jahr, setJahr] = useState<number | null>(null)
  const [monat, setMonat] = useState<number | null>(null)
  const [d, setD] = useState<AktuellerMonatResponse | null>(null)
  const [sonderkosten, setSonderkosten] = useState<number | null>(null)
  const [laden, setLaden] = useState(false)

  // Verfügbare Monate im gewählten Jahr (absteigend wäre untypisch für Monate → aufsteigend).
  const monate = useMemo(
    () => (jahr == null ? [] : [...new Set(daten.filter((r) => r.jahr === jahr).map((r) => r.monat))].sort((a, b) => a - b)),
    [daten, jahr],
  )

  // Default-Jahr = neuestes.
  useEffect(() => { if (jahr == null && jahre.length) setJahr(jahre[0]) }, [jahre, jahr])
  // Default-/Korrektur-Monat = letzter im Jahr.
  useEffect(() => {
    if (monate.length === 0) return
    if (monat == null || !monate.includes(monat)) setMonat(monate[monate.length - 1])
  }, [monate, monat])

  useEffect(() => {
    if (!anlageId || jahr == null) return
    let ab = false
    setLaden(true)
    if (modus === 'monat') {
      if (monat == null) { setLaden(false); return }
      Promise.all([
        aktuellerMonatApi.getData(anlageId, jahr, monat),
        cockpitApi.getKomponentenZeitreihe(anlageId, jahr)
          .then((kt) => kt.monatswerte?.find((v) => v.monat === monat)?.sonstige_ausgaben_euro ?? null)
          .catch(() => null),
      ])
        .then(([resp, sk]) => { if (!ab) { setD(resp); setSonderkosten(sk) } })
        .catch(() => { if (!ab) setD(null) })
        .finally(() => { if (!ab) setLaden(false) })
    } else {
      Promise.all(MONATE_1_12.map((m) => aktuellerMonatApi.getData(anlageId, jahr, m).catch(() => null)))
        .then((resps) => {
          if (ab) return
          const ok = resps.filter((r): r is AktuellerMonatResponse => r != null)
          setD(ok.length ? baueJahrAlsMonat(ok, jahr) : null)
          setSonderkosten(null) // Jahr: per-Inv-Σ deckt die Kosten ab, kein Monats-Fallback.
        })
        .finally(() => { if (!ab) setLaden(false) })
    }
    return () => { ab = true }
  }, [anlageId, modus, jahr, monat])

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <SegBtn aktiv={modus === 'monat'} onClick={() => setModus('monat')}>Monat</SegBtn>
          <SegBtn aktiv={modus === 'jahr'} onClick={() => setModus('jahr')}>Jahr</SegBtn>
        </div>
        <select
          value={jahr ?? ''}
          onChange={(e) => setJahr(e.target.value ? Number(e.target.value) : null)}
          aria-label="Jahr wählen"
          className="input w-auto"
        >
          {jahre.map((j) => <option key={j} value={j}>{j}</option>)}
        </select>
        {modus === 'monat' && (
          <select
            value={monat ?? ''}
            onChange={(e) => setMonat(e.target.value ? Number(e.target.value) : null)}
            aria-label="Monat wählen"
            className="input w-auto"
          >
            {monate.map((m) => <option key={m} value={m}>{MONAT_NAMEN[m]}</option>)}
          </select>
        )}
      </div>
      {laden ? (
        <LoadingSpinner text="Lade T-Konto…" />
      ) : d ? (
        <TKonto d={d} sonderkosten={sonderkosten} />
      ) : (
        <p className="text-sm text-gray-500 dark:text-gray-400">Für den gewählten Zeitraum liegen keine Finanzdaten vor.</p>
      )}
    </div>
  )
}

/** G10 — Cross-Link-Teaser auf den PDF-Finanzbericht. */
function FinanzberichtTeaser({ anlageId, jahr }: { anlageId: number | undefined | null; jahr: number | 'alle' }) {
  if (!anlageId) return null
  const url = importApi.getPdfZipExportUrl(anlageId, ['finanzbericht'], jahr === 'alle' ? null : jahr)
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Finanzbericht als PDF erzeugen{jahr !== 'alle' ? ` (Jahr ${jahr})` : ' (Gesamtzeitraum)'} — die zentrale
        Berichts-/Dokumentenverwaltung folgt in den Einstellungen.
      </p>
      <a
        href={url}
        className="min-h-[44px] inline-flex items-center gap-2 px-4 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700"
      >
        <FileText className="h-4 w-4" /> Finanzbericht (PDF)
      </a>
    </div>
  )
}

export default function AuswertungenFinanzenV4() {
  const { anlagen, selectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const basis = useAuswertungBasis(selectedAnlageId)

  if (anlagenLoading || basis.loading) return <LoadingSpinner text="Lade Finanzdaten…" />
  if (anlagen.length === 0) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage angelegt.</p></Card>
      </div>
    )
  }

  const bloecke: Block[] = [
    {
      id: 'uebersicht', title: 'Finanz-Übersicht', icon: Wallet, defaultOpen: true,
      summary: 'Erlöse · Ersparnisse · Netto-Ertrag über die Zeit',
      render: () => (
        <FinanzenTab
          data={basis.gefiltert}
          stats={basis.stats}
          strompreis={basis.strompreis}
          alleTarife={basis.alleTarife}
          anlageId={selectedAnlageId}
          zeitraumLabel={basis.zeitraumLabel}
        />
      ),
    },
    {
      id: 'tkonto', title: 'SOLL/HABEN-T-Konto', icon: Wallet, defaultOpen: true,
      summary: 'anlage-weite Kosten vs. Erlöse + Einsparungen (Monat oder Jahr)',
      render: () => <TKontoPeriode anlageId={selectedAnlageId} daten={basis.daten} jahre={basis.jahre} />,
    },
    {
      id: 'berichte', title: 'Berichte & Dokumente', icon: FileText, defaultOpen: false,
      summary: 'Finanzbericht als PDF',
      render: () => <FinanzberichtTeaser anlageId={selectedAnlageId} jahr={basis.jahr} />,
    },
  ]

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <AuswertungKopf titel="Finanzen" jahr={basis.jahr} setJahr={basis.setJahr} jahre={basis.jahre} />
      <BlockShell bloecke={bloecke} persistKey="v4-auswertungen-finanzen" />
    </div>
  )
}
