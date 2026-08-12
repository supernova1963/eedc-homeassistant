/**
 * Speicher-Hub, Block „Wirtschaftlichkeit" — hätte mehr Kapazität geholfen?
 * (#358 Phase 2)
 *
 * **Die Zahl ist bewusst kleiner als die naheliegende.** Wer nur zählt, wie viel
 * PV eingespeist wurde, während der Speicher voll war, bekommt an einer
 * Sommeranlage schnell mehrere hundert kWh „ungenutztes Potential" — und kauft
 * darauf hin Kapazität, die nichts bringt, weil der Speicher nachts ohnehin nicht
 * leer wird. Der Block zeigt deshalb den **gedeckelten** Wert groß und die
 * Obergrenze klein daneben; die Herleitung steht im Backend-SoT
 * `core/berechnungen/speicher_potential.py`.
 *
 * Der Block liegt im Hub, weil er über die **Lebensdauer** des Geräts geht
 * (Ortsregel nach Zeitraum, Gernot 2026-08-01) — zeitbezogene Speicher-Sichten
 * bleiben im Cockpit.
 */
import { useEffect, useState } from 'react'
import { BatteryCharging, Sun, TrendingUp } from 'lucide-react'
import { Parkbar } from '../components/park'
import { KPICard, ScrollSchatten } from '../components/ui'
import { investitionenApi, type SpeicherPotentialResponse } from '../api/investitionen'
import { COLORS } from '../lib/colors'
import { fmtZahl } from '../lib/einheiten'
import type { MeldeFn } from './komponentenAnalyse'
import type { Investition } from '../types'

const MONAT_KURZ = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

/** Bin-Beschriftung: 0 = „0–10 %", 9 = „90–100 %". */
const BIN_LABELS = Array.from({ length: 10 }, (_, i) => `${i * 10}–${(i + 1) * 10} %`)

/**
 * Häufigkeit → Deckkraft **einer** Farbe, nicht → eigene Farbe.
 * Die Datenrolle ist „Speicher"; eine zweite Farbe dafür wäre Drift
 * (Style-Guide Regel 0a). Der Farbwert selbst kommt aus `lib/colors.ts`.
 */
function zellenStil(anteil: number): { backgroundColor: string } {
  if (anteil <= 0) return { backgroundColor: 'transparent' }
  const deckkraft = 0.12 + 0.78 * Math.min(1, anteil)
  return { backgroundColor: `${COLORS.battery}${Math.round(deckkraft * 255).toString(16).padStart(2, '0')}` }
}

function useSpeicherPotential(anlageId: number) {
  const [daten, setDaten] = useState<SpeicherPotentialResponse | null>(null)
  const [laedt, setLaedt] = useState(true)

  useEffect(() => {
    let ab = false
    setLaedt(true)
    investitionenApi.getSpeicherPotential(anlageId)
      .then((d) => { if (!ab) setDaten(d) })
      .catch(() => { if (!ab) setDaten(null) })
      .finally(() => { if (!ab) setLaedt(false) })
    return () => { ab = true }
  }, [anlageId])

  return { daten, laedt }
}

/** Der Satz, der die Zahl einordnet — ohne ihn ist „0 kWh" nicht von „keine Daten" zu unterscheiden. */
function Befund({ d }: { d: SpeicherPotentialResponse }) {
  if (d.zyklen_gesamt === 0) {
    return (
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Im ausgewerteten Zeitraum war der Speicher nie voll, während gleichzeitig eingespeist wurde —
        die Frage nach mehr Kapazität stellt sich hier nicht.
      </p>
    )
  }
  if (d.nutzbares_zusatzpotential_kwh <= 0) {
    return (
      <p className="text-sm text-gray-600 dark:text-gray-300">
        <strong>Ein größerer Speicher hätte hier nichts gebracht.</strong> Zwar ging Strom ins Netz,
        während der Speicher voll war ({fmtZahl(d.ueberschuss_kwh, 0)} kWh) — aber er wurde in keiner
        der folgenden Nächte leer. Zusätzlich gespeicherte Energie hätte niemand abgenommen.
      </p>
    )
  }
  return (
    <p className="text-sm text-gray-600 dark:text-gray-300">
      Ein größerer Speicher hätte in diesem Zeitraum rund{' '}
      <strong>{fmtZahl(d.nutzbares_zusatzpotential_kwh, 0)} kWh</strong> zusätzlich durchgesetzt —
      begrenzt nicht durch die Sonne, sondern durch die Nächte:{' '}
      {d.zyklen_leergelaufen} von {d.zyklen_gesamt} Mal lief der Speicher vor dem nächsten Überschuss
      überhaupt leer.
    </p>
  )
}

function Heatmap({ d }: { d: SpeicherPotentialResponse }) {
  const maxStunden = Math.max(
    1,
    ...d.monate.flatMap((m) => m.soc_bins),
  )
  return (
    <div>
      <ScrollSchatten>
        {/* tabelle-allow: Farb-Heatmap, kein Datensatz-Raster — die Zellen tragen keinen
            Text, sondern eine Deckkraft; Zeilen sind die zehn SoC-Bins. Höhenfenster,
            sticky-Kopf und Spalten-Definitionen der Tabellen-SoT greifen hier nicht. */}
        <table className="text-xs border-separate" style={{ borderSpacing: '2px' }}>
        <thead>
          <tr>
            <th className="text-right pr-2 font-medium text-gray-400 dark:text-gray-500">Ladestand</th>
            {d.monate.map((m) => (
              <th key={`${m.jahr}-${m.monat}`} className="font-medium text-gray-400 dark:text-gray-500 px-1">
                {MONAT_KURZ[m.monat - 1]}
                {m.monat === 1 || m.monat === d.monate[0].monat ? (
                  <span className="block text-[10px] opacity-70">{m.jahr}</span>
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...Array(10).keys()].reverse().map((bin) => (
            <tr key={bin}>
              <td className="text-right pr-2 font-mono text-gray-400 dark:text-gray-500 whitespace-nowrap">
                {BIN_LABELS[bin]}
              </td>
              {d.monate.map((m) => {
                const stunden = m.soc_bins[bin] ?? 0
                return (
                  <td
                    key={`${m.jahr}-${m.monat}-${bin}`}
                    className="w-8 h-5 rounded-sm text-center align-middle"
                    style={zellenStil(stunden / maxStunden)}
                    title={`${MONAT_KURZ[m.monat - 1]} ${m.jahr}: ${stunden} Stunden bei ${BIN_LABELS[bin]} Ladestand`}
                  />
                )
              })}
            </tr>
          ))}
        </tbody>
        </table>
      </ScrollSchatten>
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
        Je dunkler, desto mehr Stunden stand der Speicher in diesem Monat auf diesem Ladestand.
        Eine dunkle Zeile ganz oben heißt „lief oft voll", eine dunkle ganz unten „lief oft leer" —
        erst beides zusammen macht mehr Kapazität sinnvoll.
      </p>
    </div>
  )
}

/** Block „Wirtschaftlichkeit" des Speicher-Hubs: Sizing-Frage über die Lebensdauer. */
export function SpeicherPotentialIST({ anlageId, melde }: { anlageId: number; inv?: Investition; melde?: MeldeFn }) {
  const { daten, laedt } = useSpeicherPotential(anlageId)
  const leer = laedt || !daten || daten.tage_mit_daten === 0

  useEffect(() => {
    melde?.(leer ? [] : ['speicher:potential'])
  }, [leer, melde])

  if (laedt) return <p className="text-sm text-gray-400 dark:text-gray-500">Lade…</p>
  if (!daten || daten.tage_mit_daten === 0) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Für diese Auswertung fehlen Stundenwerte — sie entstehen im laufenden Betrieb.
      </p>
    )
  }

  return (
    <Parkbar id="speicher:potential" titel="Hätte mehr Kapazität geholfen?">
      <div className="space-y-4">
        <Befund d={daten} />

        <div className="grid gap-3 sm:grid-cols-3">
          <KPICard
            title="Nutzbares Zusatzpotential"
            value={fmtZahl(daten.nutzbares_zusatzpotential_kwh, 0)}
            unit="kWh"
            icon={TrendingUp}
            color="blue"      /* Datenrolle Speicher-Entladung */
            subtitle={`${daten.tage_mit_daten} Tage ausgewertet`}
            formel="min(Einspeisung bei vollem Speicher, Netzbezug nach dem Leerlaufen)"
            berechnung="je Lade-Entlade-Zyklus einzeln, danach summiert"
            sicht="Was ein größerer Speicher zusätzlich durchgesetzt hätte"
          />
          <KPICard
            title="Überschuss bei vollem Speicher"
            value={fmtZahl(daten.ueberschuss_kwh, 0)}
            unit="kWh"
            icon={Sun}
            color="orange"    /* Datenrolle Speicher-Ladung */
            subtitle="Obergrenze, nicht Ertrag"
            formel="Σ Einspeisung in Stunden mit Ladestand ≥ 95 %"
            sicht="Wie viel ein beliebig großer Speicher höchstens hätte aufnehmen können"
          />
          <KPICard
            title="Nächte mit leerem Speicher"
            value={`${daten.zyklen_leergelaufen} / ${daten.zyklen_gesamt}`}
            icon={BatteryCharging}
            color="cyan"      /* Datenrolle Speicher-Effizienz */
            subtitle={`leer = Ladestand ≤ ${fmtZahl(daten.soc_leer_prozent, 0)} %`}
            sicht="Nur wenn er leer wird, kann zusätzliche Kapazität etwas abgeben"
          />
        </div>

        {daten.monate.length > 0 && <Heatmap d={daten} />}

        {daten.anzahl_speicher > 1 && (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Diese Anlage hat {daten.anzahl_speicher} Speicher. Der Ladestand ist der
            <strong> kapazitätsgewichtete</strong> Wert aller Geräte — die Aussage gilt damit für
            die Anlage als Ganzes. Die Ladestände je Gerät stehen im Block „Größerer Speicher?".
          </p>
        )}
      </div>
    </Parkbar>
  )
}

export default SpeicherPotentialIST
