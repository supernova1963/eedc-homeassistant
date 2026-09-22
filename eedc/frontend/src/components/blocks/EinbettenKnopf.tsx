/**
 * EinbettenKnopf — „Link / Einbetten" in der Kopfzeile des Fokus/Vollbilds (FD-2).
 *
 * **Leitplanke 3 des Konzepts: Ein Anwender baut nie eine URL von Hand.** Wer
 * eine eedc-Anzeige in sein Home-Assistant-Dashboard holen will, öffnet sie im
 * Fokus, drückt hier und fügt die Adresse in eine **Webseiten-Karte**.
 *
 * Genau EINE Adresse (Entscheid Gernot 22.09.): Sicht-Pfad + `?fokus=<id>`,
 * dazu `&ansicht=tabelle`, wenn gerade die Tabellen-Ablesung offen ist. Kein
 * `kiosk=`, kein `theme=`, kein `zurueck=` — die Deep-Link-Ansicht IST die
 * Einbett-Form, und das Theme folgt dem Gerät.
 *
 * ⛔ **Zeitraum-Parameter kommen NICHT mit** (`datum`/`jahr`/`monat`/`h`): Der
 * Fokus der Bilanzen trägt seine Zeitraum-Auswahl selbst, eine Karte soll den
 * *laufenden* Monat zeigen und nicht den, der beim Kopieren offen war. Wer ein
 * festes Datum will, hängt es von Hand an — es läuft durch.
 */
import { useState } from 'react'
import { Link2, Check, Copy } from 'lucide-react'
import { Button, Modal } from '../ui'
import { useCopyFeedback } from '../../hooks/useCopyFeedback'

/** Nur die Teile von `window.location`, die hier gebraucht werden — als Typ,
 *  damit die Adresse ohne Browser prüfbar ist. */
export interface OrtAngaben {
  href: string
  hash: string
  pathname: string
}

/**
 * Die Deep-Link-Adresse dieser Anzeige — absolut, auf Basis der Adresse, unter
 * der eedc gerade läuft.
 *
 * Unter dem HA-Ingress ist das die Ingress-URL
 * (`…/api/hassio_ingress/<token>/#/…`) — genau die, die eine Webseiten-Karte auf
 * demselben HA-Origin laden darf.
 */
export function baueDeepLink(ort: OrtAngaben, fokusId: string, ansicht: 'chart' | 'tabelle'): string {
  const basis = ort.href.split('#')[0]
  const pfad = (ort.hash.split('?')[0] || '').replace(/^#/, '') || '/'
  const ansichtTeil = ansicht === 'tabelle' ? '&ansicht=tabelle' : ''
  return `${basis}#${pfad}?fokus=${encodeURIComponent(fokusId)}${ansichtTeil}`
}

/** Läuft eedc gerade als HA-Add-on hinter dem Ingress? */
export function istIngress(ort: Pick<OrtAngaben, 'pathname'>): boolean {
  return ort.pathname.includes('/api/hassio_ingress/')
}

export function EinbettenKnopf({ fokusId, ansicht, ort = window.location }: {
  /** Fokus-ID dieser Anzeige (Block-`id` bzw. Kachel-`fokusId`). */
  fokusId: string
  /** Aktuelle Ablesung im Overlay — entscheidet über `&ansicht=tabelle`. */
  ansicht: 'chart' | 'tabelle'
  /** Nur für Proben: gestellte Adresse statt `window.location`. */
  ort?: OrtAngaben
}) {
  const [offen, setOffen] = useState(false)
  const { istKopiert, kopiere } = useCopyFeedback()
  const adresse = baueDeepLink(ort, fokusId, ansicht)

  return (
    <>
      <Button variant="secondary" size="sm" onClick={() => setOffen(true)}>
        <Link2 className="h-4 w-4 mr-2 max-sm:hidden" /> Link / Einbetten
      </Button>
      <Modal isOpen={offen} onClose={() => setOffen(false)} title="Link / Einbetten">
        <div className="space-y-3">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Diese Adresse öffnet genau diese Anzeige — ohne die übrige Sicht.
          </p>
          <div className="flex items-start gap-2">
            <code className="flex-1 min-w-0 break-all rounded-lg bg-gray-100 dark:bg-gray-900 px-3 py-2 text-xs text-gray-800 dark:text-gray-200">
              {adresse}
            </code>
            <Button variant="secondary" size="sm" onClick={() => kopiere(adresse)}>
              {istKopiert()
                ? <><Check className="h-4 w-4 mr-2 max-sm:hidden" /> kopiert</>
                : <><Copy className="h-4 w-4 mr-2 max-sm:hidden" /> kopieren</>}
            </Button>
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            In Home Assistant: <strong>Dashboard bearbeiten → Karte hinzufügen → Webseite →
            Adresse einfügen</strong>. Die Karte zeigt nur diese Anzeige, ohne Zurück; das
            Theme folgt dem Gerät.
          </p>
          {!istIngress(ort) && (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Hinweis zum Standalone-Betrieb: Läuft eedc über HTTP und Home Assistant über
              HTTPS, blockt der Browser die Einbettung (Mixed Content). Der Link funktioniert
              dann direkt im Browser, aber nicht als Karte.
            </p>
          )}
        </div>
      </Modal>
    </>
  )
}

export default EinbettenKnopf
