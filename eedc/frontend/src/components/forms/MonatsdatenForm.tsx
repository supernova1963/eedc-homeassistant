/**
 * Dynamisches Monatsdatenformular
 * Zeigt Felder basierend auf den vorhandenen Investitionen der Anlage an.
 */

import { useState, useEffect, useMemo, useRef, useCallback, FormEvent } from 'react'
import { Button, Input, Alert, Select, Textarea, FormSection } from '../ui'
import { useInvestitionen, useAktuellerStrompreis } from '../../hooks'
import { investitionenApi, wetterApi, monatsabschlussApi } from '../../api'
import type { MonatsabschlussResponse, FeldStatus, BehalteneAbweichung } from '../../api/monatsabschluss'
import type { WetterDaten } from '../../api/wetter'
import type { Monatsdaten, Investition } from '../../types'
import { getFelderFuerInvestition, LEGACY_FELDNAMEN, readFeldWert, ABGELEITET_SUMME_ACHSEN, istAutoSummenFeld } from '../../lib/fieldDefinitions'
import { prefillWert, ermittleZustand, zaehleAmpel, behaltenEintrag, abgeleiteteMarke, type ErfassungZustand } from '../../lib/erfassungZustand'
import { istAktivImMonat } from '../../lib/investitionAktiv'
import { fmtZahl, SONSTIGES_KATEGORIE_LABELS } from '../../lib'
import { Plug, Sun, Flame, Cloud, Loader2, Battery, Car, Zap, MoreHorizontal } from 'lucide-react'
import { InvestitionSection } from './sections/InvestitionSection'
import { SonstigePositionenFields } from './SonstigePositionenFields'
import AssistenzFeld from './AssistenzFeld'
import KopfAmpel from './KopfAmpel'
import ZustandLegende from './ZustandLegende'
import AbschlussReview, { type ReviewWarnung } from './AbschlussReview'
import type { SonstigePosition } from './sections/types'
import { haBasisWert } from '../../lib/haVergleich'

interface MonatsdatenFormProps {
  monatsdaten?: Monatsdaten | null
  anlageId: number
  onSubmit: (data: MonatsdatenSubmitData) => Promise<void>
  onCancel: () => void
  /** Voreingestellter Monat beim Erfassen einer Tabellen-Lücke (§7, Bündel 4).
   *  Setzt nur die initiale Jahr/Monat-Wahl beim Neuanlegen — sonst frei wählbar. */
  voreingestellterMonat?: { jahr: number; monat: number } | null
  /** Vorausgefüllte Werte aus HA-Statistik */
  haVorausfuellung?: {
    jahr: number
    monat: number
    monat_name: string
    basis: Array<{ feld: string; wert: number | null; sensor_id?: string }>
    investitionen: Array<{
      investition_id: number
      bezeichnung: string
      typ: string
      felder: Array<{ feld: string; wert: number | null; sensor_id?: string }>
    }>
  } | null
}

export interface MonatsdatenSubmitData {
  anlage_id: number
  jahr: number
  monat: number
  einspeisung_kwh: number
  netzbezug_kwh: number
  /** `null` = gespeicherten Anlagenwert entfernen (N-622), fehlend = unverändert lassen. */
  pv_erzeugung_kwh?: number | null
  batterie_ladung_kwh?: number
  batterie_entladung_kwh?: number
  netzbezug_durchschnittspreis_cent?: number
  einspeise_durchschnittspreis_cent?: number
  kraftstoffpreis_euro?: number
  gaspreis_cent_kwh?: number
  globalstrahlung_kwh_m2?: number
  sonnenstunden?: number
  durchschnittstemperatur?: number
  // G19-1: Anlage-Ebene Sonstige Erträge & Ausgaben (ersetzt die Legacy-Felder
  // sonderkosten_euro/_beschreibung; [] = bewusst geleert)
  sonstige_positionen?: SonstigePosition[]
  notizen?: string
  // PN 90128: bewusst behaltene Sensor-Abweichungen der Basis-Felder
  // ({feld: {sensor, wert}}); `{}` nimmt frühere Bestätigungen zurück.
  geprueft_gegen?: Record<string, BehalteneAbweichung>
  // Investitions-spezifische Daten
  investitionen_daten?: Record<string, InvestitionMonatsdaten>
}

interface InvestitionMonatsdaten {
  // E-Auto
  km_gefahren?: number
  verbrauch_kwh?: number
  ladung_pv_kwh?: number
  ladung_netz_kwh?: number
  ladung_extern_kwh?: number       // Externe Ladung (Autobahn, Arbeit, etc.)
  ladung_extern_euro?: number      // Kosten externe Ladung
  entladung_v2h_kwh?: number
  // Speicher
  ladung_kwh?: number
  entladung_kwh?: number
  speicher_ladung_netz_kwh?: number // Arbitrage: Laden aus Netz
  speicher_ladepreis_cent?: number  // Arbitrage: Ø Ladepreis
  // Wallbox - nutzt E-Auto Heim-Ladung (ladung_pv_kwh + ladung_netz_kwh)
  ladevorgaenge?: number
  // Wärmepumpe
  stromverbrauch_kwh?: number
  strom_heizen_kwh?: number
  strom_warmwasser_kwh?: number
  heizenergie_kwh?: number
  warmwasser_kwh?: number
  // Wechselrichter / PV-Module
  pv_erzeugung_kwh?: number
  // Balkonkraftwerk / Sonstiges Erzeuger
  erzeugung_kwh?: number
  eigenverbrauch_kwh?: number
  einspeisung_kwh?: number
  // Balkonkraftwerk Speicher
  speicher_ladung_kwh?: number
  speicher_entladung_kwh?: number
  // Sonstiges (Verbraucher)
  verbrauch_sonstig_kwh?: number
  bezug_pv_kwh?: number
  bezug_netz_kwh?: number
  // Sonstige Positionen (für alle Investitionstypen)
  sonstige_positionen?: SonstigePosition[]
}

// SonstigePosition wird aus ./sections/types importiert

type PflichtFeld = 'einspeisung_kwh' | 'netzbezug_kwh'

const monatOptions = [
  { value: '1', label: 'Januar' },
  { value: '2', label: 'Februar' },
  { value: '3', label: 'März' },
  { value: '4', label: 'April' },
  { value: '5', label: 'Mai' },
  { value: '6', label: 'Juni' },
  { value: '7', label: 'Juli' },
  { value: '8', label: 'August' },
  { value: '9', label: 'September' },
  { value: '10', label: 'Oktober' },
  { value: '11', label: 'November' },
  { value: '12', label: 'Dezember' },
]

/** Schlüssel eines Investitionsfeldes in `bestaetigteFelder`. Rein aus den
 *  Argumenten gebildet — auf Modul-Ebene, damit die Funktion stabil ist und
 *  Hook-Deps nicht bei jedem Render neu anschlagen. */
const invKey = (invId: number, feld: string) => `${invId}:${feld}`

/** Sektions-Untertitel „x,x kWp" eines Balkonkraftwerks.
 *
 *  ANZEIGE, kein Eingabefeld ⇒ `leistung_kwp_effektiv` statt der Rohspalte
 *  (A26/N106): ein BKW, dessen Leistung als `leistung_wp × anzahl` im
 *  `parameter`-JSON steht, hatte hier bisher gar keinen Untertitel.
 *  Zahl über die `fmtZahl`-SoT (de-DE) statt roher Interpolation. */
const bkwLeistung = (inv: Investition) =>
  inv.leistung_kwp_effektiv != null ? `${fmtZahl(inv.leistung_kwp_effektiv, 1)} kWp` : null

/**
 * Die drei Felder des Wetter-Auto-Fills — EINE Liste, EINE Regel (**N-426**).
 *
 * Sie steht hier, damit die Regel „nur in eine Lücke" nicht dreimal als `if`
 * im Handler klebt: Genau so ist der Bestand auseinandergelaufen — zwei Felder
 * überschrieben bedingungslos, das dritte wurde gar nicht erst gesetzt, und
 * der Feld-Hinweis der Globalstrahlung versprach schon damals das Gegenteil
 * („…, wenn nicht manuell gepflegt"). Ein viertes Wetterfeld hängt sich hier
 * ein und erbt die Regel, statt sie neu zu erfinden.
 *
 * `label` ist der Text, unter dem der Anwender das Feld im Formular sieht —
 * er wird im Hinweis unter dem Knopf wiederverwendet.
 */
const WETTER_AUTOFILL_FELDER: ReadonlyArray<{
  feld: 'globalstrahlung_kwh_m2' | 'sonnenstunden' | 'durchschnittstemperatur'
  label: string
  ausAntwort: (d: WetterDaten) => number | null | undefined
}> = [
  { feld: 'globalstrahlung_kwh_m2', label: 'Globalstrahlung', ausAntwort: d => d.globalstrahlung_kwh_m2 },
  { feld: 'sonnenstunden', label: 'Sonnenstunden', ausAntwort: d => d.sonnenstunden },
  { feld: 'durchschnittstemperatur', label: 'Ø Temperatur', ausAntwort: d => d.durchschnittstemperatur_c },
]

/** „A", „A und B", „A, B und C" — deutsche Aufzählung für den Hinweistext. */
const aufzaehlung = (teile: string[]): string =>
  teile.length <= 1
    ? (teile[0] ?? '')
    : `${teile.slice(0, -1).join(', ')} und ${teile[teile.length - 1]}`

export default function MonatsdatenForm({ monatsdaten, anlageId, onSubmit, onCancel, haVorausfuellung, voreingestellterMonat }: MonatsdatenFormProps) {
  const currentYear = new Date().getFullYear()
  const currentMonth = new Date().getMonth() + 1

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // V1/V2: Inline-Fehler erst nach Berührung bzw. Absende-Versuch (Muster Slice 1/2).
  const [touched, setTouched] = useState<Set<string>>(new Set())
  const [submitted, setSubmitted] = useState(false)
  const feldRefs = useRef<Record<PflichtFeld, HTMLDivElement | null>>({
    einspeisung_kwh: null,
    netzbezug_kwh: null,
  })
  const markTouched = (name: string) => setTouched(prev => new Set(prev).add(name))
  const feldFehler = (name: PflichtFeld): string | undefined => {
    const roh = formData[name]
    if (roh === '') return 'Pflichtfeld'
    const n = parseFloat(roh)
    if (Number.isNaN(n)) return 'Bitte eine Zahl eingeben'
    if (n < 0) return 'Darf nicht negativ sein'
    return undefined
  }
  const zeigeFehler = (name: PflichtFeld): string | undefined =>
    (submitted || touched.has(name)) ? feldFehler(name) : undefined

  // Investitionen für diese Anlage laden.
  const { investitionen, loading: invLoading } = useInvestitionen(anlageId)

  // Strompreis für dynamischen Tarif prüfen
  const { strompreis } = useAktuellerStrompreis(anlageId)
  const hatDynamischenTarif = strompreis?.vertragsart === 'dynamisch'
  // #392: variable Einspeisevergütung — Monatssatz-Feld einblenden
  const hatVariableEinspeisung = strompreis?.einspeisung_variabel === true

  // Hilfsfunktion um HA-Basiswert zu finden — N-534: das Backend liefert die
  // DB-Feldnamen (`einspeisung_kwh`); mit den Mapping-Kurzformen blieb die
  // Vorbelegung seit v2.5.3 leer.
  const getHaBasisWert = (feld: string): string => haBasisWert(haVorausfuellung?.basis, feld)
  // N-622: hat „Aus HA laden" den PV-Gesamtzähler geliefert, bekommt er eine eigene
  // Zeile — auch wenn Module/Wechselrichter Werte haben und das Feld sonst nur als
  // „PV-Erzeugung (berechnet)" erschiene. Der Anwender bestätigt den Wert mit dem
  // Speichern (ADR-002/P7: nie unsichtbar gefüllt); eine leere Zeile speichert nichts.
  const haPvGesamt = getHaBasisWert('pv_erzeugung_kwh') !== ''
  // N-622 Nacharbeit: ein GESPEICHERTER Anlagenwert wirkt (er füllt die Lücken der
  // Quellen ohne eigenen Wert) — dann muss er auch sichtbar und änderbar sein, nicht
  // nur unsichtbar mitgesendet werden. Dieselbe Zeile, neutral beschriftet.
  const gespeicherterPvGesamt = monatsdaten?.pv_erzeugung_kwh != null
  const zeigePvGesamtZeile = haPvGesamt || gespeicherterPvGesamt

  // Basis-Formulardaten
  const [formData, setFormData] = useState({
    jahr: haVorausfuellung?.jahr?.toString() || monatsdaten?.jahr?.toString() || voreingestellterMonat?.jahr?.toString() || currentYear.toString(),
    monat: haVorausfuellung?.monat?.toString() || monatsdaten?.monat?.toString() || voreingestellterMonat?.monat?.toString() || currentMonth.toString(),
    einspeisung_kwh: getHaBasisWert('einspeisung_kwh') || monatsdaten?.einspeisung_kwh?.toString() || '',
    netzbezug_kwh: getHaBasisWert('netzbezug_kwh') || monatsdaten?.netzbezug_kwh?.toString() || '',
    // N-534/N-622: der Anlagen-PV-Zähler aus HA ist das importierte Anlagen-Aggregat (ADR-002/P7).
    // Er steht dann immer in einer eigenen, sichtbaren Zeile (`haPvGesamt` unten).
    pv_erzeugung_kwh: getHaBasisWert('pv_erzeugung_kwh') || monatsdaten?.pv_erzeugung_kwh?.toString() || '',
    batterie_ladung_kwh: monatsdaten?.batterie_ladung_kwh?.toString() || '',
    batterie_entladung_kwh: monatsdaten?.batterie_entladung_kwh?.toString() || '',
    globalstrahlung_kwh_m2: monatsdaten?.globalstrahlung_kwh_m2?.toString() || '',
    sonnenstunden: monatsdaten?.sonnenstunden?.toString() || '',
    durchschnittstemperatur: monatsdaten?.durchschnittstemperatur?.toString() || '',
    netzbezug_durchschnittspreis_cent: monatsdaten?.netzbezug_durchschnittspreis_cent?.toString() || '',
    einspeise_durchschnittspreis_cent: monatsdaten?.einspeise_durchschnittspreis_cent?.toString() || '',
    kraftstoffpreis_euro: monatsdaten?.kraftstoffpreis_euro?.toString() || '',
    gaspreis_cent_kwh: monatsdaten?.gaspreis_cent_kwh?.toString() || '',
    notizen: monatsdaten?.notizen || '',
  })

  // G19-1: Basis-Positionen (Anlage-Ebene) — DERSELBE Baustein wie je
  // Investition. Legacy-Fallback fürs Bearbeiten von Alt-Daten, die die
  // Start-Migration noch nicht gesehen hat (gleiche Regel wie IMD unten).
  const [basisPositionen, setBasisPositionen] = useState<SonstigePosition[]>(() => {
    if (monatsdaten?.sonstige_positionen) return monatsdaten.sonstige_positionen
    if (monatsdaten?.sonderkosten_euro && monatsdaten.sonderkosten_euro > 0) {
      return [{
        bezeichnung: monatsdaten.sonderkosten_beschreibung || 'Sonderkosten (migriert)',
        betrag: monatsdaten.sonderkosten_euro,
        typ: 'ausgabe' as const,
      }]
    }
    return []
  })
  // Löschsignal-Spur wie bei den IMD-Positionen (#286): hatte der Monat beim
  // Laden Positionen, muss beim Leeren eine leere Liste ans Backend.
  const [initialHatteBasisPositionen] = useState(() => (
    (monatsdaten?.sonstige_positionen?.length ?? 0) > 0
    || !!(monatsdaten?.sonderkosten_euro && monatsdaten.sonderkosten_euro > 0)
  ))

  // Nur die im GEWÄHLTEN Monat betriebenen Geräte (Anschaffungs-/Stilllegungs-
  // Fenster, Backend-SoT `ist_aktiv_im_monat`) — steuert Anzeige UND Prüfungen.
  // Das aktiv-Flag allein reicht nicht ([[feedback_anschaffungsdatum_grenze]],
  // [[feedback_aktiv_inaktiv_semantik]]). Reagiert live auf die Zeitraum-Auswahl.
  const aktiveInvestitionen = useMemo(
    () => investitionen.filter(i => istAktivImMonat(i, parseInt(formData.jahr), parseInt(formData.monat))),
    [investitionen, formData.jahr, formData.monat],
  )

  // Welche Investitionstypen sind im gewählten Monat vorhanden?
  const hatSpeicher = aktiveInvestitionen.some(i => i.typ === 'speicher')
  const hatEAuto = aktiveInvestitionen.some(i => i.typ === 'e-auto')
  const hatWallbox = aktiveInvestitionen.some(i => i.typ === 'wallbox')
  const hatWaermepumpe = aktiveInvestitionen.some(i => i.typ === 'waermepumpe')
  const hatWechselrichter = aktiveInvestitionen.some(i => i.typ === 'wechselrichter')
  const hatPVModule = aktiveInvestitionen.some(i => i.typ === 'pv-module')
  const hatBalkonkraftwerk = aktiveInvestitionen.some(i => i.typ === 'balkonkraftwerk')
  const hatSonstiges = aktiveInvestitionen.some(i => i.typ === 'sonstiges')

  // Wetter-Daten Auto-Fill
  const [wetterLoading, setWetterLoading] = useState(false)
  const [wetterInfo, setWetterInfo] = useState<string | null>(null)

  // Investitions-spezifische Daten
  const [investitionsDaten, setInvestitionsDaten] = useState<Record<string, Record<string, string>>>({})
  // Sonstige Positionen (Erträge & Ausgaben) pro Investition
  const [sonstigePositionen, setSonstigePositionen] = useState<Record<string, SonstigePosition[]>>({})
  // Beim Laden gespeicherte Positionen — wenn der User alles löscht und
  // `sonstigePositionen[invId]` damit leer ist, müssen wir trotzdem `[]`
  // ans Backend senden (Löschsignal). Ohne diese Spur würde der Sub-Key
  // ausgelassen und die alte Liste bliebe in der DB stehen (#286 rcmcronny).
  const [initialHattePositionen, setInitialHattePositionen] = useState<Record<string, boolean>>({})
  const [loadingInvData, setLoadingInvData] = useState(false)
  // N-578 B2b: je Gerät die beim Laden BELEGTEN Felder — gespeicherter Wert,
  // der nicht die eigene Auto-Summe ist (`summe_achsen`). Entscheidet über die
  // weichen Felder der Registry (Spiegel von `belegte_felder` im Backend). Fest
  // ab dem Laden: ein Feld, das der Anwender leert, bleibt bis zum Speichern
  // stehen (sonst verschwände es unter dem Cursor).
  const [belegtBeimLaden, setBelegtBeimLaden] = useState<Record<string, Set<string>>>({})

  // Initialisiere Investitions-Daten und lade vorhandene Daten beim Bearbeiten
  useEffect(() => {
    if (aktiveInvestitionen.length === 0) return

    const initializeAndLoad = async () => {
      const initial: Record<string, Record<string, string>> = {}
      // N-578 B2b: belegte Felder je Gerät (s. `belegtBeimLaden`).
      const belegt: Record<string, Set<string>> = {}
      // Generische Initialisierung aus field_definitions (E3) — mit den belegten
      // Feldern, damit ein weiches Feld mit gepflegtem Wert seinen Schlüssel hat.
      const initialisiere = () => aktiveInvestitionen.forEach(inv => {
        const felder = getFelderFuerInvestition(inv.typ, inv.parameter, belegt[String(inv.id)])
        const init: Record<string, string> = {}
        felder.forEach(f => { init[f.feld] = '' })
        initial[inv.id] = init
      })

      // Sonstige Positionen aus existierenden Daten laden
      const loadedPositionen: Record<string, SonstigePosition[]> = {}

      // Beim Bearbeiten: Lade vorhandene InvestitionMonatsdaten
      if (monatsdaten?.jahr && monatsdaten?.monat) {
        setLoadingInvData(true)
        try {
          const existingData = await investitionenApi.getMonatsdatenByMonth(
            anlageId,
            monatsdaten.jahr,
            monatsdaten.monat
          )

          // N-578 B2a/B2b: ein `summe_achsen`-markierter Wert ist die eigene
          // Auto-Summe des Formulars — keine Handpflege. Er macht sein Feld nicht
          // „belegt"; das weiche Feld bekommt dann keinen Schlüssel, und der Wert
          // wird nicht geladen (sonst hielte `hasValue` die Summe beim Speichern
          // an, und der Wert fröre ein). Ohne getrennte Messung ist das Feld hart
          // sichtbar — dort wird auch ein markierter Wert normal geladen, denn er
          // ist dann die Menge, mit der eedc rechnet.
          const istAutoSumme = (imd: { abgeleitet_felder?: Record<string, string> }, key: string) =>
            imd.abgeleitet_felder?.[key] === ABGELEITET_SUMME_ACHSEN
          existingData.forEach(imd => {
            const b = new Set<string>()
            Object.entries(imd.verbrauch_daten ?? {}).forEach(([key, value]) => {
              if (value !== null && value !== undefined && !istAutoSumme(imd, key)) b.add(key)
            })
            belegt[String(imd.investition_id)] = b
          })
          initialisiere()

          // Merge vorhandene Daten in initial
          existingData.forEach(imd => {
            // investition_id kann als Zahl oder String kommen, initial verwendet String-Keys
            const invIdStr = String(imd.investition_id)

            // Sonstige Positionen extrahieren (neues Format oder Legacy-Migration)
            const vd = imd.verbrauch_daten as Record<string, unknown> | undefined
            if (vd?.sonstige_positionen) {
              loadedPositionen[invIdStr] = vd.sonstige_positionen as SonstigePosition[]
            } else if (vd?.sonderkosten_euro && Number(vd.sonderkosten_euro) > 0) {
              loadedPositionen[invIdStr] = [{
                bezeichnung: String(vd.sonderkosten_notiz || 'Sonderkosten (migriert)'),
                betrag: Number(vd.sonderkosten_euro),
                typ: 'ausgabe' as const,
              }]
            }

            if (initial[invIdStr] && imd.verbrauch_daten) {
              // Generisches Laden: kanonische + Legacy-Feldnamen (E3)
              const skipKeys = new Set(['sonstige_positionen', 'sonderkosten_euro', 'sonderkosten_notiz'])
              Object.entries(imd.verbrauch_daten).forEach(([key, value]) => {
                if (skipKeys.has(key)) return
                const val = value?.toString() || ''
                // Direkter Match mit kanonischem Namen
                if (initial[invIdStr][key] !== undefined) {
                  initial[invIdStr][key] = val
                  return
                }
                // Legacy-Key → kanonischer Name (z.B. entladung_v2h_kwh → v2h_entladung_kwh)
                const canonical = LEGACY_FELDNAMEN[key]
                if (canonical && initial[invIdStr][canonical] !== undefined) {
                  initial[invIdStr][canonical] = val
                  return
                }
                // Typ-spezifische Legacy-Fallbacks (vor Einführung kanonischer Namen)
                if (key === 'erzeugung_kwh' && initial[invIdStr]['pv_erzeugung_kwh'] !== undefined) {
                  initial[invIdStr]['pv_erzeugung_kwh'] = val  // BKW: alt erzeugung_kwh → pv_erzeugung_kwh
                }
                if (key === 'verbrauch_kwh' && initial[invIdStr]['verbrauch_sonstig_kwh'] !== undefined) {
                  initial[invIdStr]['verbrauch_sonstig_kwh'] = val  // Sonstiges: alt verbrauch_kwh → verbrauch_sonstig_kwh
                }
              })
            }
          })

          // =================================================================
          // Auto-Migration: Legacy Monatsdaten.batterie_* → InvestitionMonatsdaten
          // Wenn Speicher-Investitionen existieren, aber keine InvestitionMonatsdaten
          // für sie vorhanden sind UND Legacy-Daten in Monatsdaten existieren,
          // dann übernehme die Legacy-Daten in die Speicher-Investitionsfelder.
          // =================================================================
          const speicherInvs = aktiveInvestitionen.filter(i => i.typ === 'speicher')
          const speicherMdIds = new Set(existingData.filter(imd =>
            speicherInvs.some(s => s.id === imd.investition_id)
          ).map(imd => imd.investition_id))

          // Prüfe ob Legacy-Daten existieren
          const legacyLadung = monatsdaten?.batterie_ladung_kwh || 0
          const legacyEntladung = monatsdaten?.batterie_entladung_kwh || 0

          if (speicherInvs.length > 0 && (legacyLadung > 0 || legacyEntladung > 0)) {
            // Finde Speicher ohne InvestitionMonatsdaten
            const speicherOhneDaten = speicherInvs.filter(s => !speicherMdIds.has(s.id))

            if (speicherOhneDaten.length > 0) {
              // Verteile Legacy-Daten auf Speicher ohne Daten
              // Bei mehreren Speichern: gleichmäßig verteilen (vereinfachte Annahme)
              const anteil = 1 / speicherOhneDaten.length
              speicherOhneDaten.forEach(speicher => {
                const invIdStr = String(speicher.id)
                if (initial[invIdStr]) {
                  initial[invIdStr].ladung_kwh = (legacyLadung * anteil).toFixed(1) /* de-de-allow: Input-Value (editierbares number-Feld, wird per parseFloat gelesen) */
                  initial[invIdStr].entladung_kwh = (legacyEntladung * anteil).toFixed(1) /* de-de-allow: Input-Value (editierbares number-Feld, wird per parseFloat gelesen) */
                }
              })
            }
          }
        } catch (e) {
          // Fehler stillschweigend ignoriert
        } finally {
          setLoadingInvData(false)
        }
      }
      // Neuer Monat oder Ladefehler: nichts belegt, harte Registry.
      if (Object.keys(initial).length === 0) initialisiere()

      // =================================================================
      // HA-Vorausfüllung: Werte aus HA-Statistik einfügen
      // =================================================================
      // HA-Vorausfüllung: generisch per Feld-Key (E3)
      if (haVorausfuellung?.investitionen) {
        haVorausfuellung.investitionen.forEach(haInv => {
          const invIdStr = String(haInv.investition_id)
          if (!initial[invIdStr]) return
          haInv.felder.forEach(({ feld, wert }) => {
            if (wert !== null && wert !== undefined && initial[invIdStr][feld] !== undefined) {
              initial[invIdStr][feld] = wert.toString()
            }
          })
        })
      }

      setInvestitionsDaten(initial)
      setBelegtBeimLaden(belegt)
      if (Object.keys(loadedPositionen).length > 0) {
        setSonstigePositionen(loadedPositionen)
      }
      // Spur, welche Investitionen beim Laden bereits Positionen hatten —
      // entscheidet beim Save, ob ein leeres Array als Löschsignal raus muss
      // (siehe Submit-Logik: `hattePositionen || gueltigePositionen.length > 0`).
      const hattePos: Record<string, boolean> = {}
      Object.entries(loadedPositionen).forEach(([invId, positions]) => {
        if (positions && positions.length > 0) hattePos[invId] = true
      })
      setInitialHattePositionen(hattePos)
    }

    initializeAndLoad()
    // Bewusst OHNE `monatsdaten?.batterie_ladung_kwh`/`batterie_entladung_kwh`:
    // Trigger dieses Effekts ist die IDENTITÄT des Datensatzes (jahr/monat/anlage),
    // nicht sein Inhalt. Die beiden Legacy-Werte werden beim Initialisieren nur als
    // Startwert gelesen (einmalige Verteilung auf Speicher ohne InvestitionMonats-
    // daten, siehe oben). Als Dep würden sie den Effekt bei jedem Neuladen des
    // Datensatzes erneut feuern und dabei ungespeicherte Eingaben in
    // `investitionsDaten` überschreiben.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aktiveInvestitionen, monatsdaten?.jahr, monatsdaten?.monat, anlageId, haVorausfuellung])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleInvChange = (invId: number, field: string, value: string) => {
    setInvestitionsDaten(prev => ({
      ...prev,
      [invId]: {
        ...prev[invId],
        [field]: value,
      },
    }))
  }

  const handlePositionenChange = (invId: number, positionen: SonstigePosition[]) => {
    setSonstigePositionen(prev => ({ ...prev, [String(invId)]: positionen }))
  }

  // Berechne Summen aus den einzelnen Investitionen
  const berechneteWerte = useMemo(() => {
    let batterieLadung = 0
    let batterieEntladung = 0
    let pvErzeugung = 0

    aktiveInvestitionen.forEach(inv => {
      const daten = investitionsDaten[inv.id]
      if (!daten) return

      if (inv.typ === 'speicher') {
        batterieLadung += parseFloat(daten.ladung_kwh) || 0
        batterieEntladung += parseFloat(daten.entladung_kwh) || 0
      } else if (inv.typ === 'pv-module' || inv.typ === 'wechselrichter' || inv.typ === 'balkonkraftwerk') {
        // PV-Erzeugung aus allen Quellen summieren
        pvErzeugung += parseFloat(daten.pv_erzeugung_kwh) || 0
        // Balkonkraftwerk mit Speicher
        if (inv.typ === 'balkonkraftwerk' && inv.parameter?.hat_speicher) {
          batterieLadung += parseFloat(daten.speicher_ladung_kwh) || 0
          batterieEntladung += parseFloat(daten.speicher_entladung_kwh) || 0
        }
      } else if (inv.typ === 'sonstiges' && inv.parameter?.kategorie === 'erzeuger') {
        // Sonstige Erzeuger zur PV-Erzeugung addieren
        pvErzeugung += parseFloat(daten.erzeugung_kwh) || 0
      }
    })

    return { batterieLadung, batterieEntladung, pvErzeugung }
  }, [aktiveInvestitionen, investitionsDaten])

  // ─── Erfassungs-Assistenz (Monatsabschluss-V4 §4) ──────────────────────────
  // Die Form hängt an DEMSELBEN Backend-Status wie der Wizard (V-a): Felder,
  // Vorschläge, Quelle und Warnungen kommen aus einer Quelle
  // (GET /monatsabschluss/{id}/{jahr}/{monat}). Client-Aggregate (PV-berechnet,
  // Batterie-manuell) bleiben unberührt — die kennt der Status nicht.
  const [status, setStatus] = useState<MonatsabschlussResponse | null>(null)
  // Vom Nutzer per „✓ passt" bestätigte Felder (§6.6): geschätzt/weicht-ab → geprüft.
  // Basis-Felder unter ihrem Namen, Investitionsfelder unter `${invId}:${feld}`.
  const [bestaetigteFelder, setBestaetigteFelder] = useState<Set<string>>(new Set())
  const bestaetigeFeld = (name: string) => setBestaetigteFelder(prev => new Set(prev).add(name))
  const istInvBestaetigt = useCallback(
    (invId: number, feld: string) => bestaetigteFelder.has(invKey(invId, feld)),
    [bestaetigteFelder],
  )
  const bestaetigeInvFelder = (invId: number, felder: string[]) =>
    setBestaetigteFelder(prev => {
      const n = new Set(prev)
      felder.forEach(f => n.add(invKey(invId, f)))
      return n
    })

  useEffect(() => {
    const j = parseInt(formData.jahr)
    const m = parseInt(formData.monat)
    if (!anlageId || !j || !m) return
    let abgebrochen = false
    monatsabschlussApi.getStatus(anlageId, j, m)
      .then(res => { if (!abgebrochen) setStatus(res) })
      .catch(() => { if (!abgebrochen) setStatus(null) })
    return () => { abgebrochen = true }
  }, [anlageId, formData.jahr, formData.monat])

  // Lookups Feld → FeldStatus (Basis/Optionale) bzw. invId → feld → FeldStatus
  const basisStatus = useMemo(() => {
    const map: Record<string, FeldStatus> = {}
    if (status) {
      for (const f of status.basis_felder) map[f.feld] = f
      for (const f of status.optionale_felder) map[f.feld] = f
    }
    return map
  }, [status])

  const invStatus = useMemo(() => {
    const map: Record<number, Record<string, FeldStatus>> = {}
    if (status) for (const inv of status.investitionen) {
      map[inv.id] = {}
      const parameter = investitionen.find(i => i.id === inv.id)?.parameter
      for (const f of inv.felder) {
        // N-578 (Master-Entscheid H2): Am Feld, das das Formular selbst als
        // Summe rechnet, ist der Summen-Vorschlag `berechnung` (Heizen +
        // Warmwasser der GESPEICHERTEN Achsen, `vorschlag_service.py`) redundant.
        // Vorbelegt oder per „übernehmen" in das Feld geholt, stünde er als
        // unmarkierte Handpflege da und fröre beim nächsten Achsen-Update wieder
        // ein. Er wird deshalb hier — an der einen Stelle, aus der Vorbelegung,
        // Assistenz und Marken-Abgleich lesen — nicht angeboten. Messwert-
        // Vorschläge (HA-Sensor, MQTT, …) bleiben.
        map[inv.id][f.feld] = istAutoSummenFeld(inv.typ, f.feld, parameter)
          ? { ...f, vorschlaege: f.vorschlaege.filter(v => v.quelle !== 'berechnung') }
          : f
      }
    }
    return map
  }, [status, investitionen])

  // N-578 B2b/H2: Felder mit zugeordnetem SENSOR je Gerät — aus dem Status
  // (`FeldStatus.strategie`). Der Status ist die eine Stelle, die die Zuordnung
  // des Geräts für diesen Monat auflöst; die Laderoute liefert nur gespeicherte
  // Zeilen (ein neuer Monat hat keine) und kennt die Zuordnung nicht.
  // ⚠ `strategie === 'sensor'`, nicht „Schlüssel vorhanden": eine geräumte
  // Zuordnung bleibt als `{"strategie": "keine"}` stehen
  // (`datenquellen_mapping_sync.py`) und liefert keinen Wert.
  const sensorFelder = useCallback((invId: number): Set<string> => new Set(
    Object.values(invStatus[invId] ?? {}).filter(f => f.strategie === 'sensor').map(f => f.feld),
  ), [invStatus])

  // Belegt im Sinn der weichen Registry-Bedingung — Spiegel von `belegte_felder`
  // (`monatsabschluss/views.py`: Wert ODER Zuordnung), mit zwei Präzisierungen:
  // die eigene Auto-Summe zählt nicht als Wert, und zugeordnet heißt Sensor.
  const belegteFuer = useCallback((inv: Investition): Set<string> => new Set([
    ...(belegtBeimLaden[String(inv.id)] ?? []),
    ...sensorFelder(inv.id),
  ]), [belegtBeimLaden, sensorFelder])

  // Wechselt beim Statusladen → Ampel-Blöcke remounten mit korrektem Einklapp-Default.
  const statusMonthKey = status ? `${status.jahr}-${status.monat}` : 'nostatus'

  // D1-Fix (Gernot 2026-07-12): der Backend-Status hat `bedingung_anlage` bereits
  // aufgelöst (z. B. E-Auto „Heim: PV/Netz" fehlt, wenn eine Wallbox existiert).
  // Ist der Status geladen, ist SEINE Feldmenge maßgeblich; sonst Fallback auf die
  // clientseitige Registry.
  const felderFuer = useCallback((inv: Investition) => {
    const alle = getFelderFuerInvestition(inv.typ, inv.parameter, belegteFuer(inv))
    const erlaubt = invStatus[inv.id]
    if (!erlaubt || Object.keys(erlaubt).length === 0) return alle
    return alle.filter(f => f.feld in erlaubt)
  }, [invStatus, belegteFuer])

  // Kopf-Ampel (§6.2) + Review (§6.6): Zustände über den Pflicht-Kern (Zähler +
  // Investitionsfelder; Wetter/Preise/Sonderkosten zählen nicht als „offen") und
  // die vom Status gelieferten Plausibilitäts-Warnungen.
  const { ampel, reviewWarnungen, behaltenBasis, behaltenInv } = useMemo(() => {
    const zustaende: ErfassungZustand[] = []
    const warnungen: ReviewWarnung[] = []
    // PN 90128: derselbe Durchlauf sammelt die bewusst behaltenen Abweichungen
    // für den Speichern-Payload. Weil er bei jeder Änderung neu läuft, fallen
    // überholte Bestätigungen von selbst heraus (kein Aufräum-Pfad nötig).
    const behaltenBasis: Record<string, BehalteneAbweichung> = {}
    const behaltenInv: Record<number, Record<string, BehalteneAbweichung>> = {}
    if (status) {
      // Alle Basis-Felder zählen mit ihrem Zustand; leere quellenlose Felder werden
      // 'optional' und von zaehleAmpel ignoriert (§6.2) → Feld-Badge ≡ Kopf-Ampel.
      for (const f of status.basis_felder) {
        const wert = (formData as Record<string, string>)[f.feld] ?? ''
        const erg = ermittleZustand(wert, f, bestaetigteFelder.has(f.feld))
        zustaende.push(erg.zustand)
        const behalten = behaltenEintrag(erg)
        if (behalten) behaltenBasis[f.feld] = behalten
        for (const w of f.warnungen) {
          warnungen.push({ feld: f.feld, feldLabel: f.label, meldung: w.meldung, schwere: w.schwere, basis: true })
        }
      }
      for (const inv of aktiveInvestitionen) {
        const daten = investitionsDaten[inv.id] ?? {}
        behaltenInv[inv.id] = {}
        for (const f of felderFuer(inv)) {
          const fs = invStatus[inv.id]?.[f.feld]
          const erg = ermittleZustand(readFeldWert(daten, f.feld), fs, istInvBestaetigt(inv.id, f.feld))
          zustaende.push(erg.zustand)
          const behalten = behaltenEintrag(erg)
          if (behalten) behaltenInv[inv.id][f.feld] = behalten
          if (fs) for (const w of fs.warnungen) {
            warnungen.push({ feld: f.feld, feldLabel: `${inv.bezeichnung} · ${f.label}`, meldung: w.meldung, schwere: w.schwere, basis: false })
          }
        }
      }
    }
    return { ampel: zaehleAmpel(zustaende), reviewWarnungen: warnungen, behaltenBasis, behaltenInv }
  }, [status, formData, investitionsDaten, aktiveInvestitionen, invStatus, bestaetigteFelder, felderFuer, istInvBestaetigt])

  const springeZuFeld = (feld: string) => {
    document.querySelector(`[data-feld="${feld}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  const springeZuOffen = () => {
    document.querySelector('[data-erfassung-offen]')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  // Prefill R1/R2/R3: sobald Status geladen UND die Investitionsdaten initialisiert
  // sind, NUR LEERE Felder mit dem besten Vorschlag füllen (Lücken füllen). Bereits
  // befüllte (gespeicherte/manuelle) Werte bleiben unangetastet → kein stiller
  // Overwrite (P4/P3b). Einmal je Monat.
  const prefillRef = useRef<string>('')
  useEffect(() => {
    if (!status) return
    const invReady =
      aktiveInvestitionen.length === 0 ||
      aktiveInvestitionen.every(i => investitionsDaten[i.id])
    if (!invReady) return
    const key = `${status.jahr}-${status.monat}`
    if (prefillRef.current === key) return
    prefillRef.current = key

    setFormData(prev => {
      const next = { ...prev } as Record<string, string>
      for (const f of [...status.basis_felder, ...status.optionale_felder]) {
        if (f.typ === 'text') continue
        if (f.feld in next && (next[f.feld] ?? '') === '') {
          const w = prefillWert(f)
          if (w != null) next[f.feld] = String(w)
        }
      }
      return next as typeof prev
    })

    setInvestitionsDaten(prev => {
      const next = { ...prev }
      for (const inv of status.investitionen) {
        const cur = next[inv.id]
        if (!cur) continue
        // N-578 B1: vorbelegt wird nur, was das Formular für DIESES Gerät
        // zeichnet (`felderFuer` — dieselbe Liste wie die Sektion darunter).
        // Der Status führt auch Felder, die der Client ausblendet (weiche
        // Backend-Bedingung, cf3b0a16). Ein Vorschlag landete dann in einem
        // unsichtbaren Schlüssel: nie gesendet, aber „belegt" — die WP-Auto-
        // Summe beim Speichern fragt genau diesen Schlüssel und fiel aus, der
        // Gesamtstrom fror auf dem Stand des ersten Speicherns ein (#416).
        // Ein Vorschlag zu einem nicht gezeichneten Feld wird verworfen.
        const geraet = aktiveInvestitionen.find(i => i.id === inv.id)
        const gezeichnet = new Set((geraet ? felderFuer(geraet) : []).map(f => f.feld))
        const nc = { ...cur }
        // Die Feldstände aus `invStatus` — dort ist der Summen-Vorschlag am
        // Auto-Summen-Feld schon herausgenommen (N-578, s. oben).
        for (const f of Object.values(invStatus[inv.id] ?? {})) {
          if (!gezeichnet.has(f.feld)) continue
          if ((nc[f.feld] ?? '') === '') {
            const w = prefillWert(f)
            if (w != null) nc[f.feld] = String(w)
          }
        }
        next[inv.id] = nc
      }
      return next
    })
  }, [status, investitionsDaten, aktiveInvestitionen, felderFuer, invStatus])

  // Wetterdaten automatisch abrufen
  const fetchWetterdaten = async () => {
    if (!formData.jahr || !formData.monat) {
      setError('Bitte zuerst Jahr und Monat auswählen')
      return
    }

    setWetterLoading(true)
    setWetterInfo(null)
    setError(null)

    try {
      const data = await wetterApi.getMonatsdaten(
        anlageId,
        parseInt(formData.jahr),
        parseInt(formData.monat)
      )

      // ── Alle drei Wetterfelder füllen nur LÜCKEN (N-426) ────────────────
      //
      // EIN Weg für die drei, kein dreifach kopiertes `if`: Bis v4.0.44
      // überschrieben Globalstrahlung und Sonnenstunden auch einen getippten
      // Wert, die Ø Temperatur wurde gar nicht gesetzt — drei Felder, drei
      // Verhalten. Maßgeblich ist jetzt für alle die Hausregel des Formulars:
      // ein selbst eingetragener Wert ist die vertrauenswürdigste Quelle und
      // wird nicht automatisch überschrieben (P3b, `lib/erfassungZustand.ts`;
      // derselbe Satz steht am Prefill weiter oben).
      //
      // ⭐ Der Feld-Hinweis der Globalstrahlung versprach das ohnehin schon
      // („…, wenn nicht manuell gepflegt") — die Regel macht ihn wahr, statt
      // ihn umschreiben zu müssen. Wer einen Wert ersetzen will, leert das
      // Feld und klickt erneut; ein zweiter Knopfzustand wäre eine Bedienung
      // mehr für einen Fall, den das leere Feld schon löst.
      const ergebnis = WETTER_AUTOFILL_FELDER.map(({ feld, label, ausAntwort }) => {
        const gepflegt = ((formData as Record<string, string>)[feld] ?? '').trim() !== ''
        const wert = ausAntwort(data)
        return { feld, label, gepflegt, wert, uebernommen: !gepflegt && wert != null }
      })

      setFormData(prev => {
        const next = { ...prev } as Record<string, string>
        for (const e of ergebnis) {
          if (e.uebernommen) next[e.feld] = String(e.wert)
        }
        return next as typeof prev
      })

      // Info-Text über die Datenquelle der Strahlung.
      const quellenText = data.datenquelle === 'open-meteo'
        ? `Historische Daten von Open-Meteo${data.abdeckung_prozent ? ` (${data.abdeckung_prozent} % Abdeckung)` : ''}`
        : data.datenquelle === 'brightsky'
        // Der DWD misst — er schätzt nicht. Ohne diesen Zweig fiel Bright Sky
        // in den Sonst-Fall und wurde als „Geschätzte Durchschnittswerte"
        // ausgegeben, und zwar für die MEHRHEIT: an einer deutschen Anlage ist
        // Bright Sky die Voreinstellung, nicht die Ausnahme.
        ? `Messwerte des DWD (Bright Sky)${data.abdeckung_prozent ? ` (${data.abdeckung_prozent} % Abdeckung)` : ''}`
        : data.datenquelle === 'pvgis-tmy'
        ? 'Durchschnittswerte von PVGIS (TMY)'
        : 'Geschätzte Durchschnittswerte'

      // Was der Klick getan hat — je Feld, und in einem Satz zusammengefasst.
      const teile: string[] = []
      const uebernommen = ergebnis.filter(e => e.uebernommen).map(e => e.label)
      const behalten = ergebnis.filter(e => e.gepflegt).map(e => e.label)
      if (uebernommen.length > 0) teile.push(`${aufzaehlung(uebernommen)} übernommen`)
      if (behalten.length > 0) {
        teile.push(`${aufzaehlung(behalten)} unverändert — der eingetragene Wert bleibt stehen`)
      }
      const bilanzText = teile.length > 0 ? ` ${teile.join(', ')}.` : ''

      // Die Herkunft der Temperatur steht daneben, weil sie eine ANDERE sein
      // kann als die der Strahlung: die eigene Messreihe der Anlage schlägt
      // das Archiv (`temperatur_herkunft`, api/wetter.ts).
      const temperatur = ergebnis.find(e => e.feld === 'durchschnittstemperatur')
      const temperaturText = temperatur?.uebernommen
        ? data.temperatur_herkunft === 'messung'
          ? ' Ø Temperatur aus den gemessenen Außentemperaturen des Monats.'
          : ` Ø Temperatur von ${data.provider_info?.name ?? 'Wetterdienst'}.`
        : ''

      setWetterInfo(quellenText + bilanzText + temperaturText)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Wetterdaten konnten nicht abgerufen werden')
    } finally {
      setWetterLoading(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitted(true)

    // V2: Pflichtfelder prüfen, bei Fehler blockieren + zum ersten scrollen.
    const pflicht: PflichtFeld[] = ['einspeisung_kwh', 'netzbezug_kwh']
    const ersterFehler = pflicht.find(feldFehler)
    if (ersterFehler) {
      feldRefs.current[ersterFehler]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }

    try {
      setLoading(true)

      // Sammle Investitions-Daten
      const invDaten: Record<string, InvestitionMonatsdaten> = {}
      // Hilfsfunktion: Wert nur setzen wenn nicht leer (aber 0 erlauben!)
      const hasValue = (val: string | undefined): boolean => val !== undefined && val !== ''
      const pf = (val: string) => parseFloat(val)
      const pi = (val: string) => parseInt(val)

      aktiveInvestitionen.forEach(inv => {
        const daten = investitionsDaten[inv.id]
        if (!daten) return

        const parsed: InvestitionMonatsdaten = {}

        // Generisches Parsen aus field_definitions (E4) — mit den belegten
        // Feldern (N-578 B2b): ein sichtbares weiches Feld wird auch gesendet.
        const felder = getFelderFuerInvestition(inv.typ, inv.parameter, belegteFuer(inv))
        // #352: Steht im Feld genau der Vorschlag, den das Backend als
        // ZERLEGUNG eines Anlagen-Gesamtwerts geliefert hat (Connector/Cloud
        // bei mehreren Modulen bzw. Speichern), geben wir seine Marke mit.
        // Ohne sie landet der gerechnete Wert als Gerätemessung in der
        // Provenance — und die String-Sichten ranken ihn gegen echte
        // Messungen. Verglichen wird mit derselben Genauigkeits-Regel wie
        // „bereits übernommen" im AssistenzFeld (PN 90128).
        const abgeleiteteFelder: Record<string, string> = {}
        felder.forEach(f => {
          if (hasValue(daten[f.feld])) {
            const wert = f.datentyp === 'int' ? pi(daten[f.feld]) : pf(daten[f.feld]);
            (parsed as Record<string, number>)[f.feld] = wert
            const marke = abgeleiteteMarke(wert, invStatus[inv.id]?.[f.feld]?.vorschlaege)
            if (marke) abgeleiteteFelder[f.feld] = marke
          }
        })
        // WP Auto-Sum: stromverbrauch aus getrennten Werten berechnen.
        // N-578 (H2): NICHT, wenn ein Gesamt-Sensor zugeordnet ist — dann
        // liefert er die Menge (Vorschlag im sichtbaren Feld bzw. später der
        // HA-Statistik-Import); eine gesendete Summe stünde als `manual:form`
        // davor und hielte den Import ab. Leer + kein Sensor = eedc rechnet.
        if (istAutoSummenFeld(inv.typ, 'stromverbrauch_kwh', inv.parameter)
            && !hasValue(daten.stromverbrauch_kwh)
            && !sensorFelder(inv.id).has('stromverbrauch_kwh')) {
          const sh = hasValue(daten.strom_heizen_kwh) ? pf(daten.strom_heizen_kwh) : 0
          const sw = hasValue(daten.strom_warmwasser_kwh) ? pf(daten.strom_warmwasser_kwh) : 0
          if (sh > 0 || sw > 0) {
            (parsed as Record<string, number>).stromverbrauch_kwh = sh + sw
            // N-578 B2a: die Summe kennzeichnet sich — sonst stünde sie in der
            // Provenance wie ein gepflegter Gesamtzähler-Wert, und nichts
            // unterschiede sie später von einer eigenen Aussage des Anwenders.
            abgeleiteteFelder.stromverbrauch_kwh = ABGELEITET_SUMME_ACHSEN
          }
        }

        // Sonstige Positionen (Erträge & Ausgaben) für alle Investitionstypen.
        // 0-€-Positionen mit Bezeichnung sind legitim (rilmor-mhrs #286 v3.32.1);
        // Filter prüft nur die Bezeichnung. Hatte die Investition beim Laden
        // Positionen und sind jetzt keine gültigen mehr da, muss eine leere
        // Liste raus — sonst lässt `_save_investitionen_monatsdaten` den
        // Sub-Key unangetastet und die alte Liste bleibt in der DB stehen
        // (#286 rcmcronny: Löschen verpuffte trotz v3.32.0-Fix, weil
        // MonatsdatenForm denselben Bug wie der MonatsabschlussWizard hatte).
        const invPositionen = sonstigePositionen[String(inv.id)] || []
        const gueltigePositionen = invPositionen.filter(p => p.bezeichnung.trim())
        const hattePositionen = initialHattePositionen[String(inv.id)] === true
        if (gueltigePositionen.length > 0 || hattePositionen) {
          (parsed as Record<string, unknown>).sonstige_positionen = gueltigePositionen
        }

        // PN 90128: bewusst behaltene Sensor-Abweichungen dieser Investition —
        // immer mitgeben, sobald überhaupt etwas für sie gespeichert wird. Ein
        // leeres Objekt nimmt frühere Bestätigungen zurück (der Sensor meldet
        // inzwischen etwas anderes oder der Wert wurde geändert).
        const invBehalten = behaltenInv[inv.id] ?? {}
        if (Object.keys(parsed).length > 0 || Object.keys(invBehalten).length > 0) {
          (parsed as Record<string, unknown>).geprueft_gegen = invBehalten
          // Gleiches Muster wie `geprueft_gegen`: kein Messwert, sondern
          // Metadaten zum Wert — das Backend zieht den Schlüssel heraus,
          // bevor `verbrauch_daten` geschrieben wird (#352).
          if (Object.keys(abgeleiteteFelder).length > 0) {
            (parsed as Record<string, unknown>).abgeleitet_felder = abgeleiteteFelder
          }
          invDaten[inv.id] = parsed
        }
      })

      // Verwende Summen aus Investitionen falls nicht manuell eingegeben
      const battLadung = formData.batterie_ladung_kwh
        ? parseFloat(formData.batterie_ladung_kwh)
        : berechneteWerte.batterieLadung || undefined
      const battEntladung = formData.batterie_entladung_kwh
        ? parseFloat(formData.batterie_entladung_kwh)
        : berechneteWerte.batterieEntladung || undefined
      // pv_erzeugung_kwh ist ein rein manuelles/importiertes Aggregat und wird
      // NIE programmatisch aus der Modul-Summe gefüllt (kWp-Verteilung-Design,
      // [[project_kwp_verteilung_aggregator]]). Die Pro-Modul-Werte gehen über
      // investitionen_daten; die Aggregat-Verteilung passiert beim Lesen.
      // N-622 Nacharbeit: Hatte der Monat einen gespeicherten Anlagenwert und ist die
      // Zeile jetzt leer, geht ein ausdrückliches `null` raus — die Schreibroute
      // (`exclude_unset`) ließe einen fehlenden Schlüssel stehen, `null` löscht.
      const pvErz = formData.pv_erzeugung_kwh
        ? parseFloat(formData.pv_erzeugung_kwh)
        : (gespeicherterPvGesamt ? null : undefined)

      await onSubmit({
        anlage_id: anlageId,
        jahr: parseInt(formData.jahr),
        monat: parseInt(formData.monat),
        einspeisung_kwh: parseFloat(formData.einspeisung_kwh),
        netzbezug_kwh: parseFloat(formData.netzbezug_kwh),
        pv_erzeugung_kwh: pvErz,
        batterie_ladung_kwh: battLadung,
        batterie_entladung_kwh: battEntladung,
        netzbezug_durchschnittspreis_cent: formData.netzbezug_durchschnittspreis_cent ? parseFloat(formData.netzbezug_durchschnittspreis_cent) : undefined,
        einspeise_durchschnittspreis_cent: formData.einspeise_durchschnittspreis_cent !== '' ? parseFloat(formData.einspeise_durchschnittspreis_cent) : undefined,
        kraftstoffpreis_euro: formData.kraftstoffpreis_euro ? parseFloat(formData.kraftstoffpreis_euro) : undefined,
        gaspreis_cent_kwh: formData.gaspreis_cent_kwh ? parseFloat(formData.gaspreis_cent_kwh) : undefined,
        globalstrahlung_kwh_m2: formData.globalstrahlung_kwh_m2 ? parseFloat(formData.globalstrahlung_kwh_m2) : undefined,
        sonnenstunden: formData.sonnenstunden ? parseFloat(formData.sonnenstunden) : undefined,
        durchschnittstemperatur: formData.durchschnittstemperatur ? parseFloat(formData.durchschnittstemperatur) : undefined,
        // G19-1: Basis-Positionen — gleiche Gültigkeits-/Löschsignal-Regel wie
        // die IMD-Positionen oben (0-€ mit Bezeichnung legitim, #286).
        sonstige_positionen: (() => {
          const gueltige = basisPositionen.filter(p => p.bezeichnung.trim())
          return (gueltige.length > 0 || initialHatteBasisPositionen) ? gueltige : undefined
        })(),
        notizen: formData.notizen || undefined,
        // PN 90128: siehe oben — immer gesendet, `{}` nimmt alles zurück.
        geprueft_gegen: behaltenBasis,
        investitionen_daten: Object.keys(invDaten).length > 0 ? invDaten : undefined,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  if (invLoading || loadingInvData) {
    return <div className="text-center py-4 text-gray-500">
      {loadingInvData ? 'Lade Investitionsdaten...' : 'Lade Investitionen...'}
    </div>
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {error && <Alert type="error">{error}</Alert>}

      {/* HA-Vorausfüllung Hinweis */}
      {haVorausfuellung && (
        <Alert type="info">
          Die Werte wurden aus der Home Assistant Langzeitstatistik geladen.
          Bitte prüfen Sie die Daten und ergänzen Sie fehlende Werte vor dem Speichern.
        </Alert>
      )}

      {/* Kopf-Ampel (§6.2) — Gesamtüberblick statt Step-Zähler */}
      {status && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-800/40 px-4 py-2.5">
          <KopfAmpel ampel={ampel} onSpringeZuOffen={springeZuOffen} />
          <ZustandLegende />
        </div>
      )}

      {/* Zeitraum */}
      <FormSection title="Zeitraum">
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Jahr"
            name="jahr"
            type="number"
            min="2000"
            max="2100"
            value={formData.jahr}
            onChange={handleChange}
            required
            disabled={!!monatsdaten}
          />
          <Select
            label="Monat"
            name="monat"
            value={formData.monat}
            onChange={handleChange}
            options={monatOptions}
            required
            disabled={!!monatsdaten}
          />
        </div>
      </FormSection>

      {/* Energie-Daten */}
      <FormSection title="Energie-Daten (kWh)">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
          <AssistenzFeld
            label="Einspeisung"
            name="einspeisung_kwh"
            min="0"
            value={formData.einspeisung_kwh}
            onChange={(v) => setFormData(prev => ({ ...prev, einspeisung_kwh: v }))}
            onBlur={() => markTouched('einspeisung_kwh')}
            required
            error={zeigeFehler('einspeisung_kwh')}
            feldStatus={basisStatus.einspeisung_kwh}
            bestaetigt={bestaetigteFelder.has('einspeisung_kwh')}
            onBestaetigen={() => bestaetigeFeld('einspeisung_kwh')}
            containerRef={(el) => { feldRefs.current.einspeisung_kwh = el }}
          />
          <AssistenzFeld
            label="Netzbezug"
            name="netzbezug_kwh"
            min="0"
            value={formData.netzbezug_kwh}
            onChange={(v) => setFormData(prev => ({ ...prev, netzbezug_kwh: v }))}
            onBlur={() => markTouched('netzbezug_kwh')}
            required
            error={zeigeFehler('netzbezug_kwh')}
            feldStatus={basisStatus.netzbezug_kwh}
            bestaetigt={bestaetigteFelder.has('netzbezug_kwh')}
            onBestaetigen={() => bestaetigeFeld('netzbezug_kwh')}
            containerRef={(el) => { feldRefs.current.netzbezug_kwh = el }}
          />
          {hatDynamischenTarif && (
            <AssistenzFeld
              label="Ø Strompreis (dynamisch)"
              name="netzbezug_durchschnittspreis_cent"
              min="0"
              value={formData.netzbezug_durchschnittspreis_cent}
              onChange={(v) => setFormData(prev => ({ ...prev, netzbezug_durchschnittspreis_cent: v }))}
              hint="Monatsdurchschnitt bei dynamischem Tarif (ct/kWh)"
              feldStatus={basisStatus.netzbezug_durchschnittspreis_cent}
            bestaetigt={bestaetigteFelder.has('netzbezug_durchschnittspreis_cent')}
            onBestaetigen={() => bestaetigeFeld('netzbezug_durchschnittspreis_cent')}
            />
          )}
          {/* #392: variable Einspeisevergütung — 0 ist ein Wert, deshalb
              prüft der Payload auf leeren String, nicht truthy. */}
          {hatVariableEinspeisung && (
            <AssistenzFeld
              label="Einspeisevergütung (Monat)"
              name="einspeise_durchschnittspreis_cent"
              min="0"
              value={formData.einspeise_durchschnittspreis_cent}
              onChange={(v) => setFormData(prev => ({ ...prev, einspeise_durchschnittspreis_cent: v }))}
              hint="Vergütungssatz dieses Monats (ct/kWh), z. B. OeMAG-Marktpreis — schlägt den Stammwert des Tarifs"
              feldStatus={basisStatus.einspeise_durchschnittspreis_cent}
              bestaetigt={bestaetigteFelder.has('einspeise_durchschnittspreis_cent')}
              onBestaetigen={() => bestaetigeFeld('einspeise_durchschnittspreis_cent')}
            />
          )}
          {/* PV-Erzeugung: berechnet → Display (D1, kein Input), sonst editierbar (Legacy) */}
          {(hatPVModule || hatWechselrichter) && berechneteWerte.pvErzeugung > 0 ? (
            <div>
              <span className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                PV-Erzeugung (berechnet)
              </span>
              <div className="flex min-h-[42px] w-full items-center rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-3 py-2 text-gray-900 dark:text-gray-100">
                {fmtZahl(berechneteWerte.pvErzeugung, 1)} kWh
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Aus {hatPVModule ? 'PV-Modulen' : 'Wechselrichtern'}: {fmtZahl(berechneteWerte.pvErzeugung, 1)} kWh
              </p>
              {/* N-622: steht daneben ein abweichender Gesamtzähler der Anlage, sagt die
                  Anzeige es — keine Rechnung, nur beide Zahlen in derselben Formatierung. */}
              {formData.pv_erzeugung_kwh !== ''
                && fmtZahl(parseFloat(formData.pv_erzeugung_kwh), 1) !== fmtZahl(berechneteWerte.pvErzeugung, 1) && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {haPvGesamt ? 'Gesamtzähler' : 'Gesamtwert'} der Anlage: {fmtZahl(parseFloat(formData.pv_erzeugung_kwh), 1)} kWh — Quellen mit eigenem Wert
                  gewinnen, er füllt nur, was sie nicht erklären.
                </p>
              )}
            </div>
          ) : !zeigePvGesamtZeile && (
            <Input
              label={hatPVModule || hatWechselrichter ? "PV-Erzeugung (aus Modulen unten)" : "PV-Erzeugung (optional)"}
              name="pv_erzeugung_kwh"
              type="number"
              step="0.01"
              min="0"
              value={formData.pv_erzeugung_kwh}
              onChange={handleChange}
              placeholder="z.B. 800"
              hint={hatPVModule || hatWechselrichter ? "Wird aus PV-Modulen berechnet" : "Manuell eingeben wenn keine PV-Module definiert"}
            />
          )}
          {zeigePvGesamtZeile && (
            <Input
              label={haPvGesamt ? 'PV-Gesamtzähler aus Home Assistant' : 'PV-Gesamtwert der Anlage'}
              name="pv_erzeugung_kwh"
              type="number"
              step="0.01"
              min="0"
              value={formData.pv_erzeugung_kwh}
              onChange={handleChange}
              hint={
                'Monatswert in kWh für die ganze Anlage: Quellen mit eigenem Wert gewinnen, der Gesamtwert füllt nur, '
                + 'was sie nicht erklären. Ist das Feld beim Speichern leer, hat der Monat keinen Gesamtwert.'
                + (haPvGesamt && gespeicherterPvGesamt
                  ? ` Bisher gespeichert: ${fmtZahl(monatsdaten?.pv_erzeugung_kwh, 1)} kWh.`
                  : '')
              }
            />
          )}
        </div>
      </FormSection>

      {/* R20-8 (Rainer): Vergleichspreise NICHT unter „Energie-Daten (kWh)" (sind
          keine kWh-Bilanz-Größen) → eigene optionale Untergruppe. Reine Gruppierung,
          Felder/Hinweise/Badges unverändert. Nur wenn eine Vergleichsgröße greift. */}
      {(hatEAuto || hatWaermepumpe) && (
        <FormSection
          title="Vergleichspreise (optional)"
          description="Monatsdurchschnitte für die Alternativ-Vergleiche (E-Auto / Wärmepumpe) — nicht Teil der kWh-Bilanz."
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
            {hatEAuto && (
              <AssistenzFeld
                label="Ø Benzinpreis"
                name="kraftstoffpreis_euro"
                step="0.001"
                min="0"
                value={formData.kraftstoffpreis_euro}
                onChange={(v) => setFormData(prev => ({ ...prev, kraftstoffpreis_euro: v }))}
                hint="€/L — Monatsdurchschnitt für E-Auto-Vergleich"
                feldStatus={basisStatus.kraftstoffpreis_euro}
                bestaetigt={bestaetigteFelder.has('kraftstoffpreis_euro')}
                onBestaetigen={() => bestaetigeFeld('kraftstoffpreis_euro')}
              />
            )}
            {hatWaermepumpe && (
              <AssistenzFeld
                label="Ø Gas-/Ölpreis"
                name="gaspreis_cent_kwh"
                min="0"
                value={formData.gaspreis_cent_kwh}
                onChange={(v) => setFormData(prev => ({ ...prev, gaspreis_cent_kwh: v }))}
                hint="ct/kWh — Monatsdurchschnitt für WP-Vergleich"
                feldStatus={basisStatus.gaspreis_cent_kwh}
                bestaetigt={bestaetigteFelder.has('gaspreis_cent_kwh')}
                onBestaetigen={() => bestaetigeFeld('gaspreis_cent_kwh')}
              />
            )}
          </div>
        </FormSection>
      )}

      {/* PV-Module (falls vorhanden) */}
      {hatPVModule && (
        <InvestitionSection
          title="PV-Module"
          icon={Sun}
          iconColor="text-yellow-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'pv-module')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={felderFuer}
          feldStatus={(id, f) => invStatus[id]?.[f]}
          statusMonthKey={statusMonthKey}
          istBestaetigt={istInvBestaetigt}
          onBestaetigen={bestaetigeInvFelder}
        />
      )}

      {/* Wechselrichter (falls vorhanden und keine PV-Module) */}
      {hatWechselrichter && !hatPVModule && (
        <InvestitionSection
          title="Wechselrichter"
          icon={Sun}
          iconColor="text-yellow-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'wechselrichter')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={felderFuer}
          feldStatus={(id, f) => invStatus[id]?.[f]}
          statusMonthKey={statusMonthKey}
          istBestaetigt={istInvBestaetigt}
          onBestaetigen={bestaetigeInvFelder}
        />
      )}

      {/* Speicher (falls vorhanden) */}
      {hatSpeicher && (
        <>
          <InvestitionSection
            title="Speicher"
            icon={Battery}
            iconColor="text-green-500"
            investitionen={aktiveInvestitionen.filter(i => i.typ === 'speicher')}
            investitionsDaten={investitionsDaten}
            onInvChange={handleInvChange}
            sonstigePositionen={sonstigePositionen}
            onPositionenChange={handlePositionenChange}
            felderFn={felderFuer}
            feldStatus={(id, f) => invStatus[id]?.[f]}
            statusMonthKey={statusMonthKey}
            istBestaetigt={istInvBestaetigt}
            onBestaetigen={bestaetigeInvFelder}
          />
          {(berechneteWerte.batterieLadung > 0 || berechneteWerte.batterieEntladung > 0) && (
            <div className="text-xs text-gray-500 dark:text-gray-400 px-1">
              Summe: Ladung {fmtZahl(berechneteWerte.batterieLadung, 1)} kWh | Entladung {fmtZahl(berechneteWerte.batterieEntladung, 1)} kWh
            </div>
          )}
        </>
      )}

      {/* E-Auto (falls vorhanden) */}
      {hatEAuto && (
        <InvestitionSection
          title="E-Auto"
          icon={Car}
          iconColor="text-blue-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'e-auto')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={felderFuer}
          feldStatus={(id, f) => invStatus[id]?.[f]}
          statusMonthKey={statusMonthKey}
          istBestaetigt={istInvBestaetigt}
          onBestaetigen={bestaetigeInvFelder}
        />
      )}

      {/* Wallbox (falls vorhanden) */}
      {hatWallbox && (
        <InvestitionSection
          title="Wallbox"
          icon={Plug}
          iconColor="text-purple-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'wallbox')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={felderFuer}
          feldStatus={(id, f) => invStatus[id]?.[f]}
          statusMonthKey={statusMonthKey}
          istBestaetigt={istInvBestaetigt}
          onBestaetigen={bestaetigeInvFelder}
        />
      )}

      {/* Wärmepumpe (falls vorhanden) */}
      {hatWaermepumpe && (
        <InvestitionSection
          title="Wärmepumpe"
          icon={Flame}
          iconColor="text-orange-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'waermepumpe')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={felderFuer}
          feldStatus={(id, f) => invStatus[id]?.[f]}
          statusMonthKey={statusMonthKey}
          istBestaetigt={istInvBestaetigt}
          onBestaetigen={bestaetigeInvFelder}
        />
      )}

      {/* Balkonkraftwerk (falls vorhanden) */}
      {hatBalkonkraftwerk && (
        <InvestitionSection
          title="Balkonkraftwerk"
          icon={Zap}
          iconColor="text-amber-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'balkonkraftwerk')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={felderFuer}
          feldStatus={(id, f) => invStatus[id]?.[f]}
          statusMonthKey={statusMonthKey}
          istBestaetigt={istInvBestaetigt}
          onBestaetigen={bestaetigeInvFelder}
          subtitleFn={bkwLeistung}
          hinweisFn={(inv) => inv.parameter?.hat_speicher
            ? 'Mit Speicher: Bei Nulleinspeisung entspricht Eigenverbrauch meist der Erzeugung.'
            : 'Ohne Speicher: Eigenverbrauch ist der direkt genutzte Anteil (typisch 30-40% der Erzeugung).'}
        />
      )}

      {/* Sonstiges (falls vorhanden) */}
      {hatSonstiges && (
        <InvestitionSection
          title="Sonstiges"
          icon={MoreHorizontal}
          iconColor="text-gray-500"
          investitionen={aktiveInvestitionen.filter(i => i.typ === 'sonstiges')}
          investitionsDaten={investitionsDaten}
          onInvChange={handleInvChange}
          sonstigePositionen={sonstigePositionen}
          onPositionenChange={handlePositionenChange}
          felderFn={felderFuer}
          feldStatus={(id, f) => invStatus[id]?.[f]}
          statusMonthKey={statusMonthKey}
          istBestaetigt={istInvBestaetigt}
          onBestaetigen={bestaetigeInvFelder}
          hinweisFn={(inv) => {
            const kat = (inv.parameter?.kategorie as string) || ''
            // SoT-Map (R3b S7); Fallback bewusst der rohe kat-Wert (wie zuvor).
            // N-244: OHNE gepflegte Kategorie steht hier kein Label mehr. Es
            // stand bis 17.08.2026 „Erzeuger" da — geraten, und seit derselben
            // Arbeit im Widerspruch zu den Feldern direkt darunter, die für ein
            // ungepflegtes Gerät beide Richtungen anbieten.
            const label = kat ? (SONSTIGES_KATEGORIE_LABELS[kat] || kat) : ''
            const beschreibung = inv.parameter?.beschreibung ? String(inv.parameter.beschreibung) : ''
            if (label && beschreibung) return `${label} - ${beschreibung}`
            return label || beschreibung || null
          }}
        />
      )}

      {/* Batterie manuell (falls kein Speicher als Investition) */}
      {!hatSpeicher && (
        <FormSection title="Batterie (optional)">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Batterie Ladung"
              name="batterie_ladung_kwh"
              type="number"
              step="0.01"
              min="0"
              value={formData.batterie_ladung_kwh}
              onChange={handleChange}
              placeholder="z.B. 150"
            />
            <Input
              label="Batterie Entladung"
              name="batterie_entladung_kwh"
              type="number"
              step="0.01"
              min="0"
              value={formData.batterie_entladung_kwh}
              onChange={handleChange}
              placeholder="z.B. 140"
            />
          </div>
        </FormSection>
      )}

      {/* Wetterdaten */}
      <FormSection variant="erweitert" title="Wetterdaten (optional)" icon={Cloud}>
        <div className="flex justify-end mb-3">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={fetchWetterdaten}
            disabled={wetterLoading}
          >
            {wetterLoading ? (
              <><Loader2 className="w-4 h-4 animate-spin mr-1" /> Lade...</>
            ) : (
              <><Cloud className="w-4 h-4 mr-1" /> Auto-Fill</>
            )}
          </Button>
        </div>
        {wetterInfo && (
          <p className="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 px-3 py-2 rounded mb-3">
            {wetterInfo}
          </p>
        )}
        <div className="grid grid-cols-3 gap-4 items-start">
          <AssistenzFeld
            label="Globalstrahlung"
            name="globalstrahlung_kwh_m2"
            step="0.1"
            min="0"
            value={formData.globalstrahlung_kwh_m2}
            onChange={(v) => setFormData(prev => ({ ...prev, globalstrahlung_kwh_m2: v }))}
            hint="kWh/m²"
            feldStatus={basisStatus.globalstrahlung_kwh_m2}
            bestaetigt={bestaetigteFelder.has('globalstrahlung_kwh_m2')}
            onBestaetigen={() => bestaetigeFeld('globalstrahlung_kwh_m2')}
          />
          <AssistenzFeld
            label="Sonnenstunden"
            name="sonnenstunden"
            step="0.1"
            min="0"
            value={formData.sonnenstunden}
            onChange={(v) => setFormData(prev => ({ ...prev, sonnenstunden: v }))}
            hint="Stunden"
            feldStatus={basisStatus.sonnenstunden}
            bestaetigt={bestaetigteFelder.has('sonnenstunden')}
            onBestaetigen={() => bestaetigeFeld('sonnenstunden')}
          />
          <AssistenzFeld
            label="Ø Temperatur"
            name="durchschnittstemperatur"
            step="0.1"
            value={formData.durchschnittstemperatur}
            onChange={(v) => setFormData(prev => ({ ...prev, durchschnittstemperatur: v }))}
            hint="°C (optional)"
            feldStatus={basisStatus.durchschnittstemperatur}
            bestaetigt={bestaetigteFelder.has('durchschnittstemperatur')}
            onBestaetigen={() => bestaetigeFeld('durchschnittstemperatur')}
          />
        </div>
      </FormSection>

      {/* G19-1: Sonstige Erträge & Ausgaben (Anlage-Ebene) + Notizen —
          DERSELBE Positions-Baustein wie je Investition (eine Code-Wahrheit). */}
      <FormSection variant="erweitert" title="Sonstige Erträge & Ausgaben + Notizen">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Für Zahlungen auf Anlagen-Ebene, die keiner Komponente zuzuordnen sind —
          beide Richtungen: Abschlag an den Versorger = Ausgabe · Einspeise-Abschlag
          vom Netzbetreiber = Ertrag · Guthaben-Auszahlung aus der Jahresabrechnung =
          Ertrag · Nachzahlung = Ausgabe. Wichtig: Wer Abschläge oder Guthaben erfasst,
          erfasst die Jahresabrechnung entsprechend reduziert — eedc rechnet Abschläge
          nicht gegen (sonst zählt derselbe Betrag doppelt).
        </p>
        <SonstigePositionenFields
          positionen={basisPositionen}
          onChange={setBasisPositionen}
        />
        <div className="mt-4">
          <Textarea
            label="Notizen"
            name="notizen"
            value={formData.notizen}
            onChange={handleChange}
            rows={2}
            placeholder="Optionale Bemerkungen..."
          />
        </div>
      </FormSection>

      {/* Abschluss-Review (§6.6) — das Tor des „Abschlusses", kein eigener Schritt */}
      {status && (
        <AbschlussReview
          ampel={ampel}
          warnungen={reviewWarnungen}
          onSpringeZuFeld={springeZuFeld}
        />
      )}

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button type="submit" loading={loading}>
          {monatsdaten ? 'Speichern & abschließen' : 'Monat erfassen & abschließen'}
        </Button>
      </div>
    </form>
  )
}
