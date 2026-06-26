/**
 * JahrAggregat — Client-Aggregation der Cockpit/Jahr-Sicht.
 *
 * Konvergenz statt zweiter Code-Pfad (wie {@link baueTagAlsMonat} beim Tag): ein
 * Jahr ist die Summe seiner 12 Einzelmonate. Statt eines neuen Backend-Endpoints
 * (D3, kein neuer Endpoint) summieren wir die KANONISCHEN Monats-Antworten
 * (`AktuellerMonatResponse` je Monat aus `aktuellerMonatApi.getData`) zu EINEM
 * Jahres-`AktuellerMonatResponse`-Shape und füttern damit die BESTEHENDEN
 * Monat-Block-Bauer (`baueMonatKpis`/`MonatBilanz`/`baueKomponentenBloecke`/
 * `finanzTeaserBlock`). So zeigt Cockpit/Jahr exakt dieselben Blöcke/Optik wie
 * Cockpit/Monat — und es gibt KEINE Datenlücke (die monatlich-only-KPIs wie
 * WP-Wärme/JAZ/€, E-Auto-km/€, Heiz/WW-Split existieren pro Monat und summieren
 * sich natürlich zum Jahr; siehe SPEC-COCKPIT-TAG-JAHR Abschnitt A).
 *
 * additive Felder (kWh/€/Zähler) → Summe (null-bewusst: alle null ⇒ null);
 * Quoten (Autarkie/EV-Quote/η/JAZ/Verbrauch/100km) → aus den Summen NEU berechnet
 * (nie Monats-Mittel der Quoten); Preise → Mittel der Monate; Kapazität → Max.
 */
import type { AktuellerMonatResponse, InvestitionFinancialDetail, SonstigesGeraet } from '../api/aktuellerMonat'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'

/** Summe null-bewusst: nur wenn KEIN Monat einen Wert liefert ⇒ null (sonst 0+…). */
function summe(werte: (number | null | undefined)[]): number | null {
  const vorhanden = werte.filter((v): v is number => v != null)
  return vorhanden.length ? vorhanden.reduce((a, v) => a + v, 0) : null
}

function max(werte: (number | null | undefined)[]): number | null {
  const vorhanden = werte.filter((v): v is number => v != null)
  return vorhanden.length ? Math.max(...vorhanden) : null
}

/** Mittel der vorhandenen Monatswerte (für Preise/Tarif-Zeile). */
function mittel(werte: (number | null | undefined)[]): number | null {
  const vorhanden = werte.filter((v): v is number => v != null)
  return vorhanden.length ? vorhanden.reduce((a, v) => a + v, 0) / vorhanden.length : null
}

/** Quote aus zwei Summen (null wenn Nenner fehlt/0). */
function quote(zaehler: number | null, nenner: number | null, faktor = 100): number | null {
  if (zaehler == null || nenner == null || nenner === 0) return null
  return (zaehler / nenner) * faktor
}

/**
 * Summiert die 12 Monats-Antworten eines Jahres zu einem
 * `AktuellerMonatResponse`-Shape (Felder, die die Monat-Bauer lesen).
 * `jahr` setzt das Jahr im Ergebnis; `monat`=0 markiert „Jahres-Aggregat".
 */
export function baueJahrAlsMonat(monate: AktuellerMonatResponse[], jahr: number): AktuellerMonatResponse {
  const f = <K extends keyof AktuellerMonatResponse>(key: K) => monate.map((m) => m[key] as number | null | undefined)

  // Energie-Summen (für Quoten-Neuberechnung gebraucht).
  const pv = summe(f('pv_erzeugung_kwh'))
  const ev = summe(f('eigenverbrauch_kwh'))
  const gesamtverbrauch = summe(f('gesamtverbrauch_kwh'))
  const speicherLadung = summe(f('speicher_ladung_kwh'))
  const speicherEntladung = summe(f('speicher_entladung_kwh'))
  const wpWaerme = summe(f('wp_waerme_kwh'))
  const wpStrom = summe(f('wp_strom_kwh'))
  const emobLadung = summe(f('emob_ladung_kwh'))
  const emobKm = summe(f('emob_km'))

  // Per-Investition-Finanzdetails über das Jahr aufsummieren (Jahres-T-Konto in
  // Auswertungen/Finanzen): numerische Felder Σ (null-bewusst), Identität/Label
  // vom ersten Vorkommen. Monats-`formel`/`berechnung` entfallen — ein Jahres-Σ
  // hat kein sinnvolles Monats-Formelbild (Tooltip zeigt dann nur Label + Σ).
  // (Die Monat-Bauer für Cockpit/Jahr lesen nur typ/bezeichnung → unverändert.)
  const addNull = (a: number | null, b: number | null): number | null =>
    a == null && b == null ? null : (a ?? 0) + (b ?? 0)
  const financialsMap = new Map<number, InvestitionFinancialDetail>()
  for (const m of monate) for (const fin of m.investitionen_financials ?? []) {
    const prev = financialsMap.get(fin.investition_id)
    if (!prev) {
      financialsMap.set(fin.investition_id, { ...fin, formel: null, berechnung: null })
    } else {
      prev.betriebskosten_monat_euro += fin.betriebskosten_monat_euro
      prev.erloes_euro = addNull(prev.erloes_euro, fin.erloes_euro)
      prev.ersparnis_euro = addNull(prev.ersparnis_euro, fin.ersparnis_euro)
      prev.sonstige_ertraege_euro += fin.sonstige_ertraege_euro
      prev.sonstige_ausgaben_euro += fin.sonstige_ausgaben_euro
      if (!prev.ersparnis_label && fin.ersparnis_label) prev.ersparnis_label = fin.ersparnis_label
    }
  }

  // Aktive Geräte je Typ über das Jahr (Union, dedup) — für „aggregiert aus …".
  const geraete: Record<string, string[]> = {}
  for (const m of monate) for (const [typ, namen] of Object.entries(m.komponenten_geraete ?? {})) {
    const set = new Set([...(geraete[typ] ?? []), ...namen])
    geraete[typ] = [...set]
  }

  // Sonstiges pro Gerät über die Monate aufsummieren (nach Kategorie + Bezeichnung).
  const sgMap = new Map<string, Required<SonstigesGeraet>>()
  for (const m of monate) for (const g of m.sonstiges_geraete ?? []) {
    const key = `${g.kategorie}|${g.bezeichnung}`
    const a = sgMap.get(key) ?? {
      bezeichnung: g.bezeichnung, kategorie: g.kategorie,
      erzeugung_kwh: 0, eigenverbrauch_kwh: 0, einspeisung_kwh: 0, verbrauch_kwh: 0, bezug_pv_kwh: 0, bezug_netz_kwh: 0,
    }
    a.erzeugung_kwh = (a.erzeugung_kwh ?? 0) + (g.erzeugung_kwh ?? 0)
    a.eigenverbrauch_kwh = (a.eigenverbrauch_kwh ?? 0) + (g.eigenverbrauch_kwh ?? 0)
    a.einspeisung_kwh = (a.einspeisung_kwh ?? 0) + (g.einspeisung_kwh ?? 0)
    a.verbrauch_kwh = (a.verbrauch_kwh ?? 0) + (g.verbrauch_kwh ?? 0)
    a.bezug_pv_kwh = (a.bezug_pv_kwh ?? 0) + (g.bezug_pv_kwh ?? 0)
    a.bezug_netz_kwh = (a.bezug_netz_kwh ?? 0) + (g.bezug_netz_kwh ?? 0)
    sgMap.set(key, a)
  }
  const nz = (v: number) => (v > 0 ? Math.round(v * 100) / 100 : null)
  const sonstigesGeraete: SonstigesGeraet[] = [...sgMap.values()].map((g) => ({
    bezeichnung: g.bezeichnung, kategorie: g.kategorie,
    erzeugung_kwh: nz(g.erzeugung_kwh ?? 0), eigenverbrauch_kwh: nz(g.eigenverbrauch_kwh ?? 0),
    einspeisung_kwh: nz(g.einspeisung_kwh ?? 0), verbrauch_kwh: nz(g.verbrauch_kwh ?? 0),
    bezug_pv_kwh: nz(g.bezug_pv_kwh ?? 0), bezug_netz_kwh: nz(g.bezug_netz_kwh ?? 0),
  }))

  // Quellen-Union (Provenance-Badges im Header).
  const feldQuellen: AktuellerMonatResponse['feld_quellen'] = {}
  for (const m of monate) Object.assign(feldQuellen, m.feld_quellen ?? {})

  const erster = monate[0]

  return {
    anlage_id: erster?.anlage_id ?? 0,
    anlage_name: erster?.anlage_name ?? '',
    jahr,
    monat: 0,
    monat_name: String(jahr),
    aktualisiert_um: erster?.aktualisiert_um ?? '',
    quellen: erster?.quellen ?? {},

    // Energie-Bilanz (Σ) + Quoten (neu berechnet)
    pv_erzeugung_kwh: pv,
    einspeisung_kwh: summe(f('einspeisung_kwh')),
    netzbezug_kwh: summe(f('netzbezug_kwh')),
    eigenverbrauch_kwh: ev,
    direktverbrauch_kwh: summe(f('direktverbrauch_kwh')),
    gesamtverbrauch_kwh: gesamtverbrauch,
    autarkie_prozent: quote(ev, gesamtverbrauch),
    eigenverbrauch_quote_prozent: quote(ev, pv),
    spez_ertrag: summe(f('spez_ertrag')),

    // Speicher
    speicher_ladung_kwh: speicherLadung,
    speicher_entladung_kwh: speicherEntladung,
    speicher_ladung_netz_kwh: summe(f('speicher_ladung_netz_kwh')),
    speicher_wirkungsgrad_prozent: quote(speicherEntladung, speicherLadung),
    speicher_vollzyklen: summe(f('speicher_vollzyklen')),
    speicher_kapazitaet_kwh: max(f('speicher_kapazitaet_kwh')),
    hat_speicher: monate.some((m) => m.hat_speicher),
    speicher_soc_drift_signifikant: monate.some((m) => m.speicher_soc_drift_signifikant),
    speicher_effektiver_ladepreis_cent: mittel(f('speicher_effektiver_ladepreis_cent')),
    speicher_effektiver_ladepreis_quelle:
      monate.find((m) => m.speicher_effektiver_ladepreis_quelle)?.speicher_effektiver_ladepreis_quelle ?? null,

    // Wärmepumpe
    wp_strom_kwh: wpStrom,
    wp_waerme_kwh: wpWaerme,
    wp_heizung_kwh: summe(f('wp_heizung_kwh')),
    wp_warmwasser_kwh: summe(f('wp_warmwasser_kwh')),
    wp_strom_heizen_kwh: summe(f('wp_strom_heizen_kwh')),
    wp_strom_warmwasser_kwh: summe(f('wp_strom_warmwasser_kwh')),
    // Jahres-Counter im period-neutralen Σ-Slot; Max/Tag = höchster Einzeltag des Jahres.
    wp_starts_summe_monat: summe(f('wp_starts_summe_monat')),
    wp_starts_max_tag: max(f('wp_starts_max_tag')),
    wp_betriebsstunden_summe_monat: summe(f('wp_betriebsstunden_summe_monat')),
    wp_betriebsstunden_max_tag: max(f('wp_betriebsstunden_max_tag')),
    hat_waermepumpe: monate.some((m) => m.hat_waermepumpe),

    // E-Mobilität
    emob_ladung_kwh: emobLadung,
    emob_km: emobKm,
    emob_verbrauch_100km: quote(emobLadung, emobKm),
    emob_verbrauch_quelle: monate.some((m) => m.emob_verbrauch_quelle === 'gemessen') ? 'gemessen'
      : monate.some((m) => m.emob_verbrauch_quelle === 'ladung') ? 'ladung' : 'keine',
    emob_ladung_pv_kwh: summe(f('emob_ladung_pv_kwh')),
    emob_ladung_netz_kwh: summe(f('emob_ladung_netz_kwh')),
    emob_ladung_extern_kwh: summe(f('emob_ladung_extern_kwh')),
    emob_v2h_kwh: summe(f('emob_v2h_kwh')),
    hat_emobilitaet: monate.some((m) => m.hat_emobilitaet),

    // BKW
    bkw_erzeugung_kwh: summe(f('bkw_erzeugung_kwh')),
    bkw_eigenverbrauch_kwh: summe(f('bkw_eigenverbrauch_kwh')),
    hat_balkonkraftwerk: monate.some((m) => m.hat_balkonkraftwerk),

    // Sonstiges
    sonstiges_erzeugung_kwh: summe(f('sonstiges_erzeugung_kwh')),
    sonstiges_eigenverbrauch_kwh: summe(f('sonstiges_eigenverbrauch_kwh')),
    sonstiges_einspeisung_kwh: summe(f('sonstiges_einspeisung_kwh')),
    sonstiges_verbrauch_kwh: summe(f('sonstiges_verbrauch_kwh')),
    sonstiges_bezug_pv_kwh: summe(f('sonstiges_bezug_pv_kwh')),
    sonstiges_bezug_netz_kwh: summe(f('sonstiges_bezug_netz_kwh')),
    sonstiges_geraete: sonstigesGeraete,
    hat_sonstiges: monate.some((m) => m.hat_sonstiges),

    // Finanzen (Σ)
    einspeise_erloes_euro: summe(f('einspeise_erloes_euro')),
    netzbezug_kosten_euro: summe(f('netzbezug_kosten_euro')),
    ev_ersparnis_euro: summe(f('ev_ersparnis_euro')),
    netto_ertrag_euro: summe(f('netto_ertrag_euro')),
    wp_ersparnis_euro: summe(f('wp_ersparnis_euro')),
    emob_ersparnis_euro: summe(f('emob_ersparnis_euro')),
    sonstige_ertraege_euro: summe(f('sonstige_ertraege_euro')) ?? 0,
    sonstige_ausgaben_euro: summe(f('sonstige_ausgaben_euro')) ?? 0,
    sonstige_netto_euro: summe(f('sonstige_netto_euro')) ?? 0,
    gesamtnettoertrag_euro: summe(f('gesamtnettoertrag_euro')),
    betriebskosten_anteilig_euro: summe(f('betriebskosten_anteilig_euro')),

    // Tarif-Info (Jahres-Mittel der Monate)
    netzbezug_preis_cent: mittel(f('netzbezug_preis_cent')),
    einspeise_preis_cent: mittel(f('einspeise_preis_cent')),
    netzbezug_durchschnittspreis_cent: mittel(f('netzbezug_durchschnittspreis_cent')),

    // SOLL (Σ Monats-PVGIS); Vorjahr-Vergleich liefert die Jahr-Sicht separat.
    soll_pv_kwh: summe(f('soll_pv_kwh')),
    vorjahr: null,

    investitionen_financials: [...financialsMap.values()],
    komponenten_geraete: geraete,
    feld_quellen: feldQuellen,
  }
}

/** Jahres-Vergleichswerte (Energie) für die IST/Vorjahr/Ø-Jahr-Spalten — aus den
 *  aggregierten Monatszeilen EINES Jahres summiert (kein neuer Endpoint). Quoten
 *  aus den Summen neu berechnet. */
export interface JahrVergleich {
  jahr: number
  pv: number | null
  ev: number | null
  direkt: number | null
  einsp: number | null
  netz: number | null
  gesamt: number | null
  autarkie: number | null
}

export function jahrVergleichAus(rows: AggregierteMonatsdaten[], jahr: number): JahrVergleich {
  const j = rows.filter((r) => r.jahr === jahr)
  const s = (f: (r: AggregierteMonatsdaten) => number | null | undefined) => summe(j.map(f))
  const ev = s((r) => r.eigenverbrauch_kwh)
  const gesamt = s((r) => r.gesamtverbrauch_kwh)
  return {
    jahr,
    pv: s((r) => r.pv_erzeugung_kwh),
    ev,
    direkt: s((r) => r.direktverbrauch_kwh),
    einsp: s((r) => r.einspeisung_kwh),
    netz: s((r) => r.netzbezug_kwh),
    gesamt,
    autarkie: quote(ev, gesamt),
  }
}

/** Mittelung mehrerer Jahres-Vergleiche (Ø über die übrigen Jahre). */
export function mittelJahre(jahre: JahrVergleich[]): (JahrVergleich & { count: number }) | null {
  if (jahre.length === 0) return null
  const m = (f: (j: JahrVergleich) => number | null) => mittel(jahre.map(f))
  return {
    jahr: 0,
    pv: m((j) => j.pv), ev: m((j) => j.ev), direkt: m((j) => j.direkt),
    einsp: m((j) => j.einsp), netz: m((j) => j.netz), gesamt: m((j) => j.gesamt),
    autarkie: m((j) => j.autarkie), count: jahre.length,
  }
}
