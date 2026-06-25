/**
 * Generic markdown doc viewer — fetches /api/docs/{name} and renders the
 * result with react-markdown + remark-gfm. Used by:
 *
 * - The top-level Changelog and Roadmap tabs
 * - The "How it works" panels embedded inline on the Topics dashboard
 *   and the Forecast Tracker view
 *
 * Tailwind classes mirror the prose styling used in IntelligenceBrief
 * so docs read consistently with the rest of the app.
 */

import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Loader2, AlertTriangle, BookOpen } from 'lucide-react';

interface DocViewerProps {
  /** Name segment passed to /api/docs/{name}. */
  name: string;
  /** Optional title rendered above the content. */
  title?: string;
  /** When true, render in a compact embedded panel (for inline use on
   *  other screens) instead of a full-page layout. */
  embedded?: boolean;
}

interface DocResponse {
  name: string;
  path: string;
  content: string;
}

export function DocViewer({ name, title, embedded = false }: DocViewerProps) {
  const [doc, setDoc] = useState<DocResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const r = await fetch(`/api/docs/${encodeURIComponent(name)}`);
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        const data = (await r.json()) as DocResponse;
        if (!cancelled) setDoc(data);
      } catch (e: any) {
        if (!cancelled) setError(e?.message || 'Failed to load doc');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [name]);

  const inner = (() => {
    if (loading) {
      return (
        <div className="flex items-center text-xs text-gray-600 dark:text-gray-300">
          <Loader2 className="w-3 h-3 mr-2 animate-spin" /> Loading documentation…
        </div>
      );
    }
    if (error) {
      return (
        <div className="text-xs px-3 py-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-900 dark:text-red-100 rounded inline-flex items-center gap-2">
          <AlertTriangle className="w-3 h-3" /> {error}
        </div>
      );
    }
    if (!doc) return null;
    return (
      <article
        // Tailwind Typography auto-decorates inline code with literal
        // backticks via ::before/::after and applies a default styling
        // that conflicts with our component overrides. ``prose-code:before:content-none``
        // and ``prose-code:after:content-none`` strip those quotes; we
        // do our own styling in the components map below.
        className="prose prose-sm dark:prose-invert max-w-none prose-code:before:content-none prose-code:after:content-none"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {doc.content}
        </ReactMarkdown>
      </article>
    );
  })();

  if (embedded) {
    return (
      <div className="rounded border border-blue-200 dark:border-blue-800 bg-blue-50/40 dark:bg-blue-900/20 p-3">
        {title && (
          <h3 className="text-xs font-semibold text-blue-900 dark:text-blue-100 mb-2 inline-flex items-center gap-1">
            <BookOpen className="w-3 h-3" /> {title}
          </h3>
        )}
        {inner}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {title && (
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 inline-flex items-center gap-2">
          <BookOpen className="w-4 h-4" /> {title}
        </h2>
      )}
      <div className="max-w-4xl">{inner}</div>
    </div>
  );
}

// Minimal styling overrides so the docs match the rest of the app —
// keep headings tight, render code with monospace, etc.
const markdownComponents = {
  h1: ({ children }: any) => (
    <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-0 mb-3">
      {children}
    </h1>
  ),
  h2: ({ children }: any) => (
    <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mt-4 mb-2">
      {children}
    </h2>
  ),
  h3: ({ children }: any) => (
    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mt-3 mb-1">
      {children}
    </h3>
  ),
  p: ({ children }: any) => (
    <p className="text-xs text-gray-700 dark:text-gray-200 my-2 leading-relaxed">
      {children}
    </p>
  ),
  ul: ({ children }: any) => (
    <ul className="list-disc ml-5 my-2 space-y-1 text-xs text-gray-700 dark:text-gray-200">
      {children}
    </ul>
  ),
  ol: ({ children }: any) => (
    <ol className="list-decimal ml-5 my-2 space-y-1 text-xs text-gray-700 dark:text-gray-200">
      {children}
    </ol>
  ),
  li: ({ children }: any) => <li className="leading-relaxed">{children}</li>,
  // react-markdown ≥9 dropped the `inline` prop. Markdown inline code never
  // carries a className; fenced blocks get className="language-…". So we
  // detect inline-vs-block via the className, not the absent `inline` flag.
  code: ({ className, children, ...props }: any) => {
    const isFenced = /^language-/.test(className || '');
    if (isFenced) {
      return (
        <code className="font-mono text-[11px]" {...props}>
          {children}
        </code>
      );
    }
    return (
      <code className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded font-mono text-[11px]" {...props}>
        {children}
      </code>
    );
  },
  // ``pre`` wraps fenced code blocks — give it the block styling so the
  // inline ``code`` overrides above don't accidentally pick up block CSS.
  pre: ({ children }: any) => (
    <pre className="my-2 p-2 bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded overflow-x-auto">
      {children}
    </pre>
  ),
  a: ({ children, href }: any) => (
    <a href={href} target="_blank" rel="noreferrer"
       className="text-blue-700 dark:text-blue-300 hover:underline">
      {children}
    </a>
  ),
  blockquote: ({ children }: any) => (
    <blockquote className="border-l-2 border-gray-300 dark:border-gray-600 pl-3 my-2 text-xs italic text-gray-600 dark:text-gray-300">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-gray-200 dark:border-gray-700" />,
  table: ({ children }: any) => (
    <div className="overflow-x-auto my-2">
      <table className="text-xs border-collapse">{children}</table>
    </div>
  ),
  th: ({ children }: any) => (
    <th className="border border-gray-300 dark:border-gray-700 px-2 py-1 bg-gray-50 dark:bg-gray-800 text-left font-medium">
      {children}
    </th>
  ),
  td: ({ children }: any) => (
    <td className="border border-gray-300 dark:border-gray-700 px-2 py-1 align-top">
      {children}
    </td>
  ),
};
