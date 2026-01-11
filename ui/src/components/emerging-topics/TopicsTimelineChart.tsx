/**
 * TopicsTimelineChart - Horizontal timeline showing emerging topics across recent days
 * Features:
 * - Arrow icons showing trajectory (up/down/right)
 * - Category icons (business, geopolitics, regulation, society, technology, other)
 * - Tail length indicating topic duration
 */

import { useMemo } from 'react';
import {
  TrendingUp,
  TrendingDown,
  ArrowRight,
  Building2,
  Globe,
  Scale,
  Users,
  Cpu,
  HelpCircle,
} from 'lucide-react';
import { format, subDays, differenceInDays, parseISO, isValid } from 'date-fns';

// Category definitions
export type TopicCategory = 'business' | 'geopolitics' | 'regulation' | 'society' | 'technology' | 'other';

const CATEGORY_CONFIG: Record<TopicCategory, { icon: React.ComponentType<{ className?: string }>; color: string; label: string }> = {
  business: { icon: Building2, color: '#3b82f6', label: 'Business' },
  geopolitics: { icon: Globe, color: '#ef4444', label: 'Geopolitics' },
  regulation: { icon: Scale, color: '#8b5cf6', label: 'Regulation' },
  society: { icon: Users, color: '#22c55e', label: 'Society' },
  technology: { icon: Cpu, color: '#06b6d4', label: 'Technology' },
  other: { icon: HelpCircle, color: '#6b7280', label: 'Other' },
};

// Keywords for category classification
const CATEGORY_KEYWORDS: Record<TopicCategory, string[]> = {
  business: ['market', 'company', 'business', 'economic', 'finance', 'stock', 'investment', 'corporate', 'enterprise', 'revenue', 'profit', 'trade', 'industry', 'merger', 'acquisition'],
  geopolitics: ['war', 'conflict', 'military', 'nato', 'russia', 'china', 'diplomatic', 'foreign', 'international', 'treaty', 'sanction', 'border', 'territory', 'alliance'],
  regulation: ['law', 'regulation', 'policy', 'legislation', 'compliance', 'legal', 'court', 'privacy', 'antitrust', 'government', 'bill', 'act', 'ruling', 'enforcement'],
  society: ['social', 'culture', 'health', 'education', 'community', 'public', 'climate', 'environment', 'protest', 'rights', 'welfare', 'demographic'],
  technology: ['ai', 'artificial intelligence', 'tech', 'software', 'digital', 'cyber', 'data', 'cloud', 'quantum', 'automation', 'algorithm', 'semiconductor', 'chip'],
  other: [],
};

interface EmergingTopicData {
  id: number;
  topic_label: string;
  detection_date: string;
  first_detection_date?: string;
  last_detection_date?: string;
  velocity: 'accelerating' | 'stable' | 'decelerating';
  trajectory?: string;
  trend_score?: {
    composite: number;
    urgency?: 'low' | 'medium' | 'high';
  };
  key_themes?: string[];
}

interface TopicsTimelineChartProps {
  topics: EmergingTopicData[];
  daysToShow?: number;
  className?: string;
  onTopicClick?: (topic: EmergingTopicData) => void;
}

// Classify a topic into a category based on label and themes
function classifyTopic(topic: EmergingTopicData): TopicCategory {
  const textToCheck = [
    topic.topic_label.toLowerCase(),
    ...(topic.key_themes?.map(t => t.toLowerCase()) || []),
  ].join(' ');

  for (const [category, keywords] of Object.entries(CATEGORY_KEYWORDS) as [TopicCategory, string[]][]) {
    if (category === 'other') continue;
    for (const keyword of keywords) {
      if (textToCheck.includes(keyword)) {
        return category;
      }
    }
  }
  return 'other';
}

// Get trajectory arrow icon and color
function getTrajectoryIcon(velocity: string, trajectory?: string) {
  const effectiveTrajectory = trajectory || velocity;
  if (effectiveTrajectory === 'accelerating' || effectiveTrajectory === 'rising') {
    return { Icon: TrendingUp, color: '#22c55e' };
  }
  if (effectiveTrajectory === 'decelerating' || effectiveTrajectory === 'declining') {
    return { Icon: TrendingDown, color: '#ef4444' };
  }
  return { Icon: ArrowRight, color: '#6b7280' };
}

export function TopicsTimelineChart({
  topics,
  daysToShow = 7,
  className = '',
  onTopicClick,
}: TopicsTimelineChartProps) {
  // Generate date range
  const dateRange = useMemo(() => {
    const dates: Date[] = [];
    const today = new Date();
    for (let i = daysToShow - 1; i >= 0; i--) {
      dates.push(subDays(today, i));
    }
    return dates;
  }, [daysToShow]);

  // Process topics with categories and positions
  const processedTopics = useMemo(() => {
    const today = new Date();
    const startDate = subDays(today, daysToShow - 1);

    return topics
      .map(topic => {
        const category = classifyTopic(topic);
        const detectionDate = topic.detection_date ? parseISO(topic.detection_date) : new Date();
        const firstDetection = topic.first_detection_date ? parseISO(topic.first_detection_date) : detectionDate;
        const lastDetection = topic.last_detection_date ? parseISO(topic.last_detection_date) : detectionDate;

        // Calculate position on timeline (0-100%)
        const daysFromStart = differenceInDays(detectionDate, startDate);
        const positionPercent = Math.max(0, Math.min(100, (daysFromStart / (daysToShow - 1)) * 100));

        // Calculate duration for tail length
        const durationDays = isValid(firstDetection) && isValid(lastDetection)
          ? Math.max(1, differenceInDays(lastDetection, firstDetection) + 1)
          : 1;
        const tailWidth = Math.min(30, durationDays * 8); // Max 30% width

        return {
          ...topic,
          category,
          positionPercent,
          tailWidth,
          durationDays,
        };
      })
      .filter(t => t.positionPercent >= 0 && t.positionPercent <= 100)
      .sort((a, b) => a.positionPercent - b.positionPercent);
  }, [topics, daysToShow]);

  // Group topics by category for Y-axis positioning
  const topicsByCategory = useMemo(() => {
    const categories = Object.keys(CATEGORY_CONFIG) as TopicCategory[];
    return categories.map(cat => ({
      category: cat,
      topics: processedTopics.filter(t => t.category === cat),
    })).filter(g => g.topics.length > 0);
  }, [processedTopics]);

  if (topics.length === 0) {
    return (
      <div className={`p-4 text-center text-gray-500 dark:text-gray-400 ${className}`}>
        No emerging topics detected in the last {daysToShow} days
      </div>
    );
  }

  return (
    <div className={`bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-4 ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
          Topics Timeline ({daysToShow} Days)
        </h3>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <TrendingUp className="w-3 h-3 text-green-500" /> Rising
          </span>
          <span className="flex items-center gap-1">
            <ArrowRight className="w-3 h-3 text-gray-500" /> Stable
          </span>
          <span className="flex items-center gap-1">
            <TrendingDown className="w-3 h-3 text-red-500" /> Declining
          </span>
        </div>
      </div>

      {/* Timeline */}
      <div className="relative">
        {/* Date axis */}
        <div className="flex justify-between mb-2 text-xs text-gray-500 dark:text-gray-400 px-1">
          {dateRange.map((date, i) => (
            <span key={i} className="text-center" style={{ width: `${100 / daysToShow}%` }}>
              {format(date, 'MMM d')}
            </span>
          ))}
        </div>

        {/* Vertical grid lines */}
        <div className="absolute inset-x-0 top-8 bottom-0 flex">
          {dateRange.map((_, i) => (
            <div
              key={i}
              className="flex-1 border-l border-gray-100 dark:border-gray-800 first:border-l-0"
            />
          ))}
        </div>

        {/* Category rows */}
        <div className="relative space-y-2">
          {topicsByCategory.map(({ category, topics: catTopics }) => {
            const config = CATEGORY_CONFIG[category];
            const CategoryIcon = config.icon;

            return (
              <div key={category} className="relative h-10 flex items-center">
                {/* Category label */}
                <div
                  className="w-24 flex items-center gap-1.5 text-xs font-medium"
                  style={{ color: config.color }}
                >
                  <CategoryIcon className="w-4 h-4" />
                  <span className="truncate">{config.label}</span>
                </div>

                {/* Topic markers */}
                <div className="flex-1 relative h-full">
                  {catTopics.map((topic, idx) => {
                    const { Icon: TrajectoryIcon, color: trajectoryColor } = getTrajectoryIcon(
                      topic.velocity,
                      topic.trajectory
                    );

                    return (
                      <div
                        key={topic.id}
                        className="absolute top-1/2 -translate-y-1/2 flex items-center cursor-pointer hover:z-10 group"
                        style={{
                          left: `${topic.positionPercent}%`,
                          transform: `translateX(-50%) translateY(-50%)`,
                        }}
                        onClick={() => onTopicClick?.(topic)}
                        title={`${topic.topic_label}\n${topic.durationDays} day${topic.durationDays > 1 ? 's' : ''}`}
                      >
                        {/* Duration tail */}
                        {topic.tailWidth > 8 && (
                          <div
                            className="absolute h-1.5 rounded-full opacity-40 -z-10"
                            style={{
                              width: `${topic.tailWidth}px`,
                              right: '50%',
                              backgroundColor: config.color,
                            }}
                          />
                        )}

                        {/* Topic marker */}
                        <div
                          className="w-6 h-6 rounded-full flex items-center justify-center shadow-sm border-2 bg-white dark:bg-gray-800 group-hover:scale-125 transition-transform"
                          style={{ borderColor: config.color }}
                        >
                          <TrajectoryIcon
                            className="w-3.5 h-3.5"
                            style={{ color: trajectoryColor }}
                          />
                        </div>

                        {/* Tooltip on hover */}
                        <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20">
                          <div className="bg-gray-900 text-white text-xs rounded px-2 py-1 whitespace-nowrap shadow-lg">
                            <div className="font-medium">{topic.topic_label}</div>
                            <div className="text-gray-300 text-[10px]">
                              {topic.durationDays} day{topic.durationDays > 1 ? 's' : ''} |{' '}
                              {topic.trend_score ? `Score: ${Math.round(topic.trend_score.composite)}` : ''}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        {/* Category legend */}
        <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t border-gray-100 dark:border-gray-800">
          {(Object.entries(CATEGORY_CONFIG) as [TopicCategory, typeof CATEGORY_CONFIG[TopicCategory]][]).map(([cat, config]) => {
            const count = processedTopics.filter(t => t.category === cat).length;
            if (count === 0) return null;
            const Icon = config.icon;
            return (
              <div key={cat} className="flex items-center gap-1 text-xs">
                <Icon className="w-3 h-3" style={{ color: config.color }} />
                <span className="text-gray-600 dark:text-gray-400">
                  {config.label} ({count})
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default TopicsTimelineChart;
