// Gemeinsame Types für Auswertungs-Tabs
import type { useAnlagen, useAggregierteStats } from '../../hooks'
import type { AggregierteMonatsdaten } from '../../api/monatsdaten'
import type { Strompreis } from '../../types'
import {
  MONAT_KURZ, TYP_LABELS, CO2_FAKTOR_KG_KWH,
  COLORS, CHART_COLORS, TYP_COLORS,
  calcAutarkie, calcEigenverbrauchsquote, calcSpezifischerErtrag,
  calcSpeicherEffizienz, calcCOP,
} from '../../lib'

// Re-Export für Rückwärtskompatibilität (bestehende Imports brechen nicht)
export { COLORS, CHART_COLORS, TYP_COLORS, TYP_LABELS }
export const monatNamen = MONAT_KURZ

// Tab Props - verwendet jetzt aggregierte Daten mit korrekter PV-Erzeugung
export interface TabProps {
  data: AggregierteMonatsdaten[]
  stats: ReturnType<typeof useAggregierteStats>
  anlage?: ReturnType<typeof useAnlagen>['anlagen'][0]
  strompreis?: Strompreis | null
  alleTarife?: Strompreis[]
  zeitraumLabel?: string  // z.B. "2025" oder "2023–2025"
}

// Interface für Monatsdaten-Zeitreihen
export interface MonatsZeitreihe {
  name: string  // z.B. "Jan 24"
  jahr: number
  monat: number
  // Energie
  erzeugung: number
  eigenverbrauch: number
  einspeisung: number
  netzbezug: number
  gesamtverbrauch: number
  direktverbrauch: number
  // Quoten
  autarkie: number
  evQuote: number
  spezErtrag: number
  // Speicher
  speicher_ladung: number
  speicher_entladung: number
  speicher_effizienz: number | null
  // Wärmepumpe
  wp_waerme: number
  wp_strom: number
  wp_cop: number | null
  // E-Auto
  eauto_km: number
  eauto_ladung: number
  eauto_pv_anteil: number | null
  // Finanzen
  einspeise_erloes: number
  ev_ersparnis: number
  netzbezug_kosten: number
  netto_ertrag: number
  // CO2
  co2_einsparung: number
}

/**
 * Findet den zum Stichtag (1. des Monats) gültigen Tarif.
 * Tarife sind nach gueltig_ab DESC sortiert → erster Treffer gewinnt.
 */
function findGueltigerTarif(tarife: Strompreis[], jahr: number, monat: number): Strompreis | null {
  const stichtag = `${jahr}-${String(monat).padStart(2, '0')}-01`
  for (const t of tarife) {
    if (t.gueltig_ab <= stichtag && (!t.gueltig_bis || t.gueltig_bis >= stichtag)) {
      return t
    }
  }
  return null
}

// Helper-Funktion zum Erstellen der Monatszeitreihen
// Verwendet jetzt AggregierteMonatsdaten mit korrekter PV-Erzeugung aus InvestitionMonatsdaten
export function createMonatsZeitreihe(
  data: AggregierteMonatsdaten[],
  anlage?: TabProps['anlage'],
  strompreis?: Strompreis | null,
  alleTarife?: Strompreis[],
): MonatsZeitreihe[] {
  // Tarife nach gueltig_ab DESC sortieren für findGueltigerTarif
  const tarifeDesc = alleTarife?.length
    ? [...alleTarife].sort((a, b) => b.gueltig_ab.localeCompare(a.gueltig_ab))
    : []

  const sorted = [...data].sort((a, b) => {
    if (a.jahr !== b.jahr) return a.jahr - b.jahr
    return a.monat - b.monat
  })

  return sorted.map(md => {
    // PV-Erzeugung kommt jetzt korrekt aus InvestitionMonatsdaten (aggregiert)
    const erzeugung = md.pv_erzeugung_kwh || 0
    const eigenverbrauch = md.eigenverbrauch_kwh || 0
    const gesamtverbrauch = md.gesamtverbrauch_kwh || (eigenverbrauch + md.netzbezug_kwh)
    const direktverbrauch = md.direktverbrauch_kwh || 0

    // Quoten berechnen - direkt aus aggregierten Daten oder berechnet
    const autarkie = md.autarkie_prozent ?? calcAutarkie(eigenverbrauch, gesamtverbrauch)
    const evQuote = md.eigenverbrauchsquote_prozent ?? calcEigenverbrauchsquote(eigenverbrauch, erzeugung)
    const spezErtrag = calcSpezifischerErtrag(erzeugung, anlage?.leistung_kwp)

    // Speicher - jetzt aus aggregierten InvestitionMonatsdaten
    const speicher_ladung = md.speicher_ladung_kwh || 0
    const speicher_entladung = md.speicher_entladung_kwh || 0
    const speicher_effizienz = calcSpeicherEffizienz(speicher_entladung, speicher_ladung)

    // Wärmepumpe - aus aggregierten InvestitionMonatsdaten
    const wp_waerme = (md.wp_heizung_kwh || 0) + (md.wp_warmwasser_kwh || 0)
    const wp_strom = md.wp_strom_kwh || 0
    const wp_cop = calcCOP(wp_waerme, wp_strom)

    // E-Auto - aus aggregierten InvestitionMonatsdaten
    const eauto_km = md.eauto_km || 0
    const eauto_ladung = md.eauto_ladung_kwh || 0
    const eauto_pv_anteil = null // Wird später berechnet wenn PV-Anteil verfügbar

    // Finanzen: historisch korrekter Tarif pro Monat, Fallback auf aktuellen
    const tarif = (tarifeDesc.length > 0 ? findGueltigerTarif(tarifeDesc, md.jahr, md.monat) : null) || strompreis
    const einspeise_erloes = tarif
      ? md.einspeisung_kwh * tarif.einspeiseverguetung_cent_kwh / 100
      : 0
    const ev_ersparnis = tarif
      ? eigenverbrauch * tarif.netzbezug_arbeitspreis_cent_kwh / 100
      : 0
    const netzbezug_kosten = tarif
      ? md.netzbezug_kwh * tarif.netzbezug_arbeitspreis_cent_kwh / 100 + (tarif.grundpreis_euro_monat || 0)
      : 0
    const netto_ertrag = einspeise_erloes + ev_ersparnis

    // CO2
    const co2_einsparung = erzeugung * CO2_FAKTOR_KG_KWH

    return {
      name: `${MONAT_KURZ[md.monat]} ${md.jahr.toString().slice(-2)}`,
      jahr: md.jahr,
      monat: md.monat,
      erzeugung,
      eigenverbrauch,
      einspeisung: md.einspeisung_kwh,
      netzbezug: md.netzbezug_kwh,
      gesamtverbrauch,
      direktverbrauch,
      autarkie,
      evQuote,
      spezErtrag,
      speicher_ladung,
      speicher_entladung,
      speicher_effizienz,
      wp_waerme,
      wp_strom,
      wp_cop,
      eauto_km,
      eauto_ladung,
      eauto_pv_anteil,
      einspeise_erloes,
      ev_ersparnis,
      netzbezug_kosten,
      netto_ertrag,
      co2_einsparung,
    }
  })
}
