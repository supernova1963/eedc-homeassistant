/**
 * Einstellungs-Sperre — Ablage des Entsperr-Nachweises im Browser.
 *
 * Bewusst ohne Abhängigkeiten: `api/client.ts` liest hier, und `api/sperre.ts` schreibt
 * hier. Läge beides in einem Modul, hätten wir einen Zirkelbezug.
 *
 * **`sessionStorage`, nicht `localStorage`.** „Entsperrt bleibt es bis zum Schließen des
 * Browsers" ist genau die Zusage, die Mathek in #391 vorgeschlagen hat — und
 * `sessionStorage` ist diese Zusage, ohne dass wir eine Frist selbst verwalten müssten.
 * Ein neuer Tab beginnt gesperrt; das ist gewollt, nicht ein Versehen.
 *
 * Der Nachweis ist **kein Geheimnis im Sinne eines Passworts** — er ist ein signierter
 * Zettel „diese Sitzung hat die PIN gezeigt". Die PIN selbst verlässt das Eingabefeld
 * nie in Richtung Speicher.
 */

const SCHLUESSEL = 'eedc-sperre-nachweis'

/** Header-Name — muss mit `backend/core/sperre.py::HEADER` übereinstimmen. */
export const SPERRE_HEADER = 'X-EEDC-Entsperrt'

function speicher(): Storage | null {
  // In Testumgebungen und bei blockiertem Speicher (privater Modus mancher Browser)
  // darf das Fehlen der Ablage die Anwendung nicht anhalten — dann ist eben nichts
  // entsperrt, und der Dialog kommt eine Ebene später erneut.
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage
  } catch {
    return null
  }
}

export function nachweisLesen(): string | null {
  return speicher()?.getItem(SCHLUESSEL) ?? null
}

export function nachweisSetzen(nachweis: string): void {
  speicher()?.setItem(SCHLUESSEL, nachweis)
}

export function nachweisLoeschen(): void {
  speicher()?.removeItem(SCHLUESSEL)
}

/** Header für einen schreibenden Aufruf — leer, wenn nichts entsperrt ist. */
export function sperrHeader(): Record<string, string> {
  const nachweis = nachweisLesen()
  return nachweis ? { [SPERRE_HEADER]: nachweis } : {}
}

// ── Der Dialog, ohne dass der Client ihn kennen muss ────────────────────────
//
// `client.ts` soll bei einem 423 den Entsperr-Dialog öffnen können, ohne eine
// React-Komponente zu importieren. Die Anwendung meldet den Dialog hier an; der Client
// fragt nur „lass die Sitzung entsperren" und bekommt zurück, ob es geklappt hat.

type EntsperrDialog = () => Promise<boolean>

let dialog: EntsperrDialog | null = null

export function entsperrDialogAnmelden(fn: EntsperrDialog | null): void {
  dialog = fn
}

export async function entsperrungAnfordern(): Promise<boolean> {
  if (!dialog) return false
  try {
    return await dialog()
  } catch {
    return false
  }
}
