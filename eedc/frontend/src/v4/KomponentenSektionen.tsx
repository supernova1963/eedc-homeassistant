/**
 * KomponentenSektionen — Komponenten-Detailblöcke der Cockpit/Monat-Sicht
 * (IA v4 E3 Slice 2d, B6 + B7).
 *
 * Pro AKTIVER Komponente (Speicher/WP/E-Mob/BKW/Sonstiges) ein eingeklappter
 * Block mit Status-KPI-Strip (D2-Kanon) + Summary-Zeile + Komponenten-Identitäts-
 * Farbe. Schlank wie in der IA-v4-Vorschau (`KOMP_STATUS`/`COCKPIT_DETAIL`), die
 * Kennzahlen aber verhaltensgleich zum Donor `MonatsabschlussView`. Wärmepumpe
 * trägt zusätzlich `VerteilungsBalken` Heizung/Warmwasser (B7-Revision: Donut → Balken).
 *
 * Quelle: `AktuellerMonatResponse` (alle Komponenten-Felder bereits vorhanden).
 * Aktiv-Gating: ein Block erscheint nur, wenn die Komponente im Monat Daten hat.
 */
import type { ReactNode } from 'react'
import { Battery, TrendingUp, TrendingDown, Plug, Power, Clock } from 'lucide-react'
import { fmtCalc } from '../components/ui'
import FormelTooltip from '../components/ui/FormelTooltip'
import QuelleBadge from '../components/ui/QuelleBadge'
import { KpiStrip, VerteilungsBalken, GeraeteHinweis, type Block, type KpiStripItem } from '../components/blocks'
import { Parkbar, NOOP_PARK, type ParkApi } from '../components/park'
// N-327: der Wortlaut zu „Nicht aufgeteilt" steht genau einmal — in der
// SoT-Komponente des Komponenten-Hubs, nicht als Kopie hier.
import { ModusSplitErklaerung } from '../components/waermepumpe'
import {
  KOMPONENTEN_IDENTITAET, INVESTITION_TYP_ORDER, SONSTIGES_ERZEUGER_FARBE, ROLLEN_BG,
  SPEICHER_KPI, WP_KPI, EAUTO_KPI, BKW_KPI,
  SONSTIGES_ERZEUGER_KPI, SONSTIGES_VERBRAUCHER_KPI,
  ersparnisAnzeige,
} from '../lib'
import type { AktuellerMonatResponse, SonstigesGeraet } from '../api/aktuellerMonat'

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
interface SektionElement { id: string; titel: string; node: ReactNode }

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
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">{e.titel}</div>
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
type DetailZeile = { label: ReactNode; wert: ReactNode; akzent?: string }

function DetailListe({ rows }: { rows: DetailZeile[] }) {
  if (rows.length === 0) return null
  return (
    <dl className="text-sm space-y-1.5">
      {rows.map((r, i) => (
        <div key={i} className="flex justify-between gap-3">
          <dt className="text-gray-500 dark:text-gray-400">{r.label}</dt>
          <dd className={`tabular-nums ${r.akzent ?? 'text-gray-800 dark:text-gray-200'}`}>{r.wert}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Speicher-Wirkungsverluste in € (Opportunitätskosten des Roundtrip-Verlusts) —
 *  verhaltensgleich `MonatsabschlussView`. Null, wenn kein Verlust oder kein Preis. */
function speicherWirkungsverluste(d: AktuellerMonatResponse) {
  if (d.speicher_ladung_kwh == null || d.speicher_entladung_kwh == null) return null
  if (d.speicher_ladung_kwh <= d.speicher_entladung_kwh) return null
  if (d.einspeise_preis_cent == null && d.netzbezug_preis_cent == null) return null
  const verlust_kwh = d.speicher_ladung_kwh - d.speicher_entladung_kwh
  const netz_kwh = d.speicher_ladung_netz_kwh ?? 0
  const anteil_netz = d.speicher_ladung_kwh > 0 ? Math.min(1, netz_kwh / d.speicher_ladung_kwh) : 0
  const anteil_pv = 1 - anteil_netz
  const eins_p = d.einspeise_preis_cent ?? 0
  const bez_p = d.netzbezug_durchschnittspreis_cent ?? d.netzbezug_preis_cent ?? 0
  const euro = (verlust_kwh * anteil_pv * eins_p) / 100 + (verlust_kwh * anteil_netz * bez_p) / 100
  const teile: string[] = []
  if (anteil_pv > 0 && eins_p > 0) teile.push(`${fmt(verlust_kwh * anteil_pv, 1)} kWh × ${fmtCalc(eins_p, 2)} ct (entg. Einspeisung)`)
  if (anteil_netz > 0 && bez_p > 0) teile.push(`${fmt(verlust_kwh * anteil_netz, 1)} kWh × ${fmtCalc(bez_p, 2)} ct (Netzbezug)`)
  return { euro, teile }
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
export function baueKomponentenBloecke(
  d: AktuellerMonatResponse,
  park: ParkApi = NOOP_PARK,
  periode: 'monat' | 'tag' | 'jahr' = 'monat',
  /** Ladezustand des Tages (Spanne + Stand am Ende) — nur die Tagessicht kennt ihn,
   *  weil er aus den Stundenwerten stammt und keine Summe ist. Monat/Jahr geben
   *  `null`; ein Monats-Mittel über SoC-Stände wäre eine Zahl ohne Aussage. */
  socTag?: { min: number; max: number; ende: number } | null,
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
          berechnung={wv.teile.join(' + ')}
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
    const jazUntertitel = jaz == null ? (d.wp_jaz_grund ?? undefined) : (d.wp_jaz_hinweis ?? undefined)
    // W-6 (Fall H-B): Eine Arbeitszahl nahe 1 ist die Wahrheit über eine Anlage,
    // die viel direkt elektrisch heizt — keine Fehlfunktion. Der Satz erklärt
    // die Zahl, er bewertet den Anwender nicht, und sein Wortlaut kommt aus dem
    // Layer, damit er nicht je Sicht abweicht.
    const kpis: KpiStripItem[] = [
      { ...WP_KPI.jaz, value: fmtCalc(jaz, 2, '—'), formel: jaz != null ? 'JAZ = Wärme ÷ Strom' : undefined,
        subtitle: jazUntertitel,
        hinweis: (jaz == null && d.wp_waerme_grund)
          ? undefined
          : tagHinweis(jaz != null, 'Tages-JAZ = Wärme ÷ Strom — ' + wmz) },
      // W-18: Der Grund steht SICHTBAR unter der Zahl — dieselbe Regel, die
      // die JAZ-Kachel darüber seit S3 befolgt. Er kommt **fertig formuliert**
      // aus dem Backend, weil nur dort bekannt ist, welcher der drei Zustände
      // vorliegt: kein Zähler · zugeordnet, aber für diesen Tag leer ·
      // Zählerrücksprung. Der alte Client-Satz kannte nur den ersten und hat
      // dietmar1968 aufgefordert, einen Sensor zuzuordnen, den er zugeordnet
      // hatte (T89667 #210). Ohne Backend-Grund bleibt der bisherige Tooltip
      // stehen — er ist dann die einzige Auskunft, die es gibt.
      { ...WP_KPI.waerme, value: fmt(d.wp_waerme_kwh), unit: 'kWh',
        subtitle: hat(d.wp_waerme_kwh) ? undefined : (d.wp_waerme_grund ?? undefined),
        hinweis: d.wp_waerme_grund ? undefined : tagHinweis(hat(d.wp_waerme_kwh), wmz) },
      { ...WP_KPI.strom, value: fmt(d.wp_strom_kwh), unit: 'kWh' },
      // W-10: Ein negativer Betrag ist keine Ersparnis, und „+-49,53 €" ist
      // keine Zahl. Zwei Melder-Screenshots (dietmar1968, 25.08.). Das Plus
      // selbst war nie falsch — falsch war, es **unbesehen** voranzustellen.
      // Titel und Vorzeichen kommen aus derselben Stelle, damit sie nicht
      // auseinanderlaufen können.
      {
        ...WP_KPI.ersparnis,
        ...(wpErsparnis?.istMehrkosten
          ? { title: 'Mehrkosten vs. Gas', icon: TrendingDown, color: 'red' as const }
          : {}),
        value: wpErsparnis?.betrag ?? '—',
        unit: '€',
        // W-18: Die Ersparnis folgt aus der Wärme — fehlt die, fehlt sie aus
        // demselben Grund. Ihn hier zu wiederholen wäre eine zweite
        // Formulierung derselben Ursache; der Verweis hält beide zusammen.
        subtitle: (wpErsparnis == null && d.wp_waerme_grund)
          ? `Folgt aus der Tages-Wärme — ${d.wp_waerme_grund}` : undefined,
        hinweis: d.wp_waerme_grund
          ? undefined
          : tagHinweis(wpErsparnis != null, 'Ersparnis folgt aus der Tages-Wärme — ' + wmz),
      },
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
    // Strom-Split Heizung/Warmwasser (#191, nur bei getrennter Strommessung).
    const wpDetail: DetailZeile[] = []
    if (hat(d.wp_strom_heizen_kwh)) wpDetail.push({ label: 'Stromverbrauch · davon Heizung', wert: `${fmt(d.wp_strom_heizen_kwh)} kWh` })
    if (hat(d.wp_strom_warmwasser_kwh)) wpDetail.push({ label: 'Stromverbrauch · davon Warmwasser', wert: `${fmt(d.wp_strom_warmwasser_kwh)} kWh` })
    // W-4 (SOLL §4.1): die Arbeitszahl je Funktion steht bei den getrennten
    // Strommengen, aus denen sie entsteht — nicht als eigene KPI-Kachel oben.
    // Dort steht die Gesamt-JAZ; drei Arbeitszahlen nebeneinander wären eine
    // Zahlenwand, und die Detailzeile ist der Ort, an dem man ohnehin nachsieht,
    // *warum* die Gesamtzahl so aussieht, wie sie aussieht.
    //
    // ⚠ **Auch das gesperrte „—" erscheint, mit seinem Grund** (S3). Eine
    // fehlende Zeile wäre von „nicht getrennt gemessen" nicht zu unterscheiden.
    const jazZeile = (wert: number | null | undefined, grund: string | null | undefined, label: string) => {
      if (wert == null && !grund) return
      wpDetail.push({
        label,
        wert: wert != null ? fmtCalc(wert, 2, '—') : `— (${grund})`,
      })
    }
    jazZeile(d.wp_jaz_heizen, d.wp_jaz_heizen_grund, 'Arbeitszahl · Heizen')
    jazZeile(d.wp_jaz_warmwasser, d.wp_jaz_warmwasser_grund, 'Arbeitszahl · Warmwasser')
    jazZeile(d.wp_jaz_kuehlen, d.wp_jaz_kuehlen_grund, 'Arbeitszahl · Kühlen')
    const wpKpis = mitParkId('wp', kpis)
    // Wärme-Aufteilung Heizung/Warmwasser (VerteilungsBalken, B7) + Strom-Split (Detail)
    // + Geräte-Hinweis — je ein parkbares Element.
    const wpEls: SektionElement[] = []
    if (hat(d.wp_heizung_kwh) || hat(d.wp_warmwasser_kwh)) wpEls.push({
      id: 'el:wp-aufteilung', titel: 'Wärme-Aufteilung',
      node: <VerteilungsBalken segmente={[
        { label: 'Heizung', wert: d.wp_heizung_kwh, farbe: ROLLEN_BG.heizung },
        { label: 'Warmwasser', wert: d.wp_warmwasser_kwh, farbe: ROLLEN_BG.warmwasser },
      ]} />,
    })
    if (wpDetail.length > 0) wpEls.push({ id: 'el:wp-detail', titel: 'Strom-Aufteilung', node: <DetailListe rows={wpDetail} /> })
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
      titel: (wpLueften || wpEntfeuchten || wpWarmwasser)
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
          ]} />
          <ModusSplitErklaerung />
        </div>
      ),
    })
    const wpGeraete = geraeteNamen(d, 'waermepumpe')
    if (wpGeraete.length >= 2) wpEls.push({ id: 'el:wp-geraete', titel: 'Geräte-Hinweis', node: <GeraeteHinweis namen={wpGeraete} /> })
    if (!alleGeparkt(park, wpKpis, wpEls)) bloecke.push({
      id: 'k-waermepumpe', title: KOMPONENTEN_IDENTITAET['waermepumpe'].label, ...ident('waermepumpe'), defaultOpen: false,
      // Summary aus den vorhandenen Werten (Wärme/JAZ wenn da — Monat/Jahr/Tag-mit-WMZ;
      // sonst Strom — Tag ohne WMZ). Period-agnostisch, kein Sonderpfad.
      summary: hat(d.wp_waerme_kwh)
        // W-10, zweite Stelle: dieselbe Klasse wie in der Kachel, ohne Melder.
        ? `${jaz != null ? `JAZ ${fmtCalc(jaz, 2)} · ` : ''}${fmt(d.wp_waerme_kwh)} kWh Wärme${wpSummaryErsparnis ? ` · ${wpSummaryErsparnis.betrag} € vs. Gas` : ''}`
        : `${fmt(d.wp_strom_kwh)} kWh Strom${hat(d.wp_starts_summe_monat) ? ` · ${d.wp_starts_summe_monat!.toLocaleString('de-DE')} Starts` : ''}`,
      render: () => <Sektion kpis={wpKpis} elemente={wpEls} />,
    })
  }

  // ── E-Mobilität ─────────────────────────────────────────────────────────
  if (hat(d.emob_ladung_kwh) || hat(d.emob_km)) {
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
      { title: 'Ladung gesamt', value: fmt(d.emob_ladung_kwh), unit: 'kWh', color: 'purple', icon: Plug },
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
      summary: `${fmt(d.emob_ladung_kwh)} kWh geladen${hat(d.emob_km) ? ` · ${fmt(d.emob_km)} km` : ''}${emobErsparnis ? ` · ${emobErsparnis.betrag} € vs. Verbrenner` : ''}`,
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
