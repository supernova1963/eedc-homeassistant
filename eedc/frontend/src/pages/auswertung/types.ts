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
  // Wetter (Einstrahlungs-Kontext) — null = keine Wetterdaten in dem Monat
  globalstrahlung: number | null
  sonnenstunden: number | null
  // Speicher — null = keine aktive Speicher-Komponente in dem Monat
  speicher_ladung: number | null
  speicher_entladung: number | null
  speicher_effizienz: number | null
  // Wärmepumpe — null = keine aktive WP in dem Monat (vor Anschaffung / nach Stilllegung)
  wp_waerme: number | null
  wp_strom: number | null
  wp_cop: number | null
  // WP-Split — Strom nur bei getrennter Strommessung (#191), Wärme aus IMD
  wp_strom_heizen: number | null
  wp_strom_warmwasser: number | null
  wp_waerme_heizen: number | null
  wp_waerme_warmwasser: number | null
  // E-Auto — null = kein aktives E-Auto in dem Monat
  eauto_km: number | null
  eauto_ladung: number | null
  eauto_pv_anteil: number | null
  // Wallbox — Durchsatz + PV-Anteil (null = keine Wallbox / nicht gemessen)
  wallbox_ladung: number | null
  wallbox_pv_ladung: number | null
  wallbox_pv_anteil: number | null
  // Finanzen
  einspeise_erloes: number
  ev_ersparnis: number
  netzbezug_kosten: number
  netto_ertrag: number
  netto_bilanz: number
  /** Real verrechneter Monats-Ø-Netzbezugspreis (Flex-Ø oder statischer Tarif, #326). */
  netzbezug_preis_cent: number | null
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

    // Speicher: null = keine Speicher-Komponente aktiv (Backend liefert null).
    // calcSpeicherEffizienz arbeitet auf 0-Default — null-Werte als 0 hineingeben
    // ergibt null Effizienz (kein Ladestrom).
    const speicher_ladung = md.speicher_ladung_kwh
    const speicher_entladung = md.speicher_entladung_kwh
    const speicher_effizienz = (speicher_ladung != null && speicher_entladung != null)
      ? calcSpeicherEffizienz(speicher_entladung, speicher_ladung)
      : null

    // Wärmepumpe: null = WP in dem Monat nicht aktiv. Wenn auch nur eines
    // der Komponenten-Felder null ist, gilt der ganze Block als nicht aktiv.
    const wp_heizung = md.wp_heizung_kwh
    const wp_warmwasser = md.wp_warmwasser_kwh
    const wp_waerme = (wp_heizung != null && wp_warmwasser != null)
      ? wp_heizung + wp_warmwasser
      : null
    const wp_strom = md.wp_strom_kwh
    const wp_cop = (wp_waerme != null && wp_strom != null)
      ? calcCOP(wp_waerme, wp_strom)
      : null
    // WP-Split: Strom-Heizen/WW nur bei getrennter Strommessung (#191), Wärme aus IMD.
    const wp_strom_heizen = md.wp_strom_heizen_kwh
    const wp_strom_warmwasser = md.wp_strom_warmwasser_kwh
    const wp_waerme_heizen = wp_heizung
    const wp_waerme_warmwasser = wp_warmwasser

    // E-Auto: null = kein aktives E-Auto.
    const eauto_km = md.eauto_km
    const eauto_ladung = md.eauto_ladung_kwh
    // Wallbox-Durchsatz + PV-Anteil (PV-Anteil ableitbar aus den beiden Roh-Feldern).
    const wallbox_ladung = md.wallbox_ladung_kwh
    const wallbox_pv_ladung = md.wallbox_ladung_pv_kwh
    const wallbox_pv_anteil = (wallbox_pv_ladung != null && wallbox_ladung != null && wallbox_ladung > 0)
      ? (wallbox_pv_ladung / wallbox_ladung) * 100
      : null
    const eauto_pv_anteil = wallbox_pv_anteil // gleicher PV-Anteil (Wallbox = Lade-Pfad des E-Autos)

    // Finanzen: historisch korrekter Tarif pro Monat, Fallback auf aktuellen
    const tarif = (tarifeDesc.length > 0 ? findGueltigerTarif(tarifeDesc, md.jahr, md.monat) : null) || strompreis
    // Netzbezugspreis: bei Flex-Tarif den aufgezeichneten Monats-Ø nutzen,
    // sonst den statischen Tarif — gleiche SoT-Quelle wie das Cockpit
    // (resolve_netzbezug_preis_cent), sonst driften die €-Werte auseinander (#326).
    const netzPreisCent = md.netzbezug_durchschnittspreis_cent ?? (tarif ? tarif.netzbezug_arbeitspreis_cent_kwh : null)
    const einspeise_erloes = tarif
      ? md.einspeisung_kwh * tarif.einspeiseverguetung_cent_kwh / 100
      : 0
    const ev_ersparnis = netzPreisCent != null
      ? eigenverbrauch * netzPreisCent / 100
      : 0
    const netzbezug_kosten = netzPreisCent != null
      ? md.netzbezug_kwh * netzPreisCent / 100 + (tarif?.grundpreis_euro_monat || 0)
      : 0
    const netto_ertrag = einspeise_erloes + ev_ersparnis
    const netto_bilanz = einspeise_erloes + ev_ersparnis - netzbezug_kosten

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
      globalstrahlung: md.globalstrahlung_kwh_m2,
      sonnenstunden: md.sonnenstunden,
      speicher_ladung,
      speicher_entladung,
      speicher_effizienz,
      wp_waerme,
      wp_strom,
      wp_cop,
      wp_strom_heizen,
      wp_strom_warmwasser,
      wp_waerme_heizen,
      wp_waerme_warmwasser,
      eauto_km,
      eauto_ladung,
      eauto_pv_anteil,
      wallbox_ladung,
      wallbox_pv_ladung,
      wallbox_pv_anteil,
      einspeise_erloes,
      ev_ersparnis,
      netzbezug_kosten,
      netto_ertrag,
      netto_bilanz,
      netzbezug_preis_cent: netzPreisCent,
      co2_einsparung,
    }
  })
}
