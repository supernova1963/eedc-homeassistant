/**
 * Datei-Download via fetch + Blob + temporärer Anchor.
 *
 * Warum nicht `window.open(url)` oder `window.location.href = url`?
 * Die HA Companion-App (iOS/Android) öffnet `_blank`-Links extern in Safari/Chrome,
 * wo die HA-Ingress-Session nicht verfügbar ist → 401. Mit fetch+Blob bleibt
 * die HTTP-Anfrage in der iframe-Session (mit Ingress-Cookie) und der Download
 * geht als blob:-URL ins Filesystem — funktioniert in App + Browser gleich.
 */
/** Fehler von {@link downloadFile} mit dem HTTP-Status (z. B. 404 = Datei nicht mehr bereit); Meldung wie zuvor. */
export class DownloadFehler extends Error {
  status: number

  constructor(meldung: string, status: number) {
    super(meldung)
    this.name = 'DownloadFehler'
    this.status = status
  }
}

export async function downloadFile(url: string, filename: string): Promise<void> {
  const res = await fetch(url)
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new DownloadFehler(detail?.detail || `HTTP ${res.status}`, res.status)
  }
  const blob = await res.blob()
  const blobUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(blobUrl)
}

/**
 * Läuft eedc im Rahmen von Home Assistant (Ingress-Pfad oder eingebettet, z. B. Companion-App)? Dort öffnet ein
 * `_blank`-Fenster extern **ohne** Ingress-Sitzung ⇒ 401 (derselbe Grund wie oben). Genutzt vom Lösungsweg-Panel
 * (E3 Daten-Checker, Entscheid Konzept §11 Nr. 10): «In eigenem Fenster öffnen» nur außerhalb dieses Rahmens.
 */
export function istImHaRahmen(
  ort: Pick<Location, 'pathname'> = window.location, fenster: Pick<Window, 'self' | 'top'> = window,
): boolean {
  return ort.pathname.includes('/api/hassio_ingress/') || fenster.self !== fenster.top
}

/**
 * iPhone, iPad oder iPod — auch die Home-Assistant-App dort (`io.robbie.HomeAssistant`) und ein iPad, das sich als Mac
 * ausgibt (`Macintosh` mit Touch). Gemessen in der iPhone-App (Diagnose-Paket v4, S0 15.11.2026): eine direkte Navigation
 * auf eine Anhang-Adresse zeigt die Datei als Seite und lässt die Ansicht hängen; der Weg über {@link downloadFile}
 * speichert 1/10/21 MB. Auf Android und am Desktop speichert die Navigation.
 */
export function istAppleMobil(nav: Pick<Navigator, 'userAgent' | 'maxTouchPoints'> = navigator): boolean {
  const ua = nav.userAgent || ''
  if (/iPhone|iPad|iPod|io\.robbie\.HomeAssistant/.test(ua)) return true
  return ua.includes('Macintosh') && (nav.maxTouchPoints ?? 0) > 1
}
