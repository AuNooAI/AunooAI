/*
 * A report's inline citation markers ([A3], [C7]) become links to the article they name, using the
 * citation index stored with the report's facts. Done on the Markdown text, so the shared renderer
 * draws them as ordinary links.
 */

export type CitationIndex = Record<string, { uri: string; title: string; vendor?: string; source?: string }>;

export function linkCitations(md: string, index?: CitationIndex | null): string {
  if (!index) return md;
  // Skip a marker that is already a link's text ([A3](...))
  return md.replace(/\[([AC]\d+)\](?!\()/g, (whole, id: string) => {
    const ref = index[id];
    return ref?.uri ? `[[${id}]](${ref.uri})` : whole;
  });
}
