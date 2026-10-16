/*
 * Auspex answers carry data inside the text as HTML comments, before the prose:
 *   <!-- ARTICLE_STATS:{json}:END_STATS -->   what retrieval found
 *   <!-- CHART_DATA:{json}:END_CHART -->      a chart (Plotly figure JSON)
 *   <!-- CHART_ERROR:message:END_CHART -->    a chart that failed
 * Stored messages keep them, so history renders the same as a live answer.
 */

export interface ArticleStats {
  total_articles?: number;
  sentiment_breakdown?: Record<string, number>;
  category_distribution?: Record<string, number>;
  date_range?: { earliest?: string | null; latest?: string | null };
  top_sources?: { name: string; count: number; sample_url?: string }[];
}
export interface ChartSpec { type?: string; chart_type?: string; title?: string; data?: unknown; layout?: { title?: unknown } }

export interface Parsed {
  /** The prose, markers removed */
  text: string;
  stats: ArticleStats | null;
  charts: ChartSpec[];
  chartErrors: string[];
}

const STATS = /<!-- ARTICLE_STATS:([\s\S]*?):END_STATS -->/g;
const CHART = /<!-- CHART_DATA:([\s\S]*?):END_CHART -->/g;
const CHART_ERR = /<!-- CHART_ERROR:([\s\S]*?):END_CHART -->/g;
// The model sometimes points at a chart as a link, "[sentiment chart](CHART: sentiment_distribution)",
// which Markdown can't parse (space in the URL): keep the link text only
const CHART_REF = /\[([^\]]*)\]\(CHART:[^)]*\)/g;
// A marker still arriving mid-stream: hide it until it's complete
const PARTIAL = /<!--[\s\S]*$/;

const json = <T,>(s: string): T | null => {
  try {
    return JSON.parse(s) as T;
  } catch {
    return null;
  }
};

export function parseAnswer(raw: string, streaming = false): Parsed {
  let stats: ArticleStats | null = null;
  const charts: ChartSpec[] = [];
  const chartErrors: string[] = [];
  for (const m of raw.matchAll(STATS)) stats = json<ArticleStats>(m[1]) ?? stats;
  for (const m of raw.matchAll(CHART)) {
    const c = json<ChartSpec>(m[1]);
    if (c) charts.push(c);
  }
  for (const m of raw.matchAll(CHART_ERR)) chartErrors.push(m[1].trim());
  let text = raw.replace(STATS, '').replace(CHART, '').replace(CHART_ERR, '').replace(CHART_REF, '$1');
  if (streaming) text = text.replace(PARTIAL, '');
  return { text: text.trim(), stats, charts, chartErrors };
}

/** Text for copy and export: the prose only. */
export const plainText = (raw: string) => parseAnswer(raw).text;
