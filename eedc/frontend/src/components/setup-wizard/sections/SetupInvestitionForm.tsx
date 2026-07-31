import { useState, useEffect } from 'react'
import { Trash2, ChevronDown, ChevronRight } from 'lucide-react'
import { Button, Input, Select, Alert, DatumFeld } from '../../ui'
import { SchalterZeile } from '../../forms/sections/SchalterZeile'
import type { Investition } from '../../../types'
import {
  PARENT_REQUIRED,
  PARENT_TYPE_LABELS,
  parentTypenFuer,
} from '../../forms/sections/investitionFormHelpers'
import { TYP_LABELS as INVESTITION_TYP_LABELS } from '../../../lib/constants'
import {
  PARAM_E_AUTO,
  PARAM_SPEICHER,
  PARAM_WAERMEPUMPE,
  PARAM_WALLBOX,
  PARAM_WECHSELRICHTER,
  PARAM_BALKONKRAFTWERK,
  PARAM_WAERMEPUMPE_DEFAULTS,
} from '../../../lib'
import { getDeviceIcon, PV_AUSRICHTUNG_OPTIONEN, BKW_AUSRICHTUNG_OPTIONEN } from './setupInvestitionHelpers'

/**
 * SetupInvestitionForm — aufklappbarer Editor EINER Investition im Setup-Wizard
 * (ausgelagert aus InvestitionenStep, Slice 6). Bewusst **reduzierter** Feldsatz
 * (Setup ≠ voller Modal-Form) + Live-Update pro Feld ([[feedback_ist_anzeigen_nur_aendern_wo_noetig]]).
 * Controls = SoT; Paket F (2026-07-17): Lösch-Aktionen auf `Button`-SoT, nur der
 * Aufklapp-Header bleibt rohes Struktur-Element (ROH_INFRA).
 */
export function SetupInvestitionForm({
  investition,
  allInvestitionen,
  onUpdate,
  onDelete,
  isNew = false,
}: {
  investition: Investition
  allInvestitionen: Investition[]
  onUpdate: (data: Partial<Investition>) => void
  onDelete: () => void
  isNew?: boolean
}) {
  const [expanded, setExpanded] = useState<boolean>(true)
  useEffect(() => { if (isNew) setExpanded(true) }, [isNew])
  const [confirmDelete, setConfirmDelete] = useState(false)

  // Mehrere Parent-Typen sind möglich (Speicher: Wechselrichter ODER
  // Balkonkraftwerk — der BKW-Akku ist genau dieser Fall). SoT ist
  // `parentTypenFuer`; der Wizard hatte dafür eine eigene, kürzere Kopie.
  const parentTypen = parentTypenFuer(investition.typ)
  const parentLabel = parentTypen.map(t => PARENT_TYPE_LABELS[t] || t).join(' / ')
  const possibleParents = parentTypen.length
    ? allInvestitionen.filter(i => parentTypen.includes(i.typ) && i.id !== investition.id)
    : []

  const getParam = (key: string) => investition.parameter?.[key] as number | string | undefined
  const getBoolParam = (key: string) => investition.parameter?.[key] === true
  const updateParam = (key: string, value: unknown) => {
    onUpdate({ parameter: { ...investition.parameter, [key]: value } })
  }
  const num = (v: string): number | undefined => parseFloat(v) || undefined

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden bg-white dark:bg-gray-800">
      {/* Header - klickbar zum Auf-/Zuklappen (amber-Theme bleibt). Disclosure-
          Struktur-Element: rohes <button> = Impl (ROH_INFRA-Freigabe Gernot
          2026-07-17, Paket F — Gattung BlockShell-Aufklapp-Kopf). */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
      >
        <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 rounded-lg flex items-center justify-center text-amber-600 dark:text-amber-400 flex-shrink-0">
          {getDeviceIcon(investition.typ)}
        </div>
        <div className="flex-1 text-left min-w-0">
          <div className="font-medium text-gray-900 dark:text-white truncate">
            {investition.bezeichnung || INVESTITION_TYP_LABELS[investition.typ]}
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">
            {INVESTITION_TYP_LABELS[investition.typ]}
            {investition.anschaffungskosten_gesamt ? (
              <span className="ml-2">• {investition.anschaffungskosten_gesamt.toLocaleString('de-DE')} €</span>
            ) : null}
          </div>
        </div>
        {expanded
          ? <ChevronDown className="w-5 h-5 text-gray-400 dark:text-gray-500 flex-shrink-0" />
          : <ChevronRight className="w-5 h-5 text-gray-400 dark:text-gray-500 flex-shrink-0" />}
      </button>

      {expanded && (
        <div className="p-4 pt-0 space-y-4 border-t border-gray-100 dark:border-gray-700">
          {/* Basis-Felder */}
          <div className="grid md:grid-cols-2 gap-4 items-start">
            <div className="md:col-span-2">
              <Input
                label="Bezeichnung"
                required
                value={investition.bezeichnung}
                onChange={(e) => onUpdate({ bezeichnung: e.target.value })}
                placeholder="z.B. SMA Sunny Tripower"
              />
            </div>
            <DatumFeld
              label="Anschaffungsdatum"
              required
              value={investition.anschaffungsdatum || ''}
              // `null` statt `undefined`: sonst fällt der Schlüssel aus dem JSON und das
              // Backend behält (exclude_unset) den alten Wert — Leeren wäre unmöglich.
              onChange={(v) => onUpdate({ anschaffungsdatum: v || null })}
            />
            <Input
              label="Kaufpreis (€)"
              required
              type="number" min="0" step="any"
              value={investition.anschaffungskosten_gesamt ?? ''}
              onChange={(e) => onUpdate({ anschaffungskosten_gesamt: parseFloat(e.target.value) || 0 })}
              placeholder="z.B. 5000"
            />
          </div>

          {/* Parent-Zuordnung */}
          {parentTypen.length > 0 && (() => {
            const isRequired = PARENT_REQUIRED.includes(investition.typ)
            const hasParents = possibleParents.length > 0
            const missingParent = isRequired && !investition.parent_investition_id && hasParents
            const label = `Gehört zu (${parentLabel})${isRequired ? '' : ' (optional)'}`
            return hasParents ? (
              <Select
                label={label}
                required={isRequired}
                value={investition.parent_investition_id ? String(investition.parent_investition_id) : ''}
                onChange={(e) => onUpdate({ parent_investition_id: e.target.value ? parseInt(e.target.value) : null })}
                placeholder={isRequired ? '-- Bitte wählen --' : '-- Keine Zuordnung --'}
                options={possibleParents.map(p => ({
                  value: String(p.id),
                  // Bei mehreren erlaubten Parent-Typen muss die Zeile sagen,
                  // WAS sie ist — sonst stehen Wechselrichter und
                  // Balkonkraftwerk namenlos untereinander.
                  label: parentTypen.length > 1
                    ? `${p.bezeichnung} (${INVESTITION_TYP_LABELS[p.typ]})`
                    : p.bezeichnung,
                }))}
                error={missingParent ? 'PV-Module müssen einem Wechselrichter zugeordnet werden' : undefined}
              />
            ) : (
              <Alert type="warning">
                {isRequired ? (
                  <>Bitte legen Sie zuerst einen <strong>Wechselrichter</strong> an, bevor Sie PV-Module zuordnen können.</>
                ) : (
                  <>Kein {parentLabel} vorhanden. Zuordnung ist optional.</>
                )}
              </Alert>
            )
          })()}

          {/* Typ-spezifische Felder (reduzierter Setup-Satz) */}
          {investition.typ === 'wechselrichter' && (
            <div className="grid md:grid-cols-2 gap-4 items-start">
              <Input
                label="Max. Leistung (kW)" required
                type="number" min="0" step="any"
                value={getParam(PARAM_WECHSELRICHTER.MAX_LEISTUNG_KW) ?? ''}
                onChange={(e) => updateParam(PARAM_WECHSELRICHTER.MAX_LEISTUNG_KW, num(e.target.value))}
                placeholder="z.B. 10"
              />
            </div>
          )}

          {investition.typ === 'pv-module' && (
            <div className="grid md:grid-cols-2 gap-4 items-start">
              <Input
                label="Leistung (kWp)" required
                type="number" min="0" step="0.01"
                value={investition.leistung_kwp ?? ''}
                onChange={(e) => onUpdate({ leistung_kwp: num(e.target.value) })}
                placeholder="z.B. 10"
              />
              <Select
                label="Ausrichtung" required
                value={investition.ausrichtung || ''}
                onChange={(e) => onUpdate({ ausrichtung: e.target.value || undefined })}
                placeholder="-- Wählen --"
                options={PV_AUSRICHTUNG_OPTIONEN}
              />
              <Input
                label="Neigung (Grad)" required
                type="number" min="0" max="90" step="1"
                value={investition.neigung_grad ?? ''}
                onChange={(e) => onUpdate({ neigung_grad: num(e.target.value) })}
                placeholder="z.B. 35"
              />
            </div>
          )}

          {investition.typ === 'speicher' && (
            <div className="grid md:grid-cols-2 gap-4 items-start">
              <Input
                label="Kapazität (kWh)" required
                type="number" min="0" step="any"
                value={getParam(PARAM_SPEICHER.KAPAZITAET_KWH) ?? ''}
                onChange={(e) => updateParam(PARAM_SPEICHER.KAPAZITAET_KWH, num(e.target.value))}
                placeholder="z.B. 10"
              />
              <div className="flex items-center">
                <SchalterZeile
                  checked={getBoolParam(PARAM_SPEICHER.ARBITRAGE_FAEHIG)}
                  onChange={(an) => updateParam(PARAM_SPEICHER.ARBITRAGE_FAEHIG, an)}
                  label="Arbitrage"
                  hint="Netzstrom günstig laden, teuer einspeisen"
                />
              </div>
            </div>
          )}

          {investition.typ === 'wallbox' && (
            <div className="grid md:grid-cols-2 gap-4 items-start">
              <Input
                label="Max. Ladeleistung (kW)" required
                type="number" min="0" step="any"
                value={getParam(PARAM_WALLBOX.MAX_LADELEISTUNG_KW) ?? ''}
                onChange={(e) => updateParam(PARAM_WALLBOX.MAX_LADELEISTUNG_KW, num(e.target.value))}
                placeholder="z.B. 11"
              />
              <div className="flex items-center">
                <SchalterZeile
                  checked={getBoolParam(PARAM_WALLBOX.BIDIREKTIONAL)}
                  onChange={(an) => updateParam(PARAM_WALLBOX.BIDIREKTIONAL, an)}
                  label="Bidirektional"
                  hint="Bidirektionales Laden (Vehicle-to-Home)"
                />
              </div>
            </div>
          )}

          {investition.typ === 'e-auto' && (
            <div className="grid md:grid-cols-2 gap-4 items-start">
              <Input
                label="Batteriekapazität (kWh)" required
                type="number" min="0" step="any"
                value={getParam(PARAM_E_AUTO.BATTERIE_KAPAZITAET_KWH) ?? ''}
                onChange={(e) => updateParam(PARAM_E_AUTO.BATTERIE_KAPAZITAET_KWH, num(e.target.value))}
                placeholder="z.B. 66"
              />
              <Input
                label="Verbrauch (kWh/100km)" required
                type="number" min="0" step="any"
                value={getParam(PARAM_E_AUTO.VERBRAUCH_KWH_100KM) ?? ''}
                onChange={(e) => updateParam(PARAM_E_AUTO.VERBRAUCH_KWH_100KM, num(e.target.value))}
                placeholder="z.B. 15"
              />
              <div className="md:col-span-2 flex items-center">
                <SchalterZeile
                  checked={getBoolParam(PARAM_E_AUTO.V2H_FAEHIG)}
                  onChange={(an) => updateParam(PARAM_E_AUTO.V2H_FAEHIG, an)}
                  label="V2H-fähig"
                  hint="Fahrzeug kann Strom ans Haus abgeben (Vehicle-to-Home)"
                />
              </div>
            </div>
          )}

          {investition.typ === 'waermepumpe' && (
            <div className="grid md:grid-cols-2 gap-4 items-start">
              <Input
                label="Nennleistung (kW)" required
                type="number" min="0" step="any"
                value={getParam(PARAM_WAERMEPUMPE.LEISTUNG_KW) ?? ''}
                onChange={(e) => updateParam(PARAM_WAERMEPUMPE.LEISTUNG_KW, num(e.target.value))}
                placeholder="z.B. 9"
              />
              <Input
                label="Jahresarbeitszahl (JAZ)" required
                type="number" min="1" max="10" step="any"
                value={getParam(PARAM_WAERMEPUMPE.JAZ) ?? PARAM_WAERMEPUMPE_DEFAULTS.jaz.toString()}
                onChange={(e) => onUpdate({
                  parameter: {
                    ...investition.parameter,
                    [PARAM_WAERMEPUMPE.JAZ]: num(e.target.value),
                    [PARAM_WAERMEPUMPE.EFFIZIENZ_MODUS]: PARAM_WAERMEPUMPE_DEFAULTS.effizienz_modus,
                  },
                })}
                placeholder="z.B. 3.5"
              />
            </div>
          )}

          {investition.typ === 'balkonkraftwerk' && (
            <div className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4 items-start">
                <Input
                  label="Leistung pro Modul (Wp)" required
                  type="number" min="0" step="any"
                  value={getParam(PARAM_BALKONKRAFTWERK.LEISTUNG_WP) ?? ''}
                  onChange={(e) => updateParam(PARAM_BALKONKRAFTWERK.LEISTUNG_WP, num(e.target.value))}
                  placeholder="z.B. 400"
                />
                <Input
                  label="Anzahl Module" required
                  type="number" min="1" step="1"
                  value={getParam(PARAM_BALKONKRAFTWERK.ANZAHL) ?? ''}
                  onChange={(e) => updateParam(PARAM_BALKONKRAFTWERK.ANZAHL, parseInt(e.target.value) || undefined)}
                  placeholder="z.B. 2"
                />
                <Select
                  label="Ausrichtung" required
                  value={(getParam(PARAM_BALKONKRAFTWERK.AUSRICHTUNG) as string) || ''}
                  onChange={(e) => updateParam(PARAM_BALKONKRAFTWERK.AUSRICHTUNG, e.target.value || undefined)}
                  placeholder="-- Wählen --"
                  options={BKW_AUSRICHTUNG_OPTIONEN}
                />
                <Input
                  label="Neigung (Grad)" required
                  type="number" min="0" max="90" step="1"
                  value={getParam(PARAM_BALKONKRAFTWERK.NEIGUNG_GRAD) ?? ''}
                  onChange={(e) => updateParam(PARAM_BALKONKRAFTWERK.NEIGUNG_GRAD, num(e.target.value))}
                  placeholder="z.B. 30"
                  hint="0° = flach, 90° = senkrecht (Balkon)"
                />
                {/* #347: ohne die AC-Grenze rechnet die Prognose mit der vollen
                    Modulleistung — Überbelegung ist beim BKW der Normalfall. */}
                <Input
                  label="Wechselrichter-Leistung (W)"
                  type="number" min="0" step="1"
                  value={getParam(PARAM_BALKONKRAFTWERK.WECHSELRICHTER_LEISTUNG_W) ?? ''}
                  onChange={(e) => updateParam(PARAM_BALKONKRAFTWERK.WECHSELRICHTER_LEISTUNG_W, num(e.target.value))}
                  placeholder="z.B. 800"
                  hint="Begrenzt die Einspeisung; leer = keine Begrenzung"
                />
              </div>

              <div className="border-t border-gray-200 dark:border-gray-700 pt-4 space-y-3">
                <SchalterZeile
                  checked={getBoolParam(PARAM_BALKONKRAFTWERK.HAT_SPEICHER)}
                  onChange={(an) => updateParam(PARAM_BALKONKRAFTWERK.HAT_SPEICHER, an)}
                  label="Mit Speicher"
                  hint="z.B. Anker SOLIX, Zendure, EcoFlow"
                />
                {getBoolParam(PARAM_BALKONKRAFTWERK.HAT_SPEICHER) && (
                  <div className="ml-8 max-w-xs">
                    <Input
                      label="Speicher-Kapazität (Wh)" required
                      type="number" min="0" step="any"
                      value={getParam(PARAM_BALKONKRAFTWERK.SPEICHER_KAPAZITAET_WH) ?? ''}
                      onChange={(e) => updateParam(PARAM_BALKONKRAFTWERK.SPEICHER_KAPAZITAET_WH, num(e.target.value))}
                      placeholder="z.B. 1600"
                      hint="z.B. 1600 Wh für Anker SOLIX"
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Löschen — Button-SoT; Bestätigungs-Reihe im Abbrechen-Kanon
              [Abbrechen secondary][destruktiv danger] (D19-6). */}
          <div className="pt-2 border-t border-gray-100 dark:border-gray-700">
            {confirmDelete ? (
              <div className="flex items-center gap-3">
                <span className="text-sm text-red-600 dark:text-red-400">Wirklich löschen?</span>
                <Button type="button" variant="secondary" size="sm" onClick={() => setConfirmDelete(false)}>
                  Abbrechen
                </Button>
                <Button type="button" variant="danger" size="sm" onClick={() => { onDelete(); setConfirmDelete(false) }}>
                  Ja, löschen
                </Button>
              </div>
            ) : (
              <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmDelete(true)}>
                <Trash2 className="w-4 h-4 mr-2" />
                Investition löschen
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
