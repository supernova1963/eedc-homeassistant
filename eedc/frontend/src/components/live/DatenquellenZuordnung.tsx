/**
 * DatenquellenZuordnung — feld-zentrische Datenquellen-Fläche (Datenquellen-V4).
 *
 * SoT: docs/drafts/KONZEPT-DATENQUELLEN-V4.md §2b1. Struktur BIS ZUR GERÄTE-EBENE
 * gespiegelt von Einstellungen → Komponenten (`KomponentenEinstellungen`):
 * `BlockShell` mit EINEM Block je Investitionstyp (farbige `TYP_ICON_STYLE`-Icons,
 * „N Geräte"-Summary) + Zusatz-Block „Anlage / Zähler" (Basis-Felder, `Gauge`).
 * Darunter je Gerät eine einklappbare Sub-Sektion (`FormSection ebene="geraet"`)
 * mit einer Feld-Tabelle in 3 Abschnitten nach Einheit: Energie (kWh) · Leistung
 * (W) · Sonstige.
 *
 * Pro Feld genau EINE Quelle (§2d). Drei Quellen-Buttons ersetzen das alte Select:
 * HA-Sensor (Supervisor ODER Remote-Token, transparent — Schritt B) · MQTT-Gateway
 * (vorhandener Picker) · MQTT-Inbound (Standard-Topic, direkt). Aktiver Button =
 * gefüllt; erneuter Klick schaltet auf „keine Quelle". Persistenz in
 * `sensor_mapping.quellen`.
 *
 * Schritt A (diese Fassung): reine Flächen-Umstellung. HA-Sensor-Button ist
 * vorbereitet, aber deaktiviert (Picker folgt Schritt B). Die Amber-„keine
 * Daten"-Markierung gilt vorerst NUR für Inbound-Felder — der quellenübergreifende
 * Wert-Lese-Pfad kommt mit dem Resolver (B5), sonst leuchtete jedes HA-/Gateway-Feld
 * fälschlich amber (§2b1).
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Gauge, Home, Waypoints, Rss, Info, Ban, ArrowUpDown, AlertTriangle } from 'lucide-react'
import { Button } from '../ui'
import FormSection from '../ui/FormSection'
import { BlockShell } from '../blocks/BlockShell'
import type { Block } from '../blocks/types'
import DatenquellenGatewayPicker from './DatenquellenGatewayPicker'
import DatenquellenHaPicker from './DatenquellenHaPicker'
import { useSelectedAnlage } from '../../hooks'
import { TYP_LABELS } from '../../lib/constants'
import { TYP_ICON_STYLE } from '../../pages/InvestitionenTeile'
import {
  datenquellenApi,
  VERBINDUNG_GEAENDERT_EVENT,
  type DatenquelleGruppe,
  type DatenquelleFeld,
  type DatenquellenVerfuegbarkeit,
  type GatewayQuelleConfig,
} from '../../api/datenquellen'

const VERFUEGBARKEIT_DEFAULT: DatenquellenVerfuegbarkeit = { ha: false, ha_quelle: null, mqtt: false }

// Quell-Kennungen (SoT backend datenquellen.py). HA-Sensor deckt beide HA-Wege
// (ha_app = Supervisor, ha_connector = Remote-Token) → EINE Spalte (§2b1).
const Q_INBOUND = 'mqtt_inbound_standard'
const Q_GATEWAY = 'mqtt_gateway'
const Q_KEINE = 'keine'
const Q_HA = new Set(['ha_app', 'ha_connector'])

// Feld-Abschnitte nach Einheit (§2b1): kWh · W · Rest.
type Abschnitt = 'kwh' | 'w' | 'sonstige'
const ABSCHNITT_TITEL: Record<Abschnitt, string> = {
  kwh: 'Energie-Sensoren (kWh)',
  w: 'Leistung-Sensoren (W)',
  sonstige: 'Sonstige Sensoren',
}
const ABSCHNITT_ORDER: Abschnitt[] = ['kwh', 'w', 'sonstige']
function abschnittVon(einheit: string): Abschnitt {
  if (einheit === 'kWh') return 'kwh'
  if (einheit === 'W') return 'w'
  return 'sonstige'
}

// Typ-Icon wie Komponenten; Basis-Block bekommt ein neutrales Zähler-Icon.
const BASIS_STYLE: { icon: LucideIcon; color: string } = { icon: Gauge, color: 'text-gray-500 dark:text-gray-400' }
function typStyle(typ: string): { icon: LucideIcon; color: string } {
  if (typ === 'basis') return BASIS_STYLE
  const s = (TYP_ICON_STYLE as Record<string, { icon: LucideIcon; color: string }>)[typ]
  return s ?? BASIS_STYLE
}

interface TypCluster {
  typ: string
  label: string
  geraete: DatenquelleGruppe[]
}

export default function DatenquellenZuordnung() {
  const { selectedAnlageId } = useSelectedAnlage()
  const [gruppen, setGruppen] = useState<DatenquelleGruppe[]>([])
  const [verfuegbarkeit, setVerfuegbarkeit] = useState<DatenquellenVerfuegbarkeit>(VERFUEGBARKEIT_DEFAULT)
  const [loading, setLoading] = useState(true)
  const [fehler, setFehler] = useState<string | null>(null)
  // Offener Gateway-Picker (Feld, für das gerade eine Fremd-Topic-Quelle gewählt wird).
  const [gatewayFeld, setGatewayFeld] = useState<DatenquelleFeld | null>(null)
  // Offener HA-Sensor-Picker (Feld, für das gerade eine HA-Entity gewählt wird).
  const [haFeld, setHaFeld] = useState<DatenquelleFeld | null>(null)
  // Aufgeklappte Feld-Hinweise (Hilfetexte aus der Registry, Q3).
  const [offeneHinweise, setOffeneHinweise] = useState<Set<string>>(new Set())
  const toggleHinweis = useCallback((id: string) => {
    setOffeneHinweise((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  useEffect(() => {
    if (selectedAnlageId == null) { setLoading(false); return }
    setLoading(true)
    setFehler(null)
    datenquellenApi.getFelder(selectedAnlageId)
      .then((r) => { setGruppen(r.gruppen); setVerfuegbarkeit(r.verfuegbarkeit) })
      .catch((e) => setFehler(e instanceof Error ? e.message : 'Laden fehlgeschlagen'))
      .finally(() => setLoading(false))
  }, [selectedAnlageId])

  // Geräte-Gruppen (Backend, typ-sortiert) zu Typ-Clustern bündeln: gleicher Typ
  // ist konsekutiv → ein Block pro Typ (wie Komponenten), darin die Geräte.
  // Basis („Anlage / Zähler") wird nach vorn gezogen.
  const cluster = useMemo<TypCluster[]>(() => {
    const out: TypCluster[] = []
    for (const g of gruppen) {
      if (g.typ === 'basis') { out.unshift({ typ: 'basis', label: g.titel, geraete: [g] }); continue }
      const last = out[out.length - 1]
      if (last && last.typ === g.typ) last.geraete.push(g)
      else out.push({ typ: g.typ, label: TYP_LABELS[g.typ] ?? g.typ, geraete: [g] })
    }
    return out
  }, [gruppen])

  const neuLaden = useCallback(() => {
    if (selectedAnlageId == null) return
    datenquellenApi.getFelder(selectedAnlageId)
      .then((r) => { setGruppen(r.gruppen); setVerfuegbarkeit(r.verfuegbarkeit) })
      .catch(() => {})
  }, [selectedAnlageId])

  // MQTT-Broker- oder HA-Verbindungs-Block gespeichert → Verfügbarkeit neu laden,
  // damit HA-/Gateway-/Inbound-Optionen ohne F5 ein-/ausblenden.
  useEffect(() => {
    const handler = () => neuLaden()
    window.addEventListener(VERBINDUNG_GEAENDERT_EVENT, handler)
    return () => window.removeEventListener(VERBINDUNG_GEAENDERT_EVENT, handler)
  }, [neuLaden])

  // Feld optimistisch aktualisieren.
  const setzeFeld = useCallback((fieldId: string, patch: Partial<DatenquelleFeld>) => {
    setGruppen((gs) => gs.map((g) => ({
      ...g, felder: g.felder.map((f) => (f.id === fieldId ? { ...f, ...patch } : f)),
    })))
  }, [])

  // Direkte Quelle ohne Modal (Inbound / keine).
  const setzeQuelleDirekt = useCallback((feld: DatenquelleFeld, quelle: string) => {
    if (selectedAnlageId == null) return
    setzeFeld(feld.id, { quelle, gateway_topic: null })
    datenquellenApi.setQuelle(selectedAnlageId, feld.id, quelle).catch(neuLaden)
  }, [selectedAnlageId, setzeFeld, neuLaden])

  const toggleInbound = useCallback((f: DatenquelleFeld) => {
    setzeQuelleDirekt(f, f.quelle === Q_INBOUND ? Q_KEINE : Q_INBOUND)
  }, [setzeQuelleDirekt])

  const toggleGateway = useCallback((f: DatenquelleFeld) => {
    // Aktiv → auf „keine" zurück; sonst Picker (Topic + Transform) öffnen.
    if (f.quelle === Q_GATEWAY) { setzeQuelleDirekt(f, Q_KEINE); return }
    setGatewayFeld(f)
  }, [setzeQuelleDirekt])

  const speichereGateway = useCallback((config: GatewayQuelleConfig) => {
    const feld = gatewayFeld
    if (selectedAnlageId == null || !feld) return
    setGatewayFeld(null)
    setzeFeld(feld.id, { quelle: Q_GATEWAY, gateway_topic: config.quell_topic })
    datenquellenApi.setQuelle(selectedAnlageId, feld.id, Q_GATEWAY, config).catch(neuLaden)
  }, [selectedAnlageId, gatewayFeld, setzeFeld, neuLaden])

  const toggleHa = useCallback((f: DatenquelleFeld) => {
    // Aktiv → auf „keine" zurück; sonst den HA-Entity-Picker öffnen.
    if (Q_HA.has(f.quelle)) { setzeQuelleDirekt(f, Q_KEINE); return }
    setHaFeld(f)
  }, [setzeQuelleDirekt])

  // Vorzeichen-Umkehr — QUELLEN-UNABHÄNGIG (Wert-Eigenschaft, gilt für jede Quelle
  // inkl. Gateway; am Read-Endwert angewendet). Eigener /invert-Endpoint, kein
  // Bezug zur Quellen-Wahl.
  const toggleInvert = useCallback((f: DatenquelleFeld) => {
    if (selectedAnlageId == null) return
    const neu = !f.invertieren
    setzeFeld(f.id, { invertieren: neu })
    datenquellenApi.setInvert(selectedAnlageId, f.id, neu).catch(neuLaden)
  }, [selectedAnlageId, setzeFeld, neuLaden])

  const speichereHa = useCallback((entityId: string) => {
    const feld = haFeld
    if (selectedAnlageId == null || !feld) return
    setHaFeld(null)
    // Transport (ha_app/ha_connector) bestimmt die aktive HA-Verbindung; der
    // Server validiert ihn ohnehin. Vorschau optimistisch mit derselben Kennung.
    const quelle = verfuegbarkeit.ha_quelle ?? 'ha_app'
    setzeFeld(feld.id, { quelle, ha_entity: entityId, gateway_topic: null })
    datenquellenApi.setQuelle(selectedAnlageId, feld.id, quelle, undefined, entityId).catch(neuLaden)
  }, [selectedAnlageId, haFeld, verfuegbarkeit.ha_quelle, setzeFeld, neuLaden])

  // ── Feld-Zeile ──────────────────────────────────────────────────────────────
  const feldZeile = (f: DatenquelleFeld) => {
    const label = f.einheit ? `${f.label} (${f.einheit})` : f.label
    const istInbound = f.quelle === Q_INBOUND
    const istGateway = f.quelle === Q_GATEWAY
    const istHA = Q_HA.has(f.quelle)
    const istKeine = f.quelle === Q_KEINE
    // Wert-lesende Quellen: Inbound + HA + Gateway (Gateway fließt seit C2a über
    // das Standard-Topic in den Inbound-Cache). Amber = zugeordnet, aber Quelle
    // liefert keinen Wert → Ausfall sichtbar (§2d).
    const istMqtt = istInbound || istGateway
    const wertQuelleLiest = istMqtt || istHA
    const amber = wertQuelleLiest && f.wert == null
    // Invert-Toggle für signierte W-Felder — quellen-UNABHÄNGIG (sitzt am Wert):
    // gilt für jede aktive Quelle (HA/Inbound/Gateway). „keine" hat keinen Wert.
    const zeigInvert = f.einheit === 'W' && !istKeine

    let istText: string
    if (f.quelle === Q_KEINE) istText = 'keine Quelle'
    else if (istGateway) istText = `Gateway: ${f.gateway_topic ?? '…'}`
    else if (istHA) istText = `HA: ${f.ha_entity ?? '…'}`
    else istText = f.standard_topic

    let wertText = '–'
    let wertTone = 'text-gray-400 dark:text-gray-500'
    if (wertQuelleLiest && f.wert != null) {
      // Auf 2 Nachkommastellen runden (HA-Rohstates haben oft viele Stellen).
      const wertNum = Math.round(f.wert * 100) / 100
      // eedc-Einheit bei MQTT (Inbound/Gateway, eedc-Topic); HA meldet HA-eigene Einheit.
      wertText = istMqtt && f.einheit ? `${wertNum} ${f.einheit}` : `${wertNum}`
      wertTone = 'text-green-700 dark:text-green-400'
    } else if (amber) {
      wertTone = 'text-amber-600 dark:text-amber-400'
    }

    const hinweisOffen = offeneHinweise.has(f.id)
    return (
      <div key={f.id} className="flex flex-col gap-1.5 py-2 sm:flex-row sm:items-center sm:gap-3">
        <div className={`min-w-0 sm:flex-1 ${istKeine ? 'opacity-60' : ''}`}>
          <div className="flex items-center gap-1">
            <span className="text-sm text-gray-800 dark:text-gray-200">{label}</span>
            {f.hinweis && (
              <Button
                type="button" variant="ghost" size="icon"
                // SoT-Button hat min-h-[36px] (app-weite Aktionshöhe) — für das
                // Inline-Info-Icon mit !min-h-0/!min-w-0 neutralisieren, sonst
                // machen Hinweis-Zeilen die Feld-Zeile 16 px höher als andere.
                className="!h-5 !w-5 !min-h-0 !min-w-0 !p-0.5"
                onClick={() => toggleHinweis(f.id)}
                aria-label="Hinweis anzeigen" aria-expanded={hinweisOffen} title="Hinweis anzeigen"
              >
                <Info className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
              </Button>
            )}
          </div>
          <div className={`font-mono text-xs break-all ${amber ? 'text-amber-600 dark:text-amber-400' : 'text-gray-500 dark:text-gray-400'}`}>
            {istText}
          </div>
          {hinweisOffen && f.hinweis && (
            <p className="mt-1 max-w-prose text-xs text-gray-500 dark:text-gray-400">{f.hinweis}</p>
          )}
          {/* §2i: diagnostische Zuordnungs-Probleme (Einheit/state_class/Redundanz/
              Doppelmapping). Rot=error, amber=warning; Redundanz mit Inline-„auf keine". */}
          {f.probleme.map((p, i) => (
            <div
              key={i}
              className={`mt-1 flex items-start gap-1 text-xs ${
                p.schwere === 'error'
                  ? 'text-red-600 dark:text-red-400'
                  : 'text-amber-600 dark:text-amber-400'
              }`}
            >
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span className="max-w-prose">
                {p.text}
                {p.art === 'redundant' && (
                  <Button
                    type="button" variant="ghost" size="sm"
                    className="!ml-1 !min-h-0 !px-1 !py-0 !text-xs underline"
                    onClick={() => setzeQuelleDirekt(f, Q_KEINE)}
                  >
                    auf keine setzen
                  </Button>
                )}
              </span>
            </div>
          ))}
        </div>
        {/* Wert + ±-Invert direkt am Wert (quellen-unabhängige Wert-Eigenschaft). */}
        <div className={`flex items-center justify-end gap-1 sm:w-28 sm:flex-shrink-0 ${istKeine ? 'opacity-60' : ''}`}>
          <span className={`text-sm tabular-nums ${wertTone}`}>{wertText}</span>
          {zeigInvert && (
            <Button
              type="button"
              variant={f.invertieren ? 'primary' : 'ghost'}
              size="icon"
              className="!h-7 !w-7 !min-h-0 !min-w-0 !p-1"
              onClick={() => toggleInvert(f)}
              aria-pressed={f.invertieren}
              aria-label="Vorzeichen umkehren"
              title="Vorzeichen umkehren — quellen-unabhängig, kehrt das Vorzeichen des Werts um"
            >
              <ArrowUpDown className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
        {/* Quellen-Wahl. Optionen ohne verfügbare Verbindung werden ausgeblendet —
            rein verbindungsbasiert: ohne HA-Verbindung keine HA-Option, ohne
            MQTT-Broker keine Gateway-/Inbound-Option. Eine bestehende Zuordnung
            bleibt trotzdem sichtbar (IST-Spalte + amber Wert), nur nicht mehr
            neu wählbar (ohne Verbindung sinnlos); umschaltbar bleibt „Keine". */}
        <div className="flex flex-wrap items-center gap-1.5 sm:flex-nowrap sm:flex-shrink-0">
          {verfuegbarkeit.ha && (
            <QuelleButton
              icon={Home}
              label="HA-Sensor"
              active={istHA}
              title="HA-Sensor (Entity) zuordnen"
              onClick={() => toggleHa(f)}
            />
          )}
          {verfuegbarkeit.mqtt && (
            <QuelleButton
              icon={Waypoints}
              label="Gateway"
              active={istGateway}
              title="Fremd-Topic vom Broker zuordnen"
              onClick={() => toggleGateway(f)}
            />
          )}
          {verfuegbarkeit.mqtt && (
            <QuelleButton
              icon={Rss}
              label="Inbound"
              active={istInbound}
              title="eedc-Standard-Topic verwenden"
              onClick={() => toggleInbound(f)}
            />
          )}
          <span className="hidden w-px self-stretch bg-gray-200 dark:bg-gray-700 sm:block" aria-hidden="true" />
          <QuelleButton
            icon={Ban}
            label="Keine"
            active={istKeine}
            title="Keine Quelle — Feld manuell / über Vorschläge im Monatsabschluss füllen"
            onClick={() => setzeQuelleDirekt(f, Q_KEINE)}
          />
        </div>
      </div>
    )
  }

  // Feld-Abschnitte (kWh/W/Sonstige) — leere Abschnitte weglassen.
  const abschnitte = (felder: DatenquelleFeld[]) => {
    const buckets: Record<Abschnitt, DatenquelleFeld[]> = { kwh: [], w: [], sonstige: [] }
    for (const f of felder) buckets[abschnittVon(f.einheit)].push(f)
    return ABSCHNITT_ORDER.filter((k) => buckets[k].length > 0).map((k) => (
      <div key={k}>
        <div className="pt-2 pb-0.5 text-xs font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">
          {ABSCHNITT_TITEL[k]}
        </div>
        <div className="divide-y divide-gray-100 dark:divide-gray-800">{buckets[k].map(feldZeile)}</div>
      </div>
    ))
  }

  // Rollup: Felder ohne Quelle je Gerät/Block.
  const ohneQuelle = (felder: DatenquelleFeld[]) => felder.filter((f) => f.quelle === Q_KEINE).length
  const geraetBadge = (g: DatenquelleGruppe) => {
    const ohne = ohneQuelle(g.felder)
    return (
      <span className="text-xs text-gray-400 dark:text-gray-500">
        {g.felder.length} Felder{ohne > 0 && <span className="text-amber-600 dark:text-amber-400"> · {ohne} ohne Quelle</span>}
      </span>
    )
  }

  const bloecke: Block[] = useMemo(() => cluster.map((tc): Block => {
    const style = typStyle(tc.typ)
    const alleFelder = tc.geraete.flatMap((g) => g.felder)
    const ohne = ohneQuelle(alleFelder)
    const istBasis = tc.typ === 'basis'
    const summary = istBasis
      ? `${alleFelder.length} Felder${ohne > 0 ? ` · ${ohne} ohne Quelle` : ''}`
      : `${tc.geraete.length} ${tc.geraete.length === 1 ? 'Gerät' : 'Geräte'}${ohne > 0 ? ` · ${ohne} Felder ohne Quelle` : ''}`
    return {
      id: `dq-${tc.typ}`,
      title: tc.label,
      icon: style.icon,
      farbe: style.color,
      summary,
      defaultOpen: istBasis,
      render: () => (
        istBasis
          ? <div>{abschnitte(tc.geraete[0].felder)}</div>
          : (
            <div className="space-y-2">
              {tc.geraete.map((g) => (
                <FormSection
                  key={g.id}
                  title={g.titel}
                  variant="erweitert"
                  ebene="geraet"
                  defaultOpen={tc.geraete.length === 1}
                  statusSlot={geraetBadge(g)}
                >
                  {abschnitte(g.felder)}
                </FormSection>
              ))}
            </div>
          )
      ),
    }
    // offeneHinweise + verfuegbarkeit müssen in den Deps stehen, sonst frieren die
    // render-Closures Aufklapp-Zustand bzw. Button-Gating ein (BlockShell rendert
    // die memoisierten Blöcke).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [cluster, verfuegbarkeit, offeneHinweise])

  if (loading) return <p className="text-sm text-gray-500 dark:text-gray-400">wird geladen …</p>
  if (fehler) return <p className="text-sm text-red-600 dark:text-red-400">{fehler}</p>
  if (selectedAnlageId == null) return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Anlage gewählt.</p>
  if (cluster.length === 0) return <p className="text-sm text-gray-500 dark:text-gray-400">Keine zuordenbaren Felder.</p>

  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Pro eedc-Feld genau eine Datenquelle. Wählbar sind HA-Sensor, MQTT-Gateway
        (Fremd-Topic vom Broker) und MQTT-Inbound (Standard-Topic). Erneuter Klick auf
        die aktive Quelle schaltet auf „keine Quelle". Zugeordnet, aber ohne empfangenen
        Wert = Hinweis in Amber.
      </p>

      <BlockShell persistKey="v4-einst-datenquellen" bloecke={bloecke} />

      {gatewayFeld && selectedAnlageId != null && (
        <DatenquellenGatewayPicker
          isOpen
          anlageId={selectedAnlageId}
          feldLabel={gatewayFeld.einheit ? `${gatewayFeld.label} (${gatewayFeld.einheit})` : gatewayFeld.label}
          initialTopic={gatewayFeld.gateway_topic}
          onClose={() => setGatewayFeld(null)}
          onSpeichern={speichereGateway}
        />
      )}

      {haFeld && selectedAnlageId != null && (
        <DatenquellenHaPicker
          isOpen
          anlageId={selectedAnlageId}
          feldLabel={haFeld.einheit ? `${haFeld.label} (${haFeld.einheit})` : haFeld.label}
          feldEinheit={haFeld.einheit}
          initialEntity={haFeld.ha_entity}
          onClose={() => setHaFeld(null)}
          onSpeichern={speichereHa}
        />
      )}
    </div>
  )
}

/** Ein Quellen-Button (aktiv = gefüllt). Icon + Label; Klick öffnet Modal bzw. setzt direkt.
 *  Pro Feld ist immer genau EINE Quelle aktiv → der grün gefüllte Chip zeigt die
 *  aktuelle Wahl (auch „Keine"); inaktive bleiben neutral (secondary). */
function QuelleButton({
  icon: Icon, label, active, disabled, title, onClick,
}: {
  icon: LucideIcon
  label: string
  active: boolean
  disabled?: boolean
  title: string
  onClick: () => void
}) {
  return (
    <Button
      type="button"
      variant={active ? 'primary' : 'secondary'}
      size="sm"
      disabled={disabled}
      onClick={onClick}
      title={title}
      aria-pressed={active}
      aria-label={label}
    >
      <Icon className="h-4 w-4" />
      <span className="ml-1.5">{label}</span>
    </Button>
  )
}
