/**
 * DatenquellenThemen — Block «Themen» je Gerät mit «Überblick» in den Datenquellen (Themen-Kacheln 4.2.0, TH-E1 §1.5).
 *
 * Ein **Thema** ist eine Kachel im Schaubild des Komponenten-Hubs (gebaut in TH-E2); seine **Einträge** sind frei
 * gewählte HA-Entitäten bzw. MQTT-Topics, deren Wert eedc **wie geliefert** zeigt — kein Registry-Feld, keine Rechnung,
 * keine Mitschrift (Bauplan §0). Der Block steht nur an Geräten aus `UEBERBLICK_TYPEN` (Spiegel des Backends), nach den
 * Abschnitten bzw. Betriebsart-Blöcken und vor «Weitere Größen erfassen».
 *
 * Die **Zeile eines Eintrags** ist eine Form-Kopie der Feldzeile in `DatenquellenZuordnung.tsx::feldZeile` (dieselben
 * Klassen, derselbe `QuelleButton`). ⚠ **Pflegehinweis:** die Feldzeile hängt an zwölf Zustandsgrößen der Fläche
 * (Hinweise, Pflicht, Probleme, Invert, Werte-Tabelle) und ist ohne Verhaltensänderung nicht herauslösbar; wer dort
 * Klassen oder Knopf-Reihenfolge ändert, zieht diese Zeile mit (Muster S1b `fahrzeugZustandZeile`).
 *
 * Schreibwege: die sechs Themen-Routen (`datenquellenApi.thema*`/`eintrag*` mit der Geräte-ID — Kennungen sind nur je
 * Gerät eindeutig, Nachlauf 4.2.0 H2; Antwort = Themen des Geräts) und für die
 * Quelle die Feld-Route `setQuelle(feld_id)` — danach lädt die Fläche neu (`onNeuLaden`).
 */
import { useCallback, useEffect, useState } from 'react'
import { Ban, ChevronDown, ChevronUp, Home, Plus, Rss, Waypoints, X } from 'lucide-react'
import { Button, ConfirmDialog, Input } from '../ui'
import { STATUS_TEXT_CLASS } from '../../lib/colors'
import { STATUS_ICONS } from '../../lib/komponentenStyle'
import { UEBERBLICK_TYPEN } from '../../v4/KomponentenTypV4'
import DatenquellenGatewayPicker from './DatenquellenGatewayPicker'
import DatenquellenHaPicker from './DatenquellenHaPicker'
import QuelleButton from './DatenquellenQuelleButton'
import {
  datenquellenApi,
  type DatenquelleGruppe,
  type DatenquellenVerfuegbarkeit,
  type GatewayQuelleConfig,
  type ThemaEintragZeile,
  type ThemaGruppe,
} from '../../api/datenquellen'

const Q_INBOUND = 'mqtt_inbound_standard'
const Q_GATEWAY = 'mqtt_gateway'
const Q_KEINE = 'keine'
const Q_HA = new Set(['ha_app', 'ha_connector'])

/** Die Hinweiszeile unter dem Kopf (Gernot 1.11.2026, Bauplan TH-E1 §1.5) — wörtlich. */
export const THEMEN_HINWEIS =
  'Jedes Thema ist eine Kachel im Schaubild: die ersten zwei Einträge mit Wert stehen im Bild, alle im Tooltip und in '
  + 'der Karte «Themen» — die Reihenfolge stellst du mit den Pfeilen ein. Angezeigt wird, was Home Assistant liefert '
  + '(z. B. locked); für Klartext einen Template-Helfer zuordnen.'

/** Hat dieses Gerät einen Block «Themen»? — dieselben Typen wie der Block «Überblick» im Hub. */
export function hatThemen(typ: string): boolean {
  return UEBERBLICK_TYPEN.includes(typ)
}

/** Investitions-ID aus der Gruppen-ID `inv:<id>` — `null` für die Basis. */
function investitionId(g: DatenquelleGruppe): number | null {
  const m = /^inv:(\d+)$/.exec(g.id)
  return m ? Number(m[1]) : null
}

interface Props {
  anlageId: number
  gruppe: DatenquelleGruppe
  verfuegbarkeit: DatenquellenVerfuegbarkeit
  /** Nach einer Quellen-Wahl: die Fläche lädt `GET /felder` neu (Zuordnung, Klarname, Wert). */
  onNeuLaden: () => void
}

/** Inline editierbarer Text — Enter oder Verlassen speichert, Escape verwirft. */
function InlineText({ wert, label, maxLength, onSpeichern }: {
  wert: string; label: string; maxLength: number; onSpeichern: (neu: string) => void
}) {
  const [text, setText] = useState(wert)
  useEffect(() => setText(wert), [wert])
  const speichern = () => {
    const neu = text.trim()
    if (neu && neu !== wert) onSpeichern(neu)
    else setText(wert)
  }
  return (
    <Input
      value={text}
      maxLength={maxLength}
      aria-label={label}
      onChange={(e) => setText(e.target.value)}
      onBlur={speichern}
      onKeyDown={(e) => {
        if (e.key === 'Enter') { e.preventDefault(); (e.target as HTMLInputElement).blur() }
        if (e.key === 'Escape') { setText(wert); (e.target as HTMLInputElement).blur() }
      }}
      className="!py-1 text-sm"
    />
  )
}

function PfeilKnoepfe({ index, anzahl, was, onVerschieben }: {
  index: number; anzahl: number; was: string; onVerschieben: (position: number) => void
}) {
  return (
    <span className="flex items-center gap-0.5">
      <Button type="button" variant="ghost" size="icon" className="!h-7 !w-7 !min-h-0 !min-w-0 !p-1"
        disabled={index === 0} onClick={() => onVerschieben(index - 1)} aria-label={`${was} nach oben`} title={`${was} nach oben`}>
        <ChevronUp className="h-3.5 w-3.5" />
      </Button>
      <Button type="button" variant="ghost" size="icon" className="!h-7 !w-7 !min-h-0 !min-w-0 !p-1"
        disabled={index >= anzahl - 1} onClick={() => onVerschieben(index + 1)} aria-label={`${was} nach unten`} title={`${was} nach unten`}>
        <ChevronDown className="h-3.5 w-3.5" />
      </Button>
    </span>
  )
}

export default function DatenquellenThemen({ anlageId, gruppe, verfuegbarkeit, onNeuLaden }: Props) {
  const invId = investitionId(gruppe)
  const [themen, setThemen] = useState<ThemaGruppe[]>(gruppe.themen ?? [])
  const [fehler, setFehler] = useState<string | null>(null)
  const [entfernen, setEntfernen] = useState<ThemaGruppe | null>(null)
  const [haEintrag, setHaEintrag] = useState<ThemaEintragZeile | null>(null)
  const [gatewayEintrag, setGatewayEintrag] = useState<ThemaEintragZeile | null>(null)
  useEffect(() => setThemen(gruppe.themen ?? []), [gruppe.themen])

  const ausfuehren = useCallback((aufruf: Promise<{ themen: ThemaGruppe[] }>) => {
    setFehler(null)
    return aufruf
      .then((r) => setThemen(r.themen))
      .catch((e) => setFehler(e instanceof Error ? e.message : 'Speichern fehlgeschlagen'))
  }, [])

  const setzeQuelle = useCallback((e: ThemaEintragZeile, quelle: string, gateway?: GatewayQuelleConfig, entity?: string) => {
    setFehler(null)
    setThemen((ts) => ts.map((t) => ({
      ...t, eintraege: t.eintraege.map((x) => (x.id === e.id ? { ...x, quelle, ...(entity ? { ha_entity: entity } : {}) } : x)),
    })))
    datenquellenApi.setQuelle(anlageId, e.feld_id, quelle, gateway, entity)
      .then(onNeuLaden)
      .catch((err) => { setFehler(err instanceof Error ? err.message : 'Speichern fehlgeschlagen'); onNeuLaden() })
  }, [anlageId, onNeuLaden])

  if (!hatThemen(gruppe.typ) || invId == null) return null
  const InfoIcon = STATUS_ICONS.info

  const eintragZeile = (t: ThemaGruppe, e: ThemaEintragZeile, index: number) => {
    const istInbound = e.quelle === Q_INBOUND
    const istGateway = e.quelle === Q_GATEWAY
    const istHA = Q_HA.has(e.quelle)
    const istKeine = e.quelle === Q_KEINE
    const amber = (istInbound || istGateway || istHA) && e.wert_text == null
    let istText: string
    if (istKeine) istText = 'keine Quelle'
    else if (istGateway) istText = `Gateway: ${e.gateway_topic ?? '…'}`
    else if (istHA) istText = e.ha_name ? `HA: ${e.ha_name} · ${e.ha_entity}` : `HA: ${e.ha_entity ?? '…'}`
    else istText = e.standard_topic
    const wertText = e.wert_text == null ? '–' : e.einheit ? `${e.wert_text} ${e.einheit}` : e.wert_text
    const wertTone = e.wert_text != null
      ? 'text-green-700 dark:text-green-400'
      : amber ? 'text-amber-600 dark:text-amber-400' : 'text-gray-400 dark:text-gray-500'
    return (
      <div key={e.id} data-themen-eintrag={e.id} className="flex flex-col gap-1.5 py-2 sm:flex-row sm:items-center sm:gap-3">
        <div className={`min-w-0 sm:flex-1 ${istKeine ? 'opacity-60' : ''}`}>
          <InlineText wert={e.label} label="Name des Eintrags" maxLength={60}
            onSpeichern={(label) => ausfuehren(datenquellenApi.eintragAendern(anlageId, invId, t.id, e.id, { label }))} />
          <div className={`font-mono text-xs break-all ${amber ? 'text-amber-600 dark:text-amber-400' : 'text-gray-500 dark:text-gray-400'}`}>
            {istText}
          </div>
        </div>
        <div className={`flex items-center justify-end gap-1 sm:w-28 sm:flex-shrink-0 ${istKeine ? 'opacity-60' : ''}`}>
          <span className={`text-sm tabular-nums break-all ${wertTone}`} data-themen-wert>{wertText}</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 sm:flex-nowrap sm:flex-shrink-0">
          {verfuegbarkeit.ha && (
            <QuelleButton icon={Home} label="HA-Sensor" active={istHA}
              title={istHA ? 'Zugeordnete HA-Entität ansehen oder wechseln' : 'HA-Entität zuordnen'}
              onClick={() => setHaEintrag(e)} />
          )}
          {verfuegbarkeit.mqtt && (
            <QuelleButton icon={Waypoints} label="Gateway" active={istGateway}
              title={istGateway ? 'Zugeordnetes Topic ansehen oder wechseln' : 'Fremd-Topic vom Broker zuordnen'}
              onClick={() => setGatewayEintrag(e)} />
          )}
          {verfuegbarkeit.mqtt && (
            <QuelleButton icon={Rss} label="Inbound" active={istInbound} title="eedc-Standard-Topic verwenden"
              onClick={() => { if (!istInbound) setzeQuelle(e, Q_INBOUND) }} />
          )}
          <span className="hidden w-px self-stretch bg-gray-200 dark:bg-gray-700 sm:block" aria-hidden="true" />
          <QuelleButton icon={Ban} label="Keine" active={istKeine} title="Keine Quelle — der Eintrag zeigt nichts"
            onClick={() => setzeQuelle(e, Q_KEINE)} />
          <PfeilKnoepfe index={index} anzahl={t.eintraege.length} was="Eintrag"
            onVerschieben={(position) => ausfuehren(datenquellenApi.eintragAendern(anlageId, invId, t.id, e.id, { position }))} />
          <Button type="button" variant="ghost" size="icon" className="!h-7 !w-7 !min-h-0 !min-w-0 !p-1"
            aria-label="Eintrag entfernen" title="Eintrag entfernen"
            onClick={() => ausfuehren(datenquellenApi.eintragEntfernen(anlageId, invId, t.id, e.id))}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="pt-3" data-themen-block>
      <div className="pt-2 pb-0.5 text-xs font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">Themen</div>
      <p className={`flex max-w-prose items-start gap-1 pb-2 text-xs ${STATUS_TEXT_CLASS.info}`} data-themen-hinweis>
        <InfoIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>{THEMEN_HINWEIS}</span>
      </p>
      {fehler && <p className="pb-2 text-xs text-red-600 dark:text-red-400">{fehler}</p>}
      <div className="space-y-3">
        {themen.map((t, i) => (
          <div key={t.id} data-thema={t.id} className="rounded-lg border border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-2 border-b border-gray-200 px-3 py-2 dark:border-gray-700">
              <div className="min-w-0 flex-1">
                <InlineText wert={t.name} label="Name des Themas" maxLength={40}
                  onSpeichern={(name) => ausfuehren(datenquellenApi.themaAendern(anlageId, invId, t.id, { name }))} />
              </div>
              <PfeilKnoepfe index={i} anzahl={themen.length} was="Thema"
                onVerschieben={(position) => ausfuehren(datenquellenApi.themaAendern(anlageId, invId, t.id, { position }))} />
              <Button type="button" variant="ghost" size="sm" className="!min-h-0 !px-1 !py-1 !text-xs"
                onClick={() => (t.eintraege.length > 0 ? setEntfernen(t) : ausfuehren(datenquellenApi.themaEntfernen(anlageId, invId, t.id)))}>
                <X className="mr-1 h-3.5 w-3.5" />Thema entfernen
              </Button>
            </div>
            <div className="divide-y divide-gray-100 px-3 dark:divide-gray-800">
              {t.eintraege.map((e, j) => eintragZeile(t, e, j))}
            </div>
            <div className="px-3 pb-2">
              <Button type="button" variant="ghost" size="sm" className="!mt-1 !min-h-0 !px-0 !py-1 !text-xs"
                onClick={() => ausfuehren(datenquellenApi.eintragAnlegen(anlageId, invId, t.id))}>
                <Plus className="mr-1 h-3.5 w-3.5" />Eintrag
              </Button>
            </div>
          </div>
        ))}
      </div>
      <Button type="button" variant="ghost" size="sm" className="!mt-2 !min-h-0 !px-0 !py-1 !text-xs"
        onClick={() => ausfuehren(datenquellenApi.themaAnlegen(anlageId, invId))}>
        <Plus className="mr-1 h-3.5 w-3.5" />Thema
      </Button>

      <ConfirmDialog
        isOpen={entfernen != null}
        onClose={() => setEntfernen(null)}
        onConfirm={async () => {
          const t = entfernen
          setEntfernen(null)
          if (t) await ausfuehren(datenquellenApi.themaEntfernen(anlageId, invId, t.id))
        }}
        title="Thema entfernen?"
        message={entfernen ? `«${entfernen.name}» mit ${entfernen.eintraege.length === 1 ? 'einem Eintrag' : `${entfernen.eintraege.length} Einträgen`} und ihren Zuordnungen entfernen?` : ''}
        confirmLabel="Entfernen"
        variant="danger"
      />
      {haEintrag && (
        <DatenquellenHaPicker
          isOpen
          alle
          anlageId={anlageId}
          feldLabel={haEintrag.label}
          initialEntity={haEintrag.ha_entity}
          onClose={() => setHaEintrag(null)}
          onSpeichern={(entityId) => {
            const e = haEintrag
            setHaEintrag(null)
            setzeQuelle(e, verfuegbarkeit.ha_quelle ?? 'ha_app', undefined, entityId)
          }}
        />
      )}
      {gatewayEintrag && (
        <DatenquellenGatewayPicker
          isOpen
          zustand
          anlageId={anlageId}
          feldLabel={gatewayEintrag.label}
          initialTopic={gatewayEintrag.gateway_topic}
          onClose={() => setGatewayEintrag(null)}
          onSpeichern={(config) => {
            const e = gatewayEintrag
            setGatewayEintrag(null)
            setzeQuelle(e, Q_GATEWAY, config)
          }}
        />
      )}
    </div>
  )
}
