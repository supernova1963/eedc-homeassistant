/**
 * Dynamisches Monatsdatenformular
 * Zeigt Felder basierend auf den vorhandenen Investitionen der Anlage an.
 */

import { useState, useEffect, useMemo, FormEvent } from 'react'
import { Button, Input, Alert, Select } from '../ui'
import { useInvestitionen, useAktuellerStrompreis } from '../../hooks'
import { investitionenApi, wetterApi } from '../../api'
import type { Monatsdaten } from '../../types'
import { getFelderFuerInvestition, LEGACY_FELDNAMEN } from '../../lib/fieldDefinitions'
import { Plug, Sun, Flame, Cloud, Loader2, Battery, Car, Zap, MoreHorizontal } from 'lucide-react'
import { InvestitionSection } from './sections/InvestitionSection'
import type { SonstigePosition } from './sections/types'

interface MonatsdatenFormProps {
  monatsdaten?: Monatsdaten | null
  anlageId: number
  onSubmit: (data: MonatsdatenSubmitData) => Promise<void>
  onCancel: () => void
  /** Vorausgefüllte Werte aus HA-Statistik */
  haVorausfuellung?: {
    jahr: number
    monat: number
    monat_name: string
    basis: Array<{ feld: string; wert: number | null; sensor_id?: string }>
    investitionen: Array<{
      investition_id: number
      bezeichnung: string
      typ: string
      felder: Array<{ feld: string; wert: number | null; sensor_id?: string }>
    }>
  } | null
}

export interface MonatsdatenSubmitData {
  anlage_id: number
  jahr: number
  monat: number
  einspeisung_kwh: number
  netzbezug_kwh: number
  pv_erzeugung_kwh?: number
  batterie_ladung_kwh?: number
  batterie_entladung_kwh?: number
  netzbezug_durchschnittspreis_cent?: number
  kraftstoffpreis_euro?: number
  gaspreis_cent_kwh?: number
  globalstrahlung_kwh_m2?: number
  sonnenstunden?: number
  durchschnittstemperatur?: number
  sonderkosten_euro?: number
  sonderkosten_beschreibung?: string
  notizen?: string
  // Investitions-spezifische Daten
  investitionen_daten?: Record<string, InvestitionMonatsdaten>
}

interface InvestitionMonatsdaten {
  // E-Auto
  km_gefahren?: number
  verbrauch_kwh?: number
  ladung_pv_kwh?: number
  ladung_netz_kwh?: number
  ladung_extern_kwh?: number       // Externe Ladung (Autobahn, Arbeit, etc.)
  ladung_extern_euro?: number      // Kosten externe Ladung
  entladung_v2h_kwh?: number
  // Speicher
  ladung_kwh?: number
  entladung_kwh?: number
  speicher_ladung_netz_kwh?: number // Arbitrage: Laden aus Netz
  speicher_ladepreis_cent?: number  // Arbitrage: Ø Ladepreis
  // Wallbox - nutzt E-Auto Heim-Ladung (ladung_pv_kwh + ladung_netz_kwh)
  ladevorgaenge?: number
  // Wärmepumpe
  stromverbrauch_kwh?: number
  strom_heizen_kwh?: number
  strom_warmwasser_kwh?: number
  heizenergie_kwh?: number
  warmwasser_kwh?: number
  // Wechselrichter / PV-Module
  pv_erzeugung_kwh?: number
  // Balkonkraftwerk / Sonstiges Erzeuger
  erzeugung_kwh?: number
  eigenverbrauch_kwh?: number
  einspeisung_kwh?: number
  // Balkonkraftwerk Speicher
  speicher_ladung_kwh?: number
  speicher_entladung_kwh?: number
  // Sonstiges (Verbraucher)
  verbrauch_sonstig_kwh?: number
  bezug_pv_kwh?: number
  bezug_netz_kwh?: number
  // Sonstige Positionen (für alle Investitionstypen)
  sonstige_positionen?: SonstigePosition[]
}

// SonstigePosition wird aus ./sections/types importiert

const monatOptions = [
  { value: '1', label: 'Januar' },
  { value: '2', label: 'Februar' },
  { value: '3', label: 'März' },
  { value: '4', label: 'April' },
  { value: '5', label: 'Mai' },
  { value: '6', label: 'Juni' },
  { value: '7', label: 'Juli' },
  { value: '8', label: 'August' },
  { value: '9', label: 'September' },
  { value: '10', label: 'Oktober' },
  { value: '11', label: 'November' },
  { value: '12', label: 'Dezember' },
]

export default function MonatsdatenForm({ monatsdaten, anlageId, onSubmit, onCancel, haVorausfuellung }: MonatsdatenFormProps) {
  const currentYear = new Date().getFullYear()
  const currentMonth = new Date().getMonth() + 1

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Investitionen für diese Anlage laden (nur aktive)
  const { investitionen, loading: invLoading } = useInvestitionen(anlageId)
  const aktiveInvestitionen = useMemo(
    () => investitionen.filter(i => i.aktiv),
    [investitionen]
  )

  // Strompreis für dynamischen Tarif prüfen
  const { strompreis } = useAktuellerStrompreis(anlageId)
  const hatDynamischenTarif = strompreis?.vertragsart === 'dynamisch'

  // Welche Investitionstypen sind vorhanden?
  const hatSpeicher = aktiveInvestitionen.some(i => i.typ === 'speicher')
  const hatEAuto = aktiveInvestitionen.some(i => i.typ === 'e-auto')
  const hatWallbox = aktiveInvestitionen.some(i => i.typ === 'wallbox')
  const hatWaermepumpe = aktiveInvestitionen.some(i => i.typ === 'waermepumpe')
  const hatWechselrichter = aktiveInvestitionen.some(i => i.typ === 'wechselrichter')
  const hatPVModule = aktiveInvestitionen.some(i => i.typ === 'pv-module')
  const hatBalkonkraftwerk = aktiveInvestitionen.some(i => i.typ === 'balkonkraftwerk')
  const hatSonstiges = aktiveInvestitionen.some(i => i.typ === 'sonstiges')

  // Hilfsfunktion um HA-Basiswert zu finden
  const getHaBasisWert = (feld: string): string => {
    if (!haVorausfuellung) return ''
    const found = haVorausfuellung.basis.find(b => b.feld === feld)
    return found?.wert !== null && found?.wert !== undefined ? found.wert.toString() : ''
  }

  // Basis-Formulardaten
  const [formData, setFormData] = useState({
    jahr: haVorausfuellung?.jahr?.toString() || monatsdaten?.jahr?.toString() || currentYear.toString(),
    monat: haVorausfuellung?.monat?.toString() || monatsdaten?.monat?.toString() || currentMonth.toString(),
    einspeisung_kwh: getHaBasisWert('einspeisung') || monatsdaten?.einspeisung_kwh?.toString() || '',
    netzbezug_kwh: getHaBasisWert('netzbezug') || monatsdaten?.netzbezug_kwh?.toString() || '',
    pv_erzeugung_kwh: monatsdaten?.pv_erzeugung_kwh?.toString() || '',
    batterie_ladung_kwh: monatsdaten?.batterie_ladung_kwh?.toString() || '',
    batterie_entladung_kwh: monatsdaten?.batterie_entladung_kwh?.toString() || '',
    globalstrahlung_kwh_m2: monatsdaten?.globalstrahlung_kwh_m2?.toString() || '',
    sonnenstunden: monatsdaten?.sonnenstunden?.toString() || '',
    durchschnittstemperatur: monatsdaten?.durchschnittstemperatur?.toString() || '',
    netzbezug_durchschnittspreis_cent: monatsdaten?.netzbezug_durchschnittspreis_cent?.toString() || '',
    kraftstoffpreis_euro: monatsdaten?.kraftstoffpreis_euro?.toString() || '',
    gaspreis_cent_kwh: monatsdaten?.gaspreis_cent_kwh?.toString() || '',
    sonderkosten_euro: monatsdaten?.sonderkosten_euro?.toString() || '',
    sonderkosten_beschreibung: monatsdaten?.sonderkosten_beschreibung || '',
    notizen: monatsdaten?.notizen || '',
  })

  // Wetter-Daten Auto-Fill
  const [wetterLoading, setWetterLoading] = useState(false)
  const [wetterInfo, setWetterInfo] = useState<string | null>(null)

  // Investitions-spezifische Daten
  const [investitionsDaten, setInvestitionsDaten] = useState<Record<string, Record<string, string>>>({})
  // Sonstige Positionen (Erträge & Ausgaben) pro Investition
  const [sonstigePositionen, setSonstigePositionen] = useState<Record<string, SonstigePosition[]>>({})
  const [loadingInvData, setLoadingInvData] = useState(false)

  // Initialisiere Investitions-Daten und lade vorhandene Daten beim Bearbeiten
  useEffect(() => {
    if (aktiveInvestitionen.length === 0) return

    const initializeAndLoad = async () => {
      // Initialisiere mit leeren Werten
      const initial: Record<string, Record<string, string>> = {}
      // Generische Initialisierung aus field_definitions (E3)
      aktiveInvestitionen.forEach(inv => {
        const felder = getFelderFuerInvestition(inv.typ, inv.parameter)
        const init: Record<string, string> = {}
        felder.forEach(f => { init[f.feld] = '' })
        initial[inv.id] = init
      })

      // Sonstige Positionen aus existierenden Daten laden
      const loadedPositionen: Record<string, SonstigePosition[]> = {}

      // Beim Bearbeiten: Lade vorhandene InvestitionMonatsdaten
      if (monatsdaten?.jahr && monatsdaten?.monat) {
        setLoadingInvData(true)
        try {
          const existingData = await investitionenApi.getMonatsdatenByMonth(
            anlageId,
            monatsdaten.jahr,
            monatsdaten.monat
          )

          // Merge vorhandene Daten in initial
          existingData.forEach(imd => {
            // investition_id kann als Zahl oder String kommen, initial verwendet String-Keys
            const invIdStr = String(imd.investition_id)

            // Sonstige Positionen extrahieren (neues Format oder Legacy-Migration)
            const vd = imd.verbrauch_daten as Record<string, unknown> | undefined
            if (vd?.sonstige_positionen) {
              loadedPositionen[invIdStr] = vd.sonstige_positionen as SonstigePosition[]
            } else if (vd?.sonderkosten_euro && Number(vd.sonderkosten_euro) > 0) {
              loadedPositionen[invIdStr] = [{
                bezeichnung: String(vd.sonderkosten_notiz || 'Sonderkosten (migriert)'),
                betrag: Number(vd.sonderkosten_euro),
                typ: 'ausgabe' as const,
              }]
            }

            if (initial[invIdStr] && imd.verbrauch_daten) {
              // Generisches Laden: kanonische + Legacy-Feldnamen (E3)
              const skipKeys = new Set(['sonstige_positionen', 'sonderkosten_euro', 'sonderkosten_notiz'])
              Object.entries(imd.verbrauch_daten).forEach(([key, value]) => {
                if (skipKeys.has(key)) return
                const val = value?.toString() || ''
                // Direkter Match mit kanonischem Namen
                if (initial[invIdStr][key] !== undefined) {
                  initial[invIdStr][key] = val
                  return
                }
                // Legacy-Key → kanonischer Name (z.B. entladung_v2h_kwh → v2h_entladung_kwh)
                const canonical = LEGACY_FELDNAMEN[key]
                if (canonical && initial[invIdStr][canonical] !== undefined) {
                  initial[invIdStr][canonical] = val
                  return
                }
                // Typ-spezifische Legacy-Fallbacks (vor Einführung kanonischer Namen)
                if (key === 'erzeugung_kwh' && initial[invIdStr]['pv_erzeugung_kwh'] !== undefined) {
                  initial[invIdStr]['pv_erzeugung_kwh'] = val  // BKW: alt erzeugung_kwh → pv_erzeugung_kwh
                }
                if (key === 'verbrauch_kwh' && initial[invIdStr]['verbrauch_sonstig_kwh'] !== undefined) {
                  initial[invIdStr]['verbrauch_sonstig_kwh'] = val  // Sonstiges: alt verbrauch_kwh → verbrauch_sonstig_kwh
                }
              })
            }
          })

          // =================================================================
          // Auto-Migration: Legacy Monatsdaten.batterie_* → InvestitionMonatsdaten
          // Wenn Speicher-Investitionen existieren, aber keine InvestitionMonatsdaten
          // für sie vorhanden sind UND Legacy-Daten in Monatsdaten existieren,
          // dann übernehme die Legacy-Daten in die Speicher-Investitionsfelder.
          // =================================================================
          const speicherInvs = aktiveInvestitionen.filter(i => i.typ === 'speicher')
          const speicherMdIds = new Set(existingData.filter(imd =>
            speicherInvs.some(s => s.id === imd.investition_id)
          ).map(imd => imd.investition_id))

          // Prüfe ob Legacy-Daten existieren
          const legacyLadung = monatsdaten?.batterie_ladung_kwh || 0
          const legacyEntladung = monatsdaten?.batterie_entladung_kwh || 0

          if (speicherInvs.length > 0 && (legacyLadung > 0 || legacyEntladung > 0)) {
            // Finde Speicher ohne InvestitionMonatsdaten
            const speicherOhneDaten = speicherInvs.filter(s => !speicherMdIds.has(s.id))

            if (speicherOhneDaten.length > 0) {
              // Verteile Legacy-Daten auf Speicher ohne Daten
              // Bei mehreren Speichern: gleichmäßig verteilen (vereinfachte Annahme)
              const anteil = 1 / speicherOhneDaten.length
              speicherOhneDaten.forEach(speicher => {
                const invIdStr = String(speicher.id)
                if (initial[invIdStr]) {
                  initial[invIdStr].ladung_kwh = (legacyLadung * anteil).toFixed(1)
                  initial[invIdStr].entladung_kwh = (legacyEntladung * anteil).toFixed(1)
                }
              })
            }
          }
        } catch (e) {
          // Fehler stillschweigend ignoriert
        } finally {
          setLoadingInvData(false)
        }
      }

      // =================================================================
      // HA-Vorausfüllung: Werte aus HA-Statistik einfügen
      // =================================================================
      // HA-Vorausfüllung: generisch per Feld-Key (E3)
      if (haVorausfuellung?.investitionen) {
        haVorausfuellung.investitionen.forEach(haInv => {
          const invIdStr = String(haInv.investition_id)
          if (!initial[invIdStr]) return
          haInv.felder.forEach(({ feld, wert }) => {
            if (wert !== null && wert !== undefined && initial[invIdStr][feld] !== undefined) {
              initial[invIdStr][feld] = wert.toString()
            }
          })
        })
      }

      setInvestitionsDaten(initial)
      if (Object.keys(loadedPositionen).length > 0) {
        setSonstigePositionen(loadedPositionen)
      }
    }

    initializeAndLoad()
  }, [aktiveInvestitionen, monatsdaten?.jahr, monatsdaten?.monat, anlageId, haVorausfuellung])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleInvChange = (invId: number, field: string, value: string) => {
    setInvestitionsDaten(prev => ({
      ...prev,
      [invId]: {
        ...prev[invId],
        [field]: value,
      },
    }))
  }

  const handlePositionenChange = (invId: number, positionen: SonstigePosition[]) => {
    setSonstigePositionen(prev => ({ ...prev, [String(invId)]: positionen }))
  }

  // Berechne Summen aus den einzelnen Investitionen
  const berechneteWerte = useMemo(() => {
    let batterieLadung = 0
    let batterieEntladung = 0
    let pvErzeugung = 0

    aktiveInvestitionen.forEach(inv => {
      const daten = investitionsDaten[inv.id]
      if (!daten) return

      if (inv.typ === 'speicher') {
        batterieLadung += parseFloat(daten.ladung_kwh) || 0
        batterieEntladung += parseFloat(daten.entladung_kwh) || 0
      } else if (inv.typ === 'pv-module' || inv.typ === 'wechselrichter' || inv.typ === 'balkonkraftwerk') {
        // PV-Erzeugung aus allen Quellen summieren
        pvErzeugung += parseFloat(daten.pv_erzeugung_kwh) || 0
        // Balkonkraftwerk mit Speicher
        if (inv.typ === 'balkonkraftwerk' && inv.parameter?.hat_speicher) {
          batterieLadung += parseFloat(daten.speicher_ladung_kwh) || 0
          batterieEntladung += parseFloat(daten.speicher_entladung_kwh) || 0
        }
      } else if (inv.typ === 'sonstiges' && inv.parameter?.kategorie === 'erzeuger') {
        // Sonstige Erzeuger zur PV-Erzeugung addieren
        pvErzeugung += parseFloat(daten.erzeugung_kwh) || 0
      }
    })

    return { batterieLadung, batterieEntladung, pvErzeugung }
  }, [aktiveInvestitionen, investitionsDaten])

  // Wetterdaten automatisch abrufen
  const fetchWetterdaten = async () => {
    if (!formData.jahr || !formData.monat) {
      setError('Bitte zuerst Jahr und Monat auswählen')
      return
    }

    setWetterLoading(true)
    setWetterInfo(null)
    setError(null)

    try {
      const data = await wetterApi.getMonatsdaten(
        anlageId,
        parseInt(formData.jahr),
        parseInt(formData.monat)
      )

      setFormData(prev => ({
        ...prev,
        globalstrahlung_kwh_m2: data.globalstrahlung_kwh_m2.toString(),
        sonnenstunden: data.sonnenstunden.toString(),
      }))

      // Info-Text über Datenquelle
      const quellenText = data.datenquelle === 'open-meteo'
        ? `Historische Daten von Open-Meteo${data.abdeckung_prozent ? ` (${data.abdeckung_prozent}% Abdeckung)` : ''}`
        : data.datenquelle === 'pvgis-tmy'
        ? 'Durchschnittswerte von PVGIS (TMY)'
        : 'Geschätzte Durchschnittswerte'

      setWetterInfo(quellenText)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Wetterdaten konnten nicht abgerufen werden')
    } finally {
      setWetterLoading(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!formData.einspeisung_kwh || !formData.netzbezug_kwh) {
      setError('Bitte Einspeisung und Netzbezug eingeben')
      return
    }

    try {
      setLoading(true)

      // Sammle Investitions-Daten
      const invDaten: Record<string, InvestitionMonatsdaten> = {}
      // Hilfsfunktion: Wert nur setzen wenn nicht leer (aber 0 erlauben!)
      const hasValue = (val: string | undefined): boolean => val !== undefined && val !== ''
      const pf = (val: string) => parseFloat(val)
      const pi = (val: string) => parseInt(val)

      aktiveInvestitionen.forEach(inv => {
        const daten = investitionsDaten[inv.id]
        if (!daten) return

        const parsed: InvestitionMonatsdaten = {}

        // Generisches Parsen aus field_definitions (E4)
        const felder = getFelderFuerInvestition(inv.typ, inv.parameter)
        felder.forEach(f => {
          if (hasValue(daten[f.feld])) {
            (parsed as Record<string, number>)[f.feld] = f.datentyp === 'int' ? pi(daten[f.feld]) : pf(daten[f.feld])
          }
        })
        // WP Auto-Sum: stromverbrauch aus getrennten Werten berechnen
        if (inv.typ === 'waermepumpe' && inv.parameter?.getrennte_strommessung === true && !hasValue(daten.stromverbrauch_kwh)) {
          const sh = hasValue(daten.strom_heizen_kwh) ? pf(daten.strom_heizen_kwh) : 0
          const sw = hasValue(daten.strom_warmwasser_kwh) ? pf(daten.strom_warmwasser_kwh) : 0
          if (sh > 0 || sw > 0) (parsed as Record<string, number>).stromverbrauch_kwh = sh + sw
        }

        // Sonstige Positionen (Erträge & Ausgaben) für alle Investitionstypen
        const invPositionen = sonstigePositionen[String(inv.id)]
        if (invPositionen && invPositionen.length > 0) {
          // Nur Positionen mit Betrag > 0 und Bezeichnung speichern
          const gueltigePositionen = invPositionen.filter(p => p.betrag > 0 && p.bezeichnung.trim())
          if (gueltigePositionen.length > 0) {
            ;(parsed as Record<string, unknown>).sonstige_positionen = gueltigePositionen
          }
        }

        if (Object.keys(parsed).length > 0) {
          invDaten[inv.id] = parsed
        }
      })

      // Verwende Summen aus Investitionen falls nicht manuell eingegeben
      const battLadung = formData.batterie_ladung_kwh
        ? parseFloat(formData.batterie_ladung_kwh)
        : berechneteWerte.batterieLadung || undefined
      const battEntladung = formData.batterie_entladung_kwh
        ? parseFloat(formData.batterie_entladung_kwh)
        : berechneteWerte.batterieEntladung || undefined
      const pvErz = formData.pv_erzeugung_kwh
        ? parseFloat(formData.pv_erzeugung_kwh)
        : berechneteWerte.pvErzeugung || undefined

      await onSubmit({
        anlage_id: anlageId,
        jahr: parseInt(formData.jahr),
        monat: parseInt(formData.monat),
        einspeisung_kwh: parseFloat(formData.einspeisung_kwh),
        netzbezug_kwh: parseFloat(formData.netzbezug_kwh),
        pv_erzeugung_kwh: pvErz,
        batterie_ladung_kwh: battLadung,
        batterie_entladung_kwh: battEntladung,
        netzbezug_durchschnittspreis_cent: formData.netzbezug_durchschnittspreis_cent ? parseFloat(formData.netzbezug_durchschnittspreis_cent) : undefined,
        kraftstoffpreis_euro: formData.kraftstoffpreis_euro ? parseFloat(formData.kraftstoffpreis_euro) : undefined,
        gaspreis_cent_kwh: formData.gaspreis_cent_kwh ? parseFloat(formData.gaspreis_cent_kwh) : undefined,
        globalstrahlung_kwh_m2: formData.globalstrahlung_kwh_m2 ? parseFloat(formData.globalstrahlung_kwh_m2) : undefined,
        sonnenstunden: formData.sonnenstunden ? parseFloat(formData.sonnenstunden) : undefined,
        durchschnittstemperatur: formData.durchschnittstemperatur ? parseFloat(formData.durchschnittstemperatur) : undefined,
        sonderkosten_euro: formData.sonderkosten_euro ? parseFloat(formData.sonderkosten_euro) : undefined,
        sonderkosten_beschreibung: formData.sonderkosten_beschreibung || undefined,
        notizen: formData.notizen || undefined,
        investitionen_daten: Object.keys(invDaten).length > 0 ? invDaten : undefined,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  if (invLoading || loadingInvData) {
    return <div className="text-center py-4 text-gray-500">
      {loadingInvData ? 'Lade Investitionsdaten...' : 'Lade Investitionen...'}
    </div>
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && <Alert type="error">{error}</Alert>}

      {/* HA-Vorausfüllung Hinweis */}
      {haVorausfuellung && (
        <Alert type="info">
          Die Werte wurden aus der Home Assistant Langzeitstatistik geladen.
          Bitte prüfen Sie die Daten und ergänzen Sie fehlende Werte vor dem Speichern.
        </Alert>
      )}

      {/* Zeitraum */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Zeitraum</h3>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Jahr"
            name="jahr"
            type="number"
            min="2000"
            max="2100"
            value={formData.jahr}
            onChange={handleChange}
            required
            disabled={!!monatsdaten || !!haVorausfuellung}
          />
          <Select
            label="Monat"
            name="monat"
            value={formData.monat}
            onChange={handleChange}
            options={monatOptions}
            required
            disabled={!!monatsdaten || !!haVorausfuellung}
          />
        </div>
      </div>

      {/* Energie-Daten */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Energie-Daten (kWh)</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Einspeisung"
            name="einspeisung_kwh"
            type="number"
            step="0.01"
            min="0"
            value={formData.einspeisung_kwh}
            onChange={handleChange}
            placeholder="z.B. 450"
            required
          />
          <Input
            label="Netzbezug"
            name="netzbezug_kwh"
            type="number"
            step="0.01"
            min="0"
            value={formData.netzbezug_kwh}
            onChange={handleChange}
            placeholder="z.B. 120"
            required
          />
          {hatDynamischenTarif && (
            <Input
              label="Ø Strompreis (dynamisch)"
              name="netzbezug_durchschnittspreis_cent"
              type="number"
              step="0.01"
              min="0"
              value={formData.netzbezug_durchschnittspreis_cent}
              onChange={handleChange}
              placeholder="z.B. 25.3"
              hint="Monatsdurchschnitt bei dynamischem Tarif (ct/kWh)"
            />
          )}
          {hatEAuto && (
            <Input
              label="Ø Benzinpreis"
              name="kraftstoffpreis_euro"
              type="number"
              step="0.001"
              min="0"
              value={formData.kraftstoffpreis_euro}
              onChange={handleChange}
              placeholder="z.B. 1.85"
              hint="€/L — Monatsdurchschnitt für E-Auto-Vergleich"
            />
          )}
          {hatWaermepumpe && (
            <Input
              label="Ø Gas-/Ölpreis"
              name="gaspreis_cent_kwh"
              type="number"
              step="0.01"
              min="0"
              value={formData.gaspreis_cent_kwh}
              onChange={handleChange}
              placeholder="z.B. 11.5"
              hint="ct/kWh — Monatsdurchschnitt für WP-Vergleich"
            />
          )}
          {/* PV-Erzeugung: readonly wenn PV-Module mit Werten vorhanden, sonst editierbar (Legacy) */}
          {(hatPVModule || hatWechselrichter) && berechneteWerte.pvErzeugung > 0 ? (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                PV-Erzeugung (berechnet)
              </label>
              <input
                type="text"
                value={`${berechneteWerte.pvErzeugung.toFixed(1)} kWh`}
                readOnly
                disabled
                className="input bg-gray-100 dark:bg-gray-800 cursor-not-allowed"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Aus {hatPVModule ? 'PV-Modulen' : 'Wechselrichtern'}: {berechneteWerte.pvErzeugung.toFixed(1)} kWh
              </p>
            </div>
          ) : (
            <Input
              label={hatPVModule || hatWechselrichter ? "PV-Erzeugung (aus Modulen unten)" : "PV-Erzeugung (optional)"}
              name="pv_erzeugung_kwh"
              type="number"
              step="0.01"
              min="0"
              value={formData.pv_erzeugung_kwh}
              onChange={handleChange}
              placeholder="z.B. 800"
              hint={hatPVModule || hatWechselrichter ? "Wird aus PV-Modulen berechnet" : "Manuell eingeben wenn keine PV-Module definiert"}
            />
          )}
        </div>
      </div>

      {/* PV-Module (falls vorhanden) */}
      {hatPVModule && (
        <InvestitionSection
          title="PV-Module"
          icon={Sun}
          iconColor="text-yellow-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'pv-module')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={(inv) => getFelderFuerInvestition('pv-module', inv.parameter)}
        />
      )}

      {/* Wechselrichter (falls vorhanden und keine PV-Module) */}
      {hatWechselrichter && !hatPVModule && (
        <InvestitionSection
          title="Wechselrichter"
          icon={Sun}
          iconColor="text-yellow-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'wechselrichter')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={(inv) => getFelderFuerInvestition('wechselrichter', inv.parameter)}
        />
      )}

      {/* Speicher (falls vorhanden) */}
      {hatSpeicher && (
        <>
          <InvestitionSection
            title="Speicher"
            icon={Battery}
            iconColor="text-green-500"
            investitionen={aktiveInvestitionen.filter(i => i.typ === 'speicher')}
            investitionsDaten={investitionsDaten}
            onInvChange={handleInvChange}
            sonstigePositionen={sonstigePositionen}
            onPositionenChange={handlePositionenChange}
            felderFn={(inv) => getFelderFuerInvestition('speicher', inv.parameter)}
          />
          {(berechneteWerte.batterieLadung > 0 || berechneteWerte.batterieEntladung > 0) && (
            <div className="text-xs text-gray-500 dark:text-gray-400 -mt-2 ml-7">
              Summe: Ladung {berechneteWerte.batterieLadung.toFixed(1)} kWh | Entladung {berechneteWerte.batterieEntladung.toFixed(1)} kWh
            </div>
          )}
        </>
      )}

      {/* E-Auto (falls vorhanden) */}
      {hatEAuto && (
        <InvestitionSection
          title="E-Auto"
          icon={Car}
          iconColor="text-blue-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'e-auto')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={(inv) => getFelderFuerInvestition('e-auto', inv.parameter)}
        />
      )}

      {/* Wallbox (falls vorhanden) */}
      {hatWallbox && (
        <InvestitionSection
          title="Wallbox"
          icon={Plug}
          iconColor="text-purple-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'wallbox')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={(inv) => getFelderFuerInvestition('wallbox', inv.parameter)}
        />
      )}

      {/* Wärmepumpe (falls vorhanden) */}
      {hatWaermepumpe && (
        <InvestitionSection
          title="Wärmepumpe"
          icon={Flame}
          iconColor="text-orange-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'waermepumpe')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={(inv) => getFelderFuerInvestition('waermepumpe', inv.parameter)}
        />
      )}

      {/* Balkonkraftwerk (falls vorhanden) */}
      {hatBalkonkraftwerk && (
        <InvestitionSection
          title="Balkonkraftwerk"
          icon={Zap}
          iconColor="text-amber-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'balkonkraftwerk')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={(inv) => getFelderFuerInvestition('balkonkraftwerk', inv.parameter)}
          subtitleFn={(inv) => inv.leistung_kwp ? `${inv.leistung_kwp} kWp` : null}
          hinweisFn={(inv) => inv.parameter?.hat_speicher
            ? 'Mit Speicher: Bei Nulleinspeisung entspricht Eigenverbrauch meist der Erzeugung.'
            : 'Ohne Speicher: Eigenverbrauch ist der direkt genutzte Anteil (typisch 30-40% der Erzeugung).'}
        />
      )}

      {/* Sonstiges (falls vorhanden) */}
      {hatSonstiges && (
        <InvestitionSection
          title="Sonstiges"
          icon={MoreHorizontal}
          iconColor="text-gray-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'sonstiges')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={(inv) => getFelderFuerInvestition('sonstiges', inv.parameter)}
          hinweisFn={(inv) => {
            const kat = (inv.parameter?.kategorie as string) || 'erzeuger'
            const katLabel: Record<string, string> = { erzeuger: 'Erzeuger', verbraucher: 'Verbraucher', speicher: 'Speicher' }
            const label = katLabel[kat] || kat
            return inv.parameter?.beschreibung ? `${label} - ${String(inv.parameter.beschreibung)}` : label
          }}
        />
      )}

      {/* Batterie manuell (falls kein Speicher als Investition) */}
      {!hatSpeicher && (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">Batterie (optional)</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Batterie Ladung"
              name="batterie_ladung_kwh"
              type="number"
              step="0.01"
              min="0"
              value={formData.batterie_ladung_kwh}
              onChange={handleChange}
              placeholder="z.B. 150"
            />
            <Input
              label="Batterie Entladung"
              name="batterie_entladung_kwh"
              type="number"
              step="0.01"
              min="0"
              value={formData.batterie_entladung_kwh}
              onChange={handleChange}
              placeholder="z.B. 140"
            />
          </div>
        </div>
      )}

      {/* Wetterdaten */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-2">
            <Cloud className="w-4 h-4" />
            Wetterdaten (optional)
          </h3>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={fetchWetterdaten}
            disabled={wetterLoading}
          >
            {wetterLoading ? (
              <><Loader2 className="w-4 h-4 animate-spin mr-1" /> Lade...</>
            ) : (
              <><Cloud className="w-4 h-4 mr-1" /> Auto-Fill</>
            )}
          </Button>
        </div>
        {wetterInfo && (
          <p className="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 px-3 py-2 rounded">
            {wetterInfo}
          </p>
        )}
        <div className="grid grid-cols-3 gap-4">
          <Input
            label="Globalstrahlung"
            name="globalstrahlung_kwh_m2"
            type="number"
            step="0.1"
            min="0"
            value={formData.globalstrahlung_kwh_m2}
            onChange={handleChange}
            placeholder="z.B. 152"
            hint="kWh/m²"
          />
          <Input
            label="Sonnenstunden"
            name="sonnenstunden"
            type="number"
            step="0.1"
            min="0"
            value={formData.sonnenstunden}
            onChange={handleChange}
            placeholder="z.B. 245"
            hint="Stunden"
          />
          <Input
            label="Ø Temperatur"
            name="durchschnittstemperatur"
            type="number"
            step="0.1"
            value={formData.durchschnittstemperatur}
            onChange={handleChange}
            placeholder="z.B. 14.5"
            hint="°C (optional)"
          />
        </div>
      </div>

      {/* Sonderkosten */}
      <div className="grid grid-cols-2 gap-4">
        <Input
          label="Sonderkosten"
          name="sonderkosten_euro"
          type="number"
          step="0.01"
          min="0"
          value={formData.sonderkosten_euro}
          onChange={handleChange}
          placeholder="z.B. 120.00"
          hint="€ — Reparatur, Wartung, etc. (optional)"
        />
        <Input
          label="Sonderkosten Beschreibung"
          name="sonderkosten_beschreibung"
          value={formData.sonderkosten_beschreibung}
          onChange={handleChange}
          placeholder="z.B. Wechselrichter-Wartung"
        />
      </div>

      {/* Notizen */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Notizen
        </label>
        <textarea
          name="notizen"
          value={formData.notizen}
          onChange={handleChange}
          rows={2}
          className="input"
          placeholder="Optionale Bemerkungen..."
        />
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button type="submit" loading={loading}>
          {monatsdaten ? 'Speichern' : 'Monat erfassen'}
        </Button>
      </div>
    </form>
  )
}
