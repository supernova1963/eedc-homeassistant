/**
 * Dynamisches Monatsdatenformular
 * Zeigt Felder basierend auf den vorhandenen Investitionen der Anlage an.
 */

import { useState, useEffect, useMemo, FormEvent } from 'react'
import { Button, Input, Alert, Select } from '../ui'
import { useInvestitionen } from '../../hooks'
import { investitionenApi, wetterApi } from '../../api'
import type { Monatsdaten, Investition } from '../../types'
import { Car, Battery, Plug, Sun, Flame, Zap, MoreHorizontal, Cloud, Loader2 } from 'lucide-react'

interface MonatsdatenFormProps {
  monatsdaten?: Monatsdaten | null
  anlageId: number
  onSubmit: (data: MonatsdatenSubmitData) => Promise<void>
  onCancel: () => void
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
  globalstrahlung_kwh_m2?: number
  sonnenstunden?: number
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
  // Sonderkosten (für alle Investitionstypen)
  sonderkosten_euro?: number
  sonderkosten_notiz?: string
}

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

export default function MonatsdatenForm({ monatsdaten, anlageId, onSubmit, onCancel }: MonatsdatenFormProps) {
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

  // Welche Investitionstypen sind vorhanden?
  const hatSpeicher = aktiveInvestitionen.some(i => i.typ === 'speicher')
  const hatEAuto = aktiveInvestitionen.some(i => i.typ === 'e-auto')
  const hatWallbox = aktiveInvestitionen.some(i => i.typ === 'wallbox')
  const hatWaermepumpe = aktiveInvestitionen.some(i => i.typ === 'waermepumpe')
  const hatWechselrichter = aktiveInvestitionen.some(i => i.typ === 'wechselrichter')
  const hatPVModule = aktiveInvestitionen.some(i => i.typ === 'pv-module')
  const hatBalkonkraftwerk = aktiveInvestitionen.some(i => i.typ === 'balkonkraftwerk')
  const hatSonstiges = aktiveInvestitionen.some(i => i.typ === 'sonstiges')

  // Basis-Formulardaten
  const [formData, setFormData] = useState({
    jahr: monatsdaten?.jahr?.toString() || currentYear.toString(),
    monat: monatsdaten?.monat?.toString() || currentMonth.toString(),
    einspeisung_kwh: monatsdaten?.einspeisung_kwh?.toString() || '',
    netzbezug_kwh: monatsdaten?.netzbezug_kwh?.toString() || '',
    pv_erzeugung_kwh: monatsdaten?.pv_erzeugung_kwh?.toString() || '',
    batterie_ladung_kwh: monatsdaten?.batterie_ladung_kwh?.toString() || '',
    batterie_entladung_kwh: monatsdaten?.batterie_entladung_kwh?.toString() || '',
    globalstrahlung_kwh_m2: monatsdaten?.globalstrahlung_kwh_m2?.toString() || '',
    sonnenstunden: monatsdaten?.sonnenstunden?.toString() || '',
    notizen: monatsdaten?.notizen || '',
  })

  // Wetter-Daten Auto-Fill
  const [wetterLoading, setWetterLoading] = useState(false)
  const [wetterInfo, setWetterInfo] = useState<string | null>(null)

  // Investitions-spezifische Daten
  const [investitionsDaten, setInvestitionsDaten] = useState<Record<string, Record<string, string>>>({})
  const [loadingInvData, setLoadingInvData] = useState(false)

  // Initialisiere Investitions-Daten und lade vorhandene Daten beim Bearbeiten
  useEffect(() => {
    if (aktiveInvestitionen.length === 0) return

    const initializeAndLoad = async () => {
      // Initialisiere mit leeren Werten
      const initial: Record<string, Record<string, string>> = {}
      aktiveInvestitionen.forEach(inv => {
        if (inv.typ === 'e-auto') {
          initial[inv.id] = {
            km_gefahren: '',
            verbrauch_kwh: '',
            ladung_pv_kwh: '',
            ladung_netz_kwh: '',
            ladung_extern_kwh: '',
            ladung_extern_euro: '',
            entladung_v2h_kwh: '',
          }
        } else if (inv.typ === 'speicher') {
          initial[inv.id] = {
            ladung_kwh: '',
            entladung_kwh: '',
            // Arbitrage-Felder (nur relevant wenn arbitrage_faehig)
            speicher_ladung_netz_kwh: '',
            speicher_ladepreis_cent: '',
          }
        } else if (inv.typ === 'wallbox') {
          initial[inv.id] = {
            ladung_kwh: '',
            ladevorgaenge: '',
          }
        } else if (inv.typ === 'waermepumpe') {
          initial[inv.id] = {
            stromverbrauch_kwh: '',
            heizenergie_kwh: '',
            warmwasser_kwh: '',
          }
        } else if (inv.typ === 'wechselrichter') {
          initial[inv.id] = {
            pv_erzeugung_kwh: '',
          }
        } else if (inv.typ === 'pv-module') {
          initial[inv.id] = {
            pv_erzeugung_kwh: '',
          }
        } else if (inv.typ === 'balkonkraftwerk') {
          const hatSpeicher = inv.parameter?.hat_speicher
          const baseFields = {
            pv_erzeugung_kwh: '',
            eigenverbrauch_kwh: '',
            einspeisung_kwh: '',
          }
          if (hatSpeicher) {
            initial[inv.id] = {
              ...baseFields,
              speicher_ladung_kwh: '',
              speicher_entladung_kwh: '',
            }
          } else {
            initial[inv.id] = baseFields
          }
        } else if (inv.typ === 'sonstiges') {
          const kategorie = inv.parameter?.kategorie || 'erzeuger'
          if (kategorie === 'erzeuger') {
            initial[inv.id] = {
              erzeugung_kwh: '',
              eigenverbrauch_kwh: '',
              einspeisung_kwh: '',
            }
          } else if (kategorie === 'verbraucher') {
            initial[inv.id] = {
              verbrauch_sonstig_kwh: '',
              bezug_pv_kwh: '',
              bezug_netz_kwh: '',
            }
          } else if (kategorie === 'speicher') {
            initial[inv.id] = { ladung_kwh: '', entladung_kwh: '' }
          }
        }
        // Sonderkosten für alle Investitionstypen hinzufügen
        if (initial[inv.id]) {
          initial[inv.id].sonderkosten_euro = ''
          initial[inv.id].sonderkosten_notiz = ''
        }
      })

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
            if (initial[invIdStr] && imd.verbrauch_daten) {
              // Konvertiere alle Werte zu Strings für die Formularfelder
              Object.entries(imd.verbrauch_daten).forEach(([key, value]) => {
                if (initial[invIdStr][key] !== undefined) {
                  initial[invIdStr][key] = value?.toString() || ''
                }
                // V2H Mapping: Backend speichert als v2h_entladung_kwh, Form erwartet entladung_v2h_kwh
                if (key === 'v2h_entladung_kwh' && initial[invIdStr]['entladung_v2h_kwh'] !== undefined) {
                  initial[invIdStr]['entladung_v2h_kwh'] = value?.toString() || ''
                }
                // Balkonkraftwerk Mapping: Backend speichert als erzeugung_kwh, Form erwartet pv_erzeugung_kwh
                if (key === 'erzeugung_kwh' && initial[invIdStr]['pv_erzeugung_kwh'] !== undefined) {
                  initial[invIdStr]['pv_erzeugung_kwh'] = value?.toString() || ''
                }
                // Sonstiges Verbraucher Mapping: Backend speichert als verbrauch_kwh, Form erwartet verbrauch_sonstig_kwh
                if (key === 'verbrauch_kwh' && initial[invIdStr]['verbrauch_sonstig_kwh'] !== undefined) {
                  initial[invIdStr]['verbrauch_sonstig_kwh'] = value?.toString() || ''
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
              console.info(
                `Migration: Legacy-Speicherdaten (${legacyLadung}/${legacyEntladung} kWh) ` +
                `auf ${speicherOhneDaten.length} Speicher übertragen`
              )
            }
          }
        } catch (e) {
          console.error('Fehler beim Laden der InvestitionMonatsdaten:', e)
        } finally {
          setLoadingInvData(false)
        }
      }

      setInvestitionsDaten(initial)
    }

    initializeAndLoad()
  }, [aktiveInvestitionen, monatsdaten?.jahr, monatsdaten?.monat, anlageId])

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
      aktiveInvestitionen.forEach(inv => {
        const daten = investitionsDaten[inv.id]
        if (!daten) return

        const parsed: InvestitionMonatsdaten = {}

        if (inv.typ === 'e-auto') {
          if (daten.km_gefahren) parsed.km_gefahren = parseFloat(daten.km_gefahren)
          if (daten.verbrauch_kwh) parsed.verbrauch_kwh = parseFloat(daten.verbrauch_kwh)
          if (daten.ladung_pv_kwh) parsed.ladung_pv_kwh = parseFloat(daten.ladung_pv_kwh)
          if (daten.ladung_netz_kwh) parsed.ladung_netz_kwh = parseFloat(daten.ladung_netz_kwh)
          if (daten.ladung_extern_kwh) parsed.ladung_extern_kwh = parseFloat(daten.ladung_extern_kwh)
          if (daten.ladung_extern_euro) parsed.ladung_extern_euro = parseFloat(daten.ladung_extern_euro)
          // V2H: Form verwendet entladung_v2h_kwh, Backend erwartet v2h_entladung_kwh
          if (daten.entladung_v2h_kwh) (parsed as Record<string, number>).v2h_entladung_kwh = parseFloat(daten.entladung_v2h_kwh)
        } else if (inv.typ === 'speicher') {
          if (daten.ladung_kwh) parsed.ladung_kwh = parseFloat(daten.ladung_kwh)
          if (daten.entladung_kwh) parsed.entladung_kwh = parseFloat(daten.entladung_kwh)
          // Arbitrage-Felder
          if (daten.speicher_ladung_netz_kwh) parsed.speicher_ladung_netz_kwh = parseFloat(daten.speicher_ladung_netz_kwh)
          if (daten.speicher_ladepreis_cent) parsed.speicher_ladepreis_cent = parseFloat(daten.speicher_ladepreis_cent)
        } else if (inv.typ === 'wallbox') {
          if (daten.ladung_kwh) parsed.ladung_kwh = parseFloat(daten.ladung_kwh)
          if (daten.ladevorgaenge) parsed.ladevorgaenge = parseInt(daten.ladevorgaenge)
        } else if (inv.typ === 'waermepumpe') {
          if (daten.stromverbrauch_kwh) parsed.stromverbrauch_kwh = parseFloat(daten.stromverbrauch_kwh)
          if (daten.heizenergie_kwh) parsed.heizenergie_kwh = parseFloat(daten.heizenergie_kwh)
          if (daten.warmwasser_kwh) parsed.warmwasser_kwh = parseFloat(daten.warmwasser_kwh)
        } else if (inv.typ === 'wechselrichter') {
          if (daten.pv_erzeugung_kwh) parsed.pv_erzeugung_kwh = parseFloat(daten.pv_erzeugung_kwh)
        } else if (inv.typ === 'pv-module') {
          if (daten.pv_erzeugung_kwh) parsed.pv_erzeugung_kwh = parseFloat(daten.pv_erzeugung_kwh)
        } else if (inv.typ === 'balkonkraftwerk') {
          // Balkonkraftwerk: Form verwendet pv_erzeugung_kwh, Backend erwartet erzeugung_kwh
          if (daten.pv_erzeugung_kwh) (parsed as Record<string, number>).erzeugung_kwh = parseFloat(daten.pv_erzeugung_kwh)
          if (daten.eigenverbrauch_kwh) parsed.eigenverbrauch_kwh = parseFloat(daten.eigenverbrauch_kwh)
          if (daten.einspeisung_kwh) parsed.einspeisung_kwh = parseFloat(daten.einspeisung_kwh)
          if (daten.speicher_ladung_kwh) parsed.speicher_ladung_kwh = parseFloat(daten.speicher_ladung_kwh)
          if (daten.speicher_entladung_kwh) parsed.speicher_entladung_kwh = parseFloat(daten.speicher_entladung_kwh)
        } else if (inv.typ === 'sonstiges') {
          // Sonstiges Erzeuger
          if (daten.erzeugung_kwh) parsed.erzeugung_kwh = parseFloat(daten.erzeugung_kwh)
          if (daten.eigenverbrauch_kwh) parsed.eigenverbrauch_kwh = parseFloat(daten.eigenverbrauch_kwh)
          if (daten.einspeisung_kwh) parsed.einspeisung_kwh = parseFloat(daten.einspeisung_kwh)
          // Sonstiges Verbraucher: Form verwendet verbrauch_sonstig_kwh, Backend erwartet verbrauch_kwh
          if (daten.verbrauch_sonstig_kwh) (parsed as Record<string, number>).verbrauch_kwh = parseFloat(daten.verbrauch_sonstig_kwh)
          if (daten.bezug_pv_kwh) parsed.bezug_pv_kwh = parseFloat(daten.bezug_pv_kwh)
          if (daten.bezug_netz_kwh) parsed.bezug_netz_kwh = parseFloat(daten.bezug_netz_kwh)
          // Sonstiges Speicher
          if (daten.ladung_kwh) parsed.ladung_kwh = parseFloat(daten.ladung_kwh)
          if (daten.entladung_kwh) parsed.entladung_kwh = parseFloat(daten.entladung_kwh)
        }

        // Sonderkosten für alle Investitionstypen
        if (daten.sonderkosten_euro) parsed.sonderkosten_euro = parseFloat(daten.sonderkosten_euro)
        if (daten.sonderkosten_notiz) parsed.sonderkosten_notiz = daten.sonderkosten_notiz

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
        globalstrahlung_kwh_m2: formData.globalstrahlung_kwh_m2 ? parseFloat(formData.globalstrahlung_kwh_m2) : undefined,
        sonnenstunden: formData.sonnenstunden ? parseFloat(formData.sonnenstunden) : undefined,
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
            disabled={!!monatsdaten}
          />
          <Select
            label="Monat"
            name="monat"
            value={formData.monat}
            onChange={handleChange}
            options={monatOptions}
            required
            disabled={!!monatsdaten}
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
          <Input
            label={(hatPVModule || hatWechselrichter) ? "PV-Erzeugung (Summe oder manuell)" : "PV-Erzeugung (optional)"}
            name="pv_erzeugung_kwh"
            type="number"
            step="0.01"
            min="0"
            value={formData.pv_erzeugung_kwh}
            onChange={handleChange}
            placeholder={berechneteWerte.pvErzeugung > 0 ? `Summe: ${berechneteWerte.pvErzeugung.toFixed(1)}` : "z.B. 800"}
            hint={berechneteWerte.pvErzeugung > 0 ? `Aus ${hatPVModule ? 'PV-Modulen' : 'Wechselrichtern'}: ${berechneteWerte.pvErzeugung.toFixed(1)} kWh` : "Wird berechnet wenn leer"}
          />
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
          felder={[
            { key: 'pv_erzeugung_kwh', label: 'PV-Erzeugung', unit: 'kWh', placeholder: 'z.B. 800' },
          ]}
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
          felder={[
            { key: 'pv_erzeugung_kwh', label: 'PV-Erzeugung', unit: 'kWh', placeholder: 'z.B. 800' },
          ]}
        />
      )}

      {/* Speicher (falls vorhanden) */}
      {hatSpeicher && (
        <>
          <SpeicherSection
            investitionen={aktiveInvestitionen.filter(i => i.typ === 'speicher')}
            investitionsDaten={investitionsDaten}
            onInvChange={handleInvChange}
          />
          {/* Summen-Anzeige wenn mehrere Speicher oder Daten vorhanden */}
          {(berechneteWerte.batterieLadung > 0 || berechneteWerte.batterieEntladung > 0) && (
            <div className="text-xs text-gray-500 dark:text-gray-400 -mt-2 ml-7">
              Summe: Ladung {berechneteWerte.batterieLadung.toFixed(1)} kWh | Entladung {berechneteWerte.batterieEntladung.toFixed(1)} kWh
            </div>
          )}
        </>
      )}

      {/* E-Auto (falls vorhanden) */}
      {hatEAuto && (
        <EAutoSection
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'e-auto')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
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
          felder={[
            { key: 'ladung_kwh', label: 'Ladung', unit: 'kWh', placeholder: 'z.B. 200' },
            { key: 'ladevorgaenge', label: 'Ladevorgänge', unit: '', placeholder: 'z.B. 12' },
          ]}
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
          felder={[
            { key: 'stromverbrauch_kwh', label: 'Stromverbrauch', unit: 'kWh', placeholder: 'z.B. 350' },
            { key: 'heizenergie_kwh', label: 'Heizenergie', unit: 'kWh', placeholder: 'z.B. 1200' },
            { key: 'warmwasser_kwh', label: 'Warmwasser', unit: 'kWh', placeholder: 'z.B. 150' },
          ]}
        />
      )}

      {/* Balkonkraftwerk (falls vorhanden) */}
      {hatBalkonkraftwerk && (
        <BalkonkraftwerkSection
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'balkonkraftwerk')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
        />
      )}

      {/* Sonstiges (falls vorhanden) */}
      {hatSonstiges && (
        <SonstigesSection
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'sonstiges')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
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
        <div className="grid grid-cols-2 gap-4">
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
            step="1"
            min="0"
            value={formData.sonnenstunden}
            onChange={handleChange}
            placeholder="z.B. 245"
            hint="Stunden"
          />
        </div>
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

// Spezielle Speicher Sektion mit konditionellem Arbitrage pro Speicher
interface SpeicherSectionProps {
  investitionen: Investition[]
  investitionsDaten: Record<string, Record<string, string>>
  onInvChange: (invId: number, field: string, value: string) => void
}

function SpeicherSection({ investitionen, investitionsDaten, onInvChange }: SpeicherSectionProps) {
  if (investitionen.length === 0) return null

  type SpeicherFeld = { key: string; label: string; unit: string; placeholder: string; hint?: string }

  const basisFelder: SpeicherFeld[] = [
    { key: 'ladung_kwh', label: 'Ladung', unit: 'kWh', placeholder: 'z.B. 150' },
    { key: 'entladung_kwh', label: 'Entladung', unit: 'kWh', placeholder: 'z.B. 140' },
  ]

  const arbitrageFelder: SpeicherFeld[] = [
    { key: 'speicher_ladung_netz_kwh', label: 'Netzladung', unit: 'kWh', placeholder: 'z.B. 50', hint: 'Arbitrage: Laden aus Netz' },
    { key: 'speicher_ladepreis_cent', label: 'Ø Ladepreis', unit: 'ct/kWh', placeholder: 'z.B. 15', hint: 'Durchschnittl. Strompreis beim Netzladen' },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Battery className="h-5 w-5 text-green-500" />
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Speicher</h3>
      </div>

      {investitionen.map((inv) => {
        // Prüfe ob dieser Speicher Arbitrage-fähig ist
        const hatArbitrage = inv.parameter?.arbitrage_faehig
        const felder = hatArbitrage ? [...basisFelder, ...arbitrageFelder] : basisFelder

        return (
          <div key={inv.id} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              {inv.bezeichnung}
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {felder.map((feld) => (
                <div key={feld.key}>
                  <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                    {feld.label} {feld.unit && <span className="text-gray-400">({feld.unit})</span>}
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={investitionsDaten[inv.id]?.[feld.key] || ''}
                    onChange={(e) => onInvChange(inv.id, feld.key, e.target.value)}
                    placeholder={feld.placeholder}
                    className="input text-sm py-1.5"
                    title={feld.hint}
                  />
                  {feld.hint && (
                    <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 truncate" title={feld.hint}>
                      {feld.hint}
                    </p>
                  )}
                </div>
              ))}
            </div>
            {/* Sonderkosten */}
            <SonderkostenFields
              invId={inv.id}
              investitionsDaten={investitionsDaten}
              onInvChange={onInvChange}
            />
          </div>
        )
      })}
    </div>
  )
}

// Spezielle E-Auto Sektion mit konditionellem V2H pro Fahrzeug
interface EAutoSectionProps {
  investitionen: Investition[]
  investitionsDaten: Record<string, Record<string, string>>
  onInvChange: (invId: number, field: string, value: string) => void
}

function EAutoSection({ investitionen, investitionsDaten, onInvChange }: EAutoSectionProps) {
  if (investitionen.length === 0) return null

  type EAutoFeld = { key: string; label: string; unit: string; placeholder: string; hint?: string }

  const basisFelder: EAutoFeld[] = [
    { key: 'km_gefahren', label: 'km gefahren', unit: 'km', placeholder: 'z.B. 1200' },
    { key: 'verbrauch_kwh', label: 'Verbrauch gesamt', unit: 'kWh', placeholder: 'z.B. 216' },
    { key: 'ladung_pv_kwh', label: 'Heim: PV', unit: 'kWh', placeholder: 'z.B. 130', hint: 'Wallbox mit PV-Strom' },
    { key: 'ladung_netz_kwh', label: 'Heim: Netz', unit: 'kWh', placeholder: 'z.B. 50', hint: 'Wallbox mit Netzstrom' },
    { key: 'ladung_extern_kwh', label: 'Extern', unit: 'kWh', placeholder: 'z.B. 36', hint: 'Autobahn, Arbeit, etc.' },
    { key: 'ladung_extern_euro', label: 'Extern Kosten', unit: '€', placeholder: 'z.B. 18.00' },
  ]

  const v2hFeld: EAutoFeld = { key: 'entladung_v2h_kwh', label: 'V2H Entladung', unit: 'kWh', placeholder: 'z.B. 25' }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Car className="h-5 w-5 text-blue-500" />
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">E-Auto</h3>
      </div>

      {investitionen.map((inv) => {
        // Prüfe ob dieses E-Auto V2H-fähig ist
        const hatV2H = inv.parameter?.v2h_faehig || inv.parameter?.nutzt_v2h
        const felder = hatV2H ? [...basisFelder, v2hFeld] : basisFelder

        return (
          <div key={inv.id} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              {inv.bezeichnung}
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {felder.map((feld) => (
                <div key={feld.key}>
                  <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                    {feld.label} {feld.unit && <span className="text-gray-400">({feld.unit})</span>}
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={investitionsDaten[inv.id]?.[feld.key] || ''}
                    onChange={(e) => onInvChange(inv.id, feld.key, e.target.value)}
                    placeholder={feld.placeholder}
                    className="input text-sm py-1.5"
                    title={feld.hint}
                  />
                  {feld.hint && (
                    <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 truncate" title={feld.hint}>
                      {feld.hint}
                    </p>
                  )}
                </div>
              ))}
            </div>
            {/* Sonderkosten */}
            <SonderkostenFields
              invId={inv.id}
              investitionsDaten={investitionsDaten}
              onInvChange={onInvChange}
            />
          </div>
        )
      })}
    </div>
  )
}

// Hilfskomponente für Investitions-Sektionen
interface InvestitionSectionProps {
  title: string
  icon: React.ElementType
  iconColor: string
  investitionen: Investition[]
  investitionsDaten: Record<string, Record<string, string>>
  onInvChange: (invId: number, field: string, value: string) => void
  felder: { key: string; label: string; unit: string; placeholder: string; hint?: string }[]
}

function InvestitionSection({
  title,
  icon: Icon,
  iconColor,
  investitionen,
  investitionsDaten,
  onInvChange,
  felder,
}: InvestitionSectionProps) {
  if (investitionen.length === 0) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Icon className={`h-5 w-5 ${iconColor}`} />
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">{title}</h3>
      </div>

      {investitionen.map((inv) => (
        <div key={inv.id} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            {inv.bezeichnung}
          </p>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {felder.map((feld) => (
              <div key={feld.key}>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  {feld.label} {feld.unit && <span className="text-gray-400">({feld.unit})</span>}
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={investitionsDaten[inv.id]?.[feld.key] || ''}
                  onChange={(e) => onInvChange(inv.id, feld.key, e.target.value)}
                  placeholder={feld.placeholder}
                  className="input text-sm py-1.5"
                  title={feld.hint}
                />
                {feld.hint && (
                  <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 truncate" title={feld.hint}>
                    {feld.hint}
                  </p>
                )}
              </div>
            ))}
          </div>
          {/* Sonderkosten */}
          <SonderkostenFields
            invId={inv.id}
            investitionsDaten={investitionsDaten}
            onInvChange={onInvChange}
          />
        </div>
      ))}
    </div>
  )
}

// Balkonkraftwerk Sektion mit konditionellem Speicher
interface BalkonkraftwerkSectionProps {
  investitionen: Investition[]
  investitionsDaten: Record<string, Record<string, string>>
  onInvChange: (invId: number, field: string, value: string) => void
}

function BalkonkraftwerkSection({ investitionen, investitionsDaten, onInvChange }: BalkonkraftwerkSectionProps) {
  if (investitionen.length === 0) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Zap className="h-5 w-5 text-amber-500" />
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Balkonkraftwerk</h3>
      </div>

      {investitionen.map((inv) => {
        const hatSpeicher = Boolean(inv.parameter?.hat_speicher)

        return (
          <div key={inv.id} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {inv.bezeichnung}
              {inv.leistung_kwp && <span className="text-xs text-gray-500 ml-2">({inv.leistung_kwp} kWp)</span>}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              {hatSpeicher
                ? 'Mit Speicher: Bei Nulleinspeisung entspricht Eigenverbrauch meist der Erzeugung.'
                : 'Ohne Speicher: Eigenverbrauch ist der direkt genutzte Anteil (typisch 30-40% der Erzeugung).'
              }
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  Erzeugung <span className="text-gray-400">(kWh)</span>
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={investitionsDaten[inv.id]?.pv_erzeugung_kwh || ''}
                  onChange={(e) => onInvChange(inv.id, 'pv_erzeugung_kwh', e.target.value)}
                  placeholder="z.B. 45"
                  className="input text-sm py-1.5"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  Eigenverbrauch <span className="text-gray-400">(kWh)</span>
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={investitionsDaten[inv.id]?.eigenverbrauch_kwh || ''}
                  onChange={(e) => onInvChange(inv.id, 'eigenverbrauch_kwh', e.target.value)}
                  placeholder={hatSpeicher ? 'z.B. 43 (≈Erzeugung)' : 'z.B. 15 (30-40%)'}
                  className="input text-sm py-1.5"
                />
              </div>
              {/* Einspeisung wird berechnet: Erzeugung - Eigenverbrauch */}
              {hatSpeicher && (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      Speicher Ladung <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={investitionsDaten[inv.id]?.speicher_ladung_kwh || ''}
                      onChange={(e) => onInvChange(inv.id, 'speicher_ladung_kwh', e.target.value)}
                      placeholder="z.B. 30"
                      className="input text-sm py-1.5"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      Speicher Entladung <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={investitionsDaten[inv.id]?.speicher_entladung_kwh || ''}
                      onChange={(e) => onInvChange(inv.id, 'speicher_entladung_kwh', e.target.value)}
                      placeholder="z.B. 28"
                      className="input text-sm py-1.5"
                    />
                  </div>
                </>
              )}
            </div>
            {/* Sonderkosten */}
            <SonderkostenFields
              invId={inv.id}
              investitionsDaten={investitionsDaten}
              onInvChange={onInvChange}
            />
          </div>
        )
      })}
    </div>
  )
}

// Sonstiges Sektion - dynamisch basierend auf Kategorie
interface SonstigesSectionProps {
  investitionen: Investition[]
  investitionsDaten: Record<string, Record<string, string>>
  onInvChange: (invId: number, field: string, value: string) => void
}

function SonstigesSection({ investitionen, investitionsDaten, onInvChange }: SonstigesSectionProps) {
  if (investitionen.length === 0) return null

  const kategorieLabels: Record<string, string> = {
    erzeuger: 'Erzeuger',
    verbraucher: 'Verbraucher',
    speicher: 'Speicher',
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <MoreHorizontal className="h-5 w-5 text-gray-500" />
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Sonstiges</h3>
      </div>

      {investitionen.map((inv) => {
        const kategorie = (inv.parameter?.kategorie as string) || 'erzeuger'

        return (
          <div key={inv.id} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {inv.bezeichnung}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              {kategorieLabels[kategorie] || kategorie}
              {inv.parameter?.beschreibung ? ` - ${String(inv.parameter.beschreibung)}` : ''}
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {kategorie === 'erzeuger' && (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      Erzeugung <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={investitionsDaten[inv.id]?.erzeugung_kwh || ''}
                      onChange={(e) => onInvChange(inv.id, 'erzeugung_kwh', e.target.value)}
                      placeholder="z.B. 100"
                      className="input text-sm py-1.5"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      Eigenverbrauch <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={investitionsDaten[inv.id]?.eigenverbrauch_kwh || ''}
                      onChange={(e) => onInvChange(inv.id, 'eigenverbrauch_kwh', e.target.value)}
                      placeholder="z.B. 85"
                      className="input text-sm py-1.5"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      Einspeisung <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={investitionsDaten[inv.id]?.einspeisung_kwh || ''}
                      onChange={(e) => onInvChange(inv.id, 'einspeisung_kwh', e.target.value)}
                      placeholder="z.B. 15"
                      className="input text-sm py-1.5"
                    />
                  </div>
                </>
              )}
              {kategorie === 'verbraucher' && (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      Verbrauch <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={investitionsDaten[inv.id]?.verbrauch_sonstig_kwh || ''}
                      onChange={(e) => onInvChange(inv.id, 'verbrauch_sonstig_kwh', e.target.value)}
                      placeholder="z.B. 50"
                      className="input text-sm py-1.5"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      davon PV <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={investitionsDaten[inv.id]?.bezug_pv_kwh || ''}
                      onChange={(e) => onInvChange(inv.id, 'bezug_pv_kwh', e.target.value)}
                      placeholder="z.B. 30"
                      className="input text-sm py-1.5"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      davon Netz <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={investitionsDaten[inv.id]?.bezug_netz_kwh || ''}
                      onChange={(e) => onInvChange(inv.id, 'bezug_netz_kwh', e.target.value)}
                      placeholder="z.B. 20"
                      className="input text-sm py-1.5"
                    />
                  </div>
                </>
              )}
              {kategorie === 'speicher' && (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      Ladung <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={investitionsDaten[inv.id]?.ladung_kwh || ''}
                      onChange={(e) => onInvChange(inv.id, 'ladung_kwh', e.target.value)}
                      placeholder="z.B. 20"
                      className="input text-sm py-1.5"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      Entladung <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={investitionsDaten[inv.id]?.entladung_kwh || ''}
                      onChange={(e) => onInvChange(inv.id, 'entladung_kwh', e.target.value)}
                      placeholder="z.B. 18"
                      className="input text-sm py-1.5"
                    />
                  </div>
                </>
              )}
            </div>
            {/* Sonderkosten */}
            <SonderkostenFields
              invId={inv.id}
              investitionsDaten={investitionsDaten}
              onInvChange={onInvChange}
            />
          </div>
        )
      })}
    </div>
  )
}

// Sonderkosten-Felder für alle Investitionstypen
interface SonderkostenFieldsProps {
  invId: number
  investitionsDaten: Record<string, Record<string, string>>
  onInvChange: (invId: number, field: string, value: string) => void
}

function SonderkostenFields({ invId, investitionsDaten, onInvChange }: SonderkostenFieldsProps) {
  const hasValue = investitionsDaten[invId]?.sonderkosten_euro || investitionsDaten[invId]?.sonderkosten_notiz
  const [expanded, setExpanded] = useState(Boolean(hasValue))

  return (
    <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
      {!expanded ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
        >
          + Sonderkosten erfassen (Reparatur, Wartung, etc.)
        </button>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
              Sonderkosten <span className="text-gray-400">(€)</span>
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={investitionsDaten[invId]?.sonderkosten_euro || ''}
              onChange={(e) => onInvChange(invId, 'sonderkosten_euro', e.target.value)}
              placeholder="z.B. 150"
              className="input text-sm py-1.5"
            />
          </div>
          <div className="md:col-span-2">
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
              Beschreibung
            </label>
            <input
              type="text"
              value={investitionsDaten[invId]?.sonderkosten_notiz || ''}
              onChange={(e) => onInvChange(invId, 'sonderkosten_notiz', e.target.value)}
              placeholder="z.B. Wechselrichter-Reparatur"
              className="input text-sm py-1.5"
            />
          </div>
        </div>
      )}
    </div>
  )
}
