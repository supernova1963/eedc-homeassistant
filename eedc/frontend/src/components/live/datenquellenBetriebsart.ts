/**
 * datenquellenBetriebsart — die Datenquellen einer Wärmepumpe nach Betriebsart (P-433-2 S2, Variante C #431).
 *
 * Reine Funktionen, getrennt von der Fläche (`DatenquellenZuordnung.tsx`), damit Blockbildung und
 * Blockkopf-Status ohne Rendering prüfbar sind.
 *
 * **Woher die Betriebsart kommt:** aus der Registry (`betriebsart` je Feld, vom Backend durchgereicht);
 * **welche Felder in der ersten Reihe stehen:** aus `erweitert` (Registry-`bedingung`/`weich` am Gerät —
 * Heizen weich `!brauchwasser`, Warmwasser weich `!luft_luft`, Kühlen weich an der Funktion `kuehlt`:
 * Klimagerät oder Stammdatum `kuehlung_art`). Bauart und Kühlung wirken damit nur über die Registry (B8);
 * diese Datei liest beides nicht. `kuehlung_art` braucht sie nur für das Status-Wort «passiv».
 *
 * **Blockregel (Bauplan §3 E3, Nacharbeit H1):** ein Block ist sichtbar ⇔ mindestens ein Feld seiner
 * Betriebsart ist nicht `erweitert`.
 *
 * **Blockkopf-Status (E-P2-3: Wörter, keine Arbeitszahl):** je Feld ● Sensor · Σ durch andere gedeckt
 * (`bedarf: inaktiv`, z. B. «Wärme gesamt», wenn Heizwärme zugeordnet ist) · ⊘ keine. Der Kopf sagt
 * «vollständig» (Strom und Wärme der Betriebsart gedeckt) · «fehlt: Strom, Wärme» · «passiv» (Kühlen
 * eines passiv kühlenden Geräts ohne Zähler) · «aus Betriebsmodus abgeleitet» (kein eigener Stromzähler,
 * aber Betriebsmodus-Sensor und Gesamtstrom — eedc teilt dann selbst auf). Ein Block, der nur Leistung
 * oder Temperatur trägt, hat keinen Kopf-Status: über Mengen sagt er nichts.
 */
import type { DatenquelleFeld, DatenquelleGruppe } from '../../api/datenquellen'
import { istKuehlungPassiv } from '../../lib/investitionParameter'

/** Reihenfolge der Blöcke: erst das Gerät als Ganzes, dann die Betriebsarten in der Kanon-Reihenfolge. */
export const BETRIEBSART_REIHENFOLGE = ['geraet', 'heizen', 'warmwasser', 'kuehlen', 'lueften', 'entfeuchten'] as const

const TITEL: Record<string, string> = {
  geraet: 'Gerät gesamt',
  heizen: 'Heizen',
  warmwasser: 'Warmwasser',
  kuehlen: 'Kühlen',
  lueften: 'Lüften',
  entfeuchten: 'Entfeuchten',
}

const GERAET = 'geraet'
const KUEHLEN = 'kuehlen'

export type FeldZeichen = '●' | 'Σ' | '⊘'

/** ● Sensor zugeordnet · Σ durch andere gedeckt (`bedarf: inaktiv`) · ⊘ keine Quelle. */
export function feldZeichen(f: Pick<DatenquelleFeld, 'quelle' | 'bedarf'>): FeldZeichen {
  if (f.quelle !== 'keine') return '●'
  return f.bedarf === 'inaktiv' ? 'Σ' : '⊘'
}

export interface BetriebsartBlock {
  betriebsart: string
  titel: string
  /** Felder der ersten Reihe (nicht `erweitert`), kWh → W → Sonstige, sonst in Route-Reihenfolge. */
  felder: DatenquelleFeld[]
  /** Alle Felder der Betriebsart, auch die erweiterten — Grundlage des Status. */
  alleFelder: DatenquelleFeld[]
}

function rang(f: DatenquelleFeld): number {
  if (f.einheit === 'kWh') return 0
  if (f.einheit === 'W') return 1
  return 2
}

/** Betriebsart eines Felds; ohne Angabe (älteres Backend) zählt es zum Gerät. */
export function betriebsartVon(f: DatenquelleFeld): string {
  return f.betriebsart ?? GERAET
}

/** Ist der Block sichtbar? — die Blockregel (s. Kopf), sonst nichts. */
export function blockSichtbar(felder: DatenquelleFeld[]): boolean {
  return felder.some((f) => !f.erweitert)
}

/** Die sichtbaren Blöcke eines Wärmepumpen-Geräts in fester Reihenfolge. */
export function betriebsartBloecke(g: DatenquelleGruppe): BetriebsartBlock[] {
  const je = new Map<string, DatenquelleFeld[]>()
  for (const f of g.felder) {
    const b = betriebsartVon(f)
    je.set(b, [...(je.get(b) ?? []), f])
  }
  const reihenfolge = [...BETRIEBSART_REIHENFOLGE, ...[...je.keys()].filter((b) => !(BETRIEBSART_REIHENFOLGE as readonly string[]).includes(b))]
  const out: BetriebsartBlock[] = []
  for (const b of reihenfolge) {
    const alle = je.get(b) ?? []
    if (!blockSichtbar(alle)) continue
    const erste = alle.filter((f) => !f.erweitert)
    out.push({
      betriebsart: b,
      titel: TITEL[b] ?? b,
      felder: erste.map((f, i) => ({ f, i })).sort((a, z) => rang(a.f) - rang(z.f) || a.i - z.i).map(({ f }) => f),
      alleFelder: alle,
    })
  }
  return out
}

export interface BlockStatus {
  /** Leitzeichen des Kopfs: ● vollständig · Σ abgeleitet · ⊘ fehlt · `null` bei «passiv». */
  zeichen: FeldZeichen | null
  text: string
}

export interface StatusKontext {
  kuehlungArt: string | undefined
  /** Betriebsarten, die eedc aus dem Modus ableitet (Route, Kanon `AUFGETEILTE_MODI`). */
  modusAbleitbar: string[]
  /** Ist am Gerät ein Betriebsmodus-Sensor zugeordnet? */
  modusZugeordnet: boolean
  /** Ist der Gesamtstrom des Geräts gedeckt (● oder Σ)? Ohne ihn gibt es nichts aufzuteilen. */
  geraetStromGedeckt: boolean
}

function gedeckt(felder: DatenquelleFeld[], menge: 'strom' | 'waerme'): boolean {
  return felder.some((f) => f.menge === menge && feldZeichen(f) !== '⊘')
}

/** Der Status im Blockkopf — die EINE Stelle für die Wörter (s. Kopf der Datei). */
export function blockStatus(block: Pick<BetriebsartBlock, 'betriebsart' | 'alleFelder'>, ctx: StatusKontext): BlockStatus | null {
  const { betriebsart, alleFelder } = block
  const sichtbareMengen = alleFelder.filter((f) => !f.erweitert && f.menge != null)
  const istKuehlen = betriebsart === KUEHLEN
  if (sichtbareMengen.length === 0) return null

  const stromGedeckt = gedeckt(alleFelder, 'strom')
  const waermeGedeckt = gedeckt(alleFelder, 'waerme')
  if (istKuehlen && istKuehlungPassiv(ctx.kuehlungArt) && !stromGedeckt && !waermeGedeckt) {
    return { zeichen: null, text: 'passiv' }
  }
  const ableitbar = ctx.modusAbleitbar.includes(betriebsart)
  const stromFehlt = (sichtbareMengen.some((f) => f.menge === 'strom') || ableitbar) && !stromGedeckt
  const waermeFehlt = sichtbareMengen.some((f) => f.menge === 'waerme') && !waermeGedeckt
  if (stromFehlt && ableitbar && ctx.modusZugeordnet && ctx.geraetStromGedeckt) {
    return { zeichen: 'Σ', text: `aus Betriebsmodus abgeleitet${waermeFehlt ? ' · fehlt: Wärme' : ''}` }
  }
  if (!stromFehlt && !waermeFehlt) return { zeichen: '●', text: 'vollständig' }
  return { zeichen: '⊘', text: `fehlt: ${[stromFehlt && 'Strom', waermeFehlt && 'Wärme'].filter(Boolean).join(', ')}` }
}

/** Kontext des Status für ein Gerät — aus seinen Feldern und den Stammdaten der Route. */
export function statusKontext(g: DatenquelleGruppe): StatusKontext {
  const geraet = g.felder.filter((f) => betriebsartVon(f) === GERAET)
  return {
    kuehlungArt: g.kuehlung_art,
    modusAbleitbar: g.modus_ableitbar ?? [],
    modusZugeordnet: g.felder.some((f) => f.zustand && f.quelle !== 'keine'),
    geraetStromGedeckt: gedeckt(geraet, 'strom'),
  }
}

/** Ein Satz je Feld für den Tooltip am Kopf: «Heizwärme: ● Sensor». */
export function statusAufschluesselung(felder: DatenquelleFeld[]): string {
  const wort: Record<FeldZeichen, string> = { '●': 'Sensor', 'Σ': 'durch andere gedeckt', '⊘': 'keine Quelle' }
  return felder.map((f) => `${f.label}: ${feldZeichen(f)} ${wort[feldZeichen(f)]}`).join('\n')
}
