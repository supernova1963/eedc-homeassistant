/**
 * Geteilte Helfer für den InvestitionenStep-Split (Slice 6, Setup-Wizard→V4-SoT).
 */
import { Car, Battery, Plug, Cpu, Flame, Sun, Package } from 'lucide-react'
import type { InvestitionTyp } from '../../../types'

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

/**
 * Ausrichtungs-Optionen — **eine** Liste für PV-Modul und Balkonkraftwerk, aus
 * dem Formular-SoT `forms/sections/investitionFormHelpers.ts`.
 *
 * ⚑ N-174 (2026-08-16): Hier standen bis dahin **zwei** eigene Listen — eine
 * wortgleiche Kopie der neun Optionen für PV-Module und eine auf **sechs**
 * reduzierte fürs Balkonkraftwerk (Nordost, Nord und Nordwest fehlten), mit dem
 * Kommentar „reduziert, wie im Setup bislang". Das ist keine Begründung,
 * sondern eine Feststellung — und die Reduktion war ohnehin wirkungslos: Wer
 * sein BKW im Wizard anlegt und danach **bearbeitet**, bekam im Formular alle
 * neun. Der Wizard war der Ausreißer, nicht das Formular.
 *
 * Re-Export statt Direktimport an den Aufrufstellen, damit dieser Helfer die
 * eine Anlaufstelle des Wizards bleibt.
 */
export { AUSRICHTUNG_OPTIONEN } from '../../forms/sections/investitionFormHelpers'
