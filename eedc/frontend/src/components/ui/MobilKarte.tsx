/**
 * MobilKarte — die mobile Hälfte des Kanons „eine Datenliste, zwei Render-Pfade".
 *
 * Passt eine Tabelle unter `sm` nicht, kommt **nicht** ein Ersatztext an ihre
 * Stelle, sondern eine **Kartenliste derselben Daten**: Tabelle in
 * `hidden sm:block`, Karten in `sm:hidden`, eine Karte je Tabellenzeile
 * (Kopfzeile = Zeilenschlüssel + Leitwert, darunter ein `dl` mit den Spalten).
 * Regel und Begründung: `docs/drafts/KONZEPT-MOBILE.md` §M3, aus N-127; die
 * Grundregel dahinter ist M1 (Gernot, 2026-05-31): **nichts wird auf Mobile
 * unerreichbar, nur de-priorisiert.**
 *
 * ⭐ **Warum diese Datei existiert (N-149, Regel 0a Fall 2).** Das Muster war
 * viermal im Baum, dreimal von Hand nachgebaut und einmal als lokale Komponente
 * in `PrognoseVergleichTeile.tsx` — also vier Orte für eine Darstellungsregel,
 * ohne SoT. Die Karten sahen deshalb nicht gleich aus, und eine Änderung an der
 * Regel hätte vier Stellen gebraucht. Die lokale Fassung ist hierher gehoben,
 * die beiden Handnachbauten hängen daran.
 *
 * ⛔ **`TKonto.tsx` gehört NICHT dazu, und das ist gemessen, nicht vergessen.**
 * Es rendert unter `sm` keine Karten, sondern **drei Tabellen** (Soll/Haben als
 * gestapelte Gewinn-und-Verlust-Rechnung, `TKonto.tsx:427`). Es ist damit kein
 * Nachbau dieses Musters, sondern ein eigenes — es hier einzuhängen hieße, eine
 * vertraute Anzeige ohne Not umzubauen. `KONZEPT-MOBILE.md` §M3 hat es bis zum
 * 2026-08-29 als Kartenbeispiel geführt; die Zeile ist mit diesem Bau berichtigt.
 */

import React from 'react'

/** Eine Wertzeile der Karte = eine Spalte der Breitansicht. */
export interface MobilKarteZeile {
  label: React.ReactNode
  wert: React.ReactNode
  /** Farbklasse des **Labels** — dieselbe wie die seiner Tabellenspalte. */
  klasse?: string
  /** Farbklasse des **Werts** (z. B. Abweichung grün/rot). */
  wertKlasse?: string
  /**
   * Inline-Farbe des Werts für Paletten aus `lib/colors.ts`, die als Hex
   * vorliegen (`STRING_COLORS` je String/Modul) — dort gibt es keinen
   * Klassen-Zwilling je Index. Kein Verstoß gegen Regel 0a: die Farbe kommt
   * aus dem Farb-SoT, nur ihre Zustellung ist inline.
   */
  wertStil?: React.CSSProperties
  /** Zusatz hinter dem Wert (Δ, VJ, Band) — klein und grau. */
  zusatz?: React.ReactNode
}

export interface MobilKarteProps {
  /** Zeilenschlüssel — ReactNode, damit Farbpunkt/Icon mit hineinpassen. */
  titel: React.ReactNode
  /** Leitwert rechts im Kopf (Saldo, Badge). */
  kopfWert?: React.ReactNode
  /** Kleine Zeile unter dem Kopf (Zuordnung, Hinweis). */
  unterzeile?: React.ReactNode
  zeilen: MobilKarteZeile[]
  /**
   * Spaltenzahl des Wertblocks. **1 und 2** setzen Label und Wert
   * nebeneinander (`justify-between`), **3** stapelt sie — bei drei Spalten
   * ist nebeneinander auf einem Telefon nicht mehr lesbar. Die Vorgabe ist
   * **1**; beide anderen Werte sind aus den migrierten Bestandsansichten
   * belegt (2 = PV-Strings, 3 = Komponenten-Finanzen).
   */
  spalten?: 1 | 2 | 3
  /**
   * Dichte Variante: `text-xs` statt `text-sm`, engeres Polster. Bewusst ein
   * eigenes Merkmal und nicht an `spalten` gekoppelt — sonst wäre eine dritte
   * Spalte in normaler Schrift nicht mehr möglich.
   */
  dicht?: boolean
  /** Zusätzliche Klassen am Rahmen (Hervorhebung der Summenkarte). */
  rahmenKlasse?: string
  /** `title`-Attribut des Rahmens (Tooltip der Tabellenzeile). */
  tooltip?: string
}

/** Kartenliste unter `sm` — der Container um die Karten einer Tabelle. */
export function MobilKarten({ children }: { children: React.ReactNode }) {
  return <div className="sm:hidden space-y-2">{children}</div>
}

/** Die Tabelle ab `sm` — die zweite Hälfte desselben Kanons. */
export function TabelleAbSm({ children }: { children: React.ReactNode }) {
  return <div className="hidden sm:block">{children}</div>
}

/** Eine Karte = eine Tabellenzeile der Breitansicht, hochkant gelesen. */
export function MobilKarte({
  titel,
  kopfWert,
  unterzeile,
  zeilen,
  spalten = 1,
  dicht = false,
  rahmenKlasse = '',
  tooltip,
}: MobilKarteProps) {
  const gestapelt = spalten === 3
  const wertBlock =
    spalten === 1
      ? 'space-y-1'
      : spalten === 2
        ? 'grid grid-cols-2 gap-x-4 gap-y-1'
        : 'grid grid-cols-3 gap-1'

  return (
    <div
      className={`rounded-lg border border-gray-200 dark:border-gray-700 ${dicht ? 'p-2.5' : 'p-3'} ${rahmenKlasse}`}
      title={tooltip}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-gray-900 dark:text-white truncate">{titel}</span>
        {kopfWert}
      </div>
      {unterzeile && (
        <span className="block text-xs text-gray-400 dark:text-gray-500">{unterzeile}</span>
      )}
      <dl className={`mt-1.5 ${wertBlock} ${dicht ? 'text-xs' : 'text-sm'}`}>
        {zeilen.map((z, i) => (
          <div
            key={i}
            className={gestapelt ? '' : 'flex items-baseline justify-between gap-2'}
          >
            <dt className={`shrink-0 ${z.klasse || 'text-gray-500 dark:text-gray-400'}`}>
              {z.label}
            </dt>
            <dd
              className={`tabular-nums ${gestapelt ? '' : 'text-right'} ${z.wertKlasse || 'text-gray-700 dark:text-gray-300'}`}
              style={z.wertStil}
            >
              {z.wert}
              {z.zusatz && <span className="ml-1.5">{z.zusatz}</span>}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

export default MobilKarte
