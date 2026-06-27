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
import { monatsZeile, tagesZeile, type WerteZeile } from '../lib/werte'
import { useSelectedAnlage } from '../hooks'
import { useWerteZeitreihe } from './useWerteZeitreihe'
import { useTagesWerte } from './useTagesWerte'
import { WerkbankZeitraum, VergleichLeisteTag, type ZeitChip, type TagVergleichModus } from './WerkbankZeitraum'

const SICHT_KEY = 'v4-auswertungen-tabelle'
const SCOPE = 'auswertungen-werkbank'
// Bild-1-Default (Gernot 2026-06-26): Energie + Quoten, ohne Finanz-Spalten.
const DEFAULT_SPALTEN = ['erzeugung', 'eigenverbrauch', 'einspeisung', 'netzbezug', 'gesamtverbrauch', 'autarkie', 'evQuote']
const vglLabel = (modus: TagVergleichModus, jahr: number) => (modus === 'periodeImJahr' ? String(jahr) : 'Vorperiode')

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
  const [vglModus, setVglModus] = useState<TagVergleichModus>('vorperiode')
  const [vglJahr, setVglJahr] = useState(0)  // 0 = noch nicht initialisiert (s. Effekt)
  useEffect(() => {
    if (!anker || tagVon) return
    setTagVon(`${anker.jahr}-${pad(anker.monat)}-01`)
    setTagBis(`${anker.jahr}-${pad(anker.monat)}-${pad(letzterTag(anker.jahr, anker.monat))}`)
  }, [anker, tagVon])
  useEffect(() => {
    if (!anker || vglJahr) return
    setVglJahr(anker.jahr - 1)  // Default-Vergleichsjahr = Primär-Jahr − 1
  }, [anker, vglJahr])

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
      id: 'energieprofile', title: 'Tageswerte', icon: CalendarDays, farbe: 'text-gray-400',
      summary: `${tagVon || '…'} – ${tagBis || '…'} · Vgl. ${vglLabel(vglModus, vglJahr)}`, defaultOpen: false,
      render: () => (
        <EnergieprofilBlock
          anlageId={selectedAnlageId!} von={tagVon} bis={tagBis}
          onRange={(v, b) => { setTagVon(v); setTagBis(b) }}
          vglModus={vglModus} onVglModus={setVglModus}
          vglJahr={vglJahr} onVglJahr={setVglJahr} jahre={jahre}
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

const keyOf = (iso: string) => { const [y, m, d] = iso.split('-').map(Number); return y * 10000 + m * 100 + d }
/** Tage in [von..bis] inklusiv. */
function tageInklusiv(von: string, bis: string): number {
  const [ay, am, ad] = von.split('-').map(Number)
  const [by, bm, bd] = bis.split('-').map(Number)
  return Math.round((Date.UTC(by, bm - 1, bd) - Date.UTC(ay, am - 1, ad)) / 86400000) + 1
}
/** ISO um `delta` Jahre verschieben, 29.2. aufs Monatsende geklemmt. */
function shiftJahr(iso: string, delta: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const ny = y + delta
  return `${ny}-${pad(m)}-${pad(Math.min(d, letzterTag(ny, m)))}`
}

type VglAlign = 'position' | 'kalender'
interface VglKonfig { von: string; bis: string; align: VglAlign; vor?: (iso: string) => string }

/**
 * Vergleichs-Konfiguration aus Modus + primärem Zeitraum + Vergleichsjahr (Gernot
 * 2026-06-27). Das Vergleichsfenster ist IMMER gleich lang wie der Primärbereich:
 *  • vorperiode — die gleich langen Tage direkt davor → **Positions-Ausrichtung**.
 *  • periodeImJahr — derselbe Spann ins Jahr `jahr` verschoben → **Kalender-Ausrichtung**
 *    (`vor()` bildet eine Vergleichszeile vorwärts auf ihren Primärtag ab).
 */
export function tagVergleich(
  modus: TagVergleichModus, von: string, bis: string, jahr: number,
): VglKonfig | null {
  if (!von || !bis) return null
  if (modus === 'vorperiode') {
    const cBisP = addTage(von, -1)
    return { von: addTage(cBisP, -(tageInklusiv(von, bis) - 1)), bis: cBisP, align: 'position' }
  }
  // periodeImJahr: Primärbereich um (jahr − Primär-Jahr) verschieben.
  const delta = jahr - Number(von.slice(0, 4))
  if (delta === 0) return null  // selbes Jahr = kein sinnvoller Vergleich
  return { von: shiftJahr(von, delta), bis: shiftJahr(bis, delta), align: 'kalender', vor: (iso) => shiftJahr(iso, -delta) }
}

/**
 * Re-Keying der Tageszeilen für die Vergleichs-Ausrichtung (s. {@link tagVergleich}).
 * Positions-Ausrichtung: chronologischer Index als Match-Key (Zeile i ↔ i). Kalender:
 * Primär behält den Datum-Key, Vergleich wird vorwärts auf den Primärtag abgebildet.
 */
export function richteAus(prim: WerteZeile[], comp: WerteZeile[] | null, vgl: VglKonfig | null): {
  primZeilen: WerteZeile[]; vglZeilen: WerteZeile[] | null
} {
  if (!vgl || !comp) return { primZeilen: prim, vglZeilen: comp }
  if (vgl.align === 'position') {
    return {
      primZeilen: [...prim].sort((a, b) => a.sortKey - b.sortKey).map((z, i) => ({ ...z, vergleichKey: i })),
      vglZeilen: [...comp].sort((a, b) => a.sortKey - b.sortKey).map((z, i) => ({ ...z, vergleichKey: i })),
    }
  }
  return {
    primZeilen: prim.map((z) => ({ ...z, vergleichKey: z.sortKey })),
    vglZeilen: comp.map((z) => ({ ...z, vergleichKey: vgl.vor ? keyOf(vgl.vor(z.id)) : z.sortKey })),
  }
}

/** Tages-Block: lazy (mountet erst beim Aufklappen) → lädt nur dann die Tageswerte. */
function EnergieprofilBlock({
  anlageId, von, bis, onRange, vglModus, onVglModus, vglJahr, onVglJahr, jahre, anker, anlagenname,
}: {
  anlageId: number
  von: string; bis: string
  onRange: (von: string, bis: string) => void
  vglModus: TagVergleichModus
  onVglModus: (m: TagVergleichModus) => void
  vglJahr: number
  onVglJahr: (j: number) => void
  jahre: number[]
  anker: { jahr: number; monat: number } | null
  anlagenname?: string
}) {
  const vgl = useMemo(
    () => (von && bis ? tagVergleich(vglModus, von, bis, vglJahr) : null),
    [von, bis, vglModus, vglJahr],
  )
  const { rows, vorjahrRows, loading, error } = useTagesWerte(anlageId, von, bis, vgl?.von ?? null, vgl?.bis ?? null)
  const { primZeilen, vglZeilen } = useMemo(
    () => richteAus(rows.map(tagesZeile), vorjahrRows ? vorjahrRows.map(tagesZeile) : null, vgl),
    [rows, vorjahrRows, vgl],
  )

  // Primär-Schnellwahl: füllt nur von–bis (Gernot 2026-06-27). Vormonat = Monat vor dem Anker.
  const vm = anker ? (anker.monat === 1 ? { jahr: anker.jahr - 1, monat: 12 } : { jahr: anker.jahr, monat: anker.monat - 1 }) : null
  const monatRange = (j: number, m: number): [string, string] => [`${j}-${pad(m)}-01`, `${j}-${pad(m)}-${pad(letzterTag(j, m))}`]
  const chips: ZeitChip[] = anker ? [
    { label: 'Aktueller Monat', range: () => monatRange(anker.jahr, anker.monat), aktiv: von === `${anker.jahr}-${pad(anker.monat)}-01` },
    ...(vm ? [{ label: 'Vormonat', range: (): [string, string] => monatRange(vm.jahr, vm.monat), aktiv: von === `${vm.jahr}-${pad(vm.monat)}-01` }] : []),
  ] : []

  // Vergleichsjahr-Optionen = Datenjahre (+ aktuelle Wahl), absteigend.
  const jahrOptionen = Array.from(new Set([...jahre, vglJahr].filter((j) => j > 0))).sort((a, b) => b - a)

  return (
    <div className="space-y-3">
      <WerkbankZeitraum
        modus="tag" von={von} bis={bis} onRange={onRange} chips={chips}
        vergleichSlot={
          <VergleichLeisteTag
            modus={vglModus} onModus={onVglModus}
            jahr={vglJahr} onJahr={onVglJahr} jahre={jahrOptionen}
          />
        }
      />
      {loading && rows.length === 0 ? (
        // Spinner nur beim Erst-Load; bei Zeitraum-/Vergleichswechsel bleibt die
        // bestehende Tabelle stehen und aktualisiert sich in-place (detLAN D7-6).
        <LoadingSpinner text="Lade Tageswerte…" />
      ) : error ? (
        <p className="text-red-500 text-sm">{error}</p>
      ) : (
        <Parkbar id="tabelle:energieprofile" titel="Tageswerte">
          <WerteTabelle
            rows={primZeilen}
            vorjahrRows={vglZeilen}
            granularitaet="tag"
            vergleichLabel={vgl ? vglLabel(vglModus, vglJahr) : null}
            vergleichDefaultAn={!!vgl}
            scope={SCOPE} defaultSpalten={DEFAULT_SPALTEN}
            csvDateiname={`werte_tag_${anlagenname ?? 'export'}.csv`}
          />
        </Parkbar>
      )}
    </div>
  )
}
