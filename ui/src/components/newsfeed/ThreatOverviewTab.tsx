/**
 * ThreatOverviewTab Component
 * Dashboard overview with stats cards and summary charts
 */

import { useEffect } from 'react';
import {
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  FileText,
  Users,
  Shield,
  Activity,
} from 'lucide-react';
import {
  type OverviewStats,
  type ThreatMapData,
  type SeverityLevel,
  type ThreatCategory,
  SEVERITY_COLORS,
  SEVERITY_LABELS,
  THREAT_CATEGORY_LABELS,
} from '../../services/threatIntelligenceApi';

interface ThreatOverviewTabProps {
  stats: OverviewStats | null;
  threats: ThreatMapData[];
  loading: boolean;
  onThreatClick: (threat: ThreatMapData) => void;
  onSeverityFilter: (level: SeverityLevel) => void;
  onCategoryFilter: (category: string) => void;
}

export function ThreatOverviewTab({
  stats,
  threats,
  loading,
  onThreatClick,
  onSeverityFilter,
  onCategoryFilter,
}: ThreatOverviewTabProps) {
  if (loading && !stats) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-500"></div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="text-center text-gray-500 dark:text-gray-400 py-12">
        No threat intelligence data available. Click "Update" to process articles.
      </div>
    );
  }

  const severityData = Object.entries(stats.by_severity || {}).map(([level, count]) => ({
    level: level as SeverityLevel,
    count,
    color: SEVERITY_COLORS[level as SeverityLevel],
    label: SEVERITY_LABELS[level as SeverityLevel],
  }));

  const typeData = Object.entries(stats.by_type || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([type, count]) => ({
      type: type as ThreatCategory,
      count,
      label: THREAT_CATEGORY_LABELS[type as ThreatCategory] || type,
    }));

  const totalBySeverity = severityData.reduce((acc, s) => acc + s.count, 0) || 1;

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 mb-1">
            <Shield className="w-4 h-4" />
            <span className="text-xs font-medium">Total Threats</span>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {stats.total_threats}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 mb-1">
            <Users className="w-4 h-4" />
            <span className="text-xs font-medium">Threat Actors</span>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {stats.total_actors}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 mb-1">
            <FileText className="w-4 h-4" />
            <span className="text-xs font-medium">Articles</span>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {stats.total_articles}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            {stats.recent_articles} this week
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 mb-1">
            <Activity className="w-4 h-4" />
            <span className="text-xs font-medium">New Threats</span>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {stats.new_threats}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">last 7 days</div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 text-red-500 mb-1">
            <TrendingUp className="w-4 h-4" />
            <span className="text-xs font-medium">Escalating</span>
          </div>
          <div className="text-2xl font-bold text-red-600 dark:text-red-400">
            {stats.escalating_count}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 text-green-500 mb-1">
            <TrendingDown className="w-4 h-4" />
            <span className="text-xs font-medium">Declining</span>
          </div>
          <div className="text-2xl font-bold text-green-600 dark:text-green-400">
            {stats.declining_count}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Severity Distribution */}
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Severity Distribution
          </h3>
          <div className="space-y-3">
            {severityData.map((item) => (
              <button
                key={item.level}
                onClick={() => onSeverityFilter(item.level)}
                className="w-full text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded p-1 -m-1 transition-colors"
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: item.color }}
                    />
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      {item.label}
                    </span>
                  </div>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {item.count}
                  </span>
                </div>
                <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${(item.count / totalBySeverity) * 100}%`,
                      backgroundColor: item.color,
                    }}
                  />
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Threat Types */}
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Threat Types
          </h3>
          <div className="space-y-2">
            {typeData.map((item, index) => {
              const maxCount = typeData[0]?.count || 1;
              return (
                <button
                  key={item.type}
                  onClick={() => onCategoryFilter(item.type)}
                  className="w-full text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded p-1 -m-1 transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      {item.label}
                    </span>
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {item.count}
                    </span>
                  </div>
                  <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-red-500 rounded-full transition-all"
                      style={{ width: `${(item.count / maxCount) * 100}%` }}
                    />
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Top Threats */}
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Top Threats
          </h3>
          <div className="space-y-3">
            {stats.top_threats?.slice(0, 6).map((threat) => (
              <button
                key={threat.id}
                onClick={() => {
                  const mapThreat = threats.find((t) => t.id === threat.id);
                  if (mapThreat) onThreatClick(mapThreat);
                }}
                className="w-full text-left p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {threat.threat_name}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className="px-2 py-0.5 text-xs font-medium rounded-full text-white"
                        style={{ backgroundColor: SEVERITY_COLORS[threat.severity_level] }}
                      >
                        {threat.severity_level.toUpperCase()}
                      </span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {THREAT_CATEGORY_LABELS[threat.threat_type] || threat.threat_type}
                      </span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {threat.article_count}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">articles</div>
                  </div>
                </div>
                {threat.threat_actor_name && (
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    Actor: {threat.threat_actor_name}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
