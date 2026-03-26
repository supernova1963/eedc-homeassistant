/**
 * Infothek-Formular für Erstellen und Bearbeiten von Einträgen.
 *
 * Lädt Kategorie-Schemas vom Backend und rendert dynamisch
 * die kategorie-spezifischen Felder.
 */

import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { Button, Alert } from '../ui'
import { infothekApi } from '../../api/infothek'
import { investitionenApi } from '../../api/investitionen'
import { KATEGORIE_KEYS, getKategorieConfig } from '../../config/infothekKategorien'
import DateiUpload from '../infothek/DateiUpload'
import type { InfothekEintrag, InfothekEintragCreate, InfothekEintragUpdate, KategorieFeld, KategorienResponse } from '../../types/infothek'
import type { Investition } from '../../types'

interface InfothekFormProps {
  eintrag: InfothekEintrag | null
  anlageId: number
  initialKategorie?: string
  onSubmit: (data: InfothekEintragCreate | InfothekEintragUpdate) => Promise<void>
  onCancel: () => void
}

export default function InfothekForm({ eintrag, anlageId, initialKategorie, onSubmit, onCancel }: InfothekFormProps) {
  const [bezeichnung, setBezeichnung] = useState(eintrag?.bezeichnung ?? '')
  const [kategorie, setKategorie] = useState(eintrag?.kategorie ?? initialKategorie ?? 'sonstiges')
  const [notizen, setNotizen] = useState(eintrag?.notizen ?? '')
  const [parameter, setParameter] = useState<Record<string, unknown>>(
    (eintrag?.parameter as Record<string, unknown>) ?? {}
  )
  const [aktiv, setAktiv] = useState(eintrag?.aktiv ?? true)
  const [investitionId, setInvestitionId] = useState<number | null>(eintrag?.investition_id ?? null)
  const [ansprechpartnerId, setAnsprechpartnerId] = useState<number | null>(eintrag?.ansprechpartner_id ?? null)
  const [investitionen, setInvestitionen] = useState<Investition[]>([])
  const [ansprechpartnerList, setAnsprechpartnerList] = useState<{ id: number; bezeichnung: string }[]>([])
  const [schemas, setSchemas] = useState<KategorienResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showVertrag, setShowVertrag] = useState(false)

  // Lade Kategorie-Schemas, Investitionen und Ansprechpartner
  useEffect(() => {
    infothekApi.getKategorien().then(setSchemas)
    investitionenApi.list(anlageId).then(setInvestitionen)
    infothekApi.list(anlageId, 'ansprechpartner').then(list =>
      setAnsprechpartnerList(list.map(e => ({ id: e.id, bezeichnung: e.bezeichnung })))
    )
  }, [anlageId])

  // Vorbelegung aus Systemdaten bei Kategorie-Wechsel (nur bei neuem Eintrag)
  const loadVorbelegung = useCallback(async (kat: string) => {
    if (eintrag) return // Keine Vorbelegung beim Bearbeiten
    try {
      const result = await infothekApi.getVorbelegung(kat, anlageId)
      if (result.parameter && Object.keys(result.parameter).length > 0) {
        setParameter(result.parameter as Record<string, unknown>)
      }
    } catch {
      // Vorbelegung ist optional, Fehler ignorieren
    }
  }, [eintrag, anlageId])

  // Vorbelegung beim Öffnen (neuer Eintrag mit vorgewählter Kategorie)
  useEffect(() => {
    if (!eintrag && kategorie !== 'sonstiges') {
      loadVorbelegung(kategorie)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Prüfe ob übergreifende Sektionen Daten haben (für Edit-Modus)
  useEffect(() => {
    if (eintrag?.parameter) {
      const p = eintrag.parameter as Record<string, unknown>
      if (p.vertragsnummer || p.vertragsbeginn || p.kuendigungsfrist_monate) {
        setShowVertrag(true)
      }
    }
  }, [eintrag])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      const params = Object.keys(parameter).length > 0 ? parameter : null
      if (eintrag) {
        const data: InfothekEintragUpdate = {
          bezeichnung,
          kategorie,
          notizen: notizen || null,
          parameter: params,
          investition_id: investitionId,
          ansprechpartner_id: ansprechpartnerId,
          aktiv,
        }
        await onSubmit(data)
      } else {
        const data: InfothekEintragCreate = {
          anlage_id: anlageId,
          bezeichnung,
          kategorie,
          notizen: notizen || null,
          parameter: params,
          investition_id: investitionId,
          ansprechpartner_id: ansprechpartnerId,
          aktiv,
        }
        await onSubmit(data)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  const updateParam = (key: string, value: unknown) => {
    setParameter(prev => {
      const next = { ...prev }
      if (value === '' || value === null || value === undefined) {
        delete next[key]
      } else {
        next[key] = value
      }
      return next
    })
  }

  const kategorieFelder = schemas?.kategorien[kategorie]?.felder ?? {}
  const vertragFelder = schemas?.uebergreifende_felder?.vertrag?.felder ?? {}

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {error && <Alert type="error">{error}</Alert>}

      {/* Bezeichnung */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Bezeichnung *
        </label>
        <input
          type="text"
          value={bezeichnung}
          onChange={e => setBezeichnung(e.target.value)}
          className="input w-full"
          placeholder="z.B. Stadtwerke Strom (Netzbetreiber)"
          required
        />
      </div>

      {/* Kategorie (nicht bei Ansprechpartnern — dort ist sie fest) */}
      {kategorie !== 'ansprechpartner' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Kategorie *
          </label>
          <select
            value={kategorie}
            title="Kategorie"
            onChange={e => {
              const newKat = e.target.value
              setKategorie(newKat)
              if (!eintrag) {
                setParameter({})
                loadVorbelegung(newKat)
              }
            }}
            className="input w-full"
          >
            {KATEGORIE_KEYS.filter(k => k !== 'ansprechpartner').map(key => {
              const config = getKategorieConfig(key)
              return (
                <option key={key} value={key}>
                  {config.label}
                </option>
              )
            })}
          </select>
        </div>
      )}

      {/* Kategorie-spezifische Felder */}
      {Object.keys(kategorieFelder).length > 0 && (
        <fieldset className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <legend className="text-sm font-medium text-gray-700 dark:text-gray-300 px-2">
            {schemas?.kategorien[kategorie]?.label ?? kategorie}
          </legend>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {Object.entries(kategorieFelder).map(([key, feld]) => (
              <ParameterFeld
                key={key}
                feld={feld}
                value={parameter[key]}
                onChange={val => updateParam(key, val)}
              />
            ))}
          </div>
        </fieldset>
      )}

      {/* Vertragspartner (Ansprechpartner-Verknüpfung) */}
      {kategorie !== 'ansprechpartner' && ansprechpartnerList.length > 0 && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Vertragspartner
          </label>
          <select
            value={ansprechpartnerId ?? ''}
            onChange={e => setAnsprechpartnerId(e.target.value ? Number(e.target.value) : null)}
            className="input w-full"
            title="Vertragspartner"
          >
            <option value="">— Kein Vertragspartner —</option>
            {ansprechpartnerList.map(asp => (
              <option key={asp.id} value={asp.id}>{asp.bezeichnung}</option>
            ))}
          </select>
        </div>
      )}

      {/* Übergreifende Vertrags-Sektion */}
      <div>
        <button
          type="button"
          onClick={() => setShowVertrag(!showVertrag)}
          className="text-sm text-primary-600 dark:text-primary-400 hover:underline flex items-center gap-1"
        >
          <span>{showVertrag ? '▾' : '▸'}</span>
          Vertragsdaten (optional)
        </button>
        {showVertrag && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3 pl-4 border-l-2 border-gray-200 dark:border-gray-700">
            {Object.entries(vertragFelder).map(([key, feld]) => (
              <ParameterFeld
                key={key}
                feld={feld}
                value={parameter[key]}
                onChange={val => updateParam(key, val)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Verknüpfte Investition (nicht bei Ansprechpartnern) */}
      {kategorie !== 'ansprechpartner' && investitionen.length > 0 && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Verknüpfte Investition
          </label>
          <select
            value={investitionId ?? ''}
            onChange={e => setInvestitionId(e.target.value ? Number(e.target.value) : null)}
            className="input w-full"
            title="Verknüpfte Investition"
          >
            <option value="">— Keine Verknüpfung —</option>
            {investitionen.map(inv => (
              <option key={inv.id} value={inv.id}>
                {inv.bezeichnung} ({inv.typ})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Notizen */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Notizen
        </label>
        <textarea
          value={notizen}
          onChange={e => setNotizen(e.target.value)}
          className="input w-full"
          rows={4}
          placeholder="Freitext für beliebige Informationen..."
        />
      </div>

      {/* Dateien (nur beim Bearbeiten — braucht eintrag_id) */}
      {eintrag && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Dateien (max. 3 — Fotos + PDFs)
          </label>
          <DateiUpload eintragId={eintrag.id} />
        </div>
      )}

      {/* Aktiv-Status (nur beim Bearbeiten) */}
      {eintrag && (
        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input
            type="checkbox"
            checked={aktiv}
            onChange={e => setAktiv(e.target.checked)}
            className="rounded border-gray-300"
          />
          Aktiv (deaktivierte Einträge werden ausgegraut angezeigt)
        </label>
      )}

      {/* Buttons */}
      <div className="flex justify-end gap-3 pt-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button type="submit" disabled={loading || !bezeichnung.trim()}>
          {loading ? 'Speichern...' : eintrag ? 'Speichern' : 'Erstellen'}
        </Button>
      </div>
    </form>
  )
}


/** Dynamisches Feld basierend auf Typ (string, number, date, select) */
function ParameterFeld({
  feld,
  value,
  onChange,
}: {
  feld: KategorieFeld
  value: unknown
  onChange: (val: unknown) => void
}) {
  const strValue = value != null ? String(value) : ''

  return (
    <div>
      <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
        {feld.label}
      </label>
      {feld.type === 'select' && feld.options ? (
        <select
          value={strValue}
          onChange={e => onChange(e.target.value || null)}
          className="input w-full"
          title={feld.label}
        >
          <option value="">— Auswählen —</option>
          {feld.options.map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      ) : (
        <input
          type={feld.type === 'number' ? 'number' : feld.type === 'date' ? 'date' : 'text'}
          value={strValue}
          title={feld.label}
          onChange={e => {
            const v = e.target.value
            if (feld.type === 'number') {
              onChange(v === '' ? null : parseFloat(v))
            } else {
              onChange(v || null)
            }
          }}
          step={feld.type === 'number' ? 'any' : undefined}
          className="input w-full"
        />
      )}
    </div>
  )
}
