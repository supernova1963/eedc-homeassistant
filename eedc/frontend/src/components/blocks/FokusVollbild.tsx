/**
 * FokusVollbild — das EINE Fokus/Vollbild-Overlay (IA-V4, Regel 0a).
 *
 * Geteilte SoT für „bildschirmfüllend" (KONZEPT-IA-V4 Z.76): genutzt von der
 * {@link BlockShell} (⤢ je Block) UND der {@link FokusKachel} (⤢ je Karte ohne
 * Block-Stack). Ein Verhalten + ein Look app-weit — keine zweite Kopie.
 */
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Minimize2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { SegmentControl } from '../ui'

export function FokusVollbild({ titel, icon: Icon, farbe, onClose, kopf, tabelle, children }: {
  titel: string
  icon?: LucideIcon
  farbe?: string
  onClose: () => void
  /** D10-2: optionaler Kopf-Slot unter der Titelzeile (z. B. Datums-Navigation der
   *  Seite). Die Seite reicht ihren bestehenden Stepper durch — kein Nav-Neubau. */
  kopf?: ReactNode
  /** Paket CT: Tabellen-Ablesung des Chart-Inhalts (i. d. R. `ChartDatenTabelle`).
   *  Gesetzt → Chart-⇄-Tabelle-Umschalter in der Kopfzeile; der Zugang zur
   *  Chart-Tabelle lebt NUR hier (kein Kartenkopf-Icon, Gernot 2026-07-18). */
  tabelle?: ReactNode
  children: ReactNode
}) {
  // Flüchtig wie der Fokus selbst: jedes Öffnen startet beim Chart.
  const [ansicht, setAnsicht] = useState<'chart' | 'tabelle'>('chart')

  // Schließen-Konvention (Style-Guide B16, Gernot 2026-07-17): ESC schließt. Einen
  // Backdrop-Klick gibt es hier bewusst NICHT — das Overlay ist deckend, es gibt kein
  // Daneben. Der Zuhörer hängt am Mount, nicht an einem `isOpen`: die Komponente ist
  // entweder gerendert oder gar nicht da (Muster wie `infothek/DateiLightbox`).
  //
  // ⚠ Warum aufgeschoben und nicht sofort geschlossen wird: Zuhörer auf `document`
  // laufen in Registrierungs-Reihenfolge. Das Vollbild steht zuerst, ein SPÄTER
  // geöffnetes Overlay darin (der `DatumPicker` im `kopf`-Slot von Cockpit/Tag und
  // /Monat, ein `ui/Modal`) läuft also NACH uns. Würden wir sofort schließen, nähme
  // ESC dem Nutzer beides auf einmal: Picker UND Vollbild. Wer die Taste verbraucht,
  // ruft `preventDefault()`; wir entscheiden erst, wenn alle Zuhörer dran waren.
  //
  // ⛔ `setTimeout`, NICHT `queueMicrotask` — am 2026-08-28 an der Box gemessen: Chrome
  // fährt nach JEDEM Zuhörer einen Microtask-Checkpoint, ein Microtask läuft dort also
  // VOR dem nächsten Zuhörer und sieht dessen `preventDefault` nicht. jsdom tut das
  // nicht: die Vitest-Probe war grün, während die Anwendung Picker und Vollbild
  // gemeinsam schloss. Ein Makrotask läuft in beiden erst nach der ganzen Zustellung.
  useEffect(() => {
    const beiTaste = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setTimeout(() => { if (!e.defaultPrevented) onClose() }, 0)
    }
    document.addEventListener('keydown', beiTaste)
    return () => document.removeEventListener('keydown', beiTaste)
  }, [onClose])

  // D10-1 (detLAN R10): Portal an `document.body`. Ein Ancestor der Block-Zone
  // erzeugt einen Containing-Block (transform/filter/backdrop-blur/contain) → ein
  // `fixed inset-0` klemmt sonst relativ dazu statt zum Viewport (Sliver oben).
  // Das Overlay an `body` zu hängen löst das app-weit (kein Ancestor mehr).
  // A9-Ausnahme (check:scrollschatten-Allowlist): das Vollbild-Overlay IST im
  // Fokus-Modus die Seite — Seiten-Scroller behalten den nativen Balken (wie
  // LayoutV4/ViewShell); der ScrollSchatten-Fade gilt für Inhalts-Container.
  const overlay = (
    <div className="fixed inset-0 z-50 bg-white dark:bg-gray-900 flex flex-col p-3 sm:p-6 gap-3 overflow-auto">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
          {Icon && <Icon className={`h-5 w-5 ${farbe ?? ''}`} />}
          {titel}
          <span className="text-xs font-normal text-gray-400 dark:text-gray-500">Fokus / Vollbild</span>
        </h2>
        <div className="flex items-center gap-2">
          {tabelle != null && (
            <SegmentControl
              ariaLabel="Darstellung"
              size="sm"
              optionen={[
                { key: 'chart', label: 'Chart' },
                { key: 'tabelle', label: 'Tabelle' },
              ]}
              value={ansicht}
              onChange={setAnsicht}
            />
          )}
          <button
            type="button"
            onClick={onClose}
            className="min-h-[44px] flex items-center gap-2 px-3 rounded-lg text-sm font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
          >
            <Minimize2 className="h-4 w-4" /> Zurück
          </button>
        </div>
      </div>
      {kopf != null && <div className="flex-shrink-0">{kopf}</div>}
      <div className="flex-1 min-h-0">
        {tabelle != null && ansicht === 'tabelle' ? tabelle : children}
      </div>
    </div>
  )
  return typeof document !== 'undefined' ? createPortal(overlay, document.body) : overlay
}
