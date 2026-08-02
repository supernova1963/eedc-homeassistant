/**
 * Daten-Checker — Rückmeldungs-Texte der Reparatur-Aktionen (reines Modul).
 *
 * Getrennt von `DatenCheckerTeile.tsx`, damit die Entscheidung „Erfolg /
 * Hinweis / Fehler" ohne Komponenten-Mount prüfbar bleibt (gleiches Muster wie
 * `baueTagKpis`) und die Seite kein react-refresh-Treffer wird.
 */
import type { ReaggregateBereichResponse, ReaggregateTagResponse } from '../api/energie_profil'
import { fmtZahl } from '../lib'

export type MeldungsArt = 'ok' | 'hinweis' | 'fehler'

export interface ReparaturMeldung {
  art: MeldungsArt
  text: string
}

/**
 * Baut die Rückmeldung zum Bereichs-Lauf aus den TATSÄCHLICHEN Zählern.
 *
 * `status: "ok"` heißt nur „durchgelaufen". Bis 2026-07-30 meldete die Seite
 * unbedingt Erfolg — auch bei `erfolgreich: 0, keine_daten: 11` (E2E gemessen
 * an der lokalen Box). `aggregate_day` liefert `None`, wenn es für den Tag
 * keine Kurvendaten findet; der Endpoint antwortet dann trotzdem mit HTTP 200.
 * Ein Knopf, der nichts geholt hat, darf das nicht als Erfolg ausgeben —
 * sonst sucht der Anwender den Fehler bei sich.
 */
export function baueBereichsMeldung(
  r: Partial<ReaggregateBereichResponse>,
  von: string,
  bis: string,
): ReparaturMeldung {
  const ok = r.erfolgreich ?? 0
  const leer = r.keine_daten ?? 0
  const kaputt = r.fehlgeschlagen ?? 0
  const fehlerTeil = kaputt > 0 ? `, ${kaputt} mit Fehler` : ''

  if (ok === 0 && (leer > 0 || kaputt > 0)) {
    return {
      art: 'hinweis',
      text:
        `Zeitraum ${von} bis ${bis}: kein Tag konnte nachgerechnet werden ` +
        `(${leer} ohne verwertbare Daten${fehlerTeil}). Häufigste Ursache: für ` +
        `diese Anlage ist kein Leistungssensor zugeordnet, oder die ` +
        `Home-Assistant-Historie reicht nicht so weit zurück. Der Zählerstand ` +
        `allein genügt dem Tages-Lauf nicht.`,
    }
  }
  if (leer > 0 || kaputt > 0) {
    return {
      art: 'hinweis',
      text:
        `Zeitraum ${von} bis ${bis}: ${ok} Tag(e) neu aus HA-Statistics ` +
        `aggregiert, ${leer} ohne verwertbare Daten übersprungen${fehlerTeil}.`,
    }
  }
  return {
    art: 'ok',
    text: `Zeitraum ${von} bis ${bis}: ${ok} Tag(e) neu aus HA-Statistics aggregiert.`,
  }
}

/** Die Ursache, die in beiden Pfaden zuerst zutrifft — Absage ohne Weg ist eine halbe Meldung. */
const URSACHE =
  `Häufigste Ursache: für die betroffene Komponente ist kein Leistungssensor ` +
  `zugeordnet, oder die Home-Assistant-Historie reicht nicht so weit zurück. ` +
  `Der Zählerstand allein genügt dem Tages-Lauf nicht.`

/**
 * Baut die Rückmeldung zum Einzeltag-Lauf — dieselben drei Fälle wie
 * `baueBereichsMeldung`, nur je Komponente statt je Tag.
 *
 * `status: "ok"` heißt auch hier nur „durchgelaufen". Bis v4.0.6 baute die
 * Seite ihre Meldung allein aus `pv_kwh_alt`/`pv_kwh_neu` (#290) und meldete
 * immer Erfolg: eine Wärmepumpe, für die der Lauf nichts holen konnte, war von
 * „PV-Wert unverändert" nicht unterscheidbar, solange die PV sich bewegt hatte
 * (N-58, Forum simon42 #89667/83, dietmar1968). Die PV-Aussage bleibt — sie
 * beantwortet die #290-Frage „hat sich etwas bewegt?" — und wird um die
 * Komponenten-Aussage ERGÄNZT.
 */
export function baueTagesMeldung(
  r: Partial<ReaggregateTagResponse>,
  datum: string,
): ReparaturMeldung {
  const alt = r.pv_kwh_alt ?? null
  const neu = r.pv_kwh_neu ?? null
  let pvTeil: string
  if (alt !== null && neu !== null && Math.abs(alt - neu) < 0.1) {
    pvTeil = `Tag ${datum}: PV-Wert blieb ${fmtZahl(alt, 1)} kWh (keine Änderung).`
  } else if (alt !== null && neu !== null) {
    pvTeil = `Tag ${datum} repariert: PV ${fmtZahl(alt, 1)} → ${fmtZahl(neu, 1)} kWh.`
  } else {
    pvTeil = `Tag ${datum} aus HA-Statistics neu aggregiert.`
  }

  const erwartet = r.komponenten_erwartet ?? 0
  const geschrieben = r.komponenten_geschrieben ?? 0
  const ohneWert = r.komponenten_ohne_wert ?? []

  // Ältere Backends ohne Komponenten-Zähler: nur die PV-Aussage, kein
  // erfundener Komponenten-Befund.
  if (erwartet === 0) {
    return { art: 'ok', text: pvTeil }
  }

  if (geschrieben === 0) {
    return {
      art: 'hinweis',
      text:
        `${pvTeil} Für keine der ${erwartet} zugeordneten Komponenten konnte ` +
        `ein Wert geschrieben werden (${ohneWert.join(', ')}). ${URSACHE}`,
    }
  }
  if (ohneWert.length > 0) {
    return {
      art: 'hinweis',
      text:
        `${pvTeil} ${geschrieben} von ${erwartet} Komponenten neu geschrieben — ` +
        `ohne Wert blieb: ${ohneWert.join(', ')}. ${URSACHE}`,
    }
  }
  return {
    art: 'ok',
    text: `${pvTeil} Alle ${erwartet} zugeordneten Komponenten tragen einen Wert.`,
  }
}
