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

import { PARAM_SONSTIGES_DEFAULTS, istLuftLuft } from './investitionParameter'

export interface FeldDefinition {
  feld: string
  label: string
  einheit: string
  typ?: 'number' | 'text'
  datentyp?: 'float' | 'int'
  placeholder?: string
  hint?: string
  /**
   * Bedingung, unter der das Feld überhaupt erscheint — ein Schlüssel aus
   * `bedingungsWerte`, optional mit `!` negiert.
   *
   * **Eine Liste bedeutet UND** (B5): `strom_warmwasser_kwh` verlangt getrennte
   * Strommessung **und** keine Split-Klimaanlage. Spiegel von
   * `field_definitions.bedingung_erfuellt` — wer hier etwas ändert, ändert es
   * dort mit, sonst zeigen Monatsabschluss und Backend verschiedene Felder.
   */
  bedingung?: string | string[]
  // #281: konditionelles Label — trifft eine Bedingung zu, ersetzt sie `label`.
  label_wenn?: Record<string, string>
  /**
   * #377: Der Parameter-Schlüssel, unter dem die Einheit am **Gerät** steht.
   *
   * Steht er, ist `einheit` oben nur der Rückfall — die wahre Einheit kommt aus
   * `inv.parameter[einheitJeGeraet]`. Gelesen wird das ausschließlich über
   * {@link einheitFuer}; wer stattdessen `feld.einheit` nimmt, zeigt beim
   * Zählerstand nichts an. Spiegel von `field_definitions.py::FELD_EINHEIT_JE_GERAET`.
   */
  einheitJeGeraet?: string
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
  // B5: die zweite Hälfte von N-304 — eine Split-Klimaanlage hat keinen
  // Warmwasserkreis, also auch keinen Warmwasser-STROM. Zwei Bedingungen (UND).
  { feld: 'strom_warmwasser_kwh', label: 'Strom Warmwasser', einheit: 'kWh',
    bedingung: ['getrennte_strommessung', '!luft_luft'],
    hint: 'Stromaufnahme nur für Warmwasser (elektrisch)' },
  { feld: 'heizenergie_kwh',      label: 'Heizwärme',        einheit: 'kWh',
    hint: 'Abgegebene Heizwärme (thermisch) — COP = Heizwärme / Strom' },
  { feld: 'warmwasser_kwh',       label: 'Warmwasser',       einheit: 'kWh', bedingung: '!luft_luft',
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
    // Konzept §9 Weg 2: eigener Einspeisetarif, den eedc nicht kennen kann
    // (ein Satz je Anlage). Spiegel von `field_definitions.py`.
    { feld: 'einspeise_erloes_euro', label: 'Einspeise-Erlös', einheit: '€' },
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
  // #377 — Verbrauchszähler (Gas, Wasser, Heizöl …). Spiegel von
  // `field_definitions.py::INVESTITION_FELDER["sonstiges"]["zaehler"]`.
  //
  // ⚑ **Die leere Einheit ist Absicht und die eigentliche Sicherung.** Was
  // neben der Zahl steht, hängt am Gerät (`zaehler_einheit`) und wird über
  // `einheitFuer()` geholt. Träge das Feld hier „m³", wäre die Einheit eine
  // Eigenschaft des Feldes — und jeder Anwender mit einem Öltank läse Kubik-
  // meter Heizöl.
  zaehler: [
    { feld: 'zaehlerstand', label: 'Zählerstand', einheit: '', einheitJeGeraet: 'zaehler_einheit' },
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
        // Ohne gepflegte Kategorie wird hier NICHT geraten (N-244) — die
        // Entscheidung liegt in `getFelderFuerSonstiges`.
        return getFelderFuerSonstiges(params.kategorie as string | undefined)
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
  // N-304: eine Split-Klimaanlage hat keinen Warmwasserkreis. Spiegel der
  // Backend-Regel (`field_definitions.py`, `ist_luft_luft_waermepumpe`) —
  // Altbestand ohne `wp_art` gilt NICHT als Klimaanlage und behält das Feld.
  // N-306 (26.08.2026): über den EINEN Client-Leser statt inline.
  const luftLuft = istLuftLuft(params)

  // #281: konditionelles Label — dieselben Bedingungs-Keys wie `bedingung`.
  const bedingungsWerte: Record<string, boolean> = {
    getrennte_strommessung: getrennt,
    arbitrage_faehig: arbitrage,
    laedt_aus_netz: laedtAusNetz,
    v2h_faehig: v2h,
    hat_speicher: hatSpeicher,
    // `luft_luft` fehlte hier, während die Filter-Kette darunter es kannte —
    // ein `label_wenn: { luft_luft: … }` wäre im Client still wirkungslos
    // geblieben, im Backend aber nicht. Beide Wege lesen jetzt dieselbe Map.
    luft_luft: luftLuft,
  }

  // Spiegel von `field_definitions.bedingung_erfuellt`: ein Schlüssel aus
  // `bedingungsWerte`, optional mit `!` negiert; eine Liste gilt als UND.
  // Ein unbekannter Schlüssel ZEIGT das Feld (fail-open) — ein Tippfehler darf
  // kein zugeordnetes Feld unsichtbar machen. Begründung im Backend-Docstring.
  const erfuellt = (bedingung: string | string[] | undefined): boolean => {
    if (!bedingung) return true
    const tokens = typeof bedingung === 'string' ? [bedingung] : bedingung
    return tokens.every(token => {
      const negiert = token.startsWith('!')
      const schluessel = negiert ? token.slice(1) : token
      if (!(schluessel in bedingungsWerte)) return true
      return bedingungsWerte[schluessel] !== negiert
    })
  }

  return allFields.filter(f => erfuellt(f.bedingung)).map(({ bedingung: _b, label_wenn, ...rest }) => {
    if (label_wenn) {
      for (const [cond, altLabel] of Object.entries(label_wenn)) {
        if (bedingungsWerte[cond]) return { ...rest, label: altLabel }
      }
    }
    return rest
  })
}

/**
 * Die *Sonstiges*-Kategorien **ohne Stromrichtung** (#377) — der dritte Zustand.
 *
 * Spiegel von `field_definitions.SONSTIGES_ZAEHLER_KATEGORIEN`. Ein Zähler ist
 * weder Erzeuger noch Verbraucher: Er führt gar keinen Strom. Jede Stelle, die
 * „Erzeuger oder Verbraucher?" fragt, fragt zuerst hier.
 */
export const SONSTIGES_ZAEHLER_KATEGORIEN: readonly string[] = ['zaehler']

/** Trägt diese Kategorie einen Zählerstand statt Strom? (#377) */
export function istZaehlerKategorie(kategorie: string | null | undefined): boolean {
  return !!kategorie && SONSTIGES_ZAEHLER_KATEGORIEN.includes(kategorie)
}

/**
 * Die Einheit, die neben diesem Wert stehen soll — **der eine Leser** (#377).
 *
 * Für fast jedes Feld steht sie in der Definition. Beim **Zählerstand** nicht:
 * Er ist einheitenlos gespeichert, und was daneben steht (m³, l, kg, t, kWh),
 * hängt am Gerät. Spiegel von `field_definitions.einheit_fuer`.
 *
 * ⚠ Anzeige, nie Rechnung — eedc rechnet Zählerstände grundsätzlich nicht um.
 */
export function einheitFuer(
  feld: FeldDefinition,
  parameter?: InvParameter | null
): string {
  if (feld.einheitJeGeraet) {
    const wert = (parameter ?? {})[feld.einheitJeGeraet]
    if (wert) return String(wert)
    return String(PARAM_SONSTIGES_DEFAULTS.zaehler_einheit)
  }
  return feld.einheit
}

/**
 * Alle Richtungen eines *Sonstiges*-Geräts, dedupliziert — **abgeleitet**.
 *
 * Spiegel von `field_definitions.SONSTIGES_FELDER_UNGEPFLEGT`. Verbraucher
 * zuerst: das ist die Richtung, als die jeder wertführende Pfad ein Gerät ohne
 * gepflegte Kategorie liest (`SONSTIGES_KATEGORIE_UNGEPFLEGT` im Backend).
 */
const SONSTIGES_FELDER_UNGEPFLEGT: FeldDefinition[] = (() => {
  const reihenfolge = [
    'verbraucher',
    // #377: Zähler-Kategorien bleiben draußen — ein Gerät ohne gepflegte
    // Kategorie wird als **Verbraucher** gelesen, und ein Zählerstand-Slot
    // neben den Strom-Feldern verleitet dazu, dort einen Gassensor
    // zuzuordnen. Das ist der N-244-Schaden mit anderem Vorzeichen.
    // Spiegel von `_sonstiges_felder_ungepflegt()` im Backend.
    ...Object.keys(SONSTIGES_FELDER).filter(k => k !== 'verbraucher' && !istZaehlerKategorie(k)),
  ]
  const gesehen = new Set<string>()
  const out: FeldDefinition[] = []
  for (const kat of reihenfolge) {
    for (const feld of SONSTIGES_FELDER[kat] ?? []) {
      if (gesehen.has(feld.feld)) continue
      gesehen.add(feld.feld)
      out.push(feld)
    }
  }
  return out
})()

/**
 * Gibt Felder für eine Sonstiges-Investition nach Kategorie zurück.
 *
 * **Ohne gepflegte Kategorie alle Richtungen, nicht eine geratene (N-244).**
 * Bis 17.08.2026 stand hier `?? SONSTIGES_FELDER.erzeuger` — ein Gerät ohne
 * Kategorie bekam also ausschließlich Erzeuger-Felder angeboten, während jeder
 * wertführende Pfad es als Verbraucher liest und `verbrauch_sonstig_kwh` ·
 * `bezug_pv_kwh` · `bezug_netz_kwh` erwartet. Die Schnittmenge beider Listen
 * ist **leer** — die Zuordnungsfläche bot damit nur Felder an, die für dieses
 * Gerät nirgends gesucht werden (die N-259-Klasse).
 */
export function getFelderFuerSonstiges(kategorie: string | null | undefined): FeldDefinition[] {
  if (kategorie && kategorie in SONSTIGES_FELDER) return SONSTIGES_FELDER[kategorie]
  return SONSTIGES_FELDER_UNGEPFLEGT
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
