/**
 * Der Lösungsweg eines Codes aus dem Handbuch «Daten-Checker» (Etappe E5, Konzept §3.5): der Abschnitt, dessen
 * Überschrift den Anker `<a name="<code>"></a>` trägt, bis zur nächsten Überschrift gleicher oder höherer Ebene. Das
 * Handbuch §4 erzeugt `scripts/daten-checker-handbuch.py` aus `docs/daten-checker/<code>.md` — eine Quelle, das Panel
 * schneidet nur aus. ``null``, wenn der Anker fehlt (der Aufrufer zeigt dann das Kapitel).
 */
export function abschnittFuerCode(markdown: string, code: string | null | undefined): string | null {
  if (!code) return null
  const zeilen = markdown.split('\n')
  const start = zeilen.findIndex((z) => /^#{2,6} /.test(z) && z.includes(`<a name="${code}"></a>`))
  if (start < 0) return null
  const ebene = zeilen[start].match(/^#+/)![0].length
  let ende = zeilen.length
  for (let i = start + 1; i < zeilen.length; i++) {
    const m = zeilen[i].match(/^(#{1,6}) /)
    if (m && m[1].length <= ebene) { ende = i; break }
  }
  return zeilen.slice(start, ende).join('\n').trim()
}
