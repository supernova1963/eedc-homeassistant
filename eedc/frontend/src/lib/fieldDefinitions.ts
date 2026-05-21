/**
 * Kanonische Felddefinitionen für Monatsdaten-Eingabe.
 *
 * Mirror von backend/core/field_definitions.py — Single Source of Truth.
 * Wird von MonatsdatenForm (Sections) und ggf. weiteren Eingabekomponenten verwendet.
 *
 * Kanonische Feldnamen (Naming-History):
 *   speicher_ladung_netz_kwh → ladung_netz_kwh   (Speicher Arbitrage-Netzladung)
 *   entladung_v2h_kwh        → v2h_entladung_kwh  (E-Auto V2H)
 */

export interface FeldDefinition {
  feld: string
  label: string
  einheit: string
  typ?: 'number' | 'text'
  datentyp?: 'float' | 'int'
  placeholder?: string
  hint?: string
  bedingung?: string
  // #281: konditionelles Label — trifft eine Bedingung zu, ersetzt sie `label`.
  label_wenn?: Record<string, string>
}

// =============================================================================
// Basis-Felder (Monatsdaten — Zählerwerte)
// =============================================================================

export const BASIS_FELDER: FeldDefinition[] = [
  { feld: 'einspeisung_kwh',        label: 'Einspeisung',     einheit: 'kWh'    },
  { feld: 'netzbezug_kwh',          label: 'Netzbezug',       einheit: 'kWh'    },
  { feld: 'globalstrahlung_kwh_m2', label: 'Globalstrahlung', einheit: 'kWh/m²' },
  { feld: 'sonnenstunden',          label: 'Sonnenstunden',   einheit: 'h'      },
  { feld: 'durchschnittstemperatur',label: 'Ø Temperatur',    einheit: '°C'     },
]

// =============================================================================
// Investitions-Felder nach Typ (inkl. Bedingungs-Marker)
// =============================================================================

const SPEICHER_FELDER: FeldDefinition[] = [
  // #281: Mit Netzladung ist "Ladung" mehrdeutig — `ladung_kwh` ist die
  // Gesamtladung (PV + Netz), `ladung_netz_kwh` ⊆ `ladung_kwh`.
  { feld: 'ladung_kwh',            label: 'Ladung',     einheit: 'kWh',
    label_wenn: { laedt_aus_netz: 'Ladung (gesamt, inkl. Netz)' } },
  { feld: 'entladung_kwh',         label: 'Entladung',  einheit: 'kWh'    },
  { feld: 'ladung_netz_kwh',       label: 'Netzladung', einheit: 'kWh',    bedingung: 'laedt_aus_netz' },
  { feld: 'speicher_ladepreis_cent', label: 'Ø Ladepreis', einheit: 'ct/kWh', bedingung: 'arbitrage_faehig' },
]

// #120: Wording-Schaerfung — Strom (elektrisch) vs. Waerme (thermisch).
// rcmcronny meldete 2026-04-13, dass „Heizenergie" mit Stromverbrauch
// verwechselt wird → COP=1 verraet das, ist aber nicht selbsterklaerend.
// „Heizwaerme" + Tooltip macht klar, dass es die abgegebene Waermemenge
// (z.B. von einem Waermemengenzaehler) ist, nicht der WP-Strom.
const WAERMEPUMPE_FELDER: FeldDefinition[] = [
  { feld: 'stromverbrauch_kwh',   label: 'Stromverbrauch',   einheit: 'kWh', bedingung: '!getrennte_strommessung',
    hint: 'Stromaufnahme der WP (elektrisch)' },
  { feld: 'strom_heizen_kwh',     label: 'Strom Heizen',     einheit: 'kWh', bedingung: 'getrennte_strommessung',
    hint: 'Stromaufnahme nur für Heizung (elektrisch)' },
  { feld: 'strom_warmwasser_kwh', label: 'Strom Warmwasser', einheit: 'kWh', bedingung: 'getrennte_strommessung',
    hint: 'Stromaufnahme nur für Warmwasser (elektrisch)' },
  { feld: 'heizenergie_kwh',      label: 'Heizwärme',        einheit: 'kWh',
    hint: 'Abgegebene Heizwärme (thermisch) — COP = Heizwärme / Strom' },
  { feld: 'warmwasser_kwh',       label: 'Warmwasser',       einheit: 'kWh',
    hint: 'Abgegebene Warmwasser-Wärme (thermisch)' },
]

const EAUTO_FELDER: FeldDefinition[] = [
  { feld: 'km_gefahren',       label: 'Gefahrene km', einheit: 'km',  placeholder: 'z.B. 1200' },
  { feld: 'verbrauch_kwh',     label: 'Verbrauch',    einheit: 'kWh', placeholder: 'z.B. 216'  },
  { feld: 'ladung_pv_kwh',     label: 'Heim: PV',     einheit: 'kWh', placeholder: 'z.B. 130'  },
  { feld: 'ladung_netz_kwh',   label: 'Heim: Netz',   einheit: 'kWh', placeholder: 'z.B. 50'   },
  { feld: 'ladung_extern_kwh', label: 'Extern',       einheit: 'kWh', placeholder: 'z.B. 36'   },
  { feld: 'ladung_extern_euro',label: 'Extern Kosten',einheit: '€',   placeholder: 'z.B. 18.00'},
  { feld: 'v2h_entladung_kwh', label: 'V2H Entladung',einheit: 'kWh', placeholder: 'z.B. 25', bedingung: 'v2h_faehig' },
]

const WALLBOX_FELDER: FeldDefinition[] = [
  { feld: 'ladung_kwh',    label: 'Ladung gesamt', einheit: 'kWh', placeholder: 'z.B. 200' },
  { feld: 'ladung_pv_kwh', label: 'Ladung PV',     einheit: 'kWh', placeholder: 'z.B. 80'  },
  { feld: 'ladevorgaenge', label: 'Ladevorgänge',  einheit: '',    placeholder: 'z.B. 12', datentyp: 'int' },
]

const BALKONKRAFTWERK_FELDER: FeldDefinition[] = [
  { feld: 'pv_erzeugung_kwh',      label: 'Erzeugung',         einheit: 'kWh' },
  { feld: 'eigenverbrauch_kwh',    label: 'Eigenverbrauch',    einheit: 'kWh' },
  { feld: 'speicher_ladung_kwh',   label: 'Speicher Ladung',   einheit: 'kWh', bedingung: 'hat_speicher' },
  { feld: 'speicher_entladung_kwh',label: 'Speicher Entladung',einheit: 'kWh', bedingung: 'hat_speicher' },
]

const SONSTIGES_FELDER: Record<string, FeldDefinition[]> = {
  erzeuger: [
    { feld: 'erzeugung_kwh',     label: 'Erzeugung',     einheit: 'kWh' },
    { feld: 'eigenverbrauch_kwh',label: 'Eigenverbrauch',einheit: 'kWh' },
    { feld: 'einspeisung_kwh',   label: 'Einspeisung',   einheit: 'kWh' },
  ],
  verbraucher: [
    { feld: 'verbrauch_sonstig_kwh',label: 'Verbrauch',  einheit: 'kWh' },
    { feld: 'bezug_pv_kwh',         label: 'davon PV',   einheit: 'kWh' },
    { feld: 'bezug_netz_kwh',        label: 'davon Netz', einheit: 'kWh' },
  ],
  speicher: [
    { feld: 'erzeugung_kwh',        label: 'Erzeugung/Entladung',einheit: 'kWh' },
    { feld: 'verbrauch_sonstig_kwh',label: 'Verbrauch/Ladung',   einheit: 'kWh' },
  ],
}

// Alte Feldnamen → neue kanonische Namen (Lese-Kompatibilität mit alten DB-Einträgen)
export const LEGACY_FELDNAMEN: Record<string, string> = {
  speicher_ladung_netz_kwh: 'ladung_netz_kwh',
  entladung_v2h_kwh:        'v2h_entladung_kwh',
}

// =============================================================================
// Hilfsfunktionen
// =============================================================================

type InvParameter = Record<string, unknown>

/**
 * Gibt die aufgelösten Felder für eine Investition zurück.
 * Filtert konditionelle Felder basierend auf inv.parameter.
 */
export function getFelderFuerInvestition(
  typ: string,
  parameter: InvParameter | null | undefined
): FeldDefinition[] {
  const params = parameter ?? {}

  const allFields = ((): FeldDefinition[] => {
    switch (typ) {
      case 'pv-module':
      case 'wechselrichter':
        return [{ feld: 'pv_erzeugung_kwh', label: 'PV-Erzeugung', einheit: 'kWh' }]
      case 'speicher':
        return SPEICHER_FELDER
      case 'waermepumpe':
        return WAERMEPUMPE_FELDER
      case 'e-auto':
        return EAUTO_FELDER
      case 'wallbox':
        return WALLBOX_FELDER
      case 'balkonkraftwerk':
        return BALKONKRAFTWERK_FELDER
      case 'sonstiges':
        return getFelderFuerSonstiges((params.kategorie as string) ?? 'erzeuger')
      default:
        return []
    }
  })()

  const getrennt = Boolean(params.getrennte_strommessung)
  const arbitrage = Boolean(params.arbitrage_faehig)
  // Arbitrage impliziert Netzladung — Flag ist nur Erfassungs-Schalter.
  const laedtAusNetz = Boolean(params.laedt_aus_netz) || arbitrage
  const v2h = Boolean(params.v2h_faehig || params.nutzt_v2h)
  const hatSpeicher = Boolean(params.hat_speicher)

  // #281: konditionelles Label — dieselben Bedingungs-Keys wie `bedingung`.
  const bedingungsWerte: Record<string, boolean> = {
    getrennte_strommessung: getrennt,
    arbitrage_faehig: arbitrage,
    laedt_aus_netz: laedtAusNetz,
    v2h_faehig: v2h,
    hat_speicher: hatSpeicher,
  }

  return allFields.filter(f => {
    if (!f.bedingung) return true
    if (f.bedingung === 'getrennte_strommessung')  return getrennt
    if (f.bedingung === '!getrennte_strommessung') return !getrennt
    if (f.bedingung === 'arbitrage_faehig')        return arbitrage
    if (f.bedingung === 'laedt_aus_netz')          return laedtAusNetz
    if (f.bedingung === 'v2h_faehig')              return v2h
    if (f.bedingung === 'hat_speicher')            return hatSpeicher
    return true
  }).map(({ bedingung: _b, label_wenn, ...rest }) => {
    if (label_wenn) {
      for (const [cond, altLabel] of Object.entries(label_wenn)) {
        if (bedingungsWerte[cond]) return { ...rest, label: altLabel }
      }
    }
    return rest
  })
}

/**
 * Gibt Felder für eine Sonstiges-Investition nach Kategorie zurück.
 */
export function getFelderFuerSonstiges(kategorie: string): FeldDefinition[] {
  return SONSTIGES_FELDER[kategorie] ?? SONSTIGES_FELDER.erzeuger
}

/**
 * Liest einen Wert aus verbrauch_daten — prüft auch alte/legacy Feldnamen.
 * Gibt leeren String zurück wenn nicht vorhanden (für Input-Felder).
 */
export function readFeldWert(
  daten: Record<string, unknown>,
  feldname: string
): string {
  const canonical = daten[feldname]
  if (canonical !== undefined && canonical !== null) return String(canonical)
  // Rückwärtskompatibilität: alten Key prüfen
  const legacyKey = Object.entries(LEGACY_FELDNAMEN).find(([, v]) => v === feldname)?.[0]
  if (legacyKey) {
    const legacy = daten[legacyKey]
    if (legacy !== undefined && legacy !== null) return String(legacy)
  }
  return ''
}
