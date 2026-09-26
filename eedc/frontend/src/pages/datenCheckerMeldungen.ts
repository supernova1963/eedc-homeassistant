/**
 * Daten-Checker — Rückmeldungs-Texte der Reparatur-Aktionen (reines Modul).
 *
 * Getrennt von `DatenCheckerTeile.tsx`, damit die Entscheidung „Erfolg /
 * Hinweis / Fehler" ohne Komponenten-Mount prüfbar bleibt (gleiches Muster wie
 * `baueTagKpis`) und die Seite kein react-refresh-Treffer wird.
 */
import type { ReaggregateBereichResponse, ReaggregateTagResponse } from '../api/energie_profil'
import { fmtZahl, formatDatum } from '../lib'

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
  vonIso: string,
  bisIso: string,
): ReparaturMeldung {
  // Anzeige-Datum de-DE — dieselbe Schreibweise wie die Tages-Meldung daneben.
  const von = formatDatum(vonIso)
  const bis = formatDatum(bisIso)
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
  datumIso: string,
): ReparaturMeldung {
  // Anzeige-Datum de-DE (`check:de-de`): die Meldung wird seit F-2 auch in
  // Cockpit/Tag gezeigt und ist damit im Scharf-Scope des Wächters.
  const datumDe = formatDatum(datumIso)
  const alt = r.pv_kwh_alt ?? null
  const neu = r.pv_kwh_neu ?? null
  let pvTeil: string
  if (alt !== null && neu !== null && Math.abs(alt - neu) < 0.1) {
    pvTeil = `Tag ${datumDe}: PV-Wert blieb ${fmtZahl(alt, 1)} kWh (keine Änderung).`
  } else if (alt !== null && neu !== null) {
    // Zählerlücken wie HA (§2): steht ein Teil der neuen PV in einer Stunde, die
    // mehr als eine reale Stunde trägt, sagt die Meldung das — sonst läse man
    // die Energie einer HA-Lücke als unerklärten Sprung.
    const ausLuecke = r.pv_kwh_aus_luecke ?? 0
    const lueckenTeil = ausLuecke >= 0.05 ? ` (davon ${fmtZahl(ausLuecke, 1)} kWh aus einer Lücke in Home Assistant)` : ''
    pvTeil = `Tag ${datumDe} repariert: PV ${fmtZahl(alt, 1)} → ${fmtZahl(neu, 1)} kWh${lueckenTeil}.`
  } else {
    pvTeil = `Tag ${datumDe} aus HA-Statistics neu aggregiert.`
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

/**
 * N-393: Rückfrage vor „Wert entfernen" — nennt Feld, Gerät und JEDEN Monat.
 * Die Aktion nimmt alle betroffenen Monate mit (eine Meldung je Feld, nicht je
 * Monat); die Rückfrage muss deshalb die Liste zeigen, nicht „diesen Eintrag".
 */
export function baueFeldwertRueckfrage(label: string, monate: string[]): string {
  const liste = monate.join(', ')
  const anzahl = monate.length === 1 ? 'im Monat' : `in ${monate.length} Monaten`
  return (
    `„${label}“ ${anzahl} ${liste} endgültig entfernen?\n\n` +
    'Das Gerät führt dieses Feld nach seinen Einstellungen nicht mehr; im ' +
    'Monatsabschluss ist der Wert deshalb nicht erreichbar. Soll er weiter ' +
    'zählen, stelle stattdessen die Einstellung am Gerät zurück.'
  )
}

/** N-393: Rückmeldung nach dem Entfernen — zählt, was wirklich weg ist. */
export function baueFeldwertMeldung(
  label: string, r: { entfernt: number; monate: { jahr: number; monat: number }[] },
): ReparaturMeldung {
  if (r.entfernt <= 0) return { art: 'hinweis', text: `„${label}“: es war nichts mehr zu entfernen.` }
  const monate = r.monate.map(m => `${String(m.monat).padStart(2, '0')}/${m.jahr}`).join(', ')
  return { art: 'ok', text: `„${label}“ in ${r.entfernt} Monat(en) entfernt (${monate}).` }
}

/**
 * Rückfrage vor „Energieprofil-Daten löschen" — nennt BEIDE Verluste.
 *
 * ⛔ **Warum der alte Satz ein Problem war** (Forum simon42 T89667, PN rapahl
 * vom 15.09.2026): Er lautete „Der Scheduler berechnet sie neu (max. 15 Min).
 * Monatsdaten bleiben erhalten." — und war damit eine **Beruhigung, die nicht
 * trägt**. Zwei Dinge kommen nicht zurück:
 *
 *  1. **Die aufgezeichneten Prognosen.** `pv_prognose_final_kwh` &
 *     `pv_prognose_final_at`, dazu die SFML- und Solcast-Felder sind
 *     Aufzeichnungen eines vergangenen Zeitpunkts und Grundlage des
 *     Genauigkeits-Vergleichs. Eine Vorhersage von damals kann niemand neu
 *     *berechnen* — sie ist endgültig weg. Rainer hat genau das gemeldet.
 *  2. **Messwerte jenseits der Recorder-Tiefe.** Der Scheduler holt aus der
 *     HA-Langzeitstatistik zurück, was dort noch liegt. In vielen Setups
 *     (Recorder-Purge, Sensor-Umbau, Add-on-Neuinstallation) reicht sie
 *     **kürzer zurück als das gepflegte Profil** — der Rest ist verloren.
 *     Das ist die Begründung, aus der der Overwrite-Modus des Vollbackfills
 *     v3.25.22 entfernt wurde; sie galt hier genauso, stand aber nirgends.
 *
 * ⚠ **Kein Abraten, keine Sonderlogik.** Die Funktion bleibt wie sie ist —
 * Rainer nutzt sie bewusst und schätzt sie. Der Text sagt nur, was passiert;
 * die Entscheidung bleibt beim Anwender (*eedc ist nicht die Strom-Polizei*).
 */
export function baueRohdatenLoeschRueckfrage(): string {
  return (
    'Alle Energieprofil-Daten dieser Anlage löschen?\n\n' +
    'Der Scheduler holt die Messwerte aus der Home-Assistant-Langzeitstatistik ' +
    'zurück (max. 15 Min) — aber nur so weit, wie deine HA-Statistik ' +
    'zurückreicht. Ältere Tage bleiben weg.\n\n' +
    'Die aufgezeichneten PV-Prognosen (Grundlage des Genauigkeits-Vergleichs) ' +
    'lassen sich nicht neu berechnen und sind endgültig verloren.\n\n' +
    'Monatsdaten bleiben erhalten.'
  )
}

/** Kurzform derselben Aussage für die Beschreibung der Operation. */
export const ROHDATEN_LOESCH_BESCHREIBUNG =
  'Entfernt alle Stundenwerte und Tageszusammenfassungen dieser Anlage. Der ' +
  'Scheduler holt die Messwerte aus HA nach (max. 15 Min), soweit die ' +
  'Langzeitstatistik zurückreicht; aufgezeichnete PV-Prognosen kommen nicht ' +
  'zurück. Monatsdaten bleiben erhalten.'

/** Rückmeldung nach dem Löschen — zählt, was weg ist, und was nicht zurückkommt. */
export function baueRohdatenLoeschMeldung(
  r: { geloescht_stundenwerte?: number; geloescht_tagessummen?: number },
): ReparaturMeldung {
  const stunden = r.geloescht_stundenwerte ?? 0
  const tage = r.geloescht_tagessummen ?? 0
  return {
    art: 'ok',
    text:
      `${stunden} Stundenwerte + ${tage} Tagessummen gelöscht. Der Scheduler ` +
      'füllt die Messwerte aus HA nach (max. 15 Min), soweit die ' +
      'Langzeitstatistik zurückreicht. Aufgezeichnete PV-Prognosen kommen ' +
      'nicht zurück.',
  }
}
