/**
 * B4 (05.09.2026, C-1) — das Jahr trägt die Wärmepumpen-Kennzahlen aus der Jahresroute.
 *
 * Bis B4 baute `baueJahrAlsMonat` das Jahr allein aus den Monatsantworten und verlor
 * dabei 16 von 33 WP-Feldern: Arbeitszahl, Grund, Hinweis, Herkunft, die drei
 * je-Funktion-Zeilen, Kühlen, Lüften/Entfeuchten, Grundmenge. In *Cockpit → Jahr* stand
 * die JAZ als „—" ohne Grund, die Zeilen fehlten ersatzlos (N-348-Klasse), und die
 * Restmenge rechnete ohne E4 (50 statt 35). Die Jahresroute (`getUebersicht(jahr)`)
 * rechnet all das im Layer — sie ist die eine Quelle (SOLL §3.3, ADR-002/P12).
 *
 * Schwesterdateien: JahrAggregat.preise.test.tsx (dieselbe Funktion, Tarif-Zeile),
 * KomponentenSektionen.b4.test.tsx (die Blockfabrik zeigt Herkunft und Vorbehalt).
 */
import { describe, it, expect } from 'vitest'
import { baueJahrAlsMonat } from './JahrAggregat'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { CockpitUebersicht } from '../api/cockpit'

const monat = (m: number, felder: Partial<AktuellerMonatResponse>) =>
  ({ jahr: 2025, monat: m, ...felder } as unknown as AktuellerMonatResponse)

const MONATE = [monat(7, {
  hat_waermepumpe: true, wp_strom_kwh: 1000, wp_waerme_kwh: 3500, wp_heizung_kwh: 3500,
  wp_modus_strom_heizen_kwh: 700, wp_modus_strom_kuehlen_kwh: 250,
  wp_modus_strom_lueften_kwh: 10, wp_modus_strom_entfeuchten_kwh: 5, wp_modus_abdeckung_h: 0,
  wp_modus_gemessen: true,
} as Partial<AktuellerMonatResponse>)]

const ROUTE = {
  wp_cop: 3.5, wp_cop_grund: null, wp_cop_hinweis: 'HEIZSTAB', wp_jaz_zaehler_kwh: 3500, wp_jaz_nenner_kwh: 735,
  wp_waerme_abgeleitet: false, wp_waerme_herkunft: 'gemessen', wp_ersparnis_vorbehalt: null,
  wp_jaz_heizen: null, wp_jaz_heizen_grund: 'Strom nicht getrennt je Funktion gemessen',
  wp_jaz_warmwasser: null, wp_jaz_warmwasser_grund: 'Strom nicht getrennt je Funktion gemessen',
  wp_jaz_kuehlen: 3.0, wp_jaz_kuehlen_grund: null,
  wp_modus_strom_lueften_kwh: 10, wp_modus_strom_entfeuchten_kwh: 5, wp_modus_strom_bezug_kwh: 1000,
  wp_modus_nicht_aufgeteilt_kwh: 35,
} as unknown as CockpitUebersicht

describe('B4/C-1 — baueJahrAlsMonat trägt die Kennzahlen der Jahresroute', () => {
  it('Arbeitszahl, Grund, Hinweis, je Funktion, Kühlen und Herkunft kommen aus der Route', () => {
    const j = baueJahrAlsMonat(MONATE, 2025, ROUTE)
    expect(j.wp_jaz).toBe(3.5)
    expect(j.wp_jaz_hinweis).toBe('HEIZSTAB')
    expect(j.wp_jaz_zaehler_kwh).toBe(3500)
    expect(j.wp_jaz_nenner_kwh).toBe(735)
    expect(j.wp_jaz_heizen_grund).toBe('Strom nicht getrennt je Funktion gemessen')
    expect(j.wp_jaz_kuehlen).toBe(3.0)
    expect(j.wp_waerme_herkunft).toBe('gemessen')
    // Die Mengen bleiben Summen der Monate (identisch mit der Route).
    expect(j.wp_strom_kwh).toBe(1000)
    expect(j.wp_modus_strom_heizen_kwh).toBe(700)
  })

  it('die Restmenge kommt aus dem Layer — mit Lüften/Entfeuchten (E4): 35, nicht 50', () => {
    const j = baueJahrAlsMonat(MONATE, 2025, ROUTE)
    expect(j.wp_modus_nicht_aufgeteilt_kwh).toBe(35)
    expect(j.wp_modus_strom_lueften_kwh).toBe(10)
    expect(j.wp_modus_strom_bezug_kwh).toBe(1000)
  })

  it('ohne Route (älterer Server, Abruf gescheitert): Mengen ja, Kennzahlen „—" ohne erfundene Zahl', () => {
    const j = baueJahrAlsMonat(MONATE, 2025, null)
    expect(j.wp_jaz).toBeNull()
    expect(j.wp_jaz_kuehlen).toBeNull()
    expect(j.wp_strom_kwh).toBe(1000)
    // Der alte Client-Rest bleibt als Fallback stehen — er kannte E4 nie (50).
    expect(j.wp_modus_nicht_aufgeteilt_kwh).toBe(50)
  })
})
