import { createContext, useContext } from 'react';
import { Citation } from '@aunoo/ui';
import type { Reference } from '../lib/model';

/** The current analysis's numbered sources, so any text can turn "[n]" into a citation link. */
export const RefsContext = createContext<Reference[]>([]);

/**
 * Renders "…text [3]…" and "[3], [5]" / "[3][5]" with each number as a Citation chip linked to
 * its source. React escapes the text (the old page injected it as raw HTML).
 */
export function CitedText({ text }: { text: string | undefined }) {
  const refs = useContext(RefsContext);
  if (!text) return null;
  const parts = text.split(/(\[\d+\])/g);
  return (
    <>
      {parts.map((part, i) => {
        const match = /^\[(\d+)\]$/.exec(part);
        if (!match) return part;
        const n = Number(match[1]);
        const ref = refs.find((r) => r.n === n);
        return <Citation key={i} n={n} href={ref?.url} title={ref ? `${ref.title}${ref.source ? ` — ${ref.source}` : ''}` : undefined} />;
      })}
    </>
  );
}

/** Text without its citation markers, for labels and screen-reader names. */
export const stripCitations = (text: string) => text.replace(/\s*\[\d+\](,\s*)?/g, '').trim();
