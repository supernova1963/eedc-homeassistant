/**
 * DatenquellenGatewayPicker — Overlay zum Zuordnen einer MQTT-Gateway-Quelle
 * an ein eedc-Feld (Datenquellen-V4 / B3.2).
 *
 * SoT: docs/KONZEPT-DATENQUELLEN-V4.md §2b (Quell-Picker Punkt 2). Ablauf:
 *   1. **Baum-Navigation** Ebene für Ebene durch die MQTT-Topic-Hierarchie bis zum
 *      Blatt. Der Server liefert je Pfad NUR die direkten Kinder (serverseitig
 *      aggregiert → vollständig, kein 1000-Topic-Cap; MQTT kann eine Ebene nicht
 *      `ls`-artig auflisten, Zwischenknoten haben oft keinen retained Payload).
 *   2. Blatt wählen → Transform (payload_typ/json_pfad/faktor/offset/invert) mit
 *      Live-Vorschau (test-transform) am Sample; JSON-Felder als Schnellauswahl.
 *   3. Speichern → eine Gateway-Quelle je Feld (mqtt_gateway_mappings, ziel_key=Feld).
 *
 * Nicht-retained/fehlende Topics: manuelle Volltext-Eingabe + Live-Test. Ebenen
 * werden gecacht; „Aktualisieren" lädt die aktuelle Ebene neu (Gernot 2026-07-14).
 */
import { useState, useEffect, useMemo, useCallback, Fragment } from 'react'
import { Search, Loader2, ChevronRight, CornerDownRight, RefreshCw } from 'lucide-react'
import { Modal, Input, Select, Button, Alert } from '../ui'
import { liveDashboardApi } from '../../api/liveDashboard'
import {
  datenquellenApi,
  type DiscoveryTopic,
  type LevelChild,
  type GatewayQuelleConfig,
} from '../../api/datenquellen'

interface Props {
  isOpen: boolean
  feldLabel: string
  /** Aktive Anlage — ihre eigenen Topic-Pfade werden aus der Discovery ausgeschlossen. */
  anlageId: number
  /** Aktuell zugeordnetes Topic (Vorauswahl beim Öffnen), falls vorhanden. */
  initialTopic?: string | null
  onClose: () => void
  onSpeichern: (config: GatewayQuelleConfig) => void
}

const PAYLOAD_OPTIONEN = [
  { value: 'plain', label: 'Zahl (plain)' },
  { value: 'json', label: 'JSON-Objekt' },
  { value: 'json_array', label: 'JSON-Array' },
]

/** Gecachte Baum-Ebene. */
interface Ebene {
  children: LevelChild[]
  selfLeaf: DiscoveryTopic | null
  begrenzt: boolean
}

const LEVEL_SEITE = 50

export default function DatenquellenGatewayPicker({
  isOpen, feldLabel, anlageId, initialTopic, onClose, onSpeichern,
}: Props) {
  const [laden, setLaden] = useState(false)
  const [scanFehler, setScanFehler] = useState<string | null>(null)
  // Cache je Pfad ('' = Root). Jede Ebene wird einzeln vom Server geholt.
  const [ebenen, setEbenen] = useState<Map<string, Ebene>>(new Map())

  // Baum-Navigation: aktueller Pfad + Ebenen-Filter + „weitere anzeigen"-Grenze.
  const [pfad, setPfad] = useState<string[]>([])
  const [filter, setFilter] = useState('')
  const [levelLimit, setLevelLimit] = useState(LEVEL_SEITE)

  const [gewaehlt, setGewaehlt] = useState<DiscoveryTopic | null>(null)
  const [manuell, setManuell] = useState(false)
  const [manuellEingabe, setManuellEingabe] = useState('')
  const [payloadTyp, setPayloadTyp] = useState('plain')
  const [jsonPfad, setJsonPfad] = useState('')
  const [faktor, setFaktor] = useState('1')
  const [offset, setOffset] = useState('0')
  // Vorzeichen-Umkehr ist NICHT mehr Teil der Gateway-Transform (Datenquellen-V4):
  // sie ist quellen-unabhängig am Feld (± an der Wert-Spalte, /invert-Endpoint).

  const [vorschau, setVorschau] = useState<{ wert?: number; fehler?: string } | null>(null)
  const [testLauft, setTestLauft] = useState(false)
  const [testHinweis, setTestHinweis] = useState<string | null>(null)

  const praefixStr = pfad.join('/')

  // Der Picker wird pro Öffnen frisch gemountet (Parent rendert ihn nur bei
  // gesetztem Feld) → kein Reset-Effekt nötig; die States starten leer.

  // Aktuelle Ebene laden, sobald der Pfad sie noch nicht im Cache hat.
  useEffect(() => {
    if (!isOpen || ebenen.has(praefixStr)) return
    let abbruch = false
    setLaden(true)
    setScanFehler(null)
    datenquellenApi.level(praefixStr, anlageId)
      .then((r) => {
        if (abbruch) return
        if (r.fehler) setScanFehler(r.fehler)
        else setEbenen((prev) => new Map(prev).set(praefixStr, {
          children: r.children, selfLeaf: r.self_leaf, begrenzt: r.begrenzt,
        }))
      })
      .catch((e) => { if (!abbruch) setScanFehler(e instanceof Error ? e.message : 'Laden fehlgeschlagen') })
      .finally(() => { if (!abbruch) setLaden(false) })
    return () => { abbruch = true }
  }, [isOpen, praefixStr, anlageId, ebenen])

  const ebene = ebenen.get(praefixStr)
  const childNodes = useMemo(() => ebene?.children ?? [], [ebene])
  const selfLeaf = ebene?.selfLeaf ?? null
  const begrenzt = ebene?.begrenzt ?? false

  const gefilterteChildren = useMemo(() => {
    const q = filter.trim().toLowerCase()
    return q ? childNodes.filter((n) => n.segment.toLowerCase().includes(q)) : childNodes
  }, [childNodes, filter])
  const angezeigteChildren = gefilterteChildren.slice(0, levelLimit)

  const gotoDepth = useCallback((depth: number) => {
    setPfad((p) => p.slice(0, depth))
    setFilter('')
    setLevelLimit(LEVEL_SEITE)
  }, [])

  const drillIn = useCallback((segment: string) => {
    setPfad((p) => [...p, segment])
    setFilter('')
    setLevelLimit(LEVEL_SEITE)
  }, [])

  // Aktuelle Ebene neu vom Broker holen (Cache-Eintrag verwerfen → Effekt lädt neu).
  const neuLaden = useCallback(() => {
    setEbenen((prev) => { const m = new Map(prev); m.delete(praefixStr); return m })
  }, [praefixStr])

  const waehleLeaf = useCallback((t: DiscoveryTopic) => {
    setGewaehlt(t)
    setManuell(false)
    setPayloadTyp(t.payload_typ)
    setJsonPfad('')
    setVorschau(null)
    setTestHinweis(null)
  }, [])

  // Manuell eingegebenes Volltext-Topic verwenden (auch nicht-retained / nicht im Scan).
  const manuellVerwenden = useCallback((topic: string) => {
    setGewaehlt({ topic, payload_sample: '', payload_typ: 'plain', wert: null })
    setManuell(true)
    setPayloadTyp('plain')
    setJsonPfad('')
    setVorschau(null)
    setTestHinweis(null)
  }, [])

  // Live-Test: kurz auf das (auch manuelle) Topic subscriben → Sample + Typ holen.
  const testeLiveTopic = useCallback(() => {
    if (!gewaehlt) return
    setTestLauft(true)
    setTestHinweis(null)
    liveDashboardApi.testGatewayTopic(gewaehlt.topic, 8)
      .then((r) => {
        if (r.empfangen && r.payload_raw != null) {
          const typ = (r.payload_typ_erkannt as DiscoveryTopic['payload_typ']) || 'plain'
          setGewaehlt((g) => (g ? { ...g, payload_sample: r.payload_raw as string, payload_typ: typ } : g))
          setPayloadTyp(typ)
          setVorschau(null)
          setTestHinweis(`empfangen nach ${r.wartezeit_s ?? '?'}s`)
        } else {
          setTestHinweis(r.fehler || 'kein Payload empfangen — Topic trotzdem verwendbar')
        }
      })
      .catch((e) => setTestHinweis(e instanceof Error ? e.message : 'Test fehlgeschlagen'))
      .finally(() => setTestLauft(false))
  }, [gewaehlt])

  // Bereits zugeordnetes Topic vorauswählen: zum Eltern-Pfad navigieren, dann das
  // passende Blatt aus der geladenen Ebene wählen.
  useEffect(() => {
    if (!isOpen || !initialTopic || gewaehlt) return
    const eltern = initialTopic.split('/').slice(0, -1)
    const elternStr = eltern.join('/')
    if (praefixStr !== elternStr) { setPfad(eltern); return }
    const lvl = ebenen.get(elternStr)
    if (!lvl) return
    const treffer = lvl.children.find((c) => c.leaf?.topic === initialTopic)
    if (treffer?.leaf) waehleLeaf(treffer.leaf)
    else if (lvl.selfLeaf?.topic === initialTopic) waehleLeaf(lvl.selfLeaf)
  }, [isOpen, initialTopic, gewaehlt, praefixStr, ebenen, waehleLeaf])

  // Top-Level-Felder des JSON-Samples als Schnellauswahl für den JSON-Pfad.
  const jsonKeys = useMemo(() => {
    if (!gewaehlt || payloadTyp !== 'json') return []
    try {
      const parsed = JSON.parse(gewaehlt.payload_sample)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return Object.keys(parsed)
    } catch { /* abgeschnittenes/ungültiges JSON — dann nur manuelle Eingabe */ }
    return []
  }, [gewaehlt, payloadTyp])

  // Live-Vorschau des Transforms am Sample.
  const testeTransform = useCallback(() => {
    if (!gewaehlt) return
    liveDashboardApi.testGatewayTransform({
      payload: gewaehlt.payload_sample,
      payload_typ: payloadTyp,
      json_pfad: jsonPfad || null,
      faktor: Number(faktor) || 0,
      offset: Number(offset) || 0,
    })
      .then((r) => setVorschau(r.erfolg ? { wert: r.wert } : { fehler: r.fehler }))
      .catch((e) => setVorschau({ fehler: e instanceof Error ? e.message : 'Test fehlgeschlagen' }))
  }, [gewaehlt, payloadTyp, jsonPfad, faktor, offset])

  const speichern = useCallback(() => {
    if (!gewaehlt) return
    onSpeichern({
      quell_topic: gewaehlt.topic,
      payload_typ: payloadTyp as GatewayQuelleConfig['payload_typ'],
      json_pfad: jsonPfad || null,
      faktor: Number(faktor) || 0,
      offset: Number(offset) || 0,
    })
  }, [gewaehlt, payloadTyp, jsonPfad, faktor, offset, onSpeichern])

  const manuellText = manuellEingabe.trim()
  const manuellWildcard = /[#+]/.test(manuellText)

  const zeileKlasse = 'w-full !justify-start text-left'

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`MQTT-Gateway-Quelle für „${feldLabel}"`} size="xl">
      <div className="space-y-4">
        <p className="text-sm text-gray-600 dark:text-gray-300">
          Fremd-Topic vom Broker wählen — Ebene für Ebene durch die Topic-Struktur bis
          zum Wert. Gezeigt werden aktuell gesendete (retained) Topics.
        </p>

        {/* Breadcrumb + Aktualisieren */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-0.5 text-sm">
            <Button type="button" variant="ghost" size="sm" onClick={() => gotoDepth(0)} disabled={pfad.length === 0}>
              alle
            </Button>
            {pfad.map((seg, i) => (
              <Fragment key={i}>
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                <Button type="button" variant="ghost" size="sm" onClick={() => gotoDepth(i + 1)}>
                  <span className="font-mono">{seg}</span>
                </Button>
              </Fragment>
            ))}
          </div>
          <Button
            type="button" variant="secondary" size="sm" disabled={laden}
            onClick={neuLaden}
            title="Diese Ebene neu vom Broker holen"
          >
            {laden ? <Loader2 className="h-4 w-4 animate-spin" /> : <><RefreshCw className="mr-1.5 h-3.5 w-3.5" />Aktualisieren</>}
          </Button>
        </div>

        {/* Ebenen-Filter */}
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <Input
            value={filter}
            onChange={(e) => { setFilter(e.target.value); setLevelLimit(LEVEL_SEITE) }}
            placeholder="in dieser Ebene filtern …"
            className="pl-8"
            aria-label="Ebene filtern"
          />
        </div>

        {scanFehler && <Alert type="error">{scanFehler}</Alert>}
        {begrenzt && (
          <Alert type="warning">
            Sehr viele Einträge auf dieser Ebene — Anzeige ggf. unvollständig. Filter nutzen.
          </Alert>
        )}

        {/* Aktuelle Baum-Ebene */}
        <div className="max-h-64 space-y-1 overflow-y-auto rounded border border-gray-200 dark:border-gray-700 p-2">
          {laden ? (
            <div className="flex items-center gap-2 p-2 text-sm text-gray-500 dark:text-gray-400">
              <Loader2 className="h-4 w-4 animate-spin" /> Ebene wird geladen …
            </div>
          ) : childNodes.length === 0 && !selfLeaf ? (
            <p className="p-2 text-sm text-gray-500 dark:text-gray-400">
              {pfad.length === 0 ? 'Keine Topics empfangen.' : 'Keine Topics unter diesem Zweig.'}
            </p>
          ) : gefilterteChildren.length === 0 && !selfLeaf ? (
            <p className="p-2 text-sm text-gray-500 dark:text-gray-400">Kein Segment passt zum Filter.</p>
          ) : (
            <>
              {selfLeaf && (
                <Button
                  type="button"
                  variant={gewaehlt?.topic === selfLeaf.topic ? 'secondary' : 'ghost'}
                  className={zeileKlasse}
                  onClick={() => waehleLeaf(selfLeaf)}
                >
                  <CornerDownRight className="mr-2 h-4 w-4 shrink-0 text-gray-400" />
                  <span className="flex min-w-0 flex-col">
                    <span className="text-sm">Diesen Zweig als Wert übernehmen</span>
                    <span className="truncate text-xs text-gray-500 dark:text-gray-400">
                      {selfLeaf.payload_typ} · {selfLeaf.payload_sample.slice(0, 60)}
                    </span>
                  </span>
                </Button>
              )}
              {angezeigteChildren.map((n) => n.has_children ? (
                <Button
                  key={n.segment}
                  type="button" variant="ghost" className={zeileKlasse}
                  onClick={() => drillIn(n.segment)}
                >
                  <span className="flex w-full items-center gap-2">
                    <span className="truncate font-mono text-sm">{n.segment}/</span>
                    {n.leaf && <span className="shrink-0 text-xs text-gray-400 dark:text-gray-500">· auch Wert</span>}
                    <ChevronRight className="ml-auto h-4 w-4 shrink-0 text-gray-400" />
                  </span>
                </Button>
              ) : (
                <Button
                  key={n.segment}
                  type="button"
                  variant={gewaehlt?.topic === n.leaf?.topic ? 'secondary' : 'ghost'}
                  className={zeileKlasse}
                  onClick={() => n.leaf && waehleLeaf(n.leaf)}
                >
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate font-mono text-sm">{n.segment}</span>
                    <span className="truncate text-xs text-gray-500 dark:text-gray-400">
                      {n.leaf?.payload_typ} · {n.leaf?.payload_sample.slice(0, 60)}
                    </span>
                  </span>
                </Button>
              ))}
            </>
          )}
        </div>
        {gefilterteChildren.length > angezeigteChildren.length && (
          <Button type="button" variant="ghost" size="sm" onClick={() => setLevelLimit((l) => l + LEVEL_SEITE)}>
            weitere anzeigen ({gefilterteChildren.length - angezeigteChildren.length})
          </Button>
        )}

        {/* Manuelle Volltext-Eingabe (nicht-retained / nicht im Scan). */}
        <div className="space-y-1 rounded border border-dashed border-gray-300 dark:border-gray-600 p-2">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Topic nicht dabei? Voll-Topic manuell eingeben (auch nicht-retained):
          </span>
          <div className="flex items-center gap-2">
            <Input
              value={manuellEingabe}
              onChange={(e) => setManuellEingabe(e.target.value)}
              placeholder="z. B. shellies/xy/emeter/0/power"
              aria-label="Topic manuell eingeben"
            />
            <Button
              type="button" variant="secondary" size="sm"
              disabled={!manuellText || manuellWildcard}
              onClick={() => manuellVerwenden(manuellText)}
            >
              verwenden
            </Button>
          </div>
        </div>

        {/* Transform-Konfiguration (nach Topic-Wahl) */}
        {gewaehlt && (
          <div className="space-y-3 rounded border border-gray-200 dark:border-gray-700 p-3">
            <div className="font-mono text-xs text-gray-600 dark:text-gray-300 break-all">
              {gewaehlt.topic}
              {manuell && <span className="ml-2 font-sans text-gray-400 dark:text-gray-500">(manuell eingegeben)</span>}
            </div>
            {gewaehlt.payload_sample
              ? <div className="font-mono text-xs text-gray-400 dark:text-gray-500 break-all">Sample: {gewaehlt.payload_sample.slice(0, 120)}</div>
              : <div className="text-xs text-gray-400 dark:text-gray-500">Noch kein Sample — „Topic testen (Live)" holt den aktuellen Wert.</div>}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Select
                label="Payload-Typ"
                options={PAYLOAD_OPTIONEN}
                value={payloadTyp}
                onChange={(e) => setPayloadTyp(e.target.value)}
              />
              {(payloadTyp === 'json' || payloadTyp === 'json_array') && (
                <Input
                  label={payloadTyp === 'json' ? 'JSON-Pfad (z. B. Power)' : 'Array-Index / Pfad'}
                  value={jsonPfad}
                  onChange={(e) => setJsonPfad(e.target.value)}
                  placeholder="z. B. emeter.0.power"
                />
              )}
              <Input
                label="Faktor" type="number" step="any"
                value={faktor} onChange={(e) => setFaktor(e.target.value)}
              />
              <Input
                label="Offset" type="number" step="any"
                value={offset} onChange={(e) => setOffset(e.target.value)}
              />
            </div>
            {payloadTyp === 'json' && jsonKeys.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs text-gray-500 dark:text-gray-400">Felder im Payload:</span>
                {jsonKeys.map((k) => (
                  <Button
                    key={k}
                    type="button"
                    variant={jsonPfad === k ? 'secondary' : 'ghost'}
                    size="sm"
                    onClick={() => { setJsonPfad(k); setVorschau(null) }}
                  >
                    {k}
                  </Button>
                ))}
              </div>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <Button type="button" variant="secondary" onClick={testeLiveTopic} disabled={testLauft}>
                {testLauft ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Topic testen (Live)'}
              </Button>
              <Button
                type="button" variant="secondary" onClick={testeTransform}
                disabled={!gewaehlt.payload_sample}
                title={gewaehlt.payload_sample ? undefined : 'Erst „Topic testen (Live)" für ein Sample'}
              >
                Vorschau berechnen
              </Button>
              {vorschau?.wert != null && (
                <span className="text-sm text-green-700 dark:text-green-400">
                  Ergebnis: <span className="font-semibold">{vorschau.wert}</span>
                </span>
              )}
              {vorschau?.fehler && (
                <span className="text-sm text-red-600 dark:text-red-400">{vorschau.fehler}</span>
              )}
              {testHinweis && (
                <span className="text-sm text-gray-500 dark:text-gray-400">{testHinweis}</span>
              )}
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-gray-100 dark:border-gray-800 pt-3">
          <Button type="button" variant="secondary" onClick={onClose}>Abbrechen</Button>
          <Button type="button" onClick={speichern} disabled={!gewaehlt}>Quelle speichern</Button>
        </div>
      </div>
    </Modal>
  )
}
