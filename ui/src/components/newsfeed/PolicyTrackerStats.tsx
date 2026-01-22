/**
 * Policy Tracker Stats Component
 * Displays KPI cards with overview statistics
 */

import { FileText, Calendar, BarChart3, Layers } from 'lucide-react';
import type { PolicyStats } from '../../services/policyTrackerApi';

interface PolicyTrackerStatsProps {
  stats: PolicyStats | null;
  loading: boolean;
}

export function PolicyTrackerStats({ stats, loading }: PolicyTrackerStatsProps) {
  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return 'N/A';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return dateStr;
    }
  };

  const kpiCards = [
    {
      label: 'Total Articles',
      value: stats?.total_articles?.toLocaleString() || '0',
      icon: FileText,
      color: 'text-blue-500',
      bgColor: 'bg-blue-50 dark:bg-blue-900/20',
    },
    {
      label: 'Date Range',
      value: stats?.date_range_start && stats?.date_range_end
        ? `${formatDate(stats.date_range_start)} - ${formatDate(stats.date_range_end)}`
        : 'N/A',
      icon: Calendar,
      color: 'text-green-500',
      bgColor: 'bg-green-50 dark:bg-green-900/20',
      isSmallText: true,
    },
    {
      label: 'Most Active Category',
      value: stats?.most_active_category || 'N/A',
      icon: BarChart3,
      color: 'text-purple-500',
      bgColor: 'bg-purple-50 dark:bg-purple-900/20',
    },
    {
      label: 'Multi-Category Articles',
      value: stats?.multi_category_count?.toLocaleString() || '0',
      subLabel: 'Articles with 3+ categories',
      icon: Layers,
      color: 'text-orange-500',
      bgColor: 'bg-orange-50 dark:bg-orange-900/20',
    },
  ];

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 animate-pulse"
          >
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-lg bg-gray-200 dark:bg-gray-700" />
              <div className="flex-1">
                <div className="h-3 w-20 bg-gray-200 dark:bg-gray-700 rounded mb-2" />
                <div className="h-6 w-24 bg-gray-200 dark:bg-gray-700 rounded" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {kpiCards.map((card) => (
        <div
          key={card.label}
          className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4"
        >
          <div className="flex items-start gap-3">
            <div className={`p-2 rounded-lg ${card.bgColor}`}>
              <card.icon className={`w-5 h-5 ${card.color}`} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-500 dark:text-gray-300 mb-1">
                {card.label}
              </p>
              <p
                className={`font-semibold text-gray-900 dark:text-gray-100 truncate ${
                  card.isSmallText ? 'text-sm' : 'text-lg'
                }`}
                title={card.value}
              >
                {card.value}
              </p>
              {card.subLabel && (
                <p className="text-xs text-gray-500 dark:text-gray-300 mt-0.5">
                  {card.subLabel}
                </p>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
