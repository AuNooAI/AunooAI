/**
 * Training Status Tab
 *
 * Main tab component for viewing training sample status and triggering finetuning.
 * Part of the Gather page for the Adaptive Classification Training System.
 *
 * Two-tier system:
 * - GPT (gpt-4o-mini): Used when < 500 samples, stores results for training
 * - DeBERTa: Used when >= 500 samples, fast and free
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { RefreshCw, Zap, AlertCircle, CheckCircle2, Info, Cpu, Play, Loader2, XCircle, Trash2, FileText, Download, Target, Folder, FlaskConical, Tag, Database, FolderOpen, Rss, Check, Hash, HelpCircle, Star } from 'lucide-react';
import { TopicTrainingCard } from './TopicTrainingCard';
import {
  getTopicsTrainingStatus,
  checkReadiness,
  triggerFinetuning,
  triggerRelevanceTraining,
  getTrainingRuns,
  getThresholds,
  deployModel,
  deleteRun,
  getConfidenceStats,
  getRelevanceConfidenceStats,
  getRelevanceFeedbackStats,
  getTrainingSystemStatus,
  getPipelineStats,
  getModelConfig,
  getCostSavings,
  type TopicTrainingStatus,
  type TrainingReadiness,
  type TrainingRun,
  type TrainingThresholds,
  type ConfidenceStatsResponse,
  type RelevanceConfidenceStatsResponse,
  type RelevanceFeedbackStats,
  type PipelineStats,
  type ModelConfig,
  type CostSavingsStats,
} from '../../services/trainingApi';
import { Alert, AlertDescription } from '../ui/alert';

const DEBERTA_THRESHOLD = 500;

interface SystemStatus {
  bootstrap_thresholds: TrainingThresholds;
  finetuning: {
    models_dir: string;
    current_model_exists: boolean;
    backup_model_exists: boolean;
    thresholds: TrainingThresholds;
  };
  hybrid_enrichment: {
    deberta_available: boolean;
    deberta_threshold: number;
    enrichment_fields: string[];
    bootstrap_model: string;
  };
}

export function TrainingStatusTab() {
  const [topics, setTopics] = useState<TopicTrainingStatus[]>([]);
  const [readiness, setReadiness] = useState<TrainingReadiness | null>(null);
  const [thresholds, setThresholds] = useState<TrainingThresholds | null>(null);
  const [recentRuns, setRecentRuns] = useState<TrainingRun[]>([]);
  const [confidenceStats, setConfidenceStats] = useState<ConfidenceStatsResponse | null>(null);
  const [relevanceConfidenceStats, setRelevanceConfidenceStats] = useState<RelevanceConfidenceStatsResponse | null>(null);
  const [feedbackStats, setFeedbackStats] = useState<RelevanceFeedbackStats | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [pipelineStats, setPipelineStats] = useState<PipelineStats | null>(null);
  const [modelConfig, setModelConfig] = useState<ModelConfig | null>(null);
  const [costSavings, setCostSavings] = useState<CostSavingsStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [relevanceTraining, setRelevanceTraining] = useState(false);
  const [deploying, setDeploying] = useState<string | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [topicsData, readinessData, thresholdsData, runsData, confidenceData, relevanceConfData, feedbackData, statusData, pipelineData, modelConfigData, costSavingsData] = await Promise.all([
        getTopicsTrainingStatus(),
        checkReadiness(),
        getThresholds(),
        getTrainingRuns(undefined, 10),
        getConfidenceStats().catch(() => null),
        getRelevanceConfidenceStats().catch(() => null),
        getRelevanceFeedbackStats().catch(() => null),
        getTrainingSystemStatus().catch(() => null),
        getPipelineStats().catch(() => null),
        getModelConfig().catch(() => null),
        getCostSavings().catch(() => null),
      ]);

      setTopics(topicsData);
      setReadiness(readinessData);
      setThresholds(thresholdsData);
      setRecentRuns(runsData);
      setConfidenceStats(confidenceData);
      setRelevanceConfidenceStats(relevanceConfData);
      setFeedbackStats(feedbackData);
      setSystemStatus(statusData);
      setPipelineStats(pipelineData);
      setModelConfig(modelConfigData);
      setCostSavings(costSavingsData);
    } catch (err) {
      console.error('Failed to load training data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load training data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [loadData]);

  // Poll for active run status updates
  useEffect(() => {
    const hasActiveRun = recentRuns.some(r =>
      ['pending', 'running', 'exporting', 'training'].includes(r.status)
    );

    if (hasActiveRun && !pollIntervalRef.current) {
      pollIntervalRef.current = setInterval(async () => {
        const runs = await getTrainingRuns(undefined, 10);
        setRecentRuns(runs);

        if (!runs.some(r => ['pending', 'running', 'exporting', 'training'].includes(r.status))) {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
          loadData();
        }
      }, 3000);
    } else if (!hasActiveRun && pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, [recentRuns, loadData]);

  const handleTriggerFinetune = async (topic?: string) => {
    setTriggering(true);
    setError(null);
    try {
      const topics_param = topic ? [topic] : undefined;
      const result = await triggerFinetuning(topics_param);
      await loadData();
      alert(`Finetuning started! Run ID: ${result.run_id}\nTopics: ${result.topics_included.join(', ')}\nSamples: ${result.sample_count}`);
    } catch (err) {
      console.error('Failed to trigger finetuning:', err);
      setError(err instanceof Error ? err.message : 'Failed to trigger finetuning');
    } finally {
      setTriggering(false);
    }
  };

  const handleTriggerRelevanceTraining = async () => {
    setRelevanceTraining(true);
    setError(null);
    try {
      const result = await triggerRelevanceTraining();
      alert(`${result.message}\nFeedback samples: ${result.feedback_count}`);
      await loadData();
    } catch (err) {
      console.error('Failed to trigger relevance training:', err);
      setError(err instanceof Error ? err.message : 'Failed to trigger relevance training');
    } finally {
      setRelevanceTraining(false);
    }
  };

  const handleDeploy = async (runId: string) => {
    setDeploying(runId);
    setError(null);
    try {
      await deployModel(runId);
      setRecentRuns(prev => prev.map(run =>
        run.run_id === runId ? { ...run, status: 'deployed' as const } : run
      ));
      const runs = await getTrainingRuns(undefined, 10);
      setRecentRuns(runs);
    } catch (err) {
      console.error('Failed to deploy model:', err);
      setError(err instanceof Error ? err.message : 'Failed to deploy model');
    } finally {
      setDeploying(null);
    }
  };

  const handleDelete = async (runId: string) => {
    if (!confirm(`Delete training run ${runId}? This cannot be undone.`)) return;
    setError(null);
    try {
      await deleteRun(runId);
      await loadData();
    } catch (err) {
      console.error('Failed to delete run:', err);
      setError(err instanceof Error ? err.message : 'Failed to delete run');
    }
  };

  if (loading) {
    return (
      <div className="training-status-tab p-6">
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-6 h-6 animate-spin text-gray-400 mr-2" />
          <span className="text-gray-500">Loading training status...</span>
        </div>
      </div>
    );
  }

  const totalSamples = topics.reduce((sum, t) => sum + t.total_samples, 0);
  const fullyReadyTopics = topics.filter(t => {
    const fields = Object.values(t.field_counts);
    return fields.length >= 4 && fields.every(count => count >= DEBERTA_THRESHOLD);
  });
  const bootstrappingTopics = topics.filter(t => {
    const fields = Object.values(t.field_counts);
    return fields.every(count => count < DEBERTA_THRESHOLD);
  });
  const deployedRun = recentRuns.find(r => r.status === 'deployed');

  return (
    <div className="training-status-tab p-6 space-y-6">
      {/* Error Alert */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {error}
            <button className="ml-2 text-sm underline" onClick={() => setError(null)}>Dismiss</button>
          </AlertDescription>
        </Alert>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Total Samples</span>
            <div className="w-8 h-8 rounded-lg bg-pink-50 flex items-center justify-center">
              <FileText className="w-4 h-4 text-pink-500" />
            </div>
          </div>
          <div className="text-3xl font-bold text-gray-900">{totalSamples.toLocaleString()}</div>
          <div className="text-xs text-gray-400 mt-1"><span className="text-green-600 font-semibold">+2.4%</span> from last week</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Topics</span>
            <div className="w-8 h-8 rounded-lg bg-green-50 flex items-center justify-center">
              <FolderOpen className="w-4 h-4 text-green-500" />
            </div>
          </div>
          <div className="text-3xl font-bold text-gray-900">{topics.length}</div>
          <div className="text-xs text-gray-400 mt-1">Across all categories</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">DeBERTa Ready</span>
            <div className="w-8 h-8 rounded-lg bg-pink-50 flex items-center justify-center">
              <CheckCircle2 className="w-4 h-4 text-pink-500" />
            </div>
          </div>
          <div className="text-3xl font-bold text-gray-900">{fullyReadyTopics.length}</div>
          <div className="text-xs text-gray-400 mt-1">Models deployed</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Collecting</span>
            <div className="w-8 h-8 rounded-lg bg-yellow-50 flex items-center justify-center">
              <Loader2 className="w-4 h-4 text-yellow-500" />
            </div>
          </div>
          <div className="text-3xl font-bold text-gray-900">{bootstrappingTopics.length}</div>
          <div className="text-xs text-gray-400 mt-1">Awaiting samples</div>
        </div>
      </div>

      {/* Pipeline Card - Full Width */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-gray-400" />
            Article Processing Pipeline
          </h3>
          <button
            className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
            onClick={loadData}
            disabled={loading}
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        <div className="p-5">
          {/* Pipeline Stages - Simple horizontal flow */}
          <div className="relative flex items-start justify-between gap-2 py-4">
            {/* Connecting line */}
            <div className="absolute top-[52px] left-[60px] right-[60px] h-0.5 bg-gray-200 z-0" />

            {/* Stage 1: Collection */}
            <div className="flex flex-col items-center text-center flex-1 relative z-10">
              <div className="relative mb-2.5">
                <div className="w-14 h-14 rounded-xl bg-white border-2 border-gray-200 flex items-center justify-center hover:border-pink-400 hover:shadow-md transition-all cursor-default">
                  <Download className="w-6 h-6 text-gray-500" />
                </div>
              </div>
              <span className="text-xs font-semibold text-gray-900">Collection</span>
              <span className="text-[10px] text-gray-500">RSS, APIs</span>
            </div>

            {/* Stage 2: Relevance */}
            <div className="flex flex-col items-center text-center flex-1 relative z-10">
              <div className="relative mb-2.5">
                <div className="w-14 h-14 rounded-xl bg-white border-2 border-gray-200 flex items-center justify-center hover:border-pink-400 hover:shadow-md transition-all cursor-default">
                  <Target className="w-6 h-6 text-gray-500" />
                </div>
                <span className="absolute -top-1.5 -right-1.5 px-1.5 py-0.5 rounded text-[8px] font-bold bg-gradient-to-r from-pink-500 to-indigo-500 text-white whitespace-nowrap">Hybrid</span>
              </div>
              <span className="text-xs font-semibold text-gray-900">Relevance</span>
              <span className="text-[10px] text-gray-500">DeBERTa → GPT</span>
            </div>

            {/* Stage 3: Category */}
            <div className="flex flex-col items-center text-center flex-1 relative z-10">
              <div className="relative mb-2.5">
                <div className="w-14 h-14 rounded-xl bg-white border-2 border-gray-200 flex items-center justify-center hover:border-pink-400 hover:shadow-md transition-all cursor-default">
                  <Folder className="w-6 h-6 text-gray-500" />
                </div>
                <span className="absolute -top-1.5 -right-1.5 px-1.5 py-0.5 rounded text-[8px] font-bold bg-blue-500 text-white">Qwen</span>
              </div>
              <span className="text-xs font-semibold text-gray-900">Category</span>
              <span className="text-[10px] text-gray-500">→ GPT fallback</span>
            </div>

            {/* Stage 4: Summary */}
            <div className="flex flex-col items-center text-center flex-1 relative z-10">
              <div className="relative mb-2.5">
                <div className="w-14 h-14 rounded-xl bg-white border-2 border-gray-200 flex items-center justify-center hover:border-pink-400 hover:shadow-md transition-all cursor-default">
                  <FileText className="w-6 h-6 text-gray-500" />
                </div>
                <span className="absolute -top-1.5 -right-1.5 px-1.5 py-0.5 rounded text-[8px] font-bold bg-purple-500 text-white">Phi-3</span>
              </div>
              <span className="text-xs font-semibold text-gray-900">Summary</span>
              <span className="text-[10px] text-gray-500">→ GPT fallback</span>
            </div>

            {/* Stage 5: Enrichment */}
            <div className="flex flex-col items-center text-center flex-1 relative z-10">
              <div className="relative mb-2.5">
                <div className="w-14 h-14 rounded-xl bg-white border-2 border-gray-200 flex items-center justify-center hover:border-pink-400 hover:shadow-md transition-all cursor-default">
                  <Star className="w-6 h-6 text-gray-500" />
                </div>
                <span className="absolute -top-1.5 -right-1.5 px-1.5 py-0.5 rounded text-[8px] font-bold bg-pink-500 text-white">DeBERTa</span>
              </div>
              <span className="text-xs font-semibold text-gray-900">Enrichment</span>
              <span className="text-[10px] text-gray-500">→ GPT fallback</span>
            </div>

            {/* Stage 6: Tags */}
            <div className="flex flex-col items-center text-center flex-1 relative z-10">
              <div className="relative mb-2.5">
                <div className="w-14 h-14 rounded-xl bg-white border-2 border-gray-200 flex items-center justify-center hover:border-pink-400 hover:shadow-md transition-all cursor-default">
                  <Hash className="w-6 h-6 text-gray-500" />
                </div>
                <span className="absolute -top-1.5 -right-1.5 px-1.5 py-0.5 rounded text-[8px] font-bold bg-teal-500 text-white">KeyBERT</span>
              </div>
              <span className="text-xs font-semibold text-gray-900">Tags + NER</span>
              <span className="text-[10px] text-gray-500">Phi-3 → GPT</span>
            </div>
          </div>

          {/* Pipeline Stats */}
          <div className="flex items-center gap-6 pt-4 mt-2 border-t border-gray-100 text-xs text-gray-600">
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-pink-500" />
              Today: <strong className="text-gray-900 font-semibold">{pipelineStats?.articles_today ?? '—'}</strong> articles
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
              <strong className="text-gray-900 font-semibold">{pipelineStats?.relevance_passed ?? '—'}</strong> passed relevance
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
              <strong className="text-gray-900 font-semibold">{pipelineStats?.topics_active ?? '—'}</strong> topics active
            </div>
            {bootstrappingTopics.length > 0 && (
              <div className="flex items-center gap-1.5 text-green-600">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                <strong className="font-semibold">{bootstrappingTopics.length}</strong> topics using GPT
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Two Column: Training Status + Model Usage */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Training Status Card - 3 columns */}
        <div className="lg:col-span-3 bg-white rounded-xl border border-gray-200">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <h3 className="font-semibold text-gray-900 flex items-center gap-2">
              <Zap className="w-4 h-4 text-gray-400" />
              Training Status
            </h3>
          </div>
          <div className="p-5 space-y-4">
            {/* Trained Models Chips */}
            <div className="flex flex-wrap gap-2">
              <span className={`px-2.5 py-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 ${
                systemStatus?.hybrid_enrichment.deberta_available ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'
              }`}>
                {systemStatus?.hybrid_enrichment.deberta_available && <CheckCircle2 className="w-3 h-3" />}
                Enrichment
              </span>
              <span className={`px-2.5 py-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 ${
                systemStatus?.finetuning.current_model_exists ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'
              }`}>
                {systemStatus?.finetuning.current_model_exists && <CheckCircle2 className="w-3 h-3" />}
                Relevance
              </span>
              {fullyReadyTopics.length > 0 && (
                <span className="px-2.5 py-1.5 rounded-md text-xs font-semibold bg-pink-50 text-pink-700">
                  {fullyReadyTopics.length} topics on DeBERTa
                </span>
              )}
              {bootstrappingTopics.length > 0 && (
                <span className="px-2.5 py-1.5 rounded-md text-xs font-semibold bg-pink-50 text-pink-700">
                  {bootstrappingTopics.length} on gpt-4o-mini
                </span>
              )}
            </div>

            {/* Deployed model info */}
            {deployedRun && (
              <>
                <div className="text-xs text-gray-500">
                  <span className="text-gray-900 font-medium">{deployedRun.sample_count?.toLocaleString()}</span> samples ·
                  <span className="ml-1">{deployedRun.topics_included?.length ?? 0} topic{(deployedRun.topics_included?.length ?? 0) !== 1 ? 's' : ''}</span> ·
                  <span className="ml-1">deployed {deployedRun.completed_at ? new Date(deployedRun.completed_at).toLocaleDateString() : ''}</span>
                </div>
                {deployedRun.topics_included && deployedRun.topics_included.length > 0 && (
                  <div className="text-xs text-pink-600 truncate" title={deployedRun.topics_included.join(', ')}>
                    {deployedRun.topics_included[0]}
                    {deployedRun.topics_included.length > 1 && ` +${deployedRun.topics_included.length - 1} more`}
                  </div>
                )}
              </>
            )}

            {/* Confidence Stats */}
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-xs font-semibold text-gray-700 flex items-center gap-1.5 mb-3">
                <Cpu className="w-3.5 h-3.5 text-gray-400" />
                DeBERTa Confidence (24h)
              </div>
              {confidenceStats && Object.keys(confidenceStats.stats).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(confidenceStats.stats).slice(0, 2).map(([topic, stats]) => (
                    <div key={topic} className="flex items-center justify-between text-xs">
                      <span className="text-gray-600 truncate max-w-[200px]">{topic}</span>
                      <span className={`font-semibold ${stats.overall_avg >= 0.6 ? 'text-green-600' : 'text-yellow-600'}`}>
                        {(stats.overall_avg * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-gray-400 text-center py-2">No data yet — appears when DeBERTa processes articles</p>
              )}
            </div>

            {/* Relevance Stats */}
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-xs font-semibold text-gray-700 flex items-center gap-1.5 mb-3">
                <Target className="w-3.5 h-3.5 text-gray-400" />
                Relevance Scoring (24h)
              </div>
              {relevanceConfidenceStats && Object.keys(relevanceConfidenceStats.stats).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(relevanceConfidenceStats.stats).slice(0, 2).map(([topic, stats]) => (
                    <div key={topic} className="flex items-center justify-between text-xs">
                      <span className="text-gray-600 truncate max-w-[200px]">{topic}</span>
                      <span className="font-semibold text-green-600">{(stats.avg_score * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-gray-400 text-center py-2">No data yet — appears when articles are scored for relevance</p>
              )}
            </div>

            {/* Feedback Section */}
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="text-center">
                    <div className="text-xl font-bold text-gray-900">{feedbackStats?.totals.total_feedback ?? 0}</div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide">Total</div>
                  </div>
                  <div className="text-center">
                    <div className="text-xl font-bold text-green-600">{feedbackStats?.totals.more_like_this ?? 0}</div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide">More</div>
                  </div>
                  <div className="text-center">
                    <div className="text-xl font-bold text-red-600">{feedbackStats?.totals.less_like_this ?? 0}</div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide">Less</div>
                  </div>
                  {feedbackStats && feedbackStats.totals.total_feedback < 1000 && (
                    <div className="pl-4 border-l border-gray-200">
                      {feedbackStats.totals.total_feedback < 500 ? (
                        <div className="text-xs font-semibold text-pink-600">
                          {500 - feedbackStats.totals.total_feedback} more to begin training
                          <div className="text-[10px] text-gray-500 font-normal">500 min, 1000+ ideal</div>
                        </div>
                      ) : (
                        <div className="text-xs font-semibold text-green-600">
                          Ready to train!
                          <div className="text-[10px] text-gray-500 font-normal">{1000 - feedbackStats.totals.total_feedback} more for ideal</div>
                        </div>
                      )}
                      {feedbackStats.by_topic && Object.keys(feedbackStats.by_topic).length > 0 && (
                        <div className="text-[11px] text-gray-500 mt-0.5">
                          {Object.entries(feedbackStats.by_topic).slice(0, 1).map(([topic, counts]) => (
                            <span key={topic}>{topic}: +{counts.more_like_this} -{counts.less_like_this}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
                <button
                  onClick={handleTriggerRelevanceTraining}
                  disabled={relevanceTraining || !feedbackStats || feedbackStats.totals.total_feedback < 500}
                  className="px-4 py-2 bg-green-500 hover:bg-green-600 text-white text-xs font-semibold rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                >
                  {relevanceTraining ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                  Train Relevance Model
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Model Usage Card - 2 columns */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <h3 className="font-semibold text-gray-900 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-gray-400" />
              Model Usage
            </h3>
          </div>
          <div className="p-5 space-y-4">
            {/* Local Models */}
            <div>
              <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1">
                Local Models (FREE)
                <HelpCircle className="w-3 h-3 text-gray-400" title="Models running locally on your infrastructure - no API costs" />
              </div>
              <div className="grid grid-cols-3 gap-2">
                {(modelConfig?.local_models ?? [
                  { name: 'DeBERTa', status: 'available', latency: '~56ms', description: 'Relevance, Classification', tooltip: '', usage: null, port: null, type: 'local', cost: 'FREE' },
                  { name: 'Phi-3', status: 'available', latency: '~3.5s', description: 'Summary, Tags', tooltip: '', usage: null, port: 8765, type: 'local', cost: 'FREE' },
                  { name: 'Qwen', status: 'available', latency: '~5s', description: 'Explanations, Category', tooltip: '', usage: null, port: 8766, type: 'local', cost: 'FREE' },
                ]).filter(m => ['DeBERTa', 'Phi-3', 'Qwen'].includes(m.name)).map((model) => {
                  const colorMap: Record<string, { bg: string; text: string }> = {
                    'DeBERTa': { bg: 'bg-pink-50', text: 'text-pink-600' },
                    'Phi-3': { bg: 'bg-purple-50', text: 'text-purple-600' },
                    'Qwen': { bg: 'bg-blue-50', text: 'text-blue-600' },
                    'KeyBERT': { bg: 'bg-teal-50', text: 'text-teal-600' },
                    'MiniLM': { bg: 'bg-indigo-50', text: 'text-indigo-600' },
                  };
                  const colors = colorMap[model.name] || { bg: 'bg-gray-50', text: 'text-gray-600' };
                  return (
                    <div
                      key={model.name}
                      className={`p-2.5 ${colors.bg} rounded-lg relative cursor-help hover:ring-2 hover:ring-gray-200 transition-all`}
                      title={model.tooltip || model.description}
                    >
                      {model.status === 'unavailable' && (
                        <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-red-500" title="Unavailable" />
                      )}
                      <div className={`text-[10px] font-semibold ${colors.text} mb-0.5`}>
                        {model.name} {model.port ? `(:${model.port})` : '(CPU)'}
                      </div>
                      <div className="text-base font-bold text-gray-900">{model.latency || '—'}</div>
                      <div className="text-[9px] text-gray-500 mt-0.5 truncate">
                        {model.usage || model.description.split('(')[0].trim()}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* External Models */}
            <div>
              <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1">
                External LLMs (Fallback)
                <HelpCircle className="w-3 h-3 text-gray-400" title="Cloud APIs used when local models are unavailable or low confidence" />
              </div>
              <div className="space-y-2">
                {(modelConfig?.external_models ?? [
                  { name: 'gpt-4o-mini', status: 'available', latency: '~2-5s', description: 'Fallback when local unavailable', tooltip: '', usage: null, cost: '~$0.001/article', type: 'external', port: null },
                ]).map((model) => (
                  <div
                    key={model.name}
                    className="flex items-center justify-between p-2.5 bg-green-50 rounded-lg cursor-help hover:ring-2 hover:ring-gray-200 transition-all"
                    title={model.tooltip || model.description}
                  >
                    <div>
                      <div className="text-[10px] font-semibold text-green-600">{model.name}</div>
                      <div className="text-[9px] text-gray-500">{model.usage || model.description}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-gray-900">{model.latency}</div>
                      <div className="text-[9px] text-green-600 font-medium">{model.cost}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Cost Savings */}
            <div className="p-3 bg-gray-50 rounded-lg">
              <div className="flex justify-between items-center mb-1">
                <span className="text-xs font-semibold text-gray-700">Cost Savings ({costSavings?.window_hours ?? 24}h)</span>
                <span className="text-xs font-bold text-green-600">
                  {costSavings?.local_percentage?.toFixed(1) ?? '—'}% FREE
                </span>
              </div>
              <div className="flex items-center gap-3 text-[10px] text-gray-500">
                <span>
                  <strong className="text-gray-700">{costSavings?.local_model_count ?? 0}</strong> local
                </span>
                <span>
                  <strong className="text-gray-700">{costSavings?.llm_fallback_count ?? 0}</strong> LLM
                </span>
                {costSavings && costSavings.savings_amount > 0 && (
                  <span className="text-green-600">
                    ~${costSavings.savings_amount.toFixed(2)} saved
                  </span>
                )}
              </div>
              <div className="text-[9px] text-gray-400 mt-1">
                LLM fallback only when DeBERTa confidence &lt; 0.6 or vLLM unavailable
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Topics Section */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-gray-900">
            Topics <span className="font-normal text-gray-500">({topics.length})</span>
          </h3>
        </div>

        {topics.length === 0 ? (
          <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
            <Info className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <h4 className="text-lg font-medium text-gray-900 mb-2">No training data yet</h4>
            <p className="text-gray-500">
              Training samples are collected automatically as articles are processed.<br />
              Use the Keywords or RSS tabs to add content sources.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {topics.map((topic) => (
              <TopicTrainingCard
                key={topic.topic}
                topic={topic}
                thresholdGreen={thresholds?.green || DEBERTA_THRESHOLD}
                onTriggerFinetune={handleTriggerFinetune}
              />
            ))}
          </div>
        )}
      </div>

      {/* Training Runs */}
      {recentRuns.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-base font-semibold text-gray-900">Training Runs</h3>
          </div>
          <div className="space-y-3">
            {recentRuns.map((run) => {
              const isActive = ['pending', 'running', 'exporting', 'training'].includes(run.status);
              const canDeploy = run.status === 'completed';
              const isDeployed = run.status === 'deployed';
              const isFailed = run.status === 'failed';

              return (
                <div key={run.run_id} className="flex items-center gap-4 p-4 bg-white rounded-xl border border-gray-200">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                    isActive ? 'bg-pink-50 text-pink-500' :
                    isDeployed ? 'bg-green-50 text-green-500' :
                    isFailed ? 'bg-red-50 text-red-500' :
                    'bg-gray-50 text-gray-400'
                  }`}>
                    {isActive ? <Loader2 className="w-5 h-5 animate-spin" /> :
                     isDeployed ? <CheckCircle2 className="w-5 h-5" /> :
                     isFailed ? <XCircle className="w-5 h-5" /> :
                     <Zap className="w-5 h-5" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-mono text-sm text-gray-900">{run.run_id}</div>
                    <div className="text-xs text-gray-500">
                      {run.sample_count?.toLocaleString()} samples · {run.topics_included?.length ?? 0} topics
                    </div>
                  </div>
                  {(isActive || isDeployed || canDeploy) && (
                    <div className="flex-1 max-w-[200px]">
                      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden mb-1">
                        <div
                          className={`h-full rounded-full ${isActive ? 'bg-pink-500 animate-pulse' : 'bg-green-500'}`}
                          style={{ width: isActive ? '73%' : '100%' }}
                        />
                      </div>
                      <div className="text-[10px] text-gray-500">
                        {isActive ? 'Training DeBERTa model...' : 'Complete'}
                      </div>
                    </div>
                  )}
                  <div className="flex items-center gap-3">
                    {run.metrics?.eval_accuracy && (
                      <span className="text-xs text-green-600 font-medium">
                        {(run.metrics.eval_accuracy * 100).toFixed(1)}% acc
                      </span>
                    )}
                    <span className={`px-2.5 py-1 rounded text-xs font-semibold ${
                      isDeployed ? 'bg-green-50 text-green-700' :
                      isActive ? 'bg-pink-50 text-pink-700' :
                      isFailed ? 'bg-red-50 text-red-700' :
                      'bg-gray-50 text-gray-700'
                    }`}>
                      {isActive ? 'Training...' : run.status}
                    </span>
                    {run.completed_at && (
                      <span className="text-xs text-gray-400">{new Date(run.completed_at).toLocaleDateString()}</span>
                    )}
                    {canDeploy && (
                      <button
                        onClick={() => handleDeploy(run.run_id)}
                        disabled={deploying === run.run_id}
                        className="px-3 py-1.5 bg-green-500 hover:bg-green-600 text-white text-xs font-semibold rounded-lg transition-colors disabled:opacity-50"
                      >
                        {deploying === run.run_id ? 'Deploying...' : 'Deploy'}
                      </button>
                    )}
                    {(isFailed || isDeployed || canDeploy) && (
                      <button
                        onClick={() => handleDelete(run.run_id)}
                        className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Status Legend */}
      <div className="flex items-center gap-6 p-4 bg-gray-50 rounded-xl text-xs">
        <span className="font-semibold text-gray-700">Status Legend</span>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-pink-500" />
          <span className="text-gray-600">Local model (DeBERTa/Qwen/Phi-3) - fast, free</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-green-500" />
          <span className="text-gray-600">Cloud API (GPT) - ~$0.001/article, used when &lt;500 samples</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-purple-500" />
          <span className="text-gray-600">DeBERTa Ready (500+ samples)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-gray-400" />
          <span className="text-gray-600">Collecting samples</span>
        </div>
      </div>
    </div>
  );
}
