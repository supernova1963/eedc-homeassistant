/**
 * Formatierungs-Helfer für die Connector-Anzeigen (aus ConnectorSetupWizard
 * ausgelagert beim V4-Umbau). Reine Darstellung — de-DE, kein Zustand.
 */

export function formatKwh(val: number | null | undefined): string {
  if (val == null) return '–'
  return val.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' kWh'
}

export function formatDate(iso: string | undefined): string {
  if (!iso) return '–'
  try {
    return new Date(iso).toLocaleString('de-DE')
  } catch {
    return iso
  }
}

export function fieldLabel(key: string): string {
  const labels: Record<string, string> = {
    pv_erzeugung_kwh: 'PV-Erzeugung',
    einspeisung_kwh: 'Einspeisung',
    netzbezug_kwh: 'Netzbezug',
    batterie_ladung_kwh: 'Batterie Ladung',
    batterie_entladung_kwh: 'Batterie Entladung',
    wallbox_ladung_kwh: 'Wallbox Ladung',
  }
  return labels[key] || key
}
