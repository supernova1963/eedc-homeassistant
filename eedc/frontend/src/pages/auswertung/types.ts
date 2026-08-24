// Gemeinsame Types für Auswertungs-Tabs
import type { useAnlagen, useAggregierteStats } from '../../hooks'
import type { AggregierteMonatsdaten } from '../../api/monatsdaten'
import type { Strompreis } from '../../types'
import type { NachhaltigkeitMonat } from '../../api/cockpit'
import {
  MONAT_KURZ, TYP_LABELS,
  COLORS, CHART_COLORS, TYP_COLORS,
  calcAutarkie, calcEigenverbrauchsquote, calcSpezifischerErtrag,
  calcCOP,
} from '../../lib'
import { speicherWirkungsgrad } from '../../lib/speicherWirkungsgrad'

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
  /**
   * #377 — Zählerstand je Verbrauchszähler (Investitions-ID → Stand) am
   * Monatsende. **Bestandsgröße**: nirgends mitsummiert, nicht Teil der Bilanz.
   */
  zaehler_stand?: Record<string, number> | null
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
  /**
   * Sonstiges je Richtung (BHKW, Heizstab, Pool …) — null = kein solches Gerät
   * in dem Monat. Die Verbrauchsseite steckt bereits im `gesamtverbrauch`; sie
   * schlüsselt ihn auf, statt etwas hinzuzufügen.
   */
  sonstiges_erzeugung: number | null
  sonstiges_verbrauch: number | null
  // ── Finanzen ───────────────────────────────────────────────────────────
  // Alle Werte kommen **fertig aus dem Backend** (`/monatsdaten/aggregiert`,
  // SoT `baue_finanz_zeile` + `berechne_finanz_aggregat`). Bis 2026-08-04
  // rechnete diese Datei sie selbst — mit eigener Tarif-Stichtags-Auflösung,
  // eigenem §51-Abzug und ohne USt/BKW-Regel (Fund N-22). Wer hier wieder eine
  // Formel einsetzt, baut die zweite Engine neu auf.
  einspeise_erloes: number
  ev_ersparnis: number
  netzbezug_kosten: number
  netto_ertrag: number
  netto_bilanz: number
  /**
   * USt auf Eigenverbrauch (§ 3 Abs. 1b UStG), bereits **in `netto_ertrag`
   * abgezogen**. 0 außerhalb der Regelbesteuerung. Steht als eigene Größe da,
   * damit die kleinere Netto-Zahl erklärbar bleibt — dieselbe Begründung wie
   * beim ausgewiesenen §51-Abzug.
   */
  ust_eigenverbrauch: number
  /** Real verrechneter Monats-Ø-Netzbezugspreis (Flex-Ø oder statischer Tarif, #326). */
  netzbezug_preis_cent: number | null
  /** Durch §51 EEG entgangener Erlös in € (0, wenn die Anlage nicht betroffen ist). */
  einspeise_nicht_verguetet_euro?: number
  /** Eingespeiste kWh ohne Vergütung (§51-Volumen); null = Anlage unterliegt nicht §51. */
  einspeise_neg_preis_kwh?: number | null
  /**
   * CO₂-Einsparung des Monats in kg — der **PV-Anteil** der kanonischen Bilanz
   * (`co2_pv_kg` aus `/cockpit/nachhaltigkeit`, Layer-SoT `berechne_co2_bilanz`).
   *
   * `null` = für diesen Monat liegt kein kanonischer Wert vor (Reihe noch nicht
   * geladen, Abruf fehlgeschlagen, oder der Monat trägt nichts zur CO₂-Bilanz
   * bei). Bewusst **nicht** ersatzweise gerechnet: ein stiller Näherungswert
   * neben einer kanonischen Zahl ist genau die Drift, die N-21 beendet hat.
   *
   * Warum der PV-Anteil und nicht `co2_gesamt_kg`: diese Zeile speist die
   * **Werte-Tabelle**, und die zeigt dieselbe Spalte auch je Tag — dort sind
   * WP-Wärme und E-Mob-Kilometer nicht gemessen (s. `tage_werte.py`). Eine
   * Spalte, die im Monat drei Quellen und am Tag eine addiert, wäre über die
   * Granularitäten nicht summierbar. Die **vollständige** Bilanz (PV + WP +
   * E-Mob) zeigen Cockpit → Jahr und Auswertungen → CO₂.
   */
  co2_einsparung: number | null
}

// Helper-Funktion zum Erstellen der Monatszeitreihen
// Verwendet jetzt AggregierteMonatsdaten mit korrekter PV-Erzeugung aus InvestitionMonatsdaten
//
// `co2Monate` ist die kanonische CO₂-Reihe aus `/cockpit/nachhaltigkeit`
// (`useAuswertungBasis().co2.monate`). Fehlt sie, bleibt `co2_einsparung` null —
// diese Funktion konstruiert **keine** CO₂-Größe mehr (N-21, ADR-001).
//
// **Die Finanzen rechnet diese Funktion seit N-22 nicht mehr** (2026-08-04). Sie
// hatte dafür einen eigenen Tarif-Stichtags-Löser (`findGueltigerTarif`, ein
// P8-Duplikat), einen eigenen §51-Abzug und eine eigene EV-Ersparnis — und war
// damit eine zweite Finanz-Engine neben `services/finanz_zeilen.py`. Sie kannte
// weder den BKW-Ersatzträger (P9) noch die USt auf Eigenverbrauch, die alle vier
// Backend-Sichten abziehen, und rechnete die Erzeugung eines Brennstoff-Erzeugers
// (BHKW) als Strompreis-Ersparnis mit. Die Werte kommen jetzt aus der Antwort.
export function createMonatsZeitreihe(
  data: AggregierteMonatsdaten[],
  anlage?: TabProps['anlage'],
  co2Monate?: NachhaltigkeitMonat[],
): MonatsZeitreihe[] {
  const co2ProMonat = new Map(
    (co2Monate ?? []).map((m) => [`${m.jahr}-${m.monat}`, m.co2_pv_kg]),
  )

  const sorted = [...data].sort((a, b) => {
    if (a.jahr !== b.jahr) return a.jahr - b.jahr
    return a.monat - b.monat
  })

  return sorted.map(md => {
    // PV-Erzeugung kommt jetzt korrekt aus InvestitionMonatsdaten (aggregiert).
    // `??` statt `||`: ein gemessener Monat mit 0 kWh ist eine Aussage, kein
    // fehlender Wert — mit `||` fiel er auf den Ersatzausdruck durch (N-22).
    const erzeugung = md.pv_erzeugung_kwh ?? 0
    const eigenverbrauch = md.eigenverbrauch_kwh ?? 0
    const gesamtverbrauch = md.gesamtverbrauch_kwh ?? (eigenverbrauch + md.netzbezug_kwh)
    const direktverbrauch = md.direktverbrauch_kwh ?? 0

    // Quoten berechnen - direkt aus aggregierten Daten oder berechnet
    const autarkie = md.autarkie_prozent ?? calcAutarkie(eigenverbrauch, gesamtverbrauch)
    const evQuote = md.eigenverbrauchsquote_prozent ?? calcEigenverbrauchsquote(eigenverbrauch, erzeugung)
    // F-58: der Monats-Nenner kommt vom Backend (Σ der im Monat aktiven
    // Module). `anlage?.leistung_kwp` bleibt Fallback für Antworten ohne
    // das Feld — Bestandsverhalten, kein zweiter Rechenweg.
    const spezErtrag = calcSpezifischerErtrag(erzeugung, md.anlagen_kwp ?? anlage?.leistung_kwp)

    // Speicher: null = keine Speicher-Komponente aktiv (Backend liefert null).
    // Der η kommt aus dem Spiegel des Layer-SoT (N-252) — hier steht er je
    // EINZELNEM Monat, also in genau dem Fall, in dem der Ladestand-Übertrag
    // über die Monatsgrenze am stärksten wirkt. Ohne SoC-Messung ist ein
    // Quotient über 100 % deshalb kein Wert, sondern eine fehlende Aussage.
    const speicher_ladung = md.speicher_ladung_kwh
    const speicher_entladung = md.speicher_entladung_kwh
    const speicher_effizienz = (speicher_ladung != null && speicher_entladung != null)
      ? speicherWirkungsgrad(speicher_ladung, speicher_entladung).prozent
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

    // CO₂: nachgeschlagen, nicht gerechnet (N-21). Der Kanon steht im Backend
    // (`berechne_co2_bilanz`); hier wird nur der Monat zugeordnet.
    const co2_einsparung = co2ProMonat.get(`${md.jahr}-${md.monat}`) ?? null

    return {
      name: `${MONAT_KURZ[md.monat]} ${md.jahr.toString().slice(-2)}`,
      jahr: md.jahr,
      // #377 — Zählerstände unverändert durchreichen. Sie werden hier bewusst
      // NICHT verrechnet: keine Summe, keine Quote, kein Durchschnitt. Ein
      // Zählerstand ist eine Bestandsgröße und geht in keine Bilanz ein.
      zaehler_stand: md.zaehler_stand ?? null,
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
      // Beide fertig aus der Antwort — hier wird nichts gefaltet (P10).
      sonstiges_erzeugung: md.sonstige_erzeugung_kwh,
      sonstiges_verbrauch: md.sonstige_verbrauch_kwh,
      einspeise_erloes: md.einspeise_erloes_euro,
      ev_ersparnis: md.ev_ersparnis_euro + md.bkw_ersparnis_euro,
      netzbezug_kosten: md.netzbezug_kosten_euro,
      netto_ertrag: md.netto_ertrag_euro,
      netto_bilanz: md.netto_bilanz_euro,
      ust_eigenverbrauch: md.ust_eigenverbrauch_euro,
      netzbezug_preis_cent: md.netzbezug_preis_cent,
      einspeise_nicht_verguetet_euro: md.einspeise_nicht_verguetet_euro,
      einspeise_neg_preis_kwh: md.einspeisung_neg_preis_kwh,
      co2_einsparung,
    }
  })
}
