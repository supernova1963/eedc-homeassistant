/**
 * UeberblickBlock — Inhalt des Hub-Blocks «Überblick» (Konzept #433 Stufe 2,
 * P-433-2 E1/E2).
 *
 * Links das Schaubild (Panorama + Energiefluss-Kacheln aller Geräte des Typs,
 * E-P2-2), rechts «Auf einen Blick» für das gewählte Gerät — Desktop 2/3 zu 1/3
 * wie Cockpit → Live, auf dem Handy gestapelt. Beide sind einzeln parkbar
 * (`el:ueberblick-schaubild`, `el:ueberblick-karte`); ist einer geparkt, nimmt
 * der andere die Breite.
 *
 * **Der Poll lebt hier, im Blockinhalt** (W10): eingeklappt oder geparkt rendert
 * `BlockShell` den Inhalt nicht, der Hook ist nicht montiert, es läuft kein
 * Abruf. Deshalb braucht der Block keinen `aktiv`-Prop, und seine Summary ist
 * statisch.
 */
import { useMemo } from 'react'
import { Parkbar, usePark } from '../../park'
import { useChartTheme } from '../../../context/ThemeContext'
import { useDemoMode } from '../../../v4/status/AppStatusContext'
import type { Investition } from '../../../types'
import { baueUeberblickKacheln } from './kachelAnker'
import UeberblickKarte from './UeberblickKarte'
import UeberblickSchaubild from './UeberblickSchaubild'
import { useLiveUeberblick } from './useLiveUeberblick'

/** Park-IDs der zwei Elemente des Blocks. */
export const UEBERBLICK_PARK_IDS = ['el:ueberblick-schaubild', 'el:ueberblick-karte'] as const

export interface UeberblickBlockProps {
  anlageId: number
  /** Alle Geräte des Typs — ihre Kacheln stehen im Bild. */
  geraete: Investition[]
  /** Das gewählte Gerät — seine Karte steht rechts. */
  inv: Investition
}

export default function UeberblickBlock({ anlageId, geraete, inv }: UeberblickBlockProps) {
  const { demoMode } = useDemoMode()
  const { live, wetter, tag } = useLiveUeberblick(anlageId, demoMode)
  const achsen = useChartTheme()
  const park = usePark()
  const { kacheln, ohneSensor } = useMemo(
    () => baueUeberblickKacheln({ geraete, live, wetter, referenz: achsen.referenz }),
    [geraete, live, wetter, achsen.referenz],
  )
  const beide = !UEBERBLICK_PARK_IDS.some((id) => park.istGeparkt(id))

  return (
    <div className={`grid grid-cols-1 gap-4${beide ? ' xl:grid-cols-3' : ''}`} data-ueberblick-block>
      <Parkbar id="el:ueberblick-schaubild" titel="Schaubild" className={beide ? 'xl:col-span-2' : undefined}>
        <UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} />
      </Parkbar>
      <Parkbar id="el:ueberblick-karte" titel="Auf einen Blick">
        <UeberblickKarte inv={inv} live={live} wetter={wetter} tag={tag} mehrereGeraete={geraete.length > 1} />
      </Parkbar>
    </div>
  )
}
