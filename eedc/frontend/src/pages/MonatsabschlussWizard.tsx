/**
 * MonatsabschlussWizard - Geführte monatliche Dateneingabe
 *
 * Features:
 * - Vorschläge aus verschiedenen Quellen
 * - Plausibilitätsprüfungen
 * - Integration mit Sensor-Mapping
 */

import { useState, useEffect, useMemo, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ChevronLeft,
  ChevronRight,
  Save,
  CheckCircle,
  Info,
  Calendar,
  Zap,
  Loader2,
  FileText,
  Database,
  Cloud,
  Cpu,
} from 'lucide-react'
import { anlagenApi, monatsabschlussApi, haStatisticsApi, wetterApi } from '../api'
import { connectorApi } from '../api/connector'
import type {
  MonatsabschlussResponse,
  InvestitionStatus,
  MonatsabschlussInput,
  FeldWert,
} from '../api'
import Alert from '../components/ui/Alert'
import Button from '../components/ui/Button'
import Stepper from '../components/ui/Stepper'
import { useWizardHost, type MonatsabschlussPayload } from '../v4/wizardHost'
import { useHAAvailable } from '../hooks/useHAAvailable'
import { MONAT_NAMEN } from '../lib/constants'
import {
  BasisStep,
  OptionaleStep,
  InvestitionStep,
  SummaryStep,
  TYP_ICONS,
  getTypLabel,
  getDatenquelleLabel,
} from '../components/monatsabschluss'
import type { WizardState } from '../components/monatsabschluss'

export default function MonatsabschlussWizard() {
  const params = useParams<{
    anlageId?: string
    jahr?: string
    monat?: string
  }>()
  const navigate = useNavigate()
  const haAvailable = useHAAvailable()
  // E2: im Overlay kommen die Aufruf-Parameter über den Payload-Kanal des
  // Wizard-Hosts (aus Monatsdaten-Zeile/Button/Fusszeile — Muster wie die
  // V3-URL-Params); auf der V3-Route weiter aus useParams.
  const wizardHost = useWizardHost()
  const payload = wizardHost.imOverlay
    ? (wizardHost.payload as MonatsabschlussPayload | undefined)
    : undefined
  const anlageId = payload?.anlageId != null ? String(payload.anlageId) : params.anlageId
  const jahr = payload?.jahr != null ? String(payload.jahr) : params.jahr
  const monat = payload?.monat != null ? String(payload.monat) : params.monat
  // Overlay ohne anlageId im Payload: erste Anlage lokal auflösen (statt navigate).
  const [fallbackAnlageId, setFallbackAnlageId] = useState<string | null>(null)
  const effektiveAnlageId = anlageId ?? fallbackAnlageId ?? undefined

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadingHA, setLoadingHA] = useState(false)
  const [loadingConnector, setLoadingConnector] = useState(false)
  const [loadingCloud, setLoadingCloud] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [haInfo, setHaInfo] = useState<string | null>(null)
  const [connectorInfo, setConnectorInfo] = useState<string | null>(null)
  const [cloudInfo, setCloudInfo] = useState<string | null>(null)

  const [anlageName, setAnlageName] = useState('')
  const [data, setData] = useState<MonatsabschlussResponse | null>(null)
  const [currentStep, setCurrentStep] = useState(0)
  const [values, setValues] = useState<WizardState>({
    basis: {},
    optionale: {},
    investitionen: {},
    sonstigePositionen: {},
  })

  // W5-Dirty-Referenz: Snapshot der geladenen Werte — Abweichung = offene Eingaben.
  const geladenRef = useRef('')
  useEffect(() => {
    wizardHost.setzeBlocker(
      success === null && !!geladenRef.current && JSON.stringify(values) !== geladenRef.current,
    )
    return () => wizardHost.setzeBlocker(false)
  }, [values, success, wizardHost])

  // Jahr und Monat aus URL oder automatisch ermitteln
  // WICHTIG: getMonth() gibt 0-11 zurück, aber API erwartet 1-12
  const [selectedJahr, setSelectedJahr] = useState<number>(
    jahr ? parseInt(jahr) : new Date().getFullYear()
  )
  const [selectedMonat, setSelectedMonat] = useState<number>(
    monat ? parseInt(monat) : new Date().getMonth() + 1
  )

  // Daten laden
  useEffect(() => {
    const loadData = async () => {
      if (!effektiveAnlageId) {
        // Erste Anlage laden — Overlay: lokal auflösen; V3-Route: URL vervollständigen.
        try {
          const anlagen = await anlagenApi.list()
          if (anlagen.length > 0) {
            if (wizardHost.imOverlay) setFallbackAnlageId(String(anlagen[0].id))
            else navigate(`/monatsabschluss/${anlagen[0].id}`)
          } else {
            setError('Keine Anlage gefunden')
          }
        } catch {
          setError('Fehler beim Laden der Anlagen')
        }
        setLoading(false)
        return
      }

      setLoading(true)
      setError(null)

      try {
        // Wenn kein Jahr/Monat in URL, nächsten unvollständigen Monat finden
        let targetJahr = selectedJahr
        let targetMonat = selectedMonat

        if (!jahr || !monat) {
          const naechster = await monatsabschlussApi.getNaechsterMonat(parseInt(effektiveAnlageId))
          if (naechster) {
            targetJahr = naechster.jahr
            targetMonat = naechster.monat
            setSelectedJahr(targetJahr)
            setSelectedMonat(targetMonat)
          }
        }

        const response = await monatsabschlussApi.getStatus(
          parseInt(effektiveAnlageId),
          targetJahr,
          targetMonat
        )
        setData(response)
        setAnlageName(response.anlage_name)

        // Werte aus aktuellen Daten initialisieren
        const basisValues: Record<string, number | null> = {}
        for (const feld of response.basis_felder) {
          basisValues[feld.feld] = feld.aktueller_wert
        }

        // Optionale Felder (Sonderkosten, Notizen)
        const optionaleValues: Record<string, number | string | null> = {}
        for (const feld of response.optionale_felder || []) {
          if (feld.typ === 'text') {
            optionaleValues[feld.feld] = feld.aktueller_text
          } else {
            optionaleValues[feld.feld] = feld.aktueller_wert
          }
        }

        const invValues: Record<number, Record<string, number | null>> = {}
        const invSonstigePos: Record<number, import('../api').SonstigePosition[]> = {}
        for (const inv of response.investitionen) {
          invValues[inv.id] = {}
          for (const feld of inv.felder) {
            invValues[inv.id][feld.feld] = feld.aktueller_wert
          }
          invSonstigePos[inv.id] = inv.sonstige_positionen || []
        }

        const geladeneWerte: WizardState = {
          basis: basisValues,
          optionale: optionaleValues,
          investitionen: invValues,
          sonstigePositionen: invSonstigePos,
        }
        setValues(geladeneWerte)
        geladenRef.current = JSON.stringify(geladeneWerte)

        // Wetterdaten automatisch im Hintergrund holen, falls noch nicht vorhanden.
        // Pro Feld nur dann übernehmen, wenn der Tester den Wert noch nicht selbst
        // gepflegt hat — sonst überschreiben wir manuelle Korrekturen still.
        const fehltWetter =
          basisValues.globalstrahlung_kwh_m2 == null ||
          basisValues.sonnenstunden == null ||
          basisValues.durchschnittstemperatur == null
        if (fehltWetter) {
          wetterApi.getMonatsdaten(parseInt(effektiveAnlageId!), targetJahr, targetMonat)
            .then(wetter => {
              setValues(prev => {
                const next = {
                  ...prev,
                  basis: {
                    ...prev.basis,
                    globalstrahlung_kwh_m2:
                      prev.basis.globalstrahlung_kwh_m2 ?? wetter.globalstrahlung_kwh_m2,
                    sonnenstunden: prev.basis.sonnenstunden ?? wetter.sonnenstunden,
                    durchschnittstemperatur:
                      prev.basis.durchschnittstemperatur ?? wetter.durchschnittstemperatur_c ?? null,
                  },
                }
                // Auto-Wetterwerte = keine Nutzer-Eingabe → W5-Dirty-Referenz mitziehen.
                geladenRef.current = JSON.stringify(next)
                return next
              })
            })
            .catch(() => { /* optional, kein Fehler anzeigen */ })
        }
      } catch (e) {
        setError('Fehler beim Laden der Monatsdaten')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [effektiveAnlageId, jahr, monat, selectedJahr, selectedMonat, navigate, wizardHost.imOverlay])

  // Step-Typ für TypeScript
  interface WizardStep {
    id: string
    title: string
    icon: React.ReactNode
  }

  // Steps dynamisch generieren
  const steps = useMemo((): WizardStep[] => {
    if (!data) return []

    const s: WizardStep[] = [
      { id: 'basis', title: 'Zählerdaten', icon: <Zap className="w-4 h-4" /> }
    ]

    // Pro Investitionstyp einen Step
    const typGroups: Record<string, InvestitionStatus[]> = {}
    for (const inv of data.investitionen) {
      if (!typGroups[inv.typ]) typGroups[inv.typ] = []
      typGroups[inv.typ].push(inv)
    }

    for (const typ of Object.keys(typGroups)) {
      // Bei genau einer 'sonstiges'-Investition die Bezeichnung als Stepper-Titel
      // zeigen — sonst kollidiert das generische 'Sonstiges' optisch mit dem
      // Stepper-Titel des typ-übergreifenden 'Allgemein'-Steps weiter hinten.
      const invs = typGroups[typ]
      const title =
        typ === 'sonstiges' && invs.length === 1 && invs[0].bezeichnung
          ? invs[0].bezeichnung
          : getTypLabel(typ)
      s.push({
        id: typ,
        title,
        icon: TYP_ICONS[typ] || <Zap className="w-4 h-4" />,
      })
    }

    // Typ-übergreifende Felder (Sonderkosten, Notizen) — eigener Step,
    // damit er nicht mit dem 'sonstiges'-Investitionstyp kollidiert.
    if (data.optionale_felder && data.optionale_felder.length > 0) {
      s.push({ id: 'optionale', title: 'Allgemein', icon: <FileText className="w-4 h-4" /> })
    }

    s.push({ id: 'summary', title: 'Zusammenfassung', icon: <CheckCircle className="w-4 h-4" /> })

    return s
  }, [data])

  const handleValueChange = (
    feld: string,
    wert: number | null,
    investitionId?: number
  ) => {
    if (investitionId) {
      setValues(prev => ({
        ...prev,
        investitionen: {
          ...prev.investitionen,
          [investitionId]: {
            ...prev.investitionen[investitionId],
            [feld]: wert,
          },
        },
      }))
    } else {
      setValues(prev => ({
        ...prev,
        basis: {
          ...prev.basis,
          [feld]: wert,
        },
      }))
    }
  }

  const handleOptionalChange = (feld: string, wert: number | string | null) => {
    setValues(prev => ({
      ...prev,
      optionale: {
        ...prev.optionale,
        [feld]: wert,
      },
    }))
  }

  // HA-Werte für diesen Monat laden
  const handleLoadHAValues = async () => {
    if (!effektiveAnlageId) return

    setLoadingHA(true)
    setError(null)
    setHaInfo(null)

    try {
      // Prüfen ob HA verfügbar
      const status = await haStatisticsApi.getStatus()
      if (!status.verfuegbar) {
        setError('Home Assistant Datenbank nicht verfügbar')
        return
      }

      // Monatswerte laden
      const monatswerte = await haStatisticsApi.getMonatswerte(
        parseInt(effektiveAnlageId),
        selectedJahr,
        selectedMonat
      )

      // Werte in State übernehmen
      let geladenCount = 0

      // Basis-Felder
      const newBasis = { ...values.basis }
      for (const feld of monatswerte.basis) {
        if (feld.wert !== null && feld.wert !== undefined) {
          newBasis[feld.feld] = feld.wert
          geladenCount++
        }
      }

      // Investitionen
      const newInv = { ...values.investitionen }
      for (const inv of monatswerte.investitionen) {
        if (!newInv[inv.investition_id]) {
          newInv[inv.investition_id] = {}
        }
        for (const feld of inv.felder) {
          if (feld.wert !== null && feld.wert !== undefined) {
            newInv[inv.investition_id][feld.feld] = feld.wert
            geladenCount++
          }
        }
      }

      setValues(prev => ({
        ...prev,
        basis: newBasis,
        investitionen: newInv,
      }))

      setHaInfo(`${geladenCount} Werte aus HA-Statistik geladen`)
    } catch (e) {
      setError('Fehler beim Laden der HA-Werte. Ist das Sensor-Mapping konfiguriert?')
    } finally {
      setLoadingHA(false)
    }
  }

  // Connector-Werte für diesen Monat laden
  const handleLoadConnectorValues = async () => {
    if (!effektiveAnlageId) return

    setLoadingConnector(true)
    setError(null)
    setConnectorInfo(null)

    try {
      const monatswerte = await connectorApi.getMonatswerte(
        parseInt(effektiveAnlageId),
        selectedJahr,
        selectedMonat
      )

      let geladenCount = 0

      // Basis-Felder
      const newBasis = { ...values.basis }
      for (const feld of monatswerte.basis) {
        if (feld.wert !== null && feld.wert !== undefined) {
          newBasis[feld.feld] = feld.wert
          geladenCount++
        }
      }

      // Investitionen
      const newInv = { ...values.investitionen }
      for (const inv of monatswerte.investitionen) {
        if (!newInv[inv.investition_id]) {
          newInv[inv.investition_id] = {}
        }
        for (const feld of inv.felder) {
          if (feld.wert !== null && feld.wert !== undefined) {
            newInv[inv.investition_id][feld.feld] = feld.wert
            geladenCount++
          }
        }
      }

      setValues(prev => ({
        ...prev,
        basis: newBasis,
        investitionen: newInv,
      }))

      setConnectorInfo(`${geladenCount} Werte vom Wechselrichter geladen`)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Fehler beim Laden der Connector-Werte'
      setError(msg)
    } finally {
      setLoadingConnector(false)
    }
  }

  // Cloud-Daten für diesen Monat laden
  const handleLoadCloudValues = async () => {
    if (!effektiveAnlageId) return

    setLoadingCloud(true)
    setError(null)
    setCloudInfo(null)

    try {
      const monatswerte = await monatsabschlussApi.cloudFetch(
        parseInt(effektiveAnlageId),
        selectedJahr,
        selectedMonat
      )

      let geladenCount = 0

      const newBasis = { ...values.basis }
      for (const feld of monatswerte.basis) {
        if (feld.wert !== null && feld.wert !== undefined) {
          newBasis[feld.feld] = feld.wert
          geladenCount++
        }
      }

      const newInv = { ...values.investitionen }
      for (const inv of monatswerte.investitionen) {
        if (!newInv[inv.investition_id]) {
          newInv[inv.investition_id] = {}
        }
        for (const feld of inv.felder) {
          if (feld.wert !== null && feld.wert !== undefined) {
            newInv[inv.investition_id][feld.feld] = feld.wert
            geladenCount++
          }
        }
      }

      setValues(prev => ({
        ...prev,
        basis: newBasis,
        investitionen: newInv,
      }))

      setCloudInfo(`${geladenCount} Werte aus Cloud-API geladen`)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Fehler beim Laden der Cloud-Werte'
      setError(msg)
    } finally {
      setLoadingCloud(false)
    }
  }

  const handleSave = async () => {
    if (!data || !effektiveAnlageId) return

    setSaving(true)
    setError(null)
    setSuccess(null)

    try {
      const input: MonatsabschlussInput = {
        investitionen: [],
      }

      // Basis-Felder generisch aus API-Response übernehmen
      for (const feld of data.basis_felder) {
        if (feld.typ === 'number') {
          const wert = values.basis[feld.feld]
          if (wert !== null && wert !== undefined) {
            input[feld.feld] = wert
          }
        }
      }

      // Optionale Felder
      if (typeof values.optionale.sonderkosten_euro === 'number') {
        input.sonderkosten_euro = values.optionale.sonderkosten_euro
      }
      if (typeof values.optionale.sonderkosten_beschreibung === 'string') {
        input.sonderkosten_beschreibung = values.optionale.sonderkosten_beschreibung
      }
      if (typeof values.optionale.notizen === 'string') {
        input.notizen = values.optionale.notizen
      }

      // Investitionen zusammenstellen
      for (const inv of data.investitionen) {
        const felder: FeldWert[] = []
        const invValues = values.investitionen[inv.id] || {}

        for (const [feld, wert] of Object.entries(invValues)) {
          if (wert !== null && wert !== undefined) {
            felder.push({ feld, wert })
          }
        }

        const positionen = values.sonstigePositionen[inv.id] || []
        // 0-€-Positionen mit Bezeichnung sind legitim (Platzhalter, „Reparatur
        // 0 € unter Garantie", noch nicht bewilligte THG-Quote, etc.). Vor
        // v3.32.1 hat das `> 0` solche Einträge stillschweigend verworfen —
        // rilmor-mhrs auf #286 v3.32.0 musste deshalb 0,01 € als Workaround
        // eintragen, weil 0 € einfach „nichts passierte". Dieselbe Regel
        // gilt im Backend, Helper `ist_gueltige_position`.
        const gueltigePositionen = positionen.filter(p => p.bezeichnung.trim())
        // Hatte die Investition beim Laden Positionen, sind jetzt aber keine
        // gültigen mehr da, muss eine leere Liste raus — sonst bleibt die alte
        // in der DB stehen und das Löschen verpufft (#286). `null` heißt
        // weiterhin „Positionen nicht anfassen".
        const hattePositionen = (inv.sonstige_positionen || []).length > 0
        const positionenRelevant = gueltigePositionen.length > 0 || hattePositionen

        if (felder.length > 0 || positionenRelevant) {
          input.investitionen.push({
            investition_id: inv.id,
            felder,
            sonstige_positionen: positionenRelevant ? gueltigePositionen : null,
          })
        }
      }

      const result = await monatsabschlussApi.save(
        parseInt(effektiveAnlageId),
        selectedJahr,
        selectedMonat,
        input
      )

      if (result.success) {
        // Schreibschutz-Warnungen sichtbar machen (FrodoVDR #251 Folge):
        // bisher gingen Provenance-Rejects still durch; jetzt zeigt Backend
        // sie als warnungen[] mit typ="schreibschutz_aktiv" zurück.
        const blockiert = (result.warnungen || []).filter(
          (w: { typ?: string }) => w.typ === 'schreibschutz_aktiv',
        )
        if (blockiert.length > 0) {
          const meldungen = blockiert
            .map((w: { meldung: string }) => `• ${w.meldung}`)
            .join('\n')
          setError(
            `Einige Felder wurden nicht übernommen:\n${meldungen}\n\n` +
            'Hinweis: Diese Felder enthalten bereits einen Wert aus einer höherprioren Quelle. ' +
            'Die vom Resolver vorgesehene Rangfolge überschreibt einen solchen Wert nicht durch ' +
            'eine manuelle Eingabe.',
          )
          // Bei Schreibschutz nicht weiter-navigieren — die betroffenen Felder
          // sind durch die Quellen-Rangfolge bewusst geschützt.
        } else {
          setSuccess(result.message)
          // Community-Nudge: Anlage laden und prüfen ob Auto-Share aktiv
          try {
            const anlageObj = await anlagenApi.get(parseInt(effektiveAnlageId!))
            if (!anlageObj.community_hash && !anlageObj.community_auto_share) {
              setSuccess(result.message + ' — Tipp: Teile deine Daten anonym mit der Community!')
            } else if (anlageObj.community_auto_share) {
              setSuccess(result.message + ' — Daten werden automatisch an die Community gesendet.')
            }
          } catch { /* ignore */ }
          // Nach 3s Terminal-Schluss (etwas mehr Zeit für Community-Hinweis):
          // Overlay → Host schließen; V3-Route → Monatsdaten-Seite.
          setTimeout(() => {
            if (wizardHost.imOverlay) wizardHost.schliessen()
            else navigate('/einstellungen/monatsdaten')
          }, 3000)
        }
      } else {
        setError('Speichern fehlgeschlagen')
      }
    } catch (e) {
      const detail = e instanceof Error ? e.message : String(e)
      setError(`Fehler beim Speichern: ${detail}`)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <Alert type="error">{error}</Alert>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <Alert type="info">Keine Daten verfügbar</Alert>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 mb-2">
          <Calendar className="w-4 h-4" />
          <span>{anlageName}</span>
        </div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Monatsabschluss {MONAT_NAMEN[selectedMonat]} {selectedJahr}
        </h1>
        <Button
          type="button" variant="ghost" size="sm"
          className="mt-1 text-xs text-gray-400 dark:text-gray-500"
          onClick={() => {
            if (wizardHost.imOverlay) {
              wizardHost.schliessen()
              navigate('/v4/einstellungen/daten')
            } else {
              navigate('/monatsdaten')
            }
          }}
        >
          Anderen Monat bearbeiten → Monatsdaten-Tabelle
        </Button>

        {/* Datenquellen-Status & Aktionen */}
        <div className="mt-4 space-y-3">
          {/* Quellen-Status-Chips */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 mr-1">Quellen:</span>

            {haAvailable && (
              <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs ${
                data.ha_mapping_konfiguriert
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                  : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
              }`}>
                <Database className="w-3 h-3" />
                HA-Statistik
                {data.ha_mapping_konfiguriert && <CheckCircle className="w-3 h-3" />}
              </span>
            )}

            <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs ${
              data.connector_konfiguriert
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}>
              <Cpu className="w-3 h-3" />
              Connector
              {data.connector_konfiguriert && <CheckCircle className="w-3 h-3" />}
            </span>

            <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs ${
              data.cloud_import_konfiguriert
                ? 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}>
              <Cloud className="w-3 h-3" />
              Cloud
              {data.cloud_import_konfiguriert && <CheckCircle className="w-3 h-3" />}
            </span>

            {data.mqtt_inbound_konfiguriert && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                <Zap className="w-3 h-3" />
                MQTT Energy
                <CheckCircle className="w-3 h-3" />
              </span>
            )}

            {data.portal_import_vorhanden && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                <FileText className="w-3 h-3" />
                Portal-Import
                <CheckCircle className="w-3 h-3" />
              </span>
            )}
          </div>

          {/* Hinweis wenn keine Quellen konfiguriert */}
          {!data.ha_mapping_konfiguriert && !data.connector_konfiguriert && !data.cloud_import_konfiguriert && !data.mqtt_inbound_konfiguriert && !data.portal_import_vorhanden && (
            <Alert type="info">
              <div className="flex items-center justify-between gap-3">
                <span>
                  Keine Datenquellen konfiguriert. Richten Sie mindestens eine Quelle ein, um Werte automatisch zu laden.
                </span>
                {wizardHost.imOverlay ? (
                  /* I9: im Overlay kein V3-Link — Einrichtungs-Hub im selben Overlay öffnen. */
                  <Button
                    type="button" variant="ghost" size="sm"
                    className="text-primary-600 whitespace-nowrap"
                    onClick={() => wizardHost.oeffneWizard('einrichtung')}
                  >
                    <Cpu className="w-4 h-4 mr-1" />
                    Einrichten
                  </Button>
                ) : (
                  <Link
                    to="/einstellungen/einrichtung"
                    className="flex items-center gap-1 text-primary-600 hover:underline whitespace-nowrap"
                  >
                    <Cpu className="w-4 h-4" />
                    Einrichten
                  </Link>
                )}
              </div>
            </Alert>
          )}

          {/* Lade-Buttons (nur konfigurierte Quellen) */}
          {/* Lade-Aktionen — Button-SoT (secondary; die frühere Quell-Farbcodierung
              blau/grün/violett war lokale Improvisation, die Icons tragen die Quelle). */}
          <div className="flex flex-wrap items-center gap-3">
            {data.ha_mapping_konfiguriert && (
              <Button type="button" variant="secondary" onClick={handleLoadHAValues} disabled={loadingHA} loading={loadingHA}>
                {loadingHA ? 'Lade HA-Werte...' : <><Database className="w-4 h-4 mr-2" />HA-Statistik laden</>}
              </Button>
            )}

            {data.connector_konfiguriert && (
              <Button type="button" variant="secondary" onClick={handleLoadConnectorValues} disabled={loadingConnector} loading={loadingConnector}>
                {loadingConnector ? 'Lade WR-Werte...' : <><Zap className="w-4 h-4 mr-2" />Wechselrichter laden</>}
              </Button>
            )}

            {data.cloud_import_konfiguriert && (
              <Button type="button" variant="secondary" onClick={handleLoadCloudValues} disabled={loadingCloud} loading={loadingCloud}>
                {loadingCloud ? 'Lade Cloud-Werte...' : <><Cloud className="w-4 h-4 mr-2" />Cloud-Daten abrufen</>}
              </Button>
            )}
          </div>

          {/* Status-Meldungen */}
          <div className="flex flex-wrap items-center gap-4">
            {haInfo && <span className="text-sm text-green-600 dark:text-green-400">{haInfo}</span>}
            {connectorInfo && <span className="text-sm text-green-600 dark:text-green-400">{connectorInfo}</span>}
            {cloudInfo && <span className="text-sm text-green-600 dark:text-green-400">{cloudInfo}</span>}
          </div>

          {/* Datenherkunft-Hinweis */}
          {data.datenquelle && data.datenquelle !== 'manual' && data.ist_abgeschlossen && (
            <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
              <Info className="w-3 h-3" />
              Vorhandene Werte stammen aus: {getDatenquelleLabel(data.datenquelle)}
            </div>
          )}
        </div>
      </div>

      {/* Step Navigation — Stepper-SoT (Teil D, W1) statt handgerolltem Balken;
          die dynamische Step-Liste (pro Investitionstyp) bleibt, nur das
          Rendering tauscht (E2). */}
      <div className="mb-8">
        <Stepper
          schritte={steps.map((s) => ({ titel: s.title }))}
          aktuell={currentStep}
          onSchrittKlick={setCurrentStep}
        />
      </div>

      {/* Alerts */}
      {error && <Alert type="error" className="mb-6">{error}</Alert>}
      {success && <Alert type="success" className="mb-6">{success}</Alert>}

      {/* Step Content */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-8">
        {currentStep === 0 && (
          <BasisStep
            felder={data.basis_felder}
            values={values.basis}
            onChange={(feld, wert) => handleValueChange(feld, wert)}
          />
        )}

        {currentStep > 0 && currentStep < steps.length - 1 && steps[currentStep].id !== 'optionale' && (
          <InvestitionStep
            typ={steps[currentStep].id}
            investitionen={data.investitionen.filter(i => i.typ === steps[currentStep].id)}
            values={values.investitionen}
            onChange={(invId, feld, wert) => handleValueChange(feld, wert, invId)}
            sonstigePositionen={values.sonstigePositionen}
            onSonstigePositionenChange={(invId, pos) =>
              setValues(prev => ({
                ...prev,
                sonstigePositionen: { ...prev.sonstigePositionen, [invId]: pos },
              }))
            }
          />
        )}

        {steps[currentStep].id === 'optionale' && (
          <OptionaleStep
            felder={data.optionale_felder || []}
            values={values.optionale}
            onChange={handleOptionalChange}
          />
        )}

        {currentStep === steps.length - 1 && (
          <SummaryStep
            data={data}
            values={values}
          />
        )}
      </div>

      {/* Navigation Buttons — Zurück mit Box-Stil (Button variant="secondary"),
          konsistent zum Sensor-Mapping-Wizard (#213 detLAN). */}
      <div className="flex items-center justify-between">
        <Button
          variant="secondary"
          onClick={() => setCurrentStep(s => Math.max(0, s - 1))}
          disabled={currentStep === 0}
        >
          <ChevronLeft className="w-4 h-4 mr-2" />
          Zurück
        </Button>

        {currentStep < steps.length - 1 ? (
          <Button
            type="button"
            onClick={() => setCurrentStep(s => Math.min(steps.length - 1, s + 1))}
          >
            Weiter
            <ChevronRight className="w-4 h-4 ml-2" />
          </Button>
        ) : (
          <Button
            type="button"
            onClick={handleSave}
            disabled={saving}
            loading={saving}
          >
            {saving ? 'Speichern...' : <><Save className="w-4 h-4 mr-2" />Speichern</>}
          </Button>
        )}
      </div>
    </div>
  )
}
