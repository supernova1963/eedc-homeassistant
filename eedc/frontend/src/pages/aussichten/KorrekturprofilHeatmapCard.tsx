/**
 * Korrekturprofil-Heatmap — Diagnose-Card für den Prognosen-Tab.
 *
 * Zeigt das mehrdimensionale Korrekturprofil pro Anlage als Heatmap
 * (Azimut × Elevation, eine Kachel pro Sonnenstand-Bin). Pro Wetterklasse
 * (klar / diffus / wechselhaft) wählbar; zusätzlich „Alle" als Fallback-
 * Sicht über die `sonnenstand`-Stufe.
 *
 * Empty-State, wenn noch nie aggregiert: Button stößt eine Aggregation an.
 *
 * Strikt eedc-intern (kein Quellen-Vergleich, siehe Tom-HA-Versprechen).
 */
import { useEffect, useMemo, useState } from 'react'
import { Sigma, RefreshCw } from 'lucide-react'
import { Card } from '../../components/ui'
import {
  aggregateKorrekturprofil,
  getProfile,
  ProfilEintrag,
  Wetterklasse,
} from '../../api/korrekturprofil'

interface Props {
  anlageId: number
}

type Sicht = Wetterklasse | 'alle'

const KLASSEN: { key: Sicht; label: string }[] = [
  { key: 'klar', label: 'Klar' },
  { key: 'diffus', label: 'Diffus' },
  { key: 'wechselhaft', label: 'Wechselhaft' },
  { key: 'alle', label: 'Alle (Fallback)' },
]

// Sichtbare Bin-Range — Tageslicht-relevant
const AZIMUT_MIN = 60
const AZIMUT_MAX = 290
const ELEVATION_MIN = 0
const ELEVATION_MAX = 80
const STEP = 10

function faktorFarbe(f: number | null): string {
  if (f == null) return 'transparent'
  // 0.5 (rot) → 1.0 (neutral grau) → 1.3 (grün)
  // Lineare Interpolation per Side
  if (f < 1.0) {
    const t = Math.max(0, Math.min(1, (f - 0.5) / 0.5)) // 0 bei 0.5, 1 bei 1.0
    const r = 220
    const g = Math.round(80 + 140 * t)
    const b = Math.round(80 + 80 * t)
    return `rgb(${r}, ${g}, ${b})`
  }
  const t = Math.max(0, Math.min(1, (f - 1.0) / 0.3))
  const r = Math.round(220 - 100 * t)
  const g = Math.round(220 - 30 * t)
  const b = Math.round(160 - 60 * t)
  return `rgb(${r}, ${g}, ${b})`
}

function formatDatum(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString('de-DE', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function KorrekturprofilHeatmapCard({ anlageId }: Props) {
  const [profile, setProfile] = useState<ProfilEintrag[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [aggregating, setAggregating] = useState(false)
  const [aggregateMsg, setAggregateMsg] = useState<string | null>(null)
  const [aggregateError, setAggregateError] = useState<string | null>(null)
  const [sicht, setSicht] = useState<Sicht>('klar')

  const reload = async () => {
    setLoading(true)
    try {
      const res = await getProfile(anlageId)
      setProfile(res.profile)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getProfile(anlageId).then(res => {
      if (!cancelled) setProfile(res.profile)
    }).catch(() => {
      if (!cancelled) setProfile([])
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [anlageId])

  const handleAggregate = async () => {
    setAggregating(true)
    setAggregateMsg(null)
    setAggregateError(null)
    try {
      const res = await aggregateKorrekturprofil(anlageId)
      if (res.status === 'ok') {
        setAggregateMsg(
          `${res.tage_eingegangen ?? 0} Tage, ` +
          `${res.bins_sonnenstand_wetter ?? 0} Bins (mit Wetter), ` +
          `${res.bins_sonnenstand ?? 0} Bins (Sonnenstand), ` +
          `Skalar ${res.skalar?.toFixed(3) ?? '—'}`
        )
        await reload()
      } else {
        setAggregateError(res.grund ?? 'Aggregator übersprungen')
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setAggregateError(msg)
    } finally {
      setAggregating(false)
    }
  }

  const sw = profile?.find(p => p.profil_typ === 'sonnenstand_wetter')
  const son = profile?.find(p => p.profil_typ === 'sonnenstand')
  const skalar = profile?.find(p => p.profil_typ === 'skalar')

  // Heatmap-Daten für aktive Sicht aufbauen
  const heat = useMemo(() => {
    type Cell = { faktor: number | null; n: number }
    const matrix: Record<number, Record<number, Cell>> = {}
    if (sicht === 'alle') {
      const f = (son?.faktoren as Record<string, number>) ?? {}
      const n = (son?.datenpunkte_pro_bin as Record<string, number>) ?? {}
      for (const key of Object.keys(f)) {
        const m = key.match(/^(\d+)_(\d+)$/)
        if (!m) continue
        const az = Number(m[1]), el = Number(m[2])
        matrix[el] ??= {}
        matrix[el][az] = { faktor: f[key], n: n[key] ?? 0 }
      }
    } else {
      const f = (sw?.faktoren as Record<string, number>) ?? {}
      const n = (sw?.datenpunkte_pro_bin as Record<string, number>) ?? {}
      const suffix = `_${sicht}`
      for (const key of Object.keys(f)) {
        if (!key.endsWith(suffix)) continue
        const m = key.replace(suffix, '').match(/^(\d+)_(\d+)$/)
        if (!m) continue
        const az = Number(m[1]), el = Number(m[2])
        matrix[el] ??= {}
        matrix[el][az] = { faktor: f[key], n: n[key] ?? 0 }
      }
    }
    return matrix
  }, [sicht, sw, son])

  const azimute: number[] = []
  for (let a = AZIMUT_MIN; a <= AZIMUT_MAX; a += STEP) azimute.push(a)
  const elevationen: number[] = []
  for (let e = ELEVATION_MAX; e >= ELEVATION_MIN; e -= STEP) elevationen.push(e)

  const isEmpty = !loading && (!profile || profile.length === 0)
  const swFaktoren = (sw?.faktoren as Record<string, number>) ?? {}
  const sFaktoren = (son?.faktoren as Record<string, number>) ?? {}
  const hatBins = Object.keys(swFaktoren).length > 0 || Object.keys(sFaktoren).length > 0
  const nurSkalar = !loading && !isEmpty && !hatBins && skalar?.faktor_skalar != null

  return (
    <Card>
      <div className="flex items-start justify-between mb-2">
        <h3 className="text-base font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Sigma className="h-4 w-4 text-orange-500" />
          Korrekturprofil — Sonnenstand × Wetter
        </h3>
        <button
          type="button"
          onClick={handleAggregate}
          disabled={aggregating}
          className="flex items-center gap-1 px-2 py-1 text-xs font-medium bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-white rounded transition-colors"
          title="Profile aus Day-Ahead-Snapshots + Wetter-Historie neu berechnen"
        >
          <RefreshCw className={`h-3 w-3 ${aggregating ? 'animate-spin' : ''}`} />
          {aggregating ? 'Aggregiert…' : 'Neu aggregieren'}
        </button>
      </div>

      <div className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        Pro Sonnenstand-Bin (10° Azimut × 10° Elevation) und Wetterklasse der
        Korrekturfaktor IST/Prognose. Live-Lookup nutzt die Fallback-Kaskade
        sonnenstand × wetter → sonnenstand → Skalar. Datenbasis:
        Day-Ahead-Snapshots + stündliche Wetter-Historie.
      </div>

      {loading && (
        <div className="text-xs text-gray-400">Lädt Profile…</div>
      )}

      {isEmpty && !loading && (
        <div className="text-xs text-gray-500">
          Noch kein Korrekturprofil aggregiert. Sobald die Beobachtungs-Phase
          genug Tage gesammelt hat, läuft der Scheduler nightly. Du kannst
          oben „Neu aggregieren" anstoßen, um den ersten Lauf manuell zu
          starten.
        </div>
      )}

      {nurSkalar && (
        <div className="text-xs text-gray-500 mb-3 p-2 rounded bg-blue-50 dark:bg-blue-900/20">
          Skalar-Faktor (×{skalar?.faktor_skalar?.toFixed(3)}) ist aktiv und
          wirkt im Live-Pfad. Sonnenstand- und Wetter-Bins brauchen
          Day-Ahead-Stundenprofile (`pv_prognose_stundenprofil`), die seit
          v3.26.0 täglich gesammelt werden — die Heatmap-Tabelle füllt sich
          ab Tag 10 organisch und wird über mehrere Wochen statistisch robust.
        </div>
      )}

      {!loading && !isEmpty && (
        <>
          {/* Klassen-Tabs */}
          <div className="flex gap-1 mb-3 border-b border-gray-200 dark:border-gray-700">
            {KLASSEN.map(k => (
              <button
                key={k.key}
                type="button"
                onClick={() => setSicht(k.key)}
                className={`px-3 py-1 text-xs font-medium border-b-2 -mb-px transition-colors ${
                  sicht === k.key
                    ? 'border-orange-500 text-orange-600 dark:text-orange-400'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                }`}
              >
                {k.label}
              </button>
            ))}
          </div>

          {/* Heatmap */}
          <div className="overflow-x-auto">
            <table className="text-[10px] border-collapse">
              <thead>
                <tr>
                  <th className="text-right pr-1 font-medium text-gray-400 sticky left-0 bg-white dark:bg-gray-900">
                    Elev↓ \ Az→
                  </th>
                  {azimute.map(az => (
                    <th key={az} className="px-0.5 py-0.5 font-normal text-gray-400 text-center" style={{ minWidth: 22 }}>
                      {az}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {elevationen.map(el => (
                  <tr key={el}>
                    <td className="text-right pr-1 text-gray-400 font-mono sticky left-0 bg-white dark:bg-gray-900">
                      {el}°
                    </td>
                    {azimute.map(az => {
                      const cell = heat[el]?.[az]
                      const f = cell?.faktor ?? null
                      const n = cell?.n ?? 0
                      const bg = faktorFarbe(f)
                      return (
                        <td
                          key={az}
                          className="text-center align-middle font-mono text-[9px]"
                          style={{
                            backgroundColor: bg,
                            color: f != null ? 'rgba(0,0,0,0.78)' : 'transparent',
                            minWidth: 22,
                            height: 18,
                            border: '1px solid rgba(255,255,255,0.4)',
                          }}
                          title={
                            f != null
                              ? `Az ${az}-${az + STEP}°, El ${el}-${el + STEP}°: ×${f.toFixed(2)} (n=${n})`
                              : ''
                          }
                        >
                          {f != null ? f.toFixed(2) : ''}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Legende */}
          <div className="flex items-center gap-2 mt-2 text-[10px] text-gray-500">
            <span>0.5</span>
            <div
              className="h-2 flex-1 rounded"
              style={{
                background:
                  'linear-gradient(to right, rgb(220,80,80) 0%, rgb(220,220,160) 50%, rgb(120,190,100) 100%)',
              }}
            />
            <span>1.3</span>
          </div>

          {/* Stats */}
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] text-gray-600 dark:text-gray-400">
            <div>
              <div className="text-gray-400">Tage eingegangen</div>
              <div className="font-mono">{sw?.tage_eingegangen ?? 0}</div>
            </div>
            <div>
              <div className="text-gray-400">Bins (×Wetter)</div>
              <div className="font-mono">{Object.keys(sw?.faktoren ?? {}).length}</div>
            </div>
            <div>
              <div className="text-gray-400">Bins (Sonnenstand)</div>
              <div className="font-mono">{Object.keys(son?.faktoren ?? {}).length}</div>
            </div>
            <div>
              <div className="text-gray-400">Skalar (Fallback)</div>
              <div className="font-mono">
                {skalar?.faktor_skalar != null ? skalar.faktor_skalar.toFixed(3) : '—'}
              </div>
            </div>
          </div>

          <div className="mt-2 text-[10px] text-gray-400">
            Aktualisiert: {formatDatum(sw?.aktualisiert_am ?? son?.aktualisiert_am ?? skalar?.aktualisiert_am)}
          </div>
        </>
      )}

      {aggregateMsg && (
        <div className="mt-3 text-xs text-green-700 dark:text-green-400">
          ✓ {aggregateMsg}
        </div>
      )}
      {aggregateError && (
        <div className="mt-3 text-xs text-red-600 dark:text-red-400">
          Fehler: {aggregateError}
        </div>
      )}
    </Card>
  )
}
