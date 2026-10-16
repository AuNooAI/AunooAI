/*
 * Small helpers over the query text. The server parses the query language; the page only adds and
 * removes tokens (a facet click adds field="value") and reads the few tokens it handles itself.
 */

/** field="value" token, quotes stripped from the value */
export const token = (field: string, value: string) => `${field}="${value.replace(/["']/g, '')}"`;

/** Adds the token, or removes it when it's already in the query */
export function toggleToken(q: string, t: string): string {
  return q.includes(t) ? q.replace(t, '').replace(/\s{2,}/g, ' ').trim() : `${q} ${t}`.trim();
}

/** Replaces any existing token of this kind (matched by the pattern) with the new one */
export function replaceToken(q: string, pattern: RegExp, t: string | null): string {
  const cleaned = q.replace(pattern, '').replace(/\s{2,}/g, ' ').trim();
  return t ? `${cleaned} ${t}`.trim() : cleaned;
}

export const SORT_RE = /\bsort:[\w_]+(?::(?:asc|desc))?/gi;
export const TIME_RE = /\bpublication_date\s*(?:>=|>)\s*(?:"[^"]*"|\S+)/gi;

/** keyword="…" switches to the full-text search, as on the old page */
export function keywordOf(q: string): string | null {
  const m = q.match(/\bkeyword\s*=\s*(?:"([^"]+)"|(\S+))/i);
  return m ? (m[1] ?? m[2]) : null;
}

/** limit:n caps the results (0 = no cap); cluster=n keeps one cluster */
export function metaOf(q: string): { limit?: number; cluster?: number } {
  const out: { limit?: number; cluster?: number } = {};
  const l = q.match(/\blimit:(\d+)\b/i);
  if (l) out.limit = Number(l[1]);
  const c = q.match(/\bcluster(?:=|:)(\d+)\b/i);
  if (c) out.cluster = Number(c[1]);
  return out;
}

export const TIME_OPTIONS = [
  { value: 'any', label: 'Any time' },
  { value: 'last_day', label: 'Last day' },
  { value: 'last_week', label: 'Last week' },
  { value: 'last_month', label: 'Last month' },
  { value: 'last_3_months', label: 'Last 3 months' },
  { value: 'last_year', label: 'Last year' },
  { value: 'today', label: 'Today' },
  { value: 'this_week', label: 'This week' },
  { value: 'this_month', label: 'This month' },
];

export const SORT_OPTIONS = [
  { value: 'relevance', label: 'Best match' },
  { value: 'publication_date:desc', label: 'Newest first' },
  { value: 'publication_date:asc', label: 'Oldest first' },
  { value: 'sentiment:asc', label: 'Sentiment' },
];

export const BUILDER_FIELDS = ['category', 'topic', 'sentiment', 'news_source', 'driver_type', 'time_to_impact', 'future_signal', 'publication_date'];
export const BUILDER_OPS = ['=', '!=', '>', '>=', '<', '<='];

/** Unix seconds for a relative date word, as the old page computed them */
export function relativeToSeconds(word: string, now = new Date()): number | null {
  const day = 86400;
  const t = Math.floor(now.getTime() / 1000);
  const startOfDay = (d: Date) => Math.floor(new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() / 1000);
  switch (word.toLowerCase()) {
    case 'last_hour': return t - 3600;
    case 'last_day': return t - day;
    case 'last_week': return t - 7 * day;
    case 'last_month': return t - 30 * day;
    case 'last_3_months': return t - 90 * day;
    case 'last_year': return t - 365 * day;
    case 'today': return startOfDay(now);
    case 'yesterday': return startOfDay(now) - day;
    case 'this_week': return startOfDay(now) - now.getDay() * day;
    case 'this_month': return Math.floor(new Date(now.getFullYear(), now.getMonth(), 1).getTime() / 1000);
    default: return null;
  }
}

/** The Time menu's token: publication_date>=<unix seconds>, the form the old page's Time menu wrote */
export const timeToken = (range: string) => {
  const s = relativeToSeconds(range);
  return s === null ? null : `publication_date>=${s}`;
};

const DATE_TOKEN = /\bpublication_date\s*(>=|<=|>|<|=|!=)\s*(?:"([^"]+)"|(\S+))/gi;

function toSeconds(v: string): number | null {
  const rel = relativeToSeconds(v);
  if (rel !== null) return rel;
  if (/^\d{10,13}$/.test(v)) {
    const n = Number(v);
    return n > 1e11 ? Math.floor(n / 1000) : n;
  }
  const d = Date.parse(v);
  return Number.isNaN(d) ? null : Math.floor(d / 1000);
}

/**
 * Date filters for the server. The search compares dates as dates (app/kissql/executor.py) and
 * reads ISO dates, so every date token (a word like last_week, the Time menu's Unix seconds, or a
 * typed date) is rewritten as publication_date<op>YYYY-MM-DD. The server then filters the search
 * itself, so Patterns and the map respect the dates too.
 */
export function datesForServer(q: string): { query: string; label: string | null } {
  const labels: string[] = [];
  const query = q.replace(DATE_TOKEN, (m, op: string, quoted?: string, bare?: string) => {
    const s = toSeconds(quoted ?? bare ?? '');
    if (s === null) return m;
    const d = new Date(s * 1000);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    labels.push(`${op} ${d.toLocaleDateString('en-GB')}`);
    return `publication_date${op}${iso}`;
  });
  return { query, label: labels.length ? `published ${labels.join(' and ')}` : null };
}

/**
 * Date filters applied in the browser, for keyword search only: the keyword route takes no
 * filters, so the tokens are taken out of the query and turned into a test on each result's date.
 */
export function splitDateFilters(q: string): { rest: string; test: ((isoDate: unknown) => boolean) | null; label: string | null } {
  const tests: ((s: number) => boolean)[] = [];
  const labels: string[] = [];
  const rest = q.replace(DATE_TOKEN, (m, op: string, quoted?: string, bare?: string) => {
    const s = toSeconds(quoted ?? bare ?? '');
    if (s === null) return m;
    labels.push(`${op} ${new Date(s * 1000).toLocaleDateString('en-GB')}`);
    const day = (x: number) => Math.floor(x / 86400);
    tests.push(
      op === '>=' ? (x) => x >= s
        : op === '>' ? (x) => x > s
        : op === '<=' ? (x) => x <= s
        : op === '<' ? (x) => x < s
        : op === '=' ? (x) => day(x) === day(s)
        : (x) => day(x) !== day(s),
    );
    return '';
  }).replace(/\s{2,}/g, ' ').trim();
  if (!tests.length) return { rest: q, test: null, label: null };
  return {
    rest,
    label: `published ${labels.join(' and ')}`,
    test: (iso) => {
      const t = typeof iso === 'string' || typeof iso === 'number' ? Date.parse(String(iso)) : NaN;
      if (Number.isNaN(t)) return false;
      const x = Math.floor(t / 1000);
      return tests.every((f) => f(x));
    },
  };
}
