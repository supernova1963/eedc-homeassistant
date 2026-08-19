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
import { MONAT_KURZ } from '../lib/constants'
import { speicherWirkungsgrad } from '../lib/speicherWirkungsgrad'
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
 * Mengengewichteter Jahres-Ø eines Monatspreises — Σ(Preis × Menge) / Σ Menge.
 *
 * Ein Jahres-Preis ist keine Eigenschaft der Monate, sondern der bezogenen Menge:
 * ein teurer Januar mit 400 kWh wiegt schwerer als ein Juli mit 20 kWh. Das
 * ungewichtete Monatsmittel, das hier bis v4.0.5 stand, widersprach der eigenen
 * Kachel — Kopfzahl und „Σ € ÷ Σ kWh" liefen bei Tarifwechsel im Jahr auseinander
 * (Forum simon42 #89667/67, Algie: 28,0 ct über 559 kWh · 210,45 €). Dasselbe
 * Muster wie beim Speicher-Netzpreis (R15-1), das dort schon so gerechnet wurde.
 *
 * Monate ohne Preis ODER ohne Menge fallen aus BEIDEN Summen — sonst verdünnte ein
 * datenloser Monat den Ø. Ohne jede Menge (Σ = 0) bleibt das ungewichtete Mittel
 * als Rückfall: besser der Tarif-Wert als eine leere Kachel.
 */
function gewichtet(
  preise: (number | null | undefined)[],
  mengen: (number | null | undefined)[],
): number | null {
  let produktSumme = 0
  let mengenSumme = 0
  for (let i = 0; i < preise.length; i++) {
    const p = preise[i]
    const m = mengen[i]
    if (p == null || m == null) continue
    produktSumme += p * m
    mengenSumme += m
  }
  if (mengenSumme === 0) return mittel(preise)
  return produktSumme / mengenSumme
}

/**
 * Die GEMESSENEN Mengen einer Monats-Antwort — daran wird abgelesen, ob ein Monat
 * überhaupt Daten trägt (s. {@link monatHatDaten}).
 *
 * Bewusst NUR Mengen: `/aktueller-monat` beantwortet auch Monate, in denen die
 * Anlage noch gar nicht lief, und liefert dort trotzdem `soll_pv_kwh` (PVGIS),
 * Tarif-Preise und die Speicher-Kapazität — alles Stammdaten-Ableitungen, keine
 * Messung. An der Box gemessen (Winterborn, 2026-08-02): Januar 2023, drei Monate
 * vor Inbetriebnahme, antwortet mit `soll_pv_kwh: 396,1`. Wer solche Monate mitzählt,
 * bläht das SOLL auf und drückt die SOLL-Erfüllung — genau die Falle, die ein
 * blindes 1–12-Fanout aufstellt.
 */
const MENGEN_FELDER = [
  'pv_erzeugung_kwh', 'einspeisung_kwh', 'netzbezug_kwh', 'eigenverbrauch_kwh',
  'direktverbrauch_kwh', 'gesamtverbrauch_kwh',
  'speicher_ladung_kwh', 'speicher_entladung_kwh',
  'wp_strom_kwh', 'wp_waerme_kwh',
  'emob_ladung_kwh', 'emob_km',
  'bkw_erzeugung_kwh', 'sonstiges_erzeugung_kwh', 'sonstiges_verbrauch_kwh',
] as const satisfies readonly (keyof AktuellerMonatResponse)[]

/** Trägt dieser Monat gemessene Daten — oder ist er nur eine Stammdaten-Antwort? */
export function monatHatDaten(m: AktuellerMonatResponse): boolean {
  return MENGEN_FELDER.some((k) => m[k] != null)
}

/**
 * Die Monate eines Jahres, die abgefragt werden müssen, um es VOLLSTÄNDIG zu
 * kennen (Fund N-65).
 *
 * Bis v4.0.6 war die Menge „Monate mit aggregierter Zeile (+ der heutige)". Eine
 * `Monatsdaten`-Zeile entsteht aber erst beim **Monatsabschluss**; ein längst
 * gelaufener Monat ohne Abschluss fiel damit komplett aus der Jahreszahl. An der
 * Box gemessen (Winterborn 2026-08-02): `/monatsdaten/aggregiert` meldet Jan–Jun,
 * Juli trägt aber 1.843 kWh — knapp ein Viertel der angezeigten Jahresernte fehlte.
 * Das ist kein Einzelfall, sondern das Muster; mehrere offene Monate sind möglich
 * und werden mitgefangen, weil hier ein **Intervall** entsteht, keine Aufzählung.
 *
 * Die Menge ist bewusst KEIN blindes 1–12 (zwölf Requests je Jahreswechsel), sondern
 * das Intervall zwischen dem ersten Datenmonat der Anlage und der Obergrenze
 * (laufender Monat bzw. Dezember). Für jedes abgeschlossene Jahr ist sie damit exakt
 * so groß wie bisher; nur das laufende Jahr wächst um seine Lücken. Erfasste Zeilen
 * sind immer enthalten — die Menge ist nie kleiner als die bisherige.
 */
export function zuLadendeMonate(
  rows: AggregierteMonatsdaten[],
  jahr: number,
  heute: Date,
): number[] {
  const menge = new Set<number>()
  // Eine erfasste Zeile zählt immer — auch außerhalb des Intervalls (Nachtrag).
  for (const r of rows) if (r.jahr === jahr) menge.add(r.monat)

  if (rows.length > 0 && jahr <= heute.getFullYear()) {
    const erstesJahr = Math.min(...rows.map((r) => r.jahr))
    if (jahr >= erstesJahr) {
      // Untergrenze: im Startjahr der erste erfasste Monat, davor lief die Anlage
      // nicht (dort antwortet der Endpoint mit reinen Stammdaten, s. MENGEN_FELDER).
      const von = jahr === erstesJahr
        ? Math.min(...rows.filter((r) => r.jahr === erstesJahr).map((r) => r.monat))
        : 1
      // Obergrenze: künftige Monate haben nichts.
      const bis = jahr === heute.getFullYear() ? heute.getMonth() + 1 : 12
      for (let m = von; m <= bis; m++) menge.add(m)
    }
  }
  return [...menge].sort((a, b) => a - b)
}

/**
 * Die abgeschlossenen Monate einer Monatsmenge — die Grundgesamtheit des Vergleichs.
 *
 * Der laufende Monat trägt Daten (er gehört in die Kopfzahl „das Jahr bis heute"),
 * darf aber in KEINEN Vergleich: zwei Augusttage gegen einen vollen August des
 * Vorjahrs wären N-37 in klein. Beschnitten wird dabei die IST-Seite genauso wie die
 * Vergleichsseite — ein Delta über ungleiche Fenster bleibt sonst falsch, egal wie
 * gut die Spalte beschriftet ist (Entscheid Gernot 2026-08-02).
 */
export function abgeschlosseneMonate(
  monate: readonly number[],
  jahr: number,
  heute: Date,
): number[] {
  if (jahr !== heute.getFullYear()) return [...monate]
  const laufend = heute.getMonth() + 1
  return monate.filter((m) => m < laufend)
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
  // Jahres-η über den Spiegel des Layer-SoT (N-252). `fenster_lang`, weil ein
  // Jahr den SoC-Übertrag der Monatsgrenzen ausmittelt — die Obergrenze gilt
  // trotzdem, und genau daran fehlte es hier.
  const _etaJahr = speicherWirkungsgrad(speicherLadung, speicherEntladung, 'fenster_lang')
  const speicherLadungNetz = summe(f('speicher_ladung_netz_kwh'))
  const speicherLadungNetzKosten = summe(f('speicher_ladung_netz_kosten_euro'))
  // #358: Die Auslastungs-BASIS wird summiert, der Prozentsatz daraus einmal
  // gebildet — Monats-Prozente zu mitteln wäre falsch (ein Februar wiegt
  // weniger als ein Juli, und ein angefangener Monat trägt nur seine
  // abgelaufenen Tage bei). Deshalb liefert das Backend beide Größen.
  const speicherAuslastungsBasis = summe(f('speicher_auslastungs_basis_kwh'))
  const wpWaerme = summe(f('wp_waerme_kwh'))
  const wpStrom = summe(f('wp_strom_kwh'))
  const emobLadung = summe(f('emob_ladung_kwh'))
  const emobKm = summe(f('emob_km'))

  // Effektiver Netzbezugspreis je Monat — dieselbe Vorrang-Regel wie in der
  // Kachel und im Backend (`resolve_netzbezug_preis_cent`): der mitgeschriebene
  // Ø-Bezugspreis schlägt den Tarif-Arbeitspreis.
  const netzbezugPreisEffektiv = monate.map(
    (m) => m.netzbezug_durchschnittspreis_cent ?? m.netzbezug_preis_cent,
  )

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

  // Grundlast (R12-1): grundlast_kwh additiv summieren; Anteil aus den Summen neu
  // bilden (Nenner = Gesamtverbrauch NUR der Monate mit Grundlast-Daten, damit das
  // Verhältnis stimmt). Ø-Leistung = Mittel der Monats-Mediane.
  const glKwh = summe(f('grundlast_kwh'))
  const glBasis = summe(monate.filter((m) => m.grundlast_kwh != null).map((m) => m.gesamtverbrauch_kwh))
  const glAnteil = glKwh != null && glBasis != null && glBasis > 0
    ? Math.round((glKwh / glBasis) * 1000) / 10
    : null

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
    speicher_ladung_netz_kwh: speicherLadungNetz,
    // N-252: NICHT `quote(...)`. Der rohe Quotient kennt keine Obergrenze — ein
    // Jahr, in dem mehr entladen als geladen gebucht ist, stand hier als
    // „104 %" und darunter der bestätigende Satz „über das ganze Fenster
    // gerechnet". Der Spiegel des Layer-SoT kappt und benennt den Fall.
    speicher_wirkungsgrad_prozent: _etaJahr.prozent,
    speicher_vollzyklen: summe(f('speicher_vollzyklen')),
    speicher_kapazitaet_kwh: max(f('speicher_kapazitaet_kwh')),
    speicher_auslastungs_basis_kwh: speicherAuslastungsBasis,
    speicher_auslastung_prozent: quote(speicherEntladung, speicherAuslastungsBasis),
    speicher_ersparnis_euro: summe(f('speicher_ersparnis_euro')),
    hat_speicher: monate.some((m) => m.hat_speicher),
    // F-22: Der Jahres-η summiert Ladung und Entladung über viele Monate — der
    // Ladestand-Übertrag einzelner Monatsgrenzen mittelt sich darin aus. Das
    // ist genau der Fall, den `EFFIZIENZ_FENSTER_MONATE` im Backend „langes
    // Fenster" nennt und ohne SoC-Korrektur für belastbar erklärt.
    //
    // Bis v4.0.11 stand hier `monate.some(...)`: ein einziger Monat ohne
    // belastbaren Wert setzte das Flag, und unter der Jahreszahl erschien
    // „SoC-Drift — Monats-η ausgeblendet" — neben einer Zahl, im Jahreskontext,
    // wegen eines Teilmonats. Der Satz war dreifach falsch.
    speicher_soc_drift_signifikant: false,
    // Die Quelle wird nicht mehr aus der Ladungsmenge GERATEN, sondern kommt
    // aus derselben Ableitung wie der Wert (N-252). Vorher hieß jeder Jahres-η
    // „fenster_lang", auch der unmögliche.
    speicher_wirkungsgrad_quelle: _etaJahr.quelle,
    speicher_effektiver_ladepreis_cent: mittel(f('speicher_effektiver_ladepreis_cent')),
    speicher_effektiver_ladepreis_quelle:
      monate.find((m) => m.speicher_effektiver_ladepreis_quelle)?.speicher_effektiver_ladepreis_quelle ?? null,
    // R15-1: Netzladung-Kosten Σ; Jahres-Ø-Preis aus den Summen (kWh-gewichtet,
    // €→ct via Faktor 100) statt Monats-Mittel der Preise.
    speicher_ladung_netz_kosten_euro: speicherLadungNetzKosten,
    speicher_ladung_netz_preis_cent: quote(speicherLadungNetzKosten, speicherLadungNetz, 100),
    speicher_ladung_netz_preis_quelle:
      monate.find((m) => m.speicher_ladung_netz_preis_quelle)?.speicher_ladung_netz_preis_quelle ?? null,

    // Wärmepumpe
    wp_strom_kwh: wpStrom,
    wp_waerme_kwh: wpWaerme,
    wp_heizung_kwh: summe(f('wp_heizung_kwh')),
    wp_warmwasser_kwh: summe(f('wp_warmwasser_kwh')),
    wp_strom_heizen_kwh: summe(f('wp_strom_heizen_kwh')),
    // #263 K-2: Teilmengen summieren sich über die Monate wie jede Menge.
    // `nicht aufgeteilt` wird NICHT summiert, sondern aus den Jahressummen
    // neu gerechnet — sonst addierten sich die Monats-Rundungen auf.
    wp_modus_strom_heizen_kwh: summe(f('wp_modus_strom_heizen_kwh')),
    wp_modus_strom_kuehlen_kwh: summe(f('wp_modus_strom_kuehlen_kwh')),
    wp_modus_abdeckung_h: summe(f('wp_modus_abdeckung_h')),
    wp_modus_nicht_aufgeteilt_kwh: Math.max(
      0,
      (wpStrom ?? 0) - (summe(f('wp_modus_strom_heizen_kwh')) ?? 0)
        - (summe(f('wp_modus_strom_kuehlen_kwh')) ?? 0),
    ),
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
    einspeisung_neg_preis_kwh: summe(f('einspeisung_neg_preis_kwh')),
    nicht_vergueteter_erloes_euro: summe(f('nicht_vergueteter_erloes_euro')),
    netzbezug_kosten_euro: summe(f('netzbezug_kosten_euro')),
    // Arbeitspreis-Anteil additiv summieren — NICHT als
    // `netzbezug_kosten_euro − grundgebuehr_euro` nachbilden. Beides ergäbe
    // hier dasselbe, aber die Ø-Preis-Kachel darf, wenn sie jemand in die
    // Jahres-Sicht holt, keine zwölf Grundpreise im Divisor haben.
    netzbezug_arbeitspreis_kosten_euro: summe(f('netzbezug_arbeitspreis_kosten_euro')),
    ev_ersparnis_euro: summe(f('ev_ersparnis_euro')),
    netto_ertrag_euro: summe(f('netto_ertrag_euro')),
    wp_ersparnis_euro: summe(f('wp_ersparnis_euro')),
    emob_ersparnis_euro: summe(f('emob_ersparnis_euro')),
    sonstige_ertraege_euro: summe(f('sonstige_ertraege_euro')) ?? 0,
    sonstige_ausgaben_euro: summe(f('sonstige_ausgaben_euro')) ?? 0,
    sonstige_netto_euro: summe(f('sonstige_netto_euro')) ?? 0,
    anlage_sonstige_ertraege_euro: summe(f('anlage_sonstige_ertraege_euro')) ?? 0,
    anlage_sonstige_ausgaben_euro: summe(f('anlage_sonstige_ausgaben_euro')) ?? 0,
    gesamtnettoertrag_euro: summe(f('gesamtnettoertrag_euro')),
    betriebskosten_anteilig_euro: summe(f('betriebskosten_anteilig_euro')),

    // Tarif-Info: verbrauchsgewichtet, nicht als Monats-Mittel (s. `gewichtet`).
    // Gewichtet wird der EFFEKTIVE Monatspreis — dieselbe Wahl, die die Kachel
    // trifft (`baueMonatKpis`: Ø-Bezugspreis vor Tarif-Arbeitspreis). Sonst
    // fiele in einem Jahr mit dynamischem Tarif der Ø auf den Referenzpreis
    // zurück, obwohl die Kosten darunter mit dem Stundenpreis gerechnet sind.
    netzbezug_preis_cent: gewichtet(netzbezugPreisEffektiv, f('netzbezug_kwh')),
    einspeise_preis_cent: gewichtet(f('einspeise_preis_cent'), f('einspeisung_kwh')),
    // Nur setzen, wenn überhaupt ein Monat einen Ø-Bezugspreis trug — die Kachel
    // liest daran ab, ob sie „dynamischer Tarif" oder „Arbeitspreis aus dem
    // Tarif" unter die Zahl schreibt.
    netzbezug_durchschnittspreis_cent: monate.some((m) => m.netzbezug_durchschnittspreis_cent != null)
      ? gewichtet(netzbezugPreisEffektiv, f('netzbezug_kwh'))
      : null,
    // G19-1 K3: Grundgebühr = Σ der Monats-Grundgebühren; Zählergebühr ist ein
    // JAHRES-Wert vom Tarif → letzter vorhandener Wert, NICHT summieren.
    grundgebuehr_euro: summe(f('grundgebuehr_euro')),
    zaehlergebuehr_euro_jahr: f('zaehlergebuehr_euro_jahr').filter((v): v is number => v != null).at(-1) ?? null,

    // SOLL (Σ Monats-PVGIS); Vorjahr-Vergleich liefert die Jahr-Sicht separat.
    // Das Fenster wird MITSUMMIERT, weil die SOLL-Summe genauso entsteht: der
    // laufende Monat steuert nur seine abgelaufenen Tage bei (N-69). Ohne die
    // beiden Summen wäre die Jahreszahl anteilig, ohne es sagen zu können.
    soll_pv_kwh: summe(f('soll_pv_kwh')),
    soll_pv_tage: summe(f('soll_pv_tage')),
    soll_pv_tage_gesamt: summe(f('soll_pv_tage_gesamt')),
    // Grundlast (R12-1): Σ Energie, Ø Leistung, Anteil aus Summen.
    grundlast_kw: mittel(f('grundlast_kw')),
    grundlast_kwh: glKwh,
    grundlast_anteil_prozent: glAnteil,
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
  /**
   * Die Monate (1–12, aufsteigend), die wirklich in die Summen eingegangen sind.
   *
   * Leer ⇒ dieses Jahr hat mit der Grundgesamtheit keine Überschneidung. Der
   * Aufrufer zeigt dann KEINEN Vergleich — eine Spalte aus lauter 0 wäre eine
   * Aussage über die Anlage und ist keine.
   */
  monate: number[]
}

/**
 * Σ der aggregierten Monatszeilen EINES Jahres — wahlweise nur über eine
 * Monatsauswahl.
 *
 * `auswahl` ist die **Grundgesamtheit** des Vergleichs: die Monate, für die das
 * ANGEZEIGTE Jahr Zeilen hat. Ohne sie stehen im laufenden Jahr sieben gelaufene
 * Monate gegen die zwölf vollen des Vorjahrs (Fund N-37) — dieselbe Frage, die
 * {@link vergleichsAggregatBasis} (`lib/werte/vergleich.ts`) für den Tabellenfuß
 * stellt. Dort fällt die Antwort bewusst anders aus: ein Fuß MUSS die Summe der
 * Spalte über ihm sein und verwirft den Vergleich deshalb lieber ganz. Eine
 * Vergleichsspalte hat diese Bindung nicht — sie darf beschneiden, solange sie
 * das Fenster ausweist (ADR-002/P4 in klein, s. {@link monatsFenster}).
 *
 * Beschnitten wird nach Monatsnummer, nicht nach „die ersten N": eine Lücke
 * mitten im angezeigten Jahr nimmt denselben Monat auch dem Vergleichsjahr.
 */
export function jahrVergleichAus(
  rows: AggregierteMonatsdaten[],
  jahr: number,
  auswahl?: readonly number[] | null,
): JahrVergleich {
  const zulaessig = auswahl ? new Set(auswahl) : null
  const j = rows.filter((r) => r.jahr === jahr && (zulaessig == null || zulaessig.has(r.monat)))
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
    monate: [...new Set(j.map((r) => r.monat))].sort((a, b) => a - b),
  }
}

/**
 * Mittelung mehrerer Jahres-Vergleiche (Ø über die übrigen Jahre).
 *
 * Mit `grundgesamtheit` trägt nur bei, wer sie **ganz** abdeckt. Ein Jahr mit
 * halber Überschneidung — die Anlage lief 2023 erst ab Juni, verglichen wird
 * Jan–Jun — brächte eine Summe über EINEN Monat in einen Ø über sechs. Genau
 * dieser Fehler eine Ebene tiefer, und eine Einzelspalte könnte ihn wenigstens
 * beschriften; ein Mittelwert kann kein Fenster je Jahr tragen. Deshalb fällt
 * das Jahr hier ganz raus statt schief einzugehen — und `count` sagt es
 * („Ø aus 2 Jahren" statt 3).
 *
 * Ohne `grundgesamtheit` bleibt das alte Verhalten (alle Jahre, die überhaupt
 * einen Monat tragen).
 */
export function mittelJahre(
  jahre: JahrVergleich[],
  grundgesamtheit?: readonly number[] | null,
): (JahrVergleich & { count: number }) | null {
  const g = grundgesamtheit && grundgesamtheit.length > 0 ? new Set(grundgesamtheit) : null
  const beitragend = jahre.filter((j) => {
    if (j.monate.length === 0) return false
    if (g == null) return true
    const eigene = new Set(j.monate)
    return [...g].every((m) => eigene.has(m))
  })
  if (beitragend.length === 0) return null
  const m = (f: (j: JahrVergleich) => number | null) => mittel(beitragend.map(f))
  return {
    jahr: 0,
    pv: m((j) => j.pv), ev: m((j) => j.ev), direkt: m((j) => j.direkt),
    einsp: m((j) => j.einsp), netz: m((j) => j.netz), gesamt: m((j) => j.gesamt),
    autarkie: m((j) => j.autarkie),
    monate: [...new Set(beitragend.flatMap((j) => j.monate))].sort((a, b) => a - b),
    count: beitragend.length,
  }
}

/** „Jan–Jul" bzw. „Jan–Feb, Apr–Jul" — zusammenhängende Läufe zusammengefasst. */
function monatsBereiche(monate: number[]): string {
  const teile: string[] = []
  let start = monate[0]
  let vorher = monate[0]
  const schliesse = () => teile.push(start === vorher ? MONAT_KURZ[start] : `${MONAT_KURZ[start]}–${MONAT_KURZ[vorher]}`)
  for (const m of monate.slice(1)) {
    if (m === vorher + 1) { vorher = m; continue }
    schliesse()
    start = m
    vorher = m
  }
  schliesse()
  return teile.join(', ')
}

/**
 * Beschriftung des Vergleichsfensters — oder `null`, wenn nichts zu sagen ist.
 *
 * Die Regel ist bewusst schlicht: **steht dort weniger als ein volles Jahr, muss
 * dranstehen, welche Monate es sind.** Ein voller Zwölfmonats-Wert braucht keine
 * Erklärung, alles andere schon — die Spalte heißt „Vorjahr", und ohne Zusatz
 * liest sie sich als ganzes Jahr.
 *
 * Geprüft wird damit die tatsächliche Deckung, NICHT „läuft das Jahr noch":
 * abgeschlossene Jahre mit Datenlücke fallen genauso darunter, und ein
 * abgeschlossenes Jahr gegen ein volles Vorjahr bleibt unbeschriftet wie bisher.
 * (`beschnitten ⟹ weniger als 12` — die Beschneidung ist der häufigste, aber
 * nicht der einzige Weg zu einem Teil-Fenster.)
 */
export function monatsFenster(vergleich: JahrVergleich | null): string | null {
  return monatsFensterAus(vergleich?.monate)
}

/** Dieselbe Regel für eine nackte Monatsmenge (IST-Spalte, s. {@link monatsFenster}). */
export function monatsFensterAus(monate: readonly number[] | null | undefined): string | null {
  if (!monate || monate.length === 0 || monate.length >= 12) return null
  return monatsBereiche([...monate])
}

/**
 * Fenster der KENNZAHLEN-Kacheln — gesetzt genau dann, wenn die Kopfzahl mehr
 * Monate umfasst als der Vergleich darunter (ADR-002/P4).
 *
 * Die 12-Monats-Ausnahme von {@link monatsFensterAus} gilt hier NICHT: im Dezember
 * deckt die Kopfzahl Jan–Dez ab, der Vergleich aber nur Jan–Nov — dann ist gerade
 * ein volles Fenster erklärungsbedürftig, weil es den angefangenen Dezember enthält.
 */
export function kennzahlenFensterAus(
  kopfMonate: readonly number[],
  vergleichsMonate: readonly number[],
): string | null {
  if (kopfMonate.length === 0) return null
  if (kopfMonate.length === vergleichsMonate.length
    && kopfMonate.every((m, i) => m === vergleichsMonate[i])) return null
  return monatsBereiche([...kopfMonate])
}
