// MOCK data for the shared shell (SHELL_NAV_SPEC §3, TOPIC_SETUP_SPEC §7). No API calls yet.
import type { IconName, SelectOption } from '@aunoo/ui';

export const user = { initial: 'd', name: 'demo.user' };
export const userMenuItems = [
  { id: 'settings', label: 'Settings', icon: 'GearSix' as const },
  { id: 'logout', label: 'Log out', icon: 'SignOut' as const },
];

export const notifications = [
  { id: 'n1', icon: 'Lightning' as IconName, title: 'Spike: Product and launches for Market Monitoring SOC Automation', description: '14 articles this week (avg: 5/week)', minutesAgo: 0, unread: true },
  { id: 'n2', icon: 'ArrowsClockwise' as IconName, title: 'RSS Feed Complete', description: 'Scheduled fetch: 2 articles, 0 enriched', minutesAgo: 0, unread: true },
  { id: 'n3', icon: 'Lightning' as IconName, title: 'Spike: Bot networks for Swiss Federal Elections 2027 Disinfo Monitoring', description: '9 articles this week (avg: 3/week)', minutesAgo: 22, unread: true },
  { id: 'n4', icon: 'ArrowsClockwise' as IconName, title: 'RSS Feed Complete', description: 'Scheduled fetch: 15 articles, 8 enriched', minutesAgo: 140, unread: false },
];

/* ---------- Topic Setup wizard ---------- */

export type KeyId = 'ai' | 'news' | 'firecrawl';

export const AI_PROVIDERS: (SelectOption & { help: string; keyUrl: string })[] = [
  { value: 'openai', label: 'OpenAI (GPT-4, GPT-4o, etc.)', help: 'Supports GPT-4, GPT-4o, and more', keyUrl: 'https://platform.openai.com/api-keys' },
  { value: 'anthropic', label: 'Anthropic (Claude)', help: 'Supports Claude 3.5, Claude 4, and more', keyUrl: 'https://console.anthropic.com/settings/keys' },
  { value: 'gemini', label: 'Google Gemini', help: 'Supports Gemini Pro, Gemini 2.0 Flash, and more', keyUrl: 'https://aistudio.google.com/app/apikey' },
];

export const NEWS_PROVIDERS: (SelectOption & { registerUrl: string })[] = [
  { value: 'newsapi', label: 'NewsAPI', registerUrl: 'https://newsapi.org/register' },
  { value: 'thenewsapi', label: 'TheNewsAPI', registerUrl: 'https://www.thenewsapi.com/register' },
  { value: 'newsdata', label: 'NewsData.io', registerUrl: 'https://newsdata.io/register' },
];

export const FIRECRAWL_URL = 'https://www.firecrawl.dev/pricing';

/** Key status from the backend. This variant has no AI key, so the wizard opens on Step 1. */
export const KEY_STATUS = { openai: false, anthropic: false, gemini: false, newsapi: false, thenewsapi: true, newsdata: false, firecrawl: true };

export const DEFAULT_SIGNALS = ['AI is hype', 'AI is evolving gradually', 'AI is accelerating', 'AI reaches plateau', 'AI breakthrough imminent'];
export const DEFAULT_CATEGORIES = ['AI in Finance', 'AI Ethics', 'AI Regulation', 'Cloud Computing', 'Edge AI'];
export const SENTIMENTS = ['Positive', 'Negative', 'Neutral'];
export const TIME_TO_IMPACT = ['Immediate (0-6 months)', 'Short-term (6-18 months)', 'Mid-term (18-60 months)', 'Long-term (60+ months)'];

export interface KeywordSets { companies: string[]; technologies: string[]; general: string[]; people: string[]; exclusions: string[] }

/** What "Suggest Details" returns (shaped like the live response). */
export function suggestFor(name: string) {
  return {
    explanation: `For “${name}”, track where the technology is heading, who is building it and what could slow it down.`,
    future_signals: ['Solid-state commercialised by 2028', 'LFP dominates mass market', 'Supply constraints slow EV adoption'],
    categories: ['Cell Chemistry', 'Gigafactories', 'Raw Materials', 'Policy & Subsidies'],
    keywords: {
      companies: ['CATL', 'BYD', 'LG Energy Solution', 'Panasonic'],
      technologies: ['solid-state battery', 'LFP', 'sodium-ion'],
      general: ['battery recycling'],
      people: [],
      exclusions: ['-phone battery'],
    } as KeywordSets,
  };
}

export const ALTERNATE_KEYWORDS: KeywordSets = {
  companies: ['Northvolt', 'SK On', 'Samsung SDI'],
  technologies: ['4680 cell', 'silicon anode', 'dry electrode'],
  general: ['gigafactory', 'cathode supply'],
  people: ['Robin Zeng'],
  exclusions: ['-laptop battery'],
};
