/**
 * KomponentenTypV4 — die Pro-Typ-Komponentenseite (IA v4 Phase A.2).
 *
 * Rendert den Block-Katalog aus SPEC-KOMPONENTEN.md in **kanonischer Default-
 * Reihenfolge**, die der Nutzer aber **verschieben** darf (`BlockShell sortierbar`,
 * Reihenfolge persistiert je Sicht — K-B4 revidiert 2026-06-21, Gernot: feste
 * Reihenfolge war falsch; IST-Dashboards konnten Sektionen schon verschieben):
 * ① Status · ② Struktur/Verknüpfung · ③ Sub-Komponente · ④ Verlauf ·
 * ⑤ Vergleich · ⑦ Einstellungen. Pflicht = ①④⑤⑦ (immer), spezifisch = ②③
 * (nur wenn der Adapter sie für den Typ liefert ⇒ Seite = Pflicht ∪
 * zutreffend-spezifisch). Aussicht (⑥) entfällt im Hub (Gernot 2026-06-21):
 * zeitliche Differenzierung → Cockpit/Aussicht. Typ-eigene IST-Analysen
 * (Verlauf/Vergleich) via `komponentenAnalyse`-Registry. Hub = Gesamtzeitraum
 * (K-B5, kein Datums-Selektor). Mehrere Geräte → Geräte-Selektor (Art ①).
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { LoadingSpinner, Card, Alert, fmtCalc } from '../components/ui'
import { BlockShell, KpiStrip, VerteilungsBalken, type Block } from '../components/blocks'
import { BLOCK_IDENTITAET, STATUS_COLORS } from '../lib'
import { KOMPONENTEN_IDENTITAET } from '../lib/komponentenStyle'
import { sensorMappingApi } from '../api/sensorMapping'
import { liveDashboardApi } from '../api/liveDashboard'
import { AlertTriangle, BarChart3, ClipboardCheck, Cpu, Euro, ExternalLink, FileText, Layers, Network, Paperclip, Radio, Settings, Zap } from 'lucide-react'
import { KOMPONENTEN_ADAPTER, type KompGeraet, type KompStruktur, type TopoItem } from './komponentenAdapter'
import { KOMPONENTEN_ANALYSE } from './komponentenAnalyse'
import { KomponentenVerlaufChart } from './KomponentenVerlaufChart'
import { KomponentenMonatsTabelle } from './KomponentenMonatsTabelle'
import { KomponentenVergleich } from './KomponentenVergleich'
import { infothekApi } from '../api/infothek'
import { KATEGORIE_CONFIG } from '../config/infothekKategorien'
import { datenCheckerApi, type CheckErgebnis } from '../api/datenChecker'
import { SEVERITY_CONFIG, type CheckSchwere } from '../config/datenCheckerKategorien'
import type { Investition } from '../types'
import type { InfothekEintrag } from '../types/infothek'

/** Parameter-Zeilen einer Investition (Stammdaten + JSON-Parameter). */
function paramFelder(inv: Investition): { label: string; wert: string }[] {
  const felder: { label: string; wert: string }[] = []
  if (inv.leistung_kwp != null) felder.push({ label: 'Leistung', wert: `${fmtCalc(inv.leistung_kwp, 1)} kWp` })
  if (inv.ausrichtung) felder.push({ label: 'Ausrichtung', wert: inv.ausrichtung })
  if (inv.neigung_grad != null) felder.push({ label: 'Neigung', wert: `${inv.neigung_grad}°` })
  if (inv.anschaffungsdatum) felder.push({ label: 'Anschaffung', wert: inv.anschaffungsdatum })
  if (inv.stilllegungsdatum) felder.push({ label: 'Stilllegung', wert: inv.stilllegungsdatum })
  if (inv.anschaffungskosten_gesamt != null) felder.push({ label: 'Anschaffungskosten', wert: `${fmtCalc(inv.anschaffungskosten_gesamt, 0)} €` })
  for (const [k, v] of Object.entries(inv.parameter ?? {})) {
    if (v == null || typeof v === 'object') continue
    felder.push({ label: k.replace(/_/g, ' '), wert: String(v) })
  }
  return felder
}

interface FeldM { strategie?: string; sensor_id?: string | null }
type LiveMap = Record<string, string | null> | null
interface InvMap { felder?: Record<string, FeldM>; live?: LiveMap }
interface MappingShape {
  basis?: Record<string, FeldM | LiveMap | undefined> & { live?: LiveMap }
  investitionen?: Record<string, InvMap>
}

interface SensorZeile { feld: string; sensor: string; live?: boolean }

/** Sensor-Zuordnungen einer Investition: Statistik-Felder (strategie 'sensor') +
 *  Live-Sensoren (`live`-Block) + Legacy `ha_entity_id`. */
function invSensoren(inv: Investition, mapping: MappingShape | null): SensorZeile[] {
  const out: SensorZeile[] = []
  const invMap = mapping?.investitionen?.[String(inv.id)]
  for (const [feld, m] of Object.entries(invMap?.felder ?? {})) {
    if (m?.strategie === 'sensor' && m.sensor_id) out.push({ feld: feld.replace(/_/g, ' '), sensor: m.sensor_id })
  }
  for (const [feld, sid] of Object.entries(invMap?.live ?? {})) {
    if (sid) out.push({ feld: feld.replace(/_/g, ' '), sensor: sid, live: true })
  }
  if (inv.ha_entity_id) out.push({ feld: 'HA-Sensor', sensor: inv.ha_entity_id })
  return out
}

/** Anlagen-Basis-Sensoren: Statistik-Rollen (strategie 'sensor') + Live-Rollen. */
function basisSensoren(mapping: MappingShape | null): SensorZeile[] {
  const basis = mapping?.basis
  if (!basis) return []
  const out: SensorZeile[] = []
  for (const [rolle, m] of Object.entries(basis)) {
    if (rolle === 'live' || rolle === 'live_invert') continue
    const fm = m as FeldM
    if (fm?.strategie === 'sensor' && fm.sensor_id) out.push({ feld: rolle.replace(/_/g, ' '), sensor: fm.sensor_id })
  }
  for (const [rolle, sid] of Object.entries(basis.live ?? {})) {
    if (sid) out.push({ feld: rolle.replace(/_/g, ' '), sensor: sid, live: true })
  }
  return out
}

/** Eine Sensor-Zeile (Feld → entity_id, Live-Marker). */
function SensorRow({ z }: { z: SensorZeile }) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="text-gray-500 dark:text-gray-400 capitalize flex items-center gap-1.5">
        {z.live && <span className="inline-block w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: STATUS_COLORS.ok }} title="Live-Sensor" />}
        {z.feld}{z.live ? ' (live)' : ''}
      </span>
      <code className="text-xs text-gray-700 dark:text-gray-300 truncate">{z.sensor}</code>
    </div>
  )
}

const EDIT_INVEST = '#/einstellungen/investitionen'
const EDIT_SENSOR = '#/einstellungen/sensor-mapping'
const EDIT_MQTT = '#/einstellungen/mqtt-inbound'
const EDIT_INFOTHEK = '#/einstellungen/infothek'
const EDIT_DATENCHECKER = '#/einstellungen/daten-checker'

/** Severity-Rang für die Sortierung der Daten-Checker-Befunde (error zuerst). */
const SCHWERE_RANG: Record<CheckSchwere, number> = { error: 0, warning: 1, info: 2, ok: 3 }

function EditLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
      <ExternalLink className="h-3.5 w-3.5" /> {children}
    </a>
  )
}

/** Kopfzeile einer Komponente (Icon + Bezeichnung + Typ-Label). */
function KompKopf({ inv, rechts }: { inv: Investition; rechts?: ReactNode }) {
  const ident = KOMPONENTEN_IDENTITAET[inv.typ]
  const Icon = ident?.icon ?? Settings
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2 font-medium text-gray-900 dark:text-white min-w-0">
        <Icon className={`h-4 w-4 shrink-0 ${ident?.farbe ?? 'text-gray-400'}`} />
        <span className="truncate">{inv.bezeichnung}</span>
        <span className="text-xs font-normal text-gray-500 dark:text-gray-400 whitespace-nowrap">{ident?.label ?? inv.typ}</span>
      </div>
      {rechts}
    </div>
  )
}

/** Gruppen-Überschrift (Bearbeitungs-Domäne) mit Bearbeiten-Verzweigung rechts. */
function GruppenKopf({ icon: Icon, titel, edit }: { icon: typeof Cpu; titel: string; edit: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-gray-100 dark:border-gray-800 pb-1">
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        <Icon className="h-3.5 w-3.5" /> {titel}
      </div>
      <div className="flex gap-3">{edit}</div>
    </div>
  )
}

/** Einstellungen-Block (#243): nach Bearbeitungs-Domäne gegliedert —
 *  **Stammdaten** (Parameter → Investition bearbeiten) und **Zuordnungen**
 *  (HA-Sensoren inkl. Live + MQTT-Topics → Sensor-Mapping/MQTT). Für die
 *  PV-Anlage über WR + Module + Speicher (sonst die eine Komponente). */
function EinstellungenBlock({ anlageId, invs }: { anlageId: number; invs: Investition[] }) {
  const [mapping, setMapping] = useState<MappingShape | null>(null)
  const [topics, setTopics] = useState<{ ziel_key: string; quell_topic: string }[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let ab = false
    setLoading(true)
    Promise.all([
      sensorMappingApi.getMapping(anlageId).then((r) => r.mapping as MappingShape | null).catch(() => null),
      liveDashboardApi.getGatewayMappings(anlageId).catch(() => [] as { ziel_key: string; quell_topic: string }[]),
    ]).then(([m, t]) => { if (!ab) { setMapping(m); setTopics(t); setLoading(false) } })
    return () => { ab = true }
  }, [anlageId])

  const echteInvs = invs.filter((i) => i.id !== 0) // PV-UI-Aggregat (id 0) selbst hat keine Parameter
  const basis = basisSensoren(mapping)
  const hatZuordnungen = echteInvs.some((i) => invSensoren(i, mapping).length > 0) || basis.length > 0 || topics.length > 0

  return (
    <div className="space-y-6">
      {/* Stammdaten — bearbeitbar über die Investition */}
      <div className="space-y-3">
        <GruppenKopf icon={Settings} titel="Stammdaten" edit={<EditLink href={EDIT_INVEST}>Investitionen bearbeiten</EditLink>} />
        {echteInvs.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">Keine Investitions-Parameter hinterlegt.</p>
        ) : echteInvs.map((inv) => {
          const felder = paramFelder(inv)
          return (
            <div key={inv.id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-2">
              <KompKopf inv={inv} rechts={<EditLink href={EDIT_INVEST}>Bearbeiten</EditLink>} />
              {felder.length > 0 ? (
                <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-1">
                  {felder.map((f) => (
                    <div key={f.label} className="flex items-center justify-between gap-2 text-sm border-b border-gray-100 dark:border-gray-800 py-0.5">
                      <dt className="text-gray-500 dark:text-gray-400 capitalize">{f.label}</dt>
                      <dd className="font-medium text-gray-900 dark:text-white whitespace-nowrap">{f.wert}</dd>
                    </div>
                  ))}
                </dl>
              ) : <p className="text-xs text-gray-400 dark:text-gray-500">Keine Parameter hinterlegt.</p>}
            </div>
          )
        })}
      </div>

      {/* Zuordnungen — bearbeitbar über Sensor-Mapping / MQTT */}
      <div className="space-y-3">
        <GruppenKopf icon={Cpu} titel="Zuordnungen — Sensoren & MQTT" edit={<>
          <EditLink href={EDIT_SENSOR}>Sensoren</EditLink>
          <EditLink href={EDIT_MQTT}>MQTT</EditLink>
        </>} />
        {loading ? (
          <p className="text-xs text-gray-400 dark:text-gray-500">Lade Zuordnungen…</p>
        ) : !hatZuordnungen ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">Keine Sensor-/MQTT-Zuordnungen hinterlegt.</p>
        ) : (
          <>
            {echteInvs.map((inv) => {
              const sensoren = invSensoren(inv, mapping)
              if (!sensoren.length) return null
              return (
                <div key={inv.id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-1.5">
                  <KompKopf inv={inv} />
                  {sensoren.map((s) => <SensorRow key={`${s.feld}-${s.sensor}`} z={s} />)}
                </div>
              )
            })}
            {(basis.length > 0 || topics.length > 0) && (
              <div className="rounded-lg border border-gray-100 dark:border-gray-800 p-3 space-y-1 bg-gray-50/50 dark:bg-gray-800/30">
                <div className="text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">Anlagen-Datenquellen</div>
                {basis.map((b) => <SensorRow key={`b-${b.feld}-${b.sensor}`} z={b} />)}
                {topics.map((t) => (
                  <div key={`${t.ziel_key}-${t.quell_topic}`} className="flex items-center justify-between gap-2 text-sm">
                    <span className="text-gray-500 dark:text-gray-400 capitalize flex items-center gap-1.5"><Radio className="h-3 w-3 shrink-0" />{t.ziel_key.replace(/_/g, ' ')}</span>
                    <code className="text-xs text-gray-700 dark:text-gray-300 truncate">{t.quell_topic}</code>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <p className="text-xs text-gray-400 dark:text-gray-500">
        Anlagenweite Einstellungen (USt, §51 EEG, Netz-Puffer, Prognosequelle) und zeitlich variable
        Strompreise liegen unter <span className="font-medium">Einstellungen</span> — anderer Geltungsbereich.
      </p>
    </div>
  )
}

/** Infothek-Block (#243): verknüpfte Dokumente & Infos dieser Komponente —
 *  read-only, dünn (volle Werkbank = Cross-Link zur Infothek). Lädt die N:M-
 *  verknüpften aktiven Einträge aller zugehörigen Investitionen (PV = WR + Module
 *  + Speicher; sonst die eine Komponente), dedupliziert + nach Kategorie gruppiert
 *  (Icon/Label aus `KATEGORIE_CONFIG`-SoT). Datei-Indikator aus `dateien_count`. */
function InfothekBlock({ invs }: { invs: Investition[] }) {
  const [eintraege, setEintraege] = useState<InfothekEintrag[]>([])
  const [loading, setLoading] = useState(true)

  // Stabiler Primitiv-Key (id 0 = PV-UI-Aggregat hat keine eigene Infothek) → kein Refetch je Render.
  const idKey = invs.filter((i) => i.id !== 0).map((i) => i.id).join(',')

  useEffect(() => {
    let ab = false
    const ids = idKey ? idKey.split(',').map(Number) : []
    setLoading(true)
    Promise.all(ids.map((id) => infothekApi.listFuerInvestition(id).catch(() => [] as InfothekEintrag[])))
      .then((listen) => {
        if (ab) return
        const seen = new Set<number>()
        const flach: InfothekEintrag[] = []
        for (const e of listen.flat()) {
          if (!e.aktiv || seen.has(e.id)) continue // archivierte raus, N:M-Duplikate dedupe
          seen.add(e.id)
          flach.push(e)
        }
        setEintraege(flach)
        setLoading(false)
      })
    return () => { ab = true }
  }, [idKey])

  // Nach Kategorie gruppieren (Erst-Vorkommen-Reihenfolge; Backend liefert je Inv nach sortierung).
  const gruppen = useMemo(() => {
    const m = new Map<string, InfothekEintrag[]>()
    for (const e of eintraege) {
      const arr = m.get(e.kategorie) ?? []
      arr.push(e)
      m.set(e.kategorie, arr)
    }
    return [...m.entries()]
  }, [eintraege])

  return (
    <div className="space-y-4">
      <GruppenKopf icon={FileText} titel="Verknüpfte Dokumente" edit={<EditLink href={EDIT_INFOTHEK}>Zur Infothek</EditLink>} />
      {loading ? (
        <p className="text-xs text-gray-400 dark:text-gray-500">Lade Dokumente…</p>
      ) : eintraege.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">Keine mit dieser Komponente verknüpften Dokumente.</p>
      ) : (
        gruppen.map(([kat, eintr]) => {
          const cfg = KATEGORIE_CONFIG[kat]
          const KatIcon = cfg?.icon ?? FileText
          return (
            <div key={kat} className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">
                <KatIcon className={`h-3.5 w-3.5 ${cfg?.color ?? 'text-gray-400'}`} /> {cfg?.label ?? kat}
              </div>
              <ul className="space-y-0.5">
                {eintr.map((e) => (
                  <li key={e.id} className="flex items-center justify-between gap-2 text-sm">
                    <span className="text-gray-700 dark:text-gray-300 truncate">{e.bezeichnung}</span>
                    {!!e.dateien_count && (
                      <span className="inline-flex items-center gap-0.5 text-xs text-gray-500 dark:text-gray-400 shrink-0" title={`${e.dateien_count} Datei(en)`}>
                        <Paperclip className="h-3 w-3" />{e.dateien_count}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )
        })
      )}
    </div>
  )
}

/** Eine Daten-Checker-Befund-Zeile (Severity-Icon + Meldung + optionale Details). */
function BefundRow({ e }: { e: CheckErgebnis }) {
  const cfg = SEVERITY_CONFIG[e.schwere]
  const Icon = cfg?.icon ?? AlertTriangle
  return (
    <li className="flex items-start gap-2 text-sm">
      <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${cfg?.colorClass ?? 'text-gray-400'}`} />
      <div className="min-w-0">
        <span className="text-gray-700 dark:text-gray-300">{e.meldung}</span>
        {e.details && <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{e.details}</p>}
      </div>
    </li>
  )
}

/** Daten-Checker-Block (#243): komponenten-zuordenbare Qualitäts-Befunde dieser
 *  Komponente (Stammdaten/Monatsdaten je Gerät), gefiltert über die vom Backend
 *  gesetzte `investition_id`. Bewusst dünn & read-only: anlagenweite Werte-
 *  Anomalien (Plausibilität/Drift, zeitpunkt-/reparatur-gebunden, K-B5) bleiben
 *  draußen und sind über den Cross-Link zur vollen Daten-Checker-Werkbank
 *  (inkl. Reparatur-Aktionen) erreichbar. */
function DatenCheckerBlock({ anlageId, invs }: { anlageId: number; invs: Investition[] }) {
  const [befunde, setBefunde] = useState<CheckErgebnis[]>([])
  const [loading, setLoading] = useState(true)

  // Stabiler Primitiv-Key (id 0 = PV-UI-Aggregat ohne eigene Befunde).
  const idKey = invs.filter((i) => i.id !== 0).map((i) => i.id).join(',')

  useEffect(() => {
    let ab = false
    const ids = new Set(idKey ? idKey.split(',').map(Number) : [])
    setLoading(true)
    datenCheckerApi.check(anlageId)
      .then((r) => {
        if (ab) return
        const eigene = r.ergebnisse
          // Nur offene Befunde dieser Komponente: investition_id gesetzt +
          // nicht OK (OK-Bestätigungen = kein Handlungsbedarf, raus aus dem Hub).
          .filter((e) => e.investition_id != null && ids.has(e.investition_id) && e.schwere !== 'ok')
          .sort((a, b) => SCHWERE_RANG[a.schwere] - SCHWERE_RANG[b.schwere])
        setBefunde(eigene)
        setLoading(false)
      })
      .catch(() => { if (!ab) { setBefunde([]); setLoading(false) } })
    return () => { ab = true }
  }, [anlageId, idKey])

  return (
    <div className="space-y-3">
      <GruppenKopf
        icon={ClipboardCheck} titel="Daten-Qualität"
        edit={<EditLink href={EDIT_DATENCHECKER}>Alle Prüfungen & Reparatur</EditLink>}
      />
      {loading ? (
        <p className="text-xs text-gray-400 dark:text-gray-500">Prüfe Daten…</p>
      ) : befunde.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">Keine offenen Befunde für diese Komponente.</p>
      ) : (
        <ul className="space-y-2">
          {befunde.map((e, i) => <BefundRow key={`${e.kategorie}-${i}`} e={e} />)}
        </ul>
      )}
      <p className="text-xs text-gray-400 dark:text-gray-500">
        Zeitpunktbezogene Werte-Auffälligkeiten (Ausreißer, Lücken einzelner Tage) und ihre Reparatur
        liegen in der <span className="font-medium">Daten-Checker</span>-Werkbank.
      </p>
    </div>
  )
}

/** Markierter Folge-Block (Verlauf/Vergleich) — ehrlich „im Bau", kein Fake. */
function FolgtHinweis({ text, crossLink }: { text: string; crossLink?: { label: string; href: string } }) {
  return (
    <div className="space-y-2">
      <p className="text-sm text-gray-500 dark:text-gray-400">{text}</p>
      {crossLink && (
        <a href={crossLink.href} className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
          <ExternalLink className="h-4 w-4" /> {crossLink.label}
        </a>
      )}
    </div>
  )
}

/** Eine Knoten-Liste (Module / Speicher) unter einem Wechselrichter (Block ② Topologie). */
function TopoListe({ titel, items }: { titel: string; items: TopoItem[] }) {
  if (!items.length) return null
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-1">{titel}</div>
      <ul className="space-y-0.5">
        {items.map((it, i) => (
          <li key={i} className="flex items-center justify-between gap-2 text-sm">
            <span className="text-gray-700 dark:text-gray-300">{it.label}</span>
            {it.detail && <span className="text-gray-500 dark:text-gray-400 whitespace-nowrap">{it.detail}</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Block ② Struktur/Verknüpfung — PV-Topologie (WR→Module/Speicher + Orphan)
 *  oder dünne Referenzzeilen (Speicher-Kopplung / Wallbox-Datenquelle). */
function StrukturInhalt({ s }: { s: KompStruktur }) {
  if (s.art === 'referenz') {
    return (
      <dl className="space-y-2">
        {s.zeilen.map((z, i) => (
          <div key={i}>
            <div className="flex items-center justify-between gap-2 border-b border-gray-100 dark:border-gray-800 py-1 text-sm">
              <dt className="text-gray-500 dark:text-gray-400">{z.label}</dt>
              {z.wert && <dd className="font-medium text-gray-900 dark:text-white whitespace-nowrap">{z.wert}</dd>}
            </div>
            {z.hinweis && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{z.hinweis}</p>}
          </div>
        ))}
      </dl>
    )
  }
  const hatOrphan = s.orphanModule.length > 0 || s.orphanSpeicher.length > 0
  return (
    <div className="space-y-3">
      {hatOrphan && (
        <Alert type="warning">
          {s.orphanModule.length > 0 && `${s.orphanModule.length} PV-Modul(e) ohne Wechselrichter-Zuordnung. `}
          {s.orphanSpeicher.length > 0 && `${s.orphanSpeicher.length} Speicher ohne Wechselrichter-Zuordnung.`}
        </Alert>
      )}
      {s.wr.map((w, i) => (
        <div key={i} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
          <div className="flex items-center gap-2 font-medium text-gray-900 dark:text-white">
            <Zap className="h-4 w-4 text-gray-400" />
            <span>{w.label}</span>
            {w.detail && <span className="text-xs font-normal text-gray-500 dark:text-gray-400">· {w.detail}</span>}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mt-2">
            <TopoListe titel="Module" items={w.module} />
            <TopoListe titel="Speicher" items={w.speicher} />
          </div>
        </div>
      ))}
      {hatOrphan && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
          <TopoListe titel="Module ohne Zuordnung" items={s.orphanModule} />
          <TopoListe titel="Speicher ohne Zuordnung" items={s.orphanSpeicher} />
        </div>
      )}
    </div>
  )
}

/** Sekundär-/Sub-KPI-Strip mit kleiner Überschrift (Block ① Sekundär, Block ③). */
function KpiUnterblock({ titel, kpis }: { titel: string; kpis: KompGeraet['status'] }) {
  return (
    <div className="space-y-2">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">{titel}</div>
      <KpiStrip kpis={kpis} />
    </div>
  )
}

/** Block „Wirtschaftlichkeit" — generische **Ertrags-Zusammensetzung** (Typen ohne
 *  Alternativ-Vergleich: PV/Speicher/BKW/Sonstiges). Ertragsposten als €-Kennzahlen
 *  + (ab 2 Posten) €-Aufteilungsbalken; `nichtBewertet` zeigt einen ehrlichen
 *  Hinweis statt Fake-Zahlen (Sonstiger Erzeuger ohne Brennstoffmodell). */
function WirtschaftlichkeitInhalt({ w }: { w: NonNullable<KompGeraet['wirtschaftlichkeit']> }) {
  if (w.nichtBewertet) return <Alert type="info">{w.nichtBewertet}</Alert>
  const posten = w.posten.filter((p) => (p.euro ?? 0) > 0)
  const kpis: KompGeraet['status'] = posten.map((p) => ({
    title: p.label, value: fmtCalc(p.euro, 0, '—'), unit: '€', color: 'green', icon: Euro, subtitle: p.hinweis,
  }))
  if (w.gesamt) kpis.push({ title: w.gesamt.label, value: fmtCalc(w.gesamt.euro, 0, '—'), unit: '€', color: 'blue', icon: Euro })
  return (
    <div className="space-y-4">
      {kpis.length > 0 && <KpiStrip kpis={kpis} />}
      {posten.length >= 2 && (
        <VerteilungsBalken titel="Zusammensetzung des Ertrags" einheit="€"
          segmente={posten.map((p) => ({ label: p.label, wert: p.euro, farbe: p.farbe }))} />
      )}
      {w.hinweis && <p className="text-xs text-gray-400 dark:text-gray-500">{w.hinweis}</p>}
    </div>
  )
}

function geraetBloecke(g: KompGeraet, typ: string, anlageId: number): Block[] {
  const analyse = KOMPONENTEN_ANALYSE[typ]
  const bloecke: Block[] = [
    // ① Status (Pflicht) — D2-KPIs + Aufteilung + ggf. Sekundär-Strip.
    {
      id: 'status', title: 'Aktueller Status', ...BLOCK_IDENTITAET.kennzahlen,
      summary: g.status.map((k) => `${k.value} ${k.unit ?? ''}`.trim()).slice(0, 2).join(' · '),
      defaultOpen: true,
      render: () => (
        <div className="space-y-4">
          <KpiStrip kpis={g.status} />
          {g.hinweise?.map((h, i) => <Alert key={i} type={h.ton}>{h.text}</Alert>)}
          {g.kennzahlen && <KpiUnterblock titel={g.kennzahlen.titel} kpis={g.kennzahlen.kpis} />}
          {g.aufteilung && <VerteilungsBalken titel={g.aufteilung.titel} einheit={g.aufteilung.einheit} segmente={g.aufteilung.segmente} />}
          {g.sekundaer && <KpiUnterblock titel={g.sekundaer.titel} kpis={g.sekundaer.kpis} />}
        </div>
      ),
    },
  ]

  // ② Struktur/Verknüpfung (spezifisch).
  if (g.struktur) {
    const topo = g.struktur.art === 'topologie'
    bloecke.push({
      id: 'struktur', title: topo ? 'System-Struktur' : 'Verknüpfung', icon: Network,
      summary: topo ? 'Wechselrichter → Module / Speicher' : 'Zuordnung & Datenquelle',
      defaultOpen: false,
      render: () => <StrukturInhalt s={g.struktur!} />,
    })
  }

  // ③ Sub-Komponente (spezifisch, In-Wirt).
  if (g.subKomponente) {
    bloecke.push({
      id: 'sub', title: g.subKomponente.titel, icon: Layers,
      summary: g.subKomponente.kpis.map((k) => `${k.value} ${k.unit ?? ''}`.trim()).slice(0, 2).join(' · '),
      defaultOpen: false,
      render: () => (
        <div className="space-y-3">
          {g.subKomponente!.hinweis && <p className="text-xs text-gray-400 dark:text-gray-500">{g.subKomponente!.hinweis}</p>}
          <KpiStrip kpis={g.subKomponente!.kpis} />
        </div>
      ),
    })
  }

  // ④ Verlauf (Pflicht) — typ-eigene IST-Charts via Analyse-Registry, sonst generischer Adapter-Verlauf.
  bloecke.push({
    id: 'verlauf', title: 'Verlauf (gesamte Historie)', ...BLOCK_IDENTITAET.verlauf,
    summary: 'Zeitreihe über die gesamte Laufzeit', defaultOpen: false,
    render: (fokus) => (analyse?.verlauf
      ? analyse.verlauf(anlageId, g.inv)
      : g.verlauf
        ? (
          <div className="space-y-4">
            <KomponentenVerlaufChart rows={g.verlauf.rows} bars={g.verlauf.bars} einheit={g.verlauf.einheit} gestapelt={g.verlauf.gestapelt} tall={fokus} />
            {g.verlauf.verteilungen && g.verlauf.verteilungen.length > 0 && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {g.verlauf.verteilungen.map((v) => (
                  <VerteilungsBalken key={v.titel} titel={v.titel} einheit={v.einheit} segmente={v.segmente} />
                ))}
              </div>
            )}
            {/* Scoped read-only Monats-Detailtabelle (WKW 1-42/70) — selbe Daten wie der Chart.
                PV ausgenommen: dessen ④ ist jahres-aggregiert (Modul-Stapel), keine Monatszeilen. */}
            {typ !== 'pv-module' && (
              <KomponentenMonatsTabelle rows={g.verlauf.rows} bars={g.verlauf.bars} einheit={g.verlauf.einheit} />
            )}
          </div>
        )
        : <FolgtHinweis text="Für diesen Typ liegt keine eigene Zeitreihe vor (z. B. Wallbox = aus E-Auto-Ladung abgeleitet)." />),
  })

  // ⑤ Vergleich (Pflicht) — typ-eigene IST-Analyse (z. B. PV-SOLL/IST pro String) via Registry, sonst generischer Jahresvergleich.
  bloecke.push({
    id: 'vergleich', title: 'Vergleich', icon: BarChart3,
    summary: analyse?.vergleich ? 'Komponentenspezifischer Vergleich' : 'Jahresvergleich · Diagramm ⇄ Tabelle', defaultOpen: false,
    render: () => (analyse?.vergleich
      ? analyse.vergleich(anlageId, g.inv)
      : g.vergleich
        ? <KomponentenVergleich label={g.vergleich.label} einheit={g.vergleich.einheit} farbe={g.vergleich.farbe} jahre={g.vergleich.jahre} />
        : <FolgtHinweis
            text="Für diesen Typ liegt noch kein Jahresvergleich vor."
            crossLink={{ label: 'Alle Werte / Tabelle →', href: '#/v4/auswertungen/tabelle' }}
          />),
  })

  // Wirtschaftlichkeit (Pflicht bei allen Typen) — zwei Modi:
  //  • Vergleich (Registry): typen MIT Alternative (WP=vs Gas, E-Auto=vs Benzin, Wallbox=ROI).
  //  • Ertrags-Zusammensetzung (Adapter `g.wirtschaftlichkeit`): PV/Speicher/BKW/Sonstiges —
  //    Aufschlüsselung in Ertragsposten; Sonstiger Erzeuger ehrlich „nicht bewertet".
  if (analyse?.wirtschaftlichkeit || g.wirtschaftlichkeit) {
    bloecke.push({
      id: 'wirtschaftlichkeit', title: 'Wirtschaftlichkeit', icon: Euro,
      summary: analyse?.wirtschaftlichkeit ? 'Kostenvergleich & Ersparnis' : 'Ertrags-Zusammensetzung',
      defaultOpen: false,
      render: () => (analyse?.wirtschaftlichkeit
        ? analyse.wirtschaftlichkeit(anlageId, g.inv)
        : <WirtschaftlichkeitInhalt w={g.wirtschaftlichkeit!} />),
    })
  }

  // ⑥ Aussicht entfällt im Hub (Gernot 2026-06-21): zeitliche Differenzierung → Cockpit/Aussicht.

  // Dokumente & Infos (#243) — N:M-verknüpfte Infothek-Einträge dieser Komponente (dünn, read-only).
  bloecke.push({
    id: 'infothek', title: 'Dokumente & Infos', icon: FileText,
    summary: 'Verträge, Datenblätter & Dokumente dieser Komponente', defaultOpen: false,
    render: () => <InfothekBlock invs={g.verknuepfteInvs ?? [g.inv]} />,
  })

  // Daten-Qualität (#243) — komponenten-zuordenbare Befunde dieser Komponente (dünn, read-only, Cross-Link zur Werkbank).
  bloecke.push({
    id: 'daten-checker', title: 'Daten-Qualität', icon: ClipboardCheck,
    summary: 'Offene Daten-Befunde dieser Komponente', defaultOpen: false,
    render: () => <DatenCheckerBlock anlageId={anlageId} invs={g.verknuepfteInvs ?? [g.inv]} />,
  })

  // ⑦ Einstellungen (Pflicht) — alle verknüpften Investitionen strukturiert + Sensor-/MQTT-Zuordnungen + Edit-Verzweigung.
  bloecke.push({
    id: 'einstellungen', title: 'Einstellungen', icon: Settings,
    summary: 'Parameter, Sensoren & MQTT dieser Komponente — mit Bearbeiten-Links', defaultOpen: false,
    render: () => <EinstellungenBlock anlageId={anlageId} invs={g.verknuepfteInvs ?? [g.inv]} />,
  })

  return bloecke
}

export default function KomponentenTypV4({ typ, anlageId }: { typ: string; anlageId: number | undefined }) {
  const [geraete, setGeraete] = useState<KompGeraet[]>([])
  const [aktiv, setAktiv] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const adapter = KOMPONENTEN_ADAPTER[typ]
  const ident = KOMPONENTEN_IDENTITAET[typ]

  useEffect(() => {
    if (!anlageId || !adapter) { setLoading(false); return }
    let ab = false
    setLoading(true); setError(null); setAktiv(0)
    adapter.fetch(anlageId)
      .then((gs) => { if (!ab) setGeraete(gs) })
      .catch(() => { if (!ab) setError('Fehler beim Laden der Komponente') })
      .finally(() => { if (!ab) setLoading(false) })
    return () => { ab = true }
  }, [anlageId, adapter, typ])

  const g = geraete[aktiv]
  const bloecke = useMemo(() => (g ? geraetBloecke(g, typ, anlageId ?? 0) : []), [g, typ, anlageId])

  if (!anlageId) return <Hinweis text="Noch keine Anlage gewählt." />
  if (!adapter) return <Hinweis text={`Für „${ident?.label ?? typ}" gibt es noch keine Hub-Sicht.`} />
  if (loading) return <div className="p-3 sm:p-6"><LoadingSpinner text="Lade Komponente…" /></div>
  if (error) return <Hinweis text={error} ton="error" />
  if (geraete.length === 0) return <Hinweis text={`Keine ${ident?.label ?? typ}-Daten erfasst.`} />

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      {/* Geräte-Selektor (Art ①) — nur ab 2 Geräten desselben Typs. */}
      {geraete.length >= 2 && (
        <div className="flex items-center gap-2 overflow-x-auto scrollbar-none">
          {geraete.map((d, i) => (
            <button
              key={d.inv.id || d.label} type="button" onClick={() => setAktiv(i)}
              className={`min-h-[44px] px-3 rounded-lg text-sm font-medium whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                i === aktiv
                  ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                  : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800/50'
              }`}
            >
              {d.label}
              {d.selektorBadge && (
                <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                  {d.selektorBadge}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
      <BlockShell key={`komp-${typ}-${g?.inv.id ?? aktiv}`} persistKey={`v4-komponenten-${typ}`} bloecke={bloecke} sortierbar />
    </div>
  )
}

function Hinweis({ text, ton }: { text: string; ton?: 'error' }) {
  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      <Card><p className={`text-sm ${ton === 'error' ? 'text-red-500' : 'text-gray-500 dark:text-gray-400'}`}>{text}</p></Card>
    </div>
  )
}
