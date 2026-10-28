/**
 * DatenquellenPresetDialog — «Preset anwenden…» in der Datenquellen-Fläche (P-433-2b K4, K4-7/K4-8).
 *
 * Seit `7e9e95fb` (13.08.2026, `live/MqttGateway.tsx` entfernt) hatten die Geräte-Presets keine Oberfläche mehr; das
 * evcc-Preset (K2b) ging nur per API. Der Dialog legt die Gateway-Zeilen eines Presets an — **nur anlegen**, das
 * Bearbeiten einer Zeile bleibt der Gateway-Picker (`DatenquellenGatewayPicker`).
 *
 * Ablauf: Liste (Name · Hersteller · Beschreibung · Anleitung) → Variablen (Vorbelegung = `vorgabe`) → Vorschau der
 * Zeilen (Topic → Beschreibung der Zeile) → «Anwenden» (`liveDashboardApi.applyGatewayPreset`). Das Backend
 * **ersetzt** vorhandene Gateway-Zeilen derselben Felder und setzt die Quelle auf «Gateway» (D-K4-1); der Dialog sagt
 * das vorher. Welche Presets an welchem Gerät stehen, sagt das Backend (`MqttPreset.typen`), keine zweite Tabelle.
 */
import { useMemo, useState } from 'react'
import { Modal, Input, Button, Alert } from '../ui'
import { liveDashboardApi } from '../../api/liveDashboard'
import type { MqttPreset, PresetApplyResponse } from '../../api/liveDashboard'

/** Hinweis vor dem Anwenden (D-K4-1). */
export const ERSETZEN_HINWEIS = 'Vorhandene Gateway-Zuordnungen derselben Felder werden ersetzt; die Felder stehen danach auf «Gateway».'

/** Die Presets, die an einem Gerät dieses Typs angeboten werden (Backend-Feld `typen`). */
export function presetsFuerTyp(presets: MqttPreset[], typ: string): MqttPreset[] {
  return presets.filter((p) => p.erfordert_investition && (p.typen ?? []).includes(typ))
}

/** Die Presets an der Anlage (Basis-Block): ohne Investitions-Bezug. */
export function presetsFuerAnlage(presets: MqttPreset[]): MqttPreset[] {
  return presets.filter((p) => !p.erfordert_investition)
}

/** Ein Topic-Template mit den Variablen (leere Variable ⇒ Vorgabe) — Anzeige der Vorschau, keine Rechnung. */
export function topicVorschau(template: string, preset: MqttPreset, werte: Record<string, string>): string {
  return preset.variablen.reduce((t, v) => {
    const wert = (werte[v.key] ?? '').trim() || v.vorgabe || `{${v.key}}`
    return t.split(`{${v.key}}`).join(wert)
  }, template)
}

interface Props {
  isOpen: boolean
  anlageId: number
  /** Gerät, an dem angewendet wird; `null` an der Anlage. */
  investitionId: number | null
  titel: string
  presets: MqttPreset[]
  onClose: () => void
  onAngewendet: (r: PresetApplyResponse) => void
}

export default function DatenquellenPresetDialog({
  isOpen, anlageId, investitionId, titel, presets, onClose, onAngewendet,
}: Props) {
  const [gewaehlt, setGewaehlt] = useState<MqttPreset | null>(presets.length === 1 ? presets[0] : null)
  const [werte, setWerte] = useState<Record<string, string>>({})
  const [laeuft, setLaeuft] = useState(false)
  const [fehler, setFehler] = useState<string | null>(null)

  const fehlt = useMemo(
    () => (gewaehlt?.variablen ?? []).some((v) => !(werte[v.key] ?? '').trim() && !v.vorgabe),
    [gewaehlt, werte],
  )

  const waehle = (p: MqttPreset) => {
    setGewaehlt(p)
    setWerte({})
    setFehler(null)
  }

  const anwenden = () => {
    if (!gewaehlt) return
    setLaeuft(true)
    setFehler(null)
    liveDashboardApi.applyGatewayPreset({
      preset_id: gewaehlt.id, anlage_id: anlageId, variablen: werte,
      ...(investitionId != null ? { investition_id: investitionId } : {}),
    })
      .then((r) => onAngewendet(r))
      .catch((e) => setFehler(e instanceof Error ? e.message : 'Anwenden fehlgeschlagen'))
      .finally(() => setLaeuft(false))
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Preset anwenden — ${titel}`} size="lg">
      <div className="space-y-4" data-preset-dialog>
        <ul className="space-y-1" data-preset-liste>
          {presets.map((p) => (
            <li key={p.id}>
              <Button
                type="button"
                variant={gewaehlt?.id === p.id ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => waehle(p)}
                aria-pressed={gewaehlt?.id === p.id}
                data-preset={p.id}
                className="w-full !justify-start text-left"
              >
                <span>
                  <span className="font-medium">{p.name}</span>
                  <span className="text-gray-500 dark:text-gray-400"> · {p.hersteller}</span>
                  <span className="block text-xs font-normal text-gray-500 dark:text-gray-400">{p.beschreibung}</span>
                </span>
              </Button>
            </li>
          ))}
        </ul>

        {gewaehlt && (
          <div className="space-y-3">
            {gewaehlt.anleitung && <p className="text-xs text-gray-600 dark:text-gray-300" data-preset-anleitung>{gewaehlt.anleitung}</p>}
            {gewaehlt.variablen.map((v) => (
              <Input
                key={v.key}
                label={v.label}
                placeholder={v.vorgabe || v.placeholder}
                hint={v.hinweis || undefined}
                value={werte[v.key] ?? ''}
                onChange={(e) => setWerte((w) => ({ ...w, [v.key]: e.target.value }))}
                data-preset-variable={v.key}
              />
            ))}
            <div className="text-xs space-y-0.5" data-preset-vorschau>
              {gewaehlt.mappings.map((m) => (
                <div key={m.ziel_key} className="flex flex-wrap gap-x-2">
                  <code className="text-gray-700 dark:text-gray-300 break-all">{topicVorschau(m.topic_template, gewaehlt, werte)}</code>
                  <span className="text-gray-500 dark:text-gray-400">→ {m.beschreibung}</span>
                </div>
              ))}
            </div>
            <Alert type="info">{ERSETZEN_HINWEIS}</Alert>
            {fehler && <Alert type="error">{fehler}</Alert>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="secondary" onClick={onClose}>Abbrechen</Button>
              <Button type="button" onClick={anwenden} loading={laeuft} disabled={fehlt || laeuft} data-preset-anwenden>
                Anwenden
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}
