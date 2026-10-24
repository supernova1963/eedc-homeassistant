/**
 * Die WP-Fälle der Datenquellen-Route als Antwortform (P-433-2 S2, E3) — für die Client-Proben.
 *
 * Quelle ist `datenquellen-wp-faelle.json`, eine Projektion der echten Route, gehalten von
 * `backend/tests/test_p433_2_datenquellen_betriebsart.py::test_fixture_der_client_probe_ist_aktuell`.
 * Ergänzt werden nur IDs und die Begleitfelder, die die Projektion weglässt.
 */
import faelle from './datenquellen-wp-faelle.json'
import type { DatenquelleFeld, DatenquelleGruppe } from '../api/datenquellen'

export type WpFall = keyof typeof faelle
export const WP_FAELLE = Object.keys(faelle) as WpFall[]

export function gruppeAusFall(name: WpFall, invId = 5): DatenquelleGruppe {
  const f = faelle[name]
  return {
    id: `inv:${invId}`, titel: f.titel, typ: 'waermepumpe', kuehlung_art: f.kuehlung_art, modus_ableitbar: f.modus_ableitbar,
    felder: f.felder.map((x) => ({
      ...x, id: `inv_${invId}_${x.feld}`, typ: 'waermepumpe', hinweis: '', standard_topic: '', gateway_topic: null,
      ha_entity: x.quelle === 'keine' ? null : `sensor.${x.feld}`, ha_name: null, invertieren: false,
      wert: x.quelle === 'keine' ? null : 1, wert_zeit: null, probleme: [], bedarf_grund: null,
    })) as DatenquelleFeld[],
  }
}
