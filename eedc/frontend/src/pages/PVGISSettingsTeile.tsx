/**
 * Solarprognose — geteilte Teile (PVGIS-Ertragsprognose + Horizontprofil +
 * optimale Ausrichtung + Wetter-Provider-Info).
 *
 * EINE Code-Wahrheit für IST (`pages/PVGISSettings.tsx`, dünner Komposer) und
 * IA-V4 (Einstellungen-Katalog-Block „Solarprognose", inline wie Strompreise/
 * Monatsdaten — Gernot 2026-07-01). Der Aufrufer reicht die bereits aufgelöste
 * `anlageId` (+ die `anlage` für Geokoordinaten), im Mehr-Anlagen-Fall einen
 * `kopfZusatz` (Anlage-Auswahl). Zahlen de-DE über `fmtZahl` (Koordinaten bleiben
 * als geografische Nicht-Menge `toFixed(4)`).
 */

import { useState, useEffect, useRef, useCallback, type ReactNode } from 'react'
import { Sun, Download, Trash2, Check, RefreshCw, TrendingUp, MapPin, AlertCircle, Mountain, Upload } from 'lucide-react'
import { LoadingSpinner, Alert, Button, Input } from '../components/ui'
import { Parkbar } from '../components/park'
import { STRING_COLORS, CHART_COLORS, xAchse, achsenEinheit, ACHSEN_MARGIN_TOP, fmtZahl } from '../lib'
import { pvgisApi } from '../api'
import type { PVGISPrognose, GespeichertePrognose, AktivePrognoseResponse, PVGISOptimum, HorizontStatus } from '../api/pvgis'
import type { Anlage } from '../types'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'
import ChartTooltip from '../components/ui/ChartTooltip'
import CollapsibleSection from '../components/ui/CollapsibleSection'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

/**
 * Volle Solarprognose-Verwaltung. Wird von der IST-Seite (V3-Hülle) und dem
 * V4-Stammdaten-Block geteilt. `anlageId` ist bereits aufgelöst; `anlage` liefert
 * die Geokoordinaten; `kopfZusatz` (z. B. Anlage-Auswahl) wandert in die Kopfleiste.
 */
export function SolarprognoseVerwaltung({ anlageId, anlage, kopfZusatz }: {
  anlageId: number
  anlage?: Anlage
  kopfZusatz?: ReactNode
}) {
  const [aktivePrognose, setAktivePrognose] = useState<AktivePrognoseResponse | null>(null)
  const [gespeichertePrognosen, setGespeichertePrognosen] = useState<GespeichertePrognose[]>([])
  const [previewPrognose, setPreviewPrognose] = useState<PVGISPrognose | null>(null)
  const [optimum, setOptimum] = useState<PVGISOptimum | null>(null)
  const [loading, setLoading] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [optimumLoading, setOptimumLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Horizont-Profil
  const [horizontStatus, setHorizontStatus] = useState<HorizontStatus | null>(null)
  const [horizontUploading, setHorizontUploading] = useState(false)
  const horizontFileRef = useRef<HTMLInputElement>(null)

  // Parameter für Vorschau
  const [systemLosses, setSystemLosses] = useState(14)

  const loadData = useCallback(async () => {
    if (!anlageId) return

    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const [aktive, gespeicherte, horizont] = await Promise.all([
        pvgisApi.getAktivePrognose(anlageId),
        pvgisApi.listeGespeichertePrognosen(anlageId),
        pvgisApi.getHorizont(anlageId).catch(() => null)
      ])
      setAktivePrognose(aktive)
      setGespeichertePrognosen(gespeicherte)
      setHorizontStatus(horizont)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }, [anlageId])

  // Daten laden wenn Anlage gewechselt wird (loadData bricht ohne anlageId selbst ab)
  useEffect(() => {
    loadData()
  }, [loadData])

  const loadPreview = async () => {
    if (!anlageId) return

    setPreviewLoading(true)
    setError(null)

    try {
      const prognose = await pvgisApi.getPrognose(anlageId, {
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
    if (!anlageId) return

    setOptimumLoading(true)
    setError(null)

    try {
      const opt = await pvgisApi.getOptimum(anlageId)
      setOptimum(opt)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Ermitteln des Optimums')
    } finally {
      setOptimumLoading(false)
    }
  }

  const speicherePrognose = async () => {
    if (!anlageId) return

    setLoading(true)
    setError(null)

    try {
      await pvgisApi.speicherePrognose(anlageId, {
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

  const hatKoordinaten = anlage?.latitude && anlage?.longitude

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-2">{kopfZusatz}</div>
        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={loadData}
            disabled={loading}
            title="Aktualisieren"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Aktualisieren
          </Button>
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
          {/* D14-3 (detLAN #113/#123, Baufreigabe Gernot 2026-07-03): Reihenfolge
              „erst Einstellung, dann Ergebnis" — Einstell-/Pflege-Bereiche
              (Horizontprofil · Neue Prognose · Gespeicherte) zuerst, danach die
              reinen Anzeige-Bereiche (Aktive Prognose · Optimale Ausrichtung ·
              Wetter-Provider · Info), jeweils parkbar (Park-SoT; inert in V3). */}
          {/* Horizontprofil */}
          <CollapsibleSection title="Horizontprofil" storageKey="solarprognose-horizont" defaultOpen={false}>
            <div className="space-y-4">

            {horizontStatus?.hat_horizont ? (
              <div className="space-y-3">
                <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
                  <p className="text-sm font-medium text-green-700 dark:text-green-300 mb-2">Profil vorhanden</p>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <p className="text-green-600 dark:text-green-400">Datenpunkte</p>
                      <p className="font-bold text-green-700 dark:text-green-300">{horizontStatus.anzahl_punkte}</p>
                    </div>
                    <div>
                      <p className="text-green-600 dark:text-green-400">Min. Elevation</p>
                      <p className="font-bold text-green-700 dark:text-green-300">{horizontStatus.min_elevation}°</p>
                    </div>
                    <div>
                      <p className="text-green-600 dark:text-green-400">Max. Elevation</p>
                      <p className="font-bold text-green-700 dark:text-green-300">{horizontStatus.max_elevation}°</p>
                    </div>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => horizontFileRef.current?.click()}
                    disabled={horizontUploading}
                  >
                    <Upload className="max-sm:hidden h-4 w-4 mr-2" />
                    Eigene Datei
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={async () => {
                      if (!anlageId || !confirm('Horizontprofil löschen?')) return
                      try {
                        await pvgisApi.deleteHorizont(anlageId)
                        setHorizontStatus(null)
                        setSuccess('Horizontprofil gelöscht')
                      } catch (e) {
                        setError(e instanceof Error ? e.message : 'Fehler beim Löschen')
                      }
                    }}
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Löschen
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Das Horizontprofil beschreibt, wie hoch Berge, Gebäude oder Bäume den Horizont
                  in jeder Himmelsrichtung verdecken. Ohne Profil verwendet PVGIS automatisch
                  Geländedaten (~90m Auflösung) bei der Ertragsprognose.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Button
                    onClick={async () => {
                      if (!anlageId) return
                      setHorizontUploading(true)
                      setError(null)
                      try {
                        const result = await pvgisApi.abrufeHorizont(anlageId)
                        setHorizontStatus(result)
                        setSuccess('Geländeprofil von PVGIS abgerufen')
                      } catch (e) {
                        const err = e as { detail?: string; message?: string }
                        setError(err?.detail || err?.message || 'Abruf fehlgeschlagen')
                      } finally {
                        setHorizontUploading(false)
                      }
                    }}
                    disabled={horizontUploading}
                  >
                    {horizontUploading ? (
                      <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                    ) : (
                      <Download className="max-sm:hidden h-4 w-4 mr-2" />
                    )}
                    Geländeprofil von PVGIS abrufen
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => horizontFileRef.current?.click()}
                    disabled={horizontUploading}
                  >
                    <Upload className="max-sm:hidden h-4 w-4 mr-2" />
                    Eigene Datei hochladen
                  </Button>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  <strong>Geländeprofil:</strong> Erfasst Berge und große Geländestrukturen (aus Satellitendaten).
                  <br />
                  <strong>Eigene Datei:</strong> Für lokale Hindernisse (Gebäude, Bäume), die im Geländemodell fehlen.
                  Kann z.B. mit Smartphone-Apps wie "Sun Surveyor" erstellt oder von{' '}
                  <a href="https://re.jrc.ec.europa.eu/pvg_tools/en/" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
                    PVGIS
                  </a>
                  {' '}heruntergeladen werden.
                </p>
              </div>
            )}

            <input
              ref={horizontFileRef}
              type="file"
              accept=".txt,.csv,.hor"
              className="hidden"
              onChange={async (e) => {
                const file = e.target.files?.[0]
                if (!file || !anlageId) return
                setHorizontUploading(true)
                setError(null)
                try {
                  const result = await pvgisApi.uploadHorizont(anlageId, file)
                  setHorizontStatus(result)
                  setSuccess('Horizontprofil gespeichert')
                } catch (e) {
                  const err = e as { detail?: string; message?: string }
                  setError(err?.detail || err?.message || 'Upload fehlgeschlagen')
                } finally {
                  setHorizontUploading(false)
                  if (horizontFileRef.current) horizontFileRef.current.value = ''
                }
              }}
            />
            </div>
          </CollapsibleSection>

          {/* Neue Prognose abrufen */}
          <CollapsibleSection title="Neue Prognose abrufen" storageKey="solarprognose-neu" defaultOpen={false}>
            <div className="space-y-4">

            {/* D14-7 (detLAN #113): Hinweis-Zeile liegt UNTER dem Grid — vorher
                drückte sie das Eingabefeld über die items-end-Schaltfläche. */}
            <div className="grid md:grid-cols-2 gap-4 items-end">
              <Input
                label="Systemverluste (%)"
                type="number"
                value={systemLosses}
                onChange={(e) => setSystemLosses(parseFloat(e.target.value) || 14)}
                min={0}
                max={50}
                step={1}
              />

              <div className="flex items-end">
                <Button
                  onClick={loadPreview}
                  disabled={previewLoading}
                  className="w-full"
                >
                  {previewLoading ? (
                    <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Download className="max-sm:hidden h-4 w-4 mr-2" />
                  )}
                  Von PVGIS abrufen
                </Button>
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Typisch: 14 % (Kabel, Wechselrichter, etc.)
            </p>

            {/* Vorschau */}
            {previewPrognose && (
              <div className="border-t border-gray-200 dark:border-gray-700 pt-4 mt-4 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium text-gray-900 dark:text-white">Vorschau</h3>
                  <Button onClick={speicherePrognose} disabled={loading}>
                    <Check className="max-sm:hidden h-4 w-4 mr-2" />
                    Speichern & Aktivieren
                  </Button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                    <p className="text-sm text-gray-500">Jahresertrag</p>
                    <p className="text-xl font-bold">{fmtZahl(previewPrognose.jahresertrag_kwh, 0)} kWh</p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                    <p className="text-sm text-gray-500">Spezifisch</p>
                    <p className="text-xl font-bold">{fmtZahl(previewPrognose.spezifischer_ertrag_kwh_kwp, 0)} kWh/kWp</p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                    <p className="text-sm text-gray-500">Gesamt-Leistung</p>
                    <p className="text-xl font-bold">{fmtZahl(previewPrognose.gesamt_leistung_kwp, 1)} kWp</p>
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
                            {fmtZahl(m.leistung_kwp, 1)} kWp • {m.ausrichtung} • {m.neigung_grad}° • {fmtZahl(m.jahresertrag_kwh, 0)} kWh/a
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Monatswerte */}
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={previewPrognose.monatsdaten.map(m => ({
                        name: monatNamen[m.monat],
                        ertrag: m.e_m
                      }))}
                      margin={{ top: ACHSEN_MARGIN_TOP, right: 20, left: 20, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" {...xAchse()} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                      <YAxis
                        width={70}
                        tick={{ fontSize: 10 }}
                        tickFormatter={(v) => fmtZahl(v, 0)}
                        label={achsenEinheit('kWh')}
                      />
                      <Tooltip content={<ChartTooltip unit="kWh" />} />
                      <Bar dataKey="ertrag" fill={CHART_COLORS.erzeugung} name="Ertrag" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
            </div>
          </CollapsibleSection>

          {/* Gespeicherte Prognosen */}
          {gespeichertePrognosen.length > 0 && (
            <CollapsibleSection title="Gespeicherte Prognosen" storageKey="solarprognose-gespeichert" defaultOpen={false}>
              <div className="space-y-4">

              {/* Abnahme-Fund R14 (Gernot 2026-07-03): < lg Kachel-Darstellung
                  statt gequetschter Tabelle; ≥ lg Tabelle (Table-SoT-Muster). */}
              <div className="lg:hidden space-y-3">
                {gespeichertePrognosen.map((p) => (
                  <div key={p.id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                    <div className="flex items-center gap-2 flex-wrap text-sm">
                      <span className="font-medium text-gray-900 dark:text-white">{new Date(p.abgerufen_am).toLocaleDateString('de-DE')}</span>
                      {p.ist_aktiv && (
                        <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400"><Check className="h-3.5 w-3.5" /> Aktiv</span>
                      )}
                      {p.horizont_verwendet ? (
                        <span title="Eigenes Profil"><Mountain className="h-4 w-4 text-green-500" /></span>
                      ) : (
                        <span className="text-gray-400 dark:text-gray-500 text-xs">DEM</span>
                      )}
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-x-4 gap-y-1 text-sm">
                      <div><span className="text-gray-500 dark:text-gray-400">Jahresertrag</span><br />{fmtZahl(p.jahresertrag_kwh, 0)} kWh</div>
                      <div><span className="text-gray-500 dark:text-gray-400">kWh/kWp</span><br />{fmtZahl(p.spezifischer_ertrag_kwh_kwp, 0)}</div>
                      <div><span className="text-gray-500 dark:text-gray-400">Neigung</span><br />{p.neigung_grad}°</div>
                    </div>
                    <div className="mt-2 border-t border-gray-100 dark:border-gray-700 pt-1 flex justify-end gap-2">
                      {!p.ist_aktiv && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => aktivierePrognose(p.id)}
                          aria-label="Prognose aktivieren"
                          title="Aktivieren"
                        >
                          <Check className="h-4 w-4 text-blue-500" />
                        </Button>
                      )}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => loeschePrognose(p.id)}
                        aria-label="Prognose löschen"
                        title="Löschen"
                      >
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="overflow-x-auto hidden lg:block">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-700">
                      <th className="text-left py-2 px-2">Datum</th>
                      <th className="text-right py-2 px-2">Jahresertrag</th>
                      <th className="text-right py-2 px-2">kWh/kWp</th>
                      <th className="text-right py-2 px-2">Neigung</th>
                      <th className="text-center py-2 px-2">Horizont</th>
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
                          {fmtZahl(p.jahresertrag_kwh, 0)} kWh
                        </td>
                        <td className="text-right py-2 px-2">
                          {fmtZahl(p.spezifischer_ertrag_kwh_kwp, 0)}
                        </td>
                        <td className="text-right py-2 px-2">
                          {p.neigung_grad}°
                        </td>
                        <td className="text-center py-2 px-2">
                          {p.horizont_verwendet ? (
                            <span title="Eigenes Profil"><Mountain className="h-4 w-4 text-green-500 mx-auto" /></span>
                          ) : (
                            <span className="text-gray-400 dark:text-gray-500 text-xs">DEM</span>
                          )}
                        </td>
                        <td className="text-center py-2 px-2">
                          {p.ist_aktiv ? (
                            <span className="inline-flex items-center gap-1 text-green-600 dark:text-green-400">
                              <Check className="h-4 w-4" />
                              Aktiv
                            </span>
                          ) : (
                            <span className="text-gray-400 dark:text-gray-500">-</span>
                          )}
                        </td>
                        <td className="text-right py-2 px-2">
                          <div className="flex items-center justify-end gap-2">
                            {!p.ist_aktiv && (
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => aktivierePrognose(p.id)}
                                aria-label="Prognose aktivieren"
                                title="Aktivieren"
                              >
                                <Check className="h-4 w-4 text-blue-500" />
                              </Button>
                            )}
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => loeschePrognose(p.id)}
                              aria-label="Prognose löschen"
                              title="Löschen"
                            >
                              <Trash2 className="h-4 w-4 text-red-500" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              </div>
            </CollapsibleSection>
          )}

          <Parkbar id="anzeige:aktive-prognose" titel="Aktive Prognose">
          {/* Aktuelle Prognose */}
          <CollapsibleSection title="Aktive Prognose" storageKey="solarprognose-aktiv" defaultOpen={false}>
            <div className="space-y-4">

            {loading ? (
              <LoadingSpinner />
            ) : aktivePrognose ? (
              <div className="space-y-4">
                {/* KPIs */}
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
                  <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-4">
                    <p className="text-sm text-yellow-600 dark:text-yellow-400">Jahresertrag</p>
                    <p className="text-2xl font-bold text-yellow-700 dark:text-yellow-300">
                      {fmtZahl(aktivePrognose.jahresertrag_kwh, 0)} kWh
                    </p>
                  </div>
                  <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-4">
                    <p className="text-sm text-orange-600 dark:text-orange-400">Spezifisch</p>
                    <p className="text-2xl font-bold text-orange-700 dark:text-orange-300">
                      {fmtZahl(aktivePrognose.spezifischer_ertrag_kwh_kwp, 0)} kWh/kWp
                    </p>
                  </div>
                  <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
                    <p className="text-sm text-blue-600 dark:text-blue-400">Neigung</p>
                    <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">
                      {aktivePrognose.neigung_grad}°
                    </p>
                  </div>
                  <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
                    <p className="text-sm text-green-600 dark:text-green-400">
                      {(aktivePrognose.module?.length ?? 0) > 1 ? 'Strings' : 'Ausrichtung'}
                    </p>
                    <p className="text-2xl font-bold text-green-700 dark:text-green-300">
                      {(aktivePrognose.module?.length ?? 0) > 1
                        ? `${aktivePrognose.module!.length} Strings`
                        : aktivePrognose.ausrichtung_richtung}
                    </p>
                  </div>
                </div>

                {/* Monatswerte Chart: stacked pro Modul wenn >1, sonst Gesamt */}
                {aktivePrognose.monatswerte && aktivePrognose.monatswerte.length > 0 && (() => {
                  const module = aktivePrognose.module ?? []
                  const multiString = module.length > 1
                  const stringFarben = STRING_COLORS

                  const chartData = multiString
                    ? Array.from({ length: 12 }, (_, i) => {
                        const monat = i + 1
                        const row: Record<string, number | string> = { name: monatNamen[monat] }
                        module.forEach(mod => {
                          const md = mod.monatsdaten.find(x => x.monat === monat)
                          row[`m_${mod.investition_id}`] = md ? md.e_m : 0
                        })
                        return row
                      })
                    : aktivePrognose.monatswerte.map(m => ({
                        name: monatNamen[m.monat],
                        prognose: m.e_m
                      }))

                  return (
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData} margin={{ top: ACHSEN_MARGIN_TOP, right: 20, left: 20, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="name" {...xAchse()} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                          <YAxis
                            width={70}
                            tick={{ fontSize: 10 }}
                            tickFormatter={(v) => fmtZahl(v, 0)}
                            label={achsenEinheit('kWh')}
                          />
                          <Tooltip content={<ChartTooltip unit="kWh" />} />
                          {multiString ? (
                            module.map((mod, idx) => (
                              <Bar
                                key={mod.investition_id}
                                dataKey={`m_${mod.investition_id}`}
                                stackId="prognose"
                                fill={stringFarben[idx % stringFarben.length]}
                                name={`${mod.bezeichnung} (${mod.ausrichtung_richtung})`}
                              />
                            ))
                          ) : (
                            <Bar dataKey="prognose" fill={CHART_COLORS.erzeugung} name="Prognose" />
                          )}
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )
                })()}

                {/* Modul-Liste bei Multi-String */}
                {aktivePrognose.module && aktivePrognose.module.length > 1 && (
                  <div className="rounded-lg border border-gray-200 dark:border-gray-700 divide-y divide-gray-200 dark:divide-gray-700">
                    {aktivePrognose.module.map(mod => (
                      <div key={mod.investition_id} className="flex items-center justify-between px-4 py-2 text-sm">
                        <span className="font-medium text-gray-900 dark:text-white">{mod.bezeichnung}</span>
                        <span className="text-gray-500 dark:text-gray-400">
                          {fmtZahl(mod.leistung_kwp, 1)} kWp • {mod.ausrichtung_richtung} • {mod.neigung_grad}° • {fmtZahl(mod.jahresertrag_kwh, 0)} kWh/a
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Abgerufen am: {new Date(aktivePrognose.abgerufen_am).toLocaleDateString('de-DE')}
                  {' • '}Koordinaten: {aktivePrognose.latitude.toFixed(4)}°N, {aktivePrognose.longitude.toFixed(4)}°E
                  {' • '}Horizont: {aktivePrognose.horizont_verwendet ? 'Eigenes Profil' : 'PVGIS-Gelände'}
                </p>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                <Sun className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Noch keine Prognose gespeichert</p>
                <p className="text-sm mt-2">Rufe eine PVGIS Prognose ab und speichere sie.</p>
              </div>
            )}
            </div>
          </CollapsibleSection>
          </Parkbar>

          <Parkbar id="anzeige:optimale-ausrichtung" titel="Optimale Ausrichtung">
          {/* Optimale Ausrichtung */}
          <CollapsibleSection
            title="Optimale Ausrichtung"
            storageKey="solarprognose-optimum"
            defaultOpen={false}
            action={
              <Button onClick={loadOptimum} disabled={optimumLoading} variant="secondary">
                {optimumLoading ? (
                  <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <TrendingUp className="h-4 w-4 mr-2" />
                )}
                Berechnen
              </Button>
            }
          >
            <div className="space-y-4">

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
                        {fmtZahl(optimum.optimal.spezifischer_ertrag_kwh_kwp, 0)} kWh/kWp
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
            </div>
          </CollapsibleSection>
          </Parkbar>

          <Parkbar id="anzeige:ueber-solarprognose" titel="Über Solarprognose">
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
          </Parkbar>

        </>
      )}
    </div>
  )
}
