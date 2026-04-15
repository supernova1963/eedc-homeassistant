/**
 * API Client für EEDC Backend
 *
 * Zentraler HTTP-Client mit Error Handling und TypeScript Support.
 * Verwendet relative Pfade für HA Ingress Kompatibilität.
 */

// Relative Basis-URL für HA Ingress Support
// './api' wird relativ zur aktuellen Seite aufgelöst
const API_BASE = './api'

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
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`

    const config: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    }

    const response = await fetch(url, config)

    if (!response.ok) {
      let detail = 'Ein Fehler ist aufgetreten'

      try {
        const data = await response.json()
        if (typeof data.detail === 'string') {
          detail = data.detail
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
  async get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' })
  }

  // POST Request
  async post<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
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
