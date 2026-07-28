/**
 * MonatAuswertungBloecke — die vor dem v4-Flip wiederhergestellten Monats-Analysen
 * aus dem alten „Energieprofil (Beta)"-Tab (Cockpit/Monat).
 *
 * Prüfung + Entscheid: `docs/drafts/archive/flip-v4/PRUEFUNG-V3-ENERGIEPROFIL-ABDECKUNG.md` §5
 * (Gernot 2026-07-19). Vier Blöcke — reine WIEDERHERSTELLUNG verlorener Abdeckung,
 * kein neues Feature; alle Werte kommen fertig berechnet aus `getMonat`
 * (`MonatsAuswertung`), daher KEIN Berechnungs-Layer (Berechnung≠UI, ADR-001):
 *   • M4  Kategorien-Anteils-Leiste — Erzeuger/Verbraucher getrennt (VerteilungsBalken-SoT)
 *   • M8  Typisches Tagesprofil     — Ø PV/Verbrauch je Stunde (Legenden-Toggle-Chart, B7)
 *   • M9  Peaks „Top-Stunden"       — Top-Netzbezug + Top-Einspeisung (ui/Table-SoT, Regel T)
 *   • M3  §51-Negativpreis          — Neg.-Stunden · Einspeisung · Börsenpreis Ø (KpiStrip)
 *
 * PR Ø Monat (M1) sitzt bewusst NICHT hier, sondern als KPI-Kachel im „Kennzahlen"-
 * Block (`baueMonatKpis` in {@link ./MonatBilanz}) — es ist eine Kennzahl, kein Block.
 *
 * Element-Park-Doktrin: jedes Element ist einzeln parkbar; ein Block entfällt, wenn
 * alle seine Elemente geparkt sind ODER keine Daten vorliegen (self-hide → der
 * Laufzeit-Leerblock-Gate `check:park-leertest` bleibt grün).
 */
import { Clock, Zap, Coins } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { ChartLegende, eedcTooltipProps, fmtCalc } from '../components/ui'
import { Table, TableHead, TableBody } from '../components/ui/Table'
import { ZELLE, KOPF_ZELLE } from '../components/ui/tabelleMasse'
import { KpiStrip, VerteilungsBalken, type Block, type KpiStripItem, type VerteilungSegment } from '../components/blocks'
import { Parkbar, type ParkApi } from '../components/park'
import {
  BLOCK_IDENTITAET, ENERGIE_KATEGORIE, KATEGORIE_FARBEN, COLORS,
  xAchse, yAchse, achsenEinheit, ACHSEN_MARGIN_TOP, fmtZahl,
} from '../lib'
import { useLegendenToggle, useSchmaleAchse } from '../hooks'
import type { MonatsAuswertung, PeakStunde, TagesprofilStunde } from '../api/energie_profil'

// ─── Bauer: die vier Auswertungs-Blöcke ──────────────────────────────────────

/** Baut die wiederhergestellten Monats-Auswertungs-Blöcke (M4/M8/M9/M3) aus der
 *  `getMonat`-Antwort. Reihenfolge = Standard-Sortierung (BlockShell ist sortierbar). */
export function baueMonatAuswertungBloecke(
  a: MonatsAuswertung,
  park: ParkApi,
  /** §51-Verlust in € aus der Monats-Antwort — die Auswertung selbst kennt keinen Tarif. */
  nichtVerguetetEuro?: number | null,
): Block[] {
  const bloecke: Block[] = []

  // M4 — Kategorien-Anteils-Leiste (Erzeuger/Verbraucher getrennt).
  const erzeuger = kategorieSegmente(a, 'erzeuger')
  const verbraucher = kategorieSegmente(a, 'verbraucher')
  if ((erzeuger.length > 0 || verbraucher.length > 0) && !park.istGeparkt('el:kategorien')) {
    bloecke.push({
      id: 'kategorien',
      title: 'Kategorien',
      ...BLOCK_IDENTITAET.energieBilanz,
      summary: 'Erzeugung & Verbrauch nach Kategorie',
      defaultOpen: false,
      render: () => (
        <Parkbar id="el:kategorien" titel="Kategorien-Anteile">
          <div className="space-y-4">
            {erzeuger.length > 0 && <VerteilungsBalken titel="Erzeugung nach Kategorie" segmente={erzeuger} />}
            {verbraucher.length > 0 && <VerteilungsBalken titel="Verbrauch nach Kategorie" segmente={verbraucher} />}
          </div>
        </Parkbar>
      ),
    })
  }

  // M8 — Typisches Tagesprofil (Ø-Stundenprofil).
  if (a.typisches_tagesprofil.length > 0 && !park.istGeparkt('el:tagesprofil')) {
    bloecke.push({
      id: 'tagesprofil',
      title: 'Typisches Tagesprofil',
      ...BLOCK_IDENTITAET.verlauf,
      summary: `Ø Stundenprofil aus ${a.tage_mit_daten} Tag${a.tage_mit_daten !== 1 ? 'en' : ''}`,
      defaultOpen: false,
      render: () => (
        <Parkbar id="el:tagesprofil" titel="Typisches Tagesprofil">
          <TagesprofilChart daten={a.typisches_tagesprofil} tageMitDaten={a.tage_mit_daten} />
        </Parkbar>
      ),
    })
  }

  // M9 — Peaks „Top-Stunden" (Netzbezug + Einspeisung), zwei einzeln parkbare Listen.
  const hatNetz = a.peak_netzbezug.length > 0
  const hatEinsp = a.peak_einspeisung.length > 0
  const netzSichtbar = hatNetz && !park.istGeparkt('el:peak-netzbezug')
  const einspSichtbar = hatEinsp && !park.istGeparkt('el:peak-einspeisung')
  if (netzSichtbar || einspSichtbar) {
    bloecke.push({
      id: 'peaks',
      title: 'Top-Stunden',
      ...BLOCK_IDENTITAET.werte,
      summary: 'Spitzenstunden Netzbezug + Einspeisung',
      defaultOpen: false,
      render: () => (
        <div className="grid md:grid-cols-2 gap-4">
          {hatNetz && (
            <Parkbar id="el:peak-netzbezug" titel="Top Netzbezug-Stunden">
              <PeakListe
                titel="Top Netzbezug-Stunden"
                hinweis="Spitzenstunden für Tarif-Optimierung"
                eintraege={a.peak_netzbezug}
              />
            </Parkbar>
          )}
          {hatEinsp && (
            <Parkbar id="el:peak-einspeisung" titel="Top Einspeise-Stunden">
              <PeakListe
                titel="Top Einspeise-Stunden"
                hinweis="PV-Spitzen, ggf. Batterie früher laden"
                eintraege={a.peak_einspeisung}
              />
            </Parkbar>
          )}
        </div>
      ),
    })
  }

  // M3 — §51-EEG-Negativpreis (nur wenn negative Preisstunden vorliegen). Jede
  // KPI-Kachel einzeln parkbar (KpiStrip-parkId-Muster wie im Kennzahlen-Block);
  // der Block entfällt, wenn alle drei geparkt sind.
  const negKpis = negativpreisKpis(a, nichtVerguetetEuro)
  const negSichtbar = negKpis.filter((k) => !park.istGeparkt(k.parkId!))
  if ((a.negative_preis_stunden ?? 0) > 0 && negSichtbar.length > 0) {
    bloecke.push({
      id: 'negativpreis',
      title: 'Börsenpreis (§51 EEG)',
      ...BLOCK_IDENTITAET.finanzen,
      summary: `${a.negative_preis_stunden} h mit negativem Börsenpreis`,
      defaultOpen: false,
      render: () => <KpiStrip kpis={negSichtbar} />,
    })
  }

  return bloecke
}

// ─── Sub-Bausteine ───────────────────────────────────────────────────────────

/** Segmente einer Kategorie-Gruppe für den {@link VerteilungsBalken} — Label/Farbe
 *  aus der zentralen {@link ENERGIE_KATEGORIE}-Map. Backend-Reihenfolge (nach Betrag
 *  absteigend) bleibt erhalten. */
function kategorieSegmente(a: MonatsAuswertung, gruppe: 'erzeuger' | 'verbraucher'): VerteilungSegment[] {
  return a.kategorien
    .filter((k) => ENERGIE_KATEGORIE[k.kategorie]?.gruppe === gruppe)
    .map((k) => ({
      label: ENERGIE_KATEGORIE[k.kategorie].label,
      wert: Math.abs(k.kwh),
      farbe: ENERGIE_KATEGORIE[k.kategorie].bg,
    }))
}

/** §51-KPIs — Neg.-Preisstunden · eingespeiste kWh bei neg. Preis · Ø-Börsenpreis.
 *  `parkId` je Kachel → einzeln parkbar (KpiStrip-Muster). */
function negativpreisKpis(a: MonatsAuswertung, nichtVerguetetEuro?: number | null): KpiStripItem[] {
  return [
    {
      title: 'Neg. Börsenpreis', value: `${a.negative_preis_stunden}`, unit: 'h',
      color: 'yellow', icon: Clock, parkId: 'kpi:51-stunden',
    },
    {
      title: 'Einspeisung bei neg. Preis', value: fmtCalc(a.einspeisung_neg_preis_kwh, 1, '—'), unit: 'kWh',
      color: 'yellow', icon: Zap, parkId: 'kpi:51-einspeisung',
      formel: 'Eingespeiste Energie in Stunden mit negativem Börsenpreis (§51 EEG: keine Vergütung)',
    },
    // Der €-Wert dazu: bis v4.0.0 wurde er im Anlage-Formular versprochen
    // („wird im Cockpit als §51-Verlust ausgewiesen"), aber nirgends gezeigt.
    ...(nichtVerguetetEuro != null ? [{
      title: '§51-Verlust', value: fmtCalc(nichtVerguetetEuro, 2, '—'), unit: '€',
      color: 'red' as const, icon: Coins, parkId: 'kpi:51-verlust',
      formel: 'Einspeisung bei negativem Börsenpreis × Einspeisevergütung',
      berechnung: `${fmtCalc(a.einspeisung_neg_preis_kwh, 1)} kWh ohne Vergütung`,
      ergebnis: `= ${fmtCalc(nichtVerguetetEuro, 2)} € entgangen`,
    }] : []),
    {
      title: 'Börsenpreis Ø', value: fmtCalc(a.boersenpreis_avg_cent, 1, '—'), unit: 'ct',
      color: 'gray', icon: Coins, parkId: 'kpi:51-boersenpreis',
    },
  ]
}

function PeakListe({ titel, hinweis, eintraege }: {
  titel: string
  hinweis: string
  eintraege: PeakStunde[]
}) {
  return (
    <div className="space-y-2">
      <div>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{titel}</h3>
        <p className="text-xs text-gray-500 dark:text-gray-400">{hinweis}</p>
      </div>
      <Table flaeche="karte">
        <TableHead>
          <tr className="text-gray-500 dark:text-gray-400">
            <th className={`${KOPF_ZELLE} text-left`}>Datum</th>
            <th className={`${KOPF_ZELLE} text-left`}>Stunde</th>
            <th className={`${KOPF_ZELLE} text-right`}>Wert</th>
          </tr>
        </TableHead>
        <TableBody>
          {eintraege.map((e, i) => (
            <tr key={`${e.datum}-${e.stunde}-${i}`} /* de-de-allow: React-key, keine Anzeige (Datum via formatTag) */>
              <td className={`${ZELLE} text-gray-700 dark:text-gray-300`}>{formatTag(e.datum)}</td>
              <td className={`${ZELLE} text-gray-700 dark:text-gray-300 tabular-nums`}>{String(e.stunde).padStart(2, '0')}:00</td>
              <td className={`${ZELLE} text-right font-medium text-gray-900 dark:text-white tabular-nums`}>{fmtCalc(e.wert_kw, 1)} kW</td>
            </tr>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function TagesprofilChart({ daten, tageMitDaten }: { daten: TagesprofilStunde[]; tageMitDaten: number }) {
  const schmal = useSchmaleAchse()
  // B7: Legenden-Klick blendet Serien aus/ein (Skalen-Lesbarkeit). SoT-Hook.
  const legende = useLegendenToggle()
  const chartDaten = daten.map((d) => ({
    stunde: String(d.stunde).padStart(2, '0'),
    pvAvg: d.pv_kw,
    verbrauchAvg: d.verbrauch_kw,
  }))
  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-400 dark:text-gray-500">
        Stündlicher Mittelwert aus {tageMitDaten} Tag{tageMitDaten !== 1 ? 'en' : ''}. Basis für Verbrauchs- und PV-Prognose.
      </p>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartDaten} margin={{ top: ACHSEN_MARGIN_TOP, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis dataKey="stunde" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse (Stunde) */ />
            <YAxis {...yAchse(schmal, 48)} tickFormatter={(v) => fmtZahl(v, 1)} label={achsenEinheit('kW')} />
            <Tooltip {...eedcTooltipProps({ formatter: (value: number) => `${fmtZahl(value, 2)} kW` })} />
            <Legend wrapperStyle={{ fontSize: 12 }} content={<ChartLegende onItemClick={legende.onItemClick} />} />
            <Line type="monotone" dataKey="pvAvg" name="PV Ø" stroke={KATEGORIE_FARBEN.pv} strokeWidth={2} dot={false} connectNulls hide={legende.istVersteckt('pvAvg')} />
            <Line type="monotone" dataKey="verbrauchAvg" name="Verbrauch Ø" stroke={COLORS.consumption} strokeWidth={2} dot={false} connectNulls hide={legende.istVersteckt('verbrauchAvg')} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

/** Kurzdatum „TT.MM." für die Peak-Listen (lokal, kein TZ-Drift bei ISO-Datum). */
function formatTag(iso: string): string {
  const [, m, d] = iso.split('-')
  return d && m ? `${d}.${m}.` : iso
}
