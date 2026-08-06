/**
 * InvestitionenTeile — geteilte Geräte-/Investitions-Verwaltung (EINE Code-Wahrheit).
 *
 * Speist sowohl die V3-Seite {@link ./Investitionen} (dünner Komposer) als auch den
 * IA-V4-Einstellungen-Reiter „Komponenten" ({@link ../v4/EinstellungenV4}, datengetriebener
 * Zweig: ein BlockShell-Block pro Investitionstyp). Der gemeinsame Zustand (Formular-Modal,
 * Löschen-Dialog, Migration, Fehler) liegt im Hook {@link useInvestitionenVerwaltung} — beide
 * Konsumenten bauen ihre Darstellung darauf auf, kein zweiter CRUD-Pfad.
 *
 * Datenrolle strikt Investition (nur `investitionenApi`/`infothekApi`-Verknüpfung, kein
 * Vermischen mit der Infothek-Verwaltung). Typ-Reihenfolge/-Farben aus der Kanon-SoT
 * (`INVESTITION_TYP_ORDER` / `KOMPONENTEN_FARBEN`).
 */
import { useState, useEffect, useMemo, useCallback, type ReactNode } from 'react'
import { Plus, Car, Flame, Battery, Plug, Settings2, Sun, LayoutGrid, Pencil, Trash2, PiggyBank, ArrowRight, FileText, ChevronDown, type LucideIcon } from 'lucide-react'
import { Button, Modal, Card, Alert, LoadingSpinner, EmptyState, DestructiveActionDialog, InlineAktion } from '../components/ui'
import { useInvestitionen, useInvestitionenByTyp } from '../hooks'
import { INVESTITION_TYP_ORDER, TYP_LABELS as INVESTITION_TYP_LABELS } from '../lib/constants'
import InvestitionForm from '../components/forms/InvestitionForm'
import InfothekForm from '../components/forms/InfothekForm'
import type { Investition, InvestitionTyp } from '../types'
import type { InvestitionCreate, InvestitionUpdate } from '../api'
import { infothekApi } from '../api/infothek'
import type { InfothekEintrag, InfothekEintragCreate } from '../types/infothek'
import {
  eAutoParameter,
  speicherParameter,
  waermepumpeParameter,
  wallboxParameter,
  wechselrichterParameter,
  pvModuleParameter,
  balkonkraftwerkParameter,
  fmtZahl,
  formatDatum,
  heuteIso,
  KOMPONENTEN_FARBEN,
} from '../lib'

// Icon pro Typ; Identitätsfarbe + Tint kommen aus der Kanon-SoT KOMPONENTEN_FARBEN
// (lib/colors.ts) — keine zweite Farbmap mehr (Regel A, war zuvor gedriftet:
// e-auto blau/wallbox lila/wp orange …). Reihenfolge + Label aus INVESTITION_TYP_ORDER /
// INVESTITION_TYP_LABELS, damit Stammdaten konsistent zu Cockpit / Sensor-Mapping bleibt.
export const TYP_ICON_STYLE: Record<InvestitionTyp, { icon: LucideIcon; color: string; bgColor: string }> = {
  'wechselrichter':  { icon: Settings2,  color: KOMPONENTEN_FARBEN['wechselrichter'].text,  bgColor: KOMPONENTEN_FARBEN['wechselrichter'].tint },
  'pv-module':       { icon: Sun,        color: KOMPONENTEN_FARBEN['pv-module'].text,       bgColor: KOMPONENTEN_FARBEN['pv-module'].tint },
  'balkonkraftwerk': { icon: LayoutGrid, color: KOMPONENTEN_FARBEN['balkonkraftwerk'].text, bgColor: KOMPONENTEN_FARBEN['balkonkraftwerk'].tint },
  'speicher':        { icon: Battery,    color: KOMPONENTEN_FARBEN['speicher'].text,        bgColor: KOMPONENTEN_FARBEN['speicher'].tint },
  'waermepumpe':     { icon: Flame,      color: KOMPONENTEN_FARBEN['waermepumpe'].text,     bgColor: KOMPONENTEN_FARBEN['waermepumpe'].tint },
  'wallbox':         { icon: Plug,       color: KOMPONENTEN_FARBEN['wallbox'].text,         bgColor: KOMPONENTEN_FARBEN['wallbox'].tint },
  'e-auto':          { icon: Car,        color: KOMPONENTEN_FARBEN['e-auto'].text,          bgColor: KOMPONENTEN_FARBEN['e-auto'].tint },
  'sonstiges':       { icon: Settings2,  color: KOMPONENTEN_FARBEN['sonstiges'].text,       bgColor: KOMPONENTEN_FARBEN['sonstiges'].tint },
}

// Innerhalb einer Typ-Gruppe: neueste Anschaffung oben, fehlende Daten ans Ende.
function sortiereTyp(typInv: Investition[]): Investition[] {
  return [...typInv].sort((a, b) => {
    const ad = a.anschaffungsdatum ?? ''
    const bd = b.anschaffungsdatum ?? ''
    if (!ad && !bd) return a.bezeichnung.localeCompare(b.bezeichnung, 'de')
    if (!ad) return 1
    if (!bd) return -1
    return bd.localeCompare(ad)
  })
}

// ─── Geteilter Zustand: Formular-Modal · Löschen-Dialog · Migration · Fehler ───

export interface InvestitionenVerwaltungState {
  investitionen: Investition[]
  loading: boolean
  groupedByTyp: Record<string, Investition[]>
  typCounts: Record<string, number>
  error: string | null
  setError: (v: string | null) => void
  /** Öffnet das Formular-Modal für eine Neuanlage des Typs. */
  oeffneNeu: (typ: InvestitionTyp) => void
  /** Öffnet das Formular-Modal zum Bearbeiten eines Geräts. */
  oeffneBearbeiten: (inv: Investition) => void
  /** Fragt das Löschen eines Geräts ab (Backup-Dialog). */
  frageLoeschen: (inv: Investition) => void
  /** Geräte-Liste eines Typs (bereits sortiert). */
  geraeteDesTyps: (typ: InvestitionTyp) => Investition[]
  /** Migrations-Hinweis + Fehler-Alerts (an gemeinsamer Stelle rendern). */
  hinweise: ReactNode
  /** Formular- + Löschen-Modals (einmal rendern). */
  modals: ReactNode
}

/**
 * Zentraler Zustand + CRUD für die Geräte-Verwaltung — geteilt von V3-Seite und
 * V4-Komponenten-Reiter. `anlagenname` speist den Backup-Hinweis im Löschen-Dialog.
 */
export function useInvestitionenVerwaltung(anlageId?: number, anlagenname?: string): InvestitionenVerwaltungState {
  const { investitionen, loading, createInvestition, updateInvestition, deleteInvestition } = useInvestitionen(anlageId)
  const groupedByTyp = useInvestitionenByTyp(investitionen)
  // Cross-Link-Präfix je Welt (V3-Seite vs. V4-Einstellungs-Block) — geteilte Datei.

  const [showForm, setShowForm] = useState(false)
  const [editingInvestition, setEditingInvestition] = useState<Investition | null>(null)
  const [selectedTyp, setSelectedTyp] = useState<InvestitionTyp | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<Investition | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [migrationCount, setMigrationCount] = useState(0)
  const [migrating, setMigrating] = useState(false)
  const [migrationDone, setMigrationDone] = useState<string | null>(null)

  // Migrations-Status prüfen
  const checkMigration = useCallback(async () => {
    if (!anlageId) return
    try {
      const status = await infothekApi.getMigrationStatus(anlageId)
      setMigrationCount(status.total)
    } catch {
      // Fehler ignorieren
    }
  }, [anlageId])

  useEffect(() => {
    checkMigration()
  }, [checkMigration])

  const handleMigrateBatch = async () => {
    if (!anlageId) return
    setMigrating(true)
    try {
      const result = await infothekApi.migrateBatch(anlageId)
      setMigrationCount(0)
      setMigrationDone(`${result.count} Einträge in die Infothek übernommen.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler bei der Migration')
    } finally {
      setMigrating(false)
    }
  }

  // Zähle Investitionen pro Typ
  const typCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    INVESTITION_TYP_ORDER.forEach(typ => {
      counts[typ] = groupedByTyp[typ]?.length || 0
    })
    return counts
  }, [groupedByTyp])

  const schliesseForm = () => {
    setShowForm(false)
    setEditingInvestition(null)
    setSelectedTyp(null)
  }

  const oeffneNeu = (typ: InvestitionTyp) => {
    setSelectedTyp(typ)
    setEditingInvestition(null)
    setShowForm(true)
  }

  const oeffneBearbeiten = (investition: Investition) => {
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
      schliesseForm()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    }
  }

  const handleDelete = async () => {
    if (!deleteConfirm) return
    // Fehler wird vom DestructiveActionDialog gefangen und im Dialog angezeigt
    await deleteInvestition(deleteConfirm.id)
    setDeleteConfirm(null)
  }

  const geraeteDesTyps = useCallback(
    (typ: InvestitionTyp) => sortiereTyp(groupedByTyp[typ] ?? []),
    [groupedByTyp],
  )

  const hinweise = (
    <>
      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {/* Migration-Hinweis */}
      {migrationDone && (
        <Alert type="success" onClose={() => setMigrationDone(null)}>
          {migrationDone}{' '}
          <a href={`#/einstellungen/infothek`} className="underline font-medium">Zur Infothek</a>
        </Alert>
      )}
      {migrationCount > 0 && !migrationDone && (
        <div className="flex items-center justify-between p-4 rounded-lg bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800">
          <div>
            <p className="text-sm font-medium text-primary-900 dark:text-primary-100">
              Stammdaten in Infothek übernehmen?
            </p>
            <p className="text-xs text-primary-700 dark:text-primary-300 mt-0.5">
              {migrationCount} Investition{migrationCount !== 1 ? 'en' : ''} mit Kontakt-, Garantie- oder Wartungsdaten gefunden.
            </p>
          </div>
          <Button
            size="sm"
            onClick={handleMigrateBatch}
            disabled={migrating}
          >
            {migrating ? 'Wird übernommen...' : (
              <>
                Übernehmen
                <ArrowRight className="h-4 w-4 ml-1" />
              </>
            )}
          </Button>
        </div>
      )}
    </>
  )

  const modals = (
    <>
      {/* Formular Modal */}
      <Modal
        isOpen={showForm}
        onClose={schliesseForm}
        title={editingInvestition ? 'Investition bearbeiten' : 'Neue Investition'}
        size="xl"
      >
        {selectedTyp && anlageId != null && (
          <InvestitionForm
            investition={editingInvestition}
            anlageId={anlageId}
            typ={selectedTyp}
            onSubmit={handleSubmit}
            onCancel={schliesseForm}
          />
        )}
      </Modal>

      {/* Löschen bestätigen — mit Backup-Angebot */}
      <DestructiveActionDialog
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Komponente löschen"
        itemLabel={<>Komponente „{deleteConfirm?.bezeichnung}" wird gelöscht.</>}
        warningMessage="Alle hinterlegten Parameter, monatlichen Detail-Daten und Verknüpfungen zu Komponenten-Akten gehen verloren."
        anlageId={anlageId ?? undefined}
        anlageName={anlagenname || ''}
        backupHint={
          <>Lädt einen vollständigen JSON-Export der gesamten Anlage <strong>„{anlagenname}"</strong> herunter — daraus lässt sich die Komponente später wiederherstellen.</>
        }
      />
    </>
  )

  return {
    investitionen,
    loading,
    groupedByTyp,
    typCounts,
    error,
    setError,
    oeffneNeu,
    oeffneBearbeiten,
    frageLoeschen: setDeleteConfirm,
    geraeteDesTyps,
    hinweise,
    modals,
  }
}

// ─── Per-Typ-Bausteine (V4-Komponenten-Reiter) ────────────────────────────────

/** „+"-Knopf für die Block-Überschrift eines Typs (Neuanlage). */
export function TypNeuButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <Button
      type="button"
      variant="secondary"
      size="sm"
      onClick={onClick}
      aria-label={`${label} hinzufügen`}
      title={`${label} hinzufügen`}
    >
      <Plus className="h-4 w-4" />
    </Button>
  )
}

/** Geräte-Liste eines Typs (Karten wie IST). Leerer Typ → dezenter Hinweis. */
export function TypGeraeteListe({
  geraete,
  onEdit,
  onDelete,
}: {
  geraete: Investition[]
  onEdit: (inv: Investition) => void
  onDelete: (inv: Investition) => void
}) {
  if (geraete.length === 0) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Noch keine Geräte dieses Typs — über „+" oben hinzufügen.
      </p>
    )
  }
  return (
    <div className="space-y-3">
      {geraete.map((inv) => (
        <InvestitionCard
          key={inv.id}
          investition={inv}
          onEdit={() => onEdit(inv)}
          onDelete={() => onDelete(inv)}
        />
      ))}
    </div>
  )
}

// ─── V3-Vollverwaltung (Typ-Übersicht + Listen) ───────────────────────────────

/**
 * Vollständige Geräte-Verwaltung wie IST (Typ-Kacheln + Listen pro Typ + Modals).
 * `kopfZusatz` = Anlage-Auswahl (Mehr-Anlagen-Fall), rechts im Kopf.
 */
export function InvestitionenVerwaltung({
  anlageId,
  anlagenname,
  kopfZusatz,
}: {
  anlageId: number
  anlagenname?: string
  kopfZusatz?: ReactNode
}) {
  const v = useInvestitionenVerwaltung(anlageId, anlagenname)

  if (v.loading) {
    return <LoadingSpinner text="Lade Investitionen..." />
  }

  return (
    <div className="space-y-6">
      {/* #218: Überschrift „Investitionen" entfernt — der Sub-Tab benennt den Bereich */}
      {kopfZusatz && (
        <div className="flex items-center justify-end">
          <div className="flex items-center gap-3">{kopfZusatz}</div>
        </div>
      )}

      {v.hinweise}

      {/* Typ-Übersicht */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        {INVESTITION_TYP_ORDER.map((typ) => {
          const style = TYP_ICON_STYLE[typ]
          const TypIcon = style.icon
          return (
            <button
              key={typ}
              onClick={() => v.oeffneNeu(typ)}
              className={`card p-4 text-center hover:shadow-md transition-shadow ${style.bgColor}`}
            >
              <TypIcon className={`h-8 w-8 mx-auto ${style.color}`} />
              <p className="mt-2 text-sm font-medium text-gray-900 dark:text-white">
                {INVESTITION_TYP_LABELS[typ]}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {v.typCounts[typ]} vorhanden
              </p>
            </button>
          )
        })}
      </div>

      {/* Investitionen Liste */}
      {v.investitionen.length === 0 ? (
        <EmptyState
          icon={PiggyBank}
          title="Keine Investitionen vorhanden"
          description="Erfasse deine Investitionen (E-Auto, Wärmepumpe, Speicher, etc.) um deren Wirtschaftlichkeit zu analysieren."
          action={
            <Button onClick={() => v.oeffneNeu('speicher')}>
              <Plus className="h-4 w-4 mr-2" />
              Erste Investition anlegen
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          {INVESTITION_TYP_ORDER.map((typ) => {
            const typInv = v.groupedByTyp[typ]
            if (!typInv || typInv.length === 0) return null
            const style = TYP_ICON_STYLE[typ]
            const TypIcon = style.icon

            return (
              <Card key={typ}>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${style.bgColor}`}>
                      <TypIcon className={`h-5 w-5 ${style.color}`} />
                    </div>
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                      {INVESTITION_TYP_LABELS[typ]}
                    </h2>
                  </div>
                  <Button variant="secondary" size="sm" onClick={() => v.oeffneNeu(typ)}>
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>

                <TypGeraeteListe
                  geraete={v.geraeteDesTyps(typ)}
                  onEdit={v.oeffneBearbeiten}
                  onDelete={v.frageLoeschen}
                />
              </Card>
            )
          })}
        </div>
      )}

      {v.modals}
    </div>
  )
}

// ─── Geräte-Karte (wie IST) ───────────────────────────────────────────────────

interface InvestitionCardProps {
  investition: Investition
  onEdit: () => void
  onDelete: () => void
}

function InvestitionCard({ investition, onEdit, onDelete }: InvestitionCardProps) {
  const [infothekEintraege, setInfothekEintraege] = useState<InfothekEintrag[]>([])
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showDropdown, setShowDropdown] = useState(false)
  // Komponenten-Akte-Links zeigen je Welt auf V3- oder V4-Infothek (geteilte Datei).
  const refreshInfothek = useCallback(() => {
    infothekApi.listFuerInvestition(investition.id).then(setInfothekEintraege).catch(() => {})
  }, [investition.id])

  useEffect(() => {
    refreshInfothek()
  }, [refreshInfothek])

  // Typspezifische Parameter anzeigen — Reads gehen über typed Helper aus lib/investitionParameter.ts
  const getDetails = () => {
    const details: string[] = []

    switch (investition.typ) {
      case 'e-auto': {
        const p = eAutoParameter(investition.parameter)
        if (p.batteriekapazitaet_kwh) details.push(`${p.batteriekapazitaet_kwh} kWh Batterie`)
        if (p.verbrauch_kwh_100km) details.push(`${p.verbrauch_kwh_100km} kWh/100km`)
        if (p.v2h_faehig) details.push('V2H fähig')
        break
      }
      case 'speicher': {
        const p = speicherParameter(investition.parameter)
        if (p.kapazitaet_kwh) details.push(`${p.kapazitaet_kwh} kWh`)
        if (p.nutzbare_kapazitaet_kwh) details.push(`${p.nutzbare_kapazitaet_kwh} kWh nutzbar`)
        if (p.arbitrage_faehig) details.push('Arbitrage')
        break
      }
      case 'waermepumpe': {
        const p = waermepumpeParameter(investition.parameter)
        if (p.leistung_kw) details.push(`${p.leistung_kw} kW`)
        if (p.jaz) details.push(`JAZ ${p.jaz}`)
        break
      }
      case 'wallbox': {
        const p = wallboxParameter(investition.parameter)
        if (p.max_ladeleistung_kw) details.push(`${p.max_ladeleistung_kw} kW`)
        if (p.bidirektional) details.push('Bidirektional')
        break
      }
      case 'wechselrichter': {
        const p = wechselrichterParameter(investition.parameter)
        if (p.max_leistung_kw) details.push(`${p.max_leistung_kw} kW`)
        break
      }
      case 'pv-module': {
        // Eigener Zweig, NICHT mit dem Balkonkraftwerk geteilt (R22-1): der
        // BKW-Helper liest `leistung_wp`/`anzahl`, ein PV-Modul führt aber
        // `anzahl_module`/`modul_leistung_wp` — die Zeile blieb deshalb leer.
        // kWp als ANZEIGE-Wert über `leistung_kwp_effektiv` (A26/N106), sonst
        // fehlt sie bei Import-/Altbestand mit kWp nur im `parameter` (#229).
        const p = pvModuleParameter(investition.parameter)
        if (investition.leistung_kwp_effektiv != null) {
          details.push(`${fmtZahl(investition.leistung_kwp_effektiv, 1)} kWp`)
        }
        if (p.anzahl_module) details.push(`${p.anzahl_module} Module`)
        if (p.modul_leistung_wp) details.push(`${p.modul_leistung_wp} Wp`)
        break
      }
      case 'balkonkraftwerk': {
        const p = balkonkraftwerkParameter(investition.parameter)
        if (p.leistung_wp) details.push(`${p.leistung_wp} Wp`)
        if (p.anzahl) details.push(`${p.anzahl} Module`)
        break
      }
    }

    return details
  }

  const details = getDetails()
  const kosten = investition.anschaffungskosten_gesamt
  // Lokales Datum (F-5): mit dem UTC-Datum galt eine zum heutigen Tag
  // stillgelegte Komponente nachts noch als aktiv.
  const heute = heuteIso()
  const istStillgelegt = !!investition.stilllegungsdatum && investition.stilllegungsdatum <= heute
  const istAktiv = investition.aktiv && !istStillgelegt

  return (
    <div className={`
      flex items-center justify-between p-3 rounded-lg border
      ${istAktiv
        ? 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
        : 'bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 opacity-60'
      }
    `}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-medium text-gray-900 dark:text-white truncate">
            {investition.bezeichnung}
          </p>
          {istStillgelegt && (
            <span className="text-xs px-2 py-0.5 bg-amber-100 dark:bg-amber-900/40 rounded text-amber-700 dark:text-amber-300" title={`Stillgelegt seit ${formatDatum(investition.stilllegungsdatum)}`}>
              Stillgelegt
            </span>
          )}
          {!investition.aktiv && !istStillgelegt && (
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
              {fmtZahl(kosten, 0)} €
            </span>
          )}
          {investition.anschaffungsdatum && (
            <span>
              seit {formatDatum(investition.anschaffungsdatum)}
            </span>
          )}
        </div>
        {/* Komponenten-Akte: kontextabhängiger Button */}
        <div className="flex items-center gap-1 mt-1 text-xs">
          {infothekEintraege.length === 0 ? (
            <InlineAktion onClick={() => setShowCreateModal(true)} ton="hinweis" title="Komponenten-Akte anlegen">
              <FileText className="h-3 w-3" />
              Komponenten-Akte anlegen
            </InlineAktion>
          ) : infothekEintraege.length === 1 ? (
            <a
              href={`#/einstellungen/infothek`}
              className="flex items-center gap-1 text-primary-600 dark:text-primary-400 hover:underline"
              title={infothekEintraege[0].bezeichnung}
            >
              <FileText className="h-3 w-3" />
              {infothekEintraege[0].bezeichnung}
            </a>
          ) : (
            <div className="relative">
              <InlineAktion onClick={() => setShowDropdown(!showDropdown)} ton="aktion" ariaExpanded={showDropdown}>
                <FileText className="h-3 w-3" />
                {infothekEintraege.length} Komponenten-Akten
                <ChevronDown className="h-3 w-3" />
              </InlineAktion>
              {showDropdown && (
                <div className="absolute left-0 top-full mt-1 z-10 bg-gray-800 border border-gray-600 rounded-lg shadow-lg py-1 min-w-48">
                  {infothekEintraege.map(e => (
                    <a
                      key={e.id}
                      href={`#/einstellungen/infothek`}
                      className="block px-3 py-1.5 text-sm text-gray-200 hover:bg-gray-700"
                    >
                      {e.bezeichnung}
                    </a>
                  ))}
                  <hr className="border-gray-600 my-1" />
                  <button
                    onClick={() => { setShowDropdown(false); setShowCreateModal(true) }}
                    className="block w-full text-left px-3 py-1.5 text-sm text-amber-400 hover:bg-gray-700"
                  >
                    + Weitere verknüpfen
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1 ml-4">
        <Button variant="ghost" size="icon" onClick={onEdit} title="Bearbeiten" className="hover:text-primary-600 dark:hover:text-primary-400">
          <Pencil className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" onClick={onDelete} title="Löschen" className="hover:text-red-600 dark:hover:text-red-400">
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>

      {/* Quick-Create Modal für Komponenten-Akte */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Komponenten-Akte anlegen"
        size="lg"
      >
        <InfothekForm
          eintrag={null}
          anlageId={investition.anlage_id}
          initialKategorie="garantie"
          initialInvestitionIds={[investition.id]}
          onSubmit={async (data) => {
            await infothekApi.create(data as InfothekEintragCreate)
            setShowCreateModal(false)
            refreshInfothek()
          }}
          onCancel={() => setShowCreateModal(false)}
        />
      </Modal>
    </div>
  )
}
