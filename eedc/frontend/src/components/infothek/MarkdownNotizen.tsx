/**
 * Markdown-Notizen-Editor mit minimaler Toolbar.
 *
 * Unterstützt: Bold, Italic, Liste, Link.
 * Toggle zwischen Bearbeiten und Vorschau.
 */

import { useState, useRef, useCallback } from 'react'
import { Bold, Italic, List, Link, Eye, Edit3 } from 'lucide-react'
import Markdown from 'react-markdown'

interface MarkdownNotizenProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  rows?: number
}

export default function MarkdownNotizen({
  value,
  onChange,
  placeholder = 'Notizen (Markdown unterstützt)...',
  rows = 4,
}: MarkdownNotizenProps) {
  const [preview, setPreview] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const wrapSelection = useCallback((before: string, after: string) => {
    const ta = textareaRef.current
    if (!ta) return

    const start = ta.selectionStart
    const end = ta.selectionEnd
    const text = ta.value
    const selected = text.substring(start, end)

    const newText = text.substring(0, start) + before + selected + after + text.substring(end)
    onChange(newText)

    // Cursor nach dem eingefügten Text setzen
    requestAnimationFrame(() => {
      ta.focus()
      ta.selectionStart = start + before.length
      ta.selectionEnd = end + before.length
    })
  }, [onChange])

  const insertAtCursor = useCallback((text: string) => {
    const ta = textareaRef.current
    if (!ta) return

    const start = ta.selectionStart
    const current = ta.value
    const newText = current.substring(0, start) + text + current.substring(start)
    onChange(newText)

    requestAnimationFrame(() => {
      ta.focus()
      ta.selectionStart = ta.selectionEnd = start + text.length
    })
  }, [onChange])

  const toolbarButtons = [
    { icon: Bold, title: 'Fett (Ctrl+B)', action: () => wrapSelection('**', '**') },
    { icon: Italic, title: 'Kursiv (Ctrl+I)', action: () => wrapSelection('*', '*') },
    { icon: List, title: 'Liste', action: () => insertAtCursor('\n- ') },
    { icon: Link, title: 'Link', action: () => wrapSelection('[', '](url)') },
  ]

  return (
    <div className="border border-gray-300 dark:border-gray-600 rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-primary-500 focus-within:border-primary-500">
      {/* Toolbar */}
      <div className="flex items-center gap-1 px-2 py-1.5 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        {toolbarButtons.map(({ icon: Icon, title, action }) => (
          <button
            key={title}
            type="button"
            onClick={action}
            className="p-1.5 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors"
            title={title}
          >
            <Icon className="h-3.5 w-3.5" />
          </button>
        ))}
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => setPreview(!preview)}
          className={`p-1.5 rounded transition-colors ${
            preview
              ? 'text-primary-600 bg-primary-50 dark:bg-primary-900/30'
              : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
          }`}
          title={preview ? 'Bearbeiten' : 'Vorschau'}
        >
          {preview ? <Edit3 className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* Editor oder Vorschau */}
      {preview ? (
        <div className="px-3 py-2 min-h-[6rem] prose prose-sm dark:prose-invert max-w-none">
          {value ? (
            <Markdown>{value}</Markdown>
          ) : (
            <p className="text-gray-400 italic">Keine Notizen</p>
          )}
        </div>
      ) : (
        <textarea
          ref={textareaRef}
          value={value}
          onChange={e => onChange(e.target.value)}
          className="w-full px-3 py-2 bg-transparent text-sm text-gray-900 dark:text-white focus:outline-none resize-y"
          rows={rows}
          placeholder={placeholder}
        />
      )}
    </div>
  )
}
