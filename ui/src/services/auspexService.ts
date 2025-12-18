/**
 * Auspex Chat Service - API calls for the Auspex AI assistant
 */

const API_BASE = '/api/auspex';

// Types
export interface Topic {
  name: string;
  display_name: string;
}

export interface Model {
  id: string;
  name: string;
  provider?: string;
}

export interface ChatSession {
  id: number;
  topic: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  model_used?: string;
}

export interface PluginTool {
  name: string;
  display_name: string;
  description: string;
  enabled: boolean;
  category?: string;
}

// Model context limits (in tokens)
const MODEL_CONTEXT_LIMITS: Record<string, number> = {
  'gpt-4o': 128000,
  'gpt-4o-mini': 128000,
  'gpt-4.1': 128000,
  'gpt-4.1-mini': 128000,
  'gpt-4-turbo': 128000,
  'gpt-4': 8192,
  'gpt-3.5-turbo': 16385,
  'claude-3-opus': 200000,
  'claude-3-sonnet': 200000,
  'claude-3-haiku': 200000,
  'claude-3.5-sonnet': 200000,
  'claude-sonnet-4': 200000,
  'default': 128000
};

export function getModelContextLimit(modelId: string): number {
  if (!modelId) return MODEL_CONTEXT_LIMITS.default;

  // Check for exact match first
  if (MODEL_CONTEXT_LIMITS[modelId]) {
    return MODEL_CONTEXT_LIMITS[modelId];
  }

  // Check for partial matches
  const lowerModel = modelId.toLowerCase();
  for (const [key, value] of Object.entries(MODEL_CONTEXT_LIMITS)) {
    if (lowerModel.includes(key.toLowerCase())) {
      return value;
    }
  }

  return MODEL_CONTEXT_LIMITS.default;
}

// API Functions

export async function getTopics(): Promise<Topic[]> {
  const response = await fetch('/api/topics');
  if (!response.ok) throw new Error('Failed to fetch topics');
  const data = await response.json();
  // API returns list directly, not {topics: [...]}
  const topics = Array.isArray(data) ? data : (data.topics || []);
  // Transform to ensure each topic has display_name
  return topics.map((t: any) => ({
    name: t.name,
    display_name: t.display_name || t.name
  }));
}

export async function getModels(): Promise<Model[]> {
  const response = await fetch('/api/auto-ingest/models');
  if (!response.ok) throw new Error('Failed to fetch models');
  const data = await response.json();
  // Transform to ensure each model has an id
  return (data.models || []).map((m: any) => ({
    id: m.id || m.name,
    name: m.name,
    provider: m.provider
  }));
}

export async function createChatSession(topic: string, model: string): Promise<ChatSession> {
  const response = await fetch(`${API_BASE}/chat/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, model })
  });
  if (!response.ok) throw new Error('Failed to create chat session');
  const data = await response.json();
  // Backend returns chat_id, transform to id for interface
  return {
    id: data.chat_id,
    topic: data.topic,
    title: data.title,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  };
}

export async function getChatSessions(topic?: string): Promise<ChatSession[]> {
  const url = topic ? `${API_BASE}/chat/sessions?topic=${encodeURIComponent(topic)}` : `${API_BASE}/chat/sessions`;
  const response = await fetch(url);
  if (!response.ok) throw new Error('Failed to fetch chat sessions');
  const data = await response.json();
  return data.sessions || [];
}

export async function getChatMessages(chatId: number): Promise<Message[]> {
  const response = await fetch(`${API_BASE}/chat/sessions/${chatId}/messages`);
  if (!response.ok) throw new Error('Failed to fetch chat messages');
  const data = await response.json();
  return data.messages || [];
}

export async function deleteChatSession(chatId: number): Promise<void> {
  const response = await fetch(`${API_BASE}/chat/sessions/${chatId}`, {
    method: 'DELETE'
  });
  if (!response.ok) throw new Error('Failed to delete chat session');
}

export interface SendMessageParams {
  chatId: number;
  message: string;
  model: string;
  topic?: string;
  sampleSizeMode?: string;
  samplingStrategy?: string;
  customLimit?: number;
  toolsConfig?: Record<string, boolean>;
  includeCharts?: boolean;
}

export type ResearchMode = 'off' | 'internal' | 'hybrid' | 'external';

export interface DeepResearchParams {
  chatId: number;
  message: string;
  topic: string;
  researchMode: ResearchMode;
  includeCharts?: boolean;
}

export async function* sendChatMessage(params: SendMessageParams): AsyncGenerator<string> {
  const response = await fetch(`${API_BASE}/chat/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: params.chatId,
      message: params.message,
      model: params.model,
      limit: params.customLimit,
      sampling_strategy: params.samplingStrategy,
      tools_config: params.toolsConfig,
      include_charts: params.includeCharts || false
    })
  });

  if (!response.ok) {
    throw new Error(`Failed to send message: ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

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
        const data = line.slice(6);
        if (data === '[DONE]') {
          return;
        }
        try {
          const parsed = JSON.parse(data);
          if (parsed.content) {
            yield parsed.content;
          } else if (parsed.error) {
            throw new Error(parsed.error);
          }
        } catch {
          // If not JSON, yield as raw content
          if (data && data !== '[DONE]') {
            yield data;
          }
        }
      }
    }
  }
}

export async function getPluginTools(): Promise<PluginTool[]> {
  const response = await fetch(`${API_BASE}/plugin-tools`);
  if (!response.ok) throw new Error('Failed to fetch plugin tools');
  const data = await response.json();
  return data.tools || [];
}

// Stage labels for deep research progress display
const STAGE_LABELS: Record<string, string> = {
  planning: '🎯 Planning research approach...',
  searching: '🔍 Searching for sources...',
  synthesis: '🧠 Synthesizing findings...',
  writing: '✍️ Writing report...',
  complete: '✅ Research complete'
};

export async function* startDeepResearch(params: DeepResearchParams): AsyncGenerator<string> {
  const response = await fetch(`${API_BASE}/research`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: params.message,
      topic: params.topic,
      chat_id: params.chatId,
      config: {
        search_source: params.researchMode,
        research_mode: params.researchMode,
        include_charts: params.includeCharts || false
      }
    })
  });

  if (!response.ok) {
    throw new Error(`Failed to start research: ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';
  let currentStage = '';
  let statusContent = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Process complete SSE events
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (data === '[DONE]') {
          return;
        }
        try {
          const parsed = JSON.parse(data);

          // Handle errors first
          if (parsed.error) {
            yield `\n\n❌ **Error:** ${parsed.error}\n\n`;
            continue;
          }

          // Handle stage progress updates
          if (parsed.stage && parsed.stage !== 'complete') {
            const stageLabel = STAGE_LABELS[parsed.stage] || parsed.stage;

            // Only yield if stage changed or status is 'started'
            if (parsed.stage !== currentStage || parsed.status === 'started') {
              currentStage = parsed.stage;
              statusContent = `**${stageLabel}**`;
              yield statusContent + '\n\n';
            }

            // When stage completes, add summary
            if (parsed.status === 'completed') {
              let completionMsg = `✓ ${parsed.stage} completed`;
              if (parsed.objectives_count) completionMsg += ` (${parsed.objectives_count} objectives)`;
              if (parsed.articles_found) completionMsg += ` (${parsed.articles_found} articles)`;
              if (parsed.confidence) completionMsg += ` (confidence: ${parsed.confidence})`;
              yield completionMsg + '\n\n';
            }
          }

          // Handle final report - this is the main content
          if (parsed.stage === 'complete' && parsed.report) {
            // Debug: Check if report contains chart markers
            const hasChartMarker = parsed.report.includes('<!-- CHART_DATA:');
            console.log('[Auspex Service] Received complete report, hasChartMarker:', hasChartMarker);
            if (hasChartMarker) {
              console.log('[Auspex Service] Report preview:', parsed.report.substring(0, 800));
            }
            yield '\n---\n\n';
            yield parsed.report;
          }

          // Handle streaming content field
          if (parsed.content) {
            yield parsed.content;
          }

          // Handle done signal
          if (parsed.done) {
            return;
          }
        } catch {
          // JSON parse error - skip malformed data
          console.warn('Failed to parse SSE data:', data);
        }
      }
    }
  }
}
