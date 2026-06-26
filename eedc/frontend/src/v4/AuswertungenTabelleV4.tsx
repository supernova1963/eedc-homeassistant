/**
 * AuswertungenTabelleV4 — die Werte-Werkbank im /v4-Baum (A.5 Sub 1).
 *
 * Zwei verschiebbare BlockShell-Blöcke, jeder mit einer **fest im Block verankerten**
 * Zeitraum-/Vergleich-Leiste (`WerkbankZeitraum`, Gernot 2026-06-26: nicht schwebend):
 *   • „Monatswerte"   — Monats-Granularität (`useWerteZeitreihe`), von/bis = Monate.
 *   • „Energieprofile" — Tages-Granularität (`useTagesWerte`/`getTageWerte`), von/bis = Tage.
 * Beide nutzen denselben Werte-SoT `WerteTabelle` mit Werkbank-eigenem Spalten-Scope
 * (`scope`/`defaultSpalten` → Cockpit-Embeds unberührt). Default-Spalten = Bild-1-Satz,
 * Vergleich = Vorjahr an (Monat: akt. Jahr↔Vorjahr · Tag: akt. Monat↔selber Monat Vorjahr).
 * Tabelle je parkbar (R6); geparkt → Block-Hülle ausgeblendet.
 */
import { useEffect, useMemo, useState } from 'react'
import { Table, CalendarDays } from 'lucide-react'
import { LoadingSpinner, Card } from '../components/ui'
import { BlockShell, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar, usePark } from '../components/park'
import { WerteTabelle } from '../components/werte'
import { monatsZeile, tagesZeile } from '../lib/werte'
import { useSelectedAnlage } from '../hooks'
import { useWerteZeitreihe } from './useWerteZeitreihe'
import { useTagesWerte, minusEinJahr } from './useTagesWerte'
import { WerkbankZeitraum, VergleichLeisteTag, type ZeitChip, type TagVergleichModus } from './WerkbankZeitraum'

const SICHT_KEY = 'v4-auswertungen-tabelle'
const SCOPE = 'auswertungen-werkbank'
// Bild-1-Default (Gernot 2026-06-26): Energie + Quoten, ohne Finanz-Spalten.
const DEFAULT_SPALTEN = ['erzeugung', 'eigenverbrauch', 'einspeisung', 'netzbezug', 'gesamtverbrauch', 'autarkie', 'evQuote']
const VGL_LABEL: Record<TagVergleichModus, string> = { vormonat: 'Vormonat', '30vj': '30 T VJ', '90vj': '90 T VJ', custom: 'Zeitraum' }

const pad = (n: number) => String(n).padStart(2, '0')
const letzterTag = (y: number, m: number) => new Date(y, m, 0).getDate()
function addTage(iso: string, tage: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d))
  dt.setUTCDate(dt.getUTCDate() + tage)
  return `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}`
}
/** Vergleichs-Label aus einem Zeitraum: bei Einzeljahr „<Vorjahr>", sonst „Vorjahr". */
function vergleichLabelVon(von: string, bis: string): string {
  const vy = Number(von.slice(0, 4)); const by = Number(bis.slice(0, 4))
  return vy === by ? `${vy - 1}` : 'Vorjahr'
}

export default function AuswertungenTabelleV4() {
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <TabelleInner />
    </ParkProvider>
  )
}

function TabelleInner() {
  const park = usePark()
  const { anlagen, selectedAnlageId, selectedAnlage, loading: anlagenLoading } = useSelectedAnlage()
  const { rows, jahre, loading, error } = useWerteZeitreihe(selectedAnlageId, selectedAnlage)

  // Neuestes (Jahr, Monat) als Default-Anker.
  const anker = useMemo(() => {
    if (rows.length === 0) return null
    const max = rows.reduce((acc, r) => (r.jahr * 100 + r.monat > acc.jahr * 100 + acc.monat ? r : acc), rows[0])
    return { jahr: max.jahr, monat: max.monat }
  }, [rows])

  // ── Monats-Block: von/bis (YYYY-MM) + Vergleich ──
  const [monVon, setMonVon] = useState('')
  const [monBis, setMonBis] = useState('')
  const [monVergleich, setMonVergleich] = useState(true)
  useEffect(() => {
    if (!anker || monVon) return
    setMonVon(`${anker.jahr}-01`); setMonBis(`${anker.jahr}-12`)
  }, [anker, monVon])

  // ── Energieprofil-Block: von/bis (YYYY-MM-DD) + Vergleichs-Auswahl ──
  const [tagVon, setTagVon] = useState('')
  const [tagBis, setTagBis] = useState('')
  const [vglModus, setVglModus] = useState<TagVergleichModus>('30vj')
  const [vglCustomVon, setVglCustomVon] = useState('')
  const [vglCustomBis, setVglCustomBis] = useState('')
  useEffect(() => {
    if (!anker || tagVon) return
    setTagVon(`${anker.jahr}-${pad(anker.monat)}-01`)
    setTagBis(`${anker.jahr}-${pad(anker.monat)}-${pad(letzterTag(anker.jahr, anker.monat))}`)
  }, [anker, tagVon])

  if (anlagenLoading || loading) return <LoadingSpinner text="Lade Werte…" />
  if (anlagen.length === 0) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage angelegt.</p></Card>
      </div>
    )
  }
  if (error) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-red-500">{error}</p></Card>
      </div>
    )
  }

  // ── Monats-Block-Daten ──
  const minJahr = jahre.length ? Math.min(...jahre) : (anker?.jahr ?? 0)
  const maxJahr = jahre.length ? Math.max(...jahre) : (anker?.jahr ?? 0)
  const monVonNum = monVon ? Number(monVon.slice(0, 4)) * 100 + Number(monVon.slice(5, 7)) : 0
  const monBisNum = monBis ? Number(monBis.slice(0, 4)) * 100 + Number(monBis.slice(5, 7)) : 999999
  const monRows = rows.filter((r) => { const n = r.jahr * 100 + r.monat; return n >= monVonNum && n <= monBisNum })
  const monVorjahr = monVergleich
    ? rows.filter((r) => { const n = r.jahr * 100 + r.monat; return n >= monVonNum - 100 && n <= monBisNum - 100 })
    : null

  const monChips: ZeitChip[] = anker ? [
    { label: 'Aktuelles Jahr', range: () => [`${anker.jahr}-01`, `${anker.jahr}-12`], aktiv: monVon === `${anker.jahr}-01` && monBis === `${anker.jahr}-12` },
    { label: 'Alle Jahre', range: () => [`${minJahr}-01`, `${maxJahr}-12`], aktiv: monVon === `${minJahr}-01` && monBis === `${maxJahr}-12` },
  ] : []

  const monGeparkt = park.istGeparkt('tabelle:monatswerte')
  const tagGeparkt = park.istGeparkt('tabelle:energieprofile')

  const bloecke: Block[] = []
  if (!monGeparkt) {
    bloecke.push({
      id: 'monatswerte', title: 'Monatswerte', icon: Table, farbe: 'text-gray-400',
      summary: `${monVon || '…'} – ${monBis || '…'}${monVergleich ? ' · vs. Vorjahr' : ''}`, defaultOpen: true,
      render: () => (
        <div className="space-y-3">
          <WerkbankZeitraum
            modus="monat" von={monVon} bis={monBis}
            onRange={(v, b) => { setMonVon(v); setMonBis(b) }}
            vergleich={monVergleich} onVergleich={setMonVergleich} chips={monChips}
          />
          <Parkbar id="tabelle:monatswerte" titel="Monatswerte">
            <WerteTabelle
              rows={monRows.map(monatsZeile)}
              vorjahrRows={monVorjahr ? monVorjahr.map(monatsZeile) : null}
              granularitaet="monat"
              vergleichLabel={monVergleich ? vergleichLabelVon(monVon, monBis) : null}
              vergleichDefaultAn={monVergleich}
              scope={SCOPE} defaultSpalten={DEFAULT_SPALTEN}
              csvDateiname={`werte_monat_${selectedAnlage?.anlagenname ?? 'export'}.csv`}
            />
          </Parkbar>
        </div>
      ),
    })
  }
  if (!tagGeparkt) {
    bloecke.push({
      id: 'energieprofile', title: 'Energieprofile (Tageswerte)', icon: CalendarDays, farbe: 'text-gray-400',
      summary: `${tagVon || '…'} – ${tagBis || '…'} · Vgl. ${VGL_LABEL[vglModus]}`, defaultOpen: false,
      render: () => (
        <EnergieprofilBlock
          anlageId={selectedAnlageId!} von={tagVon} bis={tagBis}
          onRange={(v, b) => { setTagVon(v); setTagBis(b) }}
          vglModus={vglModus} onVglModus={setVglModus}
          vglCustomVon={vglCustomVon} vglCustomBis={vglCustomBis}
          onVglCustomVon={setVglCustomVon} onVglCustomBis={setVglCustomBis}
          anker={anker} anlagenname={selectedAnlage?.anlagenname}
        />
      ),
    })
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <h1 className="text-lg font-bold text-gray-900 dark:text-white">Werte-Werkbank</h1>
      <BlockShell key="werkbank" persistKey={SICHT_KEY} bloecke={bloecke} sortierbar />
      <ParkFuss />
    </div>
  )
}

/** Vergleichsbereich (von/bis) aus Modus + primärem Zeitraum. null = keiner. */
function tagVergleichRange(
  modus: TagVergleichModus, von: string, bis: string, cVon: string, cBis: string,
): { von: string; bis: string } | null {
  if (modus === 'custom') return cVon && cBis ? { von: cVon, bis: cBis } : null
  if (modus === 'vormonat') {
    const [y, m] = von.split('-').map(Number)
    const py = m === 1 ? y - 1 : y
    const pm = m === 1 ? 12 : m - 1
    return { von: `${py}-${pad(pm)}-01`, bis: `${py}-${pad(pm)}-${pad(letzterTag(py, pm))}` }
  }
  const vBis = minusEinJahr(bis)
  return { von: addTage(vBis, modus === '30vj' ? -29 : -89), bis: vBis }
}

/** Tages-Block: lazy (mountet erst beim Aufklappen) → lädt nur dann die Tageswerte. */
function EnergieprofilBlock({
  anlageId, von, bis, onRange, vglModus, onVglModus, vglCustomVon, vglCustomBis,
  onVglCustomVon, onVglCustomBis, anker, anlagenname,
}: {
  anlageId: number
  von: string; bis: string
  onRange: (von: string, bis: string) => void
  vglModus: TagVergleichModus
  onVglModus: (m: TagVergleichModus) => void
  vglCustomVon: string; vglCustomBis: string
  onVglCustomVon: (v: string) => void; onVglCustomBis: (v: string) => void
  anker: { jahr: number; monat: number } | null
  anlagenname?: string
}) {
  const vgl = von && bis ? tagVergleichRange(vglModus, von, bis, vglCustomVon, vglCustomBis) : null
  const { rows, vorjahrRows, loading, error } = useTagesWerte(anlageId, von, bis, vgl?.von ?? null, vgl?.bis ?? null)

  const monatEnde = anker ? `${anker.jahr}-${pad(anker.monat)}-${pad(letzterTag(anker.jahr, anker.monat))}` : bis
  const chips: ZeitChip[] = anker ? [
    {
      label: 'Aktueller Monat',
      range: () => [`${anker.jahr}-${pad(anker.monat)}-01`, `${anker.jahr}-${pad(anker.monat)}-${pad(letzterTag(anker.jahr, anker.monat))}`],
      aktiv: von === `${anker.jahr}-${pad(anker.monat)}-01`,
    },
    { label: '30 Tage', range: () => [addTage(monatEnde, -29), monatEnde] },
    { label: '90 Tage', range: () => [addTage(monatEnde, -89), monatEnde] },
  ] : []

  return (
    <div className="space-y-3">
      <WerkbankZeitraum
        modus="tag" von={von} bis={bis} onRange={onRange} chips={chips}
        vergleichSlot={
          <VergleichLeisteTag
            modus={vglModus} onModus={onVglModus}
            customVon={vglCustomVon} customBis={vglCustomBis}
            onCustomVon={onVglCustomVon} onCustomBis={onVglCustomBis}
          />
        }
      />
      {loading ? (
        <LoadingSpinner text="Lade Tageswerte…" />
      ) : error ? (
        <p className="text-red-500 text-sm">{error}</p>
      ) : (
        <Parkbar id="tabelle:energieprofile" titel="Energieprofile (Tageswerte)">
          <WerteTabelle
            rows={rows.map(tagesZeile)}
            vorjahrRows={vorjahrRows ? vorjahrRows.map(tagesZeile) : null}
            granularitaet="tag"
            vergleichLabel={vgl ? VGL_LABEL[vglModus] : null}
            vergleichDefaultAn={!!vgl}
            scope={SCOPE} defaultSpalten={DEFAULT_SPALTEN}
            csvDateiname={`werte_tag_${anlagenname ?? 'export'}.csv`}
          />
        </Parkbar>
      )}
    </div>
  )
}
