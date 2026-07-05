/**
 * FormBlock — editierbares Feld-Raster als geteilte SoT (IA v4, Einstellungen-Umbau).
 *
 * Für die „leichte Config"-Blöcke der V4-Einstellungen (Anlage, Allgemein, MQTT-Export,
 * Community-Share …): echte Inline-Bearbeitung im aufgeklappten {@link Block} statt
 * Wegnavigieren. Der Block hält einen internen Entwurf, erkennt Änderungen (Dirty-Flag),
 * validiert je Feld und ruft `onSave` mit den aktuellen Werten. **Keine Netzwerk-Calls** —
 * Speichern läuft ausschließlich über den `onSave`-Callback des Konsumenten.
 *
 * Wiederverwendung der bestehenden SoT-Controls (Input/Select/Button/DatumPicker) und des
 * Element-Park (Parkbar je Feld). Ohne ParkProvider ist Parkbar inert → in v3 DOM-neutral.
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Button, Input, Select, Switch } from '../ui'
import { DatumPicker } from '../ui/DatumPicker'
import { Parkbar } from '../park/Parkbar'

export type FormBlockWert = string | number | boolean | null

interface FeldBasis {
  id: string
  label: string
  /** Hilfstext unter dem Feld. */
  hinweis?: string
  /** Pflichtfeld — leer ⇒ Fehler, Speichern blockiert. */
  pflicht?: boolean
  disabled?: boolean
  /** Element-Park-ID; ohne ParkProvider inert. */
  parkId?: string
  /** Zusätzliche Prüfung; liefert Fehlertext oder null. */
  validate?: (wert: FormBlockWert) => string | null
}

export type FormBlockFeld =
  | (FeldBasis & { typ: 'text'; wert: string })
  | (FeldBasis & { typ: 'number'; wert: number | null; einheit?: string })
  | (FeldBasis & { typ: 'select'; wert: string; optionen: { value: string; label: string }[] })
  | (FeldBasis & { typ: 'toggle'; wert: boolean })
  | (FeldBasis & { typ: 'date'; wert: string /* ISO yyyy-mm-dd */ })

function istLeer(f: FormBlockFeld, wert: FormBlockWert): boolean {
  if (f.typ === 'toggle') return false
  if (f.typ === 'number') return wert === null || wert === undefined
  return wert === '' || wert === null || wert === undefined
}

/** Signatur der eingehenden Werte — ändert sie sich (z. B. nach Reload), wird der Entwurf neu übernommen. */
function signatur(felder: FormBlockFeld[]): string {
  return JSON.stringify(felder.map((f) => [f.id, f.wert]))
}

export function FormBlock({
  felder,
  onSave,
  fokus = false,
  speichernLabel = 'Speichern',
}: {
  felder: FormBlockFeld[]
  onSave: (werte: Record<string, FormBlockWert>) => void | Promise<void>
  /** Vollbild-Render (mehr Spalten). */
  fokus?: boolean
  speichernLabel?: string
}) {
  const sig = signatur(felder)
  const initial = useMemo(
    () => Object.fromEntries(felder.map((f) => [f.id, f.wert] as [string, FormBlockWert])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sig],
  )

  const [entwurf, setEntwurf] = useState<Record<string, FormBlockWert>>(initial)
  const [beruehrt, setBeruehrt] = useState<Record<string, boolean>>({})
  const [speichert, setSpeichert] = useState(false)
  const [speicherFehler, setSpeicherFehler] = useState<string | null>(null)

  // Nach externem Wertwechsel (Reload/Save) Entwurf zurück auf die neuen Werte.
  useEffect(() => {
    setEntwurf(initial)
    setBeruehrt({})
    setSpeicherFehler(null)
  }, [initial])

  const setzeWert = (id: string, wert: FormBlockWert) => {
    setEntwurf((e) => ({ ...e, [id]: wert }))
    setBeruehrt((b) => ({ ...b, [id]: true }))
    setSpeicherFehler(null)
  }

  const fehler: Record<string, string | null> = {}
  for (const f of felder) {
    const wert = entwurf[f.id]
    if (f.pflicht && istLeer(f, wert)) fehler[f.id] = 'Pflichtfeld'
    else fehler[f.id] = f.validate?.(wert) ?? null
  }
  const hatFehler = Object.values(fehler).some(Boolean)
  const dirty = felder.some((f) => entwurf[f.id] !== initial[f.id])

  const speichern = async () => {
    if (!dirty || hatFehler || speichert) return
    setSpeichert(true)
    setSpeicherFehler(null)
    try {
      await onSave({ ...entwurf })
    } catch (e) {
      setSpeicherFehler(e instanceof Error ? e.message : 'Speichern fehlgeschlagen')
    } finally {
      setSpeichert(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className={`grid gap-3 sm:grid-cols-2 ${fokus ? 'lg:grid-cols-3' : ''}`}>
        {felder.map((f) => {
          const feldFehler = beruehrt[f.id] ? fehler[f.id] ?? undefined : undefined
          const control = <FeldControl feld={f} wert={entwurf[f.id]} fehler={feldFehler} setzeWert={setzeWert} />
          return f.parkId ? (
            <Parkbar key={f.id} id={f.parkId} titel={f.label}>
              {control}
            </Parkbar>
          ) : (
            <div key={f.id}>{control}</div>
          )
        })}
      </div>

      {speicherFehler && (
        <p className="text-sm text-red-600 dark:text-red-400">{speicherFehler}</p>
      )}

      <div className="flex items-center gap-3">
        <Button
          type="button"
          onClick={speichern}
          disabled={!dirty || hatFehler}
          loading={speichert}
        >
          {speichernLabel}
        </Button>
        {dirty && !speichert && (
          <span className="text-xs text-gray-500 dark:text-gray-400">Ungespeicherte Änderungen</span>
        )}
      </div>
    </div>
  )
}

/** Ein einzelnes Feld — mappt den Typ auf die passende SoT-Control. */
function FeldControl({
  feld,
  wert,
  fehler,
  setzeWert,
}: {
  feld: FormBlockFeld
  wert: FormBlockWert
  fehler?: string
  setzeWert: (id: string, wert: FormBlockWert) => void
}): ReactNode {
  switch (feld.typ) {
    case 'text':
      return (
        <Input
          label={feld.label}
          hint={feld.hinweis}
          error={fehler}
          disabled={feld.disabled}
          value={(wert as string) ?? ''}
          onChange={(e) => setzeWert(feld.id, e.target.value)}
        />
      )
    case 'number':
      return (
        <Input
          type="number"
          label={feld.einheit ? `${feld.label} (${feld.einheit})` : feld.label}
          hint={feld.hinweis}
          error={fehler}
          disabled={feld.disabled}
          value={wert === null || wert === undefined ? '' : String(wert)}
          onChange={(e) => {
            const v = e.target.value
            setzeWert(feld.id, v === '' ? null : Number(v))
          }}
        />
      )
    case 'select':
      return (
        <Select
          label={feld.label}
          error={fehler}
          disabled={feld.disabled}
          options={feld.optionen}
          value={(wert as string) ?? ''}
          onChange={(e) => setzeWert(feld.id, e.target.value)}
        />
      )
    case 'date':
      return (
        <label className="block">
          <span className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{feld.label}</span>
          <DatumPicker
            modus="tag"
            value={(wert as string) ?? ''}
            onChange={(v) => setzeWert(feld.id, v)}
            ariaLabel={feld.label}
          />
          {(fehler || feld.hinweis) && (
            <span className={`block text-xs mt-1 ${fehler ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'}`}>
              {fehler ?? feld.hinweis}
            </span>
          )}
        </label>
      )
    case 'toggle':
      return (
        <div className="flex items-center justify-between gap-3 py-1">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{feld.label}</span>
          {/* B15/S3: ui/Switch-SoT (aus dieser Inline-Variante extrahiert). */}
          <Switch
            checked={wert as boolean}
            onChange={(an) => setzeWert(feld.id, an)}
            ariaLabel={feld.label}
            disabled={feld.disabled}
          />
        </div>
      )
  }
}
