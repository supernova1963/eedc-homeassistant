/// <reference types="vite/client" />

// Build-Feature-Flags (siehe src/lib/flags.ts)
interface ImportMetaEnv {
  /** Schaltet den IA-v4-Vorschau-Routenbaum (`/v4/…`) frei. `.env.local`. */
  readonly VITE_IA_V4?: string
}

// SVG als Module (für Import als URL)
declare module '*.svg' {
  const content: string
  export default content
}

// PNG/JPG als Module
declare module '*.png' {
  const content: string
  export default content
}

declare module '*.jpg' {
  const content: string
  export default content
}
