/**
 * Briefing Desk API Service
 * Handles all API calls for the Briefing Desk feature
 */

import { extractErrorMessage } from './api';

// ============================================================================
// Types
// ============================================================================

export interface BriefingArticle {
  uri: string;
  title: string;
  summary?: string;
  source?: string;
  publication_date?: string;
  topic?: string;
  url?: string;
  sentiment?: string;
  bias?: string;
  category?: string;
  added_at?: string;
  analysis?: {
    key_insight?: string;
    strategic_relevance?: string;
    category?: string;
    time_horizon?: string;
    risk_opportunity?: string;
  };
}

export interface BriefingIncident {
  name: string;
  title?: string;
  type?: string;
  significance?: string;
  description?: string;
  summary?: string;
  topic?: string;
  timeline?: string;
  entities?: string[];
  article_uris?: string[];
  added_at?: string;
  analysis?: {
    key_insight?: string;
    strategic_relevance?: string;
    category?: string;
    time_horizon?: string;
    risk_opportunity?: string;
  };
}

export interface BriefingEmergingTopic {
  name: string;
  summary?: string;
  why_emerging?: string;
  key_takeaway?: string;
  article_count?: number;
  velocity?: string;
  trend_score?: {
    volume?: number;
    velocity?: number;
    diversity?: number;
    novelty?: number;
    composite?: number;
    urgency?: string;
  };
  key_entities?: string[];
  representative_keywords?: string[];
  topic?: string;
  added_at?: string;
}

export interface BriefingTheme {
  theme_name: string;
  description: string;
  supporting_items?: string[];
  strategic_implication?: string;
}

export interface BriefingAction {
  action: string;
  urgency: 'immediate' | 'this_week' | 'this_month' | 'this_quarter';
  rationale?: string;
}

export interface DeskBriefing {
  id: number;
  name: string;
  description?: string;
  topic?: string;
  articles: BriefingArticle[];
  incidents: BriefingIncident[];
  emerging_topics: BriefingEmergingTopic[];
  synthesis?: string;
  themes?: BriefingTheme[];
  priority_actions?: BriefingAction[];
  metadata?: Record<string, unknown>;
  status: 'draft' | 'finalized';
  model_used?: string;
  articles_count: number;
  incidents_count: number;
  emerging_topics_count: number;
  created_at: string;
  updated_at: string;
  finalized_at?: string;
}

export interface BriefingSummary {
  id: number;
  name: string;
  description?: string;
  topic?: string;
  status: 'draft' | 'finalized';
  articles_count: number;
  incidents_count: number;
  emerging_topics_count: number;
  model_used?: string;
  created_at: string;
  updated_at: string;
  finalized_at?: string;
}

export interface FinalizeProgressEvent {
  stage: 'analysis' | 'synthesis' | 'complete' | 'error';
  status: string;
  progress: number;
  current_item?: number;
  total_items?: number;
  item_title?: string;
  synthesis?: string;
  themes?: BriefingTheme[];
  priority_actions?: BriefingAction[];
  error?: string;
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Fetch all briefings for the current user
 */
export async function fetchBriefings(): Promise<BriefingSummary[]> {
  const response = await fetch('/api/desk-briefings', {
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to fetch briefings');
  }

  const data = await response.json();
  return data.briefings || [];
}

/**
 * Get count of draft briefings (for badge display)
 */
export async function fetchDraftBriefingsCount(): Promise<number> {
  const response = await fetch('/api/desk-briefings/count', {
    credentials: 'include',
  });

  if (!response.ok) {
    console.error('Failed to fetch draft count');
    return 0;
  }

  const data = await response.json();
  return data.draft_count || 0;
}

/**
 * Create a new briefing
 */
export async function createBriefing(
  name: string,
  description?: string,
  topic?: string
): Promise<{ briefing_id: number; message: string }> {
  const response = await fetch('/api/desk-briefings', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description, topic }),
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to create briefing');
  }

  return response.json();
}

export interface ComposeDailyBriefingResult {
  success: boolean;
  briefing_id: number;
  name: string;
  status: 'draft';
  topics_requested: string[];
  emerging_topics_staged: number;
  articles_staged: number;
  per_topic: Array<{
    topic: string;
    detected: number;
    topics_staged: number;
    articles_staged: number;
    error?: string | null;
  }>;
}

/**
 * Auto-compose a draft daily briefing: create + run Emerging Topics detection +
 * stage detected topics and relevant articles for the named topics. Leaves the
 * briefing as a DRAFT for curation. Detection can take ~30-120s per topic.
 */
/**
 * Compose configuration. Both the streaming and non-streaming endpoints take
 * the same shape, and anything omitted falls back to the server default —
 * which is what the UI relies on, since it exposes no controls for these.
 */
export interface ComposeOptions {
  min_confidence?: number;
  min_alignment?: number;
  days_back?: number;
  history_days?: number;
  run_detection?: boolean;
  model?: string;
}

export async function composeDailyBriefing(
  topics?: string[],
  opts?: ComposeOptions
): Promise<ComposeDailyBriefingResult> {
  const response = await fetch('/api/desk-briefings/auto-compose', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topics, ...opts }),
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to compose daily briefing');
  }

  return response.json();
}

export interface ComposeProgressEvent {
  stage: string;
  status?: string;
  message?: string;
  progress?: number;
  briefing_id?: number;
  name?: string;
  count?: number;
  current?: number;
  total?: number;
  fallback?: boolean;
  backfill_count?: number;
  articles_staged?: number;
  incidents_staged?: number;
  emerging_topics_staged?: number;
  error?: string;
}

/**
 * Auto-compose a draft daily briefing, streaming staged progress.
 * Calls onEvent for each progress event; resolves with the final event.
 */
export async function streamComposeDailyBriefing(
  topics: string[] | undefined,
  opts: ComposeOptions | undefined,
  onEvent: (e: ComposeProgressEvent) => void,
): Promise<ComposeProgressEvent | null> {
  const response = await fetch('/api/desk-briefings/auto-compose/stream', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topics, ...opts }),
  });
  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to start compose');
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response stream');

  const decoder = new TextDecoder();
  let buffer = '';
  let last: ComposeProgressEvent | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6);
      if (data === '[DONE]') return last;
      try {
        const evt = JSON.parse(data) as ComposeProgressEvent;
        last = evt;
        onEvent(evt);
        if (evt.stage === 'error') {
          throw new Error(evt.error || evt.message || 'Compose failed');
        }
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
  return last;
}

export interface ComposeConfig {
  available_topics: Array<{ name: string; description?: string }>;
  selected_topics: string[];
}

/**
 * Fetch configured topics + the saved default selection for the compose modal.
 */
export async function fetchComposeConfig(): Promise<ComposeConfig> {
  const response = await fetch('/api/desk-briefings/compose-config', {
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to load compose config');
  }
  return response.json();
}

/**
 * Save the default daily-briefing topic set.
 */
export async function saveComposeConfig(topics: string[]): Promise<void> {
  const response = await fetch('/api/desk-briefings/compose-config', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topics }),
  });
  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to save topic selection');
  }
}

/**
 * Get a specific briefing with full content
 */
export async function fetchBriefing(briefingId: number): Promise<DeskBriefing> {
  const response = await fetch(`/api/desk-briefings/${briefingId}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to fetch briefing');
  }

  const data = await response.json();
  return data.briefing;
}

/**
 * Update briefing name or description
 */
export async function updateBriefing(
  briefingId: number,
  updates: { name?: string; description?: string }
): Promise<void> {
  const response = await fetch(`/api/desk-briefings/${briefingId}`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to update briefing');
  }
}

/**
 * Delete a briefing
 */
export async function deleteBriefing(briefingId: number): Promise<void> {
  const response = await fetch(`/api/desk-briefings/${briefingId}`, {
    method: 'DELETE',
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to delete briefing');
  }
}

/**
 * Add an article to a briefing
 */
export async function addArticleToBriefing(
  briefingId: number,
  article: {
    uri: string;
    title: string;
    summary?: string;
    source?: string;
    publication_date?: string;
    topic?: string;
    url?: string;
    sentiment?: string;
    bias?: string;
    category?: string;
    analysis?: {
      key_insight?: string;
      executive_takeaway?: string;
      strategic_relevance?: string;
      category?: string;
      time_horizon?: string;
      risk_opportunity?: string;
      signal_strength?: string;
    };
  }
): Promise<void> {
  const response = await fetch(`/api/desk-briefings/${briefingId}/articles`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(article),
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to add article');
  }
}

/**
 * Remove an article from a briefing
 */
export async function removeArticleFromBriefing(
  briefingId: number,
  articleUri: string
): Promise<void> {
  const response = await fetch(
    `/api/desk-briefings/${briefingId}/articles/${encodeURIComponent(articleUri)}`,
    {
      method: 'DELETE',
      credentials: 'include',
    }
  );

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to remove article');
  }
}

/**
 * Add an incident to a briefing
 */
export async function addIncidentToBriefing(
  briefingId: number,
  incident: {
    name: string;
    title?: string;
    type?: string;
    significance?: string;
    description?: string;
    summary?: string;
    topic?: string;
    timeline?: string;
    first_seen?: string;
    last_seen?: string;
    entities?: string[];
    article_uris?: string[];
    organizational_relevance?: string;
    strategic_relevance?: string;
    plausibility?: string;
    source_quality?: string;
    credibility_summary?: string;
    investigation_leads?: string[];
    analyst_notes?: Array<{
      id: string;
      timestamp: string;
      analyst: string;
      comment: string;
    }>;
    analysis?: {
      key_insight?: string;
      strategic_relevance?: string;
      category?: string;
      time_horizon?: string;
      risk_opportunity?: string;
    };
  }
): Promise<void> {
  const response = await fetch(`/api/desk-briefings/${briefingId}/incidents`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(incident),
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to add incident');
  }
}

/**
 * Remove an incident from a briefing
 */
export async function removeIncidentFromBriefing(
  briefingId: number,
  incidentName: string
): Promise<void> {
  const response = await fetch(
    `/api/desk-briefings/${briefingId}/incidents/${encodeURIComponent(incidentName)}`,
    {
      method: 'DELETE',
      credentials: 'include',
    }
  );

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to remove incident');
  }
}

/**
 * Finalize a briefing with AI synthesis (streaming)
 */
export async function finalizeBriefing(
  briefingId: number,
  model: string = 'gpt-4o',
  onProgress: (event: FinalizeProgressEvent) => void,
  options?: {
    organizational_profile?: string;
    persona?: string;
  }
): Promise<void> {
  const response = await fetch(`/api/desk-briefings/${briefingId}/finalize`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model,
      organizational_profile: options?.organizational_profile,
      persona: options?.persona,
    }),
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to start finalization');
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('Failed to get response stream');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Process complete SSE events
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event = JSON.parse(line.slice(6)) as FinalizeProgressEvent;
          onProgress(event);

          if (event.stage === 'error') {
            throw new Error(event.error || 'Finalization failed');
          }
        } catch (e) {
          if (e instanceof SyntaxError) {
            console.warn('Failed to parse SSE event:', line);
          } else {
            throw e;
          }
        }
      }
    }
  }
}

/**
 * Export a briefing in the specified format
 */
export async function exportBriefing(
  briefingId: number,
  format: 'json' | 'markdown' | 'html' = 'markdown'
): Promise<Blob> {
  const response = await fetch(
    `/api/desk-briefings/${briefingId}/export?format=${format}`,
    {
      credentials: 'include',
    }
  );

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to export briefing');
  }

  return response.blob();
}

/**
 * Download exported briefing
 */
export async function downloadBriefing(
  briefingId: number,
  briefingName: string,
  format: 'json' | 'markdown' | 'html' = 'markdown'
): Promise<void> {
  const blob = await exportBriefing(briefingId, format);

  const extension = format === 'markdown' ? 'md' : format;
  const filename = `${briefingName.replace(/[^a-z0-9]/gi, '_')}.${extension}`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Update the synthesis text of a briefing
 */
export async function updateBriefingSynthesis(
  briefingId: number,
  synthesis: string
): Promise<void> {
  const response = await fetch(`/api/desk-briefings/${briefingId}/synthesis`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ synthesis }),
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to update synthesis');
  }
}

/**
 * Update the priority actions of a briefing
 */
export async function updateBriefingPriorityActions(
  briefingId: number,
  priorityActions: BriefingAction[]
): Promise<void> {
  const response = await fetch(`/api/desk-briefings/${briefingId}/priority-actions`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ priority_actions: priorityActions }),
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to update priority actions');
  }
}

/**
 * Reopen a finalized briefing to allow adding more content
 */
export async function reopenBriefing(briefingId: number): Promise<void> {
  const response = await fetch(`/api/desk-briefings/${briefingId}/reopen`, {
    method: 'POST',
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to reopen briefing');
  }
}

/**
 * Add an emerging topic to a briefing
 */
export async function addEmergingTopicToBriefing(
  briefingId: number,
  emergingTopic: {
    name: string;
    summary?: string;
    description?: string;
    why_emerging?: string;
    key_takeaway?: string;
    article_count?: number;
    velocity?: string;
    trend_score?: Record<string, unknown>;
    key_entities?: string[];
    representative_keywords?: string[];
    key_themes?: string[];
    topic?: string;
    // Rich analysis fields
    implications?: Record<string, unknown>;
    organization_implications?: Record<string, unknown>;
    signals?: Record<string, unknown>;
    actors?: Record<string, unknown>;
    events?: Record<string, unknown>;
    // Source articles with links
    source_articles?: Array<{
      title: string;
      url?: string;
      source?: string;
      date?: string;
      summary?: string;
    }>;
  }
): Promise<void> {
  const response = await fetch(`/api/desk-briefings/${briefingId}/emerging-topics`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(emergingTopic),
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to add emerging topic');
  }
}

/**
 * Remove an emerging topic from a briefing
 */
export async function removeEmergingTopicFromBriefing(
  briefingId: number,
  topicName: string
): Promise<void> {
  const response = await fetch(
    `/api/desk-briefings/${briefingId}/emerging-topics/${encodeURIComponent(topicName)}`,
    {
      method: 'DELETE',
      credentials: 'include',
    }
  );

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to remove emerging topic');
  }
}

/**
 * Update the themes of a briefing
 */
export async function updateBriefingThemes(
  briefingId: number,
  themes: BriefingTheme[]
): Promise<void> {
  const response = await fetch(`/api/desk-briefings/${briefingId}/themes`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ themes }),
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to update themes');
  }
}

/**
 * Share a briefing via email
 */
export async function shareBriefingViaEmail(
  briefingId: number,
  toEmail: string,
  options?: {
    includePdf?: boolean;
    message?: string;
  }
): Promise<{ success: boolean; message: string; method: string }> {
  const response = await fetch(`/api/desk-briefings/${briefingId}/share`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      to_email: toEmail,
      include_pdf: options?.includePdf,
      message: options?.message,
    }),
  });

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to share briefing');
  }

  return response.json();
}

/**
 * Download briefing as PDF
 */
export async function downloadBriefingPdf(
  briefingId: number,
  briefingName: string
): Promise<void> {
  const response = await fetch(
    `/api/desk-briefings/${briefingId}/export?format=pdf`,
    {
      credentials: 'include',
    }
  );

  if (!response.ok) {
    const error = await extractErrorMessage(response);
    throw new Error(error || 'Failed to export PDF');
  }

  const blob = await response.blob();
  const filename = `${briefingName.replace(/[^a-z0-9]/gi, '_')}.pdf`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
