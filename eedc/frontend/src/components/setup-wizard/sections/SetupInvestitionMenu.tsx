import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '../../ui'
import type { InvestitionTyp } from '../../../types'
import { INVESTITION_TYP_ORDER, TYP_LABELS as INVESTITION_TYP_LABELS } from '../../../lib/constants'
import { getDeviceIcon } from './setupInvestitionHelpers'

/**
 * „Investition hinzufügen"-Dropdown im Setup-Wizard (ausgelagert aus
 * InvestitionenStep, Slice 6). Paket F (2026-07-17): Trigger = `Button`-SoT,
 * Dropdown-Einträge bleiben rohe Menü-Struktur-Elemente (ROH_INFRA).
 */
export function SetupInvestitionMenu({ onAdd }: { onAdd: (typ: InvestitionTyp) => void }) {
  const [showMenu, setShowMenu] = useState(false)

  return (
    <div className="relative">
      <Button type="button" variant="secondary" onClick={() => setShowMenu(!showMenu)} aria-expanded={showMenu}>
        <Plus className="w-4 h-4 mr-2" />
        Investition hinzufügen
      </Button>

      {showMenu && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setShowMenu(false)} />
          {/* Dropdown-Einträge: Menü-Struktur-Elemente, rohes <button> = Impl
              (ROH_INFRA-Freigabe Gernot 2026-07-17, Paket F). */}
          <div className="absolute left-0 mt-2 w-64 bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-200 dark:border-gray-700 z-20 py-2">
            {INVESTITION_TYP_ORDER.map(typ => (
              <button
                key={typ}
                type="button"
                onClick={() => { onAdd(typ); setShowMenu(false) }}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors text-left"
              >
                <span className="text-amber-600 dark:text-amber-400">{getDeviceIcon(typ)}</span>
                <span className="text-gray-900 dark:text-white">{INVESTITION_TYP_LABELS[typ]}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
