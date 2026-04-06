import React from 'react'
import {
  Sun,
  Battery,
  Thermometer,
  Car,
  Zap,
  Wrench,
} from 'lucide-react'

export const TYP_ICONS: Record<string, React.ReactNode> = {
  'pv-module': React.createElement(Sun, { className: 'w-5 h-5' }),
  speicher: React.createElement(Battery, { className: 'w-5 h-5' }),
  waermepumpe: React.createElement(Thermometer, { className: 'w-5 h-5' }),
  'e-auto': React.createElement(Car, { className: 'w-5 h-5' }),
  wallbox: React.createElement(Zap, { className: 'w-5 h-5' }),
  balkonkraftwerk: React.createElement(Sun, { className: 'w-5 h-5' }),
  sonstiges: React.createElement(Wrench, { className: 'w-5 h-5' }),
}

export function getTypLabel(typ: string): string {
  const labels: Record<string, string> = {
    'pv-module': 'PV-Module',
    wechselrichter: 'Wechselrichter',
    speicher: 'Speicher',
    waermepumpe: 'Wärmepumpe',
    'e-auto': 'E-Auto',
    wallbox: 'Wallbox',
    balkonkraftwerk: 'Balkonkraftwerk',
    sonstiges: 'Sonstiges',
  }
  return labels[typ] || typ
}

export function getQuelleLabel(quelle: string): string {
  const labels: Record<string, string> = {
    ha_statistics: 'HA-Statistik',
    ha_sensor: 'HA-Sensor',
    cron_snapshot: 'Snapshot',
    local_connector: 'Connector',
    mqtt_inbound: 'MQTT Energy',
    portal_import: 'Portal-Import',
    cloud_import: 'Cloud-Import',
    vormonat: 'Vormonat',
    vorjahr: 'Vorjahr',
    berechnung: 'Berechnet',
    durchschnitt: 'Durchschnitt',
    parameter: 'Parameter',
  }
  return labels[quelle] || quelle
}

export function getDatenquelleLabel(datenquelle: string): string {
  const labels: Record<string, string> = {
    manual: 'Manuelle Eingabe',
    csv: 'CSV-Import',
    ha_import: 'HA-Statistik-Import',
    portal_import: 'Portal-Import (CSV)',
    cloud_import: 'Cloud-Import (API)',
    mqtt_inbound: 'MQTT Energy-Topics',
    cron_snapshot: 'Automatischer Snapshot',
  }
  return labels[datenquelle] || datenquelle
}
