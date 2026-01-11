/**
 * CategoryRadarChart - Radar chart showing individual topics as dots
 * Each topic is positioned by category (angle) and score (radius)
 * Dots colored by urgency level
 */

import { useMemo } from 'react';
import {
  Building2,
  Globe,
  Scale,
  Users,
  Cpu,
  HelpCircle,
} from 'lucide-react';

// Category definitions - must match TopicsTimelineChart
export type TopicCategory = 'business' | 'geopolitics' | 'regulation' | 'society' | 'technology' | 'other';

const CATEGORY_CONFIG: Record<TopicCategory, { icon: React.ComponentType<{ className?: string }>; color: string; label: string }> = {
  business: { icon: Building2, color: '#3b82f6', label: 'Business' },
  geopolitics: { icon: Globe, color: '#ef4444', label: 'Geopolitics' },
  regulation: { icon: Scale, color: '#8b5cf6', label: 'Regulation' },
  society: { icon: Users, color: '#22c55e', label: 'Society' },
  technology: { icon: Cpu, color: '#06b6d4', label: 'Technology' },
  other: { icon: HelpCircle, color: '#6b7280', label: 'Other' },
};

// Keywords for category classification (same as TimelineChart)
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
  trend_score?: {
    composite: number;
    urgency?: 'low' | 'medium' | 'high';
  };
  key_themes?: string[];
}

interface CategoryRadarChartProps {
  topics: EmergingTopicData[];
  size?: number;
  showLegend?: boolean;
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

// Get urgency color
function getUrgencyColor(urgency: string | undefined): string {
  switch (urgency) {
    case 'high': return '#ef4444'; // Red
    case 'medium': return '#f59e0b'; // Amber
    case 'low': return '#22c55e'; // Green
    default: return '#3b82f6'; // Blue
  }
}

export function CategoryRadarChart({
  topics,
  size = 300,
  showLegend = true,
  className = '',
  onTopicClick,
}: CategoryRadarChartProps) {
  // Get categories that have topics
  const activeCategories = useMemo(() => {
    const categories = Object.keys(CATEGORY_CONFIG) as TopicCategory[];
    const classifiedTopics = topics.map(t => ({
      ...t,
      category: classifyTopic(t),
    }));

    return categories.filter(cat =>
      classifiedTopics.some(t => t.category === cat)
    );
  }, [topics]);

  // Process topics with positions for the radar
  const processedTopics = useMemo(() => {
    if (activeCategories.length === 0) return [];

    return topics.map(topic => {
      const category = classifyTopic(topic);
      const score = topic.trend_score?.composite || 50;
      const urgency = topic.trend_score?.urgency || 'medium';

      // Calculate angle based on category position
      const categoryIndex = activeCategories.indexOf(category);
      const angleStep = (2 * Math.PI) / activeCategories.length;
      // Start from top (-90 degrees) and go clockwise
      const angle = -Math.PI / 2 + categoryIndex * angleStep;

      // Add some jitter within category to avoid overlap
      const jitter = (Math.random() - 0.5) * 0.3; // +/- 15% of angle step
      const finalAngle = angle + jitter * angleStep;

      // Radius based on score (0-100 maps to 20%-90% of max radius)
      const normalizedScore = Math.max(0, Math.min(100, score));
      const radiusPercent = 0.2 + (normalizedScore / 100) * 0.7;

      return {
        ...topic,
        category,
        score,
        urgency,
        angle: finalAngle,
        radiusPercent,
        color: getUrgencyColor(urgency),
        categoryColor: CATEGORY_CONFIG[category].color,
      };
    });
  }, [topics, activeCategories]);

  // Calculate category stats for legend
  const categoryStats = useMemo(() => {
    return activeCategories.map(cat => {
      const catTopics = processedTopics.filter(t => t.category === cat);
      return {
        category: cat,
        count: catTopics.length,
        config: CATEGORY_CONFIG[cat],
      };
    });
  }, [activeCategories, processedTopics]);

  if (topics.length === 0 || activeCategories.length === 0) {
    return (
      <div className={`flex items-center justify-center p-4 text-gray-500 dark:text-gray-400 ${className}`}>
        No category data available
      </div>
    );
  }

  const center = size / 2;
  const maxRadius = (size / 2) * 0.85;

  return (
    <div className={`bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-4 ${className}`}>
      {/* Legend for urgency levels */}
      <div className="flex items-center justify-end gap-2 text-xs mb-2">
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

      {/* Radar Chart SVG */}
      <svg width={size} height={size} className="mx-auto">
        {/* Concentric circles (score rings) */}
        {[0.25, 0.5, 0.75, 1].map((r, i) => (
          <circle
            key={i}
            cx={center}
            cy={center}
            r={maxRadius * r}
            fill="none"
            stroke="currentColor"
            strokeOpacity={0.1}
            className="text-gray-400 dark:text-gray-600"
          />
        ))}

        {/* Category spokes */}
        {activeCategories.map((cat, i) => {
          const angleStep = (2 * Math.PI) / activeCategories.length;
          const angle = -Math.PI / 2 + i * angleStep;
          const x2 = center + Math.cos(angle) * maxRadius;
          const y2 = center + Math.sin(angle) * maxRadius;
          const labelX = center + Math.cos(angle) * (maxRadius + 20);
          const labelY = center + Math.sin(angle) * (maxRadius + 20);
          const config = CATEGORY_CONFIG[cat];
          const Icon = config.icon;

          return (
            <g key={cat}>
              {/* Spoke line */}
              <line
                x1={center}
                y1={center}
                x2={x2}
                y2={y2}
                stroke="currentColor"
                strokeOpacity={0.2}
                className="text-gray-400 dark:text-gray-600"
              />
              {/* Category label */}
              <foreignObject
                x={labelX - 30}
                y={labelY - 10}
                width={60}
                height={20}
                style={{ overflow: 'visible' }}
              >
                <div
                  className="flex items-center justify-center gap-1 text-xs font-medium whitespace-nowrap"
                  style={{ color: config.color }}
                >
                  <Icon className="w-3 h-3" />
                  <span>{config.label}</span>
                </div>
              </foreignObject>
            </g>
          );
        })}

        {/* Topic dots */}
        {processedTopics.map((topic, idx) => {
          const r = maxRadius * topic.radiusPercent;
          const x = center + Math.cos(topic.angle) * r;
          const y = center + Math.sin(topic.angle) * r;

          return (
            <g key={topic.id} className="cursor-pointer group">
              {/* Dot with category border */}
              <circle
                cx={x}
                cy={y}
                r={8}
                fill={topic.color}
                stroke={topic.categoryColor}
                strokeWidth={2}
                className="transition-all group-hover:r-10"
                onClick={() => onTopicClick?.(topic)}
              />
              {/* Hover tooltip */}
              <title>{`${topic.topic_label}\nScore: ${Math.round(topic.score)}\nUrgency: ${topic.urgency}`}</title>
            </g>
          );
        })}

        {/* Center point */}
        <circle
          cx={center}
          cy={center}
          r={4}
          fill="currentColor"
          className="text-gray-300 dark:text-gray-600"
        />
      </svg>

      {/* Category summary */}
      {showLegend && (
        <div className="flex flex-wrap gap-2 mt-2 pt-2 border-t border-gray-100 dark:border-gray-800">
          {categoryStats.map(({ category, count, config }) => {
            const Icon = config.icon;
            return (
              <div
                key={category}
                className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-gray-50 dark:bg-gray-800 text-xs"
              >
                <Icon className="w-3 h-3" style={{ color: config.color }} />
                <span className="text-gray-700 dark:text-gray-300">{config.label}</span>
                <span className="text-gray-500">({count})</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default CategoryRadarChart;
