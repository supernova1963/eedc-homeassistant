/**
 * MQTT Gateway — Topic-Mapping-Verwaltung.
 *
 * Wird als Abschnitt in die MQTT-Inbound-Einrichtungsseite eingebettet.
 * Ermöglicht das Anlegen, Bearbeiten und Löschen von Topic-Mappings
 * sowie das Testen von Topics und Payload-Transformationen.
 */

import { useState, useEffect, useCallback } from 'react'
import { Plus, Trash2, Edit3, Play, Check, ChevronDown, ChevronRight, ToggleLeft, ToggleRight, Loader2, Radio, AlertCircle } from 'lucide-react'
import Input from '../ui/Input'
import { liveDashboardApi } from '../../api/liveDashboard'
import type { GatewayMapping, GatewayMappingCreate, GatewayStatus, TestTopicResult } from '../../api/liveDashboard'

interface MqttGatewayProps {
  anlageId: number | null
  mqttAktiv: boolean  // Ist MQTT-Inbound überhaupt aktiv?
}

// ─── Ziel-Key Optionen ──────────────────────────────────────────────

const ZIEL_KEY_OPTIONS = [
  { value: 'live/pv_gesamt_w', label: 'PV Gesamt (W)', gruppe: 'Live' },
  { value: 'live/einspeisung_w', label: 'Einspeisung (W)', gruppe: 'Live' },
  { value: 'live/netzbezug_w', label: 'Netzbezug (W)', gruppe: 'Live' },
  { value: 'live/haushalt_w', label: 'Haushalt (W)', gruppe: 'Live' },
]

// ─── Mapping-Formular ───────────────────────────────────────────────

interface MappingFormData {
  quell_topic: string
  ziel_key: string
  ziel_key_custom: string  // Für benutzerdefinierte Ziel-Keys (z.B. live/inv/3/leistung_w)
  payload_typ: string
  json_pfad: string
  array_index: string
  faktor: string
  offset: string
  invertieren: boolean
  beschreibung: string
}

const EMPTY_FORM: MappingFormData = {
  quell_topic: '',
  ziel_key: 'live/einspeisung_w',
  ziel_key_custom: '',
  payload_typ: 'plain',
  json_pfad: '',
  array_index: '',
  faktor: '1',
  offset: '0',
  invertieren: false,
  beschreibung: '',
}

function MappingForm({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial: MappingFormData
  onSave: (data: MappingFormData) => void
  onCancel: () => void
  saving: boolean
}) {
  const [form, setForm] = useState<MappingFormData>(initial)
  const [showAdvanced, setShowAdvanced] = useState(
    initial.faktor !== '1' || initial.offset !== '0' || initial.invertieren
  )
  const [testResult, setTestResult] = useState<TestTopicResult | null>(null)
  const [testing, setTesting] = useState(false)

  const isCustomZiel = !ZIEL_KEY_OPTIONS.some(o => o.value === form.ziel_key) && form.ziel_key !== '__custom__'
  const effectiveZielKey = form.ziel_key === '__custom__' || isCustomZiel
    ? form.ziel_key_custom || form.ziel_key
    : form.ziel_key

  const handleTestTopic = async () => {
    if (!form.quell_topic) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await liveDashboardApi.testGatewayTopic(form.quell_topic, 10)
      setTestResult(result)
      // Auto-detect payload_typ
      if (result.empfangen && result.payload_typ_erkannt) {
        setForm(prev => ({ ...prev, payload_typ: result.payload_typ_erkannt! }))
      }
    } catch {
      setTestResult({ empfangen: false, fehler: 'Verbindungsfehler' })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="space-y-3">
      {/* Quell-Topic */}
      <div className="flex gap-2">
        <div className="flex-1">
          <Input
            label="Quell-Topic"
            value={form.quell_topic}
            onChange={e => setForm({ ...form, quell_topic: e.target.value })}
            placeholder="z.B. shellies/em3/emeter/0/power"
            required
          />
        </div>
        <div className="flex items-end">
          <button
            onClick={handleTestTopic}
            disabled={!form.quell_topic || testing}
            className="flex items-center gap-1 px-3 py-2 text-sm rounded-lg bg-blue-50 text-blue-600 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-400 dark:hover:bg-blue-900/50 disabled:opacity-50"
          >
            {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            Testen
          </button>
        </div>
      </div>

      {/* Test-Ergebnis */}
      {testResult && (
        <div className={`text-xs p-2 rounded-lg ${testResult.empfangen
          ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
          : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
        }`}>
          {testResult.empfangen ? (
            <>
              <span className="font-medium">Empfangen</span> ({testResult.wartezeit_s}s) —
              Typ: <span className="font-mono">{testResult.payload_typ_erkannt}</span>
              {testResult.wert !== null && testResult.wert !== undefined && (
                <> — Wert: <span className="font-mono font-bold">{testResult.wert}</span></>
              )}
              {testResult.payload_raw && (
                <pre className="mt-1 text-[10px] bg-white/50 dark:bg-black/20 p-1 rounded overflow-x-auto max-h-16">
                  {testResult.payload_raw.slice(0, 500)}
                </pre>
              )}
            </>
          ) : (
            <>{testResult.fehler}</>
          )}
        </div>
      )}

      {/* Payload-Typ */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Payload-Typ</label>
        <div className="flex gap-2">
          {(['plain', 'json', 'json_array'] as const).map(typ => (
            <button
              key={typ}
              onClick={() => setForm({ ...form, payload_typ: typ })}
              className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                form.payload_typ === typ
                  ? 'border-primary-500 bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-400 dark:border-primary-600'
                  : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              {typ === 'plain' ? 'Zahl' : typ === 'json' ? 'JSON-Pfad' : 'JSON-Array'}
            </button>
          ))}
        </div>
      </div>

      {/* JSON-Pfad / Array-Index */}
      {form.payload_typ === 'json' && (
        <Input
          label="JSON-Pfad"
          value={form.json_pfad}
          onChange={e => setForm({ ...form, json_pfad: e.target.value })}
          placeholder="z.B. power oder Body.Data.Site.P_PV"
          hint="Punkt-Notation für verschachtelte Objekte"
        />
      )}
      {form.payload_typ === 'json_array' && (
        <Input
          label="Array-Index"
          type="number"
          value={form.array_index}
          onChange={e => setForm({ ...form, array_index: e.target.value })}
          placeholder="z.B. 11"
          hint="0-basierter Index im JSON-Array"
        />
      )}

      {/* Ziel-Key */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Ziel-Feld <span className="text-red-500">*</span>
        </label>
        <select
          value={isCustomZiel ? '__custom__' : form.ziel_key}
          onChange={e => {
            const val = e.target.value
            if (val === '__custom__') {
              setForm({ ...form, ziel_key: '__custom__', ziel_key_custom: '' })
            } else {
              setForm({ ...form, ziel_key: val, ziel_key_custom: '' })
            }
          }}
          className="w-full text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-2"
        >
          {ZIEL_KEY_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
          <option value="__custom__">Benutzerdefiniert...</option>
        </select>
        {(form.ziel_key === '__custom__' || isCustomZiel) && (
          <Input
            className="mt-2"
            value={form.ziel_key_custom}
            onChange={e => setForm({ ...form, ziel_key_custom: e.target.value })}
            placeholder="z.B. live/inv/3/leistung_w"
            hint="EEDC-Topic-Suffix (ohne eedc/{id}/ Prefix)"
          />
        )}
      </div>

      {/* Erweiterte Optionen */}
      <button
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
      >
        {showAdvanced ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        Erweitert (Faktor, Offset, Invertierung)
      </button>

      {showAdvanced && (
        <div className="grid grid-cols-3 gap-2">
          <Input
            label="Faktor"
            type="number"
            step="any"
            value={form.faktor}
            onChange={e => setForm({ ...form, faktor: e.target.value })}
            hint="z.B. 1000 für kW→W"
          />
          <Input
            label="Offset"
            type="number"
            step="any"
            value={form.offset}
            onChange={e => setForm({ ...form, offset: e.target.value })}
            hint="Addiert nach Faktor"
          />
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Invertieren</label>
            <button
              onClick={() => setForm({ ...form, invertieren: !form.invertieren })}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm ${
                form.invertieren
                  ? 'border-amber-400 bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                  : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400'
              }`}
            >
              {form.invertieren ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
              {form.invertieren ? '×(−1)' : 'Nein'}
            </button>
          </div>
        </div>
      )}

      {/* Beschreibung */}
      <Input
        label="Beschreibung"
        value={form.beschreibung}
        onChange={e => setForm({ ...form, beschreibung: e.target.value })}
        placeholder="z.B. Shelly 3EM Phase 1"
      />

      {/* Buttons */}
      <div className="flex gap-2 justify-end">
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700"
        >
          Abbrechen
        </button>
        <button
          onClick={() => onSave({ ...form, ziel_key: effectiveZielKey })}
          disabled={saving || !form.quell_topic || !effectiveZielKey}
          className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
        >
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
          Speichern
        </button>
      </div>
    </div>
  )
}

// ─── Hauptkomponente ─────────────────────────────────────────────────

export default function MqttGateway({ anlageId, mqttAktiv }: MqttGatewayProps) {
  const [mappings, setMappings] = useState<GatewayMapping[]>([])
  const [status, setStatus] = useState<GatewayStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState<number | null>(null)

  const loadData = useCallback(async () => {
    try {
      const [m, s] = await Promise.all([
        liveDashboardApi.getGatewayMappings(anlageId ?? undefined),
        liveDashboardApi.getGatewayStatus(),
      ])
      setMappings(m)
      setStatus(s)
    } catch {
      // Ignorieren wenn Gateway noch nicht verfügbar
    } finally {
      setLoading(false)
    }
  }, [anlageId])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleSave = async (form: MappingFormData) => {
    if (!anlageId) return
    setSaving(true)
    try {
      const data: GatewayMappingCreate = {
        anlage_id: anlageId,
        quell_topic: form.quell_topic,
        ziel_key: form.ziel_key,
        payload_typ: form.payload_typ,
        json_pfad: form.payload_typ === 'json' ? form.json_pfad || null : null,
        array_index: form.payload_typ === 'json_array' && form.array_index ? Number(form.array_index) : null,
        faktor: Number(form.faktor) || 1,
        offset: Number(form.offset) || 0,
        invertieren: form.invertieren,
        beschreibung: form.beschreibung || null,
      }

      if (editId !== null) {
        await liveDashboardApi.updateGatewayMapping(editId, data)
      } else {
        await liveDashboardApi.createGatewayMapping(data)
      }

      setShowForm(false)
      setEditId(null)
      await loadData()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Fehler beim Speichern')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Mapping wirklich löschen?')) return
    setDeleting(id)
    try {
      await liveDashboardApi.deleteGatewayMapping(id)
      await loadData()
    } catch {
      alert('Fehler beim Löschen')
    } finally {
      setDeleting(null)
    }
  }

  const handleToggle = async (m: GatewayMapping) => {
    try {
      await liveDashboardApi.updateGatewayMapping(m.id, { aktiv: !m.aktiv })
      await loadData()
    } catch {
      alert('Fehler beim Umschalten')
    }
  }

  const startEdit = (m: GatewayMapping) => {
    setEditId(m.id)
    setShowForm(true)
  }

  const getEditFormData = (): MappingFormData => {
    if (editId === null) return EMPTY_FORM
    const m = mappings.find(x => x.id === editId)
    if (!m) return EMPTY_FORM
    const isStandard = ZIEL_KEY_OPTIONS.some(o => o.value === m.ziel_key)
    return {
      quell_topic: m.quell_topic,
      ziel_key: isStandard ? m.ziel_key : '__custom__',
      ziel_key_custom: isStandard ? '' : m.ziel_key,
      payload_typ: m.payload_typ,
      json_pfad: m.json_pfad || '',
      array_index: m.array_index !== null ? String(m.array_index) : '',
      faktor: String(m.faktor),
      offset: String(m.offset),
      invertieren: m.invertieren,
      beschreibung: m.beschreibung || '',
    }
  }

  if (!mqttAktiv) {
    return (
      <div className="mt-8 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-dashed border-gray-300 dark:border-gray-600">
        <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
          <Radio className="w-4 h-4" />
          <span className="text-sm">
            MQTT-Gateway benötigt eine aktive MQTT-Broker-Verbindung.
            Konfiguriere oben zuerst den Broker.
          </span>
        </div>
      </div>
    )
  }

  return (
    <div className="mt-8 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-medium text-gray-900 dark:text-white flex items-center gap-2">
            <Radio className="w-4 h-4 text-purple-500" />
            MQTT Gateway
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Übersetze externe MQTT-Topics direkt auf EEDC-Inbound-Topics — ohne Node-RED oder HA-Automationen.
          </p>
        </div>
        {status?.aktiv && (
          <span className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-full bg-green-50 text-green-600 dark:bg-green-900/30 dark:text-green-400">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            {status.weitergeleitet ?? 0} weitergel.
          </span>
        )}
      </div>

      {/* Info-Box: Was kann das Gateway? */}
      {mappings.length === 0 && !showForm && (
        <div className="text-xs text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3 space-y-2">
          <p>
            <strong>Wann brauchst du das Gateway?</strong> Wenn deine Geräte bereits eigene MQTT-Topics
            publishen (z.B. Shelly, Tasmota, OpenDTU, Zigbee2MQTT) und du diese Daten direkt
            ins EEDC Live-Dashboard bringen willst.
          </p>
          <p>
            <strong>Connector-Bridge:</strong> Hast du einen Geräte-Connector konfiguriert
            (Einstellungen → Connector), der Live-Daten unterstützt? Dann werden seine Werte
            automatisch auf MQTT-Inbound-Topics gepublisht — kein Gateway-Mapping nötig.
          </p>
          <p className="text-[10px] text-gray-400 dark:text-gray-500">
            Live-fähige Connectors: Shelly 3EM, OpenDTU, Fronius, sonnenBatterie, go-eCharger.
            Reine kWh-Connectors (SMA, Kostal, Tasmota SML) liefern keine Live-Daten.
          </p>
        </div>
      )}

      {/* Status-Zeile */}
      {status && !status.verfuegbar && status.grund && (
        <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 p-2 rounded-lg">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          {status.grund}
        </div>
      )}

      {/* Mapping-Liste */}
      {loading ? (
        <div className="flex justify-center py-4">
          <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
        </div>
      ) : mappings.length === 0 && !showForm ? (
        <div className="text-center py-6 text-sm text-gray-500 dark:text-gray-400">
          Noch keine Mappings konfiguriert.
          <br />
          <button
            onClick={() => { setEditId(null); setShowForm(true) }}
            className="mt-2 inline-flex items-center gap-1 text-primary-600 dark:text-primary-400 hover:underline"
          >
            <Plus className="w-3.5 h-3.5" />
            Erstes Mapping anlegen
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {mappings.map(m => (
            <div
              key={m.id}
              className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                m.aktiv
                  ? 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
                  : 'bg-gray-50 dark:bg-gray-800/50 border-gray-200/50 dark:border-gray-700/50 opacity-60'
              }`}
            >
              {/* Toggle */}
              <button onClick={() => handleToggle(m)} className="shrink-0" title={m.aktiv ? 'Deaktivieren' : 'Aktivieren'}>
                {m.aktiv
                  ? <ToggleRight className="w-5 h-5 text-green-500" />
                  : <ToggleLeft className="w-5 h-5 text-gray-400" />
                }
              </button>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-gray-700 dark:text-gray-300 truncate" title={m.quell_topic}>
                    {m.quell_topic}
                  </span>
                  <span className="text-gray-400 text-xs shrink-0">→</span>
                  <span className="text-xs font-mono text-primary-600 dark:text-primary-400 truncate" title={m.ziel_key}>
                    {m.ziel_key}
                  </span>
                </div>
                {(m.beschreibung || m.payload_typ !== 'plain') && (
                  <div className="flex items-center gap-2 mt-0.5">
                    {m.beschreibung && (
                      <span className="text-[10px] text-gray-500 dark:text-gray-400 truncate">{m.beschreibung}</span>
                    )}
                    {m.payload_typ !== 'plain' && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">
                        {m.payload_typ === 'json' ? `JSON: ${m.json_pfad}` : `Array[${m.array_index}]`}
                      </span>
                    )}
                    {m.faktor !== 1 && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">
                        ×{m.faktor}
                      </span>
                    )}
                    {m.invertieren && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400">
                        ×(−1)
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => startEdit(m)}
                  className="p-1.5 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
                  title="Bearbeiten"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => handleDelete(m.id)}
                  disabled={deleting === m.id}
                  className="p-1.5 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                  title="Löschen"
                >
                  {deleting === m.id
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <Trash2 className="w-3.5 h-3.5" />
                  }
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Neues Mapping / Bearbeiten */}
      {showForm && (
        <div className="p-4 rounded-lg border border-primary-200 dark:border-primary-800 bg-primary-50/30 dark:bg-primary-900/10">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
            {editId !== null ? 'Mapping bearbeiten' : 'Neues Mapping'}
          </h3>
          <MappingForm
            initial={editId !== null ? getEditFormData() : EMPTY_FORM}
            onSave={handleSave}
            onCancel={() => { setShowForm(false); setEditId(null) }}
            saving={saving}
          />
        </div>
      )}

      {/* Neues Mapping Button (wenn Liste nicht leer) */}
      {!showForm && mappings.length > 0 && (
        <button
          onClick={() => { setEditId(null); setShowForm(true) }}
          className="flex items-center gap-1.5 text-sm text-primary-600 dark:text-primary-400 hover:underline"
        >
          <Plus className="w-4 h-4" />
          Mapping hinzufügen
        </button>
      )}
    </div>
  )
}
