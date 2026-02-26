/**
 * Datenerfassung - Informationsseite (v2.4+)
 *
 * Erklärt die modernen Wege zur Datenerfassung:
 * 1. HA-Statistik-Import (Primär für HA-User, ab v2.0)
 * 2. Monatsabschluss-Wizard (Empfohlen für alle, ab v1.1)
 * 3. Manuelles Formular (Ergänzung)
 * 4. CSV-Import (Legacy/Bulk-Import)
 * 5. Appendix: Utility Meter Anleitung (Legacy, aufklappbar)
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  FileSpreadsheet,
  PenLine,
  Upload,
  ArrowRight,
  Info,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  CalendarCheck,
  BarChart2,
  MapPin,
  Star,
} from 'lucide-react'

// Beispiel YAML für Utility Meter (Legacy-Anleitung, aufklappbar)
const UTILITY_METER_YAML = `# Utility Meter für monatliche Aggregation
# Füge dies in deine configuration.yaml ein

utility_meter:
  # PV-Erzeugung (von deinem Wechselrichter)
  pv_erzeugung_monatlich:
    source: sensor.DEIN_WR_total_yield  # <- Anpassen!
    cycle: monthly

  # Einspeisung ins Netz
  einspeisung_monatlich:
    source: sensor.DEIN_ZAEHLER_export  # <- Anpassen!
    cycle: monthly

  # Netzbezug
  netzbezug_monatlich:
    source: sensor.DEIN_ZAEHLER_import  # <- Anpassen!
    cycle: monthly

  # Speicher Ladung (optional)
  speicher_ladung_monatlich:
    source: sensor.DEIN_SPEICHER_charge_total  # <- Anpassen!
    cycle: monthly`

export default function DatenerfassungGuide() {
  const [showLegacyGuide, setShowLegacyGuide] = useState(false)
  const [copied, setCopied] = useState(false)

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <FileSpreadsheet className="w-6 h-6" />
          Datenerfassung
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Wie Sie Ihre monatlichen Energiedaten in EEDC erfassen
        </p>
      </div>

      {/* Empfohlener Workflow */}
      <div className="bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 rounded-lg p-5">
        <div className="flex items-start gap-3">
          <Star className="w-5 h-5 text-primary-600 dark:text-primary-400 flex-shrink-0 mt-0.5" />
          <div>
            <h2 className="font-semibold text-primary-800 dark:text-primary-200 mb-1">
              Empfohlener Workflow
            </h2>
            <p className="text-sm text-primary-700 dark:text-primary-300">
              Einmalig: <strong>Sensor-Zuordnung</strong> konfigurieren →
              Monatlich: <strong>Monatsabschluss-Wizard</strong> aufrufen (Werte direkt aus HA laden oder manuell eingeben)
            </p>
          </div>
        </div>
      </div>

      {/* Primäre Methoden */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* Option 1: HA-Statistik-Import */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border-2 border-primary-200 dark:border-primary-800">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-3 bg-primary-100 dark:bg-primary-900 rounded-lg">
              <BarChart2 className="w-6 h-6 text-primary-600 dark:text-primary-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                HA-Statistik-Import
              </h2>
              <span className="text-xs bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300 px-2 py-0.5 rounded">
                Primär für HA-Benutzer
              </span>
            </div>
          </div>

          <p className="text-gray-600 dark:text-gray-400 mb-4 text-sm">
            Liest Monatswerte direkt aus der Home Assistant Langzeitstatistik.
            Rückwirkend für alle vorhandenen Monate seit Installation.
          </p>

          <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400 mb-4">
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-primary-500" />
              Kein manuelles Ablesen notwendig
            </li>
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-primary-500" />
              Bulk-Import aller Monate seit Installation
            </li>
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-primary-500" />
              Konflikterkennung – vorhandene Daten werden geschützt
            </li>
          </ul>

          <Link
            to="/einstellungen/ha-statistik-import"
            className="btn btn-primary w-full flex items-center justify-center gap-2"
          >
            <BarChart2 className="w-4 h-4" />
            Zum HA-Statistik-Import
          </Link>
        </div>

        {/* Option 2: Monatsabschluss-Wizard */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border-2 border-green-200 dark:border-green-800">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-3 bg-green-100 dark:bg-green-900 rounded-lg">
              <CalendarCheck className="w-6 h-6 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Monatsabschluss-Wizard
              </h2>
              <span className="text-xs bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300 px-2 py-0.5 rounded">
                Empfohlen für alle
              </span>
            </div>
          </div>

          <p className="text-gray-600 dark:text-gray-400 mb-4 text-sm">
            Geführte Eingabe aller Monatsdaten in einem Schritt – inklusive
            Zählerwerte, Komponenten-Daten und Sonstige Positionen.
          </p>

          <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400 mb-4">
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-green-500" />
              Vorschläge aus HA-Sensoren oder historischen Werten
            </li>
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-green-500" />
              Vollständig: alle Komponenten in einem Formular
            </li>
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-green-500" />
              Plausibilitätsprüfung und Warnungen
            </li>
          </ul>

          <Link
            to="/einstellungen/monatsabschluss"
            className="btn btn-primary w-full flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700"
          >
            <CalendarCheck className="w-4 h-4" />
            Zum Monatsabschluss
          </Link>
        </div>
      </div>

      {/* Einmalige Einrichtung: Sensor-Zuordnung */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-5">
        <div className="flex items-start gap-4">
          <MapPin className="w-6 h-6 text-blue-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <h3 className="font-semibold text-blue-800 dark:text-blue-200 mb-1">
              Einmalige Einrichtung: Sensor-Zuordnung
            </h3>
            <p className="text-blue-700 dark:text-blue-300 text-sm mb-3">
              Verknüpfen Sie Ihre Home Assistant Sensoren einmalig mit den EEDC-Feldern.
              Danach werden im Monatsabschluss-Wizard automatisch Vorschläge aus HA geliefert.
            </p>
            <Link
              to="/einstellungen/sensor-mapping"
              className="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 w-fit"
            >
              <MapPin className="w-3 h-3" />
              Sensor-Zuordnung konfigurieren
            </Link>
          </div>
        </div>
      </div>

      {/* Weitere Optionen */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        {/* Manuelles Formular */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
              <PenLine className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            </div>
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Manuelles Formular
            </h3>
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
            Einzelne Monate direkt anlegen oder bearbeiten – z.B. für Korrekturen.
          </p>
          <Link
            to="/einstellungen/monatsdaten"
            className="text-sm text-primary-600 dark:text-primary-400 hover:underline flex items-center gap-1"
          >
            <ArrowRight className="w-3 h-3" />
            Zu Monatsdaten
          </Link>
        </div>

        {/* CSV-Import */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
              <Upload className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            </div>
            <h3 className="font-semibold text-gray-900 dark:text-white">
              CSV-Import
            </h3>
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
            Bulk-Import aus Tabellenkalkulationen oder externen Quellen.
            Vorlage im Import-Dialog herunterladen.
          </p>
          <Link
            to="/einstellungen/import"
            className="text-sm text-primary-600 dark:text-primary-400 hover:underline flex items-center gap-1"
          >
            <ArrowRight className="w-3 h-3" />
            Zum Import/Export
          </Link>
        </div>
      </div>

      {/* Tipps */}
      <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-5">
        <div className="flex items-start gap-2 mb-3">
          <Info className="w-5 h-5 text-gray-500 flex-shrink-0 mt-0.5" />
          <h3 className="font-semibold text-gray-900 dark:text-white">Tipps</h3>
        </div>
        <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400 ml-7">
          <li>
            <strong>EEDC erwartet Monatswerte</strong> (Differenz Monatsanfang → Monatsende),
            keine kumulierten Zählerstände.
          </li>
          <li>
            <strong>Wetterdaten</strong> (Globalstrahlung, Sonnenstunden) werden automatisch
            aus Open-Meteo geladen, wenn Ihre Anlage Koordinaten hat.
          </li>
          <li>
            <strong>Sonstige Erträge & Ausgaben</strong> (z.B. THG-Quote, Wartungskosten)
            können pro Investition im Monatsabschluss-Wizard erfasst werden.
          </li>
        </ul>
      </div>

      {/* Firmenwagen & dienstliches Laden */}
      <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-5">
        <div className="flex items-start gap-3 mb-3">
          <Info className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
          <h3 className="font-semibold text-amber-800 dark:text-amber-200">
            Firmenwagen & dienstliches Laden an der Wallbox
          </h3>
        </div>
        <p className="text-sm text-amber-700 dark:text-amber-300 mb-3">
          Wenn an Ihrer Wallbox ausschließlich Firmenwagen geladen werden (alle gefahrenen km
          sind erstattungspflichtig), unterscheidet sich die ROI-Berechnung grundlegend:
        </p>
        <ul className="space-y-1.5 text-sm text-amber-700 dark:text-amber-300 ml-4 mb-4">
          <li>
            <strong>Kosten:</strong> Netzbezug × Strompreis + PV-Anteil × Einspeisevergütung
            (= entgangene Einspeisung)
          </li>
          <li>
            <strong>Ertrag:</strong> AG-Erstattung (km-Pauschale) als "Sonstiger Ertrag"
            im Monatsabschluss erfassen
          </li>
          <li>
            <strong>Kein Benzinvergleich</strong> – der Kraftstoffvorteil geht an den
            Arbeitgeber, nicht an den Haushalt
          </li>
        </ul>
        <p className="text-sm text-amber-700 dark:text-amber-300 mb-3">
          <strong>Einrichtung:</strong> Aktivieren Sie das Flag "Ausschließlich dienstliches Laden"
          in den Wallbox-Parametern (Investitionen → Wallbox bearbeiten).
        </p>
        <div className="bg-amber-100 dark:bg-amber-900/40 rounded p-3 text-xs text-amber-800 dark:text-amber-300">
          <strong>Gemischte Nutzung (privat + dienstlich)?</strong> Legen Sie zwei separate
          Wallbox-Einträge an – einen ohne Flag für private Ladevorgänge, einen mit Flag für
          dienstliche Ladevorgänge. Das entspricht der empfohlenen Praxis mit separatem
          Zähler (steuerlich oft ohnehin sinnvoll).
        </div>
      </div>

      {/* Legacy: Utility Meter / CSV aus HA (aufklappbar) */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setShowLegacyGuide(!showLegacyGuide)}
          className="w-full p-4 flex items-center justify-between text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors rounded-lg"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-100 dark:bg-orange-900 rounded-lg">
              <FileSpreadsheet className="w-5 h-5 text-orange-600 dark:text-orange-400" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-white">
                Legacy: CSV aus Home Assistant erstellen
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Utility Meter einrichten und monatlich exportieren (ältere Methode)
              </p>
            </div>
          </div>
          {showLegacyGuide ? (
            <ChevronUp className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          )}
        </button>

        {showLegacyGuide && (
          <div className="px-4 pb-4 space-y-5 border-t border-gray-200 dark:border-gray-700 pt-4">
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-3">
              <p className="text-sm text-yellow-800 dark:text-yellow-200">
                <strong>Hinweis:</strong> Der HA-Statistik-Import (oben) ist die einfachere Alternative –
                er liest die HA Langzeitstatistiken direkt ohne Utility Meter Konfiguration.
              </p>
            </div>

            <div>
              <h4 className="font-medium text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-orange-500 text-white text-sm flex items-center justify-center">1</span>
                Utility Meter einrichten
              </h4>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                Fügen Sie folgendes in Ihre{' '}
                <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">configuration.yaml</code>{' '}
                ein und passen Sie die Sensor-IDs an:
              </p>
              <div className="relative">
                <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg text-xs overflow-x-auto max-h-64">
                  {UTILITY_METER_YAML}
                </pre>
                <button
                  onClick={() => copyToClipboard(UTILITY_METER_YAML)}
                  className="absolute top-2 right-2 p-2 bg-gray-700 hover:bg-gray-600 rounded text-gray-300"
                  title="In Zwischenablage kopieren"
                >
                  {copied ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            <div>
              <h4 className="font-medium text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-orange-500 text-white text-sm flex items-center justify-center">2</span>
                Sensoren identifizieren
              </h4>
              <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1 ml-2">
                <li>• <strong>Entwicklerwerkzeuge → Zustände</strong> in HA öffnen</li>
                <li>• Nach "total" oder "energy" filtern</li>
                <li>• Sensoren mit <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">state_class: total_increasing</code> sind ideal</li>
              </ul>
            </div>

            <div>
              <h4 className="font-medium text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-orange-500 text-white text-sm flex items-center justify-center">3</span>
                CSV-Datei erstellen
              </h4>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Am Monatsende die Utility Meter Werte ablesen und in eine CSV eintragen.
                Laden Sie im Import-Dialog eine Vorlage herunter – sie enthält alle Spalten
                passend zu Ihren Investitionen.
              </p>
              <div className="bg-gray-100 dark:bg-gray-700 p-3 rounded-lg text-xs font-mono overflow-x-auto">
                <div className="text-gray-500 dark:text-gray-400">// Mindestpflicht-Spalten:</div>
                <div>Jahr,Monat,Einspeisung_kWh,Netzbezug_kWh</div>
                <div className="text-gray-500 dark:text-gray-400 mt-2">// Beispiel:</div>
                <div>2025,12,125.9,405.5</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
