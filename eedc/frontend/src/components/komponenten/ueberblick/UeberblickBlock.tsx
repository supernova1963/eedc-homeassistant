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
import { baueFahrzeugKacheln, baueLadepunktKacheln } from './emobKachelAnker'
import { emobPanorama } from './emobPanoramaAnker'
import { baueUeberblickKacheln } from './kachelAnker'
import UeberblickKarte from './UeberblickKarte'
import UeberblickKarteEmob from './UeberblickKarteEmob'
import UeberblickSchaubild from './UeberblickSchaubild'
import { useLiveUeberblick } from './useLiveUeberblick'
import { WAERME_PANORAMA_DEF } from './waermePanoramaAnker'

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
    () => baueUeberblickKacheln({ geraete, live, wetter, referenz: achsen.referenz, tag }),
    [geraete, live, wetter, achsen.referenz, tag],
  )
  const beide = !UEBERBLICK_PARK_IDS.some((id) => park.istGeparkt(id))

  return (
    <div className={`grid grid-cols-1 gap-4${beide ? ' xl:grid-cols-3' : ''}`} data-ueberblick-block>
      <Parkbar id="el:ueberblick-schaubild" titel="Schaubild" className={beide ? 'xl:col-span-2' : undefined}>
        <UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} panorama={WAERME_PANORAMA_DEF} />
      </Parkbar>
      <Parkbar id="el:ueberblick-karte" titel="Auf einen Blick">
        <UeberblickKarte inv={inv} live={live} wetter={wetter} tag={tag} mehrereGeraete={geraete.length > 1} />
      </Parkbar>
    </div>
  )
}

/**
 * Der Block «Überblick» der Typ-Seiten Wallbox und E-Auto (P-433-2b K1; Schaubild seit S1b, Bauplan Fassung 2 §9):
 * dieselbe Bauform wie Wärme/Klima — links das Schaubild, rechts «Auf einen Blick», je einzeln parkbar mit denselben
 * Park-IDs ({@link UEBERBLICK_PARK_IDS}). **Die Szene gehört dem gewählten Gerät** (E-2b-22): Wallbox ⇒ Szene
 * «Ladepunkt», E-Auto ⇒ Szene «Fahrzeug» ({@link emobPanorama}); die Kacheln bauen `baueLadepunktKacheln` bzw.
 * `baueFahrzeugKacheln` für `inv` — ein Selektor-Wechsel wechselt Bild-Kacheln und Karte zusammen. Neben dem Schaubild
 * stehen die Karten ab `xl` untereinander (`nebenSchaubild`); ist das Schaubild geparkt, nebeneinander in voller Breite.
 * Derselbe Live-Hook (Poll nur, solange der Inhalt montiert und die Seite sichtbar ist).
 */
export function UeberblickBlockEmob({ anlageId, geraete, inv }: UeberblickBlockProps) {
  const { demoMode } = useDemoMode()
  const { live, tag } = useLiveUeberblick(anlageId, demoMode)
  const achsen = useChartTheme()
  const park = usePark()
  const istWallbox = inv.typ === 'wallbox'
  const { kacheln, ohneSensor } = useMemo(
    () => (istWallbox ? baueLadepunktKacheln : baueFahrzeugKacheln)({ inv, geraete, live, tag, referenz: achsen.referenz }),
    [istWallbox, inv, geraete, live, tag, achsen.referenz],
  )
  const beide = !UEBERBLICK_PARK_IDS.some((id) => park.istGeparkt(id))

  return (
    <div className={`grid grid-cols-1 gap-4${beide ? ' xl:grid-cols-3' : ''}`} data-ueberblick-block>
      <Parkbar id="el:ueberblick-schaubild" titel="Schaubild" className={beide ? 'xl:col-span-2' : undefined}>
        <UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} panorama={emobPanorama(inv.typ)} />
      </Parkbar>
      <Parkbar id="el:ueberblick-karte" titel="Auf einen Blick">
        <UeberblickKarteEmob inv={inv} live={live} tag={tag} mehrereGeraete={geraete.length > 1} nebenSchaubild={beide} />
      </Parkbar>
    </div>
  )
}
