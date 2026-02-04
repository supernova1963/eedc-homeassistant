/**
 * Dynamisches Monatsdatenformular
 * Zeigt Felder basierend auf den vorhandenen Investitionen der Anlage an.
 */

import { useState, useEffect, useMemo, FormEvent } from 'react'
import { Button, Input, Alert, Select } from '../ui'
import { useInvestitionen } from '../../hooks'
import type { Monatsdaten, Investition } from '../../types'
import { Car, Battery, Plug, Sun, Flame } from 'lucide-react'

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
  // Wallbox - nutzt E-Auto Heim-Ladung (ladung_pv_kwh + ladung_netz_kwh)
  ladevorgaenge?: number
  // Wärmepumpe
  stromverbrauch_kwh?: number
  heizenergie_kwh?: number
  warmwasser_kwh?: number
  // Wechselrichter
  pv_erzeugung_kwh?: number
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

  // Basis-Formulardaten
  const [formData, setFormData] = useState({
    jahr: monatsdaten?.jahr?.toString() || currentYear.toString(),
    monat: monatsdaten?.monat?.toString() || currentMonth.toString(),
    einspeisung_kwh: monatsdaten?.einspeisung_kwh?.toString() || '',
    netzbezug_kwh: monatsdaten?.netzbezug_kwh?.toString() || '',
    pv_erzeugung_kwh: monatsdaten?.pv_erzeugung_kwh?.toString() || '',
    batterie_ladung_kwh: monatsdaten?.batterie_ladung_kwh?.toString() || '',
    batterie_entladung_kwh: monatsdaten?.batterie_entladung_kwh?.toString() || '',
    notizen: monatsdaten?.notizen || '',
  })

  // Investitions-spezifische Daten
  const [investitionsDaten, setInvestitionsDaten] = useState<Record<string, Record<string, string>>>({})

  // Initialisiere Investitions-Daten wenn Investitionen geladen
  useEffect(() => {
    if (aktiveInvestitionen.length === 0) return

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
      }
    })
    setInvestitionsDaten(initial)
  }, [aktiveInvestitionen])

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
      } else if (inv.typ === 'wechselrichter') {
        pvErzeugung += parseFloat(daten.pv_erzeugung_kwh) || 0
      }
    })

    return { batterieLadung, batterieEntladung, pvErzeugung }
  }, [aktiveInvestitionen, investitionsDaten])

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
          if (daten.entladung_v2h_kwh) parsed.entladung_v2h_kwh = parseFloat(daten.entladung_v2h_kwh)
        } else if (inv.typ === 'speicher') {
          if (daten.ladung_kwh) parsed.ladung_kwh = parseFloat(daten.ladung_kwh)
          if (daten.entladung_kwh) parsed.entladung_kwh = parseFloat(daten.entladung_kwh)
        } else if (inv.typ === 'wallbox') {
          if (daten.ladung_kwh) parsed.ladung_kwh = parseFloat(daten.ladung_kwh)
          if (daten.ladevorgaenge) parsed.ladevorgaenge = parseInt(daten.ladevorgaenge)
        } else if (inv.typ === 'waermepumpe') {
          if (daten.stromverbrauch_kwh) parsed.stromverbrauch_kwh = parseFloat(daten.stromverbrauch_kwh)
          if (daten.heizenergie_kwh) parsed.heizenergie_kwh = parseFloat(daten.heizenergie_kwh)
          if (daten.warmwasser_kwh) parsed.warmwasser_kwh = parseFloat(daten.warmwasser_kwh)
        } else if (inv.typ === 'wechselrichter') {
          if (daten.pv_erzeugung_kwh) parsed.pv_erzeugung_kwh = parseFloat(daten.pv_erzeugung_kwh)
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
        notizen: formData.notizen || undefined,
        investitionen_daten: Object.keys(invDaten).length > 0 ? invDaten : undefined,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  if (invLoading) {
    return <div className="text-center py-4 text-gray-500">Lade Investitionen...</div>
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
            label={hatWechselrichter ? "PV-Erzeugung (Summe oder manuell)" : "PV-Erzeugung (optional)"}
            name="pv_erzeugung_kwh"
            type="number"
            step="0.01"
            min="0"
            value={formData.pv_erzeugung_kwh}
            onChange={handleChange}
            placeholder={berechneteWerte.pvErzeugung > 0 ? `Summe: ${berechneteWerte.pvErzeugung.toFixed(1)}` : "z.B. 800"}
            hint={berechneteWerte.pvErzeugung > 0 ? `Aus Wechselrichtern: ${berechneteWerte.pvErzeugung.toFixed(1)} kWh` : "Wird berechnet wenn leer"}
          />
        </div>
      </div>

      {/* Wechselrichter (falls vorhanden) */}
      {hatWechselrichter && (
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
        <InvestitionSection
          title="Speicher"
          icon={Battery}
          iconColor="text-green-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'speicher')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          felder={[
            { key: 'ladung_kwh', label: 'Ladung', unit: 'kWh', placeholder: 'z.B. 150' },
            { key: 'entladung_kwh', label: 'Entladung', unit: 'kWh', placeholder: 'z.B. 140' },
          ]}
        />
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
          felder={[
            { key: 'km_gefahren', label: 'km gefahren', unit: 'km', placeholder: 'z.B. 1200' },
            { key: 'verbrauch_kwh', label: 'Verbrauch gesamt', unit: 'kWh', placeholder: 'z.B. 216' },
            { key: 'ladung_pv_kwh', label: 'Heim: PV', unit: 'kWh', placeholder: 'z.B. 130', hint: 'Wallbox mit PV-Strom' },
            { key: 'ladung_netz_kwh', label: 'Heim: Netz', unit: 'kWh', placeholder: 'z.B. 50', hint: 'Wallbox mit Netzstrom' },
            { key: 'ladung_extern_kwh', label: 'Extern', unit: 'kWh', placeholder: 'z.B. 36', hint: 'Autobahn, Arbeit, etc.' },
            { key: 'ladung_extern_euro', label: 'Extern Kosten', unit: '€', placeholder: 'z.B. 18.00' },
            { key: 'entladung_v2h_kwh', label: 'V2H Entladung', unit: 'kWh', placeholder: 'z.B. 25' },
          ]}
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
        </div>
      ))}
    </div>
  )
}
