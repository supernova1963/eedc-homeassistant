import { fetchApi } from './fetchApi'
/**
 * Cloud-Import API Client
 * Importiert historische Energiedaten aus Hersteller-Cloud-APIs.
 */

const API_BASE = './api'

export interface CredentialField {
  id: string
  label: string
  type: 'text' | 'password' | 'select'
  placeholder: string
  required: boolean
  options: { value: string; label: string }[]
}

export interface CloudProviderInfo {
  id: string
  name: string
  hersteller: string
  beschreibung: string
  anleitung: string
  credential_fields: CredentialField[]
  getestet: boolean
}

export interface CloudTestResult {
  erfolg: boolean
  geraet_name: string | null
  geraet_typ: string | null
  seriennummer: string | null
  verfuegbare_daten: string | null
  fehler: string | null
}

export interface CloudFetchedMonth {
  jahr: number
  monat: number
  pv_erzeugung_kwh: number | null
  einspeisung_kwh: number | null
  netzbezug_kwh: number | null
  batterie_ladung_kwh: number | null
  batterie_entladung_kwh: number | null
  eigenverbrauch_kwh: number | null
  wallbox_ladung_kwh: number | null
  wallbox_ladung_pv_kwh: number | null
  wallbox_ladevorgaenge: number | null
  eauto_km_gefahren: number | null
}

export interface CloudPreviewResult {
  provider: CloudProviderInfo
  monate: CloudFetchedMonth[]
  anzahl_monate: number
}

/** Eine gespeicherte Cloud-Quelle. `schluessel` ist die Adresse zum Löschen. */
export interface CloudQuelle {
  schluessel: string
  provider_id: string
  credentials: Record<string, string>
  ziel_investition_id: number | null
  ziel_bezeichnung: string | null
  bezeichnung: string | null
}

export interface CloudCredentials {
  /** Alt-Felder: beschreiben die ERSTE Quelle. Maßgeblich ist `quellen`. */
  provider_id: string | null
  credentials: Record<string, string>
  has_credentials: boolean
  quellen: CloudQuelle[]
}

// #261 FrodoVDR: kopierte API-Keys/Site-IDs haben oft Whitespace mit drin,
// SolarEdge antwortet dann mit 403. Vor jedem Cloud-Call trimmen.
function trimCredentials(credentials: Record<string, string>): Record<string, string> {
  const trimmed: Record<string, string> = {}
  for (const [key, value] of Object.entries(credentials)) {
    trimmed[key] = typeof value === 'string' ? value.trim() : value
  }
  return trimmed
}

export const cloudImportApi = {
  /**
   * Verfügbare Cloud-Import-Provider abrufen
   */
  async getProviders(): Promise<CloudProviderInfo[]> {
    const response = await fetchApi(`${API_BASE}/cloud-import/providers`)
    if (!response.ok) throw new Error('Fehler beim Laden der Provider')
    return response.json()
  },

  /**
   * Verbindung zur Cloud-API testen
   */
  async testConnection(
    providerId: string,
    credentials: Record<string, string>
  ): Promise<CloudTestResult> {
    const response = await fetchApi(`${API_BASE}/cloud-import/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_id: providerId, credentials: trimCredentials(credentials) }),
    })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Verbindungstest fehlgeschlagen')
    }
    return response.json()
  },

  /**
   * Monatsdaten aus der Cloud-API abrufen (Vorschau)
   */
  async fetchPreview(
    providerId: string,
    credentials: Record<string, string>,
    startYear: number,
    startMonth: number,
    endYear: number,
    endMonth: number
  ): Promise<CloudPreviewResult> {
    const response = await fetchApi(`${API_BASE}/cloud-import/fetch-preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider_id: providerId,
        credentials: trimCredentials(credentials),
        start_year: startYear,
        start_month: startMonth,
        end_year: endYear,
        end_month: endMonth,
      }),
    })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Datenabruf fehlgeschlagen')
    }
    return response.json()
  },

  /**
   * Monatsdaten als Hintergrund-Job abrufen + Status pollen (#328).
   *
   * Vermeidet "Failed to fetch" bei langen Zeiträumen: der Server startet den
   * Abruf im Hintergrund und gibt sofort eine job_id zurück; hier wird der
   * Status gepollt, bis fertig/fehler. `onPoll` feuert je laufendem Tick (für
   * eine Verlaufsanzeige), `signal` erlaubt Abbruch.
   */
  async fetchPreviewAsync(
    providerId: string,
    credentials: Record<string, string>,
    startYear: number,
    startMonth: number,
    endYear: number,
    endMonth: number,
    opts?: { onPoll?: () => void; signal?: AbortSignal; pollMs?: number }
  ): Promise<CloudPreviewResult> {
    const startResp = await fetchApi(`${API_BASE}/cloud-import/fetch-async`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider_id: providerId,
        credentials: trimCredentials(credentials),
        start_year: startYear,
        start_month: startMonth,
        end_year: endYear,
        end_month: endMonth,
      }),
      signal: opts?.signal,
    })
    if (!startResp.ok) {
      const error = await startResp.json().catch(() => ({}))
      throw new Error(error.detail || 'Datenabruf konnte nicht gestartet werden')
    }
    const { job_id: jobId } = await startResp.json()

    const pollMs = opts?.pollMs ?? 3000
    // eslint-disable-next-line no-constant-condition
    while (true) {
      if (opts?.signal?.aborted) throw new DOMException('Abgebrochen', 'AbortError')
      const statusResp = await fetchApi(
        `${API_BASE}/cloud-import/fetch-status/${jobId}`,
        { signal: opts?.signal }
      )
      if (!statusResp.ok) {
        const error = await statusResp.json().catch(() => ({}))
        throw new Error(error.detail || 'Status-Abruf fehlgeschlagen')
      }
      const data = await statusResp.json()
      if (data.status === 'done') return data.result as CloudPreviewResult
      if (data.status === 'error') {
        throw new Error(data.error || 'Datenabruf fehlgeschlagen')
      }
      opts?.onPoll?.()
      await new Promise((resolve) => setTimeout(resolve, pollMs))
    }
  },

  /**
   * Credentials an einer Anlage speichern
   */
  async saveCredentials(
    anlageId: number,
    providerId: string,
    credentials: Record<string, string>,
    /**
     * N-229 (#349): Misst dieses Konto nur EIN Gerät (Hersteller-Wolken führen
     * je Wechselrichter eine eigene „Station"), dann gehört seine ID hierher.
     * Mehrere Quellen liegen dann nebeneinander, statt sich zu verdrängen.
     * `null`/`undefined` = die Quelle beschreibt die ganze Anlage.
     */
    zielInvestitionId?: number | null
  ): Promise<{ erfolg: boolean; message: string; anzahl_quellen?: number }> {
    const response = await fetchApi(
      `${API_BASE}/cloud-import/save-credentials/${anlageId}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider_id: providerId,
          credentials: trimCredentials(credentials),
          ziel_investition_id: zielInvestitionId ?? null,
        }),
      }
    )
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Speichern fehlgeschlagen')
    }
    return response.json()
  },

  /**
   * Gespeicherte Credentials abrufen (Secrets maskiert)
   */
  async getCredentials(anlageId: number): Promise<CloudCredentials> {
    const response = await fetchApi(
      `${API_BASE}/cloud-import/credentials/${anlageId}`
    )
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Fehler beim Laden der Credentials')
    }
    return response.json()
  },

  /**
   * Credentials entfernen
   */
  async removeCredentials(
    anlageId: number,
    /** Schlüssel EINER Quelle (aus `getCredentials`). Ohne Angabe: alle. */
    quelle?: string
  ): Promise<{ erfolg: boolean; message: string; entfernt?: number }> {
    const query = quelle ? `?quelle=${encodeURIComponent(quelle)}` : ''
    const response = await fetchApi(
      `${API_BASE}/cloud-import/credentials/${anlageId}${query}`,
      { method: 'DELETE' }
    )
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Löschen fehlgeschlagen')
    }
    return response.json()
  },
}
