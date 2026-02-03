import { useState, useMemo } from 'react'
import { Plus, Car, Flame, Battery, Plug, Settings2, Sun, LayoutGrid, Pencil, Trash2 } from 'lucide-react'
import { Button, Modal, Card, Alert, LoadingSpinner, EmptyState } from '../components/ui'
import { useAnlagen, useInvestitionen, useInvestitionenByTyp } from '../hooks'
import InvestitionForm from '../components/forms/InvestitionForm'
import type { Investition, InvestitionTyp } from '../types'
import type { InvestitionCreate, InvestitionUpdate } from '../api'

const investitionTypen: {
  typ: InvestitionTyp
  label: string
  icon: React.ElementType
  color: string
  bgColor: string
}[] = [
  { typ: 'e-auto', label: 'E-Auto', icon: Car, color: 'text-blue-500', bgColor: 'bg-blue-50 dark:bg-blue-900/20' },
  { typ: 'waermepumpe', label: 'Wärmepumpe', icon: Flame, color: 'text-orange-500', bgColor: 'bg-orange-50 dark:bg-orange-900/20' },
  { typ: 'speicher', label: 'Speicher', icon: Battery, color: 'text-green-500', bgColor: 'bg-green-50 dark:bg-green-900/20' },
  { typ: 'wallbox', label: 'Wallbox', icon: Plug, color: 'text-purple-500', bgColor: 'bg-purple-50 dark:bg-purple-900/20' },
  { typ: 'wechselrichter', label: 'Wechselrichter', icon: Settings2, color: 'text-cyan-500', bgColor: 'bg-cyan-50 dark:bg-cyan-900/20' },
  { typ: 'pv-module', label: 'PV-Module', icon: Sun, color: 'text-yellow-500', bgColor: 'bg-yellow-50 dark:bg-yellow-900/20' },
  { typ: 'balkonkraftwerk', label: 'Balkonkraftwerk', icon: LayoutGrid, color: 'text-teal-500', bgColor: 'bg-teal-50 dark:bg-teal-900/20' },
  { typ: 'sonstiges', label: 'Sonstiges', icon: Settings2, color: 'text-gray-500', bgColor: 'bg-gray-50 dark:bg-gray-900/20' },
]

export default function Investitionen() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editingInvestition, setEditingInvestition] = useState<Investition | null>(null)
  const [selectedTyp, setSelectedTyp] = useState<InvestitionTyp | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<Investition | null>(null)
  const [error, setError] = useState<string | null>(null)

  const anlageId = selectedAnlageId ?? anlagen[0]?.id
  const { investitionen, loading, createInvestition, updateInvestition, deleteInvestition } = useInvestitionen(anlageId)
  const groupedByTyp = useInvestitionenByTyp(investitionen)

  // Zähle Investitionen pro Typ
  const typCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    investitionTypen.forEach(t => {
      counts[t.typ] = groupedByTyp[t.typ]?.length || 0
    })
    return counts
  }, [groupedByTyp])

  const handleCreate = (typ: InvestitionTyp) => {
    setSelectedTyp(typ)
    setEditingInvestition(null)
    setShowForm(true)
  }

  const handleEdit = (investition: Investition) => {
    setEditingInvestition(investition)
    setSelectedTyp(investition.typ)
    setShowForm(true)
  }

  const handleSubmit = async (data: InvestitionCreate | InvestitionUpdate) => {
    try {
      if (editingInvestition) {
        await updateInvestition(editingInvestition.id, data as InvestitionUpdate)
      } else {
        await createInvestition(data as InvestitionCreate)
      }
      setShowForm(false)
      setEditingInvestition(null)
      setSelectedTyp(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    }
  }

  const handleDelete = async () => {
    if (!deleteConfirm) return
    try {
      await deleteInvestition(deleteConfirm.id)
      setDeleteConfirm(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Löschen')
    }
  }

  if (anlagenLoading || loading) {
    return <LoadingSpinner text="Lade Investitionen..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Investitionen</h1>
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an, um Investitionen zu verwalten.
        </Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Investitionen
        </h1>
        <div className="flex items-center gap-3">
          {anlagen.length > 1 && (
            <select
              value={anlageId ?? ''}
              onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
              className="input w-auto"
            >
              {anlagen.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.anlagenname}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Typ-Übersicht */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {investitionTypen.map((typ) => (
          <button
            key={typ.typ}
            onClick={() => handleCreate(typ.typ)}
            className={`card p-4 text-center hover:shadow-md transition-shadow ${typ.bgColor}`}
          >
            <typ.icon className={`h-8 w-8 mx-auto ${typ.color}`} />
            <p className="mt-2 text-sm font-medium text-gray-900 dark:text-white">
              {typ.label}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {typCounts[typ.typ]} vorhanden
            </p>
          </button>
        ))}
      </div>

      {/* Investitionen Liste */}
      {investitionen.length === 0 ? (
        <EmptyState
          title="Keine Investitionen vorhanden"
          description="Erfasse deine Investitionen (E-Auto, Wärmepumpe, Speicher, etc.) um deren Wirtschaftlichkeit zu analysieren."
          action={
            <Button onClick={() => handleCreate('speicher')}>
              <Plus className="h-4 w-4 mr-2" />
              Erste Investition anlegen
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          {investitionTypen.map((typ) => {
            const typInv = groupedByTyp[typ.typ]
            if (!typInv || typInv.length === 0) return null

            return (
              <Card key={typ.typ}>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${typ.bgColor}`}>
                      <typ.icon className={`h-5 w-5 ${typ.color}`} />
                    </div>
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                      {typ.label}
                    </h2>
                  </div>
                  <Button variant="secondary" size="sm" onClick={() => handleCreate(typ.typ)}>
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>

                <div className="space-y-3">
                  {typInv.map((inv) => (
                    <InvestitionCard
                      key={inv.id}
                      investition={inv}
                      onEdit={() => handleEdit(inv)}
                      onDelete={() => setDeleteConfirm(inv)}
                    />
                  ))}
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {/* Formular Modal */}
      <Modal
        isOpen={showForm}
        onClose={() => {
          setShowForm(false)
          setEditingInvestition(null)
          setSelectedTyp(null)
        }}
        title={editingInvestition ? 'Investition bearbeiten' : 'Neue Investition'}
        size="lg"
      >
        {selectedTyp && anlageId && (
          <InvestitionForm
            investition={editingInvestition}
            anlageId={anlageId}
            typ={selectedTyp}
            onSubmit={handleSubmit}
            onCancel={() => {
              setShowForm(false)
              setEditingInvestition(null)
              setSelectedTyp(null)
            }}
          />
        )}
      </Modal>

      {/* Löschen bestätigen */}
      <Modal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        title="Investition löschen"
        size="sm"
      >
        <p className="text-gray-600 dark:text-gray-400 mb-4">
          Möchtest du die Investition "{deleteConfirm?.bezeichnung}" wirklich löschen?
        </p>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setDeleteConfirm(null)}>
            Abbrechen
          </Button>
          <Button variant="danger" onClick={handleDelete}>
            Löschen
          </Button>
        </div>
      </Modal>
    </div>
  )
}

interface InvestitionCardProps {
  investition: Investition
  onEdit: () => void
  onDelete: () => void
}

function InvestitionCard({ investition, onEdit, onDelete }: InvestitionCardProps) {
  const params = investition.parameter || {}

  // Typspezifische Parameter anzeigen
  const getDetails = () => {
    const details: string[] = []

    switch (investition.typ) {
      case 'e-auto':
        if (params.batteriekapazitaet_kwh) details.push(`${params.batteriekapazitaet_kwh} kWh Batterie`)
        if (params.verbrauch_kwh_100km) details.push(`${params.verbrauch_kwh_100km} kWh/100km`)
        if (params.v2h_faehig) details.push('V2H fähig')
        break
      case 'speicher':
        if (params.kapazitaet_kwh) details.push(`${params.kapazitaet_kwh} kWh`)
        if (params.nutzbare_kapazitaet_kwh) details.push(`${params.nutzbare_kapazitaet_kwh} kWh nutzbar`)
        if (params.arbitrage_faehig) details.push('Arbitrage')
        break
      case 'waermepumpe':
        if (params.leistung_kw) details.push(`${params.leistung_kw} kW`)
        if (params.cop) details.push(`COP ${params.cop}`)
        break
      case 'wallbox':
        if (params.max_ladeleistung_kw) details.push(`${params.max_ladeleistung_kw} kW`)
        if (params.bidirektional) details.push('Bidirektional')
        break
      case 'wechselrichter':
        if (params.max_leistung_kw) details.push(`${params.max_leistung_kw} kW`)
        break
      case 'pv-module':
      case 'balkonkraftwerk':
        if (params.leistung_wp) details.push(`${params.leistung_wp} Wp`)
        if (params.anzahl) details.push(`${params.anzahl} Module`)
        break
    }

    return details
  }

  const details = getDetails()
  const kosten = investition.anschaffungskosten_gesamt

  return (
    <div className={`
      flex items-center justify-between p-3 rounded-lg border
      ${investition.aktiv
        ? 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
        : 'bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 opacity-60'
      }
    `}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-medium text-gray-900 dark:text-white truncate">
            {investition.bezeichnung}
          </p>
          {!investition.aktiv && (
            <span className="text-xs px-2 py-0.5 bg-gray-200 dark:bg-gray-700 rounded text-gray-600 dark:text-gray-400">
              Inaktiv
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-1 text-sm text-gray-500 dark:text-gray-400">
          {details.length > 0 && (
            <span>{details.join(' • ')}</span>
          )}
          {kosten && (
            <span className="text-green-600 dark:text-green-400">
              {kosten.toLocaleString('de-DE')} €
            </span>
          )}
          {investition.anschaffungsdatum && (
            <span>
              seit {new Date(investition.anschaffungsdatum).toLocaleDateString('de-DE')}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1 ml-4">
        <button
          onClick={onEdit}
          className="p-2 text-gray-400 hover:text-primary-600 transition-colors"
          title="Bearbeiten"
        >
          <Pencil className="h-4 w-4" />
        </button>
        <button
          onClick={onDelete}
          className="p-2 text-gray-400 hover:text-red-600 transition-colors"
          title="Löschen"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
