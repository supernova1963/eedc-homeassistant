/**
 * Speicher-Hub, Block „Größerer Speicher?" — der Sizing-Simulator (#358 Phase 3).
 *
 * **Eigener Block, nicht in „Wirtschaftlichkeit" dazugestapelt.** Dort sitzt seit
 * Phase 2 die Frage „hätte mehr Kapazität *überhaupt* geholfen?"; hier steht die
 * andere Hälfte: *wie viel* Kapazität, und was sie kostet. Zwei Antworten in
 * einem Block hätten die eine hinter der anderen versteckt.
 *
 * **Die Zahl ist der Spread, nicht der Strompreis.** Ein größerer Speicher senkt
 * den Netzbezug *und* die Einspeisung — wer nur den gesparten Bezug bewertet,
 * verkauft die entgangene Vergütung als Gewinn (Kanon Gernot 2026-08-04, an der
 * Referenzanlage 67 € statt 49 €). Die Herleitung steht im Backend-SoT
 * `core/berechnungen/speicher_sizing.py`.
 *
 * **Der Hinweis ist Pflicht und parkt mit der Zahl.** Die Simulation kennt nur
 * das beobachtete Wetter und ein Verbrauchsverhalten, das bereits auf den
 * *vorhandenen* Speicher eingespielt ist. Ein Regler, den man ohne diesen Satz
 * bedienen kann, verspricht eine Genauigkeit, die die Methode nicht hat —
 * deshalb liegt er in derselben Parkbar wie das Ergebnis (Park-Doktrin:
 * Annotation parkt mit ihrem Bezugswert).
 *
 * Der Block liegt im Hub, weil er über die **Lebensdauer** des Geräts geht
 * (Ortsregel nach Zeitraum, Gernot 2026-08-01).
 */
import { useEffect, useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from 'recharts'
import { BatteryFull, Euro, PiggyBank } from 'lucide-react'
import { Parkbar } from '../components/park'
import { Alert, KPICard, Slider } from '../components/ui'
import { eedcTooltipProps } from '../components/ui/eedcTooltip'
import { ChartContainer } from '../components/charts'
import { investitionenApi, type SizingPunkt, type SpeicherSizingResponse } from '../api/investitionen'
import { CHART_COLORS, ACHSEN_MARGIN_TOP, achsenEinheit, achsenTick, xAchse, yAchse, fmtZahl } from '../lib'
import { useSchmaleAchse } from '../hooks'
import type { MeldeFn } from './komponentenAnalyse'
import type { Investition } from '../types'

function useSpeicherSizing(anlageId: number) {
  const [daten, setDaten] = useState<SpeicherSizingResponse | null>(null)
  const [laedt, setLaedt] = useState(true)

  useEffect(() => {
    let ab = false
    setLaedt(true)
    investitionenApi.getSpeicherSizing(anlageId)
      .then((d) => { if (!ab) setDaten(d) })
      .catch(() => { if (!ab) setDaten(null) })
      .finally(() => { if (!ab) setLaedt(false) })
    return () => { ab = true }
  }, [anlageId])

  return { daten, laedt }
}

/** Der Satz, der die Kurve beantwortet — ohne ihn ist „49 €" nur eine Zahl. */
function Befund({ d, punkt }: { d: SpeicherSizingResponse; punkt: SizingPunkt }) {
  const heute = fmtZahl(d.basis_kapazitaet_kwh, 1)
  if (punkt.faktor === 1) {
    return (
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Das ist die heutige Kapazität von <strong>{heute} kWh</strong> — der Bezugspunkt.
        Ziehen Sie den Regler, um zu sehen, was eine andere Größe im ausgewerteten Zeitraum
        gebracht hätte.
      </p>
    )
  }
  if (punkt.faktor < 1) {
    return (
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Mit nur <strong>{fmtZahl(punkt.kapazitaet_kwh, 1)} kWh</strong> statt {heute} kWh hätten
        Sie <strong>{fmtZahl(punkt.delta_netzbezug_kwh, 0)} kWh</strong> mehr aus dem Netz
        gebraucht — der vorhandene Speicher trägt also{' '}
        {punkt.nutzen_euro_jahr != null && (
          <>rund <strong>{fmtZahl(-punkt.nutzen_euro_jahr, 0)} € im Jahr</strong> bei</>
        )}
        {punkt.nutzen_euro_jahr == null && <>seinen Teil bei</>}.
      </p>
    )
  }
  const mehr = punkt.kapazitaet_kwh - d.basis_kapazitaet_kwh
  if (punkt.nutzen_euro_jahr == null) {
    return (
      <p className="text-sm text-gray-600 dark:text-gray-300">
        <strong>{fmtZahl(mehr, 1)} kWh</strong> mehr hätten den Netzbezug um{' '}
        <strong>{fmtZahl(-punkt.delta_netzbezug_kwh, 0)} kWh</strong> gesenkt. Was das in Euro
        wert ist, lässt sich ohne gepflegten Tarif nicht sagen.
      </p>
    )
  }
  const lohnt = punkt.amortisation_jahre != null && punkt.amortisation_jahre <= 15
  return (
    <p className="text-sm text-gray-600 dark:text-gray-300">
      <strong>{fmtZahl(mehr, 1)} kWh</strong> mehr Kapazität hätten{' '}
      <strong>{fmtZahl(punkt.nutzen_euro_jahr, 0)} € im Jahr</strong> gebracht —{' '}
      {fmtZahl(-punkt.delta_netzbezug_kwh, 0)} kWh weniger aus dem Netz, dafür aber auch{' '}
      {fmtZahl(-punkt.delta_einspeisung_kwh, 0)} kWh weniger Einspeisung.{' '}
      {punkt.amortisation_jahre == null ? (
        <>Ein Zugewinn, der sich nicht bezahlt macht.</>
      ) : lohnt ? (
        <>
          Bei rund {fmtZahl(d.richtpreis_eur_je_kwh, 0)} € je kWh wären das etwa{' '}
          {fmtZahl(punkt.mehrkosten_euro, 0)} € Anschaffung —{' '}
          <strong>amortisiert in gut {fmtZahl(punkt.amortisation_jahre, 0)} Jahren</strong>.
        </>
      ) : (
        <>
          Bei rund {fmtZahl(d.richtpreis_eur_je_kwh, 0)} € je kWh kostet das etwa{' '}
          {fmtZahl(punkt.mehrkosten_euro, 0)} € — das <strong>rechnet sich nicht</strong>{' '}
          (über {fmtZahl(punkt.amortisation_jahre, 0)} Jahre bis zur Amortisation, länger als
          der Speicher hält).
        </>
      )}
    </p>
  )
}

/**
 * „Wie groß ist Ihr Speicher wirklich?" — die gepflegte Zahl neben der gemessenen,
 * und der Satz, der den Unterschied **erklärt** statt ihn zu behaupten (N-238).
 *
 * **Warum das nicht einfach die gepflegte Zahl ersetzt** (Gernots Einwand
 * 2026-08-12): die gepflegte nutzbare Kapazität ist eine **Absicht** — es gibt
 * Anwender, die ihren Speicher bewusst nicht dauernd auf 100 % fahren. Für die
 * wäre eine „Korrektur" auf den gemessenen Wert falsch: sie wollen wissen, wann
 * **ihr** Ziel erreicht ist. Die gemessene Zahl ist **Verhalten**. Beide stehen
 * deshalb nebeneinander, und der Ladestands-Bereich sagt, welcher der beiden
 * Fälle vorliegt.
 */
function GroesseIST({ d }: { d: SpeicherSizingResponse }) {
  const n = d.soc_nutzung
  const gepflegt = d.gepflegte_kapazitaet_kwh
  const zeigtLuecke = d.basis_kalibriert && gepflegt != null
    && Math.abs(gepflegt - d.basis_kapazitaet_kwh) > 0.5

  return (
    <div className="space-y-2">
      <dl className="grid gap-3 sm:grid-cols-3 text-sm">
        <div>
          <dt className="text-gray-500 dark:text-gray-400">Gepflegt (nutzbar)</dt>
          <dd className="font-semibold text-gray-900 dark:text-white">
            {gepflegt == null ? '—' : `${fmtZahl(gepflegt, 1)} kWh`}
          </dd>
        </div>
        <div>
          <dt className="text-gray-500 dark:text-gray-400">Im Alltag bewegt</dt>
          <dd className="font-semibold text-gray-900 dark:text-white">
            {d.basis_kalibriert ? `${fmtZahl(d.basis_kapazitaet_kwh, 1)} kWh` : '—'}
          </dd>
        </div>
        <div>
          <dt className="text-gray-500 dark:text-gray-400">Genutzter Ladestand</dt>
          <dd className="font-semibold text-gray-900 dark:text-white">
            {n == null ? '—' : `${fmtZahl(n.soc_p5, 0)} – ${fmtZahl(n.soc_p95, 0)} %`}
          </dd>
        </div>
      </dl>

      {n != null && (
        <p className="text-sm text-gray-600 dark:text-gray-300">
          An <strong>{n.tage_bis_voll} von {n.tage_mit_soc} Tagen</strong> wurde der Speicher
          voll, an {n.tage_bis_leer} lief er leer; an einem typischen Tag reicht der Ladestand
          bis {fmtZahl(n.tages_max_median, 0)} %.{' '}
          {!zeigtLuecke ? null : n.laedt_planmaessig_voll ? (
            <>
              Er wird also <strong>regelmäßig voll geladen</strong> — dass im Alltag trotzdem
              weniger durchgeht, sind <strong>Ladeverluste</strong>: gegen Ende der Ladung
              nimmt ein Speicher viel Energie auf, die den Ladestand kaum noch bewegt. Ihre
              gepflegte Kapazität ist damit richtig, die kleinere Zahl beschreibt den
              Durchsatz.
            </>
          ) : (
            <>
              Er wird also <strong>planmäßig nicht voll geladen</strong> — dann ist die
              kleinere Zahl kein Verlust, sondern Ihre eigene Ladestrategie. Falls das nicht
              gewollt ist, lohnt ein Blick auf die gepflegte nutzbare Kapazität in den
              Einstellungen der Komponente.
            </>
          )}
        </p>
      )}
    </div>
  )
}

/** Was die Simulation kann und was nicht — Pflicht neben jeder Zahl. */
function MethodenHinweis({ d }: { d: SpeicherSizingResponse }) {
  return (
    <Alert type="info" title="Wie diese Zahlen entstehen">
      <p>
        Gerechnet wird mit den <strong>tatsächlich gemessenen</strong> Stundenwerten aus{' '}
        {d.tage_simuliert} Tagen: dieselbe Sonne, derselbe Verbrauch, nur eine andere
        Speichergröße. Das trägt Ihre eigene Saisonalität — es ist aber{' '}
        <strong>keine Vorhersage</strong>: Ihr Verbrauchsverhalten ist bereits auf den
        vorhandenen Speicher eingespielt, ein größerer würde es verändern.
      </p>
      {!d.historie_reicht && (
        <p className="mt-2">
          Bislang liegen erst <strong>{d.tage_simuliert} Tage</strong> vor. Belastbar wird die
          Aussage ab etwa {d.min_tage_fuer_aussage} Tagen — ein halbes Jahr deckt Sommer und
          Winter ab, und genau dazwischen liegt der Nutzen eines Speichers.
        </p>
      )}
      {!d.basis_kalibriert && (
        <p className="mt-2">
          Für die Simulation wurden die <strong>gepflegten Geräte-Parameter</strong> genutzt
          ({fmtZahl(d.basis_kapazitaet_kwh, 1)} kWh, {fmtZahl(d.basis_roundtrip_prozent, 0)} %) —
          die gemessene Speicherbewegung reichte für eine eigene Kalibrierung nicht aus.
          Rechnungen auf dem Typenschild fallen erfahrungsgemäß{' '}
          <strong>zu günstig</strong> aus, weil Reserven, Ladestrategie und Standby darin
          nicht vorkommen.
        </p>
      )}
      {d.basis_kalibriert && (
        <p className="mt-2">
          Als Basis dient die <strong>gemessene</strong> Speicherbewegung:{' '}
          {fmtZahl(d.basis_kapazitaet_kwh, 1)} kWh effektiv nutzbar bei{' '}
          {fmtZahl(d.basis_roundtrip_prozent, 0)} % Wirkungsgrad. Das ist{' '}
          <strong>kein Gerätemangel</strong> — es ist der Teil, den Ihre Anlage im Alltag
          wirklich bewegt.
        </p>
      )}
      {d.bezug_preis_cent != null && d.einspeise_verg_cent != null && (
        <p className="mt-2">
          Bewertet mit Ihrem <strong>heutigen</strong> Tarif ({fmtZahl(d.bezug_preis_cent, 1)} ct
          Bezug, {fmtZahl(d.einspeise_verg_cent, 1)} ct Einspeisung): Gespart wird der Netzbezug,
          abgezogen wird die Einspeisung, die dafür entfällt.
        </p>
      )}
    </Alert>
  )
}

function SizingKurve({ d }: { d: SpeicherSizingResponse }) {
  const schmal = useSchmaleAchse()
  const daten = d.kurve.map((p) => ({
    kapazitaet: p.kapazitaet_kwh,
    name: `${fmtZahl(p.kapazitaet_kwh, 1)} kWh`,
    nutzen: p.nutzen_euro_jahr,
  }))
  return (
    <div>
      <ChartContainer height="h-64">
        <LineChart data={daten} margin={{ top: ACHSEN_MARGIN_TOP }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" {...xAchse(schmal)} /* achsen-allow: Kategorie-Achse (Kapazitätsstufe) */ />
          <YAxis tickFormatter={achsenTick} {...yAchse(schmal, 55)} label={achsenEinheit('€/Jahr')} />
          <Tooltip {...eedcTooltipProps({ unit: ' €/Jahr', decimals: 0, cursor: false })} />
          <ReferenceLine y={0} stroke={CHART_COLORS.netzbezug} strokeDasharray="4 4" />
          <Line type="monotone" dataKey="nutzen" name="Mehr-Nutzen gegenüber heute"
            stroke={CHART_COLORS.nettoErtrag} strokeWidth={2} dot={{ r: 3 }} connectNulls />
        </LineChart>
      </ChartContainer>
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
        Die Null-Linie ist Ihre heutige Kapazität. Flacht die Kurve nach rechts ab, ist der
        Speicher bereits groß genug — die ersten kWh sparen am meisten, jede weitere weniger.
      </p>
    </div>
  )
}

/** Block „Größerer Speicher?" des Speicher-Hubs: die Sizing-Frage in Euro. */
export function SpeicherSizingIST({ anlageId, melde }: { anlageId: number; inv?: Investition; melde?: MeldeFn }) {
  const { daten, laedt } = useSpeicherSizing(anlageId)
  // Index in die gelieferte Kurve — der Regler fragt nie nach, er liest.
  const [index, setIndex] = useState<number | null>(null)
  const leer = laedt || !daten || daten.kurve.length === 0

  const heuteIndex = useMemo(
    () => (daten ? Math.max(0, daten.kurve.findIndex((p) => p.faktor === 1)) : 0),
    [daten],
  )

  useEffect(() => {
    melde?.(leer ? [] : ['speicher:sizing-antwort', 'speicher:sizing-groesse', 'speicher:sizing-kurve'])
  }, [leer, melde])

  if (laedt) return <p className="text-sm text-gray-400 dark:text-gray-500">Lade…</p>
  if (!daten || daten.kurve.length === 0) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Für die Simulation fehlt die Bezugsgröße: entweder liegen noch keine Stundenwerte vor,
        oder für den Speicher ist keine Kapazität gepflegt. Beides entsteht im laufenden Betrieb
        bzw. in den Einstellungen der Komponente.
      </p>
    )
  }

  const gewaehlt = daten.kurve[index ?? heuteIndex] ?? daten.kurve[heuteIndex]

  return (
    <div className="space-y-4">
      {/* Regler, Ergebnis und Methoden-Hinweis in EINER Parkbar: der Hinweis ist
          die Annotation der Zahl (Park-Doktrin), und ein Regler ohne sein
          Ergebnis wäre ein Bedienelement ohne Anzeige. */}
      <Parkbar id="speicher:sizing-antwort" titel="Wäre ein größerer Speicher besser?">
        <div className="space-y-4">
          <MethodenHinweis d={daten} />

          <div>
            <div className="flex items-baseline justify-between mb-1">
              <label htmlFor="sizing-regler" className="text-sm font-medium text-gray-700 dark:text-gray-200">
                Speicher-Kapazität
              </label>
              <span className="text-sm text-gray-500 dark:text-gray-400">
                {fmtZahl(gewaehlt.kapazitaet_kwh, 1)} kWh
                {' · '}{fmtZahl(gewaehlt.faktor * 100, 0)} % von heute
              </span>
            </div>
            <Slider
              id="sizing-regler"
              min={0}
              max={daten.kurve.length - 1}
              value={index ?? heuteIndex}
              onChange={setIndex}
              ariaLabel="Speicher-Kapazität in Prozent der heutigen"
            />
          </div>

          <Befund d={daten} punkt={gewaehlt} />

          <div className="grid gap-3 sm:grid-cols-3">
            <KPICard
              title="Netto-Nutzen pro Jahr"
              value={gewaehlt.nutzen_euro_jahr == null ? '—' : fmtZahl(gewaehlt.nutzen_euro_jahr, 0)}
              unit={gewaehlt.nutzen_euro_jahr == null ? undefined : '€'}
              icon={Euro}
              color="green"     /* Datenrolle Geld */
              subtitle="gegenüber der heutigen Größe"
              formel="gesparter Netzbezug × Bezugspreis − entgangene Einspeisung × Vergütung"
              berechnung="aus dem ausgewerteten Zeitraum auf ein Jahr hochgerechnet"
              sicht="Was die andere Speichergröße unter dem Strich gebracht hätte"
            />
            <KPICard
              title="Netzbezug"
              value={fmtZahl(gewaehlt.delta_netzbezug_kwh, 0)}
              unit="kWh"
              icon={BatteryFull}
              color="blue"      /* Datenrolle Speicher-Entladung */
              subtitle="im ausgewerteten Zeitraum"
              sicht="Wie viel weniger (bzw. mehr) aus dem Netz gekommen wäre"
            />
            <KPICard
              title="Amortisation"
              value={gewaehlt.amortisation_jahre == null ? '—' : fmtZahl(gewaehlt.amortisation_jahre, 0)}
              unit={gewaehlt.amortisation_jahre == null ? undefined : 'Jahre'}
              icon={PiggyBank}
              color="cyan"      /* Datenrolle Speicher-Effizienz */
              subtitle={gewaehlt.mehrkosten_euro ? `bei rund ${fmtZahl(gewaehlt.mehrkosten_euro, 0)} € Mehrkosten` : 'kein Zukauf'}
              formel={`Mehrkapazität × ${fmtZahl(daten.richtpreis_eur_je_kwh, 0)} €/kWh ÷ Nutzen pro Jahr`}
              sicht="Wie lange die Mehrkosten brauchen, bis sie wieder hereinkommen"
            />
          </div>

          {daten.anzahl_speicher > 1 && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Diese Anlage hat {daten.anzahl_speicher} Speicher. Der Ladestand wird für die Anlage
              als Ganzes erfasst, die Simulation gilt deshalb für alle Speicher zusammen —
              nicht je Gerät.
            </p>
          )}
        </div>
      </Parkbar>

      <Parkbar id="speicher:sizing-groesse" titel="Wie groß ist Ihr Speicher wirklich?">
        <GroesseIST d={daten} />
      </Parkbar>

      <Parkbar id="speicher:sizing-kurve" titel="Nutzen über die Kapazität">
        <SizingKurve d={daten} />
      </Parkbar>
    </div>
  )
}

export default SpeicherSizingIST
