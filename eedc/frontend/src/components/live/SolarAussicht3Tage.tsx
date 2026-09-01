/**
 * SolarAussicht3Tage — 3-Tage-Solar-Vorschau (Heute/Morgen/Übermorgen) mit
 * VM/NM-Split + Verbrauchsprognose-Zeile unter „Heute".
 *
 * Aus `pages/LiveDashboard.tsx` extrahiert (IA-V4 A.3) — EINE Code-Wahrheit für
 * IST-Live + `v4/CockpitLiveV4`. Reine Darstellung; `heutePvKwh` (IST-PV heute)
 * fließt in den „verbleibend/übertroffen"-Vergleich der Heute-Zeile ein — ist er
 * `null` (Erzeugung unbekannt), entfällt die Vergleichszeile ganz, statt 0
 * anzunehmen.
 */
import { Info } from 'lucide-react'
import type { LiveWetterResponse } from '../../api/liveDashboard'
import type { SolarPrognoseTag } from '../../api/wetter'
import { SimpleTooltip } from '../ui/FormelTooltip'
import { fmtZahl, DATENROLLE, pvErtragKwh, pvVormittagKwh, pvNachmittagKwh, verbrauchsprofilBasis } from '../../lib'

export default function SolarAussicht3Tage({ prognose3Tage, wetter, heutePvKwh }: {
  prognose3Tage: SolarPrognoseTag[]
  wetter: LiveWetterResponse | null
  heutePvKwh: number | null
}) {
  if (!prognose3Tage || prognose3Tage.length === 0) return null
  // „Heute" folgt der gewählten Prognosequelle (`wetter.pv_prognose_kwh` —
  // Solcast/SFML/eedc); Morgen/Übermorgen kommen immer aus der Solar-Prognose
  // und zeigen dort seit v4.0.1 den eedc-korrigierten Wert (Fallback: OpenMeteo
  // roh). Der Tooltip sagt beides, damit Zahl und Beschriftung zusammenpassen.
  const heuteQuelle = wetter?.prognose_quelle === 'solcast' ? 'Solcast-Prognose (pur)'
    : wetter?.prognose_quelle === 'sfml' ? 'Solar Forecast ML (pur)'
    : 'eedc-Prognose (Open-Meteo + Korrektur)'
  const folgetageKanon = prognose3Tage.slice(1).some(t => t.eedc_kwh != null)
    ? 'eedc-Prognose (Open-Meteo + Korrektur)'
    : 'Open-Meteo (ohne Korrektur)'
  // ⭐ 2026-08-30: EINE Quelle für alle Zahlen dieses Blocks (Entscheid Gernot).
  // Vorher folgte nur die Kopfzahl von „Heute" der gewählten Quelle; Rest,
  // VM/NM und die Folgetage kamen immer aus dem eedc-Kanon. Drei Zahlen aus
  // zwei Rechenwegen addierten sich nicht — gemeldet von Burkard (#401) und
  // rapahl (PN 91821). `quelleTage[i]` trägt die Zahl der gewählten Quelle für
  // Tag i, oder `rueckfall: 'eedc'`, wenn sie so weit nicht reicht.
  const quelleTage = wetter?.prognose_quelle_tage ?? null
  const qTag = (i: number) => quelleTage?.[i] ?? null
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
        Solar-Aussicht{wetter?.prognose_quelle && wetter.prognose_quelle !== 'eedc' && ` (${wetter.prognose_quelle === 'solcast' ? 'Solcast' : 'SFML'})`} <SimpleTooltip text={`Alle Zahlen aus derselben Quelle: ${heuteQuelle}. Wo sie einen Tag nicht abdeckt, steht „eedc" dabei (dann: ${folgetageKanon}). „Heute" zeigt den nachgeführten Wert — bisher gemessen plus erwarteter Rest; die ursprüngliche Tagesprognose steht klein darunter. VM/NM = Split an Solar Noon.`}><Info className="inline w-3 h-3 text-gray-400 dark:text-gray-500 opacity-50 cursor-help" /></SimpleTooltip>
      </h3>
      {prognose3Tage.some(t => pvVormittagKwh(t) != null) && (
        <div className="grid grid-cols-[auto_1fr_7rem] px-3 mb-0.5">
          <span />
          <span />
          <span className="text-[10px] text-right">
            <span className="text-amber-500">VM</span>
            <span className="text-gray-400 dark:text-gray-500 mx-0.5">/</span>
            <span className="text-amber-400">NM</span>
          </span>
        </div>
      )}
      <div className="space-y-1.5">
        {prognose3Tage.map((tag, i) => {
          const label = i === 0 ? 'Heute' : i === 1 ? 'Morgen' : 'Übermorgen'
          const q = qTag(i)
          // Die ursprüngliche Tagesprognose der gewählten Quelle — sie bleibt
          // erhalten, sie wandert nur aus der Kopfzeile nach unten.
          const ursprungKwh = i === 0 ? (wetter?.pv_prognose_kwh ?? null) : null
          // ⭐ Kopfzahl von „Heute" ist der NACHGEFÜHRTE Wert (IST bisher +
          // Rest), nicht mehr die Tagesprognose. Damit addieren sich die drei
          // Zahlen des Blocks wieder sichtbar: gemessen + erwartet = Kopfzahl.
          // Vorher stand oben eine Zahl, die mit den beiden darunter nichts zu
          // tun hatte — Rainers Tag stand auf „17,6", während 23,5 kWh erzeugt
          // waren und 1,7 noch kommen sollten.
          //
          // ⚠ `heutePvKwh != null` ist Bedingung, aus demselben Grund wie unten
          // bei `abweichungProzent`: ohne bekannte Erzeugung liefert der Kanon
          // `ist_bisher` als 0,0 statt null, und die Kopfzahl bestünde allein
          // aus dem Rest — sie sähe nach einem Einbruch aus, obwohl nur die
          // Messung fehlt. Dann bleibt die Tagesprognose oben stehen.
          const nachgefuehrtKwh = i === 0 && heutePvKwh != null
            ? wetter?.pv_prognose_heute_rollend_kwh ?? null
            : null
          const kopfKwh = nachgefuehrtKwh
            ?? (i === 0 ? (wetter?.pv_prognose_kwh ?? pvErtragKwh(tag))
                        : (q && q.rueckfall == null ? q.kwh : pvErtragKwh(tag)))
          // VM/NM aus derselben Quelle wie die Zahl darüber. Liefert die
          // gewählte Quelle kein Stundenprofil für diesen Tag, gilt der Kanon.
          const vmKwh = q?.vm_kwh ?? pvVormittagKwh(tag)
          const nmKwh = q?.nm_kwh ?? pvNachmittagKwh(tag)
          const hasVmNm = vmKwh != null
          const isProminent = i < 3
          const verbrPrognKwh = i === 0 && wetter?.verbrauchsprofil?.length
            ? wetter.verbrauchsprofil.reduce((s, v) => s + v.verbrauch_kw, 0)
            : null
          // Wortlaut-SoT `lib/verbrauchsprofilHerkunft` — dieselbe Grundlage steht in
          // der Legende des Wetter-Widgets. Sie nennt seit N-48 auch die gemessene
          // Abdeckung: „N Tage" allein las sich wie die Güte des Profils.
          const verbrBasis = verbrauchsprofilBasis(
            wetter?.profil_typ, wetter?.profil_tage, wetter?.profil_slots,
          )
          const verbrTooltip = verbrBasis
            ? `Individuelles Profil (${verbrBasis}) — Haus + Batterie + WP + Wallbox + Sonstige`
            : 'BDEW H0 Standardlastprofil — Haus + Batterie + WP + Wallbox + Sonstige'
          // ⭐ „verbleibend" ist seit 2026-08-23 der GEMESSENE Rest, nicht mehr
          // die Differenz (rapahl-PN). Vorher stand hier
          // `pv_prognose_kwh − heutePvKwh` — eine Differenz, deren Minuend die
          // vergangenen Stunden als *Vorhersage* enthält. Läuft der Tag besser
          // als vorhergesagt, schrumpft die Restmenge dadurch, obwohl die Sonne
          // unverändert weiterscheint: An Rainers Beispiel standen 5,9 kWh
          // „verbleibend", während die Restprognose 12,0 kWh sagte.
          // Der Prognosen-Vergleich hat genau dieses Verfahren mit #296 abgelegt
          // („nicht mehr Tagesprognose − IST"); dieser Block hatte den Fix nie
          // bekommen. Jetzt liefert die Route den Rest selbst
          // (`pv_prognose_rest_kwh` = Σ Slots ab jetzt, laufende Stunde
          // anteilig) — dieselbe Größe, die `sonnenstunden_rest` daneben schon
          // immer war.
          //
          // Nach Sonnenuntergang gibt es keinen Rest mehr — dann steht dort
          // nichts (nicht 0: „der Tag ist durch" ist keine Restmenge).
          const nachSonnenuntergang = wetter?.sunset ? (() => {
            const now = new Date()
            const [h, m] = wetter.sunset!.split(':').map(Number)
            return now.getHours() * 60 + now.getMinutes() >= h * 60 + m
          })() : false
          const verbleibenKwh = i === 0 && !nachSonnenuntergang
            ? wetter?.pv_prognose_rest_kwh ?? null
            : null
          // Rainers zweiter Punkt: „Mit dem realen Restwert könnte auch gleich
          // eine %-tuale Abweichung des Tages angezeigt werden." Genau das —
          // der nachgeführte Tageswert (IST bisher + Rest) gegen die
          // Tagesprognose. Erst ab 5 % sichtbar: darunter ist es Rauschen, und
          // eine Prognose, die auf 2 % genau wäre, gibt es nicht.
          //
          // ⚠ `heutePvKwh` bleibt Bedingung — hier und NUR hier. Es ist kein
          // Rechenwert mehr, sondern das Signal „eedc kennt die heutige
          // Erzeugung". Ist sie unbekannt, liefert der Kanon `ist_bisher` als
          // 0,0 (nicht als null), und der nachgeführte Tageswert bestünde allein
          // aus dem Rest — die Abweichung läse sich dann als dramatischer
          // Einbruch, obwohl nur die Messung fehlt. Das ist die Klasse aus
          // Forum #22 (Algie, 2026-07-28), eine Ebene weiter: unbekannt ist
          // nicht null. Der Rest oben braucht die Bedingung NICHT — er ist
          // reine Prognose und von der IST-Kenntnis unabhängig.
          const abweichungProzent = i === 0
            && heutePvKwh != null
            && wetter?.pv_prognose_heute_rollend_kwh != null
            && wetter?.pv_prognose_kwh != null
            && wetter.pv_prognose_kwh > 0
            ? (() => {
                const p = Math.round(
                  (wetter.pv_prognose_heute_rollend_kwh! - wetter.pv_prognose_kwh!)
                  / wetter.pv_prognose_kwh! * 100,
                )
                return Math.abs(p) >= 5 ? p : null
              })()
            : null
          return (
            <div key={tag.datum}>
            <div className={`grid grid-cols-[auto_1fr_7rem] items-center gap-x-2 rounded-lg px-3 py-2 ${
              i === 0 ? 'bg-yellow-50 dark:bg-yellow-900/20' :
              'bg-amber-50/60 dark:bg-amber-900/10'
            }`}>
              <span className={`shrink-0 ${isProminent ? 'text-sm font-medium text-gray-600 dark:text-gray-300' : 'text-xs text-gray-400 dark:text-gray-500'}`}>
                {label}
                {/* Wo die gewählte Quelle nicht so weit reicht, steht das dabei
                    — statt still eine eedc-Zahl unter der Überschrift der
                    Fremdquelle zu zeigen (Burkard #401: „Cockpit → Aussicht
                    folgt der Einstellung gar nicht"). */}
                {q?.rueckfall === 'eedc' && (
                  <span className="ml-1 text-[9px] text-gray-400 dark:text-gray-500"
                        title="Die gewählte Prognosequelle liefert für diesen Tag keinen Wert — hier steht die eedc-Prognose.">
                    eedc
                  </span>
                )}
              </span>
              <div className="flex flex-col items-end">
                <span className={`font-bold ${DATENROLLE.pv.text} ${isProminent ? 'text-base' : 'text-xs'}`}>
                  {fmtZahl(kopfKwh, 1)}
                  <span className="text-xs font-normal ml-0.5">kWh</span>
                </span>
                {/* Die ursprüngliche Tagesprognose bleibt sichtbar: an ihr wird
                    morgens geplant und abends bewertet. Nur bei „Heute", und nur
                    wenn die Nachführung sie tatsächlich verschoben hat. */}
                {i === 0 && ursprungKwh != null && kopfKwh != null
                  && Math.abs(ursprungKwh - kopfKwh) >= 0.1 && (
                  <span className="text-[10px] text-gray-400 dark:text-gray-500"
                        title="Die Tagesprognose von heute Morgen — unverändert. Oben steht, worauf der Tag nach dem bisher Gemessenen hinausläuft.">
                    Prognose {fmtZahl(ursprungKwh, 1)} kWh
                  </span>
                )}
                {(verbleibenKwh != null && verbleibenKwh > 0) || abweichungProzent != null ? (
                  <span className={`text-[10px] ${(abweichungProzent ?? 0) >= 0 ? 'text-lime-600 dark:text-lime-400' : 'text-amber-600 dark:text-amber-400'}`}
                        title={[
                          verbleibenKwh != null && verbleibenKwh > 0
                            ? `Noch ~${fmtZahl(verbleibenKwh, 1)} kWh erwartet (Prognose der restlichen Stunden)`
                            : null,
                          wetter?.pv_prognose_heute_rollend_kwh != null
                            ? `Tag läuft auf ~${fmtZahl(wetter.pv_prognose_heute_rollend_kwh, 1)} kWh hinaus (bisher erzeugt + Rest)`
                            : null,
                        ].filter(Boolean).join('\n')}>
                    {verbleibenKwh != null && verbleibenKwh > 0 ? `~${fmtZahl(verbleibenKwh, 1)} verbl.` : ''}
                    {verbleibenKwh != null && verbleibenKwh > 0 && abweichungProzent != null ? ' ' : ''}
                    {/* N-324 (rapahl, PN 91547): „+14 %" stand nackt neben der
                        Prognose-Zahl und war in beide Richtungen lesbar — der
                        Melder las es als Aussage über die PROGNOSE, gemeint war
                        der TAG. Der Bezug steht jetzt sichtbar dabei, nicht nur
                        im Tooltip. Seit die Kopfzahl der nachgeführte Wert ist,
                        stehen beide Bezugsgrößen ohnehin direkt beieinander. */}
                    {abweichungProzent != null
                      ? `(${abweichungProzent > 0 ? '+' : ''}${abweichungProzent} % ggü. Prognose)`
                      : ''}
                  </span>
                ) : null}
              </div>
              <span className="text-right text-xs w-28">
                {hasVmNm ? (
                  <>
                    <span className="font-semibold text-amber-500">{fmtZahl(vmKwh!, 1)}</span>
                    <span className="text-gray-400 dark:text-gray-500 mx-0.5">/</span>
                    <span className="font-semibold text-amber-400">{fmtZahl(nmKwh ?? 0, 1)}</span>
                  </>
                ) : null}
              </span>
            </div>
            {/* Verbrauchsprognose im Stil der Prognose-Zeilen — nur unter Heute */}
            {verbrPrognKwh != null && (
              <div className="grid grid-cols-[auto_1fr_7rem] items-center gap-x-2 rounded-lg px-3 py-1 bg-gray-50 dark:bg-gray-700/50">
                <span className="text-xs text-gray-400 dark:text-gray-300 flex items-center gap-1">
                  Verbrauchsprognose
                  {wetter?.profil_typ?.startsWith('individuell') && (
                    <span className="text-[9px] text-emerald-500">(ind.)</span>
                  )}
                  <SimpleTooltip text={verbrTooltip}><Info className="w-3 h-3 opacity-40 cursor-help" /></SimpleTooltip>
                </span>
                <div className="flex flex-col items-end">
                  <span className="text-xs font-bold text-orange-500 dark:text-orange-400">
                    ~{fmtZahl(verbrPrognKwh, 1)}<span className="text-xs font-normal ml-0.5">kWh</span>
                  </span>
                </div>
                <span className="w-28" />
              </div>
            )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
