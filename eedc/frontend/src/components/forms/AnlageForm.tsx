import { useState, useEffect, FormEvent } from 'react'
import { Info, ExternalLink, Cloud, Sun, Receipt, Mountain, Users, Zap } from 'lucide-react'
import { Button, Input, Alert } from '../ui'
import VersorgerSection from './VersorgerSection'
import { wetterApi, type WetterProvider, type WetterProviderOption } from '../../api/wetter'
import type { Anlage, AnlageCreate, VersorgerDaten } from '../../types'

interface AnlageFormProps {
  anlage?: Anlage | null
  onSubmit: (data: AnlageCreate) => Promise<void>
  onCancel: () => void
}

export default function AnlageForm({ anlage, onSubmit, onCancel }: AnlageFormProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
    wetter_provider: (anlage as any)?.wetter_provider || 'auto',
    wetter_modell: anlage?.wetter_modell || 'auto',
    steuerliche_behandlung: anlage?.steuerliche_behandlung || 'keine_ust',
    ust_satz_prozent: anlage?.ust_satz_prozent?.toString() || '',
    community_auto_share: anlage?.community_auto_share ?? false,
    netz_puffer_w: anlage?.netz_puffer_w?.toString() || '100',
  })

  // Track if user manually changed USt-Satz
  const [ustManuell, setUstManuell] = useState(false)

  const [versorgerDaten, setVersorgerDaten] = useState<VersorgerDaten>(
    anlage?.versorger_daten || {}
  )

  const [wetterProviderOptions, setWetterProviderOptions] = useState<WetterProviderOption[]>([])
  const [loadingProvider, setLoadingProvider] = useState(false)

  // Wetter-Provider laden wenn Anlage existiert und Koordinaten hat
  useEffect(() => {
    if (anlage?.id && anlage.latitude && anlage.longitude) {
      setLoadingProvider(true)
      wetterApi.getProvider(anlage.id)
        .then(data => setWetterProviderOptions(data.provider))
        .catch(() => {})
        .finally(() => setLoadingProvider(false))
    }
  }, [anlage?.id, anlage?.latitude, anlage?.longitude])

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

    if (!formData.anlagenname.trim()) {
      setError('Bitte einen Namen eingeben')
      return
    }

    if (!formData.leistung_kwp || parseFloat(formData.leistung_kwp) <= 0) {
      setError('Bitte eine gültige Leistung eingeben')
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
        versorger_daten: Object.keys(versorgerDaten).length > 0 ? versorgerDaten : undefined,
        wetter_provider: formData.wetter_provider as WetterProvider,
        wetter_modell: formData.wetter_modell,
        steuerliche_behandlung: formData.steuerliche_behandlung || 'keine_ust',
        ust_satz_prozent: formData.ust_satz_prozent ? parseFloat(formData.ust_satz_prozent) : undefined,
        community_auto_share: formData.community_auto_share,
        netz_puffer_w: formData.netz_puffer_w ? parseInt(formData.netz_puffer_w) : 100,
      } as AnlageCreate)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && <Alert type="error">{error}</Alert>}

      {/* Basis-Daten */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Basis-Daten</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Anlagenname"
            name="anlagenname"
            value={formData.anlagenname}
            onChange={handleChange}
            placeholder="z.B. Meine PV-Anlage"
            required
          />
          <Input
            label="Leistung (kWp)"
            name="leistung_kwp"
            type="number"
            step="0.01"
            min="0.1"
            value={formData.leistung_kwp}
            onChange={handleChange}
            placeholder="z.B. 10.5"
            required
          />
          <Input
            label="Installationsdatum"
            name="installationsdatum"
            type="date"
            min="2000-01-01"
            max="2099-12-31"
            value={formData.installationsdatum}
            onChange={handleChange}
          />
        </div>
      </div>

      {/* Hinweis zu technischen Daten */}
      <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg flex gap-2">
        <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-blue-700 dark:text-blue-300">
          <p className="font-medium mb-1">Ausrichtung & Neigung</p>
          <p>
            Diese Werte werden pro <strong>PV-Modul</strong> unter <strong>Einstellungen → Investitionen</strong> gepflegt.
            So können auch Anlagen mit mehreren Dachflächen korrekt abgebildet werden.
          </p>
        </div>
      </div>

      {/* Standort */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Standort</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label htmlFor="standort_land" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Land</label>
            <select
              id="standort_land"
              name="standort_land"
              value={formData.standort_land}
              onChange={handleChange}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="DE">Deutschland</option>
              <option value="AT">Österreich</option>
              <option value="CH">Schweiz</option>
              <option value="IT">Italien</option>
            </select>
          </div>
          <Input
            label="PLZ"
            name="standort_plz"
            value={formData.standort_plz}
            onChange={handleChange}
            placeholder={formData.standort_land === 'CH' ? 'z.B. 1234' : 'z.B. 12345'}
          />
          <Input
            label="Ort"
            name="standort_ort"
            value={formData.standort_ort}
            onChange={handleChange}
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
      </div>

      {/* Geokoordinaten */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">
          Geokoordinaten
          <span className="text-xs font-normal text-gray-500 ml-2">(für PVGIS-Prognose)</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Breitengrad (Latitude)"
            name="latitude"
            type="number"
            step="0.000001"
            value={formData.latitude}
            onChange={handleChange}
            placeholder="z.B. 52.520008"
            hint="Nördliche Breite (positiv)"
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
      </div>

      {/* Erweiterte Stammdaten */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">
          Erweiterte Stammdaten
        </h3>
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
      </div>

      {/* Steuerliche Behandlung */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-2">
          <Receipt className="w-4 h-4 text-amber-500" />
          Steuerliche Behandlung
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="w-full">
            <label
              htmlFor="steuerliche_behandlung"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              USt-Behandlung
            </label>
            <select
              id="steuerliche_behandlung"
              name="steuerliche_behandlung"
              title="USt-Behandlung"
              value={formData.steuerliche_behandlung}
              onChange={handleChange}
              className="w-full px-3 py-2 rounded-lg border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent border-gray-300 dark:border-gray-600"
            >
              <option value="keine_ust">Keine USt-Auswirkung (Standard)</option>
              <option value="regelbesteuerung">Regelbesteuerung (USt auf Eigenverbrauch)</option>
            </select>
          </div>
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
              hint={`Standard: ${UST_DEFAULTS[formData.standort_land] || '19'}% (${formData.standort_land || 'DE'})`}
            />
          )}
        </div>
        <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg flex gap-2">
          <Info className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-amber-700 dark:text-amber-300">
            {formData.steuerliche_behandlung === 'regelbesteuerung' ? (
              <p>
                Bei <strong>Regelbesteuerung</strong> wird USt auf den Eigenverbrauch (unentgeltliche Wertabgabe)
                als Kostenfaktor in den Finanzergebnissen berechnet. Die Bemessungsgrundlage basiert auf den
                Selbstkosten (Abschreibung + Betriebskosten / Jahresertrag).
              </p>
            ) : (
              <p>
                <strong>Keine USt</strong> gilt fur PV-Anlagen ab 2023 mit Nullsteuersatz (&le;30 kWp),
                Kleinunternehmer (&sect;19 UStG) oder wenn Sie keine steuerliche Erfassung wunschen.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Wetterdaten-Quelle */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-2">
          <Cloud className="w-4 h-4 text-blue-500" />
          Wetterdaten-Quelle
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="w-full">
            <label
              htmlFor="wetter_provider"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Bevorzugter Provider
            </label>
            <select
              id="wetter_provider"
              name="wetter_provider"
              value={formData.wetter_provider}
              onChange={handleChange}
              disabled={loadingProvider}
              className="w-full px-3 py-2 rounded-lg border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:bg-gray-100 dark:disabled:bg-gray-700 disabled:cursor-not-allowed border-gray-300 dark:border-gray-600"
            >
              {wetterProviderOptions.length > 0 ? (
                wetterProviderOptions.map(p => (
                  <option
                    key={p.id}
                    value={p.id}
                    disabled={!p.verfuegbar}
                  >
                    {p.name}
                    {p.empfohlen ? ' (empfohlen)' : ''}
                    {!p.verfuegbar ? ' (nicht verfügbar)' : ''}
                  </option>
                ))
              ) : (
                <>
                  <option value="auto">Automatisch (empfohlen)</option>
                  <option value="open-meteo">Open-Meteo</option>
                  <option value="brightsky">Bright Sky (DWD)</option>
                  <option value="open-meteo-solar">Open-Meteo Solar</option>
                </>
              )}
            </select>
          </div>
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
        {!anlage?.latitude && !anlage?.longitude && (
          <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg flex gap-2">
            <Sun className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700 dark:text-amber-300">
              Bitte zuerst Geokoordinaten eintragen, um die verfügbaren Provider zu sehen.
            </p>
          </div>
        )}
      </div>

      {/* Prognose-Wettermodell */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-2">
          <Mountain className="w-4 h-4 text-emerald-500" />
          Prognose-Wettermodell
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="w-full">
            <label
              htmlFor="wetter_modell"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Modell für Solar-Prognose
            </label>
            <select
              id="wetter_modell"
              name="wetter_modell"
              value={formData.wetter_modell}
              onChange={handleChange}
              className="w-full px-3 py-2 rounded-lg border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent border-gray-300 dark:border-gray-600"
            >
              <option value="auto">Automatisch (best_match)</option>
              <optgroup label="── Seamless (empfohlen) ──">
                <option value="icon_seamless">DWD ICON Seamless — Deutschland/Europa</option>
                <option value="meteoswiss_seamless">MeteoSwiss Seamless — Alpenraum</option>
                <option value="ecmwf_seamless">ECMWF Seamless — Global (15 Tage)</option>
              </optgroup>
              <optgroup label="── Einzelmodelle ──">
                <option value="meteoswiss_icon_ch2">MeteoSwiss ICON-CH2 (2.1 km, 5 Tage)</option>
                <option value="icon_d2">DWD ICON-D2 (2.2 km, 2 Tage)</option>
                <option value="icon_eu">DWD ICON-EU (7 km, 5 Tage)</option>
                <option value="ecmwf_ifs04">ECMWF IFS (9 km, 10 Tage)</option>
              </optgroup>
            </select>
          </div>
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
          <div className="p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg flex gap-2">
            <Info className="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-emerald-700 dark:text-emerald-300">
              Seamless-Modelle kaskadieren intern bei Open-Meteo automatisch zwischen Hoch- und Grobauflösung — für die beste Prognosequalität über den gesamten Vorhersagezeitraum. Die Herkunft der Daten wird in der Kurzfrist-Ansicht pro Tag angezeigt.
            </p>
          </div>
        )}
        {['meteoswiss_icon_ch2', 'icon_d2', 'icon_eu', 'ecmwf_ifs04'].includes(formData.wetter_modell) && (
          <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg flex gap-2">
            <Info className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700 dark:text-amber-300">
              Einzelmodell: nach Ablauf des Modell-Horizonts wird automatisch auf best_match zurückgefallen. Für die meisten Standorte ist das entsprechende Seamless-Modell die bessere Wahl.
            </p>
          </div>
        )}
      </div>

      {/* Energiefluss-Einstellungen */}
      <div className="space-y-3">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Zap className="w-5 h-5 text-green-500" />
          Energiefluss
        </h3>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1" htmlFor="netz_puffer_w">
            Netz-Puffer (Watt)
          </label>
          <div className="flex items-center gap-3">
            <Input
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
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Unterhalb dieses Werts wird das Netz als Balance (grün) angezeigt. Standard: 100 W
            </span>
          </div>
        </div>
      </div>

      {/* Community Auto-Share */}
      <div className="space-y-3">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Users className="w-5 h-5 text-blue-500" />
          Community
        </h3>
        <label className="flex items-start gap-3 cursor-pointer p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
          <input
            type="checkbox"
            checked={formData.community_auto_share}
            onChange={(e) => setFormData(prev => ({ ...prev, community_auto_share: e.target.checked }))}
            className="mt-1 h-4 w-4 text-orange-500 border-gray-300 dark:border-gray-600 rounded focus:ring-orange-500"
          />
          <div>
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
              Automatisch teilen nach Monatsabschluss
            </span>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Anonymisierte Monatsdaten werden nach jedem Abschluss automatisch an den Community-Benchmark gesendet.
            </p>
          </div>
        </label>
      </div>

      {/* Versorger & Zähler */}
      <VersorgerSection value={versorgerDaten} onChange={setVersorgerDaten} />

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
