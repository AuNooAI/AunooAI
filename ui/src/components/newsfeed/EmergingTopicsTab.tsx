/**
 * Emerging Topics Tab Component (v2)
 *
 * Full tab view for emerging topic detection and exploration.
 * Displays detected topics with rich actor/event/implication data.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Loader2,
  TrendingUp,
  TrendingDown,
  Zap,
  Circle,
  AlertCircle,
  Play,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Sparkles,
  Clock,
  BarChart3,
  Building2,
  User,
  Landmark,
  Target,
  AlertTriangle,
  Eye,
  Gauge,
  Users,
  Settings2,
  X,
  MoreVertical,
  Share2,
  Bookmark,
  Trash2,
  Download,
  FileText,
  FileSpreadsheet,
  FileDown,
  MessageSquare,
} from 'lucide-react';
import { openAuspexWithQuery } from '../../utils/auspexEvents';
import { Card, CardContent } from '../ui/card';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Progress } from '../ui/progress';
import { Alert, AlertDescription, AlertTitle } from '../ui/alert';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import {
  EmergingTopicsConfigModal,
  EmergingTopicsConfig,
  loadEmergingTopicsConfig,
} from './EmergingTopicsConfigModal';
import { EmergingTopicsScheduleModal } from './EmergingTopicsScheduleModal';
// ShareModal removed - needs proper data type support for emerging topics
import { getAvailableModels } from '../../services/newsFeedApi';
import { ExportService } from '../../services/exportService';
// Visual components
import { TopicScoreRadar } from '../emerging-topics/TopicScoreRadar';
import { TopicWordCloud } from '../emerging-topics/TopicWordCloud';
import { TopicComparisonDashboard } from '../emerging-topics/TopicComparisonDashboard';
import { TopicSparkline } from '../emerging-topics/TopicSparkline';
import { MomentumGauge } from '../emerging-topics/MomentumGauge';
import { TrajectoryTimeline } from '../emerging-topics/TrajectoryTimeline';

// Types for v2
interface TrendScore {
  volume: number;
  velocity: number;
  diversity: number;
  novelty: number;
  composite: number;
}

interface Actors {
  companies?: string[];
  people?: string[];
  organizations?: string[];
}

interface Events {
  trigger_event?: string;
  timeline?: (string | { date?: string; event?: string })[];
  current_status?: string;
}

interface Implications {
  industry_impact?: string;
  regulatory?: string;
  market?: string;
}

interface Signals {
  growth_indicators?: string[];
  risk_factors?: string[];
  watch_for?: string[];
}

interface Synthesis {
  key_takeaway?: string;
  stakeholders_affected?: string[];
  urgency?: 'low' | 'medium' | 'high';
}

interface EmergingTopic {
  id: number;
  topic_label: string;
  topic_description: string;
  detection_date: string;
  detection_type: string;
  article_count: number;
  growth_rate: number;
  velocity: 'accelerating' | 'stable' | 'decelerating';
  confidence_score: number;
  key_themes: string[];
  key_entities?: string[];
  why_emerging?: string;
  representative_keywords: string[];
  status: string;
  // V2 fields
  trend_score?: TrendScore;
  actors?: Actors;
  events?: Events;
  implications?: Implications;
  signals?: Signals;
  synthesis?: Synthesis;
  source_count?: number;
  // V3 Trend tracking fields
  first_detection_date?: string;
  last_detection_date?: string;
  detection_count?: number;
  consecutive_detections?: number;
  missed_runs?: number;
  trajectory?: string;
}

interface HighNoveltyArticle {
  article_uri: string;
  article_title?: string;
  title?: string;
  composite_novelty_score: number;
  is_outlier: boolean;
  publication_date?: string;
  topic?: string;
}

interface DetectionProgress {
  step?: number;
  progress?: number;
  message: string;
  proposed_count?: number;
  validated_count?: number;
  total_emerging_topics?: number;
  emerging_topics?: EmergingTopic[];
}

interface EmergingTopicsTabProps {
  topic?: string;
  onArticleClick?: (article: { uri: string }) => void;
}

// Type badge styling - function to avoid module-level JSX initialization issues
function getTypeBadgeStyle(detectionType: string) {
  switch (detectionType) {
    case 'new_cluster':
      return {
        label: 'New Topic',
        className: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
        icon: <Circle className="w-3 h-3" />,
      };
    case 'accelerating':
      return {
        label: 'Growing',
        className: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
        icon: <TrendingUp className="w-3 h-3" />,
      };
    default: // llm_proposed
      return {
        label: 'Detected',
        className: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
        icon: <Sparkles className="w-3 h-3" />,
      };
  }
}

// Velocity badge styling - function to avoid module-level JSX initialization issues
function getVelocityStyle(velocity: string) {
  switch (velocity) {
    case 'accelerating':
      return {
        label: 'Accelerating',
        className: 'text-green-600 dark:text-green-400',
        icon: <TrendingUp className="w-3 h-3" />,
      };
    case 'decelerating':
      return {
        label: 'Slowing',
        className: 'text-orange-600 dark:text-orange-400',
        icon: <TrendingDown className="w-3 h-3" />,
      };
    default: // stable
      return {
        label: 'Stable',
        className: 'text-gray-600 dark:text-gray-400',
        icon: <Circle className="w-3 h-3" />,
      };
  }
}

// Urgency badge styling
const urgencyStyles: Record<string, { label: string; className: string }> = {
  low: { label: 'Low Urgency', className: 'bg-gray-100 text-gray-700' },
  medium: { label: 'Medium Urgency', className: 'bg-yellow-100 text-yellow-700' },
  high: { label: 'High Urgency', className: 'bg-red-100 text-red-700' },
};

// Score color helper
function getScoreColor(score: number): string {
  if (score >= 70) return 'text-green-600 dark:text-green-400';
  if (score >= 40) return 'text-yellow-600 dark:text-yellow-400';
  return 'text-gray-600 dark:text-gray-400';
}

export function EmergingTopicsTab({ topic, onArticleClick }: EmergingTopicsTabProps) {
  // State
  const [emergingTopics, setEmergingTopics] = useState<EmergingTopic[]>([]);
  const [highNoveltyArticles, setHighNoveltyArticles] = useState<HighNoveltyArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [detecting, setDetecting] = useState(false);
  const [detectionProgress, setDetectionProgress] = useState<DetectionProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedTopicId, setExpandedTopicId] = useState<number | null>(null);
  const [topicDetails, setTopicDetails] = useState<Record<number, any>>({});

  // Config state
  const [config, setConfig] = useState<EmergingTopicsConfig>(loadEmergingTopicsConfig);
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [isScheduleOpen, setIsScheduleOpen] = useState(false);

  // Model selection state
  const [availableModels, setAvailableModels] = useState<Array<{id: string; name: string; provider: string}>>([]);

  // Delete confirmation state
  const [topicToDelete, setTopicToDelete] = useState<EmergingTopic | null>(null);

  // Clear all confirmation state
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  // Menu state
  const [menuOpenId, setMenuOpenId] = useState<number | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Export menu state
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);

  // Topic history for sparklines
  const [topicHistories, setTopicHistories] = useState<Record<number, Array<{ run_date: string; composite_score: number }>>>({});


  // Track which topics are saved (tracked)
  const [trackedTopicIds, setTrackedTopicIds] = useState<Set<number>>(new Set());

  // Fetch emerging topics
  const fetchTopics = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams({
        days_back: '7',
        limit: '20',
      });

      if (topic) {
        params.append('topic', topic);
      }

      const response = await fetch(`/api/emerging-topics/topics?${params}`);
      if (!response.ok) throw new Error(`Failed to fetch: ${response.status}`);

      const data = await response.json();
      setEmergingTopics(data.topics || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load emerging topics');
    } finally {
      setLoading(false);
    }
  }, [topic]);

  // Fetch high novelty articles
  const fetchHighNovelty = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        threshold: '70',
        days_back: '3',
        limit: '10',
      });

      if (topic) {
        params.append('topic', topic);
      }

      const response = await fetch(`/api/emerging-topics/high-novelty?${params}`);
      if (!response.ok) return;

      const data = await response.json();
      setHighNoveltyArticles(data.articles || []);
    } catch (err) {
      console.error('Failed to load high novelty articles:', err);
    }
  }, [topic]);

  // Fetch tracked topics on mount to show correct save state
  const fetchTrackedStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/emerging-topics/tracked', {
        credentials: 'include',
      });
      if (res.ok) {
        const data = await res.json();
        const ids = new Set<number>((data.topics || []).map((t: { id: number }) => t.id));
        setTrackedTopicIds(ids);
      }
    } catch (err) {
      console.error('Error fetching tracked topics:', err);
    }
  }, []);

  // Run detection - uses single topic endpoint if topic selected, batch endpoint if not
  const runDetection = async () => {
    setDetecting(true);
    setDetectionProgress(null);
    setError(null);

    try {
      // If a topic is selected, use single topic detection
      // Otherwise, use batch detection to scan all topics
      const endpoint = topic ? '/api/emerging-topics/detect' : '/api/emerging-topics/detect/batch';
      const body = topic
        ? {
            topic: topic,
            days_back: config.daysBack,
            sample_size: config.sampleSize,
            distance_threshold: config.distanceThreshold,
            min_articles_per_theme: config.minArticlesPerTheme,
            max_articles_per_theme: config.maxArticlesPerTheme,
            model: config.model,
            stream: true,
          }
        : {
            topics: null, // null = all topics
            days_back: config.daysBack,
            sample_size: config.sampleSize,
            distance_threshold: config.distanceThreshold,
            min_articles_per_theme: config.minArticlesPerTheme,
            max_articles_per_theme: config.maxArticlesPerTheme,
            model: config.model,
          };

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) throw new Error(`Detection failed: ${response.status}`);

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              setDetectionProgress(data);

              if (data.emerging_topics) {
                setEmergingTopics(data.emerging_topics);
              }
            } catch (e) {
              // Ignore parse errors
            }
          }
        }
      }

      // Refresh data after detection
      await fetchTopics();
      await fetchHighNovelty();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Detection failed');
    } finally {
      setDetecting(false);
      setDetectionProgress(null);
    }
  };


  // Fetch topic details
  const fetchTopicDetails = async (topicId: number) => {
    if (topicDetails[topicId]) return;

    try {
      const response = await fetch(`/api/emerging-topics/topics/${topicId}`);
      if (!response.ok) {
        setTopicDetails(prev => ({ ...prev, [topicId]: { error: `Error: ${response.status}` } }));
        return;
      }

      const data = await response.json();
      setTopicDetails(prev => ({ ...prev, [topicId]: data }));
    } catch (err) {
      setTopicDetails(prev => ({ ...prev, [topicId]: { error: 'Network error' } }));
    }
  };

  // Toggle topic expansion
  const toggleTopicExpand = (topicId: number) => {
    if (expandedTopicId === topicId) {
      setExpandedTopicId(null);
    } else {
      setExpandedTopicId(topicId);
      fetchTopicDetails(topicId);
    }
  };

  // Initial load
  useEffect(() => {
    fetchTopics();
    fetchHighNovelty();
    fetchTrackedStatus();
  }, [fetchTopics, fetchHighNovelty, fetchTrackedStatus]);

  // Fetch available models on mount
  useEffect(() => {
    getAvailableModels()
      .then(models => setAvailableModels(models))
      .catch(() => setAvailableModels([]));
  }, []);

  // Handle click outside for menu
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
      }
    };
    if (menuOpenId !== null) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuOpenId]);

  // Handle click outside for export menu
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setExportMenuOpen(false);
      }
    };
    if (exportMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [exportMenuOpen]);

  // Fetch topic histories for sparklines
  useEffect(() => {
    const fetchHistories = async () => {
      if (emergingTopics.length === 0) return;

      const topicIds = emergingTopics.map((t) => t.id).join(',');
      try {
        const response = await fetch(`/api/emerging-topics/batch-history?topic_ids=${topicIds}`, {
          credentials: 'include',
        });
        if (response.ok) {
          const data = await response.json();
          setTopicHistories(data.histories || {});
        }
      } catch (err) {
        console.error('Error fetching topic histories:', err);
      }
    };

    fetchHistories();
  }, [emergingTopics]);

  // Delete topic handler
  const handleDeleteTopic = async (topicId: number) => {
    try {
      const res = await fetch(`/api/emerging-topics/topics/${topicId}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (res.ok) {
        setEmergingTopics(prev => prev.filter(t => t.id !== topicId));
        setTopicToDelete(null);
      }
    } catch (err) {
      console.error('Error deleting topic:', err);
    }
  };

  // Share topic handler
  const handleShareTopic = (topic: EmergingTopic) => {
    // TODO: Implement share functionality for emerging topics
    console.log('Share topic:', topic.topic_label);
    setMenuOpenId(null);
  };

  // Track (save) topic handler
  const handleTrackTopic = async (topicId: number) => {
    try {
      const isTracked = trackedTopicIds.has(topicId);
      const method = isTracked ? 'DELETE' : 'POST';

      const res = await fetch(`/api/emerging-topics/topics/${topicId}/track`, {
        method,
        credentials: 'include',
      });

      if (res.ok) {
        setTrackedTopicIds(prev => {
          const newSet = new Set(prev);
          if (isTracked) {
            newSet.delete(topicId);
          } else {
            newSet.add(topicId);
          }
          return newSet;
        });
      }
    } catch (err) {
      console.error('Error tracking/untracking topic:', err);
    }
    setMenuOpenId(null);
  };

  // Ask Auspex handler - builds comprehensive context for LLM analysis
  const handleAskAuspex = (emergingTopic: EmergingTopic) => {
    const actorsList: string[] = [];
    if (emergingTopic.actors?.companies?.length) actorsList.push(`Companies: ${emergingTopic.actors.companies.join(', ')}`);
    if (emergingTopic.actors?.people?.length) actorsList.push(`People: ${emergingTopic.actors.people.join(', ')}`);
    if (emergingTopic.actors?.organizations?.length) actorsList.push(`Organizations: ${emergingTopic.actors.organizations.join(', ')}`);

    // Include search keywords for Auspex to find related articles
    const keywordsSection = emergingTopic.representative_keywords?.length
      ? `\nSEARCH KEYWORDS (use these to find related articles):\n${emergingTopic.representative_keywords.slice(0, 10).join(', ')}\n`
      : '';

    const themesSection = emergingTopic.key_themes?.length
      ? `\nKEY THEMES:\n${emergingTopic.key_themes.join(', ')}\n`
      : '';

    const prompt = `Analyze this emerging topic: "${emergingTopic.topic_label}"

DESCRIPTION:
${emergingTopic.topic_description}

${emergingTopic.why_emerging ? `WHY EMERGING:\n${emergingTopic.why_emerging}\n` : ''}METRICS:
- Articles: ${emergingTopic.article_count}
- Velocity: ${emergingTopic.velocity}
- Detection Type: ${emergingTopic.detection_type}
${emergingTopic.trend_score ? `- Trend Score: ${Math.round(emergingTopic.trend_score.composite)}/100` : ''}
${keywordsSection}${themesSection}${actorsList.length ? `KEY ACTORS:\n${actorsList.join('\n')}\n` : ''}${emergingTopic.events?.trigger_event ? `TRIGGER EVENT:\n${emergingTopic.events.trigger_event}\n` : ''}${emergingTopic.synthesis?.key_takeaway ? `KEY TAKEAWAY:\n${emergingTopic.synthesis.key_takeaway}\n` : ''}${emergingTopic.implications?.industry_impact ? `INDUSTRY IMPACT:\n${emergingTopic.implications.industry_impact}\n` : ''}
Please provide:
1. Deep analysis of this emerging trend (search for and analyze related articles using the keywords above)
2. Potential implications for our organization
3. Key developments to monitor
4. Recommended actions or responses
5. Related trends or connections to explore`;

    // Pass the topic filter to Auspex so it knows which collection to search
    openAuspexWithQuery(prompt, false, topic || 'All');
  };

  // Render actors section
  const renderActors = (actors: Actors) => {
    const hasActors = actors?.companies?.length || actors?.people?.length || actors?.organizations?.length;
    if (!hasActors) return null;

    return (
      <div className="space-y-2">
        <h5 className="text-xs font-medium text-gray-500 uppercase flex items-center gap-1">
          <Users className="w-3 h-3" /> Key Actors
        </h5>
        <div className="flex flex-wrap gap-2">
          {actors.companies?.map((c, i) => (
            <Badge key={`c-${i}`} variant="outline" className="text-xs flex items-center gap-1">
              <Building2 className="w-3 h-3 text-blue-500" />
              {c}
            </Badge>
          ))}
          {actors.people?.map((p, i) => (
            <Badge key={`p-${i}`} variant="outline" className="text-xs flex items-center gap-1">
              <User className="w-3 h-3 text-green-500" />
              {p}
            </Badge>
          ))}
          {actors.organizations?.map((o, i) => (
            <Badge key={`o-${i}`} variant="outline" className="text-xs flex items-center gap-1">
              <Landmark className="w-3 h-3 text-purple-500" />
              {o}
            </Badge>
          ))}
        </div>
      </div>
    );
  };

  // Render events section
  const renderEvents = (events: Events) => {
    if (!events?.trigger_event && !events?.timeline?.length) return null;

    // Helper to format timeline item - handles both string and {date, event} object formats
    const formatTimelineItem = (item: string | { date?: string; event?: string }): string => {
      if (typeof item === 'string') return item;
      if (typeof item === 'object' && item !== null) {
        const { date, event } = item;
        if (date && event) return `${date}: ${event}`;
        if (event) return event;
        if (date) return date;
      }
      return String(item);
    };

    return (
      <div className="space-y-2">
        <h5 className="text-xs font-medium text-gray-500 uppercase flex items-center gap-1">
          <Clock className="w-3 h-3" /> Events
        </h5>
        {events.trigger_event && (
          <div className="text-sm bg-blue-50 dark:bg-blue-900/20 p-2 rounded">
            <span className="font-medium">Trigger:</span> {events.trigger_event}
          </div>
        )}
        {events.timeline && events.timeline.length > 0 && (
          <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1 list-disc list-inside">
            {events.timeline.slice(0, 3).map((t, i) => (
              <li key={i}>{formatTimelineItem(t)}</li>
            ))}
          </ul>
        )}
        {events.current_status && (
          <div className="text-sm">
            <span className="font-medium">Status:</span> {events.current_status}
          </div>
        )}
      </div>
    );
  };

  // Render signals section
  const renderSignals = (signals: Signals) => {
    const hasSignals = signals?.growth_indicators?.length || signals?.risk_factors?.length || signals?.watch_for?.length;
    if (!hasSignals) return null;

    return (
      <div className="space-y-2">
        <h5 className="text-xs font-medium text-gray-500 uppercase flex items-center gap-1">
          <Eye className="w-3 h-3" /> Signals
        </h5>
        <div className="grid grid-cols-3 gap-2 text-xs">
          {signals.growth_indicators && signals.growth_indicators.length > 0 && (
            <div>
              <div className="font-medium text-green-600 mb-1 flex items-center gap-1">
                <TrendingUp className="w-3 h-3" /> Growth
              </div>
              <ul className="text-gray-600 dark:text-gray-400 space-y-0.5">
                {signals.growth_indicators.slice(0, 2).map((g, i) => (
                  <li key={i}>• {g}</li>
                ))}
              </ul>
            </div>
          )}
          {signals.risk_factors && signals.risk_factors.length > 0 && (
            <div>
              <div className="font-medium text-orange-600 mb-1 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" /> Risks
              </div>
              <ul className="text-gray-600 dark:text-gray-400 space-y-0.5">
                {signals.risk_factors.slice(0, 2).map((r, i) => (
                  <li key={i}>• {r}</li>
                ))}
              </ul>
            </div>
          )}
          {signals.watch_for && signals.watch_for.length > 0 && (
            <div>
              <div className="font-medium text-blue-600 mb-1 flex items-center gap-1">
                <Target className="w-3 h-3" /> Watch
              </div>
              <ul className="text-gray-600 dark:text-gray-400 space-y-0.5">
                {signals.watch_for.slice(0, 2).map((w, i) => (
                  <li key={i}>• {w}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    );
  };

  // Render trend score with radar chart
  const renderTrendScore = (trend: TrendScore) => {
    return (
      <div className="space-y-2">
        <h5 className="text-xs font-medium text-gray-500 uppercase flex items-center gap-1">
          <Gauge className="w-3 h-3" /> Trend Score
        </h5>
        <div className="flex flex-col md:flex-row gap-4 items-center">
          {/* Radar Chart */}
          <div className="flex-shrink-0">
            <TopicScoreRadar trendScore={trend} size={160} />
          </div>
          {/* Numeric Grid */}
          <div className="flex-1 grid grid-cols-5 gap-2 text-center">
            {[
              { label: 'Volume', value: trend.volume },
              { label: 'Velocity', value: trend.velocity },
              { label: 'Diversity', value: trend.diversity },
              { label: 'Novelty', value: trend.novelty },
              { label: 'Overall', value: trend.composite },
            ].map((item, i) => (
              <div key={i} className="bg-gray-50 dark:bg-gray-800 rounded p-1.5">
                <div className={`text-lg font-bold ${getScoreColor(item.value)}`}>
                  {Math.round(item.value)}
                </div>
                <div className="text-xs text-gray-500">{item.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-amber-500" />
            Emerging Topics
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Emerging developments from your article corpus
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsScheduleOpen(true)}
            title="Schedule automatic detection"
            disabled={detecting}
          >
            <Clock className="w-4 h-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsConfigOpen(true)}
            title="Configure detection settings"
            disabled={detecting}
          >
            <Settings2 className="w-4 h-4" />
          </Button>
          {/* Export dropdown */}
          {emergingTopics.length > 0 && (
            <div className="relative" ref={exportMenuRef}>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setExportMenuOpen(!exportMenuOpen)}
                disabled={detecting}
                title="Export all detected themes"
              >
                <Download className="w-4 h-4 mr-1" />
                Export
                <ChevronDown className="w-3 h-3 ml-1" />
              </Button>
              {exportMenuOpen && (
                <div className="absolute right-0 top-full mt-1 w-44 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 py-1">
                  <button
                    onClick={() => {
                      ExportService.exportEmergingTopicsMarkdown(emergingTopics, topic);
                      setExportMenuOpen(false);
                    }}
                    className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                  >
                    <FileText className="w-4 h-4 text-blue-500" />
                    Export Markdown
                  </button>
                  <button
                    onClick={() => {
                      ExportService.exportEmergingTopicsCSV(emergingTopics);
                      setExportMenuOpen(false);
                    }}
                    className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                  >
                    <FileSpreadsheet className="w-4 h-4 text-green-500" />
                    Export CSV
                  </button>
                  <button
                    onClick={() => {
                      ExportService.exportEmergingTopicsPDF(emergingTopics, topic);
                      setExportMenuOpen(false);
                    }}
                    className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                  >
                    <FileDown className="w-4 h-4 text-red-500" />
                    Export PDF
                  </button>
                </div>
              )}
            </div>
          )}
          {(emergingTopics.length > 0 || highNoveltyArticles.length > 0) && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowClearConfirm(true)}
              disabled={detecting}
              title="Clear all detected topics from database"
            >
              <Trash2 className="w-4 h-4 mr-1" />
              Clear
            </Button>
          )}
          <Button
            onClick={runDetection}
            disabled={detecting}
            className="bg-pink-500 hover:bg-pink-600 text-white"
            title={topic ? `Scan ${topic}` : 'Scan all configured topics'}
          >
            {detecting ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Scanning...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 mr-2" />
                Scan
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Detection Progress */}
      {detecting && detectionProgress && (
        <Card>
          <CardContent className="py-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{detectionProgress.message}</span>
                <span className="text-gray-500">
                  {detectionProgress.progress ? `${Math.round(detectionProgress.progress)}%` : ''}
                </span>
              </div>
              {detectionProgress.progress && (
                <Progress value={detectionProgress.progress} className="h-2" />
              )}
              <div className="flex gap-4 text-xs text-gray-500">
                {detectionProgress.proposed_count !== undefined && (
                  <span>Proposed: {detectionProgress.proposed_count}</span>
                )}
                {detectionProgress.validated_count !== undefined && (
                  <span>Validated: {detectionProgress.validated_count}</span>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Stats Summary */}
      {!loading && emergingTopics.length > 0 && (
        <div className="grid grid-cols-4 gap-4">
          <Card>
            <CardContent className="py-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-purple-100 dark:bg-purple-900 rounded-lg">
                  <Sparkles className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold">{emergingTopics.length}</div>
                  <div className="text-xs text-gray-500">Total Themes</div>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-100 dark:bg-green-900 rounded-lg">
                  <TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold">
                    {emergingTopics.filter(t => t.velocity === 'accelerating').length}
                  </div>
                  <div className="text-xs text-gray-500">Accelerating</div>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 dark:bg-blue-900 rounded-lg">
                  <BarChart3 className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold">
                    {emergingTopics.reduce((sum, t) => sum + t.article_count, 0)}
                  </div>
                  <div className="text-xs text-gray-500">Total Articles</div>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-amber-100 dark:bg-amber-900 rounded-lg">
                  <Gauge className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold">
                    {Math.round(
                      emergingTopics.reduce((sum, t) => sum + (t.trend_score?.composite || t.confidence_score * 100), 0) / emergingTopics.length
                    )}
                  </div>
                  <div className="text-xs text-gray-500">Avg Score</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Emerging Topics Overview Dashboard */}
      {emergingTopics.length >= 2 && (
        <TopicComparisonDashboard
          topics={emergingTopics}
          onTopicClick={(clickedTopic) => {
            const element = document.getElementById(`topic-${clickedTopic.id}`);
            if (element) {
              element.scrollIntoView({ behavior: 'smooth', block: 'center' });
              setExpandedTopicId(clickedTopic.id);
            }
          }}
        />
      )}

      {/* Detected Themes - 2 column grid */}
      <div className="space-y-4">
        <h3 className="font-medium text-gray-900 dark:text-gray-100">Detected Themes</h3>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
          </div>
        ) : emergingTopics.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <Sparkles className="w-12 h-12 mx-auto text-gray-300 dark:text-gray-600 mb-4" />
              <h4 className="font-medium text-gray-900 dark:text-gray-100">No emerging themes detected</h4>
              <p className="text-sm text-gray-500 mt-1">
                Run detection to identify new and growing developments
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {emergingTopics.map((topicItem) => {
                const typeStyle = getTypeBadgeStyle(topicItem.detection_type);
                const velocityStyle = getVelocityStyle(topicItem.velocity);
                const isExpanded = expandedTopicId === topicItem.id;
                const details = topicDetails[topicItem.id];

                return (
                  <Card key={topicItem.id} id={`topic-${topicItem.id}`} className="overflow-hidden">
                    <CardContent className="p-4">
                      {/* Topic Header */}
                      <div
                        className="flex items-start justify-between cursor-pointer"
                        onClick={() => toggleTopicExpand(topicItem.id)}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-semibold text-gray-900 dark:text-gray-100">
                              {topicItem.topic_label}
                            </span>
                            <Badge className={`text-xs ${typeStyle.className}`}>
                              {typeStyle.icon}
                              <span className="ml-1">{typeStyle.label}</span>
                            </Badge>
                            {topicItem.synthesis?.urgency && (
                              <Badge className={`text-xs ${urgencyStyles[topicItem.synthesis.urgency]?.className}`}>
                                {urgencyStyles[topicItem.synthesis.urgency]?.label}
                              </Badge>
                            )}
                            {(topicItem.detection_count || 1) > 1 && (
                              <Badge variant="outline" className="text-xs bg-blue-50 dark:bg-blue-900/30">
                                <Clock className="w-3 h-3 mr-1" />
                                {topicItem.detection_count}x detected
                              </Badge>
                            )}
                            {topicItem.trajectory && (
                              <Badge variant="outline" className={`text-xs ${
                                topicItem.trajectory === 'rising' ? 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                                topicItem.trajectory === 'declining' ? 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                                'bg-gray-50 text-gray-700 dark:bg-gray-800 dark:text-gray-400'
                              }`}>
                                {topicItem.trajectory === 'rising' && <TrendingUp className="w-3 h-3 mr-1" />}
                                {topicItem.trajectory === 'declining' && <TrendingDown className="w-3 h-3 mr-1" />}
                                {topicItem.trajectory}
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                            {topicItem.topic_description}
                          </p>
                          {/* Trajectory Timeline - visual detection history */}
                          {topicItem.first_detection_date && (topicItem.detection_count || 1) > 1 && (
                            <div className="mt-2">
                              <TrajectoryTimeline
                                firstDetection={topicItem.first_detection_date}
                                lastDetection={topicItem.last_detection_date || topicItem.detection_date}
                                detectionCount={topicItem.detection_count || 1}
                                consecutiveDetections={topicItem.consecutive_detections || 1}
                                missedRuns={topicItem.missed_runs || 0}
                                trajectory={topicItem.trajectory || 'stable'}
                              />
                            </div>
                          )}
                          {/* Key Entities (from theme proposal) */}
                          {topicItem.key_entities && topicItem.key_entities.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-2">
                              {topicItem.key_entities.slice(0, 5).map((entity, i) => (
                                <Badge key={i} variant="outline" className="text-xs">
                                  {entity}
                                </Badge>
                              ))}
                            </div>
                          )}
                        </div>
                        <div className="flex items-start gap-2 ml-4">
                          {/* Ask Auspex Button */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleAskAuspex(topicItem);
                            }}
                            className="inline-flex items-center gap-1 text-sm text-pink-600 dark:text-pink-400 hover:text-pink-700 dark:hover:text-pink-300 font-medium transition-colors"
                            title="Ask Auspex about this topic"
                          >
                            <MessageSquare className="w-3.5 h-3.5" />
                            Ask Auspex
                          </button>

                          {/* Delete X Button */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setTopicToDelete(topicItem);
                            }}
                            className="p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded opacity-60 hover:opacity-100"
                            title="Delete topic"
                          >
                            <X className="w-4 h-4 text-gray-400 hover:text-red-500" />
                          </button>

                          {/* Menu Button */}
                          <div
                            className="relative"
                            ref={menuOpenId === topicItem.id ? menuRef : null}
                          >
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setMenuOpenId(menuOpenId === topicItem.id ? null : topicItem.id);
                              }}
                              className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                              title="More options"
                            >
                              <MoreVertical className="w-4 h-4 text-gray-400" />
                            </button>

                            {menuOpenId === topicItem.id && (
                              <div className="absolute right-0 top-full mt-1 w-32 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 py-1">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleTrackTopic(topicItem.id);
                                  }}
                                  className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                                >
                                  <Bookmark className={`w-4 h-4 ${trackedTopicIds.has(topicItem.id) ? 'fill-current text-amber-500' : ''}`} />
                                  {trackedTopicIds.has(topicItem.id) ? 'Saved' : 'Save'}
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleShareTopic(topicItem);
                                  }}
                                  className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                                >
                                  <Share2 className="w-4 h-4" /> Share
                                </button>
                              </div>
                            )}
                          </div>

                          {/* Stats */}
                          <div className="flex flex-col items-end gap-1">
                            <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
                              {topicItem.article_count}
                            </div>
                            <div className="text-xs text-gray-500">articles</div>
                            {/* Momentum Gauge - velocity indicator */}
                            <MomentumGauge
                              velocity={topicItem.velocity}
                              velocityScore={topicItem.trend_score?.velocity}
                              size="sm"
                            />
                            {topicItem.trend_score && (
                              <div className={`text-sm font-bold ${getScoreColor(topicItem.trend_score.composite)}`}>
                                {Math.round(topicItem.trend_score.composite)} score
                              </div>
                            )}
                            {/* Sparkline for topic history */}
                            {topicHistories[topicItem.id]?.length > 1 && (
                              <TopicSparkline
                                history={topicHistories[topicItem.id]}
                                width={60}
                                height={20}
                                showTrend={false}
                              />
                            )}
                            {isExpanded ? (
                              <ChevronUp className="w-4 h-4 text-gray-400 mt-1" />
                            ) : (
                              <ChevronDown className="w-4 h-4 text-gray-400 mt-1" />
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Expanded Details */}
                      {isExpanded && (
                        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 space-y-4">
                          {/* Why Emerging */}
                          {topicItem.why_emerging && (
                            <div className="bg-amber-50 dark:bg-amber-900/20 p-3 rounded text-sm">
                              <span className="font-medium">Why Emerging:</span> {topicItem.why_emerging}
                            </div>
                          )}

                          {/* Key Takeaway from synthesis */}
                          {topicItem.synthesis?.key_takeaway && (
                            <div className="bg-purple-50 dark:bg-purple-900/20 p-3 rounded text-sm">
                              <span className="font-medium">Key Takeaway:</span> {topicItem.synthesis.key_takeaway}
                            </div>
                          )}

                          {/* Trend Score */}
                          {topicItem.trend_score && renderTrendScore(topicItem.trend_score)}

                          {/* Word Cloud */}
                          {(topicItem.representative_keywords?.length > 0 || topicItem.key_entities?.length > 0) && (
                            <div className="space-y-2">
                              <h5 className="text-xs font-medium text-gray-500 uppercase">Key Terms</h5>
                              <TopicWordCloud
                                keywords={topicItem.representative_keywords || []}
                                entities={topicItem.key_entities || []}
                                themes={topicItem.key_themes || []}
                                maxWords={15}
                              />
                            </div>
                          )}

                          {/* Actors */}
                          {topicItem.actors && renderActors(topicItem.actors)}

                          {/* Events */}
                          {topicItem.events && renderEvents(topicItem.events)}

                          {/* Signals */}
                          {topicItem.signals && renderSignals(topicItem.signals)}

                          {/* Implications */}
                          {topicItem.implications && (
                            <div className="space-y-2">
                              <h5 className="text-xs font-medium text-gray-500 uppercase">Implications</h5>
                              <div className="grid grid-cols-3 gap-2 text-xs">
                                {topicItem.implications.industry_impact && (
                                  <div className="bg-gray-50 dark:bg-gray-800 p-2 rounded">
                                    <div className="font-medium mb-1">Industry</div>
                                    <p className="text-gray-600 dark:text-gray-400 line-clamp-3">
                                      {topicItem.implications.industry_impact}
                                    </p>
                                  </div>
                                )}
                                {topicItem.implications.regulatory && (
                                  <div className="bg-gray-50 dark:bg-gray-800 p-2 rounded">
                                    <div className="font-medium mb-1">Regulatory</div>
                                    <p className="text-gray-600 dark:text-gray-400 line-clamp-3">
                                      {topicItem.implications.regulatory}
                                    </p>
                                  </div>
                                )}
                                {topicItem.implications.market && (
                                  <div className="bg-gray-50 dark:bg-gray-800 p-2 rounded">
                                    <div className="font-medium mb-1">Market</div>
                                    <p className="text-gray-600 dark:text-gray-400 line-clamp-3">
                                      {topicItem.implications.market}
                                    </p>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Sample Articles from details */}
                          {details?.articles && details.articles.length > 0 && (
                            <div>
                              <div className="flex items-center justify-between mb-2">
                                <h5 className="text-xs font-medium text-gray-500 uppercase">
                                  Sample Articles
                                </h5>
                                {details.model_used && (
                                  <span className="text-xs text-gray-400">
                                    Model: {details.model_used}
                                  </span>
                                )}
                              </div>
                              <div className="space-y-2">
                                {details.articles.slice(0, 5).map((article: any, i: number) => (
                                  <div
                                    key={i}
                                    className="flex items-start gap-2 p-2 rounded hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      onArticleClick?.({ uri: article.uri });
                                    }}
                                  >
                                    <ExternalLink className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                                    <div className="min-w-0 flex-1">
                                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-1">
                                        {article.title}
                                      </div>
                                      <div className="text-xs text-gray-500 flex items-center gap-2 flex-wrap">
                                        <span>{article.news_source} · {article.publication_date}</span>
                                        {article.novelty_score > 0 && (
                                          <span className="text-amber-600 font-medium">
                                            {Math.round(article.novelty_score)} novelty
                                          </span>
                                        )}
                                        {article.knn_distance_score != null && (
                                          <span className="text-blue-600 font-medium">
                                            {article.knn_distance_score.toFixed(2)} dist
                                          </span>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Loading indicator for details */}
                          {!details && !topicItem.actors && (
                            <div className="flex items-center justify-center py-4">
                              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
                            </div>
                          )}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
          </div>
        )}
      </div>

      {/* High Novelty Articles Section - Bottom */}
      <div className="space-y-4 mt-8 pt-6 border-t border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-500" />
              High Novelty Articles
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              Articles with unusually high novelty scores (detected during scanning)
            </p>
          </div>
        </div>

        {highNoveltyArticles.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center">
              <Zap className="w-10 h-10 mx-auto text-gray-300 dark:text-gray-600 mb-3" />
              <p className="text-sm text-gray-500">No high novelty articles found</p>
              <p className="text-xs text-gray-400 mt-1">
                Run a scan to calculate novelty scores for recent articles
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {highNoveltyArticles.map((article, i) => (
              <Card
                key={i}
                className="cursor-pointer hover:shadow-md transition-shadow"
                onClick={() => onArticleClick?.({ uri: article.article_uri })}
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2">
                        {article.article_title || article.title || 'Untitled'}
                      </div>
                      <div className="text-xs text-gray-500 mt-2 flex items-center gap-2">
                        <Clock className="w-3 h-3" />
                        {article.publication_date || 'Unknown date'}
                      </div>
                      {article.is_outlier && (
                        <Badge className="mt-2 bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 text-xs">
                          <Zap className="w-3 h-3 mr-1" />
                          Outlier
                        </Badge>
                      )}
                    </div>
                    <div className="text-center shrink-0">
                      <div className="text-2xl font-bold text-amber-600">
                        {Math.round(article.composite_novelty_score)}
                      </div>
                      <div className="text-xs text-gray-500">novelty</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Config Modal */}
      <EmergingTopicsConfigModal
        open={isConfigOpen}
        onClose={() => setIsConfigOpen(false)}
        config={config}
        onSave={setConfig}
        availableModels={availableModels}
      />

      {/* Schedule Modal */}
      <EmergingTopicsScheduleModal
        open={isScheduleOpen}
        onClose={() => setIsScheduleOpen(false)}
      />

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!topicToDelete} onOpenChange={() => setTopicToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Emerging Topic?</DialogTitle>
            <DialogDescription>
              "{topicToDelete?.topic_label}" will be permanently deleted.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setTopicToDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => topicToDelete && handleDeleteTopic(topicToDelete.id)}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Clear All Confirmation Dialog */}
      <Dialog open={showClearConfirm} onOpenChange={setShowClearConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-500" />
              Clear All Detected Topics?
            </DialogTitle>
            <DialogDescription className="space-y-2">
              <p>
                This will permanently delete <strong>{emergingTopics.length} detected topics</strong> from the database.
              </p>
              <p className="text-amber-600 dark:text-amber-400 font-medium">
                Warning: This will reset all detection counters and tracking history. Topics will need to be re-detected.
              </p>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowClearConfirm(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                try {
                  const params = topic ? `?topic=${encodeURIComponent(topic)}` : '';
                  const res = await fetch(`/api/emerging-topics/topics${params}`, {
                    method: 'DELETE',
                    credentials: 'include',
                  });
                  if (res.ok) {
                    setEmergingTopics([]);
                    setHighNoveltyArticles([]);
                    setExpandedTopicId(null);
                    setTopicDetails({});
                  }
                } catch (err) {
                  console.error('Error clearing topics:', err);
                }
                setShowClearConfirm(false);
              }}
            >
              Clear All Topics
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  );
}

export default EmergingTopicsTab;
