/**
 * Normalise raw social post bodies for display.
 * Reddit/bot posts (e.g. Wiseek) arrive with JSON-escaped newlines ("\\n"),
 * double-encoded HTML entities ("&amp;"), and mojibake replacement chars — plus
 * markdown syntax. This decodes them to real text so the UI/reports don't show raw
 * escape sequences. Markdown rendering (or stripping) is applied by the caller.
 */
export function cleanSocialText(s: string): string {
  let t = s || '';
  // JSON-escaped sequences that were never parsed
  t = t.replace(/\\r\\n|\\n|\\r/g, '\n').replace(/\\t/g, ' ').replace(/\\"/g, '"').replace(/\\'/g, "'").replace(/\\\//g, '/');
  // HTML entities (decode &amp; last so &amp;lt; resolves correctly)
  t = t
    .replace(/&lt;/gi, '<').replace(/&gt;/gi, '>').replace(/&quot;/gi, '"')
    .replace(/&#0*39;|&apos;/gi, "'").replace(/&nbsp;/gi, ' ')
    .replace(/&#(\d+);/g, (_m, n) => { const c = Number(n); return c > 0 && c < 1114112 ? String.fromCodePoint(c) : ''; })
    .replace(/&amp;/gi, '&');
  t = t.replace(/�/g, '');                       // drop mojibake replacement chars
  return t.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}

/** Strip markdown syntax to plain text (for plain-text contexts: CSV, pre-wrap report bodies). */
export function stripSocialMarkdown(s: string): string {
  let t = cleanSocialText(s);
  t = t.replace(/^\s*#{1,6}\s*/gm, '');               // headings
  t = t.replace(/^\s*([-*_]\s*){3,}\s*$/gm, '');      // --- *** ___ rules
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '$1 ($2)'); // links -> "text (url)"
  t = t.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, '$1$2'); // bold/italic
  t = t.replace(/^\s*[-*]\s+/gm, '• ');               // bullets
  return t.replace(/\n{3,}/g, '\n\n').trim();
}
