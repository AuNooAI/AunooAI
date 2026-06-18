/**
 * Topic Training Card
 *
 * Displays training sample counts and readiness status for a single topic.
 * Shows progress toward the 500-sample threshold for switching from GPT to DeBERTa.
 *
 * Two-tier system:
 * - < 500 samples: GPT (gpt-5.4-mini) for classification + training data collection
 * - >= 500 samples: DeBERTa (fast, free, trained on collected samples)
 */

import { useState } from 'react';
import { ChevronDown, ChevronUp, Zap, Cpu, Bot, Globe, GraduationCap, BookOpen, Shield, Lock, Landmark, FlaskConical, Newspaper, FileText, TrendingUp, Users, Microscope, Building2, Scale, Lightbulb, Activity, Loader2, Play } from 'lucide-react';
import type { TopicTrainingStatus, FieldDistribution } from '../../services/trainingApi';
import { getFieldDistribution, initializeTopicSamples } from '../../services/trainingApi';

interface TopicTrainingCardProps {
  topic: TopicTrainingStatus;
  thresholdGreen: number;
  onTriggerFinetune?: (topic: string) => void;
  onDeploy?: (runId: string) => void;
  onRefresh?: () => void;
}

// Field display names
const FIELD_LABELS: Record<string, string> = {
  sentiment: 'Sentiment',
  time_to_impact: 'Time to Impact',
  driver_type: 'Driver Type',
  future_signal: 'Future Signal',
};

// DeBERTa threshold (samples needed for trained model)
const DEBERTA_THRESHOLD = 500;

// Topic icon and color mapping
const getTopicStyle = (topicName: string): { icon: React.ReactNode; bgColor: string; textColor: string } => {
  const lowerTopic = topicName.toLowerCase();

  if (lowerTopic.includes('ai') || lowerTopic.includes('machine learning') || lowerTopic.includes('artificial intelligence')) {
    return { icon: <Bot className="w-4 h-4" />, bgColor: 'bg-purple-100', textColor: 'text-purple-600' };
  }
  if (lowerTopic.includes('geopolitical') || lowerTopic.includes('hotspot') || lowerTopic.includes('conflict')) {
    return { icon: <Globe className="w-4 h-4" />, bgColor: 'bg-red-100', textColor: 'text-red-600' };
  }
  if (lowerTopic.includes('r&d') || lowerTopic.includes('research') || lowerTopic.includes('compensatory')) {
    return { icon: <Microscope className="w-4 h-4" />, bgColor: 'bg-blue-100', textColor: 'text-blue-600' };
  }
  if (lowerTopic.includes('university') || lowerTopic.includes('grant') || lowerTopic.includes('academic')) {
    return { icon: <GraduationCap className="w-4 h-4" />, bgColor: 'bg-emerald-100', textColor: 'text-emerald-600' };
  }
  if (lowerTopic.includes('publish') || lowerTopic.includes('integrity') || lowerTopic.includes('journal')) {
    return { icon: <BookOpen className="w-4 h-4" />, bgColor: 'bg-amber-100', textColor: 'text-amber-600' };
  }
  if (lowerTopic.includes('attack') || lowerTopic.includes('expertise') || lowerTopic.includes('peer review')) {
    return { icon: <Shield className="w-4 h-4" />, bgColor: 'bg-rose-100', textColor: 'text-rose-600' };
  }
  if (lowerTopic.includes('patent') || lowerTopic.includes('cliff')) {
    return { icon: <Lock className="w-4 h-4" />, bgColor: 'bg-indigo-100', textColor: 'text-indigo-600' };
  }
  if (lowerTopic.includes('federal') || lowerTopic.includes('pullback') || lowerTopic.includes('government')) {
    return { icon: <Landmark className="w-4 h-4" />, bgColor: 'bg-cyan-100', textColor: 'text-cyan-600' };
  }
  if (lowerTopic.includes('scientific') || lowerTopic.includes('monitoring') || lowerTopic.includes('science')) {
    return { icon: <FlaskConical className="w-4 h-4" />, bgColor: 'bg-fuchsia-100', textColor: 'text-fuchsia-600' };
  }
  if (lowerTopic.includes('news') || lowerTopic.includes('media')) {
    return { icon: <Newspaper className="w-4 h-4" />, bgColor: 'bg-slate-100', textColor: 'text-slate-600' };
  }
  if (lowerTopic.includes('policy') || lowerTopic.includes('regulation')) {
    return { icon: <Scale className="w-4 h-4" />, bgColor: 'bg-orange-100', textColor: 'text-orange-600' };
  }
  if (lowerTopic.includes('trend') || lowerTopic.includes('market')) {
    return { icon: <TrendingUp className="w-4 h-4" />, bgColor: 'bg-teal-100', textColor: 'text-teal-600' };
  }
  if (lowerTopic.includes('organization') || lowerTopic.includes('company') || lowerTopic.includes('corporate')) {
    return { icon: <Building2 className="w-4 h-4" />, bgColor: 'bg-zinc-100', textColor: 'text-zinc-600' };
  }
  if (lowerTopic.includes('innovation') || lowerTopic.includes('startup')) {
    return { icon: <Lightbulb className="w-4 h-4" />, bgColor: 'bg-yellow-100', textColor: 'text-yellow-600' };
  }

  // Default
  return { icon: <Activity className="w-4 h-4" />, bgColor: 'bg-gray-100', textColor: 'text-gray-600' };
};

export function TopicTrainingCard({
  topic,
  thresholdGreen,
  onTriggerFinetune,
  onDeploy,
  onRefresh,
}: TopicTrainingCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedField, setSelectedField] = useState<string | null>(null);
  const [fieldDistribution, setFieldDistribution] = useState<FieldDistribution | null>(null);
  const [loadingDistribution, setLoadingDistribution] = useState(false);
  const [initializing, setInitializing] = useState(false);
  const [initResult, setInitResult] = useState<string | null>(null);

  // Calculate fields ready for DeBERTa vs still using GPT
  const fields = Object.keys(topic.field_counts);
  const debertaReadyFields = fields.filter(f => (topic.field_counts[f] || 0) >= DEBERTA_THRESHOLD);

  // Overall progress (average across fields toward DEBERTA_THRESHOLD)
  const avgProgress = fields.length > 0
    ? Math.round(
        Object.values(topic.field_counts).reduce((sum, count) => sum + Math.min(count, DEBERTA_THRESHOLD), 0) /
        (fields.length * DEBERTA_THRESHOLD) * 100
      )
    : 0;

  const isFullyReady = debertaReadyFields.length === fields.length && fields.length > 0;
  const topicStyle = getTopicStyle(topic.topic);

  const handleFieldClick = async (field: string) => {
    if (selectedField === field) {
      setSelectedField(null);
      setFieldDistribution(null);
      return;
    }

    setSelectedField(field);
    setLoadingDistribution(true);

    try {
      const distribution = await getFieldDistribution(topic.topic, field);
      setFieldDistribution(distribution);
    } catch (err) {
      console.error('Failed to load field distribution:', err);
    } finally {
      setLoadingDistribution(false);
    }
  };

  const handleInitializeSamples = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setInitializing(true);
    setInitResult(null);
    try {
      const result = await initializeTopicSamples(topic.topic, 100);
      setInitResult(`${result.bootstrapped} samples initialized`);
      onRefresh?.();
    } catch (err) {
      setInitResult(err instanceof Error ? err.message : 'Failed to initialize');
    } finally {
      setInitializing(false);
    }
  };

  // Determine progress bar color
  const getProgressColor = () => {
    if (avgProgress >= 100) return 'bg-green-500';
    if (avgProgress >= 50) return 'bg-yellow-500';
    return 'bg-pink-500';
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 hover:border-pink-300 hover:shadow-md transition-all overflow-hidden">
      {/* Header - clickable to expand */}
      <div
        className="p-4 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-start gap-3">
          {/* Topic Icon */}
          <div className={`w-9 h-9 rounded-lg ${topicStyle.bgColor} ${topicStyle.textColor} flex items-center justify-center flex-shrink-0`}>
            {topicStyle.icon}
          </div>

          {/* Topic Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-sm text-gray-900 truncate pr-2">{topic.topic}</h3>
              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold whitespace-nowrap ${
                (() => {
                  const runStatus = topic.latest_run?.status;
                  if (runStatus === 'deployed') return 'bg-green-50 text-green-700';
                  if (runStatus && ['pending','running','exporting','training'].includes(runStatus)) return 'bg-pink-50 text-pink-700 animate-pulse';
                  if (runStatus === 'completed') return 'bg-blue-50 text-blue-700';
                  if (runStatus === 'failed' && isFullyReady) return 'bg-red-50 text-red-700';
                  if (isFullyReady) return 'bg-amber-50 text-amber-700';
                  return 'bg-gray-100 text-gray-500';
                })()
              }`}>
                {(() => {
                  const runStatus = topic.latest_run?.status;
                  if (runStatus === 'deployed') return 'Deployed';
                  if (runStatus && ['pending','running','exporting','training'].includes(runStatus)) return 'Training...';
                  if (runStatus === 'completed') return 'Trained';
                  if (runStatus === 'failed' && isFullyReady) return 'Failed';
                  if (isFullyReady) return 'Ready to Train';
                  return `${debertaReadyFields.length}/${fields.length} ready`;
                })()}
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              {topic.total_samples.toLocaleString()} samples · {topic.article_count.toLocaleString()} articles
            </p>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="mt-3">
          <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${getProgressColor()}`}
              style={{ width: `${Math.min(avgProgress, 100)}%` }}
            />
          </div>
          <div className="flex items-center justify-between mt-1.5">
            <span className="text-[10px] text-gray-500">
              {(() => {
                const runStatus = topic.latest_run?.status;
                if (runStatus === 'deployed') return 'DeBERTa active';
                if (runStatus && ['pending','running','exporting','training'].includes(runStatus)) return 'Training DeBERTa...';
                if (runStatus === 'completed') return 'Ready to deploy';
                if (runStatus === 'failed') return 'Last training failed';
                if (isFullyReady) return 'Ready for finetuning';
                return 'Collecting samples';
              })()}
            </span>
            <span className="text-[10px] font-medium text-gray-600">{avgProgress}%</span>
          </div>
        </div>
      </div>

      {/* Expanded Details */}
      {isExpanded && (
        <div className="border-t border-gray-100 p-4">
          {/* Field Status Table */}
          <table className="w-full">
            <thead>
              <tr className="text-[10px] text-gray-500 border-b border-gray-100">
                <th className="text-left font-medium pb-2">Field</th>
                <th className="text-right font-medium pb-2 pr-3">Samples</th>
                <th className="text-center font-medium pb-2 w-12">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {Object.entries(topic.field_counts).map(([field, count]) => {
                const isReady = count >= DEBERTA_THRESHOLD;
                const samplesNeeded = Math.max(0, DEBERTA_THRESHOLD - count);
                const isSelected = selectedField === field;

                return (
                  <tr
                    key={field}
                    className={`cursor-pointer hover:bg-gray-50 transition-colors ${isSelected ? 'bg-pink-50' : ''}`}
                    onClick={() => handleFieldClick(field)}
                  >
                    <td className="py-2 text-xs text-gray-700">
                      {FIELD_LABELS[field] || field}
                    </td>
                    <td className="py-2 text-xs text-right pr-3">
                      <span className={`font-medium ${isReady ? 'text-green-600' : 'text-gray-900'}`}>
                        {count.toLocaleString()}
                      </span>
                      {!isReady && (
                        <span className="text-gray-400 text-[10px] ml-1">
                          (+{samplesNeeded})
                        </span>
                      )}
                    </td>
                    <td className="py-2 text-center">
                      {isReady ? (
                        <span className="inline-flex items-center text-green-600" title="DeBERTa (trained, fast)">
                          <Zap className="w-3.5 h-3.5" />
                        </span>
                      ) : (
                        <span className="inline-flex items-center text-yellow-600" title="GPT (collecting samples)">
                          <Cpu className="w-3.5 h-3.5" />
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* Field Distribution (when a field is selected) */}
          {selectedField && (
            <div className="mt-3 p-3 bg-gray-50 rounded-lg">
              {loadingDistribution ? (
                <div className="text-center text-gray-500 text-xs py-2">Loading distribution...</div>
              ) : fieldDistribution ? (
                <div className="space-y-2">
                  <div className="text-[10px] text-gray-500 mb-2 flex items-center justify-between">
                    <span>{fieldDistribution.unique_values} unique values</span>
                    {!fieldDistribution.min_per_class_met && (
                      <span className="text-yellow-600">Some values have &lt; 50 samples</span>
                    )}
                  </div>
                  {fieldDistribution.distribution.slice(0, 5).map((item) => (
                    <div key={item.value} className="flex items-center gap-2">
                      <span className="text-[10px] text-gray-600 flex-1 truncate">{item.value}</span>
                      <span className="text-[10px] text-gray-500 w-8 text-right">{item.count}</span>
                      <div className="w-16 h-1 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-pink-400 rounded-full"
                          style={{ width: `${item.percentage}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-gray-400 w-6 text-right">{item.percentage}%</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center text-gray-500 text-xs py-2">No data available</div>
              )}
            </div>
          )}

          {/* Actions */}
          {isFullyReady && (
            <div className="mt-4 pt-3 border-t border-gray-100 flex gap-2">
              {onTriggerFinetune && (
                <button
                  className="flex-1 px-4 py-2 bg-pink-500 hover:bg-pink-600 text-white text-xs font-semibold rounded-lg transition-colors"
                  onClick={(e) => {
                    e.stopPropagation();
                    onTriggerFinetune(topic.topic);
                  }}
                >
                  Trigger Finetuning
                </button>
              )}
              {topic.latest_run?.status === 'completed' && onDeploy && (
                <button
                  className="flex-1 px-4 py-2 bg-green-500 hover:bg-green-600 text-white text-xs font-semibold rounded-lg transition-colors"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeploy(topic.latest_run!.run_id);
                  }}
                >
                  Deploy
                </button>
              )}
            </div>
          )}

          {/* Info for non-ready topics */}
          {!isFullyReady && (
            <div className="mt-4 pt-3 border-t border-gray-100">
              {topic.article_count > 0 && topic.total_samples === 0 ? (
                <div className="text-center space-y-2">
                  <p className="text-[10px] text-amber-600">
                    {topic.article_count} articles exist but no training samples yet.
                  </p>
                  <button
                    onClick={handleInitializeSamples}
                    disabled={initializing}
                    className="px-4 py-2 bg-pink-500 hover:bg-pink-600 text-white text-xs font-semibold rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5 mx-auto"
                  >
                    {initializing ? (
                      <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Initializing...</>
                    ) : (
                      <><Play className="w-3.5 h-3.5" /> Initialize Samples</>
                    )}
                  </button>
                  {initResult && (
                    <p className="text-[10px] text-green-600">{initResult}</p>
                  )}
                </div>
              ) : (
                <p className="text-[10px] text-gray-500 text-center">
                  Collecting samples using GPT. DeBERTa activates at 500 samples per field.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
