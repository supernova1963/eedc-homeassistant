import type { SelectItem } from '../ui/Select'
import type { AnalyzeResult } from '../../api/customImport'

/**
 * Zielfeld-Optionen für die Spalten-Zuordnung im CustomImportWizard (Schritt 2).
 * Ausgelagert aus dem Wizard, damit die große statische Optgroup-Liste den
 * Wizard-Shell nicht aufbläht und der SoT-`Select` sie direkt konsumieren kann.
 *
 * „Jahr"/„Monat" werden deaktiviert, sobald sie in einer anderen Spalte belegt
 * sind (nur einmal zuweisbar); die dynamischen Investitions-Felder kommen aus
 * `analysis.investitions_felder`, gruppiert nach Investitionstyp.
 */

const INV_GROUP_LABELS: Record<string, string> = {
  inv_pv: 'PV-Module (einzeln)',
  inv_speicher: 'Speicher (einzeln)',
  inv_eauto: 'E-Autos (einzeln)',
  inv_wallbox: 'Wallboxen (einzeln)',
  inv_wp: 'Wärmepumpen (einzeln)',
  inv_bkw: 'Balkonkraftwerke (einzeln)',
  inv_sonstiges: 'Sonstiges (einzeln)',
}

export function mappingZielOptionen(
  analysis: AnalyzeResult,
  mappings: Record<string, string>,
  currentMapping: string,
): SelectItem[] {
  const jahrBelegt = Object.values(mappings).includes('jahr') && currentMapping !== 'jahr'
  const monatBelegt = Object.values(mappings).includes('monat') && currentMapping !== 'monat'

  const items: SelectItem[] = [
    {
      label: 'Zeit',
      options: [
        { value: 'jahr', label: 'Jahr', disabled: jahrBelegt },
        { value: 'monat', label: 'Monat', disabled: monatBelegt },
      ],
    },
    {
      label: 'Energie (Anlage gesamt)',
      options: [
        { value: 'pv_erzeugung_kwh', label: 'PV-Erzeugung gesamt (kWh)' },
        { value: 'einspeisung_kwh', label: 'Einspeisung (kWh)' },
        { value: 'netzbezug_kwh', label: 'Netzbezug (kWh)' },
        { value: 'eigenverbrauch_kwh', label: 'Eigenverbrauch (kWh)' },
      ],
    },
    {
      label: 'Batterie (Anlage gesamt)',
      options: [
        { value: 'batterie_ladung_kwh', label: 'Batterie Ladung gesamt (kWh)' },
        { value: 'batterie_entladung_kwh', label: 'Batterie Entladung gesamt (kWh)' },
      ],
    },
    {
      label: 'Wallbox / E-Auto (Anlage gesamt)',
      options: [
        { value: 'wallbox_ladung_kwh', label: 'Wallbox Ladung (kWh)' },
        { value: 'wallbox_ladung_pv_kwh', label: 'Wallbox PV-Ladung (kWh)' },
        { value: 'wallbox_ladevorgaenge', label: 'Wallbox Ladevorgänge' },
        { value: 'eauto_km_gefahren', label: 'E-Auto Gefahrene km' },
      ],
    },
  ]

  const invFelder = analysis.investitions_felder ?? []
  if (invFelder.length > 0) {
    const groups: Record<string, typeof invFelder> = {}
    for (const f of invFelder) {
      if (!groups[f.group]) groups[f.group] = []
      groups[f.group].push(f)
    }
    for (const [group, felder] of Object.entries(groups)) {
      items.push({
        label: INV_GROUP_LABELS[group] ?? group,
        options: felder.map((f) => ({ value: f.id, label: f.label })),
      })
    }
  }

  return items
}
