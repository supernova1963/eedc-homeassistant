/**
 * Infothek Kategorien — Frontend-Konfiguration
 *
 * Definiert Icons und Farben für jede Kategorie.
 * Feld-Schemas werden vom Backend geladen (/api/infothek/kategorien).
 */

import {
  Zap, Sun, Flame, Droplets, Thermometer, TreePine,
  Shield, User, Wrench, Landmark, Coins, BadgeCheck,
  Calculator, Gauge, FileText,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface KategorieConfig {
  label: string
  icon: LucideIcon
  color: string
  bgColor: string
}

export const KATEGORIE_CONFIG: Record<string, KategorieConfig> = {
  stromvertrag: {
    label: 'Stromvertrag',
    icon: Zap,
    color: 'text-yellow-500',
    bgColor: 'bg-yellow-50 dark:bg-yellow-900/20',
  },
  einspeisevertrag: {
    label: 'Einspeisevertrag',
    icon: Sun,
    color: 'text-orange-500',
    bgColor: 'bg-orange-50 dark:bg-orange-900/20',
  },
  gasvertrag: {
    label: 'Gasvertrag',
    icon: Flame,
    color: 'text-red-500',
    bgColor: 'bg-red-50 dark:bg-red-900/20',
  },
  wasservertrag: {
    label: 'Wasservertrag',
    icon: Droplets,
    color: 'text-blue-500',
    bgColor: 'bg-blue-50 dark:bg-blue-900/20',
  },
  fernwaerme: {
    label: 'Fernwärme',
    icon: Thermometer,
    color: 'text-rose-500',
    bgColor: 'bg-rose-50 dark:bg-rose-900/20',
  },
  brennstoff: {
    label: 'Brennstoff',
    icon: TreePine,
    color: 'text-amber-700',
    bgColor: 'bg-amber-50 dark:bg-amber-900/20',
  },
  versicherung: {
    label: 'Versicherung',
    icon: Shield,
    color: 'text-indigo-500',
    bgColor: 'bg-indigo-50 dark:bg-indigo-900/20',
  },
  ansprechpartner: {
    label: 'Vertragspartner',
    icon: User,
    color: 'text-teal-500',
    bgColor: 'bg-teal-50 dark:bg-teal-900/20',
  },
  wartungsvertrag: {
    label: 'Wartungsvertrag',
    icon: Wrench,
    color: 'text-gray-500',
    bgColor: 'bg-gray-50 dark:bg-gray-800/50',
  },
  marktstammdatenregister: {
    label: 'MaStR',
    icon: Landmark,
    color: 'text-purple-500',
    bgColor: 'bg-purple-50 dark:bg-purple-900/20',
  },
  foerderung: {
    label: 'Förderung',
    icon: Coins,
    color: 'text-emerald-500',
    bgColor: 'bg-emerald-50 dark:bg-emerald-900/20',
  },
  garantie: {
    label: 'Komponente / Datenblatt',
    icon: BadgeCheck,
    color: 'text-green-500',
    bgColor: 'bg-green-50 dark:bg-green-900/20',
  },
  steuerdaten: {
    label: 'Steuerdaten',
    icon: Calculator,
    color: 'text-cyan-500',
    bgColor: 'bg-cyan-50 dark:bg-cyan-900/20',
  },
  messstellenbetreiber: {
    label: 'Messstellenbetreiber',
    icon: Gauge,
    color: 'text-sky-500',
    bgColor: 'bg-sky-50 dark:bg-sky-900/20',
  },
  sonstiges: {
    label: 'Sonstiges',
    icon: FileText,
    color: 'text-gray-400',
    bgColor: 'bg-gray-50 dark:bg-gray-800/50',
  },
}

/** Alle Kategorie-Keys in definierter Reihenfolge */
export const KATEGORIE_KEYS = Object.keys(KATEGORIE_CONFIG)

/** Fallback für unbekannte Kategorien */
export const DEFAULT_KATEGORIE_CONFIG: KategorieConfig = {
  label: 'Unbekannt',
  icon: FileText,
  color: 'text-gray-400',
  bgColor: 'bg-gray-50 dark:bg-gray-800/50',
}

export function getKategorieConfig(kategorie: string): KategorieConfig {
  return KATEGORIE_CONFIG[kategorie] ?? DEFAULT_KATEGORIE_CONFIG
}
