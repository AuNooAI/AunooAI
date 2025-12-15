/**
 * RecommendationCard - Display a strategic recommendation
 *
 * Shows:
 * - Title with urgency badge
 * - Description
 * - Trends addressed (clickable to drill down)
 * - Impact/Effort indicators
 */

import React from 'react';
import { AlertCircle, Clock, Calendar, Zap, Target, ArrowRight } from 'lucide-react';
import { Badge } from '../ui/badge';
import type { Recommendation } from '../../hooks/usePAM';
import { TREND_TO_PILLAR } from './TrendsRadarCompact';

interface RecommendationCardProps {
  recommendation: Recommendation;
  onTrendClick?: (trendId: string) => void;
  compact?: boolean;
}

const RecommendationCard: React.FC<RecommendationCardProps> = ({
  recommendation,
  onTrendClick,
  compact = false,
}) => {
  const getUrgencyConfig = (urgency: string) => {
    switch (urgency) {
      case 'immediate':
        return {
          label: 'Urgent',
          icon: <AlertCircle className="w-3 h-3" />,
          color: 'bg-red-100 text-red-700 border-red-200',
        };
      case 'near_term':
        return {
          label: 'Near-Term',
          icon: <Clock className="w-3 h-3" />,
          color: 'bg-yellow-100 text-yellow-700 border-yellow-200',
        };
      default:
        return {
          label: 'Medium-Term',
          icon: <Calendar className="w-3 h-3" />,
          color: 'bg-blue-100 text-blue-700 border-blue-200',
        };
    }
  };

  const getImpactColor = (level: string) => {
    switch (level) {
      case 'high':
        return 'text-green-600';
      case 'medium':
        return 'text-yellow-600';
      default:
        return 'text-gray-500';
    }
  };

  const getEffortColor = (level: string) => {
    switch (level) {
      case 'high':
        return 'text-red-600';
      case 'medium':
        return 'text-yellow-600';
      default:
        return 'text-green-600';
    }
  };

  const urgencyConfig = getUrgencyConfig(recommendation.urgency);

  // Parse addressesTrends to extract trend IDs (e.g., "T1", "T4")
  const trendIds = (recommendation.addressesTrends || []).filter((t) =>
    /^T[1-5]$/i.test(t)
  );

  const handleTrendClick = (e: React.MouseEvent, trendId: string) => {
    e.stopPropagation();
    if (onTrendClick) {
      onTrendClick(trendId.toUpperCase());
    }
  };

  const getPillarColor = (trendId: string) => {
    const pillar = TREND_TO_PILLAR[trendId.toUpperCase()];
    switch (pillar) {
      case 'power':
        return 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200';
      case 'attention':
        return 'bg-blue-100 text-blue-700 hover:bg-blue-200';
      case 'money':
        return 'bg-green-100 text-green-700 hover:bg-green-200';
      default:
        return 'bg-gray-100 text-gray-700';
    }
  };

  if (compact) {
    return (
      <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors">
        {/* Urgency indicator */}
        <Badge className={`${urgencyConfig.color} flex items-center gap-1 shrink-0`}>
          {urgencyConfig.icon}
          {urgencyConfig.label}
        </Badge>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 line-clamp-2">
            {recommendation.title}
          </p>

          {/* Trend links */}
          {trendIds.length > 0 && (
            <div className="flex items-center gap-1 mt-1">
              <span className="text-xs text-gray-500">Addresses:</span>
              {trendIds.map((t) => (
                <Badge
                  key={t}
                  variant="outline"
                  className={`text-xs cursor-pointer ${getPillarColor(t)}`}
                  onClick={(e) => handleTrendClick(e, t)}
                >
                  {t.toUpperCase()}
                </Badge>
              ))}
            </div>
          )}
        </div>

        {/* Impact/Effort mini indicators */}
        <div className="text-xs text-right shrink-0">
          <div className={getImpactColor(recommendation.impact)}>
            Impact: {recommendation.impact}
          </div>
          <div className={getEffortColor(recommendation.effort)}>
            Effort: {recommendation.effort}
          </div>
        </div>
      </div>
    );
  }

  // Full card view
  return (
    <div className="p-4 rounded-lg border bg-white hover:shadow-sm transition-shadow">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <Badge className={`${urgencyConfig.color} flex items-center gap-1`}>
              {urgencyConfig.icon}
              {urgencyConfig.label}
            </Badge>
            <Badge variant="outline" className="text-xs capitalize">
              {recommendation.dimension}
            </Badge>
          </div>
          <h4 className="font-medium text-gray-900">{recommendation.title}</h4>
        </div>
      </div>

      {/* Description */}
      <p className="text-sm text-gray-600 mb-3">{recommendation.description}</p>

      {/* Footer */}
      <div className="flex items-center justify-between">
        {/* Trend links */}
        {trendIds.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">Addresses:</span>
            {trendIds.map((t) => (
              <Badge
                key={t}
                variant="outline"
                className={`text-xs cursor-pointer ${getPillarColor(t)}`}
                onClick={(e) => handleTrendClick(e, t)}
              >
                {t.toUpperCase()} <ArrowRight className="w-3 h-3 ml-0.5" />
              </Badge>
            ))}
          </div>
        )}

        {/* Impact/Effort pills */}
        <div className="flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1">
            <Target className={`w-3 h-3 ${getImpactColor(recommendation.impact)}`} />
            <span className={getImpactColor(recommendation.impact)}>
              Impact: {recommendation.impact}
            </span>
          </span>
          <span className="flex items-center gap-1">
            <Zap className={`w-3 h-3 ${getEffortColor(recommendation.effort)}`} />
            <span className={getEffortColor(recommendation.effort)}>
              Effort: {recommendation.effort}
            </span>
          </span>
        </div>
      </div>

      {/* Rationale (if available) */}
      {recommendation.rationale && (
        <div className="mt-3 pt-3 border-t text-xs text-gray-500">
          <strong>Rationale:</strong> {recommendation.rationale}
        </div>
      )}
    </div>
  );
};

export default RecommendationCard;
