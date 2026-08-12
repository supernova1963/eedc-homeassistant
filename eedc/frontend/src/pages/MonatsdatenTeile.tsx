/**
 * Monatsdaten — geteilte Teile (Spalten-SoT + Tabelle + Formular-Modals + HA-Import
 * + Kraftstoffpreis-Backfill). D14-8-Gate (2026-07-03): die Kraftstoffpreis-
 * Monats-Karte rendert nur in V3 — unter /v4 läuft der Backfill über das
 * Auswahlfeld der EINEN Reparatur-Werkbank (Energieprofil-Pflege).
 *
 * EINE Code-Wahrheit für IST (`pages/Monatsdaten.tsx`, dünner Komposer) und IA-V4
 * (eigene native V4-Seite `v4/MonatsdatenV4.tsx`). Der Aufrufer reicht die bereits
 * aufgelöste `anlageId` (kein interner Anlage-Guard) und – im Mehr-Anlagen-Fall –
 * einen `kopfZusatz` (Anlage-Auswahl) in die Kopfleiste. Zahlen de-DE über `fmtZahl`.
 */
import { useState, useEffect, useMemo, useCallback, type ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Plus, Calendar, Edit, Trash2, Columns, AlertTriangle, Database, Loader2, Fuel, PenLine, ArrowRight } from 'lucide-react'
import { Button, Card, Checkbox, Modal, EmptyState, Alert, Select } from '../components/ui'
import { TableHead, TableBody, TableRow, TableHeader, TableCell } from '../components/ui'
import ErfassungZustandBadge from '../components/ui/ErfassungZustandBadge'
import { MonatsdatenForm } from '../components/forms'
import { DataLoadingState } from '../components/common'
import { useMonatsdaten, useInvestitionen, useApiData, useAnlage } from '../hooks'
import { useOeffneWizard } from '../v4/wizardHost'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import { haStatisticsApi, type Monatswerte, type VerfuegbarerMonat } from '../api/haStatistics'
import { investitionenApi, type InvestitionMonatsdaten } from '../api/investitionen'
import { energieProfilApi, type KraftstoffpreisStatus } from '../api/energie_profil'
import type { Monatsdaten } from '../types'
import { MONAT_KURZ, fmtZahl } from '../lib'
import {
  ermittleStartAnker,
  ermittleFehlendeMonate,
  naechsterOffenerMonat,
  monatIndex,
  type MonatRef,
} from '../lib/monatsLuecken'

// ─── Spalten-SoT ──────────────────────────────────────────────────────────────

interface ColumnConfig {
  key: string
  label: string
  shortLabel?: string
  group: 'zaehler' | 'komponenten' | 'berechnet'
  getValue: (md: AggregierteMonatsdaten) => number | null
  format?: 'kwh' | 'percent'
  className?: string
  defaultVisible: boolean
}

const COLUMN_GROUPS = {
  zaehler: { label: 'Zählerwerte', color: 'bg-blue-500' },
  komponenten: { label: 'Komponenten', color: 'bg-amber-500' },
  berechnet: { label: 'Berechnungen', color: 'bg-green-500' },
}

const COLUMNS: ColumnConfig[] = [
  // Zählerwerte (aus Monatsdaten - direkt gemessen)
  { key: 'einspeisung', label: 'Einspeisung', shortLabel: 'Einsp.', group: 'zaehler', getValue: (md) => md.einspeisung_kwh, format: 'kwh', defaultVisible: true },
  { key: 'netzbezug', label: 'Netzbezug', shortLabel: 'Netz', group: 'zaehler', getValue: (md) => md.netzbezug_kwh, format: 'kwh', defaultVisible: true },
  // Komponenten (aggregiert aus InvestitionMonatsdaten)
  { key: 'pv_erzeugung', label: 'PV-Erzeugung', shortLabel: 'PV', group: 'komponenten', getValue: (md) => md.pv_erzeugung_kwh, format: 'kwh', defaultVisible: true },
  { key: 'speicher_ladung', label: 'Speicher Ladung', shortLabel: 'Sp.Lad', group: 'komponenten', getValue: (md) => md.speicher_ladung_kwh, format: 'kwh', defaultVisible: false },
  { key: 'speicher_entladung', label: 'Speicher Entladung', shortLabel: 'Sp.Entl', group: 'komponenten', getValue: (md) => md.speicher_entladung_kwh, format: 'kwh', defaultVisible: false },
  { key: 'wp_strom', label: 'WP Strom', shortLabel: 'WP', group: 'komponenten', getValue: (md) => md.wp_strom_kwh, format: 'kwh', defaultVisible: false },
  { key: 'wp_heizung', label: 'WP Heizung', shortLabel: 'WP Hz', group: 'komponenten', getValue: (md) => md.wp_heizung_kwh, format: 'kwh', defaultVisible: false },
  { key: 'wp_warmwasser', label: 'WP Warmwasser', shortLabel: 'WP WW', group: 'komponenten', getValue: (md) => md.wp_warmwasser_kwh, format: 'kwh', defaultVisible: false },
  { key: 'eauto_ladung', label: 'E-Auto Ladung', shortLabel: 'E-Auto', group: 'komponenten', getValue: (md) => md.eauto_ladung_kwh, format: 'kwh', defaultVisible: false },
  { key: 'eauto_km', label: 'E-Auto km', shortLabel: 'km', group: 'komponenten', getValue: (md) => md.eauto_km, defaultVisible: false },
  { key: 'wallbox_ladung', label: 'Wallbox Ladung', shortLabel: 'WB', group: 'komponenten', getValue: (md) => md.wallbox_ladung_kwh, format: 'kwh', defaultVisible: false },
  { key: 'wallbox_ladung_pv', label: 'Wallbox PV-Ladung', shortLabel: 'WB PV', group: 'komponenten', getValue: (md) => md.wallbox_ladung_pv_kwh, format: 'kwh', defaultVisible: false },
  // Berechnete Werte
  { key: 'direktverbrauch', label: 'Direktverbrauch', shortLabel: 'Direkt', group: 'berechnet', getValue: (md) => md.direktverbrauch_kwh, format: 'kwh', defaultVisible: false },
  { key: 'eigenverbrauch', label: 'Eigenverbrauch', shortLabel: 'Eigen', group: 'berechnet', getValue: (md) => md.eigenverbrauch_kwh, format: 'kwh', defaultVisible: true },
  { key: 'gesamtverbrauch', label: 'Gesamtverbrauch', shortLabel: 'Gesamt', group: 'berechnet', getValue: (md) => md.gesamtverbrauch_kwh, format: 'kwh', defaultVisible: false },
  { key: 'autarkie', label: 'Autarkie', shortLabel: 'Aut.', group: 'berechnet', getValue: (md) => md.autarkie_prozent, format: 'percent', className: 'text-green-600 dark:text-green-400', defaultVisible: true },
  { key: 'eigenverbrauchsquote', label: 'EV-Quote', shortLabel: 'EVQ', group: 'berechnet', getValue: (md) => md.eigenverbrauchsquote_prozent, format: 'percent', defaultVisible: false },
]

// LocalStorage Key für Spalten-Einstellungen (v3: alle Komponenten)
const COLUMNS_STORAGE_KEY = 'eedc-monatsdaten-columns-v3'

// ─── Verwaltung (Tabelle + alle Modals + Datenverwaltung) ─────────────────────

/**
 * Voller Monatsdaten-Manager. Wird von der IST-Seite (V3-Hülle) und der nativen
 * V4-Seite geteilt. `anlageId` ist bereits aufgelöst (nicht-null); `kopfZusatz`
 * (z. B. Anlage-Auswahl) wandert links in die Kopfleiste.
 */
export function MonatsdatenVerwaltung({ anlageId, kopfZusatz }: { anlageId: number; kopfZusatz?: ReactNode }) {
  const navigate = useNavigate()
  // E1 (Donor-Kanten): unter LayoutV4 öffnen Monatsabschluss/CSV-Import im
  // Overlay (oeffneWizard mit Payload); ohne Provider (V3) bleibt navigate.
  const oeffneWizard = useOeffneWizard()
  // Nur noch V3: der Monatsabschluss-Wizard läuft in V3 über seine Route. Unter V4
  // ist der Wizard als Fläche stillgelegt (B5) — die Öffner-Buttons sind dort
  // ausgeblendet, die assistierte Form übernimmt (Edit / „Erfassen" / Sprung).
  const monatsabschlussOeffnen = (jahr?: number, monat?: number) => {
    if (jahr != null && monat != null) navigate(`/monatsabschluss/${anlageId}/${jahr}/${monat}`)
    else navigate(`/monatsabschluss/${anlageId}`)
  }
  const { monatsdaten, loading, error, createMonatsdaten, updateMonatsdaten, deleteMonatsdaten } = useMonatsdaten(anlageId)
  // Hook wird für MonatsdatenForm benötigt
  const { investitionen } = useInvestitionen(anlageId)
  // Anlage-Installationsdatum als Fallback-Anker für den erwarteten Monatsbereich.
  const { anlage } = useAnlage(anlageId)
  const hatEAuto = investitionen.some(i => i.typ === 'e-auto')
  // D14-8-Gate: Kraftstoff-Monats-Karte nur in V3 (V4 = Werkbank).
  // IA-V4 ist die einzige Oberfläche (Flip v4.0.0). Die `!istV4`-Zweige unten sind
  // toter V3-Bestand → Entfernung als Flip-Nacharbeit (siehe PLAN-IA-V4-UMSETZUNG-FLIP §2a).
  const istV4 = true

  // Aggregierte Daten
  const { data: aggregierteDaten, loading: aggregiertLoading } = useApiData(
    () => monatsdatenApi.listAggregiert(anlageId),
    [anlageId, monatsdaten],
  )

  const [showForm, setShowForm] = useState(false)
  // Voreingestellter Monat beim Erfassen einer Lücke (§7) — sonst null (freie Wahl).
  const [createPreset, setCreatePreset] = useState<MonatRef | null>(null)
  const [editingData, setEditingData] = useState<Monatsdaten | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<Monatsdaten | null>(null)
  // #349: Begleitfunde des Lösch-Dialogs — was hängt außer der Zählerzeile dran?
  const [geraetewerte, setGeraetewerte] = useState<
    Awaited<ReturnType<typeof monatsdatenApi.getGeraetewerte>> | null
  >(null)
  const [showColumnSelector, setShowColumnSelector] = useState(false)

  // HA-Statistik Laden
  const [showHaModal, setShowHaModal] = useState(false)
  const { data: haStatus } = useApiData(
    () => haStatisticsApi.getStatus(),
    [],
  )
  const haVerfuegbar = haStatus?.verfuegbar ?? false
  const [verfuegbareMonate, setVerfuegbareMonate] = useState<VerfuegbarerMonat[]>([])
  const [haLoading, setHaLoading] = useState(false)
  const [haError, setHaError] = useState<string | null>(null)
  const [selectedHaJahr, setSelectedHaJahr] = useState<number>(new Date().getFullYear())
  const [selectedHaMonat, setSelectedHaMonat] = useState<number>(new Date().getMonth()) // Vormonat
  const [haVorausfuellung, setHaVorausfuellung] = useState<Monatswerte | null>(null)
  const [showHaVergleich, setShowHaVergleich] = useState(false) // Vergleichsansicht für existierende Monate
  const [haVergleichsDaten, setHaVergleichsDaten] = useState<{
    haWerte: Monatswerte
    vorhandeneDaten: Monatsdaten
    vorhandeneInvestitionsDaten: InvestitionMonatsdaten[]
  } | null>(null)

  // Datenverwaltung: Kraftstoffpreis-Monats-Backfill
  const [kpStatus, setKpStatus] = useState<KraftstoffpreisStatus | null>(null)
  const [kpMessage, setKpMessage] = useState<string | null>(null)
  const [kpIsError, setKpIsError] = useState(false)
  const [runningKpBackfill, setRunningKpBackfill] = useState(false)

  const loadKraftstoffStatus = useCallback(async () => {
    try {
      const s = await energieProfilApi.getKraftstoffpreisStatus(anlageId)
      setKpStatus(s)
    } catch {
      setKpStatus(null)
    }
  }, [anlageId])

  useEffect(() => { loadKraftstoffStatus() }, [loadKraftstoffStatus])

  const handleKraftstoffMonatsBackfill = async () => {
    try {
      setRunningKpBackfill(true)
      setKpMessage(null)
      setKpIsError(false)
      const res = await energieProfilApi.kraftstoffpreisBackfillMonats(anlageId)
      if (res.fehler) {
        setKpIsError(true)
        setKpMessage(`Kraftstoffpreis-Backfill: ${res.fehler}`)
      } else {
        setKpMessage(
          res.aktualisiert > 0
            ? `${res.aktualisiert} Monate mit Kraftstoffpreis (${res.land}) befüllt.`
            : (res.hinweis || 'Keine offenen Monate.')
        )
      }
      await loadKraftstoffStatus()
    } catch (e) {
      setKpIsError(true)
      setKpMessage(e instanceof Error ? e.message : 'Kraftstoffpreis-Backfill fehlgeschlagen')
    } finally {
      setRunningKpBackfill(false)
    }
  }

  // Sichtbare Spalten aus LocalStorage laden
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem(COLUMNS_STORAGE_KEY)
      if (stored) {
        return new Set(JSON.parse(stored))
      }
    } catch {
      // Ignore parse errors
    }
    return new Set(COLUMNS.filter(c => c.defaultVisible).map(c => c.key))
  })

  // Spalten-Einstellungen in LocalStorage speichern
  useEffect(() => {
    localStorage.setItem(COLUMNS_STORAGE_KEY, JSON.stringify([...visibleColumns]))
  }, [visibleColumns])

  // Verfügbare Monate laden wenn Modal geöffnet wird
  useEffect(() => {
    if (!showHaModal) return

    const loadMonate = async () => {
      setHaLoading(true)
      setHaError(null)
      try {
        const monate = await haStatisticsApi.getVerfuegbareMonate(anlageId)
        setVerfuegbareMonate(monate)
      } catch (e) {
        setHaError('Fehler beim Laden der verfügbaren Monate')
      } finally {
        setHaLoading(false)
      }
    }
    loadMonate()
  }, [showHaModal, anlageId])

  // HA-Monatswerte laden
  const handleLoadFromHa = async () => {
    if (!selectedHaJahr || !selectedHaMonat) return

    setHaLoading(true)
    setHaError(null)

    try {
      const werte = await haStatisticsApi.getMonatswerte(anlageId, selectedHaJahr, selectedHaMonat)

      // Prüfe ob Monat bereits existiert
      const vorhandeneDaten = monatsdaten.find(
        md => md.jahr === selectedHaJahr && md.monat === selectedHaMonat
      )

      if (vorhandeneDaten) {
        // Lade auch die InvestitionMonatsdaten für den Vergleich
        const vorhandeneInvestitionsDaten = await investitionenApi.getMonatsdatenByMonth(
          anlageId, selectedHaJahr, selectedHaMonat
        )
        // Zeige Vergleichsansicht
        setHaVergleichsDaten({ haWerte: werte, vorhandeneDaten, vorhandeneInvestitionsDaten })
        setShowHaModal(false)
        setShowHaVergleich(true)
      } else {
        // Direkt zum Formular
        setHaVorausfuellung(werte)
        setShowHaModal(false)
        setShowForm(true)
      }
    } catch (e) {
      setHaError('Fehler beim Laden der Monatswerte aus HA-Statistik')
    } finally {
      setHaLoading(false)
    }
  }

  // Nach Vergleich: Mit HA-Werten fortfahren
  const handleProceedWithHa = () => {
    if (!haVergleichsDaten) return
    setHaVorausfuellung(haVergleichsDaten.haWerte)
    setEditingData(haVergleichsDaten.vorhandeneDaten) // Bearbeiten statt Neu
    setShowHaVergleich(false)
    setHaVergleichsDaten(null)
  }

  // Vergleich abbrechen
  const handleCancelVergleich = () => {
    setShowHaVergleich(false)
    setHaVergleichsDaten(null)
  }

  const toggleColumn = (key: string) => {
    setVisibleColumns(prev => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  const toggleGroup = (group: keyof typeof COLUMN_GROUPS) => {
    const groupColumns = COLUMNS.filter(c => c.group === group)
    const allVisible = groupColumns.every(c => visibleColumns.has(c.key))

    setVisibleColumns(prev => {
      const next = new Set(prev)
      groupColumns.forEach(c => {
        if (allVisible) {
          next.delete(c.key)
        } else {
          next.add(c.key)
        }
      })
      return next
    })
  }

  const activeColumns = COLUMNS.filter(c => visibleColumns.has(c.key))
  // Memoisiert, weil `?? []` sonst bei JEDEM Render ein neues Array erzeugt,
  // solange noch nichts geladen ist — die drei useMemo unten hingen daran und
  // rechneten dadurch jedes Mal neu (genau der Fall, den exhaustive-deps meldet).
  const daten = useMemo(() => aggregierteDaten ?? [], [aggregierteDaten])

  // ── Vollständigkeits-Quelle (§7, V-b): fehlende Monate + „nächster offener" ──
  // EINE Ableitung für Tabellen-Färbung UND Sprung. Bereich = [Anschaffungs-Anker
  // … Vormonat(heute)]. NICHT der naive Backend-`getNaechsterMonat` (verfehlt
  // innere Lücken). Anker: frühestes Investitions-Anschaffungsdatum → Anlage-
  // Installationsdatum → erste vorhandene Zeile (feedback_anschaffungsdatum_grenze).
  const { fehlendeMonate, naechsterOffen } = useMemo(() => {
    const vorhandene: MonatRef[] = daten.map(md => ({ jahr: md.jahr, monat: md.monat }))
    const start = ermittleStartAnker({
      anschaffungsdaten: investitionen.map(i => i.anschaffungsdatum),
      anlageInstallationsdatum: anlage?.installationsdatum,
      vorhandene,
    })
    const jetzt = new Date()
    const params = { vorhandene, start, heute: { jahr: jetzt.getFullYear(), monat: jetzt.getMonth() + 1 } }
    return {
      fehlendeMonate: ermittleFehlendeMonate(params),
      naechsterOffen: naechsterOffenerMonat(params),
    }
  }, [daten, investitionen, anlage])

  // Tabellenzeilen: vorhandene Daten + fehlende-Monat-Platzhalter, absteigend
  // (neueste zuerst — CLAUDE.md Datums-Listen-Default). Platzhalter nur, wenn
  // bereits ≥1 Zeile existiert (kein Explodieren bei brandneuer Anlage).
  type TabellenZeile =
    | { kind: 'daten'; md: AggregierteMonatsdaten; idx: number }
    | { kind: 'fehlt'; jahr: number; monat: number; idx: number }
  const tabellenZeilen = useMemo<TabellenZeile[]>(() => {
    const zeilen: TabellenZeile[] = daten.map(md => ({
      kind: 'daten' as const, md, idx: monatIndex(md.jahr, md.monat),
    }))
    if (daten.length > 0) {
      for (const m of fehlendeMonate) {
        zeilen.push({ kind: 'fehlt' as const, jahr: m.jahr, monat: m.monat, idx: monatIndex(m.jahr, m.monat) })
      }
    }
    return zeilen.sort((a, b) => b.idx - a.idx)
  }, [daten, fehlendeMonate])

  // Erfassen-Icon einer Lücke / Sprung → Form für GENAU diesen Monat öffnen (Lücke
  // = garantiert ohne Zeile → Create-Preset).
  const oeffneErfassung = (jahr: number, monat: number) => {
    setHaVorausfuellung(null)
    setCreatePreset({ jahr, monat })
    setShowForm(true)
  }

  // Deep-Link/Öffner für einen beliebigen Monat (B5): existiert eine Zeile →
  // Bearbeiten-Form, sonst Create-Preset. EINE Form-Wahrheit für alle Einstiege.
  const oeffneMonat = (jahr: number, monat: number) => {
    setHaVorausfuellung(null)
    const original = monatsdaten.find(md => md.jahr === jahr && md.monat === monat)
    if (original) {
      setEditingData(original)
    } else {
      setCreatePreset({ jahr, monat })
      setShowForm(true)
    }
  }

  // B5-Deep-Link: die V4-Fusszeile navigiert mit `?erfassen=YYYY-MM` hierher →
  // Form für den offenen Monat öffnen. Param danach entfernen, damit Reload/Zurück
  // ihn nicht erneut auslöst. EinstellungenV4 klappt parallel den Block auf.
  const [searchParams, setSearchParams] = useSearchParams()
  useEffect(() => {
    const roh = searchParams.get('erfassen')
    if (!roh) return
    const [j, m] = roh.split('-').map(Number)
    if (j && m >= 1 && m <= 12) oeffneMonat(j, m)
    const next = new URLSearchParams(searchParams)
    next.delete('erfassen')
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  // Prüfe ob Legacy-Daten existieren
  const legacyCount = useMemo(() => {
    return daten.filter(md => md.hat_legacy_daten).length
  }, [daten])

  const handleCreate = async (data: Parameters<typeof createMonatsdaten>[0]) => {
    await createMonatsdaten(data)
    setShowForm(false)
    setCreatePreset(null)
  }

  const handleUpdate = async (data: Parameters<typeof createMonatsdaten>[0]) => {
    if (editingData) {
      await updateMonatsdaten(editingData.id, data)
      setEditingData(null)
    }
  }

  const handleDelete = async () => {
    if (deleteConfirm) {
      await deleteMonatsdaten(deleteConfirm.id)
      setDeleteConfirm(null)
    }
  }

  // #349: Was hängt außer der Zählerzeile noch an diesem Monat? Die Messwerte
  // je Komponente stehen in einer eigenen Tabelle und blieben bisher stehen —
  // unsichtbar, aber wirksam: sie weisen einen erneuten Import ab. Der Dialog
  // fragt beim Öffnen nach und benennt sie.
  useEffect(() => {
    if (!deleteConfirm) {
      setGeraetewerte(null)
      return
    }
    let abgebrochen = false
    monatsdatenApi.getGeraetewerte(deleteConfirm.id)
      .then(r => { if (!abgebrochen) setGeraetewerte(r) })
      .catch(() => { if (!abgebrochen) setGeraetewerte(null) })
    return () => { abgebrochen = true }
  }, [deleteConfirm])

  // Finde Original-Monatsdaten für Edit/Delete
  const findOriginalMonatsdaten = (aggregiert: AggregierteMonatsdaten): Monatsdaten | undefined => {
    return monatsdaten.find(md => md.id === aggregiert.id)
  }

  const formatValue = (val: number | null, format?: 'kwh' | 'percent') => {
    if (val === null || val === undefined || isNaN(val)) return '-'
    switch (format) {
      case 'percent':
        return `${fmtZahl(val, 1)} %`
      case 'kwh':
      default:
        return fmtZahl(val, 1)
    }
  }

  if (loading) {
    return <DataLoadingState loading={true} error={null}><div /></DataLoadingState>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          {kopfZusatz}
          {/* „Nächster offener Monat"-Sprung (§7/P11) — aus DERSELBEN
              Vollständigkeits-Quelle wie die Tabellen-Färbung. */}
          {naechsterOffen && (
            <Button
              variant="secondary"
              onClick={() => oeffneErfassung(naechsterOffen.jahr, naechsterOffen.monat)}
              title="Zum nächsten offenen Monat springen und erfassen"
            >
              <ArrowRight className="h-5 w-5 mr-2 text-gray-500" />
              Nächster offener: {MONAT_KURZ[naechsterOffen.monat]} {naechsterOffen.jahr}
            </Button>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 flex-wrap">
          {haVerfuegbar && (
            <Button variant="secondary" onClick={() => setShowHaModal(true)}>
              <Database className="h-5 w-5 mr-2" />
              Aus HA laden
            </Button>
          )}
          {/* B5: Wizard-Einstieg nur in V3 — unter V4 übernehmen Edit +
              „Nächster offener"-Sprung (assistierte Form), kein Doppel-Einstieg. */}
          {!istV4 && (
            <Button
              variant="secondary"
              onClick={() => monatsabschlussOeffnen()}
            >
              <Calendar className="h-5 w-5 mr-2" />
              Monatsabschluss
            </Button>
          )}
          <Button onClick={() => { setHaVorausfuellung(null); setCreatePreset(null); setShowForm(true) }}>
            <Plus className="h-5 w-5 mr-2" />
            Monat einfügen
          </Button>
        </div>
      </div>

      {error && <Alert type="error">{error}</Alert>}

      {/* Migrations-Hinweis für Legacy-Daten */}
      {legacyCount > 0 && (
        <Alert type="warning" className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium">Legacy-Daten gefunden</p>
            <p className="text-sm mt-1">
              {legacyCount} Monat{legacyCount > 1 ? 'e' : ''} enthält
              {legacyCount > 1 ? 'en' : ''} Daten im alten Format (PV-Erzeugung/Speicher in Monatsdaten statt InvestitionMonatsdaten).
              Bitte jeden betroffenen Monat einmal öffnen und speichern.
            </p>
          </div>
        </Alert>
      )}

      {aggregiertLoading ? (
        <DataLoadingState loading={true} error={null}><div /></DataLoadingState>
      ) : daten.length === 0 ? (
        <Card>
          <EmptyState
            icon={Calendar}
            title="Keine Monatsdaten vorhanden"
            description="Erfasse deine ersten Monatsdaten manuell oder importiere eine CSV-Datei."
            action={
              <div className="flex gap-4 flex-wrap justify-center">
                <Button onClick={() => { setHaVorausfuellung(null); setCreatePreset(null); setShowForm(true) }}>
                  <Plus className="h-5 w-5 mr-2" />
                  Monat einfügen
                </Button>
                {!istV4 && (
                  <Button
                    variant="secondary"
                    onClick={() => monatsabschlussOeffnen()}
                  >
                    Monatsabschluss starten
                  </Button>
                )}
                <Button variant="secondary" onClick={() => (oeffneWizard ? oeffneWizard('csv-import') : navigate('/import'))}>CSV importieren</Button>
              </div>
            }
          />
        </Card>
      ) : (
        <>
          {/* Spalten-Auswahl */}
          <div className="flex justify-end">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowColumnSelector(!showColumnSelector)}
            >
              <Columns className="h-4 w-4 mr-2" />
              Spalten ({activeColumns.length}/{COLUMNS.length})
            </Button>
          </div>

          {/* Spalten-Auswahl Panel mit Gruppen */}
          {showColumnSelector && (
            <Card className="bg-gray-50 dark:bg-gray-800/50">
              <div className="space-y-4">
                {(Object.keys(COLUMN_GROUPS) as Array<keyof typeof COLUMN_GROUPS>).map((groupKey) => {
                  const group = COLUMN_GROUPS[groupKey]
                  const groupColumns = COLUMNS.filter(c => c.group === groupKey)
                  const visibleCount = groupColumns.filter(c => visibleColumns.has(c.key)).length

                  return (
                    <div key={groupKey}>
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`w-3 h-3 rounded-full ${group.color}`} />
                        <Button variant="ghost" size="sm" onClick={() => toggleGroup(groupKey)}>
                          {group.label} ({visibleCount}/{groupColumns.length})
                        </Button>
                      </div>
                      <div className="flex flex-wrap gap-x-4 gap-y-1.5 ml-5">
                        {groupColumns.map((col) => (
                          <Checkbox
                            key={col.key}
                            id={`monatsdaten-spalte-${col.key}`}
                            label={col.label}
                            checked={visibleColumns.has(col.key)}
                            onChange={() => toggleColumn(col.key)}
                          />
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-4">
                Klicke auf Gruppen-Namen um alle Spalten ein-/auszublenden, oder auf einzelne Spalten.
              </p>
            </Card>
          )}

          {/* Tabelle */}
          <Card padding="none" className="overflow-hidden">
            <div className="max-h-[36rem] overflow-auto [&_thead]:sticky [&_thead]:top-0 [&_thead]:z-10">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <TableHead>
                  <TableRow>
                    <TableHeader>Monat</TableHeader>
                    {activeColumns.map((col) => (
                      <TableHeader key={col.key} className="text-right">
                        <span className="hidden sm:inline">{col.label}</span>
                        <span className="sm:hidden">{col.shortLabel || col.label}</span>
                      </TableHeader>
                    ))}
                    <TableHeader className="text-right">Aktionen</TableHeader>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {tabellenZeilen.map((zeile) => {
                    // Lücken-Zeile (§7): fehlender Monat, dieselbe Ampel-Farbsprache
                    // (§5 „offen"/grau) + Erfassen-Icon → Form für GENAU diesen Monat.
                    if (zeile.kind === 'fehlt') {
                      return (
                        <TableRow
                          key={`fehlt-${zeile.idx}`}
                          className="bg-gray-50 dark:bg-gray-800/40"
                        >
                          <TableCell>
                            <span className="font-medium text-gray-500 dark:text-gray-400">
                              {MONAT_KURZ[zeile.monat]} {zeile.jahr}
                            </span>
                            <ErfassungZustandBadge zustand="fehlt" className="ml-2 align-middle" />
                          </TableCell>
                          {activeColumns.map((col) => (
                            <TableCell key={col.key} className="text-right font-mono text-gray-400 dark:text-gray-600">
                              —
                            </TableCell>
                          ))}
                          <TableCell className="text-right">
                            <div className="flex justify-end gap-2">
                              <Button
                                variant="ghost"
                                size="sm"
                                title="Diesen Monat erfassen"
                                onClick={() => oeffneErfassung(zeile.jahr, zeile.monat)}
                              >
                                <PenLine className="h-4 w-4 text-gray-500 mr-1" />
                                Erfassen
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      )
                    }
                    const md = zeile.md
                    return (
                      <TableRow key={md.id} className={md.hat_legacy_daten ? 'bg-amber-50 dark:bg-amber-900/10' : ''}>
                        <TableCell>
                          <span className="font-medium">{MONAT_KURZ[md.monat]} {md.jahr}</span>
                          {md.hat_legacy_daten && (
                            <span title="Legacy-Daten">
                              <AlertTriangle className="h-3 w-3 text-amber-500 inline ml-1" />
                            </span>
                          )}
                        </TableCell>
                        {activeColumns.map((col) => {
                          const value = col.getValue(md)
                          return (
                            <TableCell key={col.key} className={`text-right font-mono ${col.className || ''}`}>
                              {formatValue(value, col.format)}
                            </TableCell>
                          )
                        })}
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-2">
                            {/* B5: per-Zeile-Wizard nur in V3 — unter V4 öffnet Edit
                                dieselbe assistierte Form für den Monat. */}
                            {!istV4 && (
                              <Button
                                variant="ghost"
                                size="sm"
                                title="Monatsabschluss-Assistent"
                                onClick={() => monatsabschlussOeffnen(md.jahr, md.monat)}
                              >
                                <Calendar className="h-4 w-4 text-primary-500" />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                const original = findOriginalMonatsdaten(md)
                                if (original) setEditingData(original)
                              }}
                            >
                              <Edit className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                const original = findOriginalMonatsdaten(md)
                                if (original) setDeleteConfirm(original)
                              }}
                            >
                              <Trash2 className="h-4 w-4 text-red-500" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </table>
            </div>
          </Card>
        </>
      )}

      {/* Datenverwaltung — rapahl #188: Kraftstoffpreis-Hinweis nur bei E-Auto-Anlage.
          D14-8: nur V3 — unter /v4 konsolidiert in der Reparatur-Werkbank. */}
      {!istV4 && hatEAuto && kpStatus && kpStatus.monats_offen > 0 && (
        <Card>
          <div className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <Database className="h-6 w-6 text-primary-500" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Datenverwaltung
              </h2>
            </div>

            {kpMessage && <Alert type={kpIsError ? "error" : "info"} className="mb-3">{kpMessage}</Alert>}

            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <Fuel className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <h3 className="font-medium text-gray-900 dark:text-white">
                    Kraftstoffpreise nachpflegen (Monats-Ebene)
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {fmtZahl(kpStatus.monats_offen)} Monate ohne Kraftstoffpreis.
                    Lädt den Monatsdurchschnitt aus dem EU Oil Bulletin (Euro-Super 95, {kpStatus.land}).
                  </p>
                  <div className="mt-3">
                    <Button
                      variant="secondary"
                      onClick={handleKraftstoffMonatsBackfill}
                      disabled={runningKpBackfill}
                    >
                      {runningKpBackfill ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Fuel className="h-4 w-4 mr-2" />}
                      Kraftstoffpreise nachpflegen
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* HA-Statistik Modal */}
      <Modal
        isOpen={showHaModal}
        onClose={() => setShowHaModal(false)}
        title="Monatsdaten aus HA-Statistik laden"
        size="md"
      >
        <div className="space-y-4">
          {haError && <Alert type="error">{haError}</Alert>}

          {haLoading && !verfuegbareMonate.length ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-primary-500" />
            </div>
          ) : verfuegbareMonate.length === 0 ? (
            <Alert type="warning">
              Keine Daten in HA-Statistik gefunden. Stellen Sie sicher, dass das Sensor-Mapping
              konfiguriert ist und die Sensoren Langzeit-Statistiken haben.
            </Alert>
          ) : (
            <>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Wählen Sie einen Monat aus, dessen Daten aus der Home Assistant
                Langzeitstatistik geladen werden sollen. Die Werte werden im
                Formular vorausgefüllt und können vor dem Speichern angepasst werden.
              </p>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Select
                    id="ha-jahr"
                    label="Jahr"
                    value={String(selectedHaJahr)}
                    onChange={(e) => setSelectedHaJahr(parseInt(e.target.value))}
                    options={[...new Set(verfuegbareMonate.map(m => m.jahr))]
                      .sort((a, b) => b - a)
                      .map(jahr => ({ value: String(jahr), label: String(jahr) }))}
                  />
                </div>
                <div>
                  <Select
                    id="ha-monat"
                    label="Monat"
                    value={String(selectedHaMonat)}
                    onChange={(e) => setSelectedHaMonat(parseInt(e.target.value))}
                    options={verfuegbareMonate
                      .filter(m => m.jahr === selectedHaJahr)
                      .sort((a, b) => b.monat - a.monat)
                      .map(m => ({
                        value: String(m.monat),
                        label: m.hat_daten ? m.monat_name : `${m.monat_name} (keine Daten)`,
                      }))}
                  />
                </div>
              </div>

              {/* Info über vorhandene Daten */}
              {monatsdaten.some(md => md.jahr === selectedHaJahr && md.monat === selectedHaMonat) && (
                <Alert type="info">
                  Für diesen Monat existieren bereits Daten. Nach dem Laden wird ein
                  Vergleich angezeigt, damit Sie die Unterschiede prüfen können.
                </Alert>
              )}

              <div className="flex justify-end gap-3 pt-4">
                <Button variant="secondary" onClick={() => setShowHaModal(false)}>
                  Abbrechen
                </Button>
                <Button onClick={handleLoadFromHa} disabled={haLoading}>
                  {haLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Lade...
                    </>
                  ) : (
                    <>
                      <Database className="h-4 w-4 mr-2" />
                      Werte laden
                    </>
                  )}
                </Button>
              </div>
            </>
          )}
        </div>
      </Modal>

      {/* Vergleichs-Modal: HA vs. Vorhandene Daten */}
      <Modal
        isOpen={showHaVergleich}
        onClose={handleCancelVergleich}
        title={`Vergleich: ${haVergleichsDaten?.haWerte.monat_name} ${haVergleichsDaten?.haWerte.jahr}`}
        size="lg"
      >
        {haVergleichsDaten && (
          <div className="space-y-4">
            <Alert type="warning">
              Für diesen Monat existieren bereits Daten. Bitte prüfen Sie die Unterschiede
              und entscheiden Sie, ob die HA-Werte übernommen werden sollen.
            </Alert>

            {/* Basis-Werte Vergleich */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-gray-900 dark:text-white">Basis-Werte (kWh)</h4>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b dark:border-gray-700">
                      <th className="text-left py-2 px-3 font-medium">Feld</th>
                      <th className="text-right py-2 px-3 font-medium text-blue-600">Vorhanden</th>
                      <th className="text-right py-2 px-3 font-medium text-green-600">HA-Statistik</th>
                      <th className="text-right py-2 px-3 font-medium">Diff</th>
                    </tr>
                  </thead>
                  <tbody>
                    <VergleichsZeile
                      label="Einspeisung"
                      vorhanden={haVergleichsDaten.vorhandeneDaten.einspeisung_kwh}
                      haWert={haVergleichsDaten.haWerte.basis.find(b => b.feld === 'einspeisung')?.wert}
                    />
                    <VergleichsZeile
                      label="Netzbezug"
                      vorhanden={haVergleichsDaten.vorhandeneDaten.netzbezug_kwh}
                      haWert={haVergleichsDaten.haWerte.basis.find(b => b.feld === 'netzbezug')?.wert}
                    />
                  </tbody>
                </table>
              </div>
            </div>

            {/* Investitions-Werte Vergleich */}
            {(haVergleichsDaten.haWerte.investitionen.length > 0 || haVergleichsDaten.vorhandeneInvestitionsDaten.length > 0) && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-gray-900 dark:text-white">Komponenten-Werte (kWh)</h4>
                {haVergleichsDaten.haWerte.investitionen.map(inv => {
                  // Finde die vorhandenen InvestitionMonatsdaten für diese Investition
                  const vorhandeneInv = haVergleichsDaten.vorhandeneInvestitionsDaten.find(
                    v => v.investition_id === inv.investition_id
                  )
                  const vorhandeneVerbrauchDaten = vorhandeneInv?.verbrauch_daten || {}

                  // Sammle alle Felder (aus HA und vorhanden)
                  const alleFelder = new Set<string>()
                  inv.felder.forEach(f => alleFelder.add(f.feld))
                  Object.keys(vorhandeneVerbrauchDaten).forEach(k => alleFelder.add(k))

                  return (
                    <div key={inv.investition_id} className="border rounded-lg overflow-hidden dark:border-gray-700">
                      <div className="px-3 py-2 bg-gray-50 dark:bg-gray-700/50">
                        <h5 className="text-xs font-medium text-gray-700 dark:text-gray-300">
                          {inv.bezeichnung} ({inv.typ})
                        </h5>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                          <thead>
                            <tr className="border-b dark:border-gray-700">
                              <th className="text-left py-2 px-3 font-medium">Feld</th>
                              <th className="text-right py-2 px-3 font-medium text-blue-600">Vorhanden</th>
                              <th className="text-right py-2 px-3 font-medium text-green-600">HA-Statistik</th>
                              <th className="text-right py-2 px-3 font-medium">Diff</th>
                            </tr>
                          </thead>
                          <tbody>
                            {[...alleFelder].map(feldKey => {
                              const haFeld = inv.felder.find(f => f.feld === feldKey)
                              const vorhandenWert = vorhandeneVerbrauchDaten[feldKey]
                              // Nur anzeigen wenn mindestens ein Wert vorhanden
                              if (haFeld?.wert === null && vorhandenWert === undefined) return null
                              return (
                                <VergleichsZeile
                                  key={feldKey}
                                  label={haFeld?.label || feldKey.replace(/_/g, ' ')}
                                  vorhanden={vorhandenWert}
                                  haWert={haFeld?.wert}
                                />
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )
                })}
                {/* Zeige Investitionen die nur in vorhandenen Daten existieren (nicht in HA-Mapping) */}
                {haVergleichsDaten.vorhandeneInvestitionsDaten
                  .filter(vorh => !haVergleichsDaten.haWerte.investitionen.some(ha => ha.investition_id === vorh.investition_id))
                  .filter(vorh => Object.keys(vorh.verbrauch_daten).length > 0)
                  .map(vorh => (
                    <div key={vorh.investition_id} className="border rounded-lg overflow-hidden dark:border-gray-700 opacity-75">
                      <div className="px-3 py-2 bg-gray-50 dark:bg-gray-700/50">
                        <h5 className="text-xs font-medium text-gray-500 dark:text-gray-400">
                          Investition #{vorh.investition_id} (nur Bestandsdaten, kein HA-Mapping)
                        </h5>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                          <thead>
                            <tr className="border-b dark:border-gray-700">
                              <th className="text-left py-2 px-3 font-medium">Feld</th>
                              <th className="text-right py-2 px-3 font-medium text-blue-600">Vorhanden</th>
                              <th className="text-right py-2 px-3 font-medium text-green-600">HA-Statistik</th>
                              <th className="text-right py-2 px-3 font-medium">Diff</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(vorh.verbrauch_daten).map(([feldKey, wert]) => (
                              <VergleichsZeile
                                key={feldKey}
                                label={feldKey.replace(/_/g, ' ')}
                                vorhanden={wert}
                                haWert={null}
                              />
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ))
                }
              </div>
            )}

            <div className="flex justify-end gap-3 pt-4 border-t dark:border-gray-700">
              <Button variant="secondary" onClick={handleCancelVergleich}>
                Abbrechen
              </Button>
              <Button onClick={handleProceedWithHa}>
                <Database className="h-4 w-4 mr-2" />
                Mit HA-Werten fortfahren
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Create Modal */}
      <Modal
        isOpen={showForm}
        onClose={() => { setShowForm(false); setHaVorausfuellung(null); setCreatePreset(null) }}
        title={
          haVorausfuellung
            ? `Monatsdaten aus HA laden - ${haVorausfuellung.monat_name} ${haVorausfuellung.jahr}`
            : createPreset
              ? `Monatsdaten erfassen - ${MONAT_KURZ[createPreset.monat]} ${createPreset.jahr}`
              : "Monatsdaten erfassen"
        }
        size="xl"
      >
        <MonatsdatenForm
          anlageId={anlageId}
          onSubmit={handleCreate}
          onCancel={() => { setShowForm(false); setHaVorausfuellung(null); setCreatePreset(null) }}
          haVorausfuellung={haVorausfuellung}
          voreingestellterMonat={createPreset}
        />
      </Modal>

      {/* Edit Modal */}
      <Modal
        isOpen={!!editingData}
        onClose={() => { setEditingData(null); setHaVorausfuellung(null) }}
        title={haVorausfuellung ? `HA-Werte übernehmen - ${haVorausfuellung.monat_name} ${haVorausfuellung.jahr}` : "Monatsdaten bearbeiten"}
        size="xl"
      >
        {editingData && (
          <MonatsdatenForm
            monatsdaten={editingData}
            anlageId={anlageId}
            onSubmit={handleUpdate}
            onCancel={() => { setEditingData(null); setHaVorausfuellung(null) }}
            haVorausfuellung={haVorausfuellung}
          />
        )}
      </Modal>

      {/* Delete Confirmation */}
      <Modal isOpen={!!deleteConfirm} onClose={() => setDeleteConfirm(null)} title="Monatsdaten löschen" size="sm">
        <div className="space-y-4">
          <p className="text-gray-600 dark:text-gray-300">
            Möchtest du die Daten für <strong>{MONAT_KURZ[deleteConfirm?.monat || 0]} {deleteConfirm?.jahr}</strong> wirklich löschen?
          </p>

          {/* #349: Ein Monat besteht aus zwei Teilen — der Zählerzeile und den
              Messwerten je Komponente. Beide gehen zusammen (12.08.): Einspeisung
              und Netzbezug sind Pflichtfelder, eine Hälfte allein zu löschen
              ergibt keinen darstellbaren Zustand. Bis dahin blieben die
              Gerätewerte per Vorgabe stehen — der Monat war scheinbar weg und
              wies trotzdem jeden erneuten Import ab. */}
          {geraetewerte && geraetewerte.anzahl > 0 && (
            <Alert type="warning">
              <div>
                Dazu gehören Messwerte von{' '}
                <strong>{geraetewerte.anzahl} Komponente{geraetewerte.anzahl > 1 ? 'n' : ''}</strong>{' '}
                ({geraetewerte.komponenten.map(k => k.bezeichnung).join(', ')}).
                Sie werden <strong>mitgelöscht</strong>.
              </div>
              <div className="mt-1 text-sm">
                Nur die Zählerwerte zu löschen ist nicht möglich — der Monat wäre
                danach in keiner Liste zu sehen und würde trotzdem jeden erneuten
                Import abweisen.
              </div>
            </Alert>
          )}

          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setDeleteConfirm(null)}>Abbrechen</Button>
            <Button variant="danger" onClick={handleDelete}>
              {geraetewerte && geraetewerte.anzahl > 0
                ? 'Monat vollständig löschen'
                : 'Löschen'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

// ─── Hilfskomponente: Vergleichszeile HA vs. Vorhanden ────────────────────────

function VergleichsZeile({
  label,
  vorhanden,
  haWert,
}: {
  label: string
  vorhanden: number | null | undefined
  haWert: number | null | undefined
}) {
  const vorhandenVal = vorhanden ?? null
  const haVal = haWert ?? null

  // Berechne Differenz
  let diff: number | null = null
  let diffClass = ''
  if (vorhandenVal !== null && haVal !== null) {
    diff = haVal - vorhandenVal
    if (Math.abs(diff) < 0.1) {
      diffClass = 'text-gray-500'
    } else if (diff > 0) {
      diffClass = 'text-green-600 dark:text-green-400'
    } else {
      diffClass = 'text-red-600 dark:text-red-400'
    }
  }

  const formatVal = (val: number | null) => (val !== null ? fmtZahl(val, 1) : '–')

  // Hervorhebung wenn unterschiedlich
  const isDifferent = vorhandenVal !== null && haVal !== null && Math.abs((haVal - vorhandenVal)) > 0.1

  return (
    <tr className={`border-b dark:border-gray-700 ${isDifferent ? 'bg-amber-50 dark:bg-amber-900/10' : ''}`}>
      <td className="py-2 px-3 font-medium">{label}</td>
      <td className="py-2 px-3 text-right text-blue-600 dark:text-blue-400">
        {formatVal(vorhandenVal)}
      </td>
      <td className="py-2 px-3 text-right text-green-600 dark:text-green-400 font-medium">
        {formatVal(haVal)}
      </td>
      <td className={`py-2 px-3 text-right font-medium ${diffClass}`}>
        {diff !== null ? (diff >= 0 ? '+' : '') + fmtZahl(diff, 1) : '–'}
      </td>
    </tr>
  )
}
