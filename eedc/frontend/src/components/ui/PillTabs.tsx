/**
 * PillTabs — einheitliche Sub-Tab-Leiste im Schaltflächen-Stil.
 *
 * Ersetzt das alte `border-b-2`-Underline-Muster (#208 detLAN: einheitlich
 * als Schaltfläche statt Unterstrich). Wird in Auswertungen, Aussichten,
 * Community und Daten genutzt — drift-arm via zentrale Quelle.
 */

import type { ComponentType, SVGProps } from 'react'
import { SimpleTooltip } from './FormelTooltip'

export interface PillTab<K extends string> {
  key: K
  label: string
  icon?: ComponentType<SVGProps<SVGSVGElement>>
  beta?: boolean
  tooltip?: string
}

interface PillTabsProps<K extends string> {
  tabs: PillTab<K>[]
  activeKey: K
  onChange: (key: K) => void
  /** Optional className am Container, z. B. für Margin/Justify-Anpassungen */
  className?: string
}

export function PillTabs<K extends string>({
  tabs,
  activeKey,
  onChange,
  className = '',
}: PillTabsProps<K>) {
  return (
    <nav
      role="tablist"
      className={`flex flex-wrap gap-2 ${className}`}
    >
      {tabs.map((tab) => {
        const Icon = tab.icon
        const isActive = activeKey === tab.key
        const button = (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.key)}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors ${
              isActive
                ? 'bg-primary-500 text-white shadow-sm hover:bg-primary-600 dark:bg-primary-600 dark:hover:bg-primary-500'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
            }`}
          >
            {Icon && <Icon className="h-4 w-4" />}
            <span>{tab.label}</span>
            {tab.beta && (
              <span
                className={`rounded px-1 py-0.5 text-[10px] font-semibold leading-none ${
                  isActive
                    ? 'bg-white/20 text-white'
                    : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400'
                }`}
              >
                Beta
              </span>
            )}
          </button>
        )
        return tab.tooltip ? (
          <SimpleTooltip key={tab.key} text={tab.tooltip}>
            {button}
          </SimpleTooltip>
        ) : (
          button
        )
      })}
    </nav>
  )
}

export default PillTabs
