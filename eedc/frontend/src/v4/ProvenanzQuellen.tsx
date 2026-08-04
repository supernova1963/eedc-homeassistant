/**
 * ProvenanzQuellen — die Zeile „Quellen: [Badge] [Badge]" der Cockpit-Sichten.
 *
 * Bis #360 stand dieselbe Zeile DREIMAL inline (Tag-/Monat-/JahrRahmen), und die
 * Auflöse-Funktion `provenanceQuellen` zweimal wortgleich. Hier liegt sie einmal
 * — inklusive der Teilzeitraum-Beschriftung, die #360 fordert.
 *
 * Regel-0a-Entscheidung (N-138): das ist NICHT `components/ui/QuelleBadge.tsx`
 * und wird auch nicht damit zusammengelegt. QuelleBadge etikettiert EINEN
 * Speicher-KPI (`kind: 'ladepreis' | 'wirkungsgrad'`) aus eigenen Label-Maps und
 * färbt nach Belastbarkeit amber; hier steht eine LISTE der Feld-Provenance aus
 * `DATENQUELLE_LABELS`, durchgängig neutral. Verschiedene Label-SoT, verschiedene
 * Rolle — und ein Zusammenlegen würde das Aussehen einer der beiden Stellen
 * ändern, was hier nicht zur Aufgabe gehört. Eine DRITTE Badge-Form entsteht
 * dabei nicht: die Klassen sind die der bisherigen Inline-Kopien.
 */
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { DATENQUELLE_LABELS } from '../lib/constants'
import { formatDatum, formatZeitraumKurz } from '../lib/datum'

/** Badge-Klassen der Provenance-Zeile (auch für die „Stand"-Marke im TagRahmen). */
export const PROVENANZ_BADGE =
  'text-[10px] leading-tight px-1.5 py-0.5 rounded-full font-medium bg-gray-50 text-gray-700 dark:bg-gray-700 dark:text-gray-300'

export interface ProvenanzQuelle {
  /** Klartext-Label aus `DATENQUELLE_LABELS`. */
  label: string
  /** Gemessener Zeitraum, nur bei Teilabdeckung gesetzt (z. B. `28.–30.07.2025`). */
  zusatz?: string
  /** Voller Satz für den Tooltip; nur zusammen mit `zusatz`. */
  titel?: string
}

/** Monatskontext für die Teilabdeckungs-Prüfung (nur Cockpit → Monat, E2/E3). */
export interface MonatsKontext {
  /** Erster Tag des Monats — dieselbe Grenze wie `connector_deckt_monatsanfang`. */
  start: Date
  /** Länge des Monats in Tagen (für „x von 31 Tagen"). */
  tage: number
}

const TAG_MS = 24 * 60 * 60 * 1000

/**
 * Beschriftet eine Quelle, die nur einen Teil des Monats gemessen hat.
 *
 * Rückgabe `undefined` heißt „nichts zu sagen": keine Abdeckung bekannt (nur der
 * Connector führt sie mit) oder sie beginnt am Monatsersten. Die Grenze ist
 * bewusst dieselbe wie im Backend (`core/berechnungen/datenquellen.py::
 * connector_deckt_monatsanfang`) — deckt der Wert den Monat, ist die Angabe
 * Rauschen; deckt er ihn nicht, hat er auch dort schon nicht überschrieben.
 */
function teilzeitraum(
  info: { quelle: string; abdeckung_von?: string | null; abdeckung_bis?: string | null },
  label: string,
  monat: MonatsKontext,
): Pick<ProvenanzQuelle, 'zusatz' | 'titel'> | undefined {
  if (!info.abdeckung_von) return undefined
  const von = new Date(info.abdeckung_von)
  if (Number.isNaN(von.getTime())) return undefined
  if (von <= monat.start) return undefined

  const bis = info.abdeckung_bis ? new Date(info.abdeckung_bis) : null
  const bisGueltig = bis && !Number.isNaN(bis.getTime()) ? bis : null
  if (!bisGueltig) {
    return {
      zusatz: `ab ${formatDatum(info.abdeckung_von)}`,
      titel: `${label} misst erst ab dem ${formatDatum(info.abdeckung_von)} — der Monatsanfang fehlt in dieser Zahl.`,
    }
  }
  // Gemessen wird `(von, bis]`, also die Zeit ZWISCHEN den beiden Zähler-
  // ständen — nicht die Zahl der berührten Kalendertage. „28.–30.07." sind
  // deshalb 2 Tage, nicht 3; alles andere überzeichnete die Abdeckung.
  const tage = Math.round((bisGueltig.getTime() - von.getTime()) / TAG_MS)
  const tageText = tage >= 1 ? String(tage) : 'unter 1'
  const zeitraum = formatZeitraumKurz(info.abdeckung_von, info.abdeckung_bis)
  return {
    zusatz: zeitraum,
    titel:
      `${label} misst nur ${formatDatum(info.abdeckung_von)} bis ${formatDatum(info.abdeckung_bis)} ` +
      `(${tageText} von ${monat.tage} Tagen des Monats). Der Monatsanfang fehlt in dieser Zahl.`,
  }
}

/**
 * `feld_quellen` → Liste der beteiligten Quellen (je Quelle einmal).
 *
 * Ohne `monat` bleibt es bei den reinen Labels — so ruft die Jahres-Sicht auf
 * (E3): `JahrAggregat` faltet zwölf Monate zu EINER Badge-Liste, ein Zeitraum je
 * Quelle wäre dort entweder falsch (welcher Monat?) oder eine Liste von zwölf.
 */
export function provenanzQuellen(
  feldQuellen: AktuellerMonatResponse['feld_quellen'],
  monat?: MonatsKontext,
): ProvenanzQuelle[] {
  if (!feldQuellen) return []
  const nach_label = new Map<string, ProvenanzQuelle>()
  for (const info of Object.values(feldQuellen)) {
    // R3b S7: SoT-Map (die alte lokale 6-Key-Map kannte die echten
    // feld_quellen-Enums nicht → Roh-Werte wie „ha_statistics" in der UI).
    if (!info?.quelle) continue
    const label = DATENQUELLE_LABELS[info.quelle] ?? info.quelle
    const teil = monat ? teilzeitraum(info, label, monat) : undefined
    const bekannt = nach_label.get(label)
    if (!bekannt) nach_label.set(label, { label, ...teil })
    else if (teil && !bekannt.zusatz) nach_label.set(label, { label, ...teil })
  }
  return [...nach_label.values()]
}

/** Die Zeile selbst — leere Liste ⇒ nichts (kein leeres „Quellen:"). */
export function ProvenanzQuellenZeile({ quellen }: { quellen: ProvenanzQuelle[] }) {
  if (quellen.length === 0) return null
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-xs text-gray-400 dark:text-gray-500">Quellen:</span>
      {quellen.map((q) => (
        <span key={q.label} className={PROVENANZ_BADGE} title={q.titel}>
          {q.zusatz ? `${q.label} (${q.zusatz})` : q.label}
        </span>
      ))}
    </div>
  )
}
