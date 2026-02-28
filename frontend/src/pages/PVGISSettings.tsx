/**
 * Solarprognose Einstellungen (vormals PVGIS Settings)
 *
 * Kombiniert:
 * - PVGIS Ertragsprognosen (TMY-Daten)
 * - Wetter-Provider Konfiguration für Ist-Daten
 * - Optimale Ausrichtung
 */

import { useState, useEffect } from 'react'
import { Sun, Download, Trash2, Check, RefreshCw, TrendingUp, MapPin, Compass, AlertCircle, Cloud } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, Button } from '../components/ui'
import { useAnlagen } from '../hooks'
import { pvgisApi, wetterApi } from '../api'
import type { PVGISPrognose, GespeichertePrognose, AktivePrognoseResponse, PVGISOptimum } from '../api/pvgis'
import type { WetterProviderList } from '../api/wetter'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

export default function PVGISSettings() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>()
  const [aktivePrognose, setAktivePrognose] = useState<AktivePrognoseResponse | null>(null)
  const [gespeichertePrognosen, setGespeichertePrognosen] = useState<GespeichertePrognose[]>([])
  const [previewPrognose, setPreviewPrognose] = useState<PVGISPrognose | null>(null)
  const [optimum, setOptimum] = useState<PVGISOptimum | null>(null)
  const [wetterProvider, setWetterProvider] = useState<WetterProviderList | null>(null)
  const [loading, setLoading] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [optimumLoading, setOptimumLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Parameter für Vorschau
  const [systemLosses, setSystemLosses] = useState(14)

  // Erste Anlage automatisch auswählen
  useEffect(() => {
    if (anlagen.length > 0 && !selectedAnlageId) {
      setSelectedAnlageId(anlagen[0].id)
    }
  }, [anlagen, selectedAnlageId])

  // Daten laden wenn Anlage gewechselt wird
  useEffect(() => {
    if (selectedAnlageId) {
      loadData()
    }
  }, [selectedAnlageId])

  const loadData = async () => {
    if (!selectedAnlageId) return

    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const [aktive, gespeicherte, provider] = await Promise.all([
        pvgisApi.getAktivePrognose(selectedAnlageId),
        pvgisApi.listeGespeichertePrognosen(selectedAnlageId),
        wetterApi.getProvider(selectedAnlageId).catch(() => null)
      ])
      setAktivePrognose(aktive)
      setGespeichertePrognosen(gespeicherte)
      setWetterProvider(provider)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }

  const loadPreview = async () => {
    if (!selectedAnlageId) return

    setPreviewLoading(true)
    setError(null)

    try {
      const prognose = await pvgisApi.getPrognose(selectedAnlageId, {
        system_losses: systemLosses
      })
      setPreviewPrognose(prognose)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Abrufen der PVGIS Prognose')
    } finally {
      setPreviewLoading(false)
    }
  }

  const loadOptimum = async () => {
    if (!selectedAnlageId) return

    setOptimumLoading(true)
    setError(null)

    try {
      const opt = await pvgisApi.getOptimum(selectedAnlageId)
      setOptimum(opt)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Ermitteln des Optimums')
    } finally {
      setOptimumLoading(false)
    }
  }

  const speicherePrognose = async () => {
    if (!selectedAnlageId) return

    setLoading(true)
    setError(null)

    try {
      await pvgisApi.speicherePrognose(selectedAnlageId, {
        system_losses: systemLosses
      })
      setSuccess('Prognose erfolgreich gespeichert')
      setPreviewPrognose(null)
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  const aktivierePrognose = async (prognoseId: number) => {
    try {
      await pvgisApi.aktivierePrognose(prognoseId)
      setSuccess('Prognose aktiviert')
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Aktivieren')
    }
  }

  const loeschePrognose = async (prognoseId: number) => {
    if (!confirm('Prognose wirklich löschen?')) return

    try {
      await pvgisApi.loeschePrognose(prognoseId)
      setSuccess('Prognose gelöscht')
      await loadData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Löschen')
    }
  }

  const selectedAnlage = anlagen.find(a => a.id === selectedAnlageId)
  const hatKoordinaten = selectedAnlage?.latitude && selectedAnlage?.longitude

  if (anlagenLoading) return <LoadingSpinner text="Lade..." />

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Solarprognose</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Sun className="h-8 w-8 text-yellow-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Solarprognose</h1>
        </div>
        <div className="flex items-center gap-3">
          {anlagen.length > 1 && (
            <Select
              value={selectedAnlageId?.toString() || ''}
              onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
              options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
            />
          )}
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            title="Aktualisieren"
          >
            <RefreshCw className={`h-5 w-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {error && <Alert type="error">{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      {/* Koordinaten-Warnung */}
      {!hatKoordinaten && (
        <Alert type="warning">
          <div className="flex items-start gap-2">
            <MapPin className="h-5 w-5 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-medium">Keine Geokoordinaten hinterlegt</p>
              <p className="text-sm mt-1">
                Bitte ergänze Latitude und Longitude in den Anlagen-Stammdaten,
                um PVGIS Prognosen abrufen zu können.
              </p>
            </div>
          </div>
        </Alert>
      )}

      {hatKoordinaten && (
        <>
          {/* Aktuelle Prognose */}
          <Card className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Aktive Prognose
            </h2>

            {loading ? (
              <LoadingSpinner />
            ) : aktivePrognose ? (
              <div className="space-y-4">
                {/* KPIs */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-4">
                    <p className="text-sm text-yellow-600 dark:text-yellow-400">Jahresertrag</p>
                    <p className="text-2xl font-bold text-yellow-700 dark:text-yellow-300">
                      {aktivePrognose.jahresertrag_kwh.toLocaleString('de-DE')} kWh
                    </p>
                  </div>
                  <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-4">
                    <p className="text-sm text-orange-600 dark:text-orange-400">Spezifisch</p>
                    <p className="text-2xl font-bold text-orange-700 dark:text-orange-300">
                      {aktivePrognose.spezifischer_ertrag_kwh_kwp.toFixed(0)} kWh/kWp
                    </p>
                  </div>
                  <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
                    <p className="text-sm text-blue-600 dark:text-blue-400">Neigung</p>
                    <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">
                      {aktivePrognose.neigung_grad}°
                    </p>
                  </div>
                  <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
                    <p className="text-sm text-green-600 dark:text-green-400">Ausrichtung</p>
                    <p className="text-2xl font-bold text-green-700 dark:text-green-300">
                      {aktivePrognose.ausrichtung_richtung}
                    </p>
                  </div>
                </div>

                {/* Monatswerte Chart */}
                {aktivePrognose.monatswerte && aktivePrognose.monatswerte.length > 0 && (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={aktivePrognose.monatswerte.map(m => ({
                        name: monatNamen[m.monat],
                        prognose: m.e_m
                      }))}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" />
                        <YAxis tickFormatter={(v) => `${v} kWh`} />
                        <Tooltip formatter={(v: number) => `${v.toFixed(0)} kWh`} />
                        <Bar dataKey="prognose" fill="#f59e0b" name="Prognose" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}

                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Abgerufen am: {new Date(aktivePrognose.abgerufen_am).toLocaleDateString('de-DE')}
                  {' • '}Koordinaten: {aktivePrognose.latitude.toFixed(4)}°N, {aktivePrognose.longitude.toFixed(4)}°E
                </p>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                <Sun className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Noch keine Prognose gespeichert</p>
                <p className="text-sm mt-2">Rufe eine PVGIS Prognose ab und speichere sie.</p>
              </div>
            )}
          </Card>

          {/* Neue Prognose abrufen */}
          <Card className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Neue Prognose abrufen
            </h2>

            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Systemverluste (%)
                </label>
                <input
                  type="number"
                  value={systemLosses}
                  onChange={(e) => setSystemLosses(parseFloat(e.target.value) || 14)}
                  min={0}
                  max={50}
                  step={1}
                  className="input w-full"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Typisch: 14% (Kabel, Wechselrichter, etc.)
                </p>
              </div>

              <div className="flex items-end">
                <Button
                  onClick={loadPreview}
                  disabled={previewLoading}
                  className="w-full"
                >
                  {previewLoading ? (
                    <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Download className="h-4 w-4 mr-2" />
                  )}
                  Von PVGIS abrufen
                </Button>
              </div>
            </div>

            {/* Vorschau */}
            {previewPrognose && (
              <div className="border-t border-gray-200 dark:border-gray-700 pt-4 mt-4 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium text-gray-900 dark:text-white">Vorschau</h3>
                  <Button onClick={speicherePrognose} disabled={loading}>
                    <Check className="h-4 w-4 mr-2" />
                    Speichern & Aktivieren
                  </Button>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                    <p className="text-sm text-gray-500">Jahresertrag</p>
                    <p className="text-xl font-bold">{previewPrognose.jahresertrag_kwh.toLocaleString('de-DE')} kWh</p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                    <p className="text-sm text-gray-500">Spezifisch</p>
                    <p className="text-xl font-bold">{previewPrognose.spezifischer_ertrag_kwh_kwp.toFixed(0)} kWh/kWp</p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                    <p className="text-sm text-gray-500">Gesamt-Leistung</p>
                    <p className="text-xl font-bold">{previewPrognose.gesamt_leistung_kwp.toFixed(1)} kWp</p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                    <p className="text-sm text-gray-500">PV-Module</p>
                    <p className="text-xl font-bold">{previewPrognose.module.length}</p>
                  </div>
                </div>

                {/* Detail pro Modul */}
                {previewPrognose.module.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">Module im Detail:</h4>
                    <div className="grid gap-2">
                      {previewPrognose.module.map(m => (
                        <div key={m.investition_id} className="flex items-center justify-between bg-gray-50 dark:bg-gray-800 rounded p-2 text-sm">
                          <span className="font-medium">{m.bezeichnung}</span>
                          <span className="text-gray-500">
                            {m.leistung_kwp} kWp • {m.ausrichtung} • {m.neigung_grad}° • {m.jahresertrag_kwh.toLocaleString('de-DE')} kWh/a
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Monatswerte */}
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={previewPrognose.monatsdaten.map(m => ({
                      name: monatNamen[m.monat],
                      ertrag: m.e_m
                    }))}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" fontSize={10} />
                      <YAxis tickFormatter={(v) => `${v}`} />
                      <Tooltip formatter={(v: number) => `${v.toFixed(0)} kWh`} />
                      <Bar dataKey="ertrag" fill="#22c55e" name="Ertrag" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </Card>

          {/* Optimale Ausrichtung */}
          <Card className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                <Compass className="h-5 w-5" />
                Optimale Ausrichtung
              </h2>
              <Button onClick={loadOptimum} disabled={optimumLoading} variant="secondary">
                {optimumLoading ? (
                  <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <TrendingUp className="h-4 w-4 mr-2" />
                )}
                Berechnen
              </Button>
            </div>

            {optimum ? (
              <div className="space-y-4">
                <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
                  <h4 className="text-sm font-medium text-green-600 dark:text-green-400 mb-2">Optimale Parameter für Standort</h4>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <p className="text-sm text-green-600 dark:text-green-400">Neigung</p>
                      <p className="text-xl font-bold text-green-700 dark:text-green-300">
                        {optimum.optimal.neigung_grad}°
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-green-600 dark:text-green-400">Ausrichtung</p>
                      <p className="text-xl font-bold text-green-700 dark:text-green-300">
                        {optimum.optimal.azimut_richtung}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-green-600 dark:text-green-400">Spez. Ertrag</p>
                      <p className="text-xl font-bold text-green-700 dark:text-green-300">
                        {optimum.optimal.spezifischer_ertrag_kwh_kwp.toFixed(0)} kWh/kWp
                      </p>
                    </div>
                  </div>
                </div>
                {optimum.hinweis && (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {optimum.hinweis}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-gray-500 dark:text-gray-400 text-sm">
                Klicke auf "Berechnen" um die optimale Ausrichtung für deinen Standort zu ermitteln.
              </p>
            )}
          </Card>

          {/* Gespeicherte Prognosen */}
          {gespeichertePrognosen.length > 0 && (
            <Card className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Gespeicherte Prognosen
              </h2>

              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-700">
                      <th className="text-left py-2 px-2">Datum</th>
                      <th className="text-right py-2 px-2">Jahresertrag</th>
                      <th className="text-right py-2 px-2">kWh/kWp</th>
                      <th className="text-right py-2 px-2">Neigung</th>
                      <th className="text-center py-2 px-2">Status</th>
                      <th className="text-right py-2 px-2">Aktionen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gespeichertePrognosen.map((p) => (
                      <tr key={p.id} className="border-b border-gray-100 dark:border-gray-800">
                        <td className="py-2 px-2">
                          {new Date(p.abgerufen_am).toLocaleDateString('de-DE')}
                        </td>
                        <td className="text-right py-2 px-2">
                          {p.jahresertrag_kwh.toLocaleString('de-DE')} kWh
                        </td>
                        <td className="text-right py-2 px-2">
                          {p.spezifischer_ertrag_kwh_kwp.toFixed(0)}
                        </td>
                        <td className="text-right py-2 px-2">
                          {p.neigung_grad}°
                        </td>
                        <td className="text-center py-2 px-2">
                          {p.ist_aktiv ? (
                            <span className="inline-flex items-center gap-1 text-green-600 dark:text-green-400">
                              <Check className="h-4 w-4" />
                              Aktiv
                            </span>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </td>
                        <td className="text-right py-2 px-2">
                          <div className="flex items-center justify-end gap-2">
                            {!p.ist_aktiv && (
                              <button
                                onClick={() => aktivierePrognose(p.id)}
                                className="p-1 text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded"
                                title="Aktivieren"
                              >
                                <Check className="h-4 w-4" />
                              </button>
                            )}
                            <button
                              onClick={() => loeschePrognose(p.id)}
                              className="p-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                              title="Löschen"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Wetter-Provider Info */}
          {wetterProvider && (
            <Card className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                <Cloud className="h-5 w-5" />
                Wetterdaten-Provider
              </h2>

              <p className="text-sm text-gray-600 dark:text-gray-400">
                Der Wetter-Provider bestimmt die Quelle für Globalstrahlungsdaten bei der Ist-Erfassung
                und der Kurzfrist-Prognose. Die Einstellung kann in den Anlagen-Stammdaten geändert werden.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Aktueller Provider</p>
                  <p className="text-lg font-semibold text-gray-900 dark:text-white">
                    {wetterProvider.aktueller_provider === 'auto' ? 'Automatisch' :
                     wetterProvider.aktueller_provider === 'brightsky' ? 'Bright Sky (DWD)' :
                     wetterProvider.aktueller_provider === 'open-meteo' ? 'Open-Meteo' :
                     wetterProvider.aktueller_provider === 'open-meteo-solar' ? 'Open-Meteo Solar (GTI)' :
                     wetterProvider.aktueller_provider}
                  </p>
                </div>
                <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Standort</p>
                  <p className="text-lg font-semibold text-gray-900 dark:text-white">
                    {wetterProvider.standort.land || 'Unbekannt'}
                    {wetterProvider.standort.in_deutschland && ' (DWD verfügbar)'}
                  </p>
                </div>
              </div>

              <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Verfügbare Provider</h4>
                <div className="grid gap-2">
                  {wetterProvider.provider.map(p => (
                    <div
                      key={p.id}
                      className={`flex items-center justify-between p-3 rounded-lg border ${
                        p.verfuegbar
                          ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20'
                          : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 opacity-60'
                      }`}
                    >
                      <div>
                        <p className={`font-medium ${p.verfuegbar ? 'text-green-700 dark:text-green-300' : 'text-gray-500 dark:text-gray-400'}`}>
                          {p.name}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {p.beschreibung}
                        </p>
                      </div>
                      <div className="text-sm">
                        {p.verfuegbar ? (
                          <span className="text-green-600 dark:text-green-400">✓ Verfügbar</span>
                        ) : (
                          <span className="text-gray-400">Nicht verfügbar</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )}

          {/* Info-Box */}
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-blue-500 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-blue-700 dark:text-blue-300">
                <p className="font-medium mb-1">Über Solarprognose</p>
                <p className="mb-2">
                  <strong>PVGIS</strong> (Langfrist): EU-Tool für Ertragsprognosen basierend auf Satellitendaten
                  und Klimamodellen. Nutzt historische TMY-Daten (Typical Meteorological Year).
                </p>
                <p>
                  <strong>Wetter-Provider</strong> (Kurzfrist): Aktuelle und historische Wetterdaten für
                  SOLL-IST-Vergleiche. Bright Sky liefert DWD-Daten (Deutschland), Open-Meteo weltweit.
                </p>
                <a
                  href="https://re.jrc.ec.europa.eu/pvg_tools/en/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 dark:text-blue-400 hover:underline mt-2 inline-block"
                >
                  PVGIS-Dokumentation →
                </a>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
