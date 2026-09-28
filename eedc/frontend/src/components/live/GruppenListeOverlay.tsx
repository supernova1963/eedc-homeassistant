/**
 * GruppenListeOverlay — die „Liste mit Balken" einer Energiefluss-Gruppe
 * (Bau A §A5, #341/#348; Plan §1.6, Muster „Liste mit Balken (Overlay)").
 *
 * Klick (oder Enter/Leertaste) auf eine Gruppenkachel öffnet dieses Fenster:
 * je Mitglied eine Zeile — Name, Leistung als Balken (relativ zum stärksten
 * Mitglied, in der Rollenfarbe des Mitglieds), Wert — und darunter die
 * typabhängige Angabe (PV: Auslastung + Ausrichtung/Träger · Speicher:
 * lädt/entlädt/ruht + Ladestand + nutzbare Kapazität · Wallbox: die Autos ·
 * Wärmepumpe: Betriebsart · Sonstige: Kategorie).
 *
 * **Bauform (Regel 0a):** das EINE Vollbild-Overlay `FokusVollbild` in seiner
 * Dialog-Betriebsart — `role="dialog"`, `aria-modal`, zugänglicher Name = der
 * Gruppentitel, Fokus beim Öffnen auf „Schließen". Die Rückgabe an die
 * auslösende Kachel macht `CockpitLiveV4` (nur der Aufrufer kennt sie).
 *
 * **Live (Vorlage §A5, Ü5):** die Zeilen entstehen je Render aus den AKTUELLEN
 * `komponenten`/`gauges` — die Gruppe liefert nur, WER dazugehört (ihre
 * Mitglieds-Keys aus dem aktuellen Layout). Existiert die Gruppe im Layout
 * nicht mehr, schließt `CockpitLiveV4` das Fenster; diese Komponente sieht
 * den Fall nie.
 *
 * **ESC-Staffelung:** eigener `keydown`-Zuhörer, der `preventDefault()` ruft
 * und NUR dieses Fenster schließt (Muster `ui/DatumPicker`). Das Vollbild
 * darunter (⤢) entscheidet im Makrotask nach `defaultPrevented` und bleibt
 * offen; das Deep-Link-Vollbild registriert gar keinen Zuhörer.
 *
 * ⛔ Keine Fokus-ID, kein Einbetten-Knopf (der Vertrag `LIVE_FOKUS_IDS` bleibt
 * unberührt) und keine Park-Funktion — das Fenster ist ein Detail, kein Block.
 */
import { useEffect } from 'react'
import { Battery, Car, Flame, Plug, Sun, Wrench, type LucideIcon } from 'lucide-react'
import type { LiveGauge, LiveKomponente } from '../../api/liveDashboard'
import { FokusVollbild } from '../blocks'
import { SONSTIGES_KATEGORIE_LABELS, fmtZahl } from '../../lib'
import { SATZ_ZUORDNUNG_UNBEKANNT, formatPower, getNodeColor, getSoc, nennleistungKwp } from './EnergieFluss'
import { praefix, wallboxFahrzeuge, type GezeichneterKnoten } from './energieFlussLayout'

interface Props {
  /** Die offene Gruppe, wie das AKTUELLE Layout sie zeichnet (Mitglieder, Name, Ladestand). */
  gruppe: GezeichneterKnoten
  /** Die aktuelle Live-Antwort — Quelle der Zeilenwerte. */
  komponenten: LiveKomponente[]
  gauges?: LiveGauge[]
  onClose: () => void
}

const ICONS: Record<string, LucideIcon> = {
  sun: Sun, battery: Battery, plug: Plug, flame: Flame, car: Car, wrench: Wrench,
}

/** Die Art der Gruppe in einem Wort (Muster `detail-art`). */
function gruppenArt(key: string): string {
  if (key === 'sonstige_grp_weitere') return 'Weitere Verbraucher'
  switch (praefix(key)) {
    case 'pv': return 'PV-Gruppe'
    case 'batterie': return 'Speichergruppe'
    case 'wallbox': return 'Ladegruppe'
    case 'eauto': return 'E-Autos ohne Wallbox'
    case 'waermepumpe': return 'Wärmepumpen'
    default: return 'Gerätegruppe'
  }
}

const kw2 = (kw: number) => `${fmtZahl(kw, 2)} kW`

/** Ein Auto als Text: Ladestand und — gemessen — lädt/entlädt (V2H). */
function autoText(a: { label: string; soc?: number | null; kw?: number | null }): string {
  const teile = [a.label, a.soc != null ? `${a.soc} %` : 'Ladestand unbekannt']
  const kw = a.kw ?? 0
  if (kw > 0) teile.push(`lädt ${kw2(kw)}`)
  else if (kw < 0) teile.push(`entlädt ${kw2(-kw)} (V2H)`)
  return teile.join(' · ')
}

interface Zeile {
  key: string
  name: string
  kw: number
  farbe: string
  /** Typabhängige Angabe unter der Zeile; leer = keine. */
  zusatz: string[]
}

export default function GruppenListeOverlay({ gruppe, komponenten, gauges, onClose }: Props) {
  // ESC schließt NUR dieses Fenster: `preventDefault` meldet die Taste als
  // verbraucht — das Vollbild darunter (⤢) lässt sie daraufhin liegen.
  useEffect(() => {
    const beiTaste = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      onClose()
    }
    document.addEventListener('keydown', beiTaste)
    return () => document.removeEventListener('keydown', beiTaste)
  }, [onClose])

  const mitgliedsKeys = (gruppe.mitglieder ?? []).map(m => m.key)
  const nachKey = new Map(komponenten.map(k => [k.key, k] as const))
  const mitglieder = mitgliedsKeys.map(k => nachKey.get(k)).filter((k): k is LiveKomponente => k != null)
  // Autos an Wallboxen — dieselbe Zuordnung wie die Kachel (neues Backend:
  // `fahrzeuge`; älteres: die `parent_key`-Kinder).
  const kinder = komponenten.filter(k => k.parent_key)
  const wallboxAnzahl = komponenten.filter(k => !k.parent_key && praefix(k.key) === 'wallbox').length
  const autosJeWallbox = new Map(mitglieder
    .filter(m => praefix(m.key) === 'wallbox')
    .map(m => [m.key, wallboxFahrzeuge(m, kinder, wallboxAnzahl, gauges)] as const))
  const geschaetzt = [...autosJeWallbox.values()].some(w => w.zuordnung === 'geschaetzt' && w.fahrzeuge.length > 0)
  // Bei „geschätzt" (≥ 2 Wallboxen) ist die Zuordnung reihum nur eine Annahme —
  // die Autos stehen dann EINMAL unter der Liste, nicht an einer Wallbox.
  const alleAutos = geschaetzt
    ? [...new Map([...autosJeWallbox.values()].flatMap(w => w.fahrzeuge).map(f => [f.investition_id, f] as const)).values()]
        .sort((a, b) => a.investition_id - b.investition_id)
    : []

  const zeilen: Zeile[] = mitglieder.map(m => {
    const kw = Math.max(m.erzeugung_kw ?? 0, m.verbrauch_kw ?? 0)
    const zusatz: string[] = []
    const p = praefix(m.key)
    if (p === 'pv') {
      const kwp = nennleistungKwp(m)
      if (kwp != null) zusatz.push(`${fmtZahl(Math.min(100, ((m.erzeugung_kw ?? 0) / kwp) * 100), 0)} % von ${fmtZahl(kwp, 1)} kWp`)
      if (m.ausrichtung_label) zusatz.push(m.ausrichtung_label)
      if (m.traeger_label) zusatz.push(m.traeger_label)
    } else if (p === 'batterie') {
      const erz = m.erzeugung_kw ?? 0
      const verb = m.verbrauch_kw ?? 0
      zusatz.push(erz > verb ? 'entlädt' : verb > erz ? 'lädt' : 'ruht')
      const soc = getSoc(m.key, gauges)
      if (soc != null) zusatz.push(`Ladestand ${soc} %`)
      if (m.kapazitaet_kwh != null && m.kapazitaet_kwh > 0) zusatz.push(`${fmtZahl(m.kapazitaet_kwh, 1)} kWh nutzbar`)
    } else if (p === 'wallbox') {
      const w = autosJeWallbox.get(m.key)
      if (w && w.zuordnung === 'eindeutig') w.fahrzeuge.forEach(a => zusatz.push(`Auto ${autoText(a)}`))
    } else if (p === 'eauto') {
      const soc = getSoc(m.key, gauges)
      if (soc != null) zusatz.push(`Ladestand ${soc} %`)
      if ((m.erzeugung_kw ?? 0) > 0) zusatz.push('gibt ab (V2H)')
    } else if (p === 'waermepumpe') {
      if (m.betriebsmodus_label) zusatz.push(m.betriebsmodus_label)
    } else if (p === 'sonstige') {
      if (m.kategorie) zusatz.push(SONSTIGES_KATEGORIE_LABELS[m.kategorie] ?? m.kategorie)
    }
    return { key: m.key, name: m.label, kw, farbe: getNodeColor(m), zusatz }
  })

  const maxKw = Math.max(0, ...zeilen.map(z => z.kw))
  const summeErz = mitglieder.reduce((s, m) => s + (m.erzeugung_kw ?? 0), 0)
  const summeVerb = mitglieder.reduce((s, m) => s + (m.verbrauch_kw ?? 0), 0)
  const netto = summeErz - summeVerb
  const gegenlaeufig = summeErz > 0 && summeVerb > 0
  const summe = `${kw2(Math.abs(netto))} (${netto > 0 ? 'Erzeugung' : netto < 0 ? 'Verbrauch' : 'ausgeglichen'}${gegenlaeufig ? ', netto' : ''})`

  const key = gruppe.komp.key
  const p = praefix(key)
  const fuss = [
    p === 'batterie' && gruppe.ladestand != null
      ? `Ladestand der Gruppe ${gruppe.ladestand} %, gewichtet nach nutzbarer Kapazität.` : null,
    p === 'wallbox'
      ? 'Gruppenwert = Summe der Wallboxen. Die Autos zeigen denselben Strom aus Autosicht und werden nicht addiert.' : null,
    key === 'sonstige_grp_weitere'
      ? 'Letzte Stufe am Handy: nur Verbraucher, nie zusammen mit Erzeugern oder Speichern.' : null,
  ].filter((t): t is string => t != null)

  // Der Titel ist der echte Gruppentitel — er ist zugleich der zugängliche
  // Name des Dialogs (`aria-labelledby` → Überschrift).
  const titel = `${gruppe.komp.label} (${mitgliedsKeys.length})`

  return (
    <FokusVollbild titel={titel} icon={ICONS[gruppe.komp.icon]} dialog onClose={onClose}>
      <div className="h-full overflow-y-auto" data-gruppenliste={key}>
        <div className="max-w-2xl mx-auto flex flex-col gap-3">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            <span className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{gruppenArt(key)}</span>
            <span className="mx-2" aria-hidden="true">·</span>
            Summe: {summe}
          </p>
          <ul className="flex flex-col gap-2.5">
            {zeilen.map(z => {
              const anteil = maxKw > 0 ? z.kw / maxKw : 0
              return (
                // Spalten fest (Name 2 : Balken 3 : Wert 4,5rem) — jede Zeile ist ihr
                // eigenes Grid; nur so beginnen alle Balken an derselben Kante (mit
                // `max-content` rückte der Balken bei „900 W" gegenüber „1.900 W" ein,
                // Sichtprüfung 28.09.). Der Name bricht um statt abzuschneiden.
                <li key={z.key} data-zeile={z.key} className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_4.5rem] items-center gap-x-3 gap-y-1 text-sm">
                  <span className="font-semibold text-gray-900 dark:text-white break-words">{z.name}</span>
                  <span
                    role="img"
                    aria-label={`${z.name}: ${formatPower(z.kw)}, ${fmtZahl(anteil * 100, 0)} % des stärksten Geräts`}
                    className="h-2.5 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden"
                  >
                    <span
                      data-balken
                      className="block h-full rounded-full"
                      style={{ width: `${anteil * 100}%`, backgroundColor: z.farbe }}
                    />
                  </span>
                  <span className="font-semibold tabular-nums text-right text-gray-900 dark:text-white">{formatPower(z.kw)}</span>
                  {z.zusatz.length > 0 && (
                    <span data-zusatz className="col-span-3 -mt-1 text-xs text-gray-500 dark:text-gray-400">{z.zusatz.join(' · ')}</span>
                  )}
                </li>
              )
            })}
          </ul>
          {alleAutos.length > 0 && (
            <div data-autos className="text-sm text-gray-700 dark:text-gray-300">
              <p className="font-semibold">Autos</p>
              <ul className="mt-1 flex flex-col gap-0.5">
                {alleAutos.map(a => <li key={a.investition_id}>{autoText(a)}</li>)}
              </ul>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{SATZ_ZUORDNUNG_UNBEKANNT}</p>
            </div>
          )}
          {fuss.map(t => <p key={t} className="text-xs text-gray-500 dark:text-gray-400">{t}</p>)}
        </div>
      </div>
    </FokusVollbild>
  )
}
