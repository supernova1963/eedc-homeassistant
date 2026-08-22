/**
 * API Client für eedc Backend
 *
 * Zentraler HTTP-Client mit Error Handling und TypeScript Support.
 * Verwendet relative Pfade für HA Ingress Kompatibilität.
 */

import { entsperrungAnfordern, sperrHeader } from '../lib/sperreSpeicher'

// Relative Basis-URL für HA Ingress Support
// './api' wird relativ zur aktuellen Seite aufgelöst
const API_BASE = './api'

/**
 * Antwort-Code der Einstellungs-Sperre.
 *
 * Bewusst 423 und nicht 403: Ein 403 hat in dieser Anwendung andere Ursachen, und der
 * Entsperr-Dialog soll nur bei genau diesem einen Fall aufgehen.
 */
const GESPERRT = 423

class ApiError extends Error {
  status: number

  constructor(detail: string, status: number) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
  }
}

class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    schonWiederholt = false,
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`

    const config: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        ...sperrHeader(),
        ...options.headers,
      },
      ...options,
    }

    const response = await fetch(url, config)

    // Einstellungs-Sperre: einmal den Dialog anbieten, dann denselben Aufruf
    // wiederholen. Nur EIN Wiederholungsversuch — sonst dreht sich der Aufruf im
    // Kreis, wenn der Nachweis serverseitig nicht angenommen wird.
    if (response.status === GESPERRT && !schonWiederholt) {
      if (await entsperrungAnfordern()) {
        return this.request<T>(endpoint, options, true)
      }
    }

    if (!response.ok) {
      let detail = 'Ein Fehler ist aufgetreten'

      try {
        const data = await response.json()
        if (typeof data.detail === 'string') {
          detail = data.detail
        } else if (Array.isArray(data.detail)) {
          // FastAPI/Pydantic-Validierungsfehler: lesbare Meldung statt rohem JSON.
          // Jeder Eintrag hat msg + loc (z. B. ["body", "bezeichnung"]).
          const msgs = data.detail
            .map((err: { msg?: string; loc?: (string | number)[] }) => {
              const field = Array.isArray(err.loc) ? err.loc[err.loc.length - 1] : undefined
              return field && field !== 'body' ? `${field}: ${err.msg}` : err.msg
            })
            .filter(Boolean)
          detail = msgs.length > 0 ? msgs.join('; ') : 'Eingabe ungültig'
        } else if (data.detail) {
          detail = JSON.stringify(data.detail)
        }
      } catch {
        // JSON parsing failed, use default error
      }

      throw new ApiError(detail, response.status)
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return undefined as T
    }

    return response.json()
  }

  // GET Request
  async get<T>(endpoint: string, options?: { signal?: AbortSignal }): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET', signal: options?.signal })
  }

  // POST Request
  async post<T>(endpoint: string, data?: unknown, options?: { signal?: AbortSignal }): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
      signal: options?.signal,
    })
  }

  // PUT Request
  async put<T>(endpoint: string, data: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  }

  // DELETE Request
  async delete<T = void>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' })
  }

  // PATCH Request
  async patch<T>(endpoint: string, data: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  }

  // File Upload
  async upload<T>(
    endpoint: string,
    file: File,
    fieldName: string = 'file',
    extraFields?: Record<string, string | undefined | null>,
  ): Promise<T> {
    const formData = new FormData()
    formData.append(fieldName, file)
    if (extraFields) {
      for (const [key, value] of Object.entries(extraFields)) {
        if (value !== undefined && value !== null && value !== '') {
          formData.append(key, value)
        }
      }
    }

    return this.request<T>(endpoint, {
      method: 'POST',
      headers: {}, // Let browser set Content-Type for multipart
      body: formData,
    })
  }
}

// Singleton instance
export const api = new ApiClient()
export { ApiError }
