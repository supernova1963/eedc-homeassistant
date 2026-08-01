/**
 * Stunden-Slot-Konvention (Client-SoT) — Spiegel von
 * `backend/core/berechnungen/slot_konvention.py`.
 *
 * **Backward (#144/#297):** Slot `h` trägt die Energie aus `[h-1, h)`.
 *   Slot 0  = `[Vortag 23:00, 00:00)`
 *   Slot 11 = `[10:00, 11:00)`
 *   Slot 23 = `[22:00, 23:00)`
 *
 * Alle Quellen (OpenMeteo, Solcast, IST-Snapshot, IST-LTS) legen dasselbe
 * physische Intervall in denselben Slot — das Backend hält das mit
 * `tests/test_slot_konvention_quellen.py` fest. **Der Client darf diese
 * Zuordnung nicht ein zweites Mal erfinden:** jede Sicht, die sich ihre
 * Zeitspanne selbst zusammenbaut, driftet früher oder später gegen die
 * Nachbarsicht (Rainer PN 90106, 2026-08-01 — Cockpit → Live beschriftete
 * denselben Punkt vorwärts, den Auswertungen → Prognose rückwärts
 * beschriftete, und die IST-Kurve lag dort eine Stunde neben der Prognose).
 *
 * Wer eine Stunde beschriftet oder einen Messwert/Zeitpunkt in einen Slot
 * einsortiert, nimmt eine der drei Funktionen hier.
 */

/** `06:00–07:00 Uhr` für Slot 7 — die Zeitspanne, die der Slot trägt. */
export function slotZeitspanne(slot: number): string {
  const ende = ((slot % 24) + 24) % 24
  const beginn = (ende + 23) % 24
  return `${String(beginn).padStart(2, '0')}:00–${String(ende).padStart(2, '0')}:00 Uhr`
}

/**
 * Slot für ein Intervall, das um `stunde:00` **beginnt** (Messreihen mit
 * Slot-Beginn-Stempel, z. B. die 10-Minuten-Punkte des Tagesverlaufs).
 * Das Intervall endet in `stunde+1` → Backward-Slot `stunde+1`.
 *
 * Der Rückgabewert **24 ist gewollt** und heißt: gehört in Slot 0 des
 * Folgetags. Im Tagesraster 0…23 ist er damit nicht mehr enthalten — wer
 * modulo rechnet, kippt die letzte Stunde des Tages an dessen Anfang.
 * Analog zu `backward_slot_aus_period_start` im Backend.
 */
export function slotAusIntervallStart(stunde: number): number {
  return stunde + 1
}

/**
 * Slot, in den ein **Zeitpunkt** `"HH:MM"` fällt (Sonnenaufgang, Solar Noon,
 * „jetzt"). Ein Zeitpunkt mitten in der Stunde gehört in den Slot, der auf
 * die volle Stunde endet; ein Zeitpunkt exakt auf `HH:00` ist die Grenze und
 * damit das Ende von Slot `HH`. Analog zu `backward_slot_aus_period_end`.
 *
 * `"05:56"` → 6 · `"06:00"` → 6 · `"23:30"` → 24 (Slot 0 des Folgetags).
 */
export function slotAusZeitpunkt(zeit: string): number | null {
  const m = /^(\d{1,2}):(\d{2})/.exec(zeit.trim())
  if (!m) return null
  const stunde = parseInt(m[1], 10)
  const minute = parseInt(m[2], 10)
  if (Number.isNaN(stunde) || Number.isNaN(minute)) return null
  return minute === 0 ? stunde : stunde + 1
}
