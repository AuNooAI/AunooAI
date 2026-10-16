import { api, ApiError } from '../api';

/*
 * Auspex chat on /api/auspex (app/routes/auspex_routes.py). Both streams are SSE: one
 * `data: {json}` line per event, no event names. Chat sends {content}, then {done}, or {error};
 * deep research sends stage updates, report text in `chunk`, then {stage: 'complete', report}.
 */

export const ALL_TOPICS = '__all__';

export interface Session { id: number; topic: string; title: string; created_at?: string; updated_at?: string; message_count?: number }
export interface StoredMessage { id: number; role: 'user' | 'assistant'; content: string; model_used?: string; timestamp?: string; metadata?: unknown }
export interface ModelInfo { id: string; name: string; context_limit?: number }
export interface Insights {
  key_themes?: string[];
  main_findings?: string[];
  sentiment_overview?: string;
  notable_quotes?: string[];
  data_coverage?: { articles_discussed?: number; time_period?: string; sources_mentioned?: number };
}

export const listSessions = (topic: string) =>
  api<{ sessions: Session[] }>(`/api/auspex/chat/sessions?topic=${encodeURIComponent(topic)}`).then((r) => r.sessions ?? []);
export const createSession = (topic: string) =>
  api<{ chat_id: number; title: string }>('/api/auspex/chat/sessions', { method: 'POST', json: { topic } });
export const loadMessages = (chatId: number) =>
  api<{ messages: StoredMessage[] }>(`/api/auspex/chat/sessions/${chatId}/messages`).then((r) => r.messages ?? []);
export const deleteSession = (chatId: number) => api(`/api/auspex/chat/sessions/${chatId}`, { method: 'DELETE' });
export const summarise = (chatId: number) =>
  api<{ insights: Insights | null; message?: string }>('/api/auspex/chat/insights', { method: 'POST', json: { chat_id: chatId } });

/** Reads an SSE response and yields each event's JSON. Non-JSON lines are skipped. */
async function* events(res: Response): AsyncGenerator<Record<string, unknown>> {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      const d = body?.detail;
      msg = typeof d === 'string' ? d : Array.isArray(d) ? d.map((x: { msg?: string }) => x.msg).filter(Boolean).join('. ') : body?.message ?? msg;
    } catch {
      // keep the status text
    }
    if (res.status === 401) window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    throw new ApiError(msg, res.status);
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error('The server sent no response');
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      let parsed: unknown;
      try {
        parsed = JSON.parse(line.slice(6));
      } catch {
        continue;
      }
      if (parsed && typeof parsed === 'object') yield parsed as Record<string, unknown>;
    }
  }
}

export interface ChatRequest {
  chatId: number;
  message: string;
  model: string;
  /** How many articles retrieval returns */
  limit: number;
  /** How many of them are cited in detail (the old chat never sent it, so it was always 25) */
  detailLimit: number;
  samplingStrategy: string | null;
  includeCharts: boolean;
  /** false skips the article store entirely */
  searchArticles: boolean;
}

/** Streams a chat answer as text chunks. A server error ends the stream with an exception. */
export async function* streamChat(r: ChatRequest, signal: AbortSignal): AsyncGenerator<string> {
  const res = await fetch('/api/auspex/chat/message', {
    method: 'POST',
    credentials: 'same-origin',
    signal,
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({
      chat_id: r.chatId,
      message: r.message,
      model: r.model,
      limit: r.limit,
      article_detail_limit: r.detailLimit,
      sampling_strategy: r.samplingStrategy,
      include_charts: r.includeCharts,
      // The server reads only whether any value is true; false for all skips retrieval
      tools_config: r.searchArticles ? { search_articles: true } : { search_articles: false },
    }),
  });
  for await (const e of events(res)) {
    if (typeof e.error === 'string') throw new Error(e.error);
    if (typeof e.content === 'string') yield e.content;
    if (e.done) return;
  }
}

export type ResearchMode = 'internal' | 'hybrid' | 'external';
export interface ResearchUpdate { stage?: string; status?: string; text?: string; report?: string; detail?: string }

const STAGE_WORD: Record<string, string> = {
  exploration: 'Looking at what the topic holds',
  planning: 'Planning the research',
  searching: 'Searching for sources',
  relevance_scoring: 'Checking relevance',
  synthesis: 'Working through the findings',
  writing: 'Writing the report',
};

/** Streams a deep research run: stage lines, report text as it's written, then the final report. */
export async function* streamResearch(
  q: { chatId: number; message: string; topic: string; mode: ResearchMode; includeCharts: boolean },
  signal: AbortSignal,
): AsyncGenerator<ResearchUpdate> {
  const res = await fetch('/api/auspex/research', {
    method: 'POST',
    credentials: 'same-origin',
    signal,
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ query: q.message, topic: q.topic, chat_id: q.chatId, config: { search_source: q.mode, research_mode: q.mode, include_charts: q.includeCharts } }),
  });
  for await (const e of events(res)) {
    if (typeof e.error === 'string') throw new Error(e.error);
    const stage = typeof e.stage === 'string' ? e.stage : undefined;
    if (stage === 'complete' && typeof e.report === 'string') {
      yield { stage, report: e.report };
      continue;
    }
    if (typeof e.chunk === 'string') yield { stage, text: e.chunk };
    if (stage && STAGE_WORD[stage]) {
      const extra = [
        e.articles_found != null && `${e.articles_found} articles`,
        e.remaining_count != null && `${e.remaining_count} kept`,
        e.objectives_count != null && `${e.objectives_count} objectives`,
        e.confidence != null && `confidence ${e.confidence}`,
      ].filter(Boolean).join(', ');
      yield { stage, status: String(e.status ?? ''), detail: `${STAGE_WORD[stage]}${e.status === 'completed' ? ': done' : '…'}${extra ? ` (${extra})` : ''}` };
    }
    if (e.done) return;
  }
}
