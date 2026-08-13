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
 * „Erwarteter Bereich" = [Anlagen-Anker … letzter vergangener Monat]:
 * - Start = Anlage-Installationsdatum, Fallback ältestes `anschaffungsdatum` der
 *   ERZEUGER, dann erste vorhandene Datenzeile (seit 2026-08-13, s.
 *   {@link ermittleStartAnker}). Welche Investition in welchem Monat *zählt*,
 *   entscheidet davon unberührt ihr eigenes Anschaffungs-/Stilllegungsdatum
 *   (feedback_anschaffungsdatum_grenze).
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
 * Bereichs-Start für die **Basisdaten** (Anlagenzeile: Einspeisung/Netzbezug).
 * Reihenfolge: Anlage-Installationsdatum → ältestes `anschaffungsdatum` der
 * ERZEUGER → früheste vorhandene Datenzeile. `null`, wenn keine Quelle greift.
 *
 * **Die Reihenfolge stand bis 2026-08-13 andersherum**, und der Anker nahm das
 * früheste Anschaffungsdatum ALLER Investitionen. Eine Monatszeile ist aber eine
 * Aussage über die *Anlage*, nicht über ein Gerät: Ein E-Auto von 2017 begründet
 * keine Einspeisungszeile von 2017. Zweimal aufgelaufen — fridolin22 (Forum
 * T77723 #773) hat sein Auto auf 2026 umdatiert, um die Forderung loszuwerden,
 * und damit dessen echte Historie verloren; van (PN 13.08.) sah „Sep 2016".
 *
 * ⚠ Welche Investition in welchem Monat *zählt*, bleibt davon unberührt — das
 * entscheidet ihr eigenes Anschaffungs-/Stilllegungsdatum
 * (feedback_anschaffungsdatum_grenze). Hier geht es nur um den Erwartungsrahmen.
 *
 * `erzeugerAnschaffungsdaten` filtert der Aufrufer (ERZEUGER_INVESTITION_TYPEN);
 * dieses Modul bleibt rein, damit es gegen den Backend-Spiegel testbar bleibt.
 */
export function ermittleStartAnker(params: {
  erzeugerAnschaffungsdaten: (string | null | undefined)[]
  anlageInstallationsdatum?: string | null
  vorhandene: MonatRef[]
}): MonatRef | null {
  const isoDaten = params.erzeugerAnschaffungsdaten.filter((d): d is string => !!d)
  const fruehestesIso = params.anlageInstallationsdatum
    || (isoDaten.length ? isoDaten.reduce((a, b) => (a <= b ? a : b)) : null)
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
