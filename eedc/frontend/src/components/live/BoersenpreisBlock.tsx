/**
 * BoersenpreisBlock — Kennzahlen + Zwei-Tage-Chart der Day-Ahead-Preise (#335).
 *
 * Der Block beantwortet die Frage, die hinter dem Community-Wunsch steht: „Wann
 * ist der Strom heute und morgen billig?" Die Kennzahlen darüber sind dieselben,
 * die auch die HA-Sensoren melden (`eedc_preis_aktuell_cent`,
 * `…_optimierter_durchschnitt_cent`, die Schwelle als Attribut, seit N-173
 * `…_abstand_cent`) — wer den Block gegen seine Automation hält, sieht dieselben
 * Zahlen.
 *
 * **Leitprinzip Trigger ≠ Strategie:** Der Block zeigt Preise. Er empfiehlt kein
 * Ladefenster, rechnet keine Ladeleistung und schlägt nichts vor — das bleibt
 * Sache des Nutzers in Home Assistant.
 */

import { useMemo } from 'react'
import type { BoersenpreisResponse } from '../../api/liveDashboard'
import { KpiStrip, type KpiStripItem } from '../blocks/KpiStrip'
import { BOERSENPREIS_KPI } from '../../lib/komponentenStyle'
import { fmtZahl } from '../../lib'
import BoersenpreisChart from './BoersenpreisChart'

/** Kennzahlen des Blocks — heute, sofern heute dabei ist. */
export function baueKennzahlen(daten: BoersenpreisResponse): KpiStripItem[] {
  const heute = daten.tage.find((t) => t.datum === daten.heute)
  if (!heute) return []

  const jetzt = daten.aktuelle_stunde != null
    ? heute.stunden.find((s) => s.stunde === daten.aktuelle_stunde)
    : undefined
  const guenstigeStunden = heute.stunden.filter((s) => s.unter_schwelle).length

  const kpis: KpiStripItem[] = []
  if (jetzt) {
    kpis.push({
      ...BOERSENPREIS_KPI.aktuell,
      value: fmtZahl(jetzt.preis_cent, 2),
      unit: 'ct/kWh',
      subtitle: jetzt.unter_schwelle ? 'unter der Günstig-Schwelle' : 'über der Günstig-Schwelle',
    })
  }

  // N-173/R2 (rapahl): der Endpreis dieser Stunde — was auf der Rechnung steht.
  // Alle Kacheln dieses Blocks zeigen den **Börsenpreis**; der ist die richtige
  // Größe für „wann laden", aber nicht die, die man zahlt. Dazwischen liegen
  // Netzentgelte, Steuern und Abgaben.
  //
  // Bewusst DIREKT hinter dem aktuellen Börsenpreis und nicht ans Ende: beide
  // beantworten „was kostet jetzt", und nebeneinander ist der Aufschlag ohne
  // Rechnen ablesbar. Sie verdrängt keine Kachel, sie kommt dazu — und nur
  // dann, wenn ein Strompreis-Sensor zugeordnet ist. Ohne ihn bleibt der Wert
  // `null`; ein Rückfall auf den Tarif-Arbeitspreis wäre bei dynamischem Tarif
  // ein Mittelwert im Gewand eines Stundenpreises.
  if (daten.endpreis_jetzt_cent != null) {
    kpis.push({
      ...BOERSENPREIS_KPI.endpreis,
      value: fmtZahl(daten.endpreis_jetzt_cent, 2),
      unit: 'ct/kWh',
      subtitle: 'inkl. Netzentgelte, Steuern und Abgaben',
    })
  }

  // ── Allgemein lesbare Zahlen zuerst (Zusage an Rainer, PN 2026-08-20) ──
  //
  // Höchst und Tiefst beantworten „lohnt sich Warten heute überhaupt?", das
  // Monatsmittel „ist heute ein teurer Tag?". Beides stand nirgends; darunter
  // folgen die Optimierer-Werte (Ø ohne Peaks, Schwelle, Abstand) wie bisher.
  //
  // Höchst/Tiefst werden hier gebildet und nicht im Backend: es ist eine
  // Auswahl aus der Liste, die ohnehin schon vollständig vorliegt — dieselbe
  // Bauform wie `guenstigeStunden` zwei Zeilen darüber. Das Monatsmittel
  // dagegen kommt aus dem Backend, weil dafür Daten nötig sind, die der Client
  // nie sieht (die stündliche Preis-Mitschrift des Monats).
  const preise = heute.stunden.map((s) => s.preis_cent).filter((p) => p != null)
  if (preise.length > 0) {
    const hoechst = Math.max(...preise)
    const tiefst = Math.min(...preise)
    const stundeMax = heute.stunden.find((s) => s.preis_cent === hoechst)
    const stundeMin = heute.stunden.find((s) => s.preis_cent === tiefst)
    kpis.push({
      ...BOERSENPREIS_KPI.hoechst,
      value: fmtZahl(hoechst, 2),
      unit: 'ct/kWh',
      subtitle: stundeMax ? `um ${String(stundeMax.stunde).padStart(2, '0')}:00 Uhr` : undefined,
    })
    kpis.push({
      ...BOERSENPREIS_KPI.tiefst,
      value: fmtZahl(tiefst, 2),
      unit: 'ct/kWh',
      subtitle: stundeMin ? `um ${String(stundeMin.stunde).padStart(2, '0')}:00 Uhr` : undefined,
    })
  }
  if (daten.monats_durchschnitt_cent != null) {
    kpis.push({
      ...BOERSENPREIS_KPI.monat,
      value: fmtZahl(daten.monats_durchschnitt_cent, 2),
      unit: 'ct/kWh',
      // Der Zeitraum steht dabei: am Zweiten des Monats sind es zwei Tage.
      // Ohne diesen Zusatz läse sich die Zahl als volles Monatsmittel.
      subtitle: 'bisher aufgezeichnete Stunden dieses Monats',
    })
  }

  // rapahl-PN 2026-08-23: der gewöhnliche Tagesdurchschnitt. Bis dahin zeigten
  // drei der Kacheln hier dieselbe Bezugsgröße — den Ø **ohne** die drei
  // Peaks —, und die Zahl, nach der man zuerst fragt, fehlte ganz.
  if (heute.tages_durchschnitt_cent != null) {
    kpis.push({
      ...BOERSENPREIS_KPI.tagesMittel,
      value: fmtZahl(heute.tages_durchschnitt_cent, 2),
      unit: 'ct/kWh',
      subtitle: 'Mittel aller Stunden dieses Tages',
    })
  }
  if (heute.optimierter_durchschnitt_cent != null) {
    kpis.push({
      ...BOERSENPREIS_KPI.durchschnitt,
      value: fmtZahl(heute.optimierter_durchschnitt_cent, 2),
      unit: 'ct/kWh',
      subtitle: 'Tagesmittel ohne die 3 teuersten Stunden',
    })
  }
  if (heute.schwelle_cent != null) {
    kpis.push({
      ...BOERSENPREIS_KPI.schwelle,
      value: fmtZahl(heute.schwelle_cent, 2),
      unit: 'ct/kWh',
      // Die Zahl daneben ist die UNGEKAPPTE Zählung (N-103) — sie kann größer
      // als fünf sein, anders als der Rang in den älteren Sensoren.
      subtitle: `${guenstigeStunden} ${guenstigeStunden === 1 ? 'Stunde liegt' : 'Stunden liegen'} heute darunter`,
    })
  }
  // N-173 (rapahl-PN 2026-08-11): derselbe Abstand als Betrag. Wer einen
  // dynamischen Tarif mit festen Bestandteilen zahlt, kann die ct-Zahl 1:1 auf
  // seinen Endpreis übertragen — ein Aufschlag verschiebt Stundenpreis und Ø um
  // denselben Betrag, eine Prozentzahl dagegen bedeutet auf beiden Kurven etwas
  // anderes. Bewusst **ans Ende** und nicht neben den aktuellen Preis: die drei
  // seit v4.0.10 ausgelieferten Kacheln behalten ihren Platz.
  if (jetzt?.abstand_cent != null) {
    kpis.push({
      ...BOERSENPREIS_KPI.abstand,
      value: fmtZahl(jetzt.abstand_cent, 2),
      unit: 'ct/kWh',
      subtitle: jetzt.abstand_cent < 0
        ? 'unter dem Ø ohne die 3 teuersten Stunden'
        : 'über dem Ø ohne die 3 teuersten Stunden',
    })
  }
  return kpis
}

export default function BoersenpreisBlock({ daten }: { daten: BoersenpreisResponse }) {
  const kpis = useMemo(() => baueKennzahlen(daten), [daten])

  return (
    <div className="space-y-3">
      {/* rapahl-PN 2026-08-23: Kurve und Kennzahlen NEBENEINANDER statt
          untereinander — sein Vorbild ist das Paar Energiefluss/Infoblock in
          *Cockpit → Live*, und dasselbe Raster steht hier (`xl:grid-cols-3`,
          `items-start`). Der zweite Grund ist der wichtigere: Über die volle
          Seitenbreite gezogen wirkt die Preiskurve flach, die Tagesschwankung
          verschwindet optisch. In zwei Dritteln der Breite bei gleicher Höhe
          wird derselbe Verlauf sichtbar steiler — genau das, was er mit
          „etwas gestauchter" meinte.
          ⚠ Unterhalb `xl` bleibt es einspaltig und die Reihenfolge damit
          unverändert (Kennzahlen zuerst, Kurve darunter) — auf dem Handy ist
          Nebeneinander keine Option, und `KpiStrip` fällt über
          `auto-fit/minmax` von selbst auf eine Spalte zurück. Keine zweite
          Kachel-Komponente nötig (Regel 0a). */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 items-start">
        {kpis.length > 0 && (
          <div className="xl:order-2 xl:col-span-1">
            <KpiStrip kpis={kpis} />
          </div>
        )}
        {daten.tage.length > 0 && (
          <div className={kpis.length > 0 ? 'xl:order-1 xl:col-span-2' : 'xl:col-span-3'}>
            <BoersenpreisChart daten={daten} />
          </div>
        )}
      </div>
      {/* Fehlt ein Tag, sagt der Block warum — statt die halbe Achse leer zu
          lassen und Vollständigkeit zu suggerieren (ADR-002/P4). */}
      {daten.hinweis && (
        <p className="text-xs text-gray-500 dark:text-gray-400">{daten.hinweis}</p>
      )}
      <p className="text-[10px] text-gray-400 dark:text-gray-500">
        Börsenpreise der Day-Ahead-Auktion ({daten.markt === 'AT' ? 'EPEX Österreich' : 'EPEX Deutschland'}),
        netto — ohne Steuern, Abgaben und Netzentgelte. Dein Lieferant rechnet
        andere Beträge ab; für die Frage, welche Stunde die günstige ist, zählt der Verlauf.
      </p>
    </div>
  )
}
