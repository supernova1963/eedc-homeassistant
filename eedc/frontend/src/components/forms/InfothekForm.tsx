/**
 * Infothek-Formular für Erstellen und Bearbeiten von Einträgen.
 *
 * Lädt Kategorie-Schemas vom Backend und rendert dynamisch
 * die kategorie-spezifischen Felder.
 */

import { useState, useEffect, useCallback, useRef, type FormEvent } from 'react'
import { Button, Alert, Input, Select, Textarea, DatumFeld, Switch, Checkbox, FormSection } from '../ui'
import { infothekApi } from '../../api/infothek'
import { investitionenApi } from '../../api/investitionen'
import { KATEGORIE_KEYS, getKategorieConfig } from '../../config/infothekKategorien'
import DateiUpload from '../infothek/DateiUpload'
import MarkdownNotizen from '../infothek/MarkdownNotizen'
import type { InfothekEintrag, InfothekEintragCreate, InfothekEintragUpdate, KategorieFeld, KategorienResponse } from '../../types/infothek'
import type { Investition } from '../../types'

interface InfothekFormProps {
  eintrag: InfothekEintrag | null
  anlageId: number
  initialKategorie?: string
  initialInvestitionIds?: number[]
  onSubmit: (data: InfothekEintragCreate | InfothekEintragUpdate) => Promise<void>
  onCancel: () => void
}

export default function InfothekForm({ eintrag, anlageId, initialKategorie, initialInvestitionIds, onSubmit, onCancel }: InfothekFormProps) {
  const [bezeichnung, setBezeichnung] = useState(eintrag?.bezeichnung ?? '')
  const [kategorie, setKategorie] = useState(eintrag?.kategorie ?? initialKategorie ?? 'sonstiges')
  const [notizen, setNotizen] = useState(eintrag?.notizen ?? '')
  const [parameter, setParameter] = useState<Record<string, unknown>>(
    (eintrag?.parameter as Record<string, unknown>) ?? {}
  )
  const [aktiv, setAktiv] = useState(eintrag?.aktiv ?? true)
  const [inAnlagendoku, setInAnlagendoku] = useState(eintrag?.in_anlagendoku ?? true)
  const [investitionIds, setInvestitionIds] = useState<number[]>(eintrag?.investition_ids ?? (eintrag?.investition_id ? [eintrag.investition_id] : (initialInvestitionIds ?? [])))
  const [ansprechpartnerId, setAnsprechpartnerId] = useState<number | null>(eintrag?.ansprechpartner_id ?? null)
  const [investitionen, setInvestitionen] = useState<Investition[]>([])
  const [ansprechpartnerList, setAnsprechpartnerList] = useState<{ id: number; bezeichnung: string }[]>([])
  const [schemas, setSchemas] = useState<KategorienResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // V1/V2: Bezeichnung-Pflichtfehler erst nach Berührung/Absenden (Muster Slice 1–3).
  const [bezeichnungTouched, setBezeichnungTouched] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const bezeichnungRef = useRef<HTMLDivElement>(null)

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

  const bezeichnungFehler = !bezeichnung.trim() ? 'Bitte eine Bezeichnung eingeben' : undefined
  const zeigeBezeichnungFehler = (submitted || bezeichnungTouched) ? bezeichnungFehler : undefined

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitted(true)
    setError(null)
    if (bezeichnungFehler) {
      bezeichnungRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }

    setLoading(true)
    try {
      const params = Object.keys(parameter).length > 0 ? parameter : null
      const gemeinsam = {
        bezeichnung,
        kategorie,
        notizen: notizen || null,
        parameter: params,
        investition_ids: investitionIds,
        ansprechpartner_id: ansprechpartnerId,
        aktiv,
        in_anlagendoku: inAnlagendoku,
      }
      if (eintrag) {
        await onSubmit(gemeinsam as InfothekEintragUpdate)
      } else {
        await onSubmit({ ...gemeinsam, anlage_id: anlageId } as InfothekEintragCreate)
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
  const p = (eintrag?.parameter ?? {}) as Record<string, unknown>
  const hatVertragsdaten = !!(p.vertragsnummer || p.vertragsbeginn || p.kuendigungsfrist_monate)
  const istAnsprechpartner = kategorie === 'ansprechpartner'
  const zeigeStatusSektion = !!eintrag || !istAnsprechpartner

  const KATEGORIE_OPTIONEN = KATEGORIE_KEYS
    .filter(k => k !== 'ansprechpartner')
    .map(key => ({ value: key, label: getKategorieConfig(key).label }))

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {error && <Alert type="error">{error}</Alert>}

      {/* ── Kern: Basis ── */}
      <FormSection title="Basis">
        <div className="space-y-4">
          <div ref={bezeichnungRef}>
            <Input
              label="Bezeichnung"
              name="bezeichnung"
              value={bezeichnung}
              onChange={e => setBezeichnung(e.target.value)}
              onBlur={() => setBezeichnungTouched(true)}
              placeholder="z.B. Stadtwerke Strom (Netzbetreiber)"
              required
              error={zeigeBezeichnungFehler}
            />
          </div>

          {!istAnsprechpartner && (
            <Select
              label="Kategorie"
              name="kategorie"
              value={kategorie}
              onChange={e => {
                const newKat = e.target.value
                setKategorie(newKat)
                if (!eintrag) {
                  setParameter({})
                  loadVorbelegung(newKat)
                }
              }}
              required
              options={KATEGORIE_OPTIONEN}
            />
          )}

          {!istAnsprechpartner && ansprechpartnerList.length > 0 && (
            <Select
              label="Vertragspartner"
              name="ansprechpartner_id"
              value={ansprechpartnerId ?? ''}
              onChange={e => setAnsprechpartnerId(e.target.value ? Number(e.target.value) : null)}
              placeholder="— Kein Vertragspartner —"
              options={ansprechpartnerList.map(asp => ({ value: String(asp.id), label: asp.bezeichnung }))}
            />
          )}
        </div>
      </FormSection>

      {/* ── Kern: Kategorie-spezifische Felder ── */}
      {Object.keys(kategorieFelder).length > 0 && (
        <FormSection title={schemas?.kategorien[kategorie]?.label ?? kategorie}>
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
        </FormSection>
      )}

      {/* ── Kern: Notizen ── */}
      <FormSection title="Notizen">
        <MarkdownNotizen value={notizen} onChange={setNotizen} />
      </FormSection>

      {/* ── Kern: Dateien (nur beim Bearbeiten — braucht eintrag_id) ── */}
      {eintrag && (
        <FormSection title="Dateien" description="max. 15 — Fotos + PDFs bis 10 MB">
          <DateiUpload eintragId={eintrag.id} />
        </FormSection>
      )}

      {/* ── Erweitert: Vertragsdaten ── */}
      <FormSection variant="erweitert" title="Vertragsdaten (optional)" defaultOpen={hatVertragsdaten}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {Object.entries(vertragFelder).map(([key, feld]) => (
            <ParameterFeld
              key={key}
              feld={feld}
              value={parameter[key]}
              onChange={val => updateParam(key, val)}
            />
          ))}
        </div>
      </FormSection>

      {/* ── Erweitert: Verknüpfte Investitionen ── */}
      {!istAnsprechpartner && investitionen.length > 0 && (
        <FormSection variant="erweitert" title="Verknüpfte Investitionen" defaultOpen={investitionIds.length > 0}>
          <div className="space-y-1 max-h-48 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700 p-2">
            {investitionen.map(inv => (
              <div key={inv.id} className="rounded px-1 py-0.5 hover:bg-gray-100 dark:hover:bg-gray-700/30">
                <Checkbox
                  name={`inv-${inv.id}`}
                  checked={investitionIds.includes(inv.id)}
                  onChange={e => {
                    if (e.target.checked) {
                      setInvestitionIds(prev => [...prev, inv.id])
                    } else {
                      setInvestitionIds(prev => prev.filter(id => id !== inv.id))
                    }
                  }}
                  label={
                    <span>
                      {inv.bezeichnung}
                      <span className="text-gray-500 text-xs ml-1">({inv.typ})</span>
                    </span>
                  }
                />
              </div>
            ))}
          </div>
          {investitionIds.length > 0 && (
            <button
              type="button"
              onClick={() => setInvestitionIds([])}
              className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-200 mt-1"
            >
              Alle abwählen
            </button>
          )}
        </FormSection>
      )}

      {/* ── Erweitert: Status & Anzeige ── */}
      {zeigeStatusSektion && (
        <FormSection variant="erweitert" title="Status & Anzeige" defaultOpen={eintrag ? !aktiv : false}>
          <div className="space-y-3">
            {eintrag && (
              <div className="flex items-start gap-3">
                <Switch checked={aktiv} onChange={setAktiv} ariaLabel="Aktiv" />
                <div>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Aktiv</span>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    Deaktivierte (archivierte) Einträge werden ausgegraut angezeigt.
                  </p>
                </div>
              </div>
            )}
            {!istAnsprechpartner && (
              <div className="flex items-start gap-3">
                <Switch checked={inAnlagendoku} onChange={setInAnlagendoku} ariaLabel="In Anlagendokumentation anzeigen" />
                <div>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">In Anlagendokumentation anzeigen</span>
                </div>
              </div>
            )}
          </div>
        </FormSection>
      )}

      {/* Buttons */}
      <div className="flex justify-end gap-3 pt-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button type="submit" loading={loading}>
          {eintrag ? 'Speichern' : 'Erstellen'}
        </Button>
      </div>
    </form>
  )
}


/** Dynamisches Feld basierend auf Typ (string, number, date, select) — SoT-Controls. */
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

  if (feld.type === 'select' && feld.options) {
    return (
      <Select
        label={feld.label}
        value={strValue}
        onChange={e => onChange(e.target.value || null)}
        placeholder="— Auswählen —"
        options={feld.options.map(opt => ({ value: opt, label: opt }))}
      />
    )
  }
  if (feld.type === 'text') {
    return (
      <Textarea
        label={feld.label}
        value={strValue}
        onChange={e => onChange(e.target.value || null)}
        rows={4}
      />
    )
  }
  if (feld.type === 'date') {
    return (
      <DatumFeld
        label={feld.label}
        value={strValue}
        onChange={v => onChange(v || null)}
        min="1950-01-01"
      />
    )
  }
  return (
    <Input
      label={feld.label}
      type={feld.type === 'number' ? 'number' : 'text'}
      value={strValue}
      onChange={e => {
        const v = e.target.value
        onChange(feld.type === 'number' ? (v === '' ? null : parseFloat(v)) : (v || null))
      }}
      step={feld.type === 'number' ? 'any' : undefined}
    />
  )
}
