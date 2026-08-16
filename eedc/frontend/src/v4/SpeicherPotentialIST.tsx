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
import { KpiStrip } from '../components/blocks'
import { ScrollSchatten } from '../components/ui'
import { investitionenApi, type MonatsPotential, type SpeicherPotentialResponse } from '../api/investitionen'
import { COLORS, LADEQUELLEN_FARBEN } from '../lib/colors'
import { fmtZahl } from '../lib/einheiten'
import type { MeldeFn } from './komponentenAnalyse'
import type { Investition } from '../types'

/** Park-IDs der drei Kacheln — an EINER Stelle, weil sie zweimal gebraucht
 *  werden: beim Rendern und in der Meldung an den Block (`alleGeparkt`). Zwei
 *  Listen wären die nächste Drift-Quelle. */
const PARK_IDS_KPI = [
  'speicher:potential-kpi-zusatz',
  'speicher:potential-kpi-ueberschuss',
  'speicher:potential-kpi-leer',
] as const

const MONAT_KURZ = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

/** Mindestbreite einer Monatsspalte — darunter ist der Balken keine Fläche mehr. */
const SPALTE_MIN_PX = 16

/** Höchstbreite des Balkens IN der Spalte. Die Spalte selbst darf mitwachsen
 *  (sonst steht die Grafik bei wenigen Monaten links und rechts bleibt der
 *  leere Raum, den dieser Umbau beseitigen soll) — der Balken darin nicht:
 *  bei sieben Monaten auf 1400 px wären das sonst 195 px je Balken, und eine
 *  Spanne, die so breit ist wie hoch, liest sich als Fläche statt als Balken. */
const BALKEN_MAX = 'max-w-14 mx-auto w-full' 

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
function PotentialBefund({ d }: { d: SpeicherPotentialResponse }) {
  if (d.zyklen_gesamt === 0) {
    return (
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Im ausgewerteten Zeitraum war der Speicher nie voll, während gleichzeitig eingespeist wurde —
        die Frage nach mehr Kapazität stellt sich hier nicht.
      </p>
    )
  }
  // N-254: „nie leer" hat zwei mögliche Gründe mit **entgegengesetzten** Antworten
  // — groß genug, oder eine eigene Entlade-Untergrenze. Ohne gepflegte nutzbare
  // Kapazität kann eedc sie nicht trennen und darf keinen davon behaupten.
  if (d.boden_nie_erreicht) {
    return (
      <p className="text-sm text-gray-600 dark:text-gray-300">
        <strong>Das lässt sich hier nicht beurteilen.</strong> Strom ging ins Netz, während der
        Speicher voll war ({fmtZahl(d.ueberschuss_kwh, 0)} kWh) — aber er kam in keiner Nacht
        auch nur in die Nähe von leer
        {d.soc_min_prozent != null && <>; sein tiefster Ladestand war {fmtZahl(d.soc_min_prozent, 0)} %</>}.
        Dafür gibt es zwei Erklärungen mit gegensätzlichen Folgen: Entweder ist dein Speicher
        schon groß genug — dann hätte mehr Kapazität wirklich nichts gebracht. Oder du fährst
        eine <strong>Entlade-Untergrenze</strong>, dann war er sehr wohl aufgebraucht und mehr
        Kapazität hätte geholfen. Unterscheiden kann eedc das nur, wenn beim Speicher die{' '}
        <strong>nutzbare Kapazität</strong> gepflegt ist (<em>Einstellungen → Investitionen</em>).
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

/** Eine Monatsspalte der Ladestands-Spur: Spanne P10–P90, Median, beide Anschläge. */
function SpannenSpalte({ m, soll }: { m: MonatsPotential; soll: SpeicherPotentialResponse }) {
  const beschriftung = `${MONAT_KURZ[m.monat - 1]} ${m.jahr}`
  if (m.soc_p10 == null || m.soc_p50 == null || m.soc_p90 == null) {
    return (
      <div
        className={`h-40 rounded-sm bg-gray-100 dark:bg-gray-800 ${BALKEN_MAX}`}
        title={`${beschriftung}: kein Ladestand gemessen`}
      />
    )
  }
  const hoehe = Math.max(1.5, m.soc_p90 - m.soc_p10)
  const titel = [
    beschriftung,
    `Ladestand ${fmtZahl(m.soc_p10, 0)}–${fmtZahl(m.soc_p90, 0)} %`,
    `typisch ${fmtZahl(m.soc_p50, 0)} %`,
    `${fmtZahl(m.anteil_voll_prozent ?? 0, 0)} % der Stunden ≥ ${fmtZahl(soll.soc_voll_prozent, 0)} %`,
    `${fmtZahl(m.anteil_leer_prozent ?? 0, 0)} % der Stunden ≤ ${fmtZahl(soll.soc_leer_prozent, 0)} %`,
  ].join(' · ')

  return (
    <div className={`relative h-40 rounded-sm bg-gray-100 dark:bg-gray-800 ${BALKEN_MAX}`} title={titel}>
      {/* Die Spanne: wo der Speicher in acht von zehn Stunden stand. */}
      <div
        className="absolute inset-x-0 rounded-sm"
        style={{
          bottom: `${m.soc_p10}%`,
          height: `${hoehe}%`,
          backgroundColor: `${COLORS.battery}66`,
        }}
      />
      {/* Der typische Stand — eine Linie, kein zweiter Balken. */}
      <div
        className="absolute inset-x-0 h-[2px]"
        style={{ bottom: `${m.soc_p50}%`, backgroundColor: COLORS.battery }}
      />
      {/* Die beiden Anschläge. Sie tragen ihren Anteil als BREITE, nicht als Höhe:
          eine Höhe würde man mit dem Ladestand verwechseln, den die Achse daneben
          misst. Oben UND unten breit heißt „mehr Kapazität hilft" — genau die
          Frage des Blocks. */}
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2 h-1 rounded-sm"
        style={{ width: `${m.anteil_voll_prozent ?? 0}%`, backgroundColor: COLORS.battery }}
      />
      <div
        className="absolute bottom-0 left-1/2 -translate-x-1/2 h-1 rounded-sm"
        style={{ width: `${m.anteil_leer_prozent ?? 0}%`, backgroundColor: COLORS.battery }}
      />
    </div>
  )
}

/**
 * Ladestand, Durchsatz und Netzladung je Monat — drei Spuren, eine Monatsachse.
 *
 * **Warum keine Heatmap mehr:** die Vorgängerin normierte die Deckkraft ihrer
 * Zellen **global** über alle Monate und alle zehn SoC-Bins. Ein einzelner
 * Winter-Extremwert (der Speicher steht im November hunderte Stunden bei
 * 0–10 %) setzte damit die Skala für das ganze Bild und drückte alles übrige in
 * einen schmalen Deckkraftbereich — Okt/Nov und Feb/Mär waren nicht mehr zu
 * unterscheiden (Rainer, 13.08.). Das war ein **Skalierungsfehler**, kein
 * Geschmack. Jede Monatsspalte trägt jetzt ihre eigene Aussage und braucht
 * keine gemeinsame Skala mehr.
 *
 * **Keine Wertungsfarbe.** Rot→Grün war gewünscht und wird bewusst nicht
 * geliefert: Der Block verneint die Wertung selbst („erst beides zusammen macht
 * mehr Kapazität sinnvoll") — ein voller Speicher ist nicht gut, ein leerer
 * nicht schlecht. Dazu sind Rot/Grün im Projekt Bedeutungsfarben (Regel 0a).
 * Die Datenrolle „Speicher" hat genau eine Farbe; die Netzladung ist eine
 * **andere** Rolle und trägt deshalb das Netzbezugs-Rot.
 */
function MonatsSpuren({ d }: { d: SpeicherPotentialResponse }) {
  const spalten = {
    display: 'grid',
    gridTemplateColumns: `repeat(${d.monate.length}, minmax(${SPALTE_MIN_PX}px, 1fr))`,
    gap: '2px',
  }
  const maxZyklen = Math.max(1, ...d.monate.map((m) => m.vollzyklen ?? 0))
  const hatZyklen = d.monate.some((m) => m.vollzyklen != null)
  const hatNetzladung = d.monate.some((m) => (m.netz_ladung_anteil_prozent ?? 0) > 0)

  return (
    <div className="space-y-3">
      {/* Spur 1 — Ladestand. Die Achse steht AUSSERHALB des Scrollbereichs:
          sonst wandert sie beim Schieben weg und die Prozente stehen an keiner
          Zahl mehr. */}
      <div>
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-4">
          Ladestand über den Monat
        </p>
        <div className="flex gap-2">
          <div className="relative h-40 w-8 shrink-0 text-[10px] text-gray-400 dark:text-gray-500">
            {[100, 50, 0].map((wert) => (
              <span
                key={wert}
                className="absolute right-0 -translate-y-1/2 tabular-nums"
                style={{ bottom: `${wert}%` }}
              >
                {fmtZahl(wert, 0)} %
              </span>
            ))}
          </div>
          <ScrollSchatten aussenClassName="flex-1 min-w-0">
            <div className="min-w-full" style={spalten}>
              {d.monate.map((m) => (
                <SpannenSpalte key={`${m.jahr}-${m.monat}`} m={m} soll={d} />
              ))}
            </div>
          </ScrollSchatten>
        </div>
      </div>

      {/* Spur 2 — Durchsatz. Ohne sie sieht ein Speicher, der dreimal am Tag
          durchfährt, aus wie einer, der stillsteht: der Ladestand allein zeigt
          Zustände, keine Umsätze. */}
      {hatZyklen ? (
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Durchsatz je Monat — bis {fmtZahl(maxZyklen, 1)} Vollzyklen
          </p>
          <div className="flex gap-2">
            <div className="w-8 shrink-0" />
            <ScrollSchatten aussenClassName="flex-1 min-w-0">
              <div className="min-w-full items-end" style={{ ...spalten, height: '3rem' }}>
                {d.monate.map((m) => (
                  <div
                    key={`${m.jahr}-${m.monat}`}
                    className={`rounded-sm ${BALKEN_MAX}`}
                    style={{
                      height: `${((m.vollzyklen ?? 0) / maxZyklen) * 100}%`,
                      backgroundColor: m.vollzyklen == null ? 'transparent' : `${COLORS.battery}99`,
                    }}
                    title={
                      m.vollzyklen == null
                        ? `${MONAT_KURZ[m.monat - 1]} ${m.jahr}: keine Entladung erfasst`
                        : `${MONAT_KURZ[m.monat - 1]} ${m.jahr}: ${fmtZahl(m.vollzyklen, 1)} Vollzyklen`
                    }
                  />
                ))}
              </div>
            </ScrollSchatten>
          </div>
        </div>
      ) : (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {d.kapazitaet_brutto_kwh == null
            ? 'Den Durchsatz je Monat zeigt eedc, sobald für den Speicher eine Kapazität gepflegt ist.'
            : 'Für den Durchsatz je Monat fehlen bisher Entladungswerte.'}
        </p>
      )}

      {/* Spur 3 — Netzladung. Sie füllt den Speicher OHNE Sonne; ein Monat mit
          viel Netzladung beantwortet die Frage des Blocks nicht mit. */}
      {hatNetzladung && (
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Ladung aus dem Netz (Anteil an der Ladung des Monats)
          </p>
          <div className="flex gap-2">
            <div className="w-8 shrink-0" />
            <ScrollSchatten aussenClassName="flex-1 min-w-0">
              <div className="min-w-full items-end" style={{ ...spalten, height: '1.25rem' }}>
                {d.monate.map((m) => (
                  <div
                    key={`${m.jahr}-${m.monat}`}
                    className={`rounded-sm ${BALKEN_MAX}`}
                    style={{
                      height: `${m.netz_ladung_anteil_prozent ?? 0}%`,
                      backgroundColor: LADEQUELLEN_FARBEN.netz,
                    }}
                    title={`${MONAT_KURZ[m.monat - 1]} ${m.jahr}: höchstens ${fmtZahl(m.netz_ladung_anteil_prozent ?? 0, 0)} % der Ladung aus dem Netz`}
                  />
                ))}
              </div>
            </ScrollSchatten>
          </div>
        </div>
      )}

      {/* Monatsachse — einmal, unter allen Spuren. */}
      <div className="flex gap-2">
        <div className="w-8 shrink-0" />
        <ScrollSchatten aussenClassName="flex-1 min-w-0">
          <div className="min-w-full text-[10px] text-gray-400 dark:text-gray-500" style={spalten}>
            {d.monate.map((m, i) => (
              <div key={`${m.jahr}-${m.monat}`} className="text-center overflow-hidden">
                {MONAT_KURZ[m.monat - 1]}
                {m.monat === 1 || i === 0 ? (
                  <span className="block opacity-70">{m.jahr}</span>
                ) : null}
              </div>
            ))}
          </div>
        </ScrollSchatten>
      </div>

      <p className="text-xs text-gray-500 dark:text-gray-400">
        Der Balken zeigt, wo der Ladestand in acht von zehn Stunden lag, die Linie darin den
        typischen Wert. Die kurzen Striche am oberen und unteren Rand sind die Anschläge:
        wie oft der Speicher voll (≥ {fmtZahl(d.soc_voll_prozent, 0)} %) bzw. leer
        (≤ {fmtZahl(d.soc_leer_prozent, 0)} %) war. <strong>Erst beides zusammen macht mehr
        Kapazität sinnvoll</strong> — oben angeschlagen heißt „Überschuss ging ins Netz", unten
        angeschlagen „die Nacht wurde zugekauft".
        {d.soc_leer_ist_abgeleitet && (
          <> „Leer" heißt hier <strong>deine</strong> Entladegrenze von{' '}
          {fmtZahl(d.soc_leer_prozent, 0)} %, nicht 0 % — sie ergibt sich aus der nutzbaren
          Kapazität, die du beim Speicher gepflegt hast. Darunter gibt das Gerät nichts mehr
          ab, die Nacht ist damit aufgebraucht.</>
        )}
        {hatNetzladung && (
          <> Wo Ladung aus dem Netz kam, füllt sich der Speicher ohne Sonne; solche Monate
          beantworten die Frage nach mehr Kapazität nur eingeschränkt. Der Anteil ist eine
          Obergrenze — kein Zähler trennt Haushalt und Speicher innerhalb einer Stunde.</>
        )}
      </p>
    </div>
  )
}

/** Block „Wirtschaftlichkeit" des Speicher-Hubs: Sizing-Frage über die Lebensdauer. */
export function SpeicherPotentialIST({ anlageId, melde }: { anlageId: number; inv?: Investition; melde?: MeldeFn }) {
  const { daten, laedt } = useSpeicherPotential(anlageId)
  const leer = laedt || !daten || daten.tage_mit_daten === 0

  // Jede Teil-Anzeige meldet ihre eigene ID hoch — der Block verschwindet erst,
  // wenn ALLE geparkt sind (`alleGeparkt`). Bis 2026-08-15 stand hier eine
  // einzige ID über dem ganzen Bündel; siehe Kommentar am Rumpf.
  const mehrereSpeicher = !leer && (daten?.anzahl_speicher ?? 0) > 1
  const hatSpuren = !leer && (daten?.monate.length ?? 0) > 0
  useEffect(() => {
    if (leer) { melde?.([]); return }
    melde?.([
      'speicher:potential-befund',
      ...PARK_IDS_KPI,
      ...(hatSpuren ? ['speicher:potential-spuren'] : []),
      ...(mehrereSpeicher ? ['speicher:potential-hinweis'] : []),
    ])
  }, [leer, hatSpuren, mehrereSpeicher, melde])

  if (laedt) return <p className="text-sm text-gray-400 dark:text-gray-500">Lade…</p>
  if (!daten || daten.tage_mit_daten === 0) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Für diese Auswertung fehlen Stundenwerte — sie entstehen im laufenden Betrieb.
      </p>
    )
  }

  // Jede Anzeige ihre eigene Parkbar (Park-Doktrin: EINE Parkbar = GENAU EINE
  // atomare Anzeige). Bis 2026-08-15 lag hier **eine** Parkbar um das ganze
  // Bündel — Befund, drei Kacheln, Spuren-Grafik und Mehrgeräte-Hinweis ließen
  // sich nur gemeinsam parken, und beim Rechtsklick verdunkelte sich der ganze
  // Block statt der angefassten Kachel (gemeldet von Gernot am Bild).
  // `check:parkbar` konnte das nicht sehen: sein Tripwire greift bei benannten
  // Komponenten, hier stand ein generisches `<div>` dahinter — die im Prüfer
  // selbst dokumentierte Grenze.
  return (
    <div className="space-y-4">
      <Parkbar id="speicher:potential-befund" titel="Hätte mehr Kapazität geholfen?">
        <PotentialBefund d={daten} />
      </Parkbar>

      <KpiStrip kpis={[
        {
          parkId: PARK_IDS_KPI[0],
          title: 'Nutzbares Zusatzpotential',
          // N-254: „0" wäre hier eine Aussage, die nicht gemessen ist — der
          // Speicher kam dem Boden nie nahe, also ist der Wert unbekannt.
          value: daten.boden_nie_erreicht ? '—' : fmtZahl(daten.nutzbares_zusatzpotential_kwh, 0),
          unit: daten.boden_nie_erreicht ? undefined : 'kWh',
          icon: TrendingUp,
          color: 'blue',      /* Datenrolle Speicher-Entladung */
          subtitle: daten.boden_nie_erreicht
            ? 'nicht beurteilbar — siehe Hinweis oben'
            : `${daten.tage_mit_daten} Tage ausgewertet`,
          formel: 'min(Einspeisung bei vollem Speicher, Netzbezug nach dem Leerlaufen)',
          berechnung: 'je Lade-Entlade-Zyklus einzeln, danach summiert',
          sicht: 'Was ein größerer Speicher zusätzlich durchgesetzt hätte',
        },
        {
          parkId: PARK_IDS_KPI[1],
          title: 'Überschuss bei vollem Speicher',
          value: fmtZahl(daten.ueberschuss_kwh, 0),
          unit: 'kWh',
          icon: Sun,
          color: 'orange',    /* Datenrolle Speicher-Ladung */
          subtitle: 'Obergrenze, nicht Ertrag',
          formel: `Σ Einspeisung in Stunden mit Ladestand ≥ ${fmtZahl(daten.soc_voll_prozent, 0)} %`,
          sicht: 'Wie viel ein beliebig großer Speicher höchstens hätte aufnehmen können',
        },
        {
          parkId: PARK_IDS_KPI[2],
          title: 'Nächte mit leerem Speicher',
          value: `${daten.zyklen_leergelaufen} / ${daten.zyklen_gesamt}`,
          icon: BatteryCharging,
          color: 'cyan',      /* Datenrolle Speicher-Effizienz */
          subtitle: daten.soc_leer_ist_abgeleitet
            ? `leer = Ladestand ≤ ${fmtZahl(daten.soc_leer_prozent, 0)} % (deine Entladegrenze)`
            : `leer = Ladestand ≤ ${fmtZahl(daten.soc_leer_prozent, 0)} %`,
          sicht: 'Nur wenn er leer wird, kann zusätzliche Kapazität etwas abgeben',
        },
      ]} />

      {daten.monate.length > 0 && (
        <Parkbar id="speicher:potential-spuren" titel="Ladestand, Durchsatz und Netzladung">
          <MonatsSpuren d={daten} />
        </Parkbar>
      )}

      {daten.anzahl_speicher > 1 && (
        <Parkbar id="speicher:potential-hinweis" titel="Hinweis: mehrere Speicher">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Diese Anlage hat {daten.anzahl_speicher} Speicher. Der Ladestand ist der
            <strong> kapazitätsgewichtete</strong> Wert aller Geräte — die Aussage gilt damit für
            die Anlage als Ganzes. Die Ladestände je Gerät stehen im Block „Größerer Speicher?".
          </p>
        </Parkbar>
      )}
    </div>
  )
}

export default SpeicherPotentialIST
