/**
 * Monats-Lücken — die EINE Vollständigkeits-Quelle für die Monatsdaten-Tabelle
 * (Monatsabschluss-V4 §7, V-b). Rein & getestet.
 *
 * Grundsatz (Gernot 2026-07-12, V-b): Tabellen-Färbung UND „nächster offener
 * Monat"-Sprung leiten sich aus DERSELBEN Ableitung ab — NICHT aus zwei Logiken.
 * Der bestehende Backend-Endpoint `getNaechsterMonat` ist bewusst NICHT die Quelle:
 * er springt naiv auf „letzter Monat + 1" und verfehlt innere Lücken (z. B. ein
 * einzelner fehlender Monat mitten in der Historie).
 *
 * „Erwarteter Bereich" = [Anschaffungs-Anker … letzter vergangener Monat]:
 * - Start = frühestes `anschaffungsdatum` der Investitionen (Anschaffungsdatum ist
 *   die limitierende Grenze für ALLE Auswertungen — feedback_anschaffungsdatum_grenze),
 *   Fallback Anlage-Installationsdatum, dann erste vorhandene Datenzeile.
 * - Ende = Vormonat von heute (der laufende Monat ist noch nicht abgeschlossen).
 * Ein Monat OHNE Datenzeile in diesem Bereich gilt als „offen/fehlt".
 */

export interface MonatRef {
  jahr: number
  monat: number
}

/** Fortlaufender Monatsindex (jahr*12 + monat-1) für Vergleich/Iteration. */
export function monatIndex(jahr: number, monat: number): number {
  return jahr * 12 + (monat - 1)
}

/** Umkehrung von {@link monatIndex}. */
export function ausMonatIndex(idx: number): MonatRef {
  return { jahr: Math.floor(idx / 12), monat: (idx % 12) + 1 }
}

/**
 * Bereichs-Start (Anschaffungs-Anker) aus den verfügbaren ISO-Datums-Quellen.
 * Reihenfolge: frühestes Investitions-`anschaffungsdatum` → Anlage-Installationsdatum
 * → früheste vorhandene Datenzeile. `null`, wenn keine Quelle greift.
 */
export function ermittleStartAnker(params: {
  anschaffungsdaten: (string | null | undefined)[]
  anlageInstallationsdatum?: string | null
  vorhandene: MonatRef[]
}): MonatRef | null {
  const isoDaten = params.anschaffungsdaten.filter((d): d is string => !!d)
  const fruehestesIso = isoDaten.length
    ? isoDaten.reduce((a, b) => (a <= b ? a : b))
    : params.anlageInstallationsdatum || null
  if (fruehestesIso) {
    // ISO 'YYYY-MM-DD' direkt zerlegen (kein Date → keine Zeitzonen-Falle).
    const jahr = parseInt(fruehestesIso.slice(0, 4), 10)
    const monat = parseInt(fruehestesIso.slice(5, 7), 10)
    if (jahr && monat) return { jahr, monat }
  }
  // Fallback: früheste vorhandene Datenzeile.
  if (params.vorhandene.length) {
    const minIdx = Math.min(...params.vorhandene.map((m) => monatIndex(m.jahr, m.monat)))
    return ausMonatIndex(minIdx)
  }
  return null
}

export interface LueckenParams {
  /** Monate mit vorhandener Datenzeile (aus `listAggregiert`). */
  vorhandene: MonatRef[]
  /** Bereichs-Start (Anschaffungs-Anker, {@link ermittleStartAnker}). */
  start: MonatRef | null
  /** Aktueller (noch nicht abgeschlossener) Monat = heute. */
  heute: MonatRef
}

/**
 * Alle im erwarteten Bereich fehlenden Monate, chronologisch AUFSTEIGEND.
 * Bereich = [start … Vormonat(heute)]. Ohne Start (kein Anker) → leer.
 */
export function ermittleFehlendeMonate(p: LueckenParams): MonatRef[] {
  if (!p.start) return []
  const vorhandenSet = new Set(p.vorhandene.map((m) => monatIndex(m.jahr, m.monat)))
  const startIdx = monatIndex(p.start.jahr, p.start.monat)
  // Ende = letzter VOLLSTÄNDIG vergangener Monat = Vormonat(heute).
  const endeIdx = monatIndex(p.heute.jahr, p.heute.monat) - 1
  const fehlend: MonatRef[] = []
  for (let i = startIdx; i <= endeIdx; i++) {
    if (!vorhandenSet.has(i)) fehlend.push(ausMonatIndex(i))
  }
  return fehlend
}

/**
 * Frühester offener (fehlender) Monat aus derselben Ableitung wie die
 * Tabellen-Färbung — oder `null`, wenn der Bereich lückenlos ist. Speist den
 * „nächster offener Monat"-Sprung (§7, Invariante „eine Quelle").
 */
export function naechsterOffenerMonat(p: LueckenParams): MonatRef | null {
  const fehlend = ermittleFehlendeMonate(p)
  return fehlend.length ? fehlend[0] : null
}
