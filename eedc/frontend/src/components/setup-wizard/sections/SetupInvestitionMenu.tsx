import { useState } from 'react'
import { Plus } from 'lucide-react'
import type { InvestitionTyp } from '../../../types'
import { INVESTITION_TYP_ORDER, TYP_LABELS as INVESTITION_TYP_LABELS } from '../../../lib/constants'
import { getDeviceIcon } from './setupInvestitionHelpers'

/**
 * „Investition hinzufügen"-Dropdown im Setup-Wizard (ausgelagert aus
 * InvestitionenStep, Slice 6). Reine Aktions-Buttons (amber-Theme bleibt,
 * keine Formular-Controls).
 */
export function SetupInvestitionMenu({ onAdd }: { onAdd: (typ: InvestitionTyp) => void }) {
  const [showMenu, setShowMenu] = useState(false)

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setShowMenu(!showMenu)}
        className="inline-flex items-center gap-2 px-4 py-2.5 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 font-medium rounded-lg hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors"
      >
        <Plus className="w-5 h-5" />
        Investition hinzufügen
      </button>

      {showMenu && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setShowMenu(false)} />
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
