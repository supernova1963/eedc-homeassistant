import { useState, useEffect, useRef, FormEvent } from 'react'
import { ExternalLink } from 'lucide-react'
import { Button, Input, Select, Switch, Alert, DatumFeld, FormSection } from '../ui'
import type { SelectItem, SelectOption } from '../ui/Select'
import VersorgerSection from './VersorgerSection'
import AnlagenfotoSection from './AnlagenfotoSection'
import { wetterApi, type WetterProvider, type WetterProviderList } from '../../api/wetter'
import { anlagenApi } from '../../api/anlagen'
import type { Anlage, AnlageCreate, VersorgerDaten } from '../../types'
import { useHAVerbunden } from '../../hooks/useHAAvailable'

interface AnlageFormProps {
  anlage?: Anlage | null
  onSubmit: (data: AnlageCreate) => Promise<void>
  onCancel: () => void
}

const LAND_OPTIONEN: SelectItem[] = [
  { value: 'DE', label: 'Deutschland' },
  { value: 'AT', label: 'Österreich' },
  { value: 'CH', label: 'Schweiz' },
  { value: 'IT', label: 'Italien' },
]

const UST_BEHANDLUNG_OPTIONEN: SelectItem[] = [
  { value: 'keine_ust', label: 'Keine USt-Auswirkung (Standard)' },
  { value: 'regelbesteuerung', label: 'Regelbesteuerung (USt auf Eigenverbrauch)' },
]

const WETTER_MODELL_OPTIONEN: SelectItem[] = [
  { value: 'auto', label: 'Automatisch (best_match)' },
  {
    label: '── Seamless (empfohlen) ──',
    options: [
      { value: 'icon_seamless', label: 'DWD ICON Seamless — Deutschland/Europa' },
      { value: 'meteoswiss_seamless', label: 'MeteoSwiss Seamless — Alpenraum' },
      { value: 'ecmwf_seamless', label: 'ECMWF Seamless — Global (15 Tage)' },
    ],
  },
  {
    label: '── Einzelmodelle ──',
    options: [
      { value: 'meteoswiss_icon_ch2', label: 'MeteoSwiss ICON-CH2 (2.1 km, 5 Tage)' },
      { value: 'icon_d2', label: 'DWD ICON-D2 (2.2 km, 2 Tage)' },
      { value: 'icon_eu', label: 'DWD ICON-EU (7 km, 5 Tage)' },
      { value: 'ecmwf_ifs04', label: 'ECMWF IFS (9 km, 10 Tage)' },
    ],
  },
]

const WETTER_PROVIDER_FALLBACK: SelectItem[] = [
  { value: 'auto', label: 'Automatisch (empfohlen)' },
  { value: 'open-meteo', label: 'Open-Meteo' },
  { value: 'brightsky', label: 'Bright Sky (DWD)' },
  { value: 'open-meteo-solar', label: 'Open-Meteo Solar' },
]

type PflichtFeld = 'anlagenname' | 'leistung_kwp'

/**
 * Auswahl der PV-Prognose-Quelle.
 *
 * Maßgeblich ist die **Verbindung** zu Home Assistant, nicht die Betriebsart:
 * `prognose_router.resolve_prognose_quelle` liefert SFML seit N-156 auch über
 * eine Token-Anbindung aus, und Solcast findet seine Sensoren dort ohne eigenen
 * API-Schlüssel. Das Feld hing bis dahin am Supervisor-Flag und sperrte damit
 * genau den Betrieb aus, für den der Backend-Weg gebaut wurde (F-28).
 *
 * Als reine Funktion, damit die Bedingung prüfbar ist statt im Rendering zu
 * stehen (dieselbe Form wie `fehlendeHAVoraussetzung`).
 */
export function bauePrognoseQuelleOptionen(haVerbunden: boolean): SelectOption[] {
  return [
    { value: 'eedc', label: 'eedc-optimiert (Standard)' },
    { value: 'solcast', label: 'Solcast (pur, ohne Korrektur)' },
    {
      value: 'sfml',
      label: haVerbunden
        ? 'Solar Forecast ML (pur, aus Home Assistant)'
        : 'Solar Forecast ML (pur) — nur mit verbundenem Home Assistant',
      disabled: !haVerbunden,
    },
  ]
}

/** Erklärtext unter dem Auswahlfeld — hängt an derselben Bedingung. */
export function prognoseQuelleHinweis(quelle: string, haVerbunden: boolean): string {
  if (quelle === 'eedc') {
    return 'Open-Meteo Rohprognose mit anlagenspezifischem Lernfaktor (MOS-Verfahren). Funktioniert überall, auch standalone.'
  }
  if (quelle === 'solcast') {
    return haVerbunden
      ? 'Solcast-Prognose direkt über die Solcast-Integration in Home Assistant, ohne eedc-Korrektur und ohne eigenen API-Schlüssel.'
      : 'Solcast-Prognose direkt via API-Token, ohne eedc-Korrektur. API-Token muss konfiguriert sein.'
  }
  return 'Solar Forecast ML direkt aus der HA-Integration, ohne eedc-Korrektur. eedc nutzt dabei SFMLs echtes Stundenprofil (bis zu 3 Tage, aus dem evcc-Prognose-Sensor). Setzt eine verbundene Home-Assistant-Instanz voraus — als Add-on oder über einen langlebigen Zugriffstoken.'
}

export default function AnlageForm({ anlage, onSubmit, onCancel }: AnlageFormProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const haVerbunden = useHAVerbunden()

  const [formData, setFormData] = useState({
    anlagenname: anlage?.anlagenname || '',
    leistung_kwp: anlage?.leistung_kwp?.toString() || '',
    installationsdatum: anlage?.installationsdatum || '',
    standort_land: anlage?.standort_land || 'DE',
    standort_plz: anlage?.standort_plz || '',
    standort_ort: anlage?.standort_ort || '',
    standort_strasse: anlage?.standort_strasse || '',
    latitude: anlage?.latitude?.toString() || '',
    longitude: anlage?.longitude?.toString() || '',
    mastr_id: anlage?.mastr_id || '',
    wetter_provider: anlage?.wetter_provider || 'auto',
    wetter_modell: anlage?.wetter_modell || 'auto',
    steuerliche_behandlung: anlage?.steuerliche_behandlung || 'keine_ust',
    ust_satz_prozent: anlage?.ust_satz_prozent?.toString() || '',
    unterliegt_eeg_51: anlage?.unterliegt_eeg_51 ?? false,
    community_auto_share: anlage?.community_auto_share ?? false,
    netz_puffer_w: anlage?.netz_puffer_w?.toString() || '100',
    prognose_quelle: anlage?.prognose_quelle || 'eedc',
  })

  // V1/V2: Inline-Fehler erst nach Berührung (touched) bzw. nach Absende-Versuch (Muster Slice 1).
  const [touched, setTouched] = useState<Set<string>>(new Set())
  const [submitted, setSubmitted] = useState(false)
  const feldRefs = useRef<Record<PflichtFeld, HTMLDivElement | null>>({
    anlagenname: null,
    leistung_kwp: null,
  })

  const markTouched = (name: string) => setTouched(prev => new Set(prev).add(name))

  const feldFehler = (name: PflichtFeld): string | undefined => {
    if (name === 'anlagenname') {
      return formData.anlagenname.trim() ? undefined : 'Bitte einen Namen eingeben'
    }
    if (!formData.leistung_kwp) return 'Pflichtfeld'
    const n = parseFloat(formData.leistung_kwp)
    if (Number.isNaN(n) || n <= 0) return 'Bitte eine gültige Leistung eingeben'
    return undefined
  }

  const zeigeFehler = (name: PflichtFeld): string | undefined =>
    (submitted || touched.has(name)) ? feldFehler(name) : undefined

  // Track if user manually changed USt-Satz
  const [ustManuell, setUstManuell] = useState(false)

  const [versorgerDaten, setVersorgerDaten] = useState<VersorgerDaten>(
    anlage?.versorger_daten || {}
  )

  const [providerListe, setProviderListe] = useState<WetterProviderList | null>(null)
  const [loadingProvider, setLoadingProvider] = useState(false)
  const [geocoding, setGeocoding] = useState(false)

  // Wetter-Provider-Verfügbarkeit laden, sobald Anlage + Koordinaten vorliegen
  // (Koordinaten aus dem Formular → aktualisiert sich auch nach Auto-Geocoding).
  useEffect(() => {
    if (anlage?.id && formData.latitude && formData.longitude) {
      setLoadingProvider(true)
      wetterApi.getProvider(anlage.id)
        .then(setProviderListe)
        .catch(() => {})
        .finally(() => setLoadingProvider(false))
    }
  }, [anlage?.id, formData.latitude, formData.longitude])

  // Auto-Geocoding beim Verlassen der Adresse — füllt Koordinaten NUR wenn leer
  // (kein Überschreiben manueller/bestehender Werte, Gernot-Vorgabe).
  const handleAdresseBlur = async () => {
    if (formData.latitude || formData.longitude) return
    if (!formData.standort_plz.trim()) return
    setGeocoding(true)
    try {
      const res = await anlagenApi.geocode(formData.standort_plz.trim(), formData.standort_ort.trim() || undefined)
      if (res?.latitude != null && res?.longitude != null) {
        setFormData(prev => ({
          ...prev,
          latitude: res.latitude.toFixed(6), /* de-de-allow: Input-Value (editierbares number-Feld latitude) */
          longitude: res.longitude.toFixed(6), /* de-de-allow: Input-Value (editierbares number-Feld longitude) */
        }))
      }
    } catch {
      // still ignorieren — Nutzer kann Koordinaten manuell eintragen
    } finally {
      setGeocoding(false)
    }
  }

  const UST_DEFAULTS: Record<string, string> = { DE: '19', AT: '20', CH: '8.1', IT: '22' }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData(prev => {
      const next = { ...prev, [name]: value }
      // Auto-set USt-Satz when country changes (unless user manually changed it)
      if (name === 'standort_land' && !ustManuell) {
        next.ust_satz_prozent = UST_DEFAULTS[value] || '19'
      }
      if (name === 'ust_satz_prozent') {
        setUstManuell(true)
      }
      return next
    })
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitted(true)

    // V2: alle Pflichtfelder prüfen, bei Fehler blockieren + zum ersten scrollen.
    const pflicht: PflichtFeld[] = ['anlagenname', 'leistung_kwp']
    const ersterFehler = pflicht.find(feldFehler)
    if (ersterFehler) {
      feldRefs.current[ersterFehler]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }

    try {
      setLoading(true)
      await onSubmit({
        anlagenname: formData.anlagenname.trim(),
        leistung_kwp: parseFloat(formData.leistung_kwp),
        installationsdatum: formData.installationsdatum || undefined,
        standort_land: formData.standort_land || 'DE',
        standort_plz: formData.standort_plz || undefined,
        standort_ort: formData.standort_ort || undefined,
        standort_strasse: formData.standort_strasse || undefined,
        latitude: formData.latitude ? parseFloat(formData.latitude) : undefined,
        longitude: formData.longitude ? parseFloat(formData.longitude) : undefined,
        mastr_id: formData.mastr_id || undefined,
        versorger_daten: Object.keys(versorgerDaten).length > 0 ? versorgerDaten : null,
        wetter_provider: formData.wetter_provider as WetterProvider,
        wetter_modell: formData.wetter_modell,
        steuerliche_behandlung: formData.steuerliche_behandlung || 'keine_ust',
        ust_satz_prozent: formData.ust_satz_prozent ? parseFloat(formData.ust_satz_prozent) : undefined,
        unterliegt_eeg_51: formData.unterliegt_eeg_51,
        community_auto_share: formData.community_auto_share,
        netz_puffer_w: formData.netz_puffer_w ? parseInt(formData.netz_puffer_w) : 100,
        prognose_quelle: formData.prognose_quelle || 'eedc',
      } as AnlageCreate)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  const providerOptionen: SelectItem[] = providerListe && providerListe.provider.length > 0
    ? providerListe.provider.map(p => ({
        value: p.id,
        label: `${p.name}${p.empfohlen ? ' (empfohlen)' : ''}${!p.verfuegbar ? ' (nicht verfügbar)' : ''}`,
        disabled: !p.verfuegbar,
      }))
    : WETTER_PROVIDER_FALLBACK

  const prognoseQuelleOptionen = bauePrognoseQuelleOptionen(haVerbunden)

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {error && <Alert type="error">{error}</Alert>}

      {/* ── Kern: Basis-Daten ── */}
      <FormSection title="Basis-Daten">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
          <div ref={(el) => { feldRefs.current.anlagenname = el }}>
            <Input
              label="Anlagenname"
              name="anlagenname"
              value={formData.anlagenname}
              onChange={handleChange}
              onBlur={() => markTouched('anlagenname')}
              placeholder="z.B. Meine PV-Anlage"
              required
              error={zeigeFehler('anlagenname')}
            />
          </div>
          <div ref={(el) => { feldRefs.current.leistung_kwp = el }}>
            <Input
              label="Leistung (kWp)"
              name="leistung_kwp"
              type="number"
              step="0.01"
              min="0.1"
              value={formData.leistung_kwp}
              onChange={handleChange}
              onBlur={() => markTouched('leistung_kwp')}
              placeholder="z.B. 10.5"
              required
              error={zeigeFehler('leistung_kwp')}
            />
          </div>
          {/* D14-13: DatumPicker-SoT statt nativem Datumsfeld (Einstellungen-Formulare). */}
          {/* R18-9 (rapahl #208): Label geschärft — das Feld ist das Stammdatum der
              GESAMT-Anlage (geht in Community-Hash + Benchmark-Zeitraum ein), nicht
              das älteste Gerät; genau diese Fehldeutung soll der Hinweis verhindern. */}
          <DatumFeld
            label="Inbetriebnahme (Anlage)"
            value={formData.installationsdatum}
            onChange={(v) => setFormData(prev => ({ ...prev, installationsdatum: v }))}
            hint="Stammdatum der Gesamt-Anlage (nicht das älteste Gerät) — steuert u. a. den Community-Vergleichszeitraum „seit Installation“"
          />
        </div>
        <div className="mt-4">
          <Alert type="info" title="Ausrichtung & Neigung">
            Diese Werte werden pro <strong>PV-Modul</strong> unter <strong>Einstellungen → Investitionen</strong> gepflegt.
            So können auch Anlagen mit mehreren Dachflächen korrekt abgebildet werden.
          </Alert>
        </div>
      </FormSection>

      {/* ── Kern: Standort (inkl. Koordinaten mit Auto-Geocoding) ── */}
      <FormSection title="Standort">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Select
            label="Land"
            name="standort_land"
            value={formData.standort_land}
            onChange={handleChange}
            options={LAND_OPTIONEN}
          />
          <Input
            label="PLZ"
            name="standort_plz"
            value={formData.standort_plz}
            onChange={handleChange}
            onBlur={handleAdresseBlur}
            placeholder={formData.standort_land === 'CH' ? 'z.B. 1234' : 'z.B. 12345'}
          />
          <Input
            label="Ort"
            name="standort_ort"
            value={formData.standort_ort}
            onChange={handleChange}
            onBlur={handleAdresseBlur}
            placeholder="z.B. Wien"
          />
          <Input
            label="Straße"
            name="standort_strasse"
            value={formData.standort_strasse}
            onChange={handleChange}
            placeholder="z.B. Musterstraße 1"
          />
        </div>
        {/* Koordinaten direkt unter der Adresse — nach Adress-Eingabe automatisch ermittelt (PVGIS-Prognose) */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <Input
            label="Breitengrad (Latitude)"
            name="latitude"
            type="number"
            step="0.000001"
            value={formData.latitude}
            onChange={handleChange}
            placeholder="z.B. 52.520008"
            hint="Nördliche Breite (positiv) — für die PVGIS-Prognose"
          />
          <Input
            label="Längengrad (Longitude)"
            name="longitude"
            type="number"
            step="0.000001"
            value={formData.longitude}
            onChange={handleChange}
            placeholder="z.B. 13.404954"
            hint="Östliche Länge (positiv)"
          />
        </div>
        {geocoding && (
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">Ermittle Koordinaten aus der Adresse …</p>
        )}
      </FormSection>

      {/* ── Kern: Anlagenfoto (nur für bestehende Anlagen) ── */}
      {anlage?.id && (
        <FormSection
          title="Anlagenfoto"
          description="Erscheint auf der Titelseite der Anlagendokumentation (Phase 4 Beta). Ein Foto pro Anlage — ein neues Foto ersetzt das vorherige."
        >
          <AnlagenfotoSection anlageId={anlage.id} />
        </FormSection>
      )}

      {/* ── Erweitert: Erweiterte Stammdaten (MaStR · Steuer · §51) ── */}
      <FormSection variant="erweitert" title="Erweiterte Stammdaten">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <Input
              label="MaStR-ID"
              name="mastr_id"
              value={formData.mastr_id}
              onChange={handleChange}
              placeholder="z.B. SEE123456789"
              hint="Marktstammdatenregister-ID der Anlage"
            />
            {formData.mastr_id && (
              <a
                href={`https://www.marktstammdatenregister.de/MaStR/Einheit/Detail/IndexOeffentlich/${formData.mastr_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 mt-1 text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400"
              >
                <ExternalLink className="w-3 h-3" />
                Im MaStR öffnen
              </a>
            )}
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <Select
            label="USt-Behandlung"
            name="steuerliche_behandlung"
            value={formData.steuerliche_behandlung}
            onChange={handleChange}
            options={UST_BEHANDLUNG_OPTIONEN}
          />
          {formData.steuerliche_behandlung === 'regelbesteuerung' && (
            <Input
              label="USt-Satz (%)"
              name="ust_satz_prozent"
              type="number"
              step="0.1"
              min="0"
              max="30"
              value={formData.ust_satz_prozent}
              onChange={handleChange}
              placeholder={UST_DEFAULTS[formData.standort_land] || '19'}
              hint={`Standard: ${UST_DEFAULTS[formData.standort_land] || '19'} % (${formData.standort_land || 'DE'})`}
            />
          )}
        </div>
        <div className="mt-4">
          <Alert type="warning">
            {formData.steuerliche_behandlung === 'regelbesteuerung' ? (
              <p>
                Bei <strong>Regelbesteuerung</strong> wird USt auf den Eigenverbrauch (unentgeltliche Wertabgabe)
                als Kostenfaktor in den Finanzergebnissen berechnet. Die Bemessungsgrundlage basiert auf den
                Selbstkosten (Abschreibung + Betriebskosten / Jahresertrag).
              </p>
            ) : (
              <p>
                <strong>Keine USt</strong> gilt für PV-Anlagen ab 2023 mit Nullsteuersatz (≤30 kWp),
                Kleinunternehmer (§19 UStG) oder wenn Sie keine steuerliche Erfassung wünschen.
              </p>
            )}
          </Alert>
        </div>
        <div className="mt-3 flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <Switch
            checked={formData.unterliegt_eeg_51}
            onChange={(an) => setFormData(prev => ({ ...prev, unterliegt_eeg_51: an }))}
            ariaLabel="Anlage unterliegt §51 EEG (Negativpreis-Regelung)"
          />
          <div>
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
              Anlage unterliegt §51 EEG (Negativpreis-Regelung)
            </span>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Bei Neuanlagen ab Solarpaket I (Inbetriebnahme i. d. R. ab 25.02.2025) entfällt die
              Einspeisevergütung in Stunden mit negativem Börsenpreis. Nur aktivieren, wenn Ihre Anlage
              betroffen ist — der entgangene Erlös wird dann im Cockpit als „§51-Verlust" ausgewiesen.
            </p>
          </div>
        </div>
      </FormSection>

      {/* ── Erweitert: Steuerungen (Verhalten + Prognose-Regler) ── */}
      <FormSection variant="erweitert" title="Steuerungen">
        {/* Automatisch teilen nach Monatsabschluss */}
        <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <Switch
            checked={formData.community_auto_share}
            onChange={(an) => setFormData(prev => ({ ...prev, community_auto_share: an }))}
            ariaLabel="Automatisch teilen nach Monatsabschluss"
          />
          <div>
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
              Automatisch teilen nach Monatsabschluss
            </span>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Anonymisierte Monatsdaten werden nach jedem Abschluss automatisch an den Community-Benchmark gesendet.
            </p>
          </div>
        </div>

        {/* Netz-Puffer (Energiefluss) */}
        <div className="mt-4">
          <Input
            label="Netz-Puffer (Watt)"
            id="netz_puffer_w"
            name="netz_puffer_w"
            type="number"
            min="0"
            max="1000"
            step="10"
            value={formData.netz_puffer_w}
            onChange={handleChange}
            className="w-28"
          />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Unterhalb dieses Werts wird das Netz als Balance (grün) angezeigt. Standard: 100 W
          </p>
        </div>

        {/* Wetterdaten-Quelle (Provider-Wahl) */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <Select
            label="Wetterdaten-Quelle"
            name="wetter_provider"
            value={formData.wetter_provider}
            onChange={handleChange}
            disabled={loadingProvider}
            options={providerOptionen}
          />
          <div className="flex items-end pb-1">
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {formData.wetter_provider === 'auto' && (
                <span>Automatische Auswahl: Bright Sky für DE, Open-Meteo sonst</span>
              )}
              {formData.wetter_provider === 'brightsky' && (
                <span>DWD-Daten über Bright Sky API (nur Deutschland)</span>
              )}
              {formData.wetter_provider === 'open-meteo' && (
                <span>Open-Meteo Archive API (weltweit verfügbar)</span>
              )}
              {formData.wetter_provider === 'open-meteo-solar' && (
                <span>GTI-Berechnung für geneigte PV-Module</span>
              )}
            </div>
          </div>
        </div>
        {!formData.latitude && !formData.longitude && (
          <div className="mt-3">
            <Alert type="warning">
              Bitte zuerst den Standort (Koordinaten) eintragen, um die verfügbaren Provider zu sehen.
            </Alert>
          </div>
        )}

        {/* Modell für Solar-Prognose */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <Select
            label="Modell für Solar-Prognose"
            name="wetter_modell"
            value={formData.wetter_modell}
            onChange={handleChange}
            options={WETTER_MODELL_OPTIONEN}
          />
          <div className="flex items-end pb-1">
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {formData.wetter_modell === 'auto' && (
                <span>Open-Meteo best_match — automatische Modellauswahl weltweit, bis 16 Tage.</span>
              )}
              {formData.wetter_modell === 'icon_seamless' && (
                <span>Empfohlen für Deutschland/Österreich/Schweiz. Open-Meteo kaskadiert intern: ICON-D2 (2.2 km) → ICON-EU → ICON-Global, bis 7.5 Tage.</span>
              )}
              {formData.wetter_modell === 'meteoswiss_seamless' && (
                <span>Empfohlen für Alpenraum (CH, AT-West, IT-Nord, FL). MeteoSwiss kombiniert alle Schweizer Modelle nahtlos, bis 5 Tage, danach Fallback auf best_match.</span>
              )}
              {formData.wetter_modell === 'ecmwf_seamless' && (
                <span>Empfohlen für globale Standorte und Langfrist. ECMWF kombiniert alle Modelle nahtlos, bis 15 Tage.</span>
              )}
              {formData.wetter_modell === 'meteoswiss_icon_ch2' && (
                <span>Einzelmodell: Hochauflösend für Alpenraum (2.1 km). Nur 5 Tage, danach Fallback auf best_match. Für die meisten Fälle ist MeteoSwiss Seamless besser.</span>
              )}
              {formData.wetter_modell === 'icon_d2' && (
                <span>Einzelmodell: DWD-Regionalmodell für Deutschland (2.2 km). Nur 2 Tage, danach Fallback auf best_match. Für die meisten Fälle ist ICON Seamless besser.</span>
              )}
              {formData.wetter_modell === 'icon_eu' && (
                <span>Einzelmodell: DWD-Modell für Europa (7 km). 5 Tage, danach Fallback auf best_match.</span>
              )}
              {formData.wetter_modell === 'ecmwf_ifs04' && (
                <span>Einzelmodell: ECMWF-Globalmodell (9 km). 10 Tage, danach Fallback auf best_match. Für die meisten Fälle ist ECMWF Seamless besser.</span>
              )}
            </div>
          </div>
        </div>
        {['icon_seamless', 'meteoswiss_seamless', 'ecmwf_seamless'].includes(formData.wetter_modell) && (
          <div className="mt-3">
            <Alert type="success">
              Seamless-Modelle kaskadieren intern bei Open-Meteo automatisch zwischen Hoch- und Grobauflösung — für die beste Prognosequalität über den gesamten Vorhersagezeitraum. Die Herkunft der Daten wird in der Kurzfrist-Ansicht pro Tag angezeigt.
            </Alert>
          </div>
        )}
        {['meteoswiss_icon_ch2', 'icon_d2', 'icon_eu', 'ecmwf_ifs04'].includes(formData.wetter_modell) && (
          <div className="mt-3">
            <Alert type="warning">
              Einzelmodell: nach Ablauf des Modell-Horizonts wird automatisch auf best_match zurückgefallen. Für die meisten Standorte ist das entsprechende Seamless-Modell die bessere Wahl.
            </Alert>
          </div>
        )}

        {/* PV-Prognose-Quelle */}
        <div className="mt-4">
          <Select
            label="PV-Prognose-Quelle für diese Anlage"
            name="prognose_quelle"
            value={formData.prognose_quelle}
            onChange={handleChange}
            options={prognoseQuelleOptionen}
            hint={prognoseQuelleHinweis(formData.prognose_quelle, haVerbunden)}
          />
        </div>
      </FormSection>

      {/* ── Erweitert: Wetterdaten-Provider (Verfügbarkeit) ── */}
      <FormSection variant="erweitert" title="Wetterdaten-Provider">
        {providerListe ? (
          <div className="space-y-4">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Der Wetter-Provider bestimmt die Quelle für Globalstrahlungsdaten bei der Ist-Erfassung
              und der Kurzfrist-Prognose. Die Auswahl erfolgt oben unter „Steuerungen".
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Aktueller Provider</p>
                <p className="text-lg font-semibold text-gray-900 dark:text-white">
                  {providerListe.aktueller_provider === 'auto' ? 'Automatisch' :
                   providerListe.aktueller_provider === 'brightsky' ? 'Bright Sky (DWD)' :
                   providerListe.aktueller_provider === 'open-meteo' ? 'Open-Meteo' :
                   providerListe.aktueller_provider === 'open-meteo-solar' ? 'Open-Meteo Solar (GTI)' :
                   providerListe.aktueller_provider}
                </p>
              </div>
              <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Standort</p>
                <p className="text-lg font-semibold text-gray-900 dark:text-white">
                  {providerListe.standort.land || 'Unbekannt'}
                  {providerListe.standort.in_deutschland && ' (DWD verfügbar)'}
                </p>
              </div>
            </div>
            <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Verfügbare Provider</h4>
              <div className="grid gap-2">
                {providerListe.provider.map(p => (
                  <div
                    key={p.id}
                    className={`flex items-center justify-between p-3 rounded-lg border ${
                      p.verfuegbar
                        ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20'
                        : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 opacity-60'
                    }`}
                  >
                    <div>
                      <p className={`font-medium ${p.verfuegbar ? 'text-green-700 dark:text-green-300' : 'text-gray-500 dark:text-gray-400'}`}>
                        {p.name}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{p.beschreibung}</p>
                    </div>
                    <div className="text-sm">
                      {p.verfuegbar ? (
                        <span className="text-green-600 dark:text-green-400">✓ Verfügbar</span>
                      ) : (
                        <span className="text-gray-400 dark:text-gray-500">Nicht verfügbar</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <Alert type="warning">
            Bitte zuerst den Standort (Koordinaten) eintragen, um die verfügbaren Provider zu sehen.
          </Alert>
        )}
      </FormSection>

      {/* ── Erweitert: Versorger & Zähler ── */}
      <FormSection variant="erweitert" title="Versorger & Zähler">
        <VersorgerSection value={versorgerDaten} onChange={setVersorgerDaten} />
      </FormSection>

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button type="submit" loading={loading}>
          {anlage ? 'Speichern' : 'Anlage erstellen'}
        </Button>
      </div>
    </form>
  )
}
