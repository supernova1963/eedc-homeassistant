/**
 * EnergieFlussBackground — SVG Defs + Hintergrund-Layer + Animationen.
 *
 * Extrahiert aus EnergieFluss.tsx (~991 Zeilen).
 * Rendert als SVG-Fragment innerhalb des uebergeordneten <svg>.
 */

import type { BgVariant } from './EnergieFluss'

interface BackgroundProps {
  W: number
  svgH: number
  CX: number
  CY: number
  lite: boolean
  bgVariant: BgVariant
  bgPhotoFile: Partial<Record<BgVariant, string>>
}

export default function EnergieFlussBackground({
  W, svgH, CX, CY, lite, bgVariant, bgPhotoFile,
}: BackgroundProps) {
  return (
    <>
        <defs>
          <clipPath id="ef-photo-clip">
            <rect width={W} height={svgH} rx="8" />
          </clipPath>
          {!lite && <style>{`
            @keyframes pulse-ring {
              0%, 100% { opacity: 0.15; }
              50% { opacity: 0.04; }
            }
            @keyframes bg-stream {
              from { stroke-dashoffset: 0; }
              to { stroke-dashoffset: -60; }
            }
            @keyframes haus-glow {
              0%, 100% { opacity: 0.35; }
              50% { opacity: 0.55; }
            }
          `}</style>}

          {/* Maske: Perspektivgitter nahe Zentrum ausblenden */}
          <radialGradient id="ef-grid-fade" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="white" stopOpacity="0" />
            <stop offset="25%" stopColor="white" stopOpacity="0.3" />
            <stop offset="60%" stopColor="white" stopOpacity="0.8" />
            <stop offset="100%" stopColor="white" stopOpacity="1" />
          </radialGradient>
          <mask id="ef-grid-mask">
            <rect width={W} height={svgH} fill="url(#ef-grid-fade)" />
          </mask>

          {/* Radiales Glow vom Zentrum — Light (verstärkt) */}
          <radialGradient id="ef-glow-light" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.55} gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.25" />
            <stop offset="20%" stopColor="#06b6d4" stopOpacity="0.14" />
            <stop offset="50%" stopColor="#3b82f6" stopOpacity="0.07" />
            <stop offset="100%" stopColor="#f8fafc" stopOpacity="0" />
          </radialGradient>
          {/* Radiales Glow vom Zentrum — Dark */}
          <radialGradient id="ef-glow-dark" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.55} gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.15" />
            <stop offset="20%" stopColor="#06b6d4" stopOpacity="0.08" />
            <stop offset="50%" stopColor="#3b82f6" stopOpacity="0.04" />
            <stop offset="100%" stopColor="#111827" stopOpacity="0" />
          </radialGradient>

          {/* Inner-Glow (3D-Spot unter dem Haus) — Light (verstärkt) */}
          <radialGradient id="ef-spot-light" cx={CX} cy={CY} r="80" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
          </radialGradient>
          {/* Inner-Glow — Dark */}
          <radialGradient id="ef-spot-dark" cx={CX} cy={CY} r="80" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#34d399" stopOpacity="0.14" />
            <stop offset="100%" stopColor="#34d399" stopOpacity="0" />
          </radialGradient>

          {/* Tiefe-Vignette — Light (verstärkt) */}
          <radialGradient id="ef-vignette-light" cx="50%" cy="50%" r="52%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0" />
            <stop offset="60%" stopColor="#e2e8f0" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#94a3b8" stopOpacity="0.45" />
          </radialGradient>
          {/* Tiefe-Vignette — Dark */}
          <radialGradient id="ef-vignette-dark" cx="50%" cy="50%" r="52%">
            <stop offset="0%" stopColor="#1f2937" stopOpacity="0" />
            <stop offset="70%" stopColor="#0f172a" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#020617" stopOpacity="0.6" />
          </radialGradient>

          {/* Filter: im Lite-Modus ohne Blur (Performance) */}
          {lite ? (
            <>
              <filter id="ef-inner-shadow"><feOffset dx="0" dy="0" /></filter>
              <filter id="ef-ring-glow"><feOffset dx="0" dy="0" /></filter>
              <filter id="ef-line-glow"><feOffset dx="0" dy="0" /></filter>
              <filter id="ef-icon-glow"><feOffset dx="0" dy="0" /></filter>
              <filter id="ef-card-shadow"><feOffset dx="0" dy="0" /></filter>
              <filter id="ef-haus-glow"><feOffset dx="0" dy="0" /></filter>
            </>
          ) : (
            <>
              {/* Innerer Schatten (3D-Einbuchtung) */}
              <filter id="ef-inner-shadow">
                <feGaussianBlur in="SourceAlpha" stdDeviation="8" result="blur" />
                <feOffset dx="0" dy="3" result="offsetBlur" />
                <feComposite in="SourceGraphic" in2="offsetBlur" operator="over" />
              </filter>

              {/* Soft-Glow für Ringe */}
              <filter id="ef-ring-glow">
                <feGaussianBlur stdDeviation="3" />
              </filter>

              {/* Glow-Filter für Flusslinien (weicher Schein) */}
              <filter id="ef-line-glow" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>

              {/* Glow-Filter für Icons */}
              <filter id="ef-icon-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur in="SourceGraphic" stdDeviation="3" />
              </filter>

              {/* Schatten für Knoten-Karten */}
              <filter id="ef-card-shadow" x="-10%" y="-10%" width="130%" height="140%">
                <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#000000" floodOpacity="0.15" />
              </filter>

              {/* Glow für Haus-Zentrum */}
              <filter id="ef-haus-glow" x="-60%" y="-60%" width="220%" height="220%">
                <feGaussianBlur in="SourceGraphic" stdDeviation="8" />
              </filter>
            </>
          )}

          {/* ─── Sunset-Variante: Gradients ─── */}
          {bgVariant === 'sunset' && <>
            {!lite && <style>{`
              @keyframes pulse-ring-sunset {
                0%, 100% { opacity: 0.20; }
                50% { opacity: 0.06; }
              }
              @keyframes sunset-stream {
                from { stroke-dashoffset: 0; }
                to { stroke-dashoffset: -60; }
              }
              @keyframes shimmer {
                0%, 100% { opacity: 0.12; }
                50% { opacity: 0.30; }
              }
            `}</style>}

            {/* ── Dark Mode: Himmel dunkel-lila → warmes Orange am Horizont ── */}
            <linearGradient id="ef-sky-sunset-dark" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#0f0520" />
              <stop offset="30%"  stopColor="#2d1b4e" />
              <stop offset="70%"  stopColor="#7b2d00" />
              <stop offset="100%" stopColor="#c84b11" />
            </linearGradient>
            {/* ── Dark Mode: Meer dunkles Kupfer → tiefes Marineblau ── */}
            <linearGradient id="ef-sea-sunset-dark" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#5c2a00" />
              <stop offset="40%"  stopColor="#0a1a3a" />
              <stop offset="100%" stopColor="#030d1e" />
            </linearGradient>

            {/* ── Light Mode: Himmel hellblau → Pfirsich → warmes Orange ── */}
            <linearGradient id="ef-sky-sunset-light" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#c8dff5" />
              <stop offset="35%"  stopColor="#f7d8b0" />
              <stop offset="75%"  stopColor="#f5a040" />
              <stop offset="100%" stopColor="#e8731a" />
            </linearGradient>
            {/* ── Light Mode: Meer goldene Spiegelung → Türkis → tieferes Blaugrün ── */}
            <linearGradient id="ef-sea-sunset-light" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#e8b86a" />
              <stop offset="30%"  stopColor="#5bbdc8" />
              <stop offset="100%" stopColor="#2f8a9a" />
            </linearGradient>

            {/* ── Sonnen-Glow Dark ── */}
            <radialGradient id="ef-sun-glow-dark" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.35} gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#ffd700" stopOpacity="0.55" />
              <stop offset="15%"  stopColor="#ff8c00" stopOpacity="0.30" />
              <stop offset="40%"  stopColor="#c84b11" stopOpacity="0.12" />
              <stop offset="100%" stopColor="#000000" stopOpacity="0" />
            </radialGradient>
            {/* ── Sonnen-Glow Light ── */}
            <radialGradient id="ef-sun-glow-light" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.35} gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#ffd700" stopOpacity="0.65" />
              <stop offset="15%"  stopColor="#ff8c00" stopOpacity="0.35" />
              <stop offset="45%"  stopColor="#f5a040" stopOpacity="0.15" />
              <stop offset="100%" stopColor="#ffffff"  stopOpacity="0" />
            </radialGradient>

            {/* ── Atmosphärisches Leuchten Dark ── */}
            <radialGradient id="ef-sun-atmo-dark" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.65} gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#ff6b00" stopOpacity="0.18" />
              <stop offset="35%"  stopColor="#ff4500" stopOpacity="0.08" />
              <stop offset="100%" stopColor="#000000" stopOpacity="0" />
            </radialGradient>
            {/* ── Atmosphärisches Leuchten Light ── */}
            <radialGradient id="ef-sun-atmo-light" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.65} gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#ff8c00" stopOpacity="0.22" />
              <stop offset="35%"  stopColor="#ffa040" stopOpacity="0.10" />
              <stop offset="100%" stopColor="#ffffff"  stopOpacity="0" />
            </radialGradient>

            {/* ── Innerer Sonnen-Spot Dark ── */}
            <radialGradient id="ef-sun-spot-dark" cx={CX} cy={CY} r="70" gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#ffd700" stopOpacity="0.45" />
              <stop offset="60%"  stopColor="#ffa500" stopOpacity="0.15" />
              <stop offset="100%" stopColor="#ffa500" stopOpacity="0" />
            </radialGradient>
            {/* ── Innerer Sonnen-Spot Light ── */}
            <radialGradient id="ef-sun-spot-light" cx={CX} cy={CY} r="70" gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#ffd700" stopOpacity="0.55" />
              <stop offset="60%"  stopColor="#ffb020" stopOpacity="0.20" />
              <stop offset="100%" stopColor="#ffb020" stopOpacity="0" />
            </radialGradient>

            {/* ── Vignette Dark (Ränder lila-dunkel) ── */}
            <radialGradient id="ef-vignette-sunset-dark" cx="50%" cy="50%" r="52%">
              <stop offset="0%"   stopColor="#000000" stopOpacity="0" />
              <stop offset="65%"  stopColor="#1a0533"  stopOpacity="0.25" />
              <stop offset="100%" stopColor="#0a0015"  stopOpacity="0.55" />
            </radialGradient>
            {/* ── Vignette Light (Ränder warm-beige) ── */}
            <radialGradient id="ef-vignette-sunset-light" cx="50%" cy="50%" r="52%">
              <stop offset="0%"   stopColor="#ffffff"  stopOpacity="0" />
              <stop offset="60%"  stopColor="#c87820"  stopOpacity="0.10" />
              <stop offset="100%" stopColor="#8b4010"  stopOpacity="0.28" />
            </radialGradient>

            {/* Grid-Fade-Maske für Sunset-Perspektivgitter */}
            <radialGradient id="ef-grid-fade-s" cx="50%" cy="50%" r="50%">
              <stop offset="0%"   stopColor="white" stopOpacity="0" />
              <stop offset="25%"  stopColor="white" stopOpacity="0.3" />
              <stop offset="60%"  stopColor="white" stopOpacity="0.8" />
              <stop offset="100%" stopColor="white" stopOpacity="1" />
            </radialGradient>
            <mask id="ef-grid-mask-s">
              <rect width={W} height={svgH} fill="url(#ef-grid-fade-s)" />
            </mask>
            {/* ClipPaths: Himmel / Meer trennen */}
            <clipPath id="ef-sky-clip">
              <rect x={-W} y={-svgH} width={W * 3} height={CY + svgH} />
            </clipPath>
            <clipPath id="ef-sea-clip">
              <rect x={-W} y={CY} width={W * 3} height={svgH * 2} />
            </clipPath>
          </>}

          {/* ─── Alps-Variante: Gradients ─── */}
          {bgVariant === 'alps' && <>
            {!lite && <style>{`
              @keyframes cloud-drift {
                from { transform: translateX(0); }
                to   { transform: translateX(${W * 0.18}px); }
              }
              @keyframes snow-sparkle {
                0%, 100% { opacity: 0; }
                50%       { opacity: 0.85; }
              }
              @keyframes star-twinkle {
                0%, 100% { opacity: 0.15; }
                50%       { opacity: 0.65; }
              }
            `}</style>}

            {/* Himmel Light: klares Bergblau oben → dunstiger Horizont */}
            <linearGradient id="ef-sky-alps-light" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#5ba3d8" />
              <stop offset="45%"  stopColor="#96c8f0" />
              <stop offset="100%" stopColor="#d0e8f8" />
            </linearGradient>
            {/* Himmel Dark: Nachtgrün / Sternennacht über den Alpen */}
            <linearGradient id="ef-sky-alps-dark" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#07090a" />
              <stop offset="40%"  stopColor="#0e1610" />
              <stop offset="100%" stopColor="#1a2a1c" />
            </linearGradient>

            {/* Tal-Boden Light: alpines Grün */}
            <linearGradient id="ef-valley-alps-light" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#6a9870" />
              <stop offset="100%" stopColor="#3a6040" />
            </linearGradient>
            {/* Tal-Boden Dark: dunkler Nadelwald */}
            <linearGradient id="ef-valley-alps-dark" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#0e1a0e" />
              <stop offset="100%" stopColor="#060c06" />
            </linearGradient>

            {/* Zentrum-Glow Light: kühles Blau (Bergluft) */}
            <radialGradient id="ef-alps-glow-light" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.45} gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#60a8e8" stopOpacity="0.30" />
              <stop offset="35%"  stopColor="#4488c0" stopOpacity="0.12" />
              <stop offset="100%" stopColor="#ffffff"  stopOpacity="0" />
            </radialGradient>
            {/* Zentrum-Glow Dark: Mondlicht grün-grau */}
            <radialGradient id="ef-alps-glow-dark" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.45} gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#50a060" stopOpacity="0.18" />
              <stop offset="35%"  stopColor="#306040" stopOpacity="0.08" />
              <stop offset="100%" stopColor="#000000"  stopOpacity="0" />
            </radialGradient>

            {/* Vignette Light: kühle Ränder */}
            <radialGradient id="ef-vignette-alps-light" cx="50%" cy="50%" r="52%">
              <stop offset="0%"   stopColor="#ffffff"  stopOpacity="0" />
              <stop offset="60%"  stopColor="#4a80b0"  stopOpacity="0.10" />
              <stop offset="100%" stopColor="#1a3050"  stopOpacity="0.30" />
            </radialGradient>
            {/* Vignette Dark: dunkelgrüne Ränder */}
            <radialGradient id="ef-vignette-alps-dark" cx="50%" cy="50%" r="52%">
              <stop offset="0%"   stopColor="#000000"  stopOpacity="0" />
              <stop offset="60%"  stopColor="#030a04"  stopOpacity="0.35" />
              <stop offset="100%" stopColor="#010401"  stopOpacity="0.65" />
            </radialGradient>

            {/* Schneefunkeln-Maske: Fade nahe Zentrum */}
            <radialGradient id="ef-alps-fade" cx="50%" cy="30%" r="55%">
              <stop offset="0%"   stopColor="white" stopOpacity="0.2" />
              <stop offset="50%"  stopColor="white" stopOpacity="0.7" />
              <stop offset="100%" stopColor="white" stopOpacity="1" />
            </radialGradient>
            <mask id="ef-alps-mask">
              <rect width={W} height={svgH} fill="url(#ef-alps-fade)" />
            </mask>
            <clipPath id="ef-alps-sky-clip">
              <rect x={-W} y={-svgH} width={W * 3} height={CY + svgH} />
            </clipPath>
          </>}
        </defs>

        {/* ═══ Hintergrund-Layer ═══ */}
        <g className="pointer-events-none">
          {/* Basis-Hintergrund (Light etwas dunkler für Kontrast) */}
          {bgVariant !== 'sunset' && bgVariant !== 'alps' && !bgPhotoFile[bgVariant] && <rect width={W} height={svgH} className="fill-gray-100 dark:fill-gray-900" rx="8" />}

          {/* Foto-Hintergrund */}
          {bgPhotoFile[bgVariant] && <>
            <rect width={W} height={svgH} fill="#000" rx="8" />
            <image
              href={bgPhotoFile[bgVariant]}
              x="0" y="0" width={W} height={svgH}
              preserveAspectRatio="xMidYMid slice"
              clipPath="url(#ef-photo-clip)"
            />
            {/* Overlay: hell im Light-Mode, dunkel im Dark-Mode — für Lesbarkeit der Knoten */}
            <rect width={W} height={svgH}
              className="opacity-100 dark:opacity-0"
              fill="rgba(255,255,255,0.35)" clipPath="url(#ef-photo-clip)" />
            <rect width={W} height={svgH}
              className="opacity-0 dark:opacity-100"
              fill="rgba(0,0,0,0.45)" clipPath="url(#ef-photo-clip)" />
          </>}
          {/* Sunset: Himmel + Meer — Light Mode */}
          {bgVariant === 'sunset' && <>
            <rect x="0" y="0"  width={W} height={CY}        fill="url(#ef-sky-sunset-light)" className="opacity-100 dark:opacity-0" />
            <rect x="0" y={CY} width={W} height={svgH - CY} fill="url(#ef-sea-sunset-light)" className="opacity-100 dark:opacity-0" />
          </>}
          {/* Sunset: Himmel + Meer — Dark Mode */}
          {bgVariant === 'sunset' && <>
            <rect x="0" y="0"  width={W} height={CY}        fill="url(#ef-sky-sunset-dark)" className="opacity-0 dark:opacity-100" />
            <rect x="0" y={CY} width={W} height={svgH - CY} fill="url(#ef-sea-sunset-dark)" className="opacity-0 dark:opacity-100" />
          </>}

          {/* Alps: Himmel + Tal + Bergsilhouetten */}
          {bgVariant === 'alps' && (() => {
            // Bergpfad-Generator: peaks = [[xFraction, höhe über CY], ...]
            const mkMtn = (peaks: [number, number][]): string => {
              const pts: [number, number][] = [
                [0, CY],
                ...peaks.map(([xf, h]) => [xf * W, CY - h] as [number, number]),
                [W, CY],
              ]
              let d = `M ${pts[0][0]} ${pts[0][1]}`
              for (let i = 0; i < pts.length - 2; i++) {
                const [qx, qy] = pts[i + 1]
                const nx = (pts[i + 1][0] + pts[i + 2][0]) / 2
                const ny = (pts[i + 1][1] + pts[i + 2][1]) / 2
                if (i === 0) d += ` L ${(pts[0][0] + pts[1][0]) / 2} ${(pts[0][1] + pts[1][1]) / 2}`
                d += ` Q ${qx} ${qy} ${nx} ${ny}`
              }
              return d + ` L ${W} ${CY} Z`
            }
            // Hintere Bergkette (höchste Gipfel, atmosphärisch)
            const farPeaks: [number, number][] = [
              [0.00,45],[0.08,95],[0.17,58],[0.27,128],[0.37,72],
              [0.47,118],[0.57,65],[0.68,140],[0.78,88],[0.88,110],
              [0.96,55],[1.00,42],
            ]
            // Mittlere Bergkette
            const midPeaks: [number, number][] = [
              [0.00,28],[0.07,78],[0.16,44],[0.25,102],[0.34,58],
              [0.44,88],[0.54,38],[0.64,96],[0.73,56],[0.83,76],
              [0.92,40],[1.00,24],
            ]
            // Vordergrund (dunkelste, niedrigste)
            const nearPeaks: [number, number][] = [
              [0.00,16],[0.06,50],[0.14,28],[0.23,64],[0.32,38],
              [0.43,56],[0.53,22],[0.63,70],[0.72,46],[0.82,60],
              [0.92,34],[1.00,16],
            ]
            // Schneekuppen: Pfad über alle Gipfel > minH
            const mkSnow = (peaks: [number, number][], minH: number, sz: number) =>
              peaks.filter(([, h]) => h > minH).map(([xf, h]) => {
                const px = xf * W, py = CY - h
                return `M ${px - sz} ${py + sz * 0.55} Q ${px - sz * 0.2} ${py + sz * 0.05} ${px} ${py - sz * 0.3} Q ${px + sz * 0.2} ${py + sz * 0.05} ${px + sz} ${py + sz * 0.55} Q ${px} ${py + sz * 0.3} ${px - sz} ${py + sz * 0.55}`
              }).join(' ')

            const farPath  = mkMtn(farPeaks)
            const midPath  = mkMtn(midPeaks)
            const nearPath = mkMtn(nearPeaks)
            const snowFar  = mkSnow(farPeaks, 90, 14)
            const snowMid  = mkSnow(midPeaks, 75, 10)

            return (
              <>
                {/* Himmel */}
                <rect x="0" y="0" width={W} height={CY} fill="url(#ef-sky-alps-light)" className="opacity-100 dark:opacity-0" />
                <rect x="0" y="0" width={W} height={CY} fill="url(#ef-sky-alps-dark)"  className="opacity-0 dark:opacity-100" />
                {/* Talboden */}
                <rect x="0" y={CY} width={W} height={svgH - CY} fill="url(#ef-valley-alps-light)" className="opacity-100 dark:opacity-0" />
                <rect x="0" y={CY} width={W} height={svgH - CY} fill="url(#ef-valley-alps-dark)"  className="opacity-0 dark:opacity-100" />

                {/* ── Light Mode Berge ── */}
                <g className="opacity-100 dark:opacity-0">
                  <path d={farPath}  fill="#8aafc8" fillOpacity="0.55" />
                  <path d={midPath}  fill="#4e7898" fillOpacity="0.80" />
                  <path d={nearPath} fill="#2c5070" fillOpacity="0.95" />
                  <path d={snowFar}  fill="#eef6ff" fillOpacity="0.88" />
                  <path d={snowMid}  fill="#f4f9ff" fillOpacity="0.78" />
                </g>
                {/* ── Dark Mode Berge: Granit-Grau + Nadelwald-Grün ── */}
                <g className="opacity-0 dark:opacity-100">
                  {/* Hintere Kette: Granit-Hellgrau — deutlich vom Himmel abhebend */}
                  <path d={farPath}  fill="#4a5248" fillOpacity="0.82" />
                  {/* Mittlere Kette: dunkleres Grau-Grün (Nadelwald-Hänge) */}
                  <path d={midPath}  fill="#2a3828" fillOpacity="0.93" />
                  {/* Vordergrund: fast schwarz mit grünem Unterton */}
                  <path d={nearPath} fill="#141e12" fillOpacity="0.98" />
                  {/* Mondlichtschnee: kühles Weißgrau */}
                  <path d={snowFar}  fill="#ccd8c8" fillOpacity="0.82" />
                  <path d={snowMid}  fill="#baccb8" fillOpacity="0.68" />
                </g>
              </>
            )
          })()}

          {/* ─── Perspektivgitter (Fluchtpunkt = Haus-Zentrum) — nur im Effekt-Modus ─── */}
          {!lite && bgVariant !== 'sunset' && bgVariant !== 'alps' && (
            <g mask="url(#ef-grid-mask)">
              {/* Radiale Strahlen vom Zentrum zu den Rändern */}
              {Array.from({ length: 32 }, (_, i) => {
                const angle = (i / 32) * Math.PI * 2
                const farR = Math.max(W, svgH) * 0.9
                const ex = CX + Math.cos(angle) * farR
                const ey = CY + Math.sin(angle) * farR
                const isMajor = i % 4 === 0
                const isMid = i % 2 === 0
                return (
                  <line
                    key={`ray-${i}`}
                    x1={CX} y1={CY} x2={ex} y2={ey}
                    stroke="#64748b"
                    strokeWidth={isMajor ? 0.9 : isMid ? 0.5 : 0.3}
                    strokeOpacity={isMajor ? 0.3 : isMid ? 0.2 : 0.12}
                  />
                )
              })}
              {/* Konzentrische Perspektiv-Ringe (Abstand wächst nach außen → Tiefe) */}
              {[30, 55, 85, 125, 175, 240, 320].map((r, i) => (
                <circle
                  key={`pgrid-${i}`}
                  cx={CX} cy={CY} r={r}
                  fill="none"
                  stroke="#64748b"
                  strokeWidth={i < 2 ? 0.3 : 0.5 + i * 0.1}
                  strokeOpacity={0.12 + i * 0.04}
                />
              ))}
              {/* Knotenpunkte an den Schnittpunkten (äußere Ringe) */}
              {[85, 125, 175, 240, 320].flatMap((r, ri) =>
                Array.from({ length: 32 }, (_, ai) => {
                  if (ri < 2 && ai % 2 !== 0) return null
                  if (ri < 1 && ai % 4 !== 0) return null
                  const angle = (ai / 32) * Math.PI * 2
                  const px = CX + Math.cos(angle) * r
                  const py = CY + Math.sin(angle) * r
                  return (
                    <circle
                      key={`node-${ri}-${ai}`}
                      cx={px} cy={py}
                      r={0.7 + ri * 0.2}
                      fill="#64748b"
                      fillOpacity={0.18 + ri * 0.04}
                    />
                  )
                })
              )}
            </g>
          )}
          {/* ─── Sunset-Gitter: Krepuskulare Strahlen (Himmel) + Meerperspektive ─── */}
          {!lite && bgVariant === 'sunset' && (() => {
            // Gemeinsame Geometrie-Berechnung für beide Modi
            const farR = Math.max(W, svgH) * 1.2
            const skyRays = Array.from({ length: 20 }, (_, i) => ({
              angle: -Math.PI + (i / 19) * Math.PI,
              isEven: i % 2 === 0,
              isMajor: i % 4 === 0,
            }))
            const seaLines = Array.from({ length: 20 }, (_, i) => ({
              angle: (i / 19) * Math.PI,
              isMajor: i % 4 === 0,
              isMid: i % 2 === 0,
            }))
            const waveEllipses = [22, 50, 90, 140, 200, 270]
            const sparkRows = [50, 90, 140, 200]
            const arcRadii = [65, 115, 175, 250, 340]

            const renderGrid = (
              rayWide1: string, rayWide2: string,
              rayThin: string,
              arc1: string, arc2: string,
              seaLine: string, wave: string, spark: string,
            ) => (
              <>
                {/* ══ HIMMEL: Krepuskulare Strahlen ══ */}
                {skyRays.map(({ angle, isEven }, i) => {
                  const ex = CX + Math.cos(angle) * farR
                  const ey = CY + Math.sin(angle) * farR
                  return (
                    <line key={`cray-wide-${i}`}
                      x1={CX} y1={CY} x2={ex} y2={ey}
                      stroke={isEven ? rayWide1 : rayWide2}
                      strokeWidth={farR * 0.14}
                      strokeOpacity={isEven ? 0.07 : 0.04}
                      clipPath="url(#ef-sky-clip)" />
                  )
                })}
                {skyRays.map(({ angle, isMajor }, i) => {
                  const ex = CX + Math.cos(angle) * farR
                  const ey = CY + Math.sin(angle) * farR
                  return (
                    <line key={`cray-thin-${i}`}
                      x1={CX} y1={CY} x2={ex} y2={ey}
                      stroke={rayThin}
                      strokeWidth={isMajor ? 0.9 : 0.4}
                      strokeOpacity={isMajor ? 0.38 : 0.18}
                      clipPath="url(#ef-sky-clip)" />
                  )
                })}
                {/* Atmosphären-Bögen */}
                {arcRadii.map((r, i) => (
                  <path key={`arc-${i}`}
                    d={`M ${CX - r} ${CY} A ${r} ${r} 0 0 1 ${CX + r} ${CY}`}
                    fill="none"
                    stroke={i < 2 ? arc1 : arc2}
                    strokeWidth={0.4 + i * 0.15}
                    strokeOpacity={0.14 + i * 0.025}
                    clipPath="url(#ef-sky-clip)" />
                ))}

                {/* ══ MEER: Perspektivlinien ══ */}
                {seaLines.map(({ angle, isMajor, isMid }, i) => {
                  const ex = CX + Math.cos(angle) * (Math.max(W, svgH) * 0.95)
                  const ey = CY + Math.sin(angle) * (Math.max(W, svgH) * 0.95)
                  return (
                    <line key={`pline-${i}`}
                      x1={CX} y1={CY} x2={ex} y2={ey}
                      stroke={seaLine}
                      strokeWidth={isMajor ? 0.9 : isMid ? 0.5 : 0.3}
                      strokeOpacity={isMajor ? 0.32 : isMid ? 0.20 : 0.12}
                      clipPath="url(#ef-sea-clip)" />
                  )
                })}
                {/* Elliptische Wellenebenen */}
                {waveEllipses.map((dy, i) => (
                  <ellipse key={`wave-${i}`}
                    cx={CX} cy={CY + dy}
                    rx={CX * (0.22 + i * 0.14)}
                    ry={Math.max(3, dy * 0.10)}
                    fill="none"
                    stroke={wave}
                    strokeWidth={0.4 + i * 0.12}
                    strokeOpacity={0.12 + i * 0.03}
                    clipPath="url(#ef-sea-clip)" />
                ))}
                {/* Lichtfunken auf dem Wasser */}
                {sparkRows.flatMap((dy, ri) =>
                  Array.from({ length: 14 }, (_, ai) => {
                    if (ri < 1 && ai % 2 !== 0) return null
                    const angle = (ai / 13) * Math.PI
                    const rx = CX * (0.36 + ri * 0.14)
                    const px = CX + Math.cos(angle) * rx
                    const py = CY + dy + Math.sin(angle) * Math.max(3, dy * 0.10)
                    if (py <= CY + 2) return null
                    return (
                      <circle key={`spark-${ri}-${ai}`}
                        cx={px} cy={py}
                        r={0.6 + ri * 0.25}
                        fill={spark}
                        fillOpacity={0.22 + ri * 0.05} />
                    )
                  })
                )}
              </>
            )

            return (
              <>
                {/* Light Mode */}
                <g mask="url(#ef-grid-mask-s)" className="opacity-100 dark:opacity-0">
                  {renderGrid('#c47820', '#c05808', '#c47820', '#c05808', '#8b1a50', '#0e6070', '#0e6070', '#c47820')}
                </g>
                {/* Dark Mode */}
                <g mask="url(#ef-grid-mask-s)" className="opacity-0 dark:opacity-100">
                  {renderGrid('#ffd700', '#ff8c00', '#ffd700', '#ff8c00', '#ec4899', '#c47310', '#c47310', '#ffd700')}
                </g>
              </>
            )
          })()}

          {/* Alps-Gitter: Sonnenstrahlen im Bergkamm-Himmel */}
          {!lite && bgVariant === 'alps' && (() => {
            // Sonne sitzt rechts oben (10-Uhr-Position)
            const sunX = CX + W * 0.22, sunY = CY * 0.28
            const farR  = Math.max(W, svgH) * 1.1
            const rays  = Array.from({ length: 14 }, (_, i) => {
              const angle = -Math.PI * 0.85 + (i / 13) * Math.PI * 0.7
              return { ex: sunX + Math.cos(angle) * farR, ey: sunY + Math.sin(angle) * farR, isMajor: i % 3 === 0 }
            })
            return (
              <>
                {/* Light: goldene Sonnenstrahlen */}
                <g mask="url(#ef-alps-mask)" className="opacity-100 dark:opacity-0">
                  {rays.map(({ ex, ey, isMajor }, i) => (
                    <line key={`alray-${i}`} x1={sunX} y1={sunY} x2={ex} y2={ey}
                      stroke="#f0d060" strokeWidth={isMajor ? farR * 0.10 : farR * 0.05}
                      strokeOpacity={isMajor ? 0.07 : 0.04} clipPath="url(#ef-alps-sky-clip)" />
                  ))}
                  {rays.map(({ ex, ey, isMajor }, i) => (
                    <line key={`althin-${i}`} x1={sunX} y1={sunY} x2={ex} y2={ey}
                      stroke="#ffe080" strokeWidth={isMajor ? 0.8 : 0.3}
                      strokeOpacity={isMajor ? 0.35 : 0.16} clipPath="url(#ef-alps-sky-clip)" />
                  ))}
                  {/* Sonnenscheibe */}
                  <circle cx={sunX} cy={sunY} r={8} fill="#fff8d0" fillOpacity="0.70" clipPath="url(#ef-alps-sky-clip)" />
                  <circle cx={sunX} cy={sunY} r={14} fill="#ffe060" fillOpacity="0.20" clipPath="url(#ef-alps-sky-clip)" />
                </g>
                {/* Dark: Mond + Sterne */}
                <g mask="url(#ef-alps-mask)" className="opacity-0 dark:opacity-100">
                  {/* Mondscheibe — warm-weißes Mondlicht */}
                  <circle cx={sunX} cy={sunY} r={9}  fill="#e8eee4" fillOpacity="0.82" clipPath="url(#ef-alps-sky-clip)" />
                  <circle cx={sunX} cy={sunY} r={16} fill="#c0cebb" fillOpacity="0.20" clipPath="url(#ef-alps-sky-clip)" />
                  {/* Mondlicht-Strahlen (grau-grünlich) */}
                  {rays.map(({ ex, ey, isMajor }, i) => (
                    <line key={`moon-${i}`} x1={sunX} y1={sunY} x2={ex} y2={ey}
                      stroke="#90aa88" strokeWidth={isMajor ? 0.9 : 0.35}
                      strokeOpacity={isMajor ? 0.40 : 0.18} clipPath="url(#ef-alps-sky-clip)" />
                  ))}
                  {/* Sterne (weißlich auf dunkelgrünem Himmel) */}
                  {Array.from({ length: 28 }, (_, i) => {
                    const sx = (W * 0.05) + (i * W * 0.033) % (W * 0.90)
                    const sy = (CY * 0.06) + ((i * 47 + 13) % 100) / 100 * CY * 0.75
                    const sz = i % 5 === 0 ? 1.5 : i % 3 === 0 ? 1.0 : 0.65
                    return <circle key={`star-${i}`} cx={sx} cy={sy} r={sz} fill="#ddeedd" fillOpacity="0.80" clipPath="url(#ef-alps-sky-clip)" />
                  })}
                  {/* Aurora-Hauch (grüne Bänder knapp über den Berggipfeln) */}
                  {[0, 1, 2].map(i => (
                    <ellipse key={`aurora-${i}`}
                      cx={CX + (i - 1) * W * 0.22} cy={CY - 60 - i * 18}
                      rx={W * (0.22 + i * 0.08)} ry={12 + i * 4}
                      fill="none" stroke="#4a9060" strokeWidth={6 + i * 3}
                      strokeOpacity={0.12 + i * 0.03}
                      filter="url(#ef-ring-glow)"
                      clipPath="url(#ef-alps-sky-clip)" />
                  ))}
                </g>
              </>
            )
          })()}

          {/* Radiales Energie-Glow (Default) */}
          {bgVariant === 'default' && <>
            <rect width={W} height={svgH} className="opacity-100 dark:opacity-0" fill="url(#ef-glow-light)" rx="8" />
            <rect width={W} height={svgH} className="opacity-0 dark:opacity-100" fill="url(#ef-glow-dark)" rx="8" />
          </>}
          {/* 3D-Spot unter dem Haus (Default) */}
          {bgVariant === 'default' && <>
            <rect width={W} height={svgH} className="opacity-100 dark:opacity-0" fill="url(#ef-spot-light)" rx="8" />
            <rect width={W} height={svgH} className="opacity-0 dark:opacity-100" fill="url(#ef-spot-dark)" rx="8" />
          </>}
          {/* Alps: Bergluft-Glow */}
          {bgVariant === 'alps' && <>
            <rect width={W} height={svgH} fill="url(#ef-alps-glow-light)" className="opacity-100 dark:opacity-0" />
            <rect width={W} height={svgH} fill="url(#ef-alps-glow-dark)"  className="opacity-0 dark:opacity-100" />
          </>}
          {/* Sunset: Sonnen-Glow-Layer Light */}
          {bgVariant === 'sunset' && <>
            <rect width={W} height={svgH} fill="url(#ef-sun-glow-light)"  className="opacity-100 dark:opacity-0" />
            <rect width={W} height={svgH} fill="url(#ef-sun-atmo-light)"  className="opacity-100 dark:opacity-0" />
            <rect width={W} height={svgH} fill="url(#ef-sun-spot-light)"  className="opacity-100 dark:opacity-0" />
          </>}
          {/* Sunset: Sonnen-Glow-Layer Dark */}
          {bgVariant === 'sunset' && <>
            <rect width={W} height={svgH} fill="url(#ef-sun-glow-dark)"  className="opacity-0 dark:opacity-100" />
            <rect width={W} height={svgH} fill="url(#ef-sun-atmo-dark)"  className="opacity-0 dark:opacity-100" />
            <rect width={W} height={svgH} fill="url(#ef-sun-spot-dark)"  className="opacity-0 dark:opacity-100" />
          </>}
          {/* Horizontlinie (goldener Schimmer) */}
          {bgVariant === 'sunset' && (
            <line x1={0} y1={CY} x2={W} y2={CY} stroke="#ffd700" strokeWidth="0.8" strokeOpacity="0.38" />
          )}

          {/* ─── Hintergrund-Animationen — nur im Effekt-Modus ─── */}
          {!lite && bgVariant !== 'sunset' && (<>
          {/* Fließende Strom-Ströme */}
          <path
            d={`M ${CX - 80} 10 Q ${CX - 40} ${CY * 0.4} ${CX} ${CY}`}
            fill="none" stroke="#ca8a04" strokeWidth="2" strokeOpacity="0.18"
            strokeDasharray="3 12"
            style={{ animation: 'bg-stream 4s linear infinite' }}
          />
          <path
            d={`M ${CX + 80} 10 Q ${CX + 40} ${CY * 0.4} ${CX} ${CY}`}
            fill="none" stroke="#ca8a04" strokeWidth="1.5" strokeOpacity="0.14"
            strokeDasharray="2 10"
            style={{ animation: 'bg-stream 5s linear infinite' }}
          />
          <path
            d={`M ${CX} 5 Q ${CX + 15} ${CY * 0.5} ${CX} ${CY}`}
            fill="none" stroke="#eab308" strokeWidth="1.8" strokeOpacity="0.16"
            strokeDasharray="4 14"
            style={{ animation: 'bg-stream 3.5s linear infinite' }}
          />
          <path
            d={`M ${CX} ${CY} Q ${CX - 50} ${CY + 60} ${CX - 100} ${svgH - 10}`}
            fill="none" stroke="#059669" strokeWidth="1.8" strokeOpacity="0.16"
            strokeDasharray="3 12"
            style={{ animation: 'bg-stream 4.5s linear infinite' }}
          />
          <path
            d={`M ${CX} ${CY} Q ${CX + 50} ${CY + 60} ${CX + 100} ${svgH - 10}`}
            fill="none" stroke="#059669" strokeWidth="1.5" strokeOpacity="0.13"
            strokeDasharray="2 10"
            style={{ animation: 'bg-stream 5.5s linear infinite' }}
          />
          <path
            d={`M 5 ${CY - 30} Q ${CX * 0.4} ${CY - 10} ${CX} ${CY}`}
            fill="none" stroke="#dc2626" strokeWidth="1.5" strokeOpacity="0.14"
            strokeDasharray="2 10"
            style={{ animation: 'bg-stream 6s linear infinite' }}
          />
          <path
            d={`M 5 ${CY + 30} Q ${CX * 0.4} ${CY + 10} ${CX} ${CY}`}
            fill="none" stroke="#dc2626" strokeWidth="1.2" strokeOpacity="0.1"
            strokeDasharray="3 14"
            style={{ animation: 'bg-stream 7s linear infinite' }}
          />
          <path
            d={`M ${CX} ${CY} Q ${CX + CX * 0.6} ${CY - 15} ${W - 5} ${CY - 20}`}
            fill="none" stroke="#2563eb" strokeWidth="1.5" strokeOpacity="0.14"
            strokeDasharray="2 10"
            style={{ animation: 'bg-stream 5s linear infinite' }}
          />
          <path
            d={`M ${CX} ${CY} Q ${CX + CX * 0.6} ${CY + 15} ${W - 5} ${CY + 20}`}
            fill="none" stroke="#2563eb" strokeWidth="1.2" strokeOpacity="0.1"
            strokeDasharray="3 12"
            style={{ animation: 'bg-stream 6.5s linear infinite' }}
          />

          {/* Konzentrische Energieringe mit Glow */}
          {[80, 130, 190, 260].map((r, i) => (
            <g key={`ring-${i}`}>
              <circle
                cx={CX} cy={CY} r={r}
                fill="none"
                stroke="#10b981"
                strokeWidth={3 - i * 0.3}
                strokeOpacity={0.08}
                strokeDasharray="6 12"
                filter="url(#ef-ring-glow)"
                style={{ animation: `pulse-ring ${4 + i * 1.5}s ease-in-out infinite` }}
              />
              <circle
                cx={CX} cy={CY} r={r}
                fill="none"
                stroke="#10b981"
                strokeWidth={1 - i * 0.1}
                strokeOpacity={0.22 - i * 0.03}
                strokeDasharray="4 8"
                style={{ animation: `pulse-ring ${4 + i * 1.5}s ease-in-out infinite` }}
              />
            </g>
          ))}

          {/* Hintergrund-Partikel */}
          {[0, 1, 2, 3, 4].map(i => (
            <circle key={`p-pv-${i}`} fill="#ca8a04" r="1.5">
              <animateMotion
                dur={`${3 + i * 0.8}s`}
                repeatCount="indefinite"
                begin={`${i * 0.7}s`}
                path={`M ${CX - 60 + i * 30} 15 Q ${CX - 20 + i * 10} ${CY * 0.45} ${CX} ${CY}`}
              />
              <animate attributeName="opacity" values="0;0.7;0.4;0" dur={`${3 + i * 0.8}s`} repeatCount="indefinite" begin={`${i * 0.7}s`} />
              <animate attributeName="r" values="1;2;0.6" dur={`${3 + i * 0.8}s`} repeatCount="indefinite" begin={`${i * 0.7}s`} />
            </circle>
          ))}
          {[0, 1, 2, 3].map(i => (
            <circle key={`p-vb-${i}`} fill="#059669" r="1.3">
              <animateMotion
                dur={`${3.5 + i * 0.9}s`}
                repeatCount="indefinite"
                begin={`${i * 1.0}s`}
                path={`M ${CX} ${CY} Q ${CX + (-1) ** i * 40} ${CY + 50} ${CX + (-1) ** i * (60 + i * 20)} ${svgH - 15}`}
              />
              <animate attributeName="opacity" values="0;0.65;0.35;0" dur={`${3.5 + i * 0.9}s`} repeatCount="indefinite" begin={`${i * 1.0}s`} />
              <animate attributeName="r" values="0.8;1.8;0.5" dur={`${3.5 + i * 0.9}s`} repeatCount="indefinite" begin={`${i * 1.0}s`} />
            </circle>
          ))}
          {[0, 1].map(i => (
            <circle key={`p-nz-${i}`} fill="#dc2626" r="1.2">
              <animateMotion
                dur={`${5 + i * 1.5}s`}
                repeatCount="indefinite"
                begin={`${i * 2.5}s`}
                path={`M 8 ${CY + (-1) ** i * 25} Q ${CX * 0.4} ${CY + (-1) ** i * 8} ${CX} ${CY}`}
              />
              <animate attributeName="opacity" values="0;0.6;0.3;0" dur={`${5 + i * 1.5}s`} repeatCount="indefinite" begin={`${i * 2.5}s`} />
            </circle>
          ))}
          {[0, 1].map(i => (
            <circle key={`p-sp-${i}`} fill="#2563eb" r="1.2">
              <animateMotion
                dur={`${4.5 + i * 1.5}s`}
                repeatCount="indefinite"
                begin={`${i * 2.0}s`}
                path={`M ${CX} ${CY} Q ${CX + CX * 0.55} ${CY + (-1) ** i * 12} ${W - 8} ${CY + (-1) ** i * 18}`}
              />
              <animate attributeName="opacity" values="0;0.6;0.3;0" dur={`${4.5 + i * 1.5}s`} repeatCount="indefinite" begin={`${i * 2.0}s`} />
            </circle>
          ))}
          </>)}

          {/* ─── Sunset-Animationen — nur im Effekt-Modus ─── */}
          {!lite && bgVariant === 'sunset' && (<>
            {/* Sonnenstrahlen von oben → Horizont */}
            <path d={`M ${CX - 80} 10 Q ${CX - 40} ${CY * 0.5} ${CX} ${CY}`}
              fill="none" stroke="#ffa500" strokeWidth="2" strokeOpacity="0.22" strokeDasharray="3 12"
              style={{ animation: 'sunset-stream 4s linear infinite' }} />
            <path d={`M ${CX + 80} 10 Q ${CX + 40} ${CY * 0.5} ${CX} ${CY}`}
              fill="none" stroke="#ffa500" strokeWidth="1.5" strokeOpacity="0.18" strokeDasharray="2 10"
              style={{ animation: 'sunset-stream 5s linear infinite' }} />
            <path d={`M ${CX} 5 Q ${CX + 15} ${CY * 0.5} ${CX} ${CY}`}
              fill="none" stroke="#ffd700" strokeWidth="1.8" strokeOpacity="0.20" strokeDasharray="4 14"
              style={{ animation: 'sunset-stream 3.5s linear infinite' }} />
            <path d={`M ${CX - 160} 5 Q ${CX - 80} ${CY * 0.3} ${CX} ${CY}`}
              fill="none" stroke="#ec4899" strokeWidth="1.2" strokeOpacity="0.14" strokeDasharray="2 10"
              style={{ animation: 'sunset-stream 6s linear infinite' }} />
            <path d={`M ${CX + 160} 5 Q ${CX + 80} ${CY * 0.3} ${CX} ${CY}`}
              fill="none" stroke="#ec4899" strokeWidth="1.2" strokeOpacity="0.12" strokeDasharray="3 12"
              style={{ animation: 'sunset-stream 7s linear infinite' }} />
            {/* Seitliche Lichtstreifen vom Horizont */}
            <path d={`M 5 ${CY - 20} Q ${CX * 0.4} ${CY - 8} ${CX} ${CY}`}
              fill="none" stroke="#ff6b35" strokeWidth="1.5" strokeOpacity="0.16" strokeDasharray="2 10"
              style={{ animation: 'sunset-stream 6s linear infinite' }} />
            <path d={`M ${W - 5} ${CY - 20} Q ${CX + CX * 0.6} ${CY - 8} ${CX} ${CY}`}
              fill="none" stroke="#ff6b35" strokeWidth="1.5" strokeOpacity="0.16" strokeDasharray="2 10"
              style={{ animation: 'sunset-stream 5.5s linear infinite' }} />
            {/* Wasserreflektionen — horizontale Shimmer-Bögen unter CY */}
            <path d={`M ${CX - 120} ${CY + 30} Q ${CX} ${CY + 25} ${CX + 120} ${CY + 30}`}
              fill="none" stroke="#ffa500" strokeWidth="1.5" strokeOpacity="0.22" strokeDasharray="8 20"
              style={{ animation: 'shimmer 3s ease-in-out infinite' }} />
            <path d={`M ${CX - 100} ${CY + 55} Q ${CX} ${CY + 50} ${CX + 100} ${CY + 55}`}
              fill="none" stroke="#ff8c00" strokeWidth="1.2" strokeOpacity="0.17" strokeDasharray="6 18"
              style={{ animation: 'shimmer 4s ease-in-out infinite 0.5s' }} />
            <path d={`M ${CX - 80} ${CY + 80} Q ${CX} ${CY + 75} ${CX + 80} ${CY + 80}`}
              fill="none" stroke="#ffa500" strokeWidth="1" strokeOpacity="0.14" strokeDasharray="5 16"
              style={{ animation: 'shimmer 3.5s ease-in-out infinite 1s' }} />
            <path d={`M ${CX - 160} ${CY + 115} Q ${CX} ${CY + 108} ${CX + 160} ${CY + 115}`}
              fill="none" stroke="#c47310" strokeWidth="0.8" strokeOpacity="0.12" strokeDasharray="4 14"
              style={{ animation: 'shimmer 5s ease-in-out infinite 1.5s' }} />
            <path d={`M 20 ${CY + 155} Q ${CX} ${CY + 145} ${W - 20} ${CY + 155}`}
              fill="none" stroke="#c47310" strokeWidth="0.7" strokeOpacity="0.10" strokeDasharray="3 12"
              style={{ animation: 'shimmer 6s ease-in-out infinite 2s' }} />

            {/* Sonnen-Halo Ringe (orange/gold statt emerald) */}
            {[80, 130, 190, 260].map((r, i) => (
              <g key={`ring-sunset-${i}`}>
                <circle cx={CX} cy={CY} r={r} fill="none"
                  stroke="#ff8c00" strokeWidth={3 - i * 0.3} strokeOpacity={0.08}
                  strokeDasharray="6 12" filter="url(#ef-ring-glow)"
                  style={{ animation: `pulse-ring-sunset ${5 + i * 1.5}s ease-in-out infinite` }} />
                <circle cx={CX} cy={CY} r={r} fill="none"
                  stroke={i < 2 ? '#ffd700' : '#ff6b00'}
                  strokeWidth={1 - i * 0.1} strokeOpacity={0.20 - i * 0.025}
                  strokeDasharray="4 8"
                  style={{ animation: `pulse-ring-sunset ${5 + i * 1.5}s ease-in-out infinite` }} />
              </g>
            ))}

            {/* Sonnen-Partikel (golden, von oben → Horizont) */}
            {[0, 1, 2, 3, 4].map(i => (
              <circle key={`p-sun-${i}`} fill="#ffd700" r="1.5">
                <animateMotion dur={`${3 + i * 0.8}s`} repeatCount="indefinite" begin={`${i * 0.7}s`}
                  path={`M ${CX - 60 + i * 30} 15 Q ${CX - 20 + i * 10} ${CY * 0.45} ${CX} ${CY}`} />
                <animate attributeName="opacity" values="0;0.75;0.45;0" dur={`${3 + i * 0.8}s`} repeatCount="indefinite" begin={`${i * 0.7}s`} />
                <animate attributeName="r" values="1;2.2;0.6" dur={`${3 + i * 0.8}s`} repeatCount="indefinite" begin={`${i * 0.7}s`} />
              </circle>
            ))}
            {/* Wasser-Reflexionspartikel (orange, schimmern auf dem Meer) */}
            {[0, 1, 2, 3].map(i => (
              <circle key={`p-reflect-${i}`} fill="#ff8c00" r="1.2">
                <animateMotion dur={`${4 + i * 1.2}s`} repeatCount="indefinite" begin={`${i * 1.1}s`}
                  path={`M ${CX + (-1) ** i * 80} ${CY + 20 + i * 25} Q ${CX + (-1) ** i * 30} ${CY + 30 + i * 20} ${CX} ${CY + 10}`} />
                <animate attributeName="opacity" values="0;0.62;0.30;0" dur={`${4 + i * 1.2}s`} repeatCount="indefinite" begin={`${i * 1.1}s`} />
                <animate attributeName="r" values="0.8;1.8;0.5" dur={`${4 + i * 1.2}s`} repeatCount="indefinite" begin={`${i * 1.1}s`} />
              </circle>
            ))}
            {/* Pink/Magenta Sky-Partikel (von oben-seitlich → Horizont) */}
            {[0, 1].map(i => (
              <circle key={`p-sky-${i}`} fill="#ec4899" r="1.2">
                <animateMotion dur={`${5.5 + i * 1.5}s`} repeatCount="indefinite" begin={`${i * 2.0}s`}
                  path={`M ${i === 0 ? CX - 140 : CX + 140} 8 Q ${CX + (i === 0 ? -60 : 60)} ${CY * 0.4} ${CX} ${CY}`} />
                <animate attributeName="opacity" values="0;0.55;0.25;0" dur={`${5.5 + i * 1.5}s`} repeatCount="indefinite" begin={`${i * 2.0}s`} />
              </circle>
            ))}
          </>)}

          {/* ─── Alps-Animationen — nur im Effekt-Modus ─── */}
          {!lite && bgVariant === 'alps' && (<>
            {/* Wolkenwisps (leichter Drift über den Bergkamm) */}
            {[0, 1, 2].map(i => {
              const cy2 = CY * (0.18 + i * 0.18)
              const x0  = -W * 0.15 + i * W * 0.12
              return (
                <g key={`cloud-${i}`} style={{ animation: `cloud-drift ${18 + i * 6}s linear infinite ${i * 4}s` }} clipPath="url(#ef-alps-sky-clip)">
                  <ellipse cx={x0 + W * 0.1} cy={cy2} rx={W * (0.08 + i * 0.04)} ry={CY * 0.04}
                    fill="#ffffff" fillOpacity={0.12 + i * 0.04} />
                  <ellipse cx={x0 + W * 0.14} cy={cy2 - 4} rx={W * (0.05 + i * 0.02)} ry={CY * 0.03}
                    fill="#ffffff" fillOpacity={0.09 + i * 0.03} />
                </g>
              )
            })}
            {/* Schneefunkeln auf den Gipfeln (Light + Dark je eigene Farbe) */}
            {([[0.27,128],[0.68,140],[0.47,118],[0.88,110]] as [number,number][]).map(([xf, h], i) => {
              const px = xf * W, py = CY - h
              return (
                <g key={`snowsp-${i}`}>
                  <circle cx={px} cy={py} r="1.8" className="opacity-100 dark:opacity-0" fill="#d8eeff"
                    style={{ animation: `snow-sparkle ${2.5 + i * 0.9}s ease-in-out infinite ${i * 0.7}s` }} />
                  <circle cx={px} cy={py} r="1.8" className="opacity-0 dark:opacity-100" fill="#c8d8c0"
                    style={{ animation: `snow-sparkle ${2.5 + i * 0.9}s ease-in-out infinite ${i * 0.7}s` }} />
                  <circle cx={px - 6} cy={py + 4} r="1.2" className="opacity-100 dark:opacity-0" fill="#e8f4ff"
                    style={{ animation: `snow-sparkle ${3 + i * 0.7}s ease-in-out infinite ${i * 1.1 + 0.4}s` }} />
                  <circle cx={px + 5} cy={py + 3} r="1.0" className="opacity-100 dark:opacity-0" fill="#e8f4ff"
                    style={{ animation: `snow-sparkle ${3.5 + i * 0.6}s ease-in-out infinite ${i * 0.9 + 0.8}s` }} />
                </g>
              )
            })}
            {/* Sterne animiert (Dark only) */}
            {Array.from({ length: 12 }, (_, i) => {
              const sx = W * 0.05 + (i * W * 0.077) % (W * 0.88)
              const sy = CY * 0.06 + ((i * 53 + 7) % 100) / 100 * CY * 0.70
              return (
                <circle key={`astar-${i}`} cx={sx} cy={sy} r={i % 3 === 0 ? 1.2 : 0.7}
                  fill="#c8dcf0" className="opacity-0 dark:opacity-100"
                  style={{ animation: `star-twinkle ${2 + i * 0.4}s ease-in-out infinite ${i * 0.3}s` }}
                  clipPath="url(#ef-alps-sky-clip)" />
              )
            })}
          </>)}

          {/* Dezente Achsenlinien (Kreuz durch Zentrum) */}
          {bgVariant !== 'sunset' && bgVariant !== 'alps' && <>
            <line x1={CX} y1={12} x2={CX} y2={svgH - 12} stroke="#9ca3af" strokeWidth="0.5" strokeOpacity={0.15} strokeDasharray="2 6" />
            <line x1={12} y1={CY} x2={W - 12} y2={CY} stroke="#9ca3af" strokeWidth="0.5" strokeOpacity={0.15} strokeDasharray="2 6" />
          </>}
          {bgVariant === 'sunset' && <>
            <line x1={CX} y1={12} x2={CX} y2={svgH - 12} stroke="#ff8c00" strokeWidth="0.5" strokeOpacity={0.18} strokeDasharray="2 6" />
            <line x1={12} y1={CY} x2={W - 12} y2={CY} stroke="#ffd700" strokeWidth="0.8" strokeOpacity={0.24} strokeDasharray="4 4" />
          </>}
          {bgVariant === 'alps' && <>
            <line x1={CX} y1={12} x2={CX} y2={svgH - 12} stroke="#7aaad0" strokeWidth="0.5" strokeOpacity={0.20} strokeDasharray="2 6" />
            <line x1={12} y1={CY} x2={W - 12} y2={CY} stroke="#88b8d8" strokeWidth="0.6" strokeOpacity={0.18} strokeDasharray="3 5" />
          </>}

          {/* Tiefe-Vignette (dunkelt Ränder ab → 3D-Einbuchtung) — nur im Effekt-Modus */}
          {!lite && bgVariant === 'default' && (
            <>
              <rect width={W} height={svgH} className="opacity-100 dark:opacity-0" fill="url(#ef-vignette-light)" rx="8" />
              <rect width={W} height={svgH} className="opacity-0 dark:opacity-100" fill="url(#ef-vignette-dark)" rx="8" />
            </>
          )}
          {!lite && bgVariant === 'sunset' && <>
            <rect width={W} height={svgH} fill="url(#ef-vignette-sunset-light)" rx="8" className="opacity-100 dark:opacity-0" />
            <rect width={W} height={svgH} fill="url(#ef-vignette-sunset-dark)"  rx="8" className="opacity-0 dark:opacity-100" />
          </>}
          {!lite && bgVariant === 'alps' && <>
            <rect width={W} height={svgH} fill="url(#ef-vignette-alps-light)" rx="8" className="opacity-100 dark:opacity-0" />
            <rect width={W} height={svgH} fill="url(#ef-vignette-alps-dark)"  rx="8" className="opacity-0 dark:opacity-100" />
          </>}
        </g>
    </>
  )
}
