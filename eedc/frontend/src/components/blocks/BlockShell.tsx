/**
 * BlockShell — rendert eine Liste universeller {@link Block}s mit Einklappen,
 * Fokus/Vollbild und (optional) ↑↓-Reihenfolge; merkt Klapp-/Reihenfolge-
 * Zustand pro Sicht in localStorage.
 *
 * Promoviert aus `components/preview/IASkeleton.tsx` (dort `BloeckeView`).
 * Hier die echte, getestete Variante für den IA-v4-Routenbaum.
 *
 * Wächter-Ausnahme: die rohen <button> (Klapp-/Fokus-/Park-Mechanik) SIND die
 * Infra-Implementierung — check:v4-migration-Infra-Allowlist (Regel 0a Fall 3,
 * Gernot-Freigabe 2026-07-11).
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowUp, ArrowDown, ChevronDown, ChevronsDown, ChevronsUp, Maximize2, RotateCcw,
} from 'lucide-react'
import type { Block } from './types'
import { FokusVollbild } from './FokusVollbild'

// ─── Persistenz Klappzustand + Reihenfolge (detLAN #243 A4) ───────────────────
const LS_PREFIX = 'eedc-bloecke:'
interface BlockState { order?: string[]; zu?: string[] }

export function ladeBlockState(key: string): BlockState {
  try {
    const raw = localStorage.getItem(LS_PREFIX + key)
    return raw ? (JSON.parse(raw) as BlockState) : {}
  } catch {
    return {}
  }
}
export function speichereBlockState(key: string, state: { order: string[]; zu: string[] }) {
  try {
    localStorage.setItem(LS_PREFIX + key, JSON.stringify(state))
  } catch {
    /* localStorage nicht verfügbar (Privatmodus o. Ä.) — Persistenz still überspringen */
  }
}

export function BlockShell({
  bloecke,
  sortierbar = false,
  persistKey,
  fokusKopf,
  oeffneBeimMount,
}: {
  bloecke: Block[]
  sortierbar?: boolean
  persistKey: string
  /** D10-2: Kopf-Slot, der im Fokus/Vollbild oben mitläuft (z. B. die Datums-Nav
   *  der Seite). Reicht ihn an {@link FokusVollbild} durch — kein Nav-Neubau. */
  fokusKopf?: import('react').ReactNode
  /** Deep-Link-Öffner (B5): klappt diesen Block beim Landen auf, auch wenn der
   *  gemerkte Zustand „zu" war (überstimmt Persistenz) — z. B. Fusszeile →
   *  Monatsabschluss öffnet den Monatsdaten-Block, damit dessen Form sichtbar
   *  wird. Ändert sich der Wert, wird erneut aufgeklappt. */
  oeffneBeimMount?: string
}) {
  const ids = useMemo(() => bloecke.map((b) => b.id), [bloecke])
  const [order, setOrder] = useState<string[]>(() => {
    const gespeichert = ladeBlockState(persistKey).order
    if (!gespeichert) return ids
    // Lücken-fest (detLAN-Vollbild-Bug 2026-06-30): die gespeicherte Reihenfolge
    // VOLLSTÄNDIG behalten — auch IDs, die gerade nicht in der Liste sind (z. B.
    // Blöcke eines Lücken-Tags, die zurückkommen) —, nur neue IDs hinten anhängen.
    // Niemals IDs wegwerfen → ein vorübergehend reduziertes `bloecke` kann die
    // Reihenfolge nicht zerstören.
    return [...gespeichert, ...ids.filter((id) => !gespeichert.includes(id))]
  })
  const [zu, setZu] = useState<Set<string>>(() => {
    // D14-2: Klapp-Zustand wird überall gemerkt (die A3-Flüchtigkeit der
    // Einstellungen ist zurückgenommen — detLAN #113, Gernot-Entscheid).
    const gespeichert = ladeBlockState(persistKey).zu
    return gespeichert
      ? new Set(gespeichert)  // Lücken-fest: Klappzustand auch absenter Blöcke behalten
      : new Set(bloecke.filter((b) => b.defaultOpen === false).map((b) => b.id))
  })
  // B5-Deep-Link: gewünschten Block beim Landen/Änderung aufklappen (überstimmt
  // den gemerkten „zu"-Zustand), damit ein extern angesteuerter Block (mit seiner
  // Form/Inhalt) tatsächlich mountet.
  useEffect(() => {
    if (!oeffneBeimMount) return
    setZu((prev) => {
      if (!prev.has(oeffneBeimMount)) return prev
      const next = new Set(prev)
      next.delete(oeffneBeimMount)
      return next
    })
  }, [oeffneBeimMount])

  const [fokus, setFokus] = useState<string | null>(null)
  // Letzte Meta des fokussierten Blocks — damit das Vollbild Titel/Icon behält,
  // falls der Block kurzzeitig aus der Liste fällt (Lücken-Tag).
  const lastFokusMeta = useRef<Pick<Block, 'title' | 'icon' | 'farbe'> | null>(null)
  const byId = useMemo(() => Object.fromEntries(bloecke.map((b) => [b.id, b] as const)), [bloecke])

  // Sichtbare Blöcke in gemerkter Reihenfolge — absente Lücken-Tag-/Komponenten-IDs
  // (z. B. E-Mobilität nur an manchen Tagen) rausgefiltert. Basis fürs Rendering UND
  // fürs ID-basierte Verschieben (R13-1).
  const ordered = useMemo(
    () => order.map((id) => byId[id]).filter(Boolean) as Block[],
    [order, byId],
  )

  // Lücken-fest: neu auftauchende Block-IDs hinten anhängen, vorhandene Position
  // behalten, NIE entfernen — verschwundene Blöcke eines Lücken-Tags bleiben in der
  // Reihenfolge und kommen an ihrer Stelle zurück (kein „nur noch ein Block").
  useEffect(() => {
    setOrder((prev) => {
      const neu = ids.filter((id) => !prev.includes(id))
      return neu.length ? [...prev, ...neu] : prev
    })
  }, [ids])

  // Default-Klappzustand (defaultOpen === false → eingeklappt) für den Reset.
  const defaultZu = useMemo(
    () => bloecke.filter((b) => b.defaultOpen === false).map((b) => b.id),
    [bloecke],
  )
  const istDefault = useMemo(() => {
    // Nur die aktuell SICHTBAREN Blöcke vergleichen (absente Lücken-Tag-IDs in
    // order/zu zählen nicht als „verändert").
    const sichtbar = order.filter((id) => ids.includes(id))
    const sameOrder = sichtbar.length === ids.length && sichtbar.every((id, i) => id === ids[i])
    const sichtbarZu = [...zu].filter((id) => ids.includes(id))
    const sameZu = sichtbarZu.length === defaultZu.length && defaultZu.every((id) => zu.has(id))
    return sameOrder && sameZu
  }, [order, ids, zu, defaultZu])
  const zuruecksetzen = () => {
    // Aktuelle Blöcke in Natur-Reihenfolge nach vorn; absente (Lücken-Tag-)IDs
    // behalten ihre Position dahinter — niemals wegwerfen (sonst Reihenfolge weg).
    setOrder([...ids, ...order.filter((id) => !ids.includes(id))])
    setZu(new Set(defaultZu))
    setFokus(null)
  }

  // R14-5 (Rainer #114, Gernot-Entscheid): „alle aufklappen / alle zuklappen" als
  // Kompromiss neben „zurücksetzen" — hilft, die mühsam erstellte Sortierung zu
  // erhalten (Reset=Standard bleibt unverändert). Lücken-fest: der Klappzustand
  // absenter Block-IDs bleibt erhalten, es werden nur die sichtbaren geändert.
  const alleAufklappen = () => setZu(new Set([...zu].filter((id) => !ids.includes(id))))
  const alleZuklappen = () => setZu(new Set([...zu, ...ids]))

  // Klappzustand (+ Reihenfolge) pro Sicht merken.
  useEffect(() => {
    speichereBlockState(persistKey, { order, zu: [...zu] })
  }, [persistKey, order, zu])

  // R13-1 (Rainer #101): `i` ist der Index der SICHTBAREN Liste (`ordered`); die
  // persistierte `order` kann absente IDs enthalten (order.length > ordered.length).
  // Deshalb NICHT order[i]↔order[i±1] tauschen (trifft falsche/unsichtbare Blöcke),
  // sondern die beiden sichtbaren Nachbarn PER ID in `order` vertauschen — absente
  // IDs bleiben an ihrer Stelle.
  const verschieben = (i: number, r: -1 | 1) => {
    const ziel = i + r
    if (ziel < 0 || ziel >= ordered.length) return
    const a = order.indexOf(ordered[i].id)
    const b = order.indexOf(ordered[ziel].id)
    if (a < 0 || b < 0) return
    const next = [...order]
    ;[next[a], next[b]] = [next[b], next[a]]
    setOrder(next)
  }
  const toggle = (id: string) => {
    const next = new Set(zu)
    next.has(id) ? next.delete(id) : next.add(id)
    setZu(next)
  }

  // ── Fokus/Vollbild: nur dieser Block, bildschirmfüllend (geteiltes Overlay) ──
  // Lücken-fest (detLAN 2026-06-30): Das Vollbild bleibt OFFEN, auch wenn der
  // fokussierte Block kurzzeitig aus `bloecke` fällt (Navigation auf einen Tag
  // ohne Daten). Statt zurückzuspringen zeigt es einen „keine Daten"-Hinweis +
  // die durchlaufende Datums-Nav (fokusKopf) — der Nutzer kann im Vollbild
  // weiterblättern, und sobald der Block zurückkommt, rendert er wieder.
  if (fokus) {
    const b = byId[fokus]
    if (b) lastFokusMeta.current = { title: b.title, icon: b.icon, farbe: b.farbe }
    const meta = b ?? lastFokusMeta.current
    if (meta) {
      return (
        <FokusVollbild titel={meta.title} icon={meta.icon} farbe={meta.farbe} kopf={fokusKopf} onClose={() => setFokus(null)}>
          {b
            ? b.render(true)
            : (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Für diesen Zeitraum liegen keine Daten vor. Wähle über die Navigation oben einen Zeitraum mit Messwerten – oder schließe die Vollansicht.
              </p>
            )}
        </FokusVollbild>
      )
    }
  }

  // D7-4 (detLAN R7): KEIN Eigen-Padding/-max-width mehr — die konsumierende Sicht
  // ist der EINE Padding-Owner (`p-3 sm:p-6 max-w-[1920px] mx-auto`). Vorher paddete
  // BlockShell zusätzlich → Doppel-Padding (Blöcke schmaler als Kopf/Parkplatz,
  // Mobil-Platzverlust). Jetzt richten sich Kopf, Blöcke und Parkplatz an EINER Kante aus.
  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-400 dark:text-gray-500 flex flex-wrap items-center gap-x-1">
        <span>
          Jeder Block: <ChevronDown className="inline h-3 w-3" /> einklappen
          {/* D14-16: ⤢ ist < 640 px ausgeblendet → Hinweis-Fragment ebenso. */}
          <span className="max-sm:hidden">
            {' '}· <Maximize2 className="inline h-3 w-3" /> Fokus/Vollbild
          </span>
          {sortierbar && (
            <>
              {' '}· <ArrowUp className="inline h-3 w-3" />
              <ArrowDown className="inline h-3 w-3" /> verschieben
            </>
          )}{' '}
          · Zustand bleibt gemerkt
        </span>
        {/* R14-5: einmal pro Seite — erhält die Sortierung (im Gegensatz zum Reset). */}
        <button
          type="button"
          onClick={alleAufklappen}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
        >
          <ChevronsDown className="h-3 w-3" /> alle aufklappen
        </button>
        <button
          type="button"
          onClick={alleZuklappen}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
        >
          <ChevronsUp className="h-3 w-3" /> alle zuklappen
        </button>
        {!istDefault && (
          <button
            type="button"
            onClick={zuruecksetzen}
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
          >
            <RotateCcw className="h-3 w-3" /> zurücksetzen
          </button>
        )}
      </p>
      {ordered.map((b, i) => {
        const istZu = zu.has(b.id)
        return (
          <section
            key={b.id}
            className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden"
          >
            <div className="flex items-center gap-2 px-3 min-h-[44px]">
              <button
                type="button"
                onClick={() => toggle(b.id)}
                className="flex-1 flex items-center gap-2 text-left py-2 min-w-0"
              >
                {b.icon && <b.icon className={`h-4 w-4 flex-shrink-0 ${b.farbe ?? 'text-gray-400 dark:text-gray-500'}`} />}
                {/* D13-6: Kopfzeile bleibt EINZEILIG — Titel truncatet als letzte
                    Reserve, damit er (mit Badge + langem Untertitel) mobil NIE über
                    die ↑↓⤢⌄-Controls läuft. Der Untertitel schrumpft zuerst
                    (starkes flex-shrink), der Titel behält Vorrang. */}
                <span className="text-sm font-semibold text-gray-900 dark:text-white truncate min-w-0">{b.title}</span>
                {b.summary && <span className="text-xs text-gray-400 dark:text-gray-500 truncate min-w-0 [flex-shrink:100]">{b.summary}</span>}
              </button>
              {b.badge && <div className="flex-shrink-0">{b.badge}</div>}
              <div className="flex items-center gap-0.5 flex-shrink-0">
                {sortierbar && (
                  <>
                    <button
                      type="button"
                      onClick={() => verschieben(i, -1)}
                      disabled={i === 0}
                      aria-label="nach oben"
                      className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-30 disabled:cursor-default"
                    >
                      <ArrowUp className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => verschieben(i, 1)}
                      disabled={i === ordered.length - 1}
                      aria-label="nach unten"
                      className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-30 disabled:cursor-default"
                    >
                      <ArrowDown className="h-4 w-4" />
                    </button>
                  </>
                )}
                {/* D14-16: „Vergrößern" unter 640 px ausblenden (nicht entfernen). */}
                <button
                  type="button"
                  onClick={() => setFokus(b.id)}
                  aria-label="Fokus / Vollbild"
                  className="max-sm:hidden p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                >
                  <Maximize2 className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => toggle(b.id)}
                  aria-label={istZu ? 'aufklappen' : 'einklappen'}
                  className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                >
                  <ChevronDown className={`h-4 w-4 transition-transform ${istZu ? '-rotate-90' : ''}`} />
                </button>
              </div>
            </div>
            {!istZu && <div className="px-3 pb-3">{b.render(false)}</div>}
          </section>
        )
      })}
    </div>
  )
}
