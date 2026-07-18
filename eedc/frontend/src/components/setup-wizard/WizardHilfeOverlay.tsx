/**
 * WizardHilfeOverlay — Kontext-Hilfe im Erst-Setup (D2, Mechanik 2026-07-18).
 *
 * Das Setup-Gate rendert VOR dem Router — `/hilfe` ist hier unerreichbar. Das
 * Overlay fetcht die Installations-Hilfe daher direkt (statisches `help/`-System
 * wie `pages/Hilfe.tsx`) und rendert sie über die geteilte `MarkdownDoc`-SoT;
 * je Wizard-Step springt es zum passenden Anker (ANKER_JE_STEP).
 *
 * ⚠️ SCHARF ERST MIT R2a (Gernot 2026-07-18): die heutige Hilfe beschreibt die
 * V3-Welt — eine V3-Anleitung im V4-Wizard wäre schlechter als keine. R2a legt
 * beim Umschreiben von HANDBUCH_INSTALLATION die Anker je Wizard-Step an und
 * setzt dann WIZARD_HILFE_AKTIV = true (+ ANKER_JE_STEP auf die realen IDs).
 */
import { useEffect, useRef, useState } from 'react'
import { Modal } from '../ui'
import MarkdownDoc from '../ui/MarkdownDoc'
import type { WizardStep } from '../../hooks/useSetupWizard'

/** R2a-Merker: Button im Wizard-Kopf erscheint erst, wenn die Hilfe V4-Anker hat. */
export const WIZARD_HILFE_AKTIV = false

/** Anker-IDs in help/installation.md je Wizard-Step — mit R2a real anlegen. */
export const ANKER_JE_STEP: Partial<Record<WizardStep, string>> = {
  welcome: 'erst-setup',
  anlage: 'erst-setup-anlage',
  strompreise: 'erst-setup-strompreise',
  investitionen: 'erst-setup-komponenten',
  integration: 'erst-setup-integration',
  summary: 'erst-setup-abschluss',
}

interface Props {
  isOpen: boolean
  step: WizardStep
  onClose: () => void
}

export default function WizardHilfeOverlay({ isOpen, step, onClose }: Props) {
  const [markdown, setMarkdown] = useState<string | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isOpen || markdown != null) return
    // Statisch wie Hilfe.tsx (Vite base './' → relativ, kein Router nötig).
    fetch('help/installation.md')
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
      .then(setMarkdown)
      .catch((e) => setFehler(e instanceof Error ? e.message : 'Hilfe nicht ladbar'))
  }, [isOpen, markdown])

  // Nach dem Laden zum Step-Anker springen (Container-Scroll, kein Seiten-Scroll).
  useEffect(() => {
    if (!isOpen || markdown == null) return
    const anker = ANKER_JE_STEP[step]
    if (!anker) return
    const t = setTimeout(() => {
      const el = scrollRef.current?.querySelector(`#${CSS.escape(anker)}`)
      el?.scrollIntoView({ block: 'start' })
    }, 50)
    return () => clearTimeout(t)
  }, [isOpen, markdown, step])

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Hilfe zur Einrichtung" size="xl">
      <div ref={scrollRef} className="markdown-help max-h-[70vh] overflow-y-auto text-gray-800 dark:text-gray-200">
        {fehler && <p className="text-sm text-red-600 dark:text-red-400">Hilfe konnte nicht geladen werden: {fehler}</p>}
        {!fehler && markdown == null && <p className="text-sm text-gray-500 dark:text-gray-400">Lade …</p>}
        {markdown != null && <MarkdownDoc markdown={markdown} />}
      </div>
    </Modal>
  )
}
