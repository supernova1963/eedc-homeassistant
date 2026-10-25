/**
 * UeberblickKarte — «Auf einen Blick» neben dem Schaubild (P-433-2 E2, Gegenentwurf W7/W8; Gestalt nach dem
 * Mockup Version 25 seit P-433-2c).
 *
 * Bis zu drei Karten für das **gewählte** Gerät (E-P2-2), jede nur mit Wert (`!= null` — keine Zeile ohne Wert,
 * keine 0 für „nicht gemessen"):
 *
 * 1. **Gerätekarte** (`data-karte="geraet"`, immer): Kopf mit Name, Modus-Chip und «Zusatzheizung aktiv»; die
 *    **Leistung groß** (Schriftgrad der Cockpit-KPI-Kachel, `KPI_WERT_SCHRIFT`); rechts daneben der **Anlagen-Ring**
 *    = Gauge `eigenverbrauch` (B9, E-P2-8: EV-Quote der Anlage inkl. Speicher-Entladung, dieselbe Zahl wie Cockpit →
 *    Live, **kein Wert je Gerät**), beschriftet «Eigenverbrauch (Anlage)», nur wenn die Live-Antwort sie liefert;
 *    darunter Warmwasser · Zusatzheizung · Vorlauf · Rücklauf · Spreizung · Außentemperatur, zweispaltig ab `sm`.
 *    Fußzeile nur, wenn Vorlauf **und** Rücklauf fehlen.
 * 2. **«AZ heute»** (`data-karte="az-heute"`): die Arbeitszahl des Geräts aus dem Tag-Detail (`wp_geraete`,
 *    Rechenstelle des Wärme/Klima-Blocks) groß, darunter die Herleitung aus Zähler/Nenner des Backends
 *    (`herleitungMengen`, eine Formatierungsstelle) und je Funktion die Arbeitszahl; dazu die Zeilen Strom heute
 *    (`heute_kwh_pro_komponente` der Live-Antwort, derselbe Tageswert wie der Energiefluss-Tooltip) und Wärme heute.
 *    Ohne Arbeitszahl heißt die Karte «Heute» und trägt nur die Mengen (der Grund steht als Tooltip am Kopf);
 *    ohne jeden Heute-Wert entfällt sie. **Benannte Grenze:** ein Gerät ohne Strom-Beitrag heute hat im Tag-Detail
 *    keine Zeile — dann fehlen Wärme und AZ heute.
 * 3. **«Betrieb heute»** (`data-karte="betrieb-heute"`): Stunden je Betriebsart aus `betrieb_stunden` (Backend, aus der
 *    Mitschrift des Modus-Sensors, nur HA), Lese-Reihenfolge Heizen · Warmwasser · Kühlen · Lüften · Entfeuchten,
 *    nur Betriebsarten > 0; ein passiv kühlendes Gerät (Stammdatum) nennt «Kühlen passiv». Ohne Feld entfällt sie.
 *    **Kein Leerlauf** — er wird nicht mitgeschrieben.
 *
 * **Gestrichen:** PV-Anteil je Gerät (Entscheid Gernot 24.10.: nicht geplant), Kompressor-Starts, «seit hh:mm» —
 * dafür gibt es kein Feld. Keine Kosten-, CO₂- oder Ersparniszahl (sie stehen in den Blöcken darunter).
 * ⛔ **Der Client rechnet nichts** (ADR-002/P12): jede Zahl kommt fertig aus Backend-Feldern.
 */
import type { ReactNode } from 'react'
import RingGauge from '../../charts/RingGauge'
import { Card } from '../../ui'
import { KPI_WERT_SCHRIFT } from '../../ui/KPICard'
import { CHART_COLORS, fmtZahl } from '../../../lib'
import { funktionsFarbe } from '../../../lib/funktionsFarben'
import { formatPower } from '../../live/EnergieFluss'
import { betriebsartTitel } from '../../live/datenquellenBetriebsart'
import ModusChip, { ZusatzChip } from '../../ui/ModusChip'
import { herleitungMengen } from '../../../v4/wpFunktionsGruppen'
import type { LiveDashboardResponse, LiveWetterResponse } from '../../../api/liveDashboard'
import type { TagDetail } from '../../../api/energie_profil'
import type { WpGeraetZeile } from '../../../api/aktuellerMonat'
import type { Investition } from '../../../types'
import {
  istPassivGekuehlt, kuehltPassiv, stromHeute, vorlaufBeschriftung, warmwasserC, wpKnoten, zusatzheizungAktiv,
} from './kachelAnker'

export interface UeberblickKarteProps {
  inv: Investition
  live: LiveDashboardResponse | null
  wetter: LiveWetterResponse | null
  tag: TagDetail | null
  /** Hat die Anlage mehr als eine Wärmepumpe? Dann zählt nur der exakte Tages-Key. */
  mehrereGeraete: boolean
}

/** Tooltip des Anlagen-Rings — die Zahl gehört der Anlage, nicht dem Gerät. */
export const RING_TOOLTIP = 'EV-Quote der Anlage inkl. Speicher-Entladung, dieselbe Zahl wie Cockpit → Live; kein Wert je Gerät'
/** Tooltip der Karte «Betrieb heute». */
export const BETRIEB_TOOLTIP = 'Stunden mit dieser Betriebsart laut Mitschrift des Modus-Sensors (HA); Leerlauf wird nicht mitgeschrieben'
/** Fußzeile der Gerätekarte ohne Vorlauf und Rücklauf (A7-Vokabular: «zugeordnet»). */
export const FUSSZEILE_OHNE_VORLAUF = 'Vorlauf und Rücklauf erscheinen hier, sobald zugeordnet'

/** Lese-Reihenfolge der Betriebsarten in «Betrieb heute» — die Reihenfolge des Backend-Layers. */
const BETRIEBSARTEN = ['heizen', 'warmwasser', 'kuehlen', 'lueften', 'entfeuchten'] as const

function Zeile({ label, children, data }: { label: string; children: ReactNode; data: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-sm" data-zeile={data}>
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
      <span className="font-semibold text-gray-900 dark:text-white whitespace-nowrap">{children}</span>
    </div>
  )
}

function Karte({ name, children }: { name: string; children: ReactNode }) {
  return (
    <Card padding="sm">
      {/* `div`, nicht `section`: `section` ist im Hub das Gehäuse eines Blocks (BlockShell). */}
      <div data-karte={name} className="space-y-2">{children}</div>
    </Card>
  )
}

function KartenKopf({ text, tip }: { text: string; tip?: string | null }) {
  return (
    <div className={`text-xs font-semibold text-gray-500 dark:text-gray-400${tip ? ' cursor-help' : ''}`} title={tip ?? undefined}>
      {text}
    </div>
  )
}

function GeraeteKarte({ inv, live, wetter }: Pick<UeberblickKarteProps, 'inv' | 'live' | 'wetter'>) {
  const k = wpKnoten(live, inv.id)
  const leistungKw = k ? Math.max(k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0) : null
  const ww = warmwasserC(live, inv.id)
  const spreizung = k?.spreizung_k ?? null
  const aussen = wetter?.aktuell?.temperatur_c ?? null
  const ev = live?.gauges?.find((g) => g.key === 'eigenverbrauch') ?? null
  // Vor der ersten Live-Antwort fehlt nichts, es ist nur noch nicht geladen (dieselbe Regel wie die «Ohne Sensor»-Zeile).
  const ohneVorlauf = live != null && k?.vorlauf_c == null && k?.ruecklauf_c == null

  return (
    <Karte name="geraet">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-gray-900 dark:text-white truncate min-w-0">{inv.bezeichnung}</span>
        <div className="flex items-center gap-1 shrink-0">
          {k?.betriebsmodus && k.betriebsmodus_label && (
            <ModusChip
              modus={k.betriebsmodus} label={k.betriebsmodus_label} passiv={istPassivGekuehlt(k, inv)}
              aktion={k.betriebsmodus_aktion_label}
            />
          )}
          {zusatzheizungAktiv(k) && <ZusatzChip text="Zusatzheizung aktiv" />}
        </div>
      </div>

      {(leistungKw != null || ev) && (
        <div className="flex items-center justify-between gap-3">
          {leistungKw != null && (
            <div data-zeile="leistung" className="min-w-0">
              <div className="text-xs text-gray-500 dark:text-gray-400">Leistung jetzt</div>
              <div className={`${KPI_WERT_SCHRIFT} font-bold text-gray-900 dark:text-white whitespace-nowrap`}>
                {formatPower(leistungKw)}
              </div>
            </div>
          )}
          {ev && (
            <div className="flex items-center gap-2 ml-auto cursor-help" title={RING_TOOLTIP} data-anlagen-ring>
              <RingGauge value={ev.wert} color={CHART_COLORS.eigenverbrauch} size={56} label={`${fmtZahl(ev.wert, 0)} %`} />
              <span className="text-xs text-gray-600 dark:text-gray-400">Eigenverbrauch (Anlage)</span>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1">
        {ww != null && <Zeile label="Warmwasser" data="warmwasser">{fmtZahl(ww, 1)} °C</Zeile>}
        {k?.heizstab_w != null && (
          <Zeile label="Zusatzheizung" data="zusatzheizung">{formatPower(k.heizstab_w / 1000)}</Zeile>
        )}
        {/* S2-8: die Zeile nennt die Heizflächen aus dem Stammdatum — dieselbe Regel wie der Anker der Kachel. */}
        {k?.vorlauf_c != null && <Zeile label={vorlaufBeschriftung(inv)} data="vorlauf">{fmtZahl(k.vorlauf_c, 1)} °C</Zeile>}
        {k?.ruecklauf_c != null && <Zeile label="Rücklauf" data="ruecklauf">{fmtZahl(k.ruecklauf_c, 1)} °C</Zeile>}
        {spreizung != null && <Zeile label="Spreizung" data="spreizung">{fmtZahl(spreizung, 1)} K</Zeile>}
        {aussen != null && <Zeile label="Außentemperatur" data="aussen">{fmtZahl(aussen, 1)} °C</Zeile>}
      </div>

      {ohneVorlauf && (
        <p className="text-xs text-gray-400 dark:text-gray-500" data-fusszeile>{FUSSZEILE_OHNE_VORLAUF}</p>
      )}
    </Karte>
  )
}

function HeuteKarte({ strom, zeile }: { strom: number | null; zeile: WpGeraetZeile | null }) {
  const azJe = zeile
    ? ([['Heizen', zeile.jaz_heizen], ['Warmwasser', zeile.jaz_warmwasser], ['Kühlen', zeile.jaz_kuehlen]] as const)
        .filter(([, v]) => v != null) as [string, number][]
    : []
  const jaz = zeile?.jaz ?? null
  if (jaz == null && strom == null && zeile?.waerme_kwh == null) return null
  const herleitung = herleitungMengen(zeile?.jaz_zaehler_kwh, zeile?.jaz_nenner_kwh)

  return (
    <Karte name="az-heute">
      {jaz != null ? (
        <div>
          <KartenKopf text="AZ heute" />
          <div className={`${KPI_WERT_SCHRIFT} font-bold text-gray-900 dark:text-white`} data-zeile="az-heute">{fmtZahl(jaz, 2)}</div>
          {(herleitung || azJe.length > 0) && (
            <div className="text-xs text-gray-500 dark:text-gray-400" data-herleitung>
              {[
                ...(herleitung ? [<span key="h">{herleitung}</span>] : []),
                ...azJe.map(([name, v]) => (
                  <span key={name} data-zeile={`az-${name.toLowerCase()}`}>{name} {fmtZahl(v, 2)}</span>
                )),
              ].flatMap((el, i) => (i === 0 ? [el] : [<span key={`t${i}`}> · </span>, el]))}
            </div>
          )}
        </div>
      ) : (
        <KartenKopf text="Heute" tip={zeile?.jaz_grund} />
      )}
      <div className="space-y-1">
        {strom != null && <Zeile label="Strom heute" data="strom-heute">{fmtZahl(strom, 1)} kWh</Zeile>}
        {zeile?.waerme_kwh != null && <Zeile label="Wärme heute" data="waerme-heute">{fmtZahl(zeile.waerme_kwh, 1)} kWh</Zeile>}
      </div>
    </Karte>
  )
}

function BetriebKarte({ inv, stunden }: { inv: Investition; stunden: Record<string, number> }) {
  const passiv = kuehltPassiv(inv)
  const arten = BETRIEBSARTEN.filter((m) => (stunden[m] ?? 0) > 0)
  const kuehlenOhneBetrieb = passiv && !arten.includes('kuehlen')

  return (
    <Karte name="betrieb-heute">
      <KartenKopf text="Betrieb heute" tip={BETRIEB_TOOLTIP} />
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {arten.map((m) => (
          <span key={m} className="inline-flex items-center gap-1.5" data-zeile={`betrieb-${m}`}>
            <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: funktionsFarbe(m) }} data-betrieb-farbe={m} />
            <span className="text-gray-500 dark:text-gray-400">{m === 'kuehlen' && passiv ? 'Kühlen passiv' : betriebsartTitel(m)}</span>
            <span className="font-semibold text-gray-900 dark:text-white whitespace-nowrap">{fmtZahl(stunden[m], 1)} h</span>
          </span>
        ))}
      </div>
      {/* Eine gemessene 0 ist eine Auskunft (P4): die Mitschrift lief, das Gerät stand. */}
      {(arten.length === 0 || kuehlenOhneBetrieb) && (
        <p className="text-xs text-gray-500 dark:text-gray-400" data-betrieb-ohne>
          {arten.length === 0 ? 'Heute kein Betrieb' : 'Kühlen passiv, heute kein Betrieb'}
        </p>
      )}
    </Karte>
  )
}

export default function UeberblickKarte({ inv, live, wetter, tag, mehrereGeraete }: UeberblickKarteProps) {
  const strom = stromHeute(live, inv.id, mehrereGeraete)
  const zeile = tag?.wp_geraete?.find((z) => z.investition_id === inv.id) ?? null

  return (
    <div className="space-y-3" data-ueberblick-karte>
      <GeraeteKarte inv={inv} live={live} wetter={wetter} />
      <HeuteKarte strom={strom} zeile={zeile} />
      {zeile?.betrieb_stunden != null && <BetriebKarte inv={inv} stunden={zeile.betrieb_stunden} />}
    </div>
  )
}
