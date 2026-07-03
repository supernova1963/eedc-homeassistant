/**
 * Community-Share-Block (IA-V4 Einstellungen, A1 2026-07-02) — oberster Block unter
 * Stammdaten. Zwei Teile:
 *  - {@link CommunityTeilenSchalter}: der „teilen"-Schalter (`community_auto_share`)
 *    in der Block-Überschrift (BlockShell-`badge`-Slot).
 *  - {@link CommunityShareBlockInhalt}: Vorschau der anonym geteilten Daten inkl.
 *    Anzahl geteilter Datensätze (`anzahl_monate`); bei ausgeschaltetem Schalter
 *    abgeblendet (nicht ausgeblendet).
 *
 * Datenrolle strikt Community (nur `communityApi`), kein Bezug zu Investitionen.
 */
import { useEffect, useState } from 'react'
import { MapPin, Zap, Battery, Home, Car, Plug } from 'lucide-react'
import { useSelectedAnlage } from '../hooks'
import { anlagenApi } from '../api'
import { communityApi, type PreviewResponse } from '../api/community'
import { REGION_NAMEN } from '../lib/constants'
import { fmtZahl } from '../lib'

/** „teilen"-Schalter für die Block-Überschrift (community_auto_share). */
export function CommunityTeilenSchalter() {
  const { selectedAnlage, refresh } = useSelectedAnlage()
  const [saving, setSaving] = useState(false)
  if (!selectedAnlage) return null
  const an = selectedAnlage.community_auto_share ?? false
  const umschalten = async () => {
    setSaving(true)
    try {
      await anlagenApi.update(selectedAnlage.id, { community_auto_share: !an })
      await refresh()
    } finally {
      setSaving(false)
    }
  }
  return (
    <div className="flex items-center gap-2">
      {/* D14-4 (detLAN #113): Label großgeschrieben. */}
      <span className="hidden text-xs text-gray-500 dark:text-gray-400 sm:inline">Teilen</span>
      <button
        type="button"
        role="switch"
        aria-checked={an}
        aria-label="Anonyme Community-Daten teilen"
        disabled={saving}
        onClick={umschalten}
        className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
          an ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600'
        }`}
      >
        <span
          className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
            an ? 'translate-x-5' : 'translate-x-0.5'
          }`}
        />
      </button>
    </div>
  )
}

/** Vorschau der geteilten (anonymen) Daten + Anzahl Datensätze; abgeblendet, wenn aus. */
export function CommunityShareBlockInhalt() {
  const { selectedAnlage, selectedAnlageId } = useSelectedAnlage()
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [laden, setLaden] = useState(false)

  useEffect(() => {
    if (selectedAnlageId == null) { setPreview(null); return }
    let aktiv = true
    setLaden(true)
    communityApi.getPreview(selectedAnlageId)
      .then((p) => { if (aktiv) setPreview(p) })
      .catch(() => { if (aktiv) setPreview(null) })
      .finally(() => { if (aktiv) setLaden(false) })
    return () => { aktiv = false }
  }, [selectedAnlageId])

  if (selectedAnlageId == null) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Anlage ausgewählt.</p>
  }

  const teiltAuto = selectedAnlage?.community_auto_share ?? false
  const v = preview?.vorschau
  const region = v ? (REGION_NAMEN[v.region] || v.region) : null

  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Anonyme Kennzahlen deiner Anlage im Community-Benchmark. Es werden ausschließlich die
        unten gezeigten, nicht-personenbezogenen Daten geteilt — keine Adresse, kein Name.
      </p>

      <div className={teiltAuto ? '' : 'pointer-events-none select-none opacity-40'} aria-hidden={!teiltAuto}>
        {laden && !preview ? (
          <p className="text-sm text-gray-400 dark:text-gray-500">Lade Vorschau …</p>
        ) : v ? (
          <div className="space-y-3">
            {/* Anlagendaten */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="flex items-center gap-2">
                <MapPin className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Region</p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{region}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-yellow-500" />
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Leistung</p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{fmtZahl(v.kwp, 1)} kWp</p>
                </div>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Ausrichtung</p>
                <p className="text-sm font-medium capitalize text-gray-900 dark:text-white">{v.ausrichtung}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Neigung</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">{v.neigung_grad}°</p>
              </div>
            </div>

            {/* Ausstattung */}
            {(v.speicher_kwh || v.hat_waermepumpe || v.hat_eauto || v.hat_wallbox) && (
              <div className="flex flex-wrap gap-2">
                {v.speicher_kwh ? (
                  <span className="inline-flex items-center gap-1 rounded bg-green-100 px-2 py-1 text-sm text-green-700 dark:bg-green-900/30 dark:text-green-300">
                    <Battery className="h-4 w-4" />
                    Speicher ({fmtZahl(v.speicher_kwh, 1)} kWh)
                  </span>
                ) : null}
                {v.hat_waermepumpe && (
                  <span className="inline-flex items-center gap-1 rounded bg-blue-100 px-2 py-1 text-sm text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                    <Home className="h-4 w-4" />
                    Wärmepumpe
                  </span>
                )}
                {v.hat_eauto && (
                  <span className="inline-flex items-center gap-1 rounded bg-purple-100 px-2 py-1 text-sm text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
                    <Car className="h-4 w-4" />
                    E-Auto
                  </span>
                )}
                {v.hat_wallbox && (
                  <span className="inline-flex items-center gap-1 rounded bg-gray-100 px-2 py-1 text-sm text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                    <Plug className="h-4 w-4" />
                    Wallbox
                  </span>
                )}
              </div>
            )}

            {/* Anzahl geteilter Datensätze */}
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {preview?.anzahl_monate
                ? `${fmtZahl(preview.anzahl_monate, 0)} Monatswerte werden geteilt.`
                : 'Noch keine Monatswerte zum Teilen vorhanden.'}
            </p>
          </div>
        ) : (
          <p className="text-sm text-gray-400 dark:text-gray-500">Keine Vorschau verfügbar.</p>
        )}
      </div>

      {!teiltAuto && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Teilen ist ausgeschaltet — aktiviere den Schalter „Teilen" oben in der Block-Überschrift.
        </p>
      )}
    </div>
  )
}
