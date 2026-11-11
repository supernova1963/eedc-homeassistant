/**
 * MarkdownDoc — SoT-Renderer für Hilfe-/Dokumentations-Markdown (D2, 2026-07-18).
 *
 * Aus `pages/Hilfe.tsx` extrahiert (EINE Code-Wahrheit, Regel 0): dieselbe
 * Typografie/Tabellen-/Code-Darstellung für die Hilfe-Seite, das Setup-Wizard-
 * Kontext-Hilfe-Overlay (D2) und später HilfeV4 (R2b). GFM + rehype-slug
 * (Anker-IDs) + rehype-raw (Roh-HTML-Anker in den Handbüchern).
 *
 * Link-Verhalten ist HOST-Sache: `linkComponent` bekommt (href, children, name)
 * und darf ein eigenes Element liefern (Hilfe: `?doc=`-Rewrite + Hash-Scroll);
 * `null`/undefined → Default (reine Anker-Marker als id, sonst externer Link).
 */
import type { ReactNode } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSlug from 'rehype-slug'
import { ExternalLink } from 'lucide-react'

export interface MarkdownDocProps {
  markdown: string
  linkComponent?: (href: string | undefined, children: ReactNode, name?: string) => ReactNode | null
}

export default function MarkdownDoc({ markdown, linkComponent }: MarkdownDocProps) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw, rehypeSlug]}
      components={{
        h1: ({ children, id }) => (
          <h1 id={id} className="text-2xl font-bold text-gray-900 dark:text-white mt-2 mb-4 pb-2 border-b border-gray-200 dark:border-gray-700">
            {children}
          </h1>
        ),
        h2: ({ children, id }) => (
          <h2 id={id} className="text-xl font-bold text-gray-900 dark:text-white mt-8 mb-3">{children}</h2>
        ),
        h3: ({ children, id }) => (
          <h3 id={id} className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-2">{children}</h3>
        ),
        h4: ({ children, id }) => (
          <h4 id={id} className="text-base font-semibold text-gray-900 dark:text-white mt-4 mb-2">{children}</h4>
        ),
        p: ({ children }) => <p className="my-3 leading-relaxed">{children}</p>,
        ul: ({ children }) => <ul className="list-disc pl-6 my-3 space-y-1 leading-relaxed">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-6 my-3 space-y-1 leading-relaxed">{children}</ol>,
        blockquote: ({ children }) => (
          <blockquote className="border-l-4 border-primary-500 dark:border-primary-400 pl-4 my-4 text-gray-600 dark:text-gray-400 italic">
            {children}
          </blockquote>
        ),
        // react-markdown ≥ 9 reicht kein `inline` mehr durch — die frühere Weiche `inline ? … : <code className="block">`
        // setzte deshalb JEDEN Inline-Code als eigenen Block (Lesehinweis «Was ist neu», Lösungswege, Handbücher;
        // gesehen 11.11.2026). Jetzt: `code` ist immer die Inline-Form, ein Code-Block steckt in `pre`, das sein
        // `code`-Kind zurücksetzt.
        code: ({ children, className }) => (
          <code className={`px-1 py-0.5 bg-gray-100 dark:bg-gray-700 text-sm rounded font-mono text-primary-700 dark:text-primary-300 ${className ?? ''}`}>
            {children}
          </code>
        ),
        pre: ({ children }) => (
          <pre className="my-4 p-3 bg-gray-100 dark:bg-gray-900 rounded overflow-x-auto text-sm font-mono text-gray-800 dark:text-gray-200 [&>code]:block [&>code]:p-0 [&>code]:bg-transparent dark:[&>code]:bg-transparent [&>code]:text-inherit dark:[&>code]:text-inherit [&>code]:rounded-none">
            {children}
          </pre>
        ),
        table: ({ children }) => (
          <div className="my-4 overflow-x-auto">
            <table className="min-w-full text-sm border-collapse">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-gray-50 dark:bg-gray-700/50">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-3 py-2 text-left font-semibold text-gray-900 dark:text-white border border-gray-200 dark:border-gray-700">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-2 align-top border border-gray-200 dark:border-gray-700">
            {children}
          </td>
        ),
        hr: () => <hr className="my-6 border-gray-200 dark:border-gray-700" />,
        a: ({ href, children, ...rest }) => {
          const name = (rest as { name?: string }).name
          const eigen = linkComponent?.(href, children, name)
          if (eigen != null) return eigen as React.ReactElement
          // Reine Anker-Targets aus Roh-HTML (z. B. <a name="…"></a>) als ID-Marker.
          if (!href && name) return <a id={name} />
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 dark:text-primary-400 hover:underline inline-flex items-center gap-0.5"
            >
              {children}
              <ExternalLink className="w-3 h-3 inline" />
            </a>
          )
        },
      }}
    >
      {markdown}
    </Markdown>
  )
}
