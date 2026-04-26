/**
 * Datei-Download via fetch + Blob + temporärer Anchor.
 *
 * Warum nicht `window.open(url)` oder `window.location.href = url`?
 * Die HA Companion-App (iOS/Android) öffnet `_blank`-Links extern in Safari/Chrome,
 * wo die HA-Ingress-Session nicht verfügbar ist → 401. Mit fetch+Blob bleibt
 * die HTTP-Anfrage in der iframe-Session (mit Ingress-Cookie) und der Download
 * geht als blob:-URL ins Filesystem — funktioniert in App + Browser gleich.
 */
export async function downloadFile(url: string, filename: string): Promise<void> {
  const res = await fetch(url)
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail || `HTTP ${res.status}`)
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
