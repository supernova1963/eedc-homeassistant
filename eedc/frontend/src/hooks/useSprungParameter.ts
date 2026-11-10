/**
 * useSprungParameter — die **eine** Lesestelle der Sprung-Parameter einer Zielseite (Etappe E4 «Daten-Checker: ein
 * Handgriff je Befund», Konzept §3.3 S2; Wächter W-5 `src/test/sprungziele.test.ts`).
 *
 * Liest die genannten Parameter aus der Adresse, sobald `bereit` gilt (die Seite hat ihre Liste geladen), und **entfernt
 * sie danach** (`replace`) — ein Neuladen oder «Zurück» öffnet nichts erneut (Muster `?bearbeiten=`, N-792). Die Werte
 * bleiben im Zustand, bis die Seite `fertig()` ruft (Sprung erledigt); schon im ersten Render stehen sie bereit, damit
 * ein zugeklappter Abschnitt beim Mount offen startet (`lib/sprungFeld.ts`).
 *
 * `nurBeiBlock`: auf einer Einstellungs-Kategorie mit mehreren Blöcken (Stammdaten: Anlage · Strompreise ·
 * Solarprognose) gilt ein Sprung nur dem Block, den `block=` aufklappt — `block` selbst liest und behält
 * `EinstellungenV4`; hier wird er nur verglichen.
 */
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

export type SprungWerte<K extends string> = Partial<Record<K, string>>

export function useSprungParameter<K extends string>(
  namen: readonly K[], bereit = true, nurBeiBlock?: string,
): [SprungWerte<K> | null, () => void] {
  const [searchParams, setSearchParams] = useSearchParams()
  const zustaendig = bereit && (nurBeiBlock === undefined || searchParams.getAll('block').includes(nurBeiBlock))
  const [werte, setWerte] = useState<SprungWerte<K> | null>(null)
  const roh = namen.map((n) => searchParams.get(n))
  const schluessel = roh.join('\u0000')
  // Ein Objekt je Parameter-Stand (gleiche Identität über die Renders) — Effekte der Seite laufen je Sprung einmal.
  const aktuell = useMemo<SprungWerte<K> | null>(() => (
    zustaendig && roh.some((r) => r != null)
      ? Object.fromEntries(namen.flatMap((n, i) => (roh[i] != null ? [[n, roh[i]]] : []))) as SprungWerte<K>
      : null
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ), [schluessel, zustaendig])

  useEffect(() => {
    if (!aktuell) return
    setWerte(aktuell)
    const next = new URLSearchParams(searchParams)
    namen.forEach((n) => next.delete(n))
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schluessel, zustaendig])

  return [werte ?? aktuell, () => setWerte(null)]
}

export default useSprungParameter
