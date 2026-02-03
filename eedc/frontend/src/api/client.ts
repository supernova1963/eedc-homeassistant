/**
 * API Client für EEDC Backend
 *
 * Zentraler HTTP-Client mit Error Handling und TypeScript Support.
 */

const API_BASE = '/api'

interface ApiError {
  detail: string
  status: number
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
      const error: ApiError = {
        detail: 'Ein Fehler ist aufgetreten',
        status: response.status,
      }

      try {
        const data = await response.json()
        error.detail = data.detail || error.detail
      } catch {
        // JSON parsing failed, use default error
      }

      throw error
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
  async delete(endpoint: string): Promise<void> {
    return this.request<void>(endpoint, { method: 'DELETE' })
  }

  // File Upload
  async upload<T>(endpoint: string, file: File, fieldName: string = 'file'): Promise<T> {
    const formData = new FormData()
    formData.append(fieldName, file)

    return this.request<T>(endpoint, {
      method: 'POST',
      headers: {}, // Let browser set Content-Type for multipart
      body: formData,
    })
  }
}

// Singleton instance
export const api = new ApiClient()
export type { ApiError }
