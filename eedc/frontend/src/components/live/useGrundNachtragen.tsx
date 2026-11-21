/**
 * useGrundNachtragen — «Grund nachtragen» an einem versetzten Stück der Standreihe (Befund «Zählerstände – versetzter
 * Abschnitt», Sitzung 4b-1). «Grund nachtragen» an einem verzeichneten Wechsel (`?nachtrag=<id>`, Sitzung 4) ist seit Weg B
 * entfernt (Sitzung B2).
 *
 * Der Befund `zaehler_versatz` springt mit `?stueck=<schlüssel>~<sprung>~<rückgang>` in die Datenquellen (`EinstellungenV4`,
 * `DATENQUELLEN_SPRUNG`). Der Hook fragt die Prüf-Route (`…/zaehler-versatz/pruefen` — schreibt nichts) und öffnet den
 * `SensorwechselDialog` im Nachtrag-Modus; die Vorschau der Korrektur kommt aus derselben Route mit Grund (am Stück steht
 * «falsch seit» fest; Vorschau = Lauf), «Übernehmen» trägt ein (`…/zaehler-versatz`). Gestartete Korrektur-Läufe gehen an
 * `merkeLaeufe` (Fortschritt an der Fläche). Der Client rechnet nichts. U3 b (G7): am Stück einer MQTT-Reihe bietet die
 * Antwort auch «Bisherige Werte bleiben» — «Übernehmen» sendet dann diesen Grund.
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  datenquellenApi, type GrundAngabe, type GrundNachtragPruefung, type KorrekturLaufStart, type StueckAngabe,
  type WartenderWechsel,
} from '../../api/datenquellen'
import { Alert } from '../ui'
import SensorwechselDialog from './SensorwechselDialog'

export const STUECK_LADEFEHLER = 'Der Abschnitt ließ sich nicht laden'

/** `<schlüssel>~<sprung>~<rückgang>` → die Angaben der Routen am Befund (kein Rechnen: nur Zerlegen des Sprung-Parameters). */
export function stueckAusParameter(wert: string | undefined): StueckAngabe | null {
  const teile = (wert ?? '').split('~')
  return teile.length === 3 && teile.every(Boolean) ? { sensor_key: teile[0], sprung: teile[1], rueckgang: teile[2] } : null
}

export function useGrundNachtragen(anlageId: number | null, merkeLaeufe: (l?: KorrekturLaufStart[]) => void,
  neuLaden: () => void, stueckParameter?: string, merkeWartende?: (w?: WartenderWechsel[]) => void): ReactNode {
  const [pruefung, setPruefung] = useState<GrundNachtragPruefung | null>(null)
  const [laeuft, setLaeuft] = useState(false)
  // Zwei Fehler, zwei Orte: der Ladefehler steht an der Fläche (kein Dialog), der Speicherfehler im Dialog — «Abbrechen»
  // verwirft ihn mit dem Dialog (sonst stünde danach ein unwahrer Ladefehler an der Fläche).
  const [ladeFehler, setLadeFehler] = useState<string | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  const stueck = useMemo(() => stueckAusParameter(stueckParameter), [stueckParameter])

  useEffect(() => {
    if (anlageId == null || stueck == null) return
    let aus = false
    setLadeFehler(null)
    setFehler(null)
    datenquellenApi.pruefeStueck(anlageId, stueck)
      .then((p) => { if (!aus) setPruefung(p) })
      .catch((e) => { if (!aus) setLadeFehler(e instanceof Error ? e.message : '') })
    return () => { aus = true }
  }, [anlageId, stueck])

  const vorschau = useCallback(() => {
    if (anlageId == null || stueck == null) return Promise.resolve(null)
    return datenquellenApi.pruefeStueck(anlageId, stueck, 'korrektur').then((p) => p.korrektur ?? null)
  }, [anlageId, stueck])

  const bestaetigen = useCallback((gruende: Record<string, GrundAngabe>) => {
    if (anlageId == null || !pruefung || stueck == null) return
    setLaeuft(true)
    setFehler(null)
    datenquellenApi.stueckKorrigieren(anlageId, stueck, gruende[pruefung.sensor_key ?? '']?.grund)
      .then((r) => { merkeLaeufe(r.korrektur); merkeWartende?.(r.wartet); setPruefung(null); neuLaden() })
      .catch((e) => setFehler(e instanceof Error ? e.message : 'Speichern fehlgeschlagen'))
      .finally(() => setLaeuft(false))
  }, [anlageId, stueck, pruefung, merkeLaeufe, merkeWartende, neuLaden])

  // Eine Liste je Prüfung (gleiche Identität über die Renders) — sonst setzte der Dialog bei jedem Render der Fläche die Wahl zurück.
  const fragen = useMemo(() => (pruefung ? [pruefung] : []), [pruefung])

  if (!pruefung) {
    if (!ladeFehler) return null
    return <Alert type="error">{`${STUECK_LADEFEHLER}: ${ladeFehler}`}</Alert>
  }
  return (
    <SensorwechselDialog isOpen fragen={fragen} onVorschau={vorschau}
      onBestaetigen={bestaetigen}
      onAbbrechen={() => { setPruefung(null); setFehler(null) }} laeuft={laeuft} fehler={fehler}
      nachtrag={{ wechselSatz: pruefung.wechsel_satz, gruende: pruefung.gruende, korrekturNicht: pruefung.korrektur_nicht,
        stueck: pruefung.stueck ?? null }} />
  )
}
