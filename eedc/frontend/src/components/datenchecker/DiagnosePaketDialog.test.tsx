/**
 * Diagnose-Paket-Dialog (E1, Konzept Daten-Checker §8.3): der Text erscheint bearbeitbar, «Kopieren» kopiert den
 * (geschwärzten) Text über `useCopyFeedback`, «Als Datei herunterladen» holt die Datei-Fassung über `downloadFile`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DiagnosePaketDialog, { DIAGNOSE_HINWEIS } from './DiagnosePaketDialog'

const kopiere = vi.fn()
vi.mock('../../hooks/useCopyFeedback', () => ({
  useCopyFeedback: () => ({ kopiert: null, istKopiert: () => false, kopiere }),
}))
// `downloadFile` wird ersetzt: die echte Fassung klickt einen `<a download>` (jsdom kennt keine Navigation).
const download = vi.fn().mockResolvedValue(undefined)
vi.mock('../../lib/download', () => ({ downloadFile: (...a: unknown[]) => download(...a) }))
const paket = vi.fn()
vi.mock('../../api/datenChecker', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/datenChecker')>()),
  datenCheckerApi: { diagnosePaket: (...a: unknown[]) => paket(...a) },
}))

describe('DiagnosePaketDialog', () => {
  beforeEach(() => {
    kopiere.mockClear()
    download.mockClear()
    paket.mockReset().mockResolvedValue({ text: '<!-- eedc-diagnose v1 -->\n# Paket', dateiname: 'eedc_diagnose_Haus_2026-11-10.md' })
  })

  it('zeigt die Kopieren-Fassung bearbeitbar mit dem Hinweis', async () => {
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    const feld = await screen.findByRole('textbox')
    expect((feld as HTMLTextAreaElement).value).toContain('<!-- eedc-diagnose v1 -->')
    expect(paket).toHaveBeenCalledWith(7, 'kopie')
    expect(screen.getByText(DIAGNOSE_HINWEIS)).toBeTruthy()
  })

  it('«Kopieren» kopiert den bearbeiteten Text', async () => {
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    const feld = await screen.findByRole('textbox')
    fireEvent.change(feld, { target: { value: 'geschwärzt' } })
    fireEvent.click(screen.getByRole('button', { name: /Kopieren/ }))
    expect(kopiere).toHaveBeenCalledWith('geschwärzt')
  })

  it('«Als Datei herunterladen» holt die ungekürzte Datei-Fassung', async () => {
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    await screen.findByRole('textbox')
    fireEvent.click(screen.getByRole('button', { name: /Als Datei herunterladen/ }))
    await waitFor(() => expect(download).toHaveBeenCalledWith(
      './api/system/diagnose-paket/7?fassung=datei', 'eedc_diagnose_Haus_2026-11-10.md'))
  })

  it('lädt nichts, solange der Dialog zu ist', () => {
    render(<DiagnosePaketDialog isOpen={false} onClose={() => {}} anlageId={7} />)
    expect(paket).not.toHaveBeenCalled()
  })
})
