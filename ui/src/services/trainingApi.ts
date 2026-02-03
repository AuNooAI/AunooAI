/**
 * API client for Adaptive Classification Training System endpoints
 */

// Types

export interface FieldStatus {
  field_name: string;
  sample_count: number;
  status: 'red' | 'yellow' | 'green';
  threshold_green: number;
  threshold_yellow: number;
}

export interface TopicTrainingStatus {
  topic: string;
  article_count: number;
  total_samples: number;
  field_counts: Record<string, number>;
  field_readiness: Record<string, 'red' | 'yellow' | 'green'>;
  overall_status: 'ready' | 'partial' | 'marginal' | 'not_ready';
}

export interface FieldDistribution {
  topic: string;
  field_name: string;
  total_samples: number;
  unique_values: number;
  distribution: Array<{
    value: string;
    count: number;
    percentage: number;
  }>;
  min_per_class_met: boolean;
}

export interface TrainingReadiness {
  ready: boolean;
  total_samples: number;
  min_required: number;
  topics_count: number;
  ready_topics_count: number;
  ready_topics: string[];
  green_fields_count: number;
}

export interface TrainingRun {
  run_id: string;
  status: 'pending' | 'running' | 'exporting' | 'training' | 'completed' | 'failed' | 'deployed';
  topics_included: string[] | null;
  fields_included: string[] | null;
  sample_count: number | null;
  metrics: Record<string, number> | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  error_message: string | null;
  model_path?: string | null;
}

export interface RoutingField {
  model: 'deberta' | 'qwen' | 'llm_bootstrap';
  status: 'red' | 'yellow' | 'green';
  sample_count: number;
  threshold_green: number;
  threshold_yellow: number;
}

export interface RoutingStatus {
  topic: string;
  fields: Record<string, RoutingField>;
  deberta_available: boolean;
  qwen_available: boolean;
}

export interface TrainingThresholds {
  red: number;
  yellow: number;
  green: number;
  min_per_class: number;
  finetune_min: number;
}

export interface FieldConfidenceStats {
  avg: number;
  min: number;
  max: number;
  count: number;
  above_threshold_pct: number;
}

export interface TopicConfidenceStats {
  fields: Record<string, FieldConfidenceStats>;
  overall_avg: number;
  total_readings: number;
  above_threshold_pct: number;
}

export interface ConfidenceStatsResponse {
  stats: Record<string, TopicConfidenceStats>;
  threshold: number;
  window_hours: number;
}

export interface RelevanceTopicStats {
  total_readings: number;
  avg_score: number;
  min_score: number;
  max_score: number;
  avg_classifier: number | null;
  avg_embedding: number | null;
  relevant_pct: number;
  method_breakdown: Record<string, number>;
  high_confidence_pct: number;
}

export interface RelevanceConfidenceStatsResponse {
  stats: Record<string, RelevanceTopicStats>;
  relevance_threshold: number;
  confidence_threshold: number;
  window_hours: number;
}

// API Functions

const API_BASE = '/api/training';

/**
 * Get sample counts per topic per field
 */
export async function getSampleCounts(topic?: string): Promise<{
  counts: Record<string, Record<string, number>>;
  thresholds: TrainingThresholds;
}> {
  const url = topic
    ? `${API_BASE}/sample-counts?topic=${encodeURIComponent(topic)}`
    : `${API_BASE}/sample-counts`;

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to get sample counts: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get training status for all topics
 */
export async function getTopicsTrainingStatus(): Promise<TopicTrainingStatus[]> {
  const response = await fetch(`${API_BASE}/topics-status`);
  if (!response.ok) {
    throw new Error(`Failed to get topics status: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get training status for a specific topic
 */
export async function getTopicStatus(topic: string): Promise<TopicTrainingStatus> {
  const response = await fetch(`${API_BASE}/topic-status/${encodeURIComponent(topic)}`);
  if (!response.ok) {
    throw new Error(`Failed to get topic status: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get value distribution for a specific field
 */
export async function getFieldDistribution(
  topic: string,
  field: string
): Promise<FieldDistribution> {
  const response = await fetch(
    `${API_BASE}/field-distribution/${encodeURIComponent(topic)}/${encodeURIComponent(field)}`
  );
  if (!response.ok) {
    throw new Error(`Failed to get field distribution: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Check training readiness
 */
export async function checkReadiness(topics?: string[]): Promise<TrainingReadiness> {
  const url = topics?.length
    ? `${API_BASE}/readiness?topics=${topics.join(',')}`
    : `${API_BASE}/readiness`;

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to check readiness: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Trigger a finetuning run
 */
export async function triggerFinetuning(
  topics?: string[],
  fields?: string[]
): Promise<{
  run_id: string;
  status: string;
  topics_included: string[];
  sample_count: number;
}> {
  const response = await fetch(`${API_BASE}/trigger-finetune`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topics, fields }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to trigger finetuning: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Trigger relevance classifier training using user feedback
 */
export async function triggerRelevanceTraining(): Promise<{
  status: string;
  message: string;
  feedback_count: number;
}> {
  const response = await fetch(`${API_BASE}/trigger-relevance-training`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to trigger relevance training: ${response.statusText}`);
  }
  return response.json();
}

/**
 * List training runs
 */
export async function getTrainingRuns(
  status?: string,
  limit = 20
): Promise<TrainingRun[]> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  params.set('limit', limit.toString());

  const response = await fetch(`${API_BASE}/runs?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to list runs: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get status of a specific training run
 */
export async function getRunStatus(runId: string): Promise<TrainingRun> {
  const response = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}`);
  if (!response.ok) {
    throw new Error(`Failed to get run status: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Deploy a trained model
 */
export async function deployModel(runId: string): Promise<{ status: string; run_id: string }> {
  const response = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/deploy`, {
    method: 'POST',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to deploy model: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Delete a training run
 */
export async function deleteRun(runId: string): Promise<{ status: string; run_id: string }> {
  const response = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to delete run: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Rollback to previous model
 */
export async function rollbackModel(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/rollback`, {
    method: 'POST',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to rollback: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get routing status for a topic
 */
export async function getRoutingStatus(topic: string): Promise<RoutingStatus> {
  const response = await fetch(`${API_BASE}/routing/${encodeURIComponent(topic)}`);
  if (!response.ok) {
    throw new Error(`Failed to get routing status: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get training thresholds
 */
export async function getThresholds(): Promise<TrainingThresholds> {
  const response = await fetch(`${API_BASE}/thresholds`);
  if (!response.ok) {
    throw new Error(`Failed to get thresholds: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get overall training system status
 */
export async function getTrainingSystemStatus(): Promise<{
  bootstrap_thresholds: TrainingThresholds;
  finetuning: {
    models_dir: string;
    current_model_exists: boolean;
    backup_model_exists: boolean;
    thresholds: TrainingThresholds;
  };
  hybrid_enrichment: {
    deberta_available: boolean;
    qwen_available: boolean;
    thresholds: TrainingThresholds;
    enrichment_fields: string[];
  };
}> {
  const response = await fetch(`${API_BASE}/status`);
  if (!response.ok) {
    throw new Error(`Failed to get status: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get DeBERTa model confidence stats for the last 24 hours
 */
export async function getConfidenceStats(topic?: string): Promise<ConfidenceStatsResponse> {
  const url = topic
    ? `${API_BASE}/confidence-stats?topic=${encodeURIComponent(topic)}`
    : `${API_BASE}/confidence-stats`;

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to get confidence stats: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get relevance scoring confidence stats for the last 24 hours
 */
export async function getRelevanceConfidenceStats(topic?: string): Promise<RelevanceConfidenceStatsResponse> {
  const url = topic
    ? `${API_BASE}/relevance-confidence-stats?topic=${encodeURIComponent(topic)}`
    : `${API_BASE}/relevance-confidence-stats`;

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to get relevance confidence stats: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// User Relevance Feedback
// ============================================================================

export interface RelevanceFeedbackRequest {
  article_uri: string;
  topic: string;
  feedback_type: 'more_like_this' | 'less_like_this';
  relevance_score?: number;
  classifier_score?: number;
  embedding_score?: number;
  article_metadata?: Record<string, unknown>;
}

export interface RelevanceFeedbackResponse {
  id: number;
  article_uri: string;
  topic: string;
  feedback_type: string;
  created_at: string;
}

export interface RelevanceFeedbackRecord {
  id: number;
  article_uri: string;
  topic: string;
  user_id: string | null;
  feedback_type: string;
  relevance_score: number | null;
  classifier_score: number | null;
  embedding_score: number | null;
  article_metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface RelevanceFeedbackListResponse {
  feedback: RelevanceFeedbackRecord[];
  total: number;
  limit: number;
  offset: number;
}

export interface RelevanceFeedbackStats {
  by_topic: Array<{
    topic: string;
    total_feedback: number;
    more_like_this: number;
    less_like_this: number;
    recent_feedback: number;
  }>;
  totals: {
    total_feedback: number;
    more_like_this: number;
    less_like_this: number;
  };
}

export interface ArticleFeedbackResponse {
  has_feedback: boolean;
  feedback: {
    id: number;
    topic: string;
    user_id: string | null;
    feedback_type: string;
    created_at: string;
  } | null;
}

export interface PipelineStats {
  articles_today: number;
  relevance_passed: number;
  topics_active: number;
  inference_mode: InferenceMode;
}

/**
 * Record user relevance feedback ("more like this" / "less like this")
 */
export async function recordRelevanceFeedback(
  request: RelevanceFeedbackRequest
): Promise<RelevanceFeedbackResponse> {
  const response = await fetch(`${API_BASE}/relevance-feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to record feedback: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get relevance feedback records
 */
export async function getRelevanceFeedback(params?: {
  topic?: string;
  feedback_type?: string;
  limit?: number;
  offset?: number;
}): Promise<RelevanceFeedbackListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.topic) searchParams.set('topic', params.topic);
  if (params?.feedback_type) searchParams.set('feedback_type', params.feedback_type);
  if (params?.limit) searchParams.set('limit', params.limit.toString());
  if (params?.offset) searchParams.set('offset', params.offset.toString());

  const url = `${API_BASE}/relevance-feedback?${searchParams}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Failed to get feedback: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get aggregated feedback stats
 */
export async function getRelevanceFeedbackStats(
  topic?: string
): Promise<RelevanceFeedbackStats> {
  const url = topic
    ? `${API_BASE}/relevance-feedback/stats?topic=${encodeURIComponent(topic)}`
    : `${API_BASE}/relevance-feedback/stats`;

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to get feedback stats: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Delete a feedback record
 */
export async function deleteRelevanceFeedback(feedbackId: number): Promise<void> {
  const response = await fetch(`${API_BASE}/relevance-feedback/${feedbackId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to delete feedback: ${response.statusText}`);
  }
}

/**
 * Get feedback for a specific article
 */
export async function getArticleFeedback(
  articleUri: string
): Promise<ArticleFeedbackResponse> {
  const response = await fetch(
    `${API_BASE}/relevance-feedback/article/${encodeURIComponent(articleUri)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to get article feedback: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get article processing pipeline stats for today
 */
export async function getPipelineStats(): Promise<PipelineStats> {
  const response = await fetch(`${API_BASE}/pipeline-stats`);
  if (!response.ok) {
    throw new Error(`Failed to get pipeline stats: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Model Configuration
// ============================================================================

export interface ModelInfo {
  name: string;
  type: 'local' | 'external';
  status: 'available' | 'unavailable';
  latency: string | null;
  description: string;
  tooltip: string;
  port: number | null;
  cost: string;
  usage: string | null;
}

export interface ModelConfig {
  local_models: ModelInfo[];
  external_models: ModelInfo[];
}

export interface CostSavingsStats {
  total_articles: number;
  local_model_count: number;
  llm_fallback_count: number;
  local_percentage: number;
  estimated_llm_cost: number;
  actual_llm_cost: number;
  savings_amount: number;
  savings_percentage: number;
  method_breakdown: Record<string, number>;
  window_hours: number;
}

/**
 * Get the current model configuration
 */
export async function getModelConfig(): Promise<ModelConfig> {
  const response = await fetch(`${API_BASE}/model-config`);
  if (!response.ok) {
    throw new Error(`Failed to get model config: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get cost savings statistics based on actual model usage
 */
export async function getCostSavings(hours = 24): Promise<CostSavingsStats> {
  const response = await fetch(`${API_BASE}/cost-savings?hours=${hours}`);
  if (!response.ok) {
    throw new Error(`Failed to get cost savings: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Inference Mode Settings
// ============================================================================

export type InferenceMode = 'local' | 'hybrid' | 'external';

export interface InferenceModeResponse {
  mode: InferenceMode;
}

/**
 * Get the current inference mode setting
 */
export async function getInferenceMode(): Promise<InferenceModeResponse> {
  const response = await fetch(`${API_BASE}/inference-mode`);
  if (!response.ok) {
    throw new Error(`Failed to get inference mode: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Set the inference mode
 * @param mode - 'local' (DeBERTa only), 'hybrid' (DeBERTa + GPT fallback), or 'external' (GPT only)
 */
export async function setInferenceMode(mode: InferenceMode): Promise<{ success: boolean; mode: InferenceMode }> {
  const response = await fetch(`${API_BASE}/inference-mode`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to set inference mode: ${response.statusText}`);
  }
  return response.json();
}

export interface LocalModelsStatus {
  available: boolean;
  models: Record<string, { available: boolean; name: string; error: string | null; configured_models?: string[] }>;
  missing: string[];
  external_llm_available: boolean;
}

/**
 * Check if local models are available for 'local' inference mode
 */
export async function getLocalModelsStatus(): Promise<LocalModelsStatus> {
  const response = await fetch(`${API_BASE}/local-models-status`);
  if (!response.ok) {
    throw new Error(`Failed to get local models status: ${response.statusText}`);
  }
  return response.json();
}
