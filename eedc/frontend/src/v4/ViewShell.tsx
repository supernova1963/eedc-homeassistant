/**
 * ViewShell — Sicht-Schale für /v4-Inhalts-Sichten (IA v4, #243).
 *
 * Ab `lg` bleibt die zweite Leiste (`bar`, z. B. die Zeit-Achse) FIX außerhalb
 * des Scrollbereichs; darunter scrollt nur der Inhalt. Damit schließt der
 * vertikale Scrollbalken die Leiste auf dem Desktop nicht mehr ein (behebt das
 * Safari/Firefox-Ruckeln der früheren `sticky`-Leiste). Unter `lg` scrollt alles
 * zusammen (Mobile-Schale).
 *
 * Aus der IA-v4-Vorschau (`components/preview/IASkeleton.tsx` `ViewShell`) als
 * echte /v4-Komponente übernommen — Regel-SoT, damit Vorschau und Realbau dieselbe
 * Schale tragen. Setzt voraus, dass der `main`-Container von {@link LayoutV4} ab
 * `lg` `overflow-hidden lg:flex lg:flex-col lg:min-h-0` ist (gibt die Höhe).
 */
import type { ReactNode } from 'react'

export function ViewShell({ bar, children }: { bar?: ReactNode; children: ReactNode }) {
  return (
    <div className="lg:flex lg:flex-col lg:h-full lg:min-h-0">
      {bar}
      <div className="lg:flex-1 lg:overflow-auto lg:min-h-0">{children}</div>
    </div>
  )
}
