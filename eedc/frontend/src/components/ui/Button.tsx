import { forwardRef, ButtonHTMLAttributes } from 'react'
import { Loader2 } from 'lucide-react'

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'amber'
type ButtonSize = 'sm' | 'md' | 'lg' | 'icon'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
}

// D7-7 (detLAN R7) → revidiert #27/R-Runde (Gernot 2026-06-28): einheitliche
// Aktions-Button-Höhe = **36 px** app-weit (vorher 44 px). detLAN fand 44 px „etwas
// zu hoch / reingequetscht" (CSV-Export im kompakten Block-Kopf neben 32-px-Nav-Icons).
// `min-h-[36px]` im Basis-Stil → alle Größen gleich hoch (sm/md/lg variieren nur
// Padding/Schrift). Filter-Controls (Pillen/Inputs/Selects) liegen bei 32 px (STEUER_H).
//
// D14-14 (detLAN #116, Gernot-Entscheid 2026-07-03) — Kontext-Regel Icons mobil:
// CSV-/PDF-/Export-Buttons behalten IMMER Icon + Wort (CsvExportButton-SoT bzw.
// PDF-Primäraktion); ANDERE mehrwortige Aktions-Buttons verlieren < 640 px ihr
// vorangestelltes Icon (`max-sm:hidden` an der Icon-Klasse), damit der Text
// einzeilig bleibt. Lauf-Spinner (Loader2) bleiben als Aktivitäts-Signal sichtbar.
const baseStyles = 'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed active:scale-95 min-h-[36px]'

const variants: Record<ButtonVariant, string> = {
  primary: 'bg-primary-600 text-white hover:bg-primary-700 focus:ring-primary-500',
  secondary: 'bg-gray-200 text-gray-900 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-100 dark:hover:bg-gray-600 focus:ring-gray-500',
  danger: 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
  ghost: 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700 focus:ring-gray-500',
  // amber: Identitäts-Variante des Erst-Setup-Gates (Setup-Wizard) — dieselbe
  // Achse wie Stepper `akzent="amber"` (Gernot 2026-07-17). Außerhalb des
  // Setup-Chromes nicht verwenden; Primäraktionen der App bleiben `primary`.
  amber: 'bg-amber-500 text-white hover:bg-amber-600 focus:ring-amber-500',
}

const sizes: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-3 text-base',
  // icon-only (B15): quadratisch (36×36, an die Button-Höhe angeglichen). Pflicht: title/aria-label.
  icon: 'p-2 min-w-[36px]',
}

/**
 * buttonClasses — Klassen-SoT für Button-Look, nutzbar auch außerhalb `<button>`
 * (z. B. Download-`<a>`), damit solche Aktions-Links dieselbe Höhe/Optik wie der
 * Button-SoT tragen statt eigene Klassen zu duplizieren (D7-7).
 */
export function buttonClasses(
  { variant = 'primary', size = 'md', className = '' }:
  { variant?: ButtonVariant; size?: ButtonSize; className?: string } = {},
): string {
  return `${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`.trim()
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = '', variant = 'primary', size = 'md', loading, disabled, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={buttonClasses({ variant, size, className })}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
        {children}
      </button>
    )
  }
)

Button.displayName = 'Button'

export default Button
