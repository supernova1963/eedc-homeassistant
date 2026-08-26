/**
 * Aufteilung des Stromverbrauchs nach Betriebsmodus (#263 K-2, S4 · Konzept §4).
 *
 * Eine Split-Klimaanlage heizt und kühlt über denselben Zähler. Wo eedc den
 * Betriebsmodus mitschreibt, kann es sagen, welcher Teil des Verbrauchs wohin
 * ging — hier steht diese Aufteilung, und **nur** hier ist sie eine eigene
 * Zahl. Sie ist eine **Teilmenge** des Gesamtverbrauchs und wird nirgends
 * aufaddiert (dieselbe Bauform wie `ladung_pv_kwh` bei der Wallbox).
 *
 * ⚠ **Ohne Modus-Signal erscheint dieser Block gar nicht** — statt mit Nullen.
 * Eine 0 hieße „hat nicht geheizt"; das weiß eedc ohne Sensor nicht
 * (ADR-002/P4, die N-258-Klasse, an der F-42 hing).
 */
import { fmtCalc } from '../ui'
import { VerteilungsBalken } from '../blocks'
import { ROLLEN_BG } from '../../lib'

/** Die Felder, die der Block braucht — Ausschnitt aus `WaermepumpeZusammenfassung`. */
export interface ModusSplitDaten {
  gesamt_stromverbrauch_kwh: number
  modus_strom_heizen_kwh?: number
  modus_strom_kuehlen_kwh?: number
  /** E4 (Konzept §2.3): nur aus **gemessenen** Betriebsart-Zählern. Ohne
   *  solchen Zähler 0 — dann stecken sie weiterhin in `nicht_aufgeteilt`. */
  modus_strom_lueften_kwh?: number
  modus_strom_entfeuchten_kwh?: number
  modus_nicht_aufgeteilt_kwh?: number
  modus_abdeckung_h?: number
  /** **W-17b** — die Grundmenge der Aufteilung: der Strom der Monate MIT
   *  Split, nicht der Gesamtstrom des Geräts. Fehlt sie (Altbestand), gilt
   *  weiterhin `gesamt_stromverbrauch_kwh` als Bezug. */
  modus_strom_bezug_kwh?: number
  /** #263: Aufteilung ist GEMESSEN (Betriebsart-Zähler) statt abgeleitet. */
  modus_gemessen?: boolean
  gesamt_heizenergie_kwh?: number
  waerme_abgeleitet?: boolean
  waerme_abgeleitet_faktor?: number | null
}

/** Hat dieses Gerät überhaupt eine Aufteilung? Auch der Hub-Block fragt das. */
export function hatModusSplit(z: ModusSplitDaten | undefined | null): boolean {
  if (!z) return false
  // #263 — zwei Wege hierher: abgeleitet aus dem Betriebsmodus (dann gibt es
  // Abdeckungs-Stunden) oder gemessen aus Betriebsart-Zählern (dann gibt es
  // keine — ein Zähler zählt kWh, keine Stunden mit Signal). Nur die Abdeckung
  // zu prüfen hieße, eine gemessene Aufteilung nirgends zu zeigen.
  if (z.modus_gemessen) return true
  return z.modus_abdeckung_h != null && z.modus_abdeckung_h > 0
}

const fmt = (v: number | null | undefined, dec = 0) => fmtCalc(v, dec, '—')

function anteil(teil: number | undefined, gesamt: number): string {
  if (teil == null || !gesamt) return ''
  return ` (${fmtCalc((teil / gesamt) * 100, 0, '—')} %)`
}

export function WaermepumpeModusSplit({ zusammenfassung: z }: { zusammenfassung: ModusSplitDaten }) {
  // W-17b: **Der Nenner der Prozente ist die Grundmenge, nicht der
  // Gesamtstrom.** Die Teilmengen entstehen nur aus Monaten mit Split; gegen
  // den Gesamtstrom gerechnet summierten sich „Heizen + Kühlen + nicht
  // aufgeteilt" deshalb auf weniger als 100 % — sichtbar falsch, ohne dass
  // irgendwo stand, worauf sich die Zahlen beziehen.
  //
  // ⚠ Fallback auf den Gesamtstrom, wenn die Grundmenge fehlt: eine ältere
  // Antwort ohne das Feld verhält sich damit wie bisher (bitgleich), statt
  // durch 0 zu teilen.
  const bezug = z.modus_strom_bezug_kwh
  const gesamt = (bezug != null && bezug > 0 ? bezug : z.gesamt_stromverbrauch_kwh) || 0
  const heizen = z.modus_strom_heizen_kwh
  const kuehlen = z.modus_strom_kuehlen_kwh
  const lueften = z.modus_strom_lueften_kwh
  const entfeuchten = z.modus_strom_entfeuchten_kwh
  const rest = z.modus_nicht_aufgeteilt_kwh

  // E4: Lüften und Entfeuchten erscheinen **nur, wenn gemessen**. Ein Segment
  // mit 0 kWh an jeder Wärmepumpe wäre eine Zeile, die für fast jeden Anwender
  // nichts sagt — und der SOLL-Satz endet ausdrücklich mit „Wer sie nicht
  // erfasst, sieht sie nicht."
  const segmente = [
    { label: 'Heizen', wert: heizen ?? 0, farbe: ROLLEN_BG.heizung },
    { label: 'Kühlen', wert: kuehlen ?? 0, farbe: ROLLEN_BG.kuehlung },
    ...(lueften ? [{ label: 'Lüften', wert: lueften, farbe: ROLLEN_BG.lueftung }] : []),
    ...(entfeuchten
      ? [{ label: 'Entfeuchten', wert: entfeuchten, farbe: ROLLEN_BG.entfeuchtung }]
      : []),
    { label: 'Nicht aufgeteilt', wert: rest ?? 0, farbe: ROLLEN_BG.nicht_aufgeteilt },
  ]

  return (
    <div className="space-y-3">
      <VerteilungsBalken segmente={segmente} />

      <dl className="text-sm space-y-1">
        <div className="flex justify-between">
          <dt className="text-gray-600 dark:text-gray-400">Strom gesamt</dt>
          <dd className="font-medium">{fmt(gesamt)} kWh</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-gray-600 dark:text-gray-400">davon Heizen</dt>
          <dd>{fmt(heizen)} kWh{anteil(heizen, gesamt)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-gray-600 dark:text-gray-400">davon Kühlen</dt>
          <dd>{fmt(kuehlen)} kWh{anteil(kuehlen, gesamt)}</dd>
        </div>
        {lueften ? (
          <div className="flex justify-between">
            <dt className="text-gray-600 dark:text-gray-400">davon Lüften</dt>
            <dd>{fmt(lueften)} kWh{anteil(lueften, gesamt)}</dd>
          </div>
        ) : null}
        {entfeuchten ? (
          <div className="flex justify-between">
            <dt className="text-gray-600 dark:text-gray-400">davon Entfeuchten</dt>
            <dd>{fmt(entfeuchten)} kWh{anteil(entfeuchten, gesamt)}</dd>
          </div>
        ) : null}
        <div className="flex justify-between">
          <dt className="text-gray-600 dark:text-gray-400">nicht aufgeteilt</dt>
          <dd>{fmt(rest)} kWh{anteil(rest, gesamt)}</dd>
        </div>
        <div className="flex justify-between border-t border-gray-100 dark:border-gray-800 pt-1">
          {/* #263 — die Herkunft steht neben der Zahl. Ein Betriebsart-Zähler
              hat keine „Stunden mit Signal"; dort „0 Stunden" zu zeigen sähe
              aus wie ein Sensor-Ausfall. */}
          <dt className="text-gray-600 dark:text-gray-400">
            {z.modus_gemessen ? 'Herkunft' : 'Modus erfasst'}
          </dt>
          <dd>{z.modus_gemessen ? 'gemessen' : `${fmt(z.modus_abdeckung_h, 0)} Stunden`}</dd>
        </div>
        {/* W-17b: Die Aufteilung nennt ihre Grundmenge, sobald sie vom
            Gesamtstrom abweicht — sonst stünde sie stumm unter einer größeren
            Zahl. Stimmen beide überein, sagt die Zeile nichts Neues und
            entfällt. */}
        {bezug != null && Math.abs(bezug - (z.gesamt_stromverbrauch_kwh || 0)) > 0.05 ? (
          <div className="flex justify-between">
            <dt className="text-gray-600 dark:text-gray-400">aufgeteilte Menge</dt>
            <dd>{fmt(bezug)} von {fmt(z.gesamt_stromverbrauch_kwh)} kWh</dd>
          </div>
        ) : null}
      </dl>

      {/* Die Wärme steht hier nur, wenn sie abgeleitet ist — als Wert MIT
          Herkunft. Gemessene Wärme hat ihren Platz in der Wärme-Aufteilung
          und braucht hier keine zweite Anzeige. */}
      {z.waerme_abgeleitet && z.gesamt_heizenergie_kwh != null && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Heizwärme {fmt(z.gesamt_heizenergie_kwh)} kWh — <strong>abgeleitet</strong> aus
          dem Heiz-Strom
          {z.waerme_abgeleitet_faktor != null && <> × {fmtCalc(z.waerme_abgeleitet_faktor, 2, '—')}</>}
          , nicht gemessen. Deshalb steht bei der JAZ „—": aus einer gerechneten
          Wärme kommt wieder genau der Faktor heraus, mit dem sie gerechnet wurde.
        </p>
      )}

      {z.modus_gemessen && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Diese Aufteilung stammt aus <strong>zugeordneten Zählern je
          Betriebsart</strong> — sie hat Vorrang vor der Aufteilung, die eedc
          sonst aus dem Betriebsmodus ableitet.
        </p>
      )}

      <ModusSplitErklaerung />
    </div>
  )
}



/**
 * Was „Nicht aufgeteilt" bedeutet — der EINE Wortlaut für alle Sichten.
 *
 * ⚠ **Warum das eine eigene Komponente ist (N-327):** Denselben Balken zeigt
 * auch das Cockpit (Tag/Monat, `v4/KomponentenSektionen.tsx`), dort aber bis
 * zum 25.08.2026 **ohne** jede Erklärung. Zwei Melder haben am selben Tag
 * dasselbe gefragt — Klausnn (GitHub #263) sah „Nicht aufgeteilt 1 kWh · 100 %"
 * und hielt die Aufteilung für kaputt, dietmar1968 (Forum T89667 #194) sah
 * 74 % und wartete ab. Beide hatten recht mit dem, was sie sahen: Bei einem
 * Gerät, das überwiegend aus war, IST der Standby-Strom weder Heizen noch
 * Kühlen. Was fehlte, war der Grund neben der Zahl.
 *
 * Der Text steht deshalb genau einmal und wird von beiden Sichten gerendert —
 * ein zweiter Wortlaut daneben würde driften (Regel 0a: eine Komponenten-Klasse,
 * eine SoT-Komponente).
 */
export function ModusSplitErklaerung() {
  return (
    <p className="text-xs text-gray-500 dark:text-gray-400">
      „Nicht aufgeteilt" ist Standby und alles, was keiner erfassten Betriebsart
      zugeordnet werden konnte (Automatik ohne Rückmeldung) — dazu die Zeit, in
      der eedc keinen Modus mitlesen konnte. <strong>Lüften und Entfeuchten</strong>{' '}
      erscheinen als eigene Zeile, sobald du dafür einen Zähler zugeordnet hast;
      ohne Zähler stecken sie hier mit drin. Sie bekommen bewusst keine
      Arbeitszahl: Sie erzeugen keine Wärme, die sich messen ließe. Die
      Aufteilung entsteht nur für Zeiten mit laufender Datenanbindung;
      rückwirkend gibt es sie nicht.
    </p>
  )
}
