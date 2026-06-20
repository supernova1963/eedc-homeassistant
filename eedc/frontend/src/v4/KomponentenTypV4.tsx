/**
 * KomponentenTypV4 — die Pro-Typ-Komponentenseite (IA v4 Phase A.2).
 *
 * Rendert den Block-Katalog aus SPEC-KOMPONENTEN.md: **Pflicht-Blöcke**
 * ① Status · ④ Verlauf · ⑤ Vergleich (dünn) · ⑦ Einstellungen — fix-linear,
 * nicht sortierbar (K-B4), einklappbar via BlockShell. Hub = Gesamtzeitraum
 * (K-B5, kein Datums-Selektor). Mehrere Geräte desselben Typs → Geräte-Selektor
 * (Art ①, Muster wie Anlagen-Selektor).
 *
 * Stand A.2-1: Status (D2-KPIs SoT + Aufteilung) + Einstellungen real auf
 * Lebensdauer-Daten; Verlauf/Vergleich als markierte Folge-Blöcke (Chart +
 * WerteTabelle-Embed im nächsten Schritt), Aussicht + spezifische Blöcke (②③⑥)
 * danach je Typ.
 */
import { useEffect, useMemo, useState } from 'react'
import { LoadingSpinner, Card, fmtCalc } from '../components/ui'
import { BlockShell, KpiStrip, VerteilungsBalken, type Block } from '../components/blocks'
import { BLOCK_IDENTITAET } from '../lib'
import { KOMPONENTEN_IDENTITAET } from '../lib/komponentenStyle'
import { BarChart3, ExternalLink, Settings } from 'lucide-react'
import { KOMPONENTEN_ADAPTER, type KompGeraet } from './komponentenAdapter'
import { KomponentenVerlaufChart } from './KomponentenVerlaufChart'
import { KomponentenVergleich } from './KomponentenVergleich'
import type { Investition } from '../types'

/** Read-only Einstellungs-Anzeige je Gerät (#243 A1-B): Stammdaten + Parameter
 *  + „Investition öffnen"-Link; anlagenweite/zeitliche Param liegen woanders. */
function EinstellungInhalt({ inv }: { inv: Investition }) {
  const felder: { label: string; wert: string }[] = []
  if (inv.leistung_kwp != null) felder.push({ label: 'Leistung', wert: `${fmtCalc(inv.leistung_kwp, 1)} kWp` })
  if (inv.ausrichtung) felder.push({ label: 'Ausrichtung', wert: inv.ausrichtung })
  if (inv.neigung_grad != null) felder.push({ label: 'Neigung', wert: `${inv.neigung_grad}°` })
  if (inv.anschaffungsdatum) felder.push({ label: 'Anschaffung', wert: inv.anschaffungsdatum })
  if (inv.stilllegungsdatum) felder.push({ label: 'Stilllegung', wert: inv.stilllegungsdatum })
  if (inv.anschaffungskosten_gesamt != null) felder.push({ label: 'Anschaffungskosten', wert: `${fmtCalc(inv.anschaffungskosten_gesamt, 0)} €` })
  for (const [k, v] of Object.entries(inv.parameter ?? {})) {
    if (v == null || typeof v === 'object') continue
    felder.push({ label: k.replace(/_/g, ' '), wert: String(v) })
  }
  return (
    <div className="space-y-3">
      {inv.id === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          „PV-Anlage" bündelt mehrere Geräte (Module/Wechselrichter). Parameter je Gerät liegen in den Investitionen.
        </p>
      ) : felder.length ? (
        <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-1">
          {felder.map((f) => (
            <div key={f.label} className="flex items-center justify-between gap-2 text-sm border-b border-gray-100 dark:border-gray-800 py-1">
              <dt className="text-gray-500 dark:text-gray-400 capitalize">{f.label}</dt>
              <dd className="font-medium text-gray-900 dark:text-white whitespace-nowrap">{f.wert}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-sm text-gray-500 dark:text-gray-400">Keine Parameter hinterlegt.</p>
      )}
      <a href="#/v4/einstellungen" className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
        <Settings className="h-4 w-4" /> Diese Parameter bearbeiten (Investition öffnen)
      </a>
      <p className="text-xs text-gray-400 dark:text-gray-500">
        Anlagenweite Einstellungen (USt, §51 EEG, Netz-Puffer, Prognosequelle) und zeitlich variable
        Strompreise liegen unter <span className="font-medium">Einstellungen</span> — anderer Geltungsbereich, dort verlinkt.
      </p>
    </div>
  )
}

/** Markierter Folge-Block (Verlauf/Vergleich) — ehrlich „im Bau", kein Fake. */
function FolgtHinweis({ text, crossLink }: { text: string; crossLink?: { label: string; href: string } }) {
  return (
    <div className="space-y-2">
      <p className="text-sm text-gray-500 dark:text-gray-400">{text}</p>
      {crossLink && (
        <a href={crossLink.href} className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
          <ExternalLink className="h-4 w-4" /> {crossLink.label}
        </a>
      )}
    </div>
  )
}

function geraetBloecke(g: KompGeraet): Block[] {
  return [
    {
      id: 'status', title: 'Aktueller Status', ...BLOCK_IDENTITAET.kennzahlen,
      summary: g.status.map((k) => `${k.value} ${k.unit ?? ''}`.trim()).slice(0, 2).join(' · '),
      defaultOpen: true,
      render: () => (
        <div className="space-y-4">
          <KpiStrip kpis={g.status} />
          {g.aufteilung && <VerteilungsBalken titel={g.aufteilung.titel} einheit={g.aufteilung.einheit} segmente={g.aufteilung.segmente} />}
        </div>
      ),
    },
    {
      id: 'verlauf', title: 'Verlauf (gesamte Historie)', ...BLOCK_IDENTITAET.verlauf,
      summary: 'Monatsverlauf über die gesamte Laufzeit', defaultOpen: false,
      render: (fokus) => (g.verlauf
        ? <KomponentenVerlaufChart rows={g.verlauf.rows} bars={g.verlauf.bars} einheit={g.verlauf.einheit} tall={fokus} />
        : <FolgtHinweis text="Für diesen Typ liegt keine eigene Monatszeitreihe vor (z. B. Wallbox = aus E-Auto-Ladung abgeleitet)." />),
    },
    {
      id: 'vergleich', title: 'Vergleich', icon: BarChart3,
      summary: 'Jahresvergleich · Diagramm ⇄ Tabelle', defaultOpen: false,
      render: () => (g.vergleich
        ? <KomponentenVergleich label={g.vergleich.label} einheit={g.vergleich.einheit} farbe={g.vergleich.farbe} jahre={g.vergleich.jahre} />
        : <FolgtHinweis
            text="Für diesen Typ liegt noch kein Jahresvergleich vor."
            crossLink={{ label: 'Alle Werte / Tabelle →', href: '#/v4/auswertungen/tabelle' }}
          />),
    },
    {
      id: 'einstellungen', title: 'Einstellungen', icon: Settings,
      summary: 'Parameter dieser Komponente — nicht mehr raten (#243)', defaultOpen: false,
      render: () => <EinstellungInhalt inv={g.inv} />,
    },
  ]
}

export default function KomponentenTypV4({ typ, anlageId }: { typ: string; anlageId: number | undefined }) {
  const [geraete, setGeraete] = useState<KompGeraet[]>([])
  const [aktiv, setAktiv] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const adapter = KOMPONENTEN_ADAPTER[typ]
  const ident = KOMPONENTEN_IDENTITAET[typ]

  useEffect(() => {
    if (!anlageId || !adapter) { setLoading(false); return }
    let ab = false
    setLoading(true); setError(null); setAktiv(0)
    adapter.fetch(anlageId)
      .then((gs) => { if (!ab) setGeraete(gs) })
      .catch(() => { if (!ab) setError('Fehler beim Laden der Komponente') })
      .finally(() => { if (!ab) setLoading(false) })
    return () => { ab = true }
  }, [anlageId, adapter, typ])

  const g = geraete[aktiv]
  const bloecke = useMemo(() => (g ? geraetBloecke(g) : []), [g])

  if (!anlageId) return <Hinweis text="Noch keine Anlage gewählt." />
  if (!adapter) return <Hinweis text={`Für „${ident?.label ?? typ}" gibt es noch keine Hub-Sicht.`} />
  if (loading) return <div className="p-3 sm:p-6"><LoadingSpinner text="Lade Komponente…" /></div>
  if (error) return <Hinweis text={error} ton="error" />
  if (geraete.length === 0) return <Hinweis text={`Keine ${ident?.label ?? typ}-Daten erfasst.`} />

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      {/* Geräte-Selektor (Art ①) — nur ab 2 Geräten desselben Typs. */}
      {geraete.length >= 2 && (
        <div className="flex items-center gap-2 overflow-x-auto scrollbar-none">
          {geraete.map((d, i) => (
            <button
              key={d.inv.id || d.label} type="button" onClick={() => setAktiv(i)}
              className={`min-h-[44px] px-3 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                i === aktiv
                  ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                  : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800/50'
              }`}
            >{d.label}</button>
          ))}
        </div>
      )}
      <BlockShell key={`komp-${typ}-${g?.inv.id ?? aktiv}`} persistKey={`v4-komponenten-${typ}`} bloecke={bloecke} />
    </div>
  )
}

function Hinweis({ text, ton }: { text: string; ton?: 'error' }) {
  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      <Card><p className={`text-sm ${ton === 'error' ? 'text-red-500' : 'text-gray-500 dark:text-gray-400'}`}>{text}</p></Card>
    </div>
  )
}
