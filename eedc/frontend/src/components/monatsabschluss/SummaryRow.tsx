export default function SummaryRow({
  label,
  wert,
  einheit,
  isText = false,
}: {
  label: string
  wert: number | string | null | undefined
  einheit: string
  isText?: boolean
}) {
  const hasValue = wert !== null && wert !== undefined && wert !== ''

  return (
    <div className="flex items-center justify-between px-4 py-2">
      <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>
      <span className="text-sm font-medium text-gray-900 dark:text-white">
        {hasValue ? (
          isText ? (
            <span className="max-w-xs truncate">{wert}</span>
          ) : (
            <>
              {typeof wert === 'number'
                ? wert.toLocaleString('de-DE', { maximumFractionDigits: 1 })
                : wert} {einheit}
            </>
          )
        ) : (
          <span className="text-gray-400 italic">nicht ausgefüllt</span>
        )}
      </span>
    </div>
  )
}
