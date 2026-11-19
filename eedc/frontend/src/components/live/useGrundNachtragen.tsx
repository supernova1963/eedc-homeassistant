/**
 * useGrundNachtragen — «Grund nachtragen» an einem verzeichneten Wechsel (Sensorwechsel mit Grund, Sitzung 4, Bauplan B-7)
 * und — seit Sitzung 4b-1 — an einem versetzten Stück der Standreihe (Befund «Zählerstände – versetzter Abschnitt»).
 *
 * Der Befund «Zuordnung geändert, Grund fehlt» springt mit `?nachtrag=<id>` in die Datenquellen (`EinstellungenV4`,
 * `DATENQUELLEN_SPRUNG`), der Befund `zaehler_versatz` mit `?stueck=<schlüssel>~<sprung>~<rückgang>`. Der Hook fragt die
 * Prüf-Route (`…/zuordnung-wechsel/{id}/grund/pruefen` bzw. `…/zaehler-versatz/pruefen` — schreibt nichts) und öffnet
 * denselben `SensorwechselDialog` im Nachtrag-Modus; die Vorschau einer Korrektur kommt aus derselben Route mit Grund (und
 * «falsch seit», wo es wählbar ist — am Stück steht es fest; Vorschau = Lauf), «Übernehmen» trägt ein (`…/grund` bzw.
 * `…/zaehler-versatz`). Gestartete Korrektur-Läufe gehen an `merkeLaeufe` (Fortschritt an der Fläche). Der Client rechnet
 * nichts. U2 Lauf b (F10): «bleiben» zwischen zwei HA-Sensoren mit derselben Frage — «Der neue Sensor zählt ab» holt die
 * Vorschau über dieselbe Prüf-Route (`zaehlt_ab`); ein Wartegrund aus der Antwort geht an `merkeWartende`.
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  datenquellenApi, type GrundAngabe, type GrundNachtragPruefung, type KorrekturLaufStart, type StueckAngabe,
  type WartenderWechsel,
} from '../../api/datenquellen'
import { Alert } from '../ui'
import SensorwechselDialog from './SensorwechselDialog'

export const NACHTRAG_LADEFEHLER = 'Der Wechsel ließ sich nicht laden'
export const STUECK_LADEFEHLER = 'Der Abschnitt ließ sich nicht laden'

/** `<schlüssel>~<sprung>~<rückgang>` → die Angaben der Routen am Befund (kein Rechnen: nur Zerlegen des Sprung-Parameters). */
export function stueckAusParameter(wert: string | undefined): StueckAngabe | null {
  const teile = (wert ?? '').split('~')
  return teile.length === 3 && teile.every(Boolean) ? { sensor_key: teile[0], sprung: teile[1], rueckgang: teile[2] } : null
}

export function useGrundNachtragen(anlageId: number | null, wechselId: string | undefined,
  merkeLaeufe: (l?: KorrekturLaufStart[]) => void, neuLaden: () => void, stueckParameter?: string,
  merkeWartende?: (w?: WartenderWechsel[]) => void): ReactNode {
  const [pruefung, setPruefung] = useState<GrundNachtragPruefung | null>(null)
  const [laeuft, setLaeuft] = useState(false)
  // Zwei Fehler, zwei Orte: der Ladefehler steht an der Fläche (kein Dialog), der Speicherfehler im Dialog — «Abbrechen»
  // verwirft ihn mit dem Dialog (sonst stünde danach ein unwahrer Ladefehler an der Fläche).
  const [ladeFehler, setLadeFehler] = useState<string | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  const id = wechselId && /^\d+$/.test(wechselId) ? Number(wechselId) : null
  const stueck = useMemo(() => (id == null ? stueckAusParameter(stueckParameter) : null), [id, stueckParameter])

  useEffect(() => {
    if (anlageId == null || (id == null && stueck == null)) return
    let aus = false
    setLadeFehler(null)
    setFehler(null)
    const anfrage = id != null ? datenquellenApi.pruefeGrundNachtragen(anlageId, id) : datenquellenApi.pruefeStueck(anlageId, stueck!)
    anfrage
      .then((p) => { if (!aus) setPruefung(p) })
      .catch((e) => { if (!aus) setLadeFehler(e instanceof Error ? e.message : '') })
    return () => { aus = true }
  }, [anlageId, id, stueck])

  const vorschau = useCallback((_key: string, falschSeit: string) => {
    if (anlageId == null) return Promise.resolve(null)
    if (id != null) {
      return datenquellenApi.pruefeGrundNachtragen(anlageId, id, { grund: 'korrektur', falsch_seit: falschSeit })
        .then((p) => p.korrektur)
    }
    if (stueck == null) return Promise.resolve(null)
    return datenquellenApi.pruefeStueck(anlageId, stueck, 'korrektur').then((p) => p.korrektur)
  }, [anlageId, id, stueck])

  const bleibenVorschau = useCallback((_key: string, zaehltAb: string) => {
    if (anlageId == null || id == null) return Promise.resolve(null)
    return datenquellenApi.pruefeGrundNachtragen(anlageId, id, { grund: 'fortsetzung', zaehlt_ab: zaehltAb })
      .then((p) => p.bleiben ?? null)
  }, [anlageId, id])

  const bestaetigen = useCallback((gruende: Record<string, GrundAngabe>) => {
    if (anlageId == null || !pruefung) return
    setLaeuft(true)
    setFehler(null)
    const eintragen = id != null
      ? datenquellenApi.grundNachtragen(anlageId, id, gruende[pruefung.sensor_key ?? ''])
      : datenquellenApi.stueckKorrigieren(anlageId, stueck!)
    eintragen
      .then((r) => { merkeLaeufe(r.korrektur); merkeWartende?.(r.wartet); setPruefung(null); neuLaden() })
      .catch((e) => setFehler(e instanceof Error ? e.message : 'Speichern fehlgeschlagen'))
      .finally(() => setLaeuft(false))
  }, [anlageId, id, stueck, pruefung, merkeLaeufe, merkeWartende, neuLaden])

  // Eine Liste je Prüfung (gleiche Identität über die Renders) — sonst setzte der Dialog bei jedem Render der Fläche die Wahl zurück.
  const fragen = useMemo(() => (pruefung ? [pruefung] : []), [pruefung])

  if (!pruefung) {
    if (!ladeFehler) return null
    return <Alert type="error">{`${id != null ? NACHTRAG_LADEFEHLER : STUECK_LADEFEHLER}: ${ladeFehler}`}</Alert>
  }
  return (
    <SensorwechselDialog isOpen fragen={fragen} onVorschau={vorschau} onBleibenVorschau={bleibenVorschau}
      onBestaetigen={bestaetigen}
      onAbbrechen={() => { setPruefung(null); setFehler(null) }} laeuft={laeuft} fehler={fehler}
      nachtrag={{ wechselSatz: pruefung.wechsel_satz, gruende: pruefung.gruende, korrekturNicht: pruefung.korrektur_nicht,
        stueck: pruefung.stueck ?? null }} />
  )
}
