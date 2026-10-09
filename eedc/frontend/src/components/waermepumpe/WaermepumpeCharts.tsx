/**
 * Geteilte Wärmepumpen-Charts (heute allein vom IA-v4-Hub genutzt; die V3-Seite
 * `WaermepumpeDashboard` ist mit dem V4-Flip entfallen — F-WK10-B3, 18.09.2026):
 * - {@link WaermepumpeMonatsverlauf}: Wärmeerzeugung/Monat (Heizung+Warmwasser, Area)
 * - {@link WaermepumpeKostenvergleich}: WP vs. Gas/Öl (Bar) + Ersparnis
 * - {@link WaermepumpeMonatsTabelle}: Strom · Heizung · Warmwasser · JAZ je Monat
 * Eine Code-Wahrheit für alle Leser dieser Charts.
 */
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area,
} from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { ChartLegende, Table, TableHead, TableBody } from '../ui'
import { ZELLE, KOPF_ZELLE } from '../ui/tabelleMasse'
import { MONAT_KURZ, CHART_COLORS, GELD_COLORS, GELD_TEXT_CLASS, CHART_HOVER_CURSOR, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'
import { useLegendenToggle, useSchmaleAchse } from '../../hooks'
import type { WaermepumpeDashboardResponse, WpMonatsWert } from '../../api/investitionen'

type Zusammenfassung = WaermepumpeDashboardResponse['zusammenfassung']

/** Monatszeilen des Wärme-Verlaufs aus der bewerteten Monatsreihe (N-643).
 *
 * Bis 4.1.3 las der Verlauf `heizenergie_kwh`/`warmwasser_kwh` roh: ein gemeinsamer
 * Wärmezähler (`waerme_kwh`, M05: 648 kWh) und die Heizwärme eines Klimageräts aus den
 * Betriebsart-Zählern (N-398, M06: 54 kWh) standen als 0 da, während die Kacheln darüber
 * dieselbe Wärme zählten. Jetzt kommen alle drei Größen aus der Faltung der Kopfzahlen
 * (`monatsreihe`); `waerme` ist die Wärme gesamt (Gesamtwert vor Summanden, D1).
 */
export function prepWpMonate(monatsreihe: WpMonatsWert[], hatWarmwasserAchse = true) {
  return monatsreihe.map((m) => ({
    name: `${MONAT_KURZ[m.monat]} ${m.jahr.toString().slice(2)}`,
    heizung: m.heizung_kwh,
    warmwasser: hatWarmwasserAchse ? m.warmwasser_kwh : 0,
    waerme: m.waerme_kwh,
  }))
}

/** Wärmeerzeugung pro Monat (Heizung + Warmwasser gestapelt; ohne Warmwasser-Achse EINE Fläche „Wärme").
 *
 * N-379 / SOLL §3.3/S2: `hatWarmwasserAchse=false` nimmt die zweite Fläche samt
 * Legendeneintrag heraus — eine Split-Klimaanlage hat keinen Warmwasserkreis
 * (N-304), und genau dieser Chart zeigte dietmar1968 eine blaue Warmwasser-Fläche
 * über seine ganze Kühlsaison (T89667 #295). Default `true`: ohne die Angabe
 * bleibt alles, wie es war.
 */
export function WaermepumpeMonatsverlauf(
  { monatsreihe, hatWarmwasserAchse = true }: {
    monatsreihe: WpMonatsWert[]; hatWarmwasserAchse?: boolean
  },
) {
  const schmal = useSchmaleAchse()
  const legende = useLegendenToggle()
  const data = prepWpMonate(monatsreihe, hatWarmwasserAchse)
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: ACHSEN_MARGIN_TOP }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis dataKey="name" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
          <YAxis label={achsenEinheit('kWh')} tickFormatter={achsenTick} {...yAchse(schmal)} />
          <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="kWh" />} />
          <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
          {/* B3/N-391: Ohne Warmwasser-Achse trägt diese Fläche die GESAMTE Wärme
              des Geräts — ob nur Heizung (8ear) oder Heizung und Warmwasser durch
              einen Zähler (Lage B) weiß eedc nicht. „Wärme" ist in beiden Lagen
              wahr, „Heizung" nur in einer (SOLL §3.3/S2). N-643: sie zeichnet
              deshalb die Wärme gesamt (`waerme`), nicht die Heizwärme — bei einem
              gemeinsamen Wärmezähler ist die Heizwärme 0. */}
          {hatWarmwasserAchse ? (
            <>
              <Area type="monotone" dataKey="heizung" stackId="1" fill={CHART_COLORS.wpWaerme} stroke={CHART_COLORS.wpWaerme} name="Heizung" hide={legende.istVersteckt('heizung')} />
              <Area type="monotone" dataKey="warmwasser" stackId="1" fill={CHART_COLORS.wpWarmwasser} stroke={CHART_COLORS.wpWarmwasser} name="Warmwasser" hide={legende.istVersteckt('warmwasser')} />
            </>
          ) : (
            <Area type="monotone" dataKey="waerme" stackId="1" fill={CHART_COLORS.wpWaerme} stroke={CHART_COLORS.wpWaerme} name="Wärme" hide={legende.istVersteckt('waerme')} />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/**
 * F-42: Gibt es überhaupt eine ersetzte Heizung, gegen die verglichen werden kann?
 *
 * Backend-SoT ist `berechne_wp_ersparnis` (Flag `bewertbar`); hierher kommt das
 * Ergebnis als `null` statt als 0 an. Der Block darf nicht einfach verschwinden —
 * die Stromkosten sind eine echte, gepflegte Zahl und gehören weiter gezeigt.
 * Was entfällt, ist der **Vergleich**.
 */
export const wpHatVergleich = (z: Zusammenfassung) => z.ersparnis_euro != null

/** Kostenvergleich WP vs. Gas/Öl (horizontale Balken) + Ersparnis-Zeile. */
export function WaermepumpeKostenvergleich({ zusammenfassung: z }: { zusammenfassung: Zusammenfassung }) {
  // F-42: Ohne ersetzte Heizung hat der Balken „Gas/Öl" keinen Gegenstand — vorher
  // stand hier ein Vergleich gegen 0 € und darunter „Ersparnis: 0,00 €", während
  // dieselbe Anlage in Cockpit → Jahr „—" und in Auswertungen → ROI „nicht
  // bewertet" sagte. Statt den Block zu unterdrücken, zeigt er das, was gilt:
  // die reinen Stromkosten des Geräts.
  if (!wpHatVergleich(z)) {
    return (
      <div className="space-y-2 py-4 text-center">
        <p className="text-sm text-gray-500 dark:text-gray-400">Stromkosten des Geräts</p>
        <p className={`text-2xl font-semibold ${GELD_TEXT_CLASS.kosten}`}>
          {fmtZahl(z.wp_kosten_euro, 2)} €
        </p>
        <p className="mx-auto max-w-md text-xs text-gray-500 dark:text-gray-400">
          Für dieses Gerät ist „Nichts ersetzt (Neubau)" hinterlegt oder es liegt keine
          gemessene Wärmemenge vor — es gibt also keine frühere Heizung, gegen die sich
          eine Ersparnis rechnen ließe. Stromverbrauch, PV-Anteil und Kosten werden
          unverändert ausgewertet.
        </p>
      </div>
    )
  }
  const data = [
    { name: 'Wärmepumpe', value: z.wp_kosten_euro, fill: GELD_COLORS.ersparnis },
    // #411: „Gas/Öl" ließ den dritten wählbaren Träger aus — die
    // Strom-Direktheizung (`alter_energietraeger: 'strom'`, η 1,0).
    { name: 'Alternative', value: z.alte_heizung_kosten_euro, fill: GELD_COLORS.kosten },
  ]
  return (
    <div className="space-y-2">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis type="number" tickFormatter={(v) => `${fmtZahl(v, 0)} €`} tick={{ fontSize: 10 }} /* achsen-allow: Wert-Achse waagerecht, Einheit/Format pro Tick (de-DE) */ />
            <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 10 }} /* achsen-allow: Kategorie-Namen (WP vs. Gas/Öl) */ />
            <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="€" decimals={2} />} />
            <Bar dataKey="value" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="text-center">
        <span className={`text-lg font-semibold ${GELD_TEXT_CLASS.ersparnis}`}>
          Ersparnis: {fmtZahl(z.ersparnis_euro, 2)} €
        </span>
        {/* B3/H-2 + F12 (SOLL §6, 05.09.2026): Der Vorbehalt steht SICHTBAR unter
            der Zahl — eine Ersparnis aus geschätzter Wärme oder mit der Wärme eines
            zweiten Erzeugers darf nicht aussehen wie eine gemessene. Der Satz kommt
            fertig aus dem Layer (`ersparnis_vorbehalt`), damit Cockpit und PDF
            dieselben Worte tragen. */}
        {z.ersparnis_vorbehalt && (
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{z.ersparnis_vorbehalt}</p>
        )}
      </div>
    </div>
  )
}

/** Ein Eintrag aus `zusammenfassung.jaz_je_monat` — die Arbeitszahl je Monat aus dem Layer. */
export interface JazMonat {
  jahr: number
  monat: number
  wert: number | null
  grund: string | null
  /** Q und E, mit denen der Layer die Zahl **tatsächlich** gebildet hat (N-370).
   *  `nenner_kwh` ist NICHT der Stromverbrauch der Zeile — der funktionsfremde
   *  Anteil ist abgezogen. Beide `null`, wo es keine Kennzahl gibt. */
  zaehler_kwh?: number | null
  nenner_kwh?: number | null
  /** B3/H-1b: Stromverbrauch des Monats nach dem SoT — bei getrennter Strommessung
   *  steht er nicht in der Rohspalte. Fehlt er (ältere Antwort), gilt die Rohspalte. */
  strom_kwh?: number | null
}

/** kWh in dieser Tabelle: ganzzahlig, wie die drei Mengen-Spalten daneben.
 *
 * ⭐ **Und der Vergleich läuft auf DERSELBEN Ebene** (N-370): Ob die Herleitung
 * gezeigt wird, entscheidet sich an den **gerundeten** Werten, nicht an den rohen.
 * Sonst erschiene sie bei einem funktionsfremden Anteil von 0,4 kWh mit der
 * Aussage „316 ÷ 316" — eine Rechnung, die sichtbar dasselbe sagt wie die Zeile
 * und den Leser nur fragen lässt, was er übersehen hat.
 *
 * ⚠ Die Division geht dadurch nicht immer auf die zweite Stelle auf (210 ÷ 95
 * ergibt 2,21 neben einer JAZ von 2,20). Das ist der bewusste Tausch: Die
 * Herleitung soll sich gegen **die Zeile** lesen lassen, in der sie steht.
 * `fa270c6f` wählte auf der Kachel eine Nachkommastelle — dort steht sie allein,
 * hier neben drei ganzzahligen Spalten. */
const rundKwh = (x: number) => Math.round(x)

/** Monatsdaten-Tabelle: Strom · Heizung · Warmwasser · JAZ je Monat.
 *
 * ⛔ **Die JAZ-Spalte rechnet NICHT selbst** (N-369, 02.09.2026). Bis dahin stand
 * hier `(heiz + ww) / strom` — eine rohe Division auf den Rohfeldern, und damit
 * genau das, was ADR-002/**P12** seit dem 02.09. verbietet. Sie wusste von nichts:
 * kein Abzug des funktionsfremden Stroms (Kühlen · Lüften · Entfeuchten, W-14/E4),
 * keine Sperre bei aus `Strom × JAZ` **gerechneter** Wärme (dort gäbe die Division
 * die gepflegte JAZ zurück — eine Zahl, die nichts misst), keine Anwender-Angabe
 * `abgrenzung`. Und ohne Strom stand dort **`0,00`** statt „—": eine Null behauptet
 * „gemessen, und es kam nichts heraus". Bei einer Split-Klimaanlage — Strom ja,
 * Wärme bauartbedingt nein — war das der Regelfall.
 *
 * ⚠ **Gefunden wurde es NICHT vom Wächter.** `check:cop-roh` sucht
 * `<waerme> / <strom>` über Namen; hier steht im Zähler eine **Klammer-Summe**
 * (`heiz + ww`), und die ist auf dieser Fläche die Standard-Schreibweise für Wärme.
 * Der Wächter kennt das Muster seit N-369.
 *
 * Die Werte kommen jetzt aus `zusammenfassung.jaz_je_monat` — dieselbe Quelle, die
 * der Status-Strip und der Monatsvergleich desselben Geräts lesen. Damit nennt der
 * Hub für einen Monat nicht mehr zwei verschiedene Arbeitszahlen (die **W-15**-Klasse).
 */
export function WaermepumpeMonatsTabelle(
  { monatsreihe, jazJeMonat, hatWarmwasserAchse = true }: {
    /** N-643: die bewertete Monatsreihe (`monatsreihe`) — dieselbe Faltung wie die Kacheln. */
    monatsreihe: WpMonatsWert[]
    jazJeMonat?: JazMonat[]
    /** N-379 / SOLL §3.3/S2: Hat das Gerät die Warmwasser-Achse überhaupt? Eine
     *  Split-Klimaanlage hat keinen Warmwasserkreis (N-304) — dietmar1968 sah
     *  dort eine Spalte „Warmwasser (kWh)" mit 889 (T89667 #295). Default `true`,
     *  damit jeder Aufrufer ohne die Angabe das Bisherige zeigt. */
    hatWarmwasserAchse?: boolean
  },
) {
  // Nachschlagen je (Jahr, Monat) — die Listen sind unabhängig sortiert.
  const jazKey = (j: number, m: number) => j * 100 + m
  const jazMap = new Map((jazJeMonat ?? []).map((x) => [jazKey(x.jahr, x.monat), x]))

  // N-370: Zeilen vorab bilden, damit die Fußnote weiß, ob überhaupt eine
  // Herleitung vorkommt — sie soll nicht unter einer Tabelle stehen, in der
  // jede Zeile ohne sie aufgeht.
  const zeilen = monatsreihe.map((md) => {
    // B3/H-1b → N-643: Strom, Heizung und Warmwasser kommen aus der Monatsreihe —
    // derselben Faltung wie die Kacheln und die JAZ (`get_wp_strom_kwh`, Lesetüren
    // `heizwaerme_kwh`/`get_wp_warmwasser_kwh`). Die Rohspalte war bei getrennter
    // Strommessung leer (0 neben einer richtigen Arbeitszahl), die Heizwärme bei
    // einem gemeinsamen Wärmezähler oder aus Betriebsart-Zählern ebenso.
    const strom = md.strom_kwh
    // B3/N-391: ohne Warmwasser-Achse heißt die Spalte „Wärme" und trägt die Wärme
    // gesamt — bei einem gemeinsamen Wärmezähler ist die Heizwärme 0 (N-643).
    const heiz = hatWarmwasserAchse ? md.heizung_kwh : md.waerme_kwh
    // N-379: an einem Gerät ohne Warmwasserkreis liest auch die Zeile nichts —
    // sonst stünde die Zahl in der Herleitungsprobe darunter wieder im Zähler.
    const ww = hatWarmwasserAchse ? md.warmwasser_kwh : 0
    // N-369: gelesen, nicht gerechnet. Fehlt der Eintrag (älterer Monat
    // ohne Layer-Antwort), steht „—" — nie eine erfundene Zahl.
    const jaz = jazMap.get(jazKey(md.jahr, md.monat))
    // ⭐ **A6/N-370 — die Herleitung steht nur da, wo die Zeile sonst nicht aufgeht.**
    // Stimmen Q und E mit den Spalten daneben überein, SIND die Nachbarspalten die
    // eingesetzten Werte; eine zweite Zeile mit denselben Zahlen wäre Rauschen.
    // Weichen sie ab, kam bis zum 02.09.2026 eine richtige Zahl neben Rohwerten zu
    // stehen, aus denen sie sich nicht nachrechnen ließ (Strom 316 · Wärme 210 ·
    // JAZ 2,20 — und 210 ÷ 316 ergibt 0,66). Vorher war es konsistent und falsch,
    // seit N-369 richtig und unerklärlich; genau das ist die schlechtere Lage.
    //
    // ⛔ Die Zahlen kommen aus dem Layer und werden hier NICHT nachgerechnet
    // (W-3-Klasse, Präzedenz `fa270c6f`): Der Nenner ist der Strom OHNE den
    // funktionsfremden Anteil (Kühlen · Lüften · Entfeuchten). `(heiz + ww) / strom`
    // ergäbe bei jeder Anlage mit erfasstem Betriebsmodus eine Rechnung, die nicht
    // auf die Zahl daneben führt — dieselbe Bauform, die diese Datei mit N-369
    // gerade verlassen hat.
    //
    // Die bedingte Anzeige ist keine neue Erfindung, sondern **W-17b** auf
    // derselben Fläche: `WaermepumpeModusSplit.tsx` nennt die Grundmenge der
    // Aufteilung genau dann, wenn sie vom Gesamtstrom abweicht.
    const herleitung =
      jaz?.wert != null && jaz.zaehler_kwh != null && jaz.nenner_kwh != null
      && (rundKwh(jaz.zaehler_kwh) !== rundKwh(heiz + ww)
          || rundKwh(jaz.nenner_kwh) !== rundKwh(strom))
        ? `${fmtZahl(jaz.zaehler_kwh, 0)} ÷ ${fmtZahl(jaz.nenner_kwh, 0)} kWh`
        : null
    return { md, strom, heiz, ww, jaz, herleitung }
  })
  const zeigtHerleitung = zeilen.some((z) => z.herleitung !== null)
  // N-374: die Gründe zu einem gesperrten „—", SICHTBAR statt nur im `title=`.
  // Dieselbe Bauform wie die Herleitung darunter und aus demselben Grund — „ein
  // Tooltip ist auf dem Telefon keine Auskunft" (`waermepumpe_kennzahl.
  // Arbeitszahl.grund`). Einmal unter der Tabelle statt in jeder Zeile: über zwölf
  // Monate steht meist derselbe Grund, weil er aus der Anlagenkonfiguration folgt.
  const sperrGruende = [...new Set(
    zeilen.map((z) => (z.jaz?.wert == null ? z.jaz?.grund : null)).filter((g): g is string => !!g),
  )]

  return (
    <>
    <Table>
      <TableHead>
        <tr className="border-b border-gray-200 dark:border-gray-700">
          <th className={`${KOPF_ZELLE} text-left`}>Monat</th>
          <th className={`${KOPF_ZELLE} text-right`}>Strom (kWh)</th>
          {/* B3/N-391: ohne Warmwasser-Achse ist das die ganze Wärme, nicht „Heizung" (S2). */}
          <th className={`${KOPF_ZELLE} text-right`}>{hatWarmwasserAchse ? 'Heizung' : 'Wärme'} (kWh)</th>
          {hatWarmwasserAchse && (
            <th className={`${KOPF_ZELLE} text-right`}>Warmwasser (kWh)</th>
          )}
          <th className={`${KOPF_ZELLE} text-right`}>JAZ</th>
        </tr>
      </TableHead>
      <TableBody>
        {zeilen.map(({ md, strom, heiz, ww, jaz, herleitung }) => (
          <tr key={`${md.jahr}-${md.monat}`} className="border-b border-gray-100 dark:border-gray-800">
            <td className={ZELLE}>{MONAT_KURZ[md.monat]} {md.jahr}</td>
            <td className={`${ZELLE} text-right`}>{fmtZahl(strom, 0)}</td>
            {/* Heizung = WP-Rot, Warmwasser = blau (= CHART_COLORS.wpWaerme/wpWarmwasser; Gernot 2026-06-25 nach detLAN). */}
            <td className={`${ZELLE} text-right text-red-600`}>{fmtZahl(heiz, 0)}</td>
            {hatWarmwasserAchse && (
              <td className={`${ZELLE} text-right text-blue-600`}>{fmtZahl(ww, 0)}</td>
            )}
            <td className={`${ZELLE} text-right text-orange-600`} title={jaz?.grund ?? undefined}>
              {jaz?.wert != null ? fmtZahl(jaz.wert, 2) : '—'}
              {herleitung && (
                <div className="text-xs font-normal text-gray-500 dark:text-gray-400">{herleitung}</div>
              )}
            </td>
          </tr>
        ))}
      </TableBody>
    </Table>
    {/* Die Erklärung zur Herleitung — **sichtbar, nicht im Tooltip**: „ein Tooltip
        ist auf dem Telefon keine Auskunft" (`waermepumpe_kennzahl.Arbeitszahl.grund`).
        Sie steht einmal unter der Tabelle statt in jeder Zelle, damit sie nicht mit
        der Fläche driftet — und nur, wenn oben überhaupt eine Herleitung vorkommt.
        ⚠ Bewusst OHNE Zuschreibung der konkreten Differenz: Der funktionsfremde
        Anteil ist der Regelfall, aber bei getrennter Strommessung liest die
        Strom-Spalte ein anderes Feld als der Layer (`get_wp_strom_kwh`) — ein Satz,
        der die Abweichung fest einer Ursache zuordnet, wäre dort eine Behauptung. */}
    {sperrGruende.length > 0 && (
      <ul className="mt-2 text-xs text-gray-500 dark:text-gray-400 space-y-0.5">
        {sperrGruende.map((g) => <li key={g}>Arbeitszahl nicht gebildet — {g}</li>)}
      </ul>
    )}
    {zeigtHerleitung && (
      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        Die Arbeitszahl wird mit dem Strom gebildet, der zur gemessenen Wärme gehört.
        Strom fürs Kühlen, Lüften oder Entfeuchten zählt nicht mit — deshalb kann ihr
        Nenner von dem Stromverbrauch abweichen, der in der Zeile steht. Wo beide
        übereinstimmen, steht keine gesonderte Rechnung.
      </p>
    )}
    </>
  )
}
