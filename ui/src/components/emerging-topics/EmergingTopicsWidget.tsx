/**
 * Emerging Topics Dashboard Widget
 *
 * Displays a compact view of detected emerging topics
 * suitable for embedding in dashboards.
 */

import { useState, useEffect } from 'react';
import {
  Loader2,
  TrendingUp,
  Zap,
  GitBranch,
  Circle,
  ChevronRight,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';

// Types
interface EmergingTopic {
  id: number;
  label: string;
  description: string;
  type: 'new_cluster' | 'accelerating' | 'splitting' | 'proto_cluster';
  article_count: number;
  velocity: 'accelerating' | 'stable' | 'decelerating';
  confidence: number;
  themes: string[];
}

interface WidgetData {
  summary: {
    total_emerging_topics: number;
    by_type: Record<string, number>;
    accelerating_count: number;
    new_cluster_count: number;
    proto_cluster_count: number;
  };
  top_topics: EmergingTopic[];
}

interface EmergingTopicsWidgetProps {
  topic?: string;
  onTopicClick?: (topicId: number) => void;
  compact?: boolean;
  maxTopics?: number;
}

// Type badge styling
const typeBadgeStyles: Record<string, { label: string; className: string; icon: JSX.Element }> = {
  new_cluster: {
    label: 'New',
    className: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    icon: <Circle className="w-3 h-3" />,
  },
  accelerating: {
    label: 'Growing',
    className: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    icon: <TrendingUp className="w-3 h-3" />,
  },
  splitting: {
    label: 'Splitting',
    className: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    icon: <GitBranch className="w-3 h-3" />,
  },
  proto_cluster: {
    label: 'Forming',
    className: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
    icon: <Zap className="w-3 h-3" />,
  },
};

// Velocity badge styling
const velocityStyles: Record<string, { label: string; className: string }> = {
  accelerating: {
    label: 'Accelerating',
    className: 'text-green-600 dark:text-green-400',
  },
  stable: {
    label: 'Stable',
    className: 'text-gray-600 dark:text-gray-400',
  },
  decelerating: {
    label: 'Slowing',
    className: 'text-orange-600 dark:text-orange-400',
  },
};

export function EmergingTopicsWidget({
  topic,
  onTopicClick,
  compact = false,
  maxTopics = 5,
}: EmergingTopicsWidgetProps) {
  const [data, setData] = useState<WidgetData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams({
        limit: maxTopics.toString(),
      });

      if (topic) {
        params.append('topic', topic);
      }

      const response = await fetch(`/api/emerging-topics/dashboard-widget?${params}`);

      if (!response.ok) {
        throw new Error(`Failed to fetch: ${response.status}`);
      }

      const result = await response.json();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load emerging topics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [topic, maxTopics]);

  if (loading) {
    return (
      <Card className="w-full">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Zap className="w-4 h-4" />
            Emerging Topics
          </CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="w-full">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Zap className="w-4 h-4" />
            Emerging Topics
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-center justify-center py-4 gap-2">
          <AlertCircle className="w-6 h-6 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">{error}</p>
          <Button variant="outline" size="sm" onClick={fetchData}>
            <RefreshCw className="w-3 h-3 mr-1" />
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <Card className="w-full">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-500" />
            Emerging Topics
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="text-xs">
              {data.summary.total_emerging_topics} detected
            </Badge>
            <Button variant="ghost" size="sm" onClick={fetchData} className="h-6 w-6 p-0">
              <RefreshCw className="w-3 h-3" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {/* Summary stats */}
        {!compact && data.summary.total_emerging_topics > 0 && (
          <div className="flex gap-3 mb-3 text-xs">
            {data.summary.accelerating_count > 0 && (
              <div className="flex items-center gap-1 text-green-600 dark:text-green-400">
                <TrendingUp className="w-3 h-3" />
                <span>{data.summary.accelerating_count} growing</span>
              </div>
            )}
            {data.summary.new_cluster_count > 0 && (
              <div className="flex items-center gap-1 text-blue-600 dark:text-blue-400">
                <Circle className="w-3 h-3" />
                <span>{data.summary.new_cluster_count} new</span>
              </div>
            )}
            {data.summary.proto_cluster_count > 0 && (
              <div className="flex items-center gap-1 text-orange-600 dark:text-orange-400">
                <Zap className="w-3 h-3" />
                <span>{data.summary.proto_cluster_count} forming</span>
              </div>
            )}
          </div>
        )}

        {/* Topics list */}
        {data.top_topics.length === 0 ? (
          <div className="text-center py-4 text-sm text-muted-foreground">
            No emerging topics detected
          </div>
        ) : (
          <div className="space-y-2">
            {data.top_topics.map((topic) => (
              <TopicCard
                key={topic.id}
                topic={topic}
                compact={compact}
                onClick={() => onTopicClick?.(topic.id)}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Individual topic card
interface TopicCardProps {
  topic: EmergingTopic;
  compact?: boolean;
  onClick?: () => void;
}

function TopicCard({ topic, compact, onClick }: TopicCardProps) {
  const typeStyle = typeBadgeStyles[topic.type] || typeBadgeStyles.new_cluster;
  const velocityStyle = velocityStyles[topic.velocity] || velocityStyles.stable;

  return (
    <div
      className={`
        p-2 rounded-lg border bg-card hover:bg-accent/50 transition-colors
        ${onClick ? 'cursor-pointer' : ''}
      `}
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-medium text-sm truncate">{topic.label}</span>
            <Badge className={`text-xs px-1.5 py-0 ${typeStyle.className}`}>
              {typeStyle.icon}
              <span className="ml-1">{typeStyle.label}</span>
            </Badge>
          </div>

          {!compact && topic.description && (
            <p className="text-xs text-muted-foreground line-clamp-1">{topic.description}</p>
          )}

          {!compact && topic.themes.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {topic.themes.slice(0, 3).map((theme, i) => (
                <Badge key={i} variant="outline" className="text-xs px-1 py-0">
                  {theme}
                </Badge>
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-col items-end gap-1 text-right">
          <div className="text-sm font-semibold">{topic.article_count}</div>
          <div className={`text-xs flex items-center gap-1 ${velocityStyle.className}`}>
            {topic.velocity === 'accelerating' && <TrendingUp className="w-3 h-3" />}
            <span>{velocityStyle.label}</span>
          </div>
          {onClick && <ChevronRight className="w-4 h-4 text-muted-foreground" />}
        </div>
      </div>
    </div>
  );
}

export default EmergingTopicsWidget;
