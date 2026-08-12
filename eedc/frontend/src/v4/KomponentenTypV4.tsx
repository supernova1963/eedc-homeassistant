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
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Card, Alert, fmtCalc, FehlerZustand } from '../components/ui'
import ScrollSchatten from '../components/ui/ScrollSchatten'
import { BlockShell, BlockStackSkeleton, HerkunftZeile, KpiStrip, VerteilungsBalken, type Block, type KpiStripItem } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar, usePark, type ParkApi } from '../components/park'
import { BLOCK_IDENTITAET, STATUS_COLORS, STATUS_ICONS, formatDatum, jaNein, fmtZahl, PARAM_PV_MODULE, LEGACY_KWP_KEY } from '../lib'
import { KOMPONENTEN_IDENTITAET } from '../lib/komponentenStyle'
import { datenquellenApi, type DatenquelleGruppe } from '../api/datenquellen'
import { BarChart3, ClipboardCheck, Cpu, Euro, ExternalLink, FileText, Layers, Network, Paperclip, Radio, Settings, SlidersHorizontal, Zap } from 'lucide-react'
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

/** Slug für view-weit eindeutige parkIds. */
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/gi, '-')
/** block-präfixierte parkId je KPI (Kollisionsschutz über mehrere Blöcke). */
const mitParkId = (prefix: string, kpis: KpiStripItem[]): KpiStripItem[] =>
  kpis.map((k) => ({ ...k, parkId: `kpi:${prefix}-${slug(k.title)}` }))

/** `parameter`-Schlüssel, die oben schon als benannte Zeile stehen — der
 *  Roh-Dump darunter überspringt sie (N119). Ohne das zeigte ein #229-Modul
 *  „Leistung 8,4 kWp" und darunter „kwp 8": dieselbe Größe zweimal, die zweite
 *  auf 0 Nachkommastellen gerundet und damit schlicht falsch. Beide Schlüssel
 *  aus dem Kanon, nicht als Literal wiederholt. */
const STAMM_DUBLETTEN: ReadonlySet<string> = new Set([PARAM_PV_MODULE.LEISTUNG_KWP, LEGACY_KWP_KEY])

/** Parameter-Zeilen einer Investition (Stammdaten + JSON-Parameter).
 *
 *  Anzeige-Stelle ⇒ `leistung_kwp_effektiv` statt der Rohspalte (A26/N106):
 *  eine nur im `parameter`-JSON gepflegte Nennleistung (#229) fehlte hier
 *  ganz. Die Eingabe daneben (Investitionen-Formular) liest weiter roh. */
function paramFelder(inv: Investition): { label: string; wert: string }[] {
  const felder: { label: string; wert: string }[] = []
  if (inv.leistung_kwp_effektiv != null) felder.push({ label: 'Leistung', wert: `${fmtCalc(inv.leistung_kwp_effektiv, 1)} kWp` })
  if (inv.ausrichtung) felder.push({ label: 'Ausrichtung', wert: inv.ausrichtung })
  if (inv.neigung_grad != null) felder.push({ label: 'Neigung', wert: `${inv.neigung_grad}°` })
  if (inv.anschaffungsdatum) felder.push({ label: 'Anschaffung', wert: formatDatum(inv.anschaffungsdatum) })
  if (inv.stilllegungsdatum) felder.push({ label: 'Stilllegung', wert: formatDatum(inv.stilllegungsdatum) })
  if (inv.anschaffungskosten_gesamt != null) felder.push({ label: 'Anschaffungskosten', wert: `${fmtCalc(inv.anschaffungskosten_gesamt, 0)} €` })
  for (const [k, v] of Object.entries(inv.parameter ?? {})) {
    if (v == null || typeof v === 'object' || STAMM_DUBLETTEN.has(k)) continue
    // de-DE-Anzeige: Boolean → Ja/Nein, Zahl → Tausenderpunkt, sonst roh (Enum/Text).
    // Nachkommastellen aus dem Wert, gedeckelt auf 2 — ein fester `nk = 0` machte
    // aus 8,4 eine 8 (N119). Der Dump kennt die Größe nicht, darf also nicht runden.
    const nk = typeof v === 'number' ? Math.min(2, (String(v).split('.')[1] ?? '').length) : 0
    const wert = typeof v === 'boolean' ? jaNein(v) : typeof v === 'number' ? fmtZahl(v, nk) : String(v)
    felder.push({ label: k.replace(/_/g, ' '), wert })
  }
  return felder
}

interface SensorZeile { feld: string; sensor: string; live?: boolean; mqtt?: boolean }

/**
 * Zuordnungs-Zeilen einer Gruppe (Investition oder Anlagen-Basis) aus der
 * **Datenquellen-V4-Wahrheit** (`/datenquellen/{id}/felder`, B7-4).
 *
 * Vorher las dieser Block das alte `sensor_mapping`-JSON direkt (strategie
 * 'sensor' · `live`-Block · Legacy `inv.ha_entity_id`) und driftete damit gegen
 * das `quellen`-Modell: MQTT-Inbound-Felder fehlten ganz, und `ha_entity_id` wurde
 * als aktive Zuordnung gezeigt, obwohl es KEINE Engine liest (nur Speichern/
 * Export/Import — verifiziert 2026-07-16). Jetzt gilt pro Feld die EINE aufgelöste
 * Quelle (§2d): HA-Entity · Gateway-Topic · Inbound-Standard-Topic; „keine" fällt raus.
 */
function zeilenDerGruppe(g: DatenquelleGruppe | undefined): SensorZeile[] {
  const out: SensorZeile[] = []
  for (const f of g?.felder ?? []) {
    if (f.quelle === 'keine') continue
    const ziel = f.ha_entity ?? f.gateway_topic ?? f.standard_topic
    if (!ziel) continue
    out.push({ feld: f.label || f.feld, sensor: ziel, live: f.kategorie === 'live', mqtt: !f.ha_entity })
  }
  return out
}

/** Eine Zuordnungs-Zeile (Feld → Quelle; Live-Marker, MQTT-Icon bei Topic-Quellen). */
function SensorRow({ z }: { z: SensorZeile }) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="text-gray-500 dark:text-gray-400 flex items-center gap-1.5 min-w-0">
        {z.live && <span className="inline-block w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: STATUS_COLORS.ok }} title="Live-Sensor" />}
        {z.mqtt && <Radio className="h-3 w-3 shrink-0" aria-label="MQTT-Quelle" />}
        <span className="truncate">{z.feld}{z.live ? ' (live)' : ''}</span>
      </span>
      {/* D12-12: min-w-0 — sonst greift `truncate` im Flex-Row nicht und lange
          entity_ids schieben die Zeile mobil über den Rand. title = voller Wert. */}
      <code className="text-xs text-gray-700 dark:text-gray-300 truncate min-w-0" title={z.sensor}>{z.sensor}</code>
    </div>
  )
}

// Bearbeitungs-Cross-Links des Komponenten-Hubs (Analyse) → die V4-Einstellungs-Reiter.
// P8-Kurskorrektur: die Geräte-Bearbeitung ist der Einstellungs-Reiter „Komponenten"
// (IST Investitionen); die V4-Einstellungen re-kategorisieren die Ziele (Zuordnung =
// config/v3ZuV4Route). KomponentenTypV4 ist v4-only → feste V4-Ziele (kein V3-Sprung).
const EDIT_INVEST = '#/einstellungen/komponenten'
// B7: Sensor- und MQTT-Zuordnung sind zur EINEN Datenquellen-Fläche verschmolzen
// (eigene Kategorie, §2g) — vorher zwei Links auf denselben Integration-Reiter.
const EDIT_DATENQUELLEN = '#/einstellungen/datenquellen'
const EDIT_INFOTHEK = '#/einstellungen/infothek'
const EDIT_DATENCHECKER = '#/einstellungen/daten'

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
        <Icon className={`h-4 w-4 shrink-0 ${ident?.farbe ?? 'text-gray-400 dark:text-gray-500'}`} />
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
  const [gruppen, setGruppen] = useState<DatenquelleGruppe[]>([])
  const [loading, setLoading] = useState(true)

  // B7-4: EIN Call auf die Datenquellen-Fläche — er trägt Quelle je Feld inkl.
  // Gateway-Topic, damit entfällt der frühere zweite Call (getGatewayMappings).
  useEffect(() => {
    let ab = false
    setLoading(true)
    datenquellenApi.getFelder(anlageId)
      .then((r) => r.gruppen)
      .catch(() => [] as DatenquelleGruppe[])
      .then((g) => { if (!ab) { setGruppen(g); setLoading(false) } })
    return () => { ab = true }
  }, [anlageId])

  const echteInvs = invs.filter((i) => i.id !== 0) // PV-UI-Aggregat (id 0) selbst hat keine Parameter
  const gruppeVon = (id: string) => gruppen.find((g) => g.id === id)
  const basis = zeilenDerGruppe(gruppeVon('basis'))
  const hatZuordnungen = echteInvs.some((i) => zeilenDerGruppe(gruppeVon(`inv:${i.id}`)).length > 0) || basis.length > 0

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
                  {/* D12-12: lange Text-Parameter (z. B. „beschreibung") müssen umbrechen
                      statt über den Rand zu laufen — `break-words` statt `whitespace-nowrap`;
                      dt `shrink-0`, Wert rechtsbündig + `min-w-0`. */}
                  {felder.map((f) => (
                    <div key={f.label} className="flex items-start justify-between gap-2 text-sm border-b border-gray-100 dark:border-gray-800 py-0.5">
                      <dt className="text-gray-500 dark:text-gray-400 capitalize shrink-0">{f.label}</dt>
                      <dd className="font-medium text-gray-900 dark:text-white break-words min-w-0 text-right">{f.wert}</dd>
                    </div>
                  ))}
                </dl>
              ) : <p className="text-xs text-gray-400 dark:text-gray-500">Keine Parameter hinterlegt.</p>}
            </div>
          )
        })}
      </div>

      {/* Zuordnungen — bearbeitbar über die Datenquellen-Fläche (B7: EIN Ziel statt
          getrennter Sensor-/MQTT-Wizards). */}
      <div className="space-y-3">
        <GruppenKopf icon={Cpu} titel="Zuordnungen — Datenquellen" edit={
          <EditLink href={EDIT_DATENQUELLEN}>Datenquellen</EditLink>
        } />
        {loading ? (
          <p className="text-xs text-gray-400 dark:text-gray-500">Lade Zuordnungen…</p>
        ) : !hatZuordnungen ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">Keine Datenquellen zugeordnet.</p>
        ) : (
          <>
            {echteInvs.map((inv) => {
              const sensoren = zeilenDerGruppe(gruppeVon(`inv:${inv.id}`))
              if (!sensoren.length) return null
              return (
                <div key={inv.id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-1.5">
                  <KompKopf inv={inv} />
                  {sensoren.map((s) => <SensorRow key={`${s.feld}-${s.sensor}`} z={s} />)}
                </div>
              )
            })}
            {basis.length > 0 && (
              <div className="rounded-lg border border-gray-100 dark:border-gray-800 p-3 space-y-1 bg-gray-50/50 dark:bg-gray-800/30">
                <div className="text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">Anlagen-Datenquellen</div>
                {basis.map((b) => <SensorRow key={`b-${b.feld}-${b.sensor}`} z={b} />)}
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
                <KatIcon className={`h-3.5 w-3.5 ${cfg?.color ?? 'text-gray-400 dark:text-gray-500'}`} /> {cfg?.label ?? kat}
              </div>
              <ul className="space-y-0.5">
                {eintr.map((e) => (
                  <li key={e.id} className="flex items-center justify-between gap-2 text-sm">
                    {/* D12-12: min-w-0 → langer Dokumenttitel truncatet statt überzulaufen. */}
                    <span className="text-gray-700 dark:text-gray-300 truncate min-w-0" title={e.bezeichnung}>{e.bezeichnung}</span>
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
  const Icon = cfg?.icon ?? STATUS_ICONS.warnung
  return (
    <li className="flex items-start gap-2 text-sm">
      <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${cfg?.colorClass ?? 'text-gray-400 dark:text-gray-500'}`} />
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
            {/* D12-12: Referenz-Wert (z. B. Gerätename) umbrechbar statt nowrap. */}
            <div className="flex items-start justify-between gap-2 border-b border-gray-100 dark:border-gray-800 py-1 text-sm">
              <dt className="text-gray-500 dark:text-gray-400 shrink-0">{z.label}</dt>
              {z.wert && <dd className="font-medium text-gray-900 dark:text-white break-words min-w-0 text-right">{z.wert}</dd>}
            </div>
            {z.hinweis && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{z.hinweis}</p>}
          </div>
        ))}
      </dl>
    )
  }
  // Nur PV-Module BRAUCHEN einen Wechselrichter (Backend: PARENT_REQUIRED).
  // Ein Speicher ohne Zuordnung ist der Normalfall eines AC-gekoppelten Speichers
  // — die frühere Warnung forderte den falschen Zustand ein und trieb Tester in
  // eine Zuordnung, die sie danach nicht mehr lösen konnten (JayJay, Forum v4.0.0).
  const hatOrphan = s.orphanModule.length > 0 || s.orphanSpeicher.length > 0
  return (
    <div className="space-y-3">
      {s.orphanModule.length > 0 && (
        <Alert type="warning">
          {`${s.orphanModule.length} PV-Modul(e) ohne Wechselrichter-Zuordnung.`}
        </Alert>
      )}
      {s.wr.map((w, i) => (
        <div key={i} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
          <div className="flex items-center gap-2 font-medium text-gray-900 dark:text-white">
            <Zap className="h-4 w-4 text-gray-400 dark:text-gray-500" />
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
          {/* Neutral formuliert: eigenständig ist für Speicher ein gültiger Zustand. */}
          <TopoListe titel="Eigenständige Speicher" items={s.orphanSpeicher} />
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
/** Roh-KPIs der Ertrags-Zusammensetzung (ohne parkId) — der Aufrufer versieht sie mit
 *  `mitParkId('wirt', …)`, damit jede Ertragsposten-Kachel einzeln parkbar ist. */
function wirtKpis(w: NonNullable<KompGeraet['wirtschaftlichkeit']>): KompGeraet['status'] {
  if (w.nichtBewertet) return []
  const posten = w.posten.filter((p) => (p.euro ?? 0) > 0)
  const kpis: KompGeraet['status'] = posten.map((p) => ({
    title: p.label, value: fmtCalc(p.euro, 0, '—'), unit: '€', color: 'green', icon: Euro, subtitle: p.hinweis,
  }))
  if (w.gesamt) kpis.push({ title: w.gesamt.label, value: fmtCalc(w.gesamt.euro, 0, '—'), unit: '€', color: 'blue', icon: Euro })
  return kpis
}

/** Element-Park-IDs des generischen Wirtschaftlichkeits-Blocks (jede Anzeige einzeln). */
function wirtParkIds(w: NonNullable<KompGeraet['wirtschaftlichkeit']>, kpis: KompGeraet['status']): string[] {
  if (w.nichtBewertet) return ['el:wirt-nichtbewertet']
  const posten = w.posten.filter((p) => (p.euro ?? 0) > 0)
  const ids = kpis.map((k) => k.parkId).filter((x): x is string => !!x)
  if (posten.length >= 2) ids.push('el:wirt-balken')
  if (w.hinweis) ids.push('el:wirt-hinweis')
  return ids
}

/** Generische Ertrags-Zusammensetzung — KpiStrip (je Posten parkbar) + Aufteilungs-
 *  balken + Hinweis, JE eigene Parkbar (Doktrin, wie Block ① Status). `kpis` kommen
 *  bereits parkId-versehen vom Aufrufer. */
function WirtschaftlichkeitInhalt({ w, kpis }: {
  w: NonNullable<KompGeraet['wirtschaftlichkeit']>; kpis: KompGeraet['status']
}) {
  if (w.nichtBewertet) return (
    <Parkbar id="el:wirt-nichtbewertet" titel="Wirtschaftlichkeit"><Alert type="info">{w.nichtBewertet}</Alert></Parkbar>
  )
  const posten = w.posten.filter((p) => (p.euro ?? 0) > 0)
  return (
    <div className="space-y-4">
      {kpis.length > 0 && <KpiStrip kpis={kpis} />}
      {posten.length >= 2 && (
        <Parkbar id="el:wirt-balken" titel="Zusammensetzung des Ertrags">
          <VerteilungsBalken titel="Zusammensetzung des Ertrags" einheit="€"
            segmente={posten.map((p) => ({ label: p.label, wert: p.euro, farbe: p.farbe }))} />
        </Parkbar>
      )}
      {w.hinweis && (
        <Parkbar id="el:wirt-hinweis" titel="Wirtschaftlichkeit-Hinweis">
          <p className="text-xs text-gray-400 dark:text-gray-500">{w.hinweis}</p>
        </Parkbar>
      )}
    </div>
  )
}

type MeldeBlock = (block: string, ids: string[]) => void

/** Blöcke eines Geräts — exportiert für Block-Tests (Muster `baueKomponentenBloecke`). */
export function geraetBloecke(g: KompGeraet, typ: string, anlageId: number, park: ParkApi, gemeldet: Record<string, string[]>, melde: MeldeBlock): Block[] {
  const analyse = KOMPONENTEN_ANALYSE[typ]
  const istGeparkt = (id: string) => park.istGeparkt(id)
  // Element-Park-Doktrin (Gernot 2026-06-27): JEDE Anzeige im Block einzeln parkbar
  // (KPIs, Charts, Tabellen, Balken, Hinweise); der Block selbst NICHT. Sind ALLE
  // Element-IDs eines Blocks geparkt → Block ausblenden.
  const alleGeparkt = (ids: string[]) => ids.length > 0 && ids.every(istGeparkt)
  // Registry-Composites (④/⑤/Wirtschaftlichkeit) sind intern in Einzel-Parkbars
  // zerlegt (Phase 2, Gernot 2026-07-09): das Composite MELDET seine real gerenderten
  // Park-IDs hoch (`gemeldet[key]`). Block ausblenden, sobald ALLE gemeldeten geparkt
  // sind — solange nichts gemeldet ist (Block noch nie geöffnet), bleibt er sichtbar.
  const regVerstecken = (key: string) => {
    const ids = gemeldet[key]
    return ids != null && ids.length > 0 && ids.every(istGeparkt)
  }
  const bloecke: Block[] = []

  // ① Status (Pflicht) — D2-KPIs + Hinweise + Sub-Strips + Aufteilung, je parkbar.
  // B4 (Gernot 2026-07-09): die Sub-Strips (Kennzahlen/Sekundär) sind KEINE atomare
  // Anzeige — jede KACHEL wird einzeln parkbar (`mitParkId`, Gold-Standard), statt den
  // ganzen KpiStrip in EINE Parkbar zu hüllen. Die Sub-Überschrift verschwindet mit der
  // letzten geparkten Kachel (wie GeraeteSektionen).
  const statusKpis = mitParkId('status', g.status)
  const kennzahlenKpis = g.kennzahlen ? mitParkId('status-kennzahlen', g.kennzahlen.kpis) : []
  const sekundaerKpis = g.sekundaer ? mitParkId('status-sekundaer', g.sekundaer.kpis) : []
  const parkIdsVon = (kpis: KpiStripItem[]) => kpis.map((k) => k.parkId).filter((x): x is string => !!x)
  const einSichtbar = (kpis: KpiStripItem[]) => kpis.some((k) => !k.parkId || !istGeparkt(k.parkId))
  const statusIds = [
    ...parkIdsVon(statusKpis),
    ...(g.hinweise?.map((_, i) => `el:status-hinweis-${i}`) ?? []),
    ...parkIdsVon(kennzahlenKpis),
    ...(g.aufteilung ? ['el:status-aufteilung'] : []),
    ...parkIdsVon(sekundaerKpis),
  ]
  if (!alleGeparkt(statusIds)) bloecke.push({
    id: 'status', title: 'Aktueller Status', ...BLOCK_IDENTITAET.kennzahlen,
    summary: g.status.map((k) => `${k.value} ${k.unit ?? ''}`.trim()).slice(0, 2).join(' · '),
    defaultOpen: true,
    render: () => (
      <div className="space-y-4">
        <KpiStrip kpis={statusKpis} />
        {g.hinweise?.map((h, i) => <Parkbar key={i} id={`el:status-hinweis-${i}`} titel="Hinweis"><Alert type={h.ton}>{h.text}</Alert></Parkbar>)}
        {g.kennzahlen && einSichtbar(kennzahlenKpis) && <KpiUnterblock titel={g.kennzahlen.titel} kpis={kennzahlenKpis} />}
        {g.aufteilung && <Parkbar id="el:status-aufteilung" titel={g.aufteilung.titel}><VerteilungsBalken titel={g.aufteilung.titel} einheit={g.aufteilung.einheit} segmente={g.aufteilung.segmente} /></Parkbar>}
        {g.sekundaer && einSichtbar(sekundaerKpis) && <KpiUnterblock titel={g.sekundaer.titel} kpis={sekundaerKpis} />}
      </div>
    ),
  })

  // ② Struktur/Verknüpfung (ein Element).
  if (g.struktur && !istGeparkt('el:struktur')) {
    const topo = g.struktur.art === 'topologie'
    bloecke.push({
      id: 'struktur', title: topo ? 'System-Struktur' : 'Zuordnung & Datenquelle', icon: Network,
      summary: topo ? 'Wechselrichter → Module / Speicher' : 'Kopplung und Herkunft der Werte',
      defaultOpen: false,
      render: () => <Parkbar id="el:struktur" titel="Struktur"><StrukturInhalt s={g.struktur!} /></Parkbar>,
    })
  }

  // ③ Sub-Komponente — Hinweis + KPIs, je parkbar.
  if (g.subKomponente) {
    const subKpis = mitParkId('sub', g.subKomponente.kpis)
    const subIds = [...subKpis.map((k) => k.parkId).filter((x): x is string => !!x), ...(g.subKomponente.hinweis ? ['el:sub-hinweis'] : [])]
    if (!alleGeparkt(subIds)) bloecke.push({
      id: 'sub', title: g.subKomponente.titel, icon: Layers,
      summary: g.subKomponente.kpis.map((k) => `${k.value} ${k.unit ?? ''}`.trim()).slice(0, 2).join(' · '),
      defaultOpen: false,
      render: () => (
        <div className="space-y-3">
          {g.subKomponente!.hinweis && <Parkbar id="el:sub-hinweis" titel="Hinweis"><p className="text-xs text-gray-400 dark:text-gray-500">{g.subKomponente!.hinweis}</p></Parkbar>}
          <KpiStrip kpis={subKpis} />
        </div>
      ),
    })
  }

  // ④ Verlauf — Registry-Analyse = intern zerlegtes Composite (meldet seine IDs hoch,
  //    KEINE umhüllende Parkbar mehr); generischer Verlauf = Chart + Verteilungen +
  //    Monatstabelle, je parkbar; ohne Daten ein parkbarer Hinweis.
  const verlaufVerstecken = analyse?.verlauf
    ? regVerstecken('verlauf')
    : alleGeparkt(g.verlauf
      ? ['el:verlauf', ...(g.verlauf.verteilungen?.map((_, i) => `el:verlauf-vert-${i}`) ?? []), ...(typ !== 'pv-module' ? ['el:verlauf-tabelle'] : [])]
      : ['el:verlauf-hinweis'])
  if (!verlaufVerstecken) bloecke.push({
    id: 'verlauf', title: 'Verlauf (gesamte Historie)', ...BLOCK_IDENTITAET.verlauf,
    summary: 'Zeitreihe über die gesamte Laufzeit', defaultOpen: false,
    render: (fokus) => (analyse?.verlauf
      ? analyse.verlauf(anlageId, g.inv, (ids) => melde('verlauf', ids))
      : g.verlauf
        ? (
          <div className="space-y-4">
            <Parkbar id="el:verlauf" titel="Verlauf">
              {/* Gerechnete statt gemessene Werte werden am Chart-Kopf ausgewiesen
                  (PV: Modul-Stapel = kWp-Anteil) — dasselbe Zustands-Badge wie am
                  Verteilungsbalken, kein zweiter Satz Bildsprache (Regel 0a). */}
              <HerkunftZeile herkunft={g.verlauf.herkunft} className="mb-2" />
              <KomponentenVerlaufChart rows={g.verlauf.rows} bars={g.verlauf.bars} einheit={g.verlauf.einheit} gestapelt={g.verlauf.gestapelt} tall={fokus} />
            </Parkbar>
            {g.verlauf.verteilungen && g.verlauf.verteilungen.length > 0 && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {g.verlauf.verteilungen.map((v, i) => (
                  <Parkbar key={v.titel} id={`el:verlauf-vert-${i}`} titel={v.titel}><VerteilungsBalken titel={v.titel} einheit={v.einheit} segmente={v.segmente} herkunft={v.herkunft} /></Parkbar>
                ))}
              </div>
            )}
            {/* Scoped read-only Monats-Detailtabelle (WKW 1-42/70) — selbe Daten wie der Chart.
                PV ausgenommen: dessen ④ ist jahres-aggregiert (Modul-Stapel), keine Monatszeilen. */}
            {typ !== 'pv-module' && (
              <Parkbar id="el:verlauf-tabelle" titel="Monats-Detailtabelle">
                <KomponentenMonatsTabelle rows={g.verlauf.rows} bars={g.verlauf.bars} einheit={g.verlauf.einheit} />
              </Parkbar>
            )}
          </div>
        )
        : <Parkbar id="el:verlauf-hinweis" titel="Verlauf-Hinweis"><FolgtHinweis text="Für diesen Typ liegt keine eigene Zeitreihe vor (z. B. Wallbox = aus E-Auto-Ladung abgeleitet)." /></Parkbar>),
  })

  // ⑤ Vergleich — Registry-Analyse = intern zerlegtes Composite (meldet IDs hoch);
  //    generische Analyse/Hinweis = je ein parkbares Element.
  const vergleichVerstecken = analyse?.vergleich
    ? regVerstecken('vergleich')
    : alleGeparkt(g.vergleich ? ['el:vergleich'] : ['el:vergleich-hinweis'])
  if (!vergleichVerstecken) bloecke.push({
    id: 'vergleich', title: 'Vergleich', icon: BarChart3,
    summary: analyse?.vergleich ? 'Komponentenspezifischer Vergleich' : 'Jahresvergleich · Diagramm ⇄ Tabelle', defaultOpen: false,
    render: () => (analyse?.vergleich
      ? analyse.vergleich(anlageId, g.inv, (ids) => melde('vergleich', ids))
      : g.vergleich
        ? <Parkbar id="el:vergleich" titel="Vergleich"><KomponentenVergleich label={g.vergleich.label} einheit={g.vergleich.einheit} farbe={g.vergleich.farbe} jahre={g.vergleich.jahre} /></Parkbar>
        : <Parkbar id="el:vergleich-hinweis" titel="Vergleich-Hinweis"><FolgtHinweis
            text="Für diesen Typ liegt noch kein Jahresvergleich vor."
            crossLink={{ label: 'Alle Werte / Tabelle →', href: '#/auswertungen/tabelle' }}
          /></Parkbar>),
  })

  // Wirtschaftlichkeit — Registry-Analyse = intern zerlegtes Composite (meldet IDs
  // hoch); generische Ertrags-Zusammensetzung = KpiStrip (je Posten parkbar) + Balken
  // + Hinweis, je eigene Parkbar; Block entfällt erst, wenn ALLE geparkt sind.
  if (analyse?.wirtschaftlichkeit) {
    if (!regVerstecken('wirtschaftlichkeit')) bloecke.push({
      id: 'wirtschaftlichkeit', title: 'Wirtschaftlichkeit', icon: Euro,
      summary: 'Kostenvergleich & Ersparnis', defaultOpen: false,
      render: () => analyse.wirtschaftlichkeit!(anlageId, g.inv, (ids) => melde('wirtschaftlichkeit', ids)),
    })
  } else if (g.wirtschaftlichkeit) {
    const wKpis = mitParkId('wirt', wirtKpis(g.wirtschaftlichkeit))
    if (!alleGeparkt(wirtParkIds(g.wirtschaftlichkeit, wKpis))) bloecke.push({
      id: 'wirtschaftlichkeit', title: 'Wirtschaftlichkeit', icon: Euro,
      summary: 'Ertrags-Zusammensetzung', defaultOpen: false,
      render: () => <WirtschaftlichkeitInhalt w={g.wirtschaftlichkeit!} kpis={wKpis} />,
    })
  }

  // Dimensionierung — was-wäre-wenn zur Gerätegröße (Speicher: Sizing-Simulator,
  // #358 Phase 3). Eigener Block hinter „Wirtschaftlichkeit", weil dort die
  // Vorfrage steht („hätte mehr Kapazität überhaupt geholfen?") und die Antwort
  // hier („wie viel, und rechnet sie sich?") sonst darunter verschwände.
  if (analyse?.dimensionierung && !regVerstecken('dimensionierung')) bloecke.push({
    id: 'dimensionierung', title: 'Größerer Speicher?', icon: SlidersHorizontal,
    summary: 'Was eine andere Größe gebracht hätte', defaultOpen: false,
    render: () => analyse.dimensionierung!(anlageId, g.inv, (ids) => melde('dimensionierung', ids)),
  })

  // ⑥ Aussicht entfällt im Hub (Gernot 2026-06-21): zeitliche Differenzierung → Cockpit/Aussicht.

  // Dokumente & Infos (#243) — N:M-verknüpfte Infothek-Einträge dieser Komponente (ein Element).
  if (!istGeparkt('el:infothek')) bloecke.push({
    id: 'infothek', title: 'Dokumente & Infos', icon: FileText,
    summary: 'Verträge, Datenblätter & Dokumente dieser Komponente', defaultOpen: false,
    render: () => <Parkbar id="el:infothek" titel="Dokumente & Infos"><InfothekBlock invs={g.verknuepfteInvs ?? [g.inv]} /></Parkbar>,
  })

  // Daten-Qualität (#243) — komponenten-zuordenbare Befunde (ein Element).
  if (!istGeparkt('el:daten-checker')) bloecke.push({
    id: 'daten-checker', title: 'Daten-Qualität', icon: ClipboardCheck,
    summary: 'Offene Daten-Befunde dieser Komponente', defaultOpen: false,
    render: () => <Parkbar id="el:daten-checker" titel="Daten-Qualität"><DatenCheckerBlock anlageId={anlageId} invs={g.verknuepfteInvs ?? [g.inv]} /></Parkbar>,
  })

  // ⑦ Einstellungen (Pflicht) — Parameter + Datenquellen-Zuordnungen (ein Element).
  if (!istGeparkt('el:einstellungen')) bloecke.push({
    id: 'einstellungen', title: 'Einstellungen', icon: Settings,
    summary: 'Parameter & Datenquellen dieser Komponente — mit Bearbeiten-Links', defaultOpen: false,
    render: () => <Parkbar id="el:einstellungen" titel="Einstellungen"><EinstellungenBlock anlageId={anlageId} invs={g.verknuepfteInvs ?? [g.inv]} /></Parkbar>,
  })

  return bloecke
}

export default function KomponentenTypV4(props: { typ: string; anlageId: number | undefined }) {
  // ParkProvider je Typ-Sicht (eigener LS-Scope `eedc-park:v4-komponenten-<typ>`,
  // analog zur BlockShell-Persistenz). Element-Park der ①Status-KPIs.
  return (
    <ParkProvider persistKey={`v4-komponenten-${props.typ}`}>
      <KomponentenTypInner {...props} />
    </ParkProvider>
  )
}

function KomponentenTypInner({ typ, anlageId }: { typ: string; anlageId: number | undefined }) {
  const park = usePark()
  // Von den Registry-Composites hochgemeldete Park-IDs je Block (Auto-Hide, Phase 2).
  // Überlebt das Unmounten eines versteckten Blocks → kein Oszillieren; Gleichheits-
  // geschützt gegen Render-Schleifen.
  const [gemeldet, setGemeldet] = useState<Record<string, string[]>>({})
  const melde = useCallback<MeldeBlock>((block, ids) => {
    setGemeldet((s) => {
      const cur = s[block]
      if (cur && cur.length === ids.length && cur.every((v, i) => v === ids[i])) return s
      return { ...s, [block]: ids }
    })
  }, [])
  const [geraete, setGeraete] = useState<KompGeraet[]>([])
  const [aktiv, setAktiv] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // S15-Retry: Zähler re-triggert den Lade-Effekt (verhaltenserhaltend — der Fetch
  // lebt bewusst inline im Effekt, kein Refactor nötig).
  const [retryKey, setRetryKey] = useState(0)

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
  }, [anlageId, adapter, typ, retryKey])

  const g = geraete[aktiv]
  const bloecke = useMemo(() => (g ? geraetBloecke(g, typ, anlageId ?? 0, park, gemeldet, melde) : []), [g, typ, anlageId, park, gemeldet, melde])

  if (!anlageId) return <Hinweis text="Noch keine Anlage gewählt." />
  if (!adapter) return <Hinweis text={`Für „${ident?.label ?? typ}" gibt es noch keine Hub-Sicht.`} />
  // B8 (S15): BlockStack-Skeleton (①Status offen + Analyse-Köpfe); Geräte-Selektor
  // bewusst NICHT vorgetäuscht (Anzahl vor dem Laden unbekannt).
  if (loading) return <div className="p-3 sm:p-6 max-w-[1920px] mx-auto"><BlockStackSkeleton label="Lade Komponente…" zu={4} /></div>
  if (error) {
    // B8-Fehler-Baustein (S15) statt des grauen Hinweis-Helpers im error-Ton.
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <FehlerZustand text={error} onRetry={() => setRetryKey((k) => k + 1)} />
      </div>
    )
  }
  if (geraete.length === 0) return <Hinweis text={`Keine ${ident?.label ?? typ}-Daten erfasst.`} />

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      {/* Geräte-Selektor (Art ①) — nur ab 2 Geräten desselben Typs.
          Bewusst KEIN ui/SegmentControl (R3b S4, 2026-07-05): das ist ein scrollbarer
          Pill-/Tab-Selektor mit Badges (B3-Territorium, Primary-Tint-Aktivstil) und
          44-px-Touch-Target, keine 32-px-Toolbar-Segmentgruppe. */}
      {geraete.length >= 2 && (
        <ScrollSchatten className="flex items-center gap-2">
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
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-50 text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                  {d.selektorBadge}
                </span>
              )}
            </button>
          ))}
        </ScrollSchatten>
      )}
      <BlockShell key={`komp-${typ}-${g?.inv.id ?? aktiv}`} persistKey={`v4-komponenten-${typ}`} bloecke={bloecke} sortierbar />

      {/* Element-Park-Fuß (SLICE 1): Hinweiszeile + „Geparkt (n)". Inert ohne Provider. */}
      <ParkFuss />
    </div>
  )
}

/** Grauer Seiten-Hinweis (Leer-Territorium) — Fehler laufen über FehlerZustand (S15). */
function Hinweis({ text }: { text: string }) {
  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      <Card><p className="text-sm text-gray-500 dark:text-gray-400">{text}</p></Card>
    </div>
  )
}
