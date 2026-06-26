/**
 * ROI-Dashboard - Wirtschaftlichkeitsanalyse aller Investitionen.
 *
 * Seiten-Chrom (Anlagen-Selektor + anpassbare Berechnungs-Parameter) + die
 * geteilte `RoiAnalyse`-SoT (KPIs/Amortisation/ROI-nach-Typ/Detail-Tabelle).
 * Die v4-Auswertung „ROI" nutzt dieselbe `RoiAnalyse` ohne Slider (D3).
 */
import { useState, useEffect } from 'react'
import { Settings2 } from 'lucide-react'
import { Card, Alert, LoadingSpinner } from '../components/ui'
import { useSelectedAnlage, useAktuellerStrompreis } from '../hooks'
import { RoiAnalyse } from '../components/roi/RoiAnalyse'

export default function ROIDashboard() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()

  // Anpassbare Parameter
  const [strompreis, setStrompreis] = useState<number>(30)
  const [einspeiseverguetung, setEinspeiseverguetung] = useState<number>(8.2)
  // Slider als reines Override: leer = Backend löst pro Investition auf
  // (per-Inv `benzinpreis_euro` → letzter Monatsdaten-Preis → Default).
  const [benzinpreis, setBenzinpreis] = useState<number | undefined>(undefined)
  // Benzinpreis-Hinweis (Backend-Default) für den Slider-Placeholder.
  const [benzinHinweis, setBenzinHinweis] = useState<number | undefined>(undefined)

  const anlageId = selectedAnlageId
  const { strompreis: aktuellerStrompreis } = useAktuellerStrompreis(anlageId ?? null)

  // Strompreis aus DB übernehmen wenn verfügbar
  useEffect(() => {
    if (aktuellerStrompreis) {
      setStrompreis(aktuellerStrompreis.netzbezug_arbeitspreis_cent_kwh)
      setEinspeiseverguetung(aktuellerStrompreis.einspeiseverguetung_cent_kwh)
    }
  }, [aktuellerStrompreis])

  if (anlagenLoading) {
    return <LoadingSpinner text="Lade Daten..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">ROI-Dashboard</h1>
        <Alert type="warning">Bitte lege zuerst eine PV-Anlage an.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">ROI-Dashboard</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Wirtschaftlichkeitsanalyse deiner Investitionen
          </p>
        </div>
        <div className="flex items-center gap-3">
          {anlagen.length > 1 && (
            <select
              value={anlageId ?? ''}
              onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
              className="input w-auto"
            >
              {anlagen.map((a) => (
                <option key={a.id} value={a.id}>{a.anlagenname}</option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Parameter-Eingabe */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Settings2 className="h-5 w-5 text-gray-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Berechnungsparameter</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Strompreis (Cent/kWh)
            </label>
            <input
              type="number"
              step="0.1"
              value={strompreis}
              onChange={(e) => setStrompreis(Number(e.target.value))}
              className="input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Einspeisevergütung (Cent/kWh)
            </label>
            <input
              type="number"
              step="0.1"
              value={einspeiseverguetung}
              onChange={(e) => setEinspeiseverguetung(Number(e.target.value))}
              className="input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Benzinpreis (Euro/Liter)
            </label>
            <input
              type="number"
              step="0.01"
              value={benzinpreis ?? ''}
              placeholder={benzinHinweis?.toFixed(2) ?? '1.65'}
              onChange={(e) => {
                const v = e.target.value
                setBenzinpreis(v === '' ? undefined : Number(v))
              }}
              className="input"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Leer lassen → pro E-Auto wird der gepflegte Wert bzw. der aktuelle
              Marktpreis aus den Monatsdaten verwendet.
            </p>
          </div>
        </div>
      </Card>

      {anlageId && (
        <RoiAnalyse
          anlageId={anlageId}
          strompreis={strompreis}
          einspeiseverguetung={einspeiseverguetung}
          benzinpreis={benzinpreis}
          onLoaded={(d) => setBenzinHinweis(d.benzinpreis_hinweis_euro ?? undefined)}
        />
      )}
    </div>
  )
}
