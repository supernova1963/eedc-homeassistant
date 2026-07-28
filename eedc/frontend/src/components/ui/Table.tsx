/**
 * Table — Tabellen-SoT (Regel T, `docs/drafts/archive/KONZEPT-TABELLEN-SOT.md`, abgenommen 2026-07-10).
 *
 * Vorgeschichte: die SoT existierte, hatte aber NULL Nutzer — 52 Dateien bauten
 * ihr eigenes `<table>`. Ergebnis waren drei Mechaniken nebeneinander und die
 * Tester-Funde D18-2 (Leiste unsichtbar, Rad kapert) + G18-1 (Kopf klebt nicht).
 *
 * **Die CSS-Wahrheit, aus der alles folgt:** sobald ein Container horizontal
 * scrollen darf (`overflow-x != visible`), macht CSS ihn AUCH vertikal zum
 * Scroll-Container; `position: sticky` haftet dann am Container, nie am Viewport.
 * ⇒ **Ein klebender Tabellenkopf ist nur mit eigener Container-Höhe möglich.**
 * Cleane Optik + vollständige Sicht + klebender Kopf sind zusammen unmöglich.
 *
 * Regeln (T2–T6):
 *  - Höhenfenster `min(zeilen × ZEILE + KOPF [+ FUSS], 70dvh)`. `zeilen` ist die
 *    FACHLICHE Fenstergröße (12 Default; 24 für Stundentabellen), nicht die
 *    Datenmenge. Kürzere Tabellen scrollen von selbst nicht → keine Ausnahme nötig.
 *  - `thead` sticky oben, `tfoot` sticky unten (beides wirkt erst durch das Fenster).
 *  - Beide Scroll-Leisten sichtbar (G16-3-Pillenstil), Fade zusätzlich als Affordanz.
 *  - Rad: durch den vertikalen Überlauf steigt die Rad-Umleitung A9 in
 *    `ScrollSchatten` von selbst aus (dort Zeile „scrollHeight > clientHeight").
 *  - Eine Zell-Typo: `text-sm` + `py-1.5`.
 */
import { ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import ScrollSchatten from './ScrollSchatten'
import { DECKEL, FLAECHE, FUSS_GRUND, KOPF_ZELLE, ZELLE, fensterHoehe, type Flaeche } from './tabelleMasse'

/**
 * Fensterhöhe aus dem GERENDERTEN DOM messen statt aus Konstanten rechnen.
 *
 * Warum: Kopf- und Fußzeilen sind nicht überall gleich hoch — die Stundentabelle
 * hat einen zweizeiligen Kopf („Verfügbare Energie" über „kW", ~44 px statt 25).
 * Mit geschätzten Konstanten war das Fenster 750 px, der Inhalt aber 767 px ⇒ die
 * 24. Zeile wurde abgeschnitten (Gernot, 2026-07-10). Die Konstanten aus
 * `tabelleMasse` bleiben der Startwert für den ersten Frame und den Test.
 */
function useGemessenesFenster(zeilen: number, mitFuss: boolean) {
  const ref = useRef<HTMLTableElement>(null)
  const [hoehe, setHoehe] = useState<string>(fensterHoehe(zeilen, mitFuss))

  const messen = useCallback(() => {
    const t = ref.current
    if (!t) return
    const kopf = t.querySelector('thead')?.getBoundingClientRect().height ?? 0
    const fuss = t.querySelector('tfoot')?.getBoundingClientRect().height ?? 0
    const bodyZeilen = t.querySelectorAll('tbody tr')
    const ersteZeile = bodyZeilen[0]?.getBoundingClientRect().height ?? 0
    if (!ersteZeile) return
    // Passt die ganze Tabelle in ihr Fenster (Zeilenzahl ≤ `zeilen`), zeige sie
    // VOLLSTÄNDIG anhand der real gemessenen Tabellenhöhe. Die Rechnung
    // `kopf + zeilen × ersteZeile + fuss` unterschätzt sonst, sobald Zeilen ungleich
    // hoch sind (Icon-/Mehrzeilen-Zellen, z. B. Monats-Details „Unter Plan" mit Icon)
    // → 1–2 px Rest-Overflow = Mini-Scroll trotz „passt eigentlich" (Gernot 2026-07-11).
    const px = bodyZeilen.length <= zeilen
      ? Math.ceil(t.getBoundingClientRect().height)
      : Math.ceil(kopf + zeilen * ersteZeile + fuss)
    setHoehe(`min(${px}px, ${DECKEL})`)
  }, [zeilen])

  useEffect(() => {
    const t = ref.current
    if (!t) return
    messen()
    const ro = new ResizeObserver(messen)
    ro.observe(t)
    return () => ro.disconnect()
  }, [messen, mitFuss])

  return { ref, hoehe }
}

interface TableProps {
  children: ReactNode
  className?: string
  /** Fachliche Fenstergröße in Zeilen (T2). 24 für Stundentabellen. */
  zeilen?: number
  /** Setzt die Tabelle ein `<TableFoot>` ein? Reserviert dessen Höhe im Fenster. */
  mitFuss?: boolean
  /** Grundfläche, auf der die Tabelle sitzt. */
  flaeche?: Flaeche
  /** `tkonto`: buchhalterisches SOLL/HABEN-Layout (feste Spaltenbreiten, Summen
   *  über Border-Zeilen statt `<tfoot>`) — Variante der Zentrale, kein Sonderfall. */
  variante?: 'standard' | 'tkonto'
  /** Klassen für den äußeren Wrapper — Display-Gating (`hidden sm:block`, wenn
   *  mobil eine Kachel-Variante gezeigt wird) und Außenabstände. */
  aussenClassName?: string
}

export function Table({
  children,
  className = '',
  zeilen = 12,
  mitFuss = false,
  flaeche = 'karte',
  variante = 'standard',
  aussenClassName = '',
}: TableProps) {
  const f = FLAECHE[flaeche]
  const { ref, hoehe } = useGemessenesFenster(zeilen, mitFuss)
  return (
    <ScrollSchatten
      achse="beide"
      fadeFrom={f.fade}
      leisten="sichtbar"
      aussenClassName={aussenClassName}
      containerStyle={{ maxHeight: hoehe }}
    >
      <table
        ref={ref}
        className={`min-w-full ${variante === 'tkonto' ? 'table-fixed' : ''} ${className}`}
        data-tabelle-sot={variante}
      >
        {children}
      </table>
    </ScrollSchatten>
  )
}

export function TableHead({ children, flaeche = 'karte' }: { children: ReactNode; flaeche?: Flaeche }) {
  // T3: klebt am Container — wirkt nur, weil <Table> ein Höhenfenster setzt.
  // Der Grund MUSS auf den Zellen liegen: ein `background` auf <thead>/<tr> wird
  // im Tabellen-Rendermodell beim Sticky nicht gemalt, die Datenzeilen scheinen
  // durch (2026-07-10 auf der Dev-Box gesehen — jsdom fängt das nicht).
  return <thead className={`sticky top-0 z-10 ${FLAECHE[flaeche].zellGrund}`}>{children}</thead>
}

/** Die Summenzeile hat einen eigenen Grund (FUSS_GRUND) — daher kein `flaeche`-Prop. */
export function TableFoot({ children }: { children: ReactNode }) {
  // T3: Summenzeile bleibt sichtbar. Der frühere „schwebt am Viewport-Boden"-Effekt
  // (tag/TagWerteTabelle) galt nur ohne scrollenden Container.
  // Grund ebenfalls auf den Zellen — s. TableHead. Die Betonung der Summenzeile
  // gehört in die Zentrale (T6: eine Summenzeile sieht überall gleich aus); ein
  // `bg-*` auf der <tr> des Aufrufers würde von der td-Regel ohnehin übersteuert.
  return (
    <tfoot className={`sticky bottom-0 z-10 ${FUSS_GRUND}`}>{children}</tfoot>
  )
}

export function TableBody({ children }: { children: ReactNode }) {
  // Hover-Highlight (Regel T, Gernot 2026-07-11): reine Lese-Orientierung — die
  // Zeile unter dem Cursor hebt sich dezent ab. Nur Body-Zeilen (Kopf/Fuß haben
  // deckende Zell-Gründe); Body-Zellen sind grundlos → die tr-Tönung schlägt durch.
  // Rein CSS, appweit über die SoT, keine Logik. Touch: greift ins Leere (kein
  // Hover) — datendichte Tabellen zeigen dort ohnehin die Kachel-Variante.
  // Farbe MUSS sich vom Karten-Grund abheben: hell white→gray-100, dunkel
  // gray-800→gray-700 (HELLER als die Karte). gray-50/gray-800 war unsichtbar —
  // dunkel identisch mit dem Karten-Grund gray-800 (Gernot 2026-07-11).
  return (
    <tbody className="divide-y divide-gray-100 dark:divide-gray-800 [&_tr:hover]:bg-gray-100 dark:[&_tr:hover]:bg-gray-700">
      {children}
    </tbody>
  )
}

export function TableRow({ children, onClick, className = '' }: { children: ReactNode; onClick?: () => void; className?: string }) {
  return (
    <tr
      className={`${onClick ? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800' : ''} ${className}`}
      onClick={onClick}
    >
      {children}
    </tr>
  )
}

export function TableHeader({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <th scope="col" className={`${KOPF_ZELLE} text-left text-gray-500 dark:text-gray-400 ${className}`}>
      {children}
    </th>
  )
}

/**
 * TableSortKopf — klickbarer Sortier-Spaltenkopf der Zentrale (Regel T).
 * Der rohe `<button>` ist hier die SoT-Implementierung (wie SegmentControl/Switch);
 * Pfeil-Icons folgen der Kontroll-Icon-Konvention E6 (erben die Kopf-Textfarbe).
 * In einen `<th>` des Aufrufers setzen — Ausrichtung/Padding bleiben Sache der Zelle.
 */
export function TableSortKopf({
  children, aktiv, richtung, onClick,
}: {
  children: ReactNode
  /** Ist DIESE Spalte die aktuelle Sortier-Spalte? (Pfeil nur dann) */
  aktiv: boolean
  richtung: 'asc' | 'desc'
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 hover:text-gray-700 dark:hover:text-gray-200"
    >
      {children} {aktiv && (richtung === 'asc' ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />)}
    </button>
  )
}

export function TableCell({
  children,
  className = '',
  style,
}: {
  children: ReactNode
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <td className={`${ZELLE} text-gray-900 dark:text-gray-100 ${className}`} style={style}>
      {children}
    </td>
  )
}
