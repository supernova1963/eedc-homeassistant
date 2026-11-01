/**
 * Themen-Kacheln (4.2.0 TH-E2, Bauplan `bauplan-themen-kacheln.md` §2.1; Konzept Fassung 3 «Kachel je Thema»).
 *
 * Ein **Thema** ist eine benannte Gruppe frei gewählter HA-Entitäten bzw. MQTT-Topics an einem Gerät mit Block
 * «Überblick» (Wärmepumpe, Wallbox, E-Auto); die Live-Antwort trägt es als {@link LiveThema} — nur Einträge mit Wert,
 * `null` ohne jeden Wert (TH-E1). Hier entsteht daraus **je Thema mit ≥ 1 Eintrag eine Wert-Kachel** `art: 'thema'`
 * am Anker HIMMEL der Szene: Name = Thema, Wert-Zeile = erster Eintrag, zweite Zeile = zweiter Eintrag (je
 * «‹Label› · ‹Wert Einheit›»), in den kompakten Dims nur «‹Wert Einheit›» des ersten; der Tooltip trägt **alle**
 * Einträge. Die Kürzung macht die Zeichnung, nicht der Bauer: `UeberblickSchaubild.tsx` ruft für `art === 'thema'`
 * {@link themenKachelTexte} mit den Dims der Reihe (Entscheid Master 1.11.2026 zu H1, Regel {@link kuerzeThemenZeile});
 * dafür trägt die Kachel Label und Wert getrennt (`themaTeile`). Rang im Layout: 3 (nach allen
 * Werten, `ueberblickLayout.ts::rang`) — bei voller Reihe wandern die Themen zuerst nach «Weitere (n)».
 *
 * **Wert wie der HA-State, keine Rechnung** (Bauplan §0): Zahl ⇒ `fmtZahl` mit so vielen Nachkommastellen, wie der
 * State trägt, höchstens zwei («259,5», «12,38»); `device_class: timestamp` oder ein ISO-8601-Zeitstempel ⇒ Uhrzeit
 * aus `lib/datum.ts` (heute) bzw. Datum mit Uhrzeit (anderer Tag) — **in der Kachel kurz** «02.11. 07:00» (Konzept
 * Fassung 3; Nachlauf 4.2.0 K1, die volle Form «02.11.2026, 07:00» passte nicht in die Zeile) und, passt auch das nicht
 * ins Zeichenbudget der Zeile, nur «02.11.» (Entscheid Master 1.11.2026, K1b: {@link ThemaTeil.wertKurz}); im Tooltip und
 * in der Karte «Themen» voll (`formatDatumZeit`); ein reines ISO-Datum ⇒ Datum; sonst **wörtlich** (`locked`, `not_home`).
 * Einheit mit Leerzeichen dahinter («80 %»). Kein Kanon, keine Übersetzung.
 *
 * Reine Funktionen — kein Hook, kein Abruf. Die Karte «Themen» (`UeberblickKarte.tsx::ThemenKarte`) nutzt dieselben
 * Formatierer ({@link themaWert}, {@link themaStand}).
 */
import type { LiveDashboardResponse, LiveThema, LiveThemaEintrag } from '../../../api/liveDashboard'
import type { Investition } from '../../../types'
import { fmtZahl } from '../../../lib'
import { formatDatum, formatDatumZeit, formatUhrzeit, toIsoDatum } from '../../../lib/datum'
import { zeichenBudget } from '../../live/EnergieFluss'
import type { LayoutDims } from '../../live/energieFlussLayout'
import type { ZweiteZeile } from '../../live/EnergieFlussKachel'
import type { AnkerId } from './panorama'
import { kachelWertText, type UeberblickKachel } from './kachelAnker'

/** Label und Wert eines sichtbaren Eintrags — getrennt, damit die Zeichnung kürzen kann. */
export interface ThemaTeil {
  label: string
  /** «‹Wert› ‹Einheit›» ({@link themaWert}). */
  wert: string
  /** Nur bei einem Zeitstempel eines anderen Tages: «TT.MM.» — steht statt {@link wert}, wenn der Wert nicht ins
   *  Zeichenbudget der Zeile passt (K1b). Sonst fehlt das Feld. */
  wertKurz?: string
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
 * Notform der Kachel, wenn «TT.MM. HH:MM» nicht ins Budget passt (K1b). `undefined` für alles andere (heute steht die
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

/** «‹Label› · ‹Wert Einheit›» — eine Kachelzeile (Zeitstempel in der Kurzform der Kachel). */
export function themaZeile(e: LiveThemaEintrag, jetzt: Date = new Date()): string {
  return `${e.label} · ${themaWert(e, jetzt, true)}`
}

/** «Stand 11:27» aus `zeitpunkt` (HA `last_changed`, MQTT Empfang) — `null` ohne Angabe. */
export function themaStand(zeitpunkt: string | null, jetzt: Date = new Date()): string | null {
  return zeitpunkt ? `Stand ${zeitText(zeitpunkt, jetzt)}` : null
}

/** Trenner zwischen Label und Wert einer Kachelzeile. */
const TRENNER = ' · '
/** Ein gekürztes Label behält mindestens so viele Zeichen (dahinter «…»). */
const MIN_LABEL = 3

/**
 * Eine Kachelzeile «‹Label› · ‹Wert›» auf `budget` Zeichen (Entscheid Master 1.11.2026 zu H1): **der Wert ist das
 * Wichtige.** Passt die Zeile nicht, wird zuerst das Label gekürzt (mindestens {@link MIN_LABEL} Zeichen + «…»), der
 * Wert bleibt ganz; reicht der Platz dafür nicht, steht der Wert allein; passt auch er nicht, wird er am Ende mit «…»
 * gekürzt. Ohne Label (`''`, kompakte Dims) gilt nur die letzte Stufe. Mit `wertKurz` (Zeitstempel eines anderen Tages,
 * K1b) tritt «TT.MM.» an die Stelle des Werts, sobald «TT.MM. HH:MM» allein das Budget überschreitet.
 */
export function kuerzeThemenZeile(label: string, wert: string, budget: number, wertKurz?: string): string {
  // K1b: ein Zeitstempel, der allein nicht ins Budget passt, steht nur als «TT.MM.» — dann gilt die Regel mit ihm.
  if (wertKurz != null && wert.length > budget) wert = wertKurz
  const voll = label ? `${label}${TRENNER}${wert}` : wert
  if (voll.length <= budget) return voll
  const platz = budget - TRENNER.length - wert.length
  if (label && platz >= MIN_LABEL + 1) return `${label.slice(0, platz - 1).trimEnd()}…${TRENNER}${wert}`
  if (wert.length <= budget) return wert
  return `${wert.slice(0, Math.max(budget - 1, 1)).trimEnd()}…`
}

/**
 * Wert-Zeile und zweite Zeile einer Themen-Kachel für diese Dims — die EINE Stelle, die `UeberblickSchaubild.tsx` für
 * `art === 'thema'` aufruft. Budget je Zeile `zeichenBudget(nodeW, Schriftgröße)` (Wert `kwFontSize`, zweite Zeile
 * `socFontSize`). In den kompakten Dims (dieselbe Weiche wie {@link kachelWertText}) steht in der Wert-Zeile der Wert
 * allein (`wertTextKompakt`), die zweite Zeile folgt derselben Regel. Ohne `themaTeile` die Texte unverändert.
 */
export function themenKachelTexte(
  k: Pick<UeberblickKachel, 'wertText' | 'wertTextKompakt' | 'zweiteZeile' | 'themaTeile'>,
  dims: Pick<LayoutDims, 'nodeW' | 'kwFontSize' | 'socFontSize'>,
): { wertText: string; zweiteZeile: ZweiteZeile | null } {
  const gewaehlt = kachelWertText(k, dims)
  const t = k.themaTeile
  if (!t) return { wertText: gewaehlt, zweiteZeile: k.zweiteZeile }
  const kompakt = k.wertTextKompakt != null && gewaehlt === k.wertTextKompakt
  const wertBudget = zeichenBudget(dims.nodeW, dims.kwFontSize)
  const zweiteBudget = zeichenBudget(dims.nodeW, dims.socFontSize)
  return {
    wertText: kuerzeThemenZeile(kompakt ? '' : t.erste.label, t.erste.wert, wertBudget, t.erste.wertKurz),
    zweiteZeile: t.zweite && k.zweiteZeile
      ? { ...k.zweiteZeile, text: kuerzeThemenZeile(t.zweite.label, t.zweite.wert, zweiteBudget, t.zweite.wertKurz) }
      : k.zweiteZeile,
  }
}

/** Label und Wert eines sichtbaren Eintrags für die Zeichnung — mit der Notform «TT.MM.», wo es eine gibt (K1b). */
function teil(e: LiveThemaEintrag, jetzt: Date): ThemaTeil {
  const wertKurz = themaWertKurz(e, jetzt)
  return { label: e.label, wert: themaWert(e, jetzt, true), ...(wertKurz != null ? { wertKurz } : {}) }
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
 * Die Themen-Kacheln eines Geräts (Bauplan §2.1): je Thema mit ≥ 1 Eintrag eine Kachel `art: 'thema'`,
 * `id: 'thema-<inv>-<t>'`, am Anker `anker`, in der Rollenfarbe `farbe`; kein Pegel, keine Leistung.
 * `inv = null` nimmt alle Themen der Liste. `mitGeraet` (Wärme mit > 1 Gerät): Tooltip-Kopf «‹Gerät› · ‹Thema›».
 */
export function baueThemenKacheln(
  themen: LiveThema[] | null | undefined, inv: Investition | null, anker: AnkerId, farbe: string,
  mitGeraet = false, jetzt: Date = new Date(),
): UeberblickKachel[] {
  return (themen ?? [])
    .filter((t) => t.eintraege.length > 0 && (inv == null || t.investition_id === inv.id))
    .map((t) => {
      const [erster, zweiter] = t.eintraege
      const kopf = mitGeraet && inv ? `${inv.bezeichnung} · ${t.name}` : t.name
      const stand = themaStand(juengster(t.eintraege), jetzt)
      const tip = [kopf, ...t.eintraege.map((e) => `${e.label}: ${themaWert(e, jetzt)}`), ...(stand ? [stand] : [])].join('\n')
      return {
        id: `thema-${t.investition_id}-${t.id}`, art: 'thema' as const, anker,
        label: t.name, icon: 'tags', color: farbe, isActive: true,
        wertText: themaZeile(erster, jetzt),
        wertTextKompakt: themaWert(erster, jetzt, true),
        zweiteZeile: zweiter ? { text: themaZeile(zweiter, jetzt), fill: null } : null,
        themaTeile: {
          erste: teil(erster, jetzt),
          zweite: zweiter ? teil(zweiter, jetzt) : null,
        },
        tip, investitionId: t.investition_id,
      }
    })
}
