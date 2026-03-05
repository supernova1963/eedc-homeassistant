/**
 * Connector API Client
 * Direkte Verbindung zu Wechselrichtern über lokale REST-API.
 */

const API_BASE = './api'

export interface ConnectorInfo {
  id: string
  name: string
  hersteller: string
  beschreibung: string
  anleitung: string
  getestet: boolean
}

export interface MeterSnapshot {
  timestamp: string
  pv_erzeugung_kwh: number | null
  einspeisung_kwh: number | null
  netzbezug_kwh: number | null
  batterie_ladung_kwh: number | null
  batterie_entladung_kwh: number | null
}

export interface ConnectionTestResult {
  erfolg: boolean
  geraet_name: string | null
  geraet_typ: string | null
  seriennummer: string | null
  firmware: string | null
  verfuegbare_sensoren: string[]
  aktuelle_werte: MeterSnapshot | null
  fehler: string | null
}

export interface ConnectorStatus {
  configured: boolean
  connector_id?: string
  host?: string
  username?: string
  geraet_name?: string
  geraet_typ?: string
  seriennummer?: string
  firmware?: string
  auto_fetch_enabled?: boolean
  last_fetch?: string
  snapshot_count?: number
  latest_snapshot?: MeterSnapshot | null
}

export interface SetupResult {
  erfolg: boolean
  geraet_name: string | null
  seriennummer: string | null
  aktuelle_werte: MeterSnapshot | null
}

export interface FetchResult {
  snapshot: MeterSnapshot
  differenz: Record<string, number> | null
  timestamp: string
}

export const connectorApi = {
  /**
   * Verfügbare Connector-Typen abrufen
   */
  async getConnectors(): Promise<ConnectorInfo[]> {
    const response = await fetch(`${API_BASE}/connectors`)
    if (!response.ok) throw new Error('Fehler beim Laden der Connectoren')
    return response.json()
  },

  /**
   * Verbindung testen (ohne zu speichern)
   */
  async testConnection(
    connectorId: string,
    host: string,
    username: string,
    password: string
  ): Promise<ConnectionTestResult> {
    const response = await fetch(`${API_BASE}/connectors/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        connector_id: connectorId,
        host,
        username,
        password,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Verbindungstest fehlgeschlagen')
    }

    return response.json()
  },

  /**
   * Connector für eine Anlage einrichten
   */
  async setup(
    anlageId: number,
    connectorId: string,
    host: string,
    username: string,
    password: string
  ): Promise<SetupResult> {
    const response = await fetch(`${API_BASE}/connectors/setup/${anlageId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        connector_id: connectorId,
        host,
        username,
        password,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Einrichtung fehlgeschlagen')
    }

    return response.json()
  },

  /**
   * Connector-Status einer Anlage abrufen
   */
  async getStatus(anlageId: number): Promise<ConnectorStatus> {
    const response = await fetch(`${API_BASE}/connectors/status/${anlageId}`)
    if (!response.ok) throw new Error('Fehler beim Laden des Connector-Status')
    return response.json()
  },

  /**
   * Zählerstand manuell vom Gerät ablesen
   */
  async fetch(anlageId: number): Promise<FetchResult> {
    const response = await fetch(`${API_BASE}/connectors/fetch/${anlageId}`, {
      method: 'POST',
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Ablesung fehlgeschlagen')
    }

    return response.json()
  },

  /**
   * Connector-Konfiguration entfernen
   */
  async remove(anlageId: number): Promise<void> {
    const response = await fetch(`${API_BASE}/connectors/${anlageId}`, {
      method: 'DELETE',
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Entfernen fehlgeschlagen')
    }
  },

  /**
   * Monatswerte aus Connector-Snapshots berechnen (für Monatsabschluss-Prefill)
   */
  async getMonatswerte(
    anlageId: number,
    jahr: number,
    monat: number
  ): Promise<ConnectorMonatswerte> {
    const response = await fetch(`${API_BASE}/connectors/monatswerte/${anlageId}/${jahr}/${monat}`)

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Keine Connector-Daten für diesen Monat')
    }

    return response.json()
  },
}

export interface ConnectorMonatswertFeld {
  feld: string
  label: string
  wert: number
  einheit: string
}

export interface ConnectorInvestitionWerte {
  investition_id: number
  bezeichnung: string
  typ: string
  felder: ConnectorMonatswertFeld[]
}

export interface ConnectorMonatswerte {
  basis: ConnectorMonatswertFeld[]
  investitionen: ConnectorInvestitionWerte[]
}
