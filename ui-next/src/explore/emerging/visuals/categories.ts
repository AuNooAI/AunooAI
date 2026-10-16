/*
 * Keyword-based theme categories, as the old TopicsTimelineChart and CategoryRadarChart used. A
 * theme goes in the first category whose keywords appear in its label or key themes. It is a rough
 * grouping by words, not a judgement by the AI.
 */

export type ThemeCategory = 'business' | 'geopolitics' | 'regulation' | 'society' | 'technology' | 'crisis' | 'other';

export const CATEGORY_LABEL: Record<ThemeCategory, string> = {
  business: 'Business',
  geopolitics: 'Geopolitics',
  regulation: 'Regulation',
  society: 'Society',
  technology: 'Technology',
  crisis: 'Crisis',
  other: 'Other',
};

const KEYWORDS: [ThemeCategory, string[]][] = [
  ['business', ['market', 'company', 'business', 'economic', 'finance', 'stock', 'investment', 'corporate', 'enterprise', 'revenue', 'profit', 'trade', 'industry', 'merger', 'acquisition']],
  ['geopolitics', ['war', 'conflict', 'military', 'nato', 'russia', 'china', 'diplomatic', 'foreign', 'international', 'treaty', 'sanction', 'border', 'territory', 'alliance']],
  ['regulation', ['law', 'regulation', 'policy', 'legislation', 'compliance', 'legal', 'court', 'privacy', 'antitrust', 'government', 'bill', 'act', 'ruling', 'enforcement']],
  ['society', ['social', 'culture', 'health', 'education', 'community', 'public', 'climate', 'environment', 'protest', 'rights', 'welfare', 'demographic']],
  ['technology', ['ai', 'artificial intelligence', 'tech', 'software', 'digital', 'cyber', 'data', 'cloud', 'quantum', 'automation', 'algorithm', 'semiconductor', 'chip']],
  ['crisis', ['crisis', 'emergency', 'disaster', 'catastrophe', 'outbreak', 'pandemic', 'collapse', 'failure', 'crash', 'breach', 'attack', 'threat', 'warning', 'alert', 'urgent', 'critical', 'severe', 'escalation', 'volatility', 'turmoil', 'disruption', 'shortage', 'outage']],
];

export function classifyTheme(label: string, themes: string[] = []): ThemeCategory {
  const text = [label, ...themes].join(' ').toLowerCase();
  // Whole words only: the old check matched "ai" inside "said" and "act" inside "impact"
  const words = new Set(text.split(/[^a-z0-9]+/).filter(Boolean));
  for (const [cat, keys] of KEYWORDS) {
    if (keys.some((k) => (k.includes(' ') ? text.includes(k) : words.has(k)))) return cat;
  }
  return 'other';
}
