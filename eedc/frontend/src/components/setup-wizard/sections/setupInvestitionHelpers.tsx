/**
 * Geteilte Helfer für den InvestitionenStep-Split (Slice 6, Setup-Wizard→V4-SoT).
 */
import { Car, Battery, Plug, Cpu, Flame, Sun, Package } from 'lucide-react'
import type { InvestitionTyp } from '../../../types'
import type { SelectOption } from '../../ui/Select'

/** Geräte-Icon je Investitionstyp (Setup-Wizard-Kacheln/Header). */
export function getDeviceIcon(typ: InvestitionTyp) {
  switch (typ) {
    case 'e-auto': return <Car className="w-5 h-5" />
    case 'speicher': return <Battery className="w-5 h-5" />
    case 'wallbox': return <Plug className="w-5 h-5" />
    case 'wechselrichter': return <Cpu className="w-5 h-5" />
    case 'waermepumpe': return <Flame className="w-5 h-5" />
    case 'balkonkraftwerk':
    case 'pv-module': return <Sun className="w-5 h-5" />
    default: return <Package className="w-5 h-5" />
  }
}

/** Ausrichtungs-Optionen PV-Modul (voll) — Setup behält den bestehenden Umfang. */
export const PV_AUSRICHTUNG_OPTIONEN: SelectOption[] = [
  { value: 'Süd', label: 'Süd (0°)' },
  { value: 'Südost', label: 'Südost (-45°)' },
  { value: 'Ost', label: 'Ost (-90°)' },
  { value: 'Nordost', label: 'Nordost (-135°)' },
  { value: 'Nord', label: 'Nord (180°)' },
  { value: 'Nordwest', label: 'Nordwest (135°)' },
  { value: 'West', label: 'West (90°)' },
  { value: 'Südwest', label: 'Südwest (45°)' },
  { value: 'Ost-West', label: 'Ost-West (gemischt)' },
]

/** Ausrichtungs-Optionen Balkonkraftwerk (reduziert, wie im Setup bislang). */
export const BKW_AUSRICHTUNG_OPTIONEN: SelectOption[] = [
  { value: 'Süd', label: 'Süd (0°)' },
  { value: 'Südost', label: 'Südost (-45°)' },
  { value: 'Ost', label: 'Ost (-90°)' },
  { value: 'West', label: 'West (90°)' },
  { value: 'Südwest', label: 'Südwest (45°)' },
  { value: 'Ost-West', label: 'Ost-West (gemischt)' },
]
