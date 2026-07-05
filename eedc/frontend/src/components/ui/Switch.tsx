/**
 * Switch — DER Schalter-SoT (Style-Guide B15, R3b S3 2026-07-05; Seed-Fund c).
 *
 * Extrahiert aus der FormBlock-'toggle'-Variante (wörtlich identisches Markup
 * lebte auch in CommunityShareBlock). Dritte, abweichende Optik in
 * `setup-wizard/steps/BasisSensorenStep.tsx` bleibt bis zu den V3-Paketen stehen
 * (V3-geteilt via SensorMappingWizard).
 *
 * Dokumentierte Eigenschaft der SoT (Kontrast-Ausnahme, A8): der Knauf bleibt in
 * BEIDEN Modi `bg-white` — auf der gefüllten Bahn (primary-600 an, gray-300/600
 * aus) ist Weiß der Kontrastträger; ein dark:-Zwilling würde ihn auf der dunklen
 * Bahn absaufen lassen.
 */
export function Switch({
  checked, onChange, disabled, ariaLabel,
}: {
  checked: boolean
  onChange: (an: boolean) => void
  disabled?: boolean
  ariaLabel: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
        checked ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600'
      }`}
    >
      <span
        className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
          checked ? 'translate-x-5' : 'translate-x-0.5'
        }`}
      />
    </button>
  )
}

export default Switch
