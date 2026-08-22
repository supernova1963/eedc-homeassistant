/**
 * `fetch` für eedc-Endpunkte — mit Entsperr-Nachweis und 423-Behandlung.
 *
 * **Warum es das gibt.** Der Löwenanteil der Aufrufe läuft über `api/client.ts`; dort
 * sitzt dieselbe Logik. Einige Module sprechen `fetch` aber direkt an, weil sie
 * `FormData` hochladen, Fortschritt lesen oder eigene Abbruch-Signale führen — für die
 * ist dies der gemeinsame Ersatz. Die Signatur ist absichtlich die von `fetch`, damit
 * die Umstellung ein Umbenennen ist und keine Umschreibung.
 *
 * **Warum nicht `window.fetch` global ersetzen.** Das wäre eine Zeile weniger und eine
 * unsichtbare Wahrheit mehr: Jeder künftige Leser müsste erst herausfinden, dass ein
 * Aufruf unterwegs verändert wird. Stattdessen ein benannter Helfer plus ein Wächter,
 * der rohe schreibende `fetch`-Aufrufe meldet (`npm run check:sperre-fetch`).
 */

import { entsperrungAnfordern, sperrHeader } from '../lib/sperreSpeicher'

const GESPERRT = 423

const SCHREIB_VERBEN = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

function istSchreibend(init?: RequestInit): boolean {
  return SCHREIB_VERBEN.has((init?.method ?? 'GET').toUpperCase())
}

export async function fetchApi(
  eingabe: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const mitNachweis: RequestInit = istSchreibend(init)
    ? { ...init, headers: { ...sperrHeader(), ...(init?.headers ?? {}) } }
    : (init ?? {})

  const antwort = await fetch(eingabe, mitNachweis)

  if (antwort.status !== GESPERRT || !istSchreibend(init)) {
    return antwort
  }

  // Einmal den Dialog anbieten und denselben Aufruf wiederholen — nicht öfter, sonst
  // dreht er sich im Kreis, falls der Nachweis serverseitig nicht angenommen wird.
  if (!(await entsperrungAnfordern())) {
    return antwort
  }

  return fetch(eingabe, {
    ...init,
    headers: { ...sperrHeader(), ...(init?.headers ?? {}) },
  })
}
