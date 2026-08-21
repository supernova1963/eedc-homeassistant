/**
 * Geteilte Helfer/Konstanten für InvestitionForm + die typ-spezifischen
 * Parameterfelder (Slice 5, Forms→V4 — Split des früheren 1461-Z.-Monolithen).
 */
import type { InvestitionTyp } from '../../../types'
import {
  PARAM_E_AUTO_DEFAULTS,
  PARAM_SPEICHER_DEFAULTS,
  PARAM_WAERMEPUMPE_DEFAULTS,
  PARAM_WALLBOX_DEFAULTS,
  PARAM_WECHSELRICHTER_DEFAULTS,
  PARAM_BALKONKRAFTWERK_DEFAULTS,
  PARAM_SONSTIGES_DEFAULTS,
} from '../../../lib'
import type { Innengeraet } from '../../../lib/investitionParameter'
import type { ParamWert } from './InvestitionTypFelder/types'
import type { SelectItem } from '../../ui/Select'

/**
 * Liefert einen Form-tauglichen String — Eingabewert wenn vorhanden, sonst Default.
 * Defaults stammen aus lib/investitionParameter.ts (Single Source of Truth, gemeinsam mit Backend).
 */
export const paramStr = (val: unknown, fallback?: unknown): string => {
  if (val !== undefined && val !== null && val !== '') return String(val)
  if (fallback !== undefined && fallback !== null) return String(fallback)
  return ''
}

// Azimut-Mapping: Himmelsrichtung → PVGIS-Grad (0=Süd, -90=Ost, 90=West, ±180=Nord)
export const AUSRICHTUNG_GRAD_MAP: Record<string, number> = {
  'Süd': 0, 'Südost': -45, 'Ost': -90, 'Nordost': -135,
  'Nord': 180, 'Nordwest': 135, 'West': 90, 'Südwest': 45,
}

export function ausrichtungToGrad(ausrichtung: string): string {
  return (AUSRICHTUNG_GRAD_MAP[ausrichtung] ?? 0).toString()
}

export function gradToAusrichtung(grad: number): string {
  let closest = 'Süd'
  let minDiff = 360
  for (const [name, deg] of Object.entries(AUSRICHTUNG_GRAD_MAP)) {
    let diff = Math.abs(grad - deg)
    if (diff > 180) diff = 360 - diff
    if (diff < minDiff) {
      minDiff = diff
      closest = name
    }
  }
  return closest
}

/** Ausrichtungs-Optionen (Select-SoT) — geteilt von PV-Modul + Balkonkraftwerk. */
export const AUSRICHTUNG_OPTIONEN: SelectItem[] = [
  { value: 'Süd', label: 'Süd (0°)' },
  { value: 'Südost', label: 'Südost (-45°)' },
  { value: 'Ost', label: 'Ost (-90°)' },
  { value: 'Nordost', label: 'Nordost (-135°)' },
  { value: 'Nord', label: 'Nord (180°)' },
  { value: 'Nordwest', label: 'Nordwest (135°)' },
  { value: 'West', label: 'West (90°)' },
  { value: 'Südwest', label: 'Südwest (45°)' },
  { value: 'Ost-West', label: 'Ost-West (gemischt)' },
]

// ── Parent-Kind-Beziehungen — Single Source of Truth (Client) ───────────────
// Pendant zu `models/investition.py::ERLAUBTE_PARENT_TYPEN`. Die Regel stand
// bis 2026-07-31 in drei uneinigen Kopien (hier, `useSetupWizard.ts` und
// `crud.py::get_parent_options`); nur diese kannte das Balkonkraftwerk.
// Wer die Regel braucht, importiert `parentTypenFuer` — nicht die Konstante,
// damit die Array-/Einzelwert-Fallunterscheidung nur EINMAL existiert.
// N-266: `pv-module` darf auch unter ein Balkonkraftwerk. Ein BKW trägt EINE
// Ausrichtung und EINE Neigung — zwei Module über Eck waren damit nicht
// abbildbar, und der Ausweg über *Einstellungen → PV-Module* war gesperrt, weil
// ein BKW kein erlaubter Parent war (Melder: Discussion #366, Forum T89667 #172).
export const PARENT_MAPPING: Partial<Record<InvestitionTyp, InvestitionTyp | InvestitionTyp[]>> = {
  'pv-module': ['wechselrichter', 'balkonkraftwerk'],      // Pflicht — BKW seit N-266
  'speicher': ['wechselrichter', 'balkonkraftwerk'],       // Optional — Hybrid-WR oder BKW-Akku (beide DC, s. N-268)
}
export const PARENT_REQUIRED: InvestitionTyp[] = ['pv-module']

export const PARENT_TYPE_LABELS: Record<string, string> = {
  'wechselrichter': 'Wechselrichter',
  'balkonkraftwerk': 'Balkonkraftwerk',
}

/**
 * Nennleistung eines Balkonkraftwerks in kWp aus Anzahl × Wp — Client-SoT (F-32).
 *
 * **Warum das hier steht und nicht in drei Formularen.** Die Spalte
 * `Investition.leistung_kwp` ist beim BKW ein **abgeleiteter** Wert: gepflegt
 * werden „Leistung pro Modul (Wp)" und „Anzahl Module" im `parameter`. Wer die
 * Spalte nicht mitschreibt, erzeugt genau F-32 — der Einrichtungsassistent tat
 * das, und die Prognose einer reinen BKW-Anlage fiel auf HTTP 400. Die Formel
 * stand danach an drei Stellen; Regel 0a verlangt die Zentrale statt der
 * vierten Kopie.
 *
 * **Rückgabe `null` heißt „Feld leeren", nicht „0".** Wird eine der beiden
 * Eingaben geleert, gibt es keine abgeleitete Nennleistung mehr — ein
 * stehengebliebener Altwert wäre eine Leistung, die niemand gepflegt hat
 * (dieselbe Falle wie die nicht lösbare Wechselrichter-Zuordnung, JayJay
 * v4.0.0). `null` ist die Nutzlast-Sprache von {@link InvestitionUpdate};
 * Schreibpfade, die nur `undefined` senden können, behalten den Altwert still.
 * Eine 0 wäre die 0-Werte-Falle: sie sieht wie eine Messung aus.
 */
export function bkwLeistungKwp(
  anzahl: number | string | undefined,
  leistungWp: number | string | undefined,
): number | null {
  const n = typeof anzahl === 'number' ? anzahl : parseInt(String(anzahl ?? ''), 10)
  const wp = typeof leistungWp === 'number' ? leistungWp : parseInt(String(leistungWp ?? ''), 10)
  if (!Number.isFinite(n) || !Number.isFinite(wp) || n <= 0 || wp <= 0) return null
  return (n * wp) / 1000
}

/** Erlaubte Parent-Typen eines Investitions-Typs — immer als Liste. */
export function parentTypenFuer(typ: InvestitionTyp): InvestitionTyp[] {
  const raw = PARENT_MAPPING[typ]
  if (!raw) return []
  return Array.isArray(raw) ? raw : [raw]
}

// Typ-Label Mapping
export const typLabels: Record<InvestitionTyp, string> = {
  'e-auto': 'E-Auto',
  'waermepumpe': 'Wärmepumpe',
  'speicher': 'Speicher',
  'wallbox': 'Wallbox',
  'wechselrichter': 'Wechselrichter',
  'pv-module': 'PV-Module',
  'balkonkraftwerk': 'Balkonkraftwerk',
  'sonstiges': 'Sonstiges',
}

/**
 * Typen, bei denen ein **Ertrag/Jahr** an der Investition gepflegt werden kann
 * (Konzept §8/1, `einsparung_prognose_jahr`).
 *
 * Die Liste spiegelt den `else`-Zweig der ROI-Typkette in
 * `backend/api/routes/investitionen/crud.py` — nur dort wird das Feld gelesen.
 * Für alle anderen Typen rechnet eedc die Jahres-Einsparung selbst (PV,
 * Speicher, WP, E-Auto, BKW); ein Eingabefeld wäre dort ohne Wirkung.
 */
export const ERTRAGSFELD_TYPEN: InvestitionTyp[] = ['wallbox', 'sonstiges']

// Kontextabhängige Hints für Alternative Kosten
//
// F-41 (#383): Der WP-Hint nannte nur den Regelfall und verschwieg, dass 0 eine
// gültige Antwort ist. Wer im Neubau baut oder eine Klimaanlage als Komfortgerät
// führt, hat keine vermiedene Heizungs-Investition — und las trotzdem im
// Daten-Check „Alternativkosten fehlen", ohne den Weg heraus zu sehen. Fünf
// andere Typen tragen den Zusatz seit jeher.
export const alternativkostenHints: Record<InvestitionTyp, string> = {
  'e-auto': 'Kosten eines vergleichbaren Verbrenners (für ROI-Berechnung)',
  'waermepumpe': 'Kosten einer neuen Gas-/Ölheizung (für ROI-Berechnung) - im Neubau meist 0',
  'speicher': 'Meist 0 - es gibt keine echte Alternative',
  'wallbox': 'Meist 0 - es gibt keine echte Alternative',
  'wechselrichter': 'Meist 0 - es gibt keine echte Alternative',
  'pv-module': 'Meist 0 - es gibt keine echte Alternative',
  'balkonkraftwerk': 'Meist 0 - es gibt keine echte Alternative',
  'sonstiges': 'Kosten einer Alternative (falls vorhanden)',
}

/**
 * Initiale typ-spezifische Parameter-Werte (Form-Strings/Booleans) aus der
 * bestehenden Investition + SoT-Defaults. Unverändert aus dem alten Monolithen.
 */
export function getInitialParamData(
  typ: InvestitionTyp,
  params: Record<string, unknown> = {},
): Record<string, ParamWert> {
  switch (typ) {
    case 'e-auto':
      return {
        batteriekapazitaet_kwh: paramStr(params.batteriekapazitaet_kwh),
        verbrauch_kwh_100km: paramStr(params.verbrauch_kwh_100km, PARAM_E_AUTO_DEFAULTS.verbrauch_kwh_100km),
        jahresfahrleistung_km: paramStr(params.jahresfahrleistung_km, PARAM_E_AUTO_DEFAULTS.jahresfahrleistung_km),
        pv_ladeanteil_prozent: paramStr(params.pv_ladeanteil_prozent, PARAM_E_AUTO_DEFAULTS.pv_ladeanteil_prozent),
        vergleich_verbrauch_l_100km: paramStr(params.vergleich_verbrauch_l_100km, PARAM_E_AUTO_DEFAULTS.vergleich_verbrauch_l_100km),
        benzinpreis_euro: paramStr(params.benzinpreis_euro, PARAM_E_AUTO_DEFAULTS.benzinpreis_euro),
        // #331: bewusst OHNE Default-Argument — das leere Feld ist die Aussage
        // „dieses Fahrzeug fährt rein elektrisch". Ein vorbelegter Wert würde
        // aus jedem Bestands-BEV beim ersten Speichern einen Hybrid machen.
        eigener_verbrauch_l_100km: paramStr(params.eigener_verbrauch_l_100km),
        elektrischer_fahranteil_prozent: paramStr(params.elektrischer_fahranteil_prozent),
        v2h_faehig: (params.v2h_faehig as boolean) ?? PARAM_E_AUTO_DEFAULTS.v2h_faehig,
        v2h_entladeleistung_kw: paramStr(params.v2h_entladeleistung_kw),
        ist_dienstlich: (params.ist_dienstlich as boolean) ?? PARAM_E_AUTO_DEFAULTS.ist_dienstlich,
      }
    case 'speicher': {
      const arbitrage = (params.arbitrage_faehig as boolean) ?? PARAM_SPEICHER_DEFAULTS.arbitrage_faehig
      // Arbitrage impliziert Netzladung — Initial-State spiegelt die Implikation.
      const laedtAusNetzGespeichert = (params.laedt_aus_netz as boolean) ?? PARAM_SPEICHER_DEFAULTS.laedt_aus_netz
      return {
        kapazitaet_kwh: paramStr(params.kapazitaet_kwh),
        nutzbare_kapazitaet_kwh: paramStr(params.nutzbare_kapazitaet_kwh),
        max_ladeleistung_kw: paramStr(params.max_ladeleistung_kw),
        max_entladeleistung_kw: paramStr(params.max_entladeleistung_kw),
        wirkungsgrad_prozent: paramStr(params.wirkungsgrad_prozent, PARAM_SPEICHER_DEFAULTS.wirkungsgrad_prozent),
        laedt_aus_netz: arbitrage ? true : laedtAusNetzGespeichert,
        arbitrage_faehig: arbitrage,
        // #351: leer = „Automatisch (aus der Zuordnung)". Bewusst OHNE Default —
        // eine Vorbelegung hier würde beim ersten Speichern die Ableitung als
        // gepflegten Wert festschreiben, und wer den Wechselrichter später
        // zuordnet, behielte still die alte Annahme.
        kopplung: paramStr(params.kopplung),
      }
    }
    case 'waermepumpe':
      return {
        leistung_kw: paramStr(params.leistung_kw),
        // Wärmepumpenart für fairen Community-Vergleich
        wp_art: paramStr(params.wp_art, PARAM_WAERMEPUMPE_DEFAULTS.wp_art),
        // #263 — die Innengeräte-Liste wandert unverändert durch das Formular.
        // Sie ist selbst der Schalter: „Multisplit" wird aus ihrer Länge
        // abgeleitet und nirgends gespeichert.
        innengeraete: Array.isArray(params.innengeraete)
          ? (params.innengeraete as Innengeraet[])
          : [],
        // Modus-Auswahl: gesamt_jaz (Standard), scop (EU-Label) oder getrennte_cops
        effizienz_modus: paramStr(params.effizienz_modus, PARAM_WAERMEPUMPE_DEFAULTS.effizienz_modus),
        // Für Modus "gesamt_jaz"
        jaz: paramStr(params.jaz, PARAM_WAERMEPUMPE_DEFAULTS.jaz),
        // Für Modus "scop" (EU-Label)
        scop_heizung: paramStr(params.scop_heizung, PARAM_WAERMEPUMPE_DEFAULTS.scop_heizung),
        scop_warmwasser: paramStr(params.scop_warmwasser, PARAM_WAERMEPUMPE_DEFAULTS.scop_warmwasser),
        vorlauftemperatur: paramStr(params.vorlauftemperatur, PARAM_WAERMEPUMPE_DEFAULTS.vorlauftemperatur),
        // Für Modus "getrennte_cops"
        cop_heizung: paramStr(params.cop_heizung, PARAM_WAERMEPUMPE_DEFAULTS.cop_heizung),
        cop_warmwasser: paramStr(params.cop_warmwasser, PARAM_WAERMEPUMPE_DEFAULTS.cop_warmwasser),
        // Getrennte Strommessung (Heizen/Warmwasser) — Bug #8 historisch als String 'true'/'false';
        // wird bei Phase 6 auf echten Boolean migriert. Bis dahin tolerieren wir beides beim Lesen.
        getrennte_strommessung: (params.getrennte_strommessung === true || params.getrennte_strommessung === 'true') ? 'true' : 'false',
        // Wärmebedarf (getrennt). N-87: Bei einer Split-Klimaanlage NICHT
        // vorbelegen — die Vorbelegung wurde beim Speichern mit übernommen und
        // sah danach aus wie eine Anwender-Eingabe; die ROI-Auswertung machte
        // daraus eine Ersparnis gegen eine nie ersetzte Gasheizung. Ein bereits
        // gespeicherter Wert bleibt erhalten (`params.…` gewinnt), es wird nur
        // nichts mehr erfunden.
        heizwaermebedarf_kwh: params.wp_art === 'luft_luft'
          ? paramStr(params.heizwaermebedarf_kwh)
          : paramStr(params.heizwaermebedarf_kwh, PARAM_WAERMEPUMPE_DEFAULTS.heizwaermebedarf_kwh),
        warmwasserbedarf_kwh: params.wp_art === 'luft_luft'
          ? paramStr(params.warmwasserbedarf_kwh)
          : paramStr(params.warmwasserbedarf_kwh, PARAM_WAERMEPUMPE_DEFAULTS.warmwasserbedarf_kwh),
        // Vergleich mit alter Heizung
        pv_anteil_prozent: paramStr(params.pv_anteil_prozent, PARAM_WAERMEPUMPE_DEFAULTS.pv_anteil_prozent),
        alter_energietraeger: paramStr(params.alter_energietraeger, PARAM_WAERMEPUMPE_DEFAULTS.alter_energietraeger),
        alter_preis_cent_kwh: paramStr(params.alter_preis_cent_kwh, PARAM_WAERMEPUMPE_DEFAULTS.alter_preis_cent_kwh),
        alternativ_zusatzkosten_jahr: paramStr(params.alternativ_zusatzkosten_jahr, PARAM_WAERMEPUMPE_DEFAULTS.alternativ_zusatzkosten_jahr),
        sg_ready: (params.sg_ready as boolean) ?? PARAM_WAERMEPUMPE_DEFAULTS.sg_ready,
      }
    case 'wallbox':
      return {
        max_ladeleistung_kw: paramStr(params.max_ladeleistung_kw, PARAM_WALLBOX_DEFAULTS.max_ladeleistung_kw),
        bidirektional: (params.bidirektional as boolean) ?? PARAM_WALLBOX_DEFAULTS.bidirektional,
        pv_optimiert: (params.pv_optimiert as boolean) ?? PARAM_WALLBOX_DEFAULTS.pv_optimiert,
        ist_dienstlich: (params.ist_dienstlich as boolean) ?? PARAM_WALLBOX_DEFAULTS.ist_dienstlich,
      }
    case 'wechselrichter':
      return {
        max_leistung_kw: paramStr(params.max_leistung_kw),
        wirkungsgrad_prozent: paramStr(params.wirkungsgrad_prozent, PARAM_WECHSELRICHTER_DEFAULTS.wirkungsgrad_prozent),
        hybrid: (params.hybrid as boolean) ?? PARAM_WECHSELRICHTER_DEFAULTS.hybrid,
      }
    case 'pv-module':
      return {
        anzahl_module: paramStr(params.anzahl_module),
        modul_leistung_wp: paramStr(params.modul_leistung_wp),
        modul_typ: paramStr(params.modul_typ),
      }
    case 'balkonkraftwerk':
      return {
        leistung_wp: paramStr(params.leistung_wp),
        anzahl: paramStr(params.anzahl, PARAM_BALKONKRAFTWERK_DEFAULTS.anzahl),
        ausrichtung: paramStr(params.ausrichtung, PARAM_BALKONKRAFTWERK_DEFAULTS.ausrichtung),
        neigung_grad: paramStr(params.neigung_grad, PARAM_BALKONKRAFTWERK_DEFAULTS.neigung_grad),
        hat_speicher: (params.hat_speicher as boolean) ?? PARAM_BALKONKRAFTWERK_DEFAULTS.hat_speicher,
        speicher_kapazitaet_wh: paramStr(params.speicher_kapazitaet_wh),
      }
    case 'sonstiges':
      return {
        kategorie: paramStr(params.kategorie, PARAM_SONSTIGES_DEFAULTS.kategorie),
        beschreibung: paramStr(params.beschreibung),
      }
    default:
      return {}
  }
}
