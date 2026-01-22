/**
 * TopicsTimelineChart - Horizontal timeline showing individual signals across recent days
 * Features:
 * - Individual dots for each signal (article) within a topic
 * - Category-based swimlanes (business, geopolitics, regulation, society, technology, other)
 * - Dots colored by urgency level, sized by score
 */

import { useMemo, useState } from 'react';
import {
  Building2,
  Globe,
  Scale,
  Users,
  Cpu,
  HelpCircle,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Minus,
} from 'lucide-react';
import { format, subDays, differenceInDays, parseISO, isValid, addDays } from 'date-fns';

// Category definitions
export type TopicCategory = 'business' | 'geopolitics' | 'regulation' | 'society' | 'technology' | 'crisis' | 'other';

const CATEGORY_CONFIG: Record<TopicCategory, { icon: React.ComponentType<{ className?: string }>; color: string; label: string }> = {
  business: { icon: Building2, color: '#3b82f6', label: 'Business' },
  geopolitics: { icon: Globe, color: '#ef4444', label: 'Geopolitics' },
  regulation: { icon: Scale, color: '#8b5cf6', label: 'Regulation' },
  society: { icon: Users, color: '#22c55e', label: 'Society' },
  technology: { icon: Cpu, color: '#06b6d4', label: 'Technology' },
  crisis: { icon: AlertTriangle, color: '#f97316', label: 'Crisis' },
  other: { icon: HelpCircle, color: '#6b7280', label: 'Other' },
};

// Keywords for category classification
const CATEGORY_KEYWORDS: Record<TopicCategory, string[]> = {
  business: ['market', 'company', 'business', 'economic', 'finance', 'stock', 'investment', 'corporate', 'enterprise', 'revenue', 'profit', 'trade', 'industry', 'merger', 'acquisition'],
  geopolitics: ['war', 'conflict', 'military', 'nato', 'russia', 'china', 'diplomatic', 'foreign', 'international', 'treaty', 'sanction', 'border', 'territory', 'alliance'],
  regulation: ['law', 'regulation', 'policy', 'legislation', 'compliance', 'legal', 'court', 'privacy', 'antitrust', 'government', 'bill', 'act', 'ruling', 'enforcement'],
  society: ['social', 'culture', 'health', 'education', 'community', 'public', 'climate', 'environment', 'protest', 'rights', 'welfare', 'demographic'],
  technology: ['ai', 'artificial intelligence', 'tech', 'software', 'digital', 'cyber', 'data', 'cloud', 'quantum', 'automation', 'algorithm', 'semiconductor', 'chip'],
  crisis: ['crisis', 'emergency', 'disaster', 'catastrophe', 'outbreak', 'pandemic', 'collapse', 'failure', 'crash', 'breach', 'attack', 'threat', 'warning', 'alert', 'urgent', 'critical', 'severe', 'escalation', 'volatility', 'turmoil', 'disruption', 'shortage', 'outage'],
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
  article_count: number;
  trend_score?: {
    composite: number;
    urgency?: 'low' | 'medium' | 'high';
  };
  synthesis?: {
    urgency?: 'low' | 'medium' | 'high';
  };
  key_themes?: string[];
}

interface TopicsTimelineChartProps {
  topics: EmergingTopicData[];
  daysToShow?: number;
  className?: string;
  onTopicClick?: (topic: EmergingTopicData) => void;
  hideTitle?: boolean;
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

// Get urgency color
function getUrgencyColor(urgency: string | undefined): string {
  switch (urgency) {
    case 'high': return '#ef4444'; // Red
    case 'medium': return '#f59e0b'; // Amber
    case 'low': return '#22c55e'; // Green
    default: return '#3b82f6'; // Blue
  }
}

// Generate signal dots for a topic based on article_count and date range
interface SignalDot {
  id: string;
  topicId: number;
  topic_label: string;
  positionPercent: number;
  category: TopicCategory;
  urgency: string;
  velocity: 'accelerating' | 'stable' | 'decelerating';
  score: number;
  signalIndex: number;
  totalSignals: number;
}

export function TopicsTimelineChart({
  topics,
  daysToShow = 7,
  className = '',
  onTopicClick,
  hideTitle = false,
}: TopicsTimelineChartProps) {
  const [hoveredSignal, setHoveredSignal] = useState<SignalDot | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  // Generate date range
  const dateRange = useMemo(() => {
    const dates: Date[] = [];
    const today = new Date();
    for (let i = daysToShow - 1; i >= 0; i--) {
      dates.push(subDays(today, i));
    }
    return dates;
  }, [daysToShow]);

  // Generate individual signal dots from topics
  const signalDots = useMemo(() => {
    const today = new Date();
    const startDate = subDays(today, daysToShow - 1);
    const dots: SignalDot[] = [];

    topics.forEach(topic => {
      const category = classifyTopic(topic);
      const detectionDate = topic.detection_date ? parseISO(topic.detection_date) : new Date();
      const firstDetection = topic.first_detection_date ? parseISO(topic.first_detection_date) : detectionDate;
      const lastDetection = topic.last_detection_date ? parseISO(topic.last_detection_date) : detectionDate;

      // Determine valid date range (clamped to visible window)
      const rangeStart = isValid(firstDetection) && firstDetection > startDate ? firstDetection : startDate;
      const rangeEnd = isValid(lastDetection) && lastDetection < today ? lastDetection : today;
      const rangeDays = Math.max(1, differenceInDays(rangeEnd, rangeStart) + 1);

      // Generate dots based on article_count, distributed across the date range
      const signalCount = Math.min(topic.article_count || 1, 20); // Cap at 20 dots per topic
      const urgency = topic.trend_score?.urgency || topic.synthesis?.urgency || 'medium';
      const velocity = topic.velocity || 'stable';
      const score = topic.trend_score?.composite || 50;

      for (let i = 0; i < signalCount; i++) {
        // Deterministic jitter based on topic id and signal index
        const hash = ((topic.id * 17 + i * 31) % 100) / 100; // 0-1 deterministic value
        const jitterOffset = (hash - 0.5) * 0.8; // +/- 0.4 days of jitter

        // Distribute dots across the topic's date range with deterministic jitter
        const dayOffset = rangeDays > 1
          ? (i / (signalCount - 1 || 1)) * (rangeDays - 1) + jitterOffset
          : jitterOffset * 0.5;
        const signalDate = addDays(rangeStart, Math.max(0, Math.min(rangeDays - 1, dayOffset)));

        const daysFromStart = differenceInDays(signalDate, startDate);
        // Add small horizontal jitter to position (for dots on same day)
        const positionJitter = ((topic.id * 7 + i * 13) % 20 - 10) / 100 * (100 / daysToShow);
        const positionPercent = Math.max(0, Math.min(100, (daysFromStart / (daysToShow - 1)) * 100 + positionJitter));

        dots.push({
          id: `${topic.id}-${i}`,
          topicId: topic.id,
          topic_label: topic.topic_label,
          positionPercent,
          category,
          urgency,
          velocity,
          score,
          signalIndex: i + 1,
          totalSignals: signalCount,
        });
      }
    });

    return dots;
  }, [topics, daysToShow]);

  // Group signals by category
  const signalsByCategory = useMemo(() => {
    const categories = Object.keys(CATEGORY_CONFIG) as TopicCategory[];
    return categories.map(cat => ({
      category: cat,
      signals: signalDots.filter(s => s.category === cat),
    })).filter(g => g.signals.length > 0);
  }, [signalDots]);

  // Count topics per category for legend
  const topicCountByCategory = useMemo(() => {
    const counts: Record<TopicCategory, number> = {} as Record<TopicCategory, number>;
    topics.forEach(t => {
      const cat = classifyTopic(t);
      counts[cat] = (counts[cat] || 0) + 1;
    });
    return counts;
  }, [topics]);

  if (topics.length === 0) {
    return (
      <div className={`p-4 text-center text-gray-700 dark:text-gray-400 ${className}`}>
        No emerging themes detected in the last {daysToShow} days
      </div>
    );
  }

  const handleMouseEnter = (signal: SignalDot, e: React.MouseEvent) => {
    const rect = (e.target as HTMLElement).getBoundingClientRect();
    setTooltipPos({ x: rect.left + rect.width / 2, y: rect.top });
    setHoveredSignal(signal);
  };

  const handleMouseLeave = () => {
    setHoveredSignal(null);
  };

  return (
    <div className={`bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-4 relative ${className}`}>
      {!hideTitle && (
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            Signals Timeline ({daysToShow} Days)
          </h3>
          <div className="flex items-center gap-3 text-xs text-gray-700 dark:text-gray-400">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-500" /> High
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-amber-500" /> Medium
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-500" /> Low
            </span>
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="relative">
        {/* Date axis */}
        <div className="flex justify-between mb-2 text-xs text-gray-700 dark:text-gray-400 px-1">
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
              className="flex-1 border-l border-gray-300 dark:border-gray-700 first:border-l-0"
            />
          ))}
        </div>

        {/* Category swimlanes */}
        <div className="relative space-y-1">
          {signalsByCategory.map(({ category, signals }) => {
            const config = CATEGORY_CONFIG[category];
            const CategoryIcon = config.icon;

            return (
              <div key={category} className="relative h-12 flex items-center">
                {/* Category label */}
                <div
                  className="w-24 flex items-center gap-1.5 text-xs font-medium"
                  style={{ color: config.color }}
                >
                  <CategoryIcon className="w-4 h-4" />
                  <span className="truncate">{config.label}</span>
                </div>

                {/* Signal dots */}
                <div className="flex-1 relative h-full">
                  {signals.map((signal) => {
                    // Deterministic vertical jitter based on topic id and signal index
                    // Spread dots across the full swimlane height (-16px to +16px)
                    const vertHash = ((signal.topicId * 13 + signal.signalIndex * 23) % 100) / 100;
                    const jitter = (vertHash - 0.5) * 32; // Range: -16px to +16px

                    // Velocity icon selection
                    const VelocityIcon = signal.velocity === 'accelerating'
                      ? TrendingUp
                      : signal.velocity === 'decelerating'
                        ? TrendingDown
                        : Minus;

                    return (
                      <div
                        key={signal.id}
                        className="absolute top-1/2 cursor-pointer hover:z-10 transition-transform hover:scale-150"
                        style={{
                          left: `${signal.positionPercent}%`,
                          transform: `translateX(-50%) translateY(calc(-50% + ${jitter}px))`,
                        }}
                        onMouseEnter={(e) => handleMouseEnter(signal, e)}
                        onMouseLeave={handleMouseLeave}
                        onClick={() => {
                          const topic = topics.find(t => t.id === signal.topicId);
                          if (topic) onTopicClick?.(topic);
                        }}
                      >
                        <div
                          className="w-4 h-4 rounded-full border-2 flex items-center justify-center"
                          style={{
                            backgroundColor: getUrgencyColor(signal.urgency),
                            borderColor: config.color,
                          }}
                        >
                          <VelocityIcon className="w-2 h-2 text-white drop-shadow-sm" />
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
            const topicCount = topicCountByCategory[cat] || 0;
            const signalCount = signalDots.filter(s => s.category === cat).length;
            if (topicCount === 0) return null;
            const Icon = config.icon;
            return (
              <div key={cat} className="flex items-center gap-1 text-xs">
                <Icon className="w-3 h-3" style={{ color: config.color }} />
                <span className="text-gray-700 dark:text-gray-400">
                  {config.label}: {topicCount} themes, {signalCount} signals
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Tooltip (rendered outside the chart for proper stacking) */}
      {hoveredSignal && (
        <div
          className="fixed z-[100] pointer-events-none"
          style={{
            left: tooltipPos.x,
            top: tooltipPos.y - 8,
            transform: 'translateX(-50%) translateY(-100%)',
          }}
        >
          <div className="bg-gray-900 text-white text-xs rounded px-2 py-1 whitespace-nowrap shadow-lg">
            <div className="font-medium">{hoveredSignal.topic_label}</div>
            <div className="text-gray-400 text-[10px]">
              Signal {hoveredSignal.signalIndex}/{hoveredSignal.totalSignals} | Score: {Math.round(hoveredSignal.score)} | {hoveredSignal.velocity}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default TopicsTimelineChart;
