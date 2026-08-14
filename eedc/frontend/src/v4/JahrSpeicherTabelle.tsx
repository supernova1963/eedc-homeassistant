/**
 * JahrSpeicherTabelle — Speicher-Monatstabelle + Saison-Vergleich (#358 Phase 1).
 *
 * Beantwortet die Issue-Fragen 1, 4, 5 und 6 aus #142/rapahl auf einen Blick:
 * wie viel ging rein und raus, wie viele Vollzyklen waren das, wie viel davon
 * kam aus dem Netz statt von der Sonne, was hat es gebracht.
 *
 * **Ort = Cockpit** (Ortsregel nach Zeitraum, Gernot 2026-08-01): zeitbezogene
 * Sichten stehen neben der Energiebilanz, im Komponenten-Hub bleibt, was über
 * die Lebensdauer des Geräts geht (SoC-Heatmap, Sizing).
 *
 * **Keine eigene Datenquelle** (D3): die Sicht faltet dieselben Monats-
 * Antworten, aus denen Cockpit → Jahr ohnehin besteht. Was hier steht, kann
 * deshalb nicht von den Kacheln darüber abweichen.
 *
 * Regel 0a: Datums-Listen absteigend (neueste zuerst), Leerwert `—`,
 * Prozent mit Leerzeichen, Zahlen über `fmtZahl`/`formatGeld`.
 */
import { Table, TableHead, TableBody, TableFoot } from '../components/ui'
import { ZELLE, KOPF_ZELLE } from '../components/ui/tabelleMasse'
import { Parkbar } from '../components/park'
import { MONAT_KURZ, SAISON_FENSTER, fmtZahl, formatGeld } from '../lib'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

const LEER = '—'

/** Eine aufbereitete Monatszeile der Speicher-Tabelle. */
export interface SpeicherZeile {
  jahr: number
  monat: number
  label: string
  ladung: number
  entladung: number
  netzladung: number | null
  vollzyklen: number | null
  auslastungsBasis: number | null
  ersparnis: number | null
}

/** Σ über eine Zeilenmenge — die Grundlage von Fuß- und Saisonzeile. */
export interface SpeicherSumme {
  ladung: number
  entladung: number
  netzladung: number
  vollzyklen: number | null
  auslastungsBasis: number
  ersparnis: number | null
  monate: number
}

/** Monate mit Speicher-Bewegung, neueste zuerst. */
export function baueSpeicherZeilen(monate: AktuellerMonatResponse[]): SpeicherZeile[] {
  return monate
    .filter((m) => (m.speicher_ladung_kwh ?? 0) > 0 || (m.speicher_entladung_kwh ?? 0) > 0)
    .map((m) => ({
      jahr: m.jahr,
      monat: m.monat,
      label: `${MONAT_KURZ[m.monat]} ${m.jahr}`,
      ladung: m.speicher_ladung_kwh ?? 0,
      entladung: m.speicher_entladung_kwh ?? 0,
      netzladung: m.speicher_ladung_netz_kwh,
      vollzyklen: m.speicher_vollzyklen,
      auslastungsBasis: m.speicher_auslastungs_basis_kwh,
      ersparnis: m.speicher_ersparnis_euro,
    }))
    .sort((a, b) => (b.jahr - a.jahr) || (b.monat - a.monat))
}

/**
 * Summiert Zeilen. Alles additiv — auch die Auslastungs-BASIS, weshalb es sie
 * als eigenes Feld gibt: der Prozentsatz entsteht erst aus Σ Entladung ÷ Σ
 * Basis. Monats-Prozente zu mitteln wäre falsch (Februar wiegt weniger als
 * Juli, ein angefangener Monat noch weniger).
 *
 * `null` bleibt `null`, wo nichts vorliegt — keine 0, die „nichts erreicht"
 * behauptet, wo „nicht gepflegt" gemeint ist (P4).
 */
export function summiereSpeicher(zeilen: SpeicherZeile[]): SpeicherSumme {
  const mitZyklen = zeilen.filter((z) => z.vollzyklen != null)
  const mitErsparnis = zeilen.filter((z) => z.ersparnis != null)
  return {
    ladung: zeilen.reduce((s, z) => s + z.ladung, 0),
    entladung: zeilen.reduce((s, z) => s + z.entladung, 0),
    netzladung: zeilen.reduce((s, z) => s + (z.netzladung ?? 0), 0),
    vollzyklen: mitZyklen.length
      ? mitZyklen.reduce((s, z) => s + (z.vollzyklen ?? 0), 0) : null,
    auslastungsBasis: zeilen.reduce((s, z) => s + (z.auslastungsBasis ?? 0), 0),
    ersparnis: mitErsparnis.length
      ? mitErsparnis.reduce((s, z) => s + (z.ersparnis ?? 0), 0) : null,
    monate: zeilen.length,
  }
}

/** Auslastung in % aus Summen — nie aus gemittelten Prozentwerten. */
export function auslastungAus(s: Pick<SpeicherSumme, 'entladung' | 'auslastungsBasis'>): number | null {
  if (!s.auslastungsBasis || s.auslastungsBasis <= 0) return null
  if (!s.entladung) return null
  return s.entladung / s.auslastungsBasis * 100
}

/** Solar-Anteil der Ladung in % — `null`, wenn keine Netzladung erfasst ist. */
export function solarAnteil(ladung: number, netzladung: number | null): number | null {
  if (netzladung == null || ladung <= 0) return null
  return Math.max(0, (ladung - netzladung)) / ladung * 100
}

const pct = (v: number | null, stellen = 0) => v == null ? LEER : `${fmtZahl(v, stellen)} %`
const kwh = (v: number | null) => v == null ? LEER : fmtZahl(v, 0)

/**
 * Die Saison-Teiltabellen, die diese Sicht für `zeilen` **tatsächlich** rendert.
 *
 * Ausgelagert, damit :func:`jahrSpeicherParkIds` und der Rumpf **dieselbe**
 * Bedingung benutzen. Eine zweite, nachgebaute Bedingung wäre genau die Drift,
 * an der eine statische Park-ID-Liste stirbt (N-248).
 */
function baueSaisons(zeilen: SpeicherZeile[]) {
  // Saison-Fenster aus dem Kanon (`SAISON_FENSTER`) — sie überlappen bewusst
  // NICHT zur Partition des Jahres, deshalb steht der Bereich im Label. Ein
  // eigener Halbjahres-Split hätte eine zweite Saison-Definition in den Baum
  // gebracht.
  return ([SAISON_FENSTER.sommer, SAISON_FENSTER.winter] as const).map((f) => {
    const teil = zeilen.filter((z) => (f.monate as readonly number[]).includes(z.monat))
    return { ...f, summe: summiereSpeicher(teil) }
  }).filter((s) => s.summe.monate > 0)
}

/**
 * IDs der **tatsächlich gerenderten** Parkbars dieses Blocks (N-248).
 *
 * Der Block „Speicher im Jahr" hing allein an `speicherZeilen.length > 0` und
 * blieb deshalb als **leere Hülle** stehen, wenn man alles parkt — die
 * Park-Doktrin verlangt, dass jeder Block verschwindet ([[feedback_park_doktrin_atomar]]).
 * Gefunden hat es `check:park-leertest`, der erstmals gegen eine laufende Box
 * mit Demo-Build lief.
 *
 * Datenabhängig abgeleitet, nicht statisch: die Saison-Tabelle erscheint nur,
 * wenn ein Saisonfenster überhaupt Monate hat. Eine feste Zweier-Liste hätte
 * die Hülle in genau dem Fall stehen lassen, in dem es sie nicht gibt.
 */
export function jahrSpeicherParkIds(monate: AktuellerMonatResponse[]): string[] {
  const zeilen = baueSpeicherZeilen(monate)
  if (zeilen.length === 0) return []
  const ids = ['tabelle:speicher-monate']
  if (baueSaisons(zeilen).length > 0) ids.push('tabelle:speicher-saison')
  return ids
}

export function JahrSpeicherTabelle({ monate }: { monate: AktuellerMonatResponse[] }) {
  const zeilen = baueSpeicherZeilen(monate)
  if (zeilen.length === 0) return null

  const gesamt = summiereSpeicher(zeilen)
  const saisons = baueSaisons(zeilen)

  return (
    <div className="space-y-4">
      <Parkbar id="tabelle:speicher-monate" titel="Speicher je Monat">
        <Table mitFuss flaeche="karte">
          <TableHead>
            <tr className="text-gray-500 dark:text-gray-400">
              <th className={`${KOPF_ZELLE} text-left`}>Monat</th>
              <th className={`${KOPF_ZELLE} text-right`}>Ladung (kWh)</th>
              <th className={`${KOPF_ZELLE} text-right`}>Entladung (kWh)</th>
              <th className={`${KOPF_ZELLE} text-right`}>Vollzyklen</th>
              <th className={`${KOPF_ZELLE} text-right`}>Solar-Anteil</th>
              <th className={`${KOPF_ZELLE} text-right`}>Auslastung</th>
              <th className={`${KOPF_ZELLE} text-right`}>Netto-Nutzen</th>
            </tr>
          </TableHead>
          <TableBody>
            {zeilen.map((z) => (
              <tr key={`${z.jahr}-${z.monat}`} className="border-b border-gray-100 dark:border-gray-800">
                <td className={`${ZELLE} text-gray-700 dark:text-gray-300`}>{z.label}</td>
                <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>{kwh(z.ladung)}</td>
                <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>{kwh(z.entladung)}</td>
                <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>
                  {z.vollzyklen == null ? LEER : fmtZahl(z.vollzyklen, 1)}
                </td>
                <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>
                  {pct(solarAnteil(z.ladung, z.netzladung))}
                </td>
                <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>
                  {pct(auslastungAus({ entladung: z.entladung, auslastungsBasis: z.auslastungsBasis ?? 0 }), 1)}
                </td>
                <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>
                  {z.ersparnis == null ? LEER : formatGeld(z.ersparnis).text}
                </td>
              </tr>
            ))}
          </TableBody>
          <TableFoot>
            <tr className="bg-gray-50 dark:bg-gray-800 font-semibold">
              <td className={`${ZELLE} text-gray-900 dark:text-white`}>Gesamt ({gesamt.monate})</td>
              <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>{kwh(gesamt.ladung)}</td>
              <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>{kwh(gesamt.entladung)}</td>
              <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>
                {gesamt.vollzyklen == null ? LEER : fmtZahl(gesamt.vollzyklen, 1)}
              </td>
              <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>
                {pct(solarAnteil(gesamt.ladung, gesamt.netzladung || null))}
              </td>
              <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>
                {pct(auslastungAus(gesamt), 1)}
              </td>
              <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>
                {gesamt.ersparnis == null ? LEER : formatGeld(gesamt.ersparnis).text}
              </td>
            </tr>
          </TableFoot>
        </Table>
      </Parkbar>

      {saisons.length > 0 && (
        <Parkbar id="tabelle:speicher-saison" titel="Speicher nach Saison">
          <Table flaeche="karte">
            <TableHead>
              <tr className="text-gray-500 dark:text-gray-400">
                <th className={`${KOPF_ZELLE} text-left`}>Saison</th>
                <th className={`${KOPF_ZELLE} text-right`}>Entladung (kWh)</th>
                <th className={`${KOPF_ZELLE} text-right`}>Vollzyklen</th>
                <th className={`${KOPF_ZELLE} text-right`}>Auslastung</th>
                <th className={`${KOPF_ZELLE} text-right`}>Netto-Nutzen</th>
              </tr>
            </TableHead>
            <TableBody>
              {saisons.map((s) => (
                <tr key={s.label} className="border-b border-gray-100 dark:border-gray-800">
                  <td className={`${ZELLE} text-gray-700 dark:text-gray-300`}>
                    {s.label} <span className="text-gray-400 dark:text-gray-500">({s.bereich})</span>
                  </td>
                  <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>{kwh(s.summe.entladung)}</td>
                  <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>
                    {s.summe.vollzyklen == null ? LEER : fmtZahl(s.summe.vollzyklen, 1)}
                  </td>
                  <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>
                    {pct(auslastungAus(s.summe), 1)}
                  </td>
                  <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>
                    {s.summe.ersparnis == null ? LEER : formatGeld(s.summe.ersparnis).text}
                  </td>
                </tr>
              ))}
            </TableBody>
          </Table>
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            Die beiden Fenster sind Fokus-Zeiträume, keine Aufteilung des Jahres —
            die Monate dazwischen zählen in keinem von beiden.
          </p>
        </Parkbar>
      )}
    </div>
  )
}
