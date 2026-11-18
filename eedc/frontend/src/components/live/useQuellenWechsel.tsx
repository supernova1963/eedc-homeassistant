/**
 * useQuellenWechsel — der eine Weg, auf dem die Datenquellen-Fläche die Quelle eines Felds ändert (Sensorwechsel mit Grund,
 * Bauplan B-2; Sitzung 3b).
 *
 * Erst prüfen (`pruefeQuelle`, derselbe Body wie das Senden — schreibt nichts), dann: ohne Frage sofort senden (die Zeile
 * zeigt die neue Quelle erst nach der Prüfung, also ohne Rücksprung); mit Frage den `SensorwechselDialog` öffnen und erst
 * nach «Übernehmen» mit Grund senden. Kein Fehlerstatus als Ablauf: die 422 der Route sieht nur ein Aufruf an der
 * Prüfung vorbei. Gestartete Korrektur-Läufe sammelt `laeufe` (Fortschritt an der Fläche) — dazu beim Laden die laufenden
 * Läufe der Anlage (`korrekturLaeufe`, Bauplan §11 Nr. 50: der Fortschritt übersteht das Neuladen der Seite); je Lauf einmal.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  datenquellenApi, type DatenquelleFeld, type GatewayQuelleConfig, type GrundAngabe, type QuellePruefung,
} from '../../api/datenquellen'
import SensorwechselDialog from './SensorwechselDialog'

export interface QuellenAnfrage {
  feld: DatenquelleFeld
  quelle: string
  gateway?: GatewayQuelleConfig
  entityId?: string
  /** Was die Zeile nach dem Senden zeigt (Anzeige, kein Rechnen). */
  patch: Partial<DatenquelleFeld>
}

/** Ein Lauf, dessen Fortschritt die Fläche zeigt (aus der Antwort einer Korrektur oder aus `korrekturLaeufe`). */
export interface LaufAnzeige {
  lauf: string
  label?: string
}

export function useQuellenWechsel(anlageId: number | null, setzeFeld: (id: string, p: Partial<DatenquelleFeld>) => void,
  neuLaden: () => void): { aendere: (a: QuellenAnfrage) => void; dialog: ReactNode; laeufe: LaufAnzeige[];
  merkeLaeufe: (l?: LaufAnzeige[]) => void } {
  const [offen, setOffen] = useState<{ anfrage: QuellenAnfrage; fragen: QuellePruefung[] } | null>(null)
  const [laeuft, setLaeuft] = useState(false)
  const [fehler, setFehler] = useState<string | null>(null)
  const [laeufe, setLaeufe] = useState<LaufAnzeige[]>([])

  const merkeLaeufe = useCallback((l?: LaufAnzeige[]) => {
    if (l && l.length > 0) {
      setLaeufe((alt) => [...alt, ...l.filter((n) => !alt.some((a) => a.lauf === n.lauf))])
    }
  }, [])

  // Die laufenden Läufe der Anlage beim Laden (und beim Wechsel der Anlage) — sonst zeigte die Fläche nach dem Neuladen nichts.
  useEffect(() => {
    setLaeufe([])
    if (anlageId == null) return
    let aus = false
    datenquellenApi.korrekturLaeufe(anlageId)
      .then((l) => { if (!aus) merkeLaeufe(l) })
      .catch(() => { /* ohne Liste zeigt die Fläche nur die Läufe dieser Sitzung */ })
    return () => { aus = true }
  }, [anlageId, merkeLaeufe])

  const senden = useCallback((a: QuellenAnfrage, grund?: GrundAngabe) => {
    if (anlageId == null) return Promise.resolve()
    return datenquellenApi.setQuelle(anlageId, a.feld.id, a.quelle, a.gateway, a.entityId, grund)
      .then((r) => { setzeFeld(a.feld.id, a.patch); merkeLaeufe(r.korrektur); if (grund) neuLaden() })
  }, [anlageId, setzeFeld, neuLaden, merkeLaeufe])

  const aendere = useCallback((a: QuellenAnfrage) => {
    if (anlageId == null) return
    datenquellenApi.pruefeQuelle(anlageId, a.feld.id, a.quelle, a.gateway, a.entityId)
      .then((p) => {
        if (p.grund_erforderlich) { setFehler(null); setOffen({ anfrage: a, fragen: [p] }); return }
        return senden(a)
      })
      .catch(neuLaden)
  }, [anlageId, senden, neuLaden])

  const vorschau = useCallback((_key: string, falschSeit: string) => {
    if (anlageId == null || !offen) return Promise.resolve(null)
    const a = offen.anfrage
    return datenquellenApi.pruefeQuelle(anlageId, a.feld.id, a.quelle, a.gateway, a.entityId,
      { grund: 'korrektur', falsch_seit: falschSeit }).then((p) => p.korrektur)
  }, [anlageId, offen])

  const bestaetigen = useCallback((gruende: Record<string, GrundAngabe>) => {
    if (!offen) return
    const key = offen.fragen[0]?.sensor_key ?? ''
    setLaeuft(true)
    senden(offen.anfrage, gruende[key])
      .then(() => setOffen(null))
      .catch((e) => setFehler(e instanceof Error ? e.message : 'Speichern fehlgeschlagen'))
      .finally(() => setLaeuft(false))
  }, [offen, senden])

  const dialog = offen && (
    <SensorwechselDialog isOpen fragen={offen.fragen} onVorschau={vorschau} onBestaetigen={bestaetigen}
      onAbbrechen={() => setOffen(null)} laeuft={laeuft} fehler={fehler} />
  )
  return { aendere, dialog, laeufe, merkeLaeufe }
}
