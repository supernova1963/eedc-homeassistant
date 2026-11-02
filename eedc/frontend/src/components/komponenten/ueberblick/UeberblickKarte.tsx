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
 * 4. **«Themen»** (`data-karte="themen"`, Themen-Kacheln 4.2.0 TH-E2, gemeinsam mit der E-Mobilität): je Thema des
 *    gewählten Geräts eine Zwischenüberschrift und je Eintrag mit Wert eine Zeile «‹Label› ‹Wert›» (Wert wie der
 *    HA-State, nur formatiert — `themenKacheln.ts::themaWert`), Tooltip «‹Entität bzw. Topic› · Stand hh:mm». Nur mit
 *    mindestens einem Eintrag mit Wert. Im Bild ist jedes Thema eine Kachel — ein Eintrag als Wert-Kachel, mehrere als
 *    dreizeilige Gruppe «‹Thema› (n)» mit Wert und Bezeichnung des ersten Eintrags und Liste (Nachlauf 4.2.1 N4) —, die
 *    Karte zeigt alle.
 *
 * **Gestrichen:** PV-Anteil je Gerät (Entscheid Gernot 24.10.: nicht geplant), Kompressor-Starts, «seit hh:mm» —
 * dafür gibt es kein Feld. Keine Kosten-, CO₂- oder Ersparniszahl (sie stehen in den Blöcken darunter).
 * ⛔ **Der Client rechnet nichts** (ADR-002/P12): jede Zahl kommt fertig aus Backend-Feldern.
 */
import type { ReactNode } from 'react'
import { Parkbar, usePark } from '../../park'
import RingGauge from '../../charts/RingGauge'
import { Card } from '../../ui'
import { KPI_WERT_SCHRIFT } from '../../ui/KPICard'
import { CHART_COLORS, fmtStundenDauer, fmtZahl } from '../../../lib'
import { funktionsFarbe } from '../../../lib/funktionsFarben'
import { formatPower } from '../../live/EnergieFluss'
import { betriebsartTitel } from '../../live/datenquellenBetriebsart'
import ModusChip, { ZusatzChip } from '../../ui/ModusChip'
import { herleitungMengen } from '../../../v4/wpFunktionsGruppen'
import type { LiveDashboardResponse, LiveThema, LiveThemaEintrag, LiveWetterResponse } from '../../../api/liveDashboard'
import type { TagDetail } from '../../../api/energie_profil'
import type { WpGeraetZeile } from '../../../api/aktuellerMonat'
import type { Investition } from '../../../types'
import {
  istPassivGekuehlt, kuehltPassiv, stromHeute, vorlaufBeschriftung, warmwasserC, wpKnoten, zusatzheizungAktiv,
} from './kachelAnker'
import { UEBERBLICK_ALT_KARTE, UEBERBLICK_KARTE, ueberblickGeparkt, type UeberblickKartenTeile } from './ueberblickPark'
import { themaStand, themaWert, themenVon } from './themenKacheln'

export interface UeberblickKarteProps {
  inv: Investition
  live: LiveDashboardResponse | null
  wetter: LiveWetterResponse | null
  tag: TagDetail | null
  /** Hat die Anlage mehr als eine Wärmepumpe? Dann zählt nur der exakte Tages-Key. */
  mehrereGeraete: boolean
  /** P-433-2b S1c: steht die Karte neben dem Schaubild (Desktop ⅓-Spalte)? Dann untereinander wie bisher; ist das
   *  Schaubild geparkt, nebeneinander in voller Breite (wie die E-Mobilität). Ohne Angabe: untereinander. */
  nebenSchaubild?: boolean
}

/** Tooltip des Anlagen-Rings — die Zahl gehört der Anlage, nicht dem Gerät. */
export const RING_TOOLTIP = 'EV-Quote der Anlage inkl. Speicher-Entladung, dieselbe Zahl wie Cockpit → Live; kein Wert je Gerät'
/** Tooltip der Karte «Betrieb heute». */
export const BETRIEB_TOOLTIP = 'Stunden mit dieser Betriebsart laut Mitschrift des Modus-Sensors (HA); Leerlauf wird nicht mitgeschrieben'
/** Fußzeile der Gerätekarte ohne Vorlauf und Rücklauf (A7-Vokabular: «zugeordnet»). */
export const FUSSZEILE_OHNE_VORLAUF = 'Vorlauf und Rücklauf erscheinen hier, sobald zugeordnet'

/** Lese-Reihenfolge der Betriebsarten in «Betrieb heute» — die Reihenfolge des Backend-Layers. */
const BETRIEBSARTEN = ['heizen', 'warmwasser', 'kuehlen', 'lueften', 'entfeuchten'] as const

/** Bausteine der Karten — exportiert für «Auf einen Blick» der E-Mobilität (P-433-2b K1, `UeberblickKarteEmob`). */
export function Zeile({ label, children, data, tip }: { label: string; children: ReactNode; data: string; tip?: string | null }) {
  return (
    <div className={`flex items-baseline justify-between gap-2 text-sm${tip ? ' cursor-help' : ''}`} data-zeile={data} title={tip ?? undefined}>
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
      <span className="font-semibold text-gray-900 dark:text-white whitespace-nowrap">{children}</span>
    </div>
  )
}

export function Karte({ name, children }: { name: string; children: ReactNode }) {
  return (
    <Card padding="sm">
      {/* `div`, nicht `section`: `section` ist im Hub das Gehäuse eines Blocks (BlockShell). */}
      <div data-karte={name} className="space-y-2">{children}</div>
    </Card>
  )
}

export function KartenKopf({ text, tip }: { text: string; tip?: string | null }) {
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
          {ev && <AnlagenRing wert={ev.wert} />}
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

/** Der Anlagen-Ring «Eigenverbrauch (Anlage)» (B9, E-P2-8) — eine Stelle für Wärme/Klima und E-Mobilität. */
export function AnlagenRing({ wert }: { wert: number }) {
  return (
    <div className="flex items-center gap-2 ml-auto cursor-help" title={RING_TOOLTIP} data-anlagen-ring>
      <RingGauge value={wert} color={CHART_COLORS.eigenverbrauch} size={56} label={`${fmtZahl(wert, 0)} %`} />
      <span className="text-xs text-gray-600 dark:text-gray-400">Eigenverbrauch (Anlage)</span>
    </div>
  )
}

/** Hat die Karte «Heute» einen Wert? Eine Regel für die Karte und ihre Park-Hülle (S1c). */
function heuteDa(strom: number | null, zeile: WpGeraetZeile | null): boolean {
  return zeile?.jaz != null || strom != null || zeile?.waerme_kwh != null
}

/** Welche datenabhängigen Karten erscheinen? (S1c: dieselbe Antwort für die Hüllen und die Meldung des Blocks.) */
export function waermeKartenTeile({ inv, live, tag, mehrereGeraete }: Pick<UeberblickKarteProps, 'inv' | 'live' | 'tag' | 'mehrereGeraete'>): UeberblickKartenTeile {
  const zeile = tag?.wp_geraete?.find((z) => z.investition_id === inv.id) ?? null
  return {
    heute: heuteDa(stromHeute(live, inv.id, mehrereGeraete), zeile),
    betrieb: zeile?.betrieb_stunden != null,
    themen: themenVon(live, inv.id).length > 0,
  }
}

/** Raster der Karten in voller Breite (Schaubild geparkt): drei Spalten; steht die vierte Karte «Themen» (gerendert und
 *  nicht geparkt), ab `xl` vier nebeneinander, darunter zwei (TH-E2, Spaltenregel S1c). */
export function kartenRaster(themen: boolean): string {
  return themen ? 'md:grid-cols-2 xl:grid-cols-4' : 'md:grid-cols-3'
}

/** Tooltip einer Themen-Zeile: «‹Entität bzw. Topic› · Stand hh:mm»; ohne Zeitpunkt nur die Kennung. */
export function themaTooltip(e: Pick<LiveThemaEintrag, 'kennung' | 'zeitpunkt'>, jetzt: Date = new Date()): string | null {
  const teile = [e.kennung, themaStand(e.zeitpunkt, jetzt)].filter((t): t is string => !!t)
  return teile.length > 0 ? teile.join(' · ') : null
}

/** Die Karte «Themen» (TH-E2) — eine Komponente für Wärme/Klima und E-Mobilität; `null` ohne Eintrag mit Wert. */
export function ThemenKarte({ themen }: { themen: LiveThema[] }) {
  if (!themen.some((t) => t.eintraege.length > 0)) return null
  return (
    <Karte name="themen">
      <KartenKopf text="Themen" />
      {themen.filter((t) => t.eintraege.length > 0).map((t) => (
        <div key={`${t.investition_id}-${t.id}`} className="space-y-1" data-thema={t.id}>
          <div className="text-xs font-semibold text-gray-700 dark:text-gray-300">{t.name}</div>
          {t.eintraege.map((e) => (
            <Zeile key={e.id} label={e.label} data={`thema-${e.id}`} tip={themaTooltip(e)}>{themaWert(e)}</Zeile>
          ))}
        </div>
      ))}
    </Karte>
  )
}

function HeuteKarte({ strom, zeile }: { strom: number | null; zeile: WpGeraetZeile | null }) {
  const azJe = zeile
    ? ([['Heizen', zeile.jaz_heizen], ['Warmwasser', zeile.jaz_warmwasser], ['Kühlen', zeile.jaz_kuehlen]] as const)
        .filter(([, v]) => v != null) as [string, number][]
    : []
  const jaz = zeile?.jaz ?? null
  if (!heuteDa(strom, zeile)) return null
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
            <span className="font-semibold text-gray-900 dark:text-white whitespace-nowrap">{fmtStundenDauer(stunden[m])}</span>
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

/**
 * «Auf einen Blick» — seit P-433-2b S1c **je Karte eine Park-Hülle** (`el:ueberblick-karte-geraet|-heute|-betrieb`,
 * seit TH-E2 `-themen`, `ueberblickPark.ts`); der Kartenkopf liegt in der Hülle, die Kopfzone der Geste greift dort.
 * Heute, Betrieb und Themen stehen nur mit Werten da — ihre Hülle ebenso (keine leere Hülle). Ist die alte Park-ID
 * `el:ueberblick-karte` geparkt, gelten alle als geparkt.
 */
export default function UeberblickKarte({ inv, live, wetter, tag, mehrereGeraete, nebenSchaubild = true }: UeberblickKarteProps) {
  const park = usePark()
  const strom = stromHeute(live, inv.id, mehrereGeraete)
  const zeile = tag?.wp_geraete?.find((z) => z.investition_id === inv.id) ?? null
  const teile = waermeKartenTeile({ inv, live, tag, mehrereGeraete })
  const altGeparkt = park.istGeparkt(UEBERBLICK_ALT_KARTE)
  const themenOffen = teile.themen && !ueberblickGeparkt(park.istGeparkt, UEBERBLICK_KARTE.themen)

  return (
    <div className={nebenSchaubild ? 'space-y-3' : `grid grid-cols-1 ${kartenRaster(themenOffen)} gap-3 items-start`} data-ueberblick-karte>
      {!altGeparkt && (
        <Parkbar id="el:ueberblick-karte-geraet" titel="Gerät">
          <GeraeteKarte inv={inv} live={live} wetter={wetter} />
        </Parkbar>
      )}
      {teile.heute && !altGeparkt && (
        <Parkbar id="el:ueberblick-karte-heute" titel="Heute">
          <HeuteKarte strom={strom} zeile={zeile} />
        </Parkbar>
      )}
      {zeile?.betrieb_stunden != null && !altGeparkt && (
        <Parkbar id="el:ueberblick-karte-betrieb" titel="Betrieb">
          <BetriebKarte inv={inv} stunden={zeile.betrieb_stunden} />
        </Parkbar>
      )}
      {teile.themen && !altGeparkt && (
        <Parkbar id="el:ueberblick-karte-themen" titel="Themen">
          <ThemenKarte themen={themenVon(live, inv.id)} />
        </Parkbar>
      )}
    </div>
  )
}
