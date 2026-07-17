/**
 * GlobalStatusProvider — hält die EINE fetchende useGlobalStatus-Instanz auf
 * Shell-Ebene (LayoutV4) und verteilt sie per Context an alle Konsumenten
 * (StatusFusszeile, useEinstellungenStatus). Paket Q: erzwingt den Doc-Vertrag
 * „einmal auf Shell-Ebene" — vorher fetchte jede Hook-Instanz selbst.
 */
import { GlobalStatusContext, useGlobalStatusQuelle } from './useGlobalStatus'

export function GlobalStatusProvider({ children }: { children: React.ReactNode }) {
  const status = useGlobalStatusQuelle()
  return <GlobalStatusContext.Provider value={status}>{children}</GlobalStatusContext.Provider>
}
