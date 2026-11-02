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
 *
 * **Fokus (Nachlauf 4.2.1):** im Block-Fokus (`vollbild`, BlockShell ⤢ oder `?fokus=ueberblick`) füllt das Schaubild
 * die Höhe (N2). Daneben trägt das Schaubild seinen eigenen ⤢ «Schaubild: Fokus / Vollbild» (N3): ein
 * `FokusVollbild` nur mit dem Bild, mit «Link / Einbetten» unter der Fokus-ID {@link SCHAUBILD_FOKUS_ID}. Den
 * Deep-Link `#/komponenten/<typ>?fokus=ueberblick:schaubild` rendert der Hub über `schaubildDeepLink` — dann zeigt
 * der Block nur dieses Overlay, rahmenlos. Das Gerät ist das gewählte der Seite; bei ≥ 2 Geräten des Typs schreibt
 * «Link / Einbetten» es als `&geraet=<investition_id>` in die Adresse (N5, `einbettenZusatz` vom Hub), und der Hub wählt
 * es beim Laden wieder.
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Image as BildIcon, Maximize2 } from 'lucide-react'
import { FokusVollbild } from '../../blocks/FokusVollbild'
import { EinbettenKnopf } from '../../blocks/EinbettenKnopf'
import { useDeepLinkFokus } from '../../../hooks/useDeepLinkFokus'
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
import type { PanoramaDef } from './panorama'
import type { UeberblickKachel } from './kachelAnker'
import { useLiveUeberblick } from './useLiveUeberblick'
import { WAERME_PANORAMA_DEF } from './waermePanoramaAnker'

export { UEBERBLICK_PARK_IDS } from './ueberblickPark'

/**
 * N3: Fokus-ID des Schaubilds allein — öffentlicher Vertrag wie jede Fokus-ID (`fokus-id-vertrag.test.ts`; geerntet
 * wird das Literal am `EinbettenKnopf` unten, diese Konstante dient dem Vergleich im Hub).
 */
export const SCHAUBILD_FOKUS_ID = 'ueberblick:schaubild'

export interface UeberblickBlockProps {
  anlageId: number
  /** Alle Geräte des Typs — ihre Kacheln stehen im Bild. */
  geraete: Investition[]
  /** Das gewählte Gerät — seine Karte steht rechts. */
  inv: Investition
  /** S1c: meldet die gerenderten Park-IDs an das Block-Gate des Hubs (`KomponentenTypV4`, Muster `regVerstecken`). */
  meldeParkIds?: (ids: string[]) => void
  /** N2: der Block steht im Fokus/Vollbild (`Block.render(fokus)`) — das Schaubild füllt dort die Höhe. */
  vollbild?: boolean
  /** N3: Deep-Link `?fokus=ueberblick:schaubild` — nur das Schaubild-Vollbild, rahmenlos (der Hub entscheidet). */
  schaubildDeepLink?: boolean
  /** N5: Zusatz für «Link / Einbetten» am Schaubild-⤢ (`{ geraet: '<id>' }` bei ≥ 2 Geräten; der Hub entscheidet). */
  einbettenZusatz?: Record<string, string>
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
  return { beide: schaubildOffen && karteOffen, karteOffen, schaubildOffen }
}

/** N3: das Schaubild allein im Fokus/Vollbild — Titel «Überblick · Schaubild», Icon des Blocks, «Link / Einbetten». */
function SchaubildVollbild({ deepLink, zusatz, onClose, children }: {
  deepLink: boolean; zusatz?: Record<string, string>; onClose: () => void; children: ReactNode
}) {
  return (
    <FokusVollbild
      titel="Überblick · Schaubild" icon={BildIcon}
      deepLink={deepLink}
      aktionen={(ansicht) => <EinbettenKnopf fokusId="ueberblick:schaubild" ansicht={ansicht} zusatz={zusatz} />}
      onClose={onClose}
    >
      {children}
    </FokusVollbild>
  )
}

/**
 * N2: im Vollbild trägt das Raster ab `xl` die volle Höhe des Overlay-Inhalts, in **einer** Zeile `minmax(0, 1fr)` — eine
 * `auto`-Zeile wüchse auf die Mindesthöhe des breiten Bildes (gemessen in Chromium 1920 × 700: Raster 797 px statt 596 px),
 * und das Bild folgte wieder der Breite. Unter `xl` stapeln Bild und Karten, die Höhe folgt dort der Breite.
 */
const RASTER_VOLLBILD = 'xl:h-full xl:grid-rows-[minmax(0,1fr)]'

interface RasterProps extends Pick<UeberblickBlockProps, 'vollbild' | 'schaubildDeepLink' | 'einbettenZusatz'> {
  kacheln: UeberblickKachel[]
  ohneSensor: string[]
  panorama: PanoramaDef
  park: ReturnType<typeof useUeberblickPark>
  /** «Auf einen Blick» — schon mit `nebenSchaubild` gebaut; nur gerendert, wenn eine Karte offen ist. */
  karte: ReactNode
}

/**
 * Raster beider Blöcke: Schaubild (parkbar) und «Auf einen Blick». N2: im Vollbild trägt das Raster ab `xl` die volle
 * Höhe ({@link RASTER_VOLLBILD}), damit das Schaubild sie füllen kann (nur mit offenem Schaubild — sonst würden die
 * Karten gestreckt). N3: der ⤢ am Schaubild öffnet das Schaubild allein; im Block-Fokus und in jeder Deep-Link-Ansicht
 * fehlt er (dort gibt es nichts zu vergrößern bzw. keinen Weg zurück, Muster Energiefluss). Die Seite darunter bleibt
 * montiert (ein Abruf für beide Darstellungen, kein Sprung beim Schließen).
 */
function UeberblickRaster({ kacheln, ohneSensor, panorama, park, karte, vollbild = false, schaubildDeepLink = false, einbettenZusatz }: RasterProps) {
  const deep = useDeepLinkFokus()
  const [fokus, setFokus] = useState(false)
  const bild = (imVollbild: boolean, kopfAktion?: ReactNode) => (
    <UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} panorama={panorama} vollbild={imVollbild} kopfAktion={kopfAktion} />
  )
  if (schaubildDeepLink) return <SchaubildVollbild deepLink zusatz={einbettenZusatz} onClose={() => {}}>{bild(true)}</SchaubildVollbild>

  // D14-16: unter 640 px ausgeblendet (nicht entfernt) wie das ⤢ am Energiefluss.
  const knopf = vollbild || deep.deepLink ? undefined : (
    <button
      type="button"
      onClick={() => setFokus(true)}
      aria-label="Schaubild: Fokus / Vollbild"
      className="max-sm:hidden p-1 rounded bg-white/80 dark:bg-gray-800/80 text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200"
    >
      <Maximize2 className="h-4 w-4" />
    </button>
  )
  const { beide, karteOffen, schaubildOffen } = park
  return (
    <div className={`grid grid-cols-1 gap-4${beide ? ' xl:grid-cols-3' : ''}${vollbild && schaubildOffen ? ` ${RASTER_VOLLBILD}` : ''}`} data-ueberblick-block>
      {fokus && <SchaubildVollbild deepLink={false} zusatz={einbettenZusatz} onClose={() => setFokus(false)}>{bild(true)}</SchaubildVollbild>}
      <Parkbar id="el:ueberblick-schaubild" titel="Schaubild" className={beide ? 'xl:col-span-2' : undefined}>
        {bild(vollbild, knopf)}
      </Parkbar>
      {karteOffen && karte}
    </div>
  )
}

export default function UeberblickBlock({ anlageId, geraete, inv, meldeParkIds, vollbild, schaubildDeepLink, einbettenZusatz }: UeberblickBlockProps) {
  const { demoMode } = useDemoMode()
  const { live, wetter, tag } = useLiveUeberblick(anlageId, demoMode)
  const achsen = useChartTheme()
  const { kacheln, ohneSensor } = useMemo(
    () => baueUeberblickKacheln({ geraete, live, wetter, referenz: achsen.referenz, tag }),
    [geraete, live, wetter, achsen.referenz, tag],
  )
  const mehrereGeraete = geraete.length > 1
  const teile = waermeKartenTeile({ inv, live, tag, mehrereGeraete })
  const park = useUeberblickPark(teile, live != null && tag != null, meldeParkIds)

  return (
    <UeberblickRaster
      kacheln={kacheln} ohneSensor={ohneSensor} panorama={WAERME_PANORAMA_DEF} park={park}
      vollbild={vollbild} schaubildDeepLink={schaubildDeepLink} einbettenZusatz={einbettenZusatz}
      karte={<UeberblickKarte inv={inv} live={live} wetter={wetter} tag={tag} mehrereGeraete={mehrereGeraete} nebenSchaubild={park.beide} />}
    />
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
export function UeberblickBlockEmob({ anlageId, geraete, inv, meldeParkIds, vollbild, schaubildDeepLink, einbettenZusatz }: UeberblickBlockProps) {
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
  const park = useUeberblickPark(teile, live != null && tag != null, meldeParkIds)

  return (
    <UeberblickRaster
      kacheln={kacheln} ohneSensor={ohneSensor} panorama={emobPanorama(inv.typ)} park={park}
      vollbild={vollbild} schaubildDeepLink={schaubildDeepLink} einbettenZusatz={einbettenZusatz}
      karte={<UeberblickKarteEmob {...kartenProps} nebenSchaubild={park.beide} />}
    />
  )
}
