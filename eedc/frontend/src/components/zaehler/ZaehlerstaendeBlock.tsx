/**
 * ZaehlerstaendeBlock — Zählerstände in *Cockpit Tag / Monat / Jahr* (#377).
 *
 * **Eine Komponente für drei Sichten**, weil die Aussage in allen dreien
 * dieselbe ist: Stand am Anfang des Zeitraums, Stand am Ende, die Differenz
 * dazwischen — und darunter der Verlauf. Nur das Fenster wechselt.
 *
 * ⚠ **Ein Zählerstand ist eine Bestandsgröße** und wird deshalb *je Gerät*
 * gezeigt, nie summiert: Zwei Gaszähler mit 12.345 und 8.900 ergeben nicht
 * 21.245. Summierbar wäre allein die Differenz — und die steht ohnehin schon
 * in jeder Zeile.
 *
 * ⚠ **Unvollständige Fenster sagen es** (ADR-002/P4): Beginnt die Aufzeichnung
 * erst im Zeitraum, steht das an der Zahl, statt sie kommentarlos zu klein
 * hinzustellen.
 */
import { useEffect, useState } from 'react'
import { fmtZahl } from '../../lib'
import { Table, TableBody, TableHead } from '../ui'
import { Parkbar, usePark } from '../park'
import { KOPF_ZELLE, ZELLE } from '../ui/tabelleMasse'
import { ZAEHLER_ART_LABELS } from '../../lib/constants'
import {
  zaehlerstaendeApi,
  type ZaehlerStand,
  type ZaehlerZeitraum,
} from '../../api/zaehlerstaende'
import ZaehlerVerlaufChart from './ZaehlerVerlaufChart'

const ZEITRAUM_WORT: Record<ZaehlerZeitraum, string> = {
  tag: 'an diesem Tag',
  monat: 'in diesem Monat',
  jahr: 'in diesem Jahr',
  gesamt: 'seit Aufzeichnungsbeginn',
}

export function useZaehlerstaende(
  anlageId: number | undefined,
  zeitraum: ZaehlerZeitraum,
  opts: { datum?: string; jahr?: number; monat?: number } = {}
) {
  const [staende, setStaende] = useState<ZaehlerStand[] | null>(null)
  const { datum, jahr, monat } = opts
  useEffect(() => {
    if (!anlageId) return
    let aktiv = true
    zaehlerstaendeApi
      .get(anlageId, { zeitraum, datum, jahr, monat })
      .then((r) => { if (aktiv) setStaende(r) })
      // Still: wer keinen Zähler pflegt, soll keine Fehlermeldung über eine
      // Funktion sehen, die er nicht benutzt.
      .catch(() => { if (aktiv) setStaende([]) })
    return () => { aktiv = false }
  }, [anlageId, zeitraum, datum, jahr, monat])
  return staende
}

/** Die zwei Park-IDs dieses Blocks — eine je atomarer Anzeige. */
export const ZAEHLER_PARK_IDS = ['el:zaehlerstaende', 'el:zaehlerstaende-verlauf'] as const

export default function ZaehlerstaendeBlock({
  staende,
  zeitraum,
}: {
  staende: ZaehlerStand[]
  zeitraum: ZaehlerZeitraum
}) {
  const park = usePark()
  if (staende.length === 0) return null

  const hatVerlauf = staende.some((z) => z.verlauf.length > 1)
  const tabelleGeparkt = park.istGeparkt('el:zaehlerstaende')
  const verlaufGeparkt = park.istGeparkt('el:zaehlerstaende-verlauf')

  return (
    <div className="space-y-4">
      {/* Tabellen-SoT (Regel T) statt einer selbstgebauten Tabelle — der
          Wächter `check:tabellen` hat den ersten Entwurf zu Recht abgelehnt.
          (Er hat danach auch dieses Kommentar-Literal getroffen: er liest
          Zeilen, nicht Syntax. Deshalb steht das Element hier ausgeschrieben
          nirgends.) */}
      {!tabelleGeparkt && (
      <Parkbar id="el:zaehlerstaende" titel="Zählerstände">
      <Table zeilen={Math.min(staende.length, 12)}>
        <TableHead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className={`${KOPF_ZELLE} text-left`}>Zähler</th>
            <th className={`${KOPF_ZELLE} text-right`}>Stand Anfang</th>
            <th className={`${KOPF_ZELLE} text-right`}>Stand Ende</th>
            <th className={`${KOPF_ZELLE} text-right`}>Verbrauch {ZEITRAUM_WORT[zeitraum]}</th>
          </tr>
        </TableHead>
        <TableBody>
          {staende.map((z) => (
            <tr key={z.investition_id} className="border-b border-gray-100 dark:border-gray-800">
              <td className={ZELLE}>
                <div className="font-medium text-gray-800 dark:text-gray-100">{z.name}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  {ZAEHLER_ART_LABELS[z.art] ?? z.art}
                </div>
              </td>
              <td className={`${ZELLE} text-right tabular-nums text-gray-700 dark:text-gray-200`}>
                {z.stand_anfang != null ? (
                  <>
                    {fmtZahl(z.stand_anfang, 1)}{' '}
                    <span className="text-xs text-gray-500 dark:text-gray-400">{z.einheit}</span>
                  </>
                ) : (
                  /* Display-Token: kein Wert, keine 0 (Kanon `'—'`). */
                  <span className="text-gray-400 dark:text-gray-500">—</span>
                )}
              </td>
              <td className={`${ZELLE} text-right tabular-nums text-gray-700 dark:text-gray-200`}>
                {z.stand_ende != null ? (
                  <>
                    {fmtZahl(z.stand_ende, 1)}{' '}
                    <span className="text-xs text-gray-500 dark:text-gray-400">{z.einheit}</span>
                  </>
                ) : (
                  <span className="text-gray-400 dark:text-gray-500">—</span>
                )}
              </td>
              <td className={`${ZELLE} text-right tabular-nums font-semibold text-gray-800 dark:text-gray-100`}>
                {z.differenz != null ? (
                  <>
                    {fmtZahl(z.differenz, 1)}{' '}
                    <span className="text-xs font-normal text-gray-500 dark:text-gray-400">
                      {z.einheit}
                    </span>
                    {!z.anfang_vollstaendig && (
                      <div className="text-xs font-normal text-gray-500 dark:text-gray-400">
                        Aufzeichnung beginnt im Zeitraum — Teilwert
                      </div>
                    )}
                  </>
                ) : z.reihe_gebrochen ? (
                  /* Kein „—" ohne Grund: Der Stand ist gefallen, und das kann
                     eine Menge nicht. Wer hier nur einen Strich sieht, sucht
                     den Fehler bei sich. */
                  <span className="font-normal text-gray-500 dark:text-gray-400">
                    <span className="text-gray-400 dark:text-gray-500">—</span>
                    <div className="text-xs">
                      Der Stand ist gefallen — die Reihe hat einen Bruch
                    </div>
                  </span>
                ) : (
                  <span className="font-normal text-gray-400 dark:text-gray-500">—</span>
                )}
              </td>
            </tr>
          ))}
        </TableBody>
      </Table>
      </Parkbar>
      )}

      {hatVerlauf && !verlaufGeparkt && (
        <Parkbar id="el:zaehlerstaende-verlauf" titel="Zählerstände — Verlauf">
          <ZaehlerVerlaufChart staende={staende} />
        </Parkbar>
      )}

      <p className="text-xs text-gray-500 dark:text-gray-400">
        Verbrauchszähler werden erfasst und angezeigt, aber nicht bewertet — sie gehen in
        Energiebilanz, Autarkie, Wirtschaftlichkeit und CO₂-Bilanz bewusst nicht ein.
      </p>
    </div>
  )
}
