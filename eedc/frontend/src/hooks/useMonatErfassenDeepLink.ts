/**
 * useMonatErfassenDeepLink — Deep-Link der Monatsdaten (`?erfassen=YYYY-MM[&geraet=<id>][&feld=<key>]`).
 *
 * B5: die V4-Fusszeile und «Beheben» im Daten-Checker navigieren hierher → das Formular des Monats öffnet; die Parameter
 * werden danach entfernt, damit Neuladen/Zurück sie nicht erneut auslöst (EinstellungenV4 klappt parallel den Block auf).
 * N-792: das Öffnen wartet, bis die Monatsliste geladen ist — vorher kennt `oeffneMonat` keine Zeile und wählte für
 * einen vorhandenen Monat das Formular «erfassen» (Speichern ⇒ 409). Je Parameterwert öffnet es genau einmal.
 * E4 (Daten-Checker «Sprung aufs Feld», aus `MonatsdatenTeile.tsx` hierher gezogen, Verhalten von `erfassen`
 * unverändert): `feld` (mit `geraet` das Gerätefeld `inv-<geraet>-<feld>`) liefert den Selektor, auf den das Formular
 * springt (`MonatsdatenForm` Prop `fokusFeld`); `geraet` allein springt zum ersten Feld des Geräts.
 */
import { useEffect } from 'react'
import { feldSelektor } from '../lib/sprungFeld'
import { useSprungParameter } from './useSprungParameter'

const MONAT_SPRUNG = ['erfassen', 'geraet', 'feld'] as const

export function useMonatErfassenDeepLink(
  loading: boolean, oeffneMonat: (jahr: number, monat: number) => void,
): { fokusFeld: string | null; fokusFertig: () => void } {
  const [werte, fokusFertig] = useSprungParameter(MONAT_SPRUNG, !loading)
  useEffect(() => {
    if (!werte) return
    const [j, m] = (werte.erfassen ?? '').split('-').map(Number)
    if (j && m >= 1 && m <= 12) oeffneMonat(j, m)
    else fokusFertig()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [werte])
  const geraet = werte?.geraet && /^\d+$/.test(werte.geraet) ? werte.geraet : null
  let fokusFeld: string | null = null
  if (werte?.erfassen && werte.feld) fokusFeld = feldSelektor(geraet ? `inv-${geraet}-${werte.feld}` : werte.feld)
  else if (werte?.erfassen && geraet) fokusFeld = `[data-feld^="inv-${geraet}-"]`
  return { fokusFeld, fokusFertig }
}
