/**
 * Live-Daten für den Hub-Block «Überblick» (P-433-2 E1, Gegenentwurf W10).
 *
 * Dieselben Endpunkte und Takte wie Cockpit → Live (`CockpitLiveV4.tsx`:
 * Live 5 s, Wetter 5 min) plus das Tag-Detail von heute (5 min) für Wärme und
 * Arbeitszahl je Gerät. **Ein eigener Hook** (E-P2-4): das Poll-Muster steht
 * damit zweimal im Client; die Zusammenführung ist ein eigenes Vorhaben.
 *
 * **Wann gepollt wird:** nur solange der Hook lebt UND die Seite sichtbar ist.
 * Der Hook steht im Blockinhalt — eingeklappt oder geparkt ist der Inhalt nicht
 * gemountet (`BlockShell`), dann läuft kein Abruf (kein `aktiv`-Prop nötig).
 * Unsichtbare Seite ⇒ Intervalle aus; Rückkehr ⇒ sofort auffrischen und neu
 * starten (Sichtbarkeitsregel wie `CockpitLiveV4.tsx`).
 *
 * Fehlschläge bleiben still: die Kacheln fehlen, die Zeile „Ohne Sensor …"
 * erscheint erst mit einer Live-Antwort.
 */
import { useEffect, useState } from 'react'
import { liveDashboardApi, type LiveDashboardResponse, type LiveWetterResponse } from '../../../api/liveDashboard'
import { energieProfilApi, type TagDetail } from '../../../api/energie_profil'
import { heuteIso } from '../../../lib'

export const UEBERBLICK_LIVE_TAKT = 5_000
export const UEBERBLICK_WETTER_TAKT = 300_000
export const UEBERBLICK_TAG_TAKT = 300_000

export interface LiveUeberblick {
  live: LiveDashboardResponse | null
  wetter: LiveWetterResponse | null
  tag: TagDetail | null
}

export function useLiveUeberblick(anlageId: number, demoMode: boolean): LiveUeberblick {
  const [live, setLive] = useState<LiveDashboardResponse | null>(null)
  const [wetter, setWetter] = useState<LiveWetterResponse | null>(null)
  const [tag, setTag] = useState<TagDetail | null>(null)

  useEffect(() => {
    let vorbei = false
    let intervalle: ReturnType<typeof setInterval>[] = []

    const holeLive = () => liveDashboardApi.getData(anlageId, demoMode)
      .then((r) => { if (!vorbei) setLive(r) })
      .catch(() => { /* still: Kacheln fehlen */ })
    const holeWetter = () => liveDashboardApi.getWetter(anlageId, demoMode)
      .then((r) => { if (!vorbei) setWetter(r) })
      .catch(() => { /* still: Außentemperatur fehlt */ })
    // Das Tag-Detail kennt keinen Demo-Schalter — es ist der echte heutige Tag.
    const holeTag = () => energieProfilApi.getTagDetail(anlageId, heuteIso())
      .then((r) => { if (!vorbei) setTag(r) })
      .catch(() => { /* still: Heute-Zeilen der Karte fehlen */ })

    const stoppe = () => {
      intervalle.forEach(clearInterval)
      intervalle = []
    }
    const starte = () => {
      stoppe()
      intervalle = [
        setInterval(holeLive, UEBERBLICK_LIVE_TAKT),
        setInterval(holeWetter, UEBERBLICK_WETTER_TAKT),
        setInterval(holeTag, UEBERBLICK_TAG_TAKT),
      ]
    }
    const alleHolen = () => { holeLive(); holeWetter(); holeTag() }
    const beiSichtwechsel = () => {
      if (document.visibilityState === 'hidden') { stoppe(); return }
      alleHolen()
      starte()
    }

    alleHolen()
    if (document.visibilityState !== 'hidden') starte()
    document.addEventListener('visibilitychange', beiSichtwechsel)
    return () => {
      vorbei = true
      document.removeEventListener('visibilitychange', beiSichtwechsel)
      stoppe()
    }
  }, [anlageId, demoMode])

  return { live, wetter, tag }
}
