/**
 * useEinstellungenStatus — Status-Badge je Einstellungs-Katalog-Eintrag (Schritt 3).
 *
 * Liefert pro `EINSTELLUNGEN_KATALOG`-Eintrag-`id` einen {@link KachelStatus}
 * (`ok`/`warn`/`neu`) + optionalen `hinweis` (Tooltip-Grund). **Kein zweiter
 * Severity-Kanon**: alle Werte werden aus schon vorhandenen Signalen aggregiert
 * und die Daten-Checker-Schwere (`config/datenCheckerKategorien`) nur auf die drei
 * Badge-Zustände projiziert.
 *
 * Quellen (Plan §3-Tabelle) — Detail-APIs höchstens 1×/aggregiert:
 *   - {@link useGlobalStatus}: EINE `check()`-Antwort (Aggregat + Kategorie-Befunde)
 *     + MQTT-Inbound-Status. Deckt Anlage/Strompreise/Sensor-Zuordnung/Daten-Checker/
 *     MQTT-Export/MQTT-Inbound ab.
 *   - {@link useSelectedAnlage}/{@link useInvestitionen}: Anlage-Existenz,
 *     Community-Auto-Share, Komponenten-Anzahl (Context/Liste, kein Extra-Roundtrip
 *     über das ohnehin Geladene hinaus).
 *   - {@link pvgisApi.getAktivePrognose}: Alter der aktiven Solarprognose (einziger
 *     zusätzlicher Read — nicht in `useGlobalStatus` vorhanden).
 *
 * Kein Signal → kein Eintrag im Map → EinstellungenV4 rendert **kein** Badge
 * (z. B. Backup: die App hat kein Backup-Alter-Signal — kein erfundenes ✓).
 */
import { useEffect, useState } from 'react'
import type { CheckErgebnis } from '../api/datenChecker'
import type { CheckSchwere } from '../config/datenCheckerKategorien'
import { pvgisApi, type AktivePrognoseResponse } from '../api/pvgis'
import { useGlobalStatus } from '../v4/status/useGlobalStatus'
import { useSelectedAnlage } from './useSelectedAnlage'

export type KachelStatus = 'ok' | 'warn' | 'neu'

export interface EinstellungStatus {
  status: KachelStatus
  /** Tooltip-Grund (v. a. bei `warn`/`neu`). */
  hinweis?: string
}

/** Katalog-Eintrag-`id` → Status. Nur Einträge mit belegtem Signal sind enthalten. */
export type EinstellungStatusMap = Record<string, EinstellungStatus>

const SCHWERE_RANG: Record<CheckSchwere, number> = { error: 3, warning: 2, info: 1, ok: 0 }

/** Schlimmster Befund unter den gegebenen Daten-Checker-Kategorien (oder null). */
function schlimmster(erg: CheckErgebnis[], kategorien: string[]): CheckErgebnis | null {
  let best: CheckErgebnis | null = null
  for (const e of erg) {
    if (!kategorien.includes(e.kategorie)) continue
    if (!best || SCHWERE_RANG[e.schwere] > SCHWERE_RANG[best.schwere]) best = e
  }
  return best
}

/**
 * Projiziert eine Daten-Checker-Schwere auf den Badge-Status (kein 2. Kanon):
 * error/warning → `warn` (Tooltip = Meldung), info/ok → `ok`.
 */
function ausSchwere(e: CheckErgebnis): EinstellungStatus {
  const warn = e.schwere === 'error' || e.schwere === 'warning'
  return warn ? { status: 'warn', hinweis: e.meldung } : { status: 'ok' }
}

export function useEinstellungenStatus(): EinstellungStatusMap {
  const { mqtt, datencheckErgebnisse, anlageId } = useGlobalStatus()
  const { selectedAnlage } = useSelectedAnlage()

  const [prognose, setPrognose] = useState<AktivePrognoseResponse | null>(null)
  const [prognoseGeladen, setPrognoseGeladen] = useState(false)

  useEffect(() => {
    if (!anlageId) { setPrognose(null); setPrognoseGeladen(false); return }
    let aktiv = true
    setPrognoseGeladen(false)
    pvgisApi.getAktivePrognose(anlageId)
      .then((p) => { if (aktiv) { setPrognose(p); setPrognoseGeladen(true) } })
      .catch(() => { if (aktiv) { setPrognose(null); setPrognoseGeladen(true) } })
    return () => { aktiv = false }
  }, [anlageId])

  const map: EinstellungStatusMap = {}
  const erg = datencheckErgebnisse

  // ── Stammdaten ──
  // Anlage: Existenz ist das primäre Signal; sonst Kategorie-Schwere „stammdaten".
  if (!selectedAnlage) {
    map.anlage = { status: 'neu', hinweis: 'Noch keine Anlage angelegt.' }
  } else if (erg) {
    const s = schlimmster(erg, ['stammdaten'])
    map.anlage = s ? ausSchwere(s) : { status: 'ok' }
  }

  // Strompreise: Kategorie-Abdeckung aus dem Daten-Checker (still = lückenlos).
  if (selectedAnlage && erg) {
    const s = schlimmster(erg, ['strompreise'])
    map.strompreise = s ? ausSchwere(s) : { status: 'ok' }
  }

  // (Investitionen/Geräte-Status wandert mit der Geräte-Bearbeitung in den
  // Komponenten-Hub, Entsch. 5 — kein Einstellungs-Badge mehr.)

  // Solarprognose: passt die aktive PVGIS-Prognose noch zur Anlage?
  //
  // Bis v4.0.11 stand hier das ALTER („Letzter Abruf vor N Tagen", ab 7 Tagen
  // eine Warnung). Das maß nichts: PVGIS rechnet auf einem abgeschlossenen
  // Klimamittel — eine Woche alte Prognose ist so gut wie eine von heute, und
  // ein Neuabruf hätte dieselbe Zahl geliefert. Falsch wird eine Prognose erst
  // durch eine Änderung an der Anlage, und genau das steht jetzt hier (#363).
  // Die Regel selbst gehört dem Backend (`services/pvgis_aktualitaet.py`), das
  // sie mit dem nächtlichen Neuabruf teilt — der Client zeigt nur an.
  if (anlageId && prognoseGeladen) {
    if (!prognose) {
      map.solarprognose = { status: 'neu', hinweis: 'Noch nie abgerufen.' }
    } else if (prognose.passt_zur_anlage === false) {
      map.solarprognose = {
        status: 'warn',
        hinweis: prognose.abweichung_text
          ? `Passt nicht mehr zur Anlage: ${prognose.abweichung_text}.`
          : 'Passt nicht mehr zur Anlage.',
      }
    } else {
      map.solarprognose = { status: 'ok' }
    }
  }

  // ── Daten ──
  // Daten-Checker: Aggregat der schlimmsten Schwere (aus denselben Befunden).
  if (selectedAnlage && erg) {
    const fehler = erg.filter((e) => e.schwere === 'error').length
    const warnungen = erg.filter((e) => e.schwere === 'warning').length
    const warnWort = warnungen === 1 ? 'Warnung' : 'Warnungen'
    if (fehler > 0) {
      map.datenchecker = { status: 'warn', hinweis: `${fehler} Fehler, ${warnungen} ${warnWort}.` }
    } else if (warnungen > 0) {
      map.datenchecker = { status: 'warn', hinweis: `${warnungen} ${warnWort}.` }
    } else {
      map.datenchecker = { status: 'ok' }
    }
  }

  // ── Datenquellen ──
  // Zuordnungs-Fläche (B7): erbt das Signal der aufgelösten Sensor-Zuordnung —
  // HA-Statistics- + Einheiten-Befunde (still = vollständig).
  if (selectedAnlage && erg) {
    const s = schlimmster(erg, ['sensor_mapping_lts', 'sensor_mapping_einheit'])
    map.datenquellen = s ? ausSchwere(s) : { status: 'ok' }
  }

  // ── Integration ──
  // MQTT-Export: MQTT-Inbound-Status (gemeinsamer Broker).
  if (mqtt) {
    if (mqtt.subscriber_aktiv) {
      map['ha-export'] = { status: 'ok' }
    } else if (mqtt.verfuegbar) {
      map['ha-export'] = { status: 'warn', hinweis: mqtt.grund ?? 'MQTT verfügbar, kein aktiver Subscriber.' }
    } else {
      map['ha-export'] = { status: 'neu', hinweis: mqtt.grund ?? 'Nicht konfiguriert.' }
    }
  }

  // ── Daten teilen ──
  // Community-Share: Auto-Share-Konfiguration der Anlage.
  if (selectedAnlage) {
    map.community = selectedAnlage.community_auto_share
      ? { status: 'ok' }
      : { status: 'neu', hinweis: 'Nicht eingerichtet.' }
  }

  return map
}
