/**
 * Research Agents API Service
 * Connects React frontend to FastAPI backend for signal instructions (Research Agents)
 */

// Types
export interface ResearchAgent {
  id: number;
  name: string;
  description: string;
  instruction: string;
  topic: string | null;
  is_active: boolean;
  generate_report: boolean;
  report_prompt: string | null;
  config: Record<string, unknown> | null;
  created_at?: string;
}

export interface SignalAlert {
  id: number;
  instruction_id: number;
  instruction_name: string;
  article_uri: string;
  article_title: string;
  article_source?: string;
  article_date?: string;
  threat_level: 'high' | 'medium' | 'low';
  reasoning: string;
  acknowledged: boolean;
  created_at: string;
}

export interface SignalReport {
  id: number;
  instruction_id: number | null;
  instruction_name: string;
  name: string;
  description: string | null;
  topic: string | null;
  report_prompt: string | null;
  report_content: string | null;
  alerts_data: SignalAlert[] | null;
  article_uris: string[] | null;
  articles_used: number | null;
  config: Record<string, unknown> | null;
  model_used: string | null;
  created_at: string;
}

export interface CreateAgentRequest {
  name: string;
  description: string;
  instruction: string;
  topic?: string | null;
  is_active?: boolean;
  generate_report?: boolean;
  report_prompt?: string | null;
  config?: Record<string, unknown> | null;
}

export interface UpdateAgentRequest {
  name?: string;
  description?: string;
  instruction?: string;
  topic?: string | null;
  is_active?: boolean;
  generate_report?: boolean;
  report_prompt?: string | null;
  config?: Record<string, unknown> | null;
}

export interface RunAgentsRequest {
  instruction_ids: number[];
  topic?: string | null;
  days_back?: number;
  max_articles?: number;
  model?: string;
  tag_flagged_articles?: boolean;
  generate_report?: boolean;
  report_prompt?: string | null;
  report_name?: string | null;
}

export interface RunAgentsResponse {
  success: boolean;
  message: string;
  alerts_created: SignalAlert[];
  instructions_run: number;
  total_matches: number;
  articles_analyzed: number;
  analysis_period: string;
  report?: {
    id: number;
    name: string;
    content: string;
    articles_used: number;
  } | null;
}

// API Configuration
const API_BASE_URL = '';

/**
 * Fetch with authentication and error handling
 */
async function fetchWithAuth<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  try {
    const response = await fetch(url, {
      ...options,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (response.status === 401 || response.status === 403) {
      window.location.href = '/login';
      throw new Error('Authentication required');
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Research Agents API Error:', error);
    throw error;
  }
}

/**
 * Get all research agents (signal instructions)
 */
export async function getResearchAgents(params?: {
  topic?: string;
  activeOnly?: boolean;
}): Promise<{ instructions: ResearchAgent[]; count: number }> {
  const queryParams = new URLSearchParams();

  if (params?.topic) {
    queryParams.append('topic', params.topic);
  }
  if (params?.activeOnly !== undefined) {
    queryParams.append('active_only', String(params.activeOnly));
  }

  const url = `${API_BASE_URL}/api/signal-instructions?${queryParams}`;
  return fetchWithAuth(url);
}

/**
 * Create a new research agent
 */
export async function createResearchAgent(
  agent: CreateAgentRequest
): Promise<{ success: boolean; message: string }> {
  return fetchWithAuth(`${API_BASE_URL}/api/signal-instructions`, {
    method: 'POST',
    body: JSON.stringify({
      name: agent.name,
      description: agent.description,
      instruction: agent.instruction,
      topic: agent.topic || null,
      is_active: agent.is_active !== false,
      generate_report: agent.generate_report || false,
      report_prompt: agent.report_prompt || null,
      config: agent.config || null,
    }),
  });
}

/**
 * Delete a research agent
 */
export async function deleteResearchAgent(
  agentId: number
): Promise<{ success: boolean; message: string }> {
  return fetchWithAuth(`${API_BASE_URL}/api/signal-instructions/${agentId}`, {
    method: 'DELETE',
  });
}

/**
 * Update a research agent
 */
export async function updateResearchAgent(
  agentId: number,
  updates: UpdateAgentRequest
): Promise<{ success: boolean; message: string }> {
  return fetchWithAuth(`${API_BASE_URL}/api/signal-instructions/${agentId}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

/**
 * Run specific research agents against recent articles
 */
export async function runResearchAgents(
  request: RunAgentsRequest
): Promise<RunAgentsResponse> {
  return fetchWithAuth(`${API_BASE_URL}/api/run-signals`, {
    method: 'POST',
    body: JSON.stringify({
      instruction_ids: request.instruction_ids,
      topic: request.topic || null,
      days_back: request.days_back || 7,
      max_articles: request.max_articles || 100,
      model: request.model || 'gpt-4o-mini',
      tag_flagged_articles: request.tag_flagged_articles !== false,
      generate_report: request.generate_report || false,
      report_prompt: request.report_prompt || null,
      report_name: request.report_name || null,
    }),
  });
}

/**
 * Get signal alerts
 */
export async function getSignalAlerts(params?: {
  topic?: string;
  instructionId?: number;
  acknowledged?: boolean | null;
  limit?: number;
}): Promise<{ alerts: SignalAlert[]; total: number }> {
  const queryParams = new URLSearchParams();

  if (params?.topic) {
    queryParams.append('topic', params.topic);
  }
  if (params?.instructionId !== undefined) {
    queryParams.append('instruction_id', String(params.instructionId));
  }
  if (params?.acknowledged !== undefined && params?.acknowledged !== null) {
    queryParams.append('acknowledged', String(params.acknowledged));
  }
  if (params?.limit) {
    queryParams.append('limit', String(params.limit));
  }

  const url = `${API_BASE_URL}/api/signal-alerts?${queryParams}`;
  return fetchWithAuth(url);
}

/**
 * Acknowledge a signal alert
 */
export async function acknowledgeAlert(
  alertId: number
): Promise<{ success: boolean; message: string }> {
  return fetchWithAuth(`${API_BASE_URL}/api/acknowledge-alert/${alertId}`, {
    method: 'POST',
  });
}

/**
 * Acknowledge all alerts for a specific instruction or topic
 */
export async function acknowledgeAllAlerts(params?: {
  instructionId?: number;
  topic?: string;
}): Promise<{ success: boolean; acknowledged_count: number }> {
  // First get all unacknowledged alerts
  const alerts = await getSignalAlerts({
    ...params,
    acknowledged: false,
    limit: 1000,
  });

  // Acknowledge each one
  let acknowledgedCount = 0;
  for (const alert of alerts.alerts) {
    try {
      await acknowledgeAlert(alert.id);
      acknowledgedCount++;
    } catch (error) {
      console.error(`Failed to acknowledge alert ${alert.id}:`, error);
    }
  }

  return {
    success: true,
    acknowledged_count: acknowledgedCount,
  };
}

// ========================================================================
// Signal Reports API
// ========================================================================

/**
 * Get all signal reports
 */
export async function getSignalReports(params?: {
  topic?: string;
  instructionId?: number;
  limit?: number;
}): Promise<{ reports: SignalReport[]; total: number }> {
  const queryParams = new URLSearchParams();

  if (params?.topic) {
    queryParams.append('topic', params.topic);
  }
  if (params?.instructionId !== undefined) {
    queryParams.append('instruction_id', String(params.instructionId));
  }
  if (params?.limit) {
    queryParams.append('limit', String(params.limit));
  }

  const url = `${API_BASE_URL}/api/signal-reports?${queryParams}`;
  return fetchWithAuth(url);
}

/**
 * Get a specific signal report by ID
 */
export async function getSignalReportById(
  reportId: number
): Promise<{ success: boolean; report: SignalReport }> {
  return fetchWithAuth(`${API_BASE_URL}/api/signal-reports/${reportId}`);
}

/**
 * Delete a signal report
 */
export async function deleteSignalReport(
  reportId: number
): Promise<{ success: boolean; message: string }> {
  return fetchWithAuth(`${API_BASE_URL}/api/signal-reports/${reportId}`, {
    method: 'DELETE',
  });
}

/**
 * Get count of signal reports
 */
export async function getSignalReportsCount(params?: {
  topic?: string;
}): Promise<{ success: boolean; count: number }> {
  const queryParams = new URLSearchParams();

  if (params?.topic) {
    queryParams.append('topic', params.topic);
  }

  const url = `${API_BASE_URL}/api/signal-reports-count?${queryParams}`;
  return fetchWithAuth(url);
}
