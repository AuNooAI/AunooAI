/**
 * TrendsRadarCompact - Compact horizontal view of all 5 trends
 *
 * Shows all T1-T5 trends in a scannable format with:
 * - Score as progress bar
 * - Velocity indicator (accelerating/stable/decelerating)
 * - Urgency badge
 * - Click to drill down to relevant pillar tab
 */

import React from 'react';
import { TrendingUp, TrendingDown, Minus, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Progress } from '../ui/progress';
import { Badge } from '../ui/badge';
import type { TrendStatus } from '../../hooks/usePAM';

// Map trend IDs to pillar tabs
export const TREND_TO_PILLAR: Record<string, 'power' | 'attention' | 'money'> = {
  'T1': 'attention',  // Invisible LLM ecosystems
  'T2': 'power',      // Agentic AI workflows
  'T3': 'attention',  // SEO → GEO
  'T4': 'power',      // Regulatory pressures
  'T5': 'money',      // Market consolidation
};

// Trend short descriptions
const TREND_LABELS: Record<string, string> = {
  'T1': 'Invisible LLM Ecosystems',
  'T2': 'Agentic AI Workflows',
  'T3': 'SEO → GEO Shift',
  'T4': 'Regulatory Pressures',
  'T5': 'Market Consolidation',
};

interface TrendsRadarCompactProps {
  trends: TrendStatus[];
  onTrendClick: (trendId: string) => void;
}

const TrendsRadarCompact: React.FC<TrendsRadarCompactProps> = ({
  trends,
  onTrendClick,
}) => {
  // Sort trends by score (highest first)
  const sortedTrends = [...(trends || [])].sort((a, b) => b.score - a.score);

  const getVelocityIcon = (velocity: string) => {
    switch (velocity) {
      case 'accelerating':
        return <TrendingUp className="w-4 h-4 text-green-500" />;
      case 'decelerating':
        return <TrendingDown className="w-4 h-4 text-amber-500" />;
      default:
        return <Minus className="w-4 h-4 text-gray-600" />;
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 70) return 'text-red-600';
    if (score >= 55) return 'text-orange-500';
    if (score >= 40) return 'text-yellow-600';
    return 'text-green-600';
  };

  const getProgressColor = (score: number) => {
    if (score >= 70) return 'bg-red-500';
    if (score >= 55) return 'bg-orange-500';
    if (score >= 40) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  const getUrgencyBadge = (urgency: string, score: number) => {
    if (score >= 70 || urgency === 'immediate') {
      return <Badge className="bg-red-100 text-red-700 text-xs">Critical</Badge>;
    }
    if (score >= 55 || urgency === 'near_term') {
      return <Badge className="bg-orange-100 text-orange-700 text-xs">High</Badge>;
    }
    if (urgency === 'medium_term') {
      return <Badge className="bg-yellow-100 text-yellow-700 text-xs">Watch</Badge>;
    }
    return <Badge className="bg-green-100 text-green-700 text-xs">Low</Badge>;
  };

  const getPillarBadge = (trendId: string) => {
    const pillar = TREND_TO_PILLAR[trendId];
    const colors: Record<string, string> = {
      power: 'bg-yellow-100 text-yellow-700',
      attention: 'bg-blue-100 text-blue-700',
      money: 'bg-green-100 text-green-700',
    };
    return colors[pillar] || 'bg-gray-100 text-gray-700';
  };

  if (!sortedTrends || sortedTrends.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-gray-600">
          No trend data available
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          2030 Trends Radar
          <span className="text-sm font-normal text-gray-600">
            (click any trend for details)
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {sortedTrends.map((trend) => (
          <div
            key={trend.id}
            onClick={() => onTrendClick(trend.id)}
            className="flex items-center gap-3 p-3 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors border border-transparent hover:border-gray-200"
          >
            {/* Trend ID Badge */}
            <Badge
              variant="outline"
              className={`w-10 justify-center font-mono ${getPillarBadge(trend.id)}`}
            >
              {trend.id}
            </Badge>

            {/* Trend Name + Progress */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium truncate">
                  {trend.name || TREND_LABELS[trend.id]}
                </span>
                <span className={`text-sm font-bold ${getScoreColor(trend.score)}`}>
                  {Math.round(trend.score)}%
                </span>
              </div>
              <div className="relative h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`absolute left-0 top-0 h-full rounded-full transition-all ${getProgressColor(trend.score)}`}
                  style={{ width: `${Math.min(100, trend.score)}%` }}
                />
              </div>
            </div>

            {/* Velocity */}
            <div className="flex items-center gap-1" title={`${trend.velocity}`}>
              {getVelocityIcon(trend.velocity)}
            </div>

            {/* Urgency Badge */}
            <div className="w-16">
              {getUrgencyBadge(trend.urgency, trend.score)}
            </div>

            {/* Drill-down arrow */}
            <ChevronRight className="w-4 h-4 text-gray-600" />
          </div>
        ))}

        {/* Legend */}
        <div className="flex items-center justify-between pt-2 border-t text-xs text-gray-600">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-green-500" /> Accelerating
            </span>
            <span className="flex items-center gap-1">
              <Minus className="w-3 h-3 text-gray-600" /> Stable
            </span>
            <span className="flex items-center gap-1">
              <TrendingDown className="w-3 h-3 text-amber-500" /> Decelerating
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-yellow-500" /> Power
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-blue-500" /> Attention
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-500" /> Money
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default TrendsRadarCompact;
