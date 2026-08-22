/**
 * Einstellungs-Sperre — API-Anbindung.
 *
 * Die PIN geht nur in eine Richtung: hin. Zurück kommt ein Nachweis, dass diese Sitzung
 * sie einmal gezeigt hat. Gespeichert wird nie die PIN, weder hier noch im Backend.
 */

import { api } from './client'
import { nachweisLoeschen, nachweisSetzen } from '../lib/sperreSpeicher'

export interface SperreStatus {
  pin_gesetzt: boolean
  entsperrt: boolean
  mindest_laenge: number
}

export const sperreApi = {
  status(): Promise<SperreStatus> {
    return api.get<SperreStatus>('/sperre/status')
  },

  /** Prüft die PIN und legt den Nachweis für diese Browser-Sitzung ab. */
  async entsperren(pin: string): Promise<void> {
    const { nachweis } = await api.post<{ nachweis: string }>('/sperre/entsperren', {
      pin,
    })
    nachweisSetzen(nachweis)
  },

  /** Wieder sperren — der Nachweis wird hier verworfen, nicht serverseitig. */
  async sperren(): Promise<void> {
    nachweisLoeschen()
    await api.post('/sperre/sperren')
  },

  /** Erste PIN setzen oder eine bestehende ändern. */
  setzePin(pin: string): Promise<{ erfolg: boolean }> {
    return api.post<{ erfolg: boolean }>('/sperre/pin', { pin })
  },

  /** PIN entfernen — danach ist wieder alles offen. */
  async entfernePin(): Promise<void> {
    await api.delete('/sperre/pin')
    nachweisLoeschen()
  },
}
