/**
 * Community-Demo-Fixtures — realistische Beispieldaten für die Demo-Builds
 * (`VITE_DEMO_DEFAULT=true`, Guest-/Dev-Box). Der Community-Server kennt die
 * Demo-Anlage nicht; damit die Community-Sichten trotzdem rendern, liefert
 * `communityApi` diese kanonisierten Objekte, wenn {@link DEMO_DEFAULT} aktiv ist.
 *
 * Produktiv-Build: `DEMO_DEFAULT` ist `false` → die Importe werden tree-geshaket,
 * kein Demo-Code im Auslieferungs-Bundle.
 */
import type {
  CommunityBenchmarkResponse, MonatswertOutput, Verteilung, MonatlicheDurchschnitte,
  ZeitraumTyp, SpeicherByClass, WPByRegion, EAutoByUsage, RegionStatistik,
  TrendDaten, DegradationsAnalyse, GlobaleStatistik, Ranking,
} from './community'

// Saisonale spez.-Ertragskurve (kWh/kWp je Monat) — Summe ≈ 1.075/Jahr.
const SAISON = [25, 45, 85, 120, 145, 150, 155, 135, 100, 65, 30, 20]
const KWP = 9.8

function baueMonatswerte(): MonatswertOutput[] {
  // 14 Monate: Mai 2025 … Juni 2026.
  const out: MonatswertOutput[] = []
  const start = { jahr: 2025, monat: 5 }
  for (let i = 0; i < 14; i++) {
    const monat = ((start.monat - 1 + i) % 12) + 1
    const jahr = start.jahr + Math.floor((start.monat - 1 + i) / 12)
    const spez = SAISON[monat - 1]
    out.push({
      jahr, monat,
      ertrag_kwh: Math.round(spez * KWP),
      einspeisung_kwh: Math.round(spez * KWP * 0.45),
      netzbezug_kwh: Math.round(220 - spez * 0.6),
      autarkie_prozent: Math.min(95, Math.round(40 + spez / 3)),
      eigenverbrauch_prozent: Math.min(90, Math.round(35 + spez / 5)),
      spez_ertrag_kwh_kwp: spez,
    })
  }
  return out
}

const ZEITRAUM_LABEL: Record<ZeitraumTyp, string> = {
  letzter_monat: 'Letzter Monat',
  letzte_12_monate: 'Letzte 12 Monate',
  letztes_vollstaendiges_jahr: 'Letztes Jahr (2025)',
  jahr: 'Jahr',
  seit_installation: 'Seit Installation',
}

export function demoBenchmark(zeitraum: ZeitraumTyp): CommunityBenchmarkResponse {
  return {
    anlage: {
      anlage_hash: 'demo-anlage',
      region: 'BY',
      kwp: KWP,
      ausrichtung: 'Süd',
      neigung_grad: 35,
      speicher_kwh: 10,
      installation_jahr: 2022,
      hat_waermepumpe: true,
      hat_eauto: true,
      hat_wallbox: true,
      hat_balkonkraftwerk: false,
      hat_sonstiges: false,
      wallbox_kw: 11,
      wp_art: 'luft_wasser',
      monatswerte: baueMonatswerte(),
    },
    benchmark: {
      spez_ertrag_anlage: 1075,
      spez_ertrag_durchschnitt: 982,
      spez_ertrag_region: 1015,
      rang_gesamt: 142,
      anzahl_anlagen_gesamt: 1284,
      rang_region: 11,
      anzahl_anlagen_region: 187,
    },
    benchmark_erweitert: {
      pv: { spez_ertrag: { wert: 1075, community_avg: 982, rang: 142 } },
      speicher: {
        kapazitaet: { wert: 10, community_avg: 9.2 },
        zyklen_jahr: { wert: 245, community_avg: 210 },
        wirkungsgrad: { wert: 92, community_avg: 89 },
        netz_anteil: { wert: 8, community_avg: 15 },
      },
      waermepumpe: {
        jaz: { wert: 4.2, community_avg: 3.8 },
        jaz_typ: { wert: 4.2, community_avg: 3.9 },
        stromverbrauch: { wert: 3850, community_avg: 4200 },
        waermeerzeugung: { wert: 16170, community_avg: 15960 },
      },
      eauto: {
        ladung_gesamt: { wert: 2450, community_avg: 2600 },
        pv_anteil: { wert: 72, community_avg: 58 },
        verbrauch_100km: { wert: 17, community_avg: 19 },
      },
      wallbox: {
        ladung: { wert: 2450, community_avg: 2300 },
        pv_anteil: { wert: 65, community_avg: 55 },
        ladevorgaenge: { wert: 142, community_avg: 130 },
      },
      balkonkraftwerk: null,
    },
    zeitraum,
    zeitraum_label: ZEITRAUM_LABEL[zeitraum] ?? 'Letzte 12 Monate',
  }
}

export function demoDistribution(): Verteilung {
  // 15 Klassen um den Median ~980; eigene Anlage (1075) fällt in eine obere Klasse.
  const bins = Array.from({ length: 15 }, (_, i) => {
    const von = 600 + i * 60
    const mitte = 7
    const anzahl = Math.round(140 * Math.exp(-((i - mitte) ** 2) / 18))
    return { von, bis: von + 60, anzahl: Math.max(3, anzahl) }
  })
  return {
    metric: 'spez_ertrag',
    einheit: 'kWh/kWp',
    bins,
    statistik: { min: 612, max: 1460, median: 980, durchschnitt: 982, stdabweichung: 142 },
  }
}

export function demoMonthlyAverages(): MonatlicheDurchschnitte {
  const monate = []
  for (let i = 0; i < 14; i++) {
    const monat = ((4 + i) % 12) + 1
    const jahr = 2025 + Math.floor((4 + i) / 12)
    monate.push({ jahr, monat, spez_ertrag_avg: Math.round(SAISON[monat - 1] * 0.92), anzahl_anlagen: 1100 + (i % 5) * 20 })
  }
  return { monate }
}

// ─── Komponenten-Deep-Dives ──────────────────────────────────────────────────

export function demoSpeicherByClass(): SpeicherByClass {
  // Eigene Anlage: 10 kWh → eigene Klasse „5-10 kWh".
  return {
    klassen: [
      { von_kwh: 0, bis_kwh: 5, anzahl: 64, durchschnitt_wirkungsgrad: 87, durchschnitt_zyklen: 185, durchschnitt_netz_anteil: 18 },
      { von_kwh: 5, bis_kwh: 10, anzahl: 142, durchschnitt_wirkungsgrad: 90, durchschnitt_zyklen: 232, durchschnitt_netz_anteil: 12 },
      { von_kwh: 10, bis_kwh: 15, anzahl: 98, durchschnitt_wirkungsgrad: 91, durchschnitt_zyklen: 248, durchschnitt_netz_anteil: 10 },
      { von_kwh: 15, bis_kwh: 20, anzahl: 41, durchschnitt_wirkungsgrad: 92, durchschnitt_zyklen: 256, durchschnitt_netz_anteil: 9 },
      { von_kwh: 20, bis_kwh: null, anzahl: 17, durchschnitt_wirkungsgrad: 93, durchschnitt_zyklen: 261, durchschnitt_netz_anteil: 8 },
    ],
  }
}

export function demoWaermepumpeByRegion(): WPByRegion {
  return {
    regionen: [
      { region: 'BY', anzahl: 58, durchschnitt_jaz: 4.2, durchschnitt_stromverbrauch: 3850 },
      { region: 'BW', anzahl: 49, durchschnitt_jaz: 4.0, durchschnitt_stromverbrauch: 3990 },
      { region: 'NW', anzahl: 71, durchschnitt_jaz: 3.8, durchschnitt_stromverbrauch: 4250 },
      { region: 'NI', anzahl: 38, durchschnitt_jaz: 3.7, durchschnitt_stromverbrauch: 4380 },
      { region: 'HE', anzahl: 27, durchschnitt_jaz: 3.9, durchschnitt_stromverbrauch: 4120 },
      { region: 'SN', anzahl: 19, durchschnitt_jaz: 3.6, durchschnitt_stromverbrauch: 4510 },
    ],
  }
}

export function demoEAutoByUsage(): EAutoByUsage {
  return {
    klassen: [
      { klasse: 'wenig', beschreibung: 'bis 500 km/Monat', anzahl: 52, durchschnitt_pv_anteil: 74, durchschnitt_verbrauch_100km: 16.5 },
      { klasse: 'normal', beschreibung: '500–1.000 km/Monat', anzahl: 118, durchschnitt_pv_anteil: 61, durchschnitt_verbrauch_100km: 17.8 },
      { klasse: 'viel', beschreibung: '1.000–2.000 km/Monat', anzahl: 74, durchschnitt_pv_anteil: 48, durchschnitt_verbrauch_100km: 18.9 },
      { klasse: 'intensiv', beschreibung: 'über 2.000 km/Monat', anzahl: 23, durchschnitt_pv_anteil: 39, durchschnitt_verbrauch_100km: 20.4 },
    ],
  }
}

// ─── Regional ────────────────────────────────────────────────────────────────

export function demoRegionalStatistics(): RegionStatistik[] {
  const basis = (region: string, spez: number, anlagen: number, extra: Partial<RegionStatistik> = {}): RegionStatistik => ({
    region,
    anzahl_anlagen: anlagen,
    durchschnitt_kwp: 9.4,
    durchschnitt_spez_ertrag: spez,
    durchschnitt_autarkie: 58,
    anteil_mit_speicher: 64,
    anteil_mit_waermepumpe: 31,
    anteil_mit_eauto: 27,
    anteil_mit_wallbox: 33,
    anteil_mit_balkonkraftwerk: 12,
    avg_speicher_ladung_kwh: 210,
    avg_speicher_entladung_kwh: 188,
    avg_wp_jaz: 3.9,
    avg_eauto_km: 920,
    avg_eauto_ladung_kwh: 165,
    avg_wallbox_kwh: 240,
    avg_wallbox_pv_anteil: 58,
    avg_bkw_kwh: 38,
    ...extra,
  })
  return [
    basis('BY', 1015, 187, { durchschnitt_kwp: 9.8, avg_wp_jaz: 4.1 }),
    basis('BW', 1002, 164, { avg_wp_jaz: 4.0 }),
    basis('SL', 1048, 14, { durchschnitt_kwp: 8.9 }),
    basis('RP', 1020, 58),
    basis('HE', 985, 96, { avg_bkw_kwh: null }),
    basis('NW', 928, 241, { avg_wp_jaz: 3.7 }),
    basis('NI', 945, 132, { avg_eauto_km: null, avg_eauto_ladung_kwh: null }),
    basis('SH', 962, 71, { avg_wallbox_pv_anteil: null }),
    basis('SN', 905, 53, { avg_wp_jaz: 3.6 }),
    basis('TH', 912, 29, { avg_bkw_kwh: null }),
    basis('BB', 938, 47),
    basis('MV', 951, 22, { avg_speicher_ladung_kwh: null, avg_speicher_entladung_kwh: null }),
  ]
}

// ─── Trends ──────────────────────────────────────────────────────────────────

export function demoTrends(): TrendDaten {
  const monate = ['Jul 25', 'Aug 25', 'Sep 25', 'Okt 25', 'Nov 25', 'Dez 25', 'Jan 26', 'Feb 26', 'Mär 26', 'Apr 26', 'Mai 26', 'Jun 26']
  const reihe = (start: number, schritt: number) => monate.map((m, i) => ({ monat: m, wert: Math.round((start + i * schritt) * 10) / 10 }))
  return {
    period: '12_monate',
    trends: {
      anzahl_anlagen: monate.map((m, i) => ({ monat: m, wert: 1180 + i * 9 })),
      durchschnitt_kwp: reihe(9.2, 0.05),
      speicher_quote: reihe(58, 0.7),
      waermepumpe_quote: reihe(26, 0.5),
      eauto_quote: reihe(22, 0.45),
    },
  }
}

export function demoDegradation(): DegradationsAnalyse {
  return {
    nach_alter: [
      { alter_jahre: 0, anzahl: 142, durchschnitt_spez_ertrag: 1048 },
      { alter_jahre: 1, anzahl: 168, durchschnitt_spez_ertrag: 1042 },
      { alter_jahre: 2, anzahl: 154, durchschnitt_spez_ertrag: 1031 },
      { alter_jahre: 3, anzahl: 121, durchschnitt_spez_ertrag: 1019 },
      { alter_jahre: 4, anzahl: 96, durchschnitt_spez_ertrag: 1008 },
      { alter_jahre: 5, anzahl: 78, durchschnitt_spez_ertrag: 994 },
      { alter_jahre: 7, anzahl: 51, durchschnitt_spez_ertrag: 968 },
      { alter_jahre: 10, anzahl: 34, durchschnitt_spez_ertrag: 932 },
    ],
    durchschnittliche_degradation_prozent_jahr: 0.52,
  }
}

// ─── Statistiken ─────────────────────────────────────────────────────────────

export function demoGlobalStatistics(): GlobaleStatistik {
  return {
    anzahl_anlagen: 1284,
    anzahl_regionen: 16,
    durchschnitt: {
      kwp: 9.4,
      spez_ertrag: 982,
      speicher_kwh: 9.2,
      autarkie_prozent: 57,
      eigenverbrauch_prozent: 48,
    },
    ausstattungsquoten: {
      speicher: 64.2,
      waermepumpe: 31.4,
      eauto: 27.1,
      wallbox: 33.6,
      balkonkraftwerk: 11.8,
    },
    typische_anlage: { kwp: 9.5, ausrichtung: 'Süd', neigung_grad: 35, speicher_kwh: 10 },
    stand: '2026-06-30',
  }
}

export function demoRanking(): Ranking {
  return {
    category: 'spez_ertrag',
    label: 'Spezifischer Ertrag',
    einheit: 'kWh/kWp',
    zeitraum: 'Letzte 12 Monate',
    ranking: [
      { rang: 1, wert: 1460, region: 'SL', kwp: 8.4 },
      { rang: 2, wert: 1438, region: 'BY', kwp: 11.2 },
      { rang: 3, wert: 1421, region: 'BW', kwp: 9.7 },
      { rang: 4, wert: 1402, region: 'RP', kwp: 7.9 },
      { rang: 5, wert: 1388, region: 'BY', kwp: 10.5 },
      { rang: 6, wert: 1371, region: 'HE', kwp: 8.8 },
      { rang: 7, wert: 1355, region: 'BW', kwp: 12.0 },
      { rang: 8, wert: 1342, region: 'BY', kwp: 9.1 },
      { rang: 9, wert: 1329, region: 'NW', kwp: 6.6 },
      { rang: 10, wert: 1318, region: 'SH', kwp: 8.2 },
    ],
    eigener_rang: 142,
    eigener_wert: 1075,
  }
}
