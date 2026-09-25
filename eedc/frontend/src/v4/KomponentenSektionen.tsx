/**
 * KomponentenSektionen — Komponenten-Detailblöcke der Cockpit/Monat-Sicht
 * (IA v4 E3 Slice 2d, B6 + B7).
 *
 * Pro AKTIVER Komponente (Speicher/WP/E-Mob/BKW/Sonstiges) ein eingeklappter
 * Block mit Status-KPI-Strip (D2-Kanon) + Summary-Zeile + Komponenten-Identitäts-
 * Farbe. Schlank wie in der IA-v4-Vorschau (`KOMP_STATUS`/`COCKPIT_DETAIL`), die
 * Kennzahlen aber verhaltensgleich zum Donor `MonatsabschlussView`. Wärmepumpe
 * trägt zusätzlich die Liste **je Funktion** (Bauschnitt 8) und den
 * Betriebsart-Balken.
 *
 * Quelle: `AktuellerMonatResponse` (alle Komponenten-Felder bereits vorhanden).
 * Aktiv-Gating: ein Block erscheint nur, wenn die Komponente im Monat Daten hat.
 */
import { useState, type ReactNode } from 'react'
import { Battery, TrendingUp, TrendingDown, Plug, Power, Clock, ExternalLink } from 'lucide-react'
import { fmtCalc, CollapsibleSection, SegmentControl, Table, TableHead, TableBody } from '../components/ui'
import { ZELLE, KOPF_ZELLE } from '../components/ui/tabelleMasse'
import FormelTooltip from '../components/ui/FormelTooltip'
import QuelleBadge from '../components/ui/QuelleBadge'
import { KpiStrip, VerteilungsBalken, GeraeteHinweis, type Block, type KpiStripItem } from '../components/blocks'
import { Parkbar, NOOP_PARK, type ParkApi } from '../components/park'
// N-327: der Wortlaut zu „Nicht aufgeteilt" steht genau einmal — in der
// SoT-Komponente des Komponenten-Hubs, nicht als Kopie hier.
import { ModusSplitErklaerung } from '../components/waermepumpe'
import { WaermeVerlaufChart } from './WaermeVerlaufChart'
import {
  baueWaermeVerlauf, verlaufRestZeilen, verlaufTitel, zeigtVerlauf,
  type VerlaufRest, type VerlaufSicht, type WaermeVerlaufPunkt,
} from './waermeVerlauf'
import {
  wpFunktionsGruppen, zeigtStromJeFunktion, type FunktionsGruppen, type FunktionsZeile,
} from './wpFunktionsGruppen'
import {
  balkenSegmente, kostenZeilen, verteilungHinweise, verteilungTitel,
  verteilungVerlaufDaten, zeigtVerteilung,
} from './waermeVerteilung'
import {
  ACHSE, GROESSE, geraetZelle, imKasten, jazAnzeige, kennzahlUntertitel,
} from './waermeKlimaSicht'
import type { AchsenName } from './waermeKlimaSicht'
import {
  KOMPONENTEN_IDENTITAET, INVESTITION_TYP_ORDER, SONSTIGES_ERZEUGER_FARBE, ROLLEN_BG,
  SPEICHER_KPI, WP_KPI, EAUTO_KPI, BKW_KPI,
  SONSTIGES_ERZEUGER_KPI, SONSTIGES_VERBRAUCHER_KPI,
  ersparnisAnzeige,
} from '../lib'
import type {
  AktuellerMonatResponse, SonstigesGeraet, WpGeraetZeile, WpMoeglichZeile,
} from '../api/aktuellerMonat'
import type { VerteilungVerlauf } from '../api/energie_profil'

const fmt = (v: number | null | undefined, dec = 0) => fmtCalc(v, dec, '—')
const hat = (v: number | null | undefined) => v != null

/** Sektions-Kopf-Identität (Icon + Farbe) aus dem SoT — #3b'. */
const ident = (typ: string) => {
  const i = KOMPONENTEN_IDENTITAET[typ]
  return { icon: i.icon, farbe: i.farbe }
}

/** Aktive Geräte-Namen eines oder mehrerer Typen (für den „aggregiert aus …"-Hinweis). */
function geraeteNamen(d: AktuellerMonatResponse, ...typen: string[]): string[] {
  return typen.flatMap((t) => d.komponenten_geraete?.[t] ?? [])
}

/** Slug für view-weit eindeutige parkIds (block-/gerät-präfixiert). */
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/gi, '-')

/** Ein parkbares Zusatz-Element unter dem KPI-Strip (Detailliste, Balken, Hinweis). */
interface SektionElement {
  id: string
  titel: string
  node: ReactNode
  /** Das Element zeichnet seine Überschrift **selbst** (WK-09 B2). Nötig genau
   *  dort, wo der Titel von einer Bedienung des Elements abhängt: Der
   *  Wärme/Klima-Verlauf schaltet zwischen zwei Familien um, und S2 verlangt,
   *  dass der Titel die gerade gestapelte Größe nennt. `titel` bleibt trotzdem
   *  gesetzt — er beschriftet den Parkplatz-Chip. */
  titelImNode?: boolean
}

/** Die Überschrift eines Sektions-Elements — eine Typografie, ein Ort (Regel 0a). */
export function ElementTitel({ children }: { children: ReactNode }) {
  return <div className="text-sm font-medium text-gray-700 dark:text-gray-300">{children}</div>
}

/** Eine Komponenten-Sektion: KPI-Kacheln (je parkbar via parkId) + parkbare
 *  Zusatz-Elemente. Element-Park-Doktrin (Gernot 2026-06-27): JEDE Anzeige im
 *  Block ist einzeln parkbar (auch Detaillisten/Balken/Hinweise) — der Block
 *  selbst nicht; ist alles geparkt, blendet der Aufrufer den Block aus. */
function Sektion({ kpis, elemente }: { kpis: KpiStripItem[]; elemente?: SektionElement[] }) {
  return (
    <div className="space-y-3">
      {kpis.length > 0 && <KpiStrip kpis={kpis} />}
      {/* ⭐ **S2 — ein Balken sagt, was er zeigt** (Befund W-8, dietmar1968
          T89667 #203). Der `titel` eines Elements gab es schon; er ging aber
          NUR an den Parkplatz-Chip und war in der Anzeige unsichtbar. Folge:
          Zwei völlig verschiedene Größen teilten sich unbeschriftet denselben
          Platz — im Juli die **Wärme**-Aufteilung (Heizung/Warmwasser), im
          August die **Strom**-Aufteilung (Heizen/Kühlen). Der Melder las das
          als „Warmwasser erscheint als Balken gar nicht mehr".

          ⚠ **Bewusst für JEDES Element, nicht nur die zwei gemeldeten Balken**
          (Entscheid Gernot 26.08.). Die Regel lautet „ein Balken sagt, was er
          zeigt" — sie gilt nicht nur dort, wo gerade jemand hingesehen hat.
          Die Beschriftung sitzt INNERHALB der `Parkbar`, damit sie mit ihrem
          Element geparkt wird statt als Überschrift ohne Inhalt stehenzubleiben.
          Typografie aus dem bestehenden Muster (`GeraeteSektionen`) — keine
          neue Klasse (Regel 0a). */}
      {elemente?.map((e) => (
        <Parkbar key={e.id} id={e.id} titel={e.titel}>
          <div className="space-y-2">
            {!e.titelImNode && <ElementTitel>{e.titel}</ElementTitel>}
            {e.node}
          </div>
        </Parkbar>
      ))}
    </div>
  )
}

/** view-weit eindeutige parkId je Block-KPI (block-präfixiert gegen Kollisionen
 *  über mehrere Komponenten-Blöcke derselben Sicht). */
function mitParkId(prefix: string, kpis: KpiStripItem[]): KpiStripItem[] {
  return kpis.map((k) => ({ ...k, parkId: `kpi:${prefix}-${slug(k.title)}` }))
}

/** Pro-Gerät parkId + eindeutiger Chip-Titel (Geräte-Präfix). Doktrin „jede Anzeige
 *  einzeln parkbar" (2026-06-27) jetzt auch INNERHALB der Sonstiges-Gerätegruppe
 *  (Gernot 2026-07-08): der frühere Ein-Element-pro-Gerät-Sonderfall (2026-06-26)
 *  wird durch getrennt parkbare Kacheln ersetzt. */
function mitGeraetParkId(prefix: string, bezeichnung: string, kpis: KpiStripItem[]): KpiStripItem[] {
  const gp = `${prefix}-${slug(bezeichnung)}`
  return kpis.map((k) => ({ ...k, parkId: `kpi:${gp}-${slug(k.title)}`, parkTitel: `${bezeichnung} · ${k.title}` }))
}

/** Block ausblenden, wenn ALLE seine Element-IDs (KPIs + Zusatz-Elemente) geparkt
 *  sind (Gernot 2026-06-27: leeren Block ausblenden). */
function alleGeparkt(park: ParkApi, kpis: KpiStripItem[], elemente: SektionElement[]): boolean {
  const ids = [...kpis.map((k) => k.parkId).filter((x): x is string => !!x), ...elemente.map((e) => e.id)]
  return ids.length > 0 && ids.every((id) => park.istGeparkt(id))
}

/** Sonder-Darstellung „Sonstiges": je Gerät eine beschriftete Werte-Gruppe
 *  (Gerätebezeichnung + KpiStrip). Doktrin (Gernot 2026-07-08): JEDE Kachel einzeln
 *  parkbar; die Geräte-Beschriftung bleibt, solange ≥1 Kachel des Geräts sichtbar
 *  ist, und verschwindet mit der letzten geparkten Kachel. */
function GeraeteSektionen({ prefix, geraete, kpisVon, park }: {
  prefix: string; geraete: SonstigesGeraet[]; kpisVon: (g: SonstigesGeraet) => KpiStripItem[]; park: ParkApi
}) {
  return (
    <div className="space-y-4">
      {geraete.map((g) => {
        const kpis = mitGeraetParkId(prefix, g.bezeichnung, kpisVon(g))
        const sichtbar = kpis.some((k) => !k.parkId || !park.istGeparkt(k.parkId))
        if (!sichtbar) return null
        return (
          <div key={g.bezeichnung} className="space-y-2">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">{g.bezeichnung}</div>
            <KpiStrip kpis={kpis} />
          </div>
        )
      })}
    </div>
  )
}

/** Detail-/Vergleichszeilen unter dem Status-Strip (periodensinnvolle IST-Werte,
 *  E-Gegencheck). Dieselbe dl-Bildsprache wie der Finanz-Teaser. */
type DetailZeile = {
  label: ReactNode
  wert: ReactNode
  akzent?: string
  /** Erklärt einen Strich beim Überfahren (D-Sicht 2, Gegenlesung A-4). Native
   *  `title`-Beschriftung wie an den Balken in `SpeicherPotentialIST` und den
   *  gekürzten Namen in `KomponentenTypV4` — **keine zweite Tooltip-Bauform**. */
  titel?: string
}

function DetailListe({ rows }: { rows: DetailZeile[] }) {
  if (rows.length === 0) return null
  return (
    <dl className="text-sm space-y-1.5">
      {rows.map((r, i) => (
        <div key={i} className="flex justify-between gap-3">
          <dt className="text-gray-500 dark:text-gray-400">{r.label}</dt>
          <dd className={`tabular-nums ${r.akzent ?? 'text-gray-800 dark:text-gray-200'}`}
              title={r.titel}>{r.wert}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Bauschnitt 8 — die Detail-Liste je Funktion. Überschrift in der Bauform von
 *  `GeraeteSektionen`, darunter dieselbe `DetailListe` (Regel 0a: keine zweite
 *  Listen-Komponente). Funktionen ohne Menge folgen als Einzelzeilen. */
function FunktionsGruppenListe({ fg }: { fg: FunktionsGruppen }) {
  const zeile = (z: FunktionsZeile): DetailZeile => ({
    label: z.label,
    wert: z.art === 'arbeitszahl'
      ? fmtCalc(z.wert, 2, '—')
      : `${fmt(z.kwh)} kWh`,
    // Nur der Strich einer Arbeitszahl trägt eine Erklärung — eine Menge
    // erklärt sich selbst.
    titel: z.art === 'arbeitszahl' ? z.tooltip : undefined,
  })
  return (
    <div className="space-y-4">
      {fg.gruppen.map((g) => (
        <div key={g.funktion} className="space-y-2">
          <div className="text-sm font-medium text-gray-700 dark:text-gray-300">{g.titel}</div>
          <DetailListe rows={g.zeilen.map(zeile)} />
        </div>
      ))}
    </div>
  )
}

/** **D-Sicht 3: die Kennzahlen JE GERÄT im Block selbst** (Konzept §6,
 *  14.09.2026). Bis dahin stand hier nur ein Link in den Komponenten-Hub — bei
 *  gemischter Ausstattung blieb der Anwender vor Strichen stehen, obwohl jedes
 *  seiner Geräte eine saubere Zahl hat.
 *
 *  ⛔ **Der Client rechnet keine Arbeitszahl** (ADR-002/P12, `check:cop-roh`):
 *  Die Zeilen kommen fertig aus derselben Rechenstelle, die auch den Hub
 *  speist.
 *
 *  ⭐ **Kein Strich ohne Grund** (WK-16h/**R-4**, N-502). Bis zum 15.09.2026
 *  trug im ganzen Block **kein einziges** `title`: Jede Zelle ohne Zahl stand
 *  unerklärt da, obwohl die API je Zelle einen Grund liefert. Jetzt trägt sie
 *  ihn beim Überfahren — und eine Zelle, deren **Achse es am Gerät nicht
 *  gibt**, bleibt leer statt einen Mangel zu behaupten. Welche Lage vorliegt,
 *  entscheidet `geraetZelle` (dort die Tabelle der drei Fälle); der
 *  Ausstattungs-Grund steht zusätzlich **mit Handgriff** im Kasten darunter.
 *
 *  Tabellen-SoT wie überall: `Table`/`TableHead`/`TableBody`, `ZELLE`/
 *  `KOPF_ZELLE`, Header-Farbe `text-gray-500 dark:text-gray-400`, Einheit in
 *  RUNDEN Klammern (Style-Guide B2, `check:tabellen`). */
function GeraeteKennzahlen({ zeilen, istSchranke }: {
  zeilen: WpGeraetZeile[]
  istSchranke?: boolean | null
}) {
  /** Eine Zahlen-Zelle: Zahl · „—" mit Grund · leer (nicht geltende Achse). */
  const ZZ = ({ wert, grund, achse, zeile }: {
    wert?: number | null
    grund?: string | null
    achse?: AchsenName
    zeile?: WpGeraetZeile
  }) => {
    const z = geraetZelle(wert, grund, achse, zeile)
    return (
      <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}
        title={z.title}>
        {z.leer ? '' : fmtCalc(wert, 2, '—')}
      </td>
    )
  }
  return (
    <div className="space-y-2">
      <Table flaeche="karte">
        <TableHead>
          <tr className="text-gray-500 dark:text-gray-400">
            <th className={`${KOPF_ZELLE} text-left`}>Gerät</th>
            <th className={`${KOPF_ZELLE} text-right`}>Wärme (kWh)</th>
            <th className={`${KOPF_ZELLE} text-right`}>Strom (kWh)</th>
            <th className={`${KOPF_ZELLE} text-right`}>Arbeitszahl</th>
            <th className={`${KOPF_ZELLE} text-right`}>Heizen</th>
            <th className={`${KOPF_ZELLE} text-right`}>Warmwasser</th>
            <th className={`${KOPF_ZELLE} text-right`}>Kühlen</th>
          </tr>
        </TableHead>
        <TableBody>
          {zeilen.map((g) => (
            <tr key={g.investition_id} className="border-b border-gray-100 dark:border-gray-800">
              <td className={`${ZELLE} text-gray-700 dark:text-gray-300`}>{g.name}</td>
              {/* Mengen, keine Kennzahlen — aber R-4 gilt auch hier: ein
                  Strich ohne Grund ist einer zu viel. */}
              <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}
                title={g.waerme_kwh == null ? (g.waerme_grund ?? undefined) : undefined}>{fmt(g.waerme_kwh)}</td>
              <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>{fmt(g.strom_kwh)}</td>
              <ZZ wert={g.jaz} grund={g.jaz_grund} />
              <ZZ wert={g.jaz_heizen} grund={g.jaz_heizen_grund} achse={ACHSE.heizen} zeile={g} />
              <ZZ wert={g.jaz_warmwasser} grund={g.jaz_warmwasser_grund} achse={ACHSE.warmwasser} zeile={g} />
              <ZZ wert={g.jaz_kuehlen} grund={g.jaz_kuehlen_grund} />
            </tr>
          ))}
        </TableBody>
      </Table>
      {/* Der Satz, der die Kachel oben mit dieser Tabelle verbindet: Warum die
          anlagenweite Zahl ein „≥" trägt und die Gerätezahl daneben nicht. */}
      {istSchranke && (
        <div className="text-xs text-gray-500 dark:text-gray-400">
          Die Zahl oben ist ein Mindestwert für die ganze Anlage; hier steht jedes
          Gerät für sich.
        </div>
      )}
    </div>
  )
}

/** **D-Sicht 1: der Kasten „Was noch möglich wäre"** — einmal je Sicht.
 *
 *  ⭐ **Der Grund bleibt, seine Wiederholung nicht.** W-18 hat dafür gesorgt,
 *  dass eedc den zutreffenden Grund nennt statt eines falschen; die D-Sicht
 *  sorgt dafür, dass er **einmal** dasteht statt an vier Kacheln. Daneben steht
 *  der Handgriff und der Weg dorthin — der Daten-Checker bleibt der Ort für
 *  Reparatur-Hinweise, dieser Kasten verweist nur.
 *
 *  Einklappbar wie die Erklärungen dieser Fläche (`ModusSplitErklaerung`) und
 *  parkbar wie jedes Block-Element (Park-Doktrin). */
function WasNochMoeglich({ zeilen }: { zeilen: WpMoeglichZeile[] }) {
  return (
    // ⭐ **Vorbelegt OFFEN, und das ist S3.** Der Kasten TRÄGT die Gründe, die
    // bis zur D-Sicht unter den Kacheln standen; eingeklappt wären sie wieder
    // das, was S3 verbietet — eine Auskunft, die man erst aufklappen muss („ein
    // Tooltip ist auf dem Telefon keine Auskunft"). Einklappen kann sie, wer
    // sie gelesen hat; `CollapsibleSection` merkt sich die Entscheidung.
    //
    // ⛔ **SoT-Komponente statt eines rohen Schalt-Elements** (Regel 0a / B15,
    // `check:buttons` · `check:roh-controls`): Ein aufklappbarer Abschnitt ist
    // ein bestehendes Pattern; eine zweite Bauform daneben wäre genau der Fall,
    // gegen den die Regel steht.
    <CollapsibleSection storageKey="wp-was-noch-moeglich" title="Was noch möglich wäre"
      className="shadow-none">
      <ul className="space-y-3">
        {zeilen.map((z) => (
          <li key={z.grund} className="text-sm">
            <div className="text-gray-800 dark:text-gray-200">{z.groesse}</div>
            <div className="text-gray-500 dark:text-gray-400">{z.grund}</div>
            {z.handgriff && (
              <div className="mt-0.5 text-gray-600 dark:text-gray-300">
                {z.link
                  ? (
                    <a href={z.link}
                       className="inline-flex items-center gap-1 text-primary-700 dark:text-primary-300 hover:underline">
                      <ExternalLink className="h-3.5 w-3.5" />
                      {z.handgriff}
                    </a>
                  )
                  : z.handgriff}
              </div>
            )}
          </li>
        ))}
      </ul>
    </CollapsibleSection>
  )
}

/** Speicher-Wirkungsverluste in € (Opportunitätskosten des Roundtrip-Verlusts) —
 *  verhaltensgleich `MonatsabschlussView`. Null, wenn kein Verlust oder kein Preis.
 *
 *  ⛔ **`gekappt` ist keine Kosmetik (N-444/K2, ADR-002/P4).** Der Netz-Anteil ist
 *  auf 100 % begrenzt, weil er sonst über 1 laufen und den PV-Anteil negativ
 *  machen könnte. Bis zum 13.09.2026 geschah das **stumm** — die Zeile zeigte
 *  einen Betrag, der eine Messung zu sein schien, obwohl die Rechnung ihre
 *  eigene Eingabe korrigiert hatte.
 *
 *  Seit N-444 stehen Zähler und Bezug im selben Fenster; **erreichbar bleibt die
 *  Kappung trotzdem**, und zwar aus einem zweiten, unabhängigen Grund: Der Zähler
 *  `speicher_ladung_netz_kwh` ist eine **Brutto**-Menge, der Bezug
 *  `speicher_ladung_kwh` eine **Netto**-Menge (`Σ max(0, −batterie_kw)`). Eine
 *  Stunde mit 2,0 kWh Netzladung und 1,5 kWh Entladung liefert netto 0,5 kWh.
 *  Das ist **N-197** und wird dort gelöst, nicht hier — hier wird es gesagt. */
function speicherWirkungsverluste(d: AktuellerMonatResponse) {
  if (d.speicher_ladung_kwh == null || d.speicher_entladung_kwh == null) return null
  if (d.speicher_ladung_kwh <= d.speicher_entladung_kwh) return null
  if (d.einspeise_preis_cent == null && d.netzbezug_preis_cent == null) return null
  const verlust_kwh = d.speicher_ladung_kwh - d.speicher_entladung_kwh
  const netz_kwh = d.speicher_ladung_netz_kwh ?? 0
  const roh_netz = d.speicher_ladung_kwh > 0 ? netz_kwh / d.speicher_ladung_kwh : 0
  const anteil_netz = Math.min(1, roh_netz)
  const gekappt = roh_netz > 1
  const anteil_pv = 1 - anteil_netz
  const eins_p = d.einspeise_preis_cent ?? 0
  const bez_p = d.netzbezug_durchschnittspreis_cent ?? d.netzbezug_preis_cent ?? 0
  const euro = (verlust_kwh * anteil_pv * eins_p) / 100 + (verlust_kwh * anteil_netz * bez_p) / 100
  const teile: string[] = []
  if (anteil_pv > 0 && eins_p > 0) teile.push(`${fmt(verlust_kwh * anteil_pv, 1)} kWh × ${fmtCalc(eins_p, 2)} ct (entg. Einspeisung)`)
  if (anteil_netz > 0 && bez_p > 0) teile.push(`${fmt(verlust_kwh * anteil_netz, 1)} kWh × ${fmtCalc(bez_p, 2)} ct (Netzbezug)`)
  const grund = gekappt
    ? `Netz-Anteil auf 100 % begrenzt — Netzladung (${fmt(netz_kwh, 1)} kWh) größer als die Netto-Ladung des Tages (${fmt(d.speicher_ladung_kwh, 1)} kWh): Ladung und Entladung in derselben Stunde`
    : null
  return { euro, teile, gekappt, grund }
}

/** Untertext der Wirkungsgrad-Kachel (F-22).
 *
 *  Der Wirkungsgrad eines Zeitraums ist keine reine Division: Was am Ende im
 *  Speicher steht, wird erst danach entladen. Das Backend rechnet diesen
 *  Ladestand heraus, wo es kann — und sagt über `..._quelle`, ob es das
 *  konnte. Diese Funktion macht daraus den Satz unter der Zahl.
 *
 *  Vorher stand hier ein einzelnes Boolean, das drei verschiedene Zustände auf
 *  einen Satz abbildete („SoC-Drift — Monats-η ausgeblendet"): er erschien
 *  auch dann, wenn eine Zahl danebenstand, und im Jahreskontext war er
 *  dreifach falsch. */
function wirkungsgradHinweis(
  d: AktuellerMonatResponse,
  periode: 'monat' | 'tag' | 'jahr',
): string | undefined {
  const zeitraum = periode === 'jahr' ? 'Jahres' : periode === 'tag' ? 'Tages' : 'Monats'
  switch (d.speicher_wirkungsgrad_quelle) {
    case 'soc_korrigiert':
      return 'Ladestand am Rand herausgerechnet'
    case 'fenster_lang':
      return 'über das ganze Fenster gerechnet'
    case 'roh-unkorrigiert':
      // Ehrlich benennen statt verschweigen: ohne SoC-Messung trägt der Wert
      // den Übertrag über die Zeitraumgrenze und schwankt dadurch.
      return 'ohne Ladestand gerechnet — ungenau'
    case 'keine-ladung':
      return undefined
    case 'fenster-zu-kurz':
    case 'nicht-ermittelbar':
      return `kein Ladestand erfasst — ${zeitraum}wert nicht belastbar`
    default:
      // Bestandsverhalten für Antworten ohne das neue Feld.
      return d.speicher_soc_drift_signifikant ? `${zeitraum}-η nicht belastbar` : undefined
  }
}

/** Liefert die Blöcke der aktiven Komponenten in kanonischer Reihenfolge.
 *  `periode` steuert nur die period-spezifischen Label/Texte (WP-Counter: Tag vs.
 *  Monat/Jahr); Default 'monat' lässt Cockpit/Monat unverändert. Cockpit/Tag ruft mit
 *  'tag' → gleiche Blöcke, tages-korrekte Beschriftung. Cockpit/Jahr ruft mit 'jahr'
 *  → wie 'monat' (Σ-Slot trägt die Jahressumme, Max/Tag = höchster Einzeltag des Jahres). */
/**
 * Der Wärme/Klima-Verlauf als Element — mit dem Umschalter zwischen den beiden
 * **Familien** (SOLL §3.3/**S2a**, WK-09 B2).
 *
 * ⛔ **Nie beide Stapel zugleich.** Der Balken zeigt **entweder** den Strom nach
 * *Betriebsart* (Teilmengen und Rest) **oder** nach *Funktion* (Summanden aus
 * den Zählern `strom_heizen_kwh`/`strom_warmwasser_kwh`). Beides übereinander
 * addierte Teilmengen zu Summanden — der Fehler aus SOLL §3.2, an dem schon ein
 * Tester gescheitert ist. Die Wache dafür steht in der reinen Funktion
 * (`baueWaermeVerlauf` liefert `stapel` nur für die aktive Sicht); hier hängt
 * bloß der Schalter daran.
 *
 * ⚑ **Warum eine eigene kleine Komponente:** Der Titel muss die gerade
 * gestapelte Größe nennen (S2) — er ist damit Zustand, und Zustand braucht
 * einen Ort. Der Schalter selbst ist die SoT-Komponente `SegmentControl`
 * (Style-Guide B15), keine zweite Bauform.
 *
 * ⚠ **Voreingestellt bleibt die heutige Sicht** (Betriebsart) — wer den Verlauf
 * kennt, findet ihn unverändert vor; die zweite Sicht ist ein Angebot.
 * Die Linien (Wärme, Kälte, Temperatur) stehen in **beiden** Sichten.
 */
function WaermeVerlaufElement({ punkte, rest }: {
  punkte: WaermeVerlaufPunkt[]
  rest?: VerlaufRest | null
}) {
  const [sicht, setSicht] = useState<VerlaufSicht>('betriebsart')
  const v = baueWaermeVerlauf(punkte, sicht)
  const restZeilen = verlaufRestZeilen(rest)
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <ElementTitel>{verlaufTitel(v)}</ElementTitel>
        {v.hatFunktionsStapel && (
          <SegmentControl
            ariaLabel="Aufteilung des Stroms"
            optionen={[
              { key: 'betriebsart', label: 'nach Betriebsart' },
              { key: 'funktion', label: 'nach Funktion' },
            ]}
            value={v.sicht} onChange={setSicht}
          />
        )}
      </div>
      {(v.hatStapel || v.hatGemesseneWaerme || v.hatGemesseneKaelte) && (
        <WaermeVerlaufChart rows={v.rows} stapel={v.stapel} linien={v.linien}
          rechteEinheit="°C" />
      )}
      {/* W-17b: Die Grundmenge des **Betriebsart**-Stapels ist nicht der ganze
          Wärmepumpen-Strom. In der Funktions-Sicht ist sie es (der Rest heißt
          „Übriger Strom"), deshalb steht die Zeile dort nicht. */}
      {v.sicht === 'betriebsart' && v.hatStapel
        && Math.abs(v.bezugKwh - v.stromKwh) > 0.05 && (
        <DetailListe rows={[{
          label: 'Aufgeteilte Menge',
          wert: `${fmt(v.bezugKwh)} von ${fmt(v.stromKwh)} kWh`,
        }]} />
      )}
      {restZeilen.length > 0 && (
        <DetailListe rows={restZeilen.map((r) => ({ label: r.label, wert: `${fmt(r.kwh, 1)} kWh` }))} />
      )}
    </div>
  )
}

/**
 * **Verteilung & Verlauf** — der Blockteil aus WK-16c.
 *
 * Drei Teile, eine Antwort: die **Verteilung** des Zeitraums (Strom je Gerät und
 * Funktion als Anteile), die **Kosten je Funktion**, und derselbe Satz Segmente
 * als **Verlauf** — Stunden eines Tages, Tage eines Monats, Monate eines Jahres,
 * mit Ø-Außentemperatur und Wettersymbol über der Zeitachse.
 *
 * ⭐ **Kein neues Bild.** Die Anteile zeichnet der Aufteilungs-SoT
 * {@link VerteilungsBalken} (er hat am 19.06.2026 den Aufteilungs-Donut abgelöst
 * — *eine* Bildsprache für alle Aufteilungen, mit den Werten IN der Zeile statt
 * in einer Legende; dietmar1968s Donut zeigt dieselbe Information), die Tabelle
 * der Tabellen-SoT, den Verlauf {@link WaermeVerlaufChart}, den es für genau
 * diese drei Auflösungen schon gibt. Neu ist allein, **was** in den Segmenten
 * steht.
 *
 * ⚠ **Hier wird nichts gerechnet** — kein Anteil, keine Kosten, keine Summe
 * (ADR-001; die Kosten hängen am Monatstarif, ADR-002/**P8**). Farbe,
 * Reihenfolge und Beschriftung entscheidet die reine Funktion nebenan
 * (`waermeVerteilung.ts`), damit sie ohne Rendering prüfbar sind.
 */
function WaermeVerteilungTeil({ v }: { v: VerteilungVerlauf }) {
  const daten = verteilungVerlaufDaten(v)
  const kosten = kostenZeilen(v)
  const hinweise = verteilungHinweise(v, fmt)
  return (
    <div className="space-y-4">
      <VerteilungsBalken segmente={balkenSegmente(v)} />
      {/* ⚠ **Ohne kWh-Spalte, und das ist A6-konform:** `kWh × ct/kWh = €` ist
          eine triviale Rechnung mit sichtbaren Summanden — die kWh stehen im
          Balken darüber. Eine zweite kWh-Spalte wäre dieselbe Zahl an zwei
          Orten. */}
      {v.kosten_gesamt_euro != null && (
        <Table flaeche="karte">
          <TableHead>
            <tr className="text-gray-500 dark:text-gray-400">
              <th className={`${KOPF_ZELLE} text-left`}>Funktion</th>
              <th className={`${KOPF_ZELLE} text-left`}>Herkunft</th>
              <th className={`${KOPF_ZELLE} text-right`}>Preis (ct/kWh)</th>
              <th className={`${KOPF_ZELLE} text-right`}>Kosten (€)</th>
            </tr>
          </TableHead>
          <TableBody>
            {kosten.map((z) => (
              <tr key={z.schluessel} className="border-b border-gray-100 dark:border-gray-800">
                <td className={`${ZELLE} text-gray-700 dark:text-gray-300`}>{z.label}</td>
                <td className={`${ZELLE} text-gray-500 dark:text-gray-400`}>{z.herkunft}</td>
                <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>{fmt(z.preisCent, 1)}</td>
                <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>{fmt(z.kostenEuro, 2)}</td>
              </tr>
            ))}
            <tr className="font-medium">
              <td className={`${ZELLE} text-gray-700 dark:text-gray-300`}>Summe</td>
              <td className={ZELLE} />
              <td className={ZELLE} />
              <td className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>{fmt(v.kosten_gesamt_euro, 2)}</td>
            </tr>
          </TableBody>
        </Table>
      )}
      {daten.stapel.length > 0 && (
        <WaermeVerlaufChart
          rows={daten.rows} stapel={daten.stapel} linien={daten.linien}
          rechteEinheit="°C" wetterSymbole={daten.wetterSymbole}
        />
      )}
      {/* Die Differenzen werden **genannt**, nicht hineingerechnet (W-17b/P4). */}
      <DetailListe rows={hinweise.map((h) => ({ label: h.label, wert: h.wert }))} />
    </div>
  )
}

export function baueKomponentenBloecke(
  d: AktuellerMonatResponse,
  park: ParkApi = NOOP_PARK,
  periode: 'monat' | 'tag' | 'jahr' = 'monat',
  /** Ladezustand des Tages (Spanne + Stand am Ende) — nur die Tagessicht kennt ihn,
   *  weil er aus den Stundenwerten stammt und keine Summe ist. Monat/Jahr geben
   *  `null`; ein Monats-Mittel über SoC-Stände wäre eine Zahl ohne Aussage. */
  socTag?: { min: number; max: number; ende: number } | null,
  /** Die Perioden-Reihe für den Wärme/Klima-Verlauf (Konzept Wärme/Klima §8).
   *  Nur die Sicht kennt sie — das Aggregat `d` ist eine Summe und hat keine
   *  Zeitachse. Gleiche Bauform wie `socTag` darüber: ein zusätzlicher
   *  Eingang, ohne den sich nichts ändert. Jahr liefert Monate, später Monat
   *  die Tage und Tag die Stunden. */
  wpVerlauf?: WaermeVerlaufPunkt[] | null,
  /** Nur der Tag: was sich keiner Stunde zuordnen ließ — **je Größe** (Strom-
   *  Stapel seit Bauschnitt 5, Wärme- und Kälte-Linie seit 6b/N-437). Es wird
   *  nicht gleichmäßig verteilt (P4), sondern unter dem Verlauf genannt —
   *  sonst summierte die Zeichnung still weniger als die Kachel darüber. */
  wpVerlaufRest?: VerlaufRest | null,
  /** WK-16c: Verteilung & Verlauf des Wärme/Klima-Stroms je Gerät und Funktion.
   *  Gleiche Bauform wie `wpVerlauf` darüber — ein zusätzlicher Eingang, ohne
   *  den sich nichts ändert: Bleibt der Abruf aus, fehlt genau dieser Blockteil
   *  und sonst nichts. */
  wpVerteilung?: VerteilungVerlauf | null,
): Block[] {
  const istTag = periode === 'tag'
  const bloecke: Block[] = []

  // Voraussetzungs-Hinweis bei „—" auf Tagesebene (Gernot 2026-06-24): Tooltip,
  // welcher Sensor/welche Zuordnung für den Tageswert fehlt. Nur auf Tag (istTag) —
  // auf Monat/Jahr bedeutet „—" fehlende Monatsdaten (anderer Kontext, eigener Pfad).
  const tagHinweis = (vorhanden: boolean, text: string): string | undefined =>
    istTag && !vorhanden ? text : undefined

  // ── Speicher ────────────────────────────────────────────────────────────
  // `socTag` öffnet den Block mit: an einem Tag ohne Lade-/Entladebewegung gibt es
  // trotzdem einen Ladezustand, und ohne diese Bedingung bliebe er unsichtbar.
  if (hat(d.speicher_ladung_kwh) || hat(d.speicher_entladung_kwh) || hat(d.speicher_kapazitaet_kwh) || (istTag && socTag)) {
    // Ladung/Entladung haben kein D2-Status-Pendant → bleiben (Teaser-Metrik);
    // Wirkungsgrad/Vollzyklen ziehen Icon/Farbe/Titel aus dem D2-Kanon.
    const kpis: KpiStripItem[] = [
      { title: 'Ladung', value: fmt(d.speicher_ladung_kwh), unit: 'kWh', color: 'blue', icon: Battery },
      { title: 'Entladung', value: fmt(d.speicher_entladung_kwh), unit: 'kWh', color: 'green', icon: Battery },
      { ...SPEICHER_KPI.wirkungsgrad, value: fmtCalc(d.speicher_wirkungsgrad_prozent, 1, '—'), unit: '%',
        subtitle: wirkungsgradHinweis(d, periode) },
      // Die Kapazität steht hier als BEZUGSGRÖSSE der Vollzyklen — sie muss deshalb
      // dieselbe Zahl nennen, mit der gerechnet wurde. Mit dem Datei-Default (0 Stellen)
      // wurde aus 7,5 kWh ein „8", während die Vollzyklen daneben aus 7,5 entstanden:
      // 1.433 kWh Entladung ⇒ 191,05 Zyklen, mit 8 kWh wären es 179 (Burkard, T89667
      // #276, an seiner Anlage nachgerechnet). Eine Nachkommastelle, wie überall sonst,
      // wo eine Speicherkapazität angezeigt wird (`SpeicherSizingIST`, `EnergieprofilPrognose`).
      { ...SPEICHER_KPI.vollzyklen, value: fmtCalc(d.speicher_vollzyklen, 2, '—'),
        subtitle: hat(d.speicher_kapazitaet_kwh) ? `Kapazität ${fmt(d.speicher_kapazitaet_kwh, 1)} kWh` : undefined },
    ]
    // Ladezustand: nur auf Tagesebene, und nur wenn er gemessen ist. Der Wert ist
    // der Stand am ENDE des Tages (letzte gemessene Stunde), die Spanne sagt, wie
    // weit der Speicher an diesem Tag ausgeschwungen hat — beides Bestandsgrößen,
    // die sich weder summieren noch über einen Monat mitteln lassen.
    if (istTag && socTag) {
      kpis.push({
        ...SPEICHER_KPI.ladezustand,
        value: fmtCalc(socTag.ende, 0), unit: '%',
        subtitle: `Spanne ${fmtCalc(socTag.min, 0)}–${fmtCalc(socTag.max, 0)} % · Stand am Tagesende`,
      })
    }
    // #358 Phase 1: Auslastung und Netto-Nutzen. Beide gibt es nur auf Monats-
    // und Jahresebene — die Tagessicht kennt weder Kapazität × Tage noch eine
    // Finanz-Zeile, dort erschienen sie als dauerhaftes „—".
    if (!istTag) {
      if (hat(d.speicher_auslastung_prozent)) {
        kpis.push({
          ...SPEICHER_KPI.auslastung,
          value: fmtCalc(d.speicher_auslastung_prozent, 1, '—'), unit: '%',
          subtitle: 'Entladung ÷ (Kapazität × Tage)',
        })
      }
      if (hat(d.speicher_ersparnis_euro)) {
        kpis.push({
          ...SPEICHER_KPI.ersparnis,
          value: fmtCalc(d.speicher_ersparnis_euro, 2, '—'), unit: '€',
          subtitle: 'Netzbezug − entgangene Einspeisung',
        })
      }
    }
    // Periodensinnvolle Detailzeilen (E-Gegencheck): Netzladung/Ladepreis/Bilanz/
    // Wirkungsverluste — alles als Tag/Monat/Jahr aggregierbar.
    const detail: DetailZeile[] = []
    // „davon" ist nicht Kosmetik: `ladung_netz_kwh` ⊆ `ladung_kwh` (Vertrag in
    // core/field_definitions.py). Ohne das Wort stehen zwei Zeilen untereinander,
    // die man addieren möchte — genau so ist Rainers Doppelzählungs-Verdacht
    // vom 08.08. entstanden (F-22).
    if (hat(d.speicher_ladung_netz_kwh)) detail.push({ label: 'davon aus dem Netz (Arbitrage)', wert: `${fmt(d.speicher_ladung_netz_kwh)} kWh` })
    if (hat(d.speicher_effektiver_ladepreis_cent)) detail.push({
      label: 'Effektiver Ladepreis (Netz)',
      wert: (
        <span className="inline-flex items-center gap-2">
          {fmtCalc(d.speicher_effektiver_ladepreis_cent, 1)} ct/kWh
          {d.speicher_effektiver_ladepreis_quelle && <QuelleBadge quelle={d.speicher_effektiver_ladepreis_quelle} kind="ladepreis" />}
        </span>
      ),
    })
    if (hat(d.speicher_ladung_kwh) && hat(d.speicher_entladung_kwh)) {
      const bilanz = d.speicher_entladung_kwh! - d.speicher_ladung_kwh!
      // E3 (R3b, Gernot 2026-07-05): Amber = dokumentierte HINWEIS-Rolle
      // („negativ, aber kein Fehler") — eine negative Speicher-Bilanz ist
      // physikalisch normal (Wirkungsgrad), bewusst NICHT Kosten-/Signal-Rot.
      detail.push({
        label: 'Bilanz (Entladung − Ladung)',
        wert: `${bilanz >= 0 ? '+' : ''}${fmt(bilanz, 1)} kWh`,
        akzent: bilanz >= 0 ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400',
      })
    }
    const wv = speicherWirkungsverluste(d)
    if (wv) detail.push({
      label: (
        <FormelTooltip
          formel="Verlust × (PV-Anteil × Einspeisepreis + Netz-Anteil × Bezugspreis)"
          // N-444/K2: Wurde der Netz-Anteil begrenzt, steht der Grund neben der
          // Rechnung — eine stille Kappung ist eine Zahl, die wie eine Messung
          // aussieht (ADR-002/P4).
          berechnung={[wv.teile.join(' + '), wv.grund].filter(Boolean).join(' · ')}
          ergebnis={`= ${fmtCalc(wv.euro, 2)} €`}
        >
          Wirkungsverluste (Opportunitätskosten)
        </FormelTooltip>
      ),
      wert: `−${fmtCalc(wv.euro, 2)} €`,
      // E3 (R3b, Gernot 2026-07-05): Wirkungsverluste-€ bewusst Amber =
      // Hinweis-Rolle, NICHT Kosten-Rot (Opportunitätskosten, kein Fehler).
      akzent: 'text-amber-600 dark:text-amber-400',
    })
    const speicherKpis = mitParkId('speicher', kpis)
    const speicherEls: SektionElement[] = []
    if (detail.length > 0) speicherEls.push({ id: 'el:speicher-detail', titel: 'Speicher-Details', node: <DetailListe rows={detail} /> })
    // Phantom-Fix (Gernot 2026-07-09): GeraeteHinweis rendert erst ab 2 Geräten
    // (GeraeteHinweis.tsx:13) → nur dann als parkbares Element zählen, sonst bliebe
    // der Block bei Einzelgerät mit einem gezählt-aber-unsichtbaren Element leer stehen.
    const speicherGeraete = geraeteNamen(d, 'speicher')
    if (speicherGeraete.length >= 2) speicherEls.push({ id: 'el:speicher-geraete', titel: 'Geräte-Hinweis', node: <GeraeteHinweis namen={speicherGeraete} /> })
    if (!alleGeparkt(park, speicherKpis, speicherEls)) bloecke.push({
      id: 'k-speicher', title: 'Speicher', ...ident('speicher'), defaultOpen: false,
      summary: `${fmt(d.speicher_ladung_kwh)} kWh geladen · ${fmtCalc(d.speicher_vollzyklen, 1, '—')} Zyklen · ${fmtCalc(d.speicher_wirkungsgrad_prozent, 0, '—')} % η`,
      render: () => <Sektion kpis={speicherKpis} elemente={speicherEls} />,
    })
  }

  // ── Wärmepumpe ──────────────────────────────────────────────────────────
  if (hat(d.wp_strom_kwh) || hat(d.wp_waerme_kwh)) {
    // ⛔ **Hier stand bis 26.08.2026 `d.wp_waerme_kwh! / d.wp_strom_kwh`.**
    // Die Formel war richtig, ihre **Voraussetzung** fehlte: Ob aus Wärme und
    // Strom überhaupt ein Quotient gebildet werden darf, ist eine
    // Abgrenzungsfrage (SOLL §3.2b/R2) — und die kannte der Client nicht.
    // Komponenten-Hub und Cockpit-Übersicht sperrten bei abgeleiteter Wärme,
    // diese Sicht nicht: dieselbe Anlage, zwei Antworten (Befund W-3).
    // Jetzt liefert der Layer die Zahl fertig, mit Grund und ggf. Hinweis.
    const jaz = d.wp_jaz ?? null
    const wpErsparnis = ersparnisAnzeige(d.wp_ersparnis_euro, 2)
    const wpSummaryErsparnis = ersparnisAnzeige(d.wp_ersparnis_euro, 0)
    // Dieselben Felder wie Monat — auf Tag „—" wo der Tagessensor fehlt (Wärme/JAZ
    // nur mit Wärmemengenzähler; Ersparnis € folgt aus Wärme). Kein Weglassen
    // ([[feedback_sensor_ableitbar_nicht_weglassen]]).
    const wmz = 'Tageswert braucht einen Wärmemengenzähler am Gerät (Sensor zuordnen); sonst nur Monatswert.'
    // ⭐ **Der Grund steht SICHTBAR unter der Zahl, nicht im Hover-Tooltip.**
    // S3 verlangt *„nicht ‚—', sondern der Grund"* — und ein Tooltip ist auf
    // dem Telefon keine Auskunft. Er entsteht dort, wo die Sperre entscheidet
    // (Layer), nicht als Client-Vermutung.
    // Der period-spezifische Voraussetzungs-Hinweis bleibt als Tooltip daneben:
    // er sagt, was zu TUN ist (Sensor zuordnen), der Grund sagt, was IST.
    // ── D-Sicht (Konzept §6, 14.09.2026) ─────────────────────────────────
    //
    // ⛔ **Hier stand bis dahin `jaz == null ? d.wp_jaz_grund : d.wp_jaz_hinweis`.**
    // Der Grund unter einem „—" war seit S3 richtig — und er war auf dieser
    // Fläche VIERMAL nebeneinander zu lesen (JAZ · AZ Heizen · AZ Warmwasser ·
    // AZ Kühlen), jedes Mal derselbe fehlende Zähler. Die Aussage „für dich
    // nicht messbar" gehört einmal auf die Seite, nicht sechsmal auf Kacheln.
    // Seither: Ausstattungs-Grund ⇒ Kasten am Blockende (die Kachel entfällt),
    // Zeitraum-Grund ⇒ „—" ohne Text. Welche Klasse ein Grund trägt, entscheidet
    // der Layer; der Client fragt nur ab, was im Kasten steht.
    const moeglich = d.wp_moeglich ?? []
    const jazUntertitel = kennzahlUntertitel(
      jaz, d.wp_jaz_schranke_hinweis, d.wp_jaz_hinweis,
    )
    // W-6 (Fall H-B): Eine Arbeitszahl nahe 1 ist die Wahrheit über eine Anlage,
    // die viel direkt elektrisch heizt — keine Fehlfunktion. Der Satz erklärt
    // die Zahl, er bewertet den Anwender nicht, und sein Wortlaut kommt aus dem
    // Layer, damit er nicht je Sicht abweicht.
    // ── D-Sicht 1: Kacheln nur mit Zahl ──────────────────────────────────
    //
    // Eine Kachel ohne Wert entfällt **genau dann**, wenn ihr Grund im Kasten
    // steht — dort ist er einmal zu lesen, mit dem Handgriff daneben. Ein
    // Zeitraum-Grund („kein Heizbetrieb in diesem Zeitraum") legt nichts in den
    // Kasten; seine Kachel bleibt mit „—" stehen, weil es nichts zu tun gibt.
    const jazEntfaellt = jaz == null && imKasten(moeglich, GROESSE.arbeitszahl)
    // ⭐ **Der Zeitraum-Grund der JAZ-Kachel — beim Überfahren** (Gegenlesung
    // A-4, 14.09.2026). Bleibt die Kachel mit „—" stehen, weil ihr Grund NICHT
    // im Kasten steht, dann ist er ein Zeitraum-Grund: Es gibt nichts zu tun,
    // aber er soll auch nicht verschwinden (S3).
    //
    // ⛔ **Über den bestehenden `hinweis`-Slot, nicht über ein rohes
    // `title` daneben** (Regel 0a): Die Kachel hat für genau diesen Fall schon
    // einen — `KpiStripItem.hinweis` heißt wörtlich *„Voraussetzungs-Hinweis
    // bei fehlendem Wert („—") — Tooltip"*. Eine zweite Bauform daneben wäre
    // die Klasse, gegen die die Regel steht. Die Detail-**Zeilen** haben keinen
    // solchen Slot; dort steht das native `title`, wie an den Balken in
    // `SpeicherPotentialIST`.
    //
    // ⚠ **`!jazEntfaellt` ist Gürtel UND Hosenträger, gemessen still** (14.09.):
    // Ein Sprengsatz, der genau diese Teilbedingung entfernt, bleibt grün —
    // entfällt die Kachel, wird ihr Hinweis ohnehin nie gezeigt. Sie steht hier
    // für den Tag, an dem jemand die Kachel doch rendert; **tragend ist sie
    // nicht.** (Dieselbe Bauform und dieselbe Offenlegung wie bei
    // `waerme_kwh is not None` in `waermepumpe_kennzahl.arbeitszahl`.)
    const jazZeitraumGrund = (jaz == null && !jazEntfaellt)
      ? (d.wp_jaz_grund ?? undefined) : undefined
    const waermeEntfaellt = !hat(d.wp_waerme_kwh) && imKasten(moeglich, GROESSE.waerme)
    const kpis: KpiStripItem[] = [
      ...(jazEntfaellt ? [] : [{ ...WP_KPI.jaz,
        // E1b: „≥ 3,25" — die Zahl ist eine untere **Schranke**, weil im Nenner
        // Strom ohne gemessene Wärme steht. Das Zeichen kommt aus einem Flag
        // des Layers; der Client rechnet keine Arbeitszahl (`check:cop-roh`).
        value: jazAnzeige(jaz, d.wp_jaz_ist_schranke, fmtCalc(jaz, 2, '—')),
        formel: jaz != null ? 'JAZ = Wärme ÷ Strom' : undefined,
        // ⭐ Die Herleitung mit den Zahlen, die der Layer BENUTZT hat.
        //
        // Die symbolische Formel darüber sagt, WAS gerechnet wird; erst die
        // beiden Zahlen sagen, WOMIT. Der Anlass: Ein Melder (dietmar1968,
        // T89667 #283) hatte eine Arbeitszahl von 0,7 vor sich — physikalisch
        // unmöglich, also ein sicheres Zeichen für einen falsch zugeordneten
        // Wärmemengenzähler. Mit „210 kWh Wärme ÷ 314 kWh Strom" daneben wäre
        // die Ursache sofort sichtbar gewesen. eedc warnt deshalb NICHT — es
        // zeigt seine Rechnung und überlässt den Schluss dem Anwender.
        //
        // ⛔ Die Zahlen kommen aus der Response und werden hier NICHT
        // nachgerechnet: Der Nenner ist nicht `wp_strom_kwh`, sondern der
        // Strom OHNE den funktionsfremden Anteil (Kühlen/Lüften/Entfeuchten,
        // `waermepumpe_kennzahl.arbeitszahl`). `wp_waerme_kwh ÷ wp_strom_kwh`
        // ergäbe bei jeder Anlage mit erfasstem Betriebsmodus eine Rechnung,
        // die nicht auf die Zahl daneben führt — die W-3-Klasse, und diese
        // Datei war dort schon einmal die dritte Stelle.
        //
        // Ohne Herleitung (gesperrte Zahl) bleibt das Feld leer, statt eine
        // Rechnung aus „—" zu bauen — Präzedenz `MonatBilanz.tsx:156`.
        berechnung: (d.wp_jaz_zaehler_kwh != null && d.wp_jaz_nenner_kwh != null)
          ? `${fmt(d.wp_jaz_zaehler_kwh, 1)} kWh Wärme ÷ ${fmt(d.wp_jaz_nenner_kwh, 1)} kWh Strom`
          : undefined,
        ergebnis: jaz != null && d.wp_jaz_zaehler_kwh != null
          ? `= ${fmtCalc(jaz, 2)}`
          : undefined,
        subtitle: jazUntertitel,
        // Der Zeitraum-Grund geht dem Tages-Voraussetzungs-Hinweis vor: Er sagt,
        // was IST, jener sagt, was zu TUN wäre — und wo der Zeitraum leer ist,
        // gibt es nichts zu tun.
        hinweis: jazZeitraumGrund ?? ((jaz == null && d.wp_waerme_grund)
          ? undefined
          : tagHinweis(jaz != null, 'Tages-JAZ = Wärme ÷ Strom — ' + wmz)) }]),
      // W-18: Der Grund steht SICHTBAR unter der Zahl — dieselbe Regel, die
      // die JAZ-Kachel darüber seit S3 befolgt. Er kommt **fertig formuliert**
      // aus dem Backend, weil nur dort bekannt ist, welcher der drei Zustände
      // vorliegt: kein Zähler · zugeordnet, aber für diesen Tag leer ·
      // Zählerrücksprung. Der alte Client-Satz kannte nur den ersten und hat
      // dietmar1968 aufgefordert, einen Sensor zuzuordnen, den er zugeordnet
      // hatte (T89667 #210). Ohne Backend-Grund bleibt der bisherige Tooltip
      // stehen — er ist dann die einzige Auskunft, die es gibt.
      // B4 (C-2, SOLL §6 vom 05.09.2026): Eine aus Strom × JAZ GESCHÄTZTE Wärme
      // stand hier wie eine Messung — nur die gesperrte JAZ verriet es. Jetzt
      // steht die Herkunft aus dem Layer unter der Kachel (dieselben Worte wie
      // im Hub seit B3); gemessene Wärme bleibt ohne Zusatz.
      // D-Sicht: Ohne Wert steht hier kein Grund mehr — er ist entweder im
      // Kasten (Ausstattung, mit Handgriff) oder er beschreibt einen leeren
      // Zeitraum, zu dem es nichts zu tun gibt. **Die Herkunft einer
      // vorhandenen Zahl bleibt** (B4): „geschätzt: Strom × JAZ 3,5" erklärt
      // eine Zahl und ist kein Sperrgrund.
      ...(waermeEntfaellt ? [] : [{ ...WP_KPI.waerme, value: fmt(d.wp_waerme_kwh), unit: 'kWh',
        subtitle: hat(d.wp_waerme_kwh)
          ? (d.wp_waerme_abgeleitet && d.wp_waerme_herkunft ? d.wp_waerme_herkunft : undefined)
          : undefined,
        hinweis: d.wp_waerme_grund ? undefined : tagHinweis(hat(d.wp_waerme_kwh), wmz) }]),
      // R-4/N-491: Deckt der Tag nicht 0–24 Uhr ab, sagt die Kachel es — unter
      // der Zahl, wie die Herkunft der Wärme darüber. ⛔ **Nur hier**, an der
      // Basis-Größe: derselbe Satz an Wärme, Arbeitszahl und Ersparnis wäre die
      // Strich-Flut, gegen die die D-Sicht gebaut ist. Der Wortlaut kommt aus
      // dem Layer; der Client entscheidet nur, wo er steht.
      { ...WP_KPI.strom, value: fmt(d.wp_strom_kwh), unit: 'kWh',
        subtitle: d.wp_abdeckung_hinweis ?? undefined },
      // W-10: Ein negativer Betrag ist keine Ersparnis, und „+-49,53 €" ist
      // keine Zahl. Zwei Melder-Screenshots (dietmar1968, 25.08.). Das Plus
      // selbst war nie falsch — falsch war, es **unbesehen** voranzustellen.
      // Titel und Vorzeichen kommen aus derselben Stelle, damit sie nicht
      // auseinanderlaufen können.
      // ── D-Sicht 1, zu Ende geführt: keine Kachel ohne Zahl ───────────────
      //
      // ⛔ **Hier stand bis zum 15.09.2026 `(waermeEntfaellt && wpErsparnis == null)`**
      // — die Kachel entfiel also nur, wenn *zusätzlich* der Wärme-Grund im
      // Kasten stand. Gemessen an der r28 (N-500): In *Cockpit → Tag* stand sie
      // an **jedem** geprüften Tag als „—" ohne Betrag, ohne Untertitel und
      // ohne Tooltip. Der Grund ist einfach: `tag-detail` **kennt das Feld
      // nicht** — der Tag rechnet keine Ersparnis (das bleibt so, N-501). Eine
      // Kachel, deren Sicht die Größe gar nicht liefert, hat nichts zu sagen.
      //
      // ⚠ **Und sie bekommt KEINE Kasten-Zeile.** Der Kasten heißt *„Was noch
      // möglich wäre"* und nennt Ausstattung, an der man etwas ändern kann; hier
      // fehlt kein Zähler, sondern eine Rechnung in dieser Sicht. Ein Eintrag
      // dort führte zu einem Handgriff, den es nicht gibt.
      ...(wpErsparnis == null ? [] : [{
        ...WP_KPI.ersparnis,
        ...(wpErsparnis?.istMehrkosten
          ? { title: 'Mehrkosten vs. Alternative', icon: TrendingDown, color: 'red' as const }
          : {}),
        value: wpErsparnis.betrag,
        unit: '€',
        // B4 (C-2): der Vorbehalt aus dem Layer — geschätzte Wärme oder ein
        // zweiter Erzeuger am Wärmezähler (F12). Er erklärt eine **vorhandene**
        // Zahl und ist deshalb das Einzige, was hier bleibt: Die Zweige für den
        // fehlenden Wert (`?? '—'`, `tagHinweis`, der Verweis auf den
        // Wärme-Grund) sind mit der Bedingung darüber tote Äste geworden.
        subtitle: d.wp_ersparnis_vorbehalt ?? undefined,
      }]),
    ]
    // #238 Counter (Verschleiß-/Auslegungs-Indikatoren). Monat: Σ Monat prominent,
    // Max/Tag im Untertitel. Tag: Tagessumme prominent, kein Max/Tag (period-korrekt,
    // Gernot 2026-06-23). Für Tag liefert der Aufrufer die Tages-Summe in
    // `wp_starts_summe_monat`/`wp_betriebsstunden_summe_monat` (period-neutraler Slot).
    const startsZeigen = istTag ? (d.wp_starts_summe_monat != null && d.wp_starts_summe_monat > 0)
                                : (d.wp_starts_max_tag != null && d.wp_starts_max_tag > 0)
    if (startsZeigen) kpis.push({
      title: 'Kompressor-Starts', color: 'gray', icon: Power,
      value: d.wp_starts_summe_monat != null ? d.wp_starts_summe_monat.toLocaleString('de-DE') : String(d.wp_starts_max_tag),
      formel: istTag ? 'Kompressor-Starts an diesem Tag' : 'Σ aller Tagessummen im Monat',
      subtitle: istTag ? undefined : `Max/Tag: ${d.wp_starts_max_tag}`,
    })
    const betriebZeigen = istTag ? (d.wp_betriebsstunden_summe_monat != null && d.wp_betriebsstunden_summe_monat > 0)
                                 : (d.wp_betriebsstunden_max_tag != null && d.wp_betriebsstunden_max_tag > 0)
    if (betriebZeigen) kpis.push({
      title: 'Betriebsstunden', color: 'gray', icon: Clock, unit: 'h',
      value: fmtCalc(d.wp_betriebsstunden_summe_monat ?? d.wp_betriebsstunden_max_tag, 1, '—'),
      formel: istTag ? 'Betriebsstunden an diesem Tag' : 'Σ aller Tages-Betriebsstunden im Monat',
      subtitle: istTag ? undefined : `Max/Tag: ${fmt(d.wp_betriebsstunden_max_tag, 1)} h`,
    })
    // W-4 (SOLL §4.1) → Bauschnitt 8: die Arbeitszahl je Funktion steht bei den
    // Mengen, aus denen sie entsteht — nicht als eigene KPI-Kachel oben. Dort
    // steht die Gesamt-JAZ; drei Arbeitszahlen nebeneinander wären eine
    // Zahlenwand. Seit Bauschnitt 8 je Funktion gruppiert: Strom · Nutzenergie ·
    // Arbeitszahl (`wpFunktionsGruppen.ts`, dort die Regeln).
    const wpFunktionen = wpFunktionsGruppen(d)
    const wpKpis = mitParkId('wp', kpis)
    // Verlauf + Liste je Funktion + Betriebsart-Balken + Geräte-Hinweis — je ein
    // parkbares Element.
    const wpEls: SektionElement[] = []
    // ── Verlauf (Konzept Wärme/Klima §8) ──────────────────────────────────
    // Reihenfolge im Block: **Kacheln → Verlauf → Aufteilung**. Der Verlauf ist
    // ein neues Element, kein Umbau — die Aufteilungs-Balken darunter bleiben,
    // wo sie waren.
    //
    // ⚠ **Der Stapel summiert auf die Aufteilungs-Grundmenge, nicht auf die
    // Kachel „Strom verbraucht"** — `modus_strom_bezug_kwh` zählt nur Geräte
    // mit Aufteilung. Genau dafür trägt der Balken darunter seit W-17b die
    // Zeile „Aufgeteilte Menge" (dietmar1968 sah 30 kWh Balken unter 284 kWh
    // Kachel). Der Verlauf erbt sie, statt eine zweite Antwort zu erfinden.
    const verlauf = wpVerlauf && wpVerlauf.length > 0 ? baueWaermeVerlauf(wpVerlauf) : null
    // N-437/E6 (a): Der Rest steht je Größe da — und das Element erscheint auch,
    // wenn NUR ein Rest da ist, sonst bliebe genau dieser Fall unsichtbar (S3).
    if (verlauf && wpVerlauf && zeigtVerlauf(verlauf, wpVerlaufRest)) wpEls.push({
      id: 'el:wp-verlauf',
      // W-8 — der Titel nennt, was wirklich drinsteht (Strom · Wärme · Kälte).
      // Die Temperatur ist Kontext, keine Größe der Anlage. Seit WK-09 B2 hängt
      // er an der gewählten Sicht und wird deshalb IM Element gezeichnet; hier
      // steht der Titel der voreingestellten Sicht für den Parkplatz-Chip.
      titel: verlaufTitel(verlauf),
      titelImNode: true,
      node: <WaermeVerlaufElement punkte={wpVerlauf} rest={wpVerlaufRest} />,
    })
    // ── WK-16c: Verteilung & Verlauf — ein weiterer parkbarer Blockteil ───
    //
    // ⚠ **Direkt unter dem Verlauf, und das ist die Reihenfolge des Konzepts**
    // (Kap. 6.2: *Kacheln → Verlauf → Aufteilung*): Erst der zeitliche Verlauf
    // der Anlage, dann dieselbe Menge nach Funktionen aufgeteilt — mit ihrem
    // eigenen Verlauf, der die Aufteilung über die Zeit zeigt.
    if (zeigtVerteilung(wpVerteilung)) wpEls.push({
      id: 'el:wp-verteilung',
      titel: verteilungTitel(wpVerteilung!),
      node: <WaermeVerteilungTeil v={wpVerteilung!} />,
    })
    // ⛔ **Bauschnitt 8 / E1 (b): Der Balken „Wärme-Aufteilung" ist entfallen.**
    // Seine zwei Zahlen stehen jetzt in den Gruppen Heizen und Warmwasser —
    // Konzept §4 ②: Funktions-Gruppen *statt* der Aufteilungs-Blöcke. Der
    // Betriebsart-Balken darunter bleibt (Konzeptänderung, s. dort).
    //
    // Die ID bleibt `el:wp-detail`, damit ein geparktes Element geparkt bleibt;
    // es versteckt ab jetzt auch Wärme und Kälte je Funktion (Handbuch).
    if (wpFunktionen.gruppen.length > 0) wpEls.push({
      id: 'el:wp-detail', titel: 'Je Funktion', node: <FunktionsGruppenListe fg={wpFunktionen} />,
    })
    // #263 K-2 (S4): Aufteilung Heizen/Kühlen — nur mit erfasstem Modus.
    // Der Balken zeigt dieselben drei Größen wie der Komponenten-Hub; ohne
    // Modus-Signal fehlt der Block ganz, statt drei Nullen zu zeigen.
    //
    // ⚠ **N-327 — der Grund gehört neben die Zahl.** Bis 25.08.2026 stand hier
    // der nackte Balken, während der Komponenten-Hub dieselben drei Größen mit
    // Erklärung und Abdeckungs-Zeile zeigt. Am 24.08. haben zwei Melder am
    // selben Tag dasselbe gefragt — Klausnn (#263) sah „Nicht aufgeteilt
    // 1 kWh · 100 %" und meldete die Aufteilung als kaputt, dietmar1968
    // (T89667 #194) sah 74 %. Beide Zahlen waren richtig: Bei einem Gerät, das
    // überwiegend aus war, ist Standby-Strom weder Heizen noch Kühlen. Der
    // Wortlaut kommt aus der SoT-Komponente, nicht als Kopie daneben.
    // E4: Lüften/Entfeuchten nur, wenn dafür ein Zähler zugeordnet ist —
    // sonst stecken sie weiterhin in „nicht aufgeteilt" (SOLL §2.3: *„Wer sie
    // nicht erfasst, sieht sie nicht."*).
    const wpLueften = d.wp_modus_strom_lueften_kwh ?? 0
    const wpEntfeuchten = d.wp_modus_strom_entfeuchten_kwh ?? 0
    // N-336: die dritte ableitbare Betriebsart. Sie kommt aus der ANDEREN
    // Quelle als die zwei darüber (abgeleitet statt gemessen) und gehört
    // trotzdem in dieselbe Titel- und Segment-Frage.
    const wpWarmwasser = d.wp_modus_strom_warmwasser_kwh ?? 0
    // R-C (WK-16f, N-398): die abgegebene **Nutzenergie** derselben zwei
    // Betriebsarten — als Zeile neben ihrem Strom, nie als Balken-Segment: der
    // Balken teilt den STROM auf. E4 bleibt, eine Kennzahl entsteht daraus
    // nicht.
    const wpNutzLueften = d.wp_modus_nutzenergie_lueften_kwh ?? 0
    const wpNutzEntfeuchten = d.wp_modus_nutzenergie_entfeuchten_kwh ?? 0
    if (d.wp_modus_gemessen || (hat(d.wp_modus_abdeckung_h) && d.wp_modus_abdeckung_h! > 0)) wpEls.push({
      // W-8: Der Titel nennt die **Größe**. „Aufteilung Heizen/Kühlen" allein
      // sagte nicht, dass hier **Strom** steht — direkt darüber kann die
      // Wärme-Aufteilung liegen, mit denselben Balken und anderer Einheit.
      //
      // ⚠ **E4: Er nennt auch, was wirklich drinsteht.** Sind Lüften oder
      // Entfeuchten gemessen, wäre „Heizen/Kühlen" ein Titel, der zwei
      // Segmente verschweigt — dieselbe Halbwahrheit, gegen die W-8 gebaut
      // wurde. Ohne diese Zähler bleibt der eingeführte Wortlaut unverändert.
      id: 'el:wp-modus-split',
      // Bauschnitt 8 / E3 (b): Zeigt die Liste darüber einen getrennt
      // gemessenen Strom Heizen, stehen zwei verschiedene Mengen „Heizen" im
      // Block — die Betriebsart „Heizen" enthält den Warmwasser-Strom (IST §888).
      // Dann sagt der Titel, wonach dieser Balken aufteilt (S2).
      titel: (wpLueften || wpEntfeuchten || wpWarmwasser || zeigtStromJeFunktion(wpFunktionen))
        ? 'Strom-Aufteilung nach Betriebsart'
        : 'Strom-Aufteilung Heizen/Kühlen',
      node: (
        <div className="space-y-3">
          <VerteilungsBalken segmente={[
            { label: 'Heizen', wert: d.wp_modus_strom_heizen_kwh ?? 0, farbe: ROLLEN_BG.heizung },
            ...(wpWarmwasser
              ? [{ label: 'Warmwasser', wert: wpWarmwasser, farbe: ROLLEN_BG.warmwasser }]
              : []),
            { label: 'Kühlen', wert: d.wp_modus_strom_kuehlen_kwh ?? 0, farbe: ROLLEN_BG.kuehlung },
            ...(wpLueften ? [{ label: 'Lüften', wert: wpLueften, farbe: ROLLEN_BG.lueftung }] : []),
            ...(wpEntfeuchten
              ? [{ label: 'Entfeuchten', wert: wpEntfeuchten, farbe: ROLLEN_BG.entfeuchtung }]
              : []),
            { label: 'Nicht aufgeteilt', wert: d.wp_modus_nicht_aufgeteilt_kwh ?? 0, farbe: ROLLEN_BG.nicht_aufgeteilt },
          ]} />
          {/* Woher die Aufteilung kommt — dieselbe Unterscheidung wie im Hub:
              ein Betriebsart-Zähler hat keine „Stunden mit Signal", dort „0
              Stunden" zu zeigen sähe aus wie ein Sensor-Ausfall. */}
          <DetailListe rows={[
            d.wp_modus_gemessen
              ? { label: 'Herkunft', wert: 'gemessen' }
              : { label: 'Modus erfasst', wert: `${fmtCalc(d.wp_modus_abdeckung_h, 0, '—')} Stunden` },
            // W-17b: **Der Balken nennt seine Grundmenge.** Er beschreibt nur
            // die Geräte, die eine Aufteilung beigesteuert haben; die Kachel
            // „Strom verbraucht" darüber summiert ALLE. dietmar1968 sah 30 kWh
            // Balken unter 284 kWh Kachel, ohne dass die Differenz irgendwo
            // stand (T89667 #210).
            //
            // ⚠ Die Kachel bleibt unangetastet — sie ist eine vollständige und
            // richtige Aussage über die Anlage. Wer eine Teilaussage macht,
            // nennt ihren Umfang; nicht umgekehrt.
            ...(hat(d.wp_modus_strom_bezug_kwh) && hat(d.wp_strom_kwh)
              && Math.abs(d.wp_modus_strom_bezug_kwh! - d.wp_strom_kwh!) > 0.05
              ? [{ label: 'Aufgeteilte Menge',
                   wert: `${fmt(d.wp_modus_strom_bezug_kwh)} von ${fmt(d.wp_strom_kwh)} kWh` }]
              : []),
            // R-C: **nur mit Zahl** (D-Sicht) — ohne zugeordneten Zähler stünde
            // hier an jeder Wärmepumpe eine 0-Zeile, die für fast jeden nichts
            // sagt (E4: „Wer sie nicht erfasst, sieht sie nicht.").
            ...(wpNutzLueften
              ? [{ label: 'Nutzenergie Lüften', wert: `${fmt(wpNutzLueften)} kWh` }]
              : []),
            ...(wpNutzEntfeuchten
              ? [{ label: 'Nutzenergie Entfeuchten', wert: `${fmt(wpNutzEntfeuchten)} kWh` }]
              : []),
          ]} />
          <ModusSplitErklaerung />
        </div>
      ),
    })
    const wpGeraete = geraeteNamen(d, 'waermepumpe')
    if (wpGeraete.length >= 2) wpEls.push({ id: 'el:wp-geraete', titel: 'Geräte-Hinweis', node: <GeraeteHinweis namen={wpGeraete} /> })
    // ── D-Sicht 3: Zahlen je Gerät, im Block statt nur im Hub ─────────────
    const wpGeraeteZeilen = d.wp_geraete ?? []
    if (wpGeraeteZeilen.length > 0) wpEls.push({
      id: 'el:wp-geraete-zahlen', titel: 'Zahlen je Gerät',
      node: <GeraeteKennzahlen zeilen={wpGeraeteZeilen} istSchranke={d.wp_jaz_ist_schranke} />,
    })
    // ── Weg zu den Gerätezahlen (Konzept §4, SOLL §3.3/S3) ────────────────
    // S3 sagt: Eine Sicht, die weniger zeigt, sagt **warum**. Der Link ist die
    // Fortsetzung — sie sagt auch **wo es steht**. Bis hierher hatte die
    // Blockfabrik NULL Cross-Links; der Grund stand da, der Weg nicht.
    //
    // ⛔ **Nicht bei jeder gesperrten Kennzahl.** Der Hub rechnet je Gerät und
    // sperrt bei einer gemeldeten Abgrenzungs-Störung, bei abgeleiteter Wärme
    // und bei fehlendem Zähler **genauso**. Ein Link dorthin wäre ein
    // vergeblicher Weg — schlechter als keiner. Welche Gründe der Hub wirklich
    // beantwortet, entscheidet der Layer (`GRUENDE_HUB_HILFT`); der Client
    // vergleicht keine Grund-Texte, sonst stünde dieselbe Regel an zwei Orten.
    // ⭐ **D-Sicht 3: „Der Link bleibt."** Er zeigt jetzt auch dann, wenn die
    // Tabelle darüber steht — dort gibt es **mehr** als die Zahl: Verlauf,
    // Saison-Vergleich, Wirtschaftlichkeit je Gerät.
    if (d.wp_hub_hilft || wpGeraeteZeilen.length > 0) wpEls.push({
      id: 'el:wp-hub-link', titel: 'Mehr je Gerät',
      node: (
        <a href="#/komponenten/waermepumpe"
           className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
          <ExternalLink className="h-4 w-4" />
          {wpGeraete.length >= 2
            ? 'Arbeitszahlen je Gerät im Komponenten-Hub'
            : 'Arbeitszahl je Gerät im Komponenten-Hub'} →
        </a>
      ),
    })
    // ── D-Sicht 1: der Kasten „Was noch möglich wäre" — ans Blockende ────
    //
    // ⚠ **Zuletzt eingehängt, und das ist die Aussage der Reihenfolge:** Erst
    // steht da, was die Daten hergeben; danach einmal, was noch möglich wäre.
    // Parkbar wie jedes Element (Park-Doktrin) und einklappbar, weil er eine
    // Erklärung ist und keine Messung.
    if (moeglich.length > 0) wpEls.push({
      id: 'el:wp-moeglich', titel: 'Was noch möglich wäre',
      titelImNode: true,
      node: <WasNochMoeglich zeilen={moeglich} />,
    })
    if (!alleGeparkt(park, wpKpis, wpEls)) bloecke.push({
      id: 'k-waermepumpe', title: KOMPONENTEN_IDENTITAET['waermepumpe'].label, ...ident('waermepumpe'), defaultOpen: false,
      // Summary aus den vorhandenen Werten (Wärme/JAZ wenn da — Monat/Jahr/Tag-mit-WMZ;
      // sonst Strom — Tag ohne WMZ). Period-agnostisch, kein Sonderpfad.
      summary: hat(d.wp_waerme_kwh)
        // W-10, zweite Stelle: dieselbe Klasse wie in der Kachel, ohne Melder.
        ? `${jaz != null ? `JAZ ${fmtCalc(jaz, 2)} · ` : ''}${fmt(d.wp_waerme_kwh)} kWh Wärme${wpSummaryErsparnis ? ` · ${wpSummaryErsparnis.betrag} € vs. Alternative` : ''}`
        : `${fmt(d.wp_strom_kwh)} kWh Strom${hat(d.wp_starts_summe_monat) ? ` · ${d.wp_starts_summe_monat!.toLocaleString('de-DE')} Starts` : ''}`,
      render: () => <Sektion kpis={wpKpis} elemente={wpEls} />,
    })
  }

  // ── E-Mobilität ─────────────────────────────────────────────────────────
  // N-557 (Konzept Regel 10): „Ladung gesamt" = Heim + Extern, soweit Extern
  // bekannt ist — eine eigene Größe aus dem Backend. Der Tag kennt kein Extern;
  // dort (und bei älteren Antworten) ist sie die Heimladung.
  const emobGesamt = d.emob_ladung_gesamt_kwh ?? d.emob_ladung_kwh
  if (hat(emobGesamt) || hat(d.emob_km)) {
    const pvAnteil = hat(d.emob_ladung_pv_kwh) && d.emob_ladung_kwh
      ? (d.emob_ladung_pv_kwh! / d.emob_ladung_kwh) * 100 : null
    // PV-Anteil/Netz-Anteil sind auf Tag mit Sensor erhebbar (tagDetail);
    // km und Verbrauch/100km haben keinen Tages-Sensor und stehen deshalb als
    // „—" mit Grund in den Kacheln unten, statt wegzufallen
    // ([[feedback_sensor_ableitbar_nicht_weglassen]]).
    //
    // ⛔ **Hier standen bis 29.08.2026 zusätzlich `extern`, `V2H` und
    // `Ersparnis` — alle drei falsch** (N-348, beim Messen des WP-Befunds
    // gefunden). `extern` und `V2H` werden sehr wohl weggelassen, und zwar in
    // BEIDEN Sichten: sie sind Detailzeilen hinter `hat(…)` und kommen aus
    // einem Monats-Handeintrag; ohne Eintrag fehlt die Zeile auch im Monat.
    // Das ist kein Verstoß gegen die Regel oben, sondern ein anderer Fall —
    // sie greift, wo eine Sicht in DERSELBEN Datenlage weniger sagt als ihre
    // Nachbarsicht. Und eine `Ersparnis`-Kachel gibt es in diesem Block
    // überhaupt nicht (nur den Zusammenfassungs-Satz weiter unten); die
    // Wärmepumpe hat eine, die E-Mobilität nicht.
    const emobErsparnis = ersparnisAnzeige(d.emob_ersparnis_euro, 2)
    const kpis: KpiStripItem[] = [
      { title: 'Ladung gesamt', value: fmt(emobGesamt), unit: 'kWh', color: 'purple', icon: Plug,
        // „PV-Anteil (Heim)" daneben bleibt auf die Heimladung bezogen.
        subtitle: hat(d.emob_ladung_extern_kwh) && (d.emob_ladung_extern_kwh ?? 0) > 0
          ? `davon extern ${fmt(d.emob_ladung_extern_kwh)} kWh` : undefined },
      { ...EAUTO_KPI.pvAnteil, value: fmtCalc(pvAnteil, 0, '—'), unit: '%',
        // W-18, dieselbe Klasse: Auch hier stand „Sensor zuordnen" bei jedem
        // „—", auch bei zugeordnetem Zähler. Der Grund kommt jetzt aus dem
        // Backend, sichtbar statt im Tooltip.
        //
        // ⚠ Die kWh-Zeile behält Vorrang, wenn es sie gibt — sie ist die
        // bessere Auskunft, und wo ein Wert steht, gibt es nichts zu erklären.
        subtitle: hat(d.emob_ladung_pv_kwh)
          ? `${fmt(d.emob_ladung_pv_kwh)} kWh PV`
          : (d.emob_ladung_pv_grund ?? undefined),
        hinweis: d.emob_ladung_pv_grund
          ? undefined
          : tagHinweis(pvAnteil != null, 'PV-Ladesensor (ladung_pv) der Wallbox/dem Auto zuordnen.') },
      { ...EAUTO_KPI.gefahren, value: fmt(d.emob_km), unit: 'km',
        hinweis: tagHinweis(hat(d.emob_km), 'Kein Tages-Kilometersensor — Strecke nur im Monatsabschluss erfassbar.') },
      { ...EAUTO_KPI.verbrauch, value: fmtCalc(d.emob_verbrauch_100km, 1, '—'), unit: 'kWh/100km',
        hinweis: tagHinweis(d.emob_verbrauch_100km != null, 'Folgt aus der Tages-Strecke — kein Tages-Sensor.') },
    ]
    // Lade-Herkunft + V2H als Detailzeilen — Netz-Anteil tagesgenau (tagDetail),
    // extern/V2H aus dem Monats-Handeintrag (→ nur zeigen wenn vorhanden).
    //
    // ⚑ Das gilt **period-unabhängig** und ist deshalb kein S3-Fall: Ohne
    // Eintrag fehlt die Zeile im Monat genauso. Der Kommentar oben behauptete
    // bis 29.08.2026 das Gegenteil (N-348).
    const emobDetail: DetailZeile[] = []
    if (hat(d.emob_ladung_netz_kwh)) emobDetail.push({ label: 'Ladung · Netz-Anteil', wert: `${fmt(d.emob_ladung_netz_kwh)} kWh` })
    if (hat(d.emob_ladung_extern_kwh)) emobDetail.push({ label: 'Ladung · extern', wert: `${fmt(d.emob_ladung_extern_kwh)} kWh` })
    if (hat(d.emob_v2h_kwh)) emobDetail.push({ label: 'V2H-Rückspeisung', wert: `${fmt(d.emob_v2h_kwh)} kWh` })
    const emobKpis = mitParkId('emob', kpis)
    const emobEls: SektionElement[] = []
    if (emobDetail.length > 0) emobEls.push({ id: 'el:emob-detail', titel: 'Lade-Herkunft', node: <DetailListe rows={emobDetail} /> })
    const emobGeraete = geraeteNamen(d, 'e-auto', 'wallbox')
    if (emobGeraete.length >= 2) emobEls.push({ id: 'el:emob-geraete', titel: 'Geräte-Hinweis', node: <GeraeteHinweis namen={emobGeraete} /> })
    if (!alleGeparkt(park, emobKpis, emobEls)) bloecke.push({
      id: 'k-emob', title: 'E-Mobilität', ...ident('e-auto'), defaultOpen: false,
      // W-10, dritte Stelle. Sie hatte keinen Melder und wäre bei einem Fix
      // nur an der gemeldeten Kachel stehen geblieben — der Grund, warum das
      // Vorzeichen einen SoT bekommen hat statt drei Einzelkorrekturen.
      summary: `${fmt(emobGesamt)} kWh geladen${hat(d.emob_km) ? ` · ${fmt(d.emob_km)} km` : ''}${emobErsparnis ? ` · ${emobErsparnis.betrag} € vs. Verbrenner` : ''}`,
      render: () => <Sektion kpis={emobKpis} elemente={emobEls} />,
    })
  }

  // ── Balkonkraftwerk ───────────────────────────────────────────────────────
  if (hat(d.bkw_erzeugung_kwh)) {
    const einsp = hat(d.bkw_erzeugung_kwh) && hat(d.bkw_eigenverbrauch_kwh)
      ? d.bkw_erzeugung_kwh! - d.bkw_eigenverbrauch_kwh! : null
    const evQuote = d.bkw_erzeugung_kwh && hat(d.bkw_eigenverbrauch_kwh)
      ? (d.bkw_eigenverbrauch_kwh! / d.bkw_erzeugung_kwh) * 100 : null
    // Erzeugung ist tagesgenau (Stundensumme). Eigenverbrauch/Einspeisung brauchen
    // den EV-Split — BKW hat selten einen eigenen Zähler → „—" wo nicht vorhanden
    // (korrekt, kein Weglassen; Gernot 2026-06-24, [[feedback_sensor_ableitbar_nicht_weglassen]]).
    const bkwHinweis = 'Eigenverbrauch/Einspeisung braucht einen eigenen BKW-Zähler (selten vorhanden).'
    const kpis: KpiStripItem[] = [
      { ...BKW_KPI.erzeugung, value: fmt(d.bkw_erzeugung_kwh), unit: 'kWh' },
      { ...BKW_KPI.eigenverbrauch, value: fmt(d.bkw_eigenverbrauch_kwh), unit: 'kWh',
        subtitle: evQuote != null ? `${fmt(evQuote)} % EV-Quote` : undefined,
        hinweis: tagHinweis(hat(d.bkw_eigenverbrauch_kwh), bkwHinweis) },
      { title: 'Einspeisung', value: fmt(einsp), unit: 'kWh', color: 'green', icon: TrendingUp,
        hinweis: tagHinweis(einsp != null, bkwHinweis) },
    ]
    const bkwKpis = mitParkId('bkw', kpis)
    const bkwEls: SektionElement[] = []
    const bkwGeraete = geraeteNamen(d, 'balkonkraftwerk')
    if (bkwGeraete.length >= 2) bkwEls.push({ id: 'el:bkw-geraete', titel: 'Geräte-Hinweis', node: <GeraeteHinweis namen={bkwGeraete} /> })
    if (!alleGeparkt(park, bkwKpis, bkwEls)) bloecke.push({
      id: 'k-bkw', title: 'Balkonkraftwerk', ...ident('balkonkraftwerk'), defaultOpen: false,
      summary: `${fmt(d.bkw_erzeugung_kwh)} kWh erzeugt · in Gesamt-PV enthalten`,
      render: () => <Sektion kpis={bkwKpis} elemente={bkwEls} />,
    })
  }

  // ── Sonstiges (Sonderfall #3c) ────────────────────────────────────────────
  // Heterogen (Erzeuger/Verbraucher) → keine sinnvolle Sammel-Summe. Statt einem
  // generischen „Sonstiges"-Block je Wirkrichtung EIN Block, benannt nach dem/den
  // Sonstiges-Gerät(en) (`investitionen_financials`, nur für die Namen), mit der
  // passenden Art-Variante. Energie bleibt das Wirkrichtungs-Aggregat (homogen
  // innerhalb der Art). Voller Per-Gerät-Deep-Dive → später Komponenten-Achse.
  // Sonder-Darstellung „Sonstiges" (Gernot 2026-06-26): ZWEI feste Blöcke
  // „Sonstiges – Erzeuger" / „Sonstiges – Verbraucher"; INNERHALB je Gerät eine
  // eigene Werte-Zeile mit Bezeichnung (echte Pro-Gerät-Werte, nicht die Summe).
  const sonstigesGeraete = d.sonstiges_geraete ?? []
  const erzeugerGeraete = sonstigesGeraete.filter((g) => g.kategorie === 'erzeuger')
  const verbraucherGeraete = sonstigesGeraete.filter((g) => g.kategorie === 'verbraucher')
  // §9.2 — der dritte Weg: Abgabe an Dritte (Mieterstrom, Allgemeinstrom).
  const abgabeGeraete = sonstigesGeraete.filter((g) => g.kategorie === 'abgabe')
  const abgabeKpis = (g: SonstigesGeraet): KpiStripItem[] => {
    const ks: KpiStripItem[] = [{ title: 'Abgabe', value: fmt(g.abgabe_kwh), unit: 'kWh', color: 'gray', icon: TrendingUp, subtitle: 'an Dritte — kein Eigenverbrauch' }]
    if (hat(g.erloes_euro)) ks.push({ title: 'Erlös', value: fmtCalc(g.erloes_euro ?? 0, 2, '—'), unit: '€', color: 'green', icon: TrendingUp })
    return ks
  }

  const erzeugerKpis = (g: SonstigesGeraet): KpiStripItem[] => {
    const ks: KpiStripItem[] = [{ ...SONSTIGES_ERZEUGER_KPI.erzeugung, value: fmt(g.erzeugung_kwh), unit: 'kWh' }]
    if (hat(g.eigenverbrauch_kwh)) ks.push({ ...SONSTIGES_ERZEUGER_KPI.eigenverbrauch, value: fmt(g.eigenverbrauch_kwh), unit: 'kWh' })
    if (hat(g.einspeisung_kwh)) ks.push({ title: 'Einspeisung', value: fmt(g.einspeisung_kwh), unit: 'kWh', color: 'green', icon: TrendingUp })
    return ks
  }
  const verbraucherKpis = (g: SonstigesGeraet): KpiStripItem[] => {
    const bezugGesamt = (g.bezug_pv_kwh ?? 0) + (g.bezug_netz_kwh ?? 0)
    const pvAnteil = bezugGesamt > 0 ? ((g.bezug_pv_kwh ?? 0) / bezugGesamt) * 100 : null
    const ks: KpiStripItem[] = [{ ...SONSTIGES_VERBRAUCHER_KPI.verbrauch, value: fmt(g.verbrauch_kwh), unit: 'kWh' }]
    if (pvAnteil != null) ks.push({
      ...SONSTIGES_VERBRAUCHER_KPI.pvAnteil, value: fmtCalc(pvAnteil, 0, '—'), unit: '%',
      subtitle: `${fmt(g.bezug_pv_kwh)} kWh PV · ${fmt(g.bezug_netz_kwh)} kWh Netz`,
    })
    return ks
  }

  // Sonstiges: je Kachel parkbar; Block aus, wenn ALLE Kacheln ALLER Geräte geparkt.
  const sonstigesAlleGeparkt = (prefix: string, gs: SonstigesGeraet[], kpisVon: (g: SonstigesGeraet) => KpiStripItem[]) =>
    gs.length > 0 && gs.every((g) =>
      mitGeraetParkId(prefix, g.bezeichnung, kpisVon(g)).every((k) => !!k.parkId && park.istGeparkt(k.parkId)),
    )

  if (erzeugerGeraete.length > 0 && !sonstigesAlleGeparkt('sonstiges-erzeuger', erzeugerGeraete, erzeugerKpis)) {
    const summe = erzeugerGeraete.reduce((a, g) => a + (g.erzeugung_kwh ?? 0), 0)
    bloecke.push({
      // Eigene Identitätsfarbe (Lime) — sonstiger Erzeuger ist NICHT PV (Regel A).
      id: 'k-sonstiges-erzeuger', title: 'Sonstiges – Erzeuger', ...ident('sonstiges'), farbe: SONSTIGES_ERZEUGER_FARBE.text, defaultOpen: false,
      summary: `${fmt(summe)} kWh erzeugt`,
      render: () => <GeraeteSektionen prefix="sonstiges-erzeuger" geraete={erzeugerGeraete} kpisVon={erzeugerKpis} park={park} />,
    })
  }

  if (verbraucherGeraete.length > 0 && !sonstigesAlleGeparkt('sonstiges-verbraucher', verbraucherGeraete, verbraucherKpis)) {
    const summe = verbraucherGeraete.reduce((a, g) => a + (g.verbrauch_kwh ?? 0), 0)
    bloecke.push({
      id: 'k-sonstiges-verbraucher', title: 'Sonstiges – Verbraucher', ...ident('sonstiges'), defaultOpen: false,
      summary: `${fmt(summe)} kWh verbraucht`,
      render: () => <GeraeteSektionen prefix="sonstiges-verbraucher" geraete={verbraucherGeraete} kpisVon={verbraucherKpis} park={park} />,
    })
  }

  if (abgabeGeraete.length > 0 && !sonstigesAlleGeparkt('sonstiges-abgabe', abgabeGeraete, abgabeKpis)) {
    const summe = abgabeGeraete.reduce((a, g) => a + (g.abgabe_kwh ?? 0), 0)
    bloecke.push({
      id: 'k-sonstiges-abgabe', title: 'Sonstiges – Abgabe an Dritte', ...ident('sonstiges'), defaultOpen: false,
      summary: `${fmt(summe)} kWh abgegeben`,
      render: () => <GeraeteSektionen prefix="sonstiges-abgabe" geraete={abgabeGeraete} kpisVon={abgabeKpis} park={park} />,
    })
  }

  // Default-Reihenfolge = Standard-Investitionstyp-Reihenfolge (`INVESTITION_TYP_ORDER`,
  // SoT) statt Bau-Reihenfolge — d. h. Speicher → Balkonkraftwerk → Wärmepumpe →
  // E-Mobilität → Sonstiges (BKW vor WP). Gilt einheitlich für Monat/Tag/Jahr.
  // Stabil → die zwei Sonstiges-Blöcke (Erzeuger vor Verbraucher) behalten ihre Folge.
  const ID_TYP: Record<string, string> = {
    'k-speicher': 'speicher', 'k-bkw': 'balkonkraftwerk', 'k-waermepumpe': 'waermepumpe',
    'k-emob': 'wallbox', 'k-sonstiges-erzeuger': 'sonstiges', 'k-sonstiges-verbraucher': 'sonstiges',
  }
  const ordnung = (b: Block) => {
    const i = (INVESTITION_TYP_ORDER as readonly string[]).indexOf(ID_TYP[b.id] ?? '')
    return i === -1 ? INVESTITION_TYP_ORDER.length : i
  }
  return [...bloecke].sort((a, b) => ordnung(a) - ordnung(b))
}
