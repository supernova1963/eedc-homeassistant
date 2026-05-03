import { Fragment, useState, useEffect, useMemo } from 'react'
import { Loader2, AlertTriangle, ArrowRight } from 'lucide-react'
import { Modal, Button, Alert } from '../ui'
import { energieProfilApi, type ReaggregatePreviewResponse } from '../../api/energie_profil'

interface Props {
  anlageId: number
  datum: string | null  // null = Modal geschlossen
  onClose: () => void
  onApplied: (result: { stunden_mit_messdaten: number }) => void
}

const KAT_LABELS: Record<string, string> = {
  pv: 'PV',
  einspeisung: 'Einspeisung',
  netzbezug: 'Netzbezug',
  ladung_batterie: 'Batterie-Ladung',
  entladung_batterie: 'Batterie-Entladung',
  verbrauch_wp: 'WP-Verbrauch',
  ladung_wallbox: 'Wallbox-Ladung',
  verbrauch_eauto: 'E-Auto-Verbrauch',
  erzeugung_sonstiges: 'Sonstige Erzeugung',
  verbrauch_sonstiges: 'Sonstiger Verbrauch',
}

function fmtKwh(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v.toFixed(3)
}

function diffClass(alt: number | null, neu: number | null): string {
  if (alt === null || neu === null) return ''
  const diff = Math.abs(neu - alt)
  if (diff > 1.0) return 'font-bold text-amber-600 dark:text-amber-400'
  if (diff > 0.1) return 'text-amber-600 dark:text-amber-400'
  return ''
}

export default function ReaggregatePreviewModal({ anlageId, datum, onClose, onApplied }: Props) {
  const [data, setData] = useState<ReaggregatePreviewResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!datum) {
      setData(null)
      setError(null)
      return
    }
    setLoading(true)
    setError(null)
    energieProfilApi.reaggregateTagPreview(anlageId, datum)
      .then(setData)
      .catch((e: Error) => setError(e.message || 'Vorschau konnte nicht geladen werden.'))
      .finally(() => setLoading(false))
  }, [anlageId, datum])

  // Kategorien sortiert (PV, Einspeisung, Bezug zuerst)
  const kategorien = useMemo(() => {
    if (!data) return []
    const all = new Set(data.slot_deltas.map(s => s.kategorie))
    const order = ['pv', 'einspeisung', 'netzbezug', 'ladung_batterie', 'entladung_batterie',
                   'verbrauch_wp', 'ladung_wallbox', 'verbrauch_eauto',
                   'erzeugung_sonstiges', 'verbrauch_sonstiges']
    return order.filter(k => all.has(k))
  }, [data])

  // Index slot_deltas: stunde × kategorie → {alt, neu}
  const slotIndex = useMemo(() => {
    if (!data) return new Map<string, { alt: number | null; neu: number | null }>()
    const m = new Map<string, { alt: number | null; neu: number | null }>()
    for (const s of data.slot_deltas) {
      m.set(`${s.stunde}|${s.kategorie}`, { alt: s.alt_kwh, neu: s.neu_kwh })
    }
    return m
  }, [data])

  const handleApply = async () => {
    if (!datum) return
    setApplying(true)
    setError(null)
    try {
      const res = await energieProfilApi.reaggregateTag(anlageId, datum)
      onApplied({ stunden_mit_messdaten: res.stunden_mit_messdaten })
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Übernahme fehlgeschlagen.')
      setApplying(false)
    }
  }

  if (!datum) return null

  return (
    <Modal
      isOpen={!!datum}
      onClose={applying ? () => {} : onClose}
      title={`Vorschau: ${datum} aus HA neu laden`}
      size="xl"
    >
      {loading && (
        <div className="flex items-center justify-center py-8 text-gray-500">
          <Loader2 className="w-5 h-5 mr-2 animate-spin" />
          Lade HA-Werte für Vorschau …
        </div>
      )}

      {error && <Alert type="error" className="mb-3">{error}</Alert>}

      {data && !loading && (
        <>
          {!data.ha_verfuegbar && (
            <Alert type="warning" className="mb-3">
              <AlertTriangle className="inline w-4 h-4 mr-1" />
              HA-Statistics nicht erreichbar — die "Neu"-Spalte ist leer.
              Bei Übernahme wird nichts überschrieben.
            </Alert>
          )}

          <p className="text-sm text-gray-600 dark:text-gray-300 mb-3">
            Vergleich der aktuellen Snapshots in der Datenbank (<strong>Alt</strong>) mit den
            Werten, die jetzt aus HA-Statistics kämen (<strong>Neu</strong>). Slot 0 hängt vom
            Vortags-23:00-Snapshot ab — der ist hier mit aufgeführt. Erst nach <em>Übernehmen</em>
            werden die Snapshots überschrieben und der Tag neu aggregiert.
          </p>

          {/* Tagesumme */}
          <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-700/50 rounded">
            <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
              Tagesumme {datum} (kWh)
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400">
                  <th className="pb-1">Kategorie</th>
                  <th className="pb-1 text-right">Alt</th>
                  <th className="pb-1"><span className="sr-only">wird zu</span></th>
                  <th className="pb-1 text-right">Neu</th>
                </tr>
              </thead>
              <tbody>
                {kategorien.map(k => {
                  const alt = data.tagesumme_alt[k] ?? null
                  const neu = data.tagesumme_neu[k] ?? null
                  return (
                    <tr key={k}>
                      <td className="py-0.5">{KAT_LABELS[k] || k}</td>
                      <td className="py-0.5 text-right tabular-nums">{fmtKwh(alt)}</td>
                      <td className="py-0.5 text-center text-gray-400">
                        <ArrowRight className="inline w-3 h-3" />
                      </td>
                      <td className={`py-0.5 text-right tabular-nums ${diffClass(alt, neu)}`}>
                        {fmtKwh(neu)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Stundentabelle */}
          <div className="overflow-x-auto max-h-96 border border-gray-200 dark:border-gray-700 rounded">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-gray-100 dark:bg-gray-800 z-10">
                <tr>
                  <th rowSpan={2} className="px-2 py-1 text-left">Stunde</th>
                  {kategorien.map(k => (
                    <th key={k} colSpan={2} className="px-2 py-1 text-center border-l border-gray-200 dark:border-gray-700">
                      {KAT_LABELS[k] || k}
                    </th>
                  ))}
                </tr>
                <tr>
                  {kategorien.map(k => (
                    <Fragment key={k}>
                      <th className="px-2 py-1 text-right border-l border-gray-200 dark:border-gray-700 text-gray-500">Alt</th>
                      <th className="px-2 py-1 text-right text-gray-500">Neu</th>
                    </Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: 24 }, (_, h) => h).map(h => (
                  <tr
                    key={h}
                    className={h === 0 ? 'bg-blue-50 dark:bg-blue-900/20' : 'odd:bg-gray-50 dark:odd:bg-gray-700/30'}
                  >
                    <td className="px-2 py-1 font-medium tabular-nums">
                      {String(h).padStart(2, '0')}:00
                      {h === 0 && (
                        <span className="ml-1 text-[10px] text-blue-600 dark:text-blue-400" title="Slot 0 = Wert(00:00) − Wert(Vortag 23:00)">
                          ↤ Vortag
                        </span>
                      )}
                    </td>
                    {kategorien.map(k => {
                      const cell = slotIndex.get(`${h}|${k}`)
                      const alt = cell?.alt ?? null
                      const neu = cell?.neu ?? null
                      return (
                        <Fragment key={k}>
                          <td className="px-2 py-1 text-right tabular-nums border-l border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400">
                            {fmtKwh(alt)}
                          </td>
                          <td className={`px-2 py-1 text-right tabular-nums ${diffClass(alt, neu)}`}>
                            {fmtKwh(neu)}
                          </td>
                        </Fragment>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
            Auffällige Differenzen sind orange markiert ({'>'} 0.1 kWh) bzw. fett ({'>'} 1 kWh).
            Übernahme schreibt 25 Snapshots (Vortag 23:00 bis Folgetag 00:00) und rechnet
            den Tag neu.
          </p>

          {/* Aktionen */}
          <div className="flex justify-end gap-2 mt-4 pt-3 border-t border-gray-200 dark:border-gray-700">
            <Button variant="secondary" onClick={onClose} disabled={applying}>
              Abbrechen
            </Button>
            <Button
              variant="primary"
              onClick={handleApply}
              disabled={applying || !data.ha_verfuegbar}
            >
              {applying ? (
                <>
                  <Loader2 className="inline w-4 h-4 mr-1 animate-spin" />
                  Übernehme …
                </>
              ) : 'Übernehmen'}
            </Button>
          </div>
        </>
      )}
    </Modal>
  )
}
