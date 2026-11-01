/**
 * Park-IDs des Hub-Blocks «Überblick» (P-433-2b S1c, Go Gernot 1.11.2026, Entscheid Master «Option C»).
 *
 * Der Block hat bis zu vier parkbare Teile: das Schaubild und je Karte von «Auf einen Blick» eine Hülle —
 * Gerät · Heute · Betrieb, in beiden Hubs (Wärme/Klima und E-Mobilität) mit denselben IDs. **Gerät und Schaubild
 * werden immer gerendert, Heute und Betrieb nur mit Werten** (Handbuch «Eine Zeile oder Karte ohne Wert entfällt»).
 *
 * ⛔ Deshalb steht in der **festen** Liste {@link UEBERBLICK_PARK_IDS} nur, was unbedingt gerendert wird
 * (`check:park-idliste` L2); Heute und Betrieb kommen aus den Daten ({@link ueberblickGemeldeteIds}, Muster
 * `aufEinenBlickVerfuegbar`/`zaehlerParkIds`). Das Block-Gate in `KomponentenTypV4` folgt dem Muster `regVerstecken`:
 * der Block **meldet** seine gerenderten IDs nach der ersten Live- und Tag-Antwort hoch, versteckt wird er nur, wenn
 * eine Meldung vorliegt und alle gemeldeten IDs geparkt sind — vorher bleibt er montiert und der Poll läuft.
 *
 * **Alte Park-ID** `el:ueberblick-karte` (die ganze Karte, bis S1c): steht sie im Park-Zustand, gelten alle drei
 * Karten als geparkt ({@link ueberblickGeparkt}); ihr Chip «Auf einen Blick» auf dem Parkplatz holt alle drei zurück.
 * Der Park-Rahmen bleibt unverändert — er lädt unbekannte IDs und zeigt sie als Chip.
 */

/** Park-IDs der Teile, die **immer** gerendert werden — Schaubild und Gerätekarte (L2: keine bedingte ID hier). */
export const UEBERBLICK_PARK_IDS = ['el:ueberblick-schaubild', 'el:ueberblick-karte-geraet'] as const

/** Die drei Karten-Hüllen von «Auf einen Blick». */
export const UEBERBLICK_KARTE = {
  geraet: 'el:ueberblick-karte-geraet',
  heute: 'el:ueberblick-karte-heute',
  betrieb: 'el:ueberblick-karte-betrieb',
} as const

/** Die Park-ID der ganzen Karte bis S1c — gilt beim Lesen als «alle drei Karten geparkt». */
export const UEBERBLICK_ALT_KARTE = 'el:ueberblick-karte'

/** Welche datenabhängigen Karten erscheinen unter den aktuellen Daten? */
export interface UeberblickKartenTeile {
  heute: boolean
  betrieb: boolean
}

const KARTEN_IDS: readonly string[] = Object.values(UEBERBLICK_KARTE)

/** Ist dieser Teil geparkt — unter Abbildung der alten ID `el:ueberblick-karte` auf die drei Karten? */
export function ueberblickGeparkt(istGeparkt: (id: string) => boolean, id: string): boolean {
  return istGeparkt(id) || (KARTEN_IDS.includes(id) && istGeparkt(UEBERBLICK_ALT_KARTE))
}

/** Die Park-IDs, die der Block unter diesen Daten rendert — das, was er hochmeldet. */
export function ueberblickGemeldeteIds(teile: UeberblickKartenTeile): string[] {
  return [
    ...UEBERBLICK_PARK_IDS,
    ...(teile.heute ? [UEBERBLICK_KARTE.heute] : []),
    ...(teile.betrieb ? [UEBERBLICK_KARTE.betrieb] : []),
  ]
}

/** Steht mindestens eine Karte von «Auf einen Blick» offen (gerendert und nicht geparkt)? */
export function ueberblickKarteOffen(istGeparkt: (id: string) => boolean, teile: UeberblickKartenTeile): boolean {
  const offen = (id: string) => !ueberblickGeparkt(istGeparkt, id)
  return offen(UEBERBLICK_KARTE.geraet)
    || (teile.heute && offen(UEBERBLICK_KARTE.heute))
    || (teile.betrieb && offen(UEBERBLICK_KARTE.betrieb))
}
