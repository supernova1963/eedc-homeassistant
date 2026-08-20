/**
 * DatenquellenZuordnung — feld-zentrische Datenquellen-Fläche (Datenquellen-V4).
 *
 * SoT: docs/KONZEPT-DATENQUELLEN-V4.md §2b1. Struktur BIS ZUR GERÄTE-EBENE
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
import { Alert, Button } from '../ui'
import FormSection from '../ui/FormSection'
import { BlockShell } from '../blocks/BlockShell'
import type { Block } from '../blocks/types'
import DatenquellenGatewayPicker from './DatenquellenGatewayPicker'
import DatenquellenHaPicker from './DatenquellenHaPicker'
import { useSelectedAnlage } from '../../hooks'
import { TYP_LABELS } from '../../lib/constants'
import { STATUS_TEXT_CLASS } from '../../lib/colors'
import { formatDatum } from '../../lib/datum'
import { TYP_ICON_STYLE } from '../../pages/InvestitionenTeile'
import {
  datenquellenApi,
  VERBINDUNG_GEAENDERT_EVENT,
  type DatenquelleGruppe,
  type DatenquelleFeld,
  type DatenquellenVerfuegbarkeit,
  type GatewayQuelleConfig,
  type HistorieHinweis,
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

// Mehr geänderte Felder werden im Historie-Hinweis nicht einzeln benannt; darüber
// steht „und N weitere". Er soll informieren, nicht das Änderungsprotokoll sein.
const MAX_BENANNTE_FELDER = 6

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
  // Konzept #192 B: offener Hinweis auf die unberührte Historie. Kommt vom
  // Server (Vermerk in `sensor_mapping`) und überlebt damit einen Reload — der
  // Anwender ändert eine Zuordnung und kommt Tage später wieder.
  const [historieHinweis, setHistorieHinweis] = useState<HistorieHinweis | null>(null)
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
      .then((r) => {
        setGruppen(r.gruppen)
        setVerfuegbarkeit(r.verfuegbarkeit)
        setHistorieHinweis(r.historie_hinweis)
      })
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
      .then((r) => {
        setGruppen(r.gruppen)
        setVerfuegbarkeit(r.verfuegbarkeit)
        setHistorieHinweis(r.historie_hinweis)
      })
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
    datenquellenApi.setQuelle(selectedAnlageId, feld.id, quelle)
      .then((r) => setHistorieHinweis(r.historie_hinweis))
      .catch(neuLaden)
  }, [selectedAnlageId, setzeFeld, neuLaden])

  // Der Klick auf eine Quelle WÄHLT sie — er löscht nie. Bis v4.0.0 schaltete ein
  // erneuter Klick auf die aktive Quelle auf „keine" zurück; damit bedeutete
  // derselbe Knopf je nach Zustand „Picker öffnen" oder „Zuordnung verwerfen",
  // und wer nur nachsehen wollte, welcher Sensor hinterlegt ist, verlor ihn
  // (Rainer-PN 2026-07-25). Zum Entfernen gibt es den eigenen „Keine"-Knopf.
  const waehleInbound = useCallback((f: DatenquelleFeld) => {
    if (f.quelle === Q_INBOUND) return
    setzeQuelleDirekt(f, Q_INBOUND)
  }, [setzeQuelleDirekt])

  const waehleGateway = useCallback((f: DatenquelleFeld) => {
    // Auch bei aktivem Gateway: Picker öffnen (Topic + Transform ansehen/ändern).
    setGatewayFeld(f)
  }, [])

  const speichereGateway = useCallback((config: GatewayQuelleConfig) => {
    const feld = gatewayFeld
    if (selectedAnlageId == null || !feld) return
    setGatewayFeld(null)
    setzeFeld(feld.id, { quelle: Q_GATEWAY, gateway_topic: config.quell_topic })
    datenquellenApi.setQuelle(selectedAnlageId, feld.id, Q_GATEWAY, config)
      .then((r) => setHistorieHinweis(r.historie_hinweis))
      .catch(neuLaden)
  }, [selectedAnlageId, gatewayFeld, setzeFeld, neuLaden])

  const waehleHa = useCallback((f: DatenquelleFeld) => {
    // Immer den Picker öffnen — auch wenn HA bereits aktiv ist. Der Picker zeigt
    // die aktuelle Entity vorausgewählt, also ist das zugleich der Weg zum
    // Nachsehen und zum Wechseln.
    setHaFeld(f)
  }, [])

  // Vorzeichen-Umkehr — QUELLEN-UNABHÄNGIG (Wert-Eigenschaft, gilt für jede Quelle
  // inkl. Gateway; am Read-Endwert angewendet). Eigener /invert-Endpoint, kein
  // Bezug zur Quellen-Wahl.
  const toggleInvert = useCallback((f: DatenquelleFeld) => {
    if (selectedAnlageId == null) return
    const neu = !f.invertieren
    setzeFeld(f.id, { invertieren: neu })
    datenquellenApi.setInvert(selectedAnlageId, f.id, neu)
      .then((r) => setHistorieHinweis(r.historie_hinweis))
      .catch(neuLaden)
  }, [selectedAnlageId, setzeFeld, neuLaden])

  const speichereHa = useCallback((entityId: string) => {
    const feld = haFeld
    if (selectedAnlageId == null || !feld) return
    setHaFeld(null)
    // Transport (ha_app/ha_connector) bestimmt die aktive HA-Verbindung; der
    // Server validiert ihn ohnehin. Vorschau optimistisch mit derselben Kennung.
    const quelle = verfuegbarkeit.ha_quelle ?? 'ha_app'
    setzeFeld(feld.id, { quelle, ha_entity: entityId, gateway_topic: null })
    datenquellenApi.setQuelle(selectedAnlageId, feld.id, quelle, undefined, entityId)
      .then((r) => setHistorieHinweis(r.historie_hinweis))
      .catch(neuLaden)
  }, [selectedAnlageId, haFeld, verfuegbarkeit.ha_quelle, setzeFeld, neuLaden])

  // Quittung des Anwenders („Verstanden") — sagt NICHT, dass die Vergangenheit
  // nachgezogen wurde. Optimistisch: der Block verschwindet sofort; scheitert
  // der Aufruf, holt ihn das nächste Laden zurück.
  const quittiereHinweis = useCallback(() => {
    if (selectedAnlageId == null) return
    setHistorieHinweis(null)
    datenquellenApi.quittiereHistorieHinweis(selectedAnlageId).catch(neuLaden)
  }, [selectedAnlageId, neuLaden])

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
    // F-53: Ein Zustandsfeld trägt seine Aussage im Text, nicht in `wert` —
    // sonst gälte eine einwandfreie Zuordnung als Ausfall (amber + „–").
    const wertVorhanden = f.wert != null || f.wert_text != null
    const amber = wertQuelleLiest && !wertVorhanden
    // Invert-Toggle für signierte W-Felder — quellen-UNABHÄNGIG (sitzt am Wert):
    // gilt für jede aktive Quelle (HA/Inbound/Gateway). „keine" hat keinen Wert.
    const zeigInvert = f.einheit === 'W' && !istKeine

    // Klarname vor Entity-ID: „HA: Zähler Einspeisung · sensor.einspeis_kw_monat".
    // Die nackte ID allein war für Tester nicht wiedererkennbar (Rainer-PN
    // 2026-07-25); V3 zeigte hier den Friendly Name.
    let istText: string
    // §2i-6: bei `inaktiv` sagt die Zeile, WARUM hier nichts hingehört, statt
    // ein „keine Quelle“, das wie eine Lücke aussieht.
    if (f.quelle === Q_KEINE) istText = f.bedarf_text || (f.bedarf === 'optional' ? 'optional' : 'keine Quelle')
    else if (istGateway) istText = `Gateway: ${f.gateway_topic ?? '…'}`
    else if (istHA) istText = f.ha_name ? `HA: ${f.ha_name} · ${f.ha_entity}` : `HA: ${f.ha_entity ?? '…'}`
    else istText = f.standard_topic

    let wertText = '–'
    let wertTone = 'text-gray-400 dark:text-gray-500'
    if (wertQuelleLiest && f.wert == null && f.wert_text != null) {
      // F-53: Klartext zuerst, Rohwert daneben — die Fläche beantwortet zwei
      // Fragen: kommt etwas an, und versteht eedc es? Eine unbekannte
      // Schreibweise steht hier als „Unbestimmt (xyz)“ und landet später in
      // „nicht aufgeteilt“, statt einer Seite zugeschlagen zu werden.
      // Deckungsgleich (deutscher Template-Sensor) ⇒ nur einmal.
      const roh = f.wert_text
      const klar = f.wert_klartext
      wertText = klar && klar.toLowerCase() !== roh.toLowerCase() ? `${klar} (${roh})` : (klar ?? roh)
      wertTone = 'text-green-700 dark:text-green-400'
    } else if (wertQuelleLiest && f.wert != null) {
      // Auf 2 Nachkommastellen runden (HA-Rohstates haben oft viele Stellen).
      const wertNum = Math.round(f.wert * 100) / 100
      // eedc-Einheit bei MQTT (Inbound/Gateway, eedc-Topic); HA meldet HA-eigene Einheit.
      wertText = istMqtt && f.einheit ? `${wertNum} ${f.einheit}` : `${wertNum}`
      wertTone = 'text-green-700 dark:text-green-400'
    } else if (amber) {
      wertTone = 'text-amber-600 dark:text-amber-400'
    }

    // §2i-6: offene Pflicht = Feld ist Pflicht, hat keine Quelle und wird auch
    // nicht über seine Alternativ-Gruppe abgedeckt (das Backend hätte sonst
    // `inaktiv` gesetzt). Der Hinweis erklärt dann, was hier hingehört — also
    // ohne Klick zeigen und rot einfärben (Style-Guide D1: Pflicht-Marker `*`,
    // Fehler rot unter dem Feld; Signal-Rot ist seit F2 der Fehler-Kanon).
    const offenePflicht = f.bedarf === 'pflicht' && istKeine
    const hinweisOffen = offeneHinweise.has(f.id) || offenePflicht
    return (
      <div key={f.id} className="flex flex-col gap-1.5 py-2 sm:flex-row sm:items-center sm:gap-3">
        <div className={`min-w-0 sm:flex-1 ${istKeine && !offenePflicht ? 'opacity-60' : ''}`}>
          <div className="flex items-center gap-1">
            <span className="text-sm text-gray-800 dark:text-gray-200">{label}</span>
            {f.bedarf === 'pflicht' && (
              <span className={`${STATUS_TEXT_CLASS.kritisch}`} title="Pflichtfeld">*</span>
            )}
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
                <Info className={`h-3.5 w-3.5 ${offenePflicht ? STATUS_TEXT_CLASS.kritisch : 'text-gray-400 dark:text-gray-500'}`} />
              </Button>
            )}
          </div>
          <div className={`font-mono text-xs break-all ${
            amber ? 'text-amber-600 dark:text-amber-400'
              : offenePflicht ? STATUS_TEXT_CLASS.kritisch
              : 'text-gray-500 dark:text-gray-400'
          }`}>
            {istText}
          </div>
          {hinweisOffen && f.hinweis && (
            <p className={`mt-1 max-w-prose text-xs ${offenePflicht ? STATUS_TEXT_CLASS.kritisch : 'text-gray-500 dark:text-gray-400'}`}>
              {f.hinweis}
            </p>
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
            neu wählbar (ohne Verbindung sinnlos); umschaltbar bleibt „Keine".
            Zusätzlich feldbezogen: `nur_ha` (Preis-Felder) blendet MQTT aus —
            eedc liest sie ausschließlich als HA-Sensor, ein Gateway-Eintrag
            wäre ein Versprechen ohne Leser (Backend riegelt gleichlautend ab). */}
        <div className="flex flex-wrap items-center gap-1.5 sm:flex-nowrap sm:flex-shrink-0">
          {verfuegbarkeit.ha && (
            <QuelleButton
              icon={Home}
              label="HA-Sensor"
              active={istHA}
              title={istHA ? "Zugeordneten HA-Sensor ansehen oder wechseln" : "HA-Sensor (Entity) zuordnen"}
              onClick={() => waehleHa(f)}
            />
          )}
          {verfuegbarkeit.mqtt && !f.nur_ha && (
            <QuelleButton
              icon={Waypoints}
              label="Gateway"
              active={istGateway}
              title={istGateway ? "Zugeordnetes Topic ansehen oder wechseln" : "Fremd-Topic vom Broker zuordnen"}
              onClick={() => waehleGateway(f)}
            />
          )}
          {verfuegbarkeit.mqtt && !f.nur_ha && (
            <QuelleButton
              icon={Rss}
              label="Inbound"
              active={istInbound}
              title="eedc-Standard-Topic verwenden"
              onClick={() => waehleInbound(f)}
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

  // Rollup: NUR offene Pflichtfelder je Gerät/Block (§2i-6).
  // Vorher zählte jedes Feld ohne Quelle — auf einer korrekt eingerichteten
  // Anlage waren das die Aggregat-, Alternativ- und Optional-Felder, also lauter
  // Fehlalarm in Amber (gemessen: 3 von 3 Meldungen). „inaktiv“ und „optional“
  // sind kein offener Punkt; rot bleibt dem vorbehalten, was wirklich fehlt.
  const offenePflichten = (felder: DatenquelleFeld[]) =>
    felder.filter((f) => f.bedarf === 'pflicht' && f.quelle === Q_KEINE).length
  const geraetBadge = (g: DatenquelleGruppe) => {
    const offen = offenePflichten(g.felder)
    return (
      <span className="text-xs text-gray-400 dark:text-gray-500">
        {g.felder.length} Felder{offen > 0 && <span className={STATUS_TEXT_CLASS.kritisch}> · {offen} noch ohne Quelle</span>}
      </span>
    )
  }

  const bloecke: Block[] = useMemo(() => cluster.map((tc): Block => {
    const style = typStyle(tc.typ)
    const alleFelder = tc.geraete.flatMap((g) => g.felder)
    const offen = offenePflichten(alleFelder)
    const istBasis = tc.typ === 'basis'
    const summary = istBasis
      ? `${alleFelder.length} Felder${offen > 0 ? ` · ${offen} noch ohne Quelle` : ''}`
      : `${tc.geraete.length} ${tc.geraete.length === 1 ? 'Gerät' : 'Geräte'}${offen > 0 ? ` · ${offen} Felder noch ohne Quelle` : ''}`
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
        (Fremd-Topic vom Broker) und MQTT-Inbound (Standard-Topic). Ein Klick auf die
        aktive Quelle öffnet ihre Zuordnung zum Ansehen oder Wechseln; zum Entfernen
        dient „Keine". Zugeordnet, aber ohne empfangenen Wert = Hinweis in Amber.
      </p>

      {historieHinweis && (
        <HistorieHinweisBlock
          hinweis={historieHinweis}
          onQuittieren={quittiereHinweis}
        />
      )}

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
          feldKey={haFeld.feld}
          invTyp={haFeld.typ}
          initialEntity={haFeld.ha_entity}
          onClose={() => setHaFeld(null)}
          onSpeichern={speichereHa}
        />
      )}
    </div>
  )
}

/**
 * Hinweis auf die unberührte Historie nach einer Zuordnungsänderung (#192 B).
 *
 * ⚠ **Warum er überhaupt nötig ist:** die gespeicherten Tages- und Stundenwerte
 * tragen die Zuordnung, die zum Zeitpunkt ihres Aggregationslaufs galt. Eine
 * neue Zuordnung wirkt deshalb ab jetzt — rückwirkend ändert sich nichts, bis
 * der Zeitraum neu gerechnet wird. Das galt immer schon; bis 2026-08-13 stand
 * es nur nirgends.
 *
 * Der Block ist **nicht blockierend** und bietet **keinen** Automatismus, der
 * die Vergangenheit nachzieht: er zeigt den Weg zur Bereichs-Reparatur, die der
 * Anwender selbst und in Blöcken auslöst.
 */
function HistorieHinweisBlock({
  hinweis, onQuittieren,
}: {
  hinweis: HistorieHinweis
  onQuittieren: () => void
}) {
  const felder = hinweis.felder
  const benannt = felder.slice(0, MAX_BENANNTE_FELDER)
  const rest = felder.length - benannt.length
  return (
    <Alert type="warning" title="Zuordnung geändert — die bisherigen Werte bleiben, wie sie waren">
      <p>
        Seit {formatDatum(hinweis.seit)} {felder.length === 1 ? 'wurde' : 'wurden'} die
        {' '}Datenquelle{felder.length === 1 ? '' : 'n'} von{' '}
        <span className="font-medium">{benannt.map((f) => f.label).join(' · ')}</span>
        {rest > 0 && <> und {rest} weiteren Feldern</>} geändert. Neue Werte kommen ab
        sofort aus der neuen Quelle; die bereits gespeicherten Tages- und Stundenwerte
        stammen weiter aus der vorherigen Zuordnung.
      </p>
      <p className="mt-2">
        Wenn du die zurückliegenden Tage mit der neuen Zuordnung neu rechnen lassen
        willst, geht das in der Reparatur-Werkbank („Zeitraum neu aggregieren", bis zu
        31 Tage je Lauf). Deine Monatsdaten bleiben dabei unberührt.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => { window.location.hash = '#/einstellungen/daten?block=energieprofil' }}
        >
          Zur Reparatur-Werkbank
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onQuittieren}>
          Verstanden
        </Button>
      </div>
    </Alert>
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
