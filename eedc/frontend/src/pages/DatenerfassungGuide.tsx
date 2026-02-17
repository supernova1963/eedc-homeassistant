/**
 * Datenerfassung - Informationsseite
 *
 * v0.9.9: Vereinfacht - EEDC ist primär Standalone
 *
 * Diese Seite erklärt die Möglichkeiten zur Datenerfassung:
 * 1. Manuelles Formular (empfohlen für Einsteiger)
 * 2. CSV-Import (empfohlen für regelmäßige Erfassung)
 * 3. Optional: MQTT Export für KPIs nach HA
 */

import { useState } from 'react'
import {
  FileSpreadsheet,
  PenLine,
  Upload,
  ArrowRight,
  Info,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
} from 'lucide-react'

// Beispiel YAML für Utility Meter
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
    cycle: monthly

  # Speicher Entladung (optional)
  speicher_entladung_monatlich:
    source: sensor.DEIN_SPEICHER_discharge_total  # <- Anpassen!
    cycle: monthly

  # E-Auto Ladung (optional, z.B. von evcc)
  eauto_ladung_monatlich:
    source: sensor.evcc_loadpoint_charge_total_import  # <- Anpassen!
    cycle: monthly`

// Beispiel für File Export Automation
const FILE_EXPORT_YAML = `# Automation: Monatliche CSV-Export Datei erstellen
# Voraussetzung: File Integration muss eingerichtet sein

automation:
  - alias: "EEDC Monatsdaten Export"
    trigger:
      - platform: time
        at: "00:05:00"  # Am 1. des Monats um 00:05
    condition:
      - condition: template
        value_template: "{{ now().day == 1 }}"
    action:
      - service: notify.file_export  # <- Anpassen an deinen File Notifier
        data:
          message: >
            {{ (now() - timedelta(days=1)).year }},{{ (now() - timedelta(days=1)).month }},{{ states('sensor.einspeisung_monatlich') }},{{ states('sensor.netzbezug_monatlich') }},{{ states('sensor.pv_erzeugung_monatlich') }}

# Hinweis: Die CSV muss dann manuell in EEDC importiert werden
# oder du erweiterst die Automation um einen REST-Call zu EEDC`

export default function DatenerfassungGuide() {
  const [showYamlGuide, setShowYamlGuide] = useState(false)
  const [copiedYaml, setCopiedYaml] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedYaml(id)
    setTimeout(() => setCopiedYaml(null), 2000)
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
          So erfassen Sie Ihre monatlichen Energiedaten in EEDC
        </p>
      </div>

      {/* Hauptinhalt */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Option 1: Manuelles Formular */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border-2 border-blue-200 dark:border-blue-800">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-3 bg-blue-100 dark:bg-blue-900 rounded-lg">
              <PenLine className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Manuelles Formular
              </h2>
              <span className="text-xs bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 px-2 py-0.5 rounded">
                Empfohlen für Einsteiger
              </span>
            </div>
          </div>

          <p className="text-gray-600 dark:text-gray-400 mb-4">
            Geben Sie Ihre Monatsdaten direkt im Formular ein.
            Ideal für gelegentliche Erfassung oder wenn Sie nur wenige Werte haben.
          </p>

          <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400 mb-4">
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-blue-500" />
              Einstellungen → Monatsdaten → Neu
            </li>
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-blue-500" />
              Wetterdaten können automatisch geladen werden
            </li>
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-blue-500" />
              Investitions-Daten pro Komponente erfassen
            </li>
          </ul>

          <a
            href="#/einstellungen/monatsdaten"
            className="btn btn-primary w-full flex items-center justify-center gap-2"
          >
            <PenLine className="w-4 h-4" />
            Zur Monatsdaten-Erfassung
          </a>
        </div>

        {/* Option 2: CSV-Import */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border-2 border-green-200 dark:border-green-800">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-3 bg-green-100 dark:bg-green-900 rounded-lg">
              <Upload className="w-6 h-6 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                CSV-Import
              </h2>
              <span className="text-xs bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300 px-2 py-0.5 rounded">
                Empfohlen für regelmäßige Erfassung
              </span>
            </div>
          </div>

          <p className="text-gray-600 dark:text-gray-400 mb-4">
            Laden Sie Monatsdaten per CSV-Datei hoch.
            Perfekt für größere Datenmengen oder historische Daten.
          </p>

          <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400 mb-4">
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-green-500" />
              Einstellungen → Import/Export
            </li>
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-green-500" />
              Vorlage herunterladen (passt zu Ihren Investitionen)
            </li>
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-green-500" />
              Wetterdaten werden automatisch ergänzt
            </li>
          </ul>

          <a
            href="#/einstellungen/import"
            className="btn btn-primary w-full flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700"
          >
            <Upload className="w-4 h-4" />
            Zum CSV-Import
          </a>
        </div>
      </div>

      {/* Info-Box für HA-User */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-6">
        <div className="flex items-start gap-4">
          <Info className="w-6 h-6 text-blue-500 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-blue-800 dark:text-blue-200 mb-2">
              Hinweis für Home Assistant Benutzer
            </h3>
            <p className="text-blue-700 dark:text-blue-300 text-sm mb-3">
              EEDC ist als Standalone-Anwendung konzipiert und benötigt keine Home Assistant Integration
              für die Datenerfassung. Sie können Ihre Daten aus HA manuell in eine CSV-Datei exportieren
              und in EEDC importieren.
            </p>
            <p className="text-blue-700 dark:text-blue-300 text-sm mb-3">
              <strong>Optional:</strong> Unter Einstellungen → HA-Export können Sie berechnete KPIs
              (Autarkie, Eigenverbrauch, etc.) per MQTT zurück an Home Assistant senden.
            </p>
            <div className="flex flex-wrap gap-2 mt-4">
              <a
                href="#/einstellungen/ha-export"
                className="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
              >
                <ExternalLink className="w-3 h-3" />
                HA-Export Einstellungen
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* Aufklappbare HA CSV-Export Anleitung */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setShowYamlGuide(!showYamlGuide)}
          className="w-full p-4 flex items-center justify-between text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors rounded-lg"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-100 dark:bg-orange-900 rounded-lg">
              <FileSpreadsheet className="w-5 h-5 text-orange-600 dark:text-orange-400" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-white">
                Anleitung: CSV aus Home Assistant erstellen
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                So richten Sie Utility Meter ein, um monatliche Werte für EEDC zu exportieren
              </p>
            </div>
          </div>
          {showYamlGuide ? (
            <ChevronUp className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          )}
        </button>

        {showYamlGuide && (
          <div className="px-4 pb-4 space-y-6 border-t border-gray-200 dark:border-gray-700 pt-4">
            {/* Schritt 1: Utility Meter */}
            <div>
              <h4 className="font-medium text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-orange-500 text-white text-sm flex items-center justify-center">1</span>
                Utility Meter einrichten
              </h4>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                Utility Meter aggregieren Ihre Sensordaten monatlich. Fügen Sie folgendes in Ihre{' '}
                <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">configuration.yaml</code> ein
                und passen Sie die Sensor-IDs an:
              </p>
              <div className="relative">
                <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg text-xs overflow-x-auto max-h-64">
                  {UTILITY_METER_YAML}
                </pre>
                <button
                  onClick={() => copyToClipboard(UTILITY_METER_YAML, 'utility')}
                  className="absolute top-2 right-2 p-2 bg-gray-700 hover:bg-gray-600 rounded text-gray-300"
                  title="In Zwischenablage kopieren"
                >
                  {copiedYaml === 'utility' ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            {/* Schritt 2: Sensoren identifizieren */}
            <div>
              <h4 className="font-medium text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-orange-500 text-white text-sm flex items-center justify-center">2</span>
                Ihre Sensoren finden
              </h4>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                So finden Sie die richtigen Sensor-IDs in Home Assistant:
              </p>
              <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1 ml-4">
                <li>• <strong>Entwicklerwerkzeuge → Zustände</strong> in HA öffnen</li>
                <li>• Nach "total" oder "energy" filtern</li>
                <li>• Sensoren mit <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">state_class: total_increasing</code> sind ideal</li>
                <li>• Typische Namen: <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">*_total_yield</code>, <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">*_energy</code>, <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">*_import</code>, <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">*_export</code></li>
              </ul>
            </div>

            {/* Schritt 3: CSV-Format */}
            <div>
              <h4 className="font-medium text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-orange-500 text-white text-sm flex items-center justify-center">3</span>
                CSV-Datei erstellen
              </h4>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Am Monatsende die Utility Meter Werte ablesen und in eine CSV eintragen:
              </p>
              <div className="bg-gray-100 dark:bg-gray-700 p-3 rounded-lg text-xs font-mono overflow-x-auto">
                <div className="text-gray-500 dark:text-gray-400">// Pflicht-Spalten:</div>
                <div>Jahr,Monat,Einspeisung_kWh,Netzbezug_kWh</div>
                <div className="text-gray-500 dark:text-gray-400 mt-2">// Beispiel:</div>
                <div>2025,12,125.9,405.5</div>
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                <strong>Tipp:</strong> Laden Sie unter Import/Export eine Vorlage herunter - sie enthält alle Spalten
                passend zu Ihren angelegten Investitionen!
              </p>
            </div>

            {/* Schritt 4: Optional - Automatisierung */}
            <div>
              <h4 className="font-medium text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-gray-400 text-white text-sm flex items-center justify-center">4</span>
                <span className="text-gray-500">(Optional)</span> Automatischer Export
              </h4>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                Für Fortgeschrittene: Mit der File-Integration und einer Automation können Sie die CSV
                automatisch erstellen lassen:
              </p>
              <div className="relative">
                <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg text-xs overflow-x-auto max-h-48">
                  {FILE_EXPORT_YAML}
                </pre>
                <button
                  onClick={() => copyToClipboard(FILE_EXPORT_YAML, 'file')}
                  className="absolute top-2 right-2 p-2 bg-gray-700 hover:bg-gray-600 rounded text-gray-300"
                  title="In Zwischenablage kopieren"
                >
                  {copiedYaml === 'file' ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            {/* Hinweis */}
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
              <p className="text-sm text-yellow-800 dark:text-yellow-200">
                <strong>Wichtig:</strong> Utility Meter werden bei HA-Neustart zurückgesetzt, es sei denn,
                Sie haben den Recorder korrekt konfiguriert. Alternativ können Sie auch die "Statistik"-Werte
                aus dem HA Energy Dashboard verwenden.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Tipps */}
      <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-6">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
          💡 Tipps für die Datenerfassung
        </h3>
        <ul className="space-y-3 text-sm text-gray-600 dark:text-gray-400">
          <li className="flex items-start gap-2">
            <span className="text-lg">📅</span>
            <span>
              <strong>Regelmäßigkeit:</strong> Erfassen Sie Ihre Daten am besten immer am
              gleichen Tag im Monat (z.B. am 1. oder letzten Tag).
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-lg">📊</span>
            <span>
              <strong>Zählerstände:</strong> Notieren Sie die Zählerstände Ihrer Wechselrichter,
              Speicher und Wallbox. EEDC erwartet Monatswerte (Differenz zum Vormonat).
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-lg">☀️</span>
            <span>
              <strong>Wetterdaten:</strong> Globalstrahlung und Sonnenstunden werden automatisch
              aus Open-Meteo geladen, wenn Ihre Anlage Koordinaten hat.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-lg">🚗</span>
            <span>
              <strong>E-Auto:</strong> Bei externem Laden (öffentliche Säulen) können Sie
              Ladung und Kosten separat erfassen.
            </span>
          </li>
        </ul>
      </div>
    </div>
  )
}
