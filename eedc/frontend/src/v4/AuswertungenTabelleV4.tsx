/**
 * AuswertungenTabelleV4 — die Werte-Werkbank im /v4-Baum (A.5 Sub 1).
 *
 * Zwei verschiebbare BlockShell-Blöcke, jeder mit einer **fest im Block verankerten**
 * Zeitraum-/Vergleich-Leiste (`WerkbankZeitraum`, Gernot 2026-06-26: nicht schwebend):
 *   • „Monatswerte"   — Monats-Granularität (`useWerteZeitreihe`), von/bis = Monate.
 *   • „Energieprofile" — Tages-Granularität (`useTagesWerte`/`getTageWerte`), von/bis = Tage.
 * Beide nutzen denselben Werte-SoT `WerteTabelle` mit Werkbank-eigenem Spalten-Scope
 * (`scope`/`defaultSpalten` → Cockpit-Embeds unberührt). Default-Spalten = Bild-1-Satz,
 * Vergleich = Vorjahr an (Monat: akt. Jahr↔Vorjahr · Tag: akt. Monat↔selber Monat Vorjahr).
 * Tabelle je parkbar (R6); geparkt → Block-Hülle ausgeblendet.
 */
import { useEffect, useMemo, useState } from 'react'
import { Table, CalendarDays, CalendarClock } from 'lucide-react'
import { Alert, FehlerZustand, TabellenSkeleton } from '../components/ui'
import { BlockShell, BlockStackSkeleton, GeraeteHinweis, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar, usePark } from '../components/park'
import { WerteTabelle } from '../components/werte'
import { monatsZeile, tagesZeile, richteMonateAus, type WerteZeile } from '../lib/werte'
import {
  baueErzeugerSpalten, ERZEUGER_OHNE_SENSOR_LABEL, ERZEUGER_OHNE_SENSOR_HINWEIS,
} from '../lib/erzeugerSpalten'
import { useApiData, useInvestitionen, useSelectedAnlage } from '../hooks'
import { energieProfilApi, type VerfuegbarerMonat } from '../api/energie_profil'
import { MONAT_KURZ, MONAT_NAMEN } from '../lib/constants'
import { offenerAbschlussMonat, type MonatRef } from '../lib/monatsLuecken'
import { baueZaehlerSpalten, zaehlerMitStand } from '../lib/zaehlerSpalten'
import type { AuswertungBasis } from './useAuswertungBasis'
import { useWerteZeitreihe } from './useWerteZeitreihe'
import { useTagesWerte } from './useTagesWerte'
import { AnlageLeer } from './OnboardingLeer'
import { WerkbankZeitraum, VergleichLeisteTag, type ZeitChip, type TagVergleichModus } from './WerkbankZeitraum'

const SICHT_KEY = 'v4-auswertungen-tabelle'
const SCOPE = 'auswertungen-werkbank'
// Bild-1-Default (Gernot 2026-06-26): Energie + Quoten, ohne Finanz-Spalten.
const DEFAULT_SPALTEN = ['erzeugung', 'eigenverbrauch', 'einspeisung', 'netzbezug', 'gesamtverbrauch', 'autarkie', 'evQuote']
const vglLabel = (modus: TagVergleichModus, jahr: number) => (modus === 'periodeImJahr' ? String(jahr) : 'Vorperiode')

const pad = (n: number) => String(n).padStart(2, '0')
const letzterTag = (y: number, m: number) => new Date(y, m, 0).getDate()
function addTage(iso: string, tage: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d))
  dt.setUTCDate(dt.getUTCDate() + tage)
  return `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}`
}
/** Vergleichs-Label aus einem Zeitraum: bei Einzeljahr „<Vorjahr>", sonst „Vorjahr". */
function vergleichLabelVon(von: string, bis: string): string {
  const vy = Number(von.slice(0, 4)); const by = Number(bis.slice(0, 4))
  return vy === by ? `${vy - 1}` : 'Vorjahr'
}
/** Label der „aktuellen" Spalte (R20-1a): bei Einzeljahr das Jahr, sonst „Aktuell". */
function jahrLabelVon(von: string, bis: string): string {
  const vy = Number(von.slice(0, 4)); const by = Number(bis.slice(0, 4))
  return vy === by ? `${vy}` : 'Aktuell'
}

/**
 * Fenster des Monats-Blocks: Primärzeitraum [von..bis] (YYYY-MM) und das um genau
 * ein Jahr zurückversetzte Vergleichsfenster. Über einen mehrjährigen Zeitraum
 * („Alle Jahre") enthält das Vergleichsfenster mehrere Jahrgänge — welcher davon zu
 * welcher Zeile gehört, entscheidet erst `richteMonateAus` (lib/werte).
 */
export function monatsFenster<T extends { jahr: number; monat: number }>(
  rows: T[], von: string, bis: string,
): { prim: T[]; vergleich: T[] } {
  const vonNum = von ? Number(von.slice(0, 4)) * 100 + Number(von.slice(5, 7)) : 0
  const bisNum = bis ? Number(bis.slice(0, 4)) * 100 + Number(bis.slice(5, 7)) : 999999
  const im = (r: T, a: number, b: number) => { const n = r.jahr * 100 + r.monat; return n >= a && n <= b }
  return {
    prim: rows.filter((r) => im(r, vonNum, bisNum)),
    vergleich: rows.filter((r) => im(r, vonNum - 100, bisNum - 100)),
  }
}

export default function AuswertungenTabelleV4({ basis }: { basis: AuswertungBasis }) {
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <TabelleInner basis={basis} />
    </ParkProvider>
  )
}

function TabelleInner({ basis }: { basis: AuswertungBasis }) {
  const park = usePark()
  const { anlagen, selectedAnlageId, selectedAnlage, loading: anlagenLoading } = useSelectedAnlage()
  // Monatswerte/Strompreise kommen aus der Dispatcher-Basis (EIN Fetch je Achse,
  // Paket Q) — der Hook leitet nur noch ab.
  const { rows, jahre, loading, error } = useWerteZeitreihe(basis, selectedAnlage)
  // #377 — Stammdaten für die Zähler-Spalten. **Ganz oben**, vor jedem
  // Early-Return: Hooks müssen in jedem Render in derselben Reihenfolge laufen
  // (`react-hooks/rules-of-hooks`; der Lint-Lauf hat genau das gefangen).
  const { investitionen: alleInvestitionen } = useInvestitionen(selectedAnlageId ?? undefined)

  // Neuestes (Jahr, Monat) als Default-Anker des MONATS-Blocks. Er zaehlt Monate
  // MIT ABSCHLUSS — dort ist das richtig: eine Monatszeile entsteht erst mit einem.
  const anker = useMemo(() => {
    if (rows.length === 0) return null
    const max = rows.reduce((acc, r) => (r.jahr * 100 + r.monat > acc.jahr * 100 + acc.monat ? r : acc), rows[0])
    return { jahr: max.jahr, monat: max.monat }
  }, [rows])

  // ── N-368: Der TAGES-Block bekommt seinen EIGENEN Anker (OB73-gif, #395) ──
  // Tageswerte entstehen ab Installation von selbst (Snapshot-/Aggregations-Jobs)
  // und brauchen KEINEN Monatsabschluss. Bis N-368 hing der Tages-Block trotzdem am
  // Abschluss-Anker daruber. Zwei Folgen, beide gemeldet bzw. am Code belegt:
  //   * Ein offener Vormonat schob die Tagesansicht auf einen alten Monat zurueck
  //     (Melder: August offen ⇒ Tagesansicht auf Juni, obwohl September gemessen war).
  //   * OHNE JEDEN Abschluss war `anker` null ⇒ `tagVon` blieb leer ⇒ `useTagesWerte`
  //     stand auf `enabled: false` und lud nichts, waehrend die Datumsauswahl auf
  //     `min="0-01-01"` klemmte. Das trifft jede frische Installation.
  // Quelle ist dieselbe, die Cockpit → Monat (:193) und Cockpit → Tag schon lesen:
  // `getVerfuegbareMonate` = GROUP BY ueber `TagesZusammenfassung`, ein leichter Fetch.
  const tagMonateQ = useApiData<VerfuegbarerMonat[]>(
    () => energieProfilApi.getVerfuegbareMonate(selectedAnlageId!),
    [selectedAnlageId],
    { enabled: !!selectedAnlageId, swrKey: `v4-tabelle-tagmonate:${selectedAnlageId}` },
  )
  const tagMonate = useMemo(() => tagMonateQ.data ?? [], [tagMonateQ.data])
  const tagAnker = useMemo<MonatRef | null>(() => {
    // Gedeckelt auf den laufenden Monat — dieselbe Auflage wie `waehleDefaultMonat`
    // (CockpitMonatV4): eine Snapshot-Streuzeile in der Zukunft darf keine leere
    // Sicht oeffnen. ⚠ RUECKFALL auf den Abschluss-Anker, wenn es KEINE Tagesspur
    // gibt (reine Handpflege): dann ist er die einzige Aussage, die es ueberhaupt
    // gibt — ohne diesen Zweig wuerde der Handpfleger brechen, um den Sensor-
    // Anwender zu heilen.
    const heute = new Date()
    const heuteIdx = heute.getFullYear() * 100 + (heute.getMonth() + 1)
    const bisHeute = tagMonate.filter((m) => m.jahr * 100 + m.monat <= heuteIdx)
    if (bisHeute.length === 0) return anker
    const max = bisHeute.reduce((a, m) => (m.jahr * 100 + m.monat > a.jahr * 100 + a.monat ? m : a), bisHeute[0])
    return { jahr: max.jahr, monat: max.monat }
  }, [tagMonate, anker])

  // N-368, zweite Haelfte (Gernot 2026-09-02): Der richtige Zeitraum darf das
  // VERSAEUMNIS nicht verschlucken. Bis hierher war der schiefe Anker das Einzige,
  // was in dieser Sicht auf einen offenen Abschluss deutete — und er hat es in einer
  // Sprache getan, die niemand versteht: Der Melder hielt ihn fuer einen Update-
  // Fehler und schrieb einen Fehlerbericht. Deshalb wird das Versaeumnis jetzt
  // BENANNT statt angedeutet, mit derselben Ableitung, die Cockpit → Monat benutzt
  // (`lib/monatsLuecken`) — keine zweite Wahrheit ueber „hast du etwas offen".
  const offenerAbschluss = useMemo(
    () => offenerAbschlussMonat(rows.map((r) => ({ jahr: r.jahr, monat: r.monat })), new Date()),
    [rows],
  )

  // ── Monats-Block: von/bis (YYYY-MM) + Vergleich ──
  const [monVon, setMonVon] = useState('')
  const [monBis, setMonBis] = useState('')
  const [monVergleich, setMonVergleich] = useState(true)
  useEffect(() => {
    if (!anker || monVon) return
    setMonVon(`${anker.jahr}-01`); setMonBis(`${anker.jahr}-12`)
  }, [anker, monVon])

  // ── Energieprofil-Block: von/bis (YYYY-MM-DD) + Vergleichs-Auswahl ──
  const [tagVon, setTagVon] = useState('')
  const [tagBis, setTagBis] = useState('')
  const [vglModus, setVglModus] = useState<TagVergleichModus>('vorperiode')
  const [vglJahr, setVglJahr] = useState(0)  // 0 = noch nicht initialisiert (s. Effekt)
  useEffect(() => {
    if (!tagAnker || tagVon) return   // N-368: Tages-Anker, nicht Abschluss-Anker
    setTagVon(`${tagAnker.jahr}-${pad(tagAnker.monat)}-01`)
    setTagBis(`${tagAnker.jahr}-${pad(tagAnker.monat)}-${pad(letzterTag(tagAnker.jahr, tagAnker.monat))}`)
  }, [tagAnker, tagVon])
  useEffect(() => {
    if (!tagAnker || vglJahr) return
    setVglJahr(tagAnker.jahr - 1)  // Default-Vergleichsjahr = Primär-Jahr − 1
  }, [tagAnker, vglJahr])

  if (anlagenLoading || loading) {
    // B8 (S15): Sicht-Skeleton in BlockShell-Form (Monatswerte offen + Energieprofile zu).
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <BlockStackSkeleton label="Lade Werte…" offen="tabelle" zu={1} />
      </div>
    )
  }
  if (anlagen.length === 0) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <AnlageLeer titel="Noch keine Anlage angelegt." />
      </div>
    )
  }
  if (error) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        {/* B8-Fehler-Baustein (S15) — Retry über den Basis-Refresh des Dispatchers
            (schließt den in VERIFIKATION-S15 notierten reload-Folge-Punkt). */}
        <FehlerZustand text={error} onRetry={basis.refresh} />
      </div>
    )
  }

  // ── Monats-Block-Daten ──
  const minJahr = jahre.length ? Math.min(...jahre) : (anker?.jahr ?? 0)
  const maxJahr = jahre.length ? Math.max(...jahre) : (anker?.jahr ?? 0)
  // N-368: Die Grenzen der TAGES-Datumsauswahl kommen aus der Tagesspur. Vorher
  // waren es die Jahre der ABSCHLUSS-Zeilen — ohne einen einzigen Abschluss also
  // `0`, und der Picker stand auf `min="0-01-01"` / `max="0-12-31"`.
  const tagJahre = tagMonate.map((m) => m.jahr)
  const tagMinJahr = tagJahre.length ? Math.min(...tagJahre) : minJahr
  const tagMaxJahr = tagJahre.length ? Math.max(...tagJahre) : maxJahr
  const { prim: monRows, vergleich: monVorjahrRows } = monatsFenster(rows, monVon, monBis)
  // #377 — Spalten je Verbrauchszähler, aus den Ständen im geladenen Fenster:
  // Ein nie abgelesener Zähler bekommt keine Spalte, sonst bestünde sie aus
  // lauter „—". Reine Ableitung, kein Hook (s. o.).
  const zaehlerSpaltenMonat = baueZaehlerSpalten(alleInvestitionen, zaehlerMitStand(monRows))

  const monVorjahr = monVergleich ? monVorjahrRows : null

  // N-368 (Mitnahme, Gernot 2026-09-02): Der Chip trug FEST „Aktuelles Jahr" und
  // sprang auf `anker.jahr` — das Jahr des letzten ABSCHLUSSES. Fehlt im Januar der
  // Dezember-Abschluss, ist das Vorjahr gemeint, und die Beschriftung behauptet
  // etwas anderes. Sichtbar wird es nur am Jahreswechsel, falsch war es immer.
  // ⚠ Im Regelfall aendert sich NICHTS: Solange der Anker im laufenden Jahr liegt,
  // steht dieselbe vertraute Beschriftung da (feedback_ist_anzeigen_nur_aendern_wo_noetig).
  const monChips: ZeitChip[] = anker ? [
    { label: anker.jahr === new Date().getFullYear() ? 'Aktuelles Jahr' : String(anker.jahr), range: () => [`${anker.jahr}-01`, `${anker.jahr}-12`], aktiv: monVon === `${anker.jahr}-01` && monBis === `${anker.jahr}-12` },
    { label: 'Alle Jahre', range: () => [`${minJahr}-01`, `${maxJahr}-12`], aktiv: monVon === `${minJahr}-01` && monBis === `${maxJahr}-12` },
  ] : []

  const monGeparkt = park.istGeparkt('tabelle:monatswerte')
  const tagGeparkt = park.istGeparkt('tabelle:energieprofile')

  const bloecke: Block[] = []
  if (!monGeparkt) {
    bloecke.push({
      id: 'monatswerte', title: 'Monatswerte', icon: Table, farbe: 'text-gray-400 dark:text-gray-500',
      summary: `${monVon || '…'} – ${monBis || '…'}${monVergleich ? ' · vs. Vorjahr' : ''}`, defaultOpen: true,
      render: () => (
        <div className="space-y-3">
          {/* D12-8: Eingabe-Grenzen aus dem verfügbaren Datenjahr-Bereich (analog
              CockpitTagV4 R5-F2) — sperrt Phantasie-Jahre wie „1822". */}
          <WerkbankZeitraum
            modus="monat" von={monVon} bis={monBis}
            onRange={(v, b) => { setMonVon(v); setMonBis(b) }}
            vergleich={monVergleich} onVergleich={setMonVergleich} chips={monChips}
            minDatum={`${minJahr}-01`} maxDatum={`${maxJahr}-12`}
          />
          <Parkbar id="tabelle:monatswerte" titel="Monatswerte">
            <WerteTabelle
              rows={monRows.map(monatsZeile)}
              // richteMonateAus: jede Zeile findet ihr ECHTES Vorjahr, auch wenn der
              // Zeitraum mehrere Jahrgänge umfasst („Alle Jahre"). Ohne Vorjahr → „—".
              vorjahrRows={richteMonateAus(monVorjahr ? monVorjahr.map(monatsZeile) : null)}
              granularitaet="monat"
              zusatzMetriken={zaehlerSpaltenMonat}
              jahrLabel={jahrLabelVon(monVon, monBis)}
              vergleichLabel={monVergleich ? vergleichLabelVon(monVon, monBis) : null}
              vergleichDefaultAn={monVergleich}
              scope={SCOPE} defaultSpalten={DEFAULT_SPALTEN}
              csvDateiname={`werte_monat_${selectedAnlage?.anlagenname ?? 'export'}.csv`}
            />
          </Parkbar>
        </div>
      ),
    })
  }
  if (!tagGeparkt) {
    bloecke.push({
      id: 'energieprofile', title: 'Tageswerte', icon: CalendarDays, farbe: 'text-gray-400 dark:text-gray-500',
      summary: `${tagVon || '…'} – ${tagBis || '…'} · Vgl. ${vglLabel(vglModus, vglJahr)}`, defaultOpen: false,
      render: () => (
        <EnergieprofilBlock
          anlageId={selectedAnlageId!} von={tagVon} bis={tagBis}
          onRange={(v, b) => { setTagVon(v); setTagBis(b) }}
          vglModus={vglModus} onVglModus={setVglModus}
          vglJahr={vglJahr} onVglJahr={setVglJahr} jahre={jahre}
          anker={tagAnker} anlagenname={selectedAnlage?.anlagenname}
          minJahr={tagMinJahr} maxJahr={tagMaxJahr}
        />
      ),
    })
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      {/* R19-4c (Rainer, Gernot-Entscheid 2026-07-17): kein „Werkbank"-Jargon im Titel. */}
      <h1 className="text-lg font-bold text-gray-900 dark:text-white">Monats- &amp; Tageswerte</h1>
      {/* N-368, zweite Haelfte (Gernot 2026-09-02): Die Tageswerte stehen seit N-368 auf
          dem neuesten GEMESSENEN Monat — damit darf der offene Abschluss nicht stillschweigend
          verschwinden. Er wird BENANNT samt Weg dorthin, statt sich als schiefer Zeitraum
          anzudeuten; genau daran ist die stille Variante gescheitert (der Melder hielt sie
          fuer einen Update-Fehler und schrieb einen Fehlerbericht). Der Knopf ist derselbe
          wie in Cockpit → Monat (`MonatRahmen`), die Ableitung dieselbe (`lib/monatsLuecken`)
          — kein zweiter Turm ueber „hast du etwas offen".
          ⛔ Er steht auf SICHT-Ebene und NICHT im Tages-Block: der ist `defaultOpen: false`
          und mountet lazy, ein Hinweis darin waere zugeklappt und damit unsichtbar gewesen.
          Die erste Fassung hatte genau diesen Fehler; gefunden hat ihn die Probe.
          ⚠ Der LAUFENDE Monat taucht hier nie auf: ein Monat, der noch laeuft, kann keinen
          Abschluss haben (`ermittleFehlendeMonate` endet am Vormonat von heute). */}
      {(offenerAbschluss || rows.length === 0) && (
        <Alert type="info">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <span>
              {offenerAbschluss
                ? <>Für <strong>{MONAT_NAMEN[offenerAbschluss.monat]} {offenerAbschluss.jahr}</strong> fehlt noch der Monatsabschluss. Die <strong>Tageswerte</strong> sind davon unberührt — die <strong>Monatswerte</strong> gibt es erst mit ihm.</>
                : <>Für diese Anlage ist noch kein Monat abgeschlossen. Die <strong>Tageswerte</strong> sind davon unberührt — die <strong>Monatswerte</strong> gibt es erst mit einem Abschluss.</>}
            </span>
            <a
              href="#/einstellungen/daten"
              className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-primary-600 text-white hover:bg-primary-700 transition-colors whitespace-nowrap"
            >
              <CalendarClock className="h-3.5 w-3.5" />
              Abschluss starten
            </a>
          </div>
        </Alert>
      )}
      <BlockShell key="werkbank" persistKey={SICHT_KEY} bloecke={bloecke} sortierbar />
      <ParkFuss />
    </div>
  )
}

const keyOf = (iso: string) => { const [y, m, d] = iso.split('-').map(Number); return y * 10000 + m * 100 + d }
/** Tage in [von..bis] inklusiv. */
function tageInklusiv(von: string, bis: string): number {
  const [ay, am, ad] = von.split('-').map(Number)
  const [by, bm, bd] = bis.split('-').map(Number)
  return Math.round((Date.UTC(by, bm - 1, bd) - Date.UTC(ay, am - 1, ad)) / 86400000) + 1
}
/** ISO um `delta` Jahre verschieben, 29.2. aufs Monatsende geklemmt. */
function shiftJahr(iso: string, delta: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const ny = y + delta
  return `${ny}-${pad(m)}-${pad(Math.min(d, letzterTag(ny, m)))}`
}

type VglAlign = 'position' | 'kalender'
interface VglKonfig { von: string; bis: string; align: VglAlign; vor?: (iso: string) => string }

/**
 * Vergleichs-Konfiguration aus Modus + primärem Zeitraum + Vergleichsjahr (Gernot
 * 2026-06-27). Das Vergleichsfenster ist IMMER gleich lang wie der Primärbereich:
 *  • vorperiode — die gleich langen Tage direkt davor → **Positions-Ausrichtung**.
 *  • periodeImJahr — derselbe Spann ins Jahr `jahr` verschoben → **Kalender-Ausrichtung**
 *    (`vor()` bildet eine Vergleichszeile vorwärts auf ihren Primärtag ab).
 */
export function tagVergleich(
  modus: TagVergleichModus, von: string, bis: string, jahr: number,
): VglKonfig | null {
  if (!von || !bis) return null
  if (modus === 'vorperiode') {
    const cBisP = addTage(von, -1)
    return { von: addTage(cBisP, -(tageInklusiv(von, bis) - 1)), bis: cBisP, align: 'position' }
  }
  // periodeImJahr: Primärbereich um (jahr − Primär-Jahr) verschieben.
  const delta = jahr - Number(von.slice(0, 4))
  if (delta === 0) return null  // selbes Jahr = kein sinnvoller Vergleich
  return { von: shiftJahr(von, delta), bis: shiftJahr(bis, delta), align: 'kalender', vor: (iso) => shiftJahr(iso, -delta) }
}

/**
 * Re-Keying der Tageszeilen für die Vergleichs-Ausrichtung (s. {@link tagVergleich}).
 * Positions-Ausrichtung: chronologischer Index als Match-Key (Zeile i ↔ i). Kalender:
 * Primär behält den Datum-Key, Vergleich wird vorwärts auf den Primärtag abgebildet.
 */
export function richteAus(prim: WerteZeile[], comp: WerteZeile[] | null, vgl: VglKonfig | null): {
  primZeilen: WerteZeile[]; vglZeilen: WerteZeile[] | null
} {
  if (!vgl || !comp) return { primZeilen: prim, vglZeilen: comp }
  if (vgl.align === 'position') {
    return {
      primZeilen: [...prim].sort((a, b) => a.sortKey - b.sortKey).map((z, i) => ({ ...z, vergleichKey: i })),
      vglZeilen: [...comp].sort((a, b) => a.sortKey - b.sortKey).map((z, i) => ({ ...z, vergleichKey: i })),
    }
  }
  return {
    primZeilen: prim.map((z) => ({ ...z, vergleichKey: z.sortKey })),
    vglZeilen: comp.map((z) => ({ ...z, vergleichKey: vgl.vor ? keyOf(vgl.vor(z.id)) : z.sortKey })),
  }
}

/** Tages-Block: lazy (mountet erst beim Aufklappen) → lädt nur dann die Tageswerte. */
function EnergieprofilBlock({
  anlageId, von, bis, onRange, vglModus, onVglModus, vglJahr, onVglJahr, jahre, anker, anlagenname, minJahr, maxJahr,
}: {
  anlageId: number
  von: string; bis: string
  onRange: (von: string, bis: string) => void
  vglModus: TagVergleichModus
  onVglModus: (m: TagVergleichModus) => void
  vglJahr: number
  onVglJahr: (j: number) => void
  jahre: number[]
  anker: { jahr: number; monat: number } | null
  anlagenname?: string
  minJahr: number
  maxJahr: number
}) {
  const vgl = useMemo(
    () => (von && bis ? tagVergleich(vglModus, von, bis, vglJahr) : null),
    [von, bis, vglModus, vglJahr],
  )
  const { rows, vorjahrRows, loading, error } = useTagesWerte(anlageId, von, bis, vgl?.von ?? null, vgl?.bis ?? null)
  const { primZeilen, vglZeilen } = useMemo(
    () => richteAus(rows.map(tagesZeile), vorjahrRows ? vorjahrRows.map(tagesZeile) : null, vgl),
    [rows, vorjahrRows, vgl],
  )

  // Spalten je PV-String / Balkonkraftwerk (#350, Rainer). Die Regel — ab zwei
  // Erzeugern, nur was im Zeitraum existierte, fehlende Messung benennen — liegt
  // in `lib/erzeugerSpalten` und gilt genauso für die Serien in Cockpit → Tag.
  const { investitionen } = useInvestitionen(anlageId)
  const erzeuger = useMemo(
    () => baueErzeugerSpalten(rows, investitionen, von, bis),
    [rows, investitionen, von, bis],
  )
  // #377 — dieselbe Regel wie im Monatsblock: Spalte nur, wo ein Stand vorliegt.
  const zaehlerSpalten = useMemo(
    () => baueZaehlerSpalten(investitionen, zaehlerMitStand(rows)),
    [investitionen, rows],
  )

  // Primär-Schnellwahl: füllt nur von–bis (Gernot 2026-06-27). Vormonat = Monat vor dem Anker.
  const vm = anker ? (anker.monat === 1 ? { jahr: anker.jahr - 1, monat: 12 } : { jahr: anker.jahr, monat: anker.monat - 1 }) : null
  const monatRange = (j: number, m: number): [string, string] => [`${j}-${pad(m)}-01`, `${j}-${pad(m)}-${pad(letzterTag(j, m))}`]
  // N-368: Der Chip hiess FEST „Aktueller Monat" und lieferte den Anker-Monat — genau
  // die Zusage, die der Melder eingefordert hat. Mit dem Tages-Anker ist er im Regelfall
  // wirklich der laufende; war eedc ein paar Tage aus, ist er es nicht, und dann sagt
  // die Beschriftung, welcher Monat gemeint ist, statt einen falschen zu behaupten.
  const heuteJetzt = new Date()
  const ankerIstLaufend = !!anker && anker.jahr === heuteJetzt.getFullYear() && anker.monat === heuteJetzt.getMonth() + 1
  const chips: ZeitChip[] = anker ? [
    { label: ankerIstLaufend ? 'Aktueller Monat' : `${MONAT_KURZ[anker.monat]} ${anker.jahr}`, range: () => monatRange(anker.jahr, anker.monat), aktiv: von === `${anker.jahr}-${pad(anker.monat)}-01` },
    ...(vm ? [{ label: 'Vormonat', range: (): [string, string] => monatRange(vm.jahr, vm.monat), aktiv: von === `${vm.jahr}-${pad(vm.monat)}-01` }] : []),
  ] : []

  // Vergleichsjahr-Optionen = Datenjahre (+ aktuelle Wahl), absteigend.
  const jahrOptionen = Array.from(new Set([...jahre, vglJahr].filter((j) => j > 0))).sort((a, b) => b - a)

  return (
    <div className="space-y-3">
      <WerkbankZeitraum
        modus="tag" von={von} bis={bis} onRange={onRange} chips={chips}
        // D12-8: Tages-Grenzen aus dem Datenjahr-Bereich (1. Jan – 31. Dez).
        minDatum={`${minJahr}-01-01`} maxDatum={`${maxJahr}-12-31`}
        vergleichSlot={
          <VergleichLeisteTag
            modus={vglModus} onModus={onVglModus}
            jahr={vglJahr} onJahr={onVglJahr} jahre={jahrOptionen}
          />
        }
      />
      {loading && rows.length === 0 ? (
        // Spinner nur beim Erst-Load; bei Zeitraum-/Vergleichswechsel bleibt die
        // bestehende Tabelle stehen und aktualisiert sich in-place (detLAN D7-6).
        <TabellenSkeleton label="Lade Tageswerte…" />
      ) : error ? (
        // B8-Fehler-Baustein (S15). Implizites Retry: Zeitraum-/Vergleichswechsel in der
        // stehenden Leiste re-triggert den Fetch; useTagesWerte hat kein explizites reload.
        <FehlerZustand text={error} />
      ) : (
        <Parkbar id="tabelle:energieprofile" titel="Tageswerte">
          {/* Was es gibt, aber nicht gemessen wird — sonst sucht man die Spalte
              seines Dachs vergeblich (#350). Steht über der Tabelle, weil die
              Spaltenwahl darüber getroffen wird. */}
          {erzeuger.ohneMessung.length > 0 && (
            <div className="mb-2 space-y-0.5">
              <GeraeteHinweis
                namen={erzeuger.ohneMessung.map((i) => i.bezeichnung)}
                label={ERZEUGER_OHNE_SENSOR_LABEL}
                minAnzahl={1}
              />
              <p className="text-xs text-gray-400 dark:text-gray-500 pl-5">{ERZEUGER_OHNE_SENSOR_HINWEIS}</p>
            </div>
          )}
          <WerteTabelle
            rows={primZeilen}
            vorjahrRows={vglZeilen}
            granularitaet="tag"
            zusatzMetriken={[...erzeuger.metriken, ...zaehlerSpalten]}
            // R20-1a: bei „Periode im Jahr" das Primär-Jahr als Spalten-Label; bei
            // „Vorperiode" neutral „Aktuell" (WerteTabelle-Default) — beide Spalten klar.
            jahrLabel={vglModus === 'periodeImJahr' ? von.slice(0, 4) : undefined}
            vergleichLabel={vgl ? vglLabel(vglModus, vglJahr) : null}
            vergleichDefaultAn={!!vgl}
            scope={SCOPE} defaultSpalten={DEFAULT_SPALTEN}
            csvDateiname={`werte_tag_${anlagenname ?? 'export'}.csv`}
          />
        </Parkbar>
      )}
    </div>
  )
}
