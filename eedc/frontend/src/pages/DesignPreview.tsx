/**
 * DesignPreview — interne Showcase-Page für Style-Guide-Iteration.
 *
 * Sichtbar nur in DEV-Modus (`import.meta.env.DEV`). In Production-Builds
 * rendert nichts (kein Build-Bloat, keine versehentliche Anwender-Sicht).
 *
 * Zweck: Komponenten-Galerie für die Konzepte aus
 * `docs/KONZEPT-STYLE-GUIDE.md` und `docs/KONZEPT-MOBILE.md`.
 * Hier werden neue Komponenten + Tokens nebeneinander gezeigt, bevor sie in
 * den Anwender-Flow integriert werden. Wachsend pro Umsetzungs-Welle.
 *
 * Struktur folgt dem Style-Guide:
 *   Teil A — Visuelle Sprache (A1 Typografie, A2 Farben, A3 Datenzustand,
 *            A4 Animation, A5 Icons)
 *   Teil B — Komponenten (B1 KPI-Karten, B2 Tabellen, B3 Navigation,
 *            B4 Header, B5 Selektoren, B6 Aufklapp)
 *   Teil C — Layout + Texte (C1 Spacing, C2 Schreibweisen)
 *
 * Nur Bereiche mit aktivem Iterations-Bedarf werden ausgefüllt — der Rest
 * bleibt als Platzhalter strukturell sichtbar.
 */

export default function DesignPreview() {
  if (!import.meta.env.DEV) return null

  return (
    <div className="p-6 space-y-10 max-w-7xl mx-auto">
      <header className="border-b border-amber-300 dark:border-amber-700 pb-4">
        <div className="inline-block px-2 py-0.5 mb-2 text-xs font-mono bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 rounded">
          DEV-ONLY — Showcase
        </div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          eedc Design-Preview
        </h1>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          Komponenten-Galerie für die Style-Guide-Iteration. Sichtbar nur
          unter <code>localhost:3000</code>. Strukturiert nach{' '}
          <code>docs/KONZEPT-STYLE-GUIDE.md</code>.
        </p>
      </header>

      {/* ──────────── Teil A — Visuelle Sprache ──────────── */}

      <Section id="a1" title="A1 — Typografie-System" status="todo">
        <Placeholder>
          Schrift-Skala (Display, Title-XL/L/M/S, Body-L/M/S, Caption) als
          semantische Tokens. Konkrete Tabelle folgt mit erster Welle.
        </Placeholder>
      </Section>

      <Section id="a2" title="A2 — Farb-Palette + semantische Codes" status="todo">
        <Placeholder>
          Datentyp → Farbe (PV gelb, Kosten rot, Umwelt grün, Verbrauch blau,
          Speicher lila). Status-Farben separat. Dunkel/Hell-Mode-Linien.
        </Placeholder>
      </Section>

      <Section id="a3" title="A3 — Datenzustand-Vokabular" status="seed">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <DatenzustandCard token="—" label="Echte Datenlücke" />
          <DatenzustandCard token="N/A" label="Strukturell nicht zutreffend" hint="z. B. Komponente nicht vorhanden" />
          <DatenzustandCard token="…" label="In Berechnung" hint="z. B. Spinner / pending" />
          <DatenzustandCard token="?" label="Unsicher / Schätzung" hint="z. B. mit Konfidenz-Hinweis" />
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
          Aktuell etabliert: <code>—</code> (v3.29.1 #239). Andere Tokens
          noch nicht systematisch — siehe Disc #162.
        </p>
      </Section>

      <Section id="a4" title="A4 — Animation + Übergänge" status="todo">
        <Placeholder>
          Dauer-Konvention 150 / 300 / 500 ms, Easing-Standards. Was animiert
          (Wert-Tween, Hover, Toggle), was statisch (Layout, Modal).
        </Placeholder>
      </Section>

      <Section id="a5" title="A5 — Icons + Symbol-Konventionen" status="todo">
        <Placeholder>
          Lucide als Linien-SoT, Komponenten-Typ-Icons via{' '}
          <code>komponentenStyle.ts</code> (heute unvollständig — Disc #163).
          Status-Icons Check/Warning/Error/Info konsistent.
        </Placeholder>
      </Section>

      {/* ──────────── Teil B — Komponenten ──────────── */}

      <Section id="b1" title="B1 — KPI-Karten" status="vorbedingung">
        <p className="text-xs text-gray-600 dark:text-gray-400">
          Aktuell <strong>drei parallele Implementierungen</strong> in der
          Codebase:{' '}
          <code>components/ui/KPICard.tsx</code>,{' '}
          <code>components/dashboard/KPICard.tsx</code>,{' '}
          <code>pages/auswertung/KPICard.tsx</code>.{' '}
          SoT-Komponente folgt mit B9 (Konsolidierung). Bis dahin sind
          Karten-Varianten hier nebeneinander zu zeigen — als Vergleichs-
          und Migrations-Hilfe.
        </p>
        <Placeholder>Drei aktuellen Versionen + geplante SoT (Größen-Varianten sm/md/lg, Color-Enum, Truncation-Verhalten) folgen mit B9.</Placeholder>
      </Section>

      <Section id="b2" title="B2 — Tabellen + Listen" status="todo" />
      <Section id="b3" title="B3 — Navigation" status="todo">
        <Placeholder>
          Vergleich SubTabs (SoT) vs. PillTabs (deprecated). Migrations-
          Vorschau für die 3 letzten PillTabs-Verwender (Aussichten,
          Auswertung, Community).
        </Placeholder>
      </Section>
      <Section id="b4" title="B4 — Header + Banner" status="todo" />
      <Section id="b5" title="B5 — Selektoren" status="todo" />
      <Section id="b6" title="B6 — Aufklapp-Verhalten" status="todo" />

      {/* ──────────── Teil C — Layout + Texte ──────────── */}

      <Section id="c1" title="C1 — Spacing-Standards" status="todo" />
      <Section id="c2" title="C2 — Schreibweisen + Zahlen-Format" status="todo" />
    </div>
  )
}

// ──────────── Helper-Komponenten ────────────

type SectionStatus = 'todo' | 'seed' | 'vorbedingung' | 'aktiv' | 'fertig'

const STATUS_BADGE: Record<SectionStatus, { label: string; cls: string }> = {
  todo: { label: 'TODO', cls: 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300' },
  seed: { label: 'Skelett', cls: 'bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200' },
  vorbedingung: { label: 'Vorbedingung offen', cls: 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200' },
  aktiv: { label: 'In Arbeit', cls: 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-800 dark:text-indigo-200' },
  fertig: { label: 'Fertig', cls: 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200' },
}

function Section({
  id, title, status, children,
}: {
  id: string
  title: string
  status: SectionStatus
  children?: React.ReactNode
}) {
  const badge = STATUS_BADGE[status]
  return (
    <section id={id} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-800">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
        <span className={`text-xs px-2 py-0.5 rounded font-medium ${badge.cls}`}>{badge.label}</span>
      </div>
      {children}
    </section>
  )
}

function Placeholder({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-sm text-gray-500 dark:text-gray-400 italic border border-dashed border-gray-300 dark:border-gray-600 rounded p-3">
      {children}
    </div>
  )
}

function DatenzustandCard({ token, label, hint }: { token: string; label: string; hint?: string }) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded p-3">
      <div className="text-3xl font-semibold text-gray-700 dark:text-gray-200 text-center mb-1">{token}</div>
      <div className="text-xs font-medium text-gray-600 dark:text-gray-400 text-center">{label}</div>
      {hint && <div className="text-[10px] text-gray-500 dark:text-gray-400 text-center mt-1">{hint}</div>}
    </div>
  )
}
