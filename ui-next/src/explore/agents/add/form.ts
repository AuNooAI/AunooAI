import type { CreateAgentRequest, ResearchAgent } from '@monolith/researchAgentsApi';

/*
 * The add/edit agent form as one object, with the conversions to and from the saved agent. Defaults
 * and templates are the old AddAgentModal.tsx's.
 */

export const DEFAULT_REPORT_PROMPT = `Analyze the following signal matches and create a comprehensive intelligence report.

## Your Task
1. Summarize the key findings across all matched articles
2. Identify common themes and patterns
3. Assess the overall significance and urgency
4. Note any gaps or areas requiring further investigation

Format your response as a structured markdown report with clear sections.`;

export const DEFAULT_PODCAST_PROMPT = `Create a podcast-style audio script summarizing these intelligence findings. Write it as if you're a host delivering a briefing to listeners.

## Requirements
1. Start with a brief, engaging intro (e.g., "Welcome to today's intelligence briefing...")
2. Summarize the most important findings in conversational, easy-to-follow language
3. Highlight threat levels and urgency where relevant
4. Connect related stories if patterns emerge
5. End with key takeaways and recommended actions
6. Keep the tone professional but accessible
7. Target length: 2-3 minutes when read aloud (approximately 400-500 words)`;

export const DEFAULT_ENTITIES_HINT = 'Company names, people or brands to watch for, one per line or separated by commas.';

export type SearchStrategy = 'recent' | 'chunked' | 'semantic';
export type ScheduleType = 'interval' | 'daily';
export type ScheduleUnit = 'minutes' | 'hours' | 'days';

export interface AgentForm {
  name: string;
  description: string;
  instruction: string;
  /** '' = all topics */
  topic: string;
  /** '' = the site default */
  model: string;
  isActive: boolean;
  entities: string;
  entitiesHint: string;
  searchStrategy: SearchStrategy;
  maxArticles: number;
  alertThreshold: number;
  tagArticles: boolean;
  starArticles: boolean;
  report: boolean;
  reportPrompt: string;
  includeRecommendations: boolean;
  podcast: boolean;
  podcastPrompt: string;
  podcastVoice: string;
  deepResearch: boolean;
  sendEmail: boolean;
  emailRecipient: string;
  attachPdf: boolean;
  blueskyDm: boolean;
  blueskyRecipient: string;
  scheduleEnabled: boolean;
  scheduleType: ScheduleType;
  scheduleInterval: number;
  scheduleUnit: ScheduleUnit;
  scheduleTime: string;
  daysBack: number;
}

export const emptyForm = (): AgentForm => ({
  name: '', description: '', instruction: '', topic: '', model: '', isActive: true,
  entities: '', entitiesHint: DEFAULT_ENTITIES_HINT, searchStrategy: 'recent', maxArticles: 100, alertThreshold: 1,
  tagArticles: true, starArticles: false, report: false, reportPrompt: DEFAULT_REPORT_PROMPT, includeRecommendations: false,
  podcast: false, podcastPrompt: DEFAULT_PODCAST_PROMPT, podcastVoice: '', deepResearch: false,
  sendEmail: false, emailRecipient: '', attachPdf: false, blueskyDm: false, blueskyRecipient: '',
  scheduleEnabled: false, scheduleType: 'interval', scheduleInterval: 24, scheduleUnit: 'hours', scheduleTime: '09:00', daysBack: 7,
});

export function fromAgent(a: ResearchAgent): AgentForm {
  const c = (a.config ?? {}) as Record<string, unknown>;
  const str = (k: string) => (typeof c[k] === 'string' ? (c[k] as string) : '');
  const num = (k: string, d: number) => (typeof c[k] === 'number' ? (c[k] as number) : d);
  const bool = (k: string) => c[k] === true;
  return {
    ...emptyForm(),
    name: a.name || '',
    description: a.description || '',
    instruction: a.instruction || '',
    topic: a.topic || '',
    model: str('model'),
    isActive: a.is_active !== false,
    entities: Array.isArray(c.entities_to_monitor) ? (c.entities_to_monitor as string[]).join('\n') : '',
    searchStrategy: (str('search_strategy') as SearchStrategy) || 'recent',
    maxArticles: num('max_articles', 100),
    alertThreshold: num('alert_threshold', 1),
    tagArticles: c.tag_articles !== false,
    starArticles: bool('star_flagged_articles'),
    report: !!a.generate_report,
    reportPrompt: a.report_prompt || DEFAULT_REPORT_PROMPT,
    includeRecommendations: bool('include_recommendations'),
    podcast: bool('generate_podcast'),
    podcastPrompt: str('podcast_prompt') || DEFAULT_PODCAST_PROMPT,
    podcastVoice: str('podcast_voice_id'),
    deepResearch: bool('deep_research'),
    sendEmail: bool('send_email'),
    emailRecipient: str('email_recipient'),
    attachPdf: bool('attach_pdf_report'),
    blueskyDm: bool('bluesky_dm'),
    blueskyRecipient: str('bluesky_recipient'),
    scheduleEnabled: !!a.schedule_enabled,
    scheduleType: a.schedule_type || 'interval',
    scheduleInterval: a.schedule_interval || 24,
    scheduleUnit: a.schedule_unit || 'hours',
    scheduleTime: a.schedule_time || '09:00',
    daysBack: num('days_back', 7),
  };
}

export function toRequest(f: AgentForm): CreateAgentRequest {
  const config: Record<string, unknown> = { days_back: f.daysBack };
  if (f.model) config.model = f.model;
  if (f.includeRecommendations) config.include_recommendations = true;
  if (f.starArticles) config.star_flagged_articles = true;
  // Scheduled runs read this (default on). The old dialog never saved it, so unticking did nothing.
  if (!f.tagArticles) config.tag_articles = false;
  if (f.deepResearch) config.deep_research = true;
  if (f.sendEmail) {
    config.send_email = true;
    if (f.emailRecipient.trim()) config.email_recipient = f.emailRecipient.trim();
    if (f.attachPdf) config.attach_pdf_report = true;
  }
  if (f.blueskyDm) {
    config.bluesky_dm = true;
    if (f.blueskyRecipient.trim()) config.bluesky_recipient = f.blueskyRecipient.trim();
  }
  const entities = f.entities.split(/[,\n]/).map((e) => e.trim()).filter(Boolean);
  if (entities.length) config.entities_to_monitor = entities;
  if (f.searchStrategy !== 'recent') config.search_strategy = f.searchStrategy;
  if (f.maxArticles !== 100) config.max_articles = f.maxArticles;
  if (f.alertThreshold !== 1) config.alert_threshold = f.alertThreshold;
  if (f.podcast) {
    config.generate_podcast = true;
    if (f.podcastPrompt.trim() && f.podcastPrompt.trim() !== DEFAULT_PODCAST_PROMPT.trim()) config.podcast_prompt = f.podcastPrompt.trim();
    if (f.podcastVoice) config.podcast_voice_id = f.podcastVoice;
  }
  const interval = f.scheduleEnabled && f.scheduleType === 'interval';
  return {
    name: f.name.trim(),
    description: f.description.trim(),
    instruction: f.instruction.trim(),
    topic: f.topic || null,
    is_active: f.isActive,
    generate_report: f.report,
    report_prompt: f.report ? f.reportPrompt.trim() : null,
    config,
    schedule_enabled: f.scheduleEnabled,
    schedule_type: f.scheduleEnabled ? f.scheduleType : null,
    schedule_interval: interval ? f.scheduleInterval : null,
    schedule_unit: interval ? f.scheduleUnit : null,
    schedule_time: f.scheduleEnabled && f.scheduleType === 'daily' ? f.scheduleTime : null,
  };
}

export const TEMPLATES: { name: string; instruction: string; entities?: string }[] = [
  {
    name: 'Executive Mentions',
    instruction: 'Flag any articles that mention C-level executives (CEO, CTO, CFO, etc.) making announcements, policy changes, or strategic decisions. Focus on direct quotes and business-critical information. Explain why each match is relevant to executive leadership.',
  },
  {
    name: 'Regulatory Changes',
    instruction: 'Identify articles discussing new regulations, policy changes, government actions, or compliance requirements that could impact business operations. For each match, explain the specific regulatory change and its potential business impact.',
  },
  {
    name: 'Competitive Intelligence',
    instruction: 'Monitor for articles about competitor activities including product launches, partnerships, acquisitions, market expansion, or strategic shifts. Explain how each finding relates to competitive positioning.',
  },
  {
    name: 'Emerging Threats',
    instruction: 'Watch for emerging security threats, vulnerabilities, data breaches, or cyber attacks. Rate the severity (high/medium/low) and explain the potential impact and affected systems.',
  },
  {
    name: 'Adverse Media Screening',
    instruction: 'Screen for negative news coverage including fraud allegations, corruption, sanctions violations, money laundering, bribery, criminal activity, lawsuits, regulatory fines, environmental violations, or reputational damage. Flag any mentions of individuals or organizations under investigation or facing legal action. Rate risk level (high/medium/low) and summarize the specific adverse finding.',
    entities: 'Company names, individuals or organisations to screen.',
  },
  {
    name: 'Brand Monitoring',
    instruction: 'Monitor brand mentions across news coverage including product reviews, customer complaints, PR crises, social media controversies, executive scandals, product recalls, or service outages. Track sentiment (positive/negative/neutral) and identify potential reputation risks or opportunities. Flag any coverage that could impact brand perception or require a response.',
    entities: 'Your brand name and any related brands to watch.',
  },
  {
    name: 'Competitor Monitoring',
    instruction: 'Track competitor news including new product launches, pricing changes, market expansion, executive hires, funding rounds, partnerships, M&A activity, patent filings, and strategic announcements. Identify competitive threats and opportunities. Summarize how each development could impact market position or require a strategic response.',
    entities: 'Competitor company names to track.',
  },
];
