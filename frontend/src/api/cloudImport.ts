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

export interface CloudCredentials {
  provider_id: string | null
  credentials: Record<string, string>
  has_credentials: boolean
}

export const cloudImportApi = {
  /**
   * Verfügbare Cloud-Import-Provider abrufen
   */
  async getProviders(): Promise<CloudProviderInfo[]> {
    const response = await fetch(`${API_BASE}/cloud-import/providers`)
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
    const response = await fetch(`${API_BASE}/cloud-import/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_id: providerId, credentials }),
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
    const response = await fetch(`${API_BASE}/cloud-import/fetch-preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider_id: providerId,
        credentials,
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
   * Credentials an einer Anlage speichern
   */
  async saveCredentials(
    anlageId: number,
    providerId: string,
    credentials: Record<string, string>
  ): Promise<{ erfolg: boolean; message: string }> {
    const response = await fetch(
      `${API_BASE}/cloud-import/save-credentials/${anlageId}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_id: providerId, credentials }),
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
    const response = await fetch(
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
    anlageId: number
  ): Promise<{ erfolg: boolean; message: string }> {
    const response = await fetch(
      `${API_BASE}/cloud-import/credentials/${anlageId}`,
      { method: 'DELETE' }
    )
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Löschen fehlgeschlagen')
    }
    return response.json()
  },
}
