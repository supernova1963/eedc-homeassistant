/// <reference types="vite/client" />

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
