import type { InvestitionTyp } from '../../../../types'
import type { TypFelderProps } from './types'
import { EAutoFelder } from './EAutoFelder'
import { SpeicherFelder } from './SpeicherFelder'
import { WaermepumpeFelder } from './WaermepumpeFelder'
import { WallboxFelder } from './WallboxFelder'
import { WechselrichterFelder } from './WechselrichterFelder'
import { PvModulFelder } from './PvModulFelder'
import { BalkonkraftwerkFelder } from './BalkonkraftwerkFelder'
import { SonstigesFelder } from './SonstigesFelder'

/**
 * Dispatcher für die typ-spezifischen Investitions-Parameterfelder (Slice 5).
 * Ersetzt den früheren 8-Wege-`switch` im Monolithen — je Typ eine eigene Datei.
 */
export function InvestitionTypFelder({ typ, ...props }: TypFelderProps & { typ: InvestitionTyp }) {
  switch (typ) {
    case 'e-auto': return <EAutoFelder {...props} />
    case 'speicher': return <SpeicherFelder {...props} />
    case 'waermepumpe': return <WaermepumpeFelder {...props} />
    case 'wallbox': return <WallboxFelder {...props} />
    case 'wechselrichter': return <WechselrichterFelder {...props} />
    case 'pv-module': return <PvModulFelder {...props} />
    case 'balkonkraftwerk': return <BalkonkraftwerkFelder {...props} />
    case 'sonstiges': return <SonstigesFelder {...props} />
    default: return null
  }
}

export type { TypFelderProps } from './types'
