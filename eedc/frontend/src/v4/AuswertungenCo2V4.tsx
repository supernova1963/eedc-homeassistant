/**
 * AuswertungenCo2V4 — CO₂-Auswertung (A.5). Dünner v4-Rahmen um den IST-Tab
 * `CO2Tab` (prop-getrieben, self-contained): selbst-ladender Daten-Sockel
 * (`useAuswertungBasis`) + Jahr-Filter; die IST-Komponente bleibt UNVERÄNDERT
 * wiederverwendet (eine Code-Wahrheit, IST-getreu wie A.2/A.3 — kein Neudesign).
 * Bilanz/Äquivalente (Bäume/Auto-km/Flüge)/Klimapositiv-Status (#284)/Monats-
 * Chart/CSV kommen 1:1 aus dem IST-Tab.
 */
import { LoadingSpinner, Card } from '../components/ui'
import { CO2Tab } from '../pages/auswertung/CO2Tab'
import { useSelectedAnlage } from '../hooks'
import { useAuswertungBasis } from './useAuswertungBasis'
import { AuswertungKopf } from './AuswertungKopf'

export default function AuswertungenCo2V4() {
  const { anlagen, selectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const basis = useAuswertungBasis(selectedAnlageId)

  if (anlagenLoading || basis.loading) return <LoadingSpinner text="Lade CO₂-Daten…" />
  if (anlagen.length === 0) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage angelegt.</p></Card>
      </div>
    )
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <AuswertungKopf titel="CO₂-Bilanz" jahr={basis.jahr} setJahr={basis.setJahr} jahre={basis.jahre} />
      <CO2Tab
        data={basis.gefiltert}
        stats={basis.stats}
        zeitraumLabel={basis.zeitraumLabel}
        anlageId={selectedAnlageId}
      />
    </div>
  )
}
