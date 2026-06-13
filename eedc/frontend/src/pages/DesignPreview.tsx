/**
 * DesignPreview — lokale DEV-Route `/dev/design-preview` für das IA-v4-Skelett.
 *
 * Reine Guard-Hülle: das eigentliche Skelett liegt guard-frei in
 * `components/preview/IASkeleton.tsx` (damit es auch im öffentlichen
 * Production-Vorschau-Build unter `/eedc-homeassistant/preview/` rendert, siehe
 * `preview-main.tsx`). Hier nur der DEV-Sichtbarkeits-Guard: in Produktiv-Builds
 * der App (HA-Add-on) rendert diese Route nichts.
 */

import IASkeleton from '../components/preview/IASkeleton'

export default function DesignPreview() {
  if (!import.meta.env.DEV) return null
  return <IASkeleton />
}
