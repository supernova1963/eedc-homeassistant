/**
 * Community-Share-Block (IA-V4 Einstellungen, A1 2026-07-02) — oberster Block unter
 * Stammdaten. Zwei Teile:
 *  - {@link CommunityTeilenSchalter}: der „teilen"-Schalter (`community_auto_share`)
 *    in der Block-Überschrift (BlockShell-`badge`-Slot). Einschalten löst die
 *    einmalige Erst-Übertragung aller vorhandenen Monatswerte aus (Rainer-Klarheit
 *    2026-07-04, Variante A); danach überträgt jeder Monatsabschluss automatisch.
 *  - {@link CommunityShareBlockInhalt}: Vorschau der anonym geteilten Daten inkl.
 *    aufklappbarer VOLLSTÄNDIGER Feldliste — aus dem echten Submit-Payload
 *    (`communityApi.getPreview().vorschau` = exakt `prepare_community_data`)
 *    gerendert, nicht handgepflegt → kein Drift, wenn KPIs dazukommen. Auch bei
 *    AUSGESCHALTETEM Schalter voll lesbar/bedienbar (Gernot 2026-07-04: informierte
 *    Einwilligung — man muss VOR dem Teilen sehen können, was geteilt würde;
 *    die frühere A1-Abblendung machte die Feldliste unklickbar). Aus-Zustand
 *    kommuniziert die Konjunktiv-Statuszeile („würden geteilt") + Fußnote.
 *
 * Datenrolle strikt Community (nur `communityApi`), kein Bezug zu Investitionen.
 */
import { useCallback, useEffect, useState } from 'react'
import { MapPin, Zap } from 'lucide-react'
import { KOMPONENTEN_IDENTITAET } from '../lib'
import { useSelectedAnlage } from '../hooks'
import { anlagenApi } from '../api'
import { communityApi, type PreviewResponse, type MonatswertPreview, type CommunityDataPreview } from '../api/community'
import { REGION_NAMEN, WP_ART_LABELS, MONAT_NAMEN } from '../lib/constants'
import { fmtZahl } from '../lib'
import Button from '../components/ui/Button'
import Switch from '../components/ui/Switch'

// Ausstattungs-Badge-Icons aus der Typ-Identitäts-SoT (A5) statt lokaler Kopien.
const SpeicherIcon = KOMPONENTEN_IDENTITAET['speicher'].icon
const BkwIcon = KOMPONENTEN_IDENTITAET['balkonkraftwerk'].icon
const WpIcon = KOMPONENTEN_IDENTITAET['waermepumpe'].icon
const WallboxIcon = KOMPONENTEN_IDENTITAET['wallbox'].icon
const EAutoIcon = KOMPONENTEN_IDENTITAET['e-auto'].icon
const SonstigesIcon = KOMPONENTEN_IDENTITAET['sonstiges'].icon

/** „teilen"-Schalter für die Block-Überschrift (community_auto_share).
 *  Einschalten stößt zusätzlich die Erst-Übertragung an (Fehler dabei sind ok —
 *  der Inhalt zeigt dann „Erste Übertragung steht noch aus" mit Nachhol-Knopf,
 *  und spätestens der nächste Monatsabschluss überträgt). */
export function CommunityTeilenSchalter() {
  const { selectedAnlage, refresh } = useSelectedAnlage()
  const [saving, setSaving] = useState(false)
  if (!selectedAnlage) return null
  const an = selectedAnlage.community_auto_share ?? false
  const umschalten = async () => {
    setSaving(true)
    try {
      await anlagenApi.update(selectedAnlage.id, { community_auto_share: !an })
      if (!an) {
        // Variante A: Einschalten = Einwilligung → sofortige Erst-Übertragung.
        try {
          await communityApi.share(selectedAnlage.id)
        } catch {
          // Server nicht erreichbar o. ä. — Inhalt zeigt den Ausstehend-Hinweis.
        }
      }
      await refresh()
    } finally {
      setSaving(false)
    }
  }
  return (
    <div className="flex items-center gap-2">
      {/* D14-4 (detLAN #113): Label großgeschrieben. */}
      <span className="hidden text-xs text-gray-500 dark:text-gray-400 sm:inline">Teilen</span>
      {/* B15/S3: ui/Switch-SoT statt handgebauter Kopie. */}
      <Switch checked={an} onChange={umschalten} ariaLabel="Anonyme Community-Daten teilen" disabled={saving} />
    </div>
  )
}

// ─── Feldliste — Labels für die pro Monat übertragenen Kennzahlen ────────────
// Reihenfolge: Basis, dann Komponenten in INVESTITION_TYP_ORDER-Logik
// (Speicher → BKW → WP → Wallbox → E-Auto → Sonstiges). Gerendert wird NUR,
// was im echten Payload vorkommt — die Liste hier liefert nur Label + Einheit.
const MONATSWERT_FELDER: { key: keyof MonatswertPreview; label: string; einheit: string }[] = [
  { key: 'ertrag_kwh', label: 'PV-Ertrag', einheit: 'kWh' },
  { key: 'einspeisung_kwh', label: 'Einspeisung', einheit: 'kWh' },
  { key: 'netzbezug_kwh', label: 'Netzbezug', einheit: 'kWh' },
  { key: 'autarkie_prozent', label: 'Autarkie', einheit: '%' },
  { key: 'eigenverbrauch_prozent', label: 'Eigenverbrauchsquote', einheit: '%' },
  { key: 'speicher_ladung_kwh', label: 'Speicher-Ladung', einheit: 'kWh' },
  { key: 'speicher_entladung_kwh', label: 'Speicher-Entladung', einheit: 'kWh' },
  { key: 'speicher_ladung_netz_kwh', label: 'Speicher-Ladung aus Netz', einheit: 'kWh' },
  { key: 'bkw_erzeugung_kwh', label: 'BKW-Erzeugung', einheit: 'kWh' },
  { key: 'bkw_eigenverbrauch_kwh', label: 'BKW-Eigenverbrauch', einheit: 'kWh' },
  { key: 'bkw_speicher_ladung_kwh', label: 'BKW-Speicher-Ladung', einheit: 'kWh' },
  { key: 'bkw_speicher_entladung_kwh', label: 'BKW-Speicher-Entladung', einheit: 'kWh' },
  { key: 'wp_stromverbrauch_kwh', label: 'Wärmepumpe Stromverbrauch', einheit: 'kWh' },
  { key: 'wp_heizwaerme_kwh', label: 'Wärmepumpe Heizwärme', einheit: 'kWh' },
  // „Heizwärme" darüber sagt die Größe, diese Zeile sagte sie nicht — dieselbe
  // Klasse, halb gelöst. Beide Werte sind thermisch (01.09.2026).
  { key: 'wp_warmwasser_kwh', label: 'Wärmepumpe Warmwasser-Wärme', einheit: 'kWh' },
  { key: 'wallbox_ladung_kwh', label: 'Wallbox-Ladung', einheit: 'kWh' },
  { key: 'wallbox_ladung_pv_kwh', label: 'Wallbox-Ladung aus PV', einheit: 'kWh' },
  { key: 'wallbox_ladevorgaenge', label: 'Wallbox-Ladevorgänge', einheit: '' },
  { key: 'eauto_ladung_gesamt_kwh', label: 'E-Auto-Ladung gesamt', einheit: 'kWh' },
  { key: 'eauto_ladung_pv_kwh', label: 'E-Auto-Ladung aus PV', einheit: 'kWh' },
  { key: 'eauto_ladung_extern_kwh', label: 'E-Auto-Ladung extern', einheit: 'kWh' },
  { key: 'eauto_km', label: 'E-Auto gefahrene Kilometer', einheit: 'km' },
  { key: 'eauto_v2h_kwh', label: 'E-Auto V2H-Entladung', einheit: 'kWh' },
  { key: 'sonstiges_verbrauch_kwh', label: 'Sonstiges Stromverbrauch', einheit: 'kWh' },
]

/** Jüngster Monatswert je Feld: Wert + Herkunftsmonat (Payload ist chronologisch). */
function letzterWert(monatswerte: MonatswertPreview[], key: keyof MonatswertPreview) {
  for (let i = monatswerte.length - 1; i >= 0; i--) {
    const wert = monatswerte[i][key]
    if (wert !== null && wert !== undefined) {
      return { wert: wert as number, jahr: monatswerte[i].jahr, monat: monatswerte[i].monat }
    }
  }
  return null
}

function DetailZeile({ label, wert }: { label: string; wert: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <dt className="text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="whitespace-nowrap text-right font-medium text-gray-900 dark:text-white">{wert}</dd>
    </div>
  )
}

/** Aufklappbare vollständige Feldliste — direkt aus dem Submit-Payload.
 *  (Export nur für den Test — im UI ausschließlich Teil dieses Blocks.) */
export function GeteilteFelderDetail({ v }: { v: CommunityDataPreview }) {
  // Anlagendaten: feste Felder + nur tatsächlich gesendete Komponenten-Angaben.
  const anlagenZeilen: { label: string; wert: string }[] = [
    { label: 'Region', wert: REGION_NAMEN[v.region] || v.region },
    { label: 'Leistung', wert: `${fmtZahl(v.kwp, 1)} kWp` },
    { label: 'Ausrichtung', wert: v.ausrichtung },
    { label: 'Neigung', wert: `${v.neigung_grad}°` },
    { label: 'Installationsjahr', wert: String(v.installation_jahr) },
  ]
  if (v.speicher_kwh) anlagenZeilen.push({ label: 'Speicher-Kapazität', wert: `${fmtZahl(v.speicher_kwh, 1)} kWh` })
  if (v.wp_art) anlagenZeilen.push({ label: 'Wärmepumpen-Art', wert: WP_ART_LABELS[v.wp_art] || v.wp_art })
  if (v.wallbox_kw) anlagenZeilen.push({ label: 'Wallbox-Ladeleistung', wert: `${fmtZahl(v.wallbox_kw, 1)} kW` })
  if (v.bkw_wp) anlagenZeilen.push({ label: 'BKW-Leistung', wert: `${fmtZahl(v.bkw_wp, 0)} Wp` })
  if (v.sonstiges_bezeichnung) anlagenZeilen.push({ label: 'Sonstiges-Bezeichnung', wert: v.sonstiges_bezeichnung })

  // Monats-Kennzahlen: nur Felder, die in mindestens einem Monat vorkommen.
  // R15-8 (Rainer, GPN #160): Beispiel-Monat = letzter ABGESCHLOSSENER Monat —
  // der jüngste geteilte kann der laufende (unvollständige) sein; ein
  // abgeschlossener ist sofort gegen den Monatsabschluss prüfbar. Fallback:
  // jüngster vorhandener. Der Referenz-Monat steht EINMAL in der Überschrift
  // (Gernot 2026-07-04); nur davon abweichende Werte tragen ihre Monatsangabe
  // einzeln (auch Werte, die es nur im laufenden Monat gibt).
  const heute = new Date()
  const istLaufend = (m: MonatswertPreview) =>
    m.jahr === heute.getFullYear() && m.monat === heute.getMonth() + 1
  const abgeschlossene = v.monatswerte.filter((m) => !istLaufend(m))
  const werteBasis = abgeschlossene.length > 0 ? abgeschlossene : v.monatswerte
  const juengster = werteBasis.length > 0 ? werteBasis[werteBasis.length - 1] : null
  const monatsZeilen = MONATSWERT_FELDER.flatMap((feld) => {
    // Bevorzugt aus abgeschlossenen Monaten; Felder, die nur im laufenden
    // Monat existieren, fallen darauf zurück (mit Monatsangabe via `abweichend`).
    const w = letzterWert(werteBasis, feld.key) ?? letzterWert(v.monatswerte, feld.key)
    if (!w) return []
    const nk = feld.einheit === '' ? 0 : 1
    const abweichend = !juengster || w.jahr !== juengster.jahr || w.monat !== juengster.monat
    // Regel 0a: % mit Leerzeichen.
    const wert = `${fmtZahl(w.wert, nk)}${feld.einheit ? ` ${feld.einheit}` : ''}${
      abweichend ? ` (${MONAT_NAMEN[w.monat]} ${w.jahr})` : ''
    }`
    return [{ label: feld.label, wert }]
  })

  return (
    <details className="border-t border-gray-100 dark:border-gray-800 pt-3">
      <summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
        Geteilte Felder im Detail anzeigen ({anlagenZeilen.length + monatsZeilen.length} Felder)
      </summary>
      <div className="mt-3 space-y-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Anlagendaten (einmal pro Anlage)
          </p>
          <dl className="mt-1.5 grid grid-cols-1 gap-x-8 gap-y-1 sm:grid-cols-2">
            {anlagenZeilen.map((z) => <DetailZeile key={z.label} label={z.label} wert={z.wert} />)}
          </dl>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Kennzahlen pro Monat
            {juengster ? ` — Beispielwerte aus ${MONAT_NAMEN[juengster.monat]} ${juengster.jahr}${abgeschlossene.length > 0 ? ' (letzter abgeschlossener Monat)' : ''}` : ''}
          </p>
          <dl className="mt-1.5 grid grid-cols-1 gap-x-8 gap-y-1 sm:grid-cols-2">
            {monatsZeilen.map((z) => <DetailZeile key={z.label} label={z.label} wert={z.wert} />)}
          </dl>
          <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
            Die Liste zeigt genau die Felder, die deine Anlage tatsächlich überträgt —
            Kennzahlen ohne Daten (z.&nbsp;B. nicht vorhandene Komponenten) werden nicht gesendet.
          </p>
        </div>
      </div>
    </details>
  )
}

/** Vorschau der geteilten (anonymen) Daten + Übertragungsstatus; abgeblendet, wenn aus. */
export function CommunityShareBlockInhalt() {
  const { selectedAnlage, selectedAnlageId, refresh } = useSelectedAnlage()
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [laden, setLaden] = useState(false)
  const [uebertrage, setUebertrage] = useState(false)
  // #387 Schritt 3: Steht diese Anlage noch aus? Nur Anlagen OHNE Auto-Share
  // stehen hier — die anderen senden beim nächsten Start von selbst nach.
  const [nachsendenOffen, setNachsendenOffen] = useState(false)
  const communityHash = selectedAnlage?.community_hash ?? null

  const ladePreview = useCallback(() => {
    if (selectedAnlageId == null) { setPreview(null); return }
    let aktiv = true
    setLaden(true)
    communityApi.getPreview(selectedAnlageId)
      .then((p) => { if (aktiv) setPreview(p) })
      .catch(() => { if (aktiv) setPreview(null) })
      .finally(() => { if (aktiv) setLaden(false) })
    return () => { aktiv = false }
  }, [selectedAnlageId])

  // communityHash als Dep: nach der Erst-Übertragung durch den Schalter (setzt
  // den Hash) lädt die Vorschau neu → `bereits_geteilt` springt ohne Reload um.
  useEffect(() => ladePreview(), [ladePreview, communityHash])

  // Nachsende-Status (#387 Schritt 3). Dieselbe Dep-Logik: nach einem Klick auf
  // „Jetzt übertragen" merkt sich der Server die Anlage, der Hinweis
  // verschwindet ohne Reload.
  useEffect(() => {
    if (selectedAnlageId == null) { setNachsendenOffen(false); return }
    let aktiv = true
    communityApi.getNachsendeStatus()
      .then((st) => {
        if (aktiv) setNachsendenOffen(st.offen.some((o) => o.anlage_id === selectedAnlageId))
      })
      .catch(() => { if (aktiv) setNachsendenOffen(false) })
    return () => { aktiv = false }
  }, [selectedAnlageId, communityHash])

  if (selectedAnlageId == null) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Anlage ausgewählt.</p>
  }

  const teiltAuto = selectedAnlage?.community_auto_share ?? false
  const v = preview?.vorschau
  const region = v ? (REGION_NAMEN[v.region] || v.region) : null

  // Nachhol-Pfad: Schalter ist an, aber die Erst-Übertragung hat (noch) nicht
  // geklappt (Server offline beim Einschalten o. ä.).
  const uebertragungAusstehend = teiltAuto && preview != null && !preview.bereits_geteilt && preview.anzahl_monate > 0
  const jetztUebertragen = async () => {
    if (selectedAnlageId == null) return
    setUebertrage(true)
    try {
      await communityApi.share(selectedAnlageId)
      setNachsendenOffen(false) // der Server hat die Anlage soeben vermerkt
      await refresh() // setzt community_hash → Vorschau lädt via Dep neu
    } catch {
      // bleibt „ausstehend" — nächster Monatsabschluss überträgt automatisch
    } finally {
      setUebertrage(false)
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Anonyme Kennzahlen deiner Anlage im Community-Benchmark — keine Adresse, kein Name.
        Geteilt werden ausschließlich <strong>monatlich aggregierte Werte</strong> (keine
        Live- oder Tagesdaten): beim Einschalten einmalig alle vorhandenen Monatswerte,
        danach automatisch mit jedem Monatsabschluss.
        {/* R18-10 (rapahl #208): Rainers Annahme war „nur der letzte Monatsabschluss
            wird übertragen" — tatsächlich sendet JEDE Übertragung alle Monate erneut
            (Server-Upsert), rückwirkende Korrekturen kommen also an. Das hier
            sichtbar machen ersetzt das (entschieden verworfene) Submit-Log. */}
        {' '}Jede Übertragung sendet dabei <strong>alle Monatsdaten in dieser Form erneut</strong> —
        nicht nur den neuen Monat; rückwirkende Korrekturen erreichen die Community automatisch.
      </p>

      <div>
        {laden && !preview ? (
          <p className="text-sm text-gray-400 dark:text-gray-500">Lade Vorschau …</p>
        ) : v ? (
          <div className="space-y-3">
            {/* Anlagendaten */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="flex items-center gap-2">
                <MapPin className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Region</p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{region}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-yellow-500" />
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Leistung</p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{fmtZahl(v.kwp, 1)} kWp</p>
                </div>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Ausrichtung</p>
                <p className="text-sm font-medium capitalize text-gray-900 dark:text-white">{v.ausrichtung}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Neigung</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">{v.neigung_grad}°</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Installationsjahr</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">{v.installation_jahr}</p>
              </div>
            </div>

            {/* Ausstattung — alle mitgesendeten Komponenten-Flags */}
            {(v.speicher_kwh || v.hat_waermepumpe || v.hat_eauto || v.hat_wallbox || v.hat_balkonkraftwerk || v.hat_sonstiges) && (
              <div className="flex flex-wrap gap-2">
                {v.speicher_kwh ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2 py-1 text-xs text-green-700 dark:bg-green-900/20 dark:text-green-300">
                    <SpeicherIcon className="h-4 w-4" />
                    Speicher ({fmtZahl(v.speicher_kwh, 1)} kWh)
                  </span>
                ) : null}
                {v.hat_balkonkraftwerk && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-yellow-50 px-2 py-1 text-xs text-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-300">
                    <BkwIcon className="h-4 w-4" />
                    Balkonkraftwerk{v.bkw_wp ? ` (${fmtZahl(v.bkw_wp, 0)} Wp)` : ''}
                  </span>
                )}
                {v.hat_waermepumpe && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-1 text-xs text-blue-700 dark:bg-blue-900/20 dark:text-blue-300">
                    <WpIcon className="h-4 w-4" />
                    Wärmepumpe{v.wp_art ? ` (${WP_ART_LABELS[v.wp_art] || v.wp_art})` : ''}
                  </span>
                )}
                {v.hat_wallbox && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-gray-50 px-2 py-1 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                    <WallboxIcon className="h-4 w-4" />
                    Wallbox{v.wallbox_kw ? ` (${fmtZahl(v.wallbox_kw, 1)} kW)` : ''}
                  </span>
                )}
                {v.hat_eauto && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 px-2 py-1 text-xs text-purple-700 dark:bg-purple-900/20 dark:text-purple-300">
                    <EAutoIcon className="h-4 w-4" />
                    E-Auto
                  </span>
                )}
                {v.hat_sonstiges && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-gray-50 px-2 py-1 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                    <SonstigesIcon className="h-4 w-4" />
                    Sonstiges{v.sonstiges_bezeichnung ? ` (${v.sonstiges_bezeichnung})` : ''}
                  </span>
                )}
              </div>
            )}

            {/* Übertragungsstatus */}
            {uebertragungAusstehend ? (
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm text-yellow-600 dark:text-yellow-400">
                  Erste Übertragung steht noch aus ({fmtZahl(preview.anzahl_monate, 0)} Monatswerte bereit).
                </p>
                <Button variant="secondary" size="sm" loading={uebertrage} onClick={jetztUebertragen}>
                  Jetzt übertragen
                </Button>
              </div>
            ) : nachsendenOffen ? (
              /* #387 Schritt 3: Seit dieser Version geht die Ertragserwartung
                 deines Standorts mit — der Community-Vergleich stellt am
                 1.9.2026 darauf um. Wer automatisch teilt, sendet von selbst
                 nach; hier steht nur, wer es einmal von Hand tun muss. Der
                 Knopf ist derselbe wie oben (Voll-Submit), es entsteht keine
                 zweite Übertragungsart. */
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm text-yellow-600 dark:text-yellow-400">
                  Neu: eedc kann jetzt auch die Ertragserwartung deines Standorts mitschicken.
                  Der Community-Vergleich rechnet damit ab dem 1. September fairer — für Anlagen,
                  die noch kein volles Jahr gemessen haben. Einmal übertragen genügt.
                </p>
                <Button variant="secondary" size="sm" loading={uebertrage} onClick={jetztUebertragen}>
                  Jetzt übertragen
                </Button>
              </div>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {preview?.anzahl_monate
                  ? `${fmtZahl(preview.anzahl_monate, 0)} Monatswerte ${teiltAuto ? 'werden' : 'würden'} geteilt.`
                  : 'Noch keine Monatswerte zum Teilen vorhanden.'}
              </p>
            )}

            {/* Vollständige Feldliste — Rainer-Transparenz 2026-07-04 */}
            <GeteilteFelderDetail v={v} />
          </div>
        ) : (
          <p className="text-sm text-gray-400 dark:text-gray-500">Keine Vorschau verfügbar.</p>
        )}
      </div>

      {!teiltAuto && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Teilen ist ausgeschaltet — aktiviere den Schalter „Teilen" oben in der Block-Überschrift.
        </p>
      )}
    </div>
  )
}
