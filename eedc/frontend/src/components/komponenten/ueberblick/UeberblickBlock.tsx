/**
 * UeberblickBlock — Inhalt des Hub-Blocks «Überblick» (Konzept #433 Stufe 2,
 * P-433-2 E1/E2).
 *
 * Links das Schaubild (Panorama + Energiefluss-Kacheln aller Geräte des Typs,
 * E-P2-2), rechts «Auf einen Blick» für das gewählte Gerät — Desktop 2/3 zu 1/3
 * wie Cockpit → Live, auf dem Handy gestapelt. Einzeln parkbar sind das Schaubild
 * (`el:ueberblick-schaubild`) und seit P-433-2b S1c jede Karte (Gerät · Heute ·
 * Betrieb, `ueberblickPark.ts`). Schaubild offen und mindestens eine Karte offen ⇒
 * 2/3 zu 1/3; Schaubild geparkt ⇒ die offenen Karten nebeneinander in voller Breite;
 * alle Karten geparkt ⇒ das Schaubild in voller Breite.
 *
 * **Meldung (S1c, Muster `regVerstecken`):** nach der ersten Live- und Tag-Antwort
 * meldet der Block die Park-IDs, die er rendert, über `meldeParkIds` hoch; der Hub
 * versteckt ihn erst, wenn eine Meldung vorliegt und alle gemeldeten IDs geparkt
 * sind. **Benannte Grenze:** ein ausgeblendeter Block ist nicht montiert und fragt
 * nicht ab — ein Teil, das später am Tag Werte bekommt, erscheint beim nächsten
 * Aufruf der Seite.
 *
 * **Der Poll lebt hier, im Blockinhalt** (W10): eingeklappt oder geparkt rendert
 * `BlockShell` den Inhalt nicht, der Hook ist nicht montiert, es läuft kein
 * Abruf. Deshalb braucht der Block keinen `aktiv`-Prop, und seine Summary ist
 * statisch.
 */
import { useEffect, useMemo, useRef } from 'react'
import { Parkbar, usePark } from '../../park'
import { useChartTheme } from '../../../context/ThemeContext'
import { useDemoMode } from '../../../v4/status/AppStatusContext'
import type { Investition } from '../../../types'
import { baueFahrzeugKacheln, baueLadepunktKacheln } from './emobKachelAnker'
import { emobPanorama } from './emobPanoramaAnker'
import { baueUeberblickKacheln } from './kachelAnker'
import UeberblickKarte, { waermeKartenTeile } from './UeberblickKarte'
import UeberblickKarteEmob, { emobKartenTeile } from './UeberblickKarteEmob'
import { ueberblickGemeldeteIds, ueberblickGeparkt, ueberblickKarteOffen, type UeberblickKartenTeile } from './ueberblickPark'
import UeberblickSchaubild from './UeberblickSchaubild'
import { useLiveUeberblick } from './useLiveUeberblick'
import { WAERME_PANORAMA_DEF } from './waermePanoramaAnker'

export { UEBERBLICK_PARK_IDS } from './ueberblickPark'
export interface UeberblickBlockProps {
  anlageId: number
  /** Alle Geräte des Typs — ihre Kacheln stehen im Bild. */
  geraete: Investition[]
  /** Das gewählte Gerät — seine Karte steht rechts. */
  inv: Investition
  /** S1c: meldet die gerenderten Park-IDs an das Block-Gate des Hubs (`KomponentenTypV4`, Muster `regVerstecken`). */
  meldeParkIds?: (ids: string[]) => void
}

/**
 * Spaltenlogik und Meldung beider Blöcke (S1c). Gemeldet wird erst, wenn Live- **und** Tag-Antwort da sind — vorher
 * wüsste der Block nicht, ob Heute/Betrieb erscheinen, und der Hub könnte ihn vor dem ersten Poll verstecken.
 */
function useUeberblickPark(teile: UeberblickKartenTeile, geladen: boolean, meldeParkIds: UeberblickBlockProps['meldeParkIds']) {
  const park = usePark()
  const schaubildOffen = !ueberblickGeparkt(park.istGeparkt, 'el:ueberblick-schaubild')
  const karteOffen = ueberblickKarteOffen(park.istGeparkt, teile)
  const melde = useRef(meldeParkIds)
  melde.current = meldeParkIds
  const gemeldet = ueberblickGemeldeteIds(teile).join('|')
  useEffect(() => {
    if (geladen) melde.current?.(gemeldet.split('|'))
  }, [geladen, gemeldet])
  return { beide: schaubildOffen && karteOffen, karteOffen }
}

export default function UeberblickBlock({ anlageId, geraete, inv, meldeParkIds }: UeberblickBlockProps) {
  const { demoMode } = useDemoMode()
  const { live, wetter, tag } = useLiveUeberblick(anlageId, demoMode)
  const achsen = useChartTheme()
  const { kacheln, ohneSensor } = useMemo(
    () => baueUeberblickKacheln({ geraete, live, wetter, referenz: achsen.referenz, tag }),
    [geraete, live, wetter, achsen.referenz, tag],
  )
  const mehrereGeraete = geraete.length > 1
  const teile = waermeKartenTeile({ inv, live, tag, mehrereGeraete })
  const { beide, karteOffen } = useUeberblickPark(teile, live != null && tag != null, meldeParkIds)

  return (
    <div className={`grid grid-cols-1 gap-4${beide ? ' xl:grid-cols-3' : ''}`} data-ueberblick-block>
      <Parkbar id="el:ueberblick-schaubild" titel="Schaubild" className={beide ? 'xl:col-span-2' : undefined}>
        <UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} panorama={WAERME_PANORAMA_DEF} />
      </Parkbar>
      {karteOffen && (
        <UeberblickKarte inv={inv} live={live} wetter={wetter} tag={tag} mehrereGeraete={mehrereGeraete} nebenSchaubild={beide} />
      )}
    </div>
  )
}

/**
 * Der Block «Überblick» der Typ-Seiten Wallbox und E-Auto (P-433-2b K1; Schaubild seit S1b, Bauplan Fassung 2 §9):
 * dieselbe Bauform wie Wärme/Klima — links das Schaubild, rechts «Auf einen Blick», Schaubild und jede Karte einzeln
 * parkbar mit denselben Park-IDs (`ueberblickPark.ts`, S1c). **Die Szene gehört dem gewählten Gerät** (E-2b-22): Wallbox ⇒ Szene
 * «Ladepunkt», E-Auto ⇒ Szene «Fahrzeug» ({@link emobPanorama}); die Kacheln bauen `baueLadepunktKacheln` bzw.
 * `baueFahrzeugKacheln` für `inv` — ein Selektor-Wechsel wechselt Bild-Kacheln und Karte zusammen. Neben dem Schaubild
 * stehen die Karten ab `xl` untereinander (`nebenSchaubild`); ist das Schaubild geparkt, nebeneinander in voller Breite.
 * Derselbe Live-Hook (Poll nur, solange der Inhalt montiert und die Seite sichtbar ist).
 */
export function UeberblickBlockEmob({ anlageId, geraete, inv, meldeParkIds }: UeberblickBlockProps) {
  const { demoMode } = useDemoMode()
  const { live, tag } = useLiveUeberblick(anlageId, demoMode)
  const achsen = useChartTheme()
  const istWallbox = inv.typ === 'wallbox'
  const { kacheln, ohneSensor } = useMemo(
    () => (istWallbox ? baueLadepunktKacheln : baueFahrzeugKacheln)({ inv, geraete, live, tag, referenz: achsen.referenz }),
    [istWallbox, inv, geraete, live, tag, achsen.referenz],
  )
  const kartenProps = { inv, live, tag, mehrereGeraete: geraete.length > 1 }
  const teile = emobKartenTeile(kartenProps)
  const { beide, karteOffen } = useUeberblickPark(teile, live != null && tag != null, meldeParkIds)

  return (
    <div className={`grid grid-cols-1 gap-4${beide ? ' xl:grid-cols-3' : ''}`} data-ueberblick-block>
      <Parkbar id="el:ueberblick-schaubild" titel="Schaubild" className={beide ? 'xl:col-span-2' : undefined}>
        <UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} panorama={emobPanorama(inv.typ)} />
      </Parkbar>
      {karteOffen && <UeberblickKarteEmob {...kartenProps} nebenSchaubild={beide} />}
    </div>
  )
}
