/**
 * N-237 — die Gate-Regel der Einstellungs-Kacheln, als Regel geprüft.
 *
 * Vorher stand sie als Ausdruck im Rendering (`e.haOnly && !haVerfuegbar`) und
 * kannte nur eine Voraussetzung: „läuft als Add-on". Wer Home Assistant per
 * Long-Lived-Token angebunden hatte, bekam damit auch die Flächen gesperrt, die
 * seine Verbindung sehr wohl tragen kann — allen voran den Statistik-Import.
 */

import { describe, expect, it } from 'vitest'

import {
  EINSTELLUNGEN_KATALOG,
  fehlendeHAVoraussetzung,
} from './einstellungenKatalog'

const ADDON = { addon: true, verbunden: true }
const TOKEN = { addon: false, verbunden: true }
const OHNE_HA = { addon: false, verbunden: false }

describe('fehlendeHAVoraussetzung', () => {
  it('lässt Einträge ohne HA-Bedarf immer durch', () => {
    for (const umgebung of [ADDON, TOKEN, OHNE_HA]) {
      expect(fehlendeHAVoraussetzung({}, umgebung)).toBeNull()
    }
  })

  it('sperrt Supervisor-Flächen für den Token-Betrieb — und benennt den Grund', () => {
    const eintrag = { haOnly: 'supervisor' as const }
    expect(fehlendeHAVoraussetzung(eintrag, ADDON)).toBeNull()
    expect(fehlendeHAVoraussetzung(eintrag, TOKEN)).toBe('supervisor')
    expect(fehlendeHAVoraussetzung(eintrag, OHNE_HA)).toBe('supervisor')
  })

  it('öffnet Verbindungs-Flächen für den Token-Betrieb', () => {
    const eintrag = { haOnly: 'verbindung' as const }
    expect(fehlendeHAVoraussetzung(eintrag, ADDON)).toBeNull()
    // Der eigentliche Fehler von N-237: hier stand vorher eine Sperre.
    expect(fehlendeHAVoraussetzung(eintrag, TOKEN)).toBeNull()
    expect(fehlendeHAVoraussetzung(eintrag, OHNE_HA)).toBe('verbindung')
  })
})

describe('Katalog', () => {
  it('führt den Statistik-Import als Verbindungs-Fläche, nicht als Add-on-Fläche', () => {
    const eintrag = EINSTELLUNGEN_KATALOG.find((e) => e.id === 'ha-statistik-import')
    expect(eintrag, 'Eintrag ha-statistik-import fehlt im Katalog').toBeDefined()
    expect(eintrag!.haOnly).toBe('verbindung')
    expect(fehlendeHAVoraussetzung(eintrag!, TOKEN)).toBeNull()
  })

  it('kennt keine Stufe außer den beiden definierten', () => {
    // Ein `haOnly: true` aus der Zeit vor N-237 würde als Wahrheitswert weiter
    // sperren, aber nie mehr zu 'supervisor'/'verbindung' passen — dieser
    // Wächter fängt es, statt es still durchzureichen.
    for (const e of EINSTELLUNGEN_KATALOG) {
      if (e.haOnly === undefined) continue
      expect(['supervisor', 'verbindung'], `Eintrag ${e.id}`).toContain(e.haOnly)
    }
  })
})
