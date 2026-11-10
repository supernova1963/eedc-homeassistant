/**
 * Sprung aufs Feld (Etappe E4 «Daten-Checker: ein Handgriff je Befund», Konzept §3.3, Bauplan §4 W-5).
 *
 * «Beheben» eines Befunds navigiert mit `feld=<schlüssel>` (Ziel-Bauer `backend/services/daten_checker/ziele.py`). Die
 * Zielseite liest den Parameter an **einer** Stelle, öffnet ihr Formular bzw. ihren Block und ruft
 * {@link useAufFeldSpringen}: der Hook wartet, bis das Feld im DOM steht, scrollt hin und fokussiert es — die
 * Hervorhebung ist die **bestehende Fokus-Optik** des Eingabefelds (S4: keine neue Farbe).
 *
 * **Zugeklappte Abschnitte** (`FormSection variant="erweitert"`, `CollapsibleSection`) rendern ihren Inhalt nur offen.
 * Solange ein Sprung läuft, stellt die Zielseite {@link SprungFeldKontext} bereit; beide Bausteine starten dann offen
 * (Entscheid Master zu H-E4-B: beim Sprung sind alle zugeklappten Abschnitte dieses Formulars offen). Der Kontext endet,
 * sobald das Feld gefunden ist (oder die Wartezeit abläuft) — kein Dauerzustand.
 */
import { createContext, useContext, useEffect, useRef } from 'react'

/** Aktiver Sprung im Teilbaum (Feld-Schlüssel oder Selektor) — `null` ohne Sprung. */
export const SprungFeldKontext = createContext<string | null>(null)

/** true ⇒ ein zugeklappter Abschnitt startet offen, weil im Teilbaum ein Sprung aufs Feld läuft. */
export function useSprungOffen(): boolean {
  return useContext(SprungFeldKontext) !== null
}

const WARTEN_MS = 5000
const SCHRITT_MS = 100
const TRENNER_INNENGERAET = '-'

/**
 * Der Feld-Key ohne Innengeräte-Suffix — Spiegel von `core/field_definitions/keys.py::basis_feld_key`
 * (`betriebsart_strom_kuehlen_kwh-3` → `betriebsart_strom_kuehlen_kwh`; ohne Suffix unverändert).
 */
export function basisFeldKey(feld: string): string {
  const i = feld.lastIndexOf(TRENNER_INNENGERAET)
  return i > 0 && /^\d+$/.test(feld.slice(i + 1)) ? feld.slice(0, i) : feld
}

function css(wert: string): string {
  return typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(wert) : wert.replace(/["\\]/g, '\\$&')
}

/**
 * Selektor eines Formularfelds: `name="<feld>"`, `name="param_<feld>"` (Typ-Parameter der Komponenten) oder
 * `data-feld="<feld>"` (Feldzeile der Datenquellen, Assistenz-Feld des Monatsabschlusses, Datumsfelder).
 */
export function feldSelektor(feld: string): string {
  const f = css(feld)
  return `[name="${f}"], [name="param_${f}"], [data-feld="${f}"]`
}

const FOKUSSIERBAR = 'input:not([type="hidden"]), select, textarea, button'

/** Scrollt zum Element und fokussiert es bzw. sein erstes Eingabeelement (bestehende Fokus-Optik). */
export function zeigeFeld(el: Element): void {
  el.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  const ziel = el.matches(FOKUSSIERBAR) ? el : el.querySelector(FOKUSSIERBAR)
  if (ziel instanceof HTMLElement) ziel.focus({ preventScroll: true })
}

/**
 * Wartet (höchstens 5 s), bis `selektor` im DOM steht, springt hin ({@link zeigeFeld}) und meldet `onFertig` — auch
 * wenn das Feld nicht erscheint (dann ohne Sprung). `selektor = null` ⇒ nichts.
 */
export function useAufFeldSpringen(selektor: string | null, onFertig?: () => void): void {
  const fertig = useRef(onFertig)
  fertig.current = onFertig
  useEffect(() => {
    if (!selektor) return
    const bis = Date.now() + WARTEN_MS
    let timer: ReturnType<typeof setTimeout> | undefined
    const suche = () => {
      const el = document.querySelector(selektor)
      if (el) {
        zeigeFeld(el)
        fertig.current?.()
        return
      }
      if (Date.now() < bis) timer = setTimeout(suche, SCHRITT_MS)
      else fertig.current?.()
    }
    suche()
    return () => { if (timer !== undefined) clearTimeout(timer) }
  }, [selektor])
}
