/**
 * CategoryRadarChart - Radar chart showing individual topics as dots
 * Each topic is positioned by category (angle) and score (radius)
 * Dots colored by urgency level
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

// Category definitions - must match TopicsTimelineChart
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

// Keywords for category classification (same as TimelineChart)
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
  article_count?: number;
  velocity?: 'accelerating' | 'stable' | 'decelerating';
  trend_score?: {
    composite: number;
    urgency?: 'low' | 'medium' | 'high';
  };
  synthesis?: {
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

interface ProcessedTopic extends EmergingTopicData {
  category: TopicCategory;
  score: number;
  urgency: string;
  velocityType: 'accelerating' | 'stable' | 'decelerating';
  angle: number;
  radiusPercent: number;
  color: string;
  categoryColor: string;
  dotSize: number; // Size in pixels based on article count
}

export function CategoryRadarChart({
  topics,
  size = 300,
  showLegend = true,
  className = '',
  onTopicClick,
}: CategoryRadarChartProps) {
  const [hoveredTopic, setHoveredTopic] = useState<ProcessedTopic | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

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

    // Find max article count for sizing dots
    const maxArticles = Math.max(...topics.map(t => t.article_count || 1), 1);
    const minDotSize = 12; // px
    const maxDotSize = 28; // px

    return topics.map((topic, idx) => {
      const category = classifyTopic(topic);
      const score = topic.trend_score?.composite || 50;
      // Check both trend_score.urgency and synthesis.urgency
      const urgency = topic.trend_score?.urgency || topic.synthesis?.urgency || 'medium';
      const velocityType = topic.velocity || 'stable';

      // Calculate angle based on category position
      const categoryIndex = activeCategories.indexOf(category);
      const angleStep = (2 * Math.PI) / activeCategories.length;
      // Start from top (-90 degrees) and go clockwise
      const angle = -Math.PI / 2 + categoryIndex * angleStep;

      // Add deterministic jitter within category to avoid overlap (based on topic id)
      const jitter = ((topic.id * 7) % 10 - 5) / 10 * 0.3; // +/- 15% of angle step
      const finalAngle = angle + jitter * angleStep;

      // Radius based on score (0-100 maps to 20%-90% of max radius)
      const normalizedScore = Math.max(0, Math.min(100, score));
      const radiusPercent = 0.2 + (normalizedScore / 100) * 0.7;

      // Dot size based on article count (scale from min to max)
      const articleCount = topic.article_count || 1;
      const sizeRatio = Math.log(articleCount + 1) / Math.log(maxArticles + 1); // Log scale for better distribution
      const dotSize = minDotSize + sizeRatio * (maxDotSize - minDotSize);

      return {
        ...topic,
        category,
        score,
        urgency,
        velocityType,
        angle: finalAngle,
        radiusPercent,
        color: getUrgencyColor(urgency),
        categoryColor: CATEGORY_CONFIG[category].color,
        dotSize,
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
      <div className={`flex items-center justify-center p-4 text-gray-700 dark:text-gray-400 ${className}`}>
        No category data available
      </div>
    );
  }

  const center = size / 2;
  const maxRadius = (size / 2) * 0.85;

  const handleMouseEnter = (topic: ProcessedTopic, e: React.MouseEvent) => {
    const rect = (e.target as HTMLElement).getBoundingClientRect();
    setTooltipPos({ x: rect.left + rect.width / 2, y: rect.top });
    setHoveredTopic(topic);
  };

  const handleMouseLeave = () => {
    setHoveredTopic(null);
  };

  return (
    <div className={`bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-4 relative ${className}`}>
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

      {/* Radar Chart Container */}
      <div className="relative mx-auto" style={{ width: size, height: size }}>
        {/* SVG for background elements */}
        <svg width={size} height={size} className="absolute inset-0">
          {/* Concentric circles (score rings) with labels */}
          {[0.25, 0.5, 0.75, 1].map((r, i) => {
            const scoreValue = Math.round(r * 100);
            return (
              <g key={i}>
                <circle
                  cx={center}
                  cy={center}
                  r={maxRadius * r}
                  fill="none"
                  stroke="currentColor"
                  strokeOpacity={0.3}
                  className="text-gray-500 dark:text-gray-300"
                />
                {/* Score label on the ring (positioned at top) */}
                <text
                  x={center}
                  y={center - maxRadius * r - 2}
                  textAnchor="middle"
                  className="text-[9px] fill-gray-700 dark:fill-gray-400"
                >
                  {scoreValue}
                </text>
              </g>
            );
          })}

          {/* Category spokes */}
          {activeCategories.map((cat, i) => {
            const angleStep = (2 * Math.PI) / activeCategories.length;
            const angle = -Math.PI / 2 + i * angleStep;
            const x2 = center + Math.cos(angle) * maxRadius;
            const y2 = center + Math.sin(angle) * maxRadius;

            return (
              <line
                key={cat}
                x1={center}
                y1={center}
                x2={x2}
                y2={y2}
                stroke="currentColor"
                strokeOpacity={0.4}
                className="text-gray-500 dark:text-gray-300"
              />
            );
          })}

          {/* Center point */}
          <circle
            cx={center}
            cy={center}
            r={4}
            fill="currentColor"
            className="text-gray-600 dark:text-gray-300"
          />
        </svg>

        {/* Category labels (HTML for better rendering) */}
        {activeCategories.map((cat, i) => {
          const angleStep = (2 * Math.PI) / activeCategories.length;
          const angle = -Math.PI / 2 + i * angleStep;
          const labelX = center + Math.cos(angle) * (maxRadius + 25);
          const labelY = center + Math.sin(angle) * (maxRadius + 25);
          const config = CATEGORY_CONFIG[cat];
          const Icon = config.icon;

          return (
            <div
              key={cat}
              className="absolute flex items-center gap-1 text-xs font-medium whitespace-nowrap"
              style={{
                left: labelX,
                top: labelY,
                transform: 'translate(-50%, -50%)',
                color: config.color,
              }}
            >
              <Icon className="w-3 h-3" />
              <span>{config.label}</span>
            </div>
          );
        })}

        {/* Topic dots (HTML for better hover handling) - sized by article count, with velocity icons */}
        {processedTopics.map((topic) => {
          const r = maxRadius * topic.radiusPercent;
          const x = center + Math.cos(topic.angle) * r;
          const y = center + Math.sin(topic.angle) * r;

          // Get velocity icon
          const VelocityIcon = topic.velocityType === 'accelerating'
            ? TrendingUp
            : topic.velocityType === 'decelerating'
              ? TrendingDown
              : Minus;

          // Icon size based on dot size (roughly 60% of dot)
          const iconSize = Math.max(8, Math.floor(topic.dotSize * 0.5));

          return (
            <div
              key={topic.id}
              className="absolute cursor-pointer transition-transform hover:scale-125 hover:z-10"
              style={{
                left: x,
                top: y,
                transform: 'translate(-50%, -50%)',
              }}
              onMouseEnter={(e) => handleMouseEnter(topic, e)}
              onMouseLeave={handleMouseLeave}
              onClick={() => onTopicClick?.(topic)}
            >
              <div
                className="rounded-full flex items-center justify-center"
                style={{
                  width: `${topic.dotSize}px`,
                  height: `${topic.dotSize}px`,
                  backgroundColor: topic.color,
                  border: `2px solid ${topic.categoryColor}`,
                }}
              >
                <VelocityIcon
                  className="text-white drop-shadow-sm"
                  style={{ width: iconSize, height: iconSize }}
                />
              </div>
            </div>
          );
        })}
      </div>

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
                <span className="text-gray-700 dark:text-gray-400">{config.label}</span>
                <span className="text-gray-600 dark:text-gray-300">({count})</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Tooltip (rendered outside for proper z-index) */}
      {hoveredTopic && (
        <div
          className="fixed z-[100] pointer-events-none"
          style={{
            left: tooltipPos.x,
            top: tooltipPos.y - 8,
            transform: 'translateX(-50%) translateY(-100%)',
          }}
        >
          <div className="bg-gray-900 text-white text-xs rounded px-2 py-1 whitespace-nowrap shadow-lg">
            <div className="font-medium">{hoveredTopic.topic_label}</div>
            <div className="text-gray-400 text-[10px]">
              Score: {Math.round(hoveredTopic.score)} | {hoveredTopic.urgency} urgency | {hoveredTopic.velocityType} | {hoveredTopic.article_count || 1} signals
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CategoryRadarChart;
