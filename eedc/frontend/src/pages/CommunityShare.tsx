/**
 * Community Share Page
 *
 * Ermöglicht das anonyme Teilen von Anlagendaten mit der Community.
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Share2,
  Eye,
  Send,
  CheckCircle,
  AlertCircle,
  ExternalLink,
  Shield,
  MapPin,
  Zap,
  Battery,
  Home,
  Car,
  Loader2,
  Trash2,
  RefreshCw,
  Trophy,
  BarChart3,
} from 'lucide-react'
import { anlagenApi, communityApi } from '../api'
import type { PreviewResponse, ShareResponse, CommunityStatus } from '../api'

interface Anlage {
  id: number
  anlagenname: string
}

// Bundesland-Namen
const REGION_NAMEN: Record<string, string> = {
  BW: 'Baden-Württemberg',
  BY: 'Bayern',
  BE: 'Berlin',
  BB: 'Brandenburg',
  HB: 'Bremen',
  HH: 'Hamburg',
  HE: 'Hessen',
  MV: 'Mecklenburg-Vorpommern',
  NI: 'Niedersachsen',
  NW: 'Nordrhein-Westfalen',
  RP: 'Rheinland-Pfalz',
  SL: 'Saarland',
  SN: 'Sachsen',
  ST: 'Sachsen-Anhalt',
  SH: 'Schleswig-Holstein',
  TH: 'Thüringen',
  AT: 'Österreich',
  CH: 'Schweiz',
  XX: 'Unbekannt',
}

export default function CommunityShare() {
  const navigate = useNavigate()

  const [anlagen, setAnlagen] = useState<Anlage[]>([])
  const [selectedAnlage, setSelectedAnlage] = useState<number | null>(null)
  const [status, setStatus] = useState<CommunityStatus | null>(null)
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [result, setResult] = useState<ShareResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [sharing, setSharing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [consentGiven, setConsentGiven] = useState(false)

  // Anlagen laden
  useEffect(() => {
    const loadAnlagen = async () => {
      try {
        const data = await anlagenApi.list()
        setAnlagen(data)
        if (data.length === 1) {
          setSelectedAnlage(data[0].id)
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Fehler beim Laden'
        setError(message)
      } finally {
        setLoading(false)
      }
    }
    loadAnlagen()
  }, [])

  // Community-Status prüfen
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const statusResult = await communityApi.getStatus()
        setStatus(statusResult)
      } catch {
        setStatus({ online: false, url: 'https://energy.raunet.eu', error: 'Nicht erreichbar' })
      }
    }
    checkStatus()
  }, [])

  // Vorschau laden wenn Anlage ausgewählt
  useEffect(() => {
    if (!selectedAnlage) {
      setPreview(null)
      return
    }

    const loadPreview = async () => {
      setLoadingPreview(true)
      setError(null)
      try {
        const previewResult = await communityApi.getPreview(selectedAnlage)
        setPreview(previewResult)
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Fehler beim Laden der Vorschau'
        setError(message)
      } finally {
        setLoadingPreview(false)
      }
    }
    loadPreview()
  }, [selectedAnlage])

  // Daten teilen
  const handleShare = async () => {
    if (!selectedAnlage) return

    setSharing(true)
    setError(null)

    try {
      const shareResult = await communityApi.share(selectedAnlage)
      setResult(shareResult)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Fehler beim Teilen'
      setError(message)
    } finally {
      setSharing(false)
    }
  }

  // Daten löschen
  const handleDelete = async () => {
    if (!selectedAnlage) return

    setDeleting(true)
    setError(null)

    try {
      const deleteResult = await communityApi.delete(selectedAnlage)
      if (deleteResult.success) {
        // Vorschau neu laden um "bereits_geteilt" zu aktualisieren
        const previewResult = await communityApi.getPreview(selectedAnlage)
        setPreview(previewResult)
        setShowDeleteConfirm(false)
        // Kurze Erfolgsmeldung anzeigen
        setError(null)
        alert(`Gelöscht! ${deleteResult.anzahl_geloeschte_monate} Monatswerte wurden entfernt.`)
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Fehler beim Löschen'
      setError(message)
    } finally {
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    )
  }

  if (anlagen.length === 0) {
    return (
      <div className="p-6">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <p className="text-yellow-800">Keine Anlagen vorhanden. Bitte zuerst eine Anlage anlegen.</p>
        </div>
      </div>
    )
  }

  // Erfolgsansicht nach dem Teilen
  if (result?.success) {
    const benchmark = result.benchmark
    const abweichung = benchmark
      ? ((benchmark.spez_ertrag_anlage - benchmark.spez_ertrag_durchschnitt) / benchmark.spez_ertrag_durchschnitt * 100)
      : 0

    return (
      <div className="p-6 max-w-3xl mx-auto space-y-6">
        {/* Erfolgs-Header */}
        <div className="bg-green-50 border border-green-200 rounded-lg p-6 text-center">
          <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-3" />
          <h2 className="text-2xl font-bold text-green-800 mb-2">
            Vielen Dank für deinen Beitrag!
          </h2>
          <p className="text-green-700">
            {result.anzahl_monate} Monatswerte wurden mit der Community geteilt.
          </p>
        </div>

        {/* Benchmark-Ergebnisse - Erweitert */}
        {benchmark && (
          <div className="bg-white border rounded-lg overflow-hidden">
            <div className="bg-orange-50 px-4 py-3 border-b">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-orange-500" />
                Dein Anlagenvergleich
              </h3>
            </div>
            <div className="p-4">
              {/* Haupt-KPI */}
              <div className="text-center mb-6">
                <p className="text-sm text-gray-500 mb-1">Dein spezifischer Ertrag</p>
                <p className="text-4xl font-bold text-orange-500">
                  {benchmark.spez_ertrag_anlage.toFixed(0)}
                  <span className="text-lg font-normal text-gray-500 ml-1">kWh/kWp</span>
                </p>
                <p className={`text-sm mt-1 ${abweichung >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {abweichung >= 0 ? '+' : ''}{abweichung.toFixed(1)}% vs. Durchschnitt
                </p>
              </div>

              {/* Vergleichswerte */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500">Durchschnitt</p>
                  <p className="text-lg font-semibold">
                    {benchmark.spez_ertrag_durchschnitt.toFixed(0)} kWh/kWp
                  </p>
                </div>
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500">Region</p>
                  <p className="text-lg font-semibold">
                    {benchmark.spez_ertrag_region.toFixed(0)} kWh/kWp
                  </p>
                </div>
                <div className="bg-yellow-50 rounded-lg p-3">
                  <div className="flex items-center justify-center gap-1">
                    <Trophy className="h-4 w-4 text-yellow-500" />
                    <p className="text-xs text-gray-500">Rang gesamt</p>
                  </div>
                  <p className="text-lg font-semibold">
                    #{benchmark.rang_gesamt} <span className="text-sm text-gray-400">/ {benchmark.anzahl_anlagen_gesamt}</span>
                  </p>
                </div>
                <div className="bg-blue-50 rounded-lg p-3">
                  <div className="flex items-center justify-center gap-1">
                    <MapPin className="h-4 w-4 text-blue-500" />
                    <p className="text-xs text-gray-500">Rang Region</p>
                  </div>
                  <p className="text-lg font-semibold">
                    #{benchmark.rang_region} <span className="text-sm text-gray-400">/ {benchmark.anzahl_anlagen_region}</span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Aktionen */}
        <div className="flex flex-wrap gap-4 justify-center">
          <a
            href={result?.anlage_hash
              ? `${preview?.community_url || 'https://energy.raunet.eu'}?anlage=${result.anlage_hash}`
              : preview?.community_url || 'https://energy.raunet.eu'
            }
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-orange-500 text-white rounded-lg hover:bg-orange-600 font-medium"
          >
            <ExternalLink className="h-4 w-4" />
            Dein persönliches Benchmark öffnen
          </a>
          <button
            onClick={() => {
              setResult(null)
              setPreview(null)
              if (selectedAnlage) {
                // Vorschau neu laden
                communityApi.getPreview(selectedAnlage).then(setPreview)
              }
            }}
            className="inline-flex items-center gap-2 px-5 py-2.5 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium"
          >
            <RefreshCw className="h-4 w-4" />
            Erneut teilen
          </button>
          <button
            onClick={() => navigate('/')}
            className="px-5 py-2.5 text-gray-500 hover:text-gray-700"
          >
            Zum Dashboard
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Share2 className="h-8 w-8 text-orange-500" />
        <div>
          <h1 className="text-2xl font-bold">Mit Community teilen</h1>
          <p className="text-gray-500">
            Teile deine anonymisierten Anlagendaten mit der PV-Community
          </p>
        </div>
      </div>

      {/* Anlagen-Auswahl */}
      {anlagen.length > 1 && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Anlage auswählen
          </label>
          <select
            value={selectedAnlage || ''}
            onChange={(e) => setSelectedAnlage(Number(e.target.value) || null)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
          >
            <option value="">-- Anlage wählen --</option>
            {anlagen.map((a) => (
              <option key={a.id} value={a.id}>
                {a.anlagenname}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Server-Status */}
      <div className={`p-4 rounded-lg border ${
        status?.online
          ? 'bg-green-50 border-green-200'
          : 'bg-red-50 border-red-200'
      }`}>
        <div className="flex items-center gap-3">
          {status?.online ? (
            <CheckCircle className="h-5 w-5 text-green-500" />
          ) : (
            <AlertCircle className="h-5 w-5 text-red-500" />
          )}
          <div>
            <p className={status?.online ? 'text-green-800' : 'text-red-800'}>
              Community-Server: {status?.online ? 'Online' : 'Offline'}
            </p>
            {status?.version && (
              <p className="text-sm text-green-600">Version {status.version}</p>
            )}
            {status?.error && (
              <p className="text-sm text-red-600">{status.error}</p>
            )}
          </div>
        </div>
      </div>

      {/* Fehler-Anzeige */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {/* Datenschutz-Hinweis */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <Shield className="h-5 w-5 text-blue-500 mt-0.5" />
          <div>
            <h3 className="font-semibold text-blue-800">Datenschutz</h3>
            <ul className="mt-2 text-sm text-blue-700 space-y-1">
              <li>• Keine persönlichen Daten (Name, Adresse) werden übertragen</li>
              <li>• PLZ wird auf Bundesland reduziert</li>
              <li>• Nur aggregierte Monatswerte</li>
              <li>• Daten sind anonym und können nicht zu dir zurückverfolgt werden</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Einwilligung (DSGVO Art. 6/7) - nur beim ersten Teilen */}
      {!preview?.bereits_geteilt && preview?.anzahl_monate && preview.anzahl_monate > 0 && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={consentGiven}
              onChange={(e) => setConsentGiven(e.target.checked)}
              className="mt-1 h-4 w-4 text-orange-500 border-gray-300 rounded focus:ring-orange-500"
            />
            <span className="text-sm text-gray-700">
              Ich stimme der anonymen Übertragung meiner PV-Anlagendaten an die EEDC Community zu.
              Die Daten werden gemäß der{' '}
              <a
                href="https://energy.raunet.eu/datenschutz"
                target="_blank"
                rel="noopener noreferrer"
                className="text-orange-600 hover:underline"
              >
                Datenschutzerklärung
              </a>
              {' '}verarbeitet. Ich kann meine Daten jederzeit löschen.
            </span>
          </label>
        </div>
      )}

      {/* Laden-Indikator für Vorschau */}
      {loadingPreview && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-orange-500" />
          <span className="ml-2 text-gray-500">Lade Vorschau...</span>
        </div>
      )}

      {/* Datenvorschau */}
      {preview && !loadingPreview && (
        <div className="bg-white border rounded-lg overflow-hidden">
          <button
            onClick={() => setShowPreview(!showPreview)}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50"
          >
            <div className="flex items-center gap-2">
              <Eye className="h-5 w-5 text-gray-500" />
              <span className="font-medium">Datenvorschau</span>
            </div>
            <span className="text-sm text-gray-500">
              {showPreview ? 'Ausblenden' : 'Anzeigen'}
            </span>
          </button>

          {showPreview && (
            <div className="border-t p-4 space-y-4">
              {/* Anlagendaten */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="flex items-center gap-2">
                  <MapPin className="h-4 w-4 text-gray-400" />
                  <div>
                    <p className="text-xs text-gray-500">Region</p>
                    <p className="font-medium">
                      {REGION_NAMEN[preview.vorschau.region] || preview.vorschau.region}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Zap className="h-4 w-4 text-yellow-500" />
                  <div>
                    <p className="text-xs text-gray-500">Leistung</p>
                    <p className="font-medium">{preview.vorschau.kwp} kWp</p>
                  </div>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Ausrichtung</p>
                  <p className="font-medium capitalize">{preview.vorschau.ausrichtung}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Neigung</p>
                  <p className="font-medium">{preview.vorschau.neigung_grad}°</p>
                </div>
              </div>

              {/* Ausstattung */}
              <div className="flex flex-wrap gap-2">
                {preview.vorschau.speicher_kwh && (
                  <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 rounded text-sm">
                    <Battery className="h-4 w-4" />
                    Speicher ({preview.vorschau.speicher_kwh} kWh)
                  </span>
                )}
                {preview.vorschau.hat_waermepumpe && (
                  <span className="inline-flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-700 rounded text-sm">
                    <Home className="h-4 w-4" />
                    Wärmepumpe
                  </span>
                )}
                {preview.vorschau.hat_eauto && (
                  <span className="inline-flex items-center gap-1 px-2 py-1 bg-purple-100 text-purple-700 rounded text-sm">
                    <Car className="h-4 w-4" />
                    E-Auto
                  </span>
                )}
              </div>

              {/* Monatswerte-Zusammenfassung */}
              <div className="border-t pt-4">
                <p className="text-sm text-gray-600">
                  <strong>{preview.anzahl_monate}</strong> Monatswerte werden geteilt
                  {preview.vorschau.monatswerte.length > 0 && (
                    <span className="text-gray-400">
                      {' '}(von {preview.vorschau.monatswerte[0].monat}/{preview.vorschau.monatswerte[0].jahr}
                      {' '}bis {preview.vorschau.monatswerte[preview.vorschau.monatswerte.length - 1].monat}/
                      {preview.vorschau.monatswerte[preview.vorschau.monatswerte.length - 1].jahr})
                    </span>
                  )}
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Bereits geteilt - Info & Löschen-Option */}
      {preview?.bereits_geteilt && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-start justify-between">
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-blue-500 mt-0.5" />
              <div>
                <h3 className="font-semibold text-blue-800">Bereits mit Community geteilt</h3>
                <p className="text-sm text-blue-700 mt-1">
                  Deine Daten sind bereits im Community-Dashboard sichtbar.
                  Du kannst sie aktualisieren oder löschen.
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="text-red-600 hover:text-red-800 p-1"
              title="Daten löschen"
            >
              <Trash2 className="h-5 w-5" />
            </button>
          </div>
        </div>
      )}

      {/* Lösch-Bestätigung */}
      {showDeleteConfirm && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <h3 className="font-semibold text-red-800 mb-2">Daten wirklich löschen?</h3>
          <p className="text-sm text-red-700 mb-4">
            Alle deine geteilten Daten werden vom Community-Server entfernt.
            Dies kann nicht rückgängig gemacht werden.
          </p>
          <div className="flex gap-3">
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="inline-flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
            >
              {deleting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Wird gelöscht...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4" />
                  Ja, löschen
                </>
              )}
            </button>
            <button
              onClick={() => setShowDeleteConfirm(false)}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {/* Teilen-Button */}
      <div className="flex justify-center pt-4">
        <button
          onClick={handleShare}
          disabled={
            !status?.online ||
            sharing ||
            !preview?.anzahl_monate ||
            !selectedAnlage ||
            // Consent erforderlich beim ersten Teilen
            (!preview?.bereits_geteilt && !consentGiven)
          }
          className={`
            inline-flex items-center gap-2 px-6 py-3 rounded-lg text-lg font-medium
            ${status?.online && preview?.anzahl_monate && selectedAnlage && (preview?.bereits_geteilt || consentGiven)
              ? 'bg-orange-500 text-white hover:bg-orange-600'
              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
            }
          `}
        >
          {sharing ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              Wird geteilt...
            </>
          ) : preview?.bereits_geteilt ? (
            <>
              <RefreshCw className="h-5 w-5" />
              Daten aktualisieren
            </>
          ) : (
            <>
              <Send className="h-5 w-5" />
              Jetzt anonym teilen
            </>
          )}
        </button>
      </div>

      {!preview?.anzahl_monate && selectedAnlage && !loadingPreview && (
        <p className="text-center text-sm text-gray-500">
          Keine Monatsdaten vorhanden. Bitte zuerst Daten erfassen.
        </p>
      )}

      {/* Link zur Community */}
      <div className="text-center pt-4">
        <a
          href={preview?.community_url || 'https://energy.raunet.eu'}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-blue-600 hover:underline inline-flex items-center gap-1"
        >
          <ExternalLink className="h-4 w-4" />
          Community-Dashboard ansehen
        </a>
      </div>
    </div>
  )
}
