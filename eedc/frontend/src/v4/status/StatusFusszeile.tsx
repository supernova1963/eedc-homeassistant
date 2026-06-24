/**
 * StatusFusszeile — app-weite System-Statusleiste (G11 Shell-Slice, P1 + P2).
 *
 * SPEC: `docs/drafts/SPEC-STATUS-FUSSZEILE.md`. Dünne Zeile am unteren Shell-Rand
 * (3. Flex-Kind in `LayoutV4`), drei Zonen:
 *   - **global (links)**: installations-weite Indikatoren aus {@link useGlobalStatus} —
 *     Versions-Update · offener Monatsabschluss · MQTT-Verbindung (P2).
 *   - **sicht (rechts)**: Frische der gerade gezeigten Daten (Live-Punkt · „(5s)").
 *   - **meta (ganz rechts)**: Demo-Schalter (nur Debug).
 *
 * Severity zentral aus dem IST-Daten-Checker (`SEVERITY_CONFIG`/`CheckSchwere`,
 * `config/datenCheckerKategorien.ts`): info=blau · warning=amber · error=rot ·
 * ok=grün; „neutral" = grau (kein Zustand). Jedes Symbol: Icon + Tap-Popover
 * (Erläuterung + Detail + optional Deep-Link). Mobile: nur Symbole.
 */
import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Clock, Radio, ArrowUpCircle, CalendarClock, ListChecks, Database, type LucideIcon } from 'lucide-react'
import { SEVERITY_CONFIG, type CheckSchwere } from '../../config/datenCheckerKategorien'
import { useAppStatus } from './AppStatusContext'
import { useGlobalStatus } from './useGlobalStatus'

type Severity = CheckSchwere | 'neutral'

function farbeFuer(schwere: Severity): string {
  return schwere === 'neutral' ? 'text-gray-400 dark:text-gray-500' : SEVERITY_CONFIG[schwere].colorClass
}

/** Schlimmste vorhandene Severity einer Daten-Checker-Zusammenfassung. */
function schlimmsteSchwere(z: { error: number; warning: number; info: number }): CheckSchwere {
  if (z.error > 0) return 'error'
  if (z.warning > 0) return 'warning'
  if (z.info > 0) return 'info'
  return 'ok'
}

interface ItemProps {
  id: string
  icon: LucideIcon
  schwere: Severity
  /** Kurztitel (Popover-Kopf + aria-label). */
  label: string
  /** Detailtext im Popover. */
  detail?: string
  /** Inline-Wert rechts vom Icon — nur Desktop (Mobile = nur Symbol). */
  wert?: string
  /** Aktion hinter „Öffnen" (SPA-Navigate oder externer Link); fehlt = kein Link. */
  onOeffnen?: () => void
  ausrichtung?: 'links' | 'rechts'
  offen: string | null
  setOffen: (id: string | null) => void
}

function StatusItem({ id, icon: Icon, schwere, label, detail, wert, onOeffnen, ausrichtung = 'rechts', offen, setOffen }: ItemProps) {
  const isOpen = offen === id
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOffen(isOpen ? null : id)}
        aria-label={label}
        aria-expanded={isOpen}
        title={detail ? `${label} — ${detail}` : label}
        className="flex items-center gap-1 h-6 px-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
      >
        <Icon className={`h-3.5 w-3.5 ${farbeFuer(schwere)}`} />
        {wert && <span className="hidden sm:inline text-gray-600 dark:text-gray-300 tabular-nums">{wert}</span>}
      </button>
      {isOpen && (
        <div
          role="dialog"
          className={`absolute bottom-full mb-1 z-30 w-56 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg p-3 text-left ${
            ausrichtung === 'links' ? 'left-0' : 'right-0'
          }`}
        >
          <p className="text-xs font-semibold text-gray-900 dark:text-white">{label}</p>
          {detail && <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">{detail}</p>}
          {onOeffnen && (
            <button
              type="button"
              onClick={() => { setOffen(null); onOeffnen() }}
              className="mt-2 inline-block text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline"
            >
              Öffnen →
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export function StatusFusszeile() {
  const { status, demoMode, setDemoMode, isDebug } = useAppStatus()
  const { update, offenerMonat, mqtt, datencheck, anlageId } = useGlobalStatus()
  const navigate = useNavigate()
  const [offen, setOffen] = useState<string | null>(null)
  const ref = useRef<HTMLElement | null>(null)

  // Klick außerhalb schließt das offene Popover.
  useEffect(() => {
    if (!offen) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOffen(null)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [offen])

  const updateDa = !!update?.update_verfuegbar
  const mqttAktiv = !!mqtt?.subscriber_aktiv
  // Daten-Checker-Symbol nur bei echten Befunden (ruhe = nichts zeigen).
  const checkBefunde = datencheck ? datencheck.error + datencheck.warning + datencheck.info : 0

  return (
    <footer
      ref={ref}
      className="shrink-0 flex items-center justify-between gap-3 h-8 px-3 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 text-xs"
    >
      {/* Global-Zone (links) */}
      <div className="flex items-center gap-1 min-w-0">
        {datencheck && checkBefunde > 0 && (
          <StatusItem
            id="datencheck"
            icon={ListChecks}
            schwere={schlimmsteSchwere(datencheck)}
            label="Daten-Checker"
            detail={[
              datencheck.error > 0 ? `${datencheck.error} Fehler` : null,
              datencheck.warning > 0 ? `${datencheck.warning} ${datencheck.warning === 1 ? 'Warnung' : 'Warnungen'}` : null,
              datencheck.info > 0 ? `${datencheck.info} ${datencheck.info === 1 ? 'Hinweis' : 'Hinweise'}` : null,
            ].filter(Boolean).join(' · ')}
            wert={`${checkBefunde}`}
            onOeffnen={() => navigate('/einstellungen/daten-checker')}
            ausrichtung="links"
            offen={offen}
            setOffen={setOffen}
          />
        )}
        {updateDa && (
          <StatusItem
            id="update"
            icon={ArrowUpCircle}
            schwere="info"
            label={`eedc v${update!.neueste_version} verfügbar`}
            detail={`Aktuell installiert: v${update!.aktuelle_version}. Docker: docker-compose pull && up -d · HA: Add-on aktualisieren.`}
            wert={`v${update!.neueste_version}`}
            onOeffnen={update!.release_url ? () => window.open(update!.release_url, '_blank', 'noopener') : undefined}
            ausrichtung="links"
            offen={offen}
            setOffen={setOffen}
          />
        )}
        {offenerMonat && (
          <StatusItem
            id="monatsabschluss"
            icon={CalendarClock}
            schwere="warning"
            label="Monatsabschluss offen"
            detail={`${offenerMonat.monat_name} ${offenerMonat.jahr} ist noch nicht abgeschlossen.`}
            onOeffnen={anlageId ? () => navigate(`/monatsabschluss/${anlageId}`) : undefined}
            ausrichtung="links"
            offen={offen}
            setOffen={setOffen}
          />
        )}
        {mqttAktiv && (
          <StatusItem
            id="mqtt"
            icon={Radio}
            schwere="ok"
            label="MQTT-Inbound aktiv"
            detail={`Broker: ${mqtt!.broker ?? '—'} · Nachrichten: ${mqtt!.empfangene_nachrichten ?? 0}${
              mqtt!.letzte_nachricht ? ` · Letzte: ${new Date(mqtt!.letzte_nachricht).toLocaleTimeString('de-DE')}` : ''
            }`}
            wert={mqtt!.empfangene_nachrichten ? `MQTT (${mqtt!.empfangene_nachrichten})` : 'MQTT'}
            onOeffnen={() => navigate('/einstellungen/mqtt-inbound')}
            ausrichtung="links"
            offen={offen}
            setOffen={setOffen}
          />
        )}
      </div>

      {/* Sicht-Zone (rechts) + Meta */}
      <div className="flex items-center gap-2">
        {status.quelle && (
          <StatusItem
            id="quelle"
            icon={Database}
            schwere="neutral"
            label="Datenquelle"
            detail={`Die gezeigten Daten stammen aus: ${status.quelle}.`}
            wert={status.quelle}
            offen={offen}
            setOffen={setOffen}
          />
        )}
        {status.aktualisiertText && (
          <StatusItem
            id="frische"
            icon={Clock}
            schwere={status.live ? 'ok' : 'neutral'}
            label={status.live ? 'Live-Daten aktuell' : 'Daten-Stand'}
            detail={`Aktualisiert ${status.aktualisiertText}${status.intervallText ? ` · Intervall ${status.intervallText}` : ''}`}
            wert={`${status.aktualisiertText}${status.intervallText ? ` ${status.intervallText}` : ''}`}
            offen={offen}
            setOffen={setOffen}
          />
        )}

        {isDebug && (
          <button
            type="button"
            onClick={() => setDemoMode(!demoMode)}
            aria-pressed={demoMode}
            className={`h-6 px-2 rounded font-medium transition-colors ${
              demoMode
                ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            title="Demo-Daten (Dev-Affordance) global ein/aus"
          >
            {demoMode ? 'Demo an' : 'Demo'}
          </button>
        )}
      </div>
    </footer>
  )
}
