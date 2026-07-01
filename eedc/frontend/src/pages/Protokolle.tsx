/**
 * Protokolle (IST/V3) — dünner Komposer über die geteilten `ProtokolleTeile`.
 *
 * Der gesamte Inhalt (System-Log-Viewer + Aktivitätsprotokoll + Debug-/Neustart-
 * Toolbar) lebt in {@link ./ProtokolleTeile} als EINE Code-Wahrheit — dieselben
 * Teile speisen den IA-V4-Einstellungen-Block „Protokolle" (inline wie
 * Strompreise/Backup). App-level, kein Anlage-Bezug → keine Guards nötig.
 */
import { ProtokolleVerwaltung } from './ProtokolleTeile'

export default function Protokolle() {
  return <ProtokolleVerwaltung />
}
