/**
 * WerteTabelle — die EINE Werte-Tabelle (IA v4 Werte-SoT, W1/W2).
 *
 * Gleiche Funktion + Aussehen — egal in welcher Granularität (Monats- oder
 * Tageszeilen) und egal wo eingebettet (Cockpit-Zeitsichten, Komponenten,
 * eigene Werkbank-Seite). Es unterscheiden sich NUR die übergebenen Zeiträume
 * (Zeilen-Granularität) und der je Granularität verfügbare Metrik-Satz
 * (`metrikenFuer`): voller Spalten-Picker (Sichtbarkeit + Reihenfolge je
 * Gruppe), CSV-Export, Vergleich (aktuell · Vergleich · Δ) und Footer-Aggregat
 * sind überall vorhanden (Gernot-Konzept 2026-06-16; löst die frühere
 * W3-read-only-Embed-Idee ab).
 *
 * Eingabe ist die normalisierte {@link WerteZeile} (`lib/werte/zeile`); die
 * Vergleichs-/CSV-/Footer-Logik ist in `lib/werte` zentralisiert. Die
 * Werte-SoT der Tabellen-Sichten. Die frühere Produktiv-Seite
 * `pages/auswertung/TabelleTab.tsx` ist mit dem IA-V4-Flip gefallen — diese
 * Komponente ist seither nicht mehr der künftige, sondern der geltende SoT.
 */
import { Fragment, useEffect, useMemo, useState } from 'react'
import { Columns, GitCompareArrows, ChevronUp, ChevronDown, ArrowRight } from 'lucide-react'
import { Button, Checkbox, CsvExportButton } from '../ui'
// Tabellen-SoT (Regel T): Container liefert Höhenfenster, klebenden Kopf/Fuß und
// sichtbare Leisten. Zellen nutzen die exportierte Typo — `TableCell`/`TableHeader`
// würden hier mit den Farbvarianten (Vorjahr grau, Delta klein) kollidieren.
import { Table, TableBody, TableFoot, TableHead, TableSortKopf } from '../ui/Table'
import { ZELLE, KOPF_ZELLE } from '../ui/tabelleMasse'
import {
  WERTE_GRUPPEN, GRUPPE_LABELS,
  fmtWert, alsAngezeigt, aggregiere, bewerteDelta, exportWerteCsv, metrikenFuer,
  vergleichLookup, vergleichsAggregatBasis, gepaarteVergleichsZeilen,
  type WerteMetrik, type WerteZeile, type Granularitaet,
} from '../../lib/werte'

// Dokumentierte KONVENTION (R3b E2, Gernot 2026-07-05): eigenes 2-stufiges
// Urteil-Vokabular der WerteTabelle (bewerteDelta: gut/schlecht/neutral) —
// bewusst NICHT aus AMPEL_TEXT_CLASS abgeleitet (das ist die 4-stufige
// Gauge-Skala; hier gilt Delta-Semantik mit eigener Tönung gut=green-600).
const URTEIL_KLASSE: Record<string, string> = {
  gut: 'text-green-600 dark:text-green-400',
  schlecht: 'text-red-500 dark:text-red-400',
  neutral: 'text-gray-400 dark:text-gray-500',
}

/**
 * Die Δ-Spalte erklärt die zwei Spalten links von ihr — also rechnet sie mit
 * genau den Zahlen, die dort stehen (`alsAngezeigt`), nicht mit den Rohwerten
 * dahinter. Vorher konnte neben „0" und „12" ein „▼ 11 (−97,6 %)" stehen und
 * neben zweimal „0" ein „▼ 0 (−73,3 %)" (Striker, T89667 #162).
 *
 * Folge, die so gewollt ist: Was unterhalb der Anzeige-Genauigkeit liegt, ist
 * kein Unterschied mehr — die Zeile zeigt „=" statt einer Prozentzahl ohne
 * sichtbare Grundlage. Wer die Feinheit sehen will, schaltet die Spalte auf
 * mehr Stellen oder nimmt den CSV-Export, der die Rohwerte trägt.
 */
function DeltaZelle({ current, prev, metrik }: { current: number | null; prev: number | null; metrik: WerteMetrik }) {
  if (current == null || prev == null) return <span className="text-gray-300 dark:text-gray-600">—</span>
  const gezeigtCur = alsAngezeigt(current, metrik.decimals)
  const gezeigtPrev = alsAngezeigt(prev, metrik.decimals)
  const delta = gezeigtCur - gezeigtPrev
  const deltaPct = gezeigtPrev !== 0 ? (delta / Math.abs(gezeigtPrev)) * 100 : null
  const urteil = bewerteDelta(gezeigtCur, gezeigtPrev, metrik.higherIsBetter)
  const pfeil = delta > 0 ? '▲' : delta < 0 ? '▼' : '='
  return (
    <span className={URTEIL_KLASSE[urteil]}>
      {pfeil} {fmtWert(Math.abs(delta), metrik.decimals)}
      {deltaPct != null && (
        <span className="ml-1 opacity-75">({deltaPct > 0 ? '+' : ''}{fmtWert(deltaPct, 1)} %)</span>
      )}
    </span>
  )
}

export interface WerteTabelleProps {
  rows: WerteZeile[]
  /** Vergleichs-Zeilen (Vorjahr/Vergleichsmonat); aktiviert den cur/cmp/Δ-Toggle. */
  vorjahrRows?: WerteZeile[] | null
  /** Zeilen-Granularität → verfügbarer Metrik-Satz + Footer-Einheit + LS-Scope. */
  granularitaet?: Granularitaet
  jahrLabel?: string | number
  vergleichLabel?: string | number | null
  /** Optionaler Cross-Link „alle Werte / Export →" (z. B. im Cockpit-Embed). */
  alleWerteHref?: string
  csvDateiname?: string
  /** localStorage-Namensraum für Spaltenwahl/-reihenfolge. Default-Scope teilen sich
   *  alle Embeds (Cockpit/Komponenten); eine eigene Sicht (z. B. Werte-Werkbank)
   *  setzt einen eigenen Scope → unabhängige Spaltenwahl ohne Embed-Nebenwirkung. */
  scope?: string
  /** Initial sichtbare Spalten (Registry-keys) statt Registry-`defaultVisible` —
   *  greift nur, solange im Scope nichts gespeichert ist. */
  defaultSpalten?: string[]
  /** Vergleich (cur/cmp/Δ) initial eingeschaltet, falls Vergleichszeilen vorliegen. */
  vergleichDefaultAn?: boolean
  /** Anlagen-abhängige Zusatz-Spalten, die nicht in der Produkt-Registry stehen
   *  können — heute die Erträge je Erzeuger (#350, `erzeugerMetriken`). Sie
   *  verhalten sich wie jede andere Metrik (Picker, Sortierung, Δ, CSV, Fuß). */
  zusatzMetriken?: WerteMetrik[]
}

/** Stabile leere Zusatz-Liste — als Literal in der Signatur wäre sie bei jedem
 *  Render neu und würde die `useMemo`/`useEffect`-Ketten unten dauerhaft feuern. */
const KEINE_ZUSATZ_METRIKEN: WerteMetrik[] = []

export function WerteTabelle({
  rows,
  vorjahrRows = null,
  granularitaet = 'monat',
  jahrLabel = '',
  vergleichLabel = null,
  alleWerteHref,
  csvDateiname = 'werte_tabelle.csv',
  scope = 'werte-werkbank',
  defaultSpalten,
  vergleichDefaultAn = false,
  zusatzMetriken = KEINE_ZUSATZ_METRIKEN,
}: WerteTabelleProps) {
  // Verfügbare Metriken + Picker-Gruppen je Granularität, plus die anlagen-
  // abhängigen Zusatz-Spalten (#350).
  const verfuegbar = useMemo(
    () => [...metrikenFuer(granularitaet), ...zusatzMetriken.filter((m) => m.granular.includes(granularitaet))],
    [granularitaet, zusatzMetriken],
  )
  const verfuegbarKeys = useMemo(() => new Set(verfuegbar.map((m) => m.key)), [verfuegbar])
  // Lookup über die *verfügbaren* Metriken statt der Produkt-Registry — sonst
  // fänden Picker, Sortierung und Umsortieren die Zusatz-Spalten nicht.
  const metrikByKey = useMemo(
    () => Object.fromEntries(verfuegbar.map((m) => [m.key, m])) as Record<string, WerteMetrik>,
    [verfuegbar],
  )
  const gruppen = useMemo(
    () => WERTE_GRUPPEN.filter((g) => verfuegbar.some((m) => m.gruppe === g)),
    [verfuegbar],
  )
  const einheitLabel = granularitaet === 'tag' ? 'Tage' : 'Monate'
  // LS-Scope je Granularität, damit Monats-/Tages-Spaltenwahl unabhängig bleibt.
  const lsCols = `eedc-${scope}:cols:${granularitaet}`
  const lsOrder = `eedc-${scope}:order:${granularitaet}`
  // Default-Sichtbarkeit: explizite Werkbank-Vorgabe (defaultSpalten) ∨ Registry.
  const defaultVisibleKeys = useMemo(() => {
    const base = defaultSpalten && defaultSpalten.length
      ? defaultSpalten
      : verfuegbar.filter((m) => m.defaultVisible).map((m) => m.key)
    return base.filter((k) => verfuegbarKeys.has(k))
  }, [defaultSpalten, verfuegbar, verfuegbarKeys])

  // ── Sichtbarkeit + Reihenfolge (persistiert je Granularität) ─
  const [visible, setVisible] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(lsCols)
      if (raw) {
        const keys = (JSON.parse(raw) as string[]).filter((k) => verfuegbarKeys.has(k))
        if (keys.length > 0) return new Set(keys)
      }
    } catch { /* ignore */ }
    return new Set(defaultVisibleKeys)
  })
  const [order, setOrder] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(lsOrder)
      if (raw) {
        const keys = (JSON.parse(raw) as string[]).filter((k) => verfuegbarKeys.has(k))
        if (verfuegbar.every((m) => keys.includes(m.key))) return keys
      }
    } catch { /* ignore */ }
    return verfuegbar.map((m) => m.key)
  })
  const [pickerOffen, setPickerOffen] = useState(false)
  const [vergleichAn, setVergleichAn] = useState(vergleichDefaultAn)
  // Spalten-Sortierung (IST-Parität TabelleTab): null = chronologisch aufsteigend
  // (Default, wie die Cockpit-Embeds) · '__zeit' = Zeitraum-Spalte · sonst Metrik-key.
  // Dokumentierte F10-AUSNAHME (R3b E1, Gernot 2026-07-05): WerteTabelle-Zeitreihen
  // bleiben bewusst AUFSTEIGEND (Lese-Richtung der Analyse-Tabelle mit Δ-Vergleich);
  // die F10-Regel „Datums-Listen absteigend" gilt unverändert für alle anderen
  // Tabellen (z. B. KomponentenMonatsTabelle). Scope der Ausnahme: NUR dieser Default.
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  function toggleSort(key: string) {
    if (sortKey === key) { setSortDir((d) => (d === 'asc' ? 'desc' : 'asc')); return }
    setSortKey(key)
    setSortDir(key === '__zeit' ? 'asc' : 'desc') // Metrik: größter Wert zuerst
  }

  // Granularitätswechsel → Sichtbarkeit/Reihenfolge neu aus dem passenden Scope.
  useEffect(() => {
    setVisible(() => {
      try {
        const raw = localStorage.getItem(lsCols)
        if (raw) {
          const keys = (JSON.parse(raw) as string[]).filter((k) => verfuegbarKeys.has(k))
          if (keys.length > 0) return new Set(keys)
        }
      } catch { /* ignore */ }
      return new Set(defaultVisibleKeys)
    })
    setOrder(() => {
      try {
        const raw = localStorage.getItem(lsOrder)
        if (raw) {
          const keys = (JSON.parse(raw) as string[]).filter((k) => verfuegbarKeys.has(k))
          if (verfuegbar.every((m) => keys.includes(m.key))) return keys
        }
      } catch { /* ignore */ }
      return verfuegbar.map((m) => m.key)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [granularitaet])

  // Spät eintreffende Zusatz-Spalten (#350: die Erzeuger stehen erst, wenn
  // Investitionen UND Tageszeilen geladen sind) hinten anhängen. Ohne das
  // blieben sie dauerhaft aus `order` und damit aus dem Picker — die Spalten
  // wären gebaut, aber unerreichbar.
  useEffect(() => {
    setOrder((prev) => {
      const fehlend = verfuegbar.map((m) => m.key).filter((k) => !prev.includes(k))
      return fehlend.length ? [...prev, ...fehlend] : prev
    })
  }, [verfuegbar])

  useEffect(() => {
    try { localStorage.setItem(lsCols, JSON.stringify([...visible])) } catch { /* ignore */ }
  }, [visible, lsCols])
  useEffect(() => {
    try { localStorage.setItem(lsOrder, JSON.stringify(order)) } catch { /* ignore */ }
  }, [order, lsOrder])

  const aktiveMetriken = useMemo<WerteMetrik[]>(
    () => order.map((k) => metrikByKey[k]).filter((m) => m && visible.has(m.key)),
    [order, visible, metrikByKey],
  )

  const vergleichVerfuegbar = vorjahrRows != null && vorjahrRows.length > 0 && vergleichLabel != null
  const zeigeVergleich = vergleichVerfuegbar && vergleichAn
  // Sub-Label der „aktuellen" Vergleichs-Spalte (R20-1a): explizites Perioden-Label
  // (z. B. „2026"), sonst neutral „Aktuell". Die Vergleichs-Spalte trägt `vergleichLabel`.
  const aktuellLabel = jahrLabel !== '' && jahrLabel != null ? String(jahrLabel) : 'Aktuell'

  // Vergleichs-Auflösung: EINE Regel, geteilt mit dem CSV-Export (`lib/werte/vergleich`).
  const vorjahrLookup = useMemo(() => vergleichLookup(vorjahrRows), [vorjahrRows])

  const aggregat = useMemo(() => aggregiere(rows, aktiveMetriken), [rows, aktiveMetriken])
  // Fuß-Vergleich nur, wenn JEDE angezeigte Zeile ein Gegenstück hat — sonst „—"
  // statt einer Summe über eine andere Zeitspanne (s. `lib/werte/vergleich`).
  const vorjahrAggregat = useMemo(() => {
    const basis = vergleichsAggregatBasis(rows, vorjahrRows)
    return basis ? aggregiere(basis, aktiveMetriken) : null
  }, [rows, vorjahrRows, aktiveMetriken])
  // Warum der Fuß schweigt — SICHTBAR, nicht nur als „—". Genau in der Ansicht
  // „Alle Jahre" war die fehlende Vergleichszahl der ursprünglich gemeldete Fehler
  // (PN 90204); ohne Begründung liest sich die Korrektur wie der Bug. Zahl statt
  // Pauschale, damit erkennbar ist, dass nur der Anfang der Aufzeichnung fehlt.
  const ohneGegenstueck = useMemo(
    () => rows.length - gepaarteVergleichsZeilen(rows, vorjahrRows).length,
    [rows, vorjahrRows],
  )
  const fussSchweigt = zeigeVergleich && vorjahrAggregat == null && ohneGegenstueck > 0
  const einheitDativ = granularitaet === 'tag' ? 'Tagen' : 'Monaten'
  const fussGrund = `Die Summenzeile zeigt keinen Vergleich: ${ohneGegenstueck} von ${rows.length} ${einheitDativ} `
    + `${ohneGegenstueck === 1 ? 'hat' : 'haben'} kein Gegenstück im Vergleichszeitraum. `
    + 'Eine Summe stünde dort einer anderen Zeitspanne gegenüber. '
    + 'Die Δ-Werte der einzelnen Zeilen stehen vollständig darüber.'

  function verschiebe(key: string, dir: 'up' | 'down') {
    const gruppe = metrikByKey[key].gruppe
    const gruppenKeys = verfuegbar.filter((m) => m.gruppe === gruppe).map((m) => m.key)
    const inGruppe = order.filter((k) => gruppenKeys.includes(k))
    const idx = inGruppe.indexOf(key)
    const neu = dir === 'up' ? idx - 1 : idx + 1
    if (neu < 0 || neu >= inGruppe.length) return
    const getauscht = [...inGruppe]
    ;[getauscht[idx], getauscht[neu]] = [getauscht[neu], getauscht[idx]]
    setOrder((prev) => {
      const result = [...prev]
      let gi = 0
      for (let i = 0; i < result.length; i++) {
        if (gruppenKeys.includes(result[i])) result[i] = getauscht[gi++]
      }
      return result
    })
  }

  function csvExport() {
    exportWerteCsv({
      rows,
      vorjahrRows: zeigeVergleich ? vorjahrRows : null,
      jahrLabel,
      vergleichLabel: zeigeVergleich ? vergleichLabel : null,
      metriken: aktiveMetriken,
      einheitLabel,
      dateiname: csvDateiname,
    })
  }

  const sorted = useMemo(() => {
    const arr = [...rows]
    if (sortKey === null || sortKey === '__zeit') {
      arr.sort((a, b) => a.sortKey - b.sortKey)
      if (sortKey === '__zeit' && sortDir === 'desc') arr.reverse()
      return arr
    }
    arr.sort((a, b) => {
      const av = a.wert(sortKey); const bv = b.wert(sortKey)
      if (av == null && bv == null) return 0
      if (av == null) return 1   // fehlende Werte ans Ende
      if (bv == null) return -1
      return sortDir === 'asc' ? av - bv : bv - av
    })
    return arr
  }, [rows, sortKey, sortDir])

  if (sorted.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Werte im Zeitraum.</p>
  }

  return (
    <div className="space-y-3">
      {/* ── Steuerung (überall identisch) ──────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2">
        {/* B2 #292: Anzahl-Badge (gewählt/gesamt) am Picker-Button. */}
        <Button size="sm" variant="secondary" className="gap-1.5" onClick={() => setPickerOffen((o) => !o)}>
          <Columns className="h-4 w-4" /> Spalten ({visible.size}/{verfuegbar.length})
        </Button>
        {vergleichVerfuegbar && (
          <Button
            size="sm"
            variant={zeigeVergleich ? 'primary' : 'secondary'}
            className="gap-1.5"
            onClick={() => setVergleichAn((v) => !v)}
          >
            <GitCompareArrows className="h-4 w-4" /> Vergleich {vergleichLabel}
          </Button>
        )}
        {/* D13-10: Icon + Wort immer, Breakpoint lg (CsvExportButton-SoT). */}
        <CsvExportButton onClick={csvExport} />
        {alleWerteHref && (
          <a href={alleWerteHref} className="ml-auto inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
            Alle Werte / Export <ArrowRight className="h-4 w-4" />
          </a>
        )}
      </div>

      {pickerOffen && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {gruppen.map((g) => (
            <div key={g}>
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-1">{GRUPPE_LABELS[g]}</p>
              <ul className="space-y-0.5">
                {order.filter((k) => metrikByKey[k]?.gruppe === g).map((k) => {
                  const m = metrikByKey[k]
                  const an = visible.has(k)
                  return (
                    <li key={k} className="flex items-center gap-1 text-sm">
                      <div className="flex-1 min-w-0">
                        <Checkbox
                          checked={an}
                          onChange={() => setVisible((prev) => {
                            const n = new Set(prev)
                            n.has(k) ? n.delete(k) : n.add(k)
                            return n
                          })}
                          label={<span className="block truncate">{m.label}</span>}
                        />
                      </div>
                      <button type="button" aria-label="nach oben" onClick={() => verschiebe(k, 'up')}
                        className="p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                        <ChevronUp className="h-3.5 w-3.5" />
                      </button>
                      <button type="button" aria-label="nach unten" onClick={() => verschiebe(k, 'down')}
                        className="p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                        <ChevronDown className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </div>
        {/* B2 #292: „Standard wiederherstellen" — zurück auf den Spalten-Default
            (Werkbank-`defaultSpalten` ∨ Registry) UND die Registry-Reihenfolge. */}
        <div className="border-t border-gray-100 dark:border-gray-700/50 pt-2">
          <Button
            size="sm" variant="ghost"
            onClick={() => { setVisible(new Set(defaultVisibleKeys)); setOrder(verfuegbar.map((m) => m.key)) }}
          >
            Standard wiederherstellen
          </Button>
        </div>
        </div>
      )}

      {/* ── Tabelle — Zentrale `ui/Table` (Regel T, D18-2 + G18-1) ──────────── */}
      <Table zeilen={12} mitFuss={sorted.length > 1} flaeche="karte" className="w-full">
          <TableHead>
            <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
              {/* R20-1b (Rainer): vertikale Trennlinie nach der Zeitraum-Spalte
                  (Stil = Gruppen-Trennlinien R19-4b). Im Vergleich-Modus überspannt
                  der Zeitraum-Kopf beide Kopfzeilen (Sub-Labels sitzen unter den Metriken). */}
              <th rowSpan={zeigeVergleich ? 2 : 1} className={`${KOPF_ZELLE} border-r border-gray-200 dark:border-gray-700`}>
                <TableSortKopf aktiv={sortKey === '__zeit'} richtung={sortDir} onClick={() => toggleSort('__zeit')}>
                  Zeitraum
                </TableSortKopf>
              </th>
              {aktiveMetriken.map((m) => (
                // R19-4a (Rainer): im Vergleich-Modus sitzt der Gruppen-Kopf ZENTRIERT
                // über seinen 3 Spalten (Wert · Vergleich · Δ) + feine Gruppen-Trennlinie.
                <th
                  key={m.key}
                  colSpan={zeigeVergleich ? 3 : 1}
                  className={`${KOPF_ZELLE} ${zeigeVergleich ? 'text-center border-r border-gray-200 dark:border-gray-700' : 'text-right'}`}
                >
                  <TableSortKopf aktiv={sortKey === m.key} richtung={sortDir} onClick={() => toggleSort(m.key)}>
                    {m.label}{m.unit ? ` (${m.unit})` : ''}
                  </TableSortKopf>
                </th>
              ))}
            </tr>
            {/* R20-1a (Rainer „2 Spalten ?"): Sub-Label-Zeile beschriftet die drei
                Vergleichs-Spalten je Metrik (aktuell · Vergleichsperiode · Δ), damit
                erkennbar ist, welcher Wert welcher ist. Nicht klickbar (Sortierung
                bleibt am Gruppen-Kopf oben). */}
            {zeigeVergleich && (
              <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                {aktiveMetriken.map((m) => (
                  <Fragment key={m.key}>
                    <th className={`${KOPF_ZELLE} font-normal text-right`}>{aktuellLabel}</th>
                    <th className={`${KOPF_ZELLE} font-normal text-right`}>{vergleichLabel}</th>
                    <th className={`${KOPF_ZELLE} font-normal text-right border-r border-gray-200 dark:border-gray-700`}>Δ</th>
                  </Fragment>
                ))}
              </tr>
            )}
          </TableHead>
          <TableBody>
            {sorted.map((r) => {
              const prev = zeigeVergleich ? vorjahrLookup.get(r.vergleichKey) : undefined
              return (
                <tr key={r.id} className="border-b border-gray-100 dark:border-gray-800">
                  {/* R20-1b: Wochentag/Monat linksbündig, Datum/Jahr rechtsbündig,
                      danach die Zeitraum-Trennlinie (Kopf trägt sie ebenso). */}
                  <td className={`${ZELLE} text-gray-600 dark:text-gray-400 border-r border-gray-100 dark:border-gray-800`}>
                    <span className="flex items-baseline justify-between gap-3">
                      <span>{r.zeitLinks}</span>
                      <span className="tabular-nums">{r.zeitRechts}</span>
                    </span>
                  </td>
                  {aktiveMetriken.map((m) => {
                    const v = r.wert(m.key)
                    // S3: Wo der Layer eine Kennzahl verweigert, traegt die Zelle
                    // den Grund als Tooltip statt eines nackten „—".
                    const grund = v == null ? r.grund?.(m.key) ?? undefined : undefined
                    if (zeigeVergleich) {
                      const pv = prev ? prev.wert(m.key) : null
                      return (
                        <Fragment key={m.key}>
                          <td className={`${ZELLE} text-right tabular-nums text-gray-700 dark:text-gray-300`} title={grund}>{fmtWert(v, m.decimals)}</td>
                          <td className={`${ZELLE} text-right tabular-nums text-gray-500 dark:text-gray-400`}>{fmtWert(pv, m.decimals)}</td>
                          {/* R19-4b: Gruppen-Trennlinie im Zeilen-Ton (gray-100/800 war im Dark-Mode unsichtbar). */}
                          <td className={`${ZELLE} text-right tabular-nums text-xs border-r border-gray-200 dark:border-gray-700`}><DeltaZelle current={v} prev={pv} metrik={m} /></td>
                        </Fragment>
                      )
                    }
                    return <td key={m.key} className={`${ZELLE} text-right tabular-nums text-gray-700 dark:text-gray-300`} title={grund}>{fmtWert(v, m.decimals)}</td>
                  })}
                </tr>
              )
            })}
          </TableBody>
          {sorted.length > 1 && (
            <TableFoot>
              {/* Betonung + deckender Grund kommen aus der Zentrale (FUSS_GRUND). */}
              <tr>
                <td className={`${ZELLE} text-gray-600 dark:text-gray-300 text-xs uppercase tracking-wide border-r border-gray-300 dark:border-gray-600`}>
                  {sorted.length} {einheitLabel}
                </td>
                {aktiveMetriken.map((m) => {
                  const v = aggregat[m.key]
                  const prefix = m.aggregation === 'avg' ? 'Ø ' : ''
                  if (zeigeVergleich) {
                    const pv = vorjahrAggregat?.[m.key] ?? null
                    return (
                      <Fragment key={m.key}>
                        <td className={`${ZELLE} text-right tabular-nums text-gray-800 dark:text-gray-100`}>{v != null ? `${prefix}${fmtWert(v, m.decimals)}` : '—'}</td>
                        {/* Der leere Fuß trägt seinen Grund am Hover; der sichtbare
                            Satz steht zusätzlich unter der Tabelle (nicht jeder hovert). */}
                        <td className={`${ZELLE} text-right tabular-nums text-gray-500 dark:text-gray-400`} title={fussSchweigt ? fussGrund : undefined}>{pv != null ? `${prefix}${fmtWert(pv, m.decimals)}` : '—'}</td>
                        <td className={`${ZELLE} text-right tabular-nums text-xs border-r border-gray-300 dark:border-gray-600`} title={fussSchweigt ? fussGrund : undefined}><DeltaZelle current={v} prev={pv} metrik={m} /></td>
                      </Fragment>
                    )
                  }
                  return <td key={m.key} className={`${ZELLE} text-right tabular-nums text-gray-800 dark:text-gray-100`}>{v != null ? `${prefix}${fmtWert(v, m.decimals)}` : '—'}</td>
                })}
              </tr>
            </TableFoot>
          )}
      </Table>

      {sorted.length > 1 && fussSchweigt && (
        <p className="text-xs text-gray-500 dark:text-gray-400">{fussGrund}</p>
      )}
    </div>
  )
}
