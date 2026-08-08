/**
 * DatenquellenHaPicker — HA-Sensor-Auswahl für die Datenquellen-Zuordnung (Schritt B).
 *
 * SoT: docs/KONZEPT-DATENQUELLEN-V4.md §2b1
 * + docs/drafts/archive/flip-v4/KONZEPT-DATENQUELLEN-P2.md (#343, gebaut).
 * Listet die Entities der aktiven HA-Verbindung (Supervisor ODER Remote-HA per
 * LL-Token — verbindungs-transparent über `/datenquellen/{id}/ha/sensoren`) mit
 * Suche; Klick wählt die Entity. Welche Quell-Kennung (`ha_app`/`ha_connector`)
 * persistiert wird, bestimmt der Server anhand der aktiven Verbindung.
 *
 * #343 (D2, 2026-07-18): (A) kuratierte Wissensbasis-Vorschläge über der Liste
 * („Integration erkannt: evcc") + Anti-Empfehlungen als amber Zeilen-Hinweis —
 * Assistenz, NIE Auto-Auswahl; (B) On-Demand-Takt-Check beim Wählen eines
 * kWh-Kandidaten (Session-Ende-Zähler → Warnung + „Trotzdem übernehmen").
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { Search, Loader2, Check, AlertTriangle, Lightbulb } from 'lucide-react'
import { Modal, Input, Button, Alert, Checkbox } from '../ui'
import { datenquellenApi, type HaSensor, type HaVorschlag } from '../../api/datenquellen'

interface Props {
  isOpen: boolean
  anlageId: number
  feldLabel: string
  /** Erwartete Feld-Einheit (§2i-Einheiten-Warnung beim Wählen). */
  feldEinheit?: string
  /** Feld-Key + Investitionstyp — aktivieren die Wissensbasis-Vorschläge (#343 A). */
  feldKey?: string
  invTyp?: string
  initialEntity: string | null
  onClose: () => void
  onSpeichern: (entityId: string) => void
}

// Dimensions-Klasse (Spiegel von core.field_definitions.einheit_klasse) — nur
// Leistung↔Energie, um die #200-Verwechslung beim Wählen sichtbar zu machen.
function einheitKlasse(unit: string | null | undefined): 'leistung' | 'energie' | null {
  if (unit === 'W' || unit === 'kW' || unit === 'MW') return 'leistung'
  if (unit === 'kWh' || unit === 'Wh' || unit === 'MWh') return 'energie'
  return null
}

export default function DatenquellenHaPicker({
  isOpen, anlageId, feldLabel, feldEinheit, feldKey, invTyp, initialEntity, onClose, onSpeichern,
}: Props) {
  const erwartet = einheitKlasse(feldEinheit)
  const [sensoren, setSensoren] = useState<HaSensor[]>([])
  const [vorschlaege, setVorschlaege] = useState<HaVorschlag[]>([])
  const [integrationen, setIntegrationen] = useState<string[]>([])
  const [warnungen, setWarnungen] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [fehler, setFehler] = useState<string | null>(null)
  const [suche, setSuche] = useState('')
  // fridolin22 (Forum v4.0.0): optionale Verengung der Liste auf Sensoren mit
  // passender Einheiten-Klasse. Default AUS — wer keinen geeigneten Sensor hat,
  // soll die vorhandenen sehen und daraus einen HA-Helper ableiten können.
  const [nurPassende, setNurPassende] = useState(false)
  // #343 B: Takt-Check-Zustand — pruefend (Spinner an der Zeile) bzw. eine
  // ausstehende Warnung mit „Trotzdem übernehmen"-Bestätigung.
  const [taktPrueft, setTaktPrueft] = useState<string | null>(null)
  const [taktWarnung, setTaktWarnung] = useState<{ entityId: string; text: string } | null>(null)

  useEffect(() => {
    if (!isOpen) return
    setLoading(true)
    setFehler(null)
    setTaktWarnung(null)
    datenquellenApi.haSensoren(anlageId, feldKey, invTyp)
      .then((r) => {
        if (r.fehler) setFehler(r.fehler)
        setSensoren(r.sensoren)
        setVorschlaege(r.vorschlaege ?? [])
        setIntegrationen(r.integrationen ?? [])
        setWarnungen(r.warnungen ?? {})
      })
      .catch((e) => setFehler(e instanceof Error ? e.message : 'Laden fehlgeschlagen'))
      .finally(() => setLoading(false))
  }, [isOpen, anlageId, feldKey, invTyp])

  /** Sensor mit bekannter, aber anderer Einheiten-Klasse als das Feld erwartet (§2i). */
  const istMismatch = useCallback((s: HaSensor) => {
    const k = einheitKlasse(s.unit)
    return erwartet != null && k != null && k !== erwartet
  }, [erwartet])

  const gesucht = useMemo(() => {
    const q = suche.trim().toLowerCase()
    if (!q) return sensoren
    return sensoren.filter((s) =>
      s.entity_id.toLowerCase().includes(q) || (s.friendly_name ?? '').toLowerCase().includes(q))
  }, [sensoren, suche])

  // Sensoren OHNE Einheit bleiben immer sichtbar — der Filter entfernt nur
  // nachweislich falsche Klassen (kWh-Sensor für ein W-Feld, #200). Die
  // v3.24.1-Aufweichung (Roh-Counter ohne state_class) bleibt damit erhalten.
  const ausgeblendet = useMemo(() => gesucht.filter(istMismatch).length, [gesucht, istMismatch])
  const gefiltert = useMemo(
    () => (nurPassende ? gesucht.filter((s) => !istMismatch(s)) : gesucht),
    [gesucht, nurPassende, istMismatch],
  )

  // #343 B: kWh-Felder → Takt-Check vor dem Speichern (nicht prüfbar = still
  // durchwinken, v3.23.8-Muster). W-/sonstige Felder speichern direkt.
  const waehle = useCallback((entityId: string) => {
    setTaktWarnung(null)
    if (erwartet !== 'energie') { onSpeichern(entityId); return }
    setTaktPrueft(entityId)
    datenquellenApi.taktCheck(anlageId, entityId)
      .then((r) => {
        if (r.geprueft && r.problem) setTaktWarnung({ entityId, text: r.problem.text })
        else onSpeichern(entityId)
      })
      .catch(() => onSpeichern(entityId))
      .finally(() => setTaktPrueft(null))
  }, [anlageId, erwartet, onSpeichern])

  const sensorZeile = (s: HaSensor) => {
    const aktiv = s.entity_id === initialEntity
    // §2i: Dimensions-Mismatch (kWh-Sensor für W-Feld etc.) beim Wählen.
    const mismatch = istMismatch(s)
    const antiEmpfehlung = warnungen[s.entity_id]
    return (
      <Button
        key={s.entity_id}
        type="button"
        variant="ghost"
        onClick={() => waehle(s.entity_id)}
        className="!w-full !justify-start !rounded-none"
      >
        {taktPrueft === s.entity_id
          ? <Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-gray-400" />
          : <Check className={`h-4 w-4 flex-shrink-0 ${aktiv ? 'text-green-600 dark:text-green-400' : 'text-transparent'}`} />}
        <span className="ml-2 min-w-0 flex-1 text-left">
          <span className="block truncate font-mono text-xs text-gray-800 dark:text-gray-200">{s.entity_id}</span>
          <span className="block truncate text-xs text-gray-500 dark:text-gray-400">
            {s.friendly_name ?? '—'}{s.unit ? ` · ${s.unit}` : ''}{s.state != null ? ` · ${s.state}` : ''}
          </span>
          {mismatch && (
            <span className="mt-0.5 flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
              <AlertTriangle className="h-3 w-3 shrink-0" />
              Einheit {s.unit} passt nicht zu {feldEinheit} ({erwartet === 'leistung' ? 'Leistungssensor erwartet' : 'kWh-Zähler erwartet'})
            </span>
          )}
          {antiEmpfehlung && (
            <span className="mt-0.5 flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
              <AlertTriangle className="h-3 w-3 shrink-0" />
              {antiEmpfehlung}
            </span>
          )}
        </span>
      </Button>
    )
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`HA-Sensor für „${feldLabel}"`} size="xl">
      <div className="space-y-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-gray-500" />
          <Input
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
            placeholder="Entity oder Name suchen …"
            className="pl-9"
            aria-label="HA-Sensor suchen"
          />
        </div>

        {/* Nur anbieten, wenn es überhaupt etwas zu verengen gibt. */}
        {!loading && erwartet != null && (ausgeblendet > 0 || nurPassende) && (
          <Checkbox
            name="nur-passende-einheit"
            checked={nurPassende}
            onChange={(e) => setNurPassende(e.target.checked)}
            label={`Nur passende Einheit (${erwartet === 'energie' ? 'kWh' : 'W'})`}
            hint={nurPassende
              ? `${ausgeblendet} Sensor(en) mit abweichender Einheit ausgeblendet`
              : `${ausgeblendet} Sensor(en) haben eine abweichende Einheit`}
          />
        )}

        {loading && (
          <p className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Sensoren werden geladen …
          </p>
        )}
        {fehler && <Alert type="error">{fehler}</Alert>}

        {/* #343 B: ausstehende Takt-Warnung — bestätigen oder anders wählen. */}
        {taktWarnung && (
          <Alert type="warning">
            <span className="block">{taktWarnung.text}</span>
            <span className="mt-2 flex gap-2">
              <Button type="button" variant="secondary" size="sm" onClick={() => { const e = taktWarnung.entityId; setTaktWarnung(null); onSpeichern(e) }}>
                Trotzdem übernehmen
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setTaktWarnung(null)}>
                Anderen wählen
              </Button>
            </span>
          </Alert>
        )}

        {/* #343 A: kuratierte Vorschläge — Assistenz über der Liste, nie Automatik. */}
        {!loading && vorschlaege.length > 0 && (
          <div className="rounded-lg border border-blue-200 bg-blue-50/50 dark:border-blue-800 dark:bg-blue-900/20">
            <p className="flex items-center gap-1.5 px-3 pt-2 text-xs font-medium text-blue-700 dark:text-blue-300">
              <Lightbulb className="h-3.5 w-3.5 shrink-0" />
              Vorschläge — Integration erkannt: {integrationen.join(', ')}
            </p>
            <div className="divide-y divide-blue-100 dark:divide-blue-900/40">
              {vorschlaege.map((v) => {
                const sensor = sensoren.find((s) => s.entity_id === v.entity_id)
                return (
                  <Button
                    key={`vorschlag-${v.entity_id}`}
                    type="button"
                    variant="ghost"
                    onClick={() => waehle(v.entity_id)}
                    className="!w-full !justify-start !rounded-none"
                  >
                    {taktPrueft === v.entity_id
                      ? <Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-gray-400" />
                      : <Check className={`h-4 w-4 flex-shrink-0 ${v.entity_id === initialEntity ? 'text-green-600 dark:text-green-400' : 'text-transparent'}`} />}
                    <span className="ml-2 min-w-0 flex-1 text-left">
                      <span className="block truncate font-mono text-xs text-gray-800 dark:text-gray-200">{v.entity_id}</span>
                      <span className="block text-xs text-blue-700 dark:text-blue-300">{v.hinweis}</span>
                      {sensor?.unit && (
                        <span className="block truncate text-xs text-gray-500 dark:text-gray-400">
                          {sensor.friendly_name ?? '—'} · {sensor.unit}{sensor.state != null ? ` · ${sensor.state}` : ''}
                        </span>
                      )}
                    </span>
                  </Button>
                )
              })}
            </div>
          </div>
        )}

        {!loading && !fehler && gefiltert.length === 0 && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {nurPassende && ausgeblendet > 0
              ? 'Kein Sensor mit passender Einheit. Haken entfernen, um alle zu sehen — oder in Home Assistant einen Helfer anlegen, der den Wert umrechnet.'
              : 'Keine passenden Sensoren gefunden.'}
          </p>
        )}

        {!loading && gefiltert.length > 0 && (
          <div className="max-h-96 divide-y divide-gray-100 overflow-y-auto rounded-lg border border-gray-200 dark:divide-gray-800 dark:border-gray-700">
            {gefiltert.map(sensorZeile)}
          </div>
        )}

        <div className="flex justify-end">
          <Button type="button" variant="secondary" onClick={onClose}>Abbrechen</Button>
        </div>
      </div>
    </Modal>
  )
}
