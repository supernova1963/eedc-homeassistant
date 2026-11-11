/**
 * MarkdownDoc — Inline-Code bleibt in der Zeile (11.11.2026).
 *
 * react-markdown ≥ 9 reicht kein `inline` mehr an die `code`-Komponente durch; die frühere Weiche setzte deshalb
 * jeden Inline-Code mit `className="block"` als eigenen Absatz (Lesehinweis `?doc=was-ist-neu` in «Was ist neu»,
 * Lösungswege des Daten-Checkers, Handbücher). Diese Probe hält beide Formen fest.
 */
import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import MarkdownDoc from './MarkdownDoc'

const MD = 'Lies `?doc=was-ist-neu` im Browser.\n\n```\nzeile eins\nzeile zwei\n```\n'

describe('MarkdownDoc: Inline-Code und Code-Block', () => {
  it('Inline-Code steht im Absatz und ist kein Block', () => {
    const { container } = render(<MarkdownDoc markdown={MD} />)
    const inline = [...container.querySelectorAll('code')].find((c) => c.textContent === '?doc=was-ist-neu')
    expect(inline).toBeTruthy()
    expect(inline!.parentElement?.tagName).toBe('P')
    expect(inline!.className.split(/\s+/)).not.toContain('block')
    expect(inline!.parentElement?.textContent).toBe('Lies ?doc=was-ist-neu im Browser.')
  })

  it('ein Code-Block steht in `pre`, das sein `code`-Kind als Block setzt', () => {
    const { container } = render(<MarkdownDoc markdown={MD} />)
    const pre = container.querySelector('pre')
    expect(pre?.querySelector(':scope > code')?.textContent).toBe('zeile eins\nzeile zwei\n')
    expect(pre!.className).toContain('[&>code]:block')
  })
})
