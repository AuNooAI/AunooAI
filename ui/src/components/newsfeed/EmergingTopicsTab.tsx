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
  Minus,
  Zap,
  Circle,
  AlertCircle,
  Play,
  ChevronDown,
  ChevronUp,
  ChevronRight,
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
  LayoutGrid,
  List,
  Archive,
  RotateCcw,
  Compass,
} from 'lucide-react';
import { openAuspexWithQuery } from '../../utils/auspexEvents';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import {
  EmergingTopicsConfigModal,
  EmergingTopicsConfig,
  loadEmergingTopicsConfig,
} from './EmergingTopicsConfigModal';
import { EmergingTopicsScheduleModal } from './EmergingTopicsScheduleModal';
import { ShareModal, type ShareEmergingTopicData, type ShareData } from '../ShareModal';
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
  urgency?: 'low' | 'medium' | 'high';
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

interface OrganizationImplications {
  strategic_relevance?: string;
  stakeholder_impact?: string;
  risk_assessment?: string;
  recommended_response?: string;
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
  organization_implications?: OrganizationImplications;
  future_horizons?: any;
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
  low: { label: 'Low Urgency', className: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200' },
  medium: { label: 'Medium Urgency', className: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-200' },
  high: { label: 'High Urgency', className: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200' },
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

  // Retired themes state
  const [retiredTopics, setRetiredTopics] = useState<EmergingTopic[]>([]);
  const [showRetired, setShowRetired] = useState(false);
  const [loadingRetired, setLoadingRetired] = useState(false);

  // Menu state
  const [menuOpenId, setMenuOpenId] = useState<number | null>(null);

  // Filter state for Trending Themes (multiselect)
  const [urgencyFilters, setUrgencyFilters] = useState<Set<string>>(new Set());
  const [velocityFilters, setVelocityFilters] = useState<Set<string>>(new Set());

  // View mode: 'cards' or 'table'
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');

  // Future Horizons loading state
  const [horizonsLoading, setHorizonsLoading] = useState<number | null>(null);
  const [showHorizonsModal, setShowHorizonsModal] = useState(false);
  const [horizonsResult, setHorizonsResult] = useState<any>(null);
  const [horizonsTopicLabel, setHorizonsTopicLabel] = useState<string>('');
  const [horizonsTopicId, setHorizonsTopicId] = useState<number | null>(null);
  const [savingHorizons, setSavingHorizons] = useState(false);

  const toggleUrgencyFilter = (value: string) => {
    setUrgencyFilters(prev => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  };

  const toggleVelocityFilter = (value: string) => {
    setVelocityFilters(prev => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  };
  const menuRef = useRef<HTMLDivElement>(null);

  // Export menu state
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);

  // Share modal state
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareData, setShareData] = useState<ShareData | null>(null);

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

  // Fetch retired themes
  const fetchRetiredTopics = async () => {
    setLoadingRetired(true);
    try {
      const params = new URLSearchParams();
      if (topic) params.append('topic', topic);
      params.append('limit', '50');

      const response = await fetch(`/api/emerging-topics/retired?${params}`, {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        setRetiredTopics(data.topics || []);
      }
    } catch (err) {
      console.error('Error fetching retired topics:', err);
    } finally {
      setLoadingRetired(false);
    }
  };

  // Retire theme handler
  const handleRetireTopic = async (topicId: number) => {
    try {
      const res = await fetch(`/api/emerging-topics/topics/${topicId}/retire`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'manual' }),
      });
      if (res.ok) {
        // Move from active to retired
        const topic = emergingTopics.find(t => t.id === topicId);
        if (topic) {
          setEmergingTopics(prev => prev.filter(t => t.id !== topicId));
          setRetiredTopics(prev => [{ ...topic, status: 'retired' } as any, ...prev]);
        }
      }
    } catch (err) {
      console.error('Error retiring topic:', err);
    }
  };

  // Restore theme handler
  const handleRestoreTopic = async (topicId: number) => {
    try {
      const res = await fetch(`/api/emerging-topics/topics/${topicId}/restore`, {
        method: 'POST',
        credentials: 'include',
      });
      if (res.ok) {
        // Move from retired to active
        const topic = retiredTopics.find(t => t.id === topicId);
        if (topic) {
          setRetiredTopics(prev => prev.filter(t => t.id !== topicId));
          setEmergingTopics(prev => [{ ...topic, status: 'active' } as any, ...prev]);
        }
      }
    } catch (err) {
      console.error('Error restoring topic:', err);
    }
  };

  // Fetch retired topics when section is expanded
  useEffect(() => {
    if (showRetired && retiredTopics.length === 0) {
      fetchRetiredTopics();
    }
  }, [showRetired]);

  // Share topic handler - opens share modal with full topic data including articles
  const handleShareTopic = async (topic: EmergingTopic) => {
    // Get article details - check cache first, then fetch if needed
    let articles: any[] = topicDetails[topic.id]?.articles || [];

    if (articles.length === 0) {
      try {
        const response = await fetch(`/api/emerging-topics/topics/${topic.id}`);
        if (response.ok) {
          const data = await response.json();
          articles = data.articles || [];
          // Cache for future use
          setTopicDetails(prev => ({ ...prev, [topic.id]: data }));
        }
      } catch (err) {
        console.error('Failed to fetch topic articles for share:', err);
      }
    }

    setShareData({
      type: 'emerging_topic',
      topic_id: topic.id,
      topic_label: topic.topic_label,
      topic_description: topic.topic_description,
      score: topic.trend_score?.composite || Math.round(topic.confidence_score * 100),
      urgency: topic.synthesis?.urgency || topic.trend_score?.urgency || 'medium',
      velocity: topic.velocity,
      article_count: topic.article_count,
      key_themes: topic.key_themes,
      key_entities: topic.key_entities,
      why_emerging: topic.why_emerging,
      // Enhanced fields
      key_takeaway: topic.synthesis?.key_takeaway,
      trend_score: topic.trend_score ? {
        volume: topic.trend_score.volume,
        velocity: topic.trend_score.velocity,
        diversity: topic.trend_score.diversity,
        novelty: topic.trend_score.novelty,
        composite: topic.trend_score.composite,
      } : undefined,
      actors: topic.actors ? {
        companies: topic.actors.companies,
        people: topic.actors.people,
        organizations: topic.actors.organizations,
      } : undefined,
      events: topic.events ? {
        trigger_event: topic.events.trigger_event,
        timeline: topic.events.timeline,
        current_status: topic.events.current_status,
      } : undefined,
      implications: topic.implications ? {
        industry_impact: topic.implications.industry_impact,
        regulatory: topic.implications.regulatory,
        market: topic.implications.market,
      } : undefined,
      organization_implications: topic.organization_implications ? {
        strategic_relevance: topic.organization_implications.strategic_relevance,
        stakeholder_impact: topic.organization_implications.stakeholder_impact,
        risk_assessment: topic.organization_implications.risk_assessment,
        recommended_response: topic.organization_implications.recommended_response,
      } : undefined,
      articles: articles.slice(0, 10).map((a: any) => ({
        title: a.title,
        news_source: a.news_source,
        publication_date: a.publication_date,
        uri: a.uri,
      })),
    });
    setShowShareModal(true);
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
  const handleAskAuspex = async (emergingTopic: EmergingTopic) => {
    // Get article details - check cache first, then fetch if needed
    let articles: any[] = topicDetails[emergingTopic.id]?.articles || [];

    if (articles.length === 0) {
      try {
        const response = await fetch(`/api/emerging-topics/topics/${emergingTopic.id}`);
        if (response.ok) {
          const data = await response.json();
          articles = data.articles || [];
          // Cache for future use
          setTopicDetails(prev => ({ ...prev, [emergingTopic.id]: data }));
        }
      } catch (err) {
        console.error('Failed to fetch topic articles:', err);
      }
    }

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

    // Build article details section
    let articlesSection = '';
    if (articles.length > 0) {
      articlesSection = `\nSOURCE ARTICLES (${articles.length} articles analyzed):\n`;
      articles.slice(0, 10).forEach((article: any, i: number) => {
        articlesSection += `\n${i + 1}. "${article.title}"`;
        articlesSection += `\n   Source: ${article.news_source || 'Unknown'}`;
        articlesSection += `\n   Date: ${article.publication_date || 'Unknown'}`;
        articlesSection += `\n   URI: ${article.uri}`;
        if (article.summary) {
          articlesSection += `\n   Summary: ${article.summary.substring(0, 300)}...`;
        }
      });
      articlesSection += '\n';
    }

    const prompt = `Analyze this emerging topic: "${emergingTopic.topic_label}"

DESCRIPTION:
${emergingTopic.topic_description}

${emergingTopic.why_emerging ? `WHY EMERGING:\n${emergingTopic.why_emerging}\n` : ''}METRICS:
- Articles: ${emergingTopic.article_count}
- Velocity: ${emergingTopic.velocity}
- Detection Type: ${emergingTopic.detection_type}
${emergingTopic.trend_score ? `- Trend Score: ${Math.round(emergingTopic.trend_score.composite)}/100` : ''}
${keywordsSection}${themesSection}${actorsList.length ? `KEY ACTORS:\n${actorsList.join('\n')}\n` : ''}${emergingTopic.events?.trigger_event ? `TRIGGER EVENT:\n${emergingTopic.events.trigger_event}\n` : ''}${emergingTopic.synthesis?.key_takeaway ? `KEY TAKEAWAY:\n${emergingTopic.synthesis.key_takeaway}\n` : ''}${emergingTopic.implications?.industry_impact ? `INDUSTRY IMPACT:\n${emergingTopic.implications.industry_impact}\n` : ''}${articlesSection}
Please provide:
1. Deep analysis of this emerging trend (use the source articles above for context)
2. Potential implications for our organization
3. Key developments to monitor
4. Recommended actions or responses
5. Related trends or connections to explore`;

    // Pass the topic filter to Auspex so it knows which collection to search
    openAuspexWithQuery(prompt, false, topic || 'All');
  };

  // Send to Future Horizons handler
  const handleSendToHorizons = async (topicItem: EmergingTopic) => {
    if (!topicItem.id) return;

    setHorizonsLoading(topicItem.id);
    setHorizonsTopicLabel(topicItem.topic_label);
    setHorizonsTopicId(topicItem.id);
    try {
      const response = await fetch(`/api/emerging-topics/topics/${topicItem.id}/future-horizons`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: config.model,
          future_horizon: 15,
        }),
      });

      if (response.ok) {
        const result = await response.json();
        setHorizonsResult(result);
        setShowHorizonsModal(true);
      } else {
        const error = await response.json();
        console.error('Failed to run Future Horizons analysis:', error);
        alert(`Failed to run Future Horizons: ${error.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to run Future Horizons analysis:', error);
      alert('Failed to run Future Horizons analysis. Please try again.');
    } finally {
      setHorizonsLoading(null);
    }
  };

  // Save Future Horizons to theme
  const handleSaveHorizons = async () => {
    if (!horizonsTopicId || !horizonsResult) return;

    setSavingHorizons(true);
    try {
      const response = await fetch(`/api/emerging-topics/topics/${horizonsTopicId}/save-horizons`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(horizonsResult),
      });

      if (response.ok) {
        // Update local state to reflect saved horizons
        setEmergingTopics(prev => prev.map(t =>
          t.id === horizonsTopicId
            ? { ...t, future_horizons: horizonsResult }
            : t
        ));
        setShowHorizonsModal(false);
      } else {
        const error = await response.json();
        alert(`Failed to save: ${error.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to save Future Horizons:', error);
      alert('Failed to save Future Horizons. Please try again.');
    } finally {
      setSavingHorizons(false);
    }
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

  // Render events section with visual timeline
  const renderEvents = (events: Events) => {
    if (!events?.trigger_event && !events?.timeline?.length && !events?.current_status) return null;

    // Parse timeline items to extract date and event
    const parseTimelineItem = (item: string | { date?: string; event?: string }): { date: string; event: string } => {
      if (typeof item === 'object' && item !== null) {
        return { date: item.date || '', event: item.event || '' };
      }
      // Try to parse "Date - Event" or "Date: Event" format from string
      const str = String(item);
      const dateMatch = str.match(/^([A-Za-z]+\s+\d{1,2},?\s*\d{0,4}|\d{4}-\d{2}-\d{2}|[A-Za-z]+\s+\d{4}|Prior to [^-:]+)\s*[-:]\s*/i);
      if (dateMatch) {
        return { date: dateMatch[1].trim(), event: str.substring(dateMatch[0].length).trim() };
      }
      return { date: '', event: str };
    };

    const timelineItems = (events.timeline || []).map(parseTimelineItem);

    return (
      <div className="space-y-3">
        <h5 className="text-xs font-medium text-gray-500 uppercase flex items-center gap-1">
          <Clock className="w-3 h-3" /> Events Timeline
        </h5>

        {/* Visual Timeline */}
        <div className="relative">
          {/* Trigger Event */}
          {events.trigger_event && typeof events.trigger_event === 'string' && (
            <div className="flex items-start gap-3 mb-3">
              <div className="flex flex-col items-center">
                <div className="w-4 h-4 rounded-full bg-red-500 border-2 border-red-300 flex-shrink-0 mt-1" />
                <div className="w-0.5 bg-gray-300 dark:bg-gray-600 flex-grow min-h-[20px]" />
              </div>
              <div className="flex-1 pb-2">
                <div className="text-xs font-semibold text-red-600 dark:text-red-400 uppercase tracking-wide">Trigger</div>
                <p className="text-sm text-gray-700 dark:text-gray-300 mt-1">{events.trigger_event}</p>
              </div>
            </div>
          )}

          {/* Timeline Items */}
          {timelineItems.map((item, i) => (
            <div key={i} className="flex items-start gap-3 mb-3">
              <div className="flex flex-col items-center">
                <div className="w-3 h-3 rounded-full bg-blue-500 border-2 border-blue-300 flex-shrink-0 mt-1.5" />
                {(i < timelineItems.length - 1 || events.current_status) && (
                  <div className="w-0.5 bg-gray-300 dark:bg-gray-600 flex-grow min-h-[20px]" />
                )}
              </div>
              <div className="flex-1 pb-2">
                {item.date && (
                  <div className="text-xs font-medium text-blue-600 dark:text-blue-400">{item.date}</div>
                )}
                <p className="text-sm text-gray-700 dark:text-gray-300">{item.event}</p>
              </div>
            </div>
          ))}

          {/* Current Status */}
          {events.current_status && typeof events.current_status === 'string' && (
            <div className="flex items-start gap-3">
              <div className="flex flex-col items-center">
                <div className="w-4 h-4 rounded-full bg-green-500 border-2 border-green-300 flex-shrink-0 mt-1" />
              </div>
              <div className="flex-1">
                <div className="text-xs font-semibold text-green-600 dark:text-green-400 uppercase tracking-wide">Current Status</div>
                <p className="text-sm text-gray-700 dark:text-gray-300 mt-1">{events.current_status}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  // Render signals section
  const renderSignals = (signals: Signals) => {
    // Helper to safely render signal items - handles both strings and objects
    const safeRender = (item: any): string => {
      if (typeof item === 'string') return item;
      if (typeof item === 'object' && item !== null) return JSON.stringify(item);
      return String(item);
    };

    // Helper to get array of strings from signals field
    const getStringArray = (arr: any): string[] => {
      if (!Array.isArray(arr)) return [];
      return arr.map(safeRender).filter(Boolean);
    };

    const growthIndicators = getStringArray(signals?.growth_indicators);
    const riskFactors = getStringArray(signals?.risk_factors);
    const watchFor = getStringArray(signals?.watch_for);

    const hasSignals = growthIndicators.length || riskFactors.length || watchFor.length;
    if (!hasSignals) return null;

    return (
      <div className="space-y-2">
        <h5 className="text-xs font-medium text-gray-500 uppercase flex items-center gap-1">
          <Eye className="w-3 h-3" /> Signals
        </h5>
        <div className="grid grid-cols-3 gap-2 text-xs">
          {growthIndicators.length > 0 && (
            <div>
              <div className="font-medium text-green-600 mb-1 flex items-center gap-1">
                <TrendingUp className="w-3 h-3" /> Growth
              </div>
              <ul className="text-gray-600 dark:text-gray-400 space-y-0.5">
                {growthIndicators.slice(0, 2).map((g, i) => (
                  <li key={i}>• {g}</li>
                ))}
              </ul>
            </div>
          )}
          {riskFactors.length > 0 && (
            <div>
              <div className="font-medium text-orange-600 mb-1 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" /> Risks
              </div>
              <ul className="text-gray-600 dark:text-gray-400 space-y-0.5">
                {riskFactors.slice(0, 2).map((r, i) => (
                  <li key={i}>• {r}</li>
                ))}
              </ul>
            </div>
          )}
          {watchFor.length > 0 && (
            <div>
              <div className="font-medium text-blue-600 mb-1 flex items-center gap-1">
                <Target className="w-3 h-3" /> Watch
              </div>
              <ul className="text-gray-600 dark:text-gray-400 space-y-0.5">
                {watchFor.slice(0, 2).map((w, i) => (
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
            Emerging Themes
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
                title="Export all trending themes"
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
        <div className="grid grid-cols-5 gap-3">
          {/* Total Themes */}
          <Card>
            <CardContent className="py-3">
              <div className="text-center">
                <div className="text-xl font-bold">{emergingTopics.length}</div>
                <div className="text-xs text-gray-500">Total Themes</div>
              </div>
            </CardContent>
          </Card>
          {/* Total Signals */}
          <Card>
            <CardContent className="py-3">
              <div className="text-center">
                <div className="text-xl font-bold">
                  {emergingTopics.reduce((sum, t) => sum + t.article_count, 0)}
                </div>
                <div className="text-xs text-gray-500">Total Signals</div>
              </div>
            </CardContent>
          </Card>
          {/* Accelerating */}
          <Card>
            <CardContent className="py-3">
              <div className="text-center">
                <div className="text-xl font-bold text-green-600">
                  {emergingTopics.filter(t => t.velocity === 'accelerating').length}
                </div>
                <div className="text-xs text-gray-500 flex items-center justify-center gap-1">
                  <TrendingUp className="w-3 h-3" /> Accelerating
                </div>
              </div>
            </CardContent>
          </Card>
          {/* Stable */}
          <Card>
            <CardContent className="py-3">
              <div className="text-center">
                <div className="text-xl font-bold text-blue-600">
                  {emergingTopics.filter(t => t.velocity === 'stable').length}
                </div>
                <div className="text-xs text-gray-500 flex items-center justify-center gap-1">
                  <Minus className="w-3 h-3" /> Stable
                </div>
              </div>
            </CardContent>
          </Card>
          {/* Slowing */}
          <Card>
            <CardContent className="py-3">
              <div className="text-center">
                <div className="text-xl font-bold text-amber-600">
                  {emergingTopics.filter(t => t.velocity === 'decelerating').length}
                </div>
                <div className="text-xs text-gray-500 flex items-center justify-center gap-1">
                  <TrendingDown className="w-3 h-3" /> Slowing
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Emerging Themes Overview Dashboard */}
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

      {/* Trending Themes - 2 column grid */}
      <div className="space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <h3 className="font-medium text-gray-900 dark:text-gray-100">Trending Themes</h3>
            {/* View toggle */}
            <div className="flex items-center border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
              <button
                onClick={() => setViewMode('cards')}
                className={`p-1.5 transition-colors ${
                  viewMode === 'cards'
                    ? 'bg-pink-100 text-pink-600 dark:bg-pink-900/50 dark:text-pink-400'
                    : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
                title="Card view"
              >
                <LayoutGrid className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('table')}
                className={`p-1.5 transition-colors ${
                  viewMode === 'table'
                    ? 'bg-pink-100 text-pink-600 dark:bg-pink-900/50 dark:text-pink-400'
                    : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
                title="Table view"
              >
                <List className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Filter badges */}
          {!loading && emergingTopics.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-gray-500">Filter:</span>
              {/* Urgency filters (multiselect) */}
              <button
                onClick={() => toggleUrgencyFilter('high')}
                className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                  urgencyFilters.has('high')
                    ? 'bg-red-100 border-red-300 text-red-700 dark:bg-red-900/50 dark:border-red-700 dark:text-red-300'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                High Urgency
              </button>
              <button
                onClick={() => toggleUrgencyFilter('medium')}
                className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                  urgencyFilters.has('medium')
                    ? 'bg-amber-100 border-amber-300 text-amber-700 dark:bg-amber-900/50 dark:border-amber-700 dark:text-amber-300'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                Medium
              </button>
              <button
                onClick={() => toggleUrgencyFilter('low')}
                className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                  urgencyFilters.has('low')
                    ? 'bg-green-100 border-green-300 text-green-700 dark:bg-green-900/50 dark:border-green-700 dark:text-green-300'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                Low
              </button>
              <span className="text-gray-300 dark:text-gray-600">|</span>
              {/* Velocity filters (multiselect) */}
              <button
                onClick={() => toggleVelocityFilter('accelerating')}
                className={`px-2 py-0.5 text-xs rounded-full border transition-colors flex items-center gap-1 ${
                  velocityFilters.has('accelerating')
                    ? 'bg-green-100 border-green-300 text-green-700 dark:bg-green-900/50 dark:border-green-700 dark:text-green-300'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                <TrendingUp className="w-3 h-3" /> Accelerating
              </button>
              <button
                onClick={() => toggleVelocityFilter('stable')}
                className={`px-2 py-0.5 text-xs rounded-full border transition-colors flex items-center gap-1 ${
                  velocityFilters.has('stable')
                    ? 'bg-blue-100 border-blue-300 text-blue-700 dark:bg-blue-900/50 dark:border-blue-700 dark:text-blue-300'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                <Minus className="w-3 h-3" /> Stable
              </button>
              <button
                onClick={() => toggleVelocityFilter('decelerating')}
                className={`px-2 py-0.5 text-xs rounded-full border transition-colors flex items-center gap-1 ${
                  velocityFilters.has('decelerating')
                    ? 'bg-amber-100 border-amber-300 text-amber-700 dark:bg-amber-900/50 dark:border-amber-700 dark:text-amber-300'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                <TrendingDown className="w-3 h-3" /> Slowing
              </button>
              {(urgencyFilters.size > 0 || velocityFilters.size > 0) && (
                <button
                  onClick={() => { setUrgencyFilters(new Set()); setVelocityFilters(new Set()); }}
                  className="px-2 py-0.5 text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                >
                  Clear
                </button>
              )}
            </div>
          )}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
          </div>
        ) : emergingTopics.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <Sparkles className="w-12 h-12 mx-auto text-gray-300 dark:text-gray-600 mb-4" />
              <h4 className="font-medium text-gray-900 dark:text-gray-100">No trending themes detected</h4>
              <p className="text-sm text-gray-500 mt-1">
                Run detection to identify new and growing developments
              </p>
            </CardContent>
          </Card>
        ) : (() => {
          // Apply filters (multiselect - show topics matching ANY selected filter in each category)
          const filteredTopics = emergingTopics.filter(t => {
            const topicUrgency = t.synthesis?.urgency || t.trend_score?.urgency || '';
            if (urgencyFilters.size > 0 && !urgencyFilters.has(topicUrgency)) return false;
            if (velocityFilters.size > 0 && !velocityFilters.has(t.velocity)) return false;
            return true;
          });

          if (filteredTopics.length === 0) {
            return (
              <Card>
                <CardContent className="py-8 text-center">
                  <p className="text-sm text-gray-500">No themes match the selected filters</p>
                  <button
                    onClick={() => { setUrgencyFilters(new Set()); setVelocityFilters(new Set()); }}
                    className="mt-2 text-sm text-blue-600 hover:text-blue-700"
                  >
                    Clear filters
                  </button>
                </CardContent>
              </Card>
            );
          }

          // Table view
          if (viewMode === 'table') {
            return (
              <div className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead className="bg-gray-50 dark:bg-gray-800">
                    <tr className="border-b border-gray-200 dark:border-gray-700">
                      <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300" style={{minWidth: '200px'}}>Theme</th>
                      <th className="px-2 py-2 text-center font-medium text-gray-700 dark:text-gray-300" style={{minWidth: '50px'}}>Score</th>
                      <th className="px-2 py-2 text-center font-medium text-gray-700 dark:text-gray-300" style={{minWidth: '40px'}}>Vol</th>
                      <th className="px-2 py-2 text-center font-medium text-gray-700 dark:text-gray-300" style={{minWidth: '40px'}}>Div</th>
                      <th className="px-2 py-2 text-center font-medium text-gray-700 dark:text-gray-300" style={{minWidth: '40px'}}>Nov</th>
                      <th className="px-2 py-2 text-center font-medium text-gray-700 dark:text-gray-300" style={{minWidth: '50px'}}>Signals</th>
                      <th className="px-2 py-2 text-center font-medium text-gray-700 dark:text-gray-300" style={{minWidth: '80px'}}>Urgency</th>
                      <th className="px-2 py-2 text-center font-medium text-gray-700 dark:text-gray-300" style={{minWidth: '80px'}}>Velocity</th>
                      <th className="px-2 py-2 text-center font-medium text-gray-700 dark:text-gray-300" style={{minWidth: '70px'}}>Type</th>
                      <th className="px-2 py-2 text-right font-medium text-gray-700 dark:text-gray-300" style={{minWidth: '80px'}}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTopics.map((topicItem) => {
                      const typeStyle = getTypeBadgeStyle(topicItem.detection_type);
                      const urgency = topicItem.synthesis?.urgency || topicItem.trend_score?.urgency || 'medium';
                      const score = topicItem.trend_score?.composite || Math.round((topicItem.confidence_score || 0) * 100);

                      return (
                        <tr
                          key={topicItem.id}
                          id={`topic-${topicItem.id}`}
                          className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 border-b border-gray-100 dark:border-gray-800"
                          onClick={() => {
                            setViewMode('cards');
                            setExpandedTopicId(topicItem.id);
                            setTimeout(() => {
                              document.getElementById(`topic-${topicItem.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            }, 100);
                          }}
                        >
                          <td className="px-3 py-2">
                            <div>
                              <div className="font-medium text-gray-900 dark:text-gray-100 line-clamp-1">
                                {topicItem.topic_label}
                              </div>
                              <div className="text-xs text-gray-500 line-clamp-1 mt-0.5">
                                {topicItem.topic_description}
                              </div>
                            </div>
                          </td>
                          <td className="px-2 py-2 text-center">
                            <span className={`font-bold ${getScoreColor(score)}`}>
                              {Math.round(score)}
                            </span>
                          </td>
                          <td className="px-2 py-2 text-center">
                            <span className="text-sm text-gray-600 dark:text-gray-400">
                              {topicItem.trend_score?.volume != null ? Math.round(topicItem.trend_score.volume) : '-'}
                            </span>
                          </td>
                          <td className="px-2 py-2 text-center">
                            <span className="text-sm text-gray-600 dark:text-gray-400">
                              {topicItem.trend_score?.diversity != null ? Math.round(topicItem.trend_score.diversity) : '-'}
                            </span>
                          </td>
                          <td className="px-2 py-2 text-center">
                            <span className="text-sm text-gray-600 dark:text-gray-400">
                              {topicItem.trend_score?.novelty != null ? Math.round(topicItem.trend_score.novelty) : '-'}
                            </span>
                          </td>
                          <td className="px-2 py-2 text-center">
                            <span className="font-medium">{topicItem.article_count}</span>
                          </td>
                          <td className="px-2 py-2 text-center">
                            <Badge className={`text-xs ${urgencyStyles[urgency]?.className || 'bg-gray-100 text-gray-700'}`}>
                              {urgencyStyles[urgency]?.label || urgency}
                            </Badge>
                          </td>
                          <td className="px-2 py-2 text-center">
                            <div className="flex items-center justify-center gap-1">
                              {topicItem.velocity === 'accelerating' && <TrendingUp className="w-3.5 h-3.5 text-green-500" />}
                              {topicItem.velocity === 'stable' && <Minus className="w-3.5 h-3.5 text-gray-400" />}
                              {topicItem.velocity === 'decelerating' && <TrendingDown className="w-3.5 h-3.5 text-amber-500" />}
                              <span className="text-xs capitalize">{topicItem.velocity}</span>
                            </div>
                          </td>
                          <td className="px-2 py-2 text-center">
                            <Badge className={`text-xs ${typeStyle.className}`}>
                              {typeStyle.label}
                            </Badge>
                          </td>
                          <td className="px-2 py-2 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleAskAuspex(topicItem);
                                }}
                                className="p-1 text-pink-600 hover:text-pink-700 hover:bg-pink-50 dark:hover:bg-pink-900/20 rounded"
                                title="Ask Auspex"
                              >
                                <MessageSquare className="w-4 h-4" />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleShareTopic(topicItem);
                                }}
                                className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                                title="Share"
                              >
                                <Share2 className="w-4 h-4" />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRetireTopic(topicItem.id);
                                }}
                                className="p-1 text-gray-400 hover:text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-900/20 rounded"
                                title="Retire (archive)"
                              >
                                <Archive className="w-4 h-4" />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setTopicToDelete(topicItem);
                                }}
                                className="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                                title="Delete permanently"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            );
          }

          // Card view
          return (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {filteredTopics.map((topicItem) => {
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
                          <p className="text-sm text-gray-600 dark:text-gray-400">
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
                          {/* Retire Button */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRetireTopic(topicItem.id);
                            }}
                            className="p-1 hover:bg-amber-100 dark:hover:bg-amber-900/30 rounded opacity-60 hover:opacity-100"
                            title="Retire (archive this theme)"
                          >
                            <Archive className="w-4 h-4 text-gray-400 hover:text-amber-500" />
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
                          {topicItem.synthesis?.key_takeaway && typeof topicItem.synthesis.key_takeaway === 'string' && (
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
                              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                                {topicItem.implications.industry_impact && typeof topicItem.implications.industry_impact === 'string' && (
                                  <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded">
                                    <div className="font-medium mb-1 text-gray-700 dark:text-gray-300">Industry</div>
                                    <p className="text-gray-600 dark:text-gray-400">
                                      {topicItem.implications.industry_impact}
                                    </p>
                                  </div>
                                )}
                                {topicItem.implications.regulatory && typeof topicItem.implications.regulatory === 'string' && (
                                  <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded">
                                    <div className="font-medium mb-1 text-gray-700 dark:text-gray-300">Regulatory</div>
                                    <p className="text-gray-600 dark:text-gray-400">
                                      {topicItem.implications.regulatory}
                                    </p>
                                  </div>
                                )}
                                {topicItem.implications.market && typeof topicItem.implications.market === 'string' && (
                                  <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded">
                                    <div className="font-medium mb-1 text-gray-700 dark:text-gray-300">Market</div>
                                    <p className="text-gray-600 dark:text-gray-400">
                                      {topicItem.implications.market}
                                    </p>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Organization-Specific Implications */}
                          {topicItem.organization_implications && (
                            <div className="space-y-2">
                              <h5 className="text-xs font-medium text-indigo-600 dark:text-indigo-400 uppercase flex items-center gap-1">
                                <Building2 className="w-3 h-3" /> Organization Implications
                              </h5>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                                {topicItem.organization_implications.strategic_relevance && typeof topicItem.organization_implications.strategic_relevance === 'string' && (
                                  <div className="bg-indigo-50 dark:bg-indigo-900/30 p-3 rounded border-l-2 border-indigo-500">
                                    <div className="font-medium mb-1 text-indigo-700 dark:text-indigo-300">Strategic Relevance</div>
                                    <p className="text-gray-600 dark:text-gray-400">
                                      {topicItem.organization_implications.strategic_relevance}
                                    </p>
                                  </div>
                                )}
                                {topicItem.organization_implications.stakeholder_impact && typeof topicItem.organization_implications.stakeholder_impact === 'string' && (
                                  <div className="bg-indigo-50 dark:bg-indigo-900/30 p-3 rounded border-l-2 border-indigo-500">
                                    <div className="font-medium mb-1 text-indigo-700 dark:text-indigo-300">Stakeholder Impact</div>
                                    <p className="text-gray-600 dark:text-gray-400">
                                      {topicItem.organization_implications.stakeholder_impact}
                                    </p>
                                  </div>
                                )}
                                {topicItem.organization_implications.risk_assessment && typeof topicItem.organization_implications.risk_assessment === 'string' && (
                                  <div className="bg-indigo-50 dark:bg-indigo-900/30 p-3 rounded border-l-2 border-indigo-500">
                                    <div className="font-medium mb-1 text-indigo-700 dark:text-indigo-300">Risk Assessment</div>
                                    <p className="text-gray-600 dark:text-gray-400">
                                      {topicItem.organization_implications.risk_assessment}
                                    </p>
                                  </div>
                                )}
                                {topicItem.organization_implications.recommended_response && typeof topicItem.organization_implications.recommended_response === 'string' && (
                                  <div className="bg-indigo-50 dark:bg-indigo-900/30 p-3 rounded border-l-2 border-indigo-500">
                                    <div className="font-medium mb-1 text-indigo-700 dark:text-indigo-300">Recommended Response</div>
                                    <p className="text-gray-600 dark:text-gray-400">
                                      {topicItem.organization_implications.recommended_response}
                                    </p>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Saved Future Horizons Scenarios */}
                          {topicItem.future_horizons?.scenarios && topicItem.future_horizons.scenarios.length > 0 && (
                            <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-700">
                              <div className="flex items-center gap-2 mb-2">
                                <Compass className="w-4 h-4 text-indigo-500" />
                                <h5 className="text-xs font-medium text-gray-500 uppercase">Future Horizons</h5>
                              </div>
                              <div className="space-y-2">
                                {topicItem.future_horizons.scenarios.map((scenario: any, idx: number) => {
                                  const typeColors: Record<string, string> = {
                                    probable: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
                                    plausible: 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300',
                                    possible: 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300',
                                    wildcard: 'bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300',
                                  };
                                  const typeLabels: Record<string, string> = {
                                    probable: 'Probable',
                                    plausible: 'Plausible',
                                    possible: 'Possible',
                                    wildcard: 'Wildcard',
                                  };
                                  return (
                                    <div key={idx} className="flex items-start gap-2 p-2 bg-gray-50 dark:bg-gray-800 rounded">
                                      <span className={`px-2 py-0.5 rounded text-xs font-medium flex-shrink-0 ${typeColors[scenario.type] || 'bg-gray-100 text-gray-700'}`}>
                                        {typeLabels[scenario.type] || scenario.type}
                                      </span>
                                      <div className="min-w-0 flex-1">
                                        <div className="font-medium text-sm text-gray-900 dark:text-gray-100">{scenario.title}</div>
                                        <div className="text-sm text-gray-500 mt-0.5">{scenario.description}</div>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* Action Buttons */}
                          <div className="flex items-center gap-3 pt-2 border-t border-gray-100 dark:border-gray-700">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleAskAuspex(topicItem);
                              }}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-pink-600 dark:text-pink-400 hover:text-pink-700 dark:hover:text-pink-300 hover:bg-pink-50 dark:hover:bg-pink-900/20 font-medium transition-colors rounded-md"
                              title="Ask Auspex about this topic"
                            >
                              <MessageSquare className="w-4 h-4" />
                              Ask Auspex
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleSendToHorizons(topicItem);
                              }}
                              disabled={horizonsLoading === topicItem.id}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 font-medium transition-colors rounded-md disabled:opacity-50"
                              title="Project this topic into Future Horizons scenarios"
                            >
                              {horizonsLoading === topicItem.id ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <Compass className="w-4 h-4" />
                              )}
                              Future Horizons
                            </button>
                          </div>

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
          );
        })()}
      </div>

      {/* Retired Themes Section */}
      <div className="mt-8 pt-6 border-t border-gray-200 dark:border-gray-700">
        <button
          onClick={() => {
            if (!showRetired && retiredTopics.length === 0) {
              fetchRetiredTopics();
            }
            setShowRetired(!showRetired);
          }}
          className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
        >
          {showRetired ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
          <Archive className="w-4 h-4" />
          <span className="font-medium">Retired Themes</span>
          {retiredTopics.length > 0 && (
            <span className="text-xs bg-gray-200 dark:bg-gray-700 px-2 py-0.5 rounded-full">
              {retiredTopics.length}
            </span>
          )}
        </button>

        {showRetired && (
          <div className="mt-4 space-y-3">
            {loadingRetired ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
              </div>
            ) : retiredTopics.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <Archive className="w-10 h-10 mx-auto text-gray-300 dark:text-gray-600 mb-3" />
                <p className="text-sm">No retired themes</p>
                <p className="text-xs text-gray-400 mt-1">
                  Themes you retire will appear here
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {retiredTopics.map((topic) => (
                  <Card key={topic.id} className="opacity-70 hover:opacity-100 transition-opacity">
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <CardTitle className="text-base line-clamp-2">
                            {topic.topic_label}
                          </CardTitle>
                          <p className="text-xs text-gray-500 mt-1">
                            {topic.article_count} articles
                          </p>
                        </div>
                        <button
                          onClick={() => handleRestoreTopic(topic.id)}
                          className="p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded transition-colors"
                          title="Restore theme"
                        >
                          <RotateCcw className="w-4 h-4" />
                        </button>
                      </div>
                    </CardHeader>
                    <CardContent className="pt-0">
                      <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                        {typeof topic.synthesis?.key_takeaway === 'string'
                          ? topic.synthesis.key_takeaway
                          : topic.topic_description || 'No summary available'}
                      </p>
                      {topic.trend_score && (
                        <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
                          <span className={getScoreColor(topic.trend_score.composite)}>
                            Score: {Math.round(topic.trend_score.composite)}
                          </span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
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
            <DialogTitle>Delete Emerging Theme?</DialogTitle>
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
              Clear All Detected Themes?
            </DialogTitle>
            <DialogDescription className="space-y-2">
              <p>
                This will permanently delete <strong>{emergingTopics.length} detected themes</strong> from the database.
              </p>
              <p className="text-amber-600 dark:text-amber-400 font-medium">
                Warning: This will reset all detection counters and tracking history. Themes will need to be re-detected.
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
              Clear All Themes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Share Modal */}
      {shareData && (
        <ShareModal
          open={showShareModal}
          onOpenChange={setShowShareModal}
          data={shareData}
        />
      )}

      {/* Future Horizons Results Modal */}
      <Dialog open={showHorizonsModal} onOpenChange={setShowHorizonsModal}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto overflow-x-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Compass className="w-5 h-5 text-indigo-600" />
              Future Horizons: {horizonsTopicLabel}
            </DialogTitle>
            <DialogDescription>
              Futures cone analysis projecting potential scenarios over the next 15 years
            </DialogDescription>
          </DialogHeader>

          {horizonsResult && (
            <div className="space-y-4 mt-4">
              {/* Scenarios as Cards instead of Table for better formatting */}
              {horizonsResult.scenarios && horizonsResult.scenarios.length > 0 && (
                <div className="space-y-3">
                  {horizonsResult.scenarios.map((scenario: any, i: number) => {
                    const typeColors: Record<string, string> = {
                      probable: 'border-l-green-500 bg-green-50/50 dark:bg-green-900/20',
                      plausible: 'border-l-blue-500 bg-blue-50/50 dark:bg-blue-900/20',
                      possible: 'border-l-amber-500 bg-amber-50/50 dark:bg-amber-900/20',
                      wildcard: 'border-l-purple-500 bg-purple-50/50 dark:bg-purple-900/20',
                      preferable: 'border-l-cyan-500 bg-cyan-50/50 dark:bg-cyan-900/20'
                    };
                    const badgeColors: Record<string, string> = {
                      probable: 'text-green-700 bg-green-100 dark:text-green-300 dark:bg-green-900/50',
                      plausible: 'text-blue-700 bg-blue-100 dark:text-blue-300 dark:bg-blue-900/50',
                      possible: 'text-amber-700 bg-amber-100 dark:text-amber-300 dark:bg-amber-900/50',
                      wildcard: 'text-purple-700 bg-purple-100 dark:text-purple-300 dark:bg-purple-900/50',
                      preferable: 'text-cyan-700 bg-cyan-100 dark:text-cyan-300 dark:bg-cyan-900/50'
                    };
                    const typeLabels: Record<string, string> = {
                      probable: 'Probable',
                      plausible: 'Plausible',
                      possible: 'Possible',
                      wildcard: 'Wild Card',
                      preferable: 'Preferable'
                    };
                    return (
                      <div key={i} className={`border-l-4 rounded-r-lg p-3 ${typeColors[scenario.type] || 'border-l-gray-400 bg-gray-50/50'}`}>
                        <div className="flex items-start justify-between gap-2 mb-1">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${badgeColors[scenario.type] || 'text-gray-700 bg-gray-100'}`}>
                            {typeLabels[scenario.type] || scenario.type}
                          </span>
                          {scenario.timeframe && (
                            <span className="text-xs text-gray-500">{scenario.timeframe}</span>
                          )}
                        </div>
                        <div className="font-medium text-sm text-gray-900 dark:text-gray-100">{scenario.title}</div>
                        <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">{scenario.description}</div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Key Signals */}
              {horizonsResult.key_signals && horizonsResult.key_signals.length > 0 && (
                <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded-lg">
                  <h4 className="font-medium text-sm text-gray-900 dark:text-gray-100 mb-2">Key Signals to Watch</h4>
                  <ul className="list-disc list-inside space-y-1 text-xs text-gray-600 dark:text-gray-400">
                    {horizonsResult.key_signals.map((signal: string, i: number) => (
                      <li key={i}>{signal}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Model Used */}
              {horizonsResult.metadata?.model_used && (
                <div className="text-xs text-gray-400 text-right">
                  Generated using {horizonsResult.metadata.model_used}
                </div>
              )}
            </div>
          )}

          <DialogFooter className="mt-4 flex flex-wrap gap-2 justify-end">
            <Button variant="outline" onClick={() => setShowHorizonsModal(false)}>
              Close
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                const topic = emergingTopics.find(t => t.id === horizonsTopicId);
                if (topic) {
                  setShowHorizonsModal(false);
                  handleSendToHorizons(topic);
                }
              }}
              disabled={horizonsLoading !== null}
            >
              <RotateCcw className="w-4 h-4 mr-1" />
              Regenerate
            </Button>
            <Button
              onClick={handleSaveHorizons}
              disabled={savingHorizons}
              className="bg-indigo-600 hover:bg-indigo-700"
            >
              {savingHorizons ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save to Theme'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  );
}

export default EmergingTopicsTab;
