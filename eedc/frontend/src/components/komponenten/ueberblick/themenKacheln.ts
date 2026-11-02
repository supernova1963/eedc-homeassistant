/**
 * Themen-Kacheln (4.2.0 TH-E2, Bauplan `bauplan-themen-kacheln.md` §2.1; Konzept Fassung 3 «Kachel je Thema»;
 * Kachelform neu seit Nachlauf 4.2.1 N4, Entscheid Gernot 2.11.2026 — ändert T-3 vom 1.11.).
 *
 * Ein **Thema** ist eine benannte Gruppe frei gewählter HA-Entitäten bzw. MQTT-Topics an einem Gerät mit Block
 * «Überblick» (Wärmepumpe, Wallbox, E-Auto); die Live-Antwort trägt es als {@link LiveThema} — nur Einträge mit Wert,
 * `null` ohne jeden Wert (TH-E1). Hier entsteht daraus **je Thema mit ≥ 1 Eintrag genau eine Kachel** `art: 'thema'`
 * (`id: 'thema-<inv>-<t>'`) am Anker HIMMEL der Szene — sie belegt im Layout einen Platz, Rang 3 (nach allen Werten,
 * `ueberblickLayout.ts::rang`): bei voller Reihe wandert sie zuerst nach «Weitere (n)».
 *  - **Ein Eintrag** ⇒ eine normale Wert-Kachel wie «Außen 5,0 °C»: Beschriftung = Bezeichnung des Eintrags (gekürzt
 *    wie jede Kachel nach `labelMaxChars`), Wert = {@link themaWert} in der Kurzform der Kachel, keine zweite Zeile.
 *  - **Mehrere Einträge** ⇒ die Zeichnung (`UeberblickSchaubild.tsx`) macht daraus eine **dreizeilige Gruppenkachel**
 *    in der Form der Geräte-Kachel «1.740 W / Heizen / Daikin Al…» (Entscheid Gernot 2.11.2026): Wert des ersten
 *    Eintrags groß und immer ganz · Bezeichnung des ersten Eintrags als zweite Zeile (neutral, am Ende «…») ·
 *    Beschriftung «‹Thema› (n)»; Stapel-Optik, Klick/Tipp öffnet die Liste aller Einträge (Bezeichnung · Wert · Stand)
 *    aus {@link UeberblickKachel.themaEintraege} — das Feld steht nur an diesen Kacheln. Dieselbe Form in jeder Reihenbreite.
 * Die Kürzung auf das Zeichenbudget macht die Zeichnung ({@link themenKachelTexte}); der Tooltip trägt **alle** Einträge
 * ungekürzt.
 *
 * **Wert wie der HA-State, keine Rechnung** (Bauplan §0): Zahl ⇒ `fmtZahl` mit so vielen Nachkommastellen, wie der
 * State trägt, höchstens zwei («259,5», «12,38»); `device_class: timestamp` oder ein ISO-8601-Zeitstempel ⇒ Uhrzeit
 * aus `lib/datum.ts` (heute) bzw. Datum mit Uhrzeit (anderer Tag) — **in der Kachel kurz** «02.11. 07:00» (Konzept
 * Fassung 3; Nachlauf 4.2.0 K1, die volle Form «02.11.2026, 07:00» passte nicht in die Zeile) und in den kompakten Dims
 * nur «02.11.» (Entscheid Master 1.11.2026, K1b: {@link themaWertKurz} als `wertTextKompakt`); im
 * Tooltip, in der Gruppenliste und in der Karte «Themen» voll (`formatDatumZeit`); ein reines ISO-Datum ⇒ Datum; sonst
 * **wörtlich** (`locked`, `not_home`).
 * Einheit mit Leerzeichen dahinter («80 %»). Kein Kanon, keine Übersetzung.
 *
 * Reine Funktionen — kein Hook, kein Abruf. Die Karte «Themen» (`UeberblickKarte.tsx::ThemenKarte`) nutzt dieselben
 * Formatierer ({@link themaWert}, {@link themaStand}).
 */
import type { LiveDashboardResponse, LiveThema, LiveThemaEintrag } from '../../../api/liveDashboard'
import type { Investition } from '../../../types'
import { fmtZahl } from '../../../lib'
import { formatDatum, formatDatumZeit, formatUhrzeit, toIsoDatum } from '../../../lib/datum'
import { kuerzeMitSuffix, zeichenBudget } from '../../live/EnergieFluss'
import type { LayoutDims } from '../../live/energieFlussLayout'
import type { ZweiteZeile } from '../../live/EnergieFlussKachel'
import type { AnkerId } from './panorama'
import { kachelWertText, type UeberblickKachel } from './kachelAnker'

/** Ein Eintrag eines Themas für die Gruppenliste im Bild (Nachlauf 4.2.1 N4): eine Zeile Bezeichnung · Wert · Stand. */
export interface ThemaEintragAnzeige {
  /** Stabiler Schlüssel (Eintrags-ID). */
  id: string
  label: string
  /** «‹Wert› ‹Einheit›» in der vollen Form ({@link themaWert} ohne `kurz`, wie Tooltip und Karte). */
  wert: string
  /** «Stand 11:27» ({@link themaStand}) — `null` ohne Zeitpunkt. */
  stand: string | null
}

/** Ein Zahl-State, wie HA ihn liefert (`"259.5"`, `"-3"`, `"12.3846"`). */
const ZAHL = /^-?\d+(?:\.(\d+))?$/
/** Ein reines ISO-Datum (`device_class: date`). */
const ISO_DATUM = /^\d{4}-\d{2}-\d{2}$/
/** Ein ISO-8601-Zeitstempel mit Uhrzeit (`2026-11-01T07:00:00+00:00`). */
const ISO_ZEIT = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/

/** Höchstens zwei Nachkommastellen (Bauplan §0). */
const MAX_NACHKOMMA = 2

const zwei = (n: number) => String(n).padStart(2, '0')

/** «TT.MM.» (Browser-Zeitzone) — der Tag ohne Jahr. */
function tagKurz(d: Date): string {
  return `${zwei(d.getDate())}.${zwei(d.getMonth() + 1)}.`
}

/** «TT.MM. HH:MM» (Browser-Zeitzone) — die Kurzform der Kachel für einen anderen Tag, ohne Jahr (Konzept Fassung 3). */
function datumZeitKurz(d: Date): string {
  return `${tagKurz(d)} ${zwei(d.getHours())}:${zwei(d.getMinutes())}`
}

/**
 * Ein Zeitpunkt für die Anzeige: heute nur die Uhrzeit, an einem anderen Tag Datum und Uhrzeit (Browser-Zeitzone) —
 * `kurz` (Kachel) als «TT.MM. HH:MM», sonst (Tooltip, Karte) voll aus `lib/datum.ts`.
 */
function zeitText(iso: string, jetzt: Date, kurz = false): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  if (toIsoDatum(d) === toIsoDatum(jetzt)) return formatUhrzeit(iso)
  return kurz ? datumZeitKurz(d) : formatDatumZeit(iso)
}

/** Der Wert eines Eintrags ohne Einheit — Zahl, Zeitstempel, Datum oder wörtlich. */
function wertOhneEinheit(e: Pick<LiveThemaEintrag, 'wert' | 'device_class'>, jetzt: Date, kurz: boolean): string {
  const roh = e.wert.trim()
  const zahl = ZAHL.exec(roh)
  if (zahl) return fmtZahl(Number(roh), Math.min(zahl[1]?.length ?? 0, MAX_NACHKOMMA))
  if (ISO_DATUM.test(roh)) return formatDatum(roh)
  if (e.device_class === 'timestamp' || ISO_ZEIT.test(roh)) return zeitText(roh, jetzt, kurz)
  return e.wert
}

/**
 * «‹Wert› ‹Einheit›» eines Eintrags — die Einheit mit Leerzeichen, ohne Einheit nur der Wert. `kurz` nur für die
 * Kachel (Zeitstempel eines anderen Tages als «TT.MM. HH:MM»); Tooltip und Karte «Themen» rufen ohne.
 */
export function themaWert(
  e: Pick<LiveThemaEintrag, 'wert' | 'einheit' | 'device_class'>, jetzt: Date = new Date(), kurz = false,
): string {
  const wert = wertOhneEinheit(e, jetzt, kurz)
  return e.einheit ? `${wert} ${e.einheit}` : wert
}

/**
 * «TT.MM.» (mit Einheit, falls vorhanden) eines Eintrags, dessen Wert ein Zeitstempel eines **anderen** Tages ist — die
 * Notform der Kachel (Einzel- und Gruppenkachel) in den kompakten Dims, wo «TT.MM. HH:MM» nicht ins Budget passt (K1b). `undefined` für alles andere (heute steht die
 * Uhrzeit, die immer passt; Zahl, Datum, Text haben keine Notform).
 */
export function themaWertKurz(
  e: Pick<LiveThemaEintrag, 'wert' | 'einheit' | 'device_class'>, jetzt: Date = new Date(),
): string | undefined {
  const roh = e.wert.trim()
  if (ZAHL.test(roh) || ISO_DATUM.test(roh) || !(e.device_class === 'timestamp' || ISO_ZEIT.test(roh))) return undefined
  const d = new Date(roh)
  if (Number.isNaN(d.getTime()) || toIsoDatum(d) === toIsoDatum(jetzt)) return undefined
  return e.einheit ? `${tagKurz(d)} ${e.einheit}` : tagKurz(d)
}

/** «Stand 11:27» aus `zeitpunkt` (HA `last_changed`, MQTT Empfang) — `null` ohne Angabe. */
export function themaStand(zeitpunkt: string | null, jetzt: Date = new Date()): string | null {
  return zeitpunkt ? `Stand ${zeitText(zeitpunkt, jetzt)}` : null
}

/**
 * Wert- und zweite Zeile einer Themen-Kachel für diese Dims — die EINE Stelle, die `UeberblickSchaubild.tsx` für
 * `art === 'thema'` aufruft (Nachlauf 4.2.1 N4). Der Wert wird wie bei jeder Kachel über {@link kachelWertText} gewählt
 * (kompakte Dims: Notform «TT.MM.», K1b).
 *  - **Gruppenkachel** (`themaEintraege`): der Wert bleibt **immer ganz**; die zweite Zeile (Bezeichnung des ersten
 *    Eintrags) wird am Ende mit «…» auf `zeichenBudget(nodeW, socFontSize)` gekürzt.
 *  - **Einzel-Kachel:** der Wert am Ende mit «…» auf `zeichenBudget(nodeW, kwFontSize)`; keine zweite Zeile.
 */
export function themenKachelTexte(
  k: Pick<UeberblickKachel, 'wertText' | 'wertTextKompakt' | 'zweiteZeile' | 'themaEintraege'>,
  dims: Pick<LayoutDims, 'nodeW' | 'kwFontSize' | 'socFontSize'>,
): { wertText: string; zweiteZeile: ZweiteZeile | null } {
  const wert = kachelWertText(k, dims)
  if (k.themaEintraege && k.zweiteZeile) {
    const budget = zeichenBudget(dims.nodeW, dims.socFontSize)
    return { wertText: wert, zweiteZeile: { ...k.zweiteZeile, text: kuerzeMitSuffix(k.zweiteZeile.text, '', budget) } }
  }
  return { wertText: kuerzeMitSuffix(wert, '', zeichenBudget(dims.nodeW, dims.kwFontSize)), zweiteZeile: k.zweiteZeile }
}

/** Der jüngste Zeitpunkt der Einträge eines Themas — der Stand der Kachel. */
function juengster(eintraege: LiveThemaEintrag[]): string | null {
  let best: string | null = null
  let bestMs = -Infinity
  for (const e of eintraege) {
    const ms = e.zeitpunkt ? new Date(e.zeitpunkt).getTime() : NaN
    if (!Number.isNaN(ms) && ms > bestMs) { best = e.zeitpunkt; bestMs = ms }
  }
  return best
}

/** Die Themen eines Geräts aus der Live-Antwort — in Store-Reihenfolge, nur Themen mit ≥ 1 Eintrag. */
export function themenVon(live: Pick<LiveDashboardResponse, 'themen'> | null, invId: number): LiveThema[] {
  return (live?.themen ?? []).filter((t) => t.investition_id === invId && t.eintraege.length > 0)
}

/**
 * Die Themen-Kacheln eines Geräts (Bauplan §2.1, Kachelform Nachlauf 4.2.1 N4): je Thema mit ≥ 1 Eintrag eine Kachel
 * `art: 'thema'`, `id: 'thema-<inv>-<t>'`, am Anker `anker`, in der Rollenfarbe `farbe`, Symbol `tags`; kein Pegel, keine
 * Leistung. Wert = Wert des ersten Eintrags (Kurzform der Kachel, Notform «TT.MM.» als `wertTextKompakt`). Ein Eintrag ⇒
 * Beschriftung = Bezeichnung, keine zweite Zeile; mehrere ⇒ Beschriftung = Thema, zweite Zeile = Bezeichnung des ersten
 * (neutral, `fill: null`), `themaEintraege` = alle (die Zeichnung macht die dreizeilige Gruppe daraus).
 * `inv = null` nimmt alle Themen der Liste. `mitGeraet` (Wärme mit > 1 Gerät): Tooltip-Kopf «‹Gerät› · ‹Thema›».
 * Tooltip: Kopf, je Eintrag «Bezeichnung: Wert» (Gruppe: «• Bezeichnung: Wert» unter «‹Kopf› (n)»), dann «Stand …».
 */
export function baueThemenKacheln(
  themen: LiveThema[] | null | undefined, inv: Investition | null, anker: AnkerId, farbe: string,
  mitGeraet = false, jetzt: Date = new Date(),
): UeberblickKachel[] {
  return (themen ?? [])
    .filter((t) => t.eintraege.length > 0 && (inv == null || t.investition_id === inv.id))
    .map((t) => {
      const [erster] = t.eintraege
      const gruppe = t.eintraege.length > 1
      const kopf = mitGeraet && inv ? `${inv.bezeichnung} · ${t.name}` : t.name
      const stand = themaStand(juengster(t.eintraege), jetzt)
      const tip = [
        gruppe ? `${kopf} (${t.eintraege.length})` : kopf,
        ...t.eintraege.map((e) => `${gruppe ? '• ' : ''}${e.label}: ${themaWert(e, jetzt)}`),
        ...(stand ? [stand] : []),
      ].join('\n')
      const basis = {
        id: `thema-${t.investition_id}-${t.id}`, art: 'thema' as const, anker,
        icon: 'tags', color: farbe, isActive: true, zweiteZeile: null, tip, investitionId: t.investition_id,
      }
      const wertKurz = themaWertKurz(erster, jetzt)
      const wert = { wertText: themaWert(erster, jetzt, true), ...(wertKurz != null ? { wertTextKompakt: wertKurz } : {}) }
      if (gruppe) {
        return {
          ...basis, ...wert, label: t.name, zweiteZeile: { text: erster.label, fill: null },
          themaEintraege: t.eintraege.map((e) => ({ id: e.id, label: e.label, wert: themaWert(e, jetzt), stand: themaStand(e.zeitpunkt, jetzt) })),
        }
      }
      return { ...basis, ...wert, label: erster.label }
    })
}
